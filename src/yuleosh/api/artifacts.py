#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Artifacts API — pipeline stage artifact management (design doc 模块 ④).

Serves REAL data only, scanned from ``OSH_HOME/.osh/sessions/<run_id>/``
directories (each pipeline run = one session dir).  No mock fallback:
when there is nothing on disk the endpoints return an empty list plus a
``note`` explaining the absence — fabricated demo rows are forbidden.

Endpoints (mounted at /api/v1/artifacts/ in the main server router):

    GET /api/v1/artifacts/list?project=xxx         — artifact tree per run
    GET /api/v1/artifacts/preview?run=xxx&file=xxx — read-only file preview
    GET /api/v1/artifacts/evidence-pack?run=xxx    — evidence pack file list

Security (preview): the requested file is resolved with
``Path.resolve()`` and must remain inside the session directory —
``../`` traversal (or any symlink escape) is rejected with 403.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Iterator, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.artifacts")

# Repository root — OSH_HOME env var wins, falls back to the repo root
# so ``.osh/sessions`` resolves correctly in dev.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

# Preview cap: files larger than this are truncated (never streamed whole).
MAX_PREVIEW_BYTES = 100 * 1024  # 100 KB

# Previewable file types (Markdown / JSON / plain text).
PREVIEW_EXTS = {
    "md", "markdown", "json", "txt", "log", "yaml", "yml", "toml",
    "ini", "cfg", "conf", "csv", "xml", "html", "htm", "rst", "adoc",
    "py", "c", "h", "sh",
}

# Files that are metadata, not artifacts (never listed as stage output).
_METADATA_FILES = {"session.json"}

# 产出物总览只展示 ASPICE 文档证据（用户要求：不要列出每个 commit 的测试、
# 不要配置文件，只要 ASPICE 流程产出的文档）。
# - 保留：md / html / pdf / docx / rst / adoc（正式的文档载体）
# - 过滤：json / xml / yaml / toml / lock / csv / txt / log / 其它
#   （中间步骤产物、测试 runner 报告、原始 LLM 输出、配置/清单文件）
_ASPICE_DOCUMENT_EXTS = {"md", "html", "htm", "pdf", "docx", "rst", "adoc"}


class _PathTraversal(Exception):
    """Raised when a requested artifact path escapes its session directory."""


def _sessions_root() -> Path:
    """Primary root directory holding per-run session folders."""
    return Path(OSH_HOME) / ".osh" / "sessions"


def _sessions_roots() -> list[Path]:
    """All roots that may contain per-run session dirs.

    Primary: ``OSH_HOME/.osh/sessions``.  PLUS every ``.osh/sessions`` found
    by recursively walking OSH_HOME (bounded depth) so pipeline runs scoped
    to a sub-project directory (``OSH_HOME=<project>``) remain discoverable
    from the backend's ``OSH_HOME`` — e.g. a GPIO demo run under
    ``templates/gpio-led-chaser/.osh/sessions`` (depth-2) shows up when the
    server's ``OSH_HOME`` is the repo root.  ``_iter_sessions`` de-dups by
    resolved path, so overlapping roots are harmless.
    """
    roots: list[Path] = [_sessions_root()]
    home = Path(OSH_HOME)
    if home.is_dir():
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv",
                ".tox", "dist", "build", ".yuleosh", "frontend", ".osh"}
        try:
            for root, dirs, _files in os.walk(home):
                root_path = Path(root)
                rel_depth = (
                    len(root_path.relative_to(home).parts)
                    if root_path != home else 0
                )
                # 剪枝：无关大目录不进入；深度 > 5 不再下钻
                dirs[:] = [d for d in dirs if d not in skip]
                if rel_depth > 5:
                    dirs[:] = []
                    continue
                cand = root_path / ".osh" / "sessions"
                if cand.is_dir():
                    roots.append(cand)
        except OSError:
            pass
    return roots


def _q(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value (tolerates parse_qs list values)."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return val or default


def _safe_run_id(run_id: str) -> bool:
    """Reject run ids that could address paths outside the sessions dir."""
    return bool(run_id) and run_id not in (".", "..") \
        and "/" not in run_id and "\\" not in run_id


def _session_dir(run_id: str) -> Optional[Path]:
    """Return the session directory for a run, or None when unknown.

    Searches every known session root (primary + sub-project dirs) so a
    run scoped to a project directory is still resolvable by run id.
    """
    if not _safe_run_id(run_id):
        return None
    for root in _sessions_roots():
        d = root / run_id
        if d.is_dir():
            return d
    return None


def _session_meta(session_dir: Path) -> dict:
    """Parse session.json for a run; {} when absent/corrupt (no crash)."""
    try:
        meta = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        return meta if isinstance(meta, dict) else {}
    except Exception:
        log.debug("Unreadable session.json in %s — treated as absent", session_dir)
        return {}


def _iter_sessions() -> Iterator[tuple[str, Path, dict]]:
    """Yield (run_id, session_dir, session_meta) for every session dir.

    Scans all session roots (primary + sub-project dirs); de-duplicates by
    resolved path so a session found under two roots is yielded once.
    """
    seen: set[Path] = set()
    for root in _sessions_roots():
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            key = d.resolve()
            if key in seen:
                continue
            seen.add(key)
            yield d.name, d, _session_meta(d)


def _session_matches_project(meta: dict, project: str) -> bool:
    """Filter sessions by project fields in session.json (exact match)."""
    if not project:
        return True
    for key in ("project", "project_id", "project_name"):
        val = meta.get(key)
        if val is not None and str(val) == project:
            return True
    return False


def _artifact_files(session_dir: Path) -> list[dict]:
    """List artifact files in a session dir (metadata + non-document files excluded).

    Returns ``[{path, name, size, ext}]`` with ``path`` relative to the
    session directory, sorted for stable output.

    只保留 ASPICE 流程文档证据（见 ``_ASPICE_DOCUMENT_EXTS``）：.json / .xml /
    .yaml / .toml / .lock / .csv / .txt / .log 等中间产物与配置文件不在
    产出物总览展示。session.json 仍走 ``_METADATA_FILES`` 排除。
    """
    files = []
    for p in sorted(session_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(session_dir)
        if rel.as_posix() in _METADATA_FILES:
            continue
        ext = p.suffix.lstrip(".").lower()
        if ext not in _ASPICE_DOCUMENT_EXTS:
            continue
        files.append({
            "path": rel.as_posix(),
            "name": p.name,
            "size": p.stat().st_size,
            "ext": ext,
        })
    return files


def _resolve_within(session_dir: Path, rel_path: str) -> Path:
    """Resolve an artifact path and enforce it stays inside session_dir.

    Raises _PathTraversal when the resolved path escapes the session dir
    (path traversal / symlink escape guard).
    """
    try:
        candidate = (session_dir / rel_path).resolve()
        base = session_dir.resolve()
    except OSError:
        raise _PathTraversal()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise _PathTraversal()
    return candidate


# ── Handlers ────────────────────────────────────────────────────────────

@require_auth
def handle_artifacts(method: str, path_tail: str, body: dict, query: dict,
                     handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/artifacts/... requests.

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth.

    Supported routes:
        GET /api/v1/artifacts/list          — artifact tree per run
        GET /api/v1/artifacts/preview       — read-only file preview
        GET /api/v1/artifacts/evidence-pack — evidence pack file list
    """
    if path_tail == "list" and method == "GET":
        return _artifacts_list(query)
    if path_tail == "preview" and method == "GET":
        return _artifacts_preview(query)
    if path_tail == "evidence-pack" and method == "GET":
        return _artifacts_evidence_pack(query)

    return json_error(f"Unknown artifacts sub-path or method: {method} {path_tail}", 404)


def _artifacts_list(query: dict) -> tuple[dict, int]:
    """GET /api/v1/artifacts/list — artifact tree for every pipeline run.

    Each run entry: ``{run_id, name, status, files: [{path, name, size, ext}]}``
    where ``name``/``status`` come from the session's session.json and
    ``files`` are the stage output files (session.json excluded).
    """
    project = _q(query, "project")

    runs = []
    for run_id, session_dir, meta in _iter_sessions():
        if not _session_matches_project(meta, project):
            continue
        files = _artifact_files(session_dir)
        runs.append({
            "run_id": run_id,
            "name": meta.get("name") or run_id,
            "status": meta.get("status", "unknown"),
            "updated_at": meta.get("updated_at", ""),
            "files": files,
        })
    # Newest first — prefer session updated_at, fall back to run_id.
    runs.sort(key=lambda r: (r["updated_at"], r["run_id"]), reverse=True)
    for r in runs:
        r.pop("updated_at", None)

    if not runs:
        note = f"未找到流水线会话产出物 (.osh/sessions 无数据)"
        if project:
            note = f"未找到项目 {project} 的会话产出物"
        return json_ok({"runs": [], "count": 0, "note": note})

    return json_ok({"runs": runs, "count": len(runs), "note": None})


def _artifacts_preview(query: dict) -> tuple[dict, int]:
    """GET /api/v1/artifacts/preview — read-only preview of one artifact.

    Security: the file must resolve inside the session directory
    (``Path.resolve()`` + containment check) — traversal is rejected 403.
    Content is capped at 100 KB (``truncated`` flag set when cut).
    """
    run = _q(query, "run")
    file = _q(query, "file")
    if not run or not file:
        return json_error("run and file query params are required", 400)

    session_dir = _session_dir(run)
    if session_dir is None:
        return json_error(f"run not found: {run}", 404)

    try:
        target = _resolve_within(session_dir, file)
    except _PathTraversal:
        log.warning("artifacts/preview path traversal blocked: run=%s file=%s", run, file)
        return json_error("file path must stay inside the session directory", 403)

    if not target.is_file():
        return json_error(f"file not found: {file}", 404)

    ext = target.suffix.lstrip(".").lower()
    if ext not in PREVIEW_EXTS:
        return json_error(f"unsupported file type for preview: {file}", 415)

    raw = target.read_bytes()
    size = len(raw)
    truncated = size > MAX_PREVIEW_BYTES
    if truncated:
        raw = raw[:MAX_PREVIEW_BYTES]
    content = raw.decode("utf-8", errors="replace")

    return json_ok({
        "run_id": run,
        "file": file,
        "name": target.name,
        "size": size,
        "ext": ext,
        "content": content,
        "truncated": truncated,
        "note": "内容超过 100KB，已截断预览" if truncated else None,
    })


def _artifacts_evidence_pack(query: dict) -> tuple[dict, int]:
    """GET /api/v1/artifacts/evidence-pack — evidence pack file list for a run.

    The evidence pack comprises the final report (``final-report.md``) plus
    the related JSON evidence files of that run.
    """
    run = _q(query, "run")
    if not run:
        return json_error("run query param is required", 400)

    session_dir = _session_dir(run)
    if session_dir is None:
        return json_error(f"run not found: {run}", 404)

    meta = _session_meta(session_dir)

    files = []
    final_report = session_dir / "final-report.md"
    if final_report.is_file():
        rel = final_report.relative_to(session_dir)
        files.append({
            "path": rel.as_posix(),
            "name": final_report.name,
            "size": final_report.stat().st_size,
            "ext": "md",
        })
    for p in sorted(session_dir.glob("*.json")):
        if p.name == "session.json":
            continue
        files.append({
            "path": p.name,
            "name": p.name,
            "size": p.stat().st_size,
            "ext": "json",
        })

    if not files:
        return json_ok({
            "run_id": run,
            "name": meta.get("name") or run,
            "status": meta.get("status", "unknown"),
            "files": [],
            "count": 0,
            "note": "该 run 无证据包文件（缺少 final-report.md 或相关 JSON）",
        })

    return json_ok({
        "run_id": run,
        "name": meta.get("name") or run,
        "status": meta.get("status", "unknown"),
        "files": files,
        "count": len(files),
        "note": None,
    })
