# Plan — yuleOSH v3.9.0（Track3 前端安全）开发计划与 Checkpoint

> 开发: 小克 · 契约: `.osh/specs/v3.9.0/`（spec / spec-delta / startup-analysis / acceptance-matrix）
> 基线: v3.8.0 发布（9953 passed / 0 failed，cov 84.14%）· HEAD=5f91b33
> 裁决: B1-B8 全部「按推荐」（2026-08-03 老板确认，已写入 spec-delta 附录 B）

---

## 0. 开工检查（2026-08-03 22:05）

- [x] HEAD = 5f91b33（契约 commit 已含）
- [x] 无 plan-v3.9.0.md 存在 → 本 session 为首个开发者（无重复 spawn）
- [x] 无其它 agent 在写 yuleOSH 工作区（ps 检查无相关进程）
- [x] 契约四文档已读：spec.md / spec-delta.md / startup-analysis.md / acceptance-matrix.md

### 关键事实核对（实测 HEAD=5f91b33）

| 项 | 实测 | 备注 |
|----|------|------|
| 前端 token 面 | api.ts TOKEN_KEY/localStorage + 4 页面 10 处调用 | 与契约一致 |
| 后端签发 | `_generate_token` exp=now+72h；`_create_login_response`/`handle_org_create`/`register` 单 token | 待改双 token |
| middleware | `_extract_token` 仅 Bearer；`require_auth` fail-closed | 待加 cookie 回退 |
| auth_routes | `_get_bearer_token` 仅 Bearer；`handle_api_action` 各分支 `_send_json_response` | 待加 Set-Cookie |
| is_authenticated | X-API-Key → osh_session → Bearer 三链 | 待加租户 cookie 链 |
| user_sessions | token UNIQUE，sha256 落库；双 token = 双行（无冲突） | 已确认 |
| ⚠️ 既有 bug | `server._handle_api` 双响应：wire 上 `{...}HTTP/1.0 200 OK...null` 拼接（实测复现） | **P1 一并修复**（Set-Cookie 必须落在首个响应） |
| gh-pages | origin/gh-pages 含独立静态页：app/、architecture.html、docs.html、en/（out/ 中没有） | P6 必须保留后推 |
| 测试风险 | `test_jwt_auth`/`test_auth_extended_handlers` 断言 `_generate_token()` 默认 72h exp → **保持默认 TTL 参数** | 登录链改用 ACCESS_TTL 不破坏 |
| v1 register | `_handle_register` → `json_ok({token,user})` → `router._respond` | 待加 Set-Cookie 通道 |
| `_send_json_response` | 无 extra headers 通道；mock handler 走 inline 分支（send_header 可断言） | 待扩展 |

### 设计要点（已定）

1. **双 token 机制**：`_issue_token_pair` 签发 access（30min，无 purpose）+ refresh（7d，purpose="refresh"）；两条 user_sessions 行（sha256）。
2. **refresh 不可当 Bearer 用**：`verify_token`/`get_session_user` 拒绝 `purpose=="refresh"`（T1.4/T1.5 语义，防 refresh 冒充 access）。
3. **JSON body 契约保持**：响应 dict 带 `refresh_token`（供路由层），路由层 pop 后转 Set-Cookie，wire body 与 v3.8.0 逐字段一致。
4. **cookie 单一来源**：`ui/auth_cookies.py` 常量 + builder（HttpOnly; SameSite=Lax; Path=/; Secure=生产）。
5. **Secure 策略**：`is_development()` 时省略 Secure（dev http 可用），测试默认生产模式（带 Secure，不影响 contains 断言）。
6. **_handle_api 双响应修复**：改为只调 `handle_api_action`（内部已发响应），不再二次 `_json_response(None)`。
7. **前端 refresh 单飞**：模块级 refreshPromise 互斥，401→refresh→重放一次→失败 redirectToLogin。
8. **TTL**：ACCESS_TTL_HOURS=0.5（30min），REFRESH_TTL_HOURS=168（7d）；`_generate_token` 默认 TTL 仍 72h（既有测试契约不动）。

### 批次与 commit 计划

| 批次 | 内容 | commit 主题 | 回归 |
|------|------|------------|------|
| P1 | T1 Step 0-1：auth_cookies 常量 + 双 token 签发 + 路由 Set-Cookie（signin/org_create/register）+ logout 清 cookie + **_handle_api 双响应修复** | `feat(T1 v3.9.0): P1 — 双 cookie 常量 + 签发时下发 access/refresh + logout 清除（含 _handle_api 双响应修复）` | 局部 6 文件 |
| P2 | T1 Step 2：middleware/auth_routes cookie 回退读取 + is_authenticated 租户 cookie 链 | `feat(T1 v3.9.0): P2 — cookie 回退读取（middleware/auth_routes/is_authenticated）双链互认` | 局部 + 新负例 |
| P3 | T1 Step 3：POST /api/auth/refresh 端点（轮换）+ 前端 401→refresh→重放（后端先行） | `feat(T1 v3.9.0): P3 — refresh 续期端点（轮换+失效清理）` | 局部 + 续期用例 |
| P4 | T1 Step 4-5：前端去 localStorage（api.ts+4 页面）+ 前端 refresh 重试 + TTL 收窄验证 + jest 适配 | `feat(T1 v3.9.0): P4 — 前端去 localStorage + 401 无感续期 + 测试适配` | 局部 + 前端 jest + **全量** |
| P5 | T2 CSP：nginx 清放行 + Python HTML CSP + 基础指令 + unsafe 收窄（B5/B6 评估） | `feat(T2 v3.9.0): P5 — CSP Phase 1（清遗留放行 + 基础指令 + unsafe 收窄）` | 局部 + nginx grep |
| P6 | F1：重建 out/ + 保留 gh-pages 独立静态页 + 发布 + meta CSP（B7/B8） | `feat(F1 v3.9.0): P6 — 重建产物 + gh-pages 发布（保留 app/architecture/docs/en）` | 前端 build/tsc/jest + **全量** |

### 每批局部回归命令
```bash
python3 -m pytest tests/test_api_auth_deep.py tests/test_auth_extended.py tests/test_onboarding_e2e.py tests/test_security.py tests/test_v380_a1_auth_unify.py tests/test_backlog_p1_v350.py tests/test_v361_critical_fixes.py -q
```

### 全量回归（CI 等价口径）
```bash
python3 -m pytest tests/ -q --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py
```

### 验收基线
- 全量 ≥9953 passed / 0 failed（只增不减）
- 覆盖率 ≥84.14% 不降
- 安全债 grep 六项全过
- X-01：markdown.test.ts（10）+ test_kb_sanitize_xss.py（15）全绿

---

## Checkpoint 记录

### [P0] 2026-08-03 22:05 — 开工
契约核对完成，设计定稿，本 plan 落盘。开始 P1。

### [P1] 待完成
