#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Skill data model — the unit of the yuleOSH skills library.

A :class:`Skill` bundles a name, metadata, and markdown content that can be
rendered into an LLM prompt (see :mod:`yuleosh.skills.prompt`).  Skills are
stored in-memory by :class:`yuleosh.skills.registry.SkillRegistry` and may be
persisted as JSON for reuse across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class Skill:
    """A reusable skill: name + metadata + markdown body.

    Attributes:
        name: Unique machine-readable identifier (e.g. ``autosar-coding``).
        title: Human-readable title (e.g. "AUTOSAR C 编码规范要点").
        description: One-line summary shown by ``yuleosh skills list``.
        content: Markdown body spliced into LLM prompts by ``render_skills``.
        tags: Optional category tags (e.g. ``["c", "autosar"]``).
        version: Semantic version of the skill content.
        created_at: ISO timestamp (auto-set on construction).
    """

    name: str
    title: str
    description: str
    content: str
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Skill":
        """Deserialize from a dict (skips unknown keys for forward compat)."""
        known = {
            k: v
            for k, v in data.items()
            if k in {"name", "title", "description", "content", "tags", "version", "created_at"}
        }
        known.setdefault("tags", [])
        return cls(**known)

    def render_header(self) -> str:
        """Render the skill header block (name / title / description)."""
        tags = ", ".join(self.tags) if self.tags else "—"
        return (
            f"### Skill: {self.name}\n"
            f"- **Title**: {self.title}\n"
            f"- **Description**: {self.description}\n"
            f"- **Tags**: {tags}\n"
            f"- **Version**: {self.version}\n"
        )

    def render(self) -> str:
        """Render the full skill (header + content) for prompt splicing."""
        return f"{self.render_header()}\n{self.content.strip()}\n"
