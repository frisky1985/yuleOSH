#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ultra-Plan Agent — data models.

Defines PlanStep, Plan, and PlanStatus — the core data types
for the plan agent's structured output.

A Plan is a tree of PlanStep nodes with metadata describing
the overall objective, technical approach, risks, and prerequisites.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# ── Plan status values ──────────────────────────────────────────────────

class PlanStatus:
    """Well-known plan lifecycle status values."""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    EXECUTING = "executing"
    DONE = "done"
    CANCELLED = "cancelled"

    VALID_STATUSES = frozenset({DRAFT, REVIEW, APPROVED, EXECUTING, DONE, CANCELLED})


# ── Known agent identifiers ─────────────────────────────────────────────

AGENT_MAP = {
    "code": "小克 👨‍💻",
    "review": "小马 🐴",
    "orchestration": "小明",
    "spec": "小马 🐴",
    "test": "小克 👨‍💻",
    "architecture": "小克 👨‍💻",
    "compliance": "小马 🐴",
}

AGENT_KEYS = frozenset(AGENT_MAP.keys())


@dataclass
class PlanStep:
    """A single step in an ultra-plan.

    Each step maps to one unit of work that can be assigned to an
    agent, verified independently, and optionally mapped onto the
    CheckpointEngine pipeline.

    Attributes:
        step_id:        Unique step identifier, e.g. "P1-spec-analysis".
        name:           Short human-readable name, e.g. "需求分析".
        description:    Longer description of what this step does.
        agent:          Responsible agent string, e.g. "小克 👨‍💻".
        effort_hours:   Estimated person-hours.
        depends_on:     List of step_ids that must complete first.
        verification:   How to verify this step is done correctly.
        pipeline_step:  Optional mapping to CheckpointEngine step_id.
    """
    step_id: str
    name: str
    description: str
    agent: str
    effort_hours: float
    depends_on: list[str] = field(default_factory=list)
    verification: str = ""
    pipeline_step: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "agent": self.agent,
            "effort_hours": self.effort_hours,
            "depends_on": list(self.depends_on),
            "verification": self.verification,
            "pipeline_step": self.pipeline_step,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlanStep:
        return cls(
            step_id=d["step_id"],
            name=d["name"],
            description=d.get("description", ""),
            agent=d["agent"],
            effort_hours=float(d.get("effort_hours", 1.0)),
            depends_on=list(d.get("depends_on", [])),
            verification=d.get("verification", ""),
            pipeline_step=d.get("pipeline_step"),
        )


@dataclass
class Plan:
    """A complete ultra-plan.

    Attributes:
        title:              Plan title, e.g. "KG → Dashboard 接入方案".
        objective:          Single-sentence objective.
        background:         Context / background description.
        technical_approach: Technical approach overview.
        steps:              Ordered list of PlanStep instances.
        risks:              List of identified risks.
        prerequisites:      Prerequisites that must be in place.
        generated_at:       ISO-8601 generation timestamp.
        status:             Plan lifecycle status (see PlanStatus).
    """
    title: str
    objective: str
    background: str
    technical_approach: str
    steps: list[PlanStep] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = PlanStatus.DRAFT

    def __post_init__(self):
        if self.status not in PlanStatus.VALID_STATUSES:
            raise ValueError(f"Invalid plan status: {self.status!r}")

    @property
    def total_effort_hours(self) -> float:
        """Sum of all step effort estimates."""
        return sum(s.effort_hours for s in self.steps)

    @property
    def agent_breakdown(self) -> dict[str, float]:
        """Effort broken down by agent name."""
        breakdown: dict[str, float] = {}
        for s in self.steps:
            breakdown[s.agent] = breakdown.get(s.agent, 0.0) + s.effort_hours
        return breakdown

    @property
    def agent_count(self) -> int:
        """Number of unique agents involved."""
        return len({s.agent for s in self.steps})

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "objective": self.objective,
            "background": self.background,
            "technical_approach": self.technical_approach,
            "steps": [s.to_dict() for s in self.steps],
            "risks": list(self.risks),
            "prerequisites": list(self.prerequisites),
            "generated_at": self.generated_at,
            "status": self.status,
        }

    def to_json(self, **kwargs) -> str:
        """Serialize to JSON string.

        Args:
            **kwargs: Passed through to json.dumps (indent, ensure_ascii, etc.)

        Returns:
            JSON string representation of this plan.
        """
        opts = {"indent": 2, "ensure_ascii": False, "default": str}
        opts.update(kwargs)
        return json.dumps(self.to_dict(), **opts)

    @classmethod
    def from_dict(cls, d: dict) -> Plan:
        return cls(
            title=d["title"],
            objective=d.get("objective", ""),
            background=d.get("background", ""),
            technical_approach=d.get("technical_approach", ""),
            steps=[PlanStep.from_dict(s) for s in d.get("steps", [])],
            risks=list(d.get("risks", [])),
            prerequisites=list(d.get("prerequisites", [])),
            generated_at=d.get("generated_at", ""),
            status=d.get("status", PlanStatus.DRAFT),
        )

    @classmethod
    def from_json(cls, text: str) -> Plan:
        d = json.loads(text)
        return cls.from_dict(d)
