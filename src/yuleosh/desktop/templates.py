# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Project document template generators (ASPICE SUP/MAN evidence).

The compliance checker recognizes several documents under ``docs/`` (qa-plan,
known-issues, risk-register, project-plan, change-requests, impact-analysis,
...). Without them the corresponding SUP/MAN base practices stay RED. This
module generates starter templates with the right sections so users can fill
in real content instead of hand-writing empty files.

Templates are intentionally **minimal skeletons** — they create documents with
the sections the checker looks for, populated with placeholders, so the
project never claims compliance from a stub.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

DOCS_DIR = "docs"


def _docs_dir(project_id: str) -> Path:
    d = workspace._project_dir(project_id) / DOCS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _header(title: str, doc_id: str, project_id: str) -> str:
    return (
        f"# {title}\n\n"
        f"> Document ID: {doc_id}\n"
        f"> Project: {_project_name(project_id)}\n"
        f"> Generated: {datetime.now():%Y-%m-%d %H:%M}\n"
        f"> Status: DRAFT — fill in real content before using as evidence.\n\n"
    )


def _project_name(project_id: str) -> str:
    try:
        return workspace._load_meta(project_id).get("name", project_id)
    except FileNotFoundError:
        return project_id


# ── Template bodies ───────────────────────────────────────────────────────

def _qa_plan() -> str:
    return (
        "## 1. Scope\n"
        "- [ ] Define quality objectives for this project.\n"
        "- [ ] Identify applicable standards (ASPICE, ISO 26262, ...).\n\n"
        "## 2. Quality Assurance Activities\n"
        "| Activity | Responsible | Frequency | Output |\n"
        "|---|---|---|---|\n"
        "| Requirements review | | | |\n"
        "| Architecture review | | | |\n"
        "| Code review | | | |\n"
        "| Test review | | | |\n"
        "| Configuration audit | | | |\n\n"
        "## 3. Audit Schedule\n"
        "- [ ] Planned audit dates and criteria.\n\n"
        "## 4. Nonconformity Handling\n"
        "- [ ] Escalation and closure process for audit findings.\n"
    )


def _known_issues() -> str:
    return (
        "## Issue Log\n\n"
        "| ID | Title | Severity | Status | Opened | Closed | Owner | Description |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| ISSUE-001 | (sample) | Low | Open | | | | Replace with real issues. |\n\n"
        "## Resolution Process\n"
        "- [ ] Each issue has a root-cause analysis.\n"
        "- [ ] Each issue has a verified fix and closure evidence.\n"
    )


def _risk_register() -> str:
    return (
        "## Risk Register\n\n"
        "| ID | Risk | Likelihood | Impact | Level | Mitigation | Owner | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| RSK-001 | (sample) | Low | Low | Low | | | Open |\n\n"
        "## Review\n"
        "- [ ] Risks reviewed at each project milestone.\n"
    )


def _project_plan() -> str:
    return (
        "## 1. Objectives\n"
        "- [ ] Project goals and success criteria.\n\n"
        "## 2. Schedule\n"
        "| Milestone | Date | Deliverable |\n"
        "|---|---|---|\n\n"
        "## 3. Resources\n"
        "- [ ] Team roles and responsibilities.\n\n"
        "## 4. Estimation\n"
        "- [ ] Effort and cost estimates.\n\n"
        "## 5. Monitoring\n"
        "- [ ] Progress metrics and reporting cadence.\n"
    )


def _change_requests() -> str:
    return (
        "> Changes are also tracked as first-class entities via the change-request "
        "API (see `change-requests/*.json`). This document provides the human-readable "
        "register.\n\n"
        "## Change Register\n\n"
        "| CR ID | Title | Status | Approver | Opened | Closed |\n"
        "|---|---|---|---|---|---|\n\n"
        "## Process\n"
        "- [ ] Every change request goes through impact analysis.\n"
        "- [ ] Approved changes are baselined after implementation.\n"
    )


def _impact_analysis() -> str:
    return (
        "## Impact Analysis Template\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Change Request | |\n"
        "| Affected Requirements | |\n"
        "| Affected Components | |\n"
        "| Schedule Impact | |\n"
        "| Resource Impact | |\n"
        "| Risk Impact | |\n\n"
        "> Automated impact analysis is also available via the change-request "
        "API (`.osh/evidence/impact-analysis-*.json`).\n"
    )


# name → (filename, title, generator)
TEMPLATES: dict[str, tuple[str, str, Any]] = {
    "qa-plan": ("qa-plan.md", "Quality Assurance Plan", _qa_plan),
    "known-issues": ("known-issues.md", "Known Issues Log", _known_issues),
    "risk-register": ("risk-register.md", "Risk Register", _risk_register),
    "project-plan": ("project-plan.md", "Project Plan", _project_plan),
    "change-requests": ("change-requests.md", "Change Request Register", _change_requests),
    "impact-analysis": ("impact-analysis.md", "Impact Analysis", _impact_analysis),
}


def list_templates() -> list[str]:
    return sorted(TEMPLATES)


def generate_doc_template(project_id: str, name: str, overwrite: bool = False) -> dict:
    """Generate one template document under ``docs/``.

    Args:
        project_id: target project.
        name: template key from :data:`TEMPLATES`.
        overwrite: if True, replace an existing file.

    Returns:
        ``{"name", "path", "created"}`` — ``created`` is False when an existing
        file was left untouched (and ``overwrite`` was False).
    """
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template '{name}'. Available: {list_templates()}")

    filename, title, gen = TEMPLATES[name]
    workspace._load_meta(project_id)  # project must exist
    path = _docs_dir(project_id) / filename
    doc_id = f"{name.upper().replace('-', '_')}-{datetime.now():%Y%m%d}"

    if path.exists() and not overwrite:
        return {"name": name, "path": f"{DOCS_DIR}/{filename}", "created": False}

    content = _header(title, doc_id, project_id) + gen()
    path.write_text(content, encoding="utf-8")
    return {"name": name, "path": f"{DOCS_DIR}/{filename}", "created": True}


def generate_doc_templates(project_id: str, names: list[str] | None = None,
                           overwrite: bool = False) -> list[dict]:
    """Generate multiple templates; defaults to all when ``names`` is None."""
    targets = names or list_templates()
    results = []
    for name in targets:
        try:
            results.append(generate_doc_template(project_id, name, overwrite=overwrite))
        except ValueError:
            results.append({"name": name, "path": None, "created": False,
                            "error": "unknown template"})
    return results
