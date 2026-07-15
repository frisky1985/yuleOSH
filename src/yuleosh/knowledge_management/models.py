#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Management — data models.

Single dataclass for KnowledgeArticle with full spec-compliant metadata.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Status enumeration ──────────────────────────────────────────────────

ARTICLE_STATUSES = frozenset({
    "draft",
    "review_pending",
    "approved",
    "published",
    "deprecated",
    "archived",
})

# ── Safety level enumeration ───────────────────────────────────────────

SAFETY_LEVELS = frozenset({
    "ASIL_A",
    "ASIL_B",
    "ASIL_C",
    "ASIL_D",
    "QM",
})

# ── Valid status transitions (KBS-13) ──────────────────────────────────

VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft":           {"review_pending"},
    "review_pending":  {"approved", "draft"},
    "approved":        {"published", "deprecated"},
    "published":       {"deprecated"},
    "deprecated":      {"approved"},
    "archived":        set(),
}

# Confidence decay policy
CONFIDENCE_DECAY_POLICIES = frozenset({"usage_based"})


@dataclass
class KnowledgeArticle:
    """A knowledge article in the KB module.

    Maps directly to KBS-03 spec fields. All optional fields default to
    None / factory default so callers only set what they know.
    """

    id: Optional[str] = None                    # UUID — generated if None
    title: str = ""
    content: str = ""
    status: str = "draft"
    safety_level: str = "QM"
    created_by: str = ""
    updated_by: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    version: str = "1.0.0"
    confidence: int = 100
    confidence_decay_policy: str = "usage_based"
    is_deleted: bool = False
    deleted_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    # Optional spec-extended fields (P0 stores as JSON; active use in P1)
    ota_binding: Optional[dict] = None        # {ota_version, ota_manifest_hash}
    tcl_doc_slot: Optional[dict] = None        # {tcl_tool_id, cert_doc_refs, assessment_status}
    hw_bom: Optional[list[dict]] = None        # [{platform, chip, version}]
    dtc_codes: list[str] = field(default_factory=list)
    autosar_layers: list[str] = field(default_factory=list)  # ASW/RTE/BSW/HW
    code_paths: list[str] = field(default_factory=list)
    spec_refs: list[str] = field(default_factory=list)
    safety_goals: list[dict] = field(default_factory=list)
    test_refs: list[dict] = field(default_factory=list)
    change_reason: Optional[str] = None
    review_notes: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a plain dict safe for JSON/storage."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "safety_level": self.safety_level,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "confidence": self.confidence,
            "confidence_decay_policy": self.confidence_decay_policy,
            "is_deleted": self.is_deleted,
            "deleted_at": self.deleted_at,
            "tags": self.tags,
            "ota_binding": self.ota_binding,
            "tcl_doc_slot": self.tcl_doc_slot,
            "hw_bom": self.hw_bom,
            "dtc_codes": self.dtc_codes,
            "autosar_layers": self.autosar_layers,
            "code_paths": self.code_paths,
            "spec_refs": self.spec_refs,
            "safety_goals": self.safety_goals,
            "test_refs": self.test_refs,
            "change_reason": self.change_reason,
            "review_notes": self.review_notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeArticle":
        """Deserialize from a dict (coming from store rows)."""
        kwargs = {k: v for k, v in data.items()
                  if k in cls.__dataclass_fields__}
        return cls(**kwargs)
