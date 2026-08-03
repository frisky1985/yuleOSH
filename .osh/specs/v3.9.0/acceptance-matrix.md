# Acceptance Matrix — yuleOSH v3.9.0（Track3 前端安全）

> 版本: v3.9.0 · 基线: v3.8.0 (7e864e2) · 日期: 2026-08-03
> 用途: 小克开发测试清单 + 小马复验对照表。**负例（-neg）为必选项**。
> 规则: 每项至少 1 正例 + 1 负例；测试 ID 命名 `T-T1.x-<描述>` / `T-T2.x-<描述>`；复验勾选 ✅ 表示小马独立跑通。
> 回归基线: 9953 passed / 0 failed（CI 等价口径）；覆盖率 ≥84.14% 不降。

---

## T1 验收 — token cookie 迁移（来源 S-P2-03，🔴 最高风险）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-T1-01-cookie-set-signin | signin 下发双 cookie | POST `/api/auth/signin`（合法凭据，模拟浏览器无 Authorization） | 200；响应含 `Set-Cookie: yuleosh_at=...; HttpOnly; SameSite=Lax; Path=/` 与 `yuleosh_rt=...`（同名属性）；JSON body 与 v3.8.0 逐字段一致（token 字段保留） | 正例 |
| T-T1-02-cookie-set-orgcreate | org/create 下发双 cookie | POST `/api/org/create`（org_setup token 流程） | 200 + 双 Set-Cookie；body 一致 | 正例 |
| T-T1-03-cookie-set-register | v1 register 下发双 cookie | POST `/api/v1/auth/register` | 200 + 双 Set-Cookie（若走统一实现） | 正例 |
| T-T1-04-cookie-session-no-bearer | 纯 cookie 读 session | 模拟浏览器带 cookie（无 Authorization）GET `/api/auth/session` | 200，同一 user（user_id/email/org_id 一致） | 正例 |
| T-T1-05-cookie-v1-require-auth | cookie 访问 require_auth | 带 cookie 访问 GET `/api/v1/stats/overview` | 200（middleware cookie 回退生效） | 正例 |
| T-T1-06-neg-forged-cookie | **负例：伪造 cookie 401** | 篡改/伪造 `yuleosh_at` 值访问 session 与 require_auth 端点 | 均 401（fail-closed，与 Bearer 伪造判定一致） | 负例 |
| T-T1-07-bearer-equivalent | Bearer 与 cookie 等价 | 同一 JWT 分别经 Authorization 头与 cookie 访问同一端点 | 判定一致（合法→200，非法→401） | 正例 |
| T-T1-08-neg-no-localstorage | **负例：前端无 token 落盘** | grep `localStorage.*yuleosh_token`/`TOKEN_KEY` 于 frontend/src（除 __tests__ mock） | 零命中 | 负例 |
| T-T1-09-neg-no-bearer-inject | **负例：前端无手工 Bearer** | grep `Authorization.*Bearer` 于 frontend/src（除 __tests__ mock） | 零命中 | 负例 |
| T-T1-10-refresh-issue | refresh 续期 | access 过期（monkeypatch TTL）→ 请求 401 → 调 refresh | 新 access 签发 + 原请求重放成功（无感续期） | 正例 |
| T-T1-11-neg-refresh-expired | **负例：refresh 过期** | refresh 过期/无效 → 调 refresh | 401 + 双 cookie 清除（Max-Age=0） | 负例 |
| T-T1-12-neg-refresh-rotation | **负例：refresh 轮换（SHOULD 项）** | 续期后旧 refresh 再使用 | 旧 refresh 失效（若 B2 走独立端点+轮换） | 负例 |
| T-T1-13-logout-clears-cookie | logout 清 cookie | POST `/api/auth/logout`（带 cookie） | 200；响应 Set-Cookie 双 cookie `Max-Age=0`；DB session 删除 | 正例 |
| T-T1-14-neg-logout-keeps-db | **负例：logout 后 session 失效** | logout 后带旧 cookie 访问 | 401（DB 与 cookie 双清） | 负例 |
| T-T1-15-access-ttl-short | access 短期化 | 断言 `ACCESS_TTL_HOURS`（或等价）≤ 72h 且建议 ≤0.5h（裁决值） | TTL 配置生效；exp 与裁决一致 | 正例 |
| T-T1-16-api-key-kept | legacy API key 保留 | X-API-Key 合法 → `/api/evidence` | 200（独立机制不回退） | 回归 |
| T-T1-17-osh-session-kept | legacy osh_session 保留 | `_auth/login` 设 osh_session cookie → 页面请求 | 放行（create_session/validate_session 不回退） | 回归 |
| T-T1-18-neg-cookie-vs-osh-session | **负例：两 cookie 不混用** | 仅 osh_session 无 yuleosh_at 访问租户端点 / 反之 | 各自独立判定（不互相冒充） | 负例 |
| T-T1-19-frontend-chain-cookie | 前端登录链 cookie 模式 E2E | signin（无 Bearer）→ org/create → session → project/list → stats/overview | 全链路 200，字段逐项一致 | 回归 |
| T-T1-20-frontend-jest | 前端测试适配 | `cd frontend && npm test` | jest 全绿（api.test.ts 改造后 + login.test.tsx 适配） | 回归 |
| T-T1-21-neg-401-redirect | **负例：401 兜底跳转** | 无凭据访问 dashboard 数据端点 | 401 + 前端 redirectToLogin（无感续期失败兜底） | 负例 |
| T-T1-22-cookie-http-only-flag | httpOnly 属性断言 | 检查 Set-Cookie 响应头 | access/refresh 均含 `HttpOnly`（JS 不可读） | 正例 |
| T-T1-23-neg-cookie-not-readable | **负例：JS 读不到 cookie** | 页面 `document.cookie` 检查（浏览器级） | 不含 yuleosh_at/rt（HttpOnly 生效） | 负例 |
| T-T1-24-desktop-topology | 桌面拓扑（B4 按裁决） | 若 B4=Bearer：desktop 请求带 Authorization 正常；若 B4=cookie：fetch credentials include + CORS Allow-Credentials | 按裁决行为通过 | 回归 |

## T2 验收 — CSP Phase 1（来源 CSP）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-T2-01-python-html-csp | Python HTML 响应带 CSP | GET `/dashboard`（`_serve_file`/`_serve_static` 渲染） | 响应含 `Content-Security-Policy` 头（含 T2.1-T2.5 指令） | 正例 |
| T-T2-02-nginx-csp-clean | nginx 清遗留放行 | grep `cdn.tailwindcss.com`/`js.stripe.com`/`fonts.googleapis.com`/`fonts.gstatic.com` 于 nginx.conf CSP 行 | 零命中 | 正例 |
| T-T2-03-neg-no-unsafe-inline-script | **负例：script-src 无裸 unsafe-inline** | 解析 CSP 头 script-src 指令 | 不含 `'unsafe-inline'`（除非 B5 裁决保留并注释） | 负例 |
| T-T2-04-inline-rsc-loads | 内联 RSC 脚本可加载 | 浏览器加载 frontend/out/index.html（6 内联 script） | 页面正常渲染，无 script 阻断（nonce/hash 放行或 B5③ 最小保留） | 正例 |
| T-T2-05-inline-style-attr | 内联 style 属性可渲染 | 检查 index.html 31 个 style= 属性 | 样式生效（style-src-attr 'unsafe-inline' 或等价） | 正例 |
| T-T2-06-neg-eval-policy | **负例：unsafe-eval 处置明确** | 检查 CSP script-src 与产物 `Function("return this")` | 若移除：构建配置消除且页面正常；若保留：注释含文件证据 | 负例 |
| T-T2-07-neg-object-none | **负例：object-src 收紧** | 解析 CSP | 含 `object-src 'none'`、`base-uri 'self'`、`frame-ancestors`（'self'/'none'） | 负例 |
| T-T2-08-page-load-no-violation | 页面加载无 violation | 浏览器逐一加载 index/dashboard/login/pricing | console 无 CSP violation；脚本/样式/字体/图片正常 | 正例 |
| T-T2-09-neg-x01-kept | **负例：X-01 不回退** | `frontend/src/__tests__/markdown.test.ts` + `tests/test_kb_sanitize_xss.py` 全量 | 全绿（escapeHtml 先转义 + _strip_html 保持） | 负例 |
| T-T2-10-csp-constant-single | CSP 策略单一来源 | grep CSP 常量定义与引用 | nginx 与 Python 同源（或各自文件注明对应关系） | 正例 |
| T-T2-11-json-csp-kept | API JSON CSP 保持 | GET `/api/v1/health` | 响应 CSP 存在（default-src 'self' 或新策略），不回归 | 回归 |
| T-T2-12-neg-ghpages-boundary | **负例：静态托管边界说明** | 文档/代码注明 GitHub Pages 无自定义响应头 → CSP 覆盖边界（meta 或文档） | 有明确说明（不静默声称全覆盖） | 负例 |
| T-T2-13-build-pass | 前端构建通过 | `npm run build`（若改前端源码） | 成功；产物与 CSP 方案匹配（hash 则同步） | 回归 |

## 附项验收

### F1 — 前端产物策略（B6 遗留联动）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-F1-01-decision-recorded | 裁决已记录 | 检查 spec-delta 附录 B7 | 小明裁决落盘（①源码验收 ②重建+发布 ③重建不发布） | 正例 |
| T-F1-02-neg-no-rebuild-without-decision | **负例：未裁决不重建** | 裁决前检查 out/ 提交状态 | 无未经裁决的产物提交 | 负例 |
| T-F1-03-ghpages-health | gh-pages 健康（若发布） | 裁决为②后检查线上 | 200 健康、404 兜底正常 | 回归 |

---

## 全局回归清单（每批后必跑）

```bash
# 局部（每批）
python3 -m pytest tests/test_api_auth_deep.py tests/test_auth_extended.py \
  tests/test_onboarding_e2e.py tests/test_security.py tests/test_v380_a1_auth_unify.py \
  tests/test_backlog_p1_v350.py tests/test_v361_critical_fixes.py -q

# 全量（P4/P6 后 + 收尾）— CI 等价口径
python3 -m pytest tests/ -q \
  --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py \
  --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py \
  --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py

# 前端（每次动前端源码后）
cd frontend && npm run build && npx tsc --noEmit && npm test
```

- 门禁：≥ 9953 passed / 0 failed（CI 等价口径）；覆盖率 ≥84.14% 不降（`--cov-fail-under` 按 CI 配置）。
- 安全债消失 grep 证据（复验必查）：
  1. `grep -rn "localStorage" frontend/src/lib/api.ts frontend/src/app/ --include="*.ts" --include="*.tsx"` → 仅 LOCALE_KEY 等非敏感 key（T1）
  2. `grep -rn "Authorization.*Bearer" frontend/src/ --include="*.ts" --include="*.tsx"` → 零命中（除测试 mock）（T1）
  3. `grep -rn "cdn.tailwindcss\|js.stripe.com\|fonts.googleapis\|fonts.gstatic" deploy/nginx/nginx.conf src/yuleosh/ui/server.py` → 零命中（T2）
  4. `grep -rn "Content-Security-Policy" src/yuleosh/ui/server.py` → 存在（HTML 响应路径）（T2）
  5. `grep -rn "yuleosh_at\|yuleosh_rt" src/yuleosh/ --include="*.py"` → 存在且含 HttpOnly（T1）
  6. `grep -rn "Set-Cookie.*yuleosh" src/yuleosh/ --include="*.py"` → 登录链路径存在（T1）

---

## 小马复验记录（2026-08-03 契约产出，复验待开发后执行）

> 复验人: 小马（Hermes QA）· 方式: 独立执行，不采信开发自报
> 状态: ⏳ 契约已落盘，待小克按批次开发后复验填写

| 验证项 | 结果 |
|--------|------|
| 全量回归（CI 等价口径） | ⏳ 待复验（基线 9953/0） |
| 覆盖率 | ⏳ 待复验（基线 ≥84.14%） |
| 前端 build + tsc + jest | ⏳ 待复验 |
| 安全债 6 项 grep | ⏳ 待复验 |
| B1-B8 裁决落地 | ⏳ 待小明裁决 |
| 手工浏览器登录链（cookie 模式） | ⏳ 待复验 |
| Tag v3.9.0 | ⏳ 待发布 |
