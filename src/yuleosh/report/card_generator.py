#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Quality Summary Card Generator — produces a compact Markdown "quality card"
embeddable in Feishu group messages.

Content:
  - MISRA: total violations ▲/▼ vs previous, Required count, violation density
  - UT: test pass rate, coverage, SHALL coverage
  - Key changes: new/resolved violations, new/failed tests

Usage:
    from yuleosh.report.card_generator import generate_quality_card

    card_md = generate_quality_card(project_dir="/path/to/project")
    # Post card_md to Feishu webhook
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("report.card_generator")


def _load_json(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None on failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.debug("Cannot load %s: %s", path, e)
        return None


def _load_jsonl_latest(path: Path) -> Optional[dict]:
    """Load the last line of a JSONL file."""
    if not path.exists():
        return None
    try:
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except (json.JSONDecodeError, OSError) as e:
        log.debug("Cannot load JSONL %s: %s", path, e)
        return None


def _format_delta(current: float, previous: float, higher_is_better: bool = True) -> str:
    """Format a delta with ▲/▼ emoji."""
    if previous == 0:
        return "—"
    delta = ((current - previous) / previous) * 100
    if abs(delta) < 0.5:
        return "→"
    if higher_is_better:
        return f"🟢 +{delta:.0f}%" if delta > 0 else f"🔴 {delta:.0f}%"
    else:
        return f"🔴 +{delta:.0f}%" if delta > 0 else f"🟢 {delta:.0f}%"


def generate_quality_card(
    project_dir: str,
    misra_report_path: Optional[Path] = None,
    coverage_report_path: Optional[Path] = None,
    selftest_report_path: Optional[Path] = None,
) -> str:
    """Generate a compact quality summary card in Markdown.

    The card is formatted for embedding in Feishu group messages.

    Parameters
    ----------
    project_dir : str
        Root path of the project.
    misra_report_path : Path, optional
        Path to MISRA report JSON. Defaults to ``.yuleosh/reports/misra-report.json``.
    coverage_report_path : Path, optional
        Path to C coverage report JSON. Defaults to ``.yuleosh/reports/c-coverage.json``.
    selftest_report_path : Path, optional
        Path to self-test report XLSX/JSON. Defaults to ``.yuleosh/reports/selftest-report.xlsx``.

    Returns
    -------
    str
        Markdown quality card content.
    """
    proj = Path(project_dir)
    misra_path = misra_report_path or (proj / ".yuleosh" / "reports" / "misra-report.json")
    cov_path = coverage_report_path or (proj / ".yuleosh" / "reports" / "c-coverage.json")
    trend_path = proj / ".yuleosh" / "reports" / "misra-trend.jsonl"
    coverage_trend_path = proj / ".yuleosh" / "reports" / "coverage-trend.jsonl"

    # ── Load data ──────────────────────────────────────────────────────
    misra = _load_json(misra_path)
    coverage = _load_json(cov_path)
    misra_trend = _load_jsonl_latest(trend_path)
    coverage_trend = _load_jsonl_latest(coverage_trend_path)

    # ── MISRA section ───────────────────────────────────────────────────
    misra_lines: list[str] = []
    if misra:
        ms = misra.get("summary", {})
        total = ms.get("total_violations", 0)
        classification = ms.get("misra_classification", {})
        required = classification.get("required", 0)
        advisory = classification.get("advisory", 0)
        violations_per_kloc = ms.get("violations_per_kloc", 0.0)
        rules_violated = ms.get("total_rules_violated", 0)
        files_affected = len(ms.get("unique_files", []))

        # Compute delta vs previous trend
        if misra_trend is not None:
            prev_total = misra_trend.get("total_violations", 0)
            delta_str = _format_delta(total, prev_total, higher_is_better=False)
            misra_lines.append(f"  总违规: **{total}** ({delta_str})")
        else:
            misra_lines.append(f"  总违规: **{total}**")

        misra_lines.append(f"  Required: **{required}** | Advisory: **{advisory}**")
        misra_lines.append(f"  违规密度: **{violations_per_kloc:.2f}** violations/KLOC")
        misra_lines.append(f"  违规规则: **{rules_violated}** | 影响文件: **{files_affected}**")

        # Key changes from trend diff
        if misra and misra.get("prev_build_diff"):
            diff = misra["prev_build_diff"]
            delta = diff.get("total_violations_delta", 0)
            if delta > 0:
                misra_lines.append(f"  🚨 新增违规: **+{delta}** (vs 前次)")
            elif delta < 0:
                misra_lines.append(f"  ✅ 解决违规: **{delta}** (vs 前次)")
    else:
        misra_lines.append("  未有 MISRA 分析记录")

    # ── Coverage section ───────────────────────────────────────────────
    cov_lines: list[str] = []
    if coverage:
        line_rate = coverage.get("line_rate", 0)
        branch_rate = coverage.get("branch_rate", 0)
        total_files = coverage.get("total_files", 0)

        if coverage_trend:
            # Support both nested format ({"c": {"line_rate": 99.19}}) and flat format
            c_data = coverage_trend.get("c", {})
            prev_line = c_data.get("line_rate")
            if prev_line is None:
                prev_line = coverage_trend.get("line_rate", 0)
            prev_branch = c_data.get("branch_rate")
            if prev_branch is None:
                prev_branch = coverage_trend.get("branch_rate", 0)
            line_delta = _format_delta(line_rate, prev_line)
            branch_delta = _format_delta(branch_rate, prev_branch)
        else:
            line_delta = "—"
            branch_delta = "—"

        line_icon = "✅" if line_rate >= 85 else ("⚠️" if line_rate >= 70 else "❌")
        branch_icon = "✅" if branch_rate >= 80 else ("⚠️" if branch_rate >= 60 else "❌")

        cov_lines.append(f"  行覆盖率: {line_icon} **{line_rate:.1f}%** ({line_delta})")
        cov_lines.append(f"  分支覆盖率: {branch_icon} **{branch_rate:.1f}%** ({branch_delta})")
        cov_lines.append(f"  覆盖文件: **{total_files}**")
    else:
        cov_lines.append("  未有覆盖率报告")

    # ── UT section ─────────────────────────────────────────────────────
    ut_lines: list[str] = []
    selftest_md_path = proj / ".yuleosh" / "reports" / "selftest-report.json"
    selftest_json = _load_json(selftest_md_path)

    if selftest_json:
        total_tests = selftest_json.get("total_tests", 0)
        passed = selftest_json.get("passed", 0)
        failed = selftest_json.get("failed", 0)
        coverage_pct = selftest_json.get("coverage", 0)

        pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0
        pass_icon = "✅" if pass_rate >= 90 else ("⚠️" if pass_rate >= 70 else "❌")

        ut_lines.append(f"  通过率: {pass_icon} **{passed}/{total_tests}** ({pass_rate:.0f}%)")
        if coverage_pct:
            ut_lines.append(f"  自测覆盖率: **{coverage_pct:.1f}%**")

        shall_coverage = selftest_json.get("shall_coverage", {})
        if shall_coverage:
            shall_total = shall_coverage.get("total", 0)
            shall_covered = shall_coverage.get("covered", 0)
            shall_pct = (shall_covered / shall_total * 100) if shall_total > 0 else 0
            shall_icon = "✅" if shall_pct >= 90 else ("⚠️" if shall_pct >= 70 else "❌")
            ut_lines.append(f"  SHALL 覆盖: {shall_icon} **{shall_covered}/{shall_total}** ({shall_pct:.0f}%)")
    else:
        # Fallback: try to read from the layer result
        layer_1 = _load_json(proj / ".osh" / "ci")
        ut_lines.append("  未有自测报告")

    # ── Key changes ────────────────────────────────────────────────────
    changes_lines: list[str] = []
    if misra and misra.get("prev_build_diff"):
        diff = misra["prev_build_diff"]
        files_added = diff.get("files_added", [])
        files_removed = diff.get("files_removed", [])
        if files_added:
            changes_lines.append(f"  🆕 新增违规文件: **{len(files_added)}** 个")
            for f in files_added[:3]:
                changes_lines.append(f"    - `{f}`")
        if files_removed:
            changes_lines.append(f"  🗑️ 消除违规文件: **{len(files_removed)}** 个")

    # ── Build card ─────────────────────────────────────────────────────
    lines = [
        "📊 **yuleOSH 质量摘要卡片**",
        "",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("### 🔍 MISRA 静态分析")
    lines.extend(misra_lines)
    lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("### 📊 代码覆盖率")
    lines.extend(cov_lines)
    lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("### 🧪 单元测试")
    lines.extend(ut_lines)
    lines.append("")

    if changes_lines:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("### 🔄 关键变化")
        lines.extend(changes_lines)
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("*由 yuleOSH CI 自动生成*")

    return "\n".join(lines)


def generate_feishu_card_json(project_dir: str) -> dict:
    """Generate a Feishu interactive card (JSON) from the quality card.

    Returns a dict suitable for posting as Feishu interactive card message.
    """
    md_content = generate_quality_card(project_dir)

    # Build a simple Feishu interactive card
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📊 yuleOSH 质量报告"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": md_content,
            },
            {
                "tag": "hr",
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            },
        ],
    }
    return card
