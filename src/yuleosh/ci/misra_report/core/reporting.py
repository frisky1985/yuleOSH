#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985

"""
MISRA Report — JSON / Markdown Report Generation and Saving.

Split from core.py (Phase 2.2 → Phase 3).
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.misra_report")

from yuleosh.ci.misra_report.core.config import (
    _MISRA_SCHEMA_VERSION,
    _SELFTEST_SCHEMA_VERSION,
    _DEFAULT_REPORT_DIR,
    get_tool_version,
    get_ruleset_version,
    get_ci_environ,
    _extract_excluded_rules,
    _extract_excluded_files,
    load_rule_definitions,
)
from yuleosh.ci.misra_report.core.analysis import (
    compute_summary_stats,
    _compute_prev_build_diff,
    _load_prev_report,
    _compute_category_breakdown,
)


def generate_json_report(
    violations: list[dict],
    groups: dict,
    rule_defs: dict | None = None,
    output_dir: str | Path = _DEFAULT_REPORT_DIR,
    deviation_list: Optional[list] = None,
    excluded_rules: Optional[list] = None,
    excluded_files: Optional[list] = None,
) -> dict:
    """Generate the full MISRA report as a JSON-serializable dict."""
    rule_defs = rule_defs or load_rule_definitions()
    excluded_rules = excluded_rules or _extract_excluded_rules()
    excluded_files = excluded_files or _extract_excluded_files()

    stats = compute_summary_stats(violations, groups, rule_defs)
    category_bd = _compute_category_breakdown(violations)

    # Diff against previous report
    prev = _load_prev_report(output_dir)
    diff_info = _compute_prev_build_diff(stats, prev) if prev else {}

    report = {
        "schema_version": _MISRA_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(),
        "tool_version": get_tool_version(),
        "ruleset_version": get_ruleset_version(rule_defs),
        "ci_environ": get_ci_environ(),
        **stats,
        "category_breakdown": category_bd,
        "groups": {rid: _serialize_group(g) for rid, g in groups.items()},
        "deviations": [_deviation_to_dict(d) for d in (deviation_list or [])],
        "excluded_rules": excluded_rules,
        "excluded_files": excluded_files,
    }

    if diff_info:
        report["diff"] = diff_info
    return report


def _serialize_group(group: list[dict] | dict) -> dict:
    """Serialize a group of violations (by rule) to a dict."""
    if isinstance(group, dict):
        # Already a serialized group dict — pass through
        return group
    return {
        "count": len(group),
        "violations": group[:100] if isinstance(group, list) else [],  # cap display
        "total": len(group),
    }


def _format_delta(delta: int) -> str:
    """Format integer delta with + prefix for positive values."""
    if delta > 0:
        return f"+{delta}"
    return str(delta)


def generate_markdown_report(
    report: dict,
    title: str = "MISRA Compliance Report",
) -> str:
    """Generate a human-readable Markdown report from the JSON report dict."""
    lines = [
        f"# {title}",
        "",
        f"**Generated**: {report.get('generated_at', 'N/A')}",
        f"**Tool**: {report.get('tool_version', 'N/A')}",
        f"**Ruleset**: {report.get('ruleset_version', 'N/A')}",
        "",
        "## Summary",
        "",
        f"- **Total Violations**: {report.get('total_violations', 0)}",
        f"- **Unique Rules**: {report.get('unique_rules', 0)}",
        f"- **Affected Files**: {report.get('affected_files', 0)}",
        f"- **Density**: {report.get('density_per_kloc', 0)} violations/KLOC",
        "",
    ]

    # Diff section
    if "diff" in report:
        d = report["diff"]
        delta_str = _format_delta(d.get("delta_total", 0))
        lines.extend([
            "## Trend vs Previous Build",
            "",
            f"- **Previous Total**: {d.get('previous_total', 0)}",
            f"- **Delta**: {delta_str}",
            "",
        ])

    # Severity breakdown
    by_severity = report.get("by_severity", {})
    if by_severity:
        lines.extend(["## By Severity", "", "| Severity | Count |", "|---------|------:|"])
        for sev in ["error", "warning", "style", "performance", "portability"]:
            if sev in by_severity:
                lines.append(f"| {sev} | {by_severity[sev]} |")
        lines.append("")

    # Rule type breakdown
    by_rule_type = report.get("by_rule_type", {})
    if by_rule_type:
        lines.extend(["## By Rule Type", "", "| Type | Count |", "|------|------:|"])
        for rtype in ["required", "advisory", "directive"]:
            if rtype in by_rule_type:
                lines.append(f"| {rtype} | {by_rule_type[rtype]} |")
        lines.append("")

    # Category breakdown
    category_bd = report.get("category_breakdown", {})
    if category_bd:
        lines.extend(["## By Category", "", "| Category | Count |", "|----------|------:|"])
        for cat, cnt in sorted(category_bd.items(), key=lambda x: -x[1]):
            lines.append(f"| {cat} | {cnt} |")
        lines.append("")

    # Group details (top rules)
    groups = report.get("groups", {})
    if groups:
        lines.extend(["## Violations by Rule", ""])
        sorted_groups = sorted(groups.items(), key=lambda x: x[1]["count"], reverse=True)
        for rid, g in sorted_groups[:20]:
            lines.append(f"- **{rid}** ({g['count']} violations)")
            for v in g.get("violations", [])[:5]:
                file = v.get("file", "?")
                line = v.get("line", "?")
                msg = v.get("message", "")[:80]
                lines.append(f"  - `{file}:{line}` — {msg}")
        if len(sorted_groups) > 20:
            lines.append(f"\n... and {len(sorted_groups) - 20} more rules")

    return "\n".join(lines)


def _deviation_to_dict(d) -> dict:
    """Serialize a deviation object to dict."""
    return {
        "rule_id": getattr(d, "rule_id", str(d)),
        "reason": getattr(d, "reason", ""),
        "expires": getattr(d, "expires", None),
    }


def save_report(
    violations_or_report: list | dict,
    groups_or_output_dir: dict | str | Path = None,
    summary_or_filename=None,
    rule_defs_or_formats=None,
    output_dir_or_none: str | Path | None = None,
    deviations: list | None = None,
) -> list[Path] | tuple:
    """Save the MISRA report to disk.

    Supports both new-style (report dict) and legacy (violations list) calling.
    """
    # Detect calling convention: new style (pass dict report + output_dir)
    if isinstance(violations_or_report, dict) and isinstance(groups_or_output_dir, (str, Path)):
        # New-style: save_report(report_dict, output_dir, filename, formats)
        report = violations_or_report
        output_dir = Path(groups_or_output_dir)
        filename = str(summary_or_filename) if summary_or_filename else "misra-report"
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = []

        json_path = output_dir / f"{filename}.json"
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        saved.append(json_path)
        log.info("Saved MISRA JSON report: %s", json_path)

        md_content = generate_markdown_report(report)
        md_path = output_dir / f"{filename}.md"
        md_path.write_text(md_content)
        saved.append(md_path)
        log.info("Saved MISRA Markdown report: %s", md_path)

        return saved

    # Legacy: save_report(violations, groups, summary, rule_defs, output_dir, deviations) -> tuple
    violations = violations_or_report
    groups = groups_or_output_dir or {}
    summary = summary_or_filename or {}
    rule_defs = rule_defs_or_formats or {}
    output_dir = Path(output_dir_or_none) if output_dir_or_none else Path(_DEFAULT_REPORT_DIR)
    deviations = deviations or []

    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate report dict
    report = generate_json_report(
        violations=violations,
        groups=groups,
        rule_defs=rule_defs,
        output_dir=output_dir,
        deviation_list=deviations,
    )

    # Save JSON
    json_path = output_dir / "misra-report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    log.info("Saved MISRA JSON report: %s", json_path)

    # Save Markdown
    md_content = generate_markdown_report(report)
    md_path = output_dir / "misra-report.md"
    md_path.write_text(md_content)
    log.info("Saved MISRA Markdown report: %s", md_path)

    # Save traceability matrix
    from yuleosh.ci.misra_report.traceability import generate_traceability_matrix as _gen_trace
    trace_path = output_dir / "misra-traceability.csv"
    trace_matrix = _gen_trace(violations, rule_defs, deviations)
    with open(trace_path, "w") as f:
        import csv
        if trace_matrix:
            fields = list(trace_matrix[0].keys())
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for row in trace_matrix:
                writer.writerow(row)

    # Save Excel (placeholder - use CSV as fallback)
    excel_path = output_dir / "misra-report.xlsx"
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "MISRA Report"
        ws.append(["Rule ID", "File", "Line", "Severity", "Message", "Status"])
        dev_rule_ids = set()
        for d in deviations:
            if isinstance(d, tuple) and len(d) > 0:
                dev_rule_ids.add(str(d[0]))
            elif isinstance(d, dict):
                dev_rule_ids.add(str(d.get("rule_id", "")))
            else:
                dev_rule_ids.add(str(d))
        for v in violations:
            status = "acknowledged" if v.get("rule_id", "") in dev_rule_ids else ""
            ws.append([
                v.get("rule_id", ""), v.get("file", ""), v.get("line", ""),
                v.get("severity", ""), v.get("message", ""),
                status,
            ])
        wb.save(str(excel_path))
    except ImportError:
        # Fallback: save CSV
        excel_path = output_dir / "misra-report.csv"
        with open(excel_path, "w") as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(["Rule ID", "File", "Line", "Severity", "Message"])
            for v in violations:
                writer.writerow([
                    v.get("rule_id", ""), v.get("file", ""), v.get("line", ""),
                    v.get("severity", ""), v.get("message", ""),
                ])

    return json_path, md_path, trace_path, excel_path


def save_merged_report(
    misra_report: dict,
    selftest_review: dict | None = None,
    output_path: str | Path = "merged-report.json",
) -> Path:
    """Save a merged report combining MISRA analysis with self-test review."""
    merged = {
        "_schema": _SELFTEST_SCHEMA_VERSION,
        "misra": misra_report,
        "selftest": selftest_review or {},
        "merged_at": datetime.now().isoformat(),
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    log.info("Saved merged report: %s", output_path)
    return output_path


def print_summary(summary: dict) -> None:
    """Print a human-readable summary to stdout."""
    lines = [
        "=" * 60,
        "MISRA Report Summary",
        "=" * 60,
        f"Total violations:  {summary.get('total_violations', 0)}",
        f"Unique rules:     {summary.get('unique_rules', 0)}",
        f"Affected files:   {summary.get('affected_files', 0)}",
    ]

    by_severity = summary.get("by_severity", {})
    for sev in ["error", "warning", "style"]:
        if sev in by_severity:
            lines.append(f"  {sev:12s}: {by_severity[sev]}")

    lines.extend([
        "-" * 60,
        f"Density: {summary.get('density_per_kloc', 0):.1f} violations/KLOC",
        "=" * 60,
    ])
    print("\n".join(lines))
