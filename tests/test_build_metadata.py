#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for Build Metadata Persistence (DEF-009 / G-48).
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ci.build_metadata import (
    record_build,
    get_build_metadata,
    get_build_chain,
    validate_metadata_integrity,
    show_build_metadata,
    REQUIRED_FIELDS,
)


class TestBuildMetadata:
    """Test build metadata recording and retrieval."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize git repo for commit hash detection
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True)
            yield tmpdir

    def test_record_build(self, temp_project):
        """Verify build metadata is recorded."""
        entry = record_build(
            temp_project,
            commit="abc123def456",
            status="passed",
            layer=1,
        )
        assert entry["build_id"] is not None
        assert entry["commit"] == "abc123def456"
        assert entry["status"] == "passed"
        assert entry["layer"] == 1
        assert "tool_versions" in entry
        assert "timestamp" in entry

    def test_record_build_required_fields(self, temp_project):
        """Verify all required fields are present (G-48 §20.2)."""
        entry = record_build(
            temp_project,
            commit="abc123def456",
            status="passed",
            layer=1,
        )
        for field in REQUIRED_FIELDS:
            assert field in entry, f"Missing required field: {field}"

    def test_get_build_metadata(self, temp_project):
        """Verify metadata retrieval."""
        record_build(temp_project, commit="abc123", status="passed", layer=1)
        entries = get_build_metadata(temp_project, limit=1)
        assert len(entries) >= 1
        assert entries[0]["commit"] == "abc123"

    def test_get_build_chain(self, temp_project):
        """Verify build chain retrieval by commit (G-48 §20.4)."""
        record_build(temp_project, commit="abc123", status="passed", layer=1)
        record_build(temp_project, commit="abc123", status="warning", layer=2)
        chain = get_build_chain(temp_project, "abc123")
        assert len(chain) >= 2

    def test_validate_integrity(self, temp_project):
        """Verify metadata file integrity validation (G-48 §20.5)."""
        record_build(temp_project, commit="abc123", status="passed", layer=1)
        result = validate_metadata_integrity(temp_project)
        assert result["valid"] is True
        assert result["entry_count"] >= 1

    def test_show_build_metadata(self, temp_project):
        """Verify formatted output."""
        record_build(temp_project, commit="abc123", status="passed", layer=1)
        output = show_build_metadata(temp_project)
        assert "Build Metadata" in output

    def test_show_build_metadata_json(self, temp_project):
        """Verify JSON output."""
        record_build(temp_project, commit="abc123", status="passed", layer=1)
        output = show_build_metadata(temp_project, as_json=True)
        data = json.loads(output)
        assert len(data) >= 1

    def test_tool_versions_captured(self, temp_project):
        """Verify tool versions are captured."""
        entry = record_build(temp_project, commit="abc123", status="passed", layer=1)
        # At minimum should have python version
        assert "tool_versions" in entry
        assert "python" in entry["tool_versions"]
