# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for kb/models.py — dataclass models and sanitization helpers."""

import pytest
from datetime import datetime

from yuleosh.kb.models import (
    KbArticle,
    Lesson,
    FmeaEntry,
    sanitize_kb_article_fields,
    sanitize_lesson_fields,
    sanitize_fmea_fields,
)


class TestKbArticle:
    def test_to_dict(self):
        """KbArticle.to_dict() returns correct dict."""
        a = KbArticle(
            id=1,
            title="Test Title",
            content="# Markdown content",
            source="misra_analysis",
            source_ref="R.10.1",
            tags="misra, safety",
            created_at=datetime(2025, 1, 15, 10, 30),
            updated_at=datetime(2025, 1, 15, 12, 0),
        )
        d = a.to_dict()
        assert d["id"] == 1
        assert d["title"] == "Test Title"
        assert d["source"] == "misra_analysis"
        assert d["tags"] == "misra, safety"
        assert d["created_at"] == "2025-01-15T10:30:00"
        assert d["updated_at"] == "2025-01-15T12:00:00"

    def test_from_dict(self):
        """KbArticle.from_dict() reconstructs from dict."""
        d = {
            "id": 2,
            "title": "From Dict",
            "content": "body",
            "source": "manual",
            "source_ref": "",
            "tags": "",
            "created_at": "2025-06-01T08:00:00",
        }
        a = KbArticle.from_dict(d)
        assert a.id == 2
        assert a.title == "From Dict"
        assert a.created_at == datetime(2025, 6, 1, 8, 0)
        assert a.updated_at is None

    def test_from_dict_with_empty(self):
        """KbArticle.from_dict() handles missing fields."""
        a = KbArticle.from_dict({"id": 3})
        assert a.id == 3
        assert a.title == ""
        assert a.content == ""

    def test_to_dict_no_dates(self):
        """KbArticle.to_dict() handles None dates."""
        a = KbArticle(id=5, title="No dates")
        d = a.to_dict()
        assert d["created_at"] is None
        assert d["updated_at"] is None

    def test_sanitize_allows_valid_fields(self):
        """sanitize_kb_article_fields only keeps allowed fields."""
        body = {
            "title": "Hello",
            "content": "World",
            "source": "manual",
            "source_ref": "abc",
            "tags": "c, embedded",
            "extra_field": "should be dropped",
            "id": 999,
        }
        cleaned = sanitize_kb_article_fields(body)
        assert cleaned["title"] == "Hello"
        assert cleaned["content"] == "World"
        assert cleaned["source"] == "manual"
        assert "extra_field" not in cleaned
        assert "id" not in cleaned

    def test_sanitize_strips_non_string(self):
        """sanitize_kb_article_fields drops non-string values."""
        body = {"title": "OK", "content": 12345}
        cleaned = sanitize_kb_article_fields(body)
        assert cleaned["title"] == "OK"
        assert "content" not in cleaned


class TestLesson:
    def test_to_dict(self):
        """Lesson.to_dict() returns correct dict."""
        l = Lesson(
            id=1,
            title="Bad pointer usage",
            problem="Dangling pointer after free",
            solution="Set pointer to NULL after free",
            root_cause="Missing null assignment",
            project_id="brake-light",
            severity="high",
            created_at=datetime(2025, 3, 10, 14, 0),
        )
        d = l.to_dict()
        assert d["id"] == 1
        assert d["title"] == "Bad pointer usage"
        assert d["severity"] == "high"
        assert d["project_id"] == "brake-light"

    def test_from_dict(self):
        """Lesson.from_dict() reconstructs from dict."""
        d = {
            "id": 2,
            "title": "Test",
            "problem": "P",
            "solution": "S",
            "root_cause": "R",
            "project_id": "proj",
            "severity": "critical",
        }
        l = Lesson.from_dict(d)
        assert l.title == "Test"
        assert l.severity == "critical"

    def test_from_dict_invalid_severity(self):
        """Lesson.from_dict() defaults to 'medium' for invalid severity."""
        d = {"title": "T", "severity": "unknown"}
        l = Lesson.from_dict(d)
        assert l.severity == "medium"

    def test_valid_severities_enum(self):
        """VALID_SEVERITIES contains expected values."""
        assert Lesson.VALID_SEVERITIES == {"low", "medium", "high", "critical"}

    def test_sanitize_lesson_fields(self):
        """sanitize_lesson_fields only keeps allowed fields."""
        body = {
            "title": "Lesson",
            "problem": "P",
            "solution": "S",
            "root_cause": "R",
            "project_id": "brake",
            "severity": "high",
            "id": 999,
            "extra": "x",
        }
        cleaned = sanitize_lesson_fields(body)
        assert cleaned["title"] == "Lesson"
        assert cleaned["severity"] == "high"
        assert "id" not in cleaned
        assert "extra" not in cleaned

    def test_sanitize_lesson_defaults_severity(self):
        """sanitize_lesson_fields defaults invalid severity to 'medium'."""
        cleaned = sanitize_lesson_fields({"severity": "invalid"})
        assert cleaned["severity"] == "medium"


class TestFmeaEntry:
    def test_to_dict(self):
        """FmeaEntry.to_dict() returns correct dict with computed RPN."""
        e = FmeaEntry(
            id=1,
            item="Brake Controller",
            failure_mode="Stuck high",
            effect="Brake always on",
            cause="MOSFET short",
            severity=8,
            occurence=4,
            detection=3,
            recommendation="Add redundancy",
            created_at=datetime(2025, 4, 1, 9, 0),
        )
        d = e.to_dict()
        assert d["item"] == "Brake Controller"
        assert d["severity"] == 8
        assert d["occurence"] == 4
        assert d["detection"] == 3
        assert d["rpn"] == 96  # 8 * 4 * 3

    def test_rpn_recomputed_on_post_init(self):
        """FmeaEntry rpn is computed in __post_init__."""
        e = FmeaEntry(severity=5, occurence=6, detection=7)
        assert e.rpn == 210

    def test_rpn_recomputed_on_to_dict(self):
        """FmeaEntry rpn is recomputed on to_dict()."""
        e = FmeaEntry(severity=2, occurence=3, detection=4)
        d = e.to_dict()
        assert d["rpn"] == 24

        # Modify after init
        e.severity = 10
        d2 = e.to_dict()
        assert d2["rpn"] == 120  # 10 * 3 * 4

    def test_from_dict(self):
        """FmeaEntry.from_dict() reconstructs."""
        d = {
            "item": "Sensor",
            "failure_mode": "No output",
            "effect": "No reading",
            "cause": "Wire broken",
            "severity": 6,
            "occurence": 2,
            "detection": 5,
            "recommendation": "Use shielded cable",
        }
        e = FmeaEntry.from_dict(d)
        assert e.item == "Sensor"
        assert e.rpn == 60

    def test_sanitize_fmea_fields(self):
        """sanitize_fmea_fields keeps allowed fields and clamps numbers."""
        body = {
            "item": "Motor",
            "failure_mode": "Overheat",
            "effect": "Fire",
            "cause": "Overcurrent",
            "severity": "11",
            "occurence": "0",
            "detection": "-1",
            "recommendation": "Add fuse",
            "extra": "x",
        }
        cleaned = sanitize_fmea_fields(body)
        assert cleaned["item"] == "Motor"
        assert cleaned["severity"] == 10   # clamped
        assert cleaned["occurence"] == 1   # clamped
        assert cleaned["detection"] == 1   # clamped
        assert "extra" not in cleaned

    def test_sanitize_fmea_defaults(self):
        """sanitize_fmea_fields defaults missing numeric to 1."""
        cleaned = sanitize_fmea_fields({"item": "X", "failure_mode": "Y"})
        assert cleaned["severity"] == 1
        assert cleaned["occurence"] == 1
        assert cleaned["detection"] == 1

    def test_sanitize_fmea_non_numeric_defaults_to_1(self):
        """Non-numeric severity/occurence/detection defaults to 1."""
        cleaned = sanitize_fmea_fields({
            "item": "X",
            "failure_mode": "Y",
            "severity": "abc",
        })
        assert cleaned["severity"] == 1
