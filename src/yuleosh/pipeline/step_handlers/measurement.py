"""MAN.6 测量（确定性）— 补齐 ASPICE 管理过程组的度量能力。

设计原则与 ``validation.py`` / ``sys_layer.py`` 一致：**确定性生成 +
确定性评审**，不依赖 LLM 判绿：

- 度量项定义自 ``ci.kpi`` 的阈值单一来源派生，避免文档与代码漂移；
- 测量结果**只**汇总 ``kpi_status()`` 的真实数据；无数据的度量项如实
  标注「无数据」，绝不以 0 或默认值伪装成通过；
- 阈值判定沿用 ``ci.kpi`` 既有 PASS/FAIL 逻辑，不在此重复实现。

产物路径与 ``aspice_man_v3.1.yaml`` 的 evidence 路径严格对齐
（``docs/measurement-*.md``），使 ``yuleosh compliance check --profile
aspice_man_v3.1`` 能直接识别为 MAN.6 证据。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from yuleosh.ci.coverage_trend import TREND_FILE as COVERAGE_TREND_FILE
from yuleosh.ci.kpi.kpi_state import (
    DEFECT_ESCAPE_FILE,
    DEFAULT_THRESHOLDS,
    PROCESS_KPI_FILE,
)
from yuleosh.ci.misra_trend import TREND_FILE as MISRA_TREND_FILE
from yuleosh.ci.kpi.report import kpi_status
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.measurement")

MEASUREMENT_PLAN = "docs/measurement-plan.md"
MEASUREMENT_REPORT = "docs/measurement-report.md"

_PLAN_SECTIONS = ("## 度量项定义", "## 测量规程", "## 可追溯性")
_REPORT_SECTIONS = ("## 测量结果", "## 可追溯性")

# (度量ID, 名称, kpi_status.entries.metric, 单位, 阈值键, 判据方向)
# 阈值键取自 ci.kpi.kpi_state.DEFAULT_THRESHOLDS（单一事实来源）。
INDICATORS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("M-001", "MISRA 总违规数", "misra_total_violations", "count",
     "misra_total_violations", "≤"),
    ("M-002", "MISRA Required 违规数", "misra_required_violations", "count",
     "misra_required_violations", "≤"),
    ("M-003", "C 语言行覆盖率", "c_line_coverage_pct", "%",
     "c_line_coverage_pct", "≥"),
    ("M-004", "Python 行覆盖率", "python_line_coverage_pct", "%",
     "python_line_coverage_pct", "≥"),
    ("M-005", "构建成功率", "build_success_rate", "%",
     "build_success_rate_pct", "≥"),
    ("M-006", "回归触发率", "regression_trigger_rate", "%",
     "regression_trigger_rate_pct", "≤"),
    ("M-007", "缺陷逃逸率", "defect_escape_rate", "%",
     "defect_escape_rate_pct", "≤"),
    ("M-008", "KG 需求覆盖率", "kg_coverage_pct", "%",
     "kg_coverage_pct", "≥"),
)

_DATA_SOURCES = {
    "misra_total_violations": MISRA_TREND_FILE,
    "misra_required_violations": MISRA_TREND_FILE,
    "c_line_coverage_pct": COVERAGE_TREND_FILE,
    "python_line_coverage_pct": COVERAGE_TREND_FILE,
    "build_success_rate": PROCESS_KPI_FILE,
    "regression_trigger_rate": PROCESS_KPI_FILE,
    "defect_escape_rate": DEFECT_ESCAPE_FILE,
    "kg_coverage_pct": ".yuleosh/knowledge_graph.db",
}


def _cell(text: object) -> str:
    return " ".join(str(text).replace("|", "\\|").split())


def _write_doc(session: PipelineSession, rel_path: str, content: str) -> Path:
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _has_data(project_dir: str, metric: str) -> bool:
    """原始数据文件是否存在且非空。

    ``kpi_status()`` 在缺失数据时会回退到 0 并给出 PASS（例如无 MISRA 报告时
    "0 违规 PASS"）。MAN.6 要求如实反映采集情况，故此处以原始文件是否存在
    为准；面板值在无数据时一律不采信。
    """
    rel = _DATA_SOURCES.get(metric)
    if not rel:
        return False
    path = Path(project_dir) / rel
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _load_dashboard(project_dir: str) -> dict:
    """调用既有 KPI 面板；任何异常都降级为「无数据」而不是中断流水线。"""
    try:
        raw = kpi_status(project_dir, as_json=True)
        data = json.loads(raw)
    except (TypeError, ValueError, OSError) as exc:
        log.warning("[MAN.6] KPI 面板不可用，按无数据处理: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


def _build_plan() -> str:
    rows = []
    for mid, name, metric, unit, thr_key, direction in INDICATORS:
        threshold = DEFAULT_THRESHOLDS.get(thr_key, "—")
        rows.append(
            f"| {mid} | {name} | `{_DATA_SOURCES.get(metric, '—')}` | 每次流水线 | "
            f"{direction} {threshold} {unit} |"
        )
    return (
        "# 测量计划 (MAN.6)\n\n"
        "## 测量目标\n\n"
        "- 以可量化指标评价过程与产品质量，支撑管理决策。\n"
        "- 度量项与阈值复用 `ci.kpi` 的单一事实来源，避免文档与代码漂移。\n"
        "- 每个度量项都必须能追溯到具体数据文件与采集时点。\n\n"
        "## 度量项定义\n\n"
        "| 度量ID | 度量项 | 数据来源 | 采集频率 | 阈值与判据 |\n"
        "|:-------|:-------|:---------|:---------|:-----------|\n"
        + "\n".join(rows) + "\n\n"
        "## 测量规程\n\n"
        "- **采集**：由流水线在对应步骤产出后写入 `.yuleosh/reports/`，不手工补数。\n"
        "- **存储**：原始数据保留在项目内，测量报告只做汇总与判定。\n"
        "- **分析**：PASS/FAIL 由阈值判定；无数据项标注「无数据」，不得推断。\n"
        "- **通报与措施**：FAIL 项须在测量报告中给出原因分析与纠正措施。\n\n"
        "## 可追溯性\n\n"
        "- 度量项 ↔ 阈值: `ci.kpi.kpi_state.DEFAULT_THRESHOLDS`。\n"
        "- 度量项 ↔ 数据文件: 见「度量项定义」表的数据来源列。\n"
        "- 测量结果支撑 MAN.3 项目管理与 MAN.5 风险管理决策。\n"
    )


def _build_report(dashboard: dict, project_dir: str) -> tuple[str, dict[str, int]]:
    entries = dashboard.get("entries") or []
    by_metric = {
        str(e.get("metric", "")): e
        for e in entries
        if isinstance(e, dict) and e.get("metric")
    }
    counts = {"PASS": 0, "FAIL": 0, "NO_DATA": 0}
    rows: list[str] = []
    failed: list[str] = []

    for mid, name, metric, unit, thr_key, direction in INDICATORS:
        entry = by_metric.get(metric)
        if entry is None or not _has_data(project_dir, metric):
            counts["NO_DATA"] += 1
            rows.append(f"| {mid} | {name} | — | — | — 无数据 |")
            continue
        value = entry.get("value", "—")
        threshold = entry.get("threshold", DEFAULT_THRESHOLDS.get(thr_key, "—"))
        status = str(entry.get("status", "")).upper()
        if status not in ("PASS", "FAIL"):
            counts["NO_DATA"] += 1
            rows.append(f"| {mid} | {name} | {_cell(value)} {unit} | "
                        f"{direction} {_cell(threshold)} {unit} | — 无判定 |")
            continue
        counts[status] += 1
        icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
        if status == "FAIL":
            failed.append(f"{mid} {name}")
        rows.append(
            f"| {mid} | {name} | {_cell(value)} {unit} | "
            f"{direction} {_cell(threshold)} {unit} | {icon} |"
        )

    total = sum(counts.values())
    summary = (
        f"共 {total} 个度量项：✅ {counts['PASS']} / ❌ {counts['FAIL']} / "
        f"— {counts['NO_DATA']} 无数据。"
    )
    if counts["NO_DATA"]:
        summary += (
            "\n\n> ⚠️ 存在无数据度量项：对应数据文件尚未产出，"
            "本报告不对其做任何通过性推断。"
        )

    if failed:
        analysis = (
            "## 数据分析\n\n"
            "- 超阈值度量项：" + "、".join(failed) + "。\n"
            "- 需在纠正措施中给出根因、责任人与期限；下一周期复测。\n"
        )
        actions = (
            "## 纠正措施\n\n"
            "| 度量ID | 措施 | 责任人 | 期限 | 状态 |\n"
            "|:-------|:-----|:-------|:-----|:-----|\n"
            + "\n".join(f"| {f.split(' ')[0]} | 待制定 | 待指定 | 待定 | 未开始 |"
                        for f in failed) + "\n"
        )
    else:
        analysis = (
            "## 数据分析\n\n"
            "- 无超阈值度量项；未采集数据的项不参与结论。\n"
        )
        actions = (
            "## 纠正措施\n\n"
            "> 当前无 FAIL 项，无需纠正措施。\n"
        )

    trend = dashboard.get("trend_28d") or {}
    trend_lines = []
    for key, label in (("misra", "MISRA"), ("coverage", "覆盖率")):
        if isinstance(trend.get(key), dict) and trend[key]:
            pairs = ", ".join(f"{k}={v}" for k, v in sorted(trend[key].items())[:3])
            trend_lines.append(f"- {label} 28 天趋势均值: {_cell(pairs)}。")
    trend_section = (
        "## 趋势\n\n" + "\n".join(trend_lines) + "\n"
        if trend_lines else
        "## 趋势\n\n> 无历史数据，无法计算趋势。\n"
    )

    report = (
        "# 测量报告 (MAN.6)\n\n"
        "## 概述\n\n"
        f"本报告基于 `kpi_status()` 的真实数据汇总，采集时点 "
        f"`{_cell(dashboard.get('timestamp', '—'))}`。\n\n"
        f"{summary}\n\n"
        "## 测量结果\n\n"
        "| 度量ID | 度量项 | 实测值 | 阈值 | 判定 |\n"
        "|:-------|:-------|:-------|:-----|:-----|\n"
        + "\n".join(rows) + "\n\n"
        f"{analysis}\n"
        f"{trend_section}\n"
        f"{actions}\n"
        "## 可追溯性\n\n"
        "- 度量项定义见 `docs/measurement-plan.md`。\n"
        "- 数据源文件路径见测量计划「度量项定义」表。\n"
        "- 测量结论供 MAN.3 项目管理与 MAN.5 风险管理使用。\n"
    )
    return report, counts


def step_measurement(session: PipelineSession) -> str:
    """MAN.6 — 生成测量计划，并按真实 KPI 数据汇总测量报告。"""
    plan_path = _write_doc(session, MEASUREMENT_PLAN, _build_plan())

    dashboard = _load_dashboard(session.project_dir)
    report, counts = _build_report(dashboard, session.project_dir)
    report_path = _write_doc(session, MEASUREMENT_REPORT, report)

    _write_step_marker(
        session, "measurement",
        status="completed",
        plan=MEASUREMENT_PLAN,
        report=MEASUREMENT_REPORT,
        pass_count=counts["PASS"],
        fail_count=counts["FAIL"],
        no_data_count=counts["NO_DATA"],
    )
    log.info(
        "[MAN.6] 测量计划/报告已生成: %s, %s (pass=%d, fail=%d, no_data=%d)",
        plan_path, report_path,
        counts["PASS"], counts["FAIL"], counts["NO_DATA"],
    )
    return str(report_path)


def step_review_measurement(session: PipelineSession) -> str:
    """MAN.6 测量评审（确定性门禁）。

    只校验计划/报告的结构完整性；不对「无数据」做通过性推断。
    """
    problems: list[str] = []
    for rel_path, sections in (
        (MEASUREMENT_PLAN, _PLAN_SECTIONS),
        (MEASUREMENT_REPORT, _REPORT_SECTIONS),
    ):
        target = Path(session.project_dir) / rel_path
        if not target.is_file():
            problems.append(f"缺少产物 {rel_path}")
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        for sec in sections:
            if sec not in text:
                problems.append(f"{rel_path} 缺少章节 {sec}")
    if problems:
        raise PipelineStepError(
            "MAN.6 测量门禁 RED：" + "；".join(problems)
        )
    _write_step_marker(
        session, "measurement-review",
        status="completed",
        verified=[MEASUREMENT_PLAN, MEASUREMENT_REPORT],
    )
    return str(Path(session.project_dir) / MEASUREMENT_REPORT)
