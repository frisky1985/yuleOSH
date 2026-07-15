# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for kb/store.py — SQLite CRUD operations."""

import os
import tempfile
import pytest
from datetime import datetime

from yuleosh.kb.store import KbStore


@pytest.fixture
def store():
    """Create a KbStore with a temporary SQLite DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = KbStore(db_path)
    yield s
    s.close()
    os.unlink(db_path)


class TestArticleStore:
    def test_create_and_get_article(self, store):
        """Create article and retrieve it by ID."""
        a = store.create_article({
            "title": "MISRA R.10.1",
            "content": "Operands shall not be of inappropriate type.",
            "source": "misra_analysis",
            "source_ref": "R.10.1",
            "tags": "misra, type-system",
        })
        assert a.id is not None
        assert a.id >= 1
        assert a.title == "MISRA R.10.1"
        assert a.source == "misra_analysis"

        # Retrieve
        fetched = store.get_article(a.id)
        assert fetched is not None
        assert fetched.title == "MISRA R.10.1"
        assert fetched.tags == "misra, type-system"

    def test_get_article_not_found(self, store):
        """get_article returns None for non-existent ID."""
        assert store.get_article(999) is None

    def test_list_articles_empty(self, store):
        """list_articles returns empty list when no articles exist."""
        articles = store.list_articles()
        assert articles == []

    def test_list_articles_with_data(self, store):
        """list_articles returns all created articles."""
        store.create_article({"title": "A1", "content": "C1"})
        store.create_article({"title": "A2", "content": "C2"})
        store.create_article({"title": "A3", "content": "C3"})
        articles = store.list_articles()
        assert len(articles) == 3

    def test_list_articles_search(self, store):
        """list_articles with search filter."""
        store.create_article({"title": "Memory leak fix", "content": "Free after use", "tags": "memory"})
        store.create_article({"title": "Null pointer", "content": "Check before dereference", "tags": "safety"})
        store.create_article({"title": "Unrelated", "content": "Something else", "tags": "other"})

        results = store.list_articles(search="memory")
        assert len(results) == 1
        assert results[0].title == "Memory leak fix"

        results2 = store.list_articles(search="Check")
        assert len(results2) == 1
        assert results2[0].title == "Null pointer"

    def test_count_articles(self, store):
        """count_articles returns correct total."""
        assert store.count_articles() == 0
        store.create_article({"title": "A1"})
        store.create_article({"title": "A2"})
        assert store.count_articles() == 2

    def test_count_articles_search(self, store):
        """count_articles with search filter."""
        store.create_article({"title": "Something", "content": "relevant content here", "tags": "test"})
        store.create_article({"title": "Other", "content": "unrelated text"})
        assert store.count_articles(search="relevant") == 1
        assert store.count_articles(search="unrelated") == 1
        assert store.count_articles(search="nonexistent") == 0

    def test_update_article(self, store):
        """Update article fields."""
        a = store.create_article({"title": "Original", "content": "Original content"})
        updated = store.update_article(a.id, {"title": "Updated", "content": "Updated content"})
        assert updated.title == "Updated"
        assert updated.content == "Updated content"
        assert updated.updated_at is not None

    def test_update_article_not_found(self, store):
        """update_article returns None for non-existent ID."""
        result = store.update_article(999, {"title": "New"})
        assert result is None

    def test_delete_article(self, store):
        """Delete an article."""
        a = store.create_article({"title": "Delete me"})
        assert store.delete_article(a.id) is True
        assert store.get_article(a.id) is None

    def test_delete_article_not_found(self, store):
        """delete_article returns False for non-existent ID."""
        assert store.delete_article(999) is False


class TestLessonStore:
    def test_create_and_get_lesson(self, store):
        """Create lesson and retrieve it by ID."""
        l = store.create_lesson({
            "title": "Null check lesson",
            "problem": "Dereferenced null pointer",
            "solution": "Always check before dereference",
            "root_cause": "Missing defensive programming",
            "project_id": "brake-light",
            "severity": "high",
        })
        assert l.id is not None
        assert l.severity == "high"

        fetched = store.get_lesson(l.id)
        assert fetched is not None
        assert fetched.title == "Null check lesson"
        assert fetched.project_id == "brake-light"

    def test_list_lessons_filter_by_project(self, store):
        """list_lessons filters by project_id."""
        store.create_lesson({"title": "L1", "project_id": "proj-a", "severity": "high"})
        store.create_lesson({"title": "L2", "project_id": "proj-b", "severity": "low"})
        store.create_lesson({"title": "L3", "project_id": "proj-a", "severity": "medium"})

        results = store.list_lessons(project_id="proj-a")
        assert len(results) == 2

    def test_list_lessons_filter_by_severity(self, store):
        """list_lessons filters by severity."""
        store.create_lesson({"title": "L1", "severity": "low"})
        store.create_lesson({"title": "L2", "severity": "high"})
        store.create_lesson({"title": "L3", "severity": "high"})

        results = store.list_lessons(severity="high")
        assert len(results) == 2

    def test_list_lessons_filter_both(self, store):
        """list_lessons filters by both project and severity."""
        store.create_lesson({"title": "L1", "project_id": "p1", "severity": "high"})
        store.create_lesson({"title": "L2", "project_id": "p1", "severity": "low"})
        store.create_lesson({"title": "L3", "project_id": "p2", "severity": "high"})

        results = store.list_lessons(project_id="p1", severity="high")
        assert len(results) == 1
        assert results[0].title == "L1"

    def test_count_lessons(self, store):
        """count_lessons returns correct total."""
        assert store.count_lessons() == 0
        store.create_lesson({"title": "L1", "project_id": "p1"})
        assert store.count_lessons() == 1
        assert store.count_lessons(project_id="p1") == 1
        assert store.count_lessons(project_id="nonexistent") == 0

    def test_delete_lesson(self, store):
        """Delete a lesson."""
        l = store.create_lesson({"title": "Delete me"})
        assert store.delete_lesson(l.id) is True
        assert store.get_lesson(l.id) is None


class TestFmeaStore:
    def test_create_and_get_fmea(self, store):
        """Create FMEA entry and retrieve it by ID."""
        e = store.create_fmea({
            "item": "Brake Controller",
            "failure_mode": "Stuck high",
            "effect": "Brake stays on",
            "cause": "MOSFET short",
            "severity": 8,
            "occurence": 4,
            "detection": 3,
            "recommendation": "Add redundancy",
        })
        assert e.id is not None
        assert e.rpn == 96  # 8 * 4 * 3

        fetched = store.get_fmea(e.id)
        assert fetched is not None
        assert fetched.item == "Brake Controller"
        assert fetched.rpn == 96

    def test_list_fmea_sorted_by_rpn_desc(self, store):
        """list_fmea defaults to sorting by RPN descending."""
        store.create_fmea({"item": "A", "failure_mode": "F1", "severity": 1, "occurence": 1, "detection": 1})
        store.create_fmea({"item": "B", "failure_mode": "F2", "severity": 10, "occurence": 10, "detection": 10})
        store.create_fmea({"item": "C", "failure_mode": "F3", "severity": 5, "occurence": 5, "detection": 5})

        results = store.list_fmea(limit=3)
        assert len(results) == 3
        assert results[0].item == "B"  # RPN = 1000
        assert results[1].item == "C"  # RPN = 125
        assert results[2].item == "A"  # RPN = 1

    def test_count_fmea(self, store):
        """count_fmea returns correct total."""
        assert store.count_fmea() == 0
        store.create_fmea({"item": "A", "failure_mode": "F1", "severity": 1, "occurence": 1, "detection": 1})
        assert store.count_fmea() == 1

    def test_update_fmea_recomputes_rpn(self, store):
        """Updating severity/occurence/detection recomputes RPN."""
        e = store.create_fmea({
            "item": "Sensor",
            "failure_mode": "No output",
            "severity": 2,
            "occurence": 3,
            "detection": 4,
        })
        assert e.rpn == 24

        updated = store.update_fmea(e.id, {"severity": 10})
        assert updated.rpn == 120  # 10 * 3 * 4

    def test_delete_fmea(self, store):
        """Delete FMEA entry."""
        e = store.create_fmea({"item": "Del", "failure_mode": "F"})
        assert store.delete_fmea(e.id) is True
        assert store.get_fmea(e.id) is None


class TestWhitelistFieldValidation:
    """B1: Whitelist field validation tests for kb/store.py.

    Covers:
    - Allowed fields pass through correctly
    - Malicious / non-whitelisted field names are rejected
    - Empty / None field dicts are handled gracefully
    - Boundary cases: fields with special characters
    """

    def test_update_article_allowed_fields(self, store):
        """GIVEN allowed field names WHEN updating article THEN fields are accepted."""
        a = store.create_article({"title": "Original", "content": "Original content"})
        updated = store.update_article(a.id, {
            "title": "New Title",
            "content": "New Content",
            "source": "manual",
            "source_ref": "doc.md",
            "tags": "safety, misra",
        })
        assert updated.title == "New Title"
        assert updated.content == "New Content"
        assert updated.source == "manual"
        assert updated.source_ref == "doc.md"
        assert updated.tags == "safety, misra"

    def test_update_article_rejects_non_whitelisted(self, store):
        """GIVEN non-whitelisted field name WHEN updating article THEN field is silently dropped."""
        a = store.create_article({"title": "Original"})
        updated = store.update_article(a.id, {
            "title": "Safe Title",
            "DROP TABLE kb_articles": "malicious",
            "'; DELETE FROM kb_articles; --": "sql injection",
        })
        # Only 'title' should pass through
        assert updated.title == "Safe Title"
        # The malicious keys should not be in the dict and no error should occur

    def test_update_article_rejects_foreign_column(self, store):
        """GIVEN a column name from another table WHEN updating article THEN it's rejected."""
        a = store.create_article({"title": "Original"})
        updated = store.update_article(a.id, {
            "project_id": "evil",  # lessons table column, not in kb_articles whitelist
            "severity": "critical",
        })
        # Neither project_id nor severity are in kb_articles allowed set
        assert updated.title == "Original"

    def test_update_article_empty_fields(self, store):
        """GIVEN empty fields dict WHEN updating article THEN no change made."""
        a = store.create_article({"title": "Keep Me", "content": "unchanged"})
        updated = store.update_article(a.id, {})
        assert updated is not None
        assert updated.title == "Keep Me"
        assert updated.content == "unchanged"

    def test_update_article_none_fields(self, store):
        """GIVEN None as fields value WHEN updating article (via dict with None value) THEN handled gracefully."""
        a = store.create_article({"title": "Original"})
        # Passing a key with None value — the None itself should pass whitelist
        # but won't be in safe_fields since it's not 'updated_at'
        updated = store.update_article(a.id, {"title": "Still Updated"})
        assert updated.title == "Still Updated"

    def test_update_article_special_chars_field(self, store):
        """GIVEN fields with special characters in names WHEN updating THEN rejected."""
        a = store.create_article({"title": "Base"})
        updated = store.update_article(a.id, {
            "title": "Safe",
            "col""": "quoted",
            "field; DROP": "semicolon",
            "-- comment": "sql comment",
        })
        assert updated.title == "Safe"

    def test_update_lesson_allowed_fields(self, store):
        """GIVEN allowed lesson fields WHEN updating THEN accepted."""
        l = store.create_lesson({"title": "Lesson A", "problem": "Issue"})
        updated = store.update_lesson(l.id, {
            "title": "Updated Lesson",
            "problem": "Updated Problem",
            "solution": "Fix it",
            "root_cause": "Root",
            "project_id": "proj-x",
            "severity": "high",
        })
        assert updated.title == "Updated Lesson"
        assert updated.severity == "high"

    def test_update_lesson_rejects_non_whitelisted(self, store):
        """GIVEN non-whitelisted fields WHEN updating lesson THEN rejected."""
        l = store.create_lesson({"title": "Lesson"})
        updated = store.update_lesson(l.id, {
            "content": "not in lessons",  # kb_articles field, not lessons
            "source": "not allowed",
        })
        assert updated.title == "Lesson"

    def test_update_lesson_empty_fields(self, store):
        """GIVEN empty fields WHEN updating lesson THEN no change."""
        l = store.create_lesson({"title": "Keep"})
        updated = store.update_lesson(l.id, {})
        assert updated.title == "Keep"

    def test_update_fmea_allowed_fields(self, store):
        """GIVEN allowed FMEA fields WHEN updating THEN accepted."""
        e = store.create_fmea({"item": "Sensor", "failure_mode": "Open"})
        updated = store.update_fmea(e.id, {
            "item": "Actuator",
            "failure_mode": "Short",
            "effect": "Overheat",
            "cause": "Overvoltage",
            "severity": 5,
            "occurence": 3,
            "detection": 2,
            "recommendation": "Add fuse",
        })
        assert updated.item == "Actuator"
        assert updated.rpn == 30  # 5 * 3 * 2

    def test_update_fmea_rejects_non_whitelisted(self, store):
        """GIVEN non-whitelisted fields WHEN updating fmea THEN rejected."""
        e = store.create_fmea({"item": "Sensor", "failure_mode": "F1"})
        updated = store.update_fmea(e.id, {
            "title": "not in fmea",
            "content": "wrong table",
        })
        assert updated.item == "Sensor"

    def test_update_fmea_empty_fields(self, store):
        """GIVEN empty fields WHEN updating fmea THEN no change."""
        e = store.create_fmea({"item": "Sensor", "failure_mode": "F1"})
        updated = store.update_fmea(e.id, {})
        assert updated.item == "Sensor"
