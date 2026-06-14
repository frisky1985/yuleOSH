"""Tests for src/store_pg.py — PostgreSQL-backed persistent store.

Uses mocking for psycopg2 since it's not installed in all environments.
"""

import sys
import os
import json
from datetime import datetime
from unittest import mock

import pytest

# Ensure we import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_psycopg2():
    """Mock psycopg2 so tests run without the real package."""
    mock_conn = mock.MagicMock()
    mock_cursor = mock.MagicMock()

    # The cursor's __enter__/__exit__ for context manager usage
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = None

    # fetchone returns None by default (no rows)
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []

    # cursor.description — used by _row_to_dict
    mock_cursor.description = []

    mock_conn.cursor.return_value = mock_cursor
    mock_conn.closed = False

    # connect returns the mock connection
    fake_connect = mock.MagicMock(return_value=mock_conn)
    with mock.patch.dict("sys.modules", {"psycopg2": mock.MagicMock(connect=fake_connect)}):
        yield mock_conn, mock_cursor


@pytest.fixture
def store():
    """Create a fresh PostgresStore instance for each test."""
    from yuleosh.store_pg import PostgresStore
    PostgresStore.reset()
    store = PostgresStore("postgresql://test:test@localhost:5432/test")
    yield store
    PostgresStore.reset()


# ---------------------------------------------------------------------------
# Connection tests
# ---------------------------------------------------------------------------

class TestConnection:
    """Tests for PostgresStore connection management."""

    def test_singleton_pattern(self, mock_psycopg2):
        """Same DSN should return the same instance."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        s1 = PostgresStore("postgresql://test:test@localhost:5432/test")
        s2 = PostgresStore("postgresql://test:test@localhost:5432/test")
        assert s1 is s2
        PostgresStore.reset()

    def test_different_dsn_different_instance(self, mock_psycopg2):
        """Different DSNs should return different instances."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        s1 = PostgresStore("postgresql://a:a@localhost:5432/a")
        s2 = PostgresStore("postgresql://b:b@localhost:5432/b")
        assert s1 is not s2
        PostgresStore.reset()

    def test_conn_property_creates_connection(self, mock_psycopg2, store):
        """conn property should call psycopg2.connect."""
        mock_conn, _ = mock_psycopg2
        c = store.conn
        assert c is not None
        from yuleosh.store_pg import PostgresStore
        # psycopg2.connect should have been called
        import sys
        psycopg2_mod = sys.modules.get("psycopg2")
        assert psycopg2_mod is not None
        psycopg2_mod.connect.assert_called_once()

    def test_reset_clears_instances(self, mock_psycopg2):
        """reset() should clear all cached instances."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        s1 = PostgresStore("postgresql://test:test@localhost:5432/test")
        PostgresStore.reset()
        s2 = PostgresStore("postgresql://test:test@localhost:5432/test")
        assert s1 is not s2


# ---------------------------------------------------------------------------
# Organization CRUD tests
# ---------------------------------------------------------------------------

class TestOrganizations:
    """Tests for organization CRUD operations."""

    def test_create_organization(self, mock_psycopg2, store):
        """create_organization should return a dict with id."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = (42,)
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("slug", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
        ]

        result = store.create_organization("Test Org", "test-org")
        assert result["id"] == 42
        assert result["name"] == "Test Org"
        assert result["slug"] == "test-org"

    def test_get_organization(self, mock_psycopg2, store):
        """get_organization should return the org dict when found."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = (1, "Found Org", "found-org", "pro", "2025-01-01T00:00:00")
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("slug", None, None, None, None, None, None),
            ("tier", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
        ]

        result = store.get_organization("found-org")
        assert result is not None
        assert result["slug"] == "found-org"
        assert result["tier"] == "pro"

    def test_get_organization_not_found(self, mock_psycopg2, store):
        """get_organization should return None when not found."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = None

        result = store.get_organization("nonexistent")
        assert result is None

    def test_list_organizations(self, mock_psycopg2, store):
        """list_organizations should return all orgs."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            (2, "Org B", "org-b", "pro", "2025-02-01T00:00:00"),
            (1, "Org A", "org-a", "community", "2025-01-01T00:00:00"),
        ]
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("slug", None, None, None, None, None, None),
            ("tier", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
        ]

        results = store.list_organizations()
        assert len(results) == 2
        assert results[0]["name"] == "Org B"


# ---------------------------------------------------------------------------
# User CRUD tests
# ---------------------------------------------------------------------------

class TestUsers:
    """Tests for user CRUD operations."""

    def test_create_user(self, mock_psycopg2, store):
        """create_user should insert and return user data."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = (7,)
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("org_id", None, None, None, None, None, None),
            ("email", None, None, None, None, None, None),
            ("role", None, None, None, None, None, None),
            ("password_hash", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
        ]

        result = store.create_user(1, "user@test.com", role="admin", password_hash="hash123")
        assert result["id"] == 7
        assert result["email"] == "user@test.com"
        assert result["role"] == "admin"

    def test_get_user(self, mock_psycopg2, store):
        """get_user should return matching user."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = (3, 1, "found@test.com", "member", None, "2025-01-01T00:00:00")
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("org_id", None, None, None, None, None, None),
            ("email", None, None, None, None, None, None),
            ("role", None, None, None, None, None, None),
            ("password_hash", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
        ]

        result = store.get_user(1, "found@test.com")
        assert result is not None
        assert result["email"] == "found@test.com"


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------

class TestPipelines:
    """Tests for pipeline storage."""

    def test_save_and_get_pipeline(self, mock_psycopg2, store):
        """save_pipeline then get_pipeline should return matching data."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = (
            1, "my-pipe", "spec.md", "completed",
            "2025-01-01T00:00:00", "2025-01-01T01:00:00",
            json.dumps({"report": "final.md"}),
            json.dumps([{"name": "build", "status": "passed"}]),
            json.dumps([]),
        )
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
            ("spec_path", None, None, None, None, None, None),
            ("status", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
            ("updated_at", None, None, None, None, None, None),
            ("artifacts", None, None, None, None, None, None),
            ("steps", None, None, None, None, None, None),
            ("errors", None, None, None, None, None, None),
        ]

        store.save_pipeline("my-pipe", {"spec_path": "spec.md", "status": "completed"})
        result = store.get_pipeline("my-pipe")
        assert result is not None
        assert result["name"] == "my-pipe"
        assert result["status"] == "completed"

    def test_list_pipelines(self, mock_psycopg2, store):
        """list_pipelines should return stored pipelines."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            ("p2", "completed", "2025-02-01T00:00:00", "2025-02-01T01:00:00"),
            ("p1", "running", "2025-01-01T00:00:00", "2025-01-01T00:30:00"),
        ]
        mock_cursor.description = [
            ("name", None, None, None, None, None, None),
            ("status", None, None, None, None, None, None),
            ("created_at", None, None, None, None, None, None),
            ("updated_at", None, None, None, None, None, None),
        ]

        results = store.list_pipelines()
        assert len(results) == 2
        assert results[0]["name"] == "p2"


# ---------------------------------------------------------------------------
# Usage & Subscription tests
# ---------------------------------------------------------------------------

class TestUsage:
    """Tests for usage logging and subscriptions."""

    def test_record_usage(self, mock_psycopg2, store):
        """record_usage should execute INSERT."""
        mock_conn, mock_cursor = mock_psycopg2
        store.record_usage(1, 1, "pipeline_runs", 5)
        # Verify execute was called with the SQL and params
        mock_cursor.execute.assert_called()

    def test_get_monthly_usage(self, mock_psycopg2, store):
        """get_monthly_usage should return usage dict."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchall.return_value = [
            ("pipeline_runs", 42),
            ("llm_tokens", 15000),
        ]
        mock_cursor.fetchone.return_value = (5,)

        result = store.get_monthly_usage(1)
        assert isinstance(result, dict)
        assert "project_count" in result
        assert result["project_count"] == 5

    def test_upsert_subscription(self, mock_psycopg2, store):
        """upsert_subscription should insert or update."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.fetchone.return_value = None  # no existing sub → insert

        store.upsert_subscription(1, {
            "stripe_subscription_id": "sub_abc",
            "stripe_customer_id": "cus_xyz",
            "tier": "pro",
            "status": "active",
        })
        # Should have executed INSERT
        assert mock_cursor.execute.call_count >= 1


# ---------------------------------------------------------------------------
# Stats & helpers
# ---------------------------------------------------------------------------

class TestStats:
    """Tests for usage stats and helpers."""

    def test_get_usage_stats(self, mock_psycopg2, store):
        """get_usage_stats should return aggregated counts."""
        mock_conn, mock_cursor = mock_psycopg2
        # Each fetchone returns a different count
        counts = [(5,), (3,), (7,), (2,), (10,), (4,), (1,)]
        mock_cursor.fetchone.side_effect = counts
        # fetchall for GROUP BY queries
        mock_cursor.fetchall.return_value = [("completed", 3)]

        result = store.get_usage_stats()
        assert result["total_pipelines"] == 5
        assert result["total_ci_runs"] == 3
        assert result["total_reviews"] == 7
        assert result["total_projects"] == 10
        assert result["total_organizations"] == 4

    def test_row_to_dict(self, mock_psycopg2, store):
        """_row_to_dict should convert cursor row to dict."""
        mock_conn, mock_cursor = mock_psycopg2
        mock_cursor.description = [
            ("id", None, None, None, None, None, None),
            ("name", None, None, None, None, None, None),
        ]
        row = (1, "test-name")
        result = store._row_to_dict(mock_cursor, row)
        assert result == {"id": 1, "name": "test-name"}

    def test_complete_wizard(self, mock_psycopg2, store):
        """complete_wizard should set wizard flag."""
        mock_conn, mock_cursor = mock_psycopg2
        store.complete_wizard()
        # Verify meta was set
        mock_cursor.execute.assert_called()
        args, _ = mock_cursor.execute.call_args
        assert "wizard_completed" in str(args[0])
