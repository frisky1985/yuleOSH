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
from yuleosh.pipeline.prompts import SPEC_INJECT_LIMIT

# Skills applied by default when none are requested explicitly.
DEFAULT_CODEGEN_SKILLS = ["autosar-coding"]

# Seed 基线限制: 最多收集的文件数与单文件字符数 (防止 prompt 超长)。
SEED_MAX_FILES = 15
SEED_MAX_CHARS = 4000
# 复制 seed 时排除的目录名 (构建产物/缓存)。
SEED_EXCLUDE_DIRS = {
    "build", "cmake-build-debug", "cmake-build-release", "cmake-build-coverage",
    "__pycache__", ".git", "artifacts", ".yuleosh", ".venv", "venv", "node_modules",
}


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


def collect_seed_sources(project_dir: str | Path, max_files: int = SEED_MAX_FILES,
                         max_chars: int = SEED_MAX_CHARS) -> str:
    """收集项目现有 src 代码 (src/**/*.c, *.h) 作为 seed 基线。

    2026-08-12 (方案 C seed 增量): codegen 不再从零全量生成 — LLM 基于
    现有 src 做增量修改。seed 块注入 prompt 让模型看到真实代码基线
    (头文件 + 实现), 只输出它新增/修改的文件。返回拼接后的 markdown,
    无代码返回 ""。
    """
    proot = Path(project_dir)
    src_dir = proot / "src"
    if not src_dir.is_dir():
        return ""
    files: list[Path] = []
    for p in sorted(src_dir.rglob("*")):
        if p.suffix.lower() not in (".c", ".h"):
            continue
        if any(part in SEED_EXCLUDE_DIRS for part in p.relative_to(src_dir).parts):
            continue
        files.append(p)
    files = files[:max_files]
    parts: list[str] = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        rel = str(f.relative_to(proot))
        parts.append(f"### {rel}\n```c\n{content[:max_chars]}\n```")
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
    seed_sources: str = "",
    context_content: str = "",
) -> tuple[str, str]:
    """Build ``(system_prompt, user_prompt)`` for code generation.

    The model is asked to emit every file with a ``### FILE: <path>`` marker
    followed by a fenced code block, so the output is machine-parseable by
    :func:`yuleosh.codegen.engine.parse_generated_files`.

    existing_headers (2026-08-12): 项目既有头文件内容 (src/**/include/*.h)。
    生成的代码必须实现这些既有 API 契约 — 不得改名/改签名 — 否则
    codegen-deploy 的 API 契约护栏会拒绝部署 (生成的是新设计而非对
    既有接口的实现, 破坏测试/harness)。

    seed_sources (2026-08-12, 方案 C seed 增量): 项目现有 src 代码
    (.c/.h) 作为基线。模型基于这些代码做增量修改 — 只输出它新增或
    修改的文件, 未修改的文件不要重发 (engine 端保留 seed 副本)。

    context_content (2026-08-14, headlamp dogfood): CONTEXT.md 领域术语 +
    语言约束 (如 "C99 嵌入式固件, 禁止生成 Python")。此前未注入导致
    LLM 不知项目语言 → 语言漂移假绿。
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
        "2. Output ALL files you create or modify in one response. Do not "
        "add prose between files.\n"
        "3. Code must be syntactically valid: Python files compile under "
        "`py_compile`; C files pass `gcc -fsyntax-only`.\n"
        "4. Follow the injected skills (coding standards, fix patterns, "
        "testing best practices) exactly.\n"
        "5. When a project code baseline (seed) is injected: it already "
        "exists on disk. **Incrementally modify** — only emit files you "
        "created or changed. Never re-emit unchanged baseline files.\n"
    )

    context_parts = [
        f"# Specification: {spec_name}\n```markdown\n{spec_content[:SPEC_INJECT_LIMIT]}\n```"
    ]
    # Project context (2026-08-14, headlamp dogfood): CONTEXT.md 领域术语 +
    # 语言约束放最前 — LLM 必须先知道项目语言/约束再写代码。
    if context_content:
        context_parts.insert(
            1,
            f"# Project Context (必须遵守)\n```markdown\n{context_content[:8000]}\n```",
        )
    if architecture_content:
        context_parts.append(
            f"# Architecture\n```markdown\n{architecture_content[:12000]}\n```"
        )
    if prd_content:
        # 2026-08-16: was [:4000] — codegen LLM saw only the PRD head (FR-001..),
        # missing the tail contracts (FR-044 |delta|, G-01..G-12 guardrail map,
        # SW-005..008 FRs) → generated signed-delta / raw-memcpy code every round.
        # PRD is the behavioral contract for codegen; inject it in full.
        context_parts.append(
            f"# PRD\n```markdown\n{prd_content[:SPEC_INJECT_LIMIT]}\n```"
        )
    if super_analysis_content:
        context_parts.append(
            f"# S.U.P.E.R Analysis\n```markdown\n{super_analysis_content[:6000]}\n```"
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
    # seed 基线 (2026-08-12, 方案 C): 现有代码, 增量修改
    if seed_sources:
        context_parts.append(
            "# 项目现有代码基线 (seed)\n"
            "以下是项目 **已经存在** 的代码。请基于它们做增量修改：\n"
            "- **只输出你新增或修改的文件**；未修改的文件绝对不要重发。\n"
            "- **不要修改与本次功能无关的现有实现**。seed 中已满足 spec\n"
            "  的行为/逻辑/状态机必须原样保留 — 删除或重写它们会被既有\n"
            "  测试判为回归。只改 spec 明确要求变更的部分。\n"
            "- 保持现有文件路径、函数签名、类型、宏不变（既有测试依赖）。\n"
            "- 新功能优先复用现有函数/结构，不要重复造轮子。\n\n"
            + seed_sources
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
