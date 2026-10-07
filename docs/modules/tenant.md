# 模块设计速写：tenant（多租户数据模型与持久化）

> 包：`src/yuleosh/tenant/` ｜ 规模：2 .py ≈ 277 行 ｜ 标注 SAAS-1
> 关联：身份以 slug 为主键；与 `usage`（org_id 整数）非原生统一

## 职责
基于文件系统的多租户数据模型与持久化层，每个租户用 slug 命名，数据隔离在独立目录 + JSON 元数据中（"SAAS-1: Data isolation at the file-system layer"）。证据：`tenant/model.py:4-11`、`tenant/__init__.py:4-11`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `tenant/__init__.py` (20) | re-export | `Tenant` / `TenantStore` / `PLAN_*` / `TIER_LIMITS` `:13-20` |
| `tenant/model.py` (257) | 核心实现 | `PLAN_FREE/PRO/ENTERPRISE` `:33-35`；`TIER_LIMITS` `:37-60`；`Tenant` `:67`；`TenantStore` `:109` |

## 公共 API / 入口点（均 `model.py`）
- `TenantStore.get/get_or_create/create/update/delete/list_tenants` `:133/:141/:148/:170/:182/:194`
- `save_project/get_project/list_projects/delete_project` `:208/:219/:226/:236`
- `get_config/set_config` `:246/:253`；`Tenant.has_feature` `:92`、`Tenant.limits` 属性 `:88`

## 生产接线（真实调用方）
- `ui/routes/tenant_routes.py:19` 导入 `TenantStore` 并实例化用于 `:100,:124,:144,:168,:181,:204`
- `ui/routes/project_routes.py:26` 用于 `:116,:135,:169,:205`
- 路由注册：`api/router.py:112` `"tenant" -> handle_tenant`；`:113` `"tenants" -> handle_tenant_list`（`_LAZY_HANDLERS` 懒加载）

## 运行时触发方式
REST：`GET/PUT/POST /api/v1/tenant/{slug}[/projects|/usage]` 经 `handle_tenant` 分发（`tenant_routes.py:60-87`）；`GET /api/v1/tenants` 经 `handle_tenant_list`（`tenant_routes.py:137`）。均 `_require_auth`（`tenant_routes.py:33-48`）。

## 环境变量 / 配置
- `OSH_HOME`（`model.py:122-124`）：数据根目录，默认 `~/.openclaw/workspace/tasks/yuleOSH/data`。tenant 子系统本身不读其他 env。

## 隔离模型
文件系统层：租户元数据 `data/tenants/{slug}.json`（`model.py:128`、`_save` `:202-204`），数据目录 `data/{slug}/`（含 projects/config/evidence/audit 子目录，`model.py:161-166`）。无数据库，靠 slug 路径前缀；`slug` 受 `SLUG_RE` 校验（`model.py:106`）。

## 偏差 / 待注意（设计文档必记）
- **D1：计划口径不一致**——`tenant/model.py:37-60` 的 `TIER_LIMITS`（键 `max_pipeline_runs_monthly` 等）与 `usage/metering.py:34-65` 的 `TIERS`（键 `max_pipeline_runs` 等）是两套不同键名、非同一来源。
- **D2：`tenant/__init__.py` 导出的 `PLAN_*`/`TIER_LIMITS` 未被其他模块复用**（billing 侧用 `yuleosh.billing` 的 `PLAN_LIMITS`）。租户计划表基本未被计量侧消费。
- `create()` 创建 `audit` 子目录（`:166`）但 model 内无审计写入 API（可能由其他模块负责）。

## 规模
2 .py ≈ 277 行。
