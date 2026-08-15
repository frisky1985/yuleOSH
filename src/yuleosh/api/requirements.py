#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Requirements management API — mounted at /api/v1/requirements/.

Module ② of the dashboard design (docs/architecture/dashboard-design.md):
OpenSpec requirement lifecycle board, traceability and gap analysis.

Endpoints:
    GET /api/v1/requirements?project=xxx      — requirement list parsed from
                                                 spec files (Req-XXX-001 headers,
                                                 SHALL/SHOULD/MAY statements,
                                                 GIVEN/WHEN/THEN scenarios)
    GET /api/v1/requirements/{req_id}/trace   — traceability: scan the project
                                                 directory for files referencing
                                                 req_id (design / code / test /
                                                 evidence)
    GET /api/v1/requirements/gaps?project=xxx — gap analysis: requirements
                                                 without test / evidence

Lightweight implementation: spec parsing is regex-based (no full OpenSpec
engine) and reads REAL files only. When no spec file exists the endpoints
return an empty result plus a note — no fabricated data.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.requirements")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

ALLOWED_STATES = ("PROPOSED", "APPROVED", "IMPLEMENTED", "VERIFIED")
MAX_SPEC_BYTES = 2 * 1024 * 1024
MAX_SCAN_BYTES = 512 * 1024
MAX_SCAN_FILES = 500

# "### Req-SYS-001: 标题" / "## TG-REQ-001: 模板存储结构" / "## RS-001.2: Title"
REQ_HEADER_RE = re.compile(
    r"^#{2,4}\s+([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*-\d+(?:\.\d+)?)\s*[:：]?\s*(.*)$"
)
STATUS_RE = re.compile(r"(?i)\b(?:Status|状态)\s*[:：]\s*([A-Z]+)")
KIND_RE = re.compile(r"\b(SHALL|SHOULD|MAY)\b")
GWT_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:\*\*)?(GIVEN|WHEN|THEN|AND)(?:\*\*)?\s*[:：]?\s*(.+)$",
    re.IGNORECASE,
)

CODE_EXTS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".py", ".rs", ".go",
             ".js", ".ts", ".s", ".S", ".asm"}
TEXT_EXTS = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".xml", ".csv", ".log"}
SKIP_DIRS = {"node_modules", "dist", "build", "__pycache__", ".venv", "venv"}


def _q(query: dict, key: str, default: Any = None) -> Any:
    """Query param accessor — router passes lists (parse_qs), tests pass scalars."""
    val = query.get(key, default)
    if isinstance(val, list):
        return val[0] if val else default
    return val if val is not None else default


@require_auth
def handle_requirements(method: str, path_tail: str, body: dict, query: dict,
                        handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Route /api/v1/requirements/... requests.

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth
    (user_id / org_id / email / role).
    """
    if method == "GET" and path_tail == "":
        return _list_requirements(query)
    if method == "GET" and path_tail == "gaps":
        return _gaps(query)
    if method == "GET":
        parts = path_tail.split("/")
        if len(parts) == 2 and parts[1] == "trace":
            return _trace(parts[0], query)

    return json_error(f"Unknown requirements sub-path or method: {method} {path_tail}", 404)


# ── Spec discovery & parsing ────────────────────────────────────────────

def _resolve_project_dir(project: str) -> tuple[Optional[Path], Optional[tuple]]:
    """Resolve OSH_HOME/projects/<project> with a path-traversal guard.

    Returns (project_dir, None) on success or (None, error_tuple) on
    failure. project names must be a single path segment (no '/', '\\',
    '..' or leading dot) and must resolve inside OSH_HOME/projects.
    """
    if not project:
        return None, json_error("缺少 project 参数", 400)
    if "/" in project or "\\" in project or project in (".", "..") or project.startswith("."):
        return None, json_error("非法 project 名称", 403)
    base = Path(OSH_HOME).resolve() / "projects"
    try:
        proj_dir = (base / project).resolve()
        proj_dir.relative_to(base)
    except (ValueError, OSError):
        return None, json_error("project 路径越界", 403)
    return proj_dir, None


def _find_spec_files(proj_dir: Path) -> list[Path]:
    """Find spec*.md files for a project.

    Primary: OSH_HOME/projects/<project>/spec*.md (also docs/spec*.md).
    Fallback: OSH_HOME/.osh/specs/<version>/spec*.md cache.
    """
    files = sorted(proj_dir.glob("spec*.md")) if proj_dir.is_dir() else []
    files += sorted(proj_dir.glob("docs/spec*.md")) if proj_dir.is_dir() else []
    if not files:
        cache_root = Path(OSH_HOME).resolve() / ".osh" / "specs"
        if cache_root.is_dir():
            for ver_dir in sorted(cache_root.iterdir()):
                if ver_dir.is_dir():
                    files += sorted(ver_dir.glob("spec*.md"))
    return files


def _clean_stmt(line: str) -> str:
    """Strip markdown list markers / bold from a statement line."""
    line = line.strip()
    line = re.sub(r"^[-*]\s+", "", line)
    line = re.sub(r"\*\*", "", line)
    return line.strip()


def _parse_scenarios(gwt_lines: list[tuple[str, str]]) -> list[dict]:
    """Group GIVEN/WHEN/THEN/AND lines into scenario dicts.

    Each WHEN starts a new scenario; GIVEN lines before the first WHEN
    attach to that first scenario; THEN/AND lines attach to the most
    recent scenario. GIVEN/THEN lines with no WHEN at all form a single
    implicit scenario (when=[]).
    """
    scenarios: list[dict] = []
    pending_given: list[str] = []
    current: Optional[dict] = None
    for kw, text in gwt_lines:
        if kw == "GIVEN":
            if current is None:
                pending_given.append(text)
            else:
                current["given"].append(text)
        elif kw == "WHEN":
            current = {"given": list(pending_given), "when": [text], "then": []}
            pending_given = []
            scenarios.append(current)
        elif kw in ("THEN", "AND"):
            if current is None:
                current = {"given": list(pending_given), "when": [], "then": []}
                pending_given = []
                scenarios.append(current)
            current["then"].append(text)
    if pending_given and not scenarios:
        scenarios.append({"given": pending_given, "when": [], "then": []})
    return scenarios


def _finalize(current: dict, reqs: list[dict], seen: set) -> None:
    """Flush a parsed requirement block into the result list (dedup by id)."""
    req_id = current["req_id"]
    if req_id in seen:
        return
    seen.add(req_id)

    counts = {"SHALL": 0, "SHOULD": 0, "MAY": 0}
    for kind, _stmt in current["statements"]:
        counts[kind] = counts.get(kind, 0) + 1
    kind = next((k for k in ("SHALL", "SHOULD", "MAY") if counts.get(k)), "SHALL")
    text = " ".join(stmt for _kind, stmt in current["statements"])

    reqs.append({
        "req_id": req_id,
        "title": current["title"],
        "kind": kind,
        "text": text,
        "state": current["state"],
        "scenarios": _parse_scenarios(current["gwt"]),
    })


def _parse_spec_text(text: str, reqs: list[dict], seen: set) -> None:
    """Regex-parse one spec file into requirement dicts (lightweight)."""
    current: Optional[dict] = None
    for line in text.splitlines():
        m = REQ_HEADER_RE.match(line)
        if m:
            if current is not None:
                _finalize(current, reqs, seen)
            current = {
                "req_id": m.group(1).upper(),
                "title": m.group(2).strip(),
                "state": "PROPOSED",
                "statements": [],
                "gwt": [],
            }
            continue
        if current is None:
            continue
        gm = GWT_RE.match(line)
        if gm:
            current["gwt"].append((gm.group(1).upper(), gm.group(2).strip()))
            continue
        sm = STATUS_RE.search(line)
        if sm:
            state = sm.group(1).upper()
            if state in ALLOWED_STATES:
                current["state"] = state
            continue
        km = KIND_RE.search(line)
        if km:
            current["statements"].append((km.group(1).upper(), _clean_stmt(line)))
    if current is not None:
        _finalize(current, reqs, seen)


def _parse_requirements(spec_files: list[Path]) -> list[dict]:
    reqs: list[dict] = []
    seen: set = set()
    for f in spec_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            log.debug("skip unreadable spec %s: %s", f, e)
            continue
        if len(text) > MAX_SPEC_BYTES:
            text = text[:MAX_SPEC_BYTES]
        _parse_spec_text(text, reqs, seen)
    return reqs


# ── Project directory scanning (trace / gaps) ───────────────────────────

def _iter_project_files(proj_dir: Path):
    """Yield text-ish files under proj_dir, skipping dot/skip dirs."""
    count = 0
    for root, dirs, files in os.walk(proj_dir):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d not in SKIP_DIRS]
        for name in files:
            if count >= MAX_SCAN_FILES:
                return
            count += 1
            yield Path(root) / name


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in CODE_EXTS or path.suffix.lower() in TEXT_EXTS


def _classify_artifact(path: Path, proj_dir: Path) -> str:
    """Classify a referencing file as design / code / test / evidence."""
    rel = str(path.relative_to(proj_dir)).lower()
    name = path.name.lower()
    if "evidence" in rel or "report" in rel or "manifest" in rel:
        return "evidence"
    if "test" in rel or name.startswith("test_") or name.startswith("test-"):
        return "test"
    if path.suffix.lower() in CODE_EXTS:
        return "code"
    return "design"


def _referencing_artifacts(proj_dir: Path, req_id: str,
                           exclude_spec: bool = True) -> list[dict]:
    """Scan proj_dir for files containing req_id (case-insensitive)."""
    artifacts: list[dict] = []
    req_upper = req_id.upper()
    for f in _iter_project_files(proj_dir):
        if not _is_text_file(f):
            continue
        if exclude_spec and f.name.lower().startswith("spec") and f.suffix.lower() == ".md":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content) > MAX_SCAN_BYTES:
            content = content[:MAX_SCAN_BYTES]
        if req_upper in content.upper():
            artifacts.append({
                "type": _classify_artifact(f, proj_dir),
                "ref": str(f.relative_to(proj_dir)),
            })
    return artifacts


# ── Endpoints ───────────────────────────────────────────────────────────

def _list_requirements(query: dict) -> tuple[dict, int]:
    """GET /api/v1/requirements — requirement list parsed from spec files."""
    project = _q(query, "project")
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err
    assert proj_dir is not None  # err is None on success

    spec_files = _find_spec_files(proj_dir)
    if not spec_files:
        return json_ok({
            "requirements": [],
            "count": 0,
            "note": f"项目 '{project}' 未找到 spec 文件"
                    f"（projects/{project}/spec*.md 或 .osh/specs 缓存）",
        })

    reqs = _parse_requirements(spec_files)
    return json_ok({"requirements": reqs, "count": len(reqs), "note": None})


def _trace(req_id: str, query: dict) -> tuple[dict, int]:
    """GET /api/v1/requirements/{req_id}/trace — traceability.

    Lightweight: scans the project directory for files referencing req_id
    and classifies each hit as design / code / test / evidence.
    """
    project = _q(query, "project")
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err
    assert proj_dir is not None  # err is None on success

    req_id = req_id.upper()
    artifacts = _referencing_artifacts(proj_dir, req_id) if proj_dir.is_dir() else []
    return json_ok({"req_id": req_id, "artifacts": artifacts, "note": None})


def _gaps(query: dict) -> tuple[dict, int]:
    """GET /api/v1/requirements/gaps — test/evidence gap analysis.

    Stats: total requirements, how many have test artifacts, how many have
    evidence artifacts, and a gap list [{req_id, missing: [...]}].
    """
    project = _q(query, "project")
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err
    assert proj_dir is not None  # err is None on success

    spec_files = _find_spec_files(proj_dir)
    if not spec_files:
        return json_ok({
            "total": 0, "with_test": 0, "with_evidence": 0, "gaps": [],
            "note": f"项目 '{project}' 未找到 spec 文件"
                    f"（projects/{project}/spec*.md 或 .osh/specs 缓存）",
        })

    reqs = _parse_requirements(spec_files)
    req_ids = [r["req_id"] for r in reqs]
    coverage = {rid: set() for rid in req_ids}

    if proj_dir.is_dir():
        for f in _iter_project_files(proj_dir):
            if not _is_text_file(f):
                continue
            if f.name.lower().startswith("spec") and f.suffix.lower() == ".md":
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(content) > MAX_SCAN_BYTES:
                content = content[:MAX_SCAN_BYTES]
            upper = content.upper()
            for rid in req_ids:
                if rid in upper:
                    coverage[rid].add(_classify_artifact(f, proj_dir))

    gaps: list[dict] = []
    with_test = 0
    with_evidence = 0
    for r in reqs:
        types = coverage[r["req_id"]]
        if "test" in types:
            with_test += 1
        if "evidence" in types:
            with_evidence += 1
        missing = []
        if "test" not in types:
            missing.append("test")
        if "evidence" not in types:
            missing.append("evidence")
        if missing:
            gaps.append({"req_id": r["req_id"], "missing": missing})

    return json_ok({
        "total": len(reqs),
        "with_test": with_test,
        "with_evidence": with_evidence,
        "gaps": gaps,
        "note": None,
    })
