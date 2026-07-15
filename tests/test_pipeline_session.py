#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for pipeline/session.py — PipelineSession, PipelineStepError.

Target: 90%+ statement + branch coverage.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError


# ==================================================================
# PipelineStepError
# ==================================================================


class TestPipelineStepError:
    def test_is_runtime_error(self):
        assert issubclass(PipelineStepError, RuntimeError)

    def test_can_be_raised_with_message(self):
        with pytest.raises(PipelineStepError, match="something went wrong"):
            raise PipelineStepError("something went wrong")

    def test_can_be_raised_without_message(self):
        with pytest.raises(PipelineStepError):
            raise PipelineStepError()

    def test_can_catch_as_runtime_error(self):
        try:
            raise PipelineStepError("test error")
        except RuntimeError as e:
            assert str(e) == "test error"


# ==================================================================
# PipelineSession
# ==================================================================


class TestPipelineSessionInit:
    """Tests for PipelineSession.__init__"""

    def test_creates_session_with_name_and_spec(self):
        with mock.patch.dict(os.environ, {"OSH_HOME": tempfile.gettempdir()}):
            session = PipelineSession(name="test-session", spec_path="/tmp/spec.md")
        assert session.name == "test-session"
        assert session.spec_path == str(Path("/tmp/spec.md").resolve())
        assert session.status == "created"
        assert session.current_step == 0
        assert session.steps == []
        assert session.artifacts == {}
        assert session.errors == []
        assert session.token_usage_total == 0
        assert session.token_usage_steps == []

    def test_created_at_is_set(self):
        with mock.patch.dict(os.environ, {"OSH_HOME": tempfile.gettempdir()}):
            session = PipelineSession("test", "/tmp/spec.md")
        assert session.created_at is not None
        assert session.updated_at is not None
        assert session.updated_at == session.created_at

    def test_session_dir_is_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                session = PipelineSession("test-session", "/tmp/spec.md")
                assert session.session_dir.exists()
                assert session.session_dir.name == "test-session"
                assert ".osh" in str(session.session_dir)
                assert "sessions" in str(session.session_dir)

    def test_llm_client_stored(self):
        llm = mock.Mock()
        with mock.patch.dict(os.environ, {"OSH_HOME": tempfile.gettempdir()}):
            session = PipelineSession("test", "/tmp/spec.md", llm_client=llm)
        assert session.llm_client is llm

    def test_llm_client_none_default(self):
        with mock.patch.dict(os.environ, {"OSH_HOME": tempfile.gettempdir()}):
            session = PipelineSession("test", "/tmp/spec.md")
        assert session.llm_client is None


class TestPipelineSessionSteps:
    """Tests for step management methods."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env_patch = mock.patch.dict(os.environ, {"OSH_HOME": self.tmpdir.name})
        self.env_patch.start()
        self.session = PipelineSession("step-test", "/tmp/spec.md")

    def teardown_method(self):
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def test_add_step_returns_step_dict(self):
        step = self.session.add_step("spec-check", "小明", "验证")
        assert step["name"] == "spec-check"
        assert step["agent"] == "小明"
        assert step["action"] == "验证"
        assert step["status"] == "pending"
        assert step["started_at"] is None
        assert step["completed_at"] is None
        assert step["output_path"] is None
        assert step["errors"] == []
        assert step["step"] == 1  # first step

    def test_add_step_increments_step_number(self):
        self.session.add_step("step1", "agent1", "action1")
        self.session.add_step("step2", "agent2", "action2")
        assert len(self.session.steps) == 2
        assert self.session.steps[0]["step"] == 1
        assert self.session.steps[1]["step"] == 2

    def test_start_step_marks_running(self):
        step = self.session.add_step("build", "Claude", "生成")
        self.session.start_step(0)
        assert self.session.current_step == 0
        assert self.session.steps[0]["status"] == "running"
        assert self.session.steps[0]["started_at"] is not None
        # Started at is ISO format
        assert "T" in str(self.session.steps[0]["started_at"])

    def test_start_step_invalid_index_does_nothing(self):
        self.session.add_step("build", "Claude", "生成")
        # Should not raise
        self.session.start_step(99)
        assert self.session.steps[0]["status"] == "pending"

    def test_complete_step_marks_completed(self):
        self.session.add_step("build", "Claude", "生成")
        self.session.start_step(0)
        self.session.complete_step(0, "/tmp/output/report.json")
        assert self.session.steps[0]["status"] == "completed"
        assert self.session.steps[0]["completed_at"] is not None
        assert self.session.steps[0]["output_path"] == "/tmp/output/report.json"
        assert self.session.updated_at >= self.session.created_at

    def test_complete_step_invalid_index_does_nothing(self):
        self.session.add_step("build", "Claude", "生成")
        self.session.complete_step(99, "/tmp/output")
        assert self.session.steps[0]["status"] == "pending"

    def test_fail_step_records_error(self):
        self.session.add_step("build", "Claude", "生成")
        self.session.fail_step(0, "Build failed: compile error")
        assert self.session.steps[0]["status"] == "failed"
        assert self.session.steps[0]["completed_at"] is not None
        assert "Build failed: compile error" in self.session.steps[0]["errors"]
        assert "Build failed: compile error" in self.session.errors
        assert self.session.status == "failed"

    def test_fail_step_multiple_errors(self):
        self.session.add_step("build", "Claude", "生成")
        self.session.fail_step(0, "Error 1")
        # Status stays failed, second call with same step adds more errors
        self.session.steps[0]["errors"].append("Error 2")
        assert len(self.session.steps[0]["errors"]) == 2

    def test_fail_step_invalid_index(self):
        self.session.add_step("build", "Claude", "生成")
        self.session.fail_step(99, "error")
        assert self.session.steps[0]["status"] == "pending"
        assert self.session.status == "created"  # unchanged


class TestPipelineSessionArtifacts:
    """Tests for artifact management."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env_patch = mock.patch.dict(os.environ, {"OSH_HOME": self.tmpdir.name})
        self.env_patch.start()
        self.session = PipelineSession("artifact-test", "/tmp/spec.md")

    def teardown_method(self):
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def test_set_artifact(self):
        self.session.set_artifact("coverage", "/tmp/output/coverage.xml")
        assert self.session.artifacts["coverage"] == "/tmp/output/coverage.xml"

    def test_set_artifact_overwrites(self):
        self.session.set_artifact("report", "/tmp/report1.json")
        self.session.set_artifact("report", "/tmp/report2.json")
        assert self.session.artifacts["report"] == "/tmp/report2.json"

    def test_set_artifact_multiple_keys(self):
        self.session.set_artifact("cov", "/tmp/cov.xml")
        self.session.set_artifact("test", "/tmp/test.xml")
        assert len(self.session.artifacts) == 2


class TestPipelineSessionPersistence:
    """Tests for session save/load via _save and to_dict."""

    def setup_method(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.env_patch = mock.patch.dict(os.environ, {"OSH_HOME": self.tmpdir.name})
        self.env_patch.start()
        self.session = PipelineSession("persist-test", "/tmp/spec.md")

    def teardown_method(self):
        self.env_patch.stop()
        self.tmpdir.cleanup()

    def test_to_dict_includes_all_fields(self):
        d = self.session.to_dict()
        assert d["name"] == "persist-test"
        assert d["spec_path"] is not None
        assert "spec.md" in d["spec_path"]
        assert d["status"] == "created"
        assert d["current_step"] == 0
        assert d["created_at"] is not None
        assert d["updated_at"] is not None
        assert d["steps"] == []
        assert d["artifacts"] == {}
        assert d["errors"] == []

    def test_to_dict_with_steps(self):
        self.session.add_step("step1", "a1", "act1")
        self.session.add_step("step2", "a2", "act2")
        self.session.start_step(0)
        self.session.complete_step(0, "/tmp/out")
        d = self.session.to_dict()
        assert len(d["steps"]) == 2
        assert d["steps"][0]["status"] == "completed"
        assert d["steps"][1]["status"] == "pending"

    def test_to_dict_with_artifacts_and_errors(self):
        self.session.set_artifact("cov", "/tmp/cov.xml")
        self.session.errors.append("warning: missing file")
        d = self.session.to_dict()
        assert d["artifacts"]["cov"] == "/tmp/cov.xml"
        assert "warning: missing file" in d["errors"]

    def test_save_writes_session_json(self):
        self.session.add_step("test", "x", "y")
        self.session._save(persist=True)
        session_file = self.session.session_dir / "session.json"
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["name"] == "persist-test"
        assert len(data["steps"]) == 1

    def test_save_non_persist_does_not_write(self):
        self.session.add_step("test", "x", "y")
        self.session._save(persist=False)
        session_file = self.session.session_dir / "session.json"
        assert not session_file.exists()

    def test_calling_save_persist_multiple_times_overwrites(self):
        self.session.add_step("step1", "a1", "a1")
        self.session._save(persist=True)
        self.session.add_step("step2", "a2", "a2")
        self.session._save(persist=True)
        session_file = self.session.session_dir / "session.json"
        data = json.loads(session_file.read_text())
        assert len(data["steps"]) == 2

    @mock.patch("yuleosh.pipeline.session.log")
    def test_store_failure_is_non_fatal(self, mock_log):
        """SQLite store failure logs warning but doesn't crash."""
        with mock.patch("yuleosh.pipeline.session._store") as mock_store:
            mock_store.save_pipeline.side_effect = Exception("DB error")
            self.session._save(persist=True)
            # Should not raise — warning logged instead
            session_file = self.session.session_dir / "session.json"
            assert session_file.exists()


class TestPipelineSessionIntegration:
    """Full flow: create, add steps, run, complete, persist."""

    def test_lifecycle_equality(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                session = PipelineSession("lifecycle", "/tmp/spec.md")

                # Add steps
                s1 = session.add_step("spec", "小明", "验证")
                s2 = session.add_step("code", "Claude", "生成")
                assert s1["step"] == 1
                assert s2["step"] == 2

                # Execute
                session.start_step(0)
                session.complete_step(0, "/tmp/output/spec.json")
                session.start_step(1)
                session.fail_step(1, "Code generation failed")
                session.set_artifact("spec", "/tmp/output/spec.json")
                session.set_artifact("error_log", "/tmp/output/errors.log")

                # Verify final state
                assert session.status == "failed"
                assert len(session.steps) == 2
                assert session.steps[0]["status"] == "completed"
                assert session.steps[1]["status"] == "failed"
                assert len(session.errors) == 1
                assert session.token_usage_total == 0

                # Check persistence
                session._save(persist=True)
                session_file = session.session_dir / "session.json"
                assert session_file.exists()
                data = json.loads(session_file.read_text())
                assert data["status"] == "failed"
                assert len(data["steps"]) == 2
