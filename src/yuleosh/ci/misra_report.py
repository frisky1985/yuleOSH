#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
MISRA C:2023 Report Formatter

Parses cppcheck MISRA output (text format) and produces structured
JSON and Markdown reports grouped by rule number and severity.

Usage:
    python3 ci/misra_report.py --input misra_output.txt --output-dir reports/
    python3 ci/misra_report.py --format json    # parse from stdin or file
    python3 ci/misra_report.py --format markdown

Integration:
    Called by ci/stages.py -> run_misra_check()
    Rule definitions loaded from misra-rules.yaml
"""

import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("ci.misra_report")

# Default paths
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "misra-rules.yaml"
_DEFAULT_OUTPUT_DIR = Path(".yuleosh") / "reports"

# Regex patterns for cppcheck MISRA output
# Typical cppcheck MISRA line (--addon=misra):
#   src/main.c:42:5: style: misra-c2023-10.1: [misra-c2012-10.1] Operands shall not be of inappropriate type
#   src/main.c:42:5: style: (information) MISRA rule 17.7
_PATTERN_CPPCHECK = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<severity>error|warning|style|performance|portability|information):\s*"
    r"(?P<message>.+)$", re.MULTILINE
)

# Pattern for MISRA addon rule extraction
_PATTERN_MISRA_RULE = re.compile(
    r"misra-c(?P<year>\d{4})-(?P<rule>\d+\.\d+)", re.IGNORECASE
)

# Fallback: cppcheck text-format addon
_PATTERN_TEXT_RULE = re.compile(
    r"misra rule[:\s]+(?P<rule>\d+\.\d+)", re.IGNORECASE
)


def load_rule_definitions(rules_path: Optional[Path] = None) -> dict:
    """Load MISRA rule definitions from YAML file.

    Returns a dict keyed by rule ID (e.g. 'misra-c2023-17.7').
    Returns empty dict if the YAML file is missing or fails to parse.
    """
    path = rules_path or _DEFAULT_RULES_PATH
    if not path.exists():
        log.warning("MISRA rules file not found: %s", path)
        return {}

    if yaml is None:
        log.warning("PyYAML not installed — cannot load rule definitions")
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "meta" not in data:
            log.warning("Invalid MISRA rules file format: %s", path)
            return {}
        # Filter out the 'meta' key — only return actual rule entries
        return {k: v for k, v in data.items() if k != "meta"}
    except (yaml.YAMLError, OSError, Exception) as e:
        log.warning("Failed to load MISRA rules from %s: %s", path, e)
        return {}


def parse_cppcheck_output(text: str) -> list[dict]:
    """Parse cppcheck MISRA output text into structured violation records.

    Returns a list of dicts with keys:
      - file, line, col, severity, message, rule_id (str or None)
    """
    violations = []
    for match in _PATTERN_CPPCHECK.finditer(text):
        violation = match.groupdict()
        message = violation["message"]

        # Try to extract MISRA rule ID from message
        rule_match = _PATTERN_MISRA_RULE.search(message)
        if rule_match:
            rule_id = f"misra-c{rule_match.group('year')}-{rule_match.group('rule')}"
        else:
            text_match = _PATTERN_TEXT_RULE.search(message)
            if text_match:
                # Infer year from context (current year = 2023)
                rule_id = f"misra-c2023-{text_match.group('rule')}"
            else:
                rule_id = None

        violation["rule_id"] = rule_id
        violation["line"] = int(violation["line"])
        violation["col"] = int(violation["col"])
        violations.append(violation)

    return violations


def group_by_rule(violations: list[dict]) -> dict:
    """Group violations by rule ID and severity.

    Returns {rule_id: {title, severity, category, description, violations: [...]}}
    """
    groups: dict = {}
    for v in violations:
        rid = v.get("rule_id", "unknown")
        if rid not in groups:
            groups[rid] = {
                "rule_id": rid,
                "violations": [],
                "count": 0,
                "files": set(),
            }
        groups[rid]["violations"].append(v)
        groups[rid]["count"] += 1
        groups[rid]["files"].add(v.get("file", ""))

    # Convert sets to lists for JSON serialization
    for g in groups.values():
        g["files"] = sorted(g["files"])

    return groups


def enrich_with_definitions(
    groups: dict,
    rule_defs: dict,
) -> dict:
    """Merge rule definitions into the grouped violations.

    For each rule_id in groups, if a definition exists in rule_defs,
    add title, severity, category, and description fields.
    """
    for rule_id, group in groups.items():
        if rule_id in rule_defs:
            defn = rule_defs[rule_id]
            group["title"] = defn.get("title", "")
            group["severity_category"] = defn.get("severity", "")
            group["category"] = defn.get("category", "")
            group["description"] = defn.get("description", "")
        else:
            group["title"] = ""
            group["severity_category"] = "unknown"
            group["category"] = "unrecognized"
            group["description"] = ""
    return groups


def compute_summary_stats(violations: list[dict], groups: dict) -> dict:
    """Compute summary statistics from violations and groups.

    Returns dict with:
      - total_violations: int
      - total_rules_violated: int
      - severity_counts: dict[severity] -> count
      - unique_files: list[str]
      - per_file_counts: dict[file] -> count
    """
    severity_counts: dict[str, int] = defaultdict(int)
    per_file_counts: dict[str, int] = defaultdict(int)
    unique_files: set[str] = set()

    for v in violations:
        sev = v.get("severity", "unknown")
        severity_counts[sev] += 1
        fname = v.get("file", "")
        if fname:
            unique_files.add(fname)
            per_file_counts[fname] += 1

    return {
        "total_violations": len(violations),
        "total_rules_violated": len(groups),
        "severity_counts": dict(severity_counts),
        "unique_files": sorted(unique_files),
        "per_file_counts": dict(per_file_counts),
    }


def generate_json_report(violations: list[dict], groups: dict, summary: dict) -> str:
    """Generate a JSON formatted report."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "tool": "cppcheck --addon=misra",
        "standard": "MISRA C:2023",
        "summary": summary,
        "violations_raw": violations,
        "groups": {k: _serialize_group(v) for k, v in groups.items()},
    }
    return json.dumps(report, indent=2, ensure_ascii=False, default=str)


def _serialize_group(group: dict) -> dict:
    """Serialize a group dict, converting any non-serializable types."""
    result = {}
    for k, v in group.items():
        if isinstance(v, set):
            result[k] = sorted(v)
        else:
            result[k] = v
    return result


def generate_markdown_report(violations: list[dict], groups: dict, summary: dict, rule_defs: dict) -> str:
    """Generate a Markdown formatted MISRA report."""
    lines = [
        "# MISRA C:2023 Compliance Report",
        "",
        f"> Generated: {datetime.now().isoformat()}",
        f"> Tool: cppcheck --addon=misra",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|:-------|------:|",
        f"| Total Violations | {summary['total_violations']} |",
        f"| Rules Violated | {summary['total_rules_violated']} |",
        f"| Files Affected | {len(summary['unique_files'])} |",
        f"",
        "### Severity Breakdown",
        f"",
    ]

    for sev in ["error", "warning", "style", "performance", "portability", "information"]:
        count = summary["severity_counts"].get(sev, 0)
        if count > 0:
            icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                    "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
            lines.append(f"| {icon} {sev.capitalize()} | {count} |")

    lines.append("")
    lines.append("### Files with Violations")
    lines.append("")
    for fname, count in sorted(summary["per_file_counts"].items()):
        lines.append(f"- `{fname}`: {count} violation(s)")
    lines.append("")

    # Violations by Rule Group
    sorted_rules = sorted(groups.items(), key=lambda x: -x[1]["count"])
    if sorted_rules:
        lines.append("## Violations by Rule")
        lines.append("")

        for rule_id, group in sorted_rules:
            title = group.get("title", rule_defs.get(rule_id, {}).get("title", ""))
            sev = group.get("severity_category", rule_defs.get(rule_id, {}).get("severity", "unknown"))
            sev_icon = {"required": "🔴", "advisory": "🟡", "unknown": "⚪"}.get(sev, "⚪")
            lines.append(f"### {rule_id}: {title}")
            lines.append(f"")
            lines.append(f"- **Severity**: {sev_icon} {sev}")
            lines.append(f"- **Count**: {group['count']}")
            lines.append(f"- **Files**: {', '.join(group['files'][:5])}")
            if len(group['files']) > 5:
                lines.append(f"  *...and {len(group['files']) - 5} more file(s)*")
            lines.append("")
            lines.append("| File | Line | Column | Severity | Message |")
            lines.append("|:-----|:----|:------|:---------|:--------|")

            for v in group["violations"][:20]:
                msg = v["message"][:80]
                lines.append(f"| `{v['file']}` | {v['line']} | {v['col']} | {v['severity']} | {msg} |")

            if len(group["violations"]) > 20:
                lines.append(f"| ... | ... | ... | ... | *{len(group['violations']) - 20} more* |")
            lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    critical_rules = [r for r, g in sorted_rules if g.get("severity_category") == "required" and g["count"] > 0]
    if critical_rules:
        lines.append("### Required Rules to Fix (Priority)")
        lines.append("")
        for rule_id in critical_rules[:10]:
            defn = rule_defs.get(rule_id, {})
            title = defn.get("title", groups[rule_id].get("title", ""))
            desc = defn.get("description", "")
            lines.append(f"- **{rule_id}**: {title}")
            if desc:
                lines.append(f"  - {desc}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by yuleOSH MISRA Report Formatter*")
    return "\n".join(lines)


def save_report(
    violations: list[dict],
    groups: dict,
    summary: dict,
    rule_defs: dict,
    output_dir: str | Path,
) -> tuple[Path, Path, Path]:
    """Save JSON, Markdown, and traceability matrix reports to disk.

    Returns tuple of (json_path, md_path, trace_path).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = out_dir / "misra-report.json"
    json_content = generate_json_report(violations, groups, summary)
    json_path.write_text(json_content, encoding="utf-8")

    # Markdown
    md_path = out_dir / "misra-report.md"
    md_content = generate_markdown_report(violations, groups, summary, rule_defs)
    md_path.write_text(md_content, encoding="utf-8")

    # Traceability matrix (JSON)
    trace_path = out_dir / "misra-traceability.json"
    trace_data = generate_traceability_matrix(violations, rule_defs)
    trace_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "total_entries": len(trace_data),
                "traceability": trace_data,
            },
            indent=2, ensure_ascii=False, default=str,
        ),
        encoding="utf-8",
    )

    log.info("MISRA report saved: %s, %s, %s", json_path, md_path, trace_path)
    return json_path, md_path, trace_path


def print_summary(summary: dict) -> None:
    """Print a human-readable summary to stdout."""
    print(f"\n  📊 MISRA C:2023 Summary:")
    print(f"     Total violations: {summary['total_violations']}")
    print(f"     Rules violated:   {summary['total_rules_violated']}")
    print(f"     Files affected:   {len(summary['unique_files'])}")
    for sev in ["error", "warning", "style", "performance", "portability", "information"]:
        count = summary["severity_counts"].get(sev, 0)
        if count > 0:
            icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                    "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
            print(f"       {icon} {sev}: {count}")
    print()


def generate_traceability_matrix(
    violations: list[dict],
    rule_defs: dict,
) -> list[dict]:
    """Build traceability: Rule ID → File:Line → Spec Ref → Fix Status.

    Returns a list of dicts, one per violation, with:
      - rule_id: str
      - file: str
      - line: int
      - col: int
      - severity: str
      - message: str
      - spec_ref: str (from rule_defs, or "" if unknown)
      - check_method: str (from rule_defs, or "" if unknown)
      - auto_checkable: bool (from rule_defs, default True)
      - fix_status: str ("unresolved" | "deviation" | "suppressed")
    """
    traceability = []
    for v in violations:
        rid = v.get("rule_id", "unknown")
        defn = rule_defs.get(rid, {})
        traceability.append({
            "rule_id": rid,
            "file": v.get("file", ""),
            "line": v.get("line", 0),
            "col": v.get("col", 0),
            "severity": v.get("severity", ""),
            "message": v.get("message", ""),
            "spec_ref": defn.get("spec_ref", ""),
            "check_method": defn.get("check_method", ""),
            "auto_checkable": bool(defn.get("auto_checkable", True)),
            "fix_status": "unresolved",
        })
    return traceability


def generate_fix_tasks(
    project_dir: str,
    violations: list[dict],
    rule_defs: dict,
) -> list[str]:
    """Generate fix task .md files for each unresolved violation.

    Creates one .md file per violated rule under
    ``.yuleosh/fix-tasks/misra-{rule_id}.md``.

    Returns list of file paths created.
    """
    from datetime import datetime

    fix_dir = Path(project_dir) / ".yuleosh" / "fix-tasks"
    fix_dir.mkdir(parents=True, exist_ok=True)

    # Group violations by rule_id
    rule_groups: dict[str, list[dict]] = {}
    for v in violations:
        rid = v.get("rule_id", "unknown")
        rule_groups.setdefault(rid, []).append(v)

    created_files: list[str] = []
    for rule_id, vs in sorted(rule_groups.items()):
        defn = rule_defs.get(rule_id, {})
        title = defn.get("title", rule_id)
        spec_ref = defn.get("spec_ref", "")
        severity = defn.get("severity", "unknown")

        lines = [
            f"# MISRA Fix Task: {rule_id}",
            "",
            f"> Generated: {datetime.now().isoformat()}",
            f"> Severity: {severity}",
            f"> Spec Ref: {spec_ref}",
            "",
            f"## Rule: {title}",
            "",
            f"{defn.get('description', '')}",
            "",
            "## Violations",
            "",
            "| # | File | Line | Col | Message |",
            "|--:|:-----|:----|:----|:--------|",
        ]
        for idx, v in enumerate(vs, 1):
            msg = v.get("message", "")[:80]
            lines.append(f"| {idx} | `{v.get('file', '')}` | {v.get('line', 0)} | {v.get('col', 0)} | {msg} |")

        lines.extend([
            "",
            "## Fix Checklist",
            "",
            "- [ ] Understand the violation context",
            "- [ ] Apply fix to source code",
            "- [ ] Re-run MISRA check to verify fix",
            "- [ ] Update traceability matrix",
            "- [ ] Document deviation if fix is not feasible",
            "",
            "---",
            "*Generated by yuleOSH MISRA fix-task generator*",
        ])

        file_path = fix_dir / f"misra-{rule_id}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")
        created_files.append(str(file_path))
        log.info("MISRA fix task created: %s", file_path)

    return created_files


# ------------------------------------------------------------------
# CLI Entry Point
# ------------------------------------------------------------------


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
        choices=["json", "markdown", "summary"],
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
    summary = compute_summary_stats(violations, groups)

    # Output
    if args.format == "json":
        print(generate_json_report(violations, groups, summary))
    elif args.format == "markdown":
        print(generate_markdown_report(violations, groups, summary, rule_defs))
    else:
        # Save reports and print summary
        json_path, md_path, trace_path = save_report(
            violations, groups, summary, rule_defs, args.output_dir
        )
        if not args.quiet:
            print_summary(summary)
            print(f"  Reports saved:")
            print(f"    JSON: {json_path}")
            print(f"    MD:   {md_path}")
            print(f"    Trace: {trace_path}")


if __name__ == "__main__":
    main()
