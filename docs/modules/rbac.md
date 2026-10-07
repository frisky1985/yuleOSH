# 模块设计速写：rbac（基于角色的访问控制）

> 包：`src/yuleosh/rbac/` ｜ 规模：3 .py ≈ 398 行 ｜ 标注 SAAS-2
> 关联：权限判定在生产靠内联 `check_role()`，非装饰器

## 职责
定义角色与权限矩阵（RBAC），提供 `check_role()` 供 API/UI 路由做权限判定。证据：`rbac/__init__.py:4-8`、`rbac/model.py:6-29`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `rbac/__init__.py` (28) | re-export | `:17-27` |
| `rbac/model.py` (287) | 权限模型 + 中间件 | `PERMISSION_MATRIX` `:76-157`；`Role` `:162`；`PermissionSet` `:183`；`get_role_from_user_info()` `:214`；`check_role()` `:229`；`require_role()` 装饰器 `:253` |
| `rbac/role_contract.py` (83) | 角色词表单一事实来源 | `ROLE_*` `:26-31`；`ROLE_TO_TIER` `:50`；`INVITABLE_ROLES` `:83`；`ROLE_TO_UI_VIEW` `:64` |

## 公共 API / 入口点
- `check_role(user_info, resource, action="view") -> bool`（`model.py:229`）
- `get_role_from_user_info(user_info) -> str`（`model.py:214`）
- `require_role(resource, action="view")` 装饰器（`model.py:253`）
- 常量 `ROLE_*` / `ROLE_TO_TIER` / `INVITABLE_ROLES` / `ROLE_TO_UI_VIEW`（经 `__init__.py:17-27` 导出）

## 生产接线（真实调用方）
- `api/audit.py:72,74` `check_role(current_user, "audit", "view")`
- `api/members.py:29,35` `INVITABLE_ROLES` → `VALID_ROLES`
- `ui/routes/project_routes.py:165-166,201-202` `check_role(user, "project", ...)`
- `ui/routes/billing_routes.py:82-83,157-158,204-205` `check_role(user, "billing", ...)`

## 运行时触发方式
权限判定是**在每个路由 handler 内联调用 `check_role()`**（resolve_session 解析 user 之后）实现，**不是**通过 `require_role` 装饰器集中挂载。`require_role` 装饰器仅在其自身 docstring 示例与单测中出现。

## 环境变量 / 配置
- **模块本身不读取任何环境变量**（`rbac/**` 中 `os.environ/getenv` 搜索为空）。用户身份依赖 `ui.auth_extended.get_session_user` / `resolve_session`（`model.py:37,266`）。

## 偏差 / 死代码（设计文档必记）
- **D1：`require_role` 装饰器是孤儿**——全仓（含 `src/` 与 `tests/`）仅 `model.py` 定义 + docstring 示例 + 单测（`tests/test_rbac_model_unit.py:227,239,253`）使用；**生产路由均无使用**。权限强制完全靠内联 `check_role()`。
- **D2：`PermissionSet` 类在生产为死代码**——仅定义于 `model.py:183` 并在 `__init__.py:24` 导出；全仓实例化仅出现在测试，生产代码从未构造。
- **D3：两套并行权限矩阵**——`rbac/model.py:76-157` 的 `PERMISSION_MATRIX`（后端 resource/action 级，英文 resource）+ `api/members.py:54-85` 的 `_PERMISSION_MATRIX`（中文 UI 模块级：数据座舱/需求管理/…，粒度更粗，且 `api/members.py:38` 另有 `ADMIN_ROLES`/`PERMISSION_MODULES`）。成员管理视图自维护一份，未复用 `PERMISSION_MATRIX`。
- `ROLE_TO_UI_VIEW` / `ALL_ORG_ROLES` / `ROLE_LEGACY` 供前端 codegen（`scripts/gen_role_contract.py` 生成 `role-contract.generated.ts`）消费，不在后端运行时强制逻辑中使用。

## 规模
3 .py ≈ 398 行。
