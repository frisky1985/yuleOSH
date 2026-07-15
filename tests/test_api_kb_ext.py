"""Tests for api/kb.py — Knowledge base endpoints."""

from unittest.mock import patch, MagicMock
from yuleosh.api.kb import (
    handle_kb,
    _handle_articles,
    _handle_lessons,
    _handle_fmea,
    _parse_id,
    _get_query_param,
)


class TestKb:
    """Test KB endpoint."""

    def test_unknown_resource(self):
        """Unknown KB resource returns 404."""
        result, code = handle_kb("GET", "unknown", {}, {})
        assert code == 404

    def test_empty_path(self):
        """Empty path returns 400."""
        result, code = handle_kb("GET", "", {}, {})
        assert code == 404

    def test_parse_id_valid(self):
        """_parse_id extracts numeric ID."""
        id_val, rest = _parse_id("42")
        assert id_val == 42
        assert rest == ""

    def test_parse_id_with_rest(self):
        id_val, rest = _parse_id("42/sub")
        assert id_val == 42
        assert rest == "sub"

    def test_parse_id_invalid(self):
        id_val, rest = _parse_id("abc")
        assert id_val is None
        assert rest == "abc"

    def test_parse_id_empty(self):
        id_val, rest = _parse_id("")
        assert id_val is None
        assert rest == ""

    def test_get_query_param_exists(self):
        result = _get_query_param({"key": ["value"]}, "key")
        assert result == "value"

    def test_get_query_param_missing(self):
        result = _get_query_param({}, "key")
        assert result == ""

    def test_get_query_param_default(self):
        result = _get_query_param({}, "key", "default")
        assert result == "default"

    # Article handlers
    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_get_list(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.list_articles.return_value = []
        mock_store.count_articles.return_value = 0
        mock_get_store.return_value = mock_store

        result, code = _handle_articles("GET", "", {}, {})
        assert code == 200
        assert result["data"]["total"] == 0

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_get_one_missing(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.get_article.return_value = None
        mock_get_store.return_value = mock_store

        result, code = _handle_articles("GET", "999", {}, {})
        assert code == 404

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_post_no_title(self, mock_get_store):
        result, code = _handle_articles("POST", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_put_no_id(self, mock_get_store):
        result, code = _handle_articles("PUT", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_delete_missing(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_article.return_value = False
        mock_get_store.return_value = mock_store

        result, code = _handle_articles("DELETE", "999", {}, {})
        assert code == 404

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_articles_method_not_allowed(self, mock_get_store):
        result, code = _handle_articles("PATCH", "", {}, {})
        assert code == 405

    # Lesson handlers
    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_get_list(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.list_lessons.return_value = []
        mock_store.count_lessons.return_value = 0
        mock_get_store.return_value = mock_store

        result, code = _handle_lessons("GET", "", {}, {})
        assert code == 200

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_get_missing(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.get_lesson.return_value = None
        mock_get_store.return_value = mock_store

        result, code = _handle_lessons("GET", "999", {}, {})
        assert code == 404

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_post_no_title(self, mock_get_store):
        result, code = _handle_lessons("POST", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_put_no_id(self, mock_get_store):
        result, code = _handle_lessons("PUT", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_invalid_severity(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.list_lessons.return_value = []
        mock_store.count_lessons.return_value = 0
        mock_get_store.return_value = mock_store

        result, code = _handle_lessons("GET", "", {}, {"severity": ["invalid"]})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_lessons_method_not_allowed(self, mock_get_store):
        result, code = _handle_lessons("PATCH", "", {}, {})
        assert code == 405

    # FMEA handlers
    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_get_list(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.list_fmea.return_value = []
        mock_store.count_fmea.return_value = 0
        mock_get_store.return_value = mock_store

        result, code = _handle_fmea("GET", "", {}, {})
        assert code == 200

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_get_missing(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.get_fmea.return_value = None
        mock_get_store.return_value = mock_store

        result, code = _handle_fmea("GET", "999", {}, {})
        assert code == 404

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_post_no_item(self, mock_get_store):
        result, code = _handle_fmea("POST", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_post_no_failure_mode(self, mock_get_store):
        result, code = _handle_fmea("POST", "", {"item": "something"}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_put_no_id(self, mock_get_store):
        result, code = _handle_fmea("PUT", "", {}, {})
        assert code == 400

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_delete_missing(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_fmea.return_value = False
        mock_get_store.return_value = mock_store

        result, code = _handle_fmea("DELETE", "999", {}, {})
        assert code == 404

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_delete_ok(self, mock_get_store):
        mock_store = MagicMock()
        mock_store.delete_fmea.return_value = True
        mock_get_store.return_value = mock_store

        result, code = _handle_fmea("DELETE", "1", {}, {})
        assert code == 200

    @patch("yuleosh.api.kb._get_kb_store")
    def test_handle_fmea_method_not_allowed(self, mock_get_store):
        result, code = _handle_fmea("PATCH", "", {}, {})
        assert code == 405
