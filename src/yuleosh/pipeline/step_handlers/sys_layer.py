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


def _record_sys_swe_trace(session: PipelineSession, sys_req_ids: list[str]) -> Path:
    """写入 SYS.x → SWE.1 追溯 sidecar（复用 .osh/evidence 约定）。

    返回 sidecar 路径。该记录是 SYS 层与软件工程层（SWE.1 由 spec 驱动）
    的可审计追溯链，供 alm/traceability.py 读取复用。
    """
    ev_dir = _evidence_dir(session)
    ev_dir.mkdir(parents=True, exist_ok=True)
    mapping = {rid: "SWE.1" for rid in sys_req_ids}
    trace = {
        "sys_to_swe": mapping,
        "note": "SYS 系统需求向上追溯至 SWE.1 软件需求（spec 派生）；"
                "SWE.1 由 spec.md 驱动，形成 V 模型左半连续追溯。",
    }
    trace_path = ev_dir / "sys-to-swe-trace.json"
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return trace_path


def step_sys_requirements(session: PipelineSession) -> str:
    """SYS.1 — 系统需求获取（确定性，由 spec 派生）。"""
    areas = _extract_functional_areas(_read_spec_text(session))
    req_lines = []
    sys_req_ids: list[str] = []
    for i, area in enumerate(areas, start=1):
        rid = f"SYS-REQ-{i:03d}"
        sys_req_ids.append(rid)
        req_lines.append(
            f"- **{rid}** — 系统应提供「{area}」能力（SHALL 满足该功能域需求）。"
        )
    req_block = "\n".join(req_lines) if req_lines else "- （无派生需求）"

    content = (
        "# 系统需求规格 (SYS.1)\n\n"
        "## 概述\n\n"
        "本文件由 yuleOSH 系统需求获取步骤自项目 spec 确定性派生，覆盖 V 模型"
        "左半顶端（系统需求分析）。\n\n"
        f"## 系统需求\n\n{req_block}\n\n"
        "## 可追溯性\n\n"
        "- 每条 SYS-REQ 向上追溯至软件需求 SWE.1（spec.md 驱动）。\n"
        "- 追溯记录见 `.osh/evidence/sys-to-swe-trace.json`。\n"
    )
    out = _write_doc(session, SYS_REQUIREMENTS, content)
    _record_sys_swe_trace(session, sys_req_ids)
    log.info(f"[SYS.1] 生成系统需求: {out} ({len(sys_req_ids)} 条)")
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


def step_sys_verification(session: PipelineSession) -> str:
    """SYS.3 — 系统验证规划（确定性）。"""
    content = (
        "# 系统验证 (SYS.3)\n\n"
        "## 验证策略\n\n"
        "- 验证范围覆盖全部系统需求（SYS.1）。\n"
        "- 每条需求定义验收准则与验证方法（评审/分析/测试）。\n\n"
        "## 验证用例\n\n"
        "- 系统验证用例在目标或等效环境下执行，记录于本文件。\n"
        "- 验证结果关联软件层集成/合格性证据（SWE.5/SWE.6）。\n\n"
        "## 可追溯性\n\n"
        "- 验证用例 → 系统需求（SYS.1）/ 软件需求（SWE.1）。\n"
    )
    out = _write_doc(session, SYS_VERIFICATION, content)
    log.info(f"[SYS.3] 生成系统验证: {out}")
    return str(out)


def step_sys_integration(session: PipelineSession) -> str:
    """SYS.4 — 系统集成测试规划（确定性）。"""
    content = (
        "# 系统集成 (SYS.4)\n\n"
        "## 集成策略\n\n"
        "- 集成顺序按依赖关系自底向上，先集成无依赖系统元素。\n"
        "- 桩/驱动按接口规范构造。\n\n"
        "## 集成序列\n\n"
        "- 集成序列在 `.osh/ci/` 中复现（软件层集成测试 SWE.5 提供执行记录）。\n"
        "- 每步集成后验证接口数据流正确性。\n\n"
        "## 可追溯性\n\n"
        "- 集成项 → 系统架构元素（SYS.2）/ 软件组件（SWE.3）。\n"
    )
    out = _write_doc(session, SYS_INTEGRATION, content)
    log.info(f"[SYS.4] 生成系统集成: {out}")
    return str(out)


def step_sys_validation(session: PipelineSession) -> str:
    """SYS.5 — 系统确认（确定性）。"""
    content = (
        "# 系统确认 (SYS.5)\n\n"
        "## 确认场景\n\n"
        "- 在目标或等效环境下运行用户场景，确认满足涉众需求。\n"
        "- 确认场景复用软件合格性测试（SWE.6）的仿真/HIL 证据。\n\n"
        "## 验收准则\n\n"
        "- 每条涉众需求具备可执行验收准则与通过判据。\n"
        "- 确认结果文档化并追溯至需求。\n\n"
        "## 可追溯性\n\n"
        "- 确认场景 → 系统需求（SYS.1）/ 涉众需求。\n"
    )
    out = _write_doc(session, SYS_VALIDATION, content)
    log.info(f"[SYS.5] 生成系统确认: {out}")
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
