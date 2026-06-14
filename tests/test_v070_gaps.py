# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for T1.5 Prompt Version Management and T2.2 Race Condition Guard (v0.7.0)."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestPromptVersionManagement:
    """GIVEN prompt version registry WHEN querying versions THEN correct values."""

    def test_prompt_versions_dict_exists(self):
        """GIVEN prompts module WHEN imported THEN PROMPT_VERSIONS dict exists."""
        from yuleosh.pipeline.prompts import PROMPT_VERSIONS
        assert isinstance(PROMPT_VERSIONS, dict)
        assert len(PROMPT_VERSIONS) >= 6

    def test_all_steps_have_semver(self):
        """GIVEN PROMPT_VERSIONS WHEN iterating keys THEN all values are semver."""
        from yuleosh.pipeline.prompts import PROMPT_VERSIONS
        for key, version in PROMPT_VERSIONS.items():
            parts = version.split(".")
            assert len(parts) == 3, f"{key} has non-semver: {version}"
            for p in parts:
                assert p.isdigit(), f"{key} version part '{p}' not numeric"

    def test_get_prompt_versions_returns_copy(self):
        """GIVEN get_prompt_versions() WHEN called THEN returns a copy not reference."""
        from yuleosh.pipeline.prompts import get_prompt_versions, PROMPT_VERSIONS
        copy = get_prompt_versions()
        assert copy == PROMPT_VERSIONS
        copy["test-key"] = "9.9.9"
        assert "test-key" not in PROMPT_VERSIONS

    def test_get_prompt_version_known_key(self):
        """GIVEN a known step key WHEN get_prompt_version called THEN returns version."""
        from yuleosh.pipeline.prompts import get_prompt_version
        v = get_prompt_version("super-analysis")
        assert v != "0.0.0"

    def test_get_prompt_version_unknown_key(self):
        """GIVEN an unknown step key WHEN get_prompt_version called THEN returns 0.0.0."""
        from yuleosh.pipeline.prompts import get_prompt_version
        assert get_prompt_version("nonexistent") == "0.0.0"


class TestRaceConditionGuard:
    """GIVEN evidence generation WHEN pipeline is running THEN waits."""

    def test_check_pipeline_not_running_no_sessions(self):
        """GIVEN no sessions directory WHEN check THEN returns True."""
        from evidence.pack import _check_pipeline_not_running
        with tempfile.TemporaryDirectory() as td:
            assert _check_pipeline_not_running(td) is True

    def test_check_pipeline_not_running_clean_sessions(self):
        """GIVEN session JSON with 'completed' status WHEN check THEN returns True."""
        from evidence.pack import _check_pipeline_not_running
        with tempfile.TemporaryDirectory() as td:
            sessions_dir = Path(td) / ".osh" / "sessions"
            sessions_dir.mkdir(parents=True)
            sess_dir = sessions_dir / "pipeline-001"
            sess_dir.mkdir()
            (sess_dir / "session.json").write_text(
                json.dumps({"status": "completed", "name": "test-pipeline"})
            )
            assert _check_pipeline_not_running(td) is True

    def test_check_pipeline_running_detected(self):
        """GIVEN session JSON with 'running' status WHEN check THEN returns False."""
        from evidence.pack import _check_pipeline_not_running
        with tempfile.TemporaryDirectory() as td:
            sessions_dir = Path(td) / ".osh" / "sessions"
            sessions_dir.mkdir(parents=True)
            sess_dir = sessions_dir / "pipeline-active"
            sess_dir.mkdir()
            (sess_dir / "session.json").write_text(
                json.dumps({"status": "running", "name": "active-pipeline"})
            )
            assert _check_pipeline_not_running(td) is False

    def test_check_pipeline_in_progress_detected(self):
        """GIVEN session JSON with 'in_progress' status WHEN check THEN returns False."""
        from evidence.pack import _check_pipeline_not_running
        with tempfile.TemporaryDirectory() as td:
            sessions_dir = Path(td) / ".osh" / "sessions"
            sessions_dir.mkdir(parents=True)
            sess_dir = sessions_dir / "pipeline-progress"
            sess_dir.mkdir()
            (sess_dir / "session.json").write_text(
                json.dumps({"status": "in_progress", "name": "pipeline"})
            )
            assert _check_pipeline_not_running(td) is False

    def test_check_pipeline_corrupt_json_skipped(self):
        """GIVEN corrupt session JSON WHEN check THEN skips and returns True."""
        from evidence.pack import _check_pipeline_not_running
        with tempfile.TemporaryDirectory() as td:
            sessions_dir = Path(td) / ".osh" / "sessions"
            sessions_dir.mkdir(parents=True)
            sess_dir = sessions_dir / "pipeline-corrupt"
            sess_dir.mkdir()
            (sess_dir / "session.json").write_text("{invalid json ")
            assert _check_pipeline_not_running(td) is True
