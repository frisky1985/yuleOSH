"""Tests for pipeline/session.py — PipelineSession and PipelineStepError."""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from yuleosh.pipeline.session import PipelineSession, PipelineStepError


class TestPipelineStepError:
    """Test PipelineStepError exception."""

    def test_is_runtime_error(self):
        err = PipelineStepError("Something went wrong")
        assert isinstance(err, RuntimeError)
        assert str(err) == "Something went wrong"


class TestPipelineSession:
    """Test PipelineSession class."""

    def test_init(self, tmp_path):
        """Session initializes with correct defaults."""
        with patch("yuleosh.pipeline.session.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path_cls.return_value = mock_path

            session = PipelineSession("test-session", "/spec/test.md")
            assert session.name == "test-session"
            assert session.status == "created"
            assert session.current_step == 0
            assert session.steps == []
            assert session.artifacts == {}
            assert session.errors == []

    def test_add_step(self, tmp_path):
        """add_step creates step dict."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            step = session.add_step("spec-check", "小明", "Spec Check")
            assert step["name"] == "spec-check"
            assert step["agent"] == "小明"
            assert step["status"] == "pending"
            assert step["step"] == 1

    def test_start_step(self, tmp_path):
        """start_step marks step as running."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.add_step("step1", "小明", "Step 1")
            session.start_step(0)
            assert session.steps[0]["status"] == "running"
            assert session.steps[0]["started_at"] is not None

    def test_start_step_invalid(self, tmp_path):
        """start_step with invalid index does nothing."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.start_step(999)
            # No crash

    def test_complete_step(self, tmp_path):
        """complete_step marks step as completed."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.add_step("step1", "小明", "Step 1")
            session.complete_step(0, "/path/output.md")
            assert session.steps[0]["status"] == "completed"
            assert session.steps[0]["output_path"] == "/path/output.md"

    def test_fail_step(self, tmp_path):
        """fail_step marks step and session as failed."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.add_step("step1", "小明", "Step 1")
            session.fail_step(0, "Error message")
            assert session.steps[0]["status"] == "failed"
            assert session.status == "failed"
            assert len(session.errors) == 1
            assert session.errors[0] == "Error message"

    def test_set_artifact(self, tmp_path):
        """set_artifact registers artifact and persists."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.set_artifact("analysis", "/path/analysis.md")
            assert session.artifacts["analysis"] == "/path/analysis.md"

    def test_to_dict(self, tmp_path):
        """to_dict serializes session state."""
        with patch("yuleosh.pipeline.session.Path"):
            session = PipelineSession("test", "/spec.md")
            session.add_step("step1", "小明", "Step 1")
            d = session.to_dict()
            assert d["name"] == "test"
            assert d["status"] == "created"
            assert len(d["steps"]) == 1

    def test_session_dir_creation(self, tmp_path):
        """Session directory is created."""
        with patch("yuleosh.pipeline.session.os.environ.get") as mock_env:
            mock_env.return_value = str(tmp_path)
            session = PipelineSession("test-dir", "/spec.md")
            expected_dir = tmp_path / ".osh" / "sessions" / "test-dir"
            assert session.session_dir == expected_dir
            assert expected_dir.exists()

    def test_save_to_disk(self, tmp_path):
        """_save writes session.json to disk."""
        with patch("yuleosh.pipeline.session.os.environ.get") as mock_env:
            mock_env.return_value = str(tmp_path)
            session = PipelineSession("save-test", "/spec.md")
            session._save(persist=True)
            sess_file = session.session_dir / "session.json"
            assert sess_file.exists()
            data = json.loads(sess_file.read_text())
            assert data["name"] == "save-test"

    def test_save_no_persist(self, tmp_path):
        """_save(persist=False) does not write to disk."""
        with patch("yuleosh.pipeline.session.os.environ.get") as mock_env:
            mock_env.return_value = str(tmp_path)
            session = PipelineSession("no-persist", "/spec.md")
            session._save(persist=False)
            sess_file = session.session_dir / "session.json"
            assert not sess_file.exists()

    def test_llm_client(self):
        """llm_client is stored."""
        with patch("yuleosh.pipeline.session.Path"):
            def client(system, user):
                return {"content": "mock"}
            session = PipelineSession("llm", "/spec.md", llm_client=client)
            assert session.llm_client is client
