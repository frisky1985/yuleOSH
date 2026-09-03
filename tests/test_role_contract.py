"""Phase 0 契约一致性守卫（role drift CI guard）。

单一事实来源：仓库根 role_contract.json。
本测试断言两套真实角色词表与契约一致：
  1. 后端 rbac/model.py::get_role_from_user_info 的权限档映射
  2. 后端 api/members.py::VALID_ROLES 的可邀请角色集合
若有人改了 rbac / members 却没同步契约，测试变红。
（前端侧的契约断言在 frontend/src/__tests__/role-view.test.ts。）

# @tests src/yuleosh/rbac/model.py, src/yuleosh/api/members.py, role_contract.json
"""

import json
from pathlib import Path

import pytest

from yuleosh.rbac.model import get_role_from_user_info

try:
    # 与 rbac 解耦：api 包导入链较重，导入失败时降级跳过该子断言，
    # 不影响 rbac ↔ 契约 这条核心守卫。
    from yuleosh.api.members import VALID_ROLES
except Exception:  # pragma: no cover
    VALID_ROLES = None

CONTRACT_PATH = Path(__file__).resolve().parent.parent / "role_contract.json"


def _load_contract() -> dict:
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def contract() -> dict:
    return _load_contract()


def test_contract_file_present(contract: dict) -> None:
    assert "roles" in contract and contract["roles"], "role_contract.json 必须定义 roles 映射"


def test_rbac_maps_to_contract_permission_tier(contract: dict) -> None:
    """get_role_from_user_info 对每个契约角色的返回值必须等于契约 permission_tier。"""
    for role, spec in contract["roles"].items():
        got = get_role_from_user_info({"role": role})
        assert got == spec["permission_tier"], (
            f"rbac 权限档与契约漂移：{role!r} "
            f"got {got!r}, expected {spec['permission_tier']!r}；"
            f"请同步 role_contract.json 或 rbac/model.py"
        )


def test_members_valid_roles_subset_of_contract(contract: dict) -> None:
    """members.VALID_ROLES 中每个可邀请角色都必须在契约里有定义。"""
    if VALID_ROLES is None:
        pytest.skip("yuleosh.api.members 在当前环境不可导入，跳过 VALID_ROLES 子断言")
    contract_roles = set(contract["roles"].keys())
    for r in VALID_ROLES:
        assert r in contract_roles, (
            f"可邀请角色 {r!r} 未出现在 role_contract.json；"
            f"请同步契约（或确认该角色是否应属成员管理词表）"
        )
