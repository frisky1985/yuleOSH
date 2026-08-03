# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH CLI — Traceability matrix command group.

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


def cmd_traceability_report(args):
    """Generate full traceability report (Requirement ↔ Code ↔ Test ↔ Review)."""
    from yuleosh.alm.traceability import generate_traceability_report

    project_dir = getattr(args, "project_dir", _osh_home())
    spec_path = getattr(args, "spec", None)

    report = generate_traceability_report(
        project_dir=project_dir,
        spec_path=spec_path,
        output_dir=os.path.join(project_dir, ".yuleosh", "reports"),
    )

    summary = report.get("coverage_summary", {})
    print(f"\n  📊 追溯完整性报告")
    print(f"  {'─' * 50}")
    print(f"  需求总数:        {summary.get('requirements_total', 'N/A')}")
    print(f"  测试覆盖率:      {summary.get('test_coverage_pct', 0):.1f}%")
    print(f"  代码覆盖率:      {summary.get('code_coverage', 'N/A')}")
    print(f"  评审覆盖率:      {summary.get('review_coverage', 'N/A')}")
    print(f"  覆盖缺口数:      {summary.get('total_gaps', 0)}")
    print(f"  孤立测试文件:    {summary.get('orphaned_tests', 0)}")

    recs = report.get("recommendations", [])
    if recs:
        print()
        for r in recs:
            print(f"  {r}")

    report_path = os.path.join(project_dir, ".yuleosh", "reports", "traceability-report.json")
    print(f"\n  完整报告: {report_path}\n")


def cmd_traceability_export(args):
    """Export traceability matrix in OEM-compatible format."""
    from yuleosh.evidence.oem_templates import export_traceability_matrix
    from yuleosh.knowledge_graph import get_store

    project_dir = getattr(args, "project_dir", _osh_home())
    template_name = getattr(args, "template", "generic")
    output_format = getattr(args, "output_format", "markdown")
    filter_layer = getattr(args, "layer", None)
    include_evidence = not getattr(args, "no_evidence", False)

    store = get_store()

    result = export_traceability_matrix(
        store,
        template=template_name,
        output_format=output_format,
        filter_layer=filter_layer,
        include_test_evidence=include_evidence,
    )

    print(result)

    # Also save to file
    ext_map = {"markdown": "md", "csv": "csv", "json": "json"}
    ext = ext_map.get(output_format, "md")
    out_dir = Path(project_dir) / ".yuleosh" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"traceability-{template_name}-matrix.{ext}"
    out_path.write_text(result, encoding="utf-8")
    print(f"\n  💾 Saved to: {out_path}\n", file=sys.stderr)


def cmd_traceability_matrix(args):
    """Generate LRM / LRT matrix as JSON and print formatted overview."""
    from yuleosh.alm.traceability import generate_lrm, generate_lrt

    project_dir = getattr(args, "project_dir", _osh_home())
    spec_path = getattr(args, "spec", None)
    build_id = getattr(args, "build_id", None)

    lrt = generate_lrt(project_dir, spec_path)

    # Filter by build_id if provided
    if build_id:
        lrm = lrt.get("lrm", {})
        requirements = lrm.get("requirements", [])
        lrm["requirements"] = [
            r for r in requirements
            if r.get("req_id", "").startswith(build_id) or r.get("id", "").startswith(build_id)
        ]
        lrm["summary"] = {
            "total": len(lrm["requirements"]),
            "with_code": sum(1 for r in lrm["requirements"] if r.get("has_code")),
            "with_test": sum(1 for r in lrm["requirements"] if r.get("has_test")),
            "with_review": sum(1 for r in lrm["requirements"] if r.get("has_review")),
            "without_code": sum(1 for r in lrm["requirements"] if not r.get("has_code")),
            "without_test": sum(1 for r in lrm["requirements"] if not r.get("has_test")),
            "without_review": sum(1 for r in lrm["requirements"] if not r.get("has_review")),
            "coverage_pct": (sum(1 for r in lrm["requirements"] if r.get("has_test")) / max(len(lrm["requirements"]), 1)) * 100,
        } if lrm["requirements"] else {
            "total": 0, "with_code": 0, "with_test": 0, "with_review": 0,
            "without_code": 0, "without_test": 0, "without_review": 0, "coverage_pct": 0.0,
        }
        lrt["lrm"] = lrm
    lrm = lrt.get("lrm", {})
    requirements = lrm.get("requirements", [])
    summary = lrm.get("summary", {})
    gaps = lrt.get("gap_analysis", {})

    # Print formatted overview
    print(f"\n  {'=' * 70}")
    print(f"  📋 需求追溯矩阵 (LRM / LRT)")
    print(f"  {'=' * 70}")
    print(f"  生成时间: {lrm.get('generated_at', '')[:19]}")
    print(f"  {'─' * 70}")

    # Table header
    header = f"  {'req_id':<20} {'SHALL':<8} {'Code':<6} {'Test':<6} {'Review':<6} {'StepHdlr':<8} Section"
    print(header)
    print(f"  {'─' * 70}")

    for req in requirements:
        req_id = req.get("req_id") or "—"
        shall_id = req.get("id", "—")
        code_icon = "✅" if req.get("has_code") else "❌"
        test_icon = "✅" if req.get("has_test") else "❌"
        review_icon = "✅" if req.get("has_review") else "❌"
        steps = req.get("step_handlers", [])
        step_str = f"{len(steps)}" if steps else "—"
        section = (req.get("section", "") or "")[:30]
        print(f"  {req_id:<20} {shall_id:<8} {code_icon:<6} {test_icon:<6} {review_icon:<6} {step_str:<8} {section}")

    print(f"  {'─' * 70}")
    total = summary.get("total", 0)
    cov = summary.get("coverage_pct", 0.0)
    print(f"  需求总数: {total}  |  测试覆盖率: {cov}%")
    print(f"  Code: {summary.get('with_code', 0)}/{total}  Test: {summary.get('with_test', 0)}/{total}  Review: {summary.get('with_review', 0)}/{total}")

    gap_list = gaps.get("gaps", [])
    if gap_list:
        print(f"\n  ⚠️  覆盖缺口: {len(gap_list)}")
        for g in gap_list[:10]:
            rid = g.get("req_id", "?")
            stmt = g.get("statement", "")[:50]
            print(f"    • [{g['type']}] {rid}: {stmt}...")
        if len(gap_list) > 10:
            print(f"    ... 还有 {len(gap_list) - 10} 个缺口")

    print()

    # Also output full JSON to stdout for pipe/redirect
    print(">>> Full JSON:", file=sys.stderr)
    print(json.dumps(lrt, indent=2, ensure_ascii=False, default=str))


def build_parser(sub):
    """Register the traceability command group (A5)."""
    p_trace = sub.add_parser("traceability", help="Traceability matrix management")
    tsub = p_trace.add_subparsers(dest="traceability_sub")
    p_trace_report = tsub.add_parser("report", help="Generate full traceability report")
    p_trace_report.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_report.add_argument("--spec", default=None, help="Path to spec file")
    p_trace_matrix = tsub.add_parser("matrix", help="Generate LRM/LRT matrix (JSON output)")
    p_trace_matrix.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_matrix.add_argument("--spec", default=None, help="Path to spec file")
    p_trace_matrix.add_argument("--build-id", default=None, help="Filter by build ID")
    p_trace_export = tsub.add_parser("export", help="Export traceability matrix in OEM-compatible format")
    p_trace_export.add_argument("--template", default="generic",
                                choices=["generic", "vw", "bmw", "mercedes", "oem_common"],
                                help="OEM template (default: generic)")
    p_trace_export.add_argument("--format", default="markdown", dest="output_format",
                                choices=["markdown", "csv", "json"],
                                help="Output format (default: markdown)")
    p_trace_export.add_argument("--layer", default=None, help="Filter by test layer (unit/integration/sil/hil)")
    p_trace_export.add_argument("--project-dir", default=_osh_home(), help="Project root directory")
    p_trace_export.add_argument("--no-evidence", action="store_true",
                                help="Exclude test evidence links from output")
    return p_trace
