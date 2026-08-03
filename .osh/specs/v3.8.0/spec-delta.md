# Spec-Delta — yuleOSH v3.8.0 变更点分析

> 版本: v3.8.0 · 基线: v3.7.0 (2e0eef5) · 日期: 2026-08-03
> 用途: 小克开发变更清单 + 小马复验对照 + 老板风险知情
> 行号: HEAD=2e0eef5 实测（部分与评审报告行号有偏移，以实测为准）
> ⚠️ 本版为架构收敛版，A1 认证合一改动面最大 —— 第 6 节给出详细迁移步骤与回滚方案。

---

## 0. 变更总览

| ID | 变更文件 | 行为变化 | 兼容性影响 | 风险等级 |
|----|----------|----------|-----------|---------|
| A1 | `api/middleware.py` / `api/auth.py` / `ui/auth_extended.py` / `api/subscription.py` / `api/wizard.py` | 认证三套合一：secret/verify/签发/哈希/限流/handler 单一来源 | **高（JWT 双格式、前端登录链、15 个 require_auth handler）** | 🔴 高 |
| A2 | `ui/server.py` / `ui/routes/handler_helpers.py` / `api/audit.py` / `ui/routes/audit_routes.py` / `loop_engine/event_bus.py` | 审计三套合一：DB 为主、ring 降级 hot cache、JSONL 移出 HTTP | 中（audit API 契约保持） | 🟠 高 |
| A3 | `api/router.py` / `ui/routes/{tenant,billing,project}_routes.py` / `ui/routes/handler_helpers.py` | 路由去双轨：legacy handler 迁移新式签名、删 `_dispatch_legacy` 与死分支 | 中（响应契约必须保持） | 🟠 高 |
| A4 | `api/project.py` / `api/stats.py` / `store_interface.py` / `store.py` / `store_pg.py` | Store 抽象补方法，消除裸 SQL | 中（三实现同步） | 🟡 中 |
| A5 | `cli/main.py` / `cli/commands/{traceability,misra,swe6,review_diff}.py` / tests/* | CLI 命令组拆分 + sys.path.insert 清理 | 低（行为零变化） | 🟡 中 |
| A6 | `frontend/src/app/dashboard/page.tsx` / `frontend/src/components/dashboard/*` | 拆组件 | 低（行为零变化） | 🟢 低 |
| F1 | `api/subscription.py:60` / `api/wizard.py:21` | 随机 secret 兜底 → 单一来源 | 中（修复跨调用验签失败 bug） | 🟡 中 |
| F2 | `api/preview.py:510-547` | 匿名 user_key → 登录 user_id | 低（dev 模式保留 ip 分支） | 🟢 低 |
| F3 | `ui/server.py`（do_POST/do_DELETE） | 异常审计状态码 200→500 | 低（仅异常路径） | 🟢 低 |
| F4 | `ui/server.py`（_serve_file） | 页面 HTML 补 no-cache | 低（仅 HTTP 头） | 🟢 低 |

---

## 1. A1 — 认证三套合一（🔴 最高风险）

### 1.1 现状三套调用点清单（grep 证据，HEAD=2e0eef5）

**① `ui/auth.py`（legacy API key + session cookie）— 保留（独立机制）**
- 定义：`API_KEY`(:22)、`AUTH_ENABLED`(:30-31)、`_sessions`/`_generate_session_token`/`_session_sig`/`create_session`/`validate_session`/`cleanup_sessions`/`is_authenticated`(:178-219)
- 调用点：`ui/server.py:73`（模块级 import AUTH_ENABLED）、`ui/server.py:343`（`_check_auth` 内 `is_authenticated`）、`ui/routes/api_routes.py:40`（health 内 AUTH_ENABLED，ImportError fallback 注释已说明非第三语义）、`ui/routes/auth_routes.py:20,59`（`handle_auth_check`/`handle_auth_login`）、`api/health.py:125`（`_auth_enabled()`）
- **A1 处置：保留机制本身**；`is_authenticated` 的 Bearer 委托链（:214-217 → auth_extended.get_session_user）保持。

**② `ui/auth_extended.py`（前端租户 JWT）— 定为基座**
- 定义：`JWT_SECRET`(:40-42，fail-fast)、`JWT_ALGORITHM`(:43)、`_hash_password`/`_verify_password`(:263-270)、`_generate_token`(:278-292，`sub`/`org` 声明)、`_decode_token`(:294-300)、`get_session_user`(:311-336)、`handle_signin`/`handle_org_create`/`handle_session_info`/`handle_logout`/`handle_project_list`/`handle_project_create`/`handle_org_info`、`_ThreadSafeDict` 限流（:85-190）
- 调用点：`ui/auth.py:215`、`ui/routes/auth_routes.py:94`（handle_api_action 7 动作）、`ui/routes/audit_routes.py:31`、`ui/routes/tenant_routes.py:17`、`ui/routes/billing_routes.py:32`、`ui/routes/api_routes.py:44,145`、`ui/routes/project_routes.py:43`、`rbac/model.py:32`、`api/preview.py:498,528`
- **A1 处置：基座**。所有 JWT 签发/校验/登录 handler 以本模块为准。

**③ `api/auth.py` + `api/middleware.py`（v1 API JWT）— 收敛对象**
- `api/auth.py` 定义：`_JWT_SECRET`(:38-40，fail-fast)、`_hash_password`/`_verify_password`(:72-89)、`_generate_token`(:92-103，`user_id`/`org_id` 声明)、`_decode_token`(:105-114)、`_check_rate_limit`(:110-124，普通 dict)、`handle_auth`(:143-168)、`_handle_register`/`_handle_login`/`_handle_me`/`_handle_logout`(:170-365)
- `api/middleware.py` 定义：`_JWT_SECRET` import(:17)、`_decode_token`(:23-32)、`_extract_token`(:34-47)、`require_auth`(:50-117，P0-A 双格式兼容)
- `require_auth` 装饰 15 个 handler：apikeys/audit/ci/compliance/dashboard/evidence/kb/kg/notify/pipeline/project/review/spec/stats（+middleware 自身文档）
- **A1 处置：全部收敛**到 ②。

### 1.2 文件级变更清单

| 文件 | 变更 | 删除/新增 |
|------|------|-----------|
| `src/yuleosh/api/middleware.py` | `require_auth` 内 `_decode_token`+Store 双查改为调用统一 verify（`auth_extended.get_session_user` 或公共 `verify_token`）；`current_user` 注入字段保持 `{user_id, org_id, email, role}` | 删 `_decode_token`（或薄委托）；`_JWT_SECRET`/`_JWT_ALGORITHM` 改 import 统一来源 |
| `src/yuleosh/api/auth.py` | `handle_auth` 委托 `auth_extended` 对应实现；`_hash_password`/`_verify_password`/`_generate_token`/`_decode_token`/`_check_rate_limit`/`_SIGNIN_RATE_LIMIT` 删除 | 大删；`handle_auth` 保留为路由适配层（响应契约转换）或删除后 router 改指 auth_extended 适配 |
| `src/yuleosh/ui/auth_extended.py` | 增加统一导出（如 `verify_token`/`authenticate` 供 middleware 使用）；必要时补 `register` 统一实现（v1 register 语义：org+user+token） | 少量新增 |
| `src/yuleosh/api/subscription.py:60` | `os.environ.get(..., secrets.token_urlsafe(32))` → import 统一 secret | 删随机兜底（F1） |
| `src/yuleosh/api/wizard.py:21` | 同上（F1） | 删随机兜底 |

### 1.3 行为变化

1. **`/api/v1/auth/*` 与 `/api/auth/*` 双链互认**（token 互换可用）—— v3.7.0 已部分成立（P0-A middleware 双格式），本版把"巧合兼容"固化为"单一实现"。
2. **限流表合并**：`/api/v1/auth/login` 与 `/api/auth/signin` 将共享同一 email 失败计数（同一邮箱跨两端共 10 次/5min）。v3.7.0 是两套独立计数（各 10 次）。**这是行为收紧**，防爆破更严，但需在验收矩阵注明（T-A1-08-neg 覆盖）。
3. **随机 secret 兜底消失**（F1）：subscription/wizard 验签从"每次新 secret → 必然失败"变为"稳定成功"。**这是 bug 修复**，v3.7.0 下依赖该端点的功能实际不可用（跨调用验签必失败），本版使其可用。
4. JWT 签发 claims 统一为 `sub`/`org`：依赖 `user_id`/`org_id` 声明直读的下游（middleware 已兼容两种；subscription/wizard 已 `or` 兼容）无感知。

### 1.4 兼容性影响（按调用方）

| 调用方 | 影响 |
|--------|------|
| 前端登录链（signin/org/session/project） | 零变化（端点/字段不变；见 1.6 验证方案） |
| 15 个 `@require_auth` handler | `current_user` 注入字段不变；鉴权判定对同一 token 不变 |
| API 客户端用 `/api/v1/auth/login` | 响应结构不变；限流更严（共享计数） |
| subscription/wizard 端点 | **从"必然验签失败"变为"可用"**（修复） |
| RBAC（check_role） | 不变（仍消费 get_session_user 输出） |
| 测试套件 | `test_api_auth_*.py`/`test_auth_extended*.py`/`test_jwt_auth.py`/`test_security.py` 需全绿；限流合并相关用例需适配 |

### 1.5 迁移步骤（开发顺序，先 middleware 后 handler，每步独立 commit）

> 每步完成后跑局部回归：`tests/test_api_auth_deep.py tests/test_api_auth_coverage.py tests/test_auth_extended.py tests/test_auth_extended_handlers.py tests/test_jwt_auth.py tests/test_security.py tests/test_ui_server_deep.py -q`

- **Step 0（前置，F1）**：subscription.py/wizard.py secret 改 import 统一来源。回归：subscription/wizard 相关测试 + 新增跨调用验签用例。
- **Step 1（secret 单一来源）**：`api/middleware.py` 的 `_JWT_SECRET` import 改为统一来源（`auth_extended.JWT_SECRET`）；`api/auth.py` 同改。行为无变化（同一 env 值）。回归：全部 auth 测试。
- **Step 2（middleware verify 统一）**：`require_auth` 内部改用 `get_session_user`（或公共 `verify_token`）替换自研 `_decode_token`+Store 双查；`current_user` 组装逻辑保留。**本步是行为风险最大单点**——15 个 handler 的鉴权路径全部经过这里。回归：`test_security.py`（含负例）+ 全部 require_auth 相关测试 + 前端登录链手工验证。
- **Step 3（handler 委托）**：`api/auth.py` 的 `handle_auth` 四个子端点改为委托 `auth_extended` 统一实现（login→signin 同语义、register→统一注册、me→get_session_user、logout→handle_logout），响应结构在适配层转换（v1 契约 `{token, user:{id,email,role,org}}`）。回归：`test_api_auth_*.py` + `test_onboarding_e2e.py` 相关链。
- **Step 4（删除重复实现）**：删除 `api/auth.py` 的 `_hash_password`/`_verify_password`/`_generate_token`/`_decode_token`/`_check_rate_limit`/`_SIGNIN_RATE_LIMIT`；确认全仓无残留引用。回归：全量。
- **Step 5（收尾验证）**：全量回归 9873+/0 + 覆盖率 ≥84.10% + 前端登录链 E2E。

### 1.6 前端登录链兼容验证方案

1. **自动化**：新增/保持端到端用例（`test_onboarding_e2e.py` 系）：`POST /api/auth/signin`（新用户建 org）→ `POST /api/org/create` → `GET /api/auth/session`（断言 user_id/org_id/email/role/projects）→ `GET /api/project/list` → dashboard 数据端点（任一 `@require_auth`，如 `GET /api/v1/stats/overview`）返回 200。
2. **交叉验证**：用 `/api/auth/signin` 的 token 调 `/api/v1/auth/me`（200 且同一 user）；用 `/api/v1/auth/login` 的 token 调 `/api/auth/session`（200 且同一 user）。
3. **负例**：篡改/过期 token 在两端均 401；无 token 在 `@require_auth` 端点 401（fail-closed）。
4. **手工**（小马复验）：浏览器登录 → 建组织 → 选项目 → dashboard 数据加载；刷新后 session 保持（token 仍有效）。

### 1.7 回滚方案

| 步骤 | 回滚方式 | 影响面 |
|------|----------|--------|
| Step 1 | revert commit（secret 值不变，纯 import 重构） | 零（无行为差异） |
| Step 2 | revert commit → middleware 恢复自研 verify（P0-A 双格式兼容仍在，功能不回退） | 前端/API 均无感知 |
| Step 3 | revert commit → handle_auth 恢复自研实现（v3.7.0 原状） | 无感知 |
| Step 4 | revert commit（重新引入重复实现） | 无感知（回到 v3.7.0 三套并存，功能可用） |

- 总体：**每步可独立 revert**；任何一步回归失败即回退该步，不连带后续步骤。
- 风险兜底：Step 2 前先打 tag（如 `v3.8.0-a1-step2-before`），便于快速 diff。

---

## 2. A2 — 审计统一（🟠 高）

### 2.1 现状三套（grep 证据）

| # | 位置 | 存储 | 状态 |
|---|------|------|------|
| ① | `ui/server.py:123-139`（`_audit_log_ring`/`_audit_log`）+ `handler_helpers.py:405-416`（`log_audit`） | 内存 ring（5000 上限） | **写-only**（全仓无读取方） |
| ② | `api/audit.py:22-43`（`log_request`/`_ensure_table`）+ `api/router.py:260-275`（`_do_audit_log`） | SQLite `audit_log` 表 | 主路径（/api/v1/*） |
| ③ | `audit/model.py`（`AuditLog` JSONL）+ `ui/routes/audit_routes.py:77,133` | 文件 JSONL | **HTTP 路由被 ROUTES["audit"] 遮蔽**（死代码） |
| 附带 | `loop_engine/event_bus.py:702-756`（自有 `AuditLog`） | 内存 + `self._store.insert("audit_log", ...)` | **持久化死代码**（`store` 无 `insert` 方法 → AttributeError 被吞） |

### 2.2 文件级变更清单

| 文件 | 变更 |
|------|------|
| `src/yuleosh/ui/routes/handler_helpers.py`（log_audit :405-416） | `_s._audit_log(...)` 改为调用统一 `log_request`（写 DB）；ring 写入降级为 hot cache 写入或删除（待裁决） |
| `src/yuleosh/api/audit.py` | 保持 DB 主路径；`_ensure_table` 可扩展 `actor`/`tenant` 列（可空）；导出统一 `log_request` |
| `src/yuleosh/ui/server.py`（:121-139） | ring 定位注释更新（hot cache）或删除（二选一，需小明确认） |
| `src/yuleosh/ui/routes/audit_routes.py` | 删除（死代码）或改造为薄适配（二选一，推荐删除，handle_audit 已覆盖 GET；POST 契约见 spec） |
| `src/yuleosh/loop_engine/event_bus.py`（:754,876） | `self._store.insert("audit_log", entry)` 修复（走统一接口）或删除持久化分支（仅内存+注释） |
| `src/yuleosh/audit/model.py` | 保留为独立事件库（`tests/test_audit_model_unit.py` 覆盖），不再被 HTTP 调用 |

### 2.3 行为变化与兼容性

- **行为变化**：legacy UI 请求（/api/evidence 等）首次进入持久审计（v3.7.0 只在内存 ring）。`GET /api/v1/audit` 将能看到 legacy 请求记录（**数据面扩展**，需小明确认是否可接受；如不可接受，可只记录 /api/v1/* + 页面请求，验收口径二选一）。
- **兼容**：`GET /api/v1/audit` 响应结构/RBAC/limit 上限不变；audit-dashboard.html 无需改动。
- **风险**：① legacy 请求量可能远大于 v1（页面资源请求若纳入会膨胀表）—— 建议仅记录 API 类路径（`/api/` 前缀）或全量记录但加表索引，由小克按流量评估并记录决策；② event_bus 持久化修复若走统一 audit_log 表，schema 冲突（event_id 等列 vs 请求列）需设计（可另建 `loop_audit_log` 表或事件 JSON 入 detail 列）—— **需小明确认**。

---

## 3. A3 — 路由去 legacy 双轨（🟠 高）

### 3.1 现状（grep 证据）

- **可达 legacy 路径**：`api/router.py:248` → `_dispatch_legacy`（:66-155）—— tenant(:74-99)/tenants(:102-110)/billing(:113-127)/projects(:130-143)/audit(:146-153)。
- **audit 分支被遮蔽**：`ROUTES["audit"] = handle_audit`（:115）→ `/api/v1/audit` 永远走新式，`_dispatch_legacy` 的 audit 分支不可达（死代码，巧合正确）。
- **handler_helpers 死分支**：handle_get（:216-292）、handle_post（:326-358）中 `/api/v1/tenant/`、`/api/v1/tenants`、`/api/v1/projects`、`/api/v1/audit`、`/api/v1/billing/*` 分支被 :61-63/:305-307 的 `api_v1_dispatch` 先行拦截 → 不可达。
- **legacy 签名**：`fn(handler, slug|path)` 直接写响应、自读 rfile（tenant_routes.py:68+ / billing_routes.py:73+ / project_routes.py:112+）。

### 3.2 文件级变更清单

| 文件 | 变更 |
|------|------|
| `src/yuleosh/api/router.py` | 删 `_dispatch_legacy`（:66-155）与其调用（:248）；ROUTES/_LAZY_HANDLERS 注册新资源：`tenant`/`tenants`(可并入 tenant 的 path_tail)/`billing`/`projects`（复数，勿与 `project` 冲突）；资源名与 path_tail 解析规则写注释 |
| `src/yuleosh/ui/routes/tenant_routes.py` | handler 迁移新式签名（`fn(method, path_tail, body, query, handler) -> tuple`）；响应字段不变；鉴权用统一 verify |
| `src/yuleosh/ui/routes/billing_routes.py` | 同上（usage/plan/upgrade） |
| `src/yuleosh/ui/routes/project_routes.py` | 同上（get/create/update） |
| `src/yuleosh/ui/routes/handler_helpers.py` | 删 handle_get/handle_post 中 `/api/v1/tenant|tenants|projects|audit|billing` 死分支（:216-292 中相关 elif 与 :326-358 相关 if） |
| `src/yuleosh/ui/routes/audit_routes.py` | 与 A2 合并处置（推荐删除） |

### 3.3 行为变化与兼容性

- **行为变化**：内部路由机制变化（legacy 委托 → 新式注册）；对外响应零变化（SHALL-A3.4）。
- **风险点**：① body 读取语义 —— legacy 自读 rfile，新式由 router `read_body` 统一读（POST billing/upgrade、projects create/update 的 body 解析需核对字段名）；② 鉴权等价性 —— legacy 用 `get_session_user`（:17,29 等），新式 `require_auth` 用统一 verify（A1 后同源）；③ path_tail 解析 —— `/api/v1/tenant/{slug}/projects` 在 new-style 下 resource="tenant"、path_tail="acme/projects"，需自定义解析，**易错点**，验收矩阵需逐端点对照。
- **兼容**：`/api/v1/project`（单数，新式已有）与 `/api/v1/projects`（复数，迁移后）并存不冲突。

---

## 4. A4 — Store 抽象补方法（🟡 中）

### 4.1 文件级变更清单

| 文件 | 变更 |
|------|------|
| `src/yuleosh/store_interface.py` | AbstractStore 新增：`list_projects()`、`update_project_spec_path(name, spec_path)`、`get_project_stats()`（或拆分计数方法）、`count_ci_passed()`（或并入 get_usage_stats） |
| `src/yuleosh/store.py` | 同步实现 4 方法（SQLite） |
| `src/yuleosh/store_pg.py` | 同步实现 4 方法（Postgres，`:55` defs 基础上追加） |
| `src/yuleosh/api/project.py` | :57/:73/:85-89 裸 SQL → 接口调用 |
| `src/yuleosh/api/stats.py` | :42-44 裸 SQL → 接口调用 |

### 4.2 行为变化与兼容性

- 行为零变化（查询口径、排序、字段与裸 SQL 一致）。
- 风险：PostgresStore 若漏实现 → 运行时 AttributeError/NotImplementedError；验收以 `test_store_pg_deep.py` + 新增三实现一致性测试兜底。

---

## 5. A5 / A6 — 结构拆分（🟡 中 / 🟢 低）

### 5.1 A5 cli/main.py 拆分

- 新建 4 文件：`cli/commands/{traceability,misra,swe6,review_diff}.py`（参照既有 `commands/init.py`/`template.py` 44 行小模块风格，但允许更大）。
- 迁移内容（main.py 行号）：traceability 组（:1070-1218 含 3 命令 + 私有 helper）；misra 组（:1222-1708 含 5 命令 + `_parse_dev_id`/`_cli_add_deviation`/`_interactive_add_deviation`/`_print_misra_report_summary`/`_render_misra_report_html`）；swe6 组（:1789-1967 含 2 命令）；review_diff 组（:1971-2072）。
- parser：各模块导出 `build_parser(subparsers)`；main.py `_build_parser` 装配（:2075-2482 相应段落迁走）。
- sys.path.insert 清理：tests/ 下 9 个 cli 测试 + 其他 20+ 文件的 `sys.path.insert` 删除（前提：CI 与本地均确认 `pytest.ini pythonpath = src` 生效；删除后跑全量验证）。
- 风险：① CLI 测试直接 import `yuleosh.cli.main` 内部函数（如 `_build_parser`/`cmd_*`）—— 迁移后测试 import 路径需同步（保持 `from yuleosh.cli.main import ...` 兼容层或更新测试，**需小克评估测试改动面**）；② main.py 自身 dev-mode sys.path.insert 保留。

### 5.2 A6 dashboard/page.tsx 拆分

- 新建 `frontend/src/components/dashboard/`：`overview-tab.tsx`、`gap-analysis-tab.tsx`、`evidence-modal.tsx`、`swe-card.tsx`、`mini-coverage-bar.tsx`、`knowledge-base-tab.tsx`、`misra-trends-tab.tsx`（名称小克可调）。
- page.tsx 保留：状态（activeTab/selectedProject/数据 fetch）、tab 装配、props 下发。
- 风险：props 边界设计错 → 行为漂移；验收以 `npm run build`/`tsc --noEmit` + 四 tab 手工验证兜底。前端产物不强制重建（SHALL-A6.6）。

---

## 6. 兼容性影响汇总表（按调用方）

| 调用方 | 受影响项 | 影响 |
|--------|----------|------|
| 前端 SPA（登录链） | A1, F2 | 端点/字段零变化；token 双链互认；preview 缓存键更精准 |
| API 客户端（/api/v1/*） | A1, A2, A3 | token 验签同源；限流共享计数（更严）；审计含 legacy 请求（数据面扩展）；tenant/billing/projects 响应零变化 |
| subscription/wizard 用户 | F1 | **从必失败变为可用**（bug 修复） |
| audit-dashboard 页面 | A2 | 读取路径不变（/api/v1/audit → DB） |
| loop_engine 使用者 | A2 | 审计持久化修复或显式移除（消除静默失效） |
| CLI 用户/脚本 | A5 | 命令名/输出/退出码零变化 |
| 前端开发者 | A6 | 组件化；page.tsx 瘦身；产物不强制重建 |
| 运维（部署） | A1 | 无部署变化（YULEOSH_JWT_SECRET 仍必填，fail-fast） |
| DB 既有数据 | A2 | audit_log 表加列（可空）不迁移数据；JSONL 数据文件保留不动 |
| 测试套件 | A1 最甚 | 限流合并用例适配；CLI 测试 import 路径可能更新；其余全绿 |

---

## 7. 附录 A：A1 认证调用点 grep 证据（复验用原始命令）

```bash
# 三套并存证据
grep -rn "from yuleosh.ui.auth import\|from yuleosh.ui.auth_extended import\|from yuleosh.api.auth import\|from .auth import" src/yuleosh/ --include="*.py"

# require_auth 覆盖面
grep -rln "require_auth" src/yuleosh/api/*.py

# get_session_user 调用面
grep -rn "get_session_user" src/yuleosh/ --include="*.py" | grep -v __pycache__ | grep -v "def get_session_user"

# JWT secret 读取点（A1/F1 消灭对象）
grep -rn "YULEOSH_JWT_SECRET" src/yuleosh/ --include="*.py" | grep -v __pycache__
# → api/auth.py:38, ui/auth_extended.py:40, api/subscription.py:60, api/wizard.py:21

# 随机兜底残留（合并后应为空）
grep -rn "token_urlsafe(32)" src/yuleosh/ --include="*.py" | grep -v __pycache__
```

## 8. 附录 B：待小明裁决事项（阻塞性，先裁决再开发）

> ✅ **裁决结果（2026-08-03 老板确认）**：7 项全部按推荐方案落定，见下表「裁决」列。

| # | 事项 | 选项 | 影响 | 裁决 |
|---|------|------|------|------|
| B1 | A1 公共模块归属 | ① auth_extended 为基（推荐，改动最小）② 抽 `ui/auth_core.py` 公共模块（依赖更清晰，改动面+0.5d） | A1 实现方式 | ✅ ① auth_extended 为基（改动最小，避免新模块引入面） |
| B2 | A2 ring 去留 | ① 保留为 hot cache（明确无读取方则实为死代码）② 删除（推荐） | A2 范围 | ✅ ② 删除 ring（写-only 死代码，无读取方，收敛到 DB 单一审计） |
| B3 | A2 legacy 请求是否入持久审计 | ① 仅 /api/ 前缀请求入表（推荐，控膨胀）② 全量（含页面资源）入表 | A2 数据面 | ✅ ① 仅 /api/ 前缀请求入表（控表膨胀，页面资源不入审计） |
| B4 | A2 POST /api/v1/audit | ① 保持 405（推荐，v3.7.0 实测）② 提供 DB 事件写入 | A2 契约 | ✅ ① 保持 405（审计只读面，写入走业务事件源） |
| B5 | A2 event_bus 持久化 | ① 修复走统一表（loop 事件单独表）② 显式移除（仅内存） | A2 范围 | ✅ ② 显式移除持久化分支（AttributeError 被吞从未生效，保持内存+注释；loop 事件持久化另行立项） |
| B6 | A6 前端产物 | ① 源码结构验收（推荐，产物不重建）② 重建产物并发布 | A6 验收口径 | ✅ ① 源码结构验收（产物不重建，避免构建面回归） |
| B7 | A3 资源命名 | `tenant`/`billing`/`projects` 复数资源注册（推荐）或其他 | A3 实现 | ✅ 复数资源注册（对齐现有 API 面命名） |
