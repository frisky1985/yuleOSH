#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for yuleosh.store_pg — PostgreSQL store adapter.

Uses mock-based testing (psycopg2 MagicMock) since we can't assume
a PostgreSQL instance is available in CI. Covers:

  1.  Connection & singleton pattern
  2.  Schema migration
  3.  Organization CRUD
  4.  User CRUD
  5.  Org Project CRUD
  6.  Session management
  7.  Spec cache
  8.  API Keys
  9.  Pipelines
  10. CI Runs
  11. Reviews
  12. Evidence
  13. Projects
  14. Usage & Subscription
  15. Stats & wizard
  16. Error handling
  17. Thread safety
"""

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def auto_fixtures(monkeypatch):
    """Clear PostgresStore singleton instances, set env, and patch psycopg2."""
    from yuleosh.store_pg import PostgresStore
    PostgresStore.reset()
    monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://test:test@localhost:5432/testdb")
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.cursor.return_value = MagicMock()
    with patch("psycopg2.connect", return_value=mock_conn):
        yield
    PostgresStore.reset()


@pytest.fixture
def mock_cursor():
    """Create a mock psycopg2 cursor that works with 'with' statements."""
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.rowcount = 1
    # Fix MagicMock's __enter__ to return self (needed for 'with cursor:' blocks)
    cursor.__enter__.return_value = cursor
    return cursor


@pytest.fixture
def mock_conn(mock_cursor):
    """Create a mock psycopg2 connection with a cursor."""
    conn = MagicMock()
    conn.closed = False
    conn.cursor.return_value = mock_cursor
    return conn


@pytest.fixture
def store(monkeypatch, mock_conn):
    """Create a PostgresStore with a mocked psycopg2 connection.
    Avoids calling _migrate() during construction."""
    monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://test:test@localhost:5432/testdb")

    from yuleosh.store_pg import PostgresStore
    PostgresStore._instances = {}
    s = PostgresStore.__new__(PostgresStore)
    s.dsn = "postgresql://test:test@localhost:5432/testdb"
    s._local = threading.local()
    s._local.conn = mock_conn
    # Don't call _migrate — tests call setup() explicitly
    yield s
    s.close()


@pytest.fixture
def store_with_schema(monkeypatch, mock_conn, mock_cursor):
    """Create a PostgresStore that simulates a migrated schema."""
    monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://test:test@localhost:5432/testdb")

    # Simulate meta table returning migration version
    def fetchone_side_effect(*args, **kwargs):
        # First call: check migration version -> return 7 (latest)
        return (7,)

    mock_cursor.fetchone.side_effect = fetchone_side_effect
    mock_cursor.fetchall.return_value = []

    with patch("psycopg2.connect", return_value=mock_conn):
        from yuleosh.store_pg import PostgresStore
        PostgresStore._instances = {}
        s = PostgresStore.__new__(PostgresStore)
        s.dsn = "postgresql://test:test@localhost:5432/testdb"
        s._local = threading.local()
        s._local.conn = mock_conn
        yield s
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# Connection & Singleton
# ═══════════════════════════════════════════════════════════════════════


class TestSingleton:
    """PostgresStore singleton pattern tests."""

    def test_singleton_same_dsn(self, store):
        """GIVEN a PostgresStore WHEN same DSN used THEN same instance returned."""
        from yuleosh.store_pg import PostgresStore
        s2 = PostgresStore()
        assert s2 is store

    def test_singleton_different_dsn(self, store):
        """GIVEN a PostgresStore WHEN different DSN used THEN different instance."""
        from yuleosh.store_pg import PostgresStore
        s2 = PostgresStore.__new__(PostgresStore)
        s2.dsn = "postgresql://other:pass@localhost:5432/otherdb"
        s2._local = threading.local()
        # Store it with the different key
        with patch.object(PostgresStore, '_instances', {'other': s2}):
            retrieved = PostgresStore.__new__(PostgresStore)
            retrieved.dsn = "postgresql://other:pass@localhost:5432/otherdb"
            assert retrieved.dsn == "postgresql://other:pass@localhost:5432/otherdb"

    def test_reset_clears_instances(self, store):
        """GIVEN a PostgresStore WHEN reset THEN instances cleared."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        assert PostgresStore._instances == {}

    def test_no_dsn_raises(self):
        """GIVEN no DSN WHEN creating PostgresStore THEN ValueError raised."""
        from yuleosh.store_pg import PostgresStore
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="PostgreSQL connection string is required"):
                PostgresStore.__new__(PostgresStore)


# ═══════════════════════════════════════════════════════════════════════
# Connection Management
# ═══════════════════════════════════════════════════════════════════════


class TestConnection:
    """Connection management tests."""

    def test_conn_property_creates_connection(self, store):
        """GIVEN store WHEN conn accessed THEN returns connection."""
        assert store.conn is not None
        assert not store.conn.closed

    def test_conn_property_thread_local(self, store, mock_conn):
        """GIVEN store WHEN accessed from multiple threads THEN separate connections."""
        connections = {}

        def get_conn(tid):
            with patch("psycopg2.connect", return_value=MagicMock()):
                c = store.conn
                connections[tid] = c

        t1 = threading.Thread(target=get_conn, args=(1,))
        t2 = threading.Thread(target=get_conn, args=(2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(connections) == 2

    def test_close_connection(self, store):
        """GIVEN open connection WHEN close THEN connection closed."""
        conn = store.conn
        store.close()
        conn.close.assert_called_once()

    def test_close_no_connection(self, store):
        """GIVEN store without connection WHEN close THEN no error."""
        store.close()  # Should not raise
        store.close()  # Twice should also not raise

    def test_conn_reuses_existing(self, store, mock_conn):
        """GIVEN existing connection WHEN conn property accessed THEN reuses."""
        conn1 = store.conn
        conn2 = store.conn
        assert conn1 is conn2


# ═══════════════════════════════════════════════════════════════════════
# Schema & Migration
# ═══════════════════════════════════════════════════════════════════════


class TestSchema:
    """Schema migration tests."""

    def test_setup_calls_ensure_schema(self, store, mock_conn):
        """GIVEN store WHEN setup THEN _ensure_schema called."""
        store.setup()
        # At minimum, should create _meta table
        calls = mock_conn.cursor.return_value.execute.call_args_list
        meta_create = [c for c in calls if "CREATE TABLE IF NOT EXISTS _meta" in str(c)]
        assert len(meta_create) >= 1

    def test_migrate_creates_all_tables(self, store, mock_conn):
        """GIVEN store WHEN _migrate called THEN all tables created."""
        store._migrate()
        execute_calls = mock_conn.cursor.return_value.execute.call_args_list
        # Verify key tables are created
        table_names = ["_meta", "pipelines", "ci_runs", "reviews", "evidence",
                        "projects", "organizations", "users", "org_projects",
                        "user_sessions", "usage_log", "subscriptions", "api_keys",
                        "spec_cache"]
        all_sql = " ".join(str(c) for c in execute_calls)
        for t in table_names:
            assert f"CREATE TABLE IF NOT EXISTS {t}" in all_sql, f"Missing table: {t}"


# ═══════════════════════════════════════════════════════════════════════
# Row to Dict Helper
# ═══════════════════════════════════════════════════════════════════════


class TestRowToDict:
    """_row_to_dict helper tests."""

    def test_converts_row_to_dict(self, store):
        """GIVEN cursor and row WHEN _row_to_dict THEN returns dict."""
        cursor = MagicMock()
        cursor.description = [("id",), ("name",), ("email",)]
        row = (1, "test_org", "test@example.com")
        result = store._row_to_dict(cursor, row)
        assert result == {"id": 1, "name": "test_org", "email": "test@example.com"}

    def test_converts_fetchall_cursor(self, store):
        """GIVEN cursor with multiple rows WHEN _row_to_dict THEN converts each."""
        cursor = MagicMock()
        cursor.description = [("id",), ("name",)]
        result = store._row_to_dict(cursor, (42, "acme"))
        assert result == {"id": 42, "name": "acme"}


# ═══════════════════════════════════════════════════════════════════════
# Organization CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestOrganizations:
    """Organization CRUD tests."""

    def test_create_organization(self, store, mock_conn, mock_cursor):
        """GIVEN name and slug WHEN create_organization THEN row inserted."""
        mock_cursor.fetchone.return_value = (1,)
        result = store.create_organization("Acme Corp", "acme")

        assert result["name"] == "Acme Corp"
        assert result["slug"] == "acme"
        assert result["id"] == 1
        assert "created_at" in result
        mock_cursor.execute.assert_called_once()
        assert "INSERT INTO organizations" in str(mock_cursor.execute.call_args)
        assert mock_conn.commit.called

    def test_get_organization_found(self, store, mock_cursor):
        """GIVEN existing slug WHEN get_organization THEN returns dict."""
        mock_cursor.fetchone.return_value = (1, "Acme Corp", "acme", "pro", "2025-01-01")
        mock_cursor.description = [("id",), ("name",), ("slug",), ("tier",), ("created_at",)]
        result = store.get_organization("acme")
        assert result["id"] == 1
        assert result["slug"] == "acme"

    def test_get_organization_not_found(self, store, mock_cursor):
        """GIVEN non-existent slug WHEN get_organization THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_organization("nonexistent")
        assert result is None

    def test_get_organization_by_id(self, store, mock_cursor):
        """GIVEN org_id WHEN get_organization_by_id THEN returns dict."""
        mock_cursor.fetchone.return_value = (5, "Beta", "beta", "enterprise", "2025-06-01")
        mock_cursor.description = [("id",), ("name",), ("slug",), ("tier",), ("created_at",)]
        result = store.get_organization_by_id(5)
        assert result["id"] == 5
        assert result["name"] == "Beta"

    def test_list_organizations(self, store, mock_cursor):
        """GIVEN multiple organizations WHEN list_organizations THEN returns list."""
        mock_cursor.fetchall.return_value = [
            (1, "Acme", "acme", "pro", "2025-01-01"),
            (2, "Beta", "beta", "enterprise", "2025-06-01"),
        ]
        mock_cursor.description = [("id",), ("name",), ("slug",), ("tier",), ("created_at",)]
        result = store.list_organizations()
        assert len(result) == 2
        assert result[0]["name"] == "Acme"


# ═══════════════════════════════════════════════════════════════════════
# User CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestUsers:
    """User CRUD tests."""

    def test_create_user(self, store, mock_cursor):
        """GIVEN org_id and email WHEN create_user THEN user created."""
        mock_cursor.fetchone.return_value = (10,)
        result = store.create_user(1, "alice@acme.com", role="admin")
        assert result["id"] == 10
        assert result["email"] == "alice@acme.com"
        assert result["role"] == "admin"

    def test_create_user_with_password(self, store, mock_cursor):
        """GIVEN password_hash WHEN create_user THEN hash stored."""
        mock_cursor.fetchone.return_value = (11,)
        result = store.create_user(1, "bob@acme.com", password_hash="hashed_pw")
        assert result["password_hash"] == "hashed_pw"

    def test_get_user_found(self, store, mock_cursor):
        """GIVEN org_id and email WHEN get_user THEN returns dict."""
        mock_cursor.fetchone.return_value = (1, 1, "alice@acme.com", "admin", "hash", "2025-01-01")
        mock_cursor.description = [("id",), ("org_id",), ("email",), ("role",), ("password_hash",), ("created_at",)]
        result = store.get_user(1, "alice@acme.com")
        assert result["email"] == "alice@acme.com"

    def test_get_user_not_found(self, store, mock_cursor):
        """GIVEN non-existent user WHEN get_user THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_user(999, "nobody@nowhere.com")
        assert result is None

    def test_get_user_by_id(self, store, mock_cursor):
        """GIVEN user_id WHEN get_user_by_id THEN returns dict."""
        mock_cursor.fetchone.return_value = (42, 1, "charlie@acme.com", "member", None, "2025-03-01")
        mock_cursor.description = [("id",), ("org_id",), ("email",), ("role",), ("password_hash",), ("created_at",)]
        result = store.get_user_by_id(42)
        assert result["email"] == "charlie@acme.com"

    def test_list_users(self, store, mock_cursor):
        """GIVEN org_id WHEN list_users THEN returns list."""
        mock_cursor.fetchall.return_value = [
            (1, "alice@acme.com", "admin", "2025-01-01"),
            (2, "bob@acme.com", "member", "2025-02-01"),
        ]
        mock_cursor.description = [("id",), ("email",), ("role",), ("created_at",)]
        result = store.list_users(1)
        assert len(result) == 2

    def test_list_users_empty(self, store, mock_cursor):
        """GIVEN org_id with no users WHEN list_users THEN returns empty list."""
        mock_cursor.fetchall.return_value = []
        result = store.list_users(999)
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
# Org Project CRUD
# ═══════════════════════════════════════════════════════════════════════


class TestOrgProjects:
    """Org-scoped project CRUD tests."""

    def test_create_org_project(self, store, mock_cursor):
        """GIVEN org_id and name WHEN create_org_project THEN created."""
        mock_cursor.fetchone.return_value = (100,)
        result = store.create_org_project(1, "Project Alpha", "alpha-proj", "First project")
        assert result["id"] == 100
        assert result["name"] == "Project Alpha"

    def test_get_org_project_found(self, store, mock_cursor):
        """GIVEN org_id and slug WHEN get_org_project THEN returns dict."""
        mock_cursor.fetchone.return_value = (1, 1, "Alpha", "alpha-proj", "desc", "2025-01-01")
        mock_cursor.description = [("id",), ("org_id",), ("name",), ("slug",), ("description",), ("created_at",)]
        result = store.get_org_project(1, "alpha-proj")
        assert result["slug"] == "alpha-proj"

    def test_get_org_project_not_found(self, store, mock_cursor):
        """GIVEN non-existent project WHEN get_org_project THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_org_project(1, "nonexistent")
        assert result is None

    def test_get_org_project_by_id(self, store, mock_cursor):
        """GIVEN project_id WHEN get_org_project_by_id THEN returns dict."""
        mock_cursor.fetchone.return_value = (50, 1, "Beta", "beta", "desc", "2025-06-01")
        mock_cursor.description = [("id",), ("org_id",), ("name",), ("slug",), ("description",), ("created_at",)]
        result = store.get_org_project_by_id(50)
        assert result["name"] == "Beta"

    def test_list_org_projects(self, store, mock_cursor):
        """GIVEN org_id WHEN list_org_projects THEN returns list."""
        mock_cursor.fetchall.return_value = [
            (1, 1, "Alpha", "alpha", "", "2025-01-01"),
            (2, 1, "Beta", "beta", "", "2025-06-01"),
        ]
        mock_cursor.description = [("id",), ("org_id",), ("name",), ("slug",), ("description",), ("created_at",)]
        result = store.list_org_projects(1)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════
# Sessions
# ═══════════════════════════════════════════════════════════════════════


class TestSessions:
    """Session management tests."""

    def test_create_session(self, store, mock_cursor):
        """GIVEN user_id and token WHEN create_session THEN session created."""
        result = store.create_session(1, "tok_abc123", ttl_hours=48)
        assert result["token"] == "tok_abc123"
        assert result["user_id"] == 1

    def test_get_session_valid(self, store, mock_cursor):
        """GIVEN valid token WHEN get_session THEN returns session."""
        mock_cursor.fetchone.return_value = (1, 42, "tok_abc123", "2025-01-01", "2025-01-02")
        mock_cursor.description = [("id",), ("user_id",), ("token",), ("created_at",), ("expires_at",)]
        result = store.get_session("tok_abc123")
        assert result["token"] == "tok_abc123"

    def test_get_session_expired(self, store, mock_cursor):
        """GIVEN expired token WHEN get_session THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_session("tok_expired")
        assert result is None

    def test_delete_session(self, store, mock_conn, mock_cursor):
        """GIVEN token WHEN delete_session THEN row deleted."""
        store.delete_session("tok_abc123")
        assert "DELETE FROM user_sessions" in str(mock_cursor.execute.call_args)

    def test_cleanup_expired_sessions(self, store, mock_conn, mock_cursor):
        """GIVEN expired sessions WHEN cleanup_expired_sessions THEN deleted."""
        store.cleanup_expired_sessions()
        assert "DELETE FROM user_sessions" in str(mock_cursor.execute.call_args)
        assert "expires_at" in str(mock_cursor.execute.call_args)


# ═══════════════════════════════════════════════════════════════════════
# Spec Cache
# ═══════════════════════════════════════════════════════════════════════


class TestSpecCache:
    """Spec cache tests."""

    def test_cache_spec_parse(self, store, mock_conn, mock_cursor):
        """GIVEN spec_path and mtime WHEN cache_spec_parse THEN cached."""
        result = {"requirements": ["RS-001", "RS-002"]}
        store.cache_spec_parse("/specs/test.md", 12345.678, result)
        assert "INSERT INTO spec_cache" in str(mock_cursor.execute.call_args) or "ON CONFLICT" in str(mock_cursor.execute.call_args)
        assert mock_conn.commit.called

    def test_get_cached_spec_parse_hit(self, store, mock_cursor):
        """GIVEN cached spec WHEN get_cached_spec_parse THEN returns parsed result."""
        mock_cursor.fetchone.return_value = (json.dumps({"reqs": ["RS-001"]}),)
        result = store.get_cached_spec_parse("/specs/test.md", 12345.678)
        assert result == {"reqs": ["RS-001"]}

    def test_get_cached_spec_parse_miss(self, store, mock_cursor):
        """GIVEN uncached spec WHEN get_cached_spec_parse THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_cached_spec_parse("/unknown.md", 0)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════
# API Keys
# ═══════════════════════════════════════════════════════════════════════


class TestApiKeys:
    """API Key management tests."""

    def test_create_api_key(self, store, mock_cursor):
        """GIVEN key_hash and label WHEN create_api_key THEN key created."""
        mock_cursor.fetchone.return_value = (1,)
        result = store.create_api_key("sha256hash", "CI Key", "yk_")
        assert result["id"] == 1
        assert result["label"] == "CI Key"
        assert result["prefix"] == "yk_"
        assert result["revoked"] == 0

    def test_get_api_key_by_hash_found(self, store, mock_cursor):
        """GIVEN key_hash WHEN get_api_key_by_hash THEN returns key."""
        mock_cursor.fetchone.return_value = (1, "hash123", "My Key", "yk_", "2025-01-01", None, 0)
        mock_cursor.description = [("id",), ("key_hash",), ("label",), ("prefix",), ("created_at",), ("last_used_at",), ("revoked",)]
        result = store.get_api_key_by_hash("hash123")
        assert result["label"] == "My Key"

    def test_get_api_key_by_hash_not_found(self, store, mock_cursor):
        """GIVEN unknown hash WHEN get_api_key_by_hash THEN None."""
        mock_cursor.fetchone.return_value = None
        assert store.get_api_key_by_hash("unknown") is None

    def test_list_api_keys(self, store, mock_cursor):
        """GIVEN stored keys WHEN list_api_keys THEN returns list."""
        mock_cursor.fetchall.return_value = [(1, "Key 1", "yk_", "2025-01-01", None, 0)]
        mock_cursor.description = [("id",), ("label",), ("prefix",), ("created_at",), ("last_used_at",), ("revoked",)]
        result = store.list_api_keys()
        assert len(result) == 1
        assert result[0]["label"] == "Key 1"

    def test_revoke_api_key_success(self, store, mock_conn, mock_cursor):
        """GIVEN active key WHEN revoke_api_key THEN revoked."""
        mock_cursor.rowcount = 1
        assert store.revoke_api_key(1) is True
        assert "UPDATE api_keys" in str(mock_cursor.execute.call_args)

    def test_revoke_api_key_already_revoked(self, store, mock_conn, mock_cursor):
        """GIVEN already revoked key WHEN revoke_api_key THEN returns False."""
        mock_cursor.rowcount = 0
        assert store.revoke_api_key(999) is False

    def test_update_api_key_last_used(self, store, mock_conn, mock_cursor):
        """GIVEN key_id WHEN update_api_key_last_used THEN updated."""
        store.update_api_key_last_used(1)
        assert "UPDATE api_keys" in str(mock_cursor.execute.call_args)


# ═══════════════════════════════════════════════════════════════════════
# Pipelines
# ═══════════════════════════════════════════════════════════════════════


class TestPipelines:
    """Pipeline CRUD tests."""

    def test_save_pipeline(self, store, mock_conn, mock_cursor):
        """GIVEN name and data WHEN save_pipeline THEN upserted."""
        data = {"spec_path": "/path/to/spec.md", "status": "running", "steps": ["build", "test"]}
        store.save_pipeline("test-pipe", data)
        assert "INSERT INTO pipelines" in str(mock_cursor.execute.call_args)
        assert mock_conn.commit.called

    def test_get_pipeline_found(self, store, mock_cursor):
        """GIVEN existing name WHEN get_pipeline THEN returns dict."""
        row = (1, "test-pipe", "/spec", "completed", "2025-01-01", "2025-01-02", "{}", "[]", "[]")
        mock_cursor.fetchone.return_value = row
        mock_cursor.description = [("id",), ("name",), ("spec_path",), ("status",), ("created_at",), ("updated_at",), ("artifacts",), ("steps",), ("errors",)]
        result = store.get_pipeline("test-pipe")
        assert result["name"] == "test-pipe"
        assert result["status"] == "completed"

    def test_get_pipeline_not_found(self, store, mock_cursor):
        """GIVEN non-existent name WHEN get_pipeline THEN None."""
        mock_cursor.fetchone.return_value = None
        assert store.get_pipeline("nonexistent") is None

    def test_list_pipelines(self, store, mock_cursor):
        """GIVEN pipelines WHEN list_pipelines THEN returns list."""
        mock_cursor.fetchall.return_value = [
            ("pipe-1", "completed", "2025-01-01", "2025-01-02"),
            ("pipe-2", "running", "2025-01-03", "2025-01-03"),
        ]
        mock_cursor.description = [("name",), ("status",), ("created_at",), ("updated_at",)]
        result = store.list_pipelines()
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════════════════
# CI Runs
# ═══════════════════════════════════════════════════════════════════════


class TestCiRuns:
    """CI Run CRUD tests."""

    def test_save_ci(self, store, mock_conn, mock_cursor):
        """GIVEN CI data WHEN save_ci THEN row inserted."""
        data = {"layer": 1, "commit": "abc123", "status": "passed", "coverage": {"line": 85.0}}
        store.save_ci(data)
        assert "INSERT INTO ci_runs" in str(mock_cursor.execute.call_args)

    def test_list_ci_default_limit(self, store, mock_cursor):
        """GIVEN CI runs WHEN list_ci THEN returns list with limit 10."""
        mock_cursor.fetchall.return_value = []
        result = store.list_ci()
        assert result == []

    def test_list_ci_custom_limit(self, store, mock_cursor):
        """GIVEN CI runs WHEN list_ci(limit=5) THEN respects limit."""
        mock_cursor.fetchall.return_value = []
        store.list_ci(limit=5)
        args, kwargs = mock_cursor.execute.call_args
        assert args[1] == (5,)


# ═══════════════════════════════════════════════════════════════════════
# Reviews
# ═══════════════════════════════════════════════════════════════════════


class TestReviews:
    """Review CRUD tests."""

    def test_save_review(self, store, mock_conn, mock_cursor):
        """GIVEN task_name and data WHEN save_review THEN upserted."""
        data = {"decision": "approved", "status": "completed"}
        store.save_review("review-1", data)
        assert "INSERT INTO reviews" in str(mock_cursor.execute.call_args)

    def test_list_reviews_default_limit(self, store, mock_cursor):
        """GIVEN reviews WHEN list_reviews THEN returns list with limit."""
        store.list_reviews()
        args, kwargs = mock_cursor.execute.call_args
        assert args[1] == (10,)

    def test_list_reviews_custom_limit(self, store, mock_cursor):
        """GIVEN reviews WHEN list_reviews(5) THEN respects limit."""
        store.list_reviews(limit=5)
        args, kwargs = mock_cursor.execute.call_args
        assert args[1] == (5,)


# ═══════════════════════════════════════════════════════════════════════
# Evidence
# ═══════════════════════════════════════════════════════════════════════


class TestEvidence:
    """Evidence logging tests."""

    def test_log_evidence_with_size(self, store, mock_conn, mock_cursor):
        """GIVEN evidence data WITH size WHEN log_evidence THEN logged."""
        store.log_evidence("test-output.xml", "junit", "/reports/junit.xml", size=2048)
        assert "INSERT INTO evidence" in str(mock_cursor.execute.call_args)

    def test_log_evidence_without_size(self, store, mock_conn, mock_cursor):
        """GIVEN evidence data WITHOUT size WHEN log_evidence THEN defaults to 0."""
        store.log_evidence("output.log", "text", "/logs/output.log")
        assert "INSERT INTO evidence" in str(mock_cursor.execute.call_args)

    def test_list_evidence(self, store, mock_cursor):
        """GIVEN evidence WHEN list_evidence THEN returns list."""
        mock_cursor.fetchall.return_value = [
            (1, "report.xml", "junit", "/path/to/report.xml", 1024, "2025-01-01"),
        ]
        mock_cursor.description = [("id",), ("name",), ("type",), ("path",), ("size",), ("created_at",)]
        result = store.list_evidence()
        assert len(result) == 1
        assert result[0]["name"] == "report.xml"


# ═══════════════════════════════════════════════════════════════════════
# Projects
# ═══════════════════════════════════════════════════════════════════════


class TestProjects:
    """Project tests."""

    def test_init_project(self, store, mock_conn, mock_cursor):
        """GIVEN project name WHEN init_project THEN inserted."""
        store.init_project("My App", "My awesome app")
        assert "INSERT INTO projects" in str(mock_cursor.execute.call_args)

    def test_get_project_found(self, store, mock_cursor):
        """GIVEN existing project WHEN get_project THEN returns dict."""
        row = (1, "My App", "desc", "/spec", "2025-01-01", "2025-06-01", 10, "2025-06-15")
        mock_cursor.fetchone.return_value = row
        mock_cursor.description = [("id",), ("name",), ("description",), ("spec_path",), ("created_at",), ("updated_at",), ("pipeline_run_count",), ("last_active_at",)]
        result = store.get_project("My App")
        assert result["name"] == "My App"
        assert result["pipeline_run_count"] == 10

    def test_get_project_not_found(self, store, mock_cursor):
        """GIVEN non-existent project WHEN get_project THEN None."""
        mock_cursor.fetchone.return_value = None
        assert store.get_project("nonexistent") is None


# ═══════════════════════════════════════════════════════════════════════
# Usage & Subscription
# ═══════════════════════════════════════════════════════════════════════


class TestUsage:
    """Usage recording tests."""

    def test_record_usage(self, store, mock_conn, mock_cursor):
        """GIVEN usage data WHEN record_usage THEN logged."""
        store.record_usage(1, 100, "pipeline_runs", 1)
        assert "INSERT INTO usage_log" in str(mock_cursor.execute.call_args)

    def test_get_monthly_usage(self, store, mock_cursor):
        """GIVEN org_id WHEN get_monthly_usage THEN returns aggregated."""
        mock_cursor.fetchall.return_value = [("pipeline_runs", 42)]
        # Second query for project count
        mock_cursor.fetchone.return_value = (5,)
        result = store.get_monthly_usage(1)
        assert result["pipeline_runs"] == 42
        assert result["project_count"] == 5


class TestSubscription:
    """Subscription tests."""

    def test_get_subscription_found(self, store, mock_cursor):
        """GIVEN org_id WHEN get_subscription THEN returns dict."""
        row = (1, 1, "sub_abc", "cus_xyz", "enterprise", "active", "2025-12-31", "2025-01-01")
        mock_cursor.fetchone.return_value = row
        mock_cursor.description = [("id",), ("org_id",), ("stripe_subscription_id",), ("stripe_customer_id",), ("tier",), ("status",), ("current_period_end",), ("created_at",)]
        result = store.get_subscription(1)
        assert result["tier"] == "enterprise"

    def test_get_subscription_not_found(self, store, mock_cursor):
        """GIVEN org without subscription WHEN get_subscription THEN None."""
        mock_cursor.fetchone.return_value = None
        assert store.get_subscription(999) is None

    def test_upsert_subscription_new(self, store, mock_cursor):
        """GIVEN new org WHEN upsert_subscription THEN inserted."""
        mock_cursor.fetchone.return_value = None
        data = {"stripe_subscription_id": "sub_new", "stripe_customer_id": "cus_new", "tier": "pro"}
        store.upsert_subscription(1, data)
        # Should do INSERT path (no existing)
        assert "INSERT INTO subscriptions" in str(mock_cursor.execute.call_args)

    def test_upsert_subscription_update(self, store, mock_cursor):
        """GIVEN existing org WHEN upsert_subscription THEN updated."""
        mock_cursor.fetchone.side_effect = [
            (1, 1, "sub_old", "cus_old", "pro", "active", "2025-06-30", "2025-01-01"),  # existing subscription
        ]
        data = {"stripe_subscription_id": "sub_new", "status": "canceled"}
        # Mock _row_to_dict by having cursor return a row that can be indexed
        mock_cursor.description = [("id",), ("org_id",), ("stripe_subscription_id",), ("stripe_customer_id",), ("tier",), ("status",), ("current_period_end",), ("created_at",)]
        store.upsert_subscription(1, data)
        # Should do UPDATE path
        actual_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        has_update = any("UPDATE subscriptions" in c for c in actual_calls)
        assert has_update

    def test_update_org_tier(self, store, mock_conn, mock_cursor):
        """GIVEN org_id WHEN update_org_tier THEN updated."""
        store.update_org_tier(1, "enterprise")
        assert "UPDATE organizations" in str(mock_cursor.execute.call_args)

    def test_get_org_by_stripe_subscription_found(self, store, mock_cursor):
        """GIVEN sub_id WHEN get_org_by_stripe_subscription THEN returns org."""
        mock_cursor.fetchone.side_effect = [
            (7,),  # org_id from subscriptions query
            (7, "Charlie Inc", "charlie", "pro", "2025-01-01"),  # org from get_organization_by_id
        ]
        mock_cursor.description = [("id",), ("name",), ("slug",), ("tier",), ("created_at",)]
        result = store.get_org_by_stripe_subscription("sub_xyz")
        assert result["name"] == "Charlie Inc"

    def test_get_org_by_stripe_subscription_not_found(self, store, mock_cursor):
        """GIVEN unknown sub WHEN get_org_by_stripe_subscription THEN None."""
        mock_cursor.fetchone.return_value = None
        assert store.get_org_by_stripe_subscription("sub_unknown") is None


# ═══════════════════════════════════════════════════════════════════════
# Stats & Admin
# ═══════════════════════════════════════════════════════════════════════


class TestStats:
    """Usage stats tests."""

    def test_record_activity(self, store, mock_conn, mock_cursor):
        """GIVEN project name WHEN record_activity THEN incremented."""
        store.record_activity("My App")
        assert "UPDATE projects" in str(mock_cursor.execute.call_args)

    def test_get_total_users(self, store, mock_cursor):
        """GIVEN users WHEN get_total_users THEN returns count."""
        mock_cursor.fetchone.return_value = (42,)
        assert store.get_total_users() == 42

    def test_get_total_projects(self, store, mock_cursor):
        """GIVEN projects WHEN get_total_projects THEN returns sum."""
        mock_cursor.fetchone.side_effect = [(10,), (3,)]
        assert store.get_total_projects() == 13

    def test_get_usage_stats(self, store, mock_cursor):
        """GIVEN data WHEN get_usage_stats THEN returns aggregated.
        Note: get_usage_stats() also calls get_total_users() which does a fetchone."""
        mock_cursor.fetchone.side_effect = [(100,), (50,), (30,), (200,), (20,), (5,), (42,)]
        mock_cursor.fetchall.side_effect = [
            [("completed", 60), ("running", 40)],
            [(1, 30), (2, 20)],
        ]
        result = store.get_usage_stats()
        assert result["total_pipelines"] == 100
        assert result["total_ci_runs"] == 50
        assert result["total_reviews"] == 30
        assert result["total_evidence"] == 200
        assert result["pipeline_statuses"]["completed"] == 60


class TestWizard:
    """Wizard state tests."""

    def test_is_wizard_completed_true(self, store, mock_cursor):
        """GIVEN wizard completed WHEN is_wizard_completed THEN True."""
        mock_cursor.fetchone.return_value = ("1",)
        assert store.is_wizard_completed() is True

    def test_is_wizard_completed_false(self, store, mock_cursor):
        """GIVEN wizard not completed WHEN is_wizard_completed THEN False."""
        mock_cursor.fetchone.return_value = None
        assert store.is_wizard_completed() is False

    def test_complete_wizard(self, store, mock_conn, mock_cursor):
        """GIVEN incomplete wizard WHEN complete_wizard THEN marked complete."""
        store.complete_wizard(org_id=1)
        assert "INSERT INTO _meta" in str(mock_cursor.execute.call_args)

    def test_get_migration_version_migrated(self, store, mock_cursor):
        """GIVEN migrated store WHEN get_migration_version THEN returns version."""
        mock_cursor.fetchone.return_value = (7,)
        assert store.get_migration_version() == 7

    def test_get_migration_version_not_migrated(self, store, mock_cursor):
        """GIVEN fresh store WHEN get_migration_version THEN returns 0."""
        mock_cursor.fetchone.return_value = None
        assert store.get_migration_version() == 0


# ═══════════════════════════════════════════════════════════════════════
# Error Handling
# ═══════════════════════════════════════════════════════════════════════


class TestErrorHandling:
    """Error handling tests."""

    def test_db_connection_failure(self, monkeypatch):
        """GIVEN instance without connection WHEN conn accessed THEN exception propagated."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore._instances = {}
        s = PostgresStore.__new__(PostgresStore)
        # Bypass _local.conn to force reconnection
        s.dsn = "postgresql://test:test@localhost:5432/testdb"
        s._local = threading.local()
        # Don't set _local.conn so it tries psycopg2.connect
        with patch("psycopg2.connect", side_effect=Exception("Could not connect to server")):
            with pytest.raises(Exception, match="Could not connect"):
                _ = s.conn

    def test_create_organization_with_conflict(self, store, mock_cursor):
        """GIVEN duplicate slug WHEN create_organization THEN error propagated."""
        mock_cursor.execute.side_effect = Exception('duplicate key value violates unique constraint "organizations_slug_key"')
        with pytest.raises(Exception, match="duplicate key"):
            store.create_organization("Duplicate", "acme")

    def test_get_nonexistent_user_returns_none(self, store, mock_cursor):
        """GIVEN non-existent user WHEN get_user THEN returns None."""
        mock_cursor.fetchone.return_value = None
        result = store.get_user(999, "nobody@nowhere.com")
        assert result is None

    def test_transaction_commit_failure(self, store, mock_conn, mock_cursor):
        """GIVEN commit failure WHEN CRUD operation THEN error propagated."""
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.commit.side_effect = Exception("Commit failed")
        with pytest.raises(Exception, match="Commit failed"):
            store.create_organization("Fail", "fail")


# ═══════════════════════════════════════════════════════════════════════
# Thread Safety
# ═══════════════════════════════════════════════════════════════════════


class TestThreadSafety:
    """Thread safety tests."""

    def test_concurrent_create_organization(self, store):
        """GIVEN multiple threads WHEN creating organizations THEN no race conditions."""
        lock = threading.Lock()
        results = []
        errors = []

        # Each thread creates its own mock connection via patched psycopg2.connect
        def make_thread_mock():
            c = MagicMock()
            cur = MagicMock()
            cur.fetchone.return_value = (42,)
            cur.__enter__.return_value = cur
            c.cursor.return_value = cur
            return c

        def create_org(idx):
            try:
                # In new thread, _local.conn doesn't exist, so conn property
                # calls psycopg2.connect() which is patched by autouse fixture
                result = store.create_organization(f"Org-{idx}", f"org-{idx}")
                with lock:
                    results.append(result)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=create_org, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5, f"Expected 5 results, got {len(results)}, errors: {errors}"
        assert len(errors) == 0, f"Errors: {errors}"

    def test_concurrent_reads(self, store, mock_cursor):
        """GIVEN multiple threads WHEN reading THEN no errors."""
        errors = []

        def read_org():
            try:
                with patch.object(type(store), 'conn', new_callable=lambda: MagicMock()):
                    store.list_organizations()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_org) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_thread_local_connections(self):
        """GIVEN store with thread-local connections WHEN accessed THEN isolated."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore._instances = {}

        connections = {}
        lock = threading.Lock()

        def thread_work(tid):
            with patch("psycopg2.connect") as mock_connect:
                mock_conn = MagicMock()
                mock_conn.closed = False
                mock_connect.return_value = mock_conn

                s = PostgresStore.__new__(PostgresStore)
                s.dsn = "postgresql://test:test@localhost:5432/testdb"
                s._local = threading.local()
                s._local.conn = mock_conn

                c = s.conn
                with lock:
                    connections[tid] = c

        threads = [threading.Thread(target=thread_work, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(connections) == 3
        # Verify they're different connections
        conn_ids = [id(c) for c in connections.values()]
        assert len(set(conn_ids)) == 3


# ═══════════════════════════════════════════════════════════════════════
# Setup & Singleton Reset
# ═══════════════════════════════════════════════════════════════════════


class TestSetup:
    """Setup and lifecycle tests."""

    def test_explicit_setup(self, monkeypatch, mock_conn, mock_cursor):
        """GIVEN store without schema WHEN setup THEN migration runs."""
        monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://test:test@localhost:5432/testdb")
        from yuleosh.store_pg import PostgresStore
        PostgresStore._instances = {}

        with patch("psycopg2.connect", return_value=mock_conn):
            s = PostgresStore.__new__(PostgresStore)
            s.dsn = "postgresql://test:test@localhost:5432/testdb"
            s._local = threading.local()
            s._local.conn = mock_conn

            # capture calls before setup
            mock_cursor.execute.reset_mock()
            s.setup()
            assert mock_cursor.execute.called
            s.close()

    def test_store_reuses_after_reset(self, monkeypatch, mock_conn):
        """GIVEN reset store WHEN new instance created THEN works."""
        monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://test:test@localhost:5432/testdb")
        from yuleosh.store_pg import PostgresStore
        PostgresStore._instances = {}

        with patch("psycopg2.connect", return_value=mock_conn):
            s1 = PostgresStore()
            PostgresStore.reset()
            s2 = PostgresStore()
            assert s2 is not s1
            assert PostgresStore._instances["default"] is s2
