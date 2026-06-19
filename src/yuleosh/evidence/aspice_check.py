"""
yuleOSH ASPICE Gap Check — Interactive compliance checklist (C1).

Provides ``aspice_gap_check()`` that runs the existing ``ComplianceChecker``
but formats output as **"what you're missing"** (gap-oriented) rather than
"what I found".  Organized by SWE.1~SWE.6, showing each BP and actionable
steps to close the gap.

Usage:
    from yuleosh.evidence.aspice_check import aspice_gap_check
    report = aspice_gap_check(project_dir)
    print(report)

CLI:
    yuleosh ev check [--project-dir <path>] [--format markdown|json]
"""

import json
import os
from pathlib import Path
from typing import Optional

from yuleosh.compliance.compliance_checker import ComplianceChecker


# ------------------------------------------------------------------ #
# Gap-oriented messages for each BP: what to DO, not what you have
# ------------------------------------------------------------------ #

_FIX_GUIDANCE: dict[str, list[str]] = {
    # SWE.1 — Software Requirements Analysis
    "SWE.1.BP1": [
        "📄 创建 `docs/software-requirements.md` 或 `docs/requirements.md`",
        "🔖 每条需求分配唯一标识符（REQ-xxx），包含 SHALL 语句",
        "🔗 将每条需求追溯至系统需求",
    ],
    "SWE.1.BP2": [
        "📂 在 `specs/` 目录下按功能区域组织需求文件",
        "🏷️  为每条需求定义属性（优先级、状态）",
    ],
    "SWE.1.BP3": [
        "📝 创建 `docs/impact-analysis.md`，记录变更影响分析",
        "📊 每次需求变更时更新影响分析，覆盖进度、资源和风险",
    ],

    # SWE.2 — Software Architectural Design
    "SWE.2.BP1": [
        "🏗️  创建 `docs/architecture.md` 或 `ARCHITECTURE.md`，覆盖全部软件需求",
        "🧩 明确组件边界和接口定义",
    ],
    "SWE.2.BP2": [
        "📐 在 `include/` 目录中定义外部接口的头文件",
        "📏 接口规范中包括数据类型和范围定义",
    ],
    "SWE.2.BP3": [
        "🔍 创建 `docs/architecture-review.md`，记录架构审查过程",
        "✅ 审查发现项需跟踪至闭环",
    ],

    # SWE.3 — Software Detailed Design and Unit Construction
    "SWE.3.BP1": [
        "💻 确保 `src/` 目录包含全部源代码",
        "📏 遵循已定义的编码规范（.clang-format / pyproject.toml）",
        "✂️  每个函数保持单一职责，鼓励函数 < 50 行",
    ],
    "SWE.3.BP2": [
        "🧪 在 `tests/` 目录为每个软件单元创建单元测试",
        "🔀 测试覆盖正常、边界和错误条件",
        "🔗 测试用例需可追溯至需求",
    ],
    "SWE.3.BP3": [
        "📋 创建 `docs/design-review.md`，记录每个组件的设计审查",
        "✅ 审查覆盖正确性、一致性和可测试性",
    ],

    # SWE.4 — Software Unit Verification
    "SWE.4.BP1": [
        "🧪 运行全部单元测试并确认 100% 通过",
        "📊 语句覆盖率 ≥ 80%（运行 coverage trend 检查）",
        "🌿 分支/条件覆盖率 ≥ 70%",
        "⚙️  在 `.yuleosh/ci/` 中配置 CI 执行记录",
    ],
    "SWE.4.BP2": [
        "📎 创建需求→单元测试的追溯矩阵（运行 `yuleosh evidence pack`）",
        "🔄 保持追溯矩阵最新，每次需求变更后重新生成",
    ],
    "SWE.4.BP3": [
        "📝 记录失败测试的分析结果和修复计划",
        "🔄 定义回归测试策略（建议在 ci-config.yaml 中配置）",
    ],

    # SWE.5 — Software Integration and Integration Test
    "SWE.5.BP1": [
        "📄 创建 `docs/integration-strategy.md`，定义集成序列",
        "🧩 识别所需的桩/驱动（stubs/drivers）",
    ],
    "SWE.5.BP2": [
        "🔧 确保集成构建每次成功",
        "📋 遵循已定义的集成策略进行集成",
    ],
    "SWE.5.BP3": [
        "🧪 在 `tests/integration/` 中创建集成测试",
        "🔀 集成测试覆盖组件间接口和数据流",
        "✅ 全部集成测试通过",
    ],

    # SWE.6 — Software Qualification Test
    "SWE.6.BP1": [
        "📄 创建 `docs/qualification-strategy.md`，覆盖所有需求",
        "🎯 为每条需求定义验收标准",
    ],
    "SWE.6.BP2": [
        "🧪 运行全部合格性测试并确认通过",
        "🎯 在目标环境或等效环境中执行测试",
        "📦 归档测试证据（运行 `yuleosh audit evidence`）",
    ],
    "SWE.6.BP3": [
        "📎 创建需求→合格性测试的追溯（验收矩阵）",
        "📊 运行 `yuleosh evidence pack` 生成需求覆盖率报告",
        "🔍 标识并记录覆盖缺口",
    ],
}

_DEFAULT_FIX = [
    "📋 查看 SWE 过程组文档，确认此 BP 的产出物",
    "📎 检查 `.osh/evidence/` 中是否已有部分证据",
]


def aspice_gap_check(
    project_dir: str = None,
    output_format: str = "markdown",
    template_path: Optional[str] = None,
) -> str:
    """Run ASPICE v3.1 gap-oriented compliance check.

    Instead of saying "what exists", this function reports **what is
    still missing** — organized by SWE.1~SWE.6, per BP, with actionable
    remediation steps.

    Parameters
    ----------
    project_dir : str, optional
        Project root directory. Defaults to OSH_HOME or CWD.
    output_format : str
        ``"markdown"`` (default) or ``"json"``.
    template_path : str, optional
        Path to a custom ASPICE YAML template.

    Returns
    -------
    str
        Formatted gap report (Markdown or JSON).
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    # Run the existing ComplianceChecker
    checker = ComplianceChecker(
        project_dir=project_dir,
        template_path=Path(template_path) if template_path else None,
    )
    report = checker.run()

    if output_format == "json":
        return _format_gap_json(report)

    return _format_gap_markdown(report, project_dir)


def _format_gap_markdown(report: dict, project_dir: str) -> str:
    """Format gap check as Markdown — what you're MISSING, not what you have."""
    lines = [
        "# 🔍 yuleOSH ASPICE Compliance Gap Check",
        "",
        f"> **项目**: `{report['project_dir']}`",
        f"> **标准**: {report['standard']} v{report['version']}",
        f"> **生成时间**: {report['generated_at']}",
        "",
        "---",
        "",
    ]

    summary = report["summary"]

    # ── Executive summary (gap-oriented) ─────────────────────────────────
    bps_not_fully_passed = summary["partial"] + summary["failed"]
    lines.append("## 📊 概要")
    lines.append("")
    lines.append(f"| 指标 | 数量 |")
    lines.append(f"|:-----|-----:|")
    lines.append(f"| 总 BP 数 | {summary['total_bps']} |")
    lines.append(f"| ✅ 完全就绪 | {summary['passed']} |")
    lines.append(f"| ⚠️  部分就绪 | {summary['partial']} |")
    lines.append(f"| ❌ 缺失/未开始 | {summary['failed']} |")
    lines.append("")

    if bps_not_fully_passed == 0:
        lines.append("🎉 **所有 Base Practices 均已就绪！**")
        lines.append("")
    else:
        lines.append(
            f"🚩 **{bps_not_fully_passed} 个 Base Practice 尚待补齐** — "
            f"详见下方逐项检查"
        )
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Per-SWE gap breakdown ────────────────────────────────────────────
    for swe_key in sorted(report["swe_sections"].keys()):
        section = report["swe_sections"][swe_key]
        swe_id = section["id"]
        swe_title = section["title"]
        description = section.get("description", "").strip()

        # Count gaps in this SWE
        gap_bps = [bp for bp in section["base_practices"] if bp["status"] != "✅"]

        lines.append(f"## {swe_id}: {swe_title}")
        if description:
            lines.append(f"> {description}")
            lines.append("")
        lines.append(f"**状态**: {len(gap_bps)}/{len(section['base_practices'])} BP 尚待补齐")
        lines.append("")

        for bp in section["base_practices"]:
            bp_id = bp["id"]
            bp_title = bp["title"]
            status = bp["status"]
            passed = bp["passed_checks"]
            total = bp["total_checks"]

            if status == "✅":
                # Fully passed — brief acknowledgment
                lines.append(f"### {bp_id}: {bp_title}")
                lines.append("")
                lines.append(f"**状态**: ✅ 已就绪 ({passed}/{total})")
                lines.append("")
                continue

            # GAP — show what's missing
            gap_count = total - passed
            lines.append(f"### {bp_id}: {bp_title}")
            lines.append("")
            lines.append(
                f"**状态**: {'⚠️  部分就绪' if status == '⚠️' else '❌ 缺失'} "
                f"({gap_count}/{total} 项未通过)"
            )
            lines.append("")

            # Show which checks failed
            lines.append("**❌ 缺失项**:")
            lines.append("")
            for detail in bp.get("details", []):
                if detail.startswith("  ❌"):
                    lines.append(f"- {detail.replace('  ❌ ', '').strip()}")
            lines.append("")

            # Show fix guidance
            fix_steps = _FIX_GUIDANCE.get(bp_id, _DEFAULT_FIX)
            lines.append("**✅ 修复步骤**:")
            lines.append("")
            for step in fix_steps:
                lines.append(f"- {step}")
            lines.append("")

            # Add yuleOSH CLI hints
            lines.append("**💡 相关 CLI 命令**:")
            lines.append("")
            _add_cli_hints(lines, bp_id)
            lines.append("")

        lines.append("---")
        lines.append("")

    # ── Footer with CLI summary ──────────────────────────────────────────
    lines.append("## 🚀 快速启动")
    lines.append("")
    lines.append("```bash")
    lines.append("# 生成证据包（补齐多数 BP 证据）")
    lines.append("yuleosh evidence pack")
    lines.append("")
    lines.append("# 生成 CL2 审计证据包")
    lines.append("yuleosh audit evidence")
    lines.append("")
    lines.append("# 查看覆盖趋势")
    lines.append("yuleosh coverage trend")
    lines.append("")
    lines.append("# 查看 MISRA 违规趋势")
    lines.append("yuleosh misra trend")
    lines.append("")
    lines.append("# 查看 KPI 仪表盘")
    lines.append("yuleosh kpi status")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("*报告由 yuleOSH ASPICE Gap Check 生成*")

    return "\n".join(lines)


def _add_cli_hints(lines: list[str], bp_id: str) -> None:
    """Add context-sensitive CLI hints for each BP."""
    bp_to_cli = {
        "SWE.1.BP1": (
            "`yuleosh spec validate docs/requirements.md` — 验证需求文件"
        ),
        "SWE.1.BP2": (
            "`yuleosh spec diff old.md new.md` — 对比需求变更"
        ),
        "SWE.2.BP1": (
            "`yuleosh pipeline run specs/spec.md` — 生成架构分析"
        ),
        "SWE.2.BP2": (
            "`yuleosh review task interface` — 审查接口设计"
        ),
        "SWE.3.BP1": (
            "`yuleosh review auto` — 自动审查代码"
        ),
        "SWE.3.BP2": (
            "`yuleosh test c --create-suite` — 创建 C 单元测试脚手架"
        ),
        "SWE.4.BP1": (
            "`yuleosh coverage trend` — 查看测试覆盖率趋势"
        ),
        "SWE.4.BP2": (
            "`yuleosh traceability matrix` — 生成追溯矩阵"
        ),
        "SWE.4.BP3": (
            "`yuleosh audit evidence` — 收集审计证据"
        ),
        "SWE.5.BP1": (
            "`yuleosh coverage c` — 查看集成覆盖率"
        ),
        "SWE.5.BP3": (
            "`yuleosh ci run 25` — 运行集成测试层"
        ),
        "SWE.6.BP1": (
            "`yuleosh ci run 3` — 运行合格性测试层"
        ),
        "SWE.6.BP2": (
            "`yuleosh audit evidence` — 归档测试证据"
        ),
        "SWE.6.BP3": (
            "`yuleosh evidence pack` — 生成完整证据包"
        ),
    }
    cli = bp_to_cli.get(bp_id)
    if cli:
        lines.append(f"- {cli}")
    lines.append("- 查阅 `yuleosh --help` 获取全部命令")


def _format_gap_json(report: dict) -> str:
    """Format gap check as JSON."""
    summary = report["summary"]
    summary["bps_not_fully_passed"] = summary["partial"] + summary["failed"]

    gap_detail: list[dict] = []
    for swe_key in sorted(report["swe_sections"].keys()):
        section = report["swe_sections"][swe_key]
        for bp in section["base_practices"]:
            if bp["status"] != "✅":
                gap_detail.append({
                    "swe_id": section["id"],
                    "swe_title": section["title"],
                    "bp_id": bp["id"],
                    "bp_title": bp["title"],
                    "status": bp["status"],
                    "failed_checks": bp["failed_checks"],
                    "total_checks": bp["total_checks"],
                    "missing_items": [
                        d.replace("  ❌ ", "").strip()
                        for d in bp.get("details", [])
                        if d.startswith("  ❌")
                    ],
                    "fix_steps": _FIX_GUIDANCE.get(bp["id"], _DEFAULT_FIX),
                })

    result = {
        "project_dir": report["project_dir"],
        "standard": report["standard"],
        "version": report["version"],
        "generated_at": report["generated_at"],
        "summary": summary,
        "gaps": gap_detail,
    }
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)
