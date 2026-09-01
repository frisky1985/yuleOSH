#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Traceability matrix API — mounted at /api/v1/matrix/.

Aggregates Requirement ↔ Code ↔ Test ↔ Review ↔ Step ↔ Evidence into a
single traceability matrix (RTM).

The Requirement/Code/Test/Review/Step engine already exists in
``yuleosh.alm.traceability.generate_lrt`` — this module reuses it and
ADDS the one column it does not produce: **Evidence**.  Evidence presence
per requirement is derived by scanning the project's compliance evidence
pack (``.osh/evidence/``) for the requirement id.

Endpoints:
    GET /api/v1/matrix?project=xxx        — full traceability matrix
                                            (one row per requirement + 5
                                            coverage columns + gaps)
    GET /api/v1/matrix/gaps?project=xxx   — gap-only view (missing dimensions
                                            per requirement + by-type counts)

Design notes:
    * Reads REAL files only.  When no spec file exists the endpoints return
      an empty matrix plus a note — no fabricated data.
    * Reuses :mod:`.requirements` project discovery / scanning helpers so the
      ``project`` semantics match ``/api/v1/requirements`` exactly.
    * External ALM (Jira / Polarion) is NOT a prerequisite: requirement data
      comes from local spec markdown, evidence from local ``.osh/evidence/``.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth
from .requirements import (
    _q,
    _resolve_project_dir,
    _find_spec_files,
    _iter_project_files,
    _is_text_file,
    _classify_artifact,
    TEXT_EXTS,
    MAX_SCAN_BYTES,
    MAX_SCAN_FILES,
)

log = logging.getLogger("api.matrix")


# ── Evidence scan (the one dimension generate_lrt does not produce) ────────

def _scan_evidence(proj_dir: Path, req_ids_upper: list[str]) -> set[str]:
    """Return the set of requirement ids that appear in the project's
    compliance evidence pack (``.osh/evidence/``).

    Evidence = the generated compliance artifacts (acceptance-matrix.md,
    traceability-matrix.json, requirement-coverage.md, review-log.json,
    compliance-pack.zip contents, audit manifests, …).  A requirement is
    considered "covered by evidence" when its id is referenced inside any
    text-evidence file.
    """
    hits: set[str] = set()
    ev_dir = proj_dir / ".osh" / "evidence"
    if not ev_dir.is_dir():
        return hits
    count = 0
    for f in ev_dir.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in TEXT_EXTS:
            continue
        if count >= MAX_SCAN_FILES:
            break
        count += 1
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content) > MAX_SCAN_BYTES:
            content = content[:MAX_SCAN_BYTES]
        upper = content.upper()
        for rid in req_ids_upper:
            if rid and rid in upper:
                hits.add(rid)
    return hits


def _scan_artifact_coverage(proj_dir: Path, req_ids_upper: list[str]) -> dict[str, set[str]]:
    """One-pass scan of the whole project: req_id -> set of artifact types
    (design / code / test / evidence) it is referenced from.

    Reuses the same classifier as the requirements API so "evidence" here
    matches the semantics used by ``/api/v1/requirements/gaps``.  Used only
    as a secondary signal (the authoritative evidence signal is
    ``_scan_evidence`` over ``.osh/evidence/``).
    """
    coverage: dict[str, set[str]] = {rid: set() for rid in req_ids_upper}
    if not proj_dir.is_dir():
        return coverage
    count = 0
    for f in _iter_project_files(proj_dir):
        if not _is_text_file(f):
            continue
        # Skip spec markdown — it is the SOURCE of requirement ids, not an
        # artifact that "covers" them.
        if f.name.lower().startswith("spec") and f.suffix.lower() == ".md":
            continue
        if count >= MAX_SCAN_FILES:
            break
        count += 1
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content) > MAX_SCAN_BYTES:
            content = content[:MAX_SCAN_BYTES]
        upper = content.upper()
        art_type = _classify_artifact(f, proj_dir)
        for rid in req_ids_upper:
            if rid and rid in upper:
                coverage[rid].add(art_type)
    return coverage


# ── Response builders ───────────────────────────────────────────────────────

def _empty_summary() -> dict:
    return {
        "total": 0,
        "with_code": 0,
        "with_test": 0,
        "with_review": 0,
        "with_step": 0,
        "with_evidence": 0,
        "test_coverage_pct": 0.0,
        "evidence_coverage_pct": 0.0,
    }


def _build_matrix(reqs: list[dict], evidence_hits: set[str],
                  artifact_coverage: dict[str, set[str]]) -> list[dict]:
    """Flatten ``generate_lrt`` requirement rows into a compact matrix row."""
    rows: list[dict] = []
    for r in reqs:
        rid = (r.get("req_id") or r.get("id") or "")
        rid_upper = rid.upper()
        # Evidence: authoritative source = .osh/evidence/ pack; fall back to
        # the generic artifact scan classifying a file as "evidence".
        has_evidence = rid_upper in evidence_hits or "evidence" in artifact_coverage.get(rid_upper, set())
        has_step = bool(r.get("step_handlers"))
        rows.append({
            "req_id": rid,
            "id": r.get("id"),
            "statement": r.get("statement", ""),
            "section": r.get("section", ""),
            "coverage": {
                "code": bool(r.get("has_code")),
                "test": bool(r.get("has_test")),
                "review": bool(r.get("has_review")),
                "step": has_step,
                "evidence": has_evidence,
            },
            "link_method": r.get("match_method"),
            "code_files": r.get("code_files", []) or [],
            "test_reports": r.get("test_reports", []) or [],
            "step_handlers": r.get("step_handlers", []) or [],
            "reviews": r.get("reviews", []) or [],
            "swr_mapping": bool(r.get("swr_mapping", False)),
        })
    return rows


def _summarize(rows: list[dict]) -> dict:
    total = len(rows)
    with_ev = sum(1 for r in rows if r["coverage"]["evidence"])
    return {
        "total": total,
        "with_code": sum(1 for r in rows if r["coverage"]["code"]),
        "with_test": sum(1 for r in rows if r["coverage"]["test"]),
        "with_review": sum(1 for r in rows if r["coverage"]["review"]),
        "with_step": sum(1 for r in rows if r["coverage"]["step"]),
        "with_evidence": with_ev,
        "test_coverage_pct": round(
            sum(1 for r in rows if r["coverage"]["test"]) / total * 100, 1
        ) if total else 0.0,
        "evidence_coverage_pct": round(with_ev / total * 100, 1) if total else 0.0,
    }


def _build_gaps(rows: list[dict]) -> dict:
    by_type = {
        "no_code": 0, "no_test": 0, "no_review": 0,
        "no_step": 0, "no_evidence": 0,
    }
    items: list[dict] = []
    for r in rows:
        missing: list[str] = []
        if not r["coverage"]["code"]:
            missing.append("code"); by_type["no_code"] += 1
        if not r["coverage"]["test"]:
            missing.append("test"); by_type["no_test"] += 1
        if not r["coverage"]["review"]:
            missing.append("review"); by_type["no_review"] += 1
        if not r["coverage"]["step"]:
            missing.append("step"); by_type["no_step"] += 1
        if not r["coverage"]["evidence"]:
            missing.append("evidence"); by_type["no_evidence"] += 1
        if missing:
            items.append({"req_id": r["req_id"], "missing": missing})
    return {"total_gaps": len(items), "by_type": by_type, "items": items}


# ── Handler ─────────────────────────────────────────────────────────────────

@require_auth
def handle_matrix(method: str, path_tail: str, body: dict, query: dict,
                  handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Route /api/v1/matrix/... requests.

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth.
    """
    if method == "GET" and path_tail in ("", "gaps"):
        return _matrix(query, gaps_only=(path_tail == "gaps"))
    return json_error(
        f"Unknown matrix sub-path or method: {method} {path_tail}", 404
    )


def _matrix(query: dict, gaps_only: bool = False) -> tuple[dict, int]:
    """GET /api/v1/matrix[?project=xxx] — build the traceability matrix."""
    from yuleosh.alm.traceability import generate_lrt

    project = _q(query, "project")
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err
    assert proj_dir is not None  # err is None on success

    # Early, friendly note when there is no spec to build a matrix from.
    spec_files = _find_spec_files(proj_dir)
    if not spec_files:
        return json_ok({
            "project": project,
            "generated_at": None,
            "requirements": [],
            "summary": _empty_summary(),
            "gaps": {"total_gaps": 0, "by_type": {}, "items": []},
            "note": (
                f"项目 '{project}' 未找到 spec 文件"
                f"（projects/{project}/spec*.md 或 .osh/specs 缓存），无法构建追溯矩阵"
            ),
        })

    try:
        lrt = generate_lrt(str(proj_dir))
    except Exception as e:  # noqa: BLE001 — read-only scan must not 500 the UI
        log.warning("generate_lrt failed for %s: %s", project, e)
        return json_ok({
            "project": project,
            "generated_at": None,
            "requirements": [],
            "summary": _empty_summary(),
            "gaps": {"total_gaps": 0, "by_type": {}, "items": []},
            "note": f"追溯矩阵计算失败：{e}",
        })

    lrm = lrt.get("lrm", {}) or {}
    reqs = lrm.get("requirements", []) or []

    req_ids_upper = [
        (r.get("req_id") or r.get("id") or "").upper() for r in reqs
    ]
    evidence_hits = _scan_evidence(proj_dir, req_ids_upper)
    artifact_coverage = _scan_artifact_coverage(proj_dir, req_ids_upper)

    rows = _build_matrix(reqs, evidence_hits, artifact_coverage)
    summary = _summarize(rows)
    gaps = _build_gaps(rows)

    if gaps_only:
        return json_ok({
            "project": project,
            "generated_at": lrt.get("generated_at"),
            "summary": summary,
            "gaps": gaps,
            "note": None,
        })

    return json_ok({
        "project": project,
        "generated_at": lrt.get("generated_at"),
        "requirements": rows,
        "summary": summary,
        "gaps": gaps,
        "note": None,
    })
