# `billing` 模块设计速写

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/billing/`。
> 与代码冲突时以代码为准。

## 0. 概述
计费 / 配额 / 订阅模块。核心是 `UsageMeter`（文件型用量计量）+ `BillingManager`
（Stripe mock / 真模式订阅）。模块自述「Usage metering & Stripe integration (SAAS-5)」
（`__init__.py:4`、`metering.py:6`）。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `billing/__init__.py` | 21 |
| `billing/metering.py` | 381 |

## 2. 核心职责
- **用量计量**：`UsageMeter` 以 JSONL 文件（`data/{tenant}/usage/YYYY-MM.jsonl`）记录
  CI 运行 / API 调用 / 存储用量，提供计划限额对比与 `is_within_limits` 检查
  （`metering.py:98`、`metering.py:189`）。
- **计划限额**：`PLAN_FREE` / `PLAN_PRO` / `PLAN_ENTERPRISE` 三档，含
  `max_projects/max_users/max_ci_runs/max_storage_mb/features/...`（`metering.py:43-80`）。
- **Stripe 订阅**：`BillingManager` 在 `STRIPE_SECRET_KEY` 未设置时进入 **mock 模式**
  （内存会话、自动激活订阅），否则调真实 Stripe SDK（`metering.py:222, 240-249`）。

## 3. 关键类与函数（文件:行号）
- `UsageEntry` dataclass（`metering.py:85`，`__post_init__` 自动填 `timestamp` `:93`）。
- `UsageMeter`（`metering.py:98`）：`increment` `:126`、`increment_ci_run` `:137`、
  `get_monthly_usage` `:141`、`get_usage_summary` `:168`、`is_within_limits` `:189`。
- `MockStripeSession`（`metering.py:208`）。
- `BillingManager`（`metering.py:222`）：`create_checkout_session` `:251`、`handle_webhook` `:302`、
  `_activate_subscription` `:334`、`get_subscription` `:364`、`cancel_subscription` `:378`。

## 4. 数据模型
`UsageEntry`（dataclass）：`resource`（`ci_run`/`storage_bytes`/`api_call`）、`tenant`、`amount`、
`timestamp`。`MockStripeSession` 为普通类（非 dataclass）。

## 5. 集成点
- billing **不 import 任何 `yuleosh.*` 其它子包**（仅标准库）。
- 被 import：`ui/routes/billing_routes.py:19` → `from yuleosh.billing.metering import
  (UsageMeter, BillingManager, PLAN_LIMITS, PLAN_FREE, PLAN_PRO, PLAN_ENTERPRISE)`。
- HTTP 入口：`billing_routes.py:51` `handle_billing(method, path_tail, body, query, handler)`；
  路由注册于 `api/router.py:112` → `"billing": ("yuleosh.ui.routes.billing_routes", "handle_billing")`。
  端点：`GET /api/v1/billing/usage`、`GET /api/v1/billing/plan`、`POST /api/v1/billing/upgrade`
  （`billing_routes.py:8-13`），鉴权走 `ui/auth_extended`。

## 6. 配置 / 环境变量
- `OSH_HOME`（`metering.py:109, 230`）— 数据根默认 `$OSH_HOME/data`。
- `STRIPE_SECRET_KEY`（`metering.py:240`）— 设置则真 Stripe 模式，未设则 mock
  （`self.mock_mode = not bool(self.stripe_key)`）。
- 计划限额 / 价格为代码常量 `PLAN_LIMITS`（`metering.py:47-78`）。

## 7. 测试
`test_billing_metering_unit.py`、`test_coverage_phase9_billing_user.py`。

## 8. 备注
billing 集成完整（有路由、有测试、有 env 开关），是本批评审中**偏差最小**的模块。
