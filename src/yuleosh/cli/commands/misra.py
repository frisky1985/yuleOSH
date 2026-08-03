# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH CLI — MISRA C:2023 compliance command group.

A5 (v3.8.0): extracted from cli/main.py (monolith split).  Behavior is
identical to the v3.7.0 inline implementation; cli/main.py re-exports
these functions for backward-compatible imports.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# OSH_HOME / sys.path bootstrap — mirrored from cli/main.py so command
# modules run standalone under pytest (SHALL-A5.5: no import of cli.main).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _osh_home() -> str:
    """Resolve OSH_HOME, honoring cli.main's live value (A5 compat).

    cli.main re-exports these commands; tests monkeypatch
    ``yuleosh.cli.main.OSH_HOME``.  A lazy lookup keeps the single source
    of truth in cli.main without a top-level circular import (SHALL-A5.5).
    """
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def cmd_misra_deviate(args):
    """Handle ``yuleosh misra deviate`` subcommands.

    Reads/Writes deviations from/to ``.yuleosh/ci-config.yaml``.
    """
    from yuleosh.ci.config import (
        load_ci_config, update_deviation_status, _deviations_to_yaml_dicts,
    )

    project_dir = _osh_home()
    cfg = load_ci_config(project_dir)
    deviations = cfg.misra.deviations if cfg else []

    sub = args.deviate_sub
    as_json = getattr(args, "json", False)

    if sub == "list":
        if not deviations:
            print("No deviation records found.")
            return
        if as_json:
            output = []
            for d in deviations:
                output.append({
                    "rule_id": d.rule_id,
                    "file_pattern": d.file_pattern,
                    "reason": d.reason,
                    "approved_by": d.approved_by,
                    "expires": d.expires,
                    "status": d.status,
                })
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return
        print(f"\n{'#':<3} {'Rule ID':<28} {'File Pattern':<30} {'Status':<12} {'Approved By':<16} {'Expires':<14}")
        print("-" * 105)
        for idx, d in enumerate(deviations, 1):
            print(f"{idx:<3} {d.rule_id:<28} {d.file_pattern:<30} {d.status:<12} {d.approved_by:<16} {d.expires:<14}")
        print()

    elif sub == "approve":
        dev_id = args.dev_id
        rule, file_pat = _parse_dev_id(dev_id)
        if not rule and not file_pat:
            print(f"Error: invalid dev_id format '{dev_id}' — expected 'rule_id:file_pattern'", file=sys.stderr)
            sys.exit(1)
        # Find the deviation by rule_id only (file_pattern may have glob chars)
        matched = [d for d in deviations if d.rule_id == rule]
        if not matched:
            print(f"Error: deviation for rule '{rule}' not found", file=sys.stderr)
            sys.exit(1)
        # Update via YAML write
        target_file = file_pat or matched[0].file_pattern
        ok = update_deviation_status(project_dir, rule, target_file, "approved")
        if ok:
            print(f"✅ Deviation {rule}:{target_file} → APPROVED")
        else:
            print(f"Error: failed to update deviation '{dev_id}'", file=sys.stderr)
            sys.exit(1)

    elif sub == "reject":
        dev_id = args.dev_id
        rule, file_pat = _parse_dev_id(dev_id)
        if not rule and not file_pat:
            print(f"Error: invalid dev_id format '{dev_id}' — expected 'rule_id:file_pattern'", file=sys.stderr)
            sys.exit(1)
        matched = [d for d in deviations if d.rule_id == rule]
        if not matched:
            print(f"Error: deviation for rule '{rule}' not found", file=sys.stderr)
            sys.exit(1)
        target_file = file_pat or matched[0].file_pattern
        ok = update_deviation_status(project_dir, rule, target_file, "rejected")
        if ok:
            print(f"✅ Deviation {rule}:{target_file} → REJECTED")
        else:
            print(f"Error: failed to update deviation '{dev_id}'", file=sys.stderr)
            sys.exit(1)

    elif sub == "create":
        _cli_add_deviation(project_dir, args.rule, args.file,
                           reason=args.reason,
                           approved_by=args.approved_by,
                           expires=args.expires,
                           status=args.status)

    elif sub == "add":
        _interactive_add_deviation(project_dir)

    else:
        print(f"Unknown deviate subcommand: {sub}", file=sys.stderr)
        sys.exit(1)


def _parse_dev_id(dev_id: str) -> tuple[str, str]:
    """Parse a dev_id string 'rule_id:file_pattern' into its components."""
    if ":" in dev_id:
        parts = dev_id.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    # Try matching by rule_id alone
    return dev_id.strip(), ""


def _cli_add_deviation(project_dir: str, rule: str, file_pat: str,
                        reason: str = "", approved_by: str = "",
                        expires: str = "", status: str = "open") -> None:
    """Non-interactive CLI to add a new deviation to ci-config.yaml."""
    import yaml
    from pathlib import Path

    config_path = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    new_entry = {
        "rule": rule,
        "file": file_pat,
        "reason": reason or "(not specified)",
        "approved_by": approved_by or "(not specified)",
        "expires": expires or "2099-12-31",
        "status": status,
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error: failed to parse config: {e}", file=sys.stderr)
        sys.exit(1)

    misra_block = raw.setdefault("misra", {})
    deviations = misra_block.setdefault("deviations", [])
    deviations.append(new_entry)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"✅ Deviation created: {rule}:{file_pat} (status: {status})")
    except OSError as e:
        print(f"Error: failed to write config: {e}", file=sys.stderr)
        sys.exit(1)


def _interactive_add_deviation(project_dir: str) -> None:
    """Interactive prompt to add a new deviation to ci-config.yaml."""
    import yaml
    from pathlib import Path

    config_path = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    print("\n📝 Add a new MISRA deviation:")
    try:
        rule = input("  Rule ID (e.g. misra-c2023-17.7): ").strip()
        file_pat = input("  File pattern (e.g. src/legacy/*.c): ").strip()
        reason = input("  Reason for deviation: ").strip()
        approved_by = input("  Approved by: ").strip()
        expires = input("  Expires (ISO date, e.g. 2026-09-30): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    if not rule or not file_pat:
        print("Error: rule_id and file_pattern are required.", file=sys.stderr)
        sys.exit(1)

    new_entry = {
        "rule": rule,
        "file": file_pat,
        "reason": reason or "(not specified)",
        "approved_by": approved_by or "(not specified)",
        "expires": expires or "2099-12-31",
        "status": "pending",
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"Error: failed to parse config: {e}", file=sys.stderr)
        sys.exit(1)

    # Ensure deviations list exists
    misra_block = raw.setdefault("misra", {})
    deviations = misra_block.setdefault("deviations", [])
    deviations.append(new_entry)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"✅ Deviation added: {rule}:{file_pat} (status: pending)")
    except OSError as e:
        print(f"Error: failed to write config: {e}", file=sys.stderr)
        sys.exit(1)


# ── MISRA Trend Command ────────────────────────────────────────────────


def cmd_misra_trend(args):
    """Handle ``yuleosh misra trend`` — display or export trend data."""
    from yuleosh.ci.misra_trend import show_trend

    project_dir = _osh_home()
    result = show_trend(
        project_dir,
        lines=args.lines,
        days=args.days,
        as_json=args.json,
    )
    print(result)


# ── MISRA Profile Commands (G-17) ────────────────────────────────────────


def cmd_misra_profile_list():
    """List available MISRA profiles — both from ci-config.yaml and misra-rules.yaml."""
    from yuleosh.ci.config import load_ci_config
    import yaml

    cfg = load_ci_config(_osh_home())
    profiles = cfg.misra.profiles
    active = cfg.misra.active_profile

    # Count rules per profile from misra-rules.yaml
    misra_rules_path = os.path.join(_osh_home(), "misra-rules.yaml")
    profile_counts: dict[str, int] = {"safety": 0, "performance": 0, "testing": 0}
    if os.path.exists(misra_rules_path):
        try:
            with open(misra_rules_path, encoding="utf-8") as f:
                rules_data = yaml.safe_load(f) or {}
            for rule_id, rule in rules_data.items():
                if rule_id == "meta":
                    continue
                p = rule.get("profile", "safety")
                if p in profile_counts:
                    profile_counts[p] += 1
                else:
                    profile_counts[p] = 1
        except (yaml.YAMLError, OSError):
            pass

    print(f"\n  📋 MISRA Profiles")
    print(f"  {'=' * 60}")
    
    # Show profile counts from misra-rules.yaml
    print(f"  Rules by profile (from misra-rules.yaml):")
    for prof_name in ["safety", "performance", "testing"]:
        count = profile_counts.get(prof_name, 0)
        marker = " 👉 ACTIVE" if prof_name == active else ""
        print(f"    {prof_name:15s}  {count:4d} rules{marker}")

    # Show ci-config.yaml profile overrides if any
    if profiles:
        print()
        print(f"  Profile overrides (from .yuleosh/ci-config.yaml):")
        for prof_name, prof in sorted(profiles.items()):
            marker = "👉" if prof_name == active else "  "
            ovr_count = len(prof.rule_overrides)
            dev_count = len(prof.deviations)
            print(f"  {marker} {prof_name:15s}  {prof.name}")
            if ovr_count > 0:
                print(f"        Rule overrides: {ovr_count}")
            if dev_count > 0:
                print(f"        Deviations:     {dev_count}")
    print()


def cmd_misra_profile_set(name: str):
    """Switch active MISRA profile."""
    from yuleosh.ci.config import load_ci_config

    cfg = load_ci_config(_osh_home())
    profiles = cfg.misra.profiles

    if not profiles:
        print("No MISRA profiles configured.")
        return

    if name not in profiles:
        print(f"Profile '{name}' not found. Available: {', '.join(profiles.keys())}")
        return

    # Update ci-config.yaml
    import yaml

    config_path = Path(_osh_home()) / ".yuleosh" / "ci-config.yaml"
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        print("Failed to parse config YAML.")
        return

    misra_raw = raw.setdefault("misra", {})
    misra_raw["active_profile"] = name

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"✅ Switched to profile: {name} ({profiles[name].name})")


# ── MISRA Report Command ───────────────────────────────────────────────


def cmd_misra_report(args):
    """Handle ``yuleosh misra report`` — read latest report and output."""
    report_dir = Path(_osh_home()) / ".yuleosh" / "reports"

    # Determine format
    output_format = getattr(args, "format", "summary")

    json_path = report_dir / "misra-report.json"
    md_path = report_dir / "misra-report.md"

    if not json_path.exists():
        print(f"No MISRA report found. Run CI first: yuleosh ci run 1", file=sys.stderr)
        sys.exit(1)

    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading report: {e}", file=sys.stderr)
        sys.exit(1)

    if output_format == "html":
        _render_misra_report_html(report)
    elif output_format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    elif output_format == "markdown":
        if md_path.exists():
            print(md_path.read_text(encoding="utf-8"))
        else:
            print("Markdown report not available.", file=sys.stderr)
            sys.exit(1)
    else:
        # summary (default)
        _print_misra_report_summary(report)


def _print_misra_report_summary(report: dict) -> None:
    """Print a human-readable summary of the MISRA report."""
    summary = report.get("summary", {})
    generated = report.get("generated_at", "")[:19]

    print(f"\n  📊 MISRA C:2023 Compliance Report")
    print(f"  {'─' * 50}")
    print(f"  Generated: {generated}")
    print(f"  Tool:      {report.get('tool', 'cppcheck')}")
    print()
    print(f"  Total violations:   {summary.get('total_violations', 0)}")
    print(f"  Rules violated:    {summary.get('total_rules_violated', 0)}")
    print(f"  Files affected:    {len(summary.get('unique_files', []))}")
    print()

    sev_counts = summary.get("severity_counts", {})
    if sev_counts:
        print(f"  Severity breakdown:")
        for sev in ["error", "warning", "style", "performance", "portability", "information"]:
            count = sev_counts.get(sev, 0)
            if count:
                icon = {"error": "❌", "warning": "⚠️", "style": "🎨", "performance": "⚡",
                        "portability": "🔗", "information": "ℹ️"}.get(sev, "•")
                print(f"    {icon} {sev}: {count}")

    print()
    per_file = summary.get("per_file_counts", {})
    if per_file:
        print(f"  Files with violations:")
        for fname, count in sorted(per_file.items(), key=lambda x: -x[1])[:10]:
            print(f"    • {fname}: {count}")
        if len(per_file) > 10:
            print(f"    ... and {len(per_file) - 10} more file(s)")
    print()

    # Groups (top rules)
    groups = report.get("groups", {})
    if groups:
        print(f"  Top violated rules:")
        sorted_groups = sorted(groups.items(), key=lambda x: -x[1].get("count", 0))[:5]
        for rule_id, g in sorted_groups:
            title = g.get("title", "")
            sev = g.get("severity_category", "unknown")
            sev_icon = {"required": "🔴", "advisory": "🟡", "unknown": "⚪"}.get(sev, "⚪")
            print(f"    {sev_icon} {rule_id}: {g.get('count', 0)} — {title}")
    print()

    summary_path = Path(_osh_home()) / ".yuleosh" / "reports" / "misra-report.json"
    print(f"  Full report: {summary_path}")
    print()


def _render_misra_report_html(report: dict) -> None:
    """Render MISRA report as a simple HTML page to stdout."""
    summary = report.get("summary", {})
    generated = report.get("generated_at", "")[:19]
    total_v = summary.get("total_violations", 0)
    rules_v = summary.get("total_rules_violated", 0)
    files_n = len(summary.get("unique_files", []))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MISRA C:2023 — Compliance Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #333; }}
  h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 0.5rem; }}
  h2 {{ color: #16213e; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  .summary-card {{ background: #f8f9fa; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; display: flex; gap: 2rem; }}
  .stat {{ text-align: center; }}
  .stat-value {{ font-size: 2rem; font-weight: 700; color: #e94560; }}
  .stat-label {{ font-size: 0.85rem; color: #666; }}
  .severity-required {{ color: #d32f2f; }}
  .severity-advisory {{ color: #f57c00; }}
  footer {{ margin-top: 3rem; font-size: 0.85rem; color: #999; border-top: 1px solid #eee; padding-top: 1rem; }}
</style>
</head>
<body>
<h1>🔍 MISRA C:2023 Compliance Report</h1>
<p>Generated: {generated} | Tool: {report.get('tool', 'cppcheck')}</p>
<div class="summary-card">
  <div class="stat"><div class="stat-value">{total_v}</div><div class="stat-label">Total Violations</div></div>
  <div class="stat"><div class="stat-value">{rules_v}</div><div class="stat-label">Rules Violated</div></div>
  <div class="stat"><div class="stat-value">{files_n}</div><div class="stat-label">Files Affected</div></div>
</div>
"""

    # Severity breakdown
    sev_counts = summary.get("severity_counts", {})
    if sev_counts:
        html += "<h2>Severity Breakdown</h2>\n<table>\n<tr><th>Severity</th><th>Count</th></tr>\n"
        for sev in ["error", "warning", "style", "performance", "portability", "information"]:
            count = sev_counts.get(sev, 0)
            if count:
                html += f"<tr><td>{sev}</td><td>{count}</td></tr>\n"
        html += "</table>\n"

    # Per-file
    per_file = summary.get("per_file_counts", {})
    if per_file:
        html += "<h2>Files with Violations</h2>\n<table>\n<tr><th>File</th><th>Violations</th></tr>\n"
        for fname, count in sorted(per_file.items(), key=lambda x: -x[1])[:20]:
            html += f"<tr><td>{fname}</td><td>{count}</td></tr>\n"
        html += "</table>\n"

    # Groups
    groups = report.get("groups", {})
    if groups:
        html += "<h2>Violations by Rule</h2>\n"
        sorted_groups = sorted(groups.items(), key=lambda x: -x[1].get("count", 0))
        for rule_id, g in sorted_groups:
            title = g.get("title", "")
            sev = g.get("severity_category", "unknown")
            count = g.get("count", 0)
            sev_class = f"severity-{sev}" if sev in ("required", "advisory") else ""
            html += f"<h3 class=\"{sev_class}\">{rule_id}: {title}</h3>\n"
            html += f"<p>Count: {count} | Severity: {sev}</p>\n"
            html += "<table>\n<tr><th>File</th><th>Line</th><th>Column</th><th>Message</th></tr>\n"
            for v in g.get("violations", [])[:20]:
                msg = v.get("message", "")[:80]
                html += f"<tr><td>{v.get('file', '')}</td><td>{v.get('line', '')}</td><td>{v.get('col', '')}</td><td>{msg}</td></tr>\n"
            html += "</table>\n"

    html += """
<footer>
  Report generated by yuleOSH MISRA Report Formatter
</footer>
</body>
</html>
"""

    html_path = Path(_osh_home()) / ".yuleosh" / "reports" / "misra-report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML report saved to: {html_path}")


def build_parser(sub):
    """Register the misra command group (A5)."""
    p_misra = sub.add_parser("misra", help="MISRA C:2023 compliance management")
    msub = p_misra.add_subparsers(dest="misra_sub")

    # misra trend
    p_misra_trend = msub.add_parser("trend", help="Show MISRA violation trend")
    p_misra_trend.add_argument("--json", action="store_true", help="Output as JSON")
    p_misra_trend.add_argument("--days", type=int, default=0, help="Filter entries within N days")
    p_misra_trend.add_argument("--lines", "-n", type=int, default=30, help="Number of entries to show")

    # misra report
    p_misra_report = msub.add_parser("report", help="Show MISRA compliance report")
    p_misra_report.add_argument(
        "--format", "-f",
        choices=["summary", "json", "markdown", "html"],
        default="summary",
        help="Output format (default: summary)",
    )

    # misra profile (G-17)
    p_misra_profile = msub.add_parser("profile", help="Manage MISRA profiles")
    mprof = p_misra_profile.add_subparsers(dest="profile_sub")
    mprof.add_parser("list", help="List available profiles")
    p_misra_prof_set = mprof.add_parser("set", help="Switch active profile")
    p_misra_prof_set.add_argument("name", help="Profile name (safety|performance|testing)")

    # misra deviate
    p_misra_deviate = msub.add_parser("deviate", help="Manage deviation records")
    mdev = p_misra_deviate.add_subparsers(dest="deviate_sub")
    p_misra_dev_list = mdev.add_parser("list", help="List all deviation records")
    p_misra_dev_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_misra_dev_approve = mdev.add_parser("approve", help="Approve a deviation")
    p_misra_dev_approve.add_argument("dev_id", help="Deviation ID (rule_id:file_pattern)")
    p_misra_dev_reject = mdev.add_parser("reject", help="Reject a deviation")
    p_misra_dev_reject.add_argument("dev_id", help="Deviation ID (rule_id:file_pattern)")
    p_misra_dev_create = mdev.add_parser("create", help="Create a new deviation (non-interactive)")
    p_misra_dev_create.add_argument("rule", help="Rule ID (e.g. Rule-17.7)")
    p_misra_dev_create.add_argument("file", help="File pattern (e.g. src/legacy/*.c)")
    p_misra_dev_create.add_argument("--reason", default="", help="Deviation reason")
    p_misra_dev_create.add_argument("--approved-by", "--approved_by", dest="approved_by", default="", help="Approver name")
    p_misra_dev_create.add_argument("--expires", default="", help="Expiry date (ISO format)")
    p_misra_dev_create.add_argument("--status", default="pending",
                                    choices=["pending", "approved", "rejected"],
                                    help="Initial status (default: pending)")
    return p_misra
