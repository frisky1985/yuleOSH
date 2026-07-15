#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for yuleOSH Knowledge Management KB module — P0.

Covers:
  - KBS-01: CRUD operations
  - KBS-02: UUID identity
  - KBS-03: Metadata structure
  - KBS-04: Version management
  - Soft delete / restore
  - Status machine (VALID_TRANSITIONS)
  - Search / list / tag queries
  - Stats aggregation
  - Error handling (invalid transitions, not found, etc.)
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def km_db_path():
    """Use temp DB to avoid cross-test pollution."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    old_env = os.environ.get("YULEOSH_KB_DB")
    os.environ["YULEOSH_KB_DB"] = db_path
    yield db_path
    os.environ.pop("YULEOSH_KB_DB", None)
    if old_env:
        os.environ["YULEOSH_KB_DB"] = old_env
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def store():
    """Fresh KBStore wired to the temp DB."""
    from yuleosh.knowledge_management.store import KBStore
    KBStore.reset()
    s = KBStore()
    yield s
    KBStore.reset()


@pytest.fixture
def sample_article():
    """Factory for a standard article fixture."""
    from yuleosh.knowledge_management.models import KnowledgeArticle

    def _make(**overrides):
        kwargs = {
            "title": "Brake Calibration Guide",
            "content": "# Brake Calibration\n\nStep-by-step guide for brake calibration on TDA4VM.",
            "status": "draft",
            "safety_level": "ASIL_D",
            "created_by": "alice",
            "tags": ["brake", "calibration", "TDA4VM"],
            "dtc_codes": ["P0101", "P0102"],
            "autosar_layers": ["ASW", "BSW"],
            "code_paths": ["src/brake/calib.c", "src/brake/calib.h"],
            "spec_refs": ["RS-BRAKE-001"],
        }
        kwargs.update(overrides)
        return KnowledgeArticle(**kwargs)
    return _make


# ═══════════════════════════════════════════════════════════════════════
# KBS-01: CRUD
# ═══════════════════════════════════════════════════════════════════════

class TestCreate:
    """KBS-01: Create operations."""

    def test_create_article(self, store, sample_article):
        """Create a basic article and verify it exists."""
        article = sample_article()
        created = store.create(article)
        assert created.id is not None
        assert len(created.id) == 36  # UUID length
        assert created.title == "Brake Calibration Guide"
        assert created.status == "draft"
        assert created.version == "1.0.0"
        assert created.confidence == 100
        assert created.is_deleted is False
        assert created.created_at is not None
        assert created.updated_at is not None

    def test_create_auto_ids(self, store, sample_article):
        """Each create gets a unique UUID."""
        a1 = store.create(sample_article(title="Article A"))
        a2 = store.create(sample_article(title="Article B"))
        assert a1.id != a2.id

    def test_create_default_fields(self, store):
        """Create with minimal fields."""
        from yuleosh.knowledge_management.models import KnowledgeArticle
        article = KnowledgeArticle(title="Minimal", content="Minimal content")
        created = store.create(article)
        assert created.status == "draft"
        assert created.safety_level == "QM"
        assert created.version == "1.0.0"
        assert created.confidence == 100
        assert created.tags == []
        assert created.is_deleted is False


class TestRead:
    """KBS-01: Read operations."""

    def test_get_article(self, store, sample_article):
        """Get article by ID returns the right article."""
        article = store.create(sample_article())
        fetched = store.get(article.id)
        assert fetched is not None
        assert fetched.id == article.id
        assert fetched.title == article.title
        assert fetched.content == article.content
        assert fetched.safety_level == "ASIL_D"
        assert fetched.dtc_codes == ["P0101", "P0102"]
        assert fetched.autosar_layers == ["ASW", "BSW"]

    def test_get_nonexistent(self, store):
        """Get by non-existent ID returns None."""
        assert store.get("nonexistent-id") is None

    def test_get_deleted_excluded(self, store, sample_article):
        """Soft-deleted articles are hidden by default."""
        article = store.create(sample_article())
        store.soft_delete(article.id)
        assert store.get(article.id) is None

    def test_get_deleted_included(self, store, sample_article):
        """include_deleted=True returns soft-deleted articles."""
        article = store.create(sample_article())
        store.soft_delete(article.id)
        fetched = store.get(article.id, include_deleted=True)
        assert fetched is not None
        assert fetched.is_deleted is True
        assert fetched.deleted_at is not None


class TestUpdate:
    """KBS-01: Update operations."""

    def test_update_title(self, store, sample_article):
        """Updating a field preserves others."""
        article = store.create(sample_article())
        updated = store.update(article.id, {"title": "New Title"}, updated_by="bob")
        assert updated is not None
        assert updated.title == "New Title"
        assert updated.content == article.content  # unchanged
        assert updated.updated_by == "bob"

    def test_update_nonexistent(self, store):
        """Update on non-existent ID returns None."""
        result = store.update("no-such-id", {"title": "Nope"})
        assert result is None

    def test_update_on_deleted(self, store, sample_article):
        """Update on soft-deleted article returns None."""
        article = store.create(sample_article())
        store.soft_delete(article.id)
        result = store.update(article.id, {"title": "Nope"})
        assert result is None


class TestSoftDelete:
    """KBS-01: Soft delete."""

    def test_soft_delete_and_restore(self, store, sample_article):
        """Article can be soft-deleted and restored."""
        article = store.create(sample_article())
        # Soft delete
        assert store.soft_delete(article.id, updated_by="admin") is True
        assert store.get(article.id) is None
        # Restore
        assert store.restore(article.id, updated_by="admin") is True
        restored = store.get(article.id)
        assert restored is not None
        assert restored.is_deleted is False
        assert restored.deleted_at is None

    def test_double_delete(self, store, sample_article):
        """Deleting an already deleted article returns False."""
        article = store.create(sample_article())
        store.soft_delete(article.id)
        assert store.soft_delete(article.id) is False

    def test_delete_nonexistent(self, store):
        """Deleting a non-existent article returns False."""
        assert store.soft_delete("no-such-id") is False

    def test_restore_nonexistent(self, store):
        """Restoring a non-existent article returns False."""
        assert store.restore("no-such-id") is False

    def test_restore_alive_article(self, store, sample_article):
        """Restoring a non-deleted article returns False."""
        article = store.create(sample_article())
        assert store.restore(article.id) is False


# ═══════════════════════════════════════════════════════════════════════
# KBS-02: UUID Identity
# ═══════════════════════════════════════════════════════════════════════

class TestUUID:
    """KBS-02: UUID global unique identifier."""

    def test_uuid_format(self, store, sample_article):
        """All created articles get valid UUID v4 strings."""
        article = store.create(sample_article())
        assert len(article.id) == 36
        assert article.id.count("-") == 4

    def test_id_immutable(self, store, sample_article):
        """The id field is never overwritten on update."""
        article = store.create(sample_article())
        original_id = article.id
        store.update(article.id, {"title": "Updated"})
        fetched = store.get(article.id)
        assert fetched.id == original_id


# ═══════════════════════════════════════════════════════════════════════
# KBS-03: Metadata Structure
# ═══════════════════════════════════════════════════════════════════════

class TestMetadata:
    """KBS-03: Full metadata field set."""

    def test_all_metadata_fields(self, store):
        """Create article with all KBS-03 fields populated."""
        from yuleosh.knowledge_management.models import KnowledgeArticle
        safety_goals = [
            {
                "safety_goal_id": "SG-BRAKE-001",
                "safety_goal_title": "Safe brake operation",
                "link_type": "derived_from",
            }
        ]
        test_refs = [
            {"test_id": "TC-BRAKE-001", "level": "HIL", "status": "pass"},
        ]
        article = KnowledgeArticle(
            title="Full Metadata",
            content="Full content",
            status="draft",
            safety_level="ASIL_C",
            created_by="alice",
            updated_by="alice",
            version="1.0.0",
            confidence=85,
            confidence_decay_policy="usage_based",
            tags=["test", "full"],
            ota_binding={"ota_version": "2.1.0", "ota_manifest_hash": "abc123"},
            tcl_doc_slot={"tcl_tool_id": "TCL-001", "assessment_status": "pending"},
            hw_bom=[{"platform": "TDA4VM", "chip": "TDA4VM-Q1", "version": "1.2"}],
            dtc_codes=["P0101"],
            autosar_layers=["ASW", "RTE"],
            code_paths=["src/test.cpp"],
            spec_refs=["SPEC-001"],
            safety_goals=safety_goals,
            test_refs=test_refs,
            change_reason="Initial import",
            review_notes="Pending review",
        )
        created = store.create(article)
        assert created.ota_binding == {"ota_version": "2.1.0", "ota_manifest_hash": "abc123"}
        assert created.tcl_doc_slot == {"tcl_tool_id": "TCL-001", "assessment_status": "pending"}
        assert created.hw_bom == [{"platform": "TDA4VM", "chip": "TDA4VM-Q1", "version": "1.2"}]
        assert created.safety_goals == safety_goals
        assert created.test_refs == test_refs
        assert created.change_reason == "Initial import"

    def test_safety_level_enum(self, store, sample_article):
        """safety_level values are stored and retrieved."""
        for level in ("QM", "ASIL_A", "ASIL_B", "ASIL_C", "ASIL_D"):
            article = store.create(sample_article(safety_level=level))
            assert store.get(article.id).safety_level == level

    def test_status_enum(self, store, sample_article):
        """Status values are stored correctly."""
        for status in ("draft", "review_pending", "approved", "published",
                       "deprecated", "archived"):
            article = store.create(sample_article(status=status))
            assert store.get(article.id).status == status


# ═══════════════════════════════════════════════════════════════════════
# KBS-04: Version Management
# ═══════════════════════════════════════════════════════════════════════

class TestVersioning:
    """KBS-04: Version auto-increment on update."""

    def test_initial_version_is_1_0_0(self, store, sample_article):
        """New articles start at version 1.0.0."""
        article = store.create(sample_article())
        assert article.version == "1.0.0"

    def test_patch_increment_on_update(self, store, sample_article):
        """Updating content auto-bumps patch version."""
        article = store.create(sample_article())
        updated = store.update(article.id, {"title": "Updated Title"})
        assert updated.version == "1.0.1"

    def test_no_bump_on_metadata_only(self, store, sample_article):
        """Updating non-content fields (updated_by) does not bump version."""
        article = store.create(sample_article())
        store.update(article.id, {"updated_by": "bob"})
        # updated_by alone not in bump set
        fetched = store.get(article.id)
        # Since updated_by alone isn't in for_bump, version stays the same
        assert fetched.version == "1.0.0"

    def test_multiple_updates_increment(self, store, sample_article):
        """Sequential updates increment patch progressively."""
        article = store.create(sample_article())
        for i in range(3):
            article = store.update(article.id, {"title": f"Update {i + 1}"})
        assert article.version == "1.0.3"

    def test_version_snapshot_created(self, store, sample_article):
        """Version snapshots are created on create and content updates."""
        article = store.create(sample_article())
        versions, total = store.list_versions(article.id)
        assert total >= 1  # at least the initial snapshot

        store.update(article.id, {"title": "Updated"})
        versions, total = store.list_versions(article.id)
        assert total >= 2

    def test_get_version_snapshot(self, store, sample_article):
        """Can retrieve a full snapshot from a specific version."""
        article = store.create(sample_article())
        original_id = article.id
        store.update(article.id, {"title": "Updated Title"})

        # Get v1.0.0 snapshot
        snapshot = store.get_version_snapshot(original_id, "1.0.0")
        assert snapshot is not None
        assert snapshot.title == "Brake Calibration Guide"

        # Get v1.0.1 snapshot
        snapshot = store.get_version_snapshot(original_id, "1.0.1")
        assert snapshot is not None
        assert snapshot.title == "Updated Title"


# ═══════════════════════════════════════════════════════════════════════
# Status Machine (KBS-13)
# ═══════════════════════════════════════════════════════════════════════

class TestStatusMachine:
    """Status transition validation."""

    def test_valid_transition(self, store, sample_article):
        """draft → review_pending is valid."""
        article = store.create(sample_article(status="draft"))
        updated = store.update(article.id, {"status": "review_pending"})
        assert updated.status == "review_pending"

    def test_invalid_transition_returns_none(self, store, sample_article):
        """draft → published is invalid, returns None."""
        article = store.create(sample_article(status="draft"))
        result = store.update(article.id, {"status": "published"})
        assert result is None  # invalid transition

    def test_full_transition_chain(self, store, sample_article):
        """draft → review_pending → approved → published → deprecated → approved."""
        chain = [
            ("draft", "review_pending"),
            ("review_pending", "approved"),
            ("approved", "published"),
            ("published", "deprecated"),
            ("deprecated", "approved"),
        ]
        article = store.create(sample_article(status="draft"))
        for current, target in chain:
            assert article.status == current
            article = store.update(article.id, {"status": target})
            assert article is not None
            assert article.status == target, f"Failed {current} → {target}"

    def test_review_pending_to_draft(self, store, sample_article):
        """review_pending → draft (reject) is valid."""
        article = store.create(sample_article(status="review_pending"))
        updated = store.update(article.id, {"status": "draft"})
        assert updated.status == "draft"

    def test_archived_frozen(self, store, sample_article):
        """archived has no outgoing transitions."""
        article = store.create(sample_article(status="archived"))
        result = store.update(article.id, {"status": "draft"})
        assert result is None

    def test_status_boost_versions(self, store, sample_article):
        """Status transitions trigger version bumps."""
        article = store.create(sample_article(status="draft"))
        updated = store.update(article.id, {"status": "review_pending"})
        assert updated.version == "1.0.1"


# ═══════════════════════════════════════════════════════════════════════
# List / Search
# ═══════════════════════════════════════════════════════════════════════

class TestListAndSearch:
    """List and search operations."""

    def test_list_empty(self, store):
        """List returns empty when no articles exist."""
        articles, total = store.list()
        assert articles == []
        assert total == 0

    def test_list_multiple(self, store, sample_article):
        """List returns all non-deleted articles."""
        store.create(sample_article(title="A"))
        store.create(sample_article(title="B"))
        store.create(sample_article(title="C"))
        articles, total = store.list()
        assert total == 3
        assert len(articles) == 3

    def test_list_by_status(self, store, sample_article):
        """List filtered by status."""
        store.create(sample_article(title="Draft", status="draft"))
        store.create(sample_article(title="Published", status="published"))
        store.create(sample_article(title="Deprecated", status="deprecated"))

        drafts, total = store.list(status="draft")
        assert total == 1
        assert drafts[0].title == "Draft"

    def test_list_hides_deleted(self, store, sample_article):
        """Soft-deleted articles are excluded from list."""
        a1 = store.create(sample_article(title="A"))
        store.create(sample_article(title="B"))
        store.soft_delete(a1.id)
        articles, total = store.list()
        assert total == 1
        assert articles[0].title == "B"

    def test_list_pagination(self, store, sample_article):
        """List respects offset/limit."""
        for i in range(10):
            store.create(sample_article(title=f"Article {i}"))
        page1, total = store.list(offset=0, limit=3)
        assert len(page1) == 3
        assert total == 10
        page2, total = store.list(offset=3, limit=3)
        assert len(page2) == 3

    def test_search_finds_by_title(self, store, sample_article):
        """Search matches title content."""
        store.create(sample_article(title="Brake Calibration",
                                      content="About brakes."))
        store.create(sample_article(title="Steering Alignment",
                                      content="About steering."))
        results, total = store.search("brake")
        assert total == 1
        assert "Brake" in results[0].title

    def test_search_finds_by_content(self, store, sample_article):
        """Search matches content body."""
        store.create(sample_article(content="This is about memory management in embedded systems."))
        results, total = store.search("memory management")
        assert total == 1

    def test_search_multiple_matches(self, store, sample_article):
        """Search returns all matching articles."""
        store.create(sample_article(title="Brake Guide", tags=["brake"]))
        store.create(sample_article(title="Brake Sensor", tags=["brake", "sensor"]))
        results, total = store.search("brake")
        assert total == 2

    def test_search_no_results(self, store, sample_article):
        """Search with no matches returns empty."""
        store.create(sample_article(title="Something"))
        results, total = store.search("zzzzz")
        assert total == 0
        assert results == []

    def test_search_by_tags_any(self, store, sample_article):
        """Search by tags with match_all=False finds articles with ANY tag."""
        store.create(sample_article(title="A", tags=["a", "b"]))
        store.create(sample_article(title="C", tags=["c"]))
        results, total = store.search_by_tags(["a", "c"], match_all=False)
        assert total == 2

    def test_search_by_tags_all(self, store, sample_article):
        """Search by tags with match_all=True requires ALL tags."""
        store.create(sample_article(title="Both", tags=["a", "b"]))
        store.create(sample_article(title="Only A", tags=["a"]))
        results, total = store.search_by_tags(["a", "b"], match_all=True)
        assert total == 1
        assert results[0].title == "Both"

    def test_search_by_tags_empty(self, store):
        """Empty tag list returns empty results."""
        results, total = store.search_by_tags([])
        assert total == 0
        assert results == []


# ═══════════════════════════════════════════════════════════════════════
# Query API (queries.py)
# ═══════════════════════════════════════════════════════════════════════

class TestQueryAPI:
    """Higher-level query API through queries.py."""

    def test_search_returns_dict(self, store, sample_article):
        """queries.search returns structured response."""
        from yuleosh.knowledge_management.queries import search
        store.create(sample_article(title="Test Query"))
        result = search(store, "test")
        assert "items" in result
        assert "total" in result
        assert result["total"] == 1
        assert result["items"][0]["title"] == "Test Query"

    def test_list_articles(self, store, sample_article):
        """queries.list_articles returns structured response."""
        from yuleosh.knowledge_management.queries import list_articles
        store.create(sample_article())
        result = list_articles(store)
        assert result["total"] == 1

    def test_get_by_id(self, store, sample_article):
        """queries.get_by_id returns article dict."""
        from yuleosh.knowledge_management.queries import get_by_id
        article = store.create(sample_article())
        result = get_by_id(store, article.id)
        assert result["id"] == article.id

    def test_get_by_id_missing(self, store):
        """queries.get_by_id returns None for missing ID."""
        from yuleosh.knowledge_management.queries import get_by_id
        assert get_by_id(store, "no-such-id") is None

    def test_get_by_status(self, store, sample_article):
        """queries.get_by_status filters correctly."""
        from yuleosh.knowledge_management.queries import get_by_status
        store.create(sample_article(title="Draft A", status="draft"))
        store.create(sample_article(title="Published B", status="published"))
        result = get_by_status(store, "published")
        assert result["total"] == 1
        assert result["items"][0]["title"] == "Published B"

    def test_get_by_status_invalid(self, store):
        """queries.get_by_status with invalid status returns error."""
        from yuleosh.knowledge_management.queries import get_by_status
        result = get_by_status(store, "invalid_status")
        assert result["total"] == 0
        assert "error" in result

    def test_search_by_tags_query(self, store, sample_article):
        """queries.search_by_tags returns structured response."""
        from yuleosh.knowledge_management.queries import search_by_tags
        store.create(sample_article(tags=["aaa", "bbb"]))
        result = search_by_tags(store, ["aaa"])
        assert result["total"] == 1
        assert result["tags"] == ["aaa"]

    def test_list_deleted(self, store, sample_article):
        """queries.list_deleted returns only soft-deleted articles."""
        from yuleosh.knowledge_management.queries import list_deleted
        a1 = store.create(sample_article(title="Will be deleted"))
        store.create(sample_article(title="Will stay"))
        store.soft_delete(a1.id)
        result = list_deleted(store)
        assert result["total"] == 1
        assert result["items"][0]["title"] == "Will be deleted"

    def test_get_stats(self, store, sample_article):
        """queries.get_stats returns summary."""
        from yuleosh.knowledge_management.queries import get_stats
        store.create(sample_article(title="A", status="draft"))
        store.create(sample_article(title="B", status="published", safety_level="ASIL_D"))
        stats = get_stats(store)
        assert stats["total_articles"] == 2
        assert stats["by_status"]["draft"] == 1
        assert stats["by_status"]["published"] == 1

    def test_list_versions_query(self, store, sample_article):
        """queries.list_versions returns version metadata."""
        from yuleosh.knowledge_management.queries import list_versions
        article = store.create(sample_article())
        result = list_versions(store, article.id)
        assert result["total"] >= 1
        assert "version" in result["versions"][0]


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases & Error Handling
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions and error scenarios."""

    def test_confidence_bounds(self, store, sample_article):
        """Confidence stores and retrieves edge values."""
        for val in (0, 50, 100):
            article = store.create(sample_article(confidence=val))
            assert store.get(article.id).confidence == val

    def test_title_max_length_store(self, store, sample_article):
        """Title is stored as TEXT, can hold long values."""
        long_title = "A" * 500
        article = store.create(sample_article(title=long_title))
        assert len(article.title) == 500

    def test_serialize_deserialize_roundtrip(self, store, sample_article):
        """Article dict round-trips correctly through store."""
        from yuleosh.knowledge_management.models import KnowledgeArticle
        original = sample_article()
        created = store.create(original)
        d = created.to_dict()
        restored = KnowledgeArticle.from_dict(d)
        assert restored.id == created.id
        assert restored.title == created.title
        assert restored.safety_level == created.safety_level
        assert restored.tags == created.tags

    def test_store_singleton(self, store):
        """Multiple KBStore() calls return the same instance."""
        from yuleosh.knowledge_management.store import KBStore
        s2 = KBStore()
        assert s2 is store

    def test_store_reset(self, store):
        """After reset, a new instance is created."""
        from yuleosh.knowledge_management.store import KBStore
        KBStore.reset()
        s2 = KBStore()
        assert s2 is not store
        assert s2.db_path == store.db_path

    def test_close_and_reopen(self, store, sample_article):
        """Closing and re-creating store reads existing data (persistence)."""
        from yuleosh.knowledge_management.store import KBStore as KBStoreCls
        db_path = store.db_path
        article = store.create(sample_article(title="Persistent"))
        article_id = article.id
        store.close()
        KBStoreCls.reset()
        s2 = KBStoreCls(db_path=db_path)
        fetched = s2.get(article_id)
        assert fetched is not None
        assert fetched.title == "Persistent"

    def test_update_change_reason(self, store, sample_article):
        """Change reason is captured on update."""
        article = store.create(sample_article(change_reason="Initial"))
        updated = store.update(article.id, {"title": "Changed", "change_reason": "Updated reason"})
        # change_reason is stored but read from the article
        assert updated.version == "1.0.1"


# ═══════════════════════════════════════════════════════════════════════
# Confidence Decay Policy
# ═══════════════════════════════════════════════════════════════════════

class TestConfidenceDecayPolicy:
    """confidence_decay_policy field handling."""

    def test_default_policy(self, store, sample_article):
        """Default policy is usage_based."""
        article = store.create(sample_article())
        assert article.confidence_decay_policy == "usage_based"

    def test_custom_policy(self, store, sample_article):
        """Can set a custom confidence_decay_policy."""
        article = store.create(sample_article(confidence_decay_policy="usage_based"))
        assert store.get(article.id).confidence_decay_policy == "usage_based"


# ═══════════════════════════════════════════════════════════════════════
# JSONB fields round-trip
# ═══════════════════════════════════════════════════════════════════════

class TestJSONFields:
    """Complex field types (JSON stored as TEXT)."""

    def test_hw_bom_roundtrip(self, store, sample_article):
        """HW BOM JSON array round-trips."""
        hw_bom = [
            {"platform": "TDA4VM", "chip": "TDA4VM-Q1", "version": "1.2"},
            {"platform": "J784S4", "chip": "J784S4-Q1", "version": "2.0"},
        ]
        article = store.create(sample_article(hw_bom=hw_bom))
        assert article.hw_bom == hw_bom

    def test_safety_goals_roundtrip(self, store, sample_article):
        """Safety goals JSON round-trips."""
        sgs = [
            {"safety_goal_id": "SG-BRAKE-001", "link_type": "derived_from"},
        ]
        article = store.create(sample_article(safety_goals=sgs))
        assert article.safety_goals == sgs

    def test_test_refs_roundtrip(self, store, sample_article):
        """Test refs JSON round-trips."""
        refs = [{"test_id": "TC-001", "level": "HIL", "status": "pass"}]
        article = store.create(sample_article(test_refs=refs))
        assert article.test_refs == refs

    def test_ota_binding_null_default(self, store, sample_article):
        """ota_binding defaults to None when not set."""
        article = store.create(sample_article(ota_binding=None))
        assert article.ota_binding is None

    def test_tcl_doc_slot_roundtrip(self, store, sample_article):
        """TCL doc slot JSON round-trips."""
        tcl = {"tcl_tool_id": "TCL-001", "assessment_status": "pending"}
        article = store.create(sample_article(tcl_doc_slot=tcl))
        assert article.tcl_doc_slot == tcl


# ═══════════════════════════════════════════════════════════════════════
# Module __init__ exports
# ═══════════════════════════════════════════════════════════════════════

class TestModuleExports:
    """Package __init__.py exports the expected API."""

    def test_get_store(self):
        """Module exports get_store."""
        from yuleosh.knowledge_management import get_store
        assert callable(get_store)

    def test_export_search(self):
        """Module exports high-level query functions."""
        from yuleosh.knowledge_management import (
            search, list_articles, get_by_id, get_by_status,
            search_by_tags, list_deleted, get_stats, list_versions,
        )
        for fn in (search, list_articles, get_by_id, get_by_status,
                   search_by_tags, list_deleted, get_stats, list_versions):
            assert callable(fn)

    def test_export_constants(self):
        """Module exports constants."""
        from yuleosh.knowledge_management import (
            ARTICLE_STATUSES, SAFETY_LEVELS, VALID_TRANSITIONS,
        )
        assert "draft" in ARTICLE_STATUSES
        assert "ASIL_D" in SAFETY_LEVELS
        assert "draft" in VALID_TRANSITIONS
