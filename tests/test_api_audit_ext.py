"""Tests for api/audit.py — Audit logging endpoints."""

from unittest.mock import patch, MagicMock
from yuleosh.api.audit import handle_audit, log_request


class TestAudit:
    """Test audit log endpoint."""

    @patch("yuleosh.store.Store")
    def test_handle_audit_get(self, mock_store_cls):
        mock_store = MagicMock()
        mock_cursor = MagicMock()  # execute #1: CREATE TABLE
        mock_cursor2 = MagicMock()  # execute #2: SELECT
        mock_cursor2.fetchall.return_value = [
            {"id": 1, "timestamp": "T1", "method": "GET", "path": "/health",
             "status_code": 200, "ip": "127.0.0.1", "duration_ms": 1.5}
        ]
        mock_cursor3 = MagicMock()  # execute #3: COUNT
        mock_cursor3.fetchone.return_value = {"c": 1}
        mock_store.conn.execute.side_effect = [mock_cursor, mock_cursor2, mock_cursor3]
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.audit.get_store", return_value=mock_store):
            result, code = handle_audit("GET", "", {}, {})
            assert code == 200
            assert result["data"]["count"] == 1

    def test_handle_audit_post(self):
        result, code = handle_audit("POST", "", {}, {})
        assert code == 405

    def test_handle_audit_with_path_tail(self):
        result, code = handle_audit("GET", "invalid", {}, {})
        assert code == 404

    @patch("yuleosh.store.Store")
    def test_handle_audit_pagination(self, mock_store_cls):
        mock_store = MagicMock()
        mock_cursor = MagicMock()  # CREATE TABLE
        mock_cursor2 = MagicMock()  # SELECT
        mock_cursor2.fetchall.return_value = []
        mock_cursor3 = MagicMock()  # COUNT
        mock_cursor3.fetchone.return_value = {"c": 0}
        mock_store.conn.execute.side_effect = [mock_cursor, mock_cursor2, mock_cursor3]
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.audit.get_store", return_value=mock_store):
            result, code = handle_audit("GET", "", {}, {"limit": ["10"], "offset": ["5"]})
            assert code == 200
            assert result["data"]["limit"] == 10
            assert result["data"]["offset"] == 5

    @patch("yuleosh.store.Store")
    def test_handle_audit_limit_capped(self, mock_store_cls):
        mock_store = MagicMock()
        mock_cursor = MagicMock()  # CREATE TABLE
        mock_cursor2 = MagicMock()  # SELECT
        mock_cursor2.fetchall.return_value = []
        mock_cursor3 = MagicMock()  # COUNT
        mock_cursor3.fetchone.return_value = {"c": 0}
        mock_store.conn.execute.side_effect = [mock_cursor, mock_cursor2, mock_cursor3]
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.audit.get_store", return_value=mock_store):
            result, code = handle_audit("GET", "", {}, {"limit": ["500"]})
            assert code == 200
            assert result["data"]["limit"] == 200

    @patch("yuleosh.store.Store")
    def test_log_request(self, mock_store_cls):
        """log_request calls _ensure_table (CREATE TABLE + commit) + INSERT + commit = 2 execute, 2 commit."""
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.audit.get_store", return_value=mock_store):
            log_request("GET", "/health", 200, "127.0.0.1", 1.5)
            assert mock_store.conn.execute.call_count == 2
            assert mock_store.conn.commit.call_count == 2
