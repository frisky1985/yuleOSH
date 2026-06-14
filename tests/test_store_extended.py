# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for store — multi-tenant, sessions, spec cache, API keys, wizard, stats.

Covers: record_activity, get_total_users, get_total_projects, get_usage_stats,
        create/get/list organization, create/get/list user, create/get/list org_project,
        create/get/delete/cleanup session, cache_spec_parse/get_cached_spec_parse,
        create/list/get/revoke/update API keys, wizard, get_migration_version,
        save_ci, save_review edge cases.
"""

import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.store import Store


def setup_function():
    Store.reset()


# ===================================================================
# Usage Statistics
# ===================================================================

def test_record_activity():
    """Test record_activity updates pipeline_run_count and last_active_at."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.init_project("test-proj", "A test project")
        s.record_activity("test-proj")
        p = s.get_project("test-proj")
        assert p is not None
        assert p["pipeline_run_count"] is not None
        assert int(p["pipeline_run_count"]) >= 1
        assert p["last_active_at"] is not None


def test_get_total_users():
    """Test get_total_users returns correct count."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        assert s.get_total_users() == 0
        org = s.create_organization("TestOrg", "test-org")
        s.create_user(org["id"], "user1@test.com")
        s.create_user(org["id"], "user2@test.com")
        assert s.get_total_users() == 2


def test_get_total_projects():
    """Test get_total_projects counts both legacy and org-scoped projects."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        assert s.get_total_projects() == 0
        s.init_project("legacy-proj")
        org = s.create_organization("TestOrg", "test-org")
        s.create_org_project(org["id"], "org-proj", "org-proj")
        assert s.get_total_projects() == 2


def test_get_usage_stats():
    """Test get_usage_stats returns aggregated statistics."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        stats = s.get_usage_stats()
        assert "total_pipelines" in stats
        assert "total_ci_runs" in stats
        assert "total_reviews" in stats
        assert "total_evidence" in stats
        assert "total_projects" in stats
        assert "total_organizations" in stats
        assert "total_users" in stats
        assert "pipeline_statuses" in stats
        assert "ci_by_layer" in stats
        assert stats["total_pipelines"] == 0
        assert stats["total_users"] == 0

        # Add some data and re-check
        s.save_pipeline("p1", {"status": "completed"})
        s.save_ci({"layer": 1, "status": "passed"})
        s.save_review("r1", {"decision": "passed", "status": "completed"})
        s.log_evidence("ev.md", "md", "/tmp/ev.md")
        org = s.create_organization("Org", "org")
        s.create_user(org["id"], "u@t.com")
        stats2 = s.get_usage_stats()
        assert stats2["total_pipelines"] >= 1
        assert stats2["total_ci_runs"] >= 1
        assert stats2["total_reviews"] >= 1
        assert stats2["total_evidence"] >= 1
        assert stats2["total_organizations"] >= 1
        assert stats2["total_users"] >= 1


# ===================================================================
# Multi-tenant: Organizations
# ===================================================================

def test_create_get_list_organizations():
    """Test full CR for organizations."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)

        org = s.create_organization("Alpha Corp", "alpha")
        assert org["name"] == "Alpha Corp"
        assert org["slug"] == "alpha"
        assert org["id"] > 0

        fetched = s.get_organization("alpha")
        assert fetched is not None
        assert fetched["name"] == "Alpha Corp"

        fetched_id = s.get_organization_by_id(org["id"])
        assert fetched_id is not None
        assert fetched_id["slug"] == "alpha"

        # get_organization_by_id with non-existent id
        assert s.get_organization_by_id(99999) is None

        orgs = s.list_organizations()
        assert len(orgs) >= 1
        assert any(o["slug"] == "alpha" for o in orgs)


# ===================================================================
# Multi-tenant: Users
# ===================================================================

def test_create_get_list_users():
    """Test full CR for users within an organization."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        org = s.create_organization("Org", "org")

        user = s.create_user(org["id"], "admin@org.com", "admin")
        assert user["email"] == "admin@org.com"
        assert user["role"] == "admin"

        fetched = s.get_user(org["id"], "admin@org.com")
        assert fetched is not None
        assert fetched["role"] == "admin"

        fetched_id = s.get_user_by_id(user["id"])
        assert fetched_id is not None
        assert fetched_id["email"] == "admin@org.com"

        # Non-existent user
        assert s.get_user(org["id"], "nobody@org.com") is None
        assert s.get_user_by_id(99999) is None

        users = s.list_users(org["id"])
        assert len(users) >= 1
        assert any(u["email"] == "admin@org.com" for u in users)


# ===================================================================
# Multi-tenant: Org-scoped Projects
# ===================================================================

def test_create_get_list_org_projects():
    """Test full CR for org-scoped projects."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        org = s.create_organization("Org", "org")

        proj = s.create_org_project(org["id"], "My Project", "my-project", "Desc")
        assert proj["name"] == "My Project"
        assert proj["slug"] == "my-project"

        fetched = s.get_org_project(org["id"], "my-project")
        assert fetched is not None
        assert fetched["description"] == "Desc"

        fetched_id = s.get_org_project_by_id(proj["id"])
        assert fetched_id is not None

        # Non-existent
        assert s.get_org_project(org["id"], "nonexistent") is None
        assert s.get_org_project_by_id(99999) is None

        projs = s.list_org_projects(org["id"])
        assert len(projs) >= 1


# ===================================================================
# Multi-tenant: Sessions
# ===================================================================

def test_create_get_delete_session():
    """Test session creation, retrieval, and deletion."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        org = s.create_organization("Org", "org")
        user = s.create_user(org["id"], "u@t.com")

        sess = s.create_session(user["id"], "tok_abc123", ttl_hours=48)
        assert sess["token"] == "tok_abc123"
        assert sess["user_id"] == user["id"]

        fetched = s.get_session("tok_abc123")
        assert fetched is not None
        assert fetched["user_id"] == user["id"]

        # Non-existent
        assert s.get_session("not_a_token") is None

        s.delete_session("tok_abc123")
        assert s.get_session("tok_abc123") is None


def test_cleanup_expired_sessions():
    """Test cleanup_expired_sessions removes stale sessions."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        org = s.create_organization("Org", "org")
        user = s.create_user(org["id"], "u@t.com")

        # Create already-expired session (negative TTL ensures past expires_at)
        s.create_session(user["id"], "tok_short", ttl_hours=-24)
        s.create_session(user["id"], "tok_long", ttl_hours=24)

        s.cleanup_expired_sessions()
        # tok_short expired (0 TTL), tok_long still valid
        assert s.get_session("tok_short") is None
        assert s.get_session("tok_long") is not None


# ===================================================================
# Spec parsing cache
# ===================================================================

def test_cache_spec_parse():
    """Test caching and retrieving spec parse results."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)

        spec_path = os.path.join(tmp, "spec.md")
        result = {"requirements": [{"name": "Req1"}], "scenarios": []}
        s.cache_spec_parse(spec_path, 12345.0, result)

        cached = s.get_cached_spec_parse(spec_path, 12345.0)
        assert cached is not None
        assert cached["requirements"][0]["name"] == "Req1"

        # Different mtime should miss
        cached2 = s.get_cached_spec_parse(spec_path, 99999.0)
        assert cached2 is None

        # Different path should miss
        cached3 = s.get_cached_spec_parse("/other/path", 12345.0)
        assert cached3 is None


# ===================================================================
# API Keys
# ===================================================================

def test_create_get_list_api_keys():
    """Test API key lifecycle."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)

        key = s.create_api_key("hash_abc", "My Key", "myk_")
        assert key["label"] == "My Key"
        assert key["prefix"] == "myk_"
        assert key["revoked"] == 0

        fetched = s.get_api_key_by_hash("hash_abc")
        assert fetched is not None
        assert fetched["label"] == "My Key"

        # Non-existent
        assert s.get_api_key_by_hash("nonexistent") is None

        keys = s.list_api_keys()
        assert len(keys) >= 1
        assert any(k["prefix"] == "myk_" for k in keys)


def test_revoke_api_key():
    """Test revoking an API key."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)

        key = s.create_api_key("hash_revoke", "Revokable Key", "rev_")
        assert key["revoked"] == 0

        # Revoke
        assert s.revoke_api_key(key["id"]) is True
        revoked = s.get_api_key_by_hash("hash_revoke")
        assert revoked["revoked"] == 1

        # Double revoke should return False
        assert s.revoke_api_key(key["id"]) is False


def test_update_api_key_last_used():
    """Test updating api key last_used_at."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)

        key = s.create_api_key("hash_used", "Used Key", "use_")
        s.update_api_key_last_used(key["id"])
        # Should not raise; read back
        k = s.get_api_key_by_hash("hash_used")
        assert k is not None
        assert k["last_used_at"] is not None


# ===================================================================
# Wizard
# ===================================================================

def test_wizard_lifecycle():
    """Test wizard completed state."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        assert s.is_wizard_completed() is False
        s.complete_wizard()
        assert s.is_wizard_completed() is True


# ===================================================================
# Migration version
# ===================================================================

def test_get_migration_version():
    """Test get_migration_version returns current version."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        version = s.get_migration_version()
        assert version == s._MIGRATION_VERSION


# ===================================================================
# Data persistence edge cases
# ===================================================================

def test_save_ci_with_errors():
    """Test save_ci with errors data."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_ci({
            "layer": 2,
            "commit": "abc123",
            "status": "failed",
            "coverage": {"line": 50},
            "errors": [{"step": "compile", "message": "Build failed"}],
        })
        results = s.list_ci(limit=5)
        assert len(results) >= 1
        assert results[0]["layer"] == 2


def test_save_review_with_data():
    """Test save_review stores data payload."""
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_review("task-2", {
            "decision": "retry",
            "status": "running",
            "findings": [{"severity": "critical", "message": "Bug"}],
        })
        reviews = s.list_reviews(limit=5)
        assert len(reviews) >= 1
        match = [r for r in reviews if r["task_name"] == "task-2"]
        assert len(match) >= 1
        assert match[0]["decision"] == "retry"
