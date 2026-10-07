# `yuleosh.api` 模块设计文档

> 子系统定位：Web API 层（`/api/v1/*` 端点、鉴权、限流、审计中间件）
> 代码根：`src/yuleosh/api/`
> 文档性质：详细设计（SWE.3），基于源码实地盘点。

---

## 1. 关键技术事实（先澄清常见误判）

- **框架为自研分发器，非 FastAPI / Flask**。入口链路：
  `src/yuleosh/ui/server.py`（`HTTPServer(ThreadingHTTPServer)` `:76`、`OSHHandler(BaseHTTPRequestHandler)` `:179`、各 HTTP 方法 `:262+`）
  → `src/yuleosh/ui/api_dispatch.py`（`api_v1_dispatch()` `:17` → `from yuleosh.api.router import dispatch` `:33`）
  → `src/yuleosh/api/router.py:117` `dispatch()`。
- `api/router.py:16` 与 `ui/server.py:68-69` 均 `from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer`。
- **全仓无** `fastapi` / `Flask(` 字样（已 grep 确认）。

---

## 2. 路由模型

两级映射（`router.py:85-114`）：
1. URL 第一段 **resource** → 处理函数 `handle_*`（eager `ROUTES` `:85-103` 或懒加载 `_LAZY_HANDLERS` `:42-64,109-114`）。
2. 第二段起为 `path_tail`，由各 `handle_*` 内部按 `method` / `path_tail` 再分发。

所有路径前缀 `/api/v1`。约 **60+ 个端点**，按资源分组如下（方法 + 路径 + 处理函数文件:行）：

**核心资源（eager）**
- `health`：`GET /api/v1/health`（`health.py:27`）
- `wizard`：`POST /api/v1/wizard`（`wizard.py:39`）
- `spec`：`POST /api/v1/spec/validate`、`/spec/diff`（`spec.py:20,74`）
- `pipeline`（`pipeline.py:61`，`@require_auth`）：`POST /trigger`、`GET /status`、`GET /list`、`GET /steps`、`GET /runs`、`GET /stats`、`GET /usage`、`GET /yuleasr-status`、`GET /validate`、`GET /checkpoint`、`/checkpoint/runs`、`/checkpoint/stream`、`/evidence`、`/evidence/download`、`/list`、`/status/{id}`、`POST /yuleasr-notify`、`/retry`、`/resume`、`/rerun`、`/stop`、`GET /jobs`（`pipeline.py:68-207`）
- `ci`（`ci.py:20`）：`GET /ci/runs`、`POST /ci/run/{layer}`
- `review`（`review.py:20`）：`POST /review/auto`、`/review/task`、`GET /review/list`、`/review`
- `evidence`（`evidence.py:44`）：`POST /evidence/generate`、`GET /evidence/files|history|pack|file`
- `project`（`project.py:19`）：`GET /project/stats`、`/project[/list]`、`POST /project`、`/project/seed-demo`
- `stats`（`stats.py:20`）：`GET /stats`、`/stats/overview`、`/stats/trends`
- `auth`（`auth.py:129`）：`POST /auth/register|login`、`GET /auth/me`、`POST /auth/logout`
- `kb`（`kb.py:29`）：`GET/POST /kb/articles[/<id>]`、`GET/POST /kb/search`
- `apikeys`（`apikeys.py:22`）：`POST/GET/DELETE /apikeys[/<id>]`
- `secrets`（`secrets.py:31`）：`POST/GET/DELETE /secrets[/<name>]`
- `audit`（`audit.py:51`，RBAC `audit:view`）：`GET /audit`
- `me` / `org`：`usage.py:74` `GET/PUT /me`、`usage.py:74` `GET /org`（`router.py:37` 实际导入 `api/usage.py` 的 `handle_me`）

**懒加载资源（`_LAZY_HANDLERS`，首次请求 import）**
- `webhooks`：`POST /api/v1/webhooks`（`webhooks.py:96,106`）
- `demo`：`GET /api/v1/demo/*`、`/demo/evidence/*.zip`（`demo.py:277,301,339`）
- `preview`：`POST /preview`、`GET/DELETE /preview/{sub_id}`（`preview.py:605,622,638,666`）
- `subscription`：`GET /subscription[/status]`、`POST /subscription/upgrade|cancel|webhook`（`subscription.py:80,90-96`）
- `dashboard`（`dashboard.py:287`）：`/dashboard/projects`、`/swe-status`、`/gap-analysis*`、`/evidence*`、`/llm-health`、`/coverage`、`/misra-trend`（`dashboard.py:316-367`）
- `dashboard-v2`（`dashboard_v2.py:76`）：`/overview`、`/recent-pipelines`、`/device-status`、`/tests-summary`
- `artifacts`（`artifacts.py:364`）：`/artifacts/list|preview|evidence-pack`
- `tests`（`tests.py:422`）：`/tests`、`/runs`、`/coverage`、`/layers`
- `device-ui`（`device_ui.py:72`）：`/device-ui/list|stats`、`POST /device-ui/{id}/acquire|release`、`GET /device-ui/{id}/events`
- `logs`（`logs.py:147`）：`/logs/pipeline|summary|export`
- `members`（`members.py:99`）：`/members[/list]`、`POST /members/invite`、`GET/PUT/PATCH/DELETE /members/...`
- `requirements`（`requirements.py:74`）：`/requirements`、`/requirements/gaps`、`/requirements/{project}`
- `matrix`（`matrix.py:220`）：`/matrix[/gaps]`
- `events`：`GET /api/v1/events/stream`（SSE，`events.py:71,78`）
- `projects-stats`（`projects_stats.py:130`）：`/projects-stats/stats`
- `kg`（`kg.py:22`，子路由转 `kg_impact`）
- `tenant` / `tenants` / `billing` / `projects`：来自 `yuleosh.ui.routes.*`（`router.py:110-113`），**非 api 包内**

**历史上未接入、现已纠正**
- `compliance.py:31` `handle_compliance`（含 `GET /api/v1/compliance/overview` `:42`）—— **已于 2026-10-07 注册路由**（`router.py:102` `"compliance": handle_compliance,`），`GET /api/v1/compliance/overview` 现已可用。
- `me.py:34` `handle_me` —— `me` 端点实际由 `api/usage.py:29` 的 `handle_me` 提供（`router.py:37` 导入的是 `usage.handle_me`），`me.py` 版本为未被引用的备用实现，但 `me` 端点本身已挂载，**非死代码**。

---

## 3. 认证与中间件

- 无 FastAPI 风格依赖注入。认证为**自研装饰器 + 服务器级校验**。
- `require_auth` 装饰器（`middleware.py:115`）统一注入 `current_user`（user_id/org_id/email/role）。
- 令牌提取 `_extract_token`（`middleware.py:88`）：优先 `Authorization: Bearer`，回退 cookie `yuleosh_at`（`middleware.py:111`）。JWT 校验委托 `ui/auth_extended.verify_token`（`middleware.py:162`）。
- **本地免登录开关**：`AUTH_ENABLED`（`ui/auth.py:36`，由 `YULEOSH_AUTH_DISABLED` 决定 `auth.py:33-36`）。`require_auth` 在 `AUTH_ENABLED=False` 时注入本地 admin（`middleware.py:132-136`）。
- **租户隔离**：`kb.py` 从 JWT 取 `org_id`，在 SQL 层强制 `tenant_org` 过滤（多处 `tenant_org=org_id`）。
- **RBAC**：`audit.py:72-74` `from yuleosh.rbac import check_role` 强制 `audit:view`；`members.py:29` `INVITABLE_ROLES`。
- **限流**：
  - 服务器级每 IP 滑动窗口：`ui/routes/handler_helpers.py:42` `check_rate_limit`（60 req/min 等）。
  - api 内：`api/ratelimit.py:39` `check_rate_limit`（每 IP，阈值 `YULEOSH_RATE_LIMIT` 默认 100 `:35`）；`api/ratelimit_shared.py:226`（`YULEOSH_RATE_DB` SQLite 后端，多 worker 安全）。
  - 预览/演示独立限流：`preview.py:452`、`demo.py:255`。
- **CORS / 安全头**：`api/cors.py`（`YULEOSH_ENV=development` 放行 `*` `:31`；生产校验 `YULEOSH_CORS_ALLOWED_ORIGINS` `:41`）；响应头在 `router.py:247-253`（CSP / X-Content-Type-Options / X-Frame-Options / Referrer-Policy）。
- **审计中间件**：`router.py:175-189` 每次请求写 `audit.log_request`。
- **认证失败 fail-closed**：`ui/api_dispatch.py:17,35` API 路径一律返回 JSON 错误，不降级为 HTML。

---

## 4. 数据契约

- **无** pydantic `BaseModel` / 内部 `@dataclass` 契约（grep 确认）。
- 统一响应：`json_ok(data)` → `{"ok": true, "data": ...}`（`__init__.py:83-85`）；`json_error(msg, status)` → `{"ok": false, "error": str}`（`__init__.py:88-106`）。
- 请求体解析 `read_body(handler)`（JSON / form-urlencoded，10MB 上限 `MAX_BODY_BYTES` `:80`，`:109-160`）。
- 异常类 `BadRequest`（`__init__.py:74`）。
- 外部导入的数据模型（非 api 内定义）：`NotifyConfig`（`notify.py:42`，来自 `yuleosh.notify`）、`kb.models` / `KbStore`、`AuditLog`（`me.py:22`，来自 `yuleosh.audit.model`）、`INVITABLE_ROLES`（`members.py:29`）、`Device*`（`device_ui.py:33`）。

---

## 5. 配置（`YULEOSH_*` 环境变量）

| Key | 用途 |
|---|---|
| `OSH_HOME` | 主数据根目录（`__init__.py:23,31-71` 模块级快照 + `resolve_osh_home`） |
| `YULEOSH_ENV` | `development` → CORS `*` |
| `YULEOSH_CORS_ALLOWED_ORIGINS` | 生产 CORS 白名单 |
| `YULEOSH_AUTH_DISABLED` | `true/1/yes` → 关闭认证 |
| `YULEOSH_JWT_SECRET` | 服务启动必需（JWT secret 实际由 `ui.auth_extended` 提供） |
| `YULEOSH_RATE_LIMIT` | 每 IP 限流阈值，默认 100 |
| `YULEOSH_RATE_DB` | SQLite 限流库路径 |
| `YULEOSH_DEVICE_DB` | 设备注册库路径 |
| `YULEOSH_DEMO_ENABLED` | demo 开关，默认 `true` |
| `YULEOSH_AUDIT_ROOT` | 审计根目录 |
| `YULEOSH_LLM_PROVIDER` | LLM provider，默认 `deepseek` |
| `STRIPE_SECRET_KEY` | 订阅支付 |
| `WEBHOOK_SECRET_ENV` | webhook HMAC secret 的环境变量名 |
| 端口 / bind | **不在 api 包内**，由 `ui/server.py` / `ui/http_app.py` 配置 |

---

## 6. 集成点

- `api` import 同仓：`yuleosh.store.Store`、`yuleosh.ui.auth_extended`（JWT）、`yuleosh.rbac`、`yuleosh.llm.client`、`yuleosh.realtime`（EVENT_BUS）、`yuleosh.spec.validate`、`yuleosh.pipeline.*`、`yuleosh.engine.checkpoint`、`yuleosh.evidence.*`、`yuleosh.preview.*`、`yuleosh.kb.*`、`yuleosh.knowledge_graph`、`yuleosh.device.*`、`yuleosh.notify`、`yuleosh.secret_vault`、`yuleosh.usage`、`yuleosh.audit.model`、`yuleosh.alm.traceability`、`yuleosh.ci.rulesets` 等（详见 `router.py` / 各 `handle_*`）。
- 外部 import `api`：`ui/api_dispatch.py`、`ui/routes/*`、`ui/auth_extended.py`、`ui/auth_cookies.py`、`ui/http_security.py`、`cli/main.py:690,693`（`demo_wow` / `demo_quick`）。

---

## 7. 测试

`tests/` 下相关：`test_api_smoke.py`、`test_api_auth_coverage.py`、`test_api_spec_ext.py`、`test_api_stats_ext.py`、`test_api_project_ext.py`、`test_api_members.py`、`test_api_pipeline_ext.py`、`test_api_pipeline_steps_ext.py`、`test_api_ci_ext.py`、`test_api_evidence_ci.py`、`test_api_tests.py`、`test_api_compliance_ext.py`、`test_api_validate_ext.py`、`test_api_middleware_ext.py`、`test_api_notify_ext.py`、`test_api_dashboard_unit.py`、`test_api_demo_extended.py`、`test_api_services_extended.py`、`test_api_audit_ext.py`、`test_api_small_modules.py`、`test_api_preview_unit.py`、`test_api_supplementary.py`，以及认证/安全类 `test_security.py`、`test_v380_a1_auth_unify.py`、`test_auth_extended_handlers.py`、`test_ui_auth_deep.py`、`test_tenant_security.py`、`test_role_contract.py`、集成类 `test_server_integration.py`、`test_ui_server.py`、`test_ui_routes_api_ext.py`、`test_coverage_phase4_pipeline_routes.py`、`test_product_v1.py` 等。

---

## 8. 已知偏差 / 待决

- `compliance.py`（`handle_compliance`）**已于 2026-10-07 注册路由**（`router.py:102`），`GET /api/v1/compliance/overview` 可用；`me` 端点由 `api/usage.py` 的 `handle_me` 提供并挂载，`me.py` 为未被引用的备用实现（非功能性死代码，可保留或归档）。
- 无结构化请求体 schema 校验（`validate.py` 提供辅助函数但未被路由直接调用），错误输入依赖各 handler 内散落检查。
