# 模块设计速写：usage（用量计量与 Stripe 支付）

> 包：`src/yuleosh/usage/` ｜ 规模：3 .py ≈ 301 行 ｜ 标注 v0.9.0
> 关联：与 `billing` 并存双计量系统；身份以 org_id（整数）为主键

## 职责
按组织计量（pipeline 运行次数 / LLM tokens / 存储 / 项目数）+ Stripe 支付集成 + 套餐限额强制 + 试用状态计算。证据：`usage/metering.py:4-8`、`usage/__init__.py:4`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `usage/__init__.py` (12) | 汇聚导出 | `:5-12` |
| `usage/metering.py` (171) | 纯函数式计量（依赖传入 `store`） | `TIERS` `:34`；`TRIAL_DAYS=14` `:67`；`get_org_tier` `:70`；`get_trial_status` `:78`；`check_tier_limit` `:108`；`record_pipeline_run` `:134`；`get_usage_summary` `:153` |
| `usage/stripe_gateway.py` (118) | Stripe 集成 | `is_stripe_configured` `:22`；`create_checkout_session` `:27`；`handle_stripe_webhook` `:59` |

## 公共 API / 入口点
- `get_org_tier` / `get_trial_status` / `check_tier_limit` / `record_pipeline_run` / `get_usage_summary`
- `is_stripe_configured` / `create_checkout_session` / `handle_stripe_webhook`

## 生产接线（真实调用方）
- `pipeline/async_runner.py:57` `record_pipeline_run`（仅 `org_id>0`，`:53`）
- `pipeline/orchestrator.py:775` `record_pipeline_run`（收尾，`:772` `org_id>0`）
- `api/subscription.py:19-27` 导入全套；`get_trial_status` `:128`、`get_usage_summary` `:129`、`is_stripe_configured` `:139/:198`、`create_checkout_session` `:207`、`handle_stripe_webhook` `:288`
- `ui/routes/billing_routes.py:116` 借 `TIERS` 作 LLM token 限额来源

## 运行时触发方式
- 计量写入：pipeline 执行路径内**非阻塞副作用**，失败仅 warning（`:784-785`、`:60-61`），不阻断 pipeline。
- 支付/订阅：`/api/v1/subscription/*`（`api/router.py:47` 懒加载 `handle_subscription`）分发 `status/upgrade/cancel/webhook`（`subscription.py:90-99`）。
- 计量读取：`/api/v1/subscription/status` → `get_usage_summary`+`get_trial_status`；`/api/v1/billing/usage` 只用 `TIERS`。

## 环境变量 / 配置
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `YULEOSH_BASE_URL`（默认 `http://localhost:8080`）（`stripe_gateway.py:15-19`，`BASE_URL` 派生 `SUCCESS_URL`/`CANCEL_URL` `:18-19`）
- `api/subscription.py:242` 单独再读 `STRIPE_SECRET_KEY`（与 gateway 重复，漂移风险）

## 隔离模型
自身不做隔离；函数收 `org_id:int` + `store` 实例。隔离委托 `store` 的 `usage_log` 表 `org_id` 列（`store.py:1102-1117` INSERT 含 `org_id`；`get_monthly_usage` `:1119-1134` `WHERE org_id=?`；`get_monthly_usage_by_user` `:1136-1160`）。

## 偏差 / 死代码（设计文档必记）
- **D1：双计量系统并存**——`yuleosh.usage`（org_id + SQLite `usage_log`，真实写入端 `record_pipeline_run`）vs `yuleosh.billing`（`billing/metering.py` 的 `UsageMeter`/`BillingManager`，slug + jsonl 文件，计费页主路径）。`billing_routes.handle_get_usage` 双源合并（`billing_routes.py:73-144`，Phase 9 注释）。计费页优先 `yuleosh.billing`，仅借 `yuleosh.usage` 的 `TIERS`。
- **D2：`check_tier_limit` 是孤儿**（零调用），限额实际未被强制；`TIERS` 中 `price_monthly` 全 0、`stripe_price_id` 全 `None`（`:43,53,63`）—— Stripe 价格需手动配，当前「未配置价格」状态。
- **D3：`record_pipeline_run` 命名碰撞**——`usage/metering.py:134` 写 `usage_log`（经 `store.record_usage`）；`store.py:628` 同名 `Store.record_pipeline_run` 写 `pipeline_runs` 表（schema/语义不同），易混淆。
- **D4：遗留死代码** `ui/routes/api_routes.py:136` `handle_usage` 未被 `api/router.py` 注册（router 无 `"usage"` 资源），且 `:148` 已 return 后 `:149-153` 逻辑永不执行。
- 身份模型冲突：tenant 用 slug、usage 用 org_id，唯一交汇是 `billing_routes.py:103-119` 的 slug→org 桥接（`store.get_organization(tenant_slug)`）。

## 规模
3 .py ≈ 301 行。
