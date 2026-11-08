#!/usr/bin/env python3

# @req RS-005
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Requirement drift detection.

Compares the current requirement statements against an accepted baseline of
content hashes. A changed hash means the requirement text moved while the
linked code/test/review evidence may not have been re-checked — those links
are flagged for re-review instead of silently staying "green".

The baseline lives under ``docs/evidence/baselines/`` (persisted, not
gitignored). It is created on first run and only overwritten when explicitly
accepted via ``YULEOSH_ACCEPT_REQ_BASELINE=1``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

BASELINE_REL = Path("docs/evidence/baselines/requirement-hashes.json")
ACCEPT_ENV = "YULEOSH_ACCEPT_REQ_BASELINE"


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def requirement_hashes(rows: list[dict]) -> dict[str, str]:
    """Map requirement ID → short content hash (whitespace-normalized)."""
    hashes: dict[str, str] = {}
    for row in rows:
        rid = str(row.get("req_id") or "").strip()
        if not rid:
            continue
        digest = hashlib.sha256(_normalize(row.get("statement", "")).encode("utf-8"))
        hashes[rid] = digest.hexdigest()[:16]
    return hashes


def detect_drift(project_dir: str | Path, rows: list[dict]) -> dict:
    """Compare current requirement hashes with the accepted baseline.

    Returns ``changed`` / ``added`` / ``removed`` ID lists plus baseline state.
    On first run the baseline is created and no drift is reported.
    """
    project = Path(project_dir)
    baseline_path = project / BASELINE_REL
    current = requirement_hashes(rows)

    previous: dict[str, str] = {}
    if baseline_path.exists():
        try:
            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
            previous = dict(payload.get("requirements") or {})
        except (OSError, json.JSONDecodeError):
            previous = {}

    accept = os.environ.get(ACCEPT_ENV) == "1"
    created = not previous
    accepted = created or accept

    changed = sorted(
        rid for rid, digest in current.items()
        if rid in previous and previous[rid] != digest
    )
    added = sorted(rid for rid in current if rid not in previous)
    removed = sorted(rid for rid in previous if rid not in current)

    if accepted:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(
                {"schema": "osh-req-baseline-v1", "requirements": current},
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        changed, added, removed = [], [], []

    return {
        "baseline": str(BASELINE_REL),
        "baseline_created": created,
        "baseline_accepted": accepted,
        "compared": len(previous),
        "changed": changed,
        "added": added,
        "removed": removed,
    }
