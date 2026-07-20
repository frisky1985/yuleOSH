"""Tests for api/ci.py — CI endpoints."""

from unittest.mock import patch, MagicMock
from yuleosh.api.ci import handle_ci, _run_ci_layer


class TestApiCI:
    """Test CI endpoint."""

    def test_unknown_resource(self):
        result, code = handle_ci("GET", "unknown", {}, {})
        assert code == 404

    @patch("yuleosh.api.ci.subprocess.run")
    @patch("yuleosh.api.ci.os.environ.get")
    def test_run_ci_layer_1(self, mock_env, mock_subproc):
        mock_env.return_value = "/tmp"
        mock_subproc.return_value = MagicMock(returncode=0, stdout="ok", stderr="")

        mock_path = MagicMock()
        # Path(__file__).resolve().parent.parent.parent chain
        mock_file = MagicMock()
        mock_file.resolve.return_value = mock_file
        mock_file.parent = mock_file  # chain: parent.parent.parent
        mock_path.return_value = mock_file

        with patch("yuleosh.api.ci.Path", mock_path):
            result, code = handle_ci("POST", "run/1", {}, {})
            assert code == 200
            assert result["data"]["status"] == "passed"

    @patch("yuleosh.api.ci.subprocess.run")
    def test_run_ci_layer_2(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=1, stdout="fail", stderr="e")
        result, code = handle_ci("POST", "run/2", {}, {})
        assert code == 200
        assert result["data"]["status"] == "failed"

    def test_run_ci_layer_invalid(self):
        result, code = handle_ci("POST", "run/4", {}, {})
        assert code == 400

    @patch("yuleosh.api.ci.subprocess.run")
    def test_run_ci_timeout(self, mock_subproc):
        mock_subproc.side_effect = __import__("subprocess").TimeoutExpired("cmd", 180)
        result, code = handle_ci("POST", "run/1", {}, {})
        assert code == 504

    @patch("yuleosh.api.ci.Path")
    def test_list_ci_runs_empty(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_path_cls.return_value = mock_path

        with patch("yuleosh.api.OSH_HOME", "/tmp"):
            result, code = handle_ci("GET", "runs", {}, {})
            assert code == 200
            assert result["data"]["count"] == 0

    def test_ci_post_wrong_method_on_run(self):
        result, code = handle_ci("GET", "run/1", {}, {})
        assert code == 405

    @patch("yuleosh.api.ci.subprocess.run")
    def test_run_ci_layer_3(self, mock_subproc):
        mock_subproc.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        mock_path = MagicMock()
        mock_path.return_value = MagicMock()
        mock_path.return_value.resolve.return_value = MagicMock()
        mock_path.return_value.resolve.return_value.parent = MagicMock()
        mock_path.return_value.resolve.return_value.parent.parent = MagicMock()
        mock_path.return_value.resolve.return_value.parent.parent.parent = MagicMock()

        with patch("yuleosh.api.ci.Path", mock_path):
            result, code = handle_ci("POST", "run/3", {}, {})
            assert code == 200
            assert result["data"]["layer"] == 3
