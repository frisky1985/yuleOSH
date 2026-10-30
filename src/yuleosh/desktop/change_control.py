# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Change-request management (ASPICE SUP.10 minimal loop).

A change request (CR) is a first-class on-disk entity stored under::

    {project}/change-requests/{CR-ID}.json

Each CR carries its reason, the affected requirements/artifacts, an approval
status, and an append-only history. The lifecycle is::

    draft -> analyzed -> approved | rejected
    approved -> closed
    rejected -> draft

Impact analysis reuses :mod:`yuleosh.alm.traceability` to locate the code and
test files linked to the affected requirements, and writes the result to::

    {project}/.osh/evidence/impact-analysis-{CR-ID}.json

so the SUP.10 compliance check can consume real evidence instead of a
hand-written markdown file.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

CHANGE_DIR = "change-requests"
IMPACT_EVIDENCE_DIR = Path(".osh") / "evidence"

STATUSES = ("draft", "analyzed", "approved", "rejected", "closed")

_TRANSITIONS = {
    "draft": {"analyzed"},
    "analyzed": {"approved", "rejected"},
    "approved": {"closed"},
    "rejected": {"draft"},
    "closed": set(),
}

# 与 traceability 的 @req 注解语法保持一致，用于从受影响文件中反推需求 ID。
_REQ_ID_RE = re.compile(r"@req\s*[\(\s]\s*([A-Z][A-Z0-9_\-\.]+(?:\s*,\s*[A-Z][A-Z0-9_\-\.]+)*)", re.IGNORECASE)


class InvalidTransition(ValueError):
    """Raised when a CR status transition is not allowed by the state machine."""


def _change_dir(project_id: str, create: bool = False) -> Path:
    d = workspace._project_dir(project_id) / CHANGE_DIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _cr_path(project_id: str, cr_id: str) -> Path:
    if not cr_id or ".." in cr_id or "/" in cr_id or "\\" in cr_id:
        raise ValueError(f"Invalid change request id: {cr_id}")
    return _change_dir(project_id) / f"{cr_id}.json"


def _now() -> str:
    return datetime.now().isoformat()


def _new_id() -> str:
    import uuid
    return f"CR-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def create_change_request(project_id: str, body: dict[str, Any]) -> dict:
    """Create a CR in ``draft`` state. Raises FileNotFoundError if project absent."""
    workspace._load_meta(project_id)  # 项目不存在 → FileNotFoundError
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    author = (body.get("author") or "local").strip()
    reqs = sorted({str(r).strip().upper() for r in (body.get("requirements") or []) if str(r).strip()})
    affected = [str(a).strip() for a in (body.get("affected") or []) if str(a).strip()]

    cr_id = _new_id()
    now = _now()
    cr = {
        "id": cr_id,
        "title": title,
        "reason": (body.get("reason") or "").strip(),
        "author": author,
        "affected_requirements": reqs,
        "affected_artifacts": affected,
        "status": "draft",
        "impact": None,
        "history": [{"from": None, "to": "draft", "author": author, "comment": "", "at": now}],
        "created_at": now,
        "updated_at": now,
    }
    _write_cr(project_id, cr)
    return cr


def load_change_request(project_id: str, cr_id: str) -> dict:
    workspace._load_meta(project_id)
    p = _cr_path(project_id, cr_id)
    if not p.exists():
        raise FileNotFoundError(f"Change request not found: {cr_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def list_change_requests(project_id: str) -> list[dict]:
    workspace._load_meta(project_id)
    d = _change_dir(project_id)
    if not d.exists():
        return []
    items = []
    for p in d.glob("*.json"):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    items.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return items


def _write_cr(project_id: str, cr: dict) -> None:
    cr["updated_at"] = _now()
    path = _cr_path(project_id, cr["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cr, ensure_ascii=False, indent=2), encoding="utf-8")


def _rel_files(base: Path, pattern: str = "*") -> list[Path]:
    if not base.exists():
        return []
    return sorted(p for p in base.rglob(pattern) if p.is_file())


def _files_mentioning(base: Path, req_id: str) -> list[str]:
    """Return files under ``base`` whose text contains ``req_id``."""
    hits = []
    for f in _rel_files(base):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if req_id in text:
            hits.append(str(f.relative_to(base.parent)))
    return hits


def _extract_req_ids_from_paths(paths: list[str], proj_dir: Path) -> list[str]:
    ids: set[str] = set()
    root = proj_dir.resolve()
    for rel in paths:
        f = (proj_dir / rel).resolve()
        try:
            f.relative_to(root)
        except ValueError:
            continue  # 越界路径直接忽略，不做读取
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _REQ_ID_RE.finditer(text):
            for rid in m.group(1).split(","):
                rid = rid.strip().upper()
                if rid:
                    ids.add(rid)
    return sorted(ids)


def analyze_impact(project_id: str, cr_id: str, body: dict[str, Any] | None = None) -> dict:
    """Run impact analysis for a CR and persist the evidence.

    Locates code/test/design files linked to the CR's affected requirements.
    Moves the CR from ``draft`` to ``analyzed``.
    """
    cr = load_change_request(project_id, cr_id)
    body = body or {}

    if cr["status"] != "draft":
        raise InvalidTransition(
            f"{cr['status']} -> analyzed is not allowed (only draft can be analyzed)"
        )

    proj_dir = workspace._project_dir(project_id)
    req_ids = list(cr.get("affected_requirements") or [])
    if not req_ids and body.get("requirements"):
        req_ids = sorted({str(r).strip().upper() for r in body["requirements"] if str(r).strip()})
    if not req_ids:
        # 未显式给出需求时，从受影响文件中的 @req 注解反推。
        req_ids = _extract_req_ids_from_paths(cr.get("affected_artifacts") or [], proj_dir)
    req_ids = sorted({r.upper() for r in req_ids})

    code_dir = proj_dir / "code"
    design_dir = proj_dir / "design"
    tests_dir = proj_dir / "tests"

    requirements = []
    affected_code: set[str] = set()
    affected_tests: set[str] = set()
    affected_design: set[str] = set()

    for rid in req_ids:
        code = _files_mentioning(code_dir, rid)
        tests = _files_mentioning(tests_dir, rid)
        design = _files_mentioning(design_dir, rid)
        affected_code.update(code)
        affected_tests.update(tests)
        affected_design.update(design)
        requirements.append({
            "id": rid,
            "code": code,
            "tests": tests,
            "design": design,
        })

    affected_artifacts = sorted(
        set(cr.get("affected_artifacts") or [])
        | affected_code | affected_tests | affected_design
    )

    impact = {
        "change_request": cr_id,
        "generated_at": _now(),
        "author": (body.get("author") or "local").strip(),
        "requirements": requirements,
        "affected_artifacts": affected_artifacts,
        "summary": {
            "requirements": len(requirements),
            "code_files": len(affected_code),
            "test_files": len(affected_tests),
            "design_files": len(affected_design),
        },
    }

    # 落盘：CR 内嵌快照 + 供 SUP.10 检查消费的独立证据文件。
    cr["affected_requirements"] = req_ids
    cr["impact"] = impact
    _append_history(cr, "analyzed", impact["author"], body.get("comment", ""))
    _write_cr(project_id, cr)

    evidence_path = proj_dir / IMPACT_EVIDENCE_DIR / f"impact-analysis-{cr_id}.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(impact, ensure_ascii=False, indent=2), encoding="utf-8")

    return impact


def transition(project_id: str, cr_id: str, body: dict[str, Any]) -> dict:
    """Move a CR along the state machine, recording who/why in history."""
    cr = load_change_request(project_id, cr_id)
    target = (body.get("status") or "").strip().lower()
    if target not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    current = cr["status"]
    if target not in _TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"{current} -> {target} is not allowed")

    author = (body.get("author") or "local").strip()
    _append_history(cr, target, author, body.get("comment", ""))
    _write_cr(project_id, cr)
    return cr


def _append_history(cr: dict, to_status: str, author: str, comment: Any) -> None:
    cr["history"].append({
        "from": cr["status"],
        "to": to_status,
        "author": author,
        "comment": str(comment or "").strip(),
        "at": _now(),
    })
    cr["status"] = to_status
