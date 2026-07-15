"""Tests for api/review.py — Review endpoints."""

from unittest.mock import patch, MagicMock
from yuleosh.api.review import (
    handle_review,
    _run_auto_review,
    _run_task_review,
    _list_reviews,
)


class TestApiReview:
    """Test review endpoints."""

    def test_unknown_resource(self):
        """Unknown review resource returns 404."""
        result, code = handle_review("GET", "unknown", {}, {})
        assert code == 404

    @patch("yuleosh.api.review.subprocess.run")
    @patch("yuleosh.api.review.os.environ.get")
    def test_auto_review(self, mock_env, mock_subproc):
        """POST /review/auto runs auto review."""
        mock_env.return_value = "/tmp"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "review ok"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result

        result, code = handle_review("POST", "auto", {}, {})
        assert code == 200
        assert result["data"]["status"] == "completed"

    @patch("yuleosh.api.review.subprocess.run")
    @patch("yuleosh.api.review.os.environ.get")
    def test_auto_review_timeout(self, mock_env, mock_subproc):
        """Timeout returns 504."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = __import__("subprocess").TimeoutExpired("cmd", 120)
        result, code = handle_review("POST", "auto", {}, {})
        assert code == 504

    @patch("yuleosh.api.review.subprocess.run")
    @patch("yuleosh.api.review.os.environ.get")
    def test_auto_review_exception(self, mock_env, mock_subproc):
        """Exception returns 500."""
        mock_env.return_value = "/tmp"
        mock_subproc.side_effect = Exception("error")
        result, code = handle_review("POST", "auto", {}, {})
        assert code == 500

    @patch("yuleosh.api.review.subprocess.run")
    @patch("yuleosh.api.review.os.environ.get")
    def test_task_review(self, mock_env, mock_subproc):
        """POST /review/task runs task review."""
        mock_env.return_value = "/tmp"
        mock_result = MagicMock()
        mock_result.stdout = "task review ok"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result

        result, code = handle_review("POST", "task", {"task": "my-task", "kind": "feature"}, {})
        assert code == 200
        assert result["data"]["task"] == "my-task"

    def test_task_review_no_name(self):
        """POST without task name returns 400."""
        result, code = handle_review("POST", "task", {}, {})
        assert code == 400

    def test_list_reviews_empty(self):
        """GET /review/list empty."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with patch("yuleosh.api.review.Path", return_value=mock_path):
            with patch("yuleosh.api.OSH_HOME", "/tmp"):
                result, code = handle_review("GET", "list", {}, {})
                assert code == 200
                assert result["data"]["count"] == 0

    def test_list_reviews_root(self):
        """GET /review returns list (root path)."""
        with patch("yuleosh.api.OSH_HOME", "/tmp"):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            with patch("yuleosh.api.review.Path", return_value=mock_path):
                result, code = handle_review("GET", "", {}, {})
                assert code == 200

    @patch("yuleosh.api.review.subprocess.run")
    def test_auto_review_direct(self, mock_subproc):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result
        result, code = _run_auto_review({})
        assert code == 200

    @patch("yuleosh.api.review.subprocess.run")
    def test_task_review_direct(self, mock_subproc):
        mock_result = MagicMock()
        mock_result.stdout = "ok"
        mock_result.stderr = ""
        mock_subproc.return_value = mock_result
        result, code = _run_task_review({"task": "t1", "kind": "bugfix"})
        assert code == 200

    def test_list_reviews_direct(self):
        with patch("yuleosh.api.OSH_HOME", "/tmp"):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            with patch("yuleosh.api.review.Path", return_value=mock_path):
                result, code = _list_reviews()
                assert result["data"]["count"] == 0
