# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Quality-assurance audit workflow (ASPICE SUP.1 minimal loop).

QA audits are first-class on-disk entities stored under::

    {project}/.osh/ci/qa-audit-{AUDIT-ID}.json

so the SUP.1 compliance check (``_has_qa_records``) can consume real audit
records instead of a hand-written markdown file.

Each audit carries a scope, auditor, date, and a list of nonconformity
findings.  A finding has its own lifecycle::

    open -> acknowledged -> resolved -> closed

Findings that are never closed keep the audit ``open``; an audit is
``closed`` only when every finding is closed (fail-closed: no fake-green
"all good" without evidence of resolution).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

QA_DIR = Path(".osh") / "ci"

AUDIT_STATUSES = ("open", "closed")
FINDING_STATUSES = ("open", "acknowledged", "resolved", "closed")

_FINDING_TRANSITIONS = {
    "open": {"acknowledged", "resolved", "closed"},
    "acknowledged": {"resolved", "closed"},
    "resolved": {"closed"},
    "closed": set(),
}

SEVERITIES = ("low", "medium", "high", "critical")


def _qa_dir(project_id: str, create: bool = False) -> Path:
    d = workspace._project_dir(project_id) / QA_DIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _audit_path(project_id: str, audit_id: str) -> Path:
    if not audit_id or ".." in audit_id or "/" in audit_id or "\\" in audit_id:
        raise ValueError(f"Invalid audit id: {audit_id}")
    return _qa_dir(project_id) / f"qa-audit-{audit_id}.json"


def _now() -> str:
    return datetime.now().isoformat()


def _new_id(prefix: str = "QA") -> str:
    return f"{prefix}-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _audit_status(audit: dict) -> str:
    """An audit is closed only when all its findings are closed."""
    findings = audit.get("findings", [])
    if not findings:
        # No findings → closed only if explicitly marked; default open to
        # avoid "empty audit = pass" fake-green.
        return audit.get("status", "open")
    if all(f.get("status") == "closed" for f in findings):
        return "closed"
    return "open"


# ── Public API ────────────────────────────────────────────────────────────

def list_audits(project_id: str) -> list[dict]:
    """List all QA audits (summary only, no findings body)."""
    workspace._load_meta(project_id)
    d = _qa_dir(project_id)
    audits = []
    if not d.is_dir():
        return audits
    for f in sorted(d.glob("qa-audit-*.json")):
        try:
            data = _load(f)
            audits.append({
                "id": data["id"],
                "title": data.get("title", ""),
                "auditor": data.get("auditor", ""),
                "scope": data.get("scope", ""),
                "date": data.get("date", ""),
                "status": _audit_status(data),
                "finding_count": len(data.get("findings", [])),
                "open_findings": sum(
                    1 for fn in data.get("findings", [])
                    if fn.get("status") != "closed"
                ),
            })
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return audits


def create_audit(project_id: str, body: dict[str, Any]) -> dict:
    """Create a QA audit record.

    body: ``title``, ``auditor``, ``scope``, optional ``findings`` list.
    """
    workspace._load_meta(project_id)
    title = (body.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    audit_id = _new_id("QA")
    findings = []
    for f in (body.get("findings") or []):
        findings.append(_normalize_finding(f))

    audit = {
        "id": audit_id,
        "title": title,
        "auditor": (body.get("auditor") or "local").strip(),
        "scope": (body.get("scope") or "").strip(),
        "date": body.get("date") or _now(),
        "status": "open",
        "findings": findings,
        "created_at": _now(),
        "updated_at": _now(),
    }
    audit["status"] = _audit_status(audit)
    _save(_audit_path(project_id, audit_id), audit)
    return audit


def get_audit(project_id: str, audit_id: str) -> dict:
    workspace._load_meta(project_id)
    path = _audit_path(project_id, audit_id)
    if not path.is_file():
        raise FileNotFoundError(f"Audit not found: {audit_id}")
    data = _load(path)
    data["status"] = _audit_status(data)
    return data


def add_finding(project_id: str, audit_id: str, body: dict[str, Any]) -> dict:
    """Append a nonconformity finding to an audit."""
    workspace._load_meta(project_id)
    path = _audit_path(project_id, audit_id)
    if not path.is_file():
        raise FileNotFoundError(f"Audit not found: {audit_id}")
    audit = _load(path)
    finding = _normalize_finding(body)
    audit.setdefault("findings", []).append(finding)
    audit["status"] = _audit_status(audit)
    audit["updated_at"] = _now()
    _save(path, audit)
    return finding


def transition_finding(
    project_id: str, audit_id: str, finding_id: str, body: dict[str, Any]
) -> dict:
    """Transition a finding's status through the state machine.

    body: ``status`` (target), optional ``resolution`` / ``verifier``.
    """
    workspace._load_meta(project_id)
    path = _audit_path(project_id, audit_id)
    if not path.is_file():
        raise FileNotFoundError(f"Audit not found: {audit_id}")
    audit = _load(path)

    target = (body.get("status") or "").strip().lower()
    if target not in FINDING_STATUSES:
        raise ValueError(f"Invalid finding status: {target}")

    finding = None
    for f in audit.get("findings", []):
        if f.get("id") == finding_id:
            finding = f
            break
    if finding is None:
        raise FileNotFoundError(f"Finding not found: {finding_id}")

    current = finding.get("status", "open")
    if target not in _FINDING_TRANSITIONS.get(current, set()):
        raise ValueError(
            f"Invalid finding transition: {current} -> {target}"
        )

    finding["status"] = target
    if target in ("resolved", "closed"):
        finding["resolution"] = (body.get("resolution") or finding.get("resolution") or "").strip()
        finding["resolved_at"] = _now()
    if target == "closed":
        finding["verifier"] = (body.get("verifier") or finding.get("verifier") or "local").strip()
        finding["closed_at"] = _now()
    finding["updated_at"] = _now()

    audit["status"] = _audit_status(audit)
    audit["updated_at"] = _now()
    _save(path, audit)
    return finding


def export_report(project_id: str) -> str:
    """Export a QA audit summary markdown to ``.osh/evidence/qa-audit-report.md``.

    Returns the file path.
    """
    workspace._load_meta(project_id)
    audits = list_audits(project_id)
    proj_name = workspace._load_meta(project_id).get("name", project_id)

    lines = [
        f"# QA Audit Report — {proj_name}",
        "",
        f"> Generated: {_now()}",
        f"> Audits: {len(audits)}",
        "",
        "## Summary",
        "",
        "| Audit ID | Title | Status | Findings | Open |",
        "|---|---|---|---|---|",
    ]
    for a in audits:
        lines.append(
            f"| {a['id']} | {a['title']} | {a['status']} | "
            f"{a['finding_count']} | {a['open_findings']} |"
        )
    lines.append("")

    for a in audits:
        full = get_audit(project_id, a["id"])
        lines.append(f"## {a['id']}: {a['title']}")
        lines.append("")
        lines.append(f"- Auditor: {full.get('auditor', '')}")
        lines.append(f"- Scope: {full.get('scope', '')}")
        lines.append(f"- Date: {full.get('date', '')}")
        lines.append("")
        if full.get("findings"):
            lines.append("| Finding | Severity | Status | Description |")
            lines.append("|---|---|---|---|")
            for f in full["findings"]:
                lines.append(
                    f"| {f['id']} | {f.get('severity','')} | {f['status']} | "
                    f"{f.get('description','')} |"
                )
        else:
            lines.append("_No findings._")
        lines.append("")

    out = workspace._project_dir(project_id) / ".osh" / "evidence" / "qa-audit-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


# ── Helpers ───────────────────────────────────────────────────────────────

def _normalize_finding(body: dict[str, Any]) -> dict:
    desc = (body.get("description") or body.get("title") or "").strip()
    if not desc:
        raise ValueError("finding description is required")
    severity = (body.get("severity") or "medium").strip().lower()
    if severity not in SEVERITIES:
        severity = "medium"
    return {
        "id": body.get("id") or _new_id("FN"),
        "description": desc,
        "severity": severity,
        "status": "open",
        "created_at": _now(),
        "updated_at": _now(),
    }
