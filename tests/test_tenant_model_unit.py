"""Unit tests for yuleosh.tenant.model — Tenant + TenantStore (v3.4.2 Wave 0).

Covers:
  - Plan constants / TIER_LIMITS sanity
  - Tenant dataclass: defaults, timestamps, invalid plan fallback,
    limits property, has_feature, to_dict/from_dict roundtrip
  - TenantStore: CRUD, slug validation, directory scaffolding, projects,
    config get/set, list/delete semantics
"""

# @tests src/yuleosh/tenant/model.py

import json
import os
import sys
from datetime import datetime

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.tenant.model import (
    PLAN_FREE,
    PLAN_PRO,
    PLAN_ENTERPRISE,
    SUPPORTED_PLANS,
    TIER_LIMITS,
    SLUG_RE,
    Tenant,
    TenantStore,
)


# ── Constants / Tenant dataclass ──────────────────────────────────────

class TestTenantModel:
    def test_supported_plans(self):
        """GIVEN plan constants WHEN checked THEN all supported."""
        assert SUPPORTED_PLANS == [PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE]
        assert TIER_LIMITS[PLAN_FREE]["max_projects"] == 1
        assert TIER_LIMITS[PLAN_ENTERPRISE]["max_users"] == 9999

    def test_tenant_defaults(self):
        """GIVEN bare tenant WHEN constructed THEN free plan + timestamps."""
        t = Tenant(id="my-org", name="My Org")
        assert t.plan == PLAN_FREE
        assert t.created_at and t.updated_at
        assert t.settings == {}

    def test_tenant_invalid_plan_falls_back(self):
        """GIVEN unsupported plan WHEN constructed THEN reset to free."""
        t = Tenant(id="x", name="X", plan="gold")
        assert t.plan == PLAN_FREE

    def test_tenant_limits_property(self):
        """GIVEN pro tenant WHEN limits THEN pro tier limits."""
        t = Tenant(id="x", name="X", plan=PLAN_PRO)
        assert t.limits["max_users"] == 5

    def test_tenant_has_feature(self):
        """GIVEN tenant WHEN has_feature THEN enterprise gets everything."""
        free = Tenant(id="f", name="F", plan=PLAN_FREE)
        ent = Tenant(id="e", name="E", plan=PLAN_ENTERPRISE)
        assert free.has_feature("misra_check") is True
        assert free.has_feature("rbac") is False
        assert ent.has_feature("anything") is True

    def test_tenant_roundtrip(self):
        """GIVEN tenant WHEN to_dict/from_dict THEN equal fields."""
        t = Tenant(id="my-org", name="My Org", plan=PLAN_PRO,
                   created_at="2026-01-01T00:00:00",
                   settings={"theme": "dark"})
        t2 = Tenant.from_dict(t.to_dict())
        assert t2.id == t.id
        assert t2.plan == t.plan
        assert t2.settings == {"theme": "dark"}
        assert t2.created_at == "2026-01-01T00:00:00"


# ── TenantStore ───────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    return TenantStore(data_root=str(tmp_path))


class TestTenantStoreCrud:
    def test_init_creates_tenants_dir(self, tmp_path):
        """GIVEN data_root WHEN init THEN tenants dir created."""
        s = TenantStore(data_root=str(tmp_path))
        assert (tmp_path / "tenants").is_dir()

    def test_get_missing_returns_none(self, store):
        """GIVEN no tenant WHEN get THEN None."""
        assert store.get("nope") is None

    def test_create_and_get(self, store):
        """GIVEN create WHEN get THEN roundtrip preserved."""
        t = store.create("my-org", "My Organization")
        assert t.id == "my-org"
        got = store.get("my-org")
        assert got.name == "My Organization"
        assert got.plan == PLAN_FREE

    def test_create_invalid_slug_raises(self, store):
        """GIVEN bad slug WHEN create THEN ValueError."""
        with pytest.raises(ValueError):
            store.create("Bad Slug!", "X")

    def test_create_duplicate_raises(self, store):
        """GIVEN existing slug WHEN create again THEN ValueError."""
        store.create("dup", "D")
        with pytest.raises(ValueError):
            store.create("dup", "D2")

    def test_create_scaffolds_dirs(self, store):
        """GIVEN create WHEN success THEN tenant dirs scaffolded."""
        store.create("acme", "Acme")
        root = store.data_root / "acme"
        for sub in ("projects", "config", "evidence", "audit"):
            assert (root / sub).is_dir()

    def test_get_or_create_existing(self, store):
        """GIVEN existing tenant WHEN get_or_create THEN returns existing."""
        store.create("acme", "Acme")
        t = store.get_or_create("acme", "Renamed")
        assert t.name == "Acme"

    def test_get_or_create_new(self, store):
        """GIVEN missing tenant WHEN get_or_create THEN creates with slug name."""
        t = store.get_or_create("newco")
        assert t.name == "newco"

    def test_update_fields(self, store):
        """GIVEN tenant WHEN update THEN fields changed + updated_at bumped."""
        store.create("acme", "Acme", plan=PLAN_FREE)
        t = store.update("acme", name="Acme Inc", plan=PLAN_PRO)
        assert t.name == "Acme Inc"
        assert t.plan == PLAN_PRO
        assert t.updated_at

    def test_update_missing_raises(self, store):
        """GIVEN missing tenant WHEN update THEN ValueError."""
        with pytest.raises(ValueError):
            store.update("ghost", name="X")

    def test_delete_missing_false(self, store):
        """GIVEN no tenant WHEN delete THEN False."""
        assert store.delete("ghost") is False

    def test_delete_existing_true(self, store):
        """GIVEN tenant with data dir WHEN delete THEN metadata + dir removed."""
        store.create("acme", "Acme")
        assert (store.data_root / "acme").exists()
        assert store.delete("acme") is True
        assert store.get("acme") is None
        assert not (store.data_root / "acme").exists()

    def test_list_tenants_sorted(self, store):
        """GIVEN multiple tenants WHEN list THEN sorted by slug."""
        store.create("beta", "B")
        store.create("alpha", "A")
        slugs = [t.id for t in store.list_tenants()]
        assert slugs == ["alpha", "beta"]


class TestTenantStoreProjects:
    def test_save_and_get_project(self, store):
        """GIVEN project data WHEN save/get THEN roundtrip + updated_at."""
        store.create("acme", "Acme")
        saved = store.save_project("acme", {"slug": "p1", "name": "P1"})
        assert saved["updated_at"]
        got = store.get_project("acme", "p1")
        assert got["name"] == "P1"

    def test_get_project_missing_none(self, store):
        """GIVEN no project WHEN get_project THEN None."""
        store.create("acme", "Acme")
        assert store.get_project("acme", "ghost") is None

    def test_list_projects_empty(self, store):
        """GIVEN tenant without projects dir WHEN list THEN []."""
        store.create("acme", "Acme")
        # remove the scaffolded dir to exercise the missing-dir branch
        import shutil
        shutil.rmtree(store.data_root / "acme" / "projects")
        assert store.list_projects("acme") == []

    def test_list_projects_sorted(self, store):
        """GIVEN projects WHEN list THEN sorted by file name."""
        store.create("acme", "Acme")
        store.save_project("acme", {"slug": "z", "name": "Z"})
        store.save_project("acme", {"slug": "a", "name": "A"})
        assert [p["name"] for p in store.list_projects("acme")] == ["A", "Z"]

    def test_delete_project(self, store):
        """GIVEN project WHEN delete THEN file removed; missing → False."""
        store.create("acme", "Acme")
        store.save_project("acme", {"slug": "p1"})
        assert store.delete_project("acme", "p1") is True
        assert store.delete_project("acme", "p1") is False


class TestTenantStoreConfig:
    def test_get_config_default(self, store):
        """GIVEN no config WHEN get_config THEN default returned."""
        store.create("acme", "Acme")
        assert store.get_config("acme", "theme", "light") == "light"

    def test_set_and_get_config(self, store):
        """GIVEN set_config WHEN get_config THEN value roundtrips."""
        store.create("acme", "Acme")
        store.set_config("acme", "theme", {"mode": "dark"})
        assert store.get_config("acme", "theme") == {"mode": "dark"}

    def test_slug_regex(self):
        """GIVEN slug patterns WHEN SLUG_RE THEN matches lowercase-hyphen form."""
        assert SLUG_RE.match("my-org")
        assert SLUG_RE.match("a")
        assert not SLUG_RE.match("My-Org")
        assert not SLUG_RE.match("-lead")
        assert not SLUG_RE.match("trail-")
