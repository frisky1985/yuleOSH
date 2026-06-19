#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for Agent Traceability (DEF-010 / G-47).
"""

import os
import sys
import tempfile
import json
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ci.agent_traceability import (
    record_review,
    get_reviews_for_commit,
    get_commits_for_review,
    get_findings_for_file,
    get_reviews_by_build,
    show_traceability,
    validate_traceability_file,
)


class TestAgentTraceability:
    """Test agent traceability recording and querying."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True)
            yield tmpdir

    def test_record_review(self, temp_project):
        """Verify review session recording (G-47 §19.1)."""
        findings = [
            {"file": "src/main.c", "line": 42, "severity": "error",
             "message": "Null pointer dereference", "rule_id": "Rule-11.5"},
            {"file": "src/gpio.c", "line": 15, "severity": "warning",
             "message": "Missing GPIO pull-up", "rule_id": "Rule-12.1"},
        ]
        entry = record_review(
            temp_project,
            review_type="code-review",
            findings=findings,
            commit="abc123def456",
            build_id="BLD-20260619-001",
            agent_name="小克",
        )
        assert entry["review_id"].startswith("RVW-")
        assert entry["commit"] == "abc123def456"
        assert entry["build_id"] == "BLD-20260619-001"
        assert entry["finding_count"] == 2
        assert entry["agent_name"] == "小克"
        assert entry["findings"][0]["location"] == "src/main.c:42"

    def test_get_reviews_for_commit(self, temp_project):
        """Verify commit → review lookup (G-47 §19.1)."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123def456", build_id="b1", agent_name="小克",
            findings=[{"file": "main.c", "line": 1}],
        )
        reviews = get_reviews_for_commit(temp_project, "abc123")
        assert len(reviews) >= 1
        assert reviews[0]["review_type"] == "code-review"

    def test_get_commits_for_review(self, temp_project):
        """Verify review → commit lookup (G-47 §19.1)."""
        entry = record_review(
            temp_project, review_type="arch-review",
            commit="xyz789", build_id="b2", agent_name="小马",
            findings=[{"file": "arch.md", "line": 10}],
        )
        reviews = get_commits_for_review(temp_project, entry["review_id"])
        assert len(reviews) >= 1
        assert reviews[0]["commit"] == "xyz789"

    def test_get_findings_for_file(self, temp_project):
        """Verify file → findings lookup (G-47 §19.2)."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123", build_id="b3", agent_name="小克",
            findings=[{"file": "src/main.c", "line": 42, "severity": "error", "message": "Bad",
                       "category": "safety"}],
        )
        findings = get_findings_for_file(temp_project, "main.c")
        assert len(findings) >= 1
        assert findings[0]["location"] == "src/main.c:42"

    def test_get_reviews_by_build(self, temp_project):
        """Verify build → reviews lookup (G-47 §19.3)."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123", build_id="BLD-20260619-XYZ", agent_name="小克",
            findings=[{"file": "main.c"}],
        )
        reviews = get_reviews_by_build(temp_project, "BLD-20260619")
        assert len(reviews) >= 1

    def test_show_traceability(self, temp_project):
        """Verify formatted output."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123", build_id="b1", agent_name="小克",
            findings=[{"file": "main.c"}],
        )
        output = show_traceability(temp_project)
        assert "Agent" in output or "Traceability" in output

    def test_show_traceability_json(self, temp_project):
        """Verify JSON output."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123", build_id="b1", agent_name="小克",
            findings=[{"file": "main.c"}],
        )
        output = show_traceability(temp_project, as_json=True)
        data = json.loads(output)
        assert len(data) >= 1

    def test_validate_traceability_file(self, temp_project):
        """Verify JSONL file validation."""
        record_review(
            temp_project, review_type="code-review",
            commit="abc123", build_id="b1", agent_name="小克",
            findings=[{"file": "main.c"}],
        )
        result = validate_traceability_file(temp_project)
        assert result["valid"] is True
        assert result["entry_count"] >= 1

    def test_multiple_reviews_same_commit(self, temp_project):
        """Verify multiple reviews on same commit are tracked."""
        record_review(temp_project, review_type="code-review",
                      commit="abc123", build_id="b1", agent_name="小克",
                      findings=[{"file": "a.c"}])
        record_review(temp_project, review_type="arch-review",
                      commit="abc123", build_id="b2", agent_name="小马",
                      findings=[{"file": "b.c"}])
        reviews = get_reviews_for_commit(temp_project, "abc123")
        assert len(reviews) >= 2
