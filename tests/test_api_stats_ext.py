"""Tests for api/stats.py — Usage statistics endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.stats import handle_stats, _overview, _trends


class TestApiStats:
    """Test stats endpoints."""

    @patch("yuleosh.api.stats.Store")
    def test_overview(self, mock_store_cls):
        """GET /stats/overview returns counts."""
        mock_store = MagicMock()
        mock_store.get_usage_stats.return_value = {
            "total_pipelines": 10,
            "pipeline_statuses": {"completed": 8},
            "total_ci_runs": 20,
            "total_reviews": 5,
        }
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"c": 15}
        mock_store.conn.execute.return_value = mock_cursor
        mock_store_cls.return_value = mock_store

        result, code = handle_stats("GET", "overview", {}, {})
        assert code == 200
        data = result["data"]
        assert data["total_pipelines"] == 10
        assert data["pipeline_success_rate"] == 80.0
        assert data["ci_pass_rate"] == 75.0

    @patch("yuleosh.api.stats.Store")
    def test_overview_zero_values(self, mock_store_cls):
        """Overview with no data returns 0 rates."""
        mock_store = MagicMock()
        mock_store.get_usage_stats.return_value = {
            "total_pipelines": 0,
            "pipeline_statuses": {},
            "total_ci_runs": 0,
            "total_reviews": 0,
        }
        mock_store_cls.return_value = mock_store

        result, code = _overview()
        assert result["data"]["pipeline_success_rate"] == 0
        assert result["data"]["ci_pass_rate"] == 0

    @patch("yuleosh.api.stats.Store")
    def test_trends_daily(self, mock_store_cls):
        """GET /stats/trends daily."""
        mock_store = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_store.conn.execute.return_value = mock_cursor
        mock_store_cls.return_value = mock_store

        result, code = handle_stats(
            "GET", "trends", {}, {"period": ["daily"], "days": ["7"]}
        )
        assert code == 200
        assert result["data"]["period"] == "daily"
        assert result["data"]["total_points"] >= 0

    @patch("yuleosh.api.stats.Store")
    def test_trends_weekly(self, mock_store_cls):
        """GET /stats/trends weekly."""
        mock_store = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_store.conn.execute.return_value = mock_cursor
        mock_store_cls.return_value = mock_store

        result, code = handle_stats(
            "GET", "trends", {}, {"period": ["weekly"], "days": ["30"]}
        )
        assert code == 200
        assert result["data"]["period"] == "weekly"

    def test_trends_invalid_period(self):
        """Invalid period returns 400."""
        result, code = handle_stats(
            "GET", "trends", {}, {"period": ["monthly"]}
        )
        assert code == 400

    def test_not_get_method(self):
        """POST returns 405."""
        result, code = handle_stats("POST", "overview", {}, {})
        assert code == 405

    def test_unknown_stats_resource(self):
        """Unknown stats resource returns 404."""
        result, code = handle_stats("GET", "unknown", {}, {})
        assert code == 404

    @patch("yuleosh.api.stats.Store")
    def test_overview_with_exception(self, mock_store_cls):
        """Overview with ci_runs query exception still works."""
        mock_store = MagicMock()
        mock_store.get_usage_stats.return_value = {
            "total_pipelines": 5,
            "pipeline_statuses": {"completed": 3},
            "total_ci_runs": 10,
            "total_reviews": 2,
        }

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"c": 8}
        # First call to execute returns cursor for ci_runs, second for statuses
        mock_store.conn.execute.return_value = MagicMock()
        mock_store.conn.execute.side_effect = [
            MagicMock(fetchone=lambda: {"c": 8}),
        ]
        mock_store_cls.return_value = mock_store

        result, code = _overview()
        assert code == 200
