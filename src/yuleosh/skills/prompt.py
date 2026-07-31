#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Prompt splicing — render skills into LLM prompts.

``render_skills(names)`` returns a markdown block that can be embedded into
any system/user prompt so the model follows the requested skills.  Unknown
names are skipped with a warning (never fail the caller).
"""

from __future__ import annotations

import logging
from typing import Optional

from yuleosh.skills.registry import SkillRegistry, get_registry

log = logging.getLogger("yuleosh.skills.prompt")

HEADER = (
    "## 📚 技能参考 (Skills)\n"
    "以下技能由 yuleOSH 技能库注入，请严格遵循其中规范生成代码：\n"
)


def render_skills(
    names: list[str],
    registry: Optional[SkillRegistry] = None,
    max_chars_per_skill: int = 4000,
) -> str:
    """Render the given skills as a markdown block for prompt splicing.

    Args:
        names: Skill names to include (e.g. ``["autosar-coding", "misra-fix"]``).
        registry: Registry to look up from (defaults to the singleton).
        max_chars_per_skill: Truncate each skill's content to this many chars
            to bound prompt size (0 disables truncation).

    Returns:
        Markdown string.  Empty string when no skill names are given or none
        resolve.
    """
    if not names:
        return ""
    if registry is None:
        registry = get_registry()

    rendered: list[str] = []
    for name in names:
        skill = registry.get(name)
        if skill is None:
            log.warning("Skill %s not found — skipping", name)
            continue
        block = skill.render()
        if max_chars_per_skill > 0 and len(block) > max_chars_per_skill:
            block = block[:max_chars_per_skill] + "\n…(truncated)"
        rendered.append(block)

    if not rendered:
        return ""
    return HEADER + "\n".join(rendered) + "\n"


def resolve_skill_names(
    names: Optional[list[str] | str],
    registry: Optional[SkillRegistry] = None,
) -> list[str]:
    """Normalize skill name input and drop unknown names.

    Accepts a list, a comma-separated string, or None.  Unknown names are
    filtered out (with a warning), so callers can safely pass config values.
    """
    if names is None:
        return []
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]
    if registry is None:
        registry = get_registry()
    known = [n for n in names if n in registry]
    for n in names:
        if n not in known:
            log.warning("Unknown skill %s — ignoring", n)
    return known
