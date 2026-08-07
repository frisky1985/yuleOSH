#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Skill registry — in-memory store with optional JSON persistence.

The registry is the single source of truth for the yuleOSH skills library:

* :func:`get_registry` returns the process-wide singleton.
* :meth:`SkillRegistry.register` / :meth:`SkillRegistry.get` /
  :meth:`SkillRegistry.list` / :meth:`SkillRegistry.unregister` provide the
  core API.
* :meth:`SkillRegistry.save` / :meth:`SkillRegistry.load` persist skills as
  JSON (default: ``.osh/skills/skills.json`` under the project root).

Built-in skills (see :mod:`yuleosh.skills.builtin`) are auto-registered on
first access so ``render_skills`` and the CLI work out of the box.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from yuleosh.skills.model import Skill

log = logging.getLogger("yuleosh.skills.registry")

# Default persistence location relative to the project root (OSH_HOME).
DEFAULT_PERSIST_REL = ".osh/skills/skills.json"

_registry: Optional["SkillRegistry"] = None


class SkillRegistry:
    """In-memory skill store with optional JSON persistence.

    Args:
        persist_path: Optional path to the JSON persistence file.  When set,
            :meth:`save` / :meth:`load` operate on this file.
    """

    def __init__(self, persist_path: Optional[str | Path] = None):
        self._skills: dict[str, Skill] = {}
        self.persist_path = Path(persist_path) if persist_path else None

    # ---- Core API ----------------------------------------------------

    def register(self, skill: Skill, overwrite: bool = False) -> bool:
        """Register a skill.

        Returns True when the skill was added, False when a skill with the
        same name already exists and ``overwrite`` is False.
        """
        if skill.name in self._skills and not overwrite:
            log.debug("Skill %s already registered (overwrite=False)", skill.name)
            return False
        self._skills[skill.name] = skill
        log.debug("Skill %s registered (v%s)", skill.name, skill.version)
        return True

    def register_many(self, skills: list[Skill], overwrite: bool = False) -> int:
        """Register several skills, returning how many were added."""
        added = 0
        for skill in skills:
            if self.register(skill, overwrite=overwrite):
                added += 1
        return added

    def unregister(self, name: str) -> bool:
        """Remove a skill by name.  Returns True if it existed."""
        return self._skills.pop(name, None) is not None

    def get(self, name: str) -> Optional[Skill]:
        """Look up a skill by name (None when unknown)."""
        return self._skills.get(name)

    def list(self, tag: Optional[str] = None) -> list[Skill]:
        """List all skills, optionally filtered by tag."""
        skills = list(self._skills.values())
        if tag:
            skills = [s for s in skills if tag in s.tags]
        return sorted(skills, key=lambda s: s.name)

    def names(self) -> list[str]:
        """Return registered skill names (sorted)."""
        return sorted(self._skills.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __len__(self) -> int:
        return len(self._skills)

    # ---- Persistence ---------------------------------------------------

    def save(self, path: Optional[str | Path] = None) -> Path:
        """Persist all skills as JSON.  Returns the path written."""
        out = Path(path) if path else self.persist_path
        if out is None:
            raise ValueError("No persist_path configured; pass a path to save()")
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "1",
            "skills": [s.to_dict() for s in self._skills.values()],
        }
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(out)
        log.info("Saved %d skills to %s", len(self._skills), out)
        return out

    def load(self, path: Optional[str | Path] = None) -> int:
        """Load skills from a JSON file, merging into the current registry.

        Existing entries are preserved (file entries only fill gaps).
        Returns the number of skills loaded.
        """
        src = Path(path) if path else self.persist_path
        if src is None or not src.exists():
            return 0
        payload = json.loads(src.read_text(encoding="utf-8"))
        loaded = 0
        for entry in payload.get("skills", []):
            skill = Skill.from_dict(entry)
            if self.register(skill, overwrite=False):
                loaded += 1
        log.info("Loaded %d new skills from %s", loaded, src)
        return loaded

    # ---- Convenience ----------------------------------------------------

    def default_persist_path(self) -> Path:
        """Return the default persistence path under the project root."""
        root = Path(os.environ.get("OSH_HOME", ".")).resolve()
        return root / DEFAULT_PERSIST_REL

    def save_default(self) -> Path:
        """Persist to the default location under OSH_HOME."""
        return self.save(self.default_persist_path())

    def load_default(self) -> int:
        """Load from the default location under OSH_HOME (if present)."""
        return self.load(self.default_persist_path())


def get_registry() -> SkillRegistry:
    """Return the process-wide singleton registry.

    Built-in skills are auto-registered on first call so the library is
    usable without any setup.  Custom skills registered earlier (via
    :func:`set_registry` or direct singleton mutation) are preserved.
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        from yuleosh.skills.builtin import builtin_skills

        _registry.register_many(builtin_skills())
        # v3.10.0: 自动加载持久化技能（.osh/skills/skills.json，含 mattpocock 导入）
        _registry.load_default()
    return _registry


def set_registry(registry: SkillRegistry) -> SkillRegistry:
    """Replace the singleton registry (mainly for tests/embedding)."""
    global _registry
    _registry = registry
    return _registry


def reset_registry() -> None:
    """Drop the singleton so the next ``get_registry()`` rebuilds it."""
    global _registry
    _registry = None
