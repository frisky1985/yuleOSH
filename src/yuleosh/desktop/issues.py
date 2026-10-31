# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Problem-resolution management (ASPICE SUP.9 minimal loop).

Issues/defects are first-class on-disk entities stored under::

    {project}/.osh/issues/{ISSUE-ID}.json

Each issue carries a severity, owner, root-cause analysis, resolution, and
a verification record.  The lifecycle is::

    open -> analyzed -> resolved -> verified -> closed
    open -> rejected (wontfix)

Fail-closed: an issue can only reach ``closed`` after ``verified`` (a fix
that was never verified does not count as resolved evidence).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

ISSUE_DIR = Path(".osh") / "issues"

STATUSES = ("open", "analyzed", "resolved", "verified", "closed", "rejected")

_TRANSITIONS = {
    "open": {"analyzed", "rejected"},
    "analyzed": {"resolved", "rejected"},
    "resolved": {"verified", "analyzed"},
    "verified": {"closed"},
    "closed": set(),
    "rejected": set(),
}

SEVERITIES = ("low", "medium", "high", "critical")


class InvalidTransition(ValueError):
    """Raised when an issue status transition is not allowed."""


def _issue_dir(project_id: str, create: bool = False) -> Path:
    d = workspace._project_dir(project_id) / ISSUE_DIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _issue_path(project_id: str, issue_id: str) -> Path:
    if not issue_id or ".." in issue_id or "/" in issue_id or "\\" in issue_id:
        raise ValueError(f"Invalid issue id: {issue_id}")
    return _issue_dir(project_id) / f"{issue_id}.json"


def _now() -> str:
    return datetime.now().isoformat()


def _new_id() -> str:
    return f"ISSUE-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────

def list_issues(project_id: str) -> list[dict]:
    workspace._load_meta(project_id)
    d = _issue_dir(project_id)
    issues = []
    if not d.is_dir():
        return issues
    for f in sorted(d.glob("*.json")):
        try:
            data = _load(f)
            issues.append({k: data.get(k) for k in (
                "id", "title", "severity", "status", "owner",
                "created_at", "closed_at",
            )})
        except (json.JSONDecodeError, OSError):
            continue
    return issues


def create_issue(project_id: str, body: dict[str, Any]) -> dict:
    workspace._load_meta(project_id)
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    severity = (body.get("severity") or "medium").strip().lower()
    if severity not in SEVERITIES:
        severity = "medium"

    issue_id = _new_id()
    issue = {
        "id": issue_id,
        "title": title,
        "description": (body.get("description") or "").strip(),
        "severity": severity,
        "status": "open",
        "owner": (body.get("owner") or "unassigned").strip(),
        "reported_by": (body.get("reported_by") or "local").strip(),
        "verified_by": "",
        "root_cause": "",
        "resolution": "",
        "verification": "",
        "created_at": _now(),
        "updated_at": _now(),
        "closed_at": None,
    }
    _save(_issue_path(project_id, issue_id), issue)
    return issue


def get_issue(project_id: str, issue_id: str) -> dict:
    workspace._load_meta(project_id)
    path = _issue_path(project_id, issue_id)
    if not path.is_file():
        raise FileNotFoundError(f"Issue not found: {issue_id}")
    return _load(path)


def transition(project_id: str, issue_id: str, body: dict[str, Any]) -> dict:
    """Transition an issue's status.

    Depending on the target status, ``body`` may carry:
      * analyzed → ``root_cause``
      * resolved → ``resolution``
      * verified → ``verification``
    """
    workspace._load_meta(project_id)
    path = _issue_path(project_id, issue_id)
    if not path.is_file():
        raise FileNotFoundError(f"Issue not found: {issue_id}")
    issue = _load(path)

    target = (body.get("status") or "").strip().lower()
    if target not in STATUSES:
        raise ValueError(f"Invalid issue status: {target}")

    current = issue.get("status", "open")
    if target not in _TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"Invalid issue transition: {current} -> {target}")

    now = _now()
    issue["status"] = target
    issue["updated_at"] = now

    if target == "analyzed":
        issue["root_cause"] = (body.get("root_cause") or issue.get("root_cause") or "").strip()
    elif target == "resolved":
        issue["resolution"] = (body.get("resolution") or issue.get("resolution") or "").strip()
    elif target == "verified":
        issue["verification"] = (body.get("verification") or issue.get("verification") or "").strip()
        issue["verified_by"] = (body.get("verified_by") or "local").strip()
    elif target == "closed":
        # Fail-closed: must be verified before closing.
        if current != "verified":
            raise InvalidTransition("Issue must be verified before closing")
        issue["closed_at"] = now

    _save(path, issue)
    return issue


def export_report(project_id: str) -> str:
    """Export an issue-log markdown to ``.osh/evidence/issue-report.md``."""
    workspace._load_meta(project_id)
    issues = list_issues(project_id)
    proj_name = workspace._load_meta(project_id).get("name", project_id)

    lines = [
        f"# Issue Report — {proj_name}",
        "",
        f"> Generated: {_now()}",
        f"> Issues: {len(issues)}",
        "",
        "| ID | Title | Severity | Status | Owner |",
        "|---|---|---|---|---|",
    ]
    for i in issues:
        lines.append(
            f"| {i['id']} | {i['title']} | {i['severity']} | "
            f"{i['status']} | {i['owner']} |"
        )
    lines.append("")

    for i in issues:
        full = get_issue(project_id, i["id"])
        lines.append(f"## {i['id']}: {i['title']}")
        lines.append("")
        lines.append(f"- Severity: {full['severity']}")
        lines.append(f"- Status: {full['status']}")
        lines.append(f"- Owner: {full['owner']}")
        if full.get("description"):
            lines.append(f"- Description: {full['description']}")
        if full.get("root_cause"):
            lines.append(f"- Root Cause: {full['root_cause']}")
        if full.get("resolution"):
            lines.append(f"- Resolution: {full['resolution']}")
        if full.get("verification"):
            lines.append(f"- Verification: {full['verification']}")
        lines.append("")

    out = workspace._project_dir(project_id) / ".osh" / "evidence" / "issue-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)
