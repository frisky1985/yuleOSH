"""Unit tests for yuleosh.api.members — role management endpoints (module ①).

Covers, offline against a REAL seeded SQLite store:
  - member list (org-scoped, real store users table)
  - invite (role/email validation, duplicate → 409, non-admin → 403)
  - role update (PATCH /members/{id}, org scoping, 404 for foreign ids)
  - roles matrix (static 6 roles × 8 modules from design doc chapter 4)
  - org-missing → 403 fail-closed, auth-required → 401
"""

import pytest

from yuleosh.api import members as M
from yuleosh.store import Store

# The auth wrapper injects current_user as a kwarg; unit tests call the
# wrapped original directly (same pattern as test_api_dashboard_unit.py).
_handle = M.handle_members.__wrapped__


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Seed a real SQLite store: org 1 (owner+developer), org 2 (viewer)."""
    Store.reset()
    s = Store(str(tmp_path / "members-test.db"))
    org1 = s.create_organization("Acme", "acme")
    org2 = s.create_organization("Globex", "globex")
    s.create_user(org1["id"], "owner@acme.com", "owner")
    s.create_user(org1["id"], "dev@acme.com", "developer")
    s.create_user(org2["id"], "alien@globex.com", "viewer")
    monkeypatch.setattr("yuleosh.store.Store", lambda: s)
    yield {"org1": org1["id"], "org2": org2["id"], "store": s}
    Store.reset()


def _req(method, path, body=None, query=None, org_id=1, role="owner",
         user=None):
    """Call the wrapped handler with an authenticated current_user."""
    if user is None:
        user = {"user_id": 1, "org_id": org_id, "email": "owner@acme.com",
                "role": role}
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user=user)


# ── GET /api/v1/members — member list ───────────────────────────────────

class TestListMembers:
    def test_list_members_org_scoped(self, store):
        """GIVEN org 1 with 2 users WHEN GET members THEN real rows only."""
        payload, status = _req("GET", "", org_id=store["org1"])
        assert status == 200 and payload["ok"] is True
        data = payload["data"]
        assert data["count"] == 2
        assert data["note"] is None
        emails = {m["email"] for m in data["members"]}
        assert emails == {"owner@acme.com", "dev@acme.com"}
        assert {"id", "email", "role", "created_at"} <= set(data["members"][0])

    def test_list_members_list_alias(self, store):
        """path_tail 'list' is accepted as an alias for ''."""
        payload, _ = _req("GET", "list", org_id=store["org1"])
        assert payload["data"]["count"] == 2

    def test_list_members_isolates_orgs(self, store):
        """GIVEN users in two orgs WHEN org 2 lists THEN only org 2's user."""
        payload, _ = _req("GET", "", org_id=store["org2"])
        emails = [m["email"] for m in payload["data"]["members"]]
        assert emails == ["alien@globex.com"]

    def test_list_members_other_org_query_rejected(self, store):
        """GIVEN ?org_id=other WHEN listing THEN 403 (no cross-org view)."""
        payload, status = _req("GET", "", query={"org_id": store["org2"]},
                               org_id=store["org1"])
        assert status == 403 and payload["ok"] is False

    def test_list_members_missing_org_fails_closed(self):
        """GIVEN auth context without org_id WHEN members THEN 403."""
        payload, status = _req(
            "GET", "", user={"user_id": 1, "email": "x@y.com", "role": "admin"})
        assert status == 403
        assert "org_id" in payload["error"]


# ── POST /api/v1/members/invite ─────────────────────────────────────────

class TestInvite:
    def test_invite_creates_member(self, store):
        """GIVEN valid {email, role} WHEN invite THEN row in users table."""
        payload, status = _req("POST", "invite",
                               body={"email": "qa@acme.com",
                                     "role": "quality_manager"},
                               org_id=store["org1"])
        assert status == 200
        member = payload["data"]["member"]
        assert member["email"] == "qa@acme.com"
        assert member["role"] == "quality_manager"
        # persisted with NULL password hash (set later by the invitee)
        row = store["store"].get_user(store["org1"], "qa@acme.com")
        assert row["password_hash"] is None

    def test_invite_invalid_role_400(self, store):
        """GIVEN role outside the vocabulary WHEN invite THEN 400."""
        payload, status = _req("POST", "invite",
                               body={"email": "x@acme.com", "role": "superuser"},
                               org_id=store["org1"])
        assert status == 400
        assert "非法角色" in payload["error"]

    def test_invite_invalid_email_400(self, store):
        """GIVEN malformed email WHEN invite THEN 400."""
        payload, status = _req("POST", "invite",
                               body={"email": "not-an-email", "role": "viewer"},
                               org_id=store["org1"])
        assert status == 400
        assert "邮箱" in payload["error"]

    def test_invite_duplicate_409(self, store):
        """GIVEN an email already in the org WHEN invite THEN 409."""
        payload, status = _req("POST", "invite",
                               body={"email": "owner@acme.com", "role": "admin"},
                               org_id=store["org1"])
        assert status == 409
        assert "已存在" in payload["error"]

    def test_invite_forbidden_for_non_admin(self, store):
        """GIVEN a developer caller WHEN invite THEN 403."""
        payload, status = _req("POST", "invite",
                               body={"email": "new@acme.com", "role": "viewer"},
                               org_id=store["org1"], role="developer")
        assert status == 403

    def test_invite_missing_org_403(self, store):
        """GIVEN no org in auth context WHEN invite THEN 403."""
        payload, status = _req("POST", "invite",
                               body={"email": "a@acme.com", "role": "viewer"},
                               user={"user_id": 1, "email": "o@a.com",
                                     "role": "owner"})
        assert status == 403


# ── PATCH /api/v1/members/{id} — role change ────────────────────────────

class TestUpdateRole:
    def test_update_role(self, store):
        """GIVEN member id + {role} WHEN PATCH THEN role persisted."""
        dev = store["store"].get_user(store["org1"], "dev@acme.com")
        payload, status = _req("PATCH", str(dev["id"]),
                               body={"role": "architect"},
                               org_id=store["org1"])
        assert status == 200
        assert payload["data"]["member"]["role"] == "architect"
        assert store["store"].get_user_by_id(dev["id"])["role"] == "architect"

    def test_update_role_invalid_role_400(self, store):
        """GIVEN invalid role WHEN PATCH THEN 400."""
        dev = store["store"].get_user(store["org1"], "dev@acme.com")
        payload, status = _req("PATCH", str(dev["id"]), body={"role": "root"},
                               org_id=store["org1"])
        assert status == 400
        assert "非法角色" in payload["error"]

    def test_update_role_not_found_404(self, store):
        """GIVEN unknown user id WHEN PATCH THEN 404."""
        payload, status = _req("PATCH", "99999", body={"role": "admin"},
                               org_id=store["org1"])
        assert status == 404

    def test_update_role_other_org_404(self, store):
        """GIVEN a user id belonging to another org WHEN PATCH THEN 404."""
        alien = store["store"].get_user(store["org2"], "alien@globex.com")
        payload, status = _req("PATCH", str(alien["id"]),
                               body={"role": "admin"},
                               org_id=store["org1"])
        assert status == 404

    def test_update_role_non_numeric_id_400(self, store):
        """GIVEN a non-numeric id WHEN PATCH THEN 400."""
        payload, status = _req("PATCH", "abc", body={"role": "admin"},
                               org_id=store["org1"])
        assert status == 400

    def test_update_role_forbidden_for_non_admin(self, store):
        """GIVEN a viewer caller WHEN PATCH THEN 403."""
        dev = store["store"].get_user(store["org1"], "dev@acme.com")
        payload, status = _req("PATCH", str(dev["id"]), body={"role": "admin"},
                               org_id=store["org1"], role="viewer")
        assert status == 403


# ── GET /api/v1/members/roles — permission matrix ───────────────────────

class TestRolesMatrix:
    def test_roles_matrix_shape(self, store):
        """GIVEN GET roles THEN 6 roles × 8 modules with valid values."""
        payload, status = _req("GET", "roles", org_id=store["org1"])
        assert status == 200
        data = payload["data"]
        assert len(data["roles"]) == 6
        assert len(data["modules"]) == 8
        by_role = {r["role"]: r["permissions"] for r in data["roles"]}
        assert set(by_role) == set(M.VALID_ROLES)
        for perms in by_role.values():
            assert set(perms) == set(data["modules"])
            assert set(perms.values()) <= {"full", "read", "none"}

    def test_roles_matrix_owner_full(self, store):
        """Owner has full on all 8 modules."""
        by_role = {r["role"]: r["permissions"]
                   for r in _req("GET", "roles", org_id=store["org1"])[0]["data"]["roles"]}
        assert all(v == "full" for v in by_role["owner"].values())

    def test_roles_matrix_viewer_read_only(self, store):
        """Viewer: dashboard full, most modules read, 角色管理 none."""
        by_role = {r["role"]: r["permissions"]
                   for r in _req("GET", "roles", org_id=store["org1"])[0]["data"]["roles"]}
        perms = by_role["viewer"]
        assert perms["数据座舱"] == "full"
        assert perms["需求管理"] == "read"
        assert perms["测试日志"] == "read"
        assert perms["角色管理"] == "none"

    def test_roles_matrix_quality_mgr_device_read_only(self, store):
        """Quality manager: 设备管理 read, 角色管理 none, rest full."""
        by_role = {r["role"]: r["permissions"]
                   for r in _req("GET", "roles", org_id=store["org1"])[0]["data"]["roles"]}
        perms = by_role["quality_manager"]
        assert perms["设备管理"] == "read"
        assert perms["角色管理"] == "none"
        assert perms["需求管理"] == "full"


# ── Routing / auth ──────────────────────────────────────────────────────

class TestRouting:
    def test_unknown_route_404(self, store):
        payload, status = _req("GET", "nope", org_id=store["org1"])
        assert status == 404 and payload["ok"] is False

    def test_method_not_allowed(self, store):
        payload, status = _req("DELETE", "", org_id=store["org1"])
        assert status == 404

    def test_auth_required(self):
        """GIVEN no current_user and no handler WHEN called THEN 401.

        Uses the DECORATED handler (__wrapped__ bypasses require_auth).
        """
        payload, status = M.handle_members("GET", "", {}, {}, handler=None)
        assert status == 401
        assert "Authorization" in payload["error"]
