# Spec — yuleOSH v3.8.0（Track2 架构收敛）

> 版本: v3.8.0 · 基线: v3.7.0 (2e0eef5) · 日期: 2026-08-03
> 方法: OpenSpec（SHALL/SHOULD/MAY + GIVEN/WHEN/THEN）
> 依据: `~/.openclaw/workspace/plans/yuleOSH-v3.7-roadmap.md`（方案 A：v3.8.0 = Track2 架构收敛）+ `reviews/ultra-full-2026-08-02/implementation-plan.md`（Fix 13-16）+ `TASK_STATUS.md`（v3.7.0 遗留 2/3）
> 上游裁决: 小明（需求）· 开发: 小克 · 复验: 小马（本文档为复验依据）
> 范围说明: Track3 前端安全 → v3.9.0；yuleASR-Configurator 另行排期。本文档不涉及。
> 行号证据: 全部为 HEAD=2e0eef5（v3.7.0）实测，与评审报告行号可能有偏移，以实测为准。

---

## 0. 需求编号规则

- 每项需求编号 `SHALL-Ax.n`（A1-A6）/ `SHALL-Fx.n`（附项 F1-F4），x = 项号，n = 条款序号。
- 测试 ID 规则见 `acceptance-matrix.md`（`T-Ax.n-xxx` / `T-Fx.n-xxx`），负例统一后缀 `-neg`。
- 验收判定：**所有 SHALL 条款有对应测试（正例 + 负例）且全绿**，方视为该项完成。
- 全局回归基线（v3.7.0）: **9873 passed / 0 failed**；覆盖率 ≥ **84.10%** 不降。

---

## 1. A1 — 认证三套合一（来源 A-C-02 / Fix 13，估时 2d）

### 现状（grep 证据，HEAD=2e0eef5）

**三套认证并存**：

| # | 实现 | 机制 | 关键符号 | 调用点 |
|---|------|------|----------|--------|
| ① | `ui/auth.py`（230 行） | legacy API key + session cookie（内存 HMAC 签名） | `API_KEY` / `AUTH_ENABLED` / `is_authenticated` / `create_session` / `validate_session` | `ui/server.py:73,343`；`ui/routes/api_routes.py:40`；`ui/routes/auth_routes.py:20,59`；`api/health.py:125` |
| ② | `ui/auth_extended.py`（638 行） | 前端租户 JWT（`sub`/`org` 声明）+ bcrypt + `_ThreadSafeDict` 限流 | `JWT_SECRET` / `get_session_user` / `handle_signin` / `handle_org_create` / `handle_session_info` / `handle_logout` / `handle_project_list` / `handle_project_create` / `handle_org_info` | `ui/auth.py:215`；`ui/routes/auth_routes.py:94`（`handle_api_action`）；`ui/routes/audit_routes.py:31`；`ui/routes/tenant_routes.py:17`；`ui/routes/billing_routes.py:32`；`ui/routes/api_routes.py:44,145`；`ui/routes/project_routes.py:43`；`rbac/model.py:32`；`api/preview.py:498,528` |
| ③ | `api/auth.py`（365 行）+ `api/middleware.py` | v1 API JWT（`user_id`/`org_id` 声明）+ bcrypt + 普通 dict 限流 | `_JWT_SECRET` / `handle_auth`（register/login/me/logout）/ `require_auth` | `api/router.py:35`（`handle_auth`）；`api/middleware.py:17`（`_JWT_SECRET`）；`require_auth` 装饰 15 个 handler（apikeys/audit/ci/compliance/dashboard/evidence/kb/kg/notify/pipeline/project/review/spec/stats） |

**重复实现清单**（A1 消灭对象）：
- **JWT secret 四处读取**：`api/auth.py:38-40`（fail-fast）、`ui/auth_extended.py:40-42`（fail-fast）、`api/subscription.py:60`（**每次调用随机兜底** `secrets.token_urlsafe(32)` ← bug）、`api/wizard.py:21`（**同款 bug**）。
- **两套 bcrypt**：`api/auth.py` `_hash_password`/`_verify_password`（:72-89）与 `auth_extended.py`（:263-270）。
- **两套 token 签发**：`api/auth.py._generate_token`（`user_id`/`org_id` 声明，:92-103）与 `auth_extended.py._generate_token`（`sub`/`org` 声明，:278-292）。
- **三套 token 解码**：`api/auth.py._decode_token`（:105-114）、`auth_extended.py._decode_token`（:294-300）、`api/middleware.py._decode_token`（:23-32）。
- **两套限流**：`api/auth.py._SIGNIN_RATE_LIMIT`（普通 dict，:51-53, :110-124）与 `auth_extended.py`（`_ThreadSafeDict`，W2 已加固）。
- **两套登录 handler**：`/api/v1/auth/login`（api/auth.py）与 `/api/auth/signin`（auth_extended.py）。

**收敛前提已具备**：`api/middleware.py:52-96`（P0-A）已同时接受两种 claims 格式（`user_id`/`org_id` 与 `sub`/`org`）；`get_session_user` 的身份解析以 DB session 行为准（claims 仅验签），故两格式签发的 token 在统一 verify 下行为一致。

### SHALL 条款

- **SHALL-A1.1（secret 单一来源）**: `YULEOSH_JWT_SECRET` 必须只有一份解读：以 `ui/auth_extended.py.JWT_SECRET`（或抽出的公共模块）为唯一来源，`api/auth.py`、`api/middleware.py`、`api/subscription.py`、`api/wizard.py` 一律 import，不得各自 `os.environ.get`；fail-fast 语义保持（未设置 env 即导入失败，SEC-W3 治理不回退）。
- **SHALL-A1.2（统一 verify）**: `api/middleware.py:require_auth` 的 token 校验必须调用与 ui 侧**同一** verify 函数（`auth_extended.get_session_user` 或抽出的公共 `verify_token`）；middleware 内独立的 `_decode_token` + Store 双查逻辑必须删除或退化为薄委托；对同一合法 token / 非法 token / 过期 token 的判定结果与 v3.7.0 必须一致。
- **SHALL-A1.3（统一签发）**: 服务端签发 JWT 必须只有一份 `_generate_token`（以 auth_extended 的 `sub`/`org` 格式为唯一格式）；`api/auth.py` 的 `user_id`/`org_id` 格式签发函数删除；新签发的 token 经统一 verify 与 `get_session_user` 均可解析出同一用户。
- **SHALL-A1.4（统一登录/注册/登出 handler）**: `api/auth.py:handle_auth`（register/login/me/logout）必须删除或委托 `auth_extended.py` 对应实现；`/api/v1/auth/*` 响应契约保持：`register`/`login` 返回 `{token, user:{id,email,role,org:{id,name,slug}}}`，`me` 返回 `{user:{...}}`，`logout` 返回 `{message: "Logged out successfully"}`（或等价 `{ok:true}`——以 v3.7.0 实测为准），错误码 400/401/409/429 语义不变。
- **SHALL-A1.5（统一密码哈希）**: bcrypt `_hash_password`/`_verify_password` 必须单一实现（同一模块），两处调用点引用同一函数；12 rounds 参数不变。
- **SHALL-A1.6（统一限流）**: `api/auth.py` 的普通 dict 限流必须删除；`/api/v1/auth/login` 与 `/api/auth/signin` 共用 `auth_extended` 的 `_ThreadSafeDict` 限流实现（10 次/5min email、30 次/5min IP、失败才计数语义保持）。
- **SHALL-A1.7（迁移顺序约束）**: 开发必须按"先 middleware、后 handler"顺序提交：① secret 单一来源（附项 F1 前置）→ ② middleware verify 统一 → ③ `/api/v1/auth/*` handler 委托 → ④ 删除 `api/auth.py` 重复实现；每步独立 commit、独立可回滚。
- **SHALL-A1.8（前端登录链兼容）**: 前端登录链全部端点请求/响应契约零变化：`POST /api/auth/signin`、`POST /api/org/create`、`GET /api/auth/session`、`GET /api/project/list`、`POST /api/project/create`、`POST /api/auth/logout`；Bearer token 在 `/api/v1/*`、legacy `/api/*`、页面会话三处均仍被接受（登录→建组织→选项目→进 dashboard 全链路可用）。
- **SHALL-A1.9（API key 与 session cookie 机制保留）**: `ui/auth.py` 的 X-API-Key（HMAC compare_digest）与 `osh_session` cookie 属**独立机制**（非 JWT 重复），必须保留；`is_authenticated` 的委托链（API key → cookie → Bearer→`get_session_user`）保持。
- **SHALL-A1.10（无随机兜底）**: 合并后全仓 grep 不得存在 `os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(...))` 类随机兜底（subscription/wizard 修复见 F1）。
- **SHOULD-A1.11（模块归属）**: 若抽出公共 auth 核心模块（如 `ui/auth_core.py` 或维持 auth_extended 为基），必须保持依赖方向清晰：`api/` 模块依赖 `ui.auth_extended` 既有事实已存在（preview.py），允许；但不得产生 `ui/` → `api/` 的顶层循环导入；方案二选一由小克定、小马确认，验收以行为为准。

**GIVEN/WHEN/THEN**

- GIVEN 环境变量 `YULEOSH_JWT_SECRET` 已设置，WHEN `api/auth.py` 与 `ui/auth_extended.py` 同时导入，THEN 两者使用同一 secret 值（`api._JWT_SECRET is auth_extended.JWT_SECRET` 或同源字符串）。
- GIVEN 前端经 `/api/auth/signin` 登录获得的 token，WHEN 该 token 访问任意 `@require_auth` 的 `/api/v1/*` 端点，THEN 200/业务响应（与 v3.7.0 一致，middleware 统一 verify 不 401）。
- GIVEN 经 `/api/v1/auth/login` 登录获得的 token，WHEN 该 token 访问 `GET /api/auth/session`，THEN 返回同一用户会话信息（双链互认）。
- GIVEN 无效/过期/伪造 token，WHEN 访问 `@require_auth` 端点与 legacy 端点，THEN 均 401（fail-closed，判定一致）。
- GIVEN `YULEOSH_JWT_SECRET` 未设置，WHEN 启动服务/导入认证模块，THEN 仍 fail-fast 抛 RuntimeError（SEC-W3 不回退）。
- GIVEN 前端完整登录链（signin → org/create → auth/session → project/list → dashboard），WHEN 在 A1 合并后执行，THEN 全链路成功且响应字段与 v3.7.0 逐字段一致。

---

## 2. A2 — 审计统一（来源 A-W-01 / Fix 14，估时 1.5d）

### 现状（grep 证据）

**三套审计并存**：

| # | 实现 | 存储 | 写入方 | 读取方 |
|---|------|------|--------|--------|
| ① | `ui/server.py:123-139` `_audit_log_ring`（内存 ring，上限 5000） | 内存（不落盘） | `ui/routes/handler_helpers.py:405` `log_audit`（全部 legacy UI 请求 do_GET/POST/DELETE finally） | **无**（全仓仅写入，写-only 死代码） |
| ② | `api/audit.py` `log_request` + `_ensure_table`（SQLite `audit_log` 表：timestamp/method/path/status_code/ip/duration_ms） | SQLite（持久） | `api/router.py:265` `_do_audit_log`（全部 `/api/v1/*` 请求） | `handle_audit`（GET `/api/v1/audit`，RBAC audit:view）+ `ui/pages/audit-dashboard.html:236` |
| ③ | `audit/model.py` `AuditLog`（JSONL，按天文件） | 文件（`data/audit/YYYY-MM-DD.jsonl`） | `ui/routes/audit_routes.py`（`handle_get_audit_logs`/`handle_post_audit_event`，**被 ROUTES["audit"] 遮蔽的死代码**） | 同左（死代码） |
| ⚠️ 附带 | `loop_engine/event_bus.py:702` 自有 `AuditLog` 类（内存 ring + `self._store.insert("audit_log", entry)`） | 内存 + 声称持久化 | `event_bus` 事件处理 | `audit_log()` / stats（:2193） |

**关键发现**：
- ring（①）无任何读取方 → 纯写死代码。
- `store` 无 `insert` 方法（全仓 grep `def insert` 无结果）→ `event_bus.AuditLog.record` 的持久化分支在配置了 store 时必然 `AttributeError`，被 `except Exception` 吞掉 → **静默失效死代码**。
- ③ 的 HTTP 路由被 `ROUTES["audit"] = handle_audit`（②的 DB 实现）遮蔽 → `/api/v1/audit` 实际由 DB 实现服务，JSONL 路由不可达。

### SHALL 条款

- **SHALL-A2.1（DB 为主）**: SQLite `audit_log` 表必须成为唯一持久审计存储；`log_audit`（legacy UI 请求）与 `_do_audit_log`（/api/v1/* 请求）必须收敛为同一写路径（统一 `log_request`），不得再有第二条持久写路径。
- **SHALL-A2.2（ring 降级 hot cache）**: `_audit_log_ring` 若保留，必须明确定位为 hot cache（内存最近 N 条、可清空、非持久、不得作为审计唯一记录）；若 A2 完成后仍无任何读取方，允许删除并在代码注释/本文档注明（验收以"无写-only 死代码"为准，二选一由小克定、小马确认）。
- **SHALL-A2.3（JSONL 移出 HTTP 路径）**: `ui/routes/audit_routes.py` 的 `handle_get_audit_logs`/`handle_post_audit_event` 必须删除或改造为 DB 读写；GET/POST `/api/v1/audit` 只能由 `api/audit.py` 统一服务（GET 查询 DB；POST 行为若保留须与 v3.7.0 语义对齐——v3.7.0 该 POST 为 405，保持即可，见 SHALL-A2.5）。
- **SHALL-A2.4（event_bus 审计持久化修复或移除）**: `loop_engine/event_bus.py` `AuditLog.record` 的 store 持久化分支必须修复（改走统一审计接口/表）或显式移除（仅内存 ring + 注释注明"不持久化"）；不得保留静默失效的 `self._store.insert` 调用。
- **SHALL-A2.5（audit API 契约保持）**: `GET /api/v1/audit` 响应结构 `{ok, data:{entries,count,total,limit,offset}}`、limit 上限 200、RBAC（admin/auditor 才可读，member 403）与 v3.7.0 完全一致；`POST /api/v1/audit` 保持 405（或按小明裁决提供 DB 事件写入，二选一，验收以契约文档为准）。
- **SHALL-A2.6（审计字段扩展，供 SAAS-4 语义）**: 若需承载事件语义（actor/tenant/action），统一表可加列（`actor`/`tenant` 可空），但**不得破坏**既有列与查询；JSONL `audit/model.py` 作为独立事件库（`tests/test_audit_model_unit.py` 覆盖）可保留为库形态，但不得再被 HTTP 路径调用。
- **SHALL-A2.7（无重复写入）**: 同一 HTTP 请求在全链路只能产生一条持久审计记录（不得 ring 一条 + DB 一条双写双算）。

**GIVEN/WHEN/THEN**

- GIVEN 一个 legacy UI 请求（如 GET `/api/evidence`）与一个 v1 API 请求（如 GET `/api/v1/health`），WHEN 各自处理完成，THEN 两者都写入同一 `audit_log` 表（统一 schema），且各恰好一条记录。
- GIVEN 审计表有数据，WHEN 调用 `GET /api/v1/audit?limit=10`（admin），THEN 返回 entries 含两类请求的记录（v3.7.0 只有 v1 请求记录，此为行为扩展点，需在小明确认后验收）。
- GIVEN `loop_engine` 配置了 store 并触发事件，WHEN `AuditLog.record` 执行，THEN 不再出现被吞掉的 AttributeError（持久化生效或显式移除，日志无 warning）。
- GIVEN ring 保留为 hot cache，WHEN 大量请求灌入超过上限，THEN 内存有界（≤上限）且 DB 记录完整不受影响。
- GIVEN 匿名/member 角色请求 `GET /api/v1/audit`，WHEN 鉴权+RBAC 判定，THEN 401/403（与 v3.7.0 一致）。

---

## 3. A3 — 路由去 legacy 双轨（来源 ARC-W1 / Fix 15，估时 1d）

### 现状（grep 证据）

**双轨结构**：
- `handler_helpers.handle_get`（:61-63）/`handle_post`（:305-307）第一分支 `if path.startswith("/api/v1/"): api_v1_dispatch(...)` 拦截**所有** `/api/v1/*` 请求 → 其后的 legacy elif 分支（`/api/v1/tenant/`、`/api/v1/tenants`、`/api/v1/projects/`、`/api/v1/audit`、`/api/v1/billing/*`，handle_get :216-292、handle_post :326-358）为**不可达死代码**。
- `api/router.py:66` `_dispatch_legacy`（tenant/tenants/billing/projects/audit 分支）为 `/api/v1/*` 资源未命中 ROUTES 时的**唯一可达** legacy 路径；其中 **audit 分支（`clean == "/api/v1/audit"`）被 `ROUTES["audit"] = handle_audit` 遮蔽**（死代码）。
- legacy handler 签名：`fn(handler, slug|path)`，直接写响应、自读 rfile（`handle_tenant_info` 等见 `tenant_routes.py:68`、`billing_routes.py:73`、`project_routes.py:112`）；新式 handler 签名：`fn(method, path_tail, body, query, handler) -> tuple`。

### SHALL 条款

- **SHALL-A3.1（tenant/billing/projects 迁移新式签名）**: `ui/routes/tenant_routes.py`、`billing_routes.py`、`project_routes.py` 中经 `_dispatch_legacy` 可达的全部 handler（tenant info/projects/usage/list、billing usage/plan/upgrade、projects get/create/update）必须迁移为新式签名并注册进 router（`ROUTES` 或 `_LAZY_HANDLERS`），资源名规划不得与既有 `project`（单数）冲突（建议：`tenant`/`billing`/`projects`，`projects` 为复数资源）。
- **SHALL-A3.2（删除 _dispatch_legacy）**: `api/router.py:_dispatch_legacy` 必须整体删除（含被遮蔽的 audit 分支），router 不得再有 legacy 委托路径。
- **SHALL-A3.3（删除 handler_helpers 死分支）**: `handle_get`/`handle_post` 中被 `api_v1_dispatch` 先行拦截的 legacy elif 分支必须删除；`/api/v1/*` 判定后不得再落到任何 legacy 分支。
- **SHALL-A3.4（响应契约保持）**: tenant/billing/projects 各端点 JSON 结构、状态码、错误语义与 v3.7.0 一致（tenant info/projects/usage/list、billing usage/plan/upgrade、projects get/create/update 的字段逐一对照）。
- **SHALL-A3.5（鉴权等价）**: 迁移后的新式 handler 鉴权（`require_auth` 或统一 verify）与旧式 `get_session_user` Bearer 鉴权对同一合法/非法 token 判定一致（同一 token 不会被一边接受一边拒绝）。
- **SHALL-A3.6（body 读取统一）**: 迁移后 handler 不得再自读 `rfile`；由 `router.dispatch` 的 `read_body` 统一读取（10MB 钳制 + BadRequest→400 语义保持）。
- **SHALL-A3.7（/api/v1/audit 单一路径）**: `/api/v1/audit` 仅由 `handle_audit` 服务；`_dispatch_legacy` 与 handler_helpers 中的 audit 分支全部消失。
- **SHALL-A3.8（无回归）**: 全部既有 `/api/v1/tenant|tenants|billing|projects|audit` 相关测试（`test_security.py`、`test_api_smoke.py`、`test_v344_p0ab_integration.py`、`test_ui_routes_ext.py` 等）全绿。

**GIVEN/WHEN/THEN**

- GIVEN GET `/api/v1/tenant/acme`（Bearer 合法 token），WHEN 请求到达 router，THEN 由新式 tenant handler 返回与 v3.7.0 相同的 JSON（字段/状态码一致），全程无 `_dispatch_legacy` 参与。
- GIVEN GET `/api/v1/audit`，WHEN 请求到达，THEN 由 `handle_audit`（DB）服务，返回 `{ok,data:{entries,...}}`（与 v3.7.0 一致）。
- GIVEN POST `/api/v1/billing/upgrade`（合法 body + token），WHEN 处理，THEN 响应与 v3.7.0 一致且 body 由 router 统一读取（超限 body → 400，不 500）。
- GIVEN 未知 `/api/v1/xxx` 资源，WHEN 请求到达，THEN 404 `{"ok":false,"error":"Unknown resource: xxx"}`（v3.7.0 语义保持，不再经 legacy 分支误判）。

---

## 4. A4 — Store 抽象补方法（来源 ARC-W3 / Fix 16，估时 1d）

### 现状（grep 证据）

`api/project.py` 与 `api/stats.py` 绕过 Store 接口直接 `store.conn.execute` 裸 SQL：
- `api/project.py:57` `SELECT * FROM projects ORDER BY created_at DESC`（list）
- `api/project.py:73` `UPDATE projects SET spec_path=? WHERE name=?`（create 后补 spec_path）
- `api/project.py:85-89` 5 张表 COUNT（pipelines/ci_runs/reviews/evidence/projects）→ `_project_stats`
- `api/stats.py:42-44` `SELECT COUNT(*) FROM ci_runs WHERE status='passed'`（ci_pass_rate）

`store_interface.py`（AbstractStore，49 方法）与 `store.py`（SQLite）、`store_pg.py`（Postgres，55 defs，接口已全实现）为三实现体系；project/stats 裸 SQL 使 PG 后端下这些端点行为未定义/不一致（`store.conn` 在 PG 后端不存在）。

### SHALL 条款

- **SHALL-A4.1（project 裸 SQL 消除）**: `api/project.py` 的全部 `conn.execute` 必须改走 Store 接口方法（新增 `list_projects()`、`update_project_spec_path(name, spec_path)`、`get_project_stats()` 或等价）；`api/project.py` 内不得残留 `conn.execute`。
- **SHALL-A4.2（stats 裸 SQL 消除）**: `api/stats.py` 的 ci_pass_rate 计数必须走 Store 方法（新增 `count_ci_passed()` 或扩展 `get_usage_stats()` 返回 `ci_pass_count`）；`api/stats.py` 内不得残留 `conn.execute`。
- **SHALL-A4.3（三实现同步）**: AbstractStore 新增方法必须同时实现于 `Store`（SQLite）与 `PostgresStore`（`store_pg.py`），接口签名与语义一致（PG 下 `test_store_pg_deep.py` 全绿）。
- **SHALL-A4.4（行为保持）**: 查询结果、排序（created_at DESC）、字段集合、空表行为与 v3.7.0 裸 SQL 完全一致（含 stats 各计数口径）。
- **SHALL-A4.5（接口完整性回归）**: 全仓 `src/yuleosh/api/*.py` 中 `conn.execute` 仅允许存在于明确豁免位置（如 audit 统一读写若走接口则同样收敛）；验收以 grep 计数为准。
- **MAY-A4.6**: `api/audit.py` 的 audit_log 读写若随 A2 统一，可顺带走 Store 方法（与 A2 合并实施，不单独验收）。

**GIVEN/WHEN/THEN**

- GIVEN Store 有 3 个 projects（含 spec_path 部分为空），WHEN `GET /api/v1/project`，THEN 返回与 v3.7.0 相同的列表（排序/字段一致），且实现不含 `conn.execute`。
- GIVEN 创建 project 时带 spec_path，WHEN `POST /api/v1/project`，THEN spec_path 正确落库（`update_project_spec_path` 生效）。
- GIVEN ci_runs 有 passed/failed 记录，WHEN `GET /api/v1/stats/overview`，THEN `ci_pass_rate` 计算与 v3.7.0 一致。
- GIVEN `StoreFactory` 返回 PostgresStore，WHEN 调用新增接口方法，THEN 行为与 SQLite 一致（不抛 AttributeError/接口缺失）。

---

## 5. A5 — cli/main.py 拆分命令组（来源 A-P2-01 / A-P2-05，估时 2d）

### 现状（grep 证据）

- `cli/main.py` **2873 行**；`_build_parser`（:2075-2482，约 408 行）单文件承载全部子命令定义。
- 待拆命令组（行号区间）：
  - **traceability**: `cmd_traceability_report`（:1070）/`cmd_traceability_export`（:1103）/`cmd_traceability_matrix`（:1136）→ 约 149 行
  - **misra**: `cmd_misra_deviate`（:1222）/`cmd_misra_trend`（:1422）/`cmd_misra_profile_list`（:1439）/`cmd_misra_profile_set`（:1492）/`cmd_misra_report`（:1533）+ 私有 helper（`_parse_dev_id`/`_cli_add_deviation`/`_interactive_add_deviation`/`_print_misra_report_summary`/`_render_misra_report_html`）→ 约 487 行
  - **swe6**: `cmd_swe6_status`（:1792）/`cmd_swe6_check`（:1853）→ 约 176 行
  - **review_diff**: `cmd_review_diff`（:1971）→ 约 102 行
- 先例：`cli/commands/` 已有 `init.py`/`template.py`（各 44 行，`__init__.py` re-export）。
- 测试 `sys.path.insert`：`pytest.ini` 已配 `pythonpath = src`；tests/ 下 **9 个 cli 测试 + 20+ 其他测试**仍显式 `sys.path.insert(0, .../src)`（`test_cli.py`/`test_cli_basic.py`/`test_cli_main_adv_unit.py`/`test_cli_main_cmds_unit.py`/`test_cli_smoke.py`/`test_cli_stats_deep.py`/`test_cli_template_deep.py`/`test_cli_commands_init_unit.py`/`test_cli_commands_template_unit.py` 等）。

### SHALL 条款

- **SHALL-A5.1（四命令组拆出）**: 新建 `cli/commands/{traceability,misra,swe6,review_diff}.py`，将上述命令函数与随组私有 helper 整体迁移；`cli/commands/__init__.py` re-export 新命令。
- **SHALL-A5.2（parser 跟随拆分）**: 各命令组子命令的 argparse 定义随组迁移（各模块导出 `build_parser(subparsers)` 或等价）；`cli/main.py:_build_parser` 只保留装配逻辑；命令名、参数、默认值、help 文案与 v3.7.0 完全一致。
- **SHALL-A5.3（行为零变化）**: 全部 CLI 命令的输出、退出码、异常路径与 v3.7.0 一致（130 CLI 测试全绿，含 `test_cli_main_adv_unit.py`/`test_cli_main_cmds_unit.py`/`test_cli.py` 等）。
- **SHALL-A5.4（sys.path.insert 清理）**: 确认 `pytest.ini` 的 `pythonpath = src` 在 CI 与本地均生效后，删除 tests/ 下全部冗余 `sys.path.insert`（A-P2-05）；删除后全量测试仍全绿（重点验证 conftest 缺失场景下的导入）。
- **SHALL-A5.5（循环导入防护）**: 命令模块不得在顶层导入 `cli/main.py`；`cli/main.py` 仅 import 命令模块的公开函数；`_build_parser` 保持单一入口。
- **SHALL-A5.6（共享工具不复制）**: 命令组间共享的 helper（如 `_ensure_tool_deps`、spec 解析、报告渲染工具）如被多组引用，必须抽到 `cli/commands/_common.py`（或既有公共位置），**不得**复制粘贴两份。
- **SHALL-A5.7（main.py 瘦身）**: 拆分后 `cli/main.py` 行数 ≤ 1200 行（目标验收线）；`cli/main.py` 自身运行时的 dev-mode `sys.path.insert`（:30-33）为 pip 安装兼容所需，**保留**（不属 A-P2-05 清理范围）。

**GIVEN/WHEN/THEN**

- GIVEN `yuleosh traceability report`、`yuleosh misra report`、`yuleosh swe6 check`、`yuleosh review-diff`（按 v3.7.0 命令名）分别执行，WHEN 拆分后运行，THEN 输出/退出码与 v3.7.0 逐字一致（除时间戳等固有动态内容）。
- GIVEN 删除某测试文件的 `sys.path.insert` 后运行该测试，WHEN pytest 从仓库根执行，THEN 导入正常（`pythonpath = src` 生效）。
- GIVEN `python -m pytest tests/test_cli_main_adv_unit.py -q`，WHEN 拆分后执行，THEN 全绿（无 import 断裂）。

---

## 6. A6 — dashboard/page.tsx 拆组件（来源 ARC-W5，估时 1d）

### 现状（grep 证据）

`frontend/src/app/dashboard/page.tsx` **1972 行**单体：
- 已内联组件：`MiniCoverageBar`（:196）、`SWECard`（:216）、`EvidenceModal`（:261）、`KnowledgeBaseTab`（:1323）、`MisraTrendsTab`（:1640）
- `DashboardPage` 主体（:363-1322）内含 overview tab（:790-1079，约 290 行）与 gap-analysis tab（:1080-1296，约 216 行）两大内联区块 + 状态编排（activeTab/selectedProject/API 调用）
- `frontend/src/components/` 目前仅 `ui/` 基础组件与 `github-icon.tsx`（无业务组件目录）

### SHALL 条款

- **SHALL-A6.1（拆出组件文件）**: 将 `OverviewTab`、`GapAnalysisTab`、`EvidenceModal`、`SWECard`、`MiniCoverageBar`、`KnowledgeBaseTab`、`MisraTrendsTab` 拆至 `frontend/src/components/dashboard/`（或等价目录）；`page.tsx` 只保留 `DashboardPage` 状态编排与 tab 装配。
- **SHALL-A6.2（状态接口化）**: 子组件通过 props 接收数据与回调（如 `onLoadMore`/`onFilter`/`onExport`/`onSelectProject`）；**不得**把 `page.tsx` 的 API 调用/状态复制进子组件（数据流单向）。
- **SHALL-A6.3（行为零变化）**: 渲染输出、交互行为、样式与 v3.7.0 完全一致（props 语义逐一对应）；前端 build（`next build` 或等价）通过，TS 类型检查（`tsc --noEmit`）零错误。
- **SHALL-A6.4（不复制逻辑）**: 拆分后每个功能逻辑（fetch、过滤、分页、导出、markdown 渲染）全仓仅一份实现。
- **SHALL-A6.5（行数验收线）**: 拆分后 `page.tsx` ≤ 600 行（目标），或拆出 ≥4 个业务组件文件且每文件职责单一。
- **SHALL-A6.6（既有前端测试保持）**: 前端既有测试（如 `frontend/` 下 vitest/jest 用例）全绿；若项目依赖 GitHub Pages 静态产物，本版前端产物**不强制重建**（v3.8.0 以源码结构验收为主，产物重建由小明裁决）。
- **SHALL-A6.7（不引入新依赖）**: 拆分不得新增 npm 依赖、不得改公共组件库（`components/ui/*`）接口。

**GIVEN/WHEN/THEN**

- GIVEN 打开 dashboard 页，WHEN 切到 overview / gap-analysis / knowledge-base / misra-trends 四个 tab，THEN 渲染与交互与 v3.7.0 一致（无控制台报错）。
- GIVEN `npm run build`（或项目等价命令），WHEN 拆分后执行，THEN 构建成功、类型检查零错误。
- GIVEN grep `page.tsx` 内重复的 fetch/state 定义，WHEN 拆分后检查，THEN 无重复逻辑（每逻辑单份）。

---

## 7. 附项（v3.7.0 遗留收尾，F1-F4）

### F1 — subscription/wizard 随机 secret 单一来源（v3.7.0 遗留 3，随 A1 前置）

**现状**（grep 证据）：`api/subscription.py:60` 与 `api/wizard.py:21` 均 `os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))` —— 每次调用生成**新随机值**，跨调用验签必然失败（既有行为 bug，非本版引入；认证收敛后暴露面扩大，必须修）。

- **SHALL-F1.1**: `api/subscription.py` 与 `api/wizard.py` 的 JWT secret 必须改为 import 统一来源（`auth_extended.JWT_SECRET` 或 A1 统一模块），删除随机兜底。
- **SHALL-F1.2**: 修改后两模块对合法 token 的验签跨调用稳定成功（同 token 多次解码结果一致）；非法/过期 token 仍拒绝。
- **SHALL-F1.3**: `YULEOSH_JWT_SECRET` 未设置时两模块随认证模块导入失败（fail-fast，不静默随机兜底）。

**GIVEN/WHEN/THEN**

- GIVEN `subscription._get_authenticated_org` 与 `wizard._get_org_id_from_handler`，WHEN 同一 token 先后调用两次，THEN 两次结果一致（不再因随机 secret 首次失败）。
- GIVEN `YULEOSH_JWT_SECRET` 未设置，WHEN import 相关模块，THEN 抛 RuntimeError（非静默降级）。

### F2 — preview 匿名 user_key 换 user_id（v3.7.0 遗留 2，A1 后可行）

**现状**（grep 证据）：`api/preview.py:510-547` `_get_user_key` —— 已登录 `u:<user_id>` / API key `k:<key_id>` / 匿名 `ip:<sha256(ip)>`（NAT 同 IP 互见，已知限制，注释明确"fixed properly by Track2 auth consolidation"）。

- **SHALL-F2.1**: A1 认证收敛后，凡携带合法 JWT 的请求（生产默认全量）user_key 必须为 `u:<user_id>`，匿名 `ip:` 分支仅保留给 `YULEOSH_AUTH_DISABLED=1` dev 模式。
- **SHALL-F2.2**: 同一用户跨端点（/api/auth/session、/api/v1/*）解析出的 user_id 一致，user_key 确定（可复现）。
- **SHALL-F2.3**: dev 模式下匿名分支行为与 v3.7.0 一致（同 IP 命中自己的缓存），并保留注释说明 NAT 限制与弃用条件。
- **SHALL-F2.4**: 既有 W6 隔离语义不回退：跨用户永不命中（T-W6-01/06 保持全绿）。

**GIVEN/WHEN/THEN**

- GIVEN 用户 A 登录态提交 preview，WHEN 检查 `_repo_cache` 键，THEN 键含 `u:<A的user_id>`（非 ip 维度）。
- GIVEN dev 模式（AUTH_DISABLED=1）匿名请求，WHEN 两次同 URL 提交，THEN 命中同 IP 缓存（v3.7.0 行为保持）。

### F3 — do_POST/do_DELETE 审计 _response_status 修复（v3.7.0 遗留 3）

**现状**（grep 证据）：`ui/server.py` —— `do_GET` 异常分支已设 `self._response_status = 500`（:408，W1 修复）；`do_POST`（:420-424）与 `do_DELETE`（:433-437）的 except 分支**未设 500**，`finally` 中 `getattr(self, "_response_status", 200)` 回落 200 → 异常请求被审计为 200（假成功记录）。

- **SHALL-F3.1**: `do_POST` 与 `do_DELETE` 的异常分支必须设置 `self._response_status = 500`（与 do_GET 对齐）。
- **SHALL-F3.2**: 异常请求的审计记录状态码必须为 500（非 200）；正常请求审计状态码不变。

**GIVEN/WHEN/THEN**

- GIVEN 注入 `handle_post` 抛异常（POST `/api/xxx`），WHEN 请求结束，THEN 响应 500 且审计记录 status=500。
- GIVEN 注入 `handle_delete` 抛异常，WHEN 请求结束，THEN 同上。

### F4 — _serve_file 页面路径补 Cache-Control（v3.7.0 遗留 2）

**现状**（grep 证据）：`ui/server.py:446-457` `_serve_file` 无任何 Cache-Control（M2 只覆盖了 `_serve_static`）；`_serve_file` 服务于 marketing/pages 的 HTML 模板（`/dashboard`、`/pricing`、`/billing` 等页面路径）与 404 兜底。

- **SHALL-F4.1**: `_serve_file` 对 `.html`（及等价模板）响应必须带 `Cache-Control: no-cache`（对齐 `_serve_static` 的 M2 HTML 语义）。
- **SHALL-F4.2**: `_serve_file` 非 HTML 内容（若存在）不得误加 immutable；无 hash 资源遵循 M2 既有规则（短 max-age 或不加）。
- **SHALL-F4.3**: 缓存头改动不得影响 404 兜底、Content-Type 与安全头（`_add_security_headers` 保持）。

**GIVEN/WHEN/THEN**

- GIVEN GET `/dashboard`（走 `_serve_file` 服务 dashboard-v5.html），WHEN 响应，THEN 含 `Cache-Control: no-cache`。
- GIVEN GET `/pricing`，WHEN 响应，THEN 含 `Cache-Control: no-cache`（v3.7.0 无缓存头 → 本版补上，行为变化仅 HTTP 头）。

---

## 8. 全局约束（适用全部 A/F 项）

- **SHALL-G.1**: 所有行为变更项（A1 认证、A2 审计、A3 路由、F1 验签、F3 审计状态码）必须附带正例 + 负例测试，测试 ID 见 acceptance-matrix.md。
- **SHALL-G.2**: 全量回归基线（v3.7.0）**9873 passed / 0 failed** 不得下降（新增测试只增不减）；覆盖率 ≥ **84.10%** 不降。
- **SHALL-G.3**: 不引入新依赖（标准库优先；前端拆分不新增 npm 依赖）；不修改 frontend/ 构建产物（除非小明裁决重建）。
- **SHALL-G.4**: 每项修复的代码须注明来源（`A-x`/`F-x` 注释），与既有 `W-x`/`M-x`/`P1-x` 注释风格一致。
- **SHALL-G.5**: 变更不得破坏公开 API 契约：`/api/v1/*` 响应结构、错误码语义、CLI 子命令名与退出码、既有测试全部保持。
- **SHOULD-G.6**: 小克开发过程中对 spec 有歧义处先问小马，不得自行扩大范围（尤其 A1 公共模块归属、A2 ring 去留、A2 POST /api/v1/audit 行为、A6 前端产物是否重建，需先与上游确认）。
- **SHALL-G.7（依赖顺序）**: A1 先于 F1/F2（F1 是 A1 前置子步骤）；A2 与 A3 相互独立可并行；A4 依赖 A2 的 audit 收敛可合并实施；A5/A6 纯结构拆分可并行；每批后跑局部回归（见 acceptance-matrix 回归清单），收尾全量回归。

## 9. 明确不在本版范围（防范围蔓延）

- Track3 前端安全（T1 token cookie 迁移、T2 CSP）→ v3.9.0
- W2 限流多 worker 共享存储（S-P2-02，既有 NOTE）→ 非本版
- yuleASR-Configurator 安全项 → 另行排期
- COR-W4 preview zip 解压二次校验（suggestion）→ 可选跟进
- N+1 查询、KB dedup 等既有已修项 → 不在范围
