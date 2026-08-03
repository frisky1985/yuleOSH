# Plan — yuleOSH v3.6.1 — ultra-review Critical×3 修复

> 日期: 2026-08-02 · 依据: `~/.openclaw/workspace/reviews/ultra-full-2026-08-02/`（COR-C1 / SEC-C1 / SEC-C3）
> 状态: 实施完成，待小马复验

## 修复对照表

| Fix | Review 项 | 文件 | 改动 |
|-----|-----------|------|------|
| Fix 1 | COR-C1 / SEC-C2 错误回显残留 7 处 | 新增 `src/yuleosh/api/_errors.py`；`api/ci.py:54`、`api/review.py:49/77`、`api/pipeline.py:156/222`、`api/apikeys.py:60`、`api/subscription.py:260` | 统一 `internal_error(module, e)`：`logging.error(..., exc_info=True)` + `json_error("Internal server error", 500)`。附赠修复同函数内 evidence.py 的 `"Evidence generation error: " + str(e)` 回显 |
| Fix 2 | COR-W1 / SEC-C1 evidence/dashboard project_dir 任意 cwd | `src/yuleosh/api/evidence.py::_generate_evidence`、`src/yuleosh/api/dashboard.py::_dashboard_evidence_generate` | resolve 后必须 `relative_to(OSH_HOME)`，否则 403；dashboard 在校验通过前不建 task 记录 |
| Fix 3 | SEC-C3 legacy /api/* 默认无鉴权 | `src/yuleosh/ui/auth.py`、`src/yuleosh/ui/server.py::_check_auth`、`src/yuleosh/ui/routes/handler_helpers.py` | `AUTH_ENABLED` 默认 fail-closed（`YULEOSH_AUTH_DISABLED=1|true|yes` 显式关闭）；`_check_auth` 加公开路径白名单；`is_authenticated` 增加 tenant JWT Bearer 校验；拒绝时 API 路径 401 JSON / 页面路径返回登录页 |

## 公开路径白名单（Fix 3，测试证据驱动）

- health/status: `/api/health`、`/api/status`、`/health`
- 登录/租户 onboarding 页: `/login`、`/register`、`/welcome`、`/org/setup`、`/project/select`
- 租户认证端点（自带 JWT 校验）: `/api/auth/signin`、`/api/auth/session`、`/api/auth/logout`、`/api/org/create`、`/api/org/info`、`/api/project/create`、`/api/project/list`
- 前端页面（静态壳，数据全部走受保护 /api/*）: `/`、`/index.html`、`/dashboard`、`/kanban`、`/audit-dashboard`、`/billing`、`/pipeline-flow`、`/apikeys`、`/onboarding`、`/demo`、`/pricing`、`/en/*`
- 静态资源前缀: `/static/`、`/assets/`、`/_next/`

**白名单依据（前端联调）**: 租户流程 token 存 localStorage（无 cookie），页面必须无凭据可达；数据端点（`/api/evidence`、`/api/reviews`、`/api/ci`、`/api/loops/*`、pipeline trigger 等）默认 401。前端页面携带 Bearer JWT 调 legacy 数据端点 → `is_authenticated` 增加 JWT 校验后放行（证据: test_v344_p0ab_integration.py 全链路 + 新增 test_v361_critical_fixes.py 真实子进程服务器验证）。

## 测试

- 新增 `tests/test_v361_critical_fixes.py`（32 用例）: Fix1 脱敏 9 项（含 exc_info 日志断言）、Fix2 负例（/etc、../ 逃逸 → 403）、Fix3 真实子进程服务器（默认 401 / YULEOSH_AUTH_DISABLED=1 放行 / 租户 JWT 全链路 200）
- 更新: test_api_evidence_ci.py（project_dir 改 OSH_HOME 内 + 403 负例 + 脱敏断言）、test_api_evidence_ext.py、test_api.py（evidence 2 项）、test_api_dashboard_unit.py（dashboard 403 负例 ×2）、test_ui_server_deep.py / test_backlog_p1_v350.py（_check_auth 用例补 gated path）

## 回归

- 全量: `pytest tests/`（忽略 6 个 E2E 文件）→ 基线 9756 passed / 0 failed（v3.6.0）
- 覆盖率 ≥ 84.08% 不降
- jest 3 suites: 未动 frontend/，不涉及
- test_v344_p0ab_integration.py 全链路: 通过

## 风险与遗留

- 默认部署（未设 API key）下 legacy 数据端点一律 401 — 需文档化部署要求（设 YULEOSH_API_KEY 或依赖租户登录）
- api/__init__.py `PROJECT_ROOT` 计算层级（env 未设时 OSH_HOME 兜底为 src/）为既有行为，未改；若要做可在 Track 2 收敛
- 错误文案 `"Internal server error"` 与 v3.5.0 P1-7 风格一致
