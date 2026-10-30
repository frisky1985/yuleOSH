# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Project management (ASPICE MAN.3 minimal loop): risk register & milestones.

Two on-disk entity kinds:

* **Risks** under ``{project}/.osh/risks/{RSK-ID}.json`` — each risk has
  likelihood × impact → level, a mitigation plan, owner, and status
  (open → mitigated → closed).  Fail-closed: a risk cannot close without
  a recorded mitigation.

* **Milestones** in ``{project}/.osh/project/milestones.json`` — ordered
  list of milestones with target date, deliverable, and status
  (not_started → in_progress → completed).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

RISK_DIR = Path(".osh") / "risks"
MILESTONES_FILE = Path(".osh") / "project" / "milestones.json"

RISK_STATUSES = ("open", "mitigated", "closed")
_RISK_TRANSITIONS = {
    "open": {"mitigated"},
    "mitigated": {"closed", "open"},
    "closed": set(),
}

MILESTONE_STATUSES = ("not_started", "in_progress", "completed")

_LIKELIHOOD = ("low", "medium", "high")
_IMPACT = ("low", "medium", "high")

_LEVEL_MATRIX = {
    ("low", "low"): "low",
    ("low", "medium"): "low",
    ("low", "high"): "medium",
    ("medium", "low"): "low",
    ("medium", "medium"): "medium",
    ("medium", "high"): "high",
    ("high", "low"): "medium",
    ("high", "medium"): "high",
    ("high", "high"): "critical",
}


def _now() -> str:
    return datetime.now().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _risk_level(likelihood: str, impact: str) -> str:
    return _LEVEL_MATRIX.get((likelihood, impact), "medium")


# ── Risks ─────────────────────────────────────────────────────────────────

def _risk_dir(project_id: str, create: bool = False) -> Path:
    d = workspace._project_dir(project_id) / RISK_DIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _risk_path(project_id: str, risk_id: str) -> Path:
    if not risk_id or ".." in risk_id or "/" in risk_id or "\\" in risk_id:
        raise ValueError(f"Invalid risk id: {risk_id}")
    return _risk_dir(project_id) / f"{risk_id}.json"


def list_risks(project_id: str) -> list[dict]:
    workspace._load_meta(project_id)
    d = _risk_dir(project_id)
    risks = []
    if not d.is_dir():
        return risks
    for f in sorted(d.glob("*.json")):
        try:
            data = _load(f)
            risks.append({k: data.get(k) for k in (
                "id", "description", "likelihood", "impact", "level",
                "status", "owner",
            )})
        except (json.JSONDecodeError, OSError):
            continue
    return risks


def create_risk(project_id: str, body: dict[str, Any]) -> dict:
    workspace._load_meta(project_id)
    desc = (body.get("description") or "").strip()
    if not desc:
        raise ValueError("description is required")
    likelihood = (body.get("likelihood") or "medium").strip().lower()
    impact = (body.get("impact") or "medium").strip().lower()
    if likelihood not in _LIKELIHOOD:
        likelihood = "medium"
    if impact not in _IMPACT:
        impact = "medium"

    risk_id = _new_id("RSK")
    risk = {
        "id": risk_id,
        "description": desc,
        "likelihood": likelihood,
        "impact": impact,
        "level": _risk_level(likelihood, impact),
        "mitigation": "",
        "status": "open",
        "owner": (body.get("owner") or "unassigned").strip(),
        "created_at": _now(),
        "updated_at": _now(),
        "closed_at": None,
    }
    _save(_risk_path(project_id, risk_id), risk)
    return risk


def get_risk(project_id: str, risk_id: str) -> dict:
    workspace._load_meta(project_id)
    path = _risk_path(project_id, risk_id)
    if not path.is_file():
        raise FileNotFoundError(f"Risk not found: {risk_id}")
    return _load(path)


def transition_risk(project_id: str, risk_id: str, body: dict[str, Any]) -> dict:
    workspace._load_meta(project_id)
    path = _risk_path(project_id, risk_id)
    if not path.is_file():
        raise FileNotFoundError(f"Risk not found: {risk_id}")
    risk = _load(path)

    target = (body.get("status") or "").strip().lower()
    if target not in RISK_STATUSES:
        raise ValueError(f"Invalid risk status: {target}")

    current = risk.get("status", "open")
    if target not in _RISK_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid risk transition: {current} -> {target}")

    if target == "mitigated":
        mitigation = (body.get("mitigation") or risk.get("mitigation") or "").strip()
        if not mitigation:
            raise ValueError("mitigation is required to mark a risk as mitigated")
        risk["mitigation"] = mitigation
    if target == "closed":
        # Fail-closed: must be mitigated first.
        if current != "mitigated":
            raise ValueError("Risk must be mitigated before closing")
        risk["closed_at"] = _now()

    risk["status"] = target
    risk["updated_at"] = _now()
    _save(path, risk)
    return risk


# ── Milestones ────────────────────────────────────────────────────────────

def _milestones_path(project_id: str) -> Path:
    return workspace._project_dir(project_id) / MILESTONES_FILE


def list_milestones(project_id: str) -> list[dict]:
    workspace._load_meta(project_id)
    path = _milestones_path(project_id)
    if not path.is_file():
        return []
    try:
        return _load(path)
    except (json.JSONDecodeError, OSError):
        return []


def add_milestone(project_id: str, body: dict[str, Any]) -> dict:
    workspace._load_meta(project_id)
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    milestones = list_milestones(project_id)
    ms = {
        "id": _new_id("MS"),
        "title": title,
        "target_date": (body.get("target_date") or "").strip(),
        "deliverable": (body.get("deliverable") or "").strip(),
        "status": body.get("status") or "not_started",
        "created_at": _now(),
        "updated_at": _now(),
    }
    if ms["status"] not in MILESTONE_STATUSES:
        ms["status"] = "not_started"
    milestones.append(ms)
    _save(_milestones_path(project_id), milestones)
    return ms


def update_milestone(project_id: str, milestone_id: str, body: dict[str, Any]) -> dict:
    workspace._load_meta(project_id)
    milestones = list_milestones(project_id)
    target = None
    for m in milestones:
        if m.get("id") == milestone_id:
            target = m
            break
    if target is None:
        raise FileNotFoundError(f"Milestone not found: {milestone_id}")

    if "title" in body and body["title"]:
        target["title"] = str(body["title"]).strip()
    if "target_date" in body:
        target["target_date"] = str(body["target_date"]).strip()
    if "deliverable" in body:
        target["deliverable"] = str(body["deliverable"]).strip()
    if "status" in body:
        s = str(body["status"]).strip().lower()
        if s in MILESTONE_STATUSES:
            target["status"] = s
    target["updated_at"] = _now()
    _save(_milestones_path(project_id), milestones)
    return target


# ── Export ────────────────────────────────────────────────────────────────

def export_report(project_id: str) -> str:
    """Export project management report (risks + milestones) to markdown."""
    workspace._load_meta(project_id)
    proj_name = workspace._load_meta(project_id).get("name", project_id)
    risks = list_risks(project_id)
    milestones = list_milestones(project_id)

    lines = [
        f"# Project Management Report — {proj_name}",
        "",
        f"> Generated: {_now()}",
        "",
        "## Milestones",
        "",
        "| ID | Title | Target | Deliverable | Status |",
        "|---|---|---|---|---|",
    ]
    for m in milestones:
        lines.append(
            f"| {m['id']} | {m['title']} | {m.get('target_date','')} | "
            f"{m.get('deliverable','')} | {m['status']} |"
        )
    lines.append("")
    lines.append("## Risk Register")
    lines.append("")
    lines.append("| ID | Risk | L | I | Level | Status | Owner | Mitigation |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in risks:
        lines.append(
            f"| {r['id']} | {r['description']} | {r['likelihood']} | "
            f"{r['impact']} | {r['level']} | {r['status']} | {r['owner']} | "
            f"{r.get('mitigation','')} |"
        )
    lines.append("")

    out = workspace._project_dir(project_id) / ".osh" / "evidence" / "project-mgmt-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)
