#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI MISRA Report — Cli.

Part of the misra_report/ package split from misra_report.py (Phase 2.2).
"""

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("ci.misra_report")

from yuleosh.ci.misra_report.core import parse_cppcheck_output, load_rule_definitions, compute_summary_stats


# ------------------------------------------------------------------
# Report schema version (R3-P0-6)
# ------------------------------------------------------------------

_MISRA_SCHEMA_VERSION = "misra-report-v2"
_SELFTEST_SCHEMA_VERSION = "selftest-review-v2"


# Default report directory for loading previous builds



# ------------------------------------------------------------------
# Multi-tool result types (G-15)
# ------------------------------------------------------------------





# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------



_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "misra-rules.yaml"
_DEFAULT_OUTPUT_DIR = Path(".yuleosh") / "reports"
_DEFAULT_REPORT_DIR = _DEFAULT_OUTPUT_DIR
_DEFAULT_CI_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".yuleosh" / "ci-config.yaml"

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MISRA C:2023 Report Formatter — parse cppcheck MISRA output",
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to cppcheck MISRA output file (reads from stdin if omitted)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=str(_DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--rules", "-r",
        default=str(_DEFAULT_RULES_PATH),
        help=f"Path to misra-rules.yaml (default: {_DEFAULT_RULES_PATH})",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "markdown", "summary", "excel"],
        default="summary",
        help="Output format (default: summary to stdout)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress summary output",
    )

    args = parser.parse_args()

    # Read input
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    if not text.strip():
        print("No MISRA output provided — nothing to report.")
        return

    # Load rule definitions
    rule_defs = load_rule_definitions(Path(args.rules))

    # Parse
    violations = parse_cppcheck_output(text)
    if not violations:
        print("No MISRA violations found in input.")
        return

    # Group and enrich
    groups = group_by_rule(violations)
    groups = enrich_with_definitions(groups, rule_defs)
    summary = compute_summary_stats(violations, groups, rule_defs)

    # Output
    if args.format == "json":
        print(generate_json_report(violations, groups, summary, rule_defs))
    elif args.format == "markdown":
        print(generate_markdown_report(violations, groups, summary, rule_defs))
    elif args.format == "excel":
        # Generate Excel only and save to output_dir
        from yuleosh.evidence.excel_writer import ExcelReportWriter
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        writer = ExcelReportWriter(out_dir)
        excel_path = writer.write_misra_report(
            violations=violations,
            groups=groups,
            summary=summary,
            rule_defs=rule_defs,
            deviations=None,
            output_path=out_dir / "misra-report.xlsx",
        )
        if not args.quiet:
            print_summary(summary)
            print(f"  Excel: {excel_path}")
    else:
        # Save reports and print summary
        json_path, md_path, trace_path, excel_path = save_report(
            violations, groups, summary, rule_defs, args.output_dir
        )
        if not args.quiet:
            print_summary(summary)
            print(f"  Reports saved:")
            print(f"    JSON: {json_path}")
            print(f"    MD:   {md_path}")
            print(f"    Trace: {trace_path}")
            print(f"    Excel: {excel_path}")


if __name__ == "__main__":
    main()


