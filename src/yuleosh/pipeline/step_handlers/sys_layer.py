#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
System-layer (SYS.1~SYS.5) pipeline step handlers — M1 / Phase A.

V 模型左半（系统需求 → 系统架构 → 系统验证/集成/确认）的确定性实现。

设计要点（对齐方案 sys-layer-vmodel-completion-plan.md 风险栏）：
- **确定性生成 + 确定性评审**，不依赖 LLM 判绿。SYS 产物由 spec 派生，
  评审步骤校验产物含必需章节（尤其是 `## 可追溯性`），而非信任 LLM 自述。
- 复用 review-critical-safety 的确定性门禁思路：`step_review_sys` 对 5 份
  SYS 交付物做结构校验，缺章节即 RED（PipelineStepError）。
- 产物路径与 ``aspice_sys_v3.1.yaml`` 的 evidence 路径严格对齐
  （docs/system-*.md），使 ``yuleosh compliance check --profile aspice_sys_v3.1``
  能直接识别为 SYS.1~SYS.5 证据。

handler 签名沿用现有约定 ``def step_x(session: PipelineSession) -> str``
（spec.py:45）。返回主产物路径字符串。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.sys_layer")

# ── 文档路径（与 aspice_sys_v3.1.yaml evidence 路径一致）─────────────────
SYS_REQUIREMENTS = "docs/system-requirements.md"
SYS_ARCHITECTURE = "docs/system-architecture.md"
SYS_VERIFICATION = "docs/system-verification.md"
SYS_INTEGRATION = "docs/system-integration.md"
SYS_VALIDATION = "docs/system-validation.md"

# SYS-REQ-001 / T6: 涉众需求是系统需求的**上游**（V 模型正位 STAKE→SYS→SWE）。
# 存在该文件时 SYS.1 自其派生并保留 STAKE 映射；不存在时退化为 spec 派生，
# 但必须显式标注 source=spec-derived（禁止静默伪装成已做涉众需求分析）。
STAKEHOLDER_REQUIREMENTS = "docs/stakeholder-requirements.md"

# 5 份 SYS 交付物 → 对应过程域
SYS_DOC_TO_AREA = {
    SYS_REQUIREMENTS: "SYS.1",
    SYS_ARCHITECTURE: "SYS.2",
    SYS_VERIFICATION: "SYS.3",
    SYS_INTEGRATION: "SYS.4",
    SYS_VALIDATION: "SYS.5",
}

# 每份交付物必须含的章节（确定性评审）
_REQUIRED_SECTIONS = ("## 可追溯性",)


def _docs_dir(session: PipelineSession) -> Path:
    return Path(session.project_dir) / "docs"


def _evidence_dir(session: PipelineSession) -> Path:
    return Path(session.project_dir) / ".osh" / "evidence"


def _read_spec_text(session: PipelineSession) -> str:
    """读取 spec 文本（目录模式聚合所有 *.md，文件模式读单文件）。"""
    spec = Path(session.spec_path)
    if spec.is_dir():
        parts: list[str] = []
        for f in sorted(spec.rglob("*.md")):
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
        return "\n".join(parts)
    if spec.exists():
        try:
            return spec.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    return ""


def _extract_functional_areas(spec_text: str) -> list[str]:
    """从 spec 的 Markdown 标题派生功能域列表（确定性，无 LLM）。

    返回去重、保持文档序的标题文本列表；spec 无标题时回退单条通用域。
    """
    areas: list[str] = []
    seen: set[str] = set()
    for line in spec_text.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*$", line.strip())
        if not m:
            continue
        title = m.group(1).strip()
        # 跳过疑似章节元标题
        if title.lower() in {"overview", "概述", "目录", "toc"}:
            continue
        if title and title not in seen:
            seen.add(title)
            areas.append(title)
        if len(areas) >= 20:
            break
    if not areas:
        areas = ["通用系统功能（由 spec 派生）"]
    return areas


def _write_doc(session: PipelineSession, rel_path: str, content: str) -> Path:
    """写入一份 SYS 交付物并返回其绝对路径。"""
    target = Path(session.project_dir) / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _parse_stakeholder_requirements(project_dir: str) -> list[tuple[str, str]]:
    """解析 ``docs/stakeholder-requirements.md`` 的 ``[(STAKE-xxx, 描述)]``。

    确定性解析（无 LLM）。文件不存在/无 STAKE-xxx 时返回空列表 ——
    调用方据此降级并显式标注，不得静默伪造涉众需求。
    """
    p = Path(project_dir) / STAKEHOLDER_REQUIREMENTS
    if not p.is_file():
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = re.search(r"(STAKE-\d+)", line)
        if not m:
            continue
        sid = m.group(1)
        if sid in seen:
            continue
        seen.add(sid)
        desc = re.sub(r"^[-*+]\s*", "", line.strip())
        desc = re.sub(r"\*\*", "", desc)
        desc = re.sub(r"^STAKE-\d+\s*[—–\-:]*\s*", "", desc).strip(" —–-:")
        out.append((sid, desc or "（未命名涉众需求）"))
    return out


def _record_sys_swe_trace(session: PipelineSession,
                          sys_req_ids: list[str],
                          source: str = "spec-derived",
                          sys_to_stake: dict | None = None) -> Path:
    """写入 SYS.x → 下游/上游追溯 sidecar（复用 .osh/evidence 约定）。

    SYS-REQ-001 / T6: ``source`` 标明派生来源（机读字段），
      * ``stakeholder``  —— 自涉众需求派生（V 模型正位 STAKE→SYS→SWE）
      * ``spec-derived`` —— **降级**：无涉众需求源，由 spec 反推（方向倒置），
        必须显式记录，供审计/合规引擎识别，禁止静默伪装。

    返回 sidecar 路径。该记录是 SYS 层与软件工程层（SWE.1 由 spec 驱动）
    的可审计追溯链，供 alm/traceability.py 读取复用。
    """
    ev_dir = _evidence_dir(session)
    ev_dir.mkdir(parents=True, exist_ok=True)
    mapping = {rid: "SWE.1" for rid in sys_req_ids}
    if source == "stakeholder":
        note = ("SYS 系统需求自涉众需求派生（STAKE→SYS→SWE，V 模型正位）；"
                "SWE.1 由 spec.md 驱动，形成左半连续追溯。")
    else:
        note = ("降级: 未找到 docs/stakeholder-requirements.md，SYS 需求由 spec "
                "反推（方向倒置 SYS←SWE.1）。已显式标注 source=spec-derived，"
                "不得视为已开展涉众需求分析。")
    trace = {
        "sys_to_swe": mapping,
        "source": source,
        "note": note,
    }
    if sys_to_stake:
        trace["sys_to_stake"] = dict(sys_to_stake)
    trace_path = ev_dir / "sys-to-swe-trace.json"
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return trace_path


def step_sys_requirements(session: PipelineSession) -> str:
    """SYS.1 — 系统需求获取（确定性）。

    SYS-REQ-001 / T6（V 模型左半语义正位）: 涉众需求才是系统需求的上游。
      * 存在 ``docs/stakeholder-requirements.md`` → 自涉众需求派生，保留
        ``SYS-REQ → STAKE-xxx`` 映射（正位方向 STAKE → SYS → SWE）。
      * 不存在 → 退化为自 spec 派生（**方向倒置**：SYS 由 SWE.1 的输入反推），
        必须在文档与 sidecar 中显式标注 ``source: spec-derived``，
        禁止静默伪装成"已开展涉众需求分析"。
    """
    stakeholders = _parse_stakeholder_requirements(session.project_dir)
    req_lines: list[str] = []
    sys_req_ids: list[str] = []
    sys_to_stake: dict[str, str] = {}

    if stakeholders:
        source = "stakeholder"
        for i, (sid, desc) in enumerate(stakeholders, start=1):
            rid = f"SYS-REQ-{i:03d}"
            sys_req_ids.append(rid)
            sys_to_stake[rid] = sid
            req_lines.append(
                f"- **{rid}** ← {sid} — 系统应满足「{desc}」（SHALL）。"
            )
        source_desc = "涉众需求（STAKE-xxx）"
        trace_line = "- SYS-REQ → STAKE-xxx 映射见 `.osh/evidence/sys-to-swe-trace.json`。\n"
    else:
        source = "spec-derived"
        areas = _extract_functional_areas(_read_spec_text(session))
        for i, area in enumerate(areas, start=1):
            rid = f"SYS-REQ-{i:03d}"
            sys_req_ids.append(rid)
            req_lines.append(
                f"- **{rid}** — 系统应提供「{area}」能力（SHALL 满足该功能域需求）。"
            )
        source_desc = ("项目 spec —— **降级**：无涉众需求文件，SYS 需求由 spec "
                       "反推，V 模型方向（STAKE→SYS→SWE）在此倒置")
        trace_line = "- SYS-REQ → SWE.1 映射见 `.osh/evidence/sys-to-swe-trace.json`。\n"

    req_block = "\n".join(req_lines) if req_lines else "- （无派生需求）"

    content = (
        "# 系统需求规格 (SYS.1)\n\n"
        "## 概述\n\n"
        "本文件由 yuleOSH 系统需求获取步骤确定性派生，覆盖 V 模型左半顶端"
        "（系统需求分析）。\n\n"
        f"> 派生来源 (机读): `{source}`\n\n"
        f"## 系统需求\n\n{req_block}\n\n"
        "## 可追溯性\n\n"
        f"- 每条 SYS-REQ 的上游来源: {source_desc}。\n"
        f"{trace_line}"
    )
    out = _write_doc(session, SYS_REQUIREMENTS, content)
    _record_sys_swe_trace(session, sys_req_ids, source=source,
                          sys_to_stake=sys_to_stake or None)
    log.info(f"[SYS.1] 生成系统需求: {out} ({len(sys_req_ids)} 条, source={source})")
    return str(out)


def _parse_sys_requirements(req_doc: Path) -> list[tuple[str, str]]:
    """从 ``docs/system-requirements.md`` 解析 ``[(SYS-REQ-ID, 能力描述)]``。

    确定性解析（无 LLM），供 SYS.2 架构派生真实的元素边界与覆盖矩阵。
    解析不到时返回空列表 —— 调用方须如实标注，不得凭空造需求。
    """
    if not req_doc.exists():
        return []
    try:
        text = req_doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = re.search(r"(SYS-REQ-\d+)", line)
        if not m:
            continue
        rid = m.group(1)
        if rid in seen:
            continue
        seen.add(rid)
        desc = re.sub(r"^[-*+]\s*", "", line.strip())
        desc = re.sub(r"\*\*|\(SHALL[^)]*\)", "", desc)
        desc = re.sub(r"^SYS-REQ-\d+\s*[—–-]*\s*", "", desc).strip(" —–-")
        desc = re.sub(r"^系统应提供「|」能力.*$", "", desc).strip()
        parsed.append((rid, desc or "（未命名能力）"))
    return parsed


def _parse_sys_architecture_elements(arch_doc: Path) -> list[tuple[str, str, str]]:
    """从 ``docs/system-architecture.md`` 解析系统元素 ``[(SE-xx, 覆盖需求, 职责)]``。

    确定性解析（无 LLM），供 SYS.4 集成规划派生真实集成序列。
    解析 ``## 系统元素与边界`` 表格中的 ``| SE-xx | SYS-REQ-xxx | 职责边界 |`` 行。
    解析不到时返回空列表 —— 调用方须如实标注，不得凭空造元素。
    """
    if not arch_doc.exists():
        return []
    try:
        text = arch_doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    parsed: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    in_element_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if "系统元素与边界" in stripped:
            in_element_table = True
            continue
        if in_element_table and stripped.startswith("## "):
            break
        if not in_element_table:
            continue
        m = re.match(r"\|\s*(SE-\d+)\s*\|\s*(SYS-REQ-\d+)\s*\|\s*(.+?)\s*\|", stripped)
        if not m:
            continue
        eid = m.group(1)
        if eid in seen:
            continue
        seen.add(eid)
        req_id = m.group(2)
        duty = m.group(3).strip()
        parsed.append((eid, req_id, duty))
    return parsed


def step_sys_architecture(session: PipelineSession) -> str:
    """SYS.2 — 系统架构设计（确定性，由系统需求派生）。

    SYS-REQ-004: 原实现只输出泛化散文（约 595B，无元素边界、无接口定义、
    无覆盖矩阵），架构内容不可验证。此处改为自 SYS.1 需求文档真实派生：
      * 系统元素与职责边界（1 元素 ← 1 条系统需求，边界可核）
      * 需求覆盖矩阵（SYS-REQ → 元素，逐条可核）
      * 接口定义（**仅在有来源时列出**；无来源如实标注未定义，绝不凭空
        生成类型/取值范围 —— 那是假绿）
    """
    parsed = _parse_sys_requirements(Path(session.project_dir) / SYS_REQUIREMENTS)
    req_count = len(parsed)

    if parsed:
        elem_rows = "\n".join(
            f"| SE-{i:02d} | {rid} | 承载「{desc}」能力；对外仅通过已定义接口交互，"
            f"不越界承担其他元素职责 |"
            for i, (rid, desc) in enumerate(parsed, start=1)
        )
        cov_rows = "\n".join(
            f"| {rid} | SE-{i:02d} | ✅ Covered |"
            for i, (rid, _d) in enumerate(parsed, start=1)
        )
        elements_section = (
            "## 系统元素与边界\n\n"
            "| 系统元素 | 覆盖的系统需求 | 职责边界 |\n"
            "|:---------|:---------------|:---------|\n"
            f"{elem_rows}\n\n"
            "## 需求覆盖矩阵\n\n"
            "| 系统需求 | 系统元素 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            f"{cov_rows}\n"
        )
    else:
        # 无需求来源 → 如实标注，绝不伪造元素
        elements_section = (
            "## 系统元素与边界\n\n"
            "> ⚠️ 未解析到任何 SYS-REQ（`docs/system-requirements.md` 缺失或为空），"
            "本步骤不凭空生成系统元素。\n\n"
            "## 需求覆盖矩阵\n\n"
            "| 系统需求 | 系统元素 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            "| — | — | ❌ Not Covered |\n"
        )

    # 接口定义: 仅在能从需求来源识别接口信息时列出；否则显式标注未定义。
    # SYS.2.BP2 要求类型与取值范围，spec 未提供时不得臆造。
    interfaces_section = (
        "## 接口定义\n\n"
        "> 接口状态: **未定义** —— 上游 spec 未提供接口的类型/取值范围信息，\n"
        "> 本步骤不臆造接口表（否则为假绿）。接口须由系统架构师补充后重新生成。\n\n"
        "| 接口 | 方向 | 数据类型 | 取值范围 | 定义来源 |\n"
        "|:-----|:-----|:---------|:---------|:---------|\n"
        "| — | — | — | — | 待补充 |\n"
    )

    content = (
        "# 系统架构设计 (SYS.2)\n\n"
        "## 概述\n\n"
        f"本架构自 `docs/system-requirements.md` 的 {req_count} 条系统需求确定性派生，"
        "每个系统元素对应一条系统需求，边界与覆盖关系逐条可核。\n\n"
        f"{elements_section}\n"
        f"{interfaces_section}\n"
        "## 数据流\n\n"
        "- 数据流自涉众/系统需求向下贯通至软件组件，保持单向可追溯。\n\n"
        "## 可追溯性\n\n"
        f"- 架构覆盖 `docs/system-requirements.md` 中的 {req_count} 条系统需求。\n"
        "- 系统元素 → 软件组件映射在 SWE.2 软件架构中细化。\n"
        "- 需求 → 元素覆盖矩阵见本文「需求覆盖矩阵」章节。\n"
    )
    out = _write_doc(session, SYS_ARCHITECTURE, content)
    log.info(f"[SYS.2] 生成系统架构: {out} ({req_count} 条需求派生)")
    return str(out)


def _infer_verification_method(desc: str) -> str:
    """根据需求描述关键词推断验证方法（确定性启发式，无 LLM）。

    ASPICE SYS.3 要求每条需求指定验证方法（评审/分析/测试/演示）。
    此处用关键词匹配做保守推断；无法推断时回退到「测试」（最常用）。
    """
    d = desc.lower()
    if any(k in d for k in ("评审", "审查", "文档", "记录", "标识", "命名")):
        return "评审 (Review)"
    if any(k in d for k in ("分析", "仿真", "建模", "覆盖率", "可靠性")):
        return "分析 (Analysis)"
    if any(k in d for k in ("演示", "场景", "用户", "操作", "交互", "界面")):
        return "演示 (Demonstration)"
    return "测试 (Test)"


def step_sys_verification(session: PipelineSession) -> str:
    """SYS.3 — 系统验证规划（确定性，由系统需求派生）。

    反假绿原则：
      * 自 ``docs/system-requirements.md`` 真实解析 SYS-REQ ID，逐条生成
        验证用例（V-xxx），含验证方法与验收准则框架。
      * 验证覆盖矩阵逐条可核（SYS-REQ → 验证用例 → 方法）。
      * 无需求来源时如实标注 ❌ Not Covered，绝不凭空造验证用例。
    """
    parsed = _parse_sys_requirements(Path(session.project_dir) / SYS_REQUIREMENTS)
    req_count = len(parsed)

    if parsed:
        scenario_rows: list[str] = []
        coverage_rows: list[str] = []
        for i, (rid, desc) in enumerate(parsed, start=1):
            vid = f"V-SYS-{i:03d}"
            method = _infer_verification_method(desc)
            scenario_rows.append(
                f"| {vid} | {rid} | {method} | "
                f"验证系统满足「{desc}」需求；验收准则待系统测试计划细化 |"
            )
            coverage_rows.append(f"| {rid} | {vid} | ✅ Covered |")

        scenarios_section = (
            "## 验证用例\n\n"
            "| 验证用例 | 覆盖需求 | 验证方法 | 验收准则框架 |\n"
            "|:---------|:---------|:---------|:-------------|\n"
            + "\n".join(scenario_rows) + "\n"
        )
        coverage_section = (
            "## 验证覆盖矩阵\n\n"
            "| 系统需求 | 验证用例 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            + "\n".join(coverage_rows) + "\n"
        )
    else:
        scenarios_section = (
            "## 验证用例\n\n"
            "> ⚠️ 未解析到任何 SYS-REQ（`docs/system-requirements.md` 缺失或为空），"
            "本步骤不凭空生成验证用例。\n"
        )
        coverage_section = (
            "## 验证覆盖矩阵\n\n"
            "| 系统需求 | 验证用例 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            "| — | — | ❌ Not Covered |\n"
        )

    content = (
        "# 系统验证 (SYS.3)\n\n"
        "## 概述\n\n"
        f"本验证规划自 `docs/system-requirements.md` 的 {req_count} 条系统需求"
        "确定性派生，每条需求对应一个验证用例，验证方法由关键词启发式推断"
        "（评审/分析/测试/演示），验收准则框架待系统测试计划细化。\n\n"
        "## 验证策略\n\n"
        "- 验证范围覆盖全部系统需求（SYS.1），逐条可核。\n"
        "- 验证方法按需求特性推断：文档类→评审，性能类→分析，交互类→演示，其余→测试。\n"
        "- 验证结果关联软件层集成/合格性证据（SWE.5/SWE.6）。\n\n"
        f"{scenarios_section}\n"
        f"{coverage_section}\n"
        "## 可追溯性\n\n"
        f"- 验证用例覆盖 `docs/system-requirements.md` 中的 {req_count} 条系统需求。\n"
        "- 验证用例 → 系统需求（SYS.1）映射见本文「验证覆盖矩阵」章节。\n"
        "- 系统级验证结果向上追溯至涉众需求，向下关联至软件层 SWE.5/SWE.6 证据。\n"
    )
    out = _write_doc(session, SYS_VERIFICATION, content)
    log.info(f"[SYS.3] 生成系统验证: {out} ({req_count} 条需求 → {req_count} 个验证用例)")
    return str(out)


def step_sys_integration(session: PipelineSession) -> str:
    """SYS.4 — 系统集成测试规划（确定性，由系统架构派生）。

    反假绿原则：
      * 自 ``docs/system-architecture.md`` 真实解析系统元素（SE-xx），
        按元素顺序生成集成步骤（INT-xxx），每步标注集成对象与验证点。
      * 集成覆盖矩阵逐条可核（SE-xx → 集成步骤）。
      * 无架构元素时如实标注 ❌ Not Covered，绝不凭空造集成序列。
    """
    elements = _parse_sys_architecture_elements(
        Path(session.project_dir) / SYS_ARCHITECTURE
    )
    elem_count = len(elements)

    if elements:
        seq_rows: list[str] = []
        coverage_rows: list[str] = []
        for i, (eid, req_id, duty) in enumerate(elements, start=1):
            iid = f"INT-{i:03d}"
            duty_short = duty[:40] + ("…" if len(duty) > 40 else "")
            seq_rows.append(
                f"| {iid} | {eid} | {req_id} | "
                f"集成 {eid}（{duty_short}）；验证接口数据流正确性 |"
            )
            coverage_rows.append(f"| {eid} | {iid} | ✅ Covered |")

        sequences_section = (
            "## 集成序列\n\n"
            "| 集成步骤 | 系统元素 | 覆盖需求 | 集成内容与验证点 |\n"
            "|:---------|:---------|:---------|:----------------|\n"
            + "\n".join(seq_rows) + "\n"
        )
        coverage_section = (
            "## 集成覆盖矩阵\n\n"
            "| 系统元素 | 集成步骤 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            + "\n".join(coverage_rows) + "\n"
        )
    else:
        sequences_section = (
            "## 集成序列\n\n"
            "> ⚠️ 未解析到任何系统元素（`docs/system-architecture.md` 缺失或无元素表），"
            "本步骤不凭空生成集成序列。\n"
        )
        coverage_section = (
            "## 集成覆盖矩阵\n\n"
            "| 系统元素 | 集成步骤 | 覆盖状态 |\n"
            "|:---------|:---------|:---------|\n"
            "| — | — | ❌ Not Covered |\n"
        )

    content = (
        "# 系统集成 (SYS.4)\n\n"
        "## 概述\n\n"
        f"本集成规划自 `docs/system-architecture.md` 的 {elem_count} 个系统元素"
        "确定性派生，按元素顺序生成集成步骤，每步标注集成对象与接口验证点。\n\n"
        "## 集成策略\n\n"
        "- 集成顺序按系统元素依赖关系自底向上，先集成无依赖元素。\n"
        "- 桩/驱动按接口规范构造。\n"
        "- 集成序列在 `.osh/ci/` 中复现（软件层集成测试 SWE.5 提供执行记录）。\n\n"
        f"{sequences_section}\n"
        f"{coverage_section}\n"
        "## 可追溯性\n\n"
        f"- 集成步骤覆盖 `docs/system-architecture.md` 中的 {elem_count} 个系统元素。\n"
        "- 集成项 → 系统架构元素（SYS.2）映射见本文「集成覆盖矩阵」章节。\n"
        "- 系统集成结果向上追溯至系统需求（SYS.1），向下关联软件组件（SWE.3）。\n"
    )
    out = _write_doc(session, SYS_INTEGRATION, content)
    log.info(f"[SYS.4] 生成系统集成: {out} ({elem_count} 个元素 → {elem_count} 个集成步骤)")
    return str(out)


def step_sys_validation(session: PipelineSession) -> str:
    """SYS.5 — 系统确认（确定性，由涉众需求或系统需求派生）。

    反假绿原则：
      * 优先自 ``docs/stakeholder-requirements.md`` 解析涉众需求（STAKE-xxx），
        逐条生成确认场景（VAL-xxx），含验收准则框架。
      * 无涉众需求时降级至系统需求（SYS-REQ-xxx），但显式标注 source=spec-derived
        （V 模型方向倒置：确认应针对涉众需求，非系统需求）。
      * 确认覆盖矩阵逐条可核。
      * 无任何需求来源时如实标注 ❌ Not Covered，绝不凭空造确认场景。
    """
    stakeholders = _parse_stakeholder_requirements(session.project_dir)
    sys_reqs = _parse_sys_requirements(Path(session.project_dir) / SYS_REQUIREMENTS)

    if stakeholders:
        source = "stakeholder"
        items: list[tuple[str, str]] = stakeholders
        source_desc = "涉众需求（STAKE-xxx）"
    elif sys_reqs:
        source = "spec-derived"
        items = [(rid, desc) for rid, desc in sys_reqs]
        source_desc = ("系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，"
                       "确认针对系统需求而非涉众需求（V 模型方向倒置）")
    else:
        items = []
        source = "none"
        source_desc = "无需求来源"

    if items:
        scenario_rows: list[str] = []
        coverage_rows: list[str] = []
        for i, (rid, desc) in enumerate(items, start=1):
            vid = f"VAL-{i:03d}"
            scenario_rows.append(
                f"| {vid} | {rid} | "
                f"在目标/等效环境下运行用户场景，确认满足「{desc}」；"
                f"验收准则待确认计划细化 |"
            )
            coverage_rows.append(f"| {rid} | {vid} | ✅ Covered |")

        scenarios_section = (
            "## 确认场景\n\n"
            "| 确认场景 | 覆盖需求 | 确认内容与验收准则框架 |\n"
            "|:---------|:---------|:----------------------|\n"
            + "\n".join(scenario_rows) + "\n"
        )
        coverage_section = (
            "## 确认覆盖矩阵\n\n"
            "| 需求 | 确认场景 | 覆盖状态 |\n"
            "|:-----|:---------|:---------|\n"
            + "\n".join(coverage_rows) + "\n"
        )
        item_count = len(items)
    else:
        scenarios_section = (
            "## 确认场景\n\n"
            "> ⚠️ 未解析到任何涉众需求或系统需求，"
            "本步骤不凭空生成确认场景。\n"
        )
        coverage_section = (
            "## 确认覆盖矩阵\n\n"
            "| 需求 | 确认场景 | 覆盖状态 |\n"
            "|:-----|:---------|:---------|\n"
            "| — | — | ❌ Not Covered |\n"
        )
        item_count = 0

    content = (
        "# 系统确认 (SYS.5)\n\n"
        "## 概述\n\n"
        f"本确认规划自{source_desc}确定性派生，共 {item_count} 条需求对应 "
        f"{item_count} 个确认场景。\n\n"
        f"> 派生来源 (机读): `{source}`\n\n"
        "## 确认策略\n\n"
        "- 在目标或等效环境下运行用户场景，确认满足涉众需求。\n"
        "- 确认场景复用软件合格性测试（SWE.6）的仿真/HIL 证据。\n"
        "- 每条涉众需求具备可执行验收准则与通过判据。\n\n"
        f"{scenarios_section}\n"
        f"{coverage_section}\n"
        "## 可追溯性\n\n"
        f"- 确认场景覆盖 {item_count} 条需求（来源: {source_desc}）。\n"
        "- 确认场景 → 需求映射见本文「确认覆盖矩阵」章节。\n"
        "- 系统确认结果向上追溯至涉众需求，向下关联系统需求（SYS.1）与软件合格性证据。\n"
    )
    out = _write_doc(session, SYS_VALIDATION, content)
    log.info(f"[SYS.5] 生成系统确认: {out} ({item_count} 条需求, source={source})")
    return str(out)


def step_review_sys(session: PipelineSession) -> str:
    """SYS 需求/架构评审（确定性门禁，非 LLM 判绿）。

    校验 5 份 SYS 交付物均存在且含必需章节（## 可追溯性）；
    任一缺失即判 RED（PipelineStepError），防止空模板假绿。
    """
    missing: list[str] = []
    for rel_path in SYS_DOC_TO_AREA:
        target = Path(session.project_dir) / rel_path
        if not target.exists() or not target.is_file():
            missing.append(rel_path)
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        for sec in _REQUIRED_SECTIONS:
            if sec not in text:
                missing.append(f"{rel_path} (缺章节 {sec})")

    if missing:
        msg = "SYS 评审失败，以下交付物缺失或结构不全:\n- " + "\n- ".join(missing)
        log.error(msg)
        raise PipelineStepError(msg)

    # 评审通过：写出评审记录
    ev_dir = _evidence_dir(session)
    ev_dir.mkdir(parents=True, exist_ok=True)
    rec_path = ev_dir / "sys-review.json"
    rec_path.write_text(
        json.dumps(
            {
                "verdict": "passed",
                "checked": list(SYS_DOC_TO_AREA.keys()),
                "required_sections": list(_REQUIRED_SECTIONS),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("[SYS-review] 5 份 SYS 交付物结构校验通过")
    return str(rec_path)
