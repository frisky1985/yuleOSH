"""Tests for api/pipeline.py — Pipeline endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.pipeline import (
    handle_pipeline,
    _run_pipeline,
    _list_pipeline_steps,
    _list_pipelines,
)


class TestApiPipeline:
    """Test pipeline API endpoints."""

    @patch("yuleosh.api.pipeline.subprocess.run")
    @patch("yuleosh.api.pipeline.os.environ.get")
    def test_run_pipeline(self, mock_env, mock_subproc):
        """POST /pipeline/run executes pipeline."""
        mock_env.return_value = "/tmp"
        mock_subproc.return_value = MagicMock(returncode=0, stdout="done", stderr="")

        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.stem = "test-spec"

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = handle_pipeline("POST", "run", {"spec": "/tmp/test.md"}, {})
            assert code == 200

    def test_run_pipeline_no_spec(self):
        """POST without spec returns 400."""
        result, code = handle_pipeline("POST", "run", {}, {})
        assert code == 400

    def test_run_pipeline_not_found(self):
        """POST with non-existent spec returns 400."""
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = False

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = handle_pipeline("POST", "run", {"spec": "/tmp/nonexistent.md"}, {})
            assert code == 400

    @patch("yuleosh.api.pipeline.subprocess.run")
    @patch("yuleosh.api.pipeline.os.environ.get")
    def test_run_pipeline_timeout(self, mock_env, mock_subproc):
        """Timeout returns 504."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = __import__("subprocess").TimeoutExpired("cmd", 300)

        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.stem = "test"

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = handle_pipeline("POST", "run", {"spec": "/tmp/test.md"}, {})
            assert code == 504

    @patch("yuleosh.api.pipeline.subprocess.run")
    @patch("yuleosh.api.pipeline.os.environ.get")
    def test_run_pipeline_exception(self, mock_env, mock_subproc):
        """Exception returns 500."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = Exception("Something broke")

        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.stem = "test"

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = handle_pipeline("POST", "run", {"spec": "/tmp/test.md"}, {})
            assert code == 500

    def test_get_pipeline_no_post(self):
        """GET on pipeline/run returns 405."""
        result, code = handle_pipeline("GET", "run", {}, {})
        assert code == 405

    @patch("yuleosh.store.Store")
    @patch("yuleosh.api.OSH_HOME", "/tmp")
    def test_list_pipelines_empty(self, mock_store_cls):
        """GET /pipeline/status empty."""
        mock_store = MagicMock()
        mock_store.list_pipelines.return_value = []
        mock_store_cls.return_value = mock_store

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = handle_pipeline("GET", "status", {}, {})
            assert code == 200

    def test_list_pipeline_steps(self):
        """GET /pipeline/steps returns step list."""
        with patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS", []):
            result, code = handle_pipeline("GET", "steps", {}, {})
            assert code == 200
            assert result["data"]["count"] == 0

    def test_list_pipeline_steps_empty(self):
        with patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS", []):
            result, code = _list_pipeline_steps()
            assert result["data"]["count"] == 0

    def test_unknown_resource(self):
        """Unknown resource returns 404."""
        result, code = handle_pipeline("GET", "unknown", {}, {})
        assert code == 404

    @patch("yuleosh.api.pipeline.subprocess.run")
    def test_run_pipeline_direct(self, mock_subproc):
        """Direct call to _run_pipeline."""
        mock_subproc.return_value = MagicMock(returncode=0, stdout="done", stderr="")

        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path.stem = "s"
        mock_path.parent = MagicMock()

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            mock_path.__truediv__.return_value = MagicMock()
            result, code = _run_pipeline({"spec": "/tmp/s.md", "name": "test"})
            assert code == 200
            assert result["data"]["name"] == "test"

    @patch("yuleosh.store.Store")
    @patch("yuleosh.api.OSH_HOME", "/tmp")
    def test_list_pipelines_direct(self, mock_store_cls):
        """Direct call to _list_pipelines."""
        mock_store = MagicMock()
        mock_store.list_pipelines.return_value = []
        mock_store_cls.return_value = mock_store

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("yuleosh.api.pipeline.Path", return_value=mock_path):
            result, code = _list_pipelines()
            assert code == 200

    def test_pipeline_steps_direct(self):
        with patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS", [
            ("sc", "小明", "Spec Check", lambda s: None),
        ]):
            result, code = _list_pipeline_steps()
            assert result["data"]["count"] == 1
