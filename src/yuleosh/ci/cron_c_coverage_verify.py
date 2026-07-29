#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Weekly cron job — C Coverage Gate Verification (QG-006).

Runs the C coverage gate E2E verification pipeline and logs results.
Designed to be invoked by CI scheduler or cron.

Usage:
    python -m yuleosh.ci.cron_c_coverage_verify [--project <path>]

Cron (weekly schedule):
    0 6 * * 1 cd /path/to/project && python3 -m yuleosh.ci.cron_c_coverage_verify
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ci.cron_c_coverage_verify")


def run_weekly_verification(project_path: str) -> dict:
    """Run the weekly C coverage gate verification.

    Calls :func:`verify_c_coverage_gate` and writes a timestamped summary
    to ``.yuleosh/reports/c-coverage-weekly-cron.json``.

    Returns a summary dict with:
        - success: bool
        - line_rate: float or None
        - gate_passed: bool or None
        - p0_alert: bool (True if no .gcda data)
        - cron_timestamp: str
    """
    from yuleosh.ci.verify_c_coverage_gate import verify_c_coverage_gate

    result = verify_c_coverage_gate(project_path)

    summary = {
        "success": result.get("success", False),
        "line_rate": result.get("line_rate"),
        "branch_rate": result.get("branch_rate"),
        "gate_passed": result.get("gate_passed"),
        "gcda_files_found": result.get("gcda_files_found", 0),
        "p0_alert": result.get("gcda_files_found", 0) == 0,
        "cron_timestamp": datetime.now().isoformat(),
        "warnings": result.get("warnings", []),
    }

    project_dir = Path(project_path).resolve()
    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    cron_path = report_dir / "c-coverage-weekly-cron.json"

    with open(cron_path, "w") as f:
        json.dump(summary, f, indent=2)

    log.info("Weekly C coverage verification saved to %s", cron_path)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Weekly C Coverage Gate Verification (QG-006 cron)",
    )
    parser.add_argument(
        "--project", default=".",
        help="Path to the yuleOSH project root (default: current directory)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s [%(name)s] %(message)s",
    )

    summary = run_weekly_verification(args.project)

    print(f"\n  📅 Weekly C Coverage Verification")
    print(f"  {'=' * 40}")
    print(f"  Timestamp:    {summary['cron_timestamp']}")
    print(f"  Success:      {'✅' if summary['success'] else '❌'}")
    print(f"  Line rate:    {summary.get('line_rate', 'N/A')}%")
    print(f"  Gate passed:  {'✅' if summary['gate_passed'] else '❌' if summary['gate_passed'] is False else 'N/A'}")
    print(f"  .gcda files:  {summary['gcda_files_found']}")
    if summary['p0_alert']:
        print(f"  🚨 P0 ALERT: No .gcda data produced")
    print()

    if summary.get("warnings"):
        for w in summary["warnings"]:
            print(f"  ⚠️  {w}")
        print()

    # Exit code: 0 = success, 1 = verification issue, 2 = P0 alert
    if summary["p0_alert"]:
        sys.exit(2)
    if not summary.get("gate_passed", True) and summary.get("gate_passed") is not None:
        sys.exit(1)
    if not summary["success"]:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
