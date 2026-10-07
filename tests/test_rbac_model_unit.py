"""Unit tests for yuleosh.rbac.model — Role / middleware (v3.4.2 Wave 0).

Covers:
  - Role: valid/invalid names, labels, can() permission matrix lookups
  - get_role_from_user_info(): None/unknown/legacy role mapping
  - check_role(): allow/deny paths + denial logging
"""

# @tests src/yuleosh/rbac/model.py

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
    ROLE_VIEWER,
    ROLE_QUALITY_MANAGER,
    ROLE_LABELS,
    PERMISSION_MATRIX,
    Role,
    get_role_from_user_info,
    check_role,
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

    def test_viewer_and_quality_manager_registered(self):
        """GIVEN Phase 1 new tiers WHEN in ALL_ROLES THEN constructible."""
        assert ROLE_VIEWER in ALL_ROLES
        assert ROLE_QUALITY_MANAGER in ALL_ROLES
        assert Role(ROLE_VIEWER).label == ROLE_LABELS[ROLE_VIEWER]
        assert Role(ROLE_QUALITY_MANAGER).label == ROLE_LABELS[ROLE_QUALITY_MANAGER]

    def test_viewer_is_readonly(self):
        """GIVEN viewer WHEN can THEN view-only on every module, no write/run/commit."""
        v = Role(ROLE_VIEWER)
        assert v.can("tenant", "view") is True
        assert v.can("code", "view") is True
        assert v.can("pipeline", "view") is True
        assert v.can("evidence", "view") is True
        # 只读：无创建/编辑/运行/提交/审批/导出权限
        assert v.can("pipeline", "run") is False
        assert v.can("code", "commit") is False
        assert v.can("tenant", "edit") is False
        assert v.can("review", "approve") is False
        assert v.can("evidence", "export") is False

    def test_quality_manager_approves_and_exports_but_not_dev(self):
        """GIVEN quality_manager WHEN can THEN approve/reject review + export evidence/audit, no commit/run."""
        q = Role(ROLE_QUALITY_MANAGER)
        assert q.can("review", "approve") is True
        assert q.can("review", "reject") is True
        assert q.can("evidence", "export") is True
        assert q.can("audit", "view") is True
        assert q.can("audit", "export") is True
        # 非开发者：无代码提交 / 流水线运行 / 租户编辑
        assert q.can("code", "commit") is False
        assert q.can("pipeline", "run") is False
        assert q.can("tenant", "edit") is False
        assert q.can("billing", "view") is False  # 仅 admin/auditor

    def test_repr(self):
        """GIVEN role WHEN repr THEN contains name."""
        assert "admin" in repr(Role(ROLE_ADMIN))


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


# ── (require_role decorator removed: dead code, superseded by api/members.py matrix) ──
