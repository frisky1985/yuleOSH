# Acceptance Matrix — yuleOSH v3.8.0（Track2 架构收敛）

> 版本: v3.8.0 · 基线: v3.7.0 (2e0eef5) · 日期: 2026-08-03
> 用途: 小克开发测试清单 + 小马复验对照表。**负例（-neg）为必选项**。
> 规则: 每项至少 1 正例 + 1 负例；测试 ID 命名 `T-Ax.n-<描述>` / `T-Fx.n-<描述>`；复验勾选 ✅ 表示小马独立跑通。
> 回归基线: 9873 passed / 0 failed；覆盖率 ≥84.10% 不降。

---

## A1 验收 — 认证三套合一（来源 A-C-02，🔴 最高风险）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A1-01-secret-single | secret 单一来源 | import `api.auth` 与 `ui.auth_extended`，断言同源 | 同一 secret 值（对象或字符串相等）；无第二份 env 解读 | 正例 |
| T-A1-02-mw-verify-unified | middleware 统一 verify | 合法 token（signin 签发）访问 `@require_auth` 端点 | 200（与 v3.7.0 一致）；monkeypatch 断言 `get_session_user`（或统一 verify）被调用、middleware 自研解码未执行 | 正例 |
| T-A1-03-v1-token-ui-accepts | v1 token 前端链互认 | `/api/v1/auth/login` 签发 token → `GET /api/auth/session` | 200，返回同一 user（user_id/email/org_id 一致） | 正例 |
| T-A1-04-ui-token-v1-accepts | 前端 token v1 链互认 | `/api/auth/signin` 签发 token → `GET /api/v1/auth/me` | 200，同一 user | 正例 |
| T-A1-05-login-contract | login 响应契约 | `POST /api/v1/auth/login`（合法凭据） | `{ok, data:{token, user:{id,email,role,org:{id,name,slug}}}}`（v3.7.0 结构） | 回归 |
| T-A1-06-register-contract | register 响应契约 | `POST /api/v1/auth/register` | 同上结构 + 409/400 语义不变 | 回归 |
| T-A1-07-neg-invalid-token | **负例：无效 token 两端拒绝** | 伪造/篡改 token 访问 `@require_auth` 端点与 `/api/auth/session` | 均 401（fail-closed） | 负例 |
| T-A1-08-neg-rate-merged | **负例：限流合并后共享计数** | 同一 email 先错 10 次于 `/api/v1/auth/login`，再调 `/api/auth/signin` | signin 被 429 阻断（共享 10 次/5min 预算，行为收紧） | 负例 |
| T-A1-09-neg-no-random-fallback | **负例：无随机 secret 兜底** | grep `token_urlsafe(32)` 于 src/ | 零命中（F1 联动） | 负例 |
| T-A1-10-fail-fast | fail-fast 保持 | monkeypatch 移除 `YULEOSH_JWT_SECRET` → 导入认证模块 | RuntimeError（SEC-W3 不回退） | 回归 |
| T-A1-11-frontend-chain | 前端登录链 E2E | signin → org/create → auth/session → project/list → stats/overview | 全链路 200，字段逐项一致 | 回归 |
| T-A1-12-api-key-kept | API key 机制保留 | X-API-Key 合法 → legacy `/api/evidence` | 200（独立机制不回退） | 回归 |
| T-A1-13-cookie-kept | session cookie 保留 | `_auth/login` 设 cookie → 页面请求 | 放行（create_session/validate_session 不回退） | 回归 |
| T-A1-14-neg-mw-401-no-token | **负例：无 token 401** | 无凭据访问 `@require_auth` 端点 | 401 `Authorization header with Bearer token required` | 负例 |
| T-A1-15-dead-code-gone | **负例：重复实现消失** | grep `api/auth.py` 内 `_generate_token`/`_hash_password`/`_SIGNIN_RATE_LIMIT` | 零命中（或仅适配层引用统一实现） | 负例 |

## A2 验收 — 审计统一（来源 A-W-01）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A2-01-legacy-into-db | legacy 请求入 DB | 发起 GET `/api/evidence`（legacy）→ 查 audit_log 表 | 表中含该请求记录（统一 log_request 写路径） | 正例 |
| T-A2-02-v1-into-db | v1 请求入 DB | 发起 GET `/api/v1/health` → 查表 | 表中含该请求记录 | 回归 |
| T-A2-03-single-write | 单次请求单条记录 | 一次请求后统计 audit_log 行数 | 恰好 1 条新增（无 ring+DB 双写双算） | 正例 |
| T-A2-04-audit-api-contract | GET 契约 | admin 调 `GET /api/v1/audit?limit=10` | `{ok,data:{entries,count,total,limit,offset}}`，limit 上限 200 | 回归 |
| T-A2-05-rbac-admin | RBAC admin 可读 | admin 角色调 audit API | 200 | 回归 |
| T-A2-06-neg-member-forbidden | **负例：member 403** | member 角色调 audit API | 403 | 负例 |
| T-A2-07-neg-anon-401 | **负例：匿名 401** | 无 token 调 audit API | 401 | 负例 |
| T-A2-08-ring-bounded | ring hot cache 有界 | 灌入 >5000 请求 | 内存 ≤ 上限（若保留）；DB 完整 | 正例 |
| T-A2-09-neg-no-jsonl-http | **负例：JSONL 移出 HTTP** | grep `audit_routes` 的 handle_* 引用 | 无 HTTP 路径引用（或已改造为 DB） | 负例 |
| T-A2-10-eventbus-persist | event_bus 审计修复 | 配置 store 触发事件 → 检查日志/表 | 无被吞 AttributeError；持久化生效或显式移除（无 warning） | 正例 |
| T-A2-11-neg-eventbus-silent | **负例：无静默失效** | 同 T-A2-10，断言日志无 `persist error` | 无静默失败分支 | 负例 |
| T-A2-12-jsonl-lib-kept | JSONL 库保持 | `tests/test_audit_model_unit.py` | 全绿（库形态保留） | 回归 |
| T-A2-13-neg-no-ring-only | **负例：审计非仅内存** | 重启进程后查 DB | legacy+v1 记录仍在（DB 持久） | 负例 |

## A3 验收 — 路由去 legacy 双轨（来源 ARC-W1）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A3-01-tenant-info | tenant info 迁移 | GET `/api/v1/tenant/acme`（Bearer） | 响应字段/状态码与 v3.7.0 逐一一致 | 回归 |
| T-A3-02-tenant-projects | tenant projects 迁移 | GET `/api/v1/tenant/acme/projects` | 同上 | 回归 |
| T-A3-03-tenant-usage | tenant usage 迁移 | GET `/api/v1/tenant/acme/usage` | 同上 | 回归 |
| T-A3-04-tenants-list | tenants 列表迁移 | GET `/api/v1/tenants` | 同上 | 回归 |
| T-A3-05-tenant-create | tenant 建项目迁移 | POST `/api/v1/tenant/acme/projects`（合法 body） | 同上；body 由 router read_body 统一读 | 回归 |
| T-A3-06-billing-usage | billing usage 迁移 | GET `/api/v1/billing/usage` | 同上 | 回归 |
| T-A3-07-billing-plan | billing plan 迁移 | GET `/api/v1/billing/plan` | 同上 | 回归 |
| T-A3-08-billing-upgrade | billing upgrade 迁移 | POST `/api/v1/billing/upgrade` | 同上 | 回归 |
| T-A3-09-projects-get | projects get 迁移 | GET `/api/v1/projects/xyz` | 同上 | 回归 |
| T-A3-10-projects-create | projects create 迁移 | POST `/api/v1/projects` | 同上 | 回归 |
| T-A3-11-projects-update | projects update 迁移 | POST `/api/v1/projects/xyz` | 同上 | 回归 |
| T-A3-12-audit-v1 | audit 单一路径 | GET `/api/v1/audit` | 由 handle_audit（DB）服务，结构不变 | 回归 |
| T-A3-13-neg-unknown-resource | **负例：未知资源 404** | GET `/api/v1/xxx` | `{"ok":false,"error":"Unknown resource: xxx"}` 404 | 负例 |
| T-A3-14-neg-dispatch-legacy-gone | **负例：_dispatch_legacy 删除** | grep `_dispatch_legacy` | 零命中 | 负例 |
| T-A3-15-neg-handler-dead-branch-gone | **负例：handler_helpers 死分支删除** | grep handler_helpers 中 `/api/v1/tenant/` elif | 零命中（/api/v1/* 全走 router） | 负例 |
| T-A3-16-neg-oversize-body-400 | **负例：body 超限 400** | POST billing/upgrade 超 10MB body | 400（BadRequest，不 500） | 负例 |
| T-A3-17-auth-equiv | 鉴权等价 | 同一 token 分别经旧式语义（直接调 get_session_user）与新式 require_auth 判定 | 判定一致（合法→放行，非法→拒绝） | 正例 |

## A4 验收 — Store 抽象补方法（来源 ARC-W3）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A4-01-project-list | project 列表走接口 | GET `/api/v1/project`（多项目） | 列表/排序/字段与 v3.7.0 一致 | 回归 |
| T-A4-02-spec-path-update | spec_path 更新 | POST `/api/v1/project` 带 spec_path | 落库正确（update_project_spec_path 生效） | 正例 |
| T-A4-03-project-stats | project stats 走接口 | GET `/api/v1/project/stats` | 各计数与 v3.7.0 一致 | 回归 |
| T-A4-04-stats-ci-rate | stats ci_pass_rate | GET `/api/v1/stats/overview`（有 passed/failed） | ci_pass_rate 与 v3.7.0 一致 | 回归 |
| T-A4-05-pg-interface | PG 三实现同步 | PostgresStore 调用 4 个新方法 | 行为与 SQLite 一致，无 NotImplementedError/AttributeError | 正例 |
| T-A4-06-neg-no-bare-sql | **负例：api 无裸 SQL** | grep `conn.execute` 于 `api/project.py`/`api/stats.py` | 零命中 | 负例 |
| T-A4-07-interface-complete | 接口完整性 | 遍历 AbstractStore 方法在 Store/PG 的实现 | 全部实现（无遗漏） | 正例 |
| T-A4-08-empty-tables | 空表行为 | 空库调 project/stats 端点 | 与 v3.7.0 一致（空列表/零计数） | 回归 |

## A5 验收 — cli/main.py 拆分命令组（来源 A-P2-01/05）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A5-01-traceability-cmd | traceability 组迁移 | `yuleosh traceability report/matrix/export` 各执行 | 输出/退出码与 v3.7.0 一致 | 回归 |
| T-A5-02-misra-cmd | misra 组迁移 | `yuleosh misra deviate/trend/profile/report` 各执行 | 同上 | 回归 |
| T-A5-03-swe6-cmd | swe6 组迁移 | `yuleosh swe6 status/check` 各执行 | 同上 | 回归 |
| T-A5-04-reviewdiff-cmd | review_diff 组迁移 | `yuleosh review-diff` 执行 | 同上 | 回归 |
| T-A5-05-130-cli-tests | CLI 测试全绿 | `test_cli*.py` + `test_autosar_cli_ext.py` 全量 | 全绿（import 路径兼容或已更新） | 回归 |
| T-A5-06-neg-no-syspath-tests | **负例：tests 无 sys.path.insert** | grep `sys.path.insert` 于 tests/ | 零命中（pythonpath=src 生效） | 负例 |
| T-A5-07-parser-args | 参数契约 | `yuleosh --help` / 各子命令 `--help` | 命令名/参数/默认值与 v3.7.0 逐项一致 | 回归 |
| T-A5-08-neg-no-copy | **负例：无复制逻辑** | grep 共享 helper（如 `_ensure_tool_deps`）定义 | 全仓仅一份 | 负例 |
| T-A5-09-main-slim | main.py 瘦身 | `wc -l cli/main.py` | ≤ 1200 行 | 正例 |
| T-A5-10-neg-no-cycle | **负例：无循环导入** | import `cli.main` 与各 commands 模块 | 无 ImportError/循环（cold import 验证） | 负例 |

## A6 验收 — dashboard/page.tsx 拆组件（来源 ARC-W5）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-A6-01-build-pass | 构建通过 | `npm run build`（或项目等价命令） | 成功 | 正例 |
| T-A6-02-tsc-pass | 类型检查 | `tsc --noEmit` | 零错误 | 正例 |
| T-A6-03-tabs-behavior | 四 tab 行为 | overview/gap-analysis/knowledge-base/misra-trends 切换 | 渲染/交互与 v3.7.0 一致（无 console 错误） | 回归 |
| T-A6-04-page-slim | page.tsx 瘦身 | `wc -l page.tsx` | ≤ 600 行（或 ≥4 个组件文件且职责单一） | 正例 |
| T-A6-05-neg-no-logic-copy | **负例：无逻辑复制** | grep 重复 fetch/state 定义 | 每个功能逻辑仅一份 | 负例 |
| T-A6-06-neg-no-new-deps | **负例：无新依赖** | 检查 package.json diff | 零新增 npm 依赖；`components/ui/*` 未改 | 负例 |

## 附项验收

### F1 — subscription/wizard secret 单一来源

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-F1-01-subscription-stable | subscription 跨调用验签 | 同一 token 调 `_get_authenticated_org` 两次 | 两次结果一致（修复随机 secret bug） | 正例 |
| T-F1-02-wizard-stable | wizard 跨调用验签 | 同一 token 调 `_get_org_id_from_handler` 两次 | 两次 org_id 一致 | 正例 |
| T-F1-03-neg-no-random | **负例：无随机兜底** | grep `token_urlsafe(32)` 于 subscription.py/wizard.py | 零命中 | 负例 |
| T-F1-04-fail-fast | fail-fast | 无 env import 两模块 | RuntimeError | 回归 |

### F2 — preview 匿名 user_key 换 user_id

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-F2-01-logged-user-key | 登录用户 user_id 键 | 登录态提交 preview → 检查缓存键 | `u:<user_id>`（非 ip 维度） | 正例 |
| T-F2-02-dev-anon-ip | dev 匿名保留 | AUTH_DISABLED=1 下两次同 URL | 命中同 IP 缓存（v3.7.0 行为） | 回归 |
| T-F2-03-neg-cross-user | **负例：跨用户不命中** | 用户 A/B 同 repo_url | B 不命中 A（W6 隔离不回退） | 负例 |
| T-F2-04-same-user-hit | 同用户命中 | 用户 A 两次同 URL（TTL 内） | `cached: true` | 回归 |

### F3 — do_POST/do_DELETE 审计 _response_status

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-F3-01-post-500-audit | POST 异常审计 500 | 注入 `handle_post` 抛异常 → 查审计记录 | 响应 500 且审计 status=500 | 正例 |
| T-F3-02-delete-500-audit | DELETE 异常审计 500 | 注入 `handle_delete` 抛异常 → 查审计记录 | 同上 | 正例 |
| T-F3-03-neg-post-200-audit | **负例：异常不得记 200** | 同 T-F3-01 | 断言审计 status ≠ 200 | 负例 |
| T-F3-04-normal-ok | 正常请求审计不变 | 正常 POST 200 | 审计 status=200（无回归） | 回归 |

### F4 — _serve_file 页面路径 Cache-Control

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-F4-01-dashboard-no-cache | 页面 no-cache | GET `/dashboard` | 响应含 `Cache-Control: no-cache` | 正例 |
| T-F4-02-pricing-no-cache | marketing no-cache | GET `/pricing`、`/en/pricing` | 同上 | 正例 |
| T-F4-03-neg-no-immutable-html | **负例：HTML 不 immutable** | 同上响应头 | 不含 `immutable` | 负例 |
| T-F4-04-404-kept | 404 兜底不破坏 | GET 不存在页面 → 404 页 | 状态码/安全头保持 | 回归 |

---

## 全局回归清单（每批后必跑）

```bash
# 局部（每批）
python3 -m pytest tests/test_backlog_p1_v350.py tests/test_ui_server_deep.py \
  tests/test_cli_main_adv_unit.py tests/test_api_auth_deep.py tests/test_api_audit_ext.py \
  tests/test_security.py tests/test_store_pg_deep.py -q

# 全量（P2/P5 后 + 收尾）
python3 -m pytest tests/ -q \
  --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py \
  --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py \
  --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py
```

- 门禁：≥ 9873 passed / 0 failed；覆盖率 ≥84.10%（`--cov-fail-under` 按 CI 配置）。
- 架构债消失 grep 证据（复验必查）：
  1. `grep -rn "_dispatch_legacy" src/` → 零命中（A3）
  2. `grep -rn "token_urlsafe(32)" src/yuleosh/ --include="*.py"` → 零命中（A1/F1）
  3. `grep -rn "sys.path.insert" tests/` → 零命中（A5）
  4. `grep -rn "conn.execute" src/yuleosh/api/project.py src/yuleosh/api/stats.py` → 零命中（A4）
  5. `grep -rn "from yuleosh.audit.model import\|from .audit import\|from yuleosh.ui.routes.audit_routes import" src/yuleosh/ --include="*.py"` → 无 HTTP 路径引用（A2）
  6. `grep -rn "def _generate_token\|def _hash_password\|def _check_rate_limit" src/yuleosh/api/auth.py` → 零命中（A1）
