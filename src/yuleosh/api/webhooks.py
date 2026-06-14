# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""GitHub Webhook handler — receives push events and triggers CI.

Endpoint: POST /api/v1/webhooks/github
"""

import logging
from datetime import datetime

from . import json_ok, json_error, OSH_HOME

log = logging.getLogger("webhooks")


def handle_webhooks(method: str, path_tail: str = "", body: dict = None,
                     query: dict = None, handler=None, **kwargs):
    """Handle webhook-related API calls.

    POST /api/v1/webhooks/github — Receive GitHub push webhook and trigger CI.
    """
    if method != "POST":
        return json_error("Method not allowed. Use POST.", 405)

    if body is None:
        body = {}

    # Parse the provider from the path tail: "github" or similar
    provider = path_tail.strip("/") if path_tail else ""

    if provider != "github":
        return json_error(f"Unknown webhook provider: '{provider}'. Supported: github", 404)

    return _handle_github_push(body, handler)


def _handle_github_push(payload: dict, handler=None) -> tuple:
    """Process a GitHub push event payload and trigger CI Layer 1."""
    try:
        # Extract repository info
        repo = payload.get("repository", {})
        repo_name = repo.get("full_name", repo.get("name", "unknown"))

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

        # Trigger CI Layer 1
        ci_result = _trigger_ci(repo_name, branch, commit_hash, commit_message)

        return json_ok({
            "status": "received",
            "repository": repo_name,
            "branch": branch,
            "commit": commit_hash,
            "pusher": pusher_name,
            "ci_triggered": ci_result is not None,
            "ci_status": ci_result.get("status", "unknown") if ci_result else "skipped",
            "timestamp": datetime.now().isoformat(),
        })

    except Exception as e:
        log.error(f"Error processing GitHub webhook: {e}")
        # Return 200 anyway per GitHub best practices (don't retry on server errors)
        return json_ok({
            "status": "received",
            "error": str(e),
            "ci_triggered": False,
        })


def _trigger_ci(repo_name: str, branch: str, commit_hash: str,
                commit_message: str) -> dict:
    """Trigger CI Layer 1 pipeline for the given commit.

    Returns the CI result dict or None if CI could not be triggered.
    """
    try:
        # Import CI runner
        from yuleosh.ci.run import run_layer1

        # Prepare CI context
        project_dir = OSH_HOME

        # Run CI Layer 1
        success = run_layer1(project_dir)

        # Save CI result to store
        from yuleosh.store import Store
        store = Store()
        store.save_ci({
            "layer": 1,
            "commit": commit_hash or "webhook",
            "status": "passed" if success else "failed",
            "started_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "stages": [],
            "coverage": None,
            "errors": [] if success else ["CI Layer 1 failed"],
        })

        return {
            "status": "passed" if success else "failed",
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
    except ImportError as e:
        log.warning(f"CI module not available: {e}")
        return {
            "status": "skipped",
            "error": f"CI module not available: {e}",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"Failed to trigger CI: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
