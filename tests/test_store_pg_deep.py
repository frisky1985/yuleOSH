# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for yuleosh.store_pg — mock psycopg2, no real DB.

Target: 40%+ branch coverage of store_pg.py (300 lines).
Covers: singleton, connection lifecycle, migration, all CRUD methods,
        usage stats, wizard helpers, _row_to_dict, edge cases.
"""

import json
import os
import sys
import threading
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ==================================================================
# Fixtures — mock psycopg2 at module boundary so store never hits real DB
# ==================================================================

@pytest.fixture
def mock_db():
    """Build and return (mock_conn, mock_cursor, mock_psycopg2).

    The cursor is set up as a proper context-manager so that
    ``with self.conn.cursor() as cur:`` in PostgresStore methods
    passes the same mock cursor into the ``cur`` variable.
    """
    from yuleosh import store_pg
    store_pg.PostgresStore.reset()

    # Build a mock cursor that works as a context manager
    # (conn.cursor().__enter__() → same cursor)
    mock_cursor = mock.MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = None

    # Default: no rows returned
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.rowcount = 0

    mock_conn = mock.MagicMock()
    mock_conn.closed = False
    mock_conn.cursor.return_value = mock_cursor

    mock_psycopg2 = mock.MagicMock()
    mock_psycopg2.connect.return_value = mock_conn

    with mock.patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
        yield mock_conn, mock_cursor, mock_psycopg2


@pytest.fixture
def store(mock_db):
    """Fresh PostgresStore instance wired to the mock DB."""
    from yuleosh.store_pg import PostgresStore
    conn, cursor, _ = mock_db
    # The reset in mock_db already cleared instances; create a new one
    s = PostgresStore(dsn="postgresql://test:test@localhost:5432/test")
    yield s
    PostgresStore.reset()


@pytest.fixture
def store_with_conn(store, mock_db):
    """Helper variant that also returns (store, cursor, conn)."""
    conn, cursor, _ = mock_db
    return store, cursor, conn


# ==================================================================
# Singleton & Connection
# ==================================================================

class TestSingleton:
    """GIVEN PostgresStore WHEN multiple instantiations THEN returns same instance."""

    def test_singleton_default(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        with mock.patch.dict(os.environ, {"YULEOSH_DB_URL": "pg://default:default@h/default"}):
            s1 = PostgresStore()
            s2 = PostgresStore()
        assert s1 is s2

    def test_singleton_different_dsn(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        s1 = PostgresStore(dsn="postgresql://a:b@h:5432/d1")
        s2 = PostgresStore(dsn="postgresql://a:b@h:5432/d2")
        assert s1 is not s2

    def test_singleton_same_key(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        s1 = PostgresStore(dsn="pg://a:b@h/d")
        s2 = PostgresStore(dsn="pg://a:b@h/d")
        assert s1 is s2

    def test_reset_clears_cache(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        with mock.patch.dict(os.environ, {"YULEOSH_DB_URL": "pg://default:default@h/default"}):
            _ = PostgresStore()
        PostgresStore.reset()
        assert len(PostgresStore._instances) == 0

    def test_dsn_from_env(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        with mock.patch.dict(os.environ, {"YULEOSH_DB_URL": "pg://env:var@h/db"}):
            s = PostgresStore()
            assert s.dsn == "pg://env:var@h/db"

    def test_thread_safety(self, mock_db):
        """GIVEN concurrent access WHEN __new__ THEN no race."""
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        instances = {}

        def create_instance(key):
            s = PostgresStore(dsn=f"pg://t:t@h/{key}")
            instances[key] = id(s)

        threads = [threading.Thread(target=create_instance, args=(str(i),))
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(instances.values())) == 10


class TestConnection:
    """GIVEN PostgresStore WHEN conn property accessed THEN connects."""

    def test_conn_property_creates(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        conn, cursor, mock_psycopg2 = mock_db
        s = PostgresStore(dsn="pg://t:t@h/t")
        # Clear any cached connection from the per-thread store
        if hasattr(s._local, 'conn'):
            s._local.conn = None
        c = s.conn
        assert c is not None

    def test_conn_property_reuses(self, store, mock_db):
        conn, cursor, _ = mock_db
        c1 = store.conn
        c2 = store.conn
        assert c1 is c2

    def test_close_sets_none(self, store, mock_db):
        conn, cursor, _ = mock_db
        store.close()
        assert not hasattr(store._local, 'conn') or store._local.conn is None

    def test_close_already_none(self, store, mock_db):
        if hasattr(store._local, 'conn'):
            store._local.conn = None
        store.close()

    def test_conn_reconnects_if_closed(self, store, mock_db):
        conn, cursor, mock_psycopg2 = mock_db
        # Simulate closed connection
        store._local.conn = conn
        conn.closed = True
        c = store.conn
        assert c is not None


# ==================================================================
# Schema & Migration
# ==================================================================

class TestMigration:
    """GIVEN PostgresStore WHEN _ensure_schema / _migrate THEN SQL executed."""

    def test_ensure_schema(self, store, mock_db):
        conn, cursor, _ = mock_db
        store._ensure_schema()
        assert cursor.execute.call_count >= 1
        conn.commit.assert_called()

    def test_migrate(self, store, mock_db):
        conn, cursor, _ = mock_db
        store._migrate()
        assert cursor.execute.call_count >= 4
        conn.commit.assert_called()

    def test_migrate_called_on_init(self, mock_db):
        from yuleosh.store_pg import PostgresStore
        PostgresStore.reset()
        with mock.patch.object(PostgresStore, "_migrate") as mm:
            PostgresStore(dsn="pg://x:x@h/x")
            mm.assert_called_once()


# ==================================================================
# Organizations
# ==================================================================

class TestOrganizations:
    """GIVEN organization CRUD methods WHEN called THEN correct SQL."""

    def test_create_organization(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [42]

        result = store.create_organization("My Org", "my-org")
        assert result["id"] == 42
        assert result["name"] == "My Org"
        assert result["slug"] == "my-org"
        assert "created_at" in result
        conn.commit.assert_called()

    def test_get_organization_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(["id", "name", "slug", "tier", "created_at"])
        cursor.fetchone.return_value = [1, "Acme", "acme", "pro", "2025-01-01"]

        result = store.get_organization("acme")
        assert result["id"] == 1
        assert result["name"] == "Acme"

    def test_get_organization_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_organization("nope") is None

    def test_get_organization_by_id_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(["id", "name", "slug", "tier", "created_at"])
        cursor.fetchone.return_value = [2, "Beta", "beta", "enterprise", "2025-02-01"]
        result = store.get_organization_by_id(2)
        assert result["id"] == 2

    def test_get_organization_by_id_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_organization_by_id(999) is None

    def test_list_organizations(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(["id", "name", "slug", "tier", "created_at"])
        cursor.fetchall.return_value = [[1, "Acme", "acme", "pro", "2025-01-01"],
                                         [2, "Beta", "beta", "ent", "2025-02-01"]]
        results = store.list_organizations()
        assert len(results) == 2


# ==================================================================
# Users
# ==================================================================

class TestUsers:
    """GIVEN user CRUD methods WHEN called THEN correct SQL."""

    def test_create_user(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [100]
        result = store.create_user(1, "alice@example.com", "admin", "hash123")
        assert result["id"] == 100
        assert result["email"] == "alice@example.com"
        assert result["role"] == "admin"

    def test_create_user_default_role(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [101]
        result = store.create_user(1, "bob@example.com")
        assert result["role"] == "member"

    def test_create_user_no_password(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [102]
        result = store.create_user(2, "carol@example.com")
        assert result["password_hash"] is None

    def test_get_user_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "email", "role", "password_hash", "created_at"])
        cursor.fetchone.return_value = [100, 1, "alice@example.com", "admin", "hash", "2025-01-01"]
        result = store.get_user(1, "alice@example.com")
        assert result["email"] == "alice@example.com"

    def test_get_user_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_user(1, "nobody@example.com") is None

    def test_get_user_by_id_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "email", "role", "password_hash", "created_at"])
        cursor.fetchone.return_value = [100, 1, "cat@example.com", "member", None, "2025-01-01"]
        result = store.get_user_by_id(100)
        assert result["id"] == 100
        assert result["email"] == "cat@example.com"

    def test_get_user_by_id_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_user_by_id(999) is None

    def test_list_users(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(["id", "email", "role", "created_at"])
        cursor.fetchall.return_value = [[1, "a@b.com", "admin", "2025-01-01"],
                                         [2, "b@b.com", "member", "2025-01-02"]]
        results = store.list_users(1)
        assert len(results) == 2


# ==================================================================
# Org Projects
# ==================================================================

class TestOrgProjects:
    """GIVEN org project CRUD methods WHEN called THEN correct SQL."""

    def test_create_org_project(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [200]
        result = store.create_org_project(1, "Project X", "proj-x", "desc")
        assert result["id"] == 200
        assert result["name"] == "Project X"
        assert result["slug"] == "proj-x"
        assert result["description"] == "desc"

    def test_create_org_project_default_desc(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [201]
        result = store.create_org_project(1, "P2", "p2")
        assert result["description"] == ""

    def test_get_org_project_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "name", "slug", "description", "created_at"])
        cursor.fetchone.return_value = [200, 1, "X", "x", "desc", "2025-01-01"]
        result = store.get_org_project(1, "x")
        assert result["name"] == "X"

    def test_get_org_project_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_org_project(1, "nope") is None

    def test_get_org_project_by_id_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "name", "slug", "description", "created_at"])
        cursor.fetchone.return_value = [200, 1, "Y", "y", "", "2025-01-01"]
        result = store.get_org_project_by_id(200)
        assert result["id"] == 200

    def test_get_org_project_by_id_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_org_project_by_id(999) is None

    def test_list_org_projects(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "name", "slug", "description", "created_at"])
        cursor.fetchall.return_value = [[1, 1, "A", "a", "", "2025-01-01"]]
        results = store.list_org_projects(1)
        assert len(results) == 1


# ==================================================================
# Sessions
# ==================================================================

class TestSessions:
    """GIVEN session methods WHEN called THEN correct SQL."""

    def test_create_session(self, store_with_conn):
        store, cursor, conn = store_with_conn
        result = store.create_session(1, "tok_abc", ttl_hours=24)
        assert result["user_id"] == 1
        assert result["token"] == "tok_abc"
        assert "expires_at" in result
        conn.commit.assert_called()

    def test_get_session_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "user_id", "token", "created_at", "expires_at"])
        cursor.fetchone.return_value = [1, 1, "tok_abc", "2025-01-01", "2099-01-01"]
        result = store.get_session("tok_abc")
        assert result["token"] == "tok_abc"

    def test_get_session_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_session("unknown_tok") is None

    def test_get_session_expired_by_timestamp(self, store_with_conn):
        store, cursor, conn = store_with_conn
        # mock fetchone returns None → no valid session found
        cursor.fetchone.return_value = None
        assert store.get_session("expired") is None

    def test_delete_session(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.delete_session("tok_del")
        assert cursor.execute.call_count >= 1
        conn.commit.assert_called()

    def test_cleanup_expired_sessions(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.cleanup_expired_sessions()
        assert cursor.execute.call_count >= 1
        conn.commit.assert_called()


# ==================================================================
# Spec Cache
# ==================================================================

class TestSpecCache:
    """GIVEN spec cache methods WHEN called THEN SQL executed."""

    def test_cache_spec_parse(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.cache_spec_parse("/path/spec.md", 12345.0, {"status": "ok"})
        conn.commit.assert_called()

    def test_get_cached_spec_parse_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        data = json.dumps({"status": "ok", "tasks": ["a"]})
        cursor.fetchone.return_value = [data]
        result = store.get_cached_spec_parse("/path/spec.md", 12345.0)
        assert result["status"] == "ok"

    def test_get_cached_spec_parse_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_cached_spec_parse("/path/spec.md", 12345.0) is None


# ==================================================================
# API Keys
# ==================================================================

class TestApiKeys:
    """GIVEN API key methods WHEN called THEN correct SQL."""

    def test_create_api_key(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [300]
        result = store.create_api_key("hash_abc", "My Key", "my_")
        assert result["id"] == 300
        assert result["label"] == "My Key"
        assert result["prefix"] == "my_"
        assert result["revoked"] == 0

    def test_get_api_key_by_hash_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "key_hash", "label", "prefix", "created_at", "last_used_at", "revoked"])
        cursor.fetchone.return_value = [300, "hash_abc", "My Key", "my_",
                                         "2025-01-01", None, 0]
        result = store.get_api_key_by_hash("hash_abc")
        assert result["label"] == "My Key"

    def test_get_api_key_by_hash_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_api_key_by_hash("nope") is None

    def test_list_api_keys(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "label", "prefix", "created_at", "last_used_at", "revoked"])
        cursor.fetchall.return_value = [[1, "K1", "k1_", "2025-01-01", None, 0]]
        results = store.list_api_keys()
        assert len(results) == 1

    def test_revoke_api_key_success(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.rowcount = 1
        assert store.revoke_api_key(300) is True

    def test_revoke_api_key_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.rowcount = 0
        assert store.revoke_api_key(300) is False

    def test_update_api_key_last_used(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.update_api_key_last_used(300)
        conn.commit.assert_called()


# ==================================================================
# Pipelines
# ==================================================================

class TestPipelines:
    """GIVEN pipeline methods WHEN called THEN correct SQL."""

    def test_save_pipeline(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.save_pipeline("pipe1", {
            "spec_path": "/path", "status": "running",
            "artifacts": {"a": 1}, "steps": ["step1"], "errors": []
        })
        conn.commit.assert_called()

    def test_get_pipeline_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "name", "spec_path", "status", "created_at", "updated_at",
             "artifacts", "steps", "errors"])
        cursor.fetchone.return_value = [1, "pipe1", "/path", "running",
                                         "2025-01-01", "2025-01-01", "{}", "[]", "[]"]
        result = store.get_pipeline("pipe1")
        assert result["name"] == "pipe1"

    def test_get_pipeline_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_pipeline("nope") is None

    def test_list_pipelines(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["name", "status", "created_at", "updated_at"])
        cursor.fetchall.return_value = [["pipe1", "running", "2025-01-01", "2025-01-01"]]
        results = store.list_pipelines()
        assert len(results) == 1


# ==================================================================
# CI Runs
# ==================================================================

class TestCiRuns:
    """GIVEN CI run methods WHEN called THEN correct SQL."""

    def test_save_ci(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.save_ci({
            "layer": 1, "commit": "abc", "status": "passed",
            "stages": ["build"], "coverage": 85.0, "errors": []
        })
        conn.commit.assert_called()

    def test_save_ci_with_nulls(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.save_ci({"layer": 2, "commit": "def", "status": "running"})
        conn.commit.assert_called()

    def test_list_ci(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "layer", "commit_hash", "status", "started_at",
             "completed_at", "stages", "coverage", "errors"])
        cursor.fetchall.return_value = [
            [1, 1, "abc", "passed", "2025-01-01", None, "[]", None, "[]"]]
        results = store.list_ci(limit=5)
        assert len(results) == 1


# ==================================================================
# Reviews
# ==================================================================

class TestReviews:
    """GIVEN review methods WHEN called THEN correct SQL."""

    def test_save_review(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.save_review("review1", {"decision": "approve", "status": "completed"})
        conn.commit.assert_called()

    def test_list_reviews(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["task_name", "decision", "status", "created_at"])
        cursor.fetchall.return_value = [["r1", "approve", "completed", "2025-01-01"]]
        results = store.list_reviews(limit=10)
        assert len(results) == 1


# ==================================================================
# Evidence
# ==================================================================

class TestEvidence:
    """GIVEN evidence methods WHEN called THEN correct SQL."""

    def test_log_evidence(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.log_evidence("test.log", "file", "/path/to/log", size=1024)
        conn.commit.assert_called()

    def test_list_evidence(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "name", "type", "path", "size", "created_at"])
        cursor.fetchall.return_value = [[1, "log1", "file", "/path", 1024, "2025-01-01"]]
        results = store.list_evidence()
        assert len(results) == 1


# ==================================================================
# Projects (Legacy)
# ==================================================================

class TestProjects:
    """GIVEN project methods WHEN called THEN correct SQL."""

    def test_init_project(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.init_project("my-project", "A test project")
        conn.commit.assert_called()

    def test_get_project_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "name", "description", "spec_path", "created_at",
             "updated_at", "pipeline_run_count", "last_active_at"])
        cursor.fetchone.return_value = [1, "my-project", "desc", None,
                                         "2025-01-01", "2025-01-01", 0, None]
        result = store.get_project("my-project")
        assert result["name"] == "my-project"

    def test_get_project_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_project("nope") is None


# ==================================================================
# Usage & Subscription
# ==================================================================

class TestUsage:
    """GIVEN usage/subscription methods WHEN called THEN correct SQL."""

    def test_record_usage(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.record_usage(1, 10, "pipeline_runs", 5)
        conn.commit.assert_called()

    def test_get_monthly_usage(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchall.return_value = [("pipeline_runs", 10), ("llm_tokens", 5000)]
        cursor.fetchone.return_value = [3]
        usage = store.get_monthly_usage(1)
        assert "project_count" in usage
        assert usage["pipeline_runs"] == 10
        assert usage["llm_tokens"] == 5000
        assert usage["project_count"] == 3

    def test_get_monthly_usage_empty(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = [0]
        usage = store.get_monthly_usage(1)
        assert usage["project_count"] == 0

    def test_get_subscription_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "stripe_subscription_id", "stripe_customer_id",
             "tier", "status", "current_period_end", "created_at"])
        cursor.fetchone.return_value = [1, 1, "sub_abc", "cus_abc",
                                         "pro", "active", "2025-12-31", "2025-01-01"]
        result = store.get_subscription(1)
        assert result["org_id"] == 1
        assert result["tier"] == "pro"

    def test_get_subscription_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_subscription(1) is None

    def test_upsert_subscription_insert(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None  # no existing
        store.upsert_subscription(1, {
            "stripe_subscription_id": "sub_new", "tier": "pro", "status": "active",
        })
        conn.commit.assert_called()

    def test_upsert_subscription_update(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "org_id", "stripe_subscription_id", "stripe_customer_id",
             "tier", "status", "current_period_end", "created_at"])
        cursor.fetchone.return_value = [1, 1, "sub_old", "cus_old", "pro",
                                         "active", "2025-12-31", "2025-01-01"]

        # After the first fetch, we need to reset for any subsequent query
        store.upsert_subscription(1, {"tier": "enterprise"})
        conn.commit.assert_called()

    def test_update_org_tier(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.update_org_tier(1, "enterprise")
        conn.commit.assert_called()

    def test_get_org_by_stripe_subscription_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.description = mock_description(
            ["id", "name", "slug", "tier", "created_at"])
        # First call: fetch org_id from subscriptions
        # Second call: fetch organization by id
        cursor.fetchone.side_effect = [[1], [1, "Acme", "acme", "pro", "2025-01-01"]]
        result = store.get_org_by_stripe_subscription("sub_abc")
        assert result is not None
        assert result["name"] == "Acme"

    def test_get_org_by_stripe_subscription_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        result = store.get_org_by_stripe_subscription("sub_unknown")
        assert result is None


# ==================================================================
# Activity & Stats
# ==================================================================

class TestStats:
    """GIVEN stats methods WHEN called THEN correct SQL."""

    def test_record_activity(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.record_activity("my-project")
        conn.commit.assert_called()

    def test_get_total_users(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [42]
        assert store.get_total_users() == 42

    def test_get_total_projects(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.side_effect = [[5], [3]]
        assert store.get_total_projects() == 8

    def test_get_usage_stats(self, store_with_conn):
        store, cursor, conn = store_with_conn
        # Multiple fetchone calls for each table count
        # and fetchall for aggregate queries
        fone_values = [[10], [20], [30], [40], [50], [60], [99]]
        fall_values = [
            [("passed", 8), ("failed", 2)],       # pipeline statuses
            [("1", 15), ("2", 5)],                 # ci by layer
        ]
        cursor.fetchone.side_effect = fone_values
        cursor.fetchall.side_effect = fall_values

        stats = store.get_usage_stats()
        assert stats["total_pipelines"] == 10
        assert stats["total_ci_runs"] == 20
        assert stats["total_reviews"] == 30
        assert stats["total_evidence"] == 40
        assert stats["total_projects"] == 50
        assert stats["total_organizations"] == 60
        assert stats["total_users"] == 99
        assert stats["pipeline_statuses"]["passed"] == 8
        assert stats["ci_by_layer"]["1"] == 15

    def test_get_migration_version_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = [7]
        assert store.get_migration_version() == 7

    def test_get_migration_version_not_found(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.get_migration_version() == 0

    def test_is_wizard_completed_true(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = ("1",)
        assert store.is_wizard_completed() is True

    def test_is_wizard_completed_false_due_to_value(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = ("0",)
        assert store.is_wizard_completed() is False

    def test_is_wizard_no_row(self, store_with_conn):
        store, cursor, conn = store_with_conn
        cursor.fetchone.return_value = None
        assert store.is_wizard_completed() is False

    def test_complete_wizard(self, store_with_conn):
        store, cursor, conn = store_with_conn
        store.complete_wizard()
        conn.commit.assert_called()


# ==================================================================
# _row_to_dict helper
# ==================================================================

class TestRowToDict:
    """GIVEN _row_to_dict WHEN called THEN maps columns to values."""

    def test_row_to_dict_basic(self, store, mock_db):
        conn, cursor, _ = mock_db
        # We don't use store_with_conn because we need custom cursor
        store = store  # Already provided
        mock_cursor = mock.MagicMock()
        mock_cursor.description = [["id"], ["name"], ["email"]]
        result = store._row_to_dict(mock_cursor, [1, "Alice", "a@b.com"])
        assert result == {"id": 1, "name": "Alice", "email": "a@b.com"}

    def test_row_to_dict_empty(self, store, mock_db):
        conn, cursor, _ = mock_db
        mock_cursor = mock.MagicMock()
        mock_cursor.description = []
        result = store._row_to_dict(mock_cursor, [])
        assert result == {}


# ==================================================================
# Helpers
# ==================================================================

def mock_description(names: list[str]) -> list[list[str]]:
    """Build a cursor.description-like list from column names."""
    return [[n] for n in names]
