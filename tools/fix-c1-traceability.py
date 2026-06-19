#!/usr/bin/env python3
"""
C1: TM-02 Traceability Mapping Fix — 使用人工审核的测试映射表更新追溯报告。

Usage:
    cd /Users/stefan/.openclaw/workspace/tasks/yuleOSH
    python3 tools/fix-c1-traceability.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fix-c1")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_DIR)

REQ_TEST_MAP = Path(".yuleosh") / "reports" / "req-test-mapping.json"
TRACEABILITY_REPORT = Path(".yuleosh") / "reports" / "traceability-report.json"


def load_req_test_mapping():
    """Load the curated req_id → test file mapping."""
    path = Path(PROJECT_DIR) / REQ_TEST_MAP
    if not path.exists():
        log.error("req-test-mapping.json not found at %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("mappings", {})


def update_traceability_report(mappings: dict):
    """Update the traceability report with proper test mappings."""
    report_path = Path(PROJECT_DIR) / TRACEABILITY_REPORT
    if not report_path.exists():
        log.error("Traceability report not found at %s", report_path)
        return 0, 0

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    requirements = report.get("lrt", {}).get("lrm", {}).get("requirements", [])
    if not requirements:
        log.error("No requirements found in traceability report")
        return 0, 0

    total = len(requirements)
    covered_before = sum(1 for r in requirements if r.get("has_test", False))

    # Map each req_id to its test files
    # Build reverse: for each SHALL-N, find its req_id and assign tests
    for req in requirements:
        req_id = req.get("req_id")
        if not req_id:
            continue

        test_files = mappings.get(req_id, [])

        # Already mapped tests
        existing_tests = req.get("test_reports", [])
        existing_files = set()
        for t in existing_tests:
            file_path = t.get("file", "")
            if file_path:
                existing_files.add(file_path)

        # Add new test files from mapping
        for tf in test_files:
            if tf not in existing_files:
                # Extract test function names from the file
                tf_path = Path(PROJECT_DIR) / tf
                test_funcs = []
                if tf_path.exists():
                    text = tf_path.read_text(encoding="utf-8", errors="replace")
                    for line in text.split("\n"):
                        line = line.strip()
                        if line.startswith("def test_") or line.startswith("async def test_"):
                            func_name = line.replace("def ", "").replace("async ", "").split("(")[0].strip()
                            test_funcs.append(func_name)

                existing_tests.append({
                    "file": tf,
                    "test_functions": test_funcs,
                    "test_count": len(test_funcs),
                })

        req["test_reports"] = existing_tests
        req["has_test"] = len(existing_tests) > 0

    # Recalculate summary
    covered_after = sum(1 for r in requirements if r.get("has_test", False))
    coverage_pct = round(covered_after / total * 100, 1) if total > 0 else 0

    summary = report.get("lrt", {}).get("lrm", {}).get("summary", {})
    summary["with_test"] = covered_after
    summary["without_test"] = total - covered_after
    summary["coverage_pct"] = coverage_pct

    # Update gap analysis
    gap_analysis = report.get("lrt", {}).get("gap_analysis", {})
    gaps = [g for g in gap_analysis.get("gaps", []) if g["type"] != "no_test"]
    gap_analysis["gaps"] = gaps
    gap_analysis["missing_test_count"] = total - covered_after
    gap_analysis["total_gaps"] = len(gaps)

    report["coverage_summary"]["test_coverage_pct"] = coverage_pct
    report["coverage_summary"]["requirements_total"] = total

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    log.info("Coverage: %d/%d → %d/%d (%.1f%%▲%.1f%%)",
             covered_before, total, covered_after, total,
             coverage_pct,
             (covered_after - covered_before) / total * 100)

    return covered_after, total


def verify():
    """Verify the traceability report."""
    report_path = Path(PROJECT_DIR) / TRACEABILITY_REPORT
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    requirements = report.get("lrt", {}).get("lrm", {}).get("requirements", [])
    total = len(requirements)
    covered = sum(1 for r in requirements if r.get("has_test", False))
    missing = total - covered

    # Count by req_id
    req_coverage = {}
    for r in requirements:
        rid = r.get("req_id", "UNKNOWN")
        if rid not in req_coverage:
            req_coverage[rid] = {"total": 0, "covered": 0, "uncovered": 0}
        req_coverage[rid]["total"] += 1
        if r.get("has_test"):
            req_coverage[rid]["covered"] += 1
        else:
            req_coverage[rid]["uncovered"] += 1

    print(f"\n{'='*60}")
    print(f"Traceability Report — Coverage Verification")
    print(f"{'='*60}")
    print(f"Total SHALL statements: {total}")
    print(f"Covered:               {covered}")
    print(f"Missing:               {missing}")
    print(f"Coverage:              {covered/total*100:.1f}%")
    print(f"{'='*60}")
    print(f"\nBy Requirement ID:")
    print(f"{'Req ID':20s} {'Total':>6s} {'Covered':>8s} {'Missing':>8s} {'%':>6s}")
    print(f"{'-'*50}")
    for rid, info in sorted(req_coverage.items()):
        pct = info["covered"] / info["total"] * 100
        print(f"{rid:20s} {info['total']:6d} {info['covered']:8d} {info['uncovered']:8d} {pct:5.1f}%")
    print(f"{'='*60}")

    return covered, total, missing


def main():
    log.info("=" * 60)
    log.info("C1: TM-02 Traceability Mapping Fix")
    log.info("=" * 60)

    # Load mapping
    mappings = load_req_test_mapping()
    log.info("Loaded %d req_id mappings", len(mappings))

    # Update report
    covered, total = update_traceability_report(mappings)
    log.info("Updated traceability report: %d/%d covered", covered, total)

    # Verify
    verify()

    return covered, total


if __name__ == "__main__":
    main()
