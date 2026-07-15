#!/usr/bin/env python3
"""
Dashboard Writer (P1).

Integrates swe_status writing and coverage-trend continuous collection
into the yuleOSH CI pipeline. This module is called at the end of each
CI layer run and after pipeline completion.

Functions:
    - write_swe_status(): Writes SWE.x status records to dashboard DB
    - write_coverage_trend(): Continuous coverage-trend collection
    - write_kpi_trend(): Writes process KPIs
    - run_dashboard_update(): Orchestrator that runs all of the above
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.dashboard_writer")

# ── KG integration guard ────────────────────────────────────────────
_HAS_KG: bool | None = None


def _check_kg_available() -> bool:
    """Check if the KG module is importable."""
    global _HAS_KG
    if _HAS_KG is None:
        try:
            from yuleosh import knowledge_graph  # noqa: F401
            _HAS_KG = True
        except ImportError:
            _HAS_KG = False
    return _HAS_KG

DASHBOARD_DB_DIR = Path(".yuleosh") / "reports"
SWE_STATUS_FILE = "swe-status.jsonl"
PROCESS_KPI_FILE = "process-kpi.jsonl"


# ── SWE Status Writing ────────────────────────────────────────────────

SWE_PHASES = [
    "SWE.1", "SWE.2", "SWE.3", "SWE.4",
    "SWE.5", "SWE.6", "SWE.7", "SWE.8",
    "SWE.9", "SWE.10",
]


def _swe_status_from_kg(project_dir: str | Path) -> dict[str, str]:
    """Query KG for real ASPICE evidence, return SWE phase status dict.

    Checks the project's KG database and extracts SWE phase status
    from actual traceability data rather than file probes.

    Returns:
        Dict mapping SWE phase keys to status values. Only includes
        phases where KG data was found. Returns empty dict when KG
        store is uninitialized or unavailable (graceful fallback).
    """
    project_path = Path(project_dir)
    if not _check_kg_available():
        return {}

    from yuleosh.knowledge_graph import (
        get_store,
        get_confirmation_trace,
        list_snapshots,
        get_graph_stats,
    )
    from yuleosh.knowledge_graph.queries import get_aspice_coverage

    # Resolve KG database path for this project
    kg_db_path = str(project_path / ".yuleosh" / "knowledge_graph.db")
    if not os.path.exists(kg_db_path):
        log.debug("No KG database at %s — skipping KG SWE status", kg_db_path)
        return {}

    try:
        store = get_store(db_path=kg_db_path)
    except Exception as exc:
        log.warning("Cannot open KG store: %s — falling back to file probe", exc)
        return {}

    try:
        stats = get_graph_stats(store)
        if stats.get("total_nodes", 0) == 0:
            log.debug("KG store has 0 nodes — skipping KG SWE status")
            return {}

        coverage = get_aspice_coverage(store)
        confirms = get_confirmation_trace(store)
        snapshots = list_snapshots(store)

        kg_status: dict[str, str] = {}

        # SWE.4: unit layer covers > 0
        unit_count = coverage.get("unit", {}).get("total_covers", 0)
        if unit_count > 0:
            kg_status["SWE.4"] = "completed"

        # SWE.5: validates edges (confirmation test) > 0
        confirm_count = len(confirms)
        if confirm_count > 0:
            kg_status["SWE.5"] = "completed"

        # SWE.8: CI snapshots count
        snap_count = len(snapshots)
        if snap_count >= 3:
            kg_status["SWE.8"] = "validated"
        elif snap_count > 0:
            kg_status["SWE.8"] = "completed"

        # SWE.10: bidirectional traceability
        req_count = stats.get("nodes_by_type", {}).get("requirement", 0)
        covers_count = stats.get("edges_by_type", {}).get("covers", 0)
        if req_count > 0 and covers_count >= req_count:
            kg_status["SWE.10"] = "validated"
        elif covers_count > 0:
            kg_status["SWE.10"] = "completed"

        log.info(
            "KG SWE status: %s (coverage=%s confirms=%s snapshots=%s reqs=%d covers=%d)",
            kg_status,
            unit_count,
            confirm_count,
            snap_count,
            req_count,
            covers_count,
        )
        return kg_status

    except Exception as exc:
        log.warning("KG query failed: %s — falling back to file probe", exc)
        return {}


def write_swe_status(
    project_dir: str | Path,
    spec_path: str | Path | None = None,
    force: bool = False,
) -> dict:
    """Write SWE.x status records (ASPICE compliance level) to dashboard DB.

    Evaluates the current project state and classifies each SWE.x phase
    as one of: not_started, in_progress, completed, validated.

    KG data takes priority for specific phases (SWE.4, SWE.5, SWE.8, SWE.10)
    over file-based probes. Gracefully falls back when KG is unavailable.

    Args:
        project_dir: Project root directory.
        spec_path: Optional path to spec file for SWE.1 analysis.
        force: Force write even if no changes detected.

    Returns:
        Dict with sweephase status records.
    """
    project_path = Path(project_dir)
    db_path = project_path / DASHBOARD_DB_DIR / SWE_STATUS_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect evidence from the project (file probes)
    evidence: dict[str, list[str]] = defaultdict(list)

    # SWE.1: Specification exists?
    spec = spec_path and Path(spec_path)
    if not spec or not spec.exists():
        spec = project_path / "docs" / "spec.md"
    if spec and spec.exists():
        evidence["SWE.1"].append("spec defined")
    spec_check = project_path / ".osh" / "sessions"
    if spec_check.exists():
        spec_reports = list(spec_check.rglob("spec-check.json"))
        if spec_reports:
            for r in spec_reports:
                evidence["SWE.1"].append(f"spec validated: {r.parent.name}")

    # SWE.2: Architectural design?
    arch_docs = []
    for pattern in ["docs/architecture.md", "docs/**/arch*.md"]:
        arch_docs.extend(project_path.glob(pattern))
    if arch_docs:
        evidence["SWE.2"].append(f"architecture: {len(arch_docs)} doc(s)")

    # SWE.3: Detailed design?
    for pattern in ["docs/**/design*.md", "docs/**/detail*.md"]:
        evidence["SWE.3"].extend(
            f"design: {str(p.relative_to(project_path))}"
            for p in project_path.glob(pattern)
        )

    # SWE.4: Unit verification (MISRA + static analysis)
    misra_report = project_path / ".yuleosh" / "reports" / "misra-report.json"
    if misra_report.exists():
        try:
            with open(misra_report) as f:
                mr = json.load(f)
            evidence["SWE.4"].append(
                f"misra: {mr.get('summary', {}).get('total_violations', '?')} violations"
            )
        except (json.JSONDecodeError, OSError):
            evidence["SWE.4"].append("misra: report exists (unreadable)")

    # SWE.5: Integration test?
    for pattern in ["tests/**/test_integration*", "tests/**/test_int*"]:
        tests = list(project_path.glob(pattern))
        if tests:
            evidence["SWE.5"].append(f"integration tests: {len(tests)} files")

    # SWE.6: Qualification test?
    swe6_spec = project_path / "docs" / "swe6-confirmation-spec.md"
    if swe6_spec.exists():
        evidence["SWE.6"].append("qualification spec defined")
    swe6_tests = list(project_path.glob("tests/test_swe6/**/*.py"))
    swe6_tests += list(project_path.glob("tests/test_swe6/**/*.c"))
    if swe6_tests:
        evidence["SWE.6"].append(f"qualification tests: {len(swe6_tests)} files")

    # SWE.7: C code review?
    review_evidence = project_path / ".yuleosh" / "reports" / "gscr-report.json"
    if review_evidence.exists():
        evidence["SWE.7"].append("code review report exists")
    code_reviews = list(project_path.rglob("**/code-review.json"))
    if code_reviews:
        evidence["SWE.7"].append(f"code reviews: {len(code_reviews)} session(s)")

    # SWE.8: CI pipeline status?
    ci_reports = list(project_path.glob(".yuleosh/reports/ci-final-report.json"))
    if ci_reports:
        evidence["SWE.8"].append("CI final report exists")
    for pattern in [".yuleosh/reports/layer*-report.json"]:
        reports = list(project_path.glob(pattern))
        if reports:
            evidence["SWE.8"].append(f"CI layer reports: {len(reports)}")

    # SWE.9: Defect management?
    defect_log = project_path / ".yuleosh" / "reports" / "defect-escape.jsonl"
    if defect_log.exists():
        evidence["SWE.9"].append("defect tracking active")

    # SWE.10: Change management?
    traceability = project_path / ".yuleosh" / "reports" / "traceability-report.json"
    if traceability.exists():
        evidence["SWE.10"].append("traceability matrix exists")

    # Classify each phase from file evidence
    status: dict[str, str] = {}
    for phase in SWE_PHASES:
        ev = evidence.get(phase, [])
        if len(ev) >= 3:
            status[phase] = "validated"
        elif len(ev) >= 1:
            status[phase] = "completed"
        elif any("spec" in str(e) for e in ev):
            status[phase] = "in_progress"
        else:
            status[phase] = "not_started"

    # Override SWE.6 if test code exists
    if swe6_tests:
        status["SWE.6"] = "completed"

    # ── Merge KG data (higher priority) ──────────────────────────────
    kg_status = _swe_status_from_kg(project_dir)
    for phase, kg_value in kg_status.items():
        status[phase] = kg_value
        evidence[phase].append(f"kg: {kg_value}")

    # Build status record
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "evidence_summary": {k: v for k, v in evidence.items()},
    }

    # Read existing to avoid duplicate entries
    existing_records: list[dict] = []
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    # Only append if status changed (or forced)
    if not force and existing_records:
        last = existing_records[-1].get("status", {})
        if last == status:
            log.debug("SWE status unchanged — skipping write")
            return record

    with open(db_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info("SWE status written: %s", status)
    return record


# ── Coverage Trend Continuous Collection ──────────────────────────────


def write_coverage_trend(project_dir: str | Path) -> dict:
    """Write coverage-trend record from latest test/CI run.

    Wrapper around coverage_trend.record_coverage() that ensures
    consistent output format for dashboard ingestion.

    Returns:
        Dict with coverage data written.
    """
    from yuleosh.ci.coverage_trend import record_coverage, show_coverage_trend

    project_path = Path(project_dir)

    # Record current coverage
    record_coverage(str(project_path))

    # Read the latest entry that was just written
    trend_file = project_path / DASHBOARD_DB_DIR / "coverage-trend.jsonl"
    if trend_file.exists():
        with open(trend_file, encoding="utf-8") as f:
            lines = f.readlines()
        latest = json.loads(lines[-1].strip()) if lines else {}
    else:
        latest = {}

    log.info(
        "Coverage trend recorded: C=%s (line) / %s (branch)",
        latest.get("c", {}).get("line_rate"),
        latest.get("c", {}).get("branch_rate"),
    )
    return latest


# ── KPI Trend ─────────────────────────────────────────────────────────


def write_kpi_trend(project_dir: str | Path, force: bool = False) -> dict:
    """Write process KPI trend record (MISRA violations, coverage, CI passes).

    Appends to `.yuleosh/reports/process-kpi.jsonl`.
    """
    from yuleosh.ci.config import load_ci_config

    project_path = Path(project_dir)
    db_path = project_path / DASHBOARD_DB_DIR / PROCESS_KPI_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Collect current KPIs
    kpi: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # MISRA violations
    misra_report = project_path / ".yuleosh" / "reports" / "misra-report.json"
    if misra_report.exists():
        try:
            with open(misra_report) as f:
                mr = json.load(f)
            kpi["misra_violations"] = mr.get("summary", {}).get("total_violations", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # Coverage
    cov_trend = project_path / DASHBOARD_DB_DIR / "coverage-trend.jsonl"
    if cov_trend.exists():
        with open(cov_trend) as f:
            lines = [l.strip() for l in f if l.strip()]
        if lines:
            try:
                latest_cov = json.loads(lines[-1])
                c_cov = latest_cov.get("c", {})
                kpi["c_line_coverage"] = c_cov.get("line_rate")
                kpi["c_branch_coverage"] = c_cov.get("branch_rate")
            except (json.JSONDecodeError, IndexError):
                pass

    # CI layers status
    ci_dir = project_path / ".yuleosh" / "reports"
    ci_final = ci_dir / "ci-final-report.json"
    if ci_final.exists():
        try:
            with open(ci_final) as f:
                cf = json.load(f)
            kpi["ci_status"] = cf.get("status", "unknown")
            kpi["ci_layers"] = cf.get("layers", [])
        except (json.JSONDecodeError, OSError):
            pass

    # Deviations count (Known Rate proxy)
    cfg = load_ci_config(str(project_path))
    if cfg and cfg.misra and cfg.misra.deviations:
        kpi["deviations_count"] = len(cfg.misra.deviations)

    # Write trend record (only if data changed, or forced)
    existing: list[dict] = []
    if db_path.exists():
        with open(db_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    if not force and existing and len(kpi) > 1:
        last = existing[-1]
        # Skip if key metrics unchanged
        unchanged = (
            kpi.get("misra_violations") == last.get("misra_violations")
            and kpi.get("c_line_coverage") == last.get("c_line_coverage")
            and kpi.get("ci_status") == last.get("ci_status")
        )
        if unchanged:
            log.debug("KPI unchanged — skipping write")
            return kpi

    with open(db_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(kpi, ensure_ascii=False) + "\n")

    log.info("Process KPI recorded: misra=%s coverage=%s",
             kpi.get("misra_violations"), kpi.get("c_line_coverage"))
    return kpi


# ── Orchestrator ──────────────────────────────────────────────────────


def run_dashboard_update(
    project_dir: str | Path,
    spec_path: str | Path | None = None,
    force: bool = False,
) -> dict:
    """Run all dashboard updates: SWE status + coverage trend + KPI trend.

    Called at the end of CI pipeline runs and on-demand.

    Args:
        project_dir: Project root directory.
        spec_path: Optional spec path for SWE.1 analysis.
        force: Force write even if no changes detected.

    Returns:
        Dict with all update results.
    """
    log.info("Running dashboard update for %s", project_dir)

    swe = write_swe_status(project_dir, spec_path, force)
    cov = write_coverage_trend(project_dir)
    kpi = write_kpi_trend(project_dir, force)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "swe_status": swe,
        "coverage_trend": cov,
        "kpi_trend": kpi,
        "status": "completed",
    }

    # Also update the evidence bundle
    _update_evidence_bundle(project_dir, result)

    return result


def _update_evidence_bundle(project_dir: str | Path, result: dict) -> None:
    """Mirror dashboard data into evidence-bundle/trend-data/."""
    import shutil

    project_path = Path(project_dir)

    # Copy trend data to evidence-bundle for CL2 audit
    src_files = {
        "coverage-trend.jsonl": "coverage-trend.jsonl",
        "swe-status.jsonl": None,  # May not exist yet
        "process-kpi.jsonl": "process-kpi.jsonl",
    }

    for src_name, dst_name in src_files.items():
        src = project_path / DASHBOARD_DB_DIR / src_name
        dst_name = dst_name or src_name
        dst = project_path / ".yuleosh" / "evidence-bundle" / "trend-data" / dst_name
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

    # Copy misra-trend
    src = project_path / DASHBOARD_DB_DIR / "misra-trend.jsonl"
    if src.exists():
        dst = project_path / ".yuleosh" / "evidence-bundle" / "trend-data" / "misra-trend.jsonl"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))


# ── CLI ──────────────────────────────────────────────────────────────────


def main():
    """CLI entry point for dashboard update."""
    import argparse

    parser = argparse.ArgumentParser(
        description="yuleOSH Dashboard Writer — swe_status + coverage-trend"
    )
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=os.environ.get("OSH_HOME", "."),
        help="Project root directory",
    )
    parser.add_argument(
        "--spec",
        default=None,
        help="Path to spec file for SWE.1 analysis",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force write even if data unchanged",
    )
    args = parser.parse_args()

    result = run_dashboard_update(args.project_dir, args.spec, args.force)

    print(f"\n  📊 Dashboard Update")
    print(f"  {'─' * 40}")
    swe = result.get("swe_status", {})
    swe_status = swe.get("status", {})
    if swe_status:
        completed = sum(1 for v in swe_status.values() if v in ("completed", "validated"))
        total = len(swe_status)
        print(f"  SWE Status: {completed}/{total} phases completed")
        for phase, st in swe_status.items():
            icon = {"validated": "✅", "completed": "📗", "in_progress": "🔄", "not_started": "⬜"}
            print(f"    {icon.get(st, '•')} {phase}: {st}")
    print(f"  Coverage: {result.get('coverage_trend', {}).get('c', {}).get('line_rate', 'N/A')}")
    kpi = result.get("kpi_trend", {})
    print(f"  KPI: misra={kpi.get('misra_violations', 'N/A')} cov={kpi.get('c_line_coverage', 'N/A')}")
    print(f"  Status: {result['status']}")
    print()


if __name__ == "__main__":
    main()
