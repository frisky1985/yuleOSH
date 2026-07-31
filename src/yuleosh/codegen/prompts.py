#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Prompt builders for the codegen (D3) flow.

``build_codegen_prompt`` assembles the spec + architecture + PRD context and
splices in requested skills via :func:`yuleosh.skills.prompt.render_skills`.
"""

from __future__ import annotations

from typing import Optional

from yuleosh.skills.prompt import render_skills

# Skills applied by default when none are requested explicitly.
DEFAULT_CODEGEN_SKILLS = ["autosar-coding"]


def build_codegen_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str = "",
    prd_content: str = "",
    super_analysis_content: str = "",
    skills: Optional[list[str]] = None,
    target_language: Optional[str] = None,
) -> tuple[str, str]:
    """Build ``(system_prompt, user_prompt)`` for code generation.

    The model is asked to emit every file with a ``### FILE: <path>`` marker
    followed by a fenced code block, so the output is machine-parseable by
    :func:`yuleosh.codegen.engine.parse_generated_files`.
    """
    if skills is None:
        skills = DEFAULT_CODEGEN_SKILLS
    skills_block = render_skills(skills)

    lang_hint = f"  - 目标语言: **{target_language}**" if target_language else ""

    system_prompt = (
        "You are a senior embedded software engineer implementing code from "
        "a specification, PRD, and architecture document.\n"
        "You produce **complete, compilable code files** — not plans.\n\n"
        "Output format (strict):\n"
        "1. For every file emit exactly:\n"
        "   ```\n"
        "   ### FILE: <relative/path/from/project/root>\n"
        "   ```\n"
        "   followed immediately by a fenced code block with the file's "
        "language and full content.\n"
        "2. Output ALL files in one response. Do not add prose between files.\n"
        "3. Code must be syntactically valid: Python files compile under "
        "`py_compile`; C files pass `gcc -fsyntax-only`.\n"
        "4. Follow the injected skills (coding standards, fix patterns, "
        "testing best practices) exactly.\n"
    )

    context_parts = [
        f"# Specification: {spec_name}\n```markdown\n{spec_content[:8000]}\n```"
    ]
    if architecture_content:
        context_parts.append(
            f"# Architecture\n```markdown\n{architecture_content[:5000]}\n```"
        )
    if prd_content:
        context_parts.append(
            f"# PRD\n```markdown\n{prd_content[:4000]}\n```"
        )
    if super_analysis_content:
        context_parts.append(
            f"# S.U.P.E.R Analysis\n```markdown\n{super_analysis_content[:3000]}\n```"
        )
    if skills_block:
        context_parts.append(skills_block)

    user_prompt = (
        "根据以下规范、架构与技能要求，生成完整可编译的目标代码。\n"
        f"{lang_hint}\n\n"
        + "\n\n".join(context_parts)
        + "\n\n现在生成代码。"
    )
    return system_prompt, user_prompt
