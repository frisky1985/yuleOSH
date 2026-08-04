#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
yuleOSH — Embedded AI Development Platform CLI

Usage:
    yuleosh init [dir]                       — Initialize project
    yuleosh project init [--template <name>] — Initialize project from template
    yuleosh template list                    — List available templates
    yuleosh template init <project-name>     — Create new project from starter template
    yuleosh spec validate <file>             — Validate OpenSpec spec
    yuleosh spec diff <old> <new>            — Diff two specs
    yuleosh pipeline run [--mock] <spec>     — Run full Agent pipeline
    yuleosh pipeline status [name]           — Show pipeline status
    yuleosh review auto                      — Auto-review changes
    yuleosh review task <name> [kind]        — Review specific task
    yuleosh ci run <layer>                   — Run CI layer (1/2/3)
    yuleosh evidence pack                    — Generate ASPICE compliance pack
    yuleosh audit evidence [-o <dir>]        — Generate CL2 audit evidence bundle
    yuleosh stats [--json]                   — Show project statistics
    yuleosh ui                              — Start dashboard server (:8080)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# OSH_HOME defaults to CWD for pip-installed environments;
# in dev mode, set OSH_HOME explicitly or rely on the project root.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OSH_HOME = os.environ.get(
    "OSH_HOME",
    os.getcwd(),
)

# In dev-mode (source tree), add src/ to sys.path so package imports work.
# For pip-installed mode the package is already on sys.path.
SRC_DIR = Path(SCRIPT_DIR).resolve().parent.parent.parent / "src"  # yuleosh/cli/ -> ../../ -> src/
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ANSI color constants for CLI output
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


# ── A5 (v3.8.0): command groups extracted to cli/commands/*.py ─────────
# Re-exported here so existing imports (tests, plugins) keep working
# (SHALL-A5.5: no circular import — the command modules never import
# cli.main; they bootstrap their own sys.path mirror).
from yuleosh.cli.commands.traceability import (  # noqa: E402
    cmd_traceability_report,
    cmd_traceability_export,
    cmd_traceability_matrix,
)
from yuleosh.cli.commands.misra import (  # noqa: E402
    cmd_misra_deviate,
    cmd_misra_trend,
    cmd_misra_profile_list,
    cmd_misra_profile_set,
    cmd_misra_report,
    _parse_dev_id,
    _cli_add_deviation,
    _interactive_add_deviation,
    _print_misra_report_summary,
    _render_misra_report_html,
)
from yuleosh.cli.commands.swe6 import (  # noqa: E402
    cmd_swe6_status,
    cmd_swe6_check,
)
from yuleosh.cli.commands.review_diff import cmd_review_diff  # noqa: E402

# ── A5: remaining command groups extracted to cli/commands/misc.py ─────
from yuleosh.cli.commands.misc import (  # noqa: E402
    cmd_template_list,
    cmd_ecu_template_list,
    cmd_template_init,
    _interactive_template_init,
    _ensure_tool_deps,
    cmd_init_autosar,
    cmd_init,
    cmd_spec_merge,
    cmd_spec_validate,
    cmd_spec_diff,
    cmd_pipeline_run,
    cmd_pipeline_status,
    cmd_review_auto,
    cmd_review_task,
    cmd_demo_uart,
    cmd_ci_run,
    cmd_evidence_pack,
    _cmd_coverage_c,
    cmd_audit_sync_check,
    _cmd_coverage_gate,
    _cmd_coverage_trend,
    cmd_audit_evidence,
    cmd_kpi_status,
    cmd_kpi_baseline_save,
    cmd_kpi_baseline_compare,
    cmd_stats,
    cmd_kpi_ci_alert,
)


def ensure_osh_home():
    os.environ.setdefault("OSH_HOME", OSH_HOME)


# ── A5 (v3.8.0): remaining command groups moved to cli/commands/misc.py ─
# All command functions below the A5 header are re-exported from
# cli/commands/misc.py (see the import block near the top).
# ── Parser ──────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the yuleOSH CLI."""
    parser = argparse.ArgumentParser(
        prog="yuleosh",
        description="yuleOSH — Embedded AI Development Platform CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Initialize a yuleOSH project directory")
    p_init.add_argument("dir", nargs="?", default=".", help="Project directory")
    p_init.add_argument("--template", "-t", default=None,
                        help="ECU template: bcm, dcu, vcu, bms, eps")
    p_init.add_argument("--name", default=None,
                        help="Project name (defaults to dir basename when --template is set)")
    p_init.add_argument("--mcu", default=None,
                        help="Target MCU: S32K312, S32K344, S32K324, S32K314")
    p_init.add_argument("--asil", default=None,
                        help="ASIL safety level: QM, ASIL_B, ASIL_C, ASIL_D")
    p_init.add_argument("--output", "-o", default=None,
                        help="Output parent directory (default: current dir)")

    # init-autosar
    p_init_asr = sub.add_parser("init-autosar", help="Initialize a complete yuleASR AUTOSAR BSW project")
    p_init_asr.add_argument("project_name", help="Project name")
    p_init_asr.add_argument("--dir", "-d", default=".", help="Parent directory for the project")
    p_init_asr.add_argument("--yuleasr-home", default=None, help="Path to yuleASR BSW platform checkout")

    # project
    p_project = sub.add_parser("project", help="Project management")
    pjsub = p_project.add_subparsers(dest="project_sub")
    p_proj_init = pjsub.add_parser("init", help="Initialize project from template")
    p_proj_init.add_argument("--template", "-t", default=None, help="Template name")
    p_proj_init.add_argument("project_dir", nargs="?", default=None, help="Target project directory")

    # template
    p_template = sub.add_parser("template", help="Project template management")
    tsub = p_template.add_subparsers(dest="template_sub")
    tsub.add_parser("list", help="List all available templates")
    tsub.add_parser("list-ecus", help="List all available ECU templates")
    p_template_init = tsub.add_parser("init", help="Create project from template")
    p_template_init.add_argument("--from", dest="from_template", default=None, help="Template name or path")
    p_template_init.add_argument("project_name", help="Project name")

    # spec
    p_spec = sub.add_parser("spec", help="OpenSpec management")
    ssub = p_spec.add_subparsers(dest="spec_sub")
    p_spec_val = ssub.add_parser("validate", help="Validate an OpenSpec file")
    p_spec_val.add_argument("file", help="Spec file path")
    p_spec_diff = ssub.add_parser("diff", help="Diff two OpenSpec files")
    p_spec_diff.add_argument("old", help="Old spec file")
    p_spec_diff.add_argument("new", help="New spec file")
    p_spec_merge = ssub.add_parser("merge", help="Merge a spec-delta file into the main spec")
    p_spec_merge.add_argument("delta_file", help="Spec-delta markdown file path")
    p_spec_merge.add_argument("--dry-run", action="store_true", help="Validate without writing")
    p_spec_merge.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Agent pipeline management")
    psub = p_pipe.add_subparsers(dest="pipeline_sub")
    p_pipe_run = psub.add_parser("run", help="Run the full Agent pipeline")
    p_pipe_run.add_argument("--mock", action="store_true", help="Run in mock mode (no real LLM)")
    p_pipe_run.add_argument("spec", help="Specification file path")
    p_pipe_status = psub.add_parser("status", help="Show pipeline status")
    p_pipe_status.add_argument("name", nargs="?", help="Pipeline session name")

    # review
    p_review = sub.add_parser("review", help="Code review management")
    rsub = p_review.add_subparsers(dest="review_sub")
    rsub.add_parser("auto", help="Auto-review recent changes")
    p_review_task = rsub.add_parser("task", help="Review a specific task")
    p_review_task.add_argument("name", help="Task name")
    p_review_task.add_argument("kind", nargs="?", default="feature", help="Task kind")
    from yuleosh.cli.commands.review_diff import build_parser as _build_review_diff
    _build_review_diff(rsub)

    # ci
    p_ci = sub.add_parser("ci", help="CI pipeline management")
    csub = p_ci.add_subparsers(dest="ci_sub")
    p_ci_run = csub.add_parser("run", help="Run a CI layer")
    p_ci_run.add_argument("layer", help="CI layer (1/2/3)")

    # evidence / ev — ASPICE compliance evidence
    p_ev = sub.add_parser("ev", help="ASPICE compliance evidence & gap check")
    evsub = p_ev.add_subparsers(dest="ev_sub")
    p_ev_check = evsub.add_parser("check", help="Interactive ASPICE compliance gap check (C1)")
    p_ev_check.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_ev_check.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    p_ev_check.add_argument("--save", action="store_true", help="Save report to .osh/evidence/aspice-gap-report.md")

    # evidence
    p_evidence = sub.add_parser("evidence", help="CL2 audit evidence pack & check (G-50)")
    evisub = p_evidence.add_subparsers(dest="evidence_sub")
    p_ev_pack = evisub.add_parser("pack", help="Generate evidence bundle")
    p_ev_pack.add_argument("--project-dir", default=OSH_HOME)
    p_ev_pack.add_argument("--output", "-o", default=None, help="Output directory")
    p_ev_check = evisub.add_parser("check", help="Check evidence bundle integrity")
    p_ev_check.add_argument("bundle_dir", help="Path to evidence bundle directory")
    p_ev_check.add_argument("--json", action="store_true")

    # config — Profile 变更审计 (Sprint E)
    p_config = sub.add_parser("config", help="Configuration management (Sprint E)")
    csub = p_config.add_subparsers(dest="config_sub")
    p_cfg_profile = csub.add_parser("profile", help="Pipeline profile management")
    cp_sub = p_cfg_profile.add_subparsers(dest="profile_sub")
    p_cp_audit = cp_sub.add_parser("audit", help="View profile change audit log")
    p_cp_audit.add_argument("--limit", type=int, default=50, help="Max entries")
    p_cp_audit.add_argument("--json", action="store_true", help="Output as JSON")

    # stats
    p_stats = sub.add_parser("stats", help="Show project statistics")
    p_stats.add_argument("--json", action="store_true", help="Output as JSON")

    # demo
    p_demo = sub.add_parser("demo", help="Create and run demo projects")
    dsub = p_demo.add_subparsers(dest="demo_sub")
    p_demo_wow = dsub.add_parser("wow", help="🚀 \"Wow Moment\" — Brake Light / Wiper Control demo (D3)")
    p_demo_wow.add_argument("--example", choices=["brake-light", "wiper-control"], default="brake-light",
                              help="Demo example (default: brake-light)")
    p_demo_wow.add_argument("--dir", default=".", help="Working directory")
    p_demo_quick = dsub.add_parser("quick", help="Quick pipeline from one-line requirement")
    p_demo_quick.add_argument("requirement", help="One-line user requirement (e.g. '写一个刹车灯控制')")
    p_demo_quick.add_argument("--dir", default=".", help="Working directory for the demo")
    p_demo_uart = dsub.add_parser("uart", help="STM32F4 ↔ ESP32 UART communication demo")
    p_demo_uart.add_argument("--dir", default=None, help="Target directory for the demo project")
    p_demo_uart.add_argument("--build", action="store_true", help="Build and run the demo after creating it")
    p_demo_uart.add_argument("--skip-cmake", action="store_true", help="Skip CMake environment check")

    # traceability (A5: commands extracted to cli/commands/traceability.py)
    from yuleosh.cli.commands.traceability import build_parser as _build_traceability
    _build_traceability(sub)

    # misra
    # hook
    from yuleosh.hooks.cli import build_hook_subparser
    build_hook_subparser(sub)

    # plan (Ultra-Plan Agent)
    from yuleosh.plan.cli import build_plan_subparser
    build_plan_subparser(sub)

    # kb (knowledge base)
    from yuleosh.kb.cli import build_kb_subparser
    build_kb_subparser(sub)

    # kg (knowledge graph)
    p_kg = sub.add_parser("kg", help="Knowledge Graph management")
    kgsub = p_kg.add_subparsers(dest="kg_sub")
    p_kg_build = kgsub.add_parser("build", help="Incremental knowledge graph build")
    p_kg_build.add_argument("files", nargs="*", default=None, help="Changed file paths")
    p_kg_build.add_argument("--build-id", "-b", default=None, help="Build identifier")
    p_kg_build.add_argument("--auto", action="store_true", help="Auto-detect changes from git diff")
    p_kg_build.add_argument("--ci", action="store_true", help="CI mode (auto-detect + snapshot)")
    p_kg_build.add_argument("--files", type=str, default=None, help="Comma-separated file paths")
    p_kg_build.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_bootstrap = kgsub.add_parser("bootstrap", help="Full bootstrap from traceability data")
    p_kg_bootstrap.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_snapshot = kgsub.add_parser("snapshot", help="Snapshot management")
    ssub = p_kg_snapshot.add_subparsers(dest="snapshot_sub")
    p_kg_snap_list = ssub.add_parser("list", help="List graph snapshots")
    p_kg_snap_list.add_argument("--limit", type=int, default=20, help="Maximum snapshots to show")
    p_kg_snap_list.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_snap_diff = ssub.add_parser("diff", help="Diff two snapshots")
    p_kg_snap_diff.add_argument("build_a", help="First build ID")
    p_kg_snap_diff.add_argument("build_b", help="Second build ID")
    p_kg_snap_diff.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_query = kgsub.add_parser("query", help="Knowledge Graph queries")
    qsub = p_kg_query.add_subparsers(dest="query_sub")
    p_kg_query_impact = qsub.add_parser("impact", help="Impact analysis for changed files")
    p_kg_query_impact.add_argument("file_path", help="File path(s) to analyze (comma-separated)")
    p_kg_query_impact.add_argument("--layer", default=None, help="Test layer filter (unit/integration/sil/hil)")
    p_kg_query_impact.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    # KG Merge Gate (P2: KG-42)
    p_kg_check_merge = kgsub.add_parser("check-merge", help="KG merge gate — validate PR before merge")
    p_kg_check_merge.add_argument("--base-ref", default="HEAD~1", help="Git base ref for change detection")
    p_kg_check_merge.add_argument("--min-confidence", type=float, default=None,
                                    help="Minimum traceability confidence threshold")
    p_kg_check_merge.add_argument("--min-coverage", type=float, default=None,
                                    help="Minimum requirement coverage threshold")
    p_kg_check_merge.add_argument("--no-build", action="store_true",
                                    help="Skip incremental KG build")
    p_kg_check_merge.add_argument("--fail-on-warning", action="store_true",
                                    help="Fail on warnings, not just errors")
    p_kg_check_merge.add_argument("--output", "-o", default=None,
                                    help="Output report file path")
    p_kg_check_merge.add_argument("--json", action="store_true",
                                    help="Output as JSON")
    p_kg_check_merge.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")

    p_kg_stats = kgsub.add_parser("stats", help="Show graph statistics")
    p_kg_stats.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_stats.add_argument("--json", action="store_true", help="Output as JSON")

    # P2: kg report — RTM + Metrics
    p_kg_report = kgsub.add_parser("report", help="Generate reports from KG (P2)")
    rsub = p_kg_report.add_subparsers(dest="report_sub")
    p_kg_report_rtm = rsub.add_parser("rtm", help="Generate traceability matrix")
    p_kg_report_rtm.add_argument("--format", choices=["markdown", "html", "csv"],
                                   default="markdown", help="Output format (default: markdown)")
    p_kg_report_rtm.add_argument("--layer", choices=["unit", "integration", "sil", "hil", "system"],
                                  default=None, help="Test layer filter")
    p_kg_report_rtm.add_argument("--output", "-o", default=None, help="Output file path")
    p_kg_report_rtm.add_argument("--title", default=None, help="Report title")
    p_kg_report_rtm.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_report_metrics = rsub.add_parser("metrics", help="Generate metrics report")
    p_kg_report_metrics.add_argument("--format", choices=["text", "json"],
                                      default="text", help="Output format (default: text)")
    p_kg_report_metrics.add_argument("--trend", type=int, default=5,
                                      help="Number of snapshots for trend analysis")
    p_kg_report_metrics.add_argument("--output", "-o", default=None, help="Output file path")
    p_kg_report_metrics.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")

    # P2: kg events — Event bus
    p_kg_events = kgsub.add_parser("events", help="Event bus operations (P2)")
    evsub = p_kg_events.add_subparsers(dest="events_sub")
    p_kg_events_listen = evsub.add_parser("listen", help="Listen for KG events")
    p_kg_events_listen.add_argument("--filter", default=None, help="Event type filter")
    p_kg_events_listen.add_argument("--duration", type=int, default=None,
                                     help="Listen duration in seconds")
    p_kg_events_listen.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")
    p_kg_events_history = evsub.add_parser("history", help="Show event history")
    p_kg_events_history.add_argument("--filter", default=None, help="Event type filter")
    p_kg_events_history.add_argument("--limit", type=int, default=50, help="Max events to show")
    p_kg_events_history.add_argument("--project-dir", default=OSH_HOME, help="Project root directory")

    # methodology (L3 方法论宿主包) — build_parser in cli/commands/methodology.py
    from yuleosh.cli.commands.methodology import build_parser as _build_methodology
    _build_methodology(sub)

    # coverage
    p_coverage = sub.add_parser("coverage", help="Code coverage management")
    csub = p_coverage.add_subparsers(dest="coverage_sub")
    p_coverage_c = csub.add_parser("c", help="Generate C/C++ code coverage report via gcov/lcov")
    p_coverage_c.add_argument("--build-dir", default=".",
                               help="Build directory containing .gcda/.gcno files")
    p_coverage_c.add_argument("--src-dir", default="src",
                               help="Source directory for filtering")
    p_coverage_gate = csub.add_parser("gate", help="Run coverage gate with fail-under threshold")
    p_coverage_gate.add_argument("--fail-under", type=int, default=50,
                                  help="Coverage percentage threshold (default 60)")

    p_coverage_trend = csub.add_parser("trend", help="Show coverage trend over time")
    p_coverage_trend.add_argument("--days", type=int, default=30,
                                   help="Filter entries within N days (default 30)")
    p_coverage_trend.add_argument("--lines", "-n", type=int, default=50,
                                   help="Number of entries to show")
    p_coverage_trend.add_argument("--json", action="store_true",
                                   help="Output as JSON")

    # audit
    p_audit = sub.add_parser("audit", help="CL2 audit evidence management")
    asub = p_audit.add_subparsers(dest="audit_sub")
    p_audit_evidence = asub.add_parser("evidence", help="Generate CL2 audit evidence bundle (with ZIP export)")
    p_audit_evidence.add_argument("--output-dir", "-o", default=None,
                                   help="Output directory for audit bundle (default: .yuleosh/audit/)")
    p_audit_evidence.add_argument("--zip", action="store_true", default=True,
                                   help="Package evidence into a .zip archive (default: true)")
    p_audit_evidence.add_argument("--no-zip", action="store_false", dest="zip",
                                   help="Skip .zip packaging")
    p_audit_sync = asub.add_parser("sync-check", help="Doc sync gate — verify docs updated with code")
    p_audit_sync.add_argument("--project-dir", default=OSH_HOME,
                               help="Project root directory")
    p_audit_sync.add_argument("--base-ref", default="HEAD",
                               help="Git base reference for diff (default: HEAD)")
    p_audit_sync.add_argument("--save", action="store_true", default=True,
                               help="Save evidence to .yuleosh/reports/docsync-evidence.json")

    # autosar
    p_autosar = sub.add_parser("autosar", help="AUTOSAR management (parse, gen-stub)")
    asub = p_autosar.add_subparsers(dest="autosar_sub")
    from yuleosh.autosar.stubgen import register_cli as register_autosar_stub_cli
    register_autosar_stub_cli(asub)

    # swe6 (A5: commands extracted to cli/commands/swe6.py)
    from yuleosh.cli.commands.swe6 import build_parser as _build_swe6
    _build_swe6(sub)

    # skills (v3.4.0)
    p_skills = sub.add_parser("skills", help="Skills 技能库管理 (v3.4.0)")
    sksub = p_skills.add_subparsers(dest="skills_sub")
    p_skills_list = sksub.add_parser("list", help="List all registered skills")
    p_skills_list.add_argument("--json", action="store_true", help="Output as JSON")
    p_skills_show = sksub.add_parser("show", help="Show full skill content")
    p_skills_show.add_argument("name", help="Skill name (e.g. autosar-coding)")

    # misra (A5: commands extracted to cli/commands/misra.py)
    from yuleosh.cli.commands.misra import build_parser as _build_misra
    _build_misra(sub)

    # kpi
    p_kpi = sub.add_parser("kpi", help="KPI 基线管理")
    ksub = p_kpi.add_subparsers(dest="kpi_sub")
    p_kpi_status = ksub.add_parser("status", help="Show current KPI dashboard")
    p_kpi_baseline_save = ksub.add_parser("baseline-save", help="Save current state as KPI baseline")
    p_kpi_baseline_compare = ksub.add_parser("baseline-compare", help="Compare current state against baseline")
    # G-49: Process stability KPI
    p_kpi_process = ksub.add_parser("process", help="Process stability KPIs (G-49)")
    p_kpi_proc_sub = p_kpi_process.add_subparsers(dest="process_sub")
    p_kpi_proc_status = p_kpi_proc_sub.add_parser("status", help="Show process stability status")
    p_kpi_proc_status.add_argument("--days", type=int, default=14, help="Analysis window days")
    p_kpi_proc_status.add_argument("--json", action="store_true")
    p_kpi_proc_baseline = p_kpi_proc_sub.add_parser("baseline", help="Generate process stability baseline report")
    p_kpi_proc_baseline.add_argument("--label", default="", help="Report label")
    p_kpi_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_kpi_baseline = ksub.add_parser("baseline", help="KPI baseline commands")
    bsub = p_kpi_baseline.add_subparsers(dest="baseline_sub")
    p_kpi_bl_save = bsub.add_parser("save", help="Save current state as KPI baseline")
    p_kpi_bl_save.add_argument("--label", default="", help="Baseline label (e.g. sprint-12)")
    p_kpi_bl_save.add_argument("--json", action="store_true", help="Output as JSON")
    p_kpi_bl_compare = bsub.add_parser("compare", help="Compare current state against baseline")
    p_kpi_bl_compare.add_argument("--json", action="store_true", help="Output as JSON")
    # MP-16: KPI baseline CI alert
    p_kpi_ci_alert = ksub.add_parser("ci-alert", help="Check KPI thresholds and emit CI warnings (MP-16)")
    p_kpi_ci_alert.add_argument("--json", action="store_true", help="Output as JSON")

    # Sprint E: 缺陷逃逸率
    p_kpi_defect_escape = ksub.add_parser("defect-escape", help="缺陷逃逸率采集 (Sprint E)")
    de_sub = p_kpi_defect_escape.add_subparsers(dest="defect_escape_sub")
    p_de_record = de_sub.add_parser("record", help="记录缺陷逃逸数据")
    p_de_record.add_argument("--total", type=int, required=True, help="总缺陷数")
    p_de_record.add_argument("--escaped", type=int, required=True, help="逃逸缺陷数")
    p_de_record.add_argument("--stage", default="customer", help="逃逸阶段 (default: customer)")
    p_de_record.add_argument("--desc", default="", help="描述")
    p_de_status = de_sub.add_parser("status", help="查看缺陷逃逸率")
    p_de_status.add_argument("--days", type=int, default=90, help="分析周期天数")
    p_de_status.add_argument("--json", action="store_true", help="Output as JSON")

    # onboard
    from yuleosh.cli.onboard import build_onboard_parser
    build_onboard_parser(sub)

    # loop
    from yuleosh.loop_engine.cli import build_loop_subparser
    build_loop_subparser(sub)

    # ui
    sub.add_parser("ui", help="Start the web dashboard")

    return parser


def _resolve_ecu_template(name: str) -> dict | None:
    """Resolve an ECU template by name, returning its metadata or None."""
    try:
        from yuleosh.templates.ecus import get_template
        return get_template(name)
    except ImportError:
        return None


# ── Dispatch ────────────────────────────────────────────────────────────


def main():
    ensure_osh_home()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "init":
        if args.template:
            # ECU template-based init (Jinja2 rendering)
            from yuleosh.templates.ecus import init_project, list_ecu_templates

            template_name = args.template
            project_name = args.name or os.path.basename(os.path.abspath(args.dir))
            if not project_name or project_name == ".":
                project_name = template_name + "-project"
            output_dir = args.output or os.path.dirname(os.path.abspath(args.dir))
            if output_dir == ".":
                output_dir = os.getcwd()

            # Determine MCU from template defaults if not provided
            tpl_meta = _resolve_ecu_template(template_name)
            mcu = args.mcu or (tpl_meta.get("mcu", "S32K312") if tpl_meta else "S32K312")
            asil = args.asil or (tpl_meta.get("asil", "ASIL_B") if tpl_meta else "ASIL_B")

            init_project(template_name, project_name, mcu, asil, output_dir=output_dir)
        else:
            cmd_init(args.dir)

    elif args.command == "init-autosar":
        cmd_init_autosar(args.project_name, parent_dir=args.dir, yuleasr_home=args.yuleasr_home)

    elif args.command == "project":
        if args.project_sub == "init":
            # Determine project directory name
            template_name = args.template
            project_dir = args.project_dir or (template_name + "-project" if template_name else "my-project")
            cmd_template_init(project_dir, parent_dir=".", template_name=template_name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "template":
        if args.template_sub == "list":
            cmd_template_list()
        elif args.template_sub == "list-ecus":
            cmd_ecu_template_list()
        elif args.template_sub == "init":
            template_name = getattr(args, "from_template", None)
            cmd_template_init(args.project_name, parent_dir=".", template_name=template_name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "spec":
        if args.spec_sub == "validate":
            cmd_spec_validate(args.file)
        elif args.spec_sub == "diff":
            cmd_spec_diff(args.old, args.new)
        elif args.spec_sub == "merge":
            cmd_spec_merge(
                args.delta_file,
                project_dir=getattr(args, "project_dir", None),
                dry_run=getattr(args, "dry_run", False),
            )
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "pipeline":
        if args.pipeline_sub == "run":
            cmd_pipeline_run(args.spec, mock=args.mock)
        elif args.pipeline_sub == "status":
            cmd_pipeline_status(args.name)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "review":
        if args.review_sub == "auto":
            cmd_review_auto()
        elif args.review_sub == "task":
            cmd_review_task(args.name, args.kind)
        elif args.review_sub == "diff":
            cmd_review_diff(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "coverage":
        if args.coverage_sub == "c":
            _cmd_coverage_c(args.build_dir, args.src_dir)
        elif args.coverage_sub == "gate":
            _cmd_coverage_gate(args)
        elif args.coverage_sub == "trend":
            _cmd_coverage_trend(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "demo":
        if args.demo_sub == "wow":
            from yuleosh.api.demo_wow import main as demo_wow_main
            demo_wow_main(example=args.example, work_dir=args.dir)
        elif args.demo_sub == "quick":
            from yuleosh.api.demo_quick import main as demo_quick_main
            demo_quick_main(args.requirement, args.dir)
        elif args.demo_sub == "uart":
            cmd_demo_uart(args.dir, args.build, args.skip_cmake)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "ci":
        if args.ci_sub == "run":
            cmd_ci_run(args.layer)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "ev":
        if args.ev_sub == "check":
            from yuleosh.evidence.aspice_check import aspice_gap_check
            report = aspice_gap_check(
                project_dir=args.project_dir,
                output_format=args.format,
            )
            print(report)
            if args.save:
                save_path = os.path.join(args.project_dir, ".osh", "evidence", "aspice-gap-report.md")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(report)
                print(f"\n📄 Report saved: {save_path}")
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "evidence":
        if args.evidence_sub == "pack":
            from yuleosh.evidence.evidence_check import pack_evidence_bundle
            manifest = pack_evidence_bundle(
                project_dir=getattr(args, "project_dir", OSH_HOME),
                output_dir=getattr(args, "output", None),
            )
            bundle_dir = args.output or os.path.join(OSH_HOME, ".yuleosh", "evidence-bundle")
            print(f"\n  Manifest: {bundle_dir}/audit-manifest.json")
        elif args.evidence_sub == "check":
            from yuleosh.evidence.evidence_check import check_evidence_integrity
            result = check_evidence_integrity(args.bundle_dir)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
            else:
                print(f"\n  🔍 Evidence Bundle Integrity Check")
                print(f"  {'=' * 55}")
                print(f"  Bundle: {args.bundle_dir}")
                print(f"  Status: {'✅ VALID' if result['valid'] else '❌ INVALID'}")
                print()
                for check in result.get("checks", []):
                    icon = "✅" if check["status"] == "PASS" else "❌"
                    print(f"  {icon} {check['check']}: {check['detail']}")
                for warn in result.get("warnings", []):
                    print(f"  ⚠️  {warn}")
                for err in result.get("errors", []):
                    print(f"  ❌ {err}")
                print()
            if not result.get("valid", True):
                sys.exit(1)
        else:
            # Legacy — show brief status
            print("📦 Generate ASPICE compliance evidence")
            cmd_evidence_pack()

    elif args.command == "audit":
        if args.audit_sub == "evidence":
            cmd_audit_evidence(output_dir=args.output_dir, create_zip=getattr(args, "zip", True))
        elif args.audit_sub == "sync-check":
            cmd_audit_sync_check(
                project_dir=getattr(args, "project_dir", OSH_HOME),
                base_ref=getattr(args, "base_ref", "HEAD"),
                save=getattr(args, "save", True),
            )
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "traceability":
        if args.traceability_sub == "report":
            cmd_traceability_report(args)
        elif args.traceability_sub == "matrix":
            cmd_traceability_matrix(args)
        elif args.traceability_sub == "export":
            cmd_traceability_export(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "config":
        if args.config_sub == "profile":
            if args.profile_sub == "audit":
                from yuleosh.ci.profile import get_profile_audit_log, record_profile_change
                print(get_profile_audit_log(
                    OSH_HOME,
                    limit=args.limit,
                    as_json=args.json,
                ))
            else:
                parser.print_help()
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "stats":
        cmd_stats(json_output=args.json)

    elif args.command == "hook":
        from yuleosh.hooks.cli import handle_hook_command
        sys.exit(handle_hook_command(args))

    elif args.command == "plan":
        from yuleosh.plan.cli import handle_plan_command
        sys.exit(handle_plan_command(args))

    elif args.command == "kb":
        from yuleosh.kb.cli import handle_kb_command
        sys.exit(handle_kb_command(args))

    elif args.command == "kpi":
        if args.kpi_sub == "status":
            cmd_kpi_status(args)
        elif args.kpi_sub == "baseline-save":
            cmd_kpi_baseline_save(args)
        elif args.kpi_sub == "baseline":
            if args.baseline_sub == "save":
                cmd_kpi_baseline_save(args)
            elif args.baseline_sub == "compare":
                cmd_kpi_baseline_compare(args)
            else:
                parser.print_help()
                sys.exit(1)
        elif args.kpi_sub == "process":
            # G-49: Process stability KPIs
            from yuleosh.ci.kpi import get_process_stability_summary, generate_process_baseline_report
            if args.process_sub == "status":
                print(get_process_stability_summary(
                    OSH_HOME,
                    days=args.days,
                    as_json=args.json,
                ))
            elif args.process_sub == "baseline":
                report_path = generate_process_baseline_report(OSH_HOME, label=args.label)
                print(f"\n  ✅ Process stability baseline report generated")
                print(f"     Location: {report_path}")
                print()
            else:
                print("Usage: yuleosh kpi process status|baseline")
        elif args.kpi_sub == "ci-alert":
            cmd_kpi_ci_alert(args)
        elif args.kpi_sub == "defect-escape":
            from yuleosh.ci.kpi import record_defect_escape, get_defect_escape_summary
            if args.defect_escape_sub == "record":
                result = record_defect_escape(
                    OSH_HOME,
                    total_defects=args.total,
                    escaped_defects=args.escaped,
                    stage=args.stage,
                    description=args.desc,
                )
                print(f"\n  ✅ 缺陷逃逸数据已记录")
                print(f"     逃逸率: {result['escape_rate']:.1f}% ({result['escaped_defects']}/{result['total_defects']})")
                print(f"     阶段:   {result['stage']}")
                print()
            elif args.defect_escape_sub == "status":
                print(get_defect_escape_summary(
                    OSH_HOME,
                    days=args.days,
                    as_json=args.json,
                ))
            else:
                print("Usage: yuleosh kpi defect-escape record|status")
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "autosar":
        if args.autosar_sub == "gen-stub":
            from yuleosh.autosar.stubgen import _handle_gen_stub_command
            _handle_gen_stub_command(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "swe6":
        if args.swe6_sub == "status":
            cmd_swe6_status(args)
        elif args.swe6_sub == "check":
            cmd_swe6_check(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "skills":
        from yuleosh.skills.cli import handle_skills_command
        sys.exit(handle_skills_command(args))

    elif args.command == "misra":
        if args.misra_sub == "trend":
            cmd_misra_trend(args)
        elif args.misra_sub == "report":
            cmd_misra_report(args)
        elif args.misra_sub == "deviate":
            cmd_misra_deviate(args)
        elif args.misra_sub == "profile":
            if args.profile_sub == "list":
                cmd_misra_profile_list()
            elif args.profile_sub == "set":
                cmd_misra_profile_set(args.name)
            else:
                parser.print_help()
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "kg":
        from yuleosh.knowledge_graph.kg_cli import (
            cmd_build, cmd_bootstrap, cmd_snapshot_list, cmd_snapshot_diff,
            cmd_query_impact, cmd_stats, cmd_report, cmd_events, cmd_check_merge,
        )
        if args.kg_sub == "build":
            cmd_build(args)
        elif args.kg_sub == "bootstrap":
            cmd_bootstrap(args)
        elif args.kg_sub == "snapshot":
            if args.snapshot_sub == "list":
                cmd_snapshot_list(args)
            elif args.snapshot_sub == "diff":
                cmd_snapshot_diff(args)
            else:
                parser.print_help()
                sys.exit(1)
        elif args.kg_sub == "query":
            if args.query_sub == "impact":
                cmd_query_impact(args)
            else:
                parser.print_help()
                sys.exit(1)
        elif args.kg_sub == "stats":
            cmd_stats(args)
        elif args.kg_sub == "report":
            cmd_report(args)
        elif args.kg_sub == "events":
            cmd_events(args)
        elif args.kg_sub == "check-merge":
            cmd_check_merge(args)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "onboard":
        from yuleosh.cli.onboard import handle_onboard_command
        handle_onboard_command(args)

    elif args.command == "loop":
        from yuleosh.loop_engine.cli import handle_loop_command
        sys.exit(handle_loop_command(args))

    elif args.command == "methodology":
        from yuleosh.cli.commands.methodology import cmd_methodology_check, cmd_methodology_init
        if args.methodology_sub == "init":
            cmd_methodology_init(args.dir, force=args.force)
        elif args.methodology_sub == "check":
            cmd_methodology_check(args.dir, json_out=args.json)
        else:
            parser.print_help()
            sys.exit(1)

    elif args.command == "ui":
        from yuleosh.ui.server import main as ui_main
        ui_main()


if __name__ == "__main__":
    main()
