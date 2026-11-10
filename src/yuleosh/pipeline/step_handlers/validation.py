"""VAL.1 产品确认（确定性）— 补齐 ASPICE 确认过程组。

设计原则与 ``sys_layer.py`` 一致：**确定性生成 + 确定性评审**，不依赖
LLM 判绿：

- 确认措施与准则自涉众需求（``STAKE-xxx``）派生；无涉众需求时降级至系统
  需求（``SYS-REQ-xxx``）并显式标注 ``source=spec-derived``，不得静默伪装。
- 确认结果**只**从 ``docs/validation-results.yaml`` 读取真实执行记录；
  文件缺失或无对应条目时如实标注 ❌ 未执行，绝不臆造"通过"结论。
- 产物路径与 ``aspice_val_v3.1.yaml`` 的 evidence 路径严格对齐
  （``docs/validation-*.md``），使 ``yuleosh compliance check --profile
  aspice_val_v3.1`` 能直接识别为 VAL.1 证据。

与 SYS.5 的边界：SYS.5 是系统层确认（工程侧、V 模型右半），VAL.1 是
产品级确认（预期使用场景、目标环境、验收判据），两者证据不互相替代。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.sys_layer import (
    _parse_stakeholder_requirements,
    _parse_sys_requirements,
)

log = logging.getLogger("pipeline.step_handlers.validation")

# ── 文档路径（与 aspice_val_v3.1.yaml evidence 路径一致）──────────────────
VALIDATION_PLAN = "docs/validation-plan.md"
VALIDATION_REPORT = "docs/validation-report.md"
VALIDATION_RESULTS = "docs/validation-results.yaml"

_PLAN_SECTIONS = ("## 确认措施与准则", "## 确认覆盖矩阵", "## 可追溯性")
_REPORT_SECTIONS = ("## 确认结果汇总", "## 可追溯性")

# 结果归一化：accept 显式通过/失败/阻塞，其余一律视为未执行（不猜测）。
_RESULT_ALIASES = {
    "pass": "PASS",
    "passed": "PASS",
    "通过": "PASS",
    "fail": "FAIL",
    "failed": "FAIL",
    "不通过": "FAIL",
    "blocked": "BLOCKED",
    "阻塞": "BLOCKED",
}


def _cell(text: str) -> str:
    """转义表格单元格内的竖线与换行，避免破坏 markdown 表格。"""
    return " ".join(str(text).replace("|", "\\|").split())


def _write_doc(session: PipelineSession, rel_path: str, content: str) -> Path:
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _write_step_marker(session: PipelineSession, step_key: str, **payload) -> None:
    """写步骤证据标记到 session 目录，供 Gate 聚合识别（<step_key>.json）。"""
    sdir = Path(session.session_dir)
    sdir.mkdir(parents=True, exist_ok=True)
    record = {"session": session.name, "step": step_key, **payload}
    (sdir / f"{step_key}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_results(project_dir: str) -> dict[str, dict[str, str]]:
    """读取 ``docs/validation-results.yaml`` → ``{VAL-xxx: {result, evidence}}``。

    格式（容错）::

        VAL-001:
          result: pass        # pass|fail|blocked（或中文）
          evidence: reports/val-001.md

    文件缺失/解析失败返回空 dict —— 调用方据此标注"未执行"，不得默认通过。
    """
    p = Path(project_dir) / VALIDATION_RESULTS
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace"))
    except (OSError, yaml.YAMLError):
        log.warning("[VAL.1] 无法解析 %s，按未执行处理", VALIDATION_RESULTS)
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        vid = str(key).strip().upper()
        if not vid:
            continue
        if isinstance(value, dict):
            out[vid] = {
                "result": str(value.get("result", "")).strip(),
                "evidence": str(value.get("evidence", "")).strip(),
            }
        elif isinstance(value, str):
            out[vid] = {"result": value.strip(), "evidence": ""}
    return out


def _normalize_result(raw: str) -> str:
    return _RESULT_ALIASES.get(raw.strip().lower(), "NOT_RUN")


def _resolve_items(session: PipelineSession) -> tuple[str, str, list[tuple[str, str]]]:
    """返回 (source, source_desc, [(需求ID, 描述)])；无需求时返回空列表。"""
    stakeholders = _parse_stakeholder_requirements(session.project_dir)
    if stakeholders:
        return (
            "stakeholder",
            "涉众需求（STAKE-xxx）",
            stakeholders,
        )
    sys_reqs = _parse_sys_requirements(Path(session.project_dir) / "docs/system-requirements.md")
    if sys_reqs:
        return (
            "spec-derived",
            "系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，"
            "产品确认针对系统需求而非用户预期（确认方向倒置）",
            [(rid, desc) for rid, desc in sys_reqs],
        )
    return "none", "无需求来源", []


def step_val_validation(session: PipelineSession) -> str:
    """VAL.1 — 生成确认计划，并按真实执行记录汇总确认报告。"""
    source, source_desc, items = _resolve_items(session)
    results = _load_results(session.project_dir)

    if items:
        criteria_rows: list[str] = []
        trace_rows: list[str] = []
        for i, (rid, desc) in enumerate(items, start=1):
            vid = f"VAL-{i:03d}"
            criteria_rows.append(
                f"| {vid} | {_cell(rid)} | 目标或等效环境 | 端到端用户场景 | "
                f"满足「{_cell(desc)}」，且无安全相关异常；判据可度量、可复核 |"
            )
            trace_rows.append(f"| {_cell(rid)} | {vid} | ✅ Planned |")
        criteria_section = (
            "## 确认措施与准则\n\n"
            "| 确认场景 | 覆盖需求 | 确认环境 | 确认方法 | 通过判据 |\n"
            "|:---------|:---------|:---------|:---------|:---------|\n"
            + "\n".join(criteria_rows) + "\n"
        )
        trace_section = (
            "## 确认覆盖矩阵\n\n"
            "| 需求 | 确认场景 | 覆盖状态 |\n"
            "|:-----|:---------|:---------|\n"
            + "\n".join(trace_rows) + "\n"
        )
        consistency = (
            "## 一致性检查\n\n"
            "- 确认准则逐条由需求派生，无孤立确认场景。\n"
            "- 确认环境与方法在计划中显式声明，未声明的结果不记为 PASS。\n"
            "- 系统层确认（SYS.5）与软件合格性证据（SWE.6）作为输入引用，"
            "不替代本过程的产品级确认结论。\n"
        )
        item_count = len(items)
    else:
        criteria_section = (
            "## 确认措施与准则\n\n"
            "> ⚠️ 未解析到任何涉众需求或系统需求，本步骤不凭空生成确认准则。\n"
        )
        trace_section = (
            "## 确认覆盖矩阵\n\n"
            "| 需求 | 确认场景 | 覆盖状态 |\n"
            "|:-----|:---------|:---------|\n"
            "| — | — | ❌ Not Covered |\n"
        )
        consistency = (
            "## 一致性检查\n\n"
            "> ❌ 无需求来源，无法建立确认准则与需求的一致性关系。\n"
        )
        item_count = 0

    plan = (
        "# 产品确认计划 (VAL.1)\n\n"
        "## 概述\n\n"
        f"本计划自{source_desc}确定性派生，共 {item_count} 条需求对应 "
        f"{item_count} 个确认场景。\n\n"
        f"> 派生来源 (机读): `{source}`\n\n"
        "## 确认策略\n\n"
        "- 在目标或等效环境下执行端到端用户场景，确认产品满足预期使用。\n"
        "- 确认结果须写入 `docs/validation-results.yaml`，并附可复核证据路径。\n"
        "- 未提供执行记录的场景一律视为未执行，不得推断为通过。\n\n"
        f"{criteria_section}\n"
        f"{trace_section}\n"
        f"{consistency}\n"
        "## 可追溯性\n\n"
        f"- 确认场景覆盖 {item_count} 条需求（来源: {source_desc}）。\n"
        "- 需求 ↔ 确认场景映射见「确认覆盖矩阵」。\n"
        "- 确认结果向上追溯至涉众需求，向下关联 SYS.5 系统确认与 SWE.6 合格性证据。\n"
    )
    plan_path = _write_doc(session, VALIDATION_PLAN, plan)

    detail_rows: list[str] = []
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "NOT_RUN": 0}
    for i, (rid, _desc) in enumerate(items, start=1):
        vid = f"VAL-{i:03d}"
        entry = results.get(vid, {})
        status = _normalize_result(entry.get("result", ""))
        evidence = entry.get("evidence", "")
        if status == "PASS" and not evidence:
            # 无证据的"通过"不可信：降级为未执行，避免假绿。
            status = "NOT_RUN"
        counts[status] += 1
        icon = {
            "PASS": "✅ PASS",
            "FAIL": "❌ FAIL",
            "BLOCKED": "⛔ BLOCKED",
            "NOT_RUN": "— 未执行",
        }[status]
        detail_rows.append(
            f"| {vid} | {_cell(rid)} | {icon} | {_cell(evidence) or '—'} |"
        )

    if items:
        summary = (
            f"共 {len(items)} 个确认场景：✅ {counts['PASS']} / "
            f"❌ {counts['FAIL']} / ⛔ {counts['BLOCKED']} / "
            f"— {counts['NOT_RUN']} 未执行。"
        )
        if counts["NOT_RUN"]:
            summary += (
                "\n\n> ⚠️ 存在未执行场景：缺少 `docs/validation-results.yaml` "
                "条目或证据路径，本报告**不**给出整体通过结论。"
            )
        detail_section = (
            "## 确认结果明细\n\n"
            "| 确认场景 | 覆盖需求 | 结果 | 证据 |\n"
            "|:---------|:---------|:-----|:-----|\n"
            + "\n".join(detail_rows) + "\n"
        )
    else:
        summary = "❌ 无需求来源，无确认场景可执行。"
        detail_section = (
            "## 确认结果明细\n\n"
            "| 确认场景 | 覆盖需求 | 结果 | 证据 |\n"
            "|:---------|:---------|:-----|:-----|\n"
            "| — | — | ❌ Not Covered | — |\n"
        )

    report = (
        "# 产品确认报告 (VAL.1)\n\n"
        "## 概述\n\n"
        f"本报告基于 `{VALIDATION_RESULTS}` 的真实执行记录汇总，"
        "不做推断性判定。\n\n"
        "## 确认结果汇总\n\n"
        f"{summary}\n\n"
        f"{detail_section}\n"
        "## 可追溯性\n\n"
        f"- 结果条目与确认场景一一对应（{item_count} 条）。\n"
        "- 确认计划: `docs/validation-plan.md`。\n"
        "- 上游需求与下游系统确认/合格性证据的映射见确认计划的追溯章节。\n"
    )
    report_path = _write_doc(session, VALIDATION_REPORT, report)
    _write_step_marker(
        session, "val-validation",
        status="completed",
        plan=VALIDATION_PLAN,
        report=VALIDATION_REPORT,
        scenarios=item_count,
        source=source,
    )

    log.info(
        "[VAL.1] 确认计划/报告已生成: %s, %s (source=%s, pass=%d, fail=%d, not_run=%d)",
        plan_path, report_path, source, counts["PASS"], counts["FAIL"], counts["NOT_RUN"],
    )
    return str(report_path)


def step_review_val(session: PipelineSession) -> str:
    """VAL.1 确认评审（确定性门禁，非 LLM 判绿）。

    校验确认计划/报告均存在且含必需章节；任一缺失即 RED，防止空模板假绿。
    注意：本门禁只校验**证据结构完整性**，不把"未执行"误判为通过 ——
    通过与否由 ``docs/validation-results.yaml`` 的真实记录决定。
    """
    problems: list[str] = []
    checks = (
        (VALIDATION_PLAN, _PLAN_SECTIONS),
        (VALIDATION_REPORT, _REPORT_SECTIONS),
    )
    for rel_path, sections in checks:
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
            "VAL.1 确认门禁 RED：" + "；".join(problems)
        )
    _write_step_marker(
        session, "val-review",
        status="completed",
        verified=[VALIDATION_PLAN, VALIDATION_REPORT],
    )
    return str(Path(session.project_dir) / VALIDATION_REPORT)
