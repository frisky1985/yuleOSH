"""Phase 0/1 契约一致性守卫（role drift CI guard）。

单一事实来源：后端 src/yuleosh/rbac/role_contract.py。
本测试断言三处与契约一致，任一处漂移即变红：
  1. 后端 rbac/model.py::get_role_from_user_info 的权限档映射
  2. 后端 api/members.py::VALID_ROLES 的可邀请角色集合 ⊆ 契约角色
  3. codegen 生成物（role-contract.generated.ts + role_contract.json）与契约源完全一致
（前端侧的契约断言在 frontend/src/__tests__/role-view.test.ts。）

# @tests src/yuleosh/rbac/model.py, src/yuleosh/api/members.py,
#       src/yuleosh/rbac/role_contract.py, role_contract.json,
#       frontend/src/lib/role-contract.generated.ts
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

# auth_extended 在导入链上校验 JWT_SECRET；测试环境可能未设，给 dummy 让其通过。
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-dummy-not-for-production")

from yuleosh.rbac.model import get_role_from_user_info  # noqa: E402

try:
    # 与 rbac 解耦：api 包导入链较重，导入失败时降级跳过该子断言，
    # 不影响 rbac ↔ 契约 这条核心守卫。
    from yuleosh.api.members import VALID_ROLES
except Exception:  # pragma: no cover
    VALID_ROLES = None

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = REPO_ROOT / "role_contract.json"
GEN_SCRIPT = REPO_ROOT / "scripts" / "gen_role_contract.py"
GEN_TS_PATH = REPO_ROOT / "frontend" / "src" / "lib" / "role-contract.generated.ts"


def _load_contract() -> dict:
    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_codegen():
    spec = importlib.util.spec_from_file_location("gen_role_contract", GEN_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def contract() -> dict:
    return _load_contract()


@pytest.fixture(scope="module")
def codegen():
    return _load_codegen()


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


def test_new_tiers_map_explicitly(contract: dict) -> None:
    """Phase 1 新增档位：viewer→viewer、quality_manager→quality_manager、architect→developer。"""
    assert get_role_from_user_info({"role": "viewer"}) == "viewer"
    assert get_role_from_user_info({"role": "quality_manager"}) == "quality_manager"
    assert get_role_from_user_info({"role": "architect"}) == "developer"
    # 契约镜像必须如实记录这些档位（不再标 pending_phase1）。
    assert contract["roles"]["viewer"]["permission_tier"] == "viewer"
    assert contract["roles"]["quality_manager"]["permission_tier"] == "quality_manager"
    assert contract["roles"]["architect"]["permission_tier"] == "developer"
    assert "pending_phase1" not in contract, "Phase 1 已完成，role_contract.json 不应再含 pending_phase1"


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


def test_generated_artifacts_match_contract_source(contract: dict, codegen) -> None:
    """codegen 生成物（TS + JSON）必须与后端契约源完全一致（CI 防漂移）。"""
    assert GEN_TS_PATH.read_text(encoding="utf-8") == codegen.render_ts(), (
        "role-contract.generated.ts 与后端契约漂移；请重跑 scripts/gen_role_contract.py"
    )
    committed_json = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert committed_json == json.loads(codegen.render_json()), (
        "role_contract.json 与后端契约漂移；请重跑 scripts/gen_role_contract.py"
    )
