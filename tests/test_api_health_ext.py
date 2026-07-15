"""Tests for api/health.py — Health endpoint."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.health import handle_health


class TestHealth:
    """Test health endpoint."""

    @patch("yuleosh.api.health.Store")
    @patch("yuleosh.api.health.shutil.disk_usage")
    def test_health_ok(self, mock_disk_usage, mock_store_cls):
        """GET /health returns all health data."""
        mock_store = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"ok": 1}
        mock_store.conn.execute.return_value = mock_cursor
        mock_store_cls.return_value = mock_store

        mock_disk_usage.return_value.total = 1000000000
        mock_disk_usage.return_value.free = 500000000
        mock_disk_usage.return_value.used = 500000000

        result, code = handle_health("GET")
        assert code == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["db"] == "ok"
        assert "store" in data
        assert "disk" in data
        assert data["disk"]["ok"] is True
        assert "uptime_seconds" in data

    @patch("yuleosh.api.health.Store")
    def test_health_db_error(self, mock_store_cls):
        """DB error reported as degraded."""
        mock_store = MagicMock()
        mock_store.conn.execute.side_effect = Exception("DB down")
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.health.shutil.disk_usage") as mock_disk:
            mock_disk.return_value.total = 1000000000
            mock_disk.return_value.free = 100000000
            mock_disk.return_value.used = 900000000

            result, code = handle_health("GET")
            assert code == 200
            assert result["data"]["db"].startswith("error")

    @patch("yuleosh.api.health.Store")
    def test_health_disk_full(self, mock_store_cls):
        """Disk > 90% flagged."""
        mock_store = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"ok": 1}
        mock_store.conn.execute.return_value = mock_cursor
        mock_store_cls.return_value = mock_store

        with patch("yuleosh.api.health.shutil.disk_usage") as mock_disk:
            mock_disk.return_value.total = 1000
            mock_disk.return_value.free = 10
            mock_disk.return_value.used = 990

            result, code = handle_health("GET")
            assert result["data"]["disk"]["ok"] is False
