#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""CLI handlers for the ``yuleosh skills`` command group."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from yuleosh.skills.registry import get_registry


def handle_skills_command(args: argparse.Namespace) -> int:
    """Dispatch ``yuleosh skills list|show`` (returns process exit code)."""
    sub = getattr(args, "skills_sub", None)
    if sub == "list":
        return _cmd_skills_list(json_output=bool(getattr(args, "json", False)))
    if sub == "show":
        return _cmd_skills_show(getattr(args, "name", None))
    print("Usage: yuleosh skills list | yuleosh skills show <name>")
    return 2


def _cmd_skills_list(json_output: bool = False) -> int:
    """List all registered skills."""
    registry = get_registry()
    skills = registry.list()
    if json_output:
        print(json.dumps([s.to_dict() for s in skills], indent=2, ensure_ascii=False))
        return 0

    print("\n📚 yuleOSH Skills 技能库")
    print("=" * 60)
    if not skills:
        print("  (no skills registered)")
    for skill in skills:
        tags = ", ".join(skill.tags) if skill.tags else "—"
        print(f"  • {skill.name}")
        print(f"    {skill.title}  (v{skill.version})")
        print(f"    {skill.description}")
        print(f"    tags: {tags}")
        print()
    print(f"Total: {len(skills)} skills")
    return 0


def _cmd_skills_show(name: Optional[str]) -> int:
    """Show the full content of a single skill."""
    if not name:
        print("Usage: yuleosh skills show <name>")
        return 2
    registry = get_registry()
    skill = registry.get(name)
    if skill is None:
        print(f"❌ Skill '{name}' not found.")
        print(f"   Available: {', '.join(registry.names()) or '(none)'}")
        return 1
    print(f"\n📘 Skill: {skill.name}")
    print("=" * 60)
    print(skill.render())
    return 0
