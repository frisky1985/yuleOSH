# @req RS-007  @req CR-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""角色 → 权限档 → UI 视图 的单一事实来源（single source of truth）。

本模块是 yuleOSH 角色词表的权威契约，刻意不依赖 model.py（后者会拉起
auth_extended 的 JWT 校验链，带运行期副作用），以便 codegen 与契约测试可在任意
环境无副作用导入。

后端 `rbac/model.py` 从本模块导入角色常量，并把 `get_role_from_user_info` 的映射
改为读取 `ROLE_TO_TIER`；前端 `role-view.ts` 经 `scripts/gen_role_contract.py`
生成的 `role-contract.generated.ts` 消费 `ROLE_TO_UI_VIEW`。三套词表（rbac /
members / 前端视图）因此收敛到本契约。

映射维度：
  - ROLE_TO_TIER：    组织/邀请角色 → 后端权限档（permission tier）
  - ROLE_TO_UI_VIEW： 组织/邀请角色 → 前端 UI 视图（decision=决策顶栏 / engineer=工程左栏）

改任一角色映射，必须同步本文件并重新生成：
  - 前端产物：  scripts/gen_role_contract.py（已提交，CI 校验 diff）
  - 镜像 JSON：  scripts/gen_role_contract.py 一并生成 role_contract.json
"""

# 后端权限档（permission tier）字符串常量——yuleOSH 角色词表的唯一事实来源。
ROLE_ADMIN = "admin"
ROLE_DEVELOPER = "developer"
ROLE_REVIEWER = "reviewer"
ROLE_AUDITOR = "auditor"
ROLE_VIEWER = "viewer"
ROLE_QUALITY_MANAGER = "quality_manager"

# 组织/邀请角色全集（与 api/members.py::VALID_ROLES 及 legacy 别名 member 对齐）。
ALL_ORG_ROLES = (
    "owner",
    "admin",
    "quality_manager",
    "architect",
    "developer",
    "reviewer",
    "auditor",
    "viewer",
    "member",
)

# org role → 后端权限档。
# member 为 legacy 别名（join-by-invite 创建），保持 developer 向后兼容；
# architect 复用 developer 档（架构师需要开发者级工程访问）；
# 未知/遗漏角色的下沉默认见 model.get_role_from_user_info（developer）。
ROLE_TO_TIER = {
    "owner": ROLE_ADMIN,
    "admin": ROLE_ADMIN,
    "architect": ROLE_DEVELOPER,
    "developer": ROLE_DEVELOPER,
    "reviewer": ROLE_REVIEWER,
    "auditor": ROLE_AUDITOR,
    "member": ROLE_DEVELOPER,
    "quality_manager": ROLE_QUALITY_MANAGER,
    "viewer": ROLE_VIEWER,
}

# org role → 前端 UI 视图。仅 admin/owner 走决策视角；其余（含只读 viewer、
# 质量经理 quality_manager）均走工程视角——其可见性落在工程产物（代码/测试/证据）上。
ROLE_TO_UI_VIEW = {
    "owner": "decision",
    "admin": "decision",
    "architect": "engineer",
    "developer": "engineer",
    "reviewer": "engineer",
    "auditor": "engineer",
    "member": "engineer",
    "quality_manager": "engineer",
    "viewer": "engineer",
}

# legacy 别名（不参与邀请，仅存量数据 / join-by-invite 使用）。
ROLE_LEGACY = {"member"}
