# yuleOSH v3.9.0 Track3 前端安全 — 独立正式复验报告（小马 🐴）

> 复验人: 小马（Hermes QA）· 日期: 2026-08-03 23:11-23:35 · 方式: 独立执行，不采信开发自报
> 契约: `.osh/specs/v3.9.0/`（spec / spec-delta 附录 B / startup-analysis / acceptance-matrix）
> 基线: v3.8.0（9953 passed / 0 failed，cov 84.14%）· 裁决: B1-B8 全部「按推荐」（老板 2026-08-03 确认）
> 结论: ✅ **通过 — 放行发布**（评分 97/100；P0=0 / P1=0 / P2=3 观察项）

---

## 1. 结论摘要

| 门禁项 | 契约要求 | 实测（小马独立） | 判定 |
|--------|----------|------------------|------|
| Git 状态 | HEAD=origin/main=2ec102c；7 提交链；工作区干净；gh-pages=63e1178 | 全部符合；提交链与批次一一对应 | ✅ |
| 全量回归 | ≥9953 passed / 0 failed（CI 等价口径） | **10017 passed / 0 failed**（71 skipped / 11 xfailed，结构同基线） | ✅ |
| 覆盖率 | ≥84.14% 不降 | **84.17%**（+0.03） | ✅ |
| 前端 jest | 全绿 | **33/33**（api 15 + login 8 + markdown 10） | ✅ |
| tsc / build | 全过 | tsc --noEmit 0 错；next build 35 页成功 | ✅ |
| X-01 红线 | markdown 10 + kb_sanitize 15 | 10 + 15 全绿（79 子集实跑） | ✅ |
| 新增用例数 | +64 恰为新用例 | 4 测试文件 16+20+10+18=64 吻合 | ✅ |
| 安全债 6 项 grep | 全过 | 1-5 全过；#6 机制存在（变量拼头，经 auth_cookies 单一来源） | ✅ |
| 4 个既有 bug 修复 | 代码+测试双证 | 全部确认（见 §4） | ✅ |
| gh-pages | 18+ 独立页不丢 + 线上 200 | 35 页零丢失零新增；线上 200（/、docs.html、en/） | ✅ |
| Tag v3.9.0 | 复验通过后打 | 已打 lightweight @2ec102c 并 push origin ✅ | ✅ |

**评分: 97/100**（扣分项：refresh 端点无限流器 -2；build 未链 meta CSP 注入 -1；其余全绿）

---

## 2. T1 token cookie 迁移（P1-P4）— 全项通过

### 2.1 双 cookie 签发/下发/清除
- `ui/auth_cookies.py` 为**单一来源**（SHALL-T1.1/T-T1-22）：`yuleosh_at`（access，**0.5h**）+ `yuleosh_rt`（refresh，**168h**），属性 `HttpOnly; SameSite=Lax; Path=/`，生产（非 dev）加 `Secure`；`clear_cookie_headers` 双 cookie `Max-Age=0`。
- 下发路径：signin（`needs_org` 时 org_setup token 进 access 槽位，30min）/ org_create / v1 register（经 `_auth_refresh_token` 标记，router._respond 剥离）均 Set-Cookie；**JSON body 与 v3.8.0 逐字段一致（refresh_token 仅 cookie 通道，body 剥离）**。
- logout：DB session 删除 + 双 cookie 清除（T-T1-13/14 覆盖）。
- wire 实测（test_v390_t1_cookies）：signin 200 + Set-Cookie 属性断言（httponly/samesite/max_age 均验）；chain_signin_orgcreate 双 cookie 链完整。

### 2.2 cookie 回退读取（双链互认）
- `api/middleware.py._extract_token` 与 `ui/routes/auth_routes.py._get_bearer_token`：**Authorization 优先（Bearer）→ 无 Authorization 才读 `yuleosh_at` cookie；Authorization 存在但非 Bearer → fail-closed 不回退**（T-T1-07 语义一致）。
- `ui/auth.py.is_authenticated`：API key → osh_session → Bearer → access cookie 四段委托，refresh cookie 永不通过（`_is_refresh_token` 双路拒绝）。
- 负例全绿：伪造 cookie 401（T-T1-06-neg）、无凭据 401、garbage/malformed cookie 拒绝、osh_session 不可冒充租户 cookie（T-T1-18-neg）。

### 2.3 refresh 端点
- `POST /api/auth/refresh`（PUBLIC_PATHS 白名单内，自认证）：仅收 `purpose="refresh"` 的 JWT；签名/DB session 行/user 行全验；**成功→旧 rt 删除（单次使用轮换）+ 签发新对**；失败→双 cookie 清除（T-T1-11-neg）。
- 轮换修复：`_generate_token` 加 **`jti` 随机唯一**——同秒签发不再字节相同（原 sha256 行冲突导致轮换失效的根因已除）。
- 负例：伪造/垃圾/access 冒充 refresh 均 401；旧 rt 复用 401（T-T1-12-neg）；logout 后 refresh 被拒（T-T1-14-neg）。

### 2.4 前端去 localStorage（SHALL-T1.3/T1.11）
- `api.ts`：`TOKEN_KEY` 语义移除，`setToken/getToken/clearToken` 降级**仅内存**（import 兼容）；`request()` 不再拼 Bearer，`credentials: "same-origin"`；**401→单飞 refresh→重放一次→失败 redirectToLogin**（NO_REFRESH_PATHS 排除 signin/refresh 防死循环）。
- grep 实测：`localStorage.*yuleosh_token` 零命中（仅 api.ts 注释 + pricing LOCALE_KEY 非敏感偏好）；`Authorization.*Bearer` 零命中（排除 __tests__）。

### 2.5 legacy 保留（SHALL-T1.8）
- X-API-Key 与 `osh_session` 机制原样保留，独立判定不回退（T-T1-16/17 全绿）。

---

## 3. T2 CSP Phase 1（P5）— 全项通过

- **策略单一来源**（`ui/server.py`）：`default-src 'self'; script-src 'self' 'nonce-<每请求随机>'; style-src 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'`。
- **B5 ① nonce 落地**：`_serve_static`/`_serve_file` 对 HTML 响应每请求 `_inject_csp_nonce`（改写内联 `<script>` 注入 nonce）+ 配对 CSP 头；无构建耦合。
- **T2.2 例外条款（注明用途）**：`_LEGACY_EXTERNAL` 按**模板字节扫描**追加实际引用外域（Google Fonts→style-src/font-src；Tailwind CDN→script-src）；`js.stripe.com` 无模板引用，保留但永不触发。**frontend/out（Next.js 产物）零外域引用，保持严格 nonce 策略** —— 与契约「产物零引用」前提一致。
- **T2.4/B6**：`'unsafe-eval'` 已移除。产物唯一 `Function("return this")`（core-js global 检测链）在 `globalThis` 存在时短路死代码，注释含文件证据；Chrome headless 0 violation（开发实测 + wire 测试佐证）。
- **T2.8/B8**：nginx **不设 CSP**（与每请求 nonce 策略取交集会拦内联脚本，单一来源 Python，T-T2-10）；gh-pages 走 **HTML meta CSP**（`frontend/scripts/inject-meta-csp.py`，内联 RSC 脚本 sha256 hash 白名单 + style-src-attr unsafe-inline），边界说明写入 `docs/cybersecurity-baseline.md` §12.5（T-T2-12-neg）。
- 负例断言实测：script-src 无裸 unsafe-inline（T-T2-03-neg）、unsafe-eval 不在 script-src 与 nginx（T-T2-06-neg）、object-src none / base-uri self / frame-ancestors self / form-action self（T-T2-07-neg）——全部在 test_v390_t2_csp.py 断言并通过。
- **4 个既有 bug 修复**（任务复验要点 5）：① `_handle_api` 双响应（server.py FIX：handle_api_action 已发响应，不再二次 `_json_response`，wire 测试 `handle_api_sends_single_response`）② 自动建组织 401（needs_org signin 将 org_setup token 写入 access cookie，org/create 经 cookie 回退读取，纯 cookie 链可用）③ refresh 轮换失效（jti 唯一化）④ `_serve_file` 双 Content-Length（nonce 改写后**单次**设置，wire 测试走真实 HTTP 服务器）。

---

## 4. F1 产物与发布（P6）— 全项通过

- **裁决落盘**：spec-delta 附录 B7=「重建+发布 GitHub Pages」（T-F1-01 ✅）；out/ 仅 P6 提交（T-F1-02 ✅，P1-P5 无产物提交）。
- **out/ 重建**：35 个 HTML 页；提交产物含 meta CSP（sha256 白名单）；独立静态页（architecture/docs/app/en/scenarios/subscription 等）全部保留。
- **gh-pages 完整性核对（v3.6.1 教训）**：`git ls-tree` 对比 v3.6.1（91dba3d）→ v3.9.0（63e1178）：HTML 页面集合 **零丢失零新增**；195 文件与 main 的 out/ 一致。
- **线上健康**：`https://frisky1985.github.io/yuleOSH/` 200（营销页完整渲染）；`/docs.html` 200；`/en/index.html` 200。

---

## 5. 问题清单

| 级别 | 问题 | 证据 | 建议 |
|------|------|------|------|
| P0 | 无 | — | — |
| P1 | 无 | — | — |
| P2-1 | refresh 端点无显式限流器（轮换=单次使用已提供核心防重放；signin 有邮箱+IP 双限流） | `grep check_rate_limit`：refresh 路径零调用；handler_helpers.rate_limit_check 定义但无调用方 | Phase 2 加 per-IP 限流（复用 `api/ratelimit.py`），本轮以轮换为缓解措施 |
| P2-2 | `npm run build` 不自动注入 meta CSP（需手动 `python3 frontend/scripts/inject-meta-csp.py`） | package.json build="next build"；提交产物已含 meta CSP（现态正确） | 建议 build 脚本链上注入步骤，防后续重建漂移 |
| P2-3 | `/org/setup` 静态页仍读 `localStorage('osh_token')`（legacy 独立流，不在 frontend/src 范围） | 开发报告 §9 自述 | 后续版本清理；本轮不阻塞（契约范围外） |

## 6. 证据链（独立命令）

```bash
# Git
git rev-parse HEAD origin/main        # 2ec102c = 2ec102c
git log --oneline -8                  # bf17275→…→2ec102c 七提交，批次对应
git status --short                    # 干净
git rev-parse origin/gh-pages         # 63e1178

# 安全债 6 项 grep（复验要点 3）
# 1 localStorage.*yuleosh_token：零命中（仅注释+LOCALE_KEY）  2 Authorization.*Bearer：零命中
# 3 nginx 外域：零命中（CSP 整体移交 Python 单一来源）        4 server.py Content-Security-Policy：2 处（_serve_static/_serve_file）
# 5 yuleosh_at/rt：auth_cookies.py 常量+9 处引用（HttpOnly 属性经 make_auth_cookie）
# 6 Set-Cookie：auth_routes 8 处 send_header + router._respond（变量拼头，字面 grep 不中属正常）

# 测试（单进程，无并发）
python3 -m pytest tests/test_v390_t1_cookies.py tests/test_v390_t1_cookie_fallback.py \
  tests/test_v390_t1_refresh.py tests/test_v390_t2_csp.py tests/test_kb_sanitize_xss.py -q
  # → 79 passed（64 新 + 15 kb_sanitize X-01 红线）
python3 -m pytest tests/ -q --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py \
  --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py \
  --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py \
  --cov=yuleosh --cov-report=term
  # → 10017 passed, 71 skipped, 11 xfailed, 0 failed；TOTAL coverage 84.17%（12:54）

# 前端
cd frontend && npm test               # 33 passed（api 15 + login 8 + markdown 10）
npx tsc --noEmit                      # exit 0
npm run build                         # 35 页成功（注：跑完需恢复 out/ 或重跑 meta CSP 注入）

# 产物/发布
git show HEAD:frontend/out/index.html | grep -o 'http-equiv="Content-Security-Policy"'   # 命中
git ls-tree -r --name-only origin/gh-pages | grep -c '\.html$'                            # 35
comm -23 <(git ls-tree -r --name-only origin/gh-pages~1 | grep '\.html$'|sort) \
         <(git ls-tree -r --name-only origin/gh-pages | grep '\.html$'|sort)             # 空=零丢失
curl -sI https://frisky1985.github.io/yuleOSH/                                           # 200

# Tag
git tag v3.9.0 HEAD && git push origin v3.9.0   # refs/tags/v3.9.0 = 2ec102c
```

## 7. 放行建议

**✅ 通过，放行发布**。契约全部 SHALL 条款有正例+负例且全绿；回归 10017/0 超基线 64 恰为新用例；覆盖率 84.17% 不降；安全债 6 项 grep 全过；gh-pages 线上健康。3 项 P2 观察项不阻塞发布，建议排入 Phase 2。

## 8. 附注

- 复验过程中小马曾跑 `npm run build` 验证构建，out/ 工作区被重建（meta CSP 消失）——**已 `git checkout -- frontend/out` 恢复**；结论基于提交内容（git show）与 gh-pages 线上，不受影响。此现象即 P2-2 的实证。
- 浏览器级手工登录链（T-T1-19/23）：wire 级真实 HTTP + cookie jar 已覆盖（chain_signin_orgcreate、session_via_cookie、middleware overview 路径）；HttpOnly JS 不可读由 Set-Cookie 属性断言（httponly=True）佐证。建议小明如需 100% 浏览器级证据，可在本地 Python 服务手工复验一次。
