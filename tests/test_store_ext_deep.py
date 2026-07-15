"""Depth tests for store.py — migrations, activity tracking, subscription/usage CRUD.

Covers:
  - _run_migration_v3/v6/v7: ALTER TABLE safety
  - record_activity: increment pipeline run count
  - get_total_users: count aggregation
  - record_usage: usage logging
  - get_monthly_usage: aggregation by resource
  - get_subscription / upsert_subscription: create and update
  - update_org_tier: tier change
  - get_org_by_stripe_subscription: lookup by sub ID
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.store import Store


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def store():
    """Create a Store with a temporary SQLite DB."""
    Store.reset()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        s = Store(db_path)
        yield s
        s.close()


@pytest.fixture
def store_with_data(store):
    """Store with seeded projects and org data for usage/subscription tests."""
    store.conn.execute(
        "INSERT INTO projects (name, description) VALUES (?, ?)",
        ("test-project", "Test project")
    )
    store.conn.commit()

    # Create an org
    store.conn.execute(
        "INSERT INTO organizations (name, slug, created_at) VALUES (?, ?, datetime('now'))",
        ("TestOrg", "test-org")
    )
    store.conn.commit()

    # Create org_projects link
    store.conn.execute(
        "INSERT INTO org_projects (org_id, name, slug, description, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (1, "test-project", "test-project", "Test project")
    )
    store.conn.commit()

    # Create the usage_log table if it doesn't exist yet
    store.conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER,
            project_id INTEGER,
            resource TEXT,
            amount INTEGER,
            recorded_at TEXT
        )
    """)
    store.conn.commit()

    # Create subscriptions table
    store.conn.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER UNIQUE,
            stripe_subscription_id TEXT,
            stripe_customer_id TEXT,
            tier TEXT,
            status TEXT,
            current_period_end TEXT,
            created_at TEXT
        )
    """)
    store.conn.commit()

    return store


# ── Migrations ────────────────────────────────────────────────────────

class TestMigrations:
    def test_migration_v3(self, store):
        """GIVEN existing projects table WHEN running migration v3 THEN adds columns safely."""
        store._run_migration_v3()
        # Verify columns exist
        cols = {row[1] for row in store.conn.execute("PRAGMA table_info(projects)")}
        assert "pipeline_run_count" in cols
        assert "last_active_at" in cols

    def test_migration_v3_idempotent(self, store):
        """GIVEN migration already run WHEN running again THEN no error."""
        store._run_migration_v3()
        store._run_migration_v3()  # Second call should not raise

    def test_migration_v6(self, store):
        """GIVEN existing users table WHEN running migration v6 THEN adds password_hash."""
        store.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT
            )
        """)
        store.conn.commit()
        store._run_migration_v6()
        cols = {row[1] for row in store.conn.execute("PRAGMA table_info(users)")}
        assert "password_hash" in cols

    def test_migration_v6_idempotent(self, store):
        """GIVEN migration already run WHEN running again THEN no error."""
        store._run_migration_v6()
        store._run_migration_v6()

    def test_migration_v7(self, store):
        """GIVEN existing organizations table WHEN running migration v7 THEN adds tier."""
        store.conn.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT
            )
        """)
        store.conn.commit()
        store._run_migration_v7()
        cols = {row[1] for row in store.conn.execute("PRAGMA table_info(organizations)")}
        assert "tier" in cols

    def test_migration_v7_idempotent(self, store):
        """GIVEN migration already run WHEN running again THEN no error."""
        store._run_migration_v7()
        store._run_migration_v7()


# ── Activity Tracking ─────────────────────────────────────────────────

class TestActivityTracking:
    def test_record_activity(self, store_with_data):
        """GIVEN project WHEN recording activity THEN increments pipeline_run_count."""
        store_with_data.record_activity("test-project")
        row = store_with_data.conn.execute(
            "SELECT pipeline_run_count, last_active_at FROM projects WHERE name = 'test-project'"
        ).fetchone()
        assert row["pipeline_run_count"] == 1
        assert row["last_active_at"] is not None

    def test_record_activity_multiple(self, store_with_data):
        """GIVEN multiple activity records WHEN recorded THEN count accumulates."""
        for _ in range(3):
            store_with_data.record_activity("test-project")
        count = store_with_data.conn.execute(
            "SELECT pipeline_run_count FROM projects WHERE name = 'test-project'"
        ).fetchone()[0]
        assert count == 3

    def test_get_total_users(self, store_with_data):
        """GIVEN users in database WHEN counting THEN returns total."""
        store_with_data.conn.execute("INSERT INTO users (org_id, email, created_at) VALUES (1, 'user1@test.com', datetime('now')), (1, 'user2@test.com', datetime('now'))")
        store_with_data.conn.commit()
        assert store_with_data.get_total_users() >= 2


# ── Usage Statistics ──────────────────────────────────────────────────

class TestUsageStats:
    def test_record_usage(self, store_with_data):
        """GIVEN usage event WHEN recording THEN inserts into usage_log."""
        store_with_data.record_usage(org_id=1, project_id=1, resource="pipeline_runs", amount=1)
        row = store_with_data.conn.execute(
            "SELECT * FROM usage_log WHERE org_id=1"
        ).fetchone()
        assert row is not None
        assert row["resource"] == "pipeline_runs"

    def test_get_monthly_usage(self, store_with_data):
        """GIVEN recorded usage data WHEN getting monthly THEN aggregates correctly."""
        store_with_data.record_usage(1, 1, "pipeline_runs", 5)
        store_with_data.record_usage(1, 1, "llm_tokens", 1000)
        usage = store_with_data.get_monthly_usage(1)
        assert usage["pipeline_runs"] == 5
        assert usage["llm_tokens"] == 1000
        assert usage["project_count"] >= 1


# ── Subscriptions ─────────────────────────────────────────────────────

class TestSubscriptions:
    def test_subscription_none(self, store_with_data):
        """GIVEN no subscription for org WHEN getting THEN returns None."""
        sub = store_with_data.get_subscription(1)
        assert sub is None

    def test_upsert_subscription_create(self, store_with_data):
        """GIVEN new subscription WHEN upserting THEN creates record."""
        store_with_data.upsert_subscription(1, {
            "stripe_subscription_id": "sub_123",
            "stripe_customer_id": "cus_456",
            "tier": "pro",
            "status": "active",
            "current_period_end": "2025-12-31",
        })
        sub = store_with_data.get_subscription(1)
        assert sub is not None
        assert sub["stripe_subscription_id"] == "sub_123"
        assert sub["tier"] == "pro"

    def test_upsert_subscription_update(self, store_with_data):
        """GIVEN existing subscription WHEN upserting again THEN updates."""
        store_with_data.upsert_subscription(1, {
            "stripe_subscription_id": "sub_123",
            "tier": "pro", "status": "active",
        })
        # Update status
        store_with_data.upsert_subscription(1, {
            "status": "canceled",
        })
        sub = store_with_data.get_subscription(1)
        assert sub["status"] == "canceled"
        # Original values not overwritten by None COALESCE
        assert sub["stripe_subscription_id"] == "sub_123"

    def test_upsert_subscription_partial(self, store_with_data):
        """GIVEN partial data WHEN upserting new THEN uses defaults."""
        store_with_data.upsert_subscription(1, {
            "stripe_subscription_id": "sub_new",
        })
        sub = store_with_data.get_subscription(1)
        assert sub["stripe_subscription_id"] == "sub_new"
        assert sub["tier"] == "pro"  # default

    def test_update_org_tier(self, store_with_data):
        """GIVEN org tier change WHEN updating THEN persists."""
        store_with_data.update_org_tier(1, "enterprise")
        row = store_with_data.conn.execute(
            "SELECT tier FROM organizations WHERE id=1"
        ).fetchone()
        assert row["tier"] == "enterprise"

    def test_get_org_by_stripe_subscription(self, store_with_data):
        """GIVEN subscription looking up org by sub ID WHEN querying THEN returns org."""
        store_with_data.upsert_subscription(1, {
            "stripe_subscription_id": "sub_findme",
            "tier": "pro", "status": "active",
        })
        org = store_with_data.get_org_by_stripe_subscription("sub_findme")
        assert org is not None
        assert org["name"] == "TestOrg"

    def test_get_org_by_stripe_subscription_not_found(self, store_with_data):
        """GIVEN non-existent sub ID WHEN querying THEN returns None."""
        org = store_with_data.get_org_by_stripe_subscription("sub_nonexistent")
        assert org is None
