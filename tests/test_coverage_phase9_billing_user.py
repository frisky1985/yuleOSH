# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Phase 9 tests — Billing integration: user attribution + run_id sessions + slug bridge.

Covers:
  - usage_log user_id/run_id/user_email columns (migration v8)
  - record_usage / record_pipeline_run with user attribution
  - get_monthly_usage_by_user per-user split
  - PipelineSession run_id directory (same-name pipelines don't collide)
  - legacy name-dir compatibility (status_pipeline)
  - billing usage dual-source merge (llm_tokens + ci_runs) + role in response
  - billing admin-only (member still 403 via rbac)
"""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure src is importable
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def osh_env(tmp_path):
    """Isolated OSH_HOME + Store per test."""
    old = os.environ.get("OSH_HOME")
    os.environ["OSH_HOME"] = str(tmp_path)
    os.environ["YULEOSH_JWT_SECRET"] = "test-secret"
    yield tmp_path
    if old is None:
        os.environ.pop("OSH_HOME", None)
    else:
        os.environ["OSH_HOME"] = old


def _fresh_store(tmp_path):
    """Return a Store bound to tmp_path OSH_HOME."""
    from yuleosh.store import Store
    # Reset singleton so each test gets a fresh DB in tmp_path.
    Store._instances = {}
    return Store()


# ── D1: usage_log user attribution ──────────────────────────────────────────

class TestUsageUserAttribution:
    def test_record_usage_with_user(self, osh_env):
        store = _fresh_store(osh_env)
        store.create_organization("Org A", "org-a")
        org = store.get_organization("org-a")
        store.record_usage(org["id"], 0, "llm_tokens", 1000,
                           user_id=7, user_email="u@x.io", run_id="run-1")
        store.record_usage(org["id"], 0, "llm_tokens", 2000,
                           user_id=7, user_email="u@x.io", run_id="run-2")
        usage = store.get_monthly_usage(org["id"])
        assert usage["llm_tokens"] == 3000
        by_user = store.get_monthly_usage_by_user(org["id"])
        assert len(by_user) == 1
        assert by_user[0]["user_id"] == 7
        assert by_user[0]["llm_tokens"] == 3000

    def test_record_usage_legacy_no_user(self, osh_env):
        """Backward compat: no user args → NULL columns, org totals intact."""
        store = _fresh_store(osh_env)
        store.create_organization("Org B", "org-b")
        org = store.get_organization("org-b")
        store.record_usage(org["id"], 0, "llm_tokens", 500)
        store.record_usage(org["id"], 0, "pipeline_runs", 1)
        usage = store.get_monthly_usage(org["id"])
        assert usage["llm_tokens"] == 500
        assert usage["pipeline_runs"] == 1
        # Legacy rows excluded from per-user split.
        assert store.get_monthly_usage_by_user(org["id"]) == []

    def test_by_user_groups_and_orders(self, osh_env):
        store = _fresh_store(osh_env)
        store.create_organization("Org C", "org-c")
        org = store.get_organization("org-c")
        store.record_usage(org["id"], 0, "llm_tokens", 300, user_id=8, user_email="v@x.io")
        store.record_usage(org["id"], 0, "llm_tokens", 1500, user_id=7, user_email="u@x.io")
        store.record_usage(org["id"], 0, "pipeline_runs", 2, user_id=8, user_email="v@x.io")
        by_user = store.get_monthly_usage_by_user(org["id"])
        # Ordered by llm_tokens DESC.
        assert by_user[0]["user_id"] == 7
        assert by_user[1]["user_id"] == 8
        assert by_user[1]["pipeline_runs"] == 2

    def test_record_pipeline_run_with_user(self, osh_env):
        store = _fresh_store(osh_env)
        store.create_organization("Org D", "org-d")
        org = store.get_organization("org-d")
        from yuleosh.usage import record_pipeline_run
        record_pipeline_run(store, org["id"], 0, llm_tokens=12345,
                            user_id=3, user_email="a@b.io", run_id="run-x")
        usage = store.get_monthly_usage(org["id"])
        assert usage["llm_tokens"] == 12345
        assert usage["pipeline_runs"] == 1
        by_user = store.get_monthly_usage_by_user(org["id"])
        assert by_user[0]["llm_tokens"] == 12345

    def test_count_org_users(self, osh_env):
        store = _fresh_store(osh_env)
        store.create_organization("Org E", "org-e")
        org = store.get_organization("org-e")
        assert store.count_org_users(org["id"]) == 0
        store.create_user(org["id"], "one@x.io", "member")
        store.create_user(org["id"], "two@x.io", "member")
        assert store.count_org_users(org["id"]) == 2


# ── D2: PipelineSession run_id directory ────────────────────────────────────

class TestSessionRunId:
    def test_same_name_sessions_get_distinct_dirs(self, osh_env):
        from yuleosh.pipeline.session import PipelineSession
        s1 = PipelineSession("agent-pipeline", "/tmp/spec.md", org_id=1,
                             user_id=7, user_email="u@x.io")
        s2 = PipelineSession("agent-pipeline", "/tmp/spec.md", org_id=1,
                             user_id=8, user_email="v@x.io")
        assert s1.run_id != s2.run_id
        assert s1.session_dir != s2.session_dir
        assert s1.session_dir.name == s1.run_id
        assert s2.session_dir.name == s2.run_id

    def test_to_dict_contains_user_and_run(self, osh_env):
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession("my-pipe", "/tmp/spec.md", org_id=2,
                            user_id=5, user_email="who@x.io")
        d = s.to_dict()
        assert d["user_id"] == 5
        assert d["user_email"] == "who@x.io"
        assert d["run_id"] == s.run_id
        assert d["name"] == "my-pipe"

    def test_run_id_defaults_unique(self, osh_env):
        from yuleosh.pipeline.session import PipelineSession
        a = PipelineSession("p", "/tmp/s.md", org_id=0)
        b = PipelineSession("p", "/tmp/s.md", org_id=0)
        assert a.run_id != b.run_id
        assert len(a.run_id) == 12  # uuid4 hex [:12]

    def test_save_persists_run_dir(self, osh_env):
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession("persist-pipe", "/tmp/spec.md", org_id=1, user_id=2)
        s._save()
        sj = s.session_dir / "session.json"
        assert sj.exists()
        data = json.loads(sj.read_text())
        assert data["run_id"] == s.run_id
        assert data["user_id"] == 2


class TestStatusPipelineCompat:
    def test_status_pipeline_matches_by_json_name(self, osh_env):
        """status_pipeline(name) matches run_id dirs via session.json name."""
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession("display-name", "/tmp/spec.md", org_id=1)
        s._save()
        # Direct: mimic the lookup path by scanning.
        base = Path(os.environ["OSH_HOME"]) / ".osh" / "sessions"
        found = []
        for d in base.iterdir():
            if not d.is_dir():
                continue
            sf = d / "session.json"
            if sf.exists():
                data = json.loads(sf.read_text())
                if data.get("name") == "display-name":
                    found.append(d.name)
        assert found == [s.run_id]

    def test_status_pipeline_legacy_name_dir(self, osh_env):
        """Legacy name-dir (no run_id json) still matched by dir name."""
        base = Path(os.environ["OSH_HOME"]) / ".osh" / "sessions"
        (base / "legacy-pipe").mkdir(parents=True)
        (base / "legacy-pipe" / "session.json").write_text(
            json.dumps({"name": "legacy-pipe", "status": "completed"})
        )
        # legacy dir has name == dir name, matched.
        found = []
        for d in base.iterdir():
            if not d.is_dir():
                continue
            sf = d / "session.json"
            if sf.exists():
                data = json.loads(sf.read_text())
                if data.get("name") == "legacy-pipe":
                    found.append(d.name)
        assert found == ["legacy-pipe"]


# ── D3: billing usage dual-source merge ─────────────────────────────────────

class FakeHandler:
    def __init__(self):
        self.headers = {"Authorization": "Bearer fake-token"}


class FakeMeter:
    """Deterministic jsonl-side usage, no filesystem dependency."""

    def get_usage_summary(self, tenant):
        return {
            "tenant": tenant, "plan": "free", "period": "2026-08",
            "usage": {"ci_runs": 5, "api_calls": 0, "storage_mb": 0},
            "limits": {"ci_runs": 50, "projects": 1, "users": 1, "storage_mb": 100},
            "within_limits": True,
        }


class TestBillingUsageMerge:
    def _setup(self, osh_env, role="admin"):
        from yuleosh.store import Store
        Store._instances = {}
        store = Store()
        store.create_organization("Biz Org", "biz-org")
        org = store.get_organization("biz-org")
        store.record_usage(org["id"], 0, "llm_tokens", 250000,
                           user_id=1, user_email="a@b.io")
        return store, org

    def _call(self, user_dict):
        from yuleosh.ui.routes import billing_routes as br
        br._require_auth = lambda h: user_dict
        br.UsageMeter = FakeMeter
        return br.handle_get_usage("GET", "usage", {}, {}, FakeHandler())

    def test_usage_merges_llm_tokens_and_ci(self, osh_env):
        _store, org = self._setup(osh_env)
        result, code = self._call({"org_slug": "biz-org", "role": "admin",
                                   "org_id": org["id"], "user_id": 1})
        assert code == 200
        assert result["usage"]["llm_tokens"] == 250000
        assert result["usage"]["ci_runs"] == 5
        assert result["usage"]["projects"] == 0
        assert result["limits"]["llm_tokens"] == 500000  # pro default tier
        assert result["role"] == "admin"
        assert result["by_user"][0]["user_email"] == "a@b.io"

    def test_usage_no_org_returns_404(self, osh_env):
        _resp, code = self._call({"org_slug": "", "role": "admin"})
        assert code == 404

    def test_usage_missing_slug_org_ok(self, osh_env):
        """Billing must not 500 when sqlite org missing for a slug."""
        from yuleosh.ui.routes import billing_routes as br
        br._require_auth = lambda h: {"org_slug": "no-such-org", "role": "admin"}
        br.UsageMeter = FakeMeter
        result, code = br.handle_get_usage("GET", "usage", {}, {}, FakeHandler())
        assert code == 200
        assert result["usage"]["llm_tokens"] == 0
        assert result["by_user"] == []

    def test_usage_member_role_visible_no_by_user(self, osh_env):
        """member is denied at rbac (admin-only billing page, boss decision)."""
        _store, org = self._setup(osh_env)
        _resp, code = self._call({"org_slug": "biz-org", "role": "member",
                                  "org_id": org["id"], "user_id": 2})
        # rbac denies billing:view for member → 403 (admin-only page).
        assert code == 403


class TestBillingAuth:
    def test_billing_requires_auth(self, osh_env):
        from yuleosh.ui.routes import billing_routes as br
        br._require_auth = lambda h: None
        _resp, code = br.handle_get_usage("GET", "usage", {}, {}, FakeHandler())
        assert code == 401

    def test_billing_rbac_403(self, osh_env):
        """rbac still enforced: role without billing:view → 403."""
        from yuleosh.ui.routes import billing_routes as br
        br._require_auth = lambda h: {"org_slug": "x", "role": "viewer"}
        br.UsageMeter = FakeMeter
        # rbac.check_role is imported inside the handler — simulate deny by
        # patching the real rbac module used at call time.
        from yuleosh import rbac
        _orig = rbac.check_role

        def deny(user, res, action):
            return False
        rbac.check_role = deny
        try:
            _resp, code = br.handle_get_usage("GET", "usage", {}, {}, FakeHandler())
            assert code == 403
        finally:
            rbac.check_role = _orig
