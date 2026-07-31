#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Skills 技能库 (v3.4.0).

Two complementary APIs live here:

1. **Prompt-splicing skill library** (new in v3.4.0): reusable markdown
   skills that get rendered into LLM prompts.

   * :class:`yuleosh.skills.model.Skill` — skill data model.
   * :func:`yuleosh.skills.registry.get_registry` — process-wide registry
     (built-ins auto-registered).
   * :func:`yuleosh.skills.prompt.render_skills` — splice skills into prompts.
   * :func:`yuleosh.skills.builtin.builtin_skills` — bundled skills.

   CLI: ``yuleosh skills list`` / ``yuleosh skills show <name>``.

2. **Plugin-orchestration skill store** (original API, preserved): Skills as
   workflows over plugins.

   * :class:`yuleosh.skills.plugin_skills.SkillManager` /
     :class:`yuleosh.skills.plugin_skills.SkillManifest` /
     :class:`yuleosh.skills.plugin_skills.Workflow` /
     :class:`yuleosh.skills.plugin_skills.WorkflowStep`.
"""

from yuleosh.skills.model import Skill
from yuleosh.skills.registry import (
    SkillRegistry,
    get_registry,
    reset_registry,
    set_registry,
)
from yuleosh.skills.prompt import render_skills, resolve_skill_names
from yuleosh.skills.builtin import builtin_skills, BUILTIN_SKILL_NAMES
from yuleosh.skills.plugin_skills import (
    SkillManager,
    SkillManifest,
    Workflow,
    WorkflowStep,
)

__all__ = [
    # prompt-splicing library (v3.4.0)
    "Skill",
    "SkillRegistry",
    "get_registry",
    "set_registry",
    "reset_registry",
    "render_skills",
    "resolve_skill_names",
    "builtin_skills",
    "BUILTIN_SKILL_NAMES",
    # plugin-orchestration store (original API)
    "SkillManager",
    "SkillManifest",
    "Workflow",
    "WorkflowStep",
]
