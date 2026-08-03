#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
AI Preview Assessment API (PREVIEW-REQ-001 through PREVIEW-REQ-008).

Endpoints:
  POST /api/v1/preview/assess              — Submit code for analysis
  GET  /api/v1/preview/assess/<id>         — Poll analysis status
  DELETE /api/v1/preview/assess/<id>       — Discard result

Supports two input modes:
  1. ZIP upload via multipart/form-data
  2. Git repo URL via application/json

Analysis is purely static (no LLM calls, no hardware execution).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

from . import json_ok, json_error, read_body

# ── Thread-safe dict wrapper ──────────────────────────────────────────────

class _ThreadSafeDict:
    """A dict wrapper that serializes all access with a lock."""
    def __init__(self):
        self._dict: dict = {}
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            return self._dict.get(key, default)

    def clear(self):
        """Remove all entries (test isolation / state reset)."""
        with self._lock:
            self._dict.clear()

    def pop(self, key, default=None):
        with self._lock:
            return self._dict.pop(key, default)

    def __getitem__(self, key):
        with self._lock:
            return self._dict[key]

    def __setitem__(self, key, value):
        with self._lock:
            self._dict[key] = value

    def __delitem__(self, key):
        with self._lock:
            del self._dict[key]

    def __contains__(self, key):
        with self._lock:
            return key in self._dict

    def items(self):
        with self._lock:
            return list(self._dict.items())

    def keys(self):
        with self._lock:
            return list(self._dict.keys())

    def get_and_update(self, key, updater):
        """Atomically get an entry and apply an update function."""
        with self._lock:
            if key in self._dict:
                updater(self._dict[key])
                return self._dict[key]
            return None


# ── Configuration ───────────────────────────────────────────────────────

MAX_ZIP_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_CLONED_SIZE = 200 * 1024 * 1024  # 200 MB
CLONE_TIMEOUT = 120  # seconds
ANALYSIS_TIMEOUT = 300  # 5 minutes
RESULT_TTL = 24 * 3600  # 24 hours

# Zip-bomb limits (P2-6 / S-P1-03): member count, per-member expanded size
# and total expanded size are all capped BEFORE extraction, and symlink /
# absolute-path members are rejected (zip-slip defense in depth — stdlib
# already blocks traversal, but the preflight keeps resource use bounded).
MAX_ZIP_MEMBERS = 1000
MAX_ZIP_MEMBER_BYTES = 100 * 1024 * 1024  # 100 MB per member
MAX_ZIP_EXPANDED_BYTES = 500 * 1024 * 1024  # 500 MB total expanded

SUPPORTED_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}

# ── In-memory state — thread-safe ────────────────────────────────────────

_assessment_store = _ThreadSafeDict()
_repo_cache = _ThreadSafeDict()
_cleanup_timer: Optional[threading.Timer] = None


# ── Input validation ────────────────────────────────────────────────────

def _parse_multipart_body(handler: BaseHTTPRequestHandler) -> Optional[bytes]:
    """Extract binary file data from a multipart/form-data request."""
    content_type = handler.headers.get("Content-Type", "")
    content_length = int(handler.headers.get("Content-Length", 0))

    if content_length <= 0:
        return None

    if "multipart/form-data" not in content_type:
        return None

    raw = handler.rfile.read(content_length)
    return raw


def _extract_zip_from_multipart(raw: bytes, content_type: str) -> Optional[bytes]:
    """Extract the ZIP file content from a multipart body."""
    from io import BytesIO  # noqa: F401 (kept for parity; unused)

    # Parse the boundary from content-type
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break

    if not boundary:
        return None

    # Simple extraction: find the ZIP file content between boundaries
    boundary_bytes = f"--{boundary}".encode()
    parts = raw.split(boundary_bytes)

    for part in parts:
        if b"Content-Disposition: form-data" not in part:
            continue
        if b'name="file"' not in part and b"filename=" not in part:
            continue

        # Find the actual file content
        headers_end = part.find(b"\r\n\r\n")
        if headers_end == -1:
            continue

        file_data = part[headers_end + 4:]
        # Strip trailing boundary junk
        trailing = file_data.rfind(b"\r\n--")
        if trailing > 0:
            file_data = file_data[:trailing]
        file_data = file_data.rstrip(b"\r\n-")

        return file_data

    return None


def _is_valid_zip(data: bytes) -> bool:
    """Check if data is a valid ZIP archive."""
    return data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06")


def _validate_git_url(url: str) -> tuple[bool, str]:
    """Validate a git URL. Returns (valid, error_message)."""
    if not url.startswith("https://"):
        return False, "Only HTTPS git URLs are supported."

    # Check supported hosts
    parsed = re.match(r"https://([^/]+)/", url)
    if not parsed:
        return False, "Invalid git URL format."

    host = parsed.group(1)
    # Remove port if present
    host = host.split(":")[0]

    if host not in SUPPORTED_GIT_HOSTS:
        return False, f"Unsupported git host '{host}'. Supported hosts: {', '.join(SUPPORTED_GIT_HOSTS)}"

    return True, ""


# ── Analysis execution ──────────────────────────────────────────────────

def _run_analysis(source_dir: str | Path) -> dict:
    """Run the code analysis in a thread-safe manner.

    Returns the assessment report dict.
    """
    from yuleosh.preview.analyzer import analyze_directory
    from yuleosh.preview.reporter import build_assessment_report

    analysis = analyze_directory(source_dir)
    report = build_assessment_report(analysis)
    return report


def _analyze_in_background(preview_id: str, source_dir: Path):
    """Run analysis in a background thread and store the result."""
    import logging
    log = logging.getLogger("api.preview")

    def _do_work():
        try:
            report = _run_analysis(source_dir)
            entry = _assessment_store.get(preview_id)
            if entry:
                entry["status"] = "completed"
                entry["report"] = report
                entry["completed_at"] = time.time()
                log.info("Preview %s analysis completed", preview_id)
        except Exception as e:
            log.error("Preview %s analysis failed: %s", preview_id, e)
            entry = _assessment_store.get(preview_id)
            if entry:
                entry["status"] = "failed"
                entry["error"] = str(e)
                entry["completed_at"] = time.time()
        finally:
            # Clean up temp directory after 30 minutes (PREVIEW-REQ-008)
            def _cleanup():
                try:
                    if source_dir.exists():
                        shutil.rmtree(str(source_dir))
                        log.info("Cleaned up temp dir: %s", source_dir)
                except Exception:
                    pass

            t = threading.Timer(1800, _cleanup)
            t.daemon = True
            t.start()

    thread = threading.Thread(target=_do_work, daemon=True)
    thread.start()


def _handle_zip_upload(preview_id: str, zip_data: bytes, handler) -> tuple:
    """Handle ZIP upload analysis (PREVIEW-REQ-001A)."""
    # Validate size
    if len(zip_data) > MAX_ZIP_SIZE:
        return json_error({
            "error": "file_too_large",
            "max_size_mb": MAX_ZIP_SIZE // (1024 * 1024),
        }, 413)

    # Validate ZIP format
    if not _is_valid_zip(zip_data):
        return json_error({
            "error": "invalid_archive",
            "message": "Uploaded file is not a valid ZIP archive.",
        }, 400)

    # Extract to temp directory
    import zipfile
    import io
    import stat

    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="yuleosh_preview_"))
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            infos = zf.infolist()

            # P2-6 (S-P1-03): zip-bomb preflight before any extraction.
            if len(infos) > MAX_ZIP_MEMBERS:
                return json_error({
                    "error": "archive_too_large",
                    "message": f"ZIP contains too many members (max {MAX_ZIP_MEMBERS}).",
                }, 413)
            total_expanded = 0
            for info in infos:
                if stat.S_ISLNK(info.external_attr >> 16):
                    return json_error({
                        "error": "invalid_archive",
                        "message": "ZIP members must not be symlinks.",
                    }, 400)
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in Path(name).parts:
                    return json_error({
                        "error": "invalid_archive",
                        "message": "ZIP contains an unsafe member path.",
                    }, 400)
                if info.file_size > MAX_ZIP_MEMBER_BYTES:
                    return json_error({
                        "error": "archive_too_large",
                        "message": f"ZIP member too large (max {MAX_ZIP_MEMBER_BYTES // (1024*1024)} MB).",
                    }, 413)
                total_expanded += info.file_size
                if total_expanded > MAX_ZIP_EXPANDED_BYTES:
                    return json_error({
                        "error": "archive_too_large",
                        "message": f"ZIP expands beyond {MAX_ZIP_EXPANDED_BYTES // (1024*1024)} MB.",
                    }, 413)

            zf.extractall(str(temp_dir))
    except zipfile.BadZipFile:
        return json_error({
            "error": "invalid_archive",
            "message": "Uploaded file is not a valid ZIP archive.",
        }, 400)

    # Store entry
    _assessment_store[preview_id] = {
        "status": "analyzing",
        "source_dir": str(temp_dir),
        "input_type": "zip",
        "created_at": time.time(),
        "estimated_remaining_seconds": 30,
    }

    # Start background analysis
    _analyze_in_background(preview_id, temp_dir)

    # Fix (v3.4.2b): json_ok() accepts a single argument — passing 202 raised
    # TypeError and broke the analyzing response at runtime.
    return {"ok": True, "data": {
        "preview_id": preview_id,
        "status": "analyzing",
        "estimated_seconds": 30,
    }}, 202


def _handle_git_url(preview_id: str, repo_url: str, handler) -> tuple:
    """Handle git repo URL analysis (PREVIEW-REQ-001B)."""
    # Validate git host
    valid, err_msg = _validate_git_url(repo_url)
    if not valid:
        return json_error({
            "error": err_msg if "supported" not in err_msg else "unsupported_git_host",
            "message": err_msg,
            "supported_hosts": list(SUPPORTED_GIT_HOSTS),
        }, 400)

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="yuleosh_preview_"))

    # Store entry immediately
    _assessment_store[preview_id] = {
        "status": "analyzing",
        "source_dir": str(temp_dir),
        "repo_url": repo_url,
        "input_type": "git",
        "created_at": time.time(),
        "estimated_remaining_seconds": 60,
    }

    # Clone in background
    def _clone_and_analyze():
        import logging
        log = logging.getLogger("api.preview")

        try:
            log.info("Cloning %s to %s", repo_url, temp_dir)

            # Clone with timeout
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(temp_dir)],
                capture_output=True, text=True,
                timeout=CLONE_TIMEOUT,
            )

            if result.returncode != 0:
                entry = _assessment_store.get(preview_id)
                if entry:
                    entry["status"] = "failed"
                    entry["error"] = f"Git clone failed: {result.stderr[:500]}"
                return

            # Check size
            total_size = _get_dir_size(temp_dir)
            if total_size > MAX_CLONED_SIZE:
                entry = _assessment_store.get(preview_id)
                if entry:
                    entry["status"] = "failed"
                    entry["error"] = f"Repository too large ({total_size // (1024*1024)} MB, max {MAX_CLONED_SIZE // (1024*1024)} MB)"
                shutil.rmtree(str(temp_dir))
                return

            # Run analysis
            _analyze_in_background(preview_id, temp_dir)

        except subprocess.TimeoutExpired:
            entry = _assessment_store.get(preview_id)
            if entry:
                entry["status"] = "failed"
                entry["error"] = f"Git clone timeout after {CLONE_TIMEOUT}s"
            try:
                shutil.rmtree(str(temp_dir))
            except Exception:
                pass
        except Exception as e:
            entry = _assessment_store.get(preview_id)
            if entry:
                entry["status"] = "failed"
                entry["error"] = str(e)
            try:
                shutil.rmtree(str(temp_dir))
            except Exception:
                pass

    thread = threading.Thread(target=_clone_and_analyze, daemon=True)
    thread.start()

    # Fix (v3.4.2b): json_ok() accepts a single argument — passing 202 raised
    # TypeError and broke the analyzing response at runtime.
    return {"ok": True, "data": {
        "preview_id": preview_id,
        "status": "analyzing",
        "estimated_seconds": 60,
    }}, 202


def _get_dir_size(path: Path) -> int:
    """Get total size of directory in bytes."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total


# ── Rate limiter ────────────────────────────────────────────────────────

# P1-4 (W-03 / S-P1-01): thread-safe state — the read-modify-write of the
# per-IP timestamp list is atomic under _ThreadSafeDict's lock, and stale
# IP entries are purged opportunistically (bounded memory growth).
_preview_request_log = _ThreadSafeDict()
_PREVIEW_AUTH_LIMIT = 3  # unauth: 3 per 24h
_PREVIEW_AUTHED_LIMIT = 20  # authed: 20 per 24h
_PREVIEW_WINDOW = 24 * 3600  # 24 hours
_PREVIEW_LOG_MAX_IPS = 5000  # hard cap before opportunistic cleanup


def _check_preview_rate_limit(ip: str, is_authenticated: bool = False) -> tuple[bool, int]:
    """Check rate limit per IP (PREVIEW-REQ-005).  Atomic under lock."""
    now = time.time()
    limit = _PREVIEW_AUTHED_LIMIT if is_authenticated else _PREVIEW_AUTH_LIMIT

    with _preview_request_log._lock:
        # NOTE: use the underlying dict directly — the public accessors
        # re-acquire the same (non-reentrant) lock and would deadlock.
        ts_list = _preview_request_log._dict.get(ip) or []
        # Purge old entries
        ts_list = [t for t in ts_list if now - t < _PREVIEW_WINDOW]

        if len(ts_list) >= limit:
            oldest = ts_list[0]
            retry_after = int(_PREVIEW_WINDOW - (now - oldest)) + 1
            return False, retry_after

        ts_list.append(now)
        _preview_request_log._dict[ip] = ts_list

        # Opportunistic cleanup: when the tracking table grows large, drop
        # IPs whose every timestamp is outside the window (bounded memory).
        if len(_preview_request_log._dict) > _PREVIEW_LOG_MAX_IPS:
            cutoff = now - _PREVIEW_WINDOW
            stale = [
                k for k, v in _preview_request_log._dict.items()
                if not any(t > cutoff for t in v)
            ]
            for k in stale:
                _preview_request_log._dict.pop(k, None)

    return True, 0


def _is_authed(handler) -> bool:
    """Real authentication check for preview rate-limit tiers (P1-4).

    Previously any header PRESENCE (Authorization / X-API-Key) granted the
    higher authed quota — a fake/malformed header was enough.  Now:
      - Bearer JWT must decode and resolve to a live session;
      - X-API-Key must match a non-revoked stored key (sha256).
    Fail closed on any error.
    """
    try:
        auth = handler.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            from yuleosh.ui.auth_extended import get_session_user
            return get_session_user(auth[7:]) is not None
        key = handler.headers.get("X-API-Key", "")
        if key:
            from yuleosh.store import Store
            rec = Store().get_api_key_by_hash(hashlib.sha256(key.encode("utf-8")).hexdigest())
            return rec is not None and not rec.get("revoked")
    except Exception:
        return False
    return False


def _get_user_key(handler) -> str:
    """Derive the preview-cache owner key from the request identity (W-6).

    SEC-W4 / Fix 9: the repo cache used to be keyed by URL only, so any
    caller who knew a repo URL could hit another user's cached analysis
    (the report leaks repository structure).  The cache key is now
    ``(user_key, url_hash)``:
      - authenticated session  -> ``u:<user_id>``  (F2.1: 认证收敛后
        一律用 user_id — A1 统一 verify 后 JWT 请求恒走此分支)
      - valid API key          -> ``k:<key_id>``
      - anonymous              -> ``ip:<sha256(client_ip)>`` (无凭据
        请求的隔离维度；NAT 同 IP 仍共享 — 已知限制注释于 W-6)

    Same identity must always derive the same key (deterministic).
    """
    try:
        auth = handler.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            from yuleosh.ui.auth_extended import get_session_user
            u = get_session_user(auth[7:])
            if u and u.get("user_id") is not None:
                return f"u:{u['user_id']}"
        key = handler.headers.get("X-API-Key", "")
        if key:
            from yuleosh.store import Store
            rec = Store().get_api_key_by_hash(
                hashlib.sha256(key.encode("utf-8")).hexdigest()
            )
            if rec is not None and not rec.get("revoked"):
                return f"k:{rec['id']}"
    except Exception:
        # Fail closed to the anonymous (IP) dimension.
        pass
    ip = handler.client_address[0]
    return f"ip:{hashlib.sha256(ip.encode('utf-8')).hexdigest()}"


# ── Cache by repo URL ──────────────────────────────────────────────────

def _get_cached_preview(repo_url: str, user_key: str) -> Optional[dict]:
    """Check if a cached assessment result exists (PREVIEW-REQ-007).

    W-6 (SEC-W4 / Fix 9): the key is now ``(user_key, url_hash)`` — a
    cached analysis is only visible to the SAME user (or same anonymous IP)
    who created it.  Cross-user hits are impossible even when the repo URL
    is identical and the result is fresh.
    """
    url_hash = hashlib.sha256(repo_url.encode()).hexdigest()
    if (user_key, url_hash) in _repo_cache:
        preview_id = _repo_cache[(user_key, url_hash)]
        entry = _assessment_store.get(preview_id)
        if entry and entry.get("status") == "completed":
            age = time.time() - entry.get("completed_at", 0)
            if age < RESULT_TTL:
                return {
                    "preview_id": preview_id,
                    "cached": True,
                    "status": "completed",
                    "report": entry.get("report"),
                }
    return None


# ── Cleanup ─────────────────────────────────────────────────────────────

def _cleanup_expired_results():
    """Periodic cleanup of expired assessment results (PREVIEW-REQ-006)."""
    now = time.time()
    expired = []
    for pid, entry in list(_assessment_store.items()):
        created = entry.get("created_at", 0)
        if now - created > RESULT_TTL:
            # Clean up source directory if it still exists
            src_dir = entry.get("source_dir")
            if src_dir:
                try:
                    p = Path(src_dir)
                    if p.exists():
                        shutil.rmtree(str(p))
                except Exception:
                    pass
            expired.append(pid)

    for pid in expired:
        del _assessment_store[pid]

    # Schedule next cleanup
    global _cleanup_timer
    _cleanup_timer = threading.Timer(3600, _cleanup_expired_results)
    _cleanup_timer.daemon = True
    _cleanup_timer.start()


# ── Handler ─────────────────────────────────────────────────────────────

def handle_preview(method: str, path_tail: str, body: dict, query: dict,
                   handler: BaseHTTPRequestHandler) -> tuple | None:
    """Route handler for /api/v1/preview/assess* endpoints.

    POST /api/v1/preview/assess            — Submit for analysis
    GET  /api/v1/preview/assess/<id>        — Poll status / get report
    DELETE /api/v1/preview/assess/<id>      — Discard result
    """

    ip = handler.client_address[0]

    # Parse path
    parts = [p for p in path_tail.split("/") if p]
    if parts and parts[0] == "assess":
        parts = parts[1:]
    sub_id = parts[0] if parts else None

    if method == "DELETE" and sub_id:
        # DELETE /api/v1/preview/assess/<id> (PREVIEW-REQ-006)
        if sub_id in _assessment_store:
            entry = _assessment_store[sub_id]
            src_dir = entry.get("source_dir")
            if src_dir:
                try:
                    p = Path(src_dir)
                    if p.exists():
                        shutil.rmtree(str(p))
                except Exception:
                    pass
            del _assessment_store[sub_id]
            return json_ok({"message": "Assessment result discarded."})
        return json_error("Assessment not found", 404)

    if method == "GET" and sub_id:
        # GET /api/v1/preview/assess/<id> (PREVIEW-REQ-003)
        entry = _assessment_store.get(sub_id)
        if not entry:
            return json_error("Assessment not found (may have expired)", 404)

        status = entry["status"]
        if status == "analyzing":
            elapsed = time.time() - entry.get("created_at", time.time())
            remaining = max(5, int(entry.get("estimated_remaining_seconds", 60) - elapsed))
            return json_ok({
                "preview_id": sub_id,
                "status": "analyzing",
                "estimated_remaining_seconds": remaining,
            })
        elif status == "completed":
            return json_ok({
                "preview_id": sub_id,
                "status": "completed",
                "report": entry.get("report"),
            })
        else:
            return json_ok({
                "preview_id": sub_id,
                "status": "failed",
                "error": entry.get("error", "Unknown error"),
            })

    if method == "POST":
        # POST /api/v1/preview/assess (PREVIEW-REQ-001)
        content_type = handler.headers.get("Content-Type", "")

        # Rate limiting (PREVIEW-REQ-005)
        is_authed = _is_authed(handler)
        allowed, retry_after = _check_preview_rate_limit(ip, is_authed)
        if not allowed:
            return json_error({
                "error": "rate_limited",
                "message": "Preview assessment limit reached. Sign up for more.",
            }, 429)

        preview_id = f"prev-{uuid.uuid4().hex[:12]}"

        # Check for ZIP upload
        if "multipart/form-data" in content_type:
            content_length = int(handler.headers.get("Content-Length", 0))
            raw_data = handler.rfile.read(content_length)
            zip_data = _extract_zip_from_multipart(raw_data, content_type)

            if zip_data is None:
                return json_error({
                    "error": "input_required",
                    "message": "Provide 'file' field with a .zip archive in multipart/form-data.",
                }, 400)

            return _handle_zip_upload(preview_id, zip_data, handler)

        # Check for JSON body with repo_url
        elif "application/json" in content_type or not content_type:
            repo_url = body.get("repo_url") if body else None
            if repo_url:
                # W-6 (SEC-W4): cache is owner-scoped — key derivation must
                # be identical on the hit and the store paths.
                user_key = _get_user_key(handler)
                # Check cache (PREVIEW-REQ-007)
                cached = _get_cached_preview(repo_url, user_key)
                if cached:
                    return json_ok(cached)

                result = _handle_git_url(preview_id, repo_url, handler)

                # Cache the result
                url_hash = hashlib.sha256(repo_url.encode()).hexdigest()
                _repo_cache[(user_key, url_hash)] = preview_id

                return result

            # Neither file nor repo_url provided
            return json_error({
                "error": "input_required",
                "message": "Provide either 'file' (ZIP upload) or 'repo_url' (git URL).",
            }, 400)

        return json_error({
            "error": "input_required",
            "message": "Provide either 'file' (ZIP upload) or 'repo_url' (git URL).",
        }, 400)

    return json_error("Method not allowed", 405)


# Start cleanup timer on import
_cleanup_timer = threading.Timer(3600, _cleanup_expired_results)
_cleanup_timer.daemon = True
_cleanup_timer.start()
