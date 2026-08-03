"""Unit tests for yuleosh.rbac.model — Role / PermissionSet / middleware (v3.4.2 Wave 0).

Covers:
  - Role: valid/invalid names, labels, can() permission matrix lookups
  - PermissionSet: can(), resources(), to_dict()
  - get_role_from_user_info(): None/unknown/legacy role mapping
  - check_role(): allow/deny paths + denial logging
  - require_role(): decorator success path, 403 denial path (token/no token)
"""

import io
import json
import os
import sys
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.rbac.model import (
    ALL_ROLES,
    ROLE_ADMIN,
    ROLE_DEVELOPER,
    ROLE_REVIEWER,
    ROLE_AUDITOR,
    ROLE_LABELS,
    PERMISSION_MATRIX,
    Role,
    PermissionSet,
    get_role_from_user_info,
    check_role,
    require_role,
)


# ── Role ──────────────────────────────────────────────────────────────

class TestRole:
    def test_valid_roles(self):
        """GIVEN each built-in role WHEN constructed THEN name/label set."""
        for name in ALL_ROLES:
            r = Role(name)
            assert r.name == name
            assert r.label == ROLE_LABELS[name]

    def test_invalid_role_raises(self):
        """GIVEN unknown role name WHEN constructed THEN ValueError."""
        with pytest.raises(ValueError):
            Role("superuser")

    def test_admin_can_manage_tenant(self):
        """GIVEN admin WHEN can(tenant, edit) THEN True."""
        assert Role(ROLE_ADMIN).can("tenant", "edit") is True

    def test_developer_cannot_edit_tenant(self):
        """GIVEN developer WHEN can(tenant, edit) THEN False."""
        assert Role(ROLE_DEVELOPER).can("tenant", "edit") is False

    def test_reviewer_can_approve(self):
        """GIVEN reviewer WHEN can(review, approve) THEN True."""
        assert Role(ROLE_REVIEWER).can("review", "approve") is True

    def test_auditor_can_view_audit(self):
        """GIVEN auditor WHEN can(audit, view) THEN True."""
        assert Role(ROLE_AUDITOR).can("audit", "view") is True

    def test_unknown_resource_defaults_false(self):
        """GIVEN unknown resource WHEN can THEN False (no permission)."""
        assert Role(ROLE_ADMIN).can("no_such_resource") is False

    def test_unknown_action_defaults_false(self):
        """GIVEN unknown action on known resource WHEN can THEN False."""
        assert Role(ROLE_ADMIN).can("tenant", "no_such_action") is False

    def test_repr(self):
        """GIVEN role WHEN repr THEN contains name."""
        assert "admin" in repr(Role(ROLE_ADMIN))


# ── PermissionSet ─────────────────────────────────────────────────────

class TestPermissionSet:
    def test_can_delegates(self):
        """GIVEN permission set WHEN can THEN delegates to role matrix."""
        ps = PermissionSet(ROLE_ADMIN)
        assert ps.can("billing", "upgrade") is True
        ps2 = PermissionSet(ROLE_DEVELOPER)
        assert ps2.can("billing", "upgrade") is False

    def test_resources_admin_wide(self):
        """GIVEN admin WHEN resources THEN covers all matrix resources."""
        ps = PermissionSet(ROLE_ADMIN)
        resources = set(ps.resources())
        assert resources == set(PERMISSION_MATRIX.keys())

    def test_resources_auditor_limited(self):
        """GIVEN auditor WHEN resources THEN view-only subset."""
        ps = PermissionSet(ROLE_AUDITOR)
        resources = set(ps.resources())
        assert "audit" in resources
        assert "billing" in resources  # view only
        assert "tenant" in resources
        # auditor must NOT get pipeline run
        assert not ps.can("pipeline", "run")

    def test_to_dict(self):
        """GIVEN developer WHEN to_dict THEN actions grouped by resource."""
        ps = PermissionSet(ROLE_DEVELOPER)
        d = ps.to_dict()
        assert "project" in d
        assert "create" in d["project"]
        assert "delete" not in d["project"]  # admin-only
        assert "pipeline" in d and "run" in d["pipeline"]


# ── get_role_from_user_info ───────────────────────────────────────────

class TestGetRoleFromUserInfo:
    def test_none_returns_auditor(self):
        """GIVEN None user info WHEN get_role THEN auditor (lowest)."""
        assert get_role_from_user_info(None) == ROLE_AUDITOR

    def test_member_maps_to_developer(self):
        """GIVEN legacy 'member' role WHEN get_role THEN developer."""
        assert get_role_from_user_info({"role": "member"}) == ROLE_DEVELOPER

    def test_owner_maps_to_admin(self):
        """GIVEN legacy 'owner' role WHEN get_role THEN admin."""
        assert get_role_from_user_info({"role": "owner"}) == ROLE_ADMIN

    def test_unknown_role_defaults_developer(self):
        """GIVEN unknown role string WHEN get_role THEN developer."""
        assert get_role_from_user_info({"role": "guest"}) == ROLE_DEVELOPER

    def test_missing_role_key_defaults_developer(self):
        """GIVEN user info without role key WHEN get_role THEN developer."""
        assert get_role_from_user_info({"email": "a@b.c"}) == ROLE_DEVELOPER


# ── check_role ────────────────────────────────────────────────────────

class TestCheckRole:
    def test_allows_matching_role(self):
        """GIVEN permitted user WHEN check_role THEN True."""
        assert check_role({"role": ROLE_ADMIN}, "tenant", "delete") is True

    def test_denies_non_matching_role(self):
        """GIVEN insufficient role WHEN check_role THEN False + warning."""
        with mock.patch("yuleosh.rbac.model.logger") as mlog:
            ok = check_role({"role": ROLE_DEVELOPER, "email": "d@x.io"},
                            "billing", "upgrade")
        assert ok is False
        mlog.warning.assert_called_once()

    def test_none_user_info_denied(self):
        """GIVEN no user WHEN check_role THEN denied for privileged actions."""
        assert check_role(None, "tenant", "edit") is False


# ── require_role decorator ────────────────────────────────────────────

class _FakeHandler:
    """Minimal stand-in for an HTTP request handler."""

    def __init__(self, headers=None, token=None):
        self.headers = headers or {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.wfile = io.BytesIO()
        self.sent = []

    def send_response(self, code):
        self.sent.append(("response", code))

    def send_header(self, name, value):
        self.sent.append(("header", name, value))

    def end_headers(self):
        self.sent.append(("end_headers",))


class TestRequireRole:
    def test_allowed_calls_through(self):
        """GIVEN token with sufficient role WHEN decorator THEN handler runs."""
        with mock.patch("yuleosh.rbac.model.get_session_user",
                        return_value={"role": ROLE_ADMIN, "email": "a@x.io"}):
            @require_role("tenant", "delete")
            def handle(handler, *args, **kwargs):
                return "ok"

            handler = _FakeHandler(token="tok")
            assert handle(handler, "/path") == "ok"
            assert handler.sent == []

    def test_denied_returns_403(self):
        """GIVEN token with insufficient role WHEN decorator THEN 403 body."""
        with mock.patch("yuleosh.rbac.model.get_session_user",
                        return_value={"role": ROLE_DEVELOPER, "email": "d@x.io"}):
            @require_role("billing", "upgrade")
            def handle(handler, *args, **kwargs):
                return "should-not-run"

            handler = _FakeHandler(token="tok")
            result = handle(handler, "/path")
            assert result is None
            assert ("response", 403) in handler.sent
            body = json.loads(handler.wfile.getvalue().decode())
            assert body["ok"] is False

    def test_no_token_denied(self):
        """GIVEN no Authorization header WHEN decorator THEN 403 without user lookup."""
        with mock.patch("yuleosh.rbac.model.get_session_user") as m_get:
            @require_role("tenant", "delete")
            def handle(handler, *args, **kwargs):
                return "should-not-run"

            handler = _FakeHandler(token=None)
            assert handle(handler, "/x") is None
            m_get.assert_not_called()
            assert ("response", 403) in handler.sent
