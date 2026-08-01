# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""GitHub Webhook handler — receives push events and triggers pipeline.

Enhancements:
  - Uses pipeline trigger API (POST /api/v1/pipeline/trigger) instead of direct CI
  - Maps repo name to project type (yuleASR → autosar template)
  - Pushes pipeline result to dashboard

Endpoint: POST /api/v1/webhooks/github
"""

import hmac
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import json_ok, json_error, OSH_HOME

log = logging.getLogger("webhooks")

# GitHub webhook secret — read from environment.  When unset, webhook
# delivery is refused (fail-closed).
WEBHOOK_SECRET_ENV = "YULEOSH_GITHUB_WEBHOOK_SECRET"


def _verify_github_signature(payload: Optional[bytes], signature_header: str) -> bool:
    """Verify X-Hub-Signature-256 HMAC-SHA256 against the raw payload.

    Fail-closed: returns False when the secret is not configured, the
    signature header is missing/malformed, or the HMAC does not match.
    Comparisons use hmac.compare_digest (constant-time).
    """
    secret = os.environ.get(WEBHOOK_SECRET_ENV, "")
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    if payload is None:
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header[len("sha256="):].strip(), expected)


def _read_raw_body(handler) -> bytes:
    """Read the raw request body bytes for signature verification."""
    # Prefer the body buffered by api.read_body (router flow) — re-reading
    # rfile after the router consumed it would return empty bytes.
    raw = getattr(handler, "_raw_body", None)
    if raw is not None:
        return raw
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except (ValueError, TypeError, AttributeError):
        return b""
    try:
        return handler.rfile.read(length) if length > 0 else b""
    except Exception:
        return b""

# Repo → project type mapping
REPO_PROJECT_MAP = {
    "yuleasr": "autosar",
    "yuleASR": "autosar",
    "yuleosh": "generic-embedded-c",
    "yuleOSH": "generic-embedded-c",
}

# Repo → project root path mapping
REPO_PATH_MAP: dict[str, str] = {}


def _build_repo_path_map():
    """Build a mapping of known repo names to their on-disk paths."""
    global REPO_PATH_MAP
    candidates = {
        "yuleasr": os.path.expanduser("~/.openclaw/workspace/yuleASR"),
        "yuleASR": os.path.expanduser("~/.openclaw/workspace/yuleASR"),
        "yuleosh": os.path.expanduser("~/.openclaw/workspace/tasks/yuleOSH"),
        "yuleOSH": os.path.expanduser("~/.openclaw/workspace/tasks/yuleOSH"),
    }
    for name, path in candidates.items():
        if os.path.isdir(path):
            REPO_PATH_MAP[name] = path


# Build once on import
_build_repo_path_map()


def handle_webhooks(method: str, path_tail: str = "", body: dict = None,
                     query: dict = None, handler=None, **kwargs):
    """Handle webhook-related API calls.

    POST /api/v1/webhooks/github — Receive GitHub push webhook and trigger pipeline.

    Security (P0): every delivery must carry a valid X-Hub-Signature-256
    HMAC computed with YULEOSH_GITHUB_WEBHOOK_SECRET.  Missing secret,
    missing/malformed signature, or HMAC mismatch → 401 (fail-closed).
    """
    if method != "POST":
        return json_error("Method not allowed. Use POST.", 405)

    provider = (path_tail or "").strip("/")
    if provider != "github":
        return json_error(f"Unknown webhook provider: '{provider}'. Supported: github", 404)

    if handler is None:
        return json_error("Webhook requires an HTTP handler", 400)

    raw = _read_raw_body(handler)
    signature = ""
    headers = getattr(handler, "headers", {})
    if callable(getattr(headers, "get", None)):
        signature = headers.get("X-Hub-Signature-256", "") or ""
    elif isinstance(headers, dict):
        signature = headers.get("X-Hub-Signature-256", "") or ""

    if not _verify_github_signature(raw, signature):
        log.warning("Webhook rejected: invalid or missing X-Hub-Signature-256")
        return json_error("Invalid webhook signature", 401)

    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return json_error("Invalid JSON payload", 400)

    return _handle_github_push(parsed, handler)


def _handle_github_push(payload: dict, handler=None) -> tuple:
    """Process a GitHub push event payload and trigger pipeline via API."""
    try:
        # Extract repository info
        repo = payload.get("repository", {})
        repo_name = repo.get("full_name", repo.get("name", "unknown"))
        repo_url = repo.get("clone_url", repo.get("html_url", ""))

        # Extract branch info from ref (refs/heads/main)
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else "unknown"

        # Extract commit info
        head_commit = payload.get("head_commit", {})
        commit_hash = head_commit.get("id", "")[:8] if head_commit.get("id") else ""
        commit_message = head_commit.get("message", "")
        pusher = payload.get("pusher", {})
        pusher_name = pusher.get("name", "unknown")

        log.info(
            f"GitHub push: repo={repo_name}, branch={branch}, "
            f"commit={commit_hash}, pusher={pusher_name}"
        )

        # Determine project type and project dir from repo name
        short_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        project_type = REPO_PROJECT_MAP.get(short_name, "generic-embedded-c")
        project_dir = REPO_PATH_MAP.get(short_name, OSH_HOME)

        # Map yuleASR → autosar template
        pipeline_type = "full"
        if project_type == "autosar":
            pipeline_type = "full"
        elif project_type == "generic-embedded-c":
            pipeline_type = "ci"
            project_dir = OSH_HOME

        # Trigger pipeline using the async runner directly
        pipeline_result = _trigger_pipeline(
            project_dir=project_dir,
            repo_name=repo_name,
            project_type=project_type,
            branch=branch,
            commit_hash=commit_hash,
            commit_message=commit_message,
        )

        # Push result to dashboard
        if pipeline_result and pipeline_result.get("job_id"):
            _push_to_dashboard(
                job_id=pipeline_result["job_id"],
                repo_name=repo_name,
                branch=branch,
                commit_hash=commit_hash,
                project_type=project_type,
            )

        return json_ok({
            "status": "received",
            "repository": repo_name,
            "branch": branch,
            "commit": commit_hash,
            "pusher": pusher_name,
            "project_type": project_type,
            "pipeline_triggered": pipeline_result is not None,
            "job_id": pipeline_result.get("job_id") if pipeline_result else None,
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        log.error(f"Error processing GitHub webhook: {e}", exc_info=True)
        # Return 200 per GitHub best practices (don't retry on server errors)
        return json_ok({
            "status": "received",
            "error": str(e),
            "pipeline_triggered": False,
        })


def _trigger_pipeline(project_dir: str, repo_name: str, project_type: str,
                      branch: str, commit_hash: str, commit_message: str) -> Optional[dict]:
    """Trigger yuleOSH pipeline for the given commit.

    Uses the async pipeline runner directly (same as POST /api/v1/pipeline/trigger).
    Returns job info dict or None on failure.
    """
    try:
        from yuleosh.pipeline.async_runner import submit_pipeline, submit_full_pipeline

        # Determine pipeline type based on project type
        if project_type == "autosar":
            # Full pipeline for AUTOSAR projects: ARXML → RTE → CI → MISRA
            job_id = submit_full_pipeline(
                project_dir=project_dir,
                config_json=json.dumps({
                    "trigger": "webhook",
                    "repo": repo_name,
                    "branch": branch,
                    "commit": commit_hash,
                    "message": commit_message,
                    "project_type": project_type,
                }),
            )
            pipeline_type = "full"
        else:
            # CI layer pipeline for embedded projects
            job_id = submit_pipeline(
                project_dir=project_dir,
                layer=1,  # Start with Layer 1
            )
            pipeline_type = "ci"

        if not job_id:
            return None

        # Save webhook trigger to store
        try:
            from yuleosh.store import Store
            store = Store()
            store.save_ci({
                "layer": 0,
                "commit": commit_hash or "webhook",
                "status": "queued",
                "job_id": job_id,
                "repo": repo_name,
                "branch": branch,
                "project_type": project_type,
                "started_at": datetime.now().isoformat(),
            })
        except Exception as store_err:
            log.debug("Failed to save webhook trigger to store: %s", store_err)

        return {
            "job_id": job_id,
            "type": pipeline_type,
            "status": "queued",
        }

    except ImportError as e:
        log.warning(f"Pipeline runner not available: {e}")
        return None
    except Exception as e:
        log.error(f"Failed to trigger pipeline: {e}")
        return None


def _push_to_dashboard(job_id: str, repo_name: str, branch: str,
                       commit_hash: str, project_type: str) -> None:
    """Push pipeline trigger event to dashboard store.

    Creates a dashboard activity entry so the dashboard can display
    real-time webhook-triggered pipeline runs.
    """
    try:
        dashboard_entry = {
            "event": "webhook_push",
            "job_id": job_id,
            "repository": repo_name,
            "branch": branch,
            "commit": commit_hash,
            "project_type": project_type,
            "timestamp": datetime.now().isoformat(),
            "status": "queued",
        }

        # Store in .yuleosh/reports/
        reports_dir = Path(OSH_HOME) / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        webhook_log_path = reports_dir / "webhook-triggers.jsonl"
        with open(webhook_log_path, "a") as f:
            f.write(json.dumps(dashboard_entry) + "\n")

        log.info("Dashboard webhook event pushed: job=%s repo=%s", job_id, repo_name)

    except Exception as e:
        log.debug("Failed to push to dashboard: %s", e)
