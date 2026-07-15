# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Coverage Pipeline — Enhanced gcov/lcov pipeline with CI artifact support.

Features:
  - Full gcov/lcov pipeline (line + branch coverage)
  - HTML report generation via genhtml
  - CI artifact publishing (JSON + HTML)
  - Fail-under gates for both line and branch coverage
  - Per-file coverage summary
  - Artifact ZIP packaging

Usage:
    python -m yuleosh.ci.coverage_pipeline \
        --build-dir build \
        --src-dir src \
        --fail-under 60 \
        --fail-under-branch 50 \
        --publish artifacts/coverage
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.ci.gcov_coverage import (
    run_gcov_coverage,
    parse_lcov_output,
)

log = logging.getLogger("yuleosh.ci.coverage_pipeline")


def generate_branch_coverage_report(
    build_dir: str = ".",
    fail_under: Optional[float] = None,
    fail_under_branch: Optional[float] = None,
    publish_dir: Optional[str] = None,
) -> dict:
    """Generate comprehensive coverage report with CI artifact packaging.

    Parameters
    ----------
    build_dir : str
        Build directory containing .gcda/.gcno files.
    fail_under : float, optional
        Minimum line coverage percentage.
    fail_under_branch : float, optional
        Minimum branch coverage percentage.
    publish_dir : str, optional
        Directory to publish artifacts (HTML + JSON + ZIP).

    Returns
    -------
    dict
        Complete coverage report with:
        - summary: aggregate metrics
        - files: per-file coverage
        - gates: pass/fail for each threshold
        - artifacts: paths to published files
    """
    log.info("=== Coverage Pipeline ===")
    log.info("  build_dir:       %s", build_dir)
    log.info("  fail_under:      %s", fail_under)
    log.info("  fail_under_branch: %s", fail_under_branch)
    log.info("  publish_dir:     %s", publish_dir)

    # Step 1: Run lcov capture
    result = run_gcov_coverage(build_dir=build_dir)
    if not result["success"]:
        log.error("Coverage generation failed: %s", result.get("error"))
        return {"success": False, "error": result.get("error", "unknown")}

    lcov_path = result["lcov_file"]
    if not lcov_path or not os.path.isfile(lcov_path):
        log.error("lcov file not found: %s", lcov_path)
        return {"success": False, "error": "lcov file not produced"}

    # Step 2: Parse lcov output
    parsed = parse_lcov_output(lcov_path)

    line_rate = round(parsed["line_rate"] * 100, 2)
    branch_rate = round(parsed["branch_rate"] * 100, 2)

    log.info("  Line coverage:   %.2f%%", line_rate)
    log.info("  Branch coverage: %.2f%%", branch_rate)
    log.info("  Files:           %d", len(parsed["files"]))

    # Step 3: Gate checks
    gates = []
    all_gates_passed = True

    if fail_under is not None:
        line_ok = line_rate >= fail_under
        all_gates_passed = all_gates_passed and line_ok
        gates.append({
            "metric": "line_rate",
            "value": line_rate,
            "threshold": fail_under,
            "passed": line_ok,
        })
        log.info("  Line gate: %s (%.1f%% >= %.1f%%)",
                 "PASS" if line_ok else "FAIL", line_rate, fail_under)

    if fail_under_branch is not None:
        branch_ok = branch_rate >= fail_under_branch
        all_gates_passed = all_gates_passed and branch_ok
        gates.append({
            "metric": "branch_rate",
            "value": branch_rate,
            "threshold": fail_under_branch,
            "passed": branch_ok,
        })
        log.info("  Branch gate: %s (%.1f%% >= %.1f%%)",
                 "PASS" if branch_ok else "FAIL", branch_rate, fail_under_branch)

    # Step 4: Build report
    report = {
        "generated_at": datetime.now().isoformat(),
        "toolchain": {
            "gcov": _get_tool_version("gcov"),
            "lcov": _get_tool_version("lcov"),
            "genhtml": _get_tool_version("genhtml"),
        },
        "summary": {
            "line_rate": line_rate,
            "branch_rate": branch_rate,
            "function_rate": round(
                parsed["totals"]["functions"]["hit"] / max(parsed["totals"]["functions"]["found"], 1) * 100, 2
            ),
            "total_files": len(parsed["files"]),
            "total_lines": parsed["totals"]["lines"]["found"],
            "covered_lines": parsed["totals"]["lines"]["hit"],
            "total_branches": parsed["totals"]["branches"]["found"],
            "covered_branches": parsed["totals"]["branches"]["hit"],
            "total_functions": parsed["totals"]["functions"]["found"],
            "covered_functions": parsed["totals"]["functions"]["hit"],
        },
        "gates": gates,
        "all_gates_passed": all_gates_passed,
        "files": [],
    }

    for f in parsed["files"]:
        report["files"].append({
            "file": f["file"],
            "line_rate": round(f.get("line_rate", 0) * 100, 2),
            "branch_rate": round(f.get("branch_rate", 0) * 100, 2),
            "lines": f["lines"],
            "functions": f["functions"],
        })

    # Step 4b: Record coverage trend entry (for dashboard coverage-trend.jsonl)
    try:
        from yuleosh.ci.coverage_trend import record_coverage
        project_dir = build_dir or "."
        record_coverage(project_dir)
    except Exception as e:
        log.warning("Failed to record coverage trend: %s", e)

    # Step 5: Publish artifacts
    artifacts = {}
    if publish_dir:
        artifacts = _publish_artifacts(report, result.get("html_dir", ""), publish_dir)
        report["artifacts"] = artifacts

    report["success"] = True
    return report


def _get_tool_version(name: str) -> str:
    """Get the version string of a tool."""
    try:
        r = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=5)
        first_line = r.stdout.split("\n")[0] if r.stdout else r.stderr.split("\n")[0]
        return first_line.strip()
    except Exception:
        return "not found"


def _publish_artifacts(report: dict, html_dir: str, publish_dir: str) -> dict:
    """Publish coverage artifacts to a directory.

    Generates:
      - coverage-report.json
      - coverage-report.html (from genhtml, if available)
      - coverage-artifacts.zip (complete archive)

    Parameters
    ----------
    report : dict
        Coverage report data (will be written as JSON).
    html_dir : str
        Path to genhtml output directory (may be empty).
    publish_dir : str
        Target publish directory.

    Returns
    -------
    dict
        Published artifact paths.
    """
    pub_path = Path(publish_dir)
    pub_path.mkdir(parents=True, exist_ok=True)

    artifacts = {}

    # JSON report
    json_path = pub_path / "coverage-report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    artifacts["json"] = str(json_path)
    log.info("Coverage JSON report: %s", json_path)

    # HTML report (from genhtml)
    if html_dir and os.path.isdir(html_dir):
        html_target = pub_path / "coverage-html"
        if html_target.exists():
            shutil.rmtree(html_target)
        shutil.copytree(html_dir, html_target)
        artifacts["html"] = str(html_target)
        log.info("Coverage HTML report: %s", html_target)

        # Create index redirect for easy viewing
        index_html = html_target / "index.html"
        if index_html.exists():
            artifacts["html_index"] = str(index_html)

    # ZIP archive
    zip_path = pub_path / "coverage-artifacts.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(str(json_path)):
            zf.write(str(json_path), "coverage-report.json")
        if html_dir and os.path.isdir(html_dir):
            for root, _, files in os.walk(html_dir):
                for fname in files:
                    file_path = os.path.join(root, fname)
                    arcname = os.path.relpath(file_path, os.path.dirname(html_dir))
                    zf.write(file_path, arcname)
    artifacts["zip"] = str(zip_path)
    log.info("Coverage ZIP archive: %s", zip_path)

    return artifacts


def save_coverage_markdown(report: dict) -> str:
    """Generate a Markdown coverage report summary."""
    s = report.get("summary", {})
    gates = report.get("gates", [])

    lines = [
        "# 覆盖率报告",
        "",
        f"> 生成时间：{report.get('generated_at', '')}",
        f"> gcov: {report.get('toolchain', {}).get('gcov', 'N/A')}",
        f"> lcov: {report.get('toolchain', {}).get('lcov', 'N/A')}",
        "",
        "## 汇总指标",
        "",
        "| 指标 | 值 |",
        "|:-----|:----|",
        f"| 行覆盖率 | **{s.get('line_rate', 0):.2f}%** |",
        f"| 分支覆盖率 | **{s.get('branch_rate', 0):.2f}%** |",
        f"| 函数覆盖率 | {s.get('function_rate', 0):.2f}% |",
        f"| 文件数 | {s.get('total_files', 0)} |",
        f"| 代码行 (总计/覆盖) | {s.get('total_lines', 0)} / {s.get('covered_lines', 0)} |",
        f"| 分支 (总计/覆盖) | {s.get('total_branches', 0)} / {s.get('covered_branches', 0)} |",
        f"| 函数 (总计/覆盖) | {s.get('total_functions', 0)} / {s.get('covered_functions', 0)} |",
        "",
        "## 质量门",
        "",
    ]

    for g in gates:
        status = "✅ PASS" if g["passed"] else "❌ FAIL"
        lines.append(f"- **{g['metric']}**: {status} ({g['value']:.1f}% >= {g['threshold']}%)")

    lines.append("")
    lines.append("## 各文件覆盖率")
    lines.append("")
    lines.append("| 文件 | 行覆盖 | 分支覆盖 | 函数覆盖 |")
    lines.append("|:-----|:-------|:---------|:---------|")

    for f in report.get("files", []):
        short = f["file"].split("/")[-1] if "/" in f["file"] else f["file"]
        lr = f.get("line_rate", 0)
        br = f.get("branch_rate", 0)
        fr = f.get("functions", {}).get("hit", 0) / max(f.get("functions", {}).get("found", 1), 1) * 100
        lines.append(f"| `{short}` | {lr:.1f}% | {br:.1f}% | {fr:.1f}% |")

    # Artifacts
    arts = report.get("artifacts", {})
    if arts:
        lines.append("")
        lines.append("## 产出物")
        lines.append("")
        for key, path in arts.items():
            lines.append(f"- **{key}**: `{path}`")

    lines.append("")
    lines.append("---")
    lines.append("*报告由 yuleOSH Coverage Pipeline 自动生成*")
    return "\n".join(lines)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="yuleOSH Coverage Pipeline — gcov/lcov with CI artifact publishing",
    )
    parser.add_argument("--build-dir", default=".", help="Build directory (default: .)")
    parser.add_argument("--src-dir", default="src", help="Source directory (default: src)")
    parser.add_argument("--fail-under", type=float, default=None, help="Line coverage gate")
    parser.add_argument("--fail-under-branch", type=float, default=None, help="Branch coverage gate")
    parser.add_argument("--publish", default=None, help="Publish directory for artifacts")
    parser.add_argument("--markdown", action="store_true", help="Generate Markdown report")
    parser.add_argument("--output", default="reports/coverage-report.json", help="Output JSON path")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = generate_branch_coverage_report(
        build_dir=args.build_dir,
        fail_under=args.fail_under,
        fail_under_branch=args.fail_under_branch,
        publish_dir=args.publish,
    )

    if not report.get("success"):
        print("❌ Coverage pipeline failed", file=sys.stderr)
        sys.exit(1)

    # Save JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"✅ Coverage report: {output_path}")

    # Markdown
    if args.markdown:
        md_path = output_path.with_suffix(".md")
        md_path.write_text(save_coverage_markdown(report))
        print(f"✅ Coverage markdown: {md_path}")

    # Summary
    s = report["summary"]
    print(f"\n  Line coverage:   {s['line_rate']:.2f}%")
    print(f"  Branch coverage: {s['branch_rate']:.2f}%")
    print(f"  Function coverage: {s['function_rate']:.2f}%")

    gates = report.get("gates", [])
    for g in gates:
        status = "PASS" if g["passed"] else "FAIL"
        print(f"  Gate [{g['metric']}]: {status} ({g['value']:.1f}% >= {g['threshold']}%)")

    artifacts = report.get("artifacts", {})
    for key, path in artifacts.items():
        print(f"  Artifact [{key}]: {path}")

    if not report.get("all_gates_passed", True):
        print("\n❌ Coverage gates FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
