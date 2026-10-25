#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""OpenSpec spec generator — natural language / prompt → spec draft.

Two input modes share one LLM + knowledge-injection + self-validation path:

* ``extract``   — user prompt / description → distilled OpenSpec requirements
                  (augmented with the project's RAG + active knowledge)
* ``decompose`` — an existing spec document → broken into executable
                  requirements with explicit SHALL statements and GWT scenarios

The generated markdown is written to ``spec.draft.md`` (never overwrites the
live ``spec.md``) and immediately re-parsed with :func:`spec.validate.parse_spec`
/ :func:`validate_spec` so the caller gets a structured validation report
instead of an opaque string.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.stages import _call_llm
from yuleosh.spec.validate import parse_spec, validate_spec

log = logging.getLogger("yuleosh.spec.generator")

__all__ = ["generate_spec", "SpecGenerationError"]


class SpecGenerationError(RuntimeError):
    """Raised when spec generation fails (LLM error / empty output / IO)."""


# ── Prompt contract ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位 ASPICE SWE.1 软件需求分析师。
你的任务是把用户输入转化为一份符合 OpenSpec 规范的需求规格文档（spec.md）。

输出格式规范（必须严格遵守）：
1. 每个需求用二级/三级标题开头，格式为：
   `## RS-001: 需求标题`（系统需求）或
   `## SWR-001.1: 需求标题`（软件需求，支持 .N 层级）
2. 每个需求块内必须包含至少一条强约束：
   `- The system SHALL <可测试的行为>`
   可选补充：`- The system SHOULD ...` / `- The system MAY ...`
3. 可选验收场景：
   `## Scenario: <场景名>` 下用
   `- GIVEN <前置条件>` / `- WHEN <触发动作>` / `- THEN <可验证结果>`
4. 需求 ID 必须唯一、按层级递增；不得编造输入或知识库中不存在的约束
5. 若引用了知识库中的事实，在需求正文末尾用 `<!-- source: ... -->` 标注来源

只输出 markdown 格式的 spec 正文，不要包含解释、前言或代码围栏说明。"""


def _build_user_prompt(input_text: str, mode: str) -> str:
    if mode == "decompose":
        return (
            "请将以下已有规范拆解为可执行的 OpenSpec 需求：\n"
            "— 保留原有需求 ID 与层级关系；\n"
            "— 为每条需求补全 SHALL 语句（RFC 2119 强约束）；\n"
            "— 为关键需求补充 GIVEN/WHEN/THEN 验收场景。\n\n"
            f"{input_text}"
        )
    return (
        "请基于以下描述（并结合已注入的项目知识库内容），\n"
        "提炼为可执行的 OpenSpec 需求规格。\n\n"
        f"{input_text}"
    )


def _strip_code_fence(text: str) -> str:
    """Remove a surrounding ```markdown ... ``` fence if present."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


# ── Public API ──────────────────────────────────────────────────────────

def generate_spec(
    input_text: str,
    project_dir: str | Path,
    output_path: str | Path,
    *,
    mode: str = "extract",
    auto: bool = False,
    llm_client=None,
    max_tokens: int = 8192,
) -> dict:
    """Generate an OpenSpec spec.

    Args:
        input_text: The raw input (free-form description or existing spec).
        project_dir: Project root — used for RAG + active-knowledge injection.
        output_path: Target path. In ``auto`` mode this is the *formal* spec
            (e.g. ``spec.md``); otherwise it is the draft path.
        mode: ``"extract"`` (default) or ``"decompose"``.
        auto: When ``True``, write directly to ``output_path`` (the formal
            spec) **only if** the generated content passes OpenSpec self-
            validation with zero errors. If validation fails, the content is
            written to ``<output>.draft.md`` instead and an error is reported —
            the formal spec is never overwritten with invalid content.
        llm_client: Optional callable(system, user) -> {"content": str} for
            testing / dependency injection. Falls back to the global
            ``pipeline.run.chat_completion``.
        max_tokens: LLM max output tokens.

    Returns:
        A dict with ``output_path`` (where the content was actually written),
        ``mode``, ``written`` (``"spec"`` | ``"draft"``) and ``validation``
        (errors, issues, requirement_count).
    """
    if mode not in ("extract", "decompose"):
        raise ValueError(f"mode must be 'extract' or 'decompose', got {mode!r}")
    if not input_text or not input_text.strip():
        raise ValueError("input_text is empty")

    project_dir = str(Path(project_dir).resolve())
    output_path = Path(output_path)
    # Draft always lives next to the target: spec.md -> spec.draft.md
    draft_path = output_path.with_name(output_path.stem + ".draft" + output_path.suffix)

    # Lightweight session — reused so _call_llm's knowledge injection
    # (RAG + active knowledge) and llm_client injection both work.
    session = PipelineSession(
        name="spec-generate",
        spec_path=str(output_path),
        llm_client=llm_client,
    )
    session.project_dir = project_dir
    session.pipeline_knowledge_step_key = "spec-generate"

    user_prompt = _build_user_prompt(input_text.strip(), mode)
    try:
        result = _call_llm(session, _SYSTEM_PROMPT, user_prompt, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001 — surface as typed error
        raise SpecGenerationError(f"LLM call failed: {e}") from e

    content = (result or {}).get("content", "").strip()
    if not content:
        raise SpecGenerationError("LLM returned empty content")
    content = _strip_code_fence(content)

    # Self-validation: parse the generated content and run the OpenSpec
    # validator *before* deciding where to write it.
    validation: dict = {"errors": [], "issues": [], "requirement_count": 0}
    try:
        # Write to a temp path for parsing without touching the target yet.
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(content, encoding="utf-8")
        doc = parse_spec(str(draft_path))
        validation["requirement_count"] = len(doc.requirements)
        issues = validate_spec(doc)
        validation["issues"] = issues
        validation["errors"] = [
            i for i in issues if str(i.get("severity", "")).upper() == "ERROR"
        ]
    except Exception as e:  # noqa: BLE001 — validation failure is non-fatal
        log.warning("Spec self-validation failed: %s", e)
        validation["errors"] = [f"validation exception: {e}"]

    # A spec with zero parseable requirements is invalid regardless of what
    # the validator reports — surface it as an ERROR so callers/auto mode
    # can act on it.
    if validation["requirement_count"] == 0 and not any(
        isinstance(e, dict) and "no parseable requirements" in str(e.get("message", ""))
        for e in validation["errors"]
    ):
        validation["errors"].append(
            {"severity": "ERROR", "message": "no parseable requirements found in generated content"}
        )

    errors = validation["errors"]
    has_requirements = validation["requirement_count"] > 0

    # Safety gate: in auto mode only commit to the formal spec when clean
    # (no validation errors AND at least one parsed requirement — a spec
    # with zero requirements is invalid even if the validator is silent).
    if auto and not errors and has_requirements:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
        except OSError as e:
            raise SpecGenerationError(f"Cannot write spec to {output_path}: {e}") from e
        draft_path.unlink(missing_ok=True)
        log.info(
            "Spec written to %s (%d chars, mode=%s, auto)",
            output_path, len(content), mode,
        )
        return {
            "output_path": str(output_path),
            "mode": mode,
            "written": "spec",
            "validation": validation,
        }

    # Draft path (non-auto, or auto with validation errors).
    log.info(
        "Spec draft written to %s (%d chars, mode=%s, auto=%s, errors=%d)",
        draft_path, len(content), mode, auto, len(errors),
    )
    return {
        "output_path": str(draft_path),
        "mode": mode,
        "written": "draft",
        "validation": validation,
    }
