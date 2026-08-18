#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Change Proposal (CP) management — OpenSpec spec evolution.

A Change Proposal is how a spec evolves after initial creation. Each CP
lives under ``<project>/.osh/changes/<change-id>/``:

    <change-id>/
    ├── proposal.md   # REQUIRED — frontmatter + Why / What Changes / Impact / Rollback
    ├── tasks.md      # REQUIRED — machine-parseable implementation checklist
    ├── design.md     # OPTIONAL — technical approach
    └── specs/        # OPTIONAL — spec increments to merge on archive

Status machine: proposed → approved → implemented → archived.

- ``proposed``   — created, awaiting review (pipeline spec-cp-review)
- ``approved``   — review passed; implementation MAY proceed
- ``implemented``— tasks done, spec updated; ready to archive
- ``archived``   — moved to archive/<date>-<id>/, spec baseline updated

Gate semantics (CP-05): a CP that is ``approved`` but not yet
``implemented`` BLOCKS codegen/development — the pipeline must not
implement new work on top of an approved-but-unapplied change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

CP_STATES: tuple[str, ...] = ("proposed", "approved", "implemented", "archived")
_VALID_STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "proposed": ("approved",),
    "approved": ("implemented",),
    "implemented": ("archived",),
    "archived": (),
}

PROPOSAL_TEMPLATE = """\
---
id: {change_id}
status: proposed
title: {title}
created: {created}
affects: [{affects}]
---

## Why

(为什么需要这个变更 — 背景 / 动机 / 要解决的问题)

## What Changes

(变更内容 — 影响哪些 spec / 哪些行为)

## Impact

(影响面 — 依赖方 / 兼容性 / 风险)

## Rollback Plan

(回滚方案 — 变更失败时如何恢复)
"""

TASKS_TEMPLATE = """\
## Tasks

- [ ] T1 实现核心变更
- [ ] T2 补充/更新测试（RED→GREEN）
- [ ] T3 更新 spec 与文档
"""


@dataclass
class ChangeProposal:
    """A single change proposal loaded from disk."""

    change_id: str
    path: Path
    status: str = "proposed"
    title: str = ""
    created: str = ""
    affects: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)

    @property
    def proposal_path(self) -> Path:
        return self.path / "proposal.md"

    @property
    def tasks_path(self) -> Path:
        return self.path / "tasks.md"

    @property
    def is_blocking(self) -> bool:
        """True when an approved change has not been implemented yet."""
        return self.status == "approved"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-ish frontmatter block. Returns (meta, body)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in ("affects",):
            meta[key] = [v.strip() for v in value.strip("[]").split(",") if v.strip()]
        else:
            meta[key] = value
    return meta, m.group(2)


def find_changes_dir(project_dir: str | Path) -> Path:
    """Locate the .osh/changes directory (created on demand)."""
    root = Path(project_dir)
    return root / ".osh" / "changes"


def list_changes(project_dir: str | Path) -> list[ChangeProposal]:
    """Return all change proposals sorted by change_id."""
    changes_dir = find_changes_dir(project_dir)
    if not changes_dir.exists():
        return []
    proposals: list[ChangeProposal] = []
    for child in sorted(changes_dir.iterdir()):
        if not child.is_dir():
            continue
        cp = load_proposal(project_dir, child.name)
        if cp is not None:
            proposals.append(cp)
    return proposals


def load_proposal(project_dir: str | Path, change_id: str) -> Optional[ChangeProposal]:
    """Load a single change proposal, or None if missing/invalid id."""
    changes_dir = find_changes_dir(project_dir)
    cp_dir = changes_dir / change_id
    proposal_file = cp_dir / "proposal.md"
    if not proposal_file.exists():
        return None
    text = proposal_file.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    tasks: list[str] = []
    tasks_file = cp_dir / "tasks.md"
    if tasks_file.exists():
        tasks = _parse_tasks(tasks_file.read_text(encoding="utf-8"))
    return ChangeProposal(
        change_id=change_id,
        path=cp_dir,
        status=meta.get("status", "proposed"),
        title=meta.get("title", ""),
        created=meta.get("created", ""),
        affects=meta.get("affects", []),
        tasks=tasks,
    )


def _parse_tasks(text: str) -> list[str]:
    """Parse tasks.md into a list of task descriptions."""
    tasks: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*\[\s*\]\s+(.*)$", line)
        if m:
            tasks.append(m.group(1).strip())
    return tasks


def validate_proposal(project_dir: str | Path, change_id: str) -> dict:
    """Validate a change proposal's structure. Returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []
    cp = load_proposal(project_dir, change_id)
    if cp is None:
        return {"valid": False, "errors": [f"change proposal '{change_id}' not found"], "warnings": []}

    if not cp.title:
        errors.append("proposal.md frontmatter missing 'title'")
    if not cp.created:
        errors.append("proposal.md frontmatter missing 'created'")
    if cp.status not in CP_STATES:
        errors.append(f"invalid status '{cp.status}' (expected one of {CP_STATES})")
    if not cp.tasks:
        warnings.append("tasks.md has no unchecked tasks — implementation checklist empty")

    body = _read_proposal_body(cp)
    for section in ("## Why", "## What Changes", "## Impact", "## Rollback Plan"):
        if section not in body:
            warnings.append(f"proposal.md missing recommended section '{section}'")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _read_proposal_body(cp: ChangeProposal) -> str:
    text = cp.proposal_path.read_text(encoding="utf-8")
    _, body = _parse_frontmatter(text)
    return body


def propose_change(
    project_dir: str | Path,
    change_id: str,
    title: str,
    affects: str = "core",
    created: Optional[str] = None,
) -> Path:
    """Create a new change proposal directory with template files."""
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", change_id):
        raise ValueError(f"invalid change_id '{change_id}' (allowed: [a-zA-Z0-9._-])")
    changes_dir = find_changes_dir(project_dir)
    cp_dir = changes_dir / change_id
    if cp_dir.exists():
        raise FileExistsError(f"change proposal '{change_id}' already exists at {cp_dir}")
    cp_dir.mkdir(parents=True, exist_ok=True)
    created = created or datetime.now().strftime("%Y-%m-%d")
    (cp_dir / "proposal.md").write_text(
        PROPOSAL_TEMPLATE.format(change_id=change_id, title=title, created=created, affects=affects),
        encoding="utf-8",
    )
    (cp_dir / "tasks.md").write_text(TASKS_TEMPLATE, encoding="utf-8")
    return cp_dir


def set_status(project_dir: str | Path, change_id: str, new_status: str) -> ChangeProposal:
    """Advance a CP's status along the state machine."""
    if new_status not in CP_STATES:
        raise ValueError(f"invalid status '{new_status}' (expected one of {CP_STATES})")
    cp = load_proposal(project_dir, change_id)
    if cp is None:
        raise FileNotFoundError(f"change proposal '{change_id}' not found")
    allowed = _VALID_STATUS_TRANSITIONS.get(cp.status, ())
    if new_status not in allowed:
        raise ValueError(
            f"invalid transition '{cp.status}' → '{new_status}' "
            f"(allowed from '{cp.status}': {allowed or 'none'})"
        )
    _update_frontmatter_status(cp, new_status)
    return load_proposal(project_dir, change_id)  # type: ignore[return-value]


def _update_frontmatter_status(cp: ChangeProposal, new_status: str) -> None:
    text = cp.proposal_path.read_text(encoding="utf-8")
    updated = re.sub(r"^status:.*$", f"status: {new_status}", text, count=1, flags=re.MULTILINE)
    cp.proposal_path.write_text(updated, encoding="utf-8")


def archive_change(project_dir: str | Path, change_id: str) -> Path:
    """Archive an implemented CP to changes/archive/<date>-<id>/."""
    cp = load_proposal(project_dir, change_id)
    if cp is None:
        raise FileNotFoundError(f"change proposal '{change_id}' not found")
    if cp.status != "implemented":
        raise ValueError(
            f"cannot archive CP '{change_id}' in status '{cp.status}' — must be 'implemented' first"
        )
    changes_dir = find_changes_dir(project_dir)
    archive_root = changes_dir / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / f"{datetime.now().strftime('%Y-%m-%d')}-{change_id}"
    if target.exists():
        target = archive_root / f"{datetime.now().strftime('%Y-%m-%d-%H%M%S')}-{change_id}"
    cp.path.rename(target)
    return target


def get_blocking_cps(project_dir: str | Path) -> list[ChangeProposal]:
    """Return approved-but-not-implemented CPs (gate consumers)."""
    return [cp for cp in list_changes(project_dir) if cp.is_blocking]
