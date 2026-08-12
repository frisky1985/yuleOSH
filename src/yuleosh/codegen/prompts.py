#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Prompt builders for the codegen (D3) flow.

``build_codegen_prompt`` assembles the spec + architecture + PRD context and
splices in requested skills via :func:`yuleosh.skills.prompt.render_skills`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from yuleosh.skills.prompt import render_skills

# Skills applied by default when none are requested explicitly.
DEFAULT_CODEGEN_SKILLS = ["autosar-coding"]


def collect_existing_headers(project_dir: str | Path, max_files: int = 12) -> str:
    """收集项目既有头文件内容 (src/**/include/*.h) 作为 API 契约。

    2026-08-12: codegen 生成的代码必须实现既有 API — 否则 deploy 的
    API 契约护栏拒绝部署。返回拼接后的 markdown 块, 空项目返回 ""。
    """
    proot = Path(project_dir)
    src_dir = proot / "src"
    if not src_dir.is_dir():
        return ""
    headers = sorted(
        src_dir.rglob("*.h")
    )
    parts: list[str] = []
    for h in headers[:max_files]:
        try:
            content = h.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        rel = str(h.relative_to(proot))
        parts.append(f"### {rel}\n```c\n{content[:4000]}\n```")
    return "\n\n".join(parts)


def build_codegen_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str = "",
    prd_content: str = "",
    super_analysis_content: str = "",
    skills: Optional[list[str]] = None,
    target_language: Optional[str] = None,
    existing_headers: str = "",
) -> tuple[str, str]:
    """Build ``(system_prompt, user_prompt)`` for code generation.

    The model is asked to emit every file with a ``### FILE: <path>`` marker
    followed by a fenced code block, so the output is machine-parseable by
    :func:`yuleosh.codegen.engine.parse_generated_files`.

    existing_headers (2026-08-12): 项目既有头文件内容 (src/**/include/*.h)。
    生成的代码必须实现这些既有 API 契约 — 不得改名/改签名 — 否则
    codegen-deploy 的 API 契约护栏会拒绝部署 (生成的是新设计而非对
    既有接口的实现, 破坏测试/harness)。
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
    # 既有 API 契约 (2026-08-12): 必须实现, 不得改名/改签名
    if existing_headers:
        context_parts.append(
            "# 既有 API 契约 (必须实现)\n"
            "以下是项目既有的头文件。你生成的代码 **必须保留这些头文件的\n"
            "函数签名/类型/宏不变** — 它们被既有测试与 harness 依赖。\n"
            "头文件本身可以原样重发; .c 实现必须实现其中声明的全部函数。\n\n"
            + existing_headers
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
