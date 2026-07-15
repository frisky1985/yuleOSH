# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Knowledge Base data models — dataclasses for kb_articles, lessons, fmea_entries."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class KbArticle:
    """A knowledge base entry (MISRA violations, best practices, etc.)."""
    id: Optional[int] = None
    title: str = ""
    content: str = ""
    source: str = ""
    source_ref: str = ""
    tags: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "source_ref": self.source_ref,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KbArticle":
        """Deserialize from a dict (from JSON body or DB row)."""
        created = d.get("created_at")
        updated = d.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return cls(
            id=d.get("id"),
            title=d.get("title", ""),
            content=d.get("content", ""),
            source=d.get("source", ""),
            source_ref=d.get("source_ref", ""),
            tags=d.get("tags", ""),
            created_at=created,
            updated_at=updated,
        )


@dataclass
class Lesson:
    """A lessons-learned entry."""
    id: Optional[int] = None
    title: str = ""
    problem: str = ""
    solution: str = ""
    root_cause: str = ""
    project_id: str = ""
    severity: str = "medium"
    created_at: Optional[datetime] = None

    VALID_SEVERITIES = {"low", "medium", "high", "critical"}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "problem": self.problem,
            "solution": self.solution,
            "root_cause": self.root_cause,
            "project_id": self.project_id,
            "severity": self.severity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Lesson":
        created = d.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        sev = d.get("severity", "medium")
        if sev not in cls.VALID_SEVERITIES:
            sev = "medium"
        return cls(
            id=d.get("id"),
            title=d.get("title", ""),
            problem=d.get("problem", ""),
            solution=d.get("solution", ""),
            root_cause=d.get("root_cause", ""),
            project_id=d.get("project_id", ""),
            severity=sev,
            created_at=created,
        )


@dataclass
class FmeaEntry:
    """A FMEA entry (simplified)."""
    id: Optional[int] = None
    item: str = ""
    failure_mode: str = ""
    effect: str = ""
    cause: str = ""
    severity: int = 1
    occurence: int = 1
    detection: int = 1
    rpn: int = 0  # GENERATED: severity * occurence * detection
    recommendation: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self._compute_rpn()

    def _compute_rpn(self):
        self.rpn = self.severity * self.occurence * self.detection

    def to_dict(self) -> dict:
        self._compute_rpn()
        return {
            "id": self.id,
            "item": self.item,
            "failure_mode": self.failure_mode,
            "effect": self.effect,
            "cause": self.cause,
            "severity": self.severity,
            "occurence": self.occurence,
            "detection": self.detection,
            "rpn": self.rpn,
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FmeaEntry":
        created = d.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            id=d.get("id"),
            item=d.get("item", ""),
            failure_mode=d.get("failure_mode", ""),
            effect=d.get("effect", ""),
            cause=d.get("cause", ""),
            severity=d.get("severity", 1),
            occurence=d.get("occurence", 1),
            detection=d.get("detection", 1),
            recommendation=d.get("recommendation", ""),
            created_at=created,
        )


def sanitize_kb_article_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a KbArticle."""
    allowed = {"title", "content", "source", "source_ref", "tags"}
    return {k: v for k, v in body.items() if k in allowed and isinstance(v, str)}


def sanitize_lesson_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a Lesson."""
    allowed = {"title", "problem", "solution", "root_cause", "project_id", "severity"}
    cleaned = {k: v for k, v in body.items() if k in allowed}
    sev = cleaned.get("severity", "medium")
    if sev not in Lesson.VALID_SEVERITIES:
        cleaned["severity"] = "medium"
    return cleaned


def sanitize_fmea_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a FmeaEntry."""
    allowed = {"item", "failure_mode", "effect", "cause", "severity",
               "occurence", "detection", "recommendation"}
    cleaned = {}
    for k in allowed:
        if k in body:
            cleaned[k] = body[k]
    # Clamp numeric ratings to 1-10
    for num_field in ("severity", "occurence", "detection"):
        val = cleaned.get(num_field, 1)
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = 1
        cleaned[num_field] = max(1, min(10, val))
    return cleaned
