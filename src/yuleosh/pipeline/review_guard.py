#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Review hallucination guards (2026-08-20 r22 real-4 复盘).

背景: 第四轮 (run-69f7d4ae221f) 两个 LLM 审查步骤出现系统性幻觉 —
  - internal-code-review 报 `hal_hall.c:54` 语法错误 (文件仅 53 行, 构建通过)
  - code-review 报 `window_modes.c:124` 无 (void) 抑制 (实际 137 行有)、
    `window_modes_reverse` 不返回 FAULT (实际 120-122 行有)、"0% coverage"
    (实际 66 tests passing)
根因: ① 源码注入无行号 → LLM 只能猜行号; ② prompt 无防幻觉约束;
      ③ findings 无自动验证 → 幻觉直接进 verdict 阻塞 pipeline。

三层修复:
  1. numbered_source     — 源码注入带真实行号前缀, LLM 引用的行号必须可溯源
  2. prompt 约束         — 见各 review prompt (禁止编造行号 / 未见 ≠ 缺失)
  3. validate_review_findings — file:line 存在性自动验证, 幻觉 finding
     降级为 info + hallucinated 标记, 不阻塞 pipeline; 全幻觉 critical/major
     时 status 重算为 passed 并记录 hallucination_stats。
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("pipeline.review_guard")


def dedupe_review_findings(review: dict[str, Any]) -> dict[str, Any]:
    """去重 review findings (2026-08-20 r22 real-8, code-review 重复膨胀).

    LLM 输出同一 finding 重复几十次 (run-937fecd9a2bb: 同一个 cooldown
    finding 复制 30+ 次) → 输出超长被截断 → JSON 解析失败 → 整个
    code-review 报废。解析成功后按 (file, line, snippet, message 前 80
    字符) 去重, 只保留首个; 重复计数记录到 finding 的 ``duplicate_count``。
    去重后若 status=failed 且不再有 critical/major → 重算为 passed。
    """
    findings = review.get("findings") or []
    if not findings:
        return review

    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    deduped = 0
    for f in findings:
        if not isinstance(f, dict):
            unique.append(f)
            continue
        key = (
            f.get("file", ""),
            f.get("line"),
            (f.get("snippet") or "")[:80],
            (f.get("message") or "")[:80],
        )
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        unique.append(f)

    if deduped:
        review["findings"] = unique
        review["dedupe_stats"] = {
            "removed": deduped,
            "kept": len(unique),
            "validated": True,
        }
        # 重算 breakdown
        breakdown = {"critical": 0, "major": 0, "minor": 0, "info": 0}
        for f in unique:
            sev = f.get("severity", "info")
            breakdown[sev] = breakdown.get(sev, 0) + 1
        review["finding_breakdown"] = breakdown
        # status 重算: 原 failed 但去重后无 critical/major → 通过
        orig = review.get("status")
        if orig == "failed" and breakdown["critical"] == 0 and breakdown["major"] == 0:
            review["status"] = "passed"
            review["status_recalculated"] = (
                "failed→passed: 去重后无 critical/major finding (重复膨胀)"
            )
        log.info("Review findings dedupe: removed %d duplicate(s), kept %d", deduped, len(unique))
    return review


def numbered_source(content: str) -> str:
    """给源码每行加行号前缀, 使 LLM 引用的行号必须来自真实编号。

    ``N| <code line>`` — N 为文件内真实行号 (1-based)。行号前缀本身
    不参与语义, 但截断 (引用式) 后每行仍携带真实行号, LLM 无法凭空
    编造超出文件范围的行号而不被验证层抓住。
    """
    if not content:
        return content
    lines = content.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i + 1:>{width}}| {line}" for i, line in enumerate(lines))


def _real_line_count(content: str) -> int:
    """真实源码行数 (不带行号前缀的原文)."""
    if not content:
        return 0
    return len(content.splitlines())


def validate_review_findings(
    review: dict[str, Any],
    source_files: list[dict[str, Any]],
) -> dict[str, Any]:
    """验证 review findings 的 file:line 是否指向注入源码中的真实行。

    - file 不在注入集合内            → hallucinated (file_not_found)
    - line 超出 [1, 真实行数]        → hallucinated (line_out_of_range)
    - 通过                            → 原样保留
    幻觉 finding: severity 降级为 info, 加 ``hallucinated: true`` 与
    ``hallucination_reason``。降级后若原 status=failed 且不再有
    critical/major → status 重算为 passed, 并写 hallucination_stats。

    Args:
        review: LLM 返回的 review dict (含 findings).
        source_files: 注入给 LLM 的源码列表, 每项含 path/lines/content
            (lines = 真实行数, content = 原文; 与 review prompt 注入一致).

    Returns:
        修正后的 review dict (原地修改 + 返回).
    """
    findings = review.get("findings") or []
    if not findings:
        return review

    # path → 真实行数
    line_count_by_path: dict[str, int] = {}
    content_by_path: dict[str, str] = {}
    for sf in source_files or []:
        path = sf.get("path", "")
        if not path:
            continue
        # 优先用显式 lines (读取时算好的真实行数); 缺失时从 content 现算
        line_count_by_path[path] = int(sf.get("lines") or 0) or _real_line_count(
            sf.get("content", "")
        )
        content_by_path[path] = sf.get("content", "") or ""

    hallucinated = 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        fpath = f.get("file", "")
        line = f.get("line")

        if fpath not in line_count_by_path:
            f["hallucinated"] = True
            f["hallucination_reason"] = (
                f"file '{fpath}' 不在本次注入的源码集合中 (LLM 不可见)"
            )
            hallucinated += 1
            continue

        real_lines = line_count_by_path[fpath]
        if line is not None:
            try:
                line_int = int(line)
            except (TypeError, ValueError):
                f["hallucinated"] = True
                f["hallucination_reason"] = (
                    f"line '{line}' 非整数, 无法定位 (file {fpath} 真实 {real_lines} 行)"
                )
                hallucinated += 1
                continue
            if line_int < 1 or line_int > real_lines:
                f["hallucinated"] = True
                f["hallucination_reason"] = (
                    f"line {line_int} 超出 {fpath} 真实行数范围 [1, {real_lines}]"
                )
                hallucinated += 1
                continue

            # 内容错位验证 (2026-08-20 r22 real-5): 行号有效但内容指控错误
            # (run-a97bd1d51fdf: 报 window_control.c:87 G-18 violation, 实际
            # 87 行是 IDLE cooldown; 报 202 MANUAL_RELEASE, 实际 202 是
            # PINCH_REVERSAL 分支开头)。prompt 要求 finding 带 snippet 引用
            # 真实行文本 — 若 snippet 与文件真实内容不匹配 → 幻觉。
            snippet = f.get("snippet") or ""
            if snippet:
                real_line_text = (
                    content_by_path.get(fpath, "").splitlines()[line_int - 1]
                    if content_by_path.get(fpath)
                    else ""
                )
                # 去掉行号前缀比较核心文本 (snippet 可能只引用行内容)
                norm_snippet = snippet.strip()
                norm_line = real_line_text.strip()
                # 宽松匹配: snippet 是行内容子串, 或行内容是 snippet 子串
                if norm_snippet and norm_line and norm_snippet not in norm_line \
                        and norm_line not in norm_snippet:
                    f["hallucinated"] = True
                    f["hallucination_reason"] = (
                        f"snippet 与 {fpath}:{line_int} 真实内容不匹配 "
                        f"(snippet='{norm_snippet[:60]}', 实际='{norm_line[:60]}')"
                    )
                    hallucinated += 1
                    continue

    if hallucinated:
        # 降级: 幻觉 finding 一律 info (先记录原始 severity 再降级)
        for f in findings:
            if isinstance(f, dict) and f.get("hallucinated"):
                f["severity_original"] = f.get("severity", "info")
                f["severity"] = "info"

        # 重算 breakdown
        breakdown = {"critical": 0, "major": 0, "minor": 0, "info": 0}
        for f in findings:
            if not isinstance(f, dict):
                continue
            sev = f.get("severity", "info")
            if sev in breakdown:
                breakdown[sev] += 1
            else:
                breakdown["info"] += 1
        review["finding_breakdown"] = breakdown

        # status 重算: 原 failed 但降级后无 critical/major → 视为通过
        orig_status = review.get("status")
        if orig_status == "failed" and breakdown["critical"] == 0 and breakdown["major"] == 0:
            review["status"] = "passed"
            review["status_recalculated"] = (
                "failed→passed: 全部 critical/major finding 均为幻觉, 已降级"
            )

        review["hallucination_stats"] = {
            "hallucinated_findings": hallucinated,
            "total_findings": len(findings),
            "validated": True,
        }

    return review
