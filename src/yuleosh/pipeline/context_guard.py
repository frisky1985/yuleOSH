#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Context Guard — 上下文安全强制化 + 语义溢出兜底（第九轮决策 9.3, 2026-08-19）。

背景（老板追问多 agent 协同上下文膨胀/语义溢出对策）:
  - TokenBudgetChecker 80% 硬阈值（拒绝/降级）+ SPEC 30K/artifacts 60K/
    memory 2K 截断 + max_tokens 8192 输出上限
  - 缺口: ①「上下文 >50% 主动拆分」是 prompt 建议, 无代码强制;
    ② TokenBudgetChecker 是估算（EN 3.5/CJK 1.5 chars/token）, 非真实
    tokenizer; ③ 超限策略是拒绝/降级/尾部硬截断, 无「摘要+引用式」注入。

本模块补 ①②③（执行层变动, 不新增编排层 Gate, 不改 24 步顺序）:

三档水位（运行时估算 user_prompt + system_prompt, 含 RAG/memory 注入后）:
  - ≤50% context_window → 正常注入（现状不变, mode="normal"）
  - 50%<x≤80% → 自动降级为「引用式注入」（mode="reference"）:
    超限 artifact 段落替换为
    ``(完整内容见 <session_dir>/<artifact>.json, 结论字段摘要如下: <前N字符>)``
    报告 JSON 记录 context_mode="reference" + 触发原因（不静默降质）
  - >80% → 保持 TokenBudgetChecker 拒绝/降级逻辑, 报错带
    context_mode="over_limit" 标记 + 建议（拆分任务或提高模型窗口）

局限（docstring 记录, 不阻塞本轮）:
  - token 估算复用 TokenBudgetChecker.estimate_tokens（EN 3.5 / CJK 1.5
    chars/token 启发式）, 非真实 tokenizer; 对纯 ASCII 长文本低估、对
    CJK 混合文本高估。精确计数依赖模型 tokenizer（调用时）。
  - 引用式注入是「指针 + 摘要」, 下游 LLM 若不能读文件（无工具调用
    能力）会丢失细节——外部 agent（codex/claude）有 Bash/Read 工具,
    可自主取全文; 内置步骤不触发本降级（prompt 由 handler 自己裁剪）。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from yuleosh.llm.token_budget import TokenBudgetChecker

log = logging.getLogger("pipeline.context_guard")

__all__ = [
    "CONTEXT_NORMAL",
    "CONTEXT_OVER_LIMIT",
    "CONTEXT_REFERENCE",
    "DEFAULT_CONTEXT_WINDOW",
    "ENV_WINDOW",
    "estimate_context_level",
    "reference_inject",
    "truncate_with_reference_marker",
]

CONTEXT_NORMAL = "normal"
CONTEXT_REFERENCE = "reference"
CONTEXT_OVER_LIMIT = "over_limit"

# 上下文窗口默认值（与 TokenBudgetChecker 的 pricing 兜底一致）。
DEFAULT_CONTEXT_WINDOW = 128_000
ENV_WINDOW = "YULEOSH_CONTEXT_WINDOW"

# 引用式注入的摘要长度（无结论字段的报告用前 2000 字符）。
REFERENCE_SUMMARY_LIMIT = 2000
# 触发引用式注入的段落最小长度（小段落不值得引用替换）。
REFERENCE_MIN_BLOCK = 2000

# 目标 artifact 段落标记: ```lang 代码块前的 `### <key>` 标题
_ARTIFACT_BLOCK_RE = re.compile(
    r"(?ms)^###\s+(?P<key>[A-Za-z0-9_.-]+)\s*\n```[^\n]*\n(?P<body>.*?)```"
)


def _context_window() -> int:
    """Resolve the context window (env override or default)."""
    raw = os.environ.get(ENV_WINDOW, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_CONTEXT_WINDOW


def estimate_context_level(system_prompt: str, user_prompt: str,
                           context_window: int | None = None) -> dict:
    """Estimate the context water level of a prompt pair.

    Parameters
    ----------
    system_prompt : str
        Effective system prompt (including agent constraints + knowledge
        injection).
    user_prompt : str
        User prompt.
    context_window : int, optional
        Model context window; defaults to ``DEFAULT_CONTEXT_WINDOW``
        (env ``YULEOSH_CONTEXT_WINDOW`` overrides).

    Returns
    -------
    dict
        ``{mode, estimated_tokens, context_window, ratio, reason}`` where
        mode is one of ``normal`` / ``reference`` / ``over_limit``.
    """
    window = context_window or _context_window()
    tokens = TokenBudgetChecker.estimate_tokens(
        (system_prompt or "") + "\n" + (user_prompt or "")
    )
    ratio = tokens / window if window else 0.0

    if ratio <= 0.5:
        return {
            "mode": CONTEXT_NORMAL,
            "estimated_tokens": tokens,
            "context_window": window,
            "ratio": round(ratio, 3),
            "reason": "within 50% of context window — normal injection",
        }
    if ratio <= 0.8:
        return {
            "mode": CONTEXT_REFERENCE,
            "estimated_tokens": tokens,
            "context_window": window,
            "ratio": round(ratio, 3),
            "reason": (
                f"estimated {tokens} tokens = {ratio:.0%} of {window} — "
                ">50% → reference injection (artifact blocks replaced by "
                "pointer + summary)"
            ),
        }
    return {
        "mode": CONTEXT_OVER_LIMIT,
        "estimated_tokens": tokens,
        "context_window": window,
        "ratio": round(ratio, 3),
        "reason": (
            f"estimated {tokens} tokens = {ratio:.0%} of {window} — "
            ">80% → reject/degrade (TokenBudgetChecker) with "
            "context_mode=over_limit marker"
        ),
    }


def reference_inject(text: str, session_dir: str | Path) -> tuple[str, list[dict]]:
    """Replace oversized artifact blocks with reference pointers + summaries.

    Scans the prompt text for ``### <key>```...``` blocks (the artifact
    rendering convention in external_agents.py) and replaces blocks larger
    than :data:`REFERENCE_MIN_BLOCK` with:

        (完整内容见 <session_dir>/<key>.json, 结论字段摘要如下: <前N字符>)

    The summary is the first :data:`REFERENCE_SUMMARY_LIMIT` characters of
    the block body (no conclusion-field parsing here — callers that know
    JSON conclusions use :func:`truncate_with_reference_marker`).

    Returns ``(new_text, changes)`` where changes lists replaced blocks
    ``{key, original_len, summary_len}``.
    """
    sdir = str(session_dir)
    changes: list[dict] = []

    def _replace(m: re.Match) -> str:
        key = m.group("key")
        body = m.group("body")
        if len(body) < REFERENCE_MIN_BLOCK:
            return m.group(0)
        summary = body[:REFERENCE_SUMMARY_LIMIT]
        changes.append({
            "key": key,
            "original_len": len(body),
            "summary_len": len(summary),
        })
        return (
            f"### {key}\n```\n"
            f"(完整内容见 {sdir}/{key}.json，结论字段摘要如下: {summary}...)\n"
            f"```"
        )

    new_text = _ARTIFACT_BLOCK_RE.sub(_replace, text)
    return new_text, changes


def truncate_with_reference_marker(text: str, limit: int, path: str) -> str:
    """Tail-truncate with an explicit omission marker (替代静默截断).

    Keeps the CONTRACT/TAIL sections: when the text exceeds ``limit``,
    keep the first 60% of the budget, add
    ``…[omitted N chars — 全文见 <path>]``, then keep the final 40% of the
    budget (contracts / JSON conclusion fields usually live at the tail).

    9.3.2 (2026-08-19): external_agents prompt 注入改用此函数 — 外部
    agent（codex/claude）见省略标记后可自主读文件取全文, 语义不丢失。
    """
    if len(text) <= limit:
        return text
    head_budget = int(limit * 0.6)
    tail_budget = limit - head_budget
    omitted = len(text) - head_budget - tail_budget
    if omitted <= 0:
        return text[:limit]
    marker = f"\n…[omitted {omitted} chars — 全文见 {path}]\n"
    return text[:head_budget] + marker + text[-tail_budget:]
