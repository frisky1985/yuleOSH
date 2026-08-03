# yuleOSH v3.9.0 Track3 前端安全 — 开发报告（小克 👨‍💻）

> 日期: 2026-08-04 · 契约: `.osh/specs/v3.9.0/`（spec / spec-delta / startup-analysis / acceptance-matrix）
> 基线: v3.8.0 发布（9953 passed / 0 failed，cov 84.14%）· 裁决: B1-B8 全部「按推荐」
> 提交链: bf17275(P1) → 71765ef(P2) → b3d31ad(P3) → 42e3cb2(P4) → 01f6eff(P5) → 1ce183f(P6)
> gh-pages: 63e1178 已推送 · tag: 待小马复验后打

---

## 1. 交付总览

| 批次 | 内容 | commit | 回归 |
|------|------|--------|------|
| P1 | T1 Step 0-1：双 cookie 常量 + 签发时下发 access/refresh + logout 清除 + _handle_api 双响应修复 | bf17275 | 408 passed |
| P2 | T1 Step 2：middleware/auth_routes/is_authenticated cookie 回退读取（双链互认） | 71765ef | 428 passed |
| P3 | T1 Step 3：POST /api/auth/refresh（轮换 + 失效清 cookie）+ jti 唯一化修复 | b3d31ad | 438 passed |
| P4 | T1 Step 4-5：前端去 localStorage + 401 无感续期 + needs_org 链 cookie 化 + jest 适配 | 42e3cb2 | 438 passed + 前端 33 |
| P5 | T2 CSP Phase 1：nonce 方案 + nginx 清放行 + unsafe-eval 移除 + meta CSP 脚本 | 01f6eff | 307 passed + Chrome 0 violation |
| P6 | F1：重建产物 + meta CSP + 保留独立静态页 + 发布 gh-pages | 1ce183f + gh-pages 63e1178 | 线上验证通过 |

## 2. 验收数字（CI 等价口径）

| 项 | 基线 v3.8.0 | v3.9.0 | 判定 |
|----|-------------|--------|------|
| 全量 passed | 9953 | **10017（+64，恰为新用例数）** | ✅ 只增不减 |
| 全量 failed | 0 | **0** | ✅ |
| 覆盖率 | 84.14% | **84.17%（+0.03）** | ✅ 门禁通过 |
| 前端 jest | 3 套件 | **33 passed**（api.test.ts 重写 + login 适配 + markdown 保持） | ✅ |
| tsc --noEmit / build | — | **全过** | ✅ |
| X-01 红线 | markdown 10 + kb 15 | **10 + 15 全绿** | ✅ |

## 3. 安全债消失证据（验收基线 5，grep 实测）

| # | 检查 | 结果 |
|---|------|------|
| 1 | `localStorage.*yuleosh_token` / `TOKEN_KEY`（frontend/src 除 __tests__） | 零命中 ✅ |
| 2 | `Authorization.*Bearer`（frontend/src 除 __tests__） | 零命中 ✅ |
| 3 | nginx 外域放行（cdn.tailwindcss / stripe / fonts.*） | nginx.conf 零命中（CSP 已整体移除，单一来源 Python）✅ |
| 4 | Python HTML 响应 CSP | `Content-Security-Policy` 在 server.py（_serve_static/_serve_file）✅ |
| 5 | 服务端 yuleosh_at / yuleosh_rt（含 HttpOnly） | 9 处引用，全部经 auth_cookies.make_auth_cookie（HttpOnly; SameSite=Lax; Path=/; Secure=生产）✅ |
| 6 | Set-Cookie 登录链路径 | auth_routes + router._respond 共 8 处 ✅ |

## 4. 前端登录链（cookie 模式）验证

wire 级（真实 HTTP + cookie jar，等价浏览器 cookie 行为）：
```
signin(needs_org) → 200 + yuleosh_at=org_setup(30min)  ← 无用户会话，仅 setup token
org/create        → 200 + 双 Set-Cookie（yuleosh_at + yuleosh_rt）
session           → 200（纯 cookie，无 Authorization 头）
project/list      → 200（纯 cookie）
v1 stats/overview → 200（纯 cookie，middleware 回退生效）
伪造 yuleosh_at   → session 401 + v1 401（fail-closed）
refresh（cookie） → 200 + 轮换（旧 rt 复用 401 + 双 cookie Max-Age=0 清除）
```
双链互认（T-T1-07）：同一 token 经 Bearer 与 cookie 判定一致（合法→200，伪造→401），测试覆盖。

**浏览器级说明**：生产路由 `/login`/`/dashboard` 等实际服务 legacy Python 模板页（见 §6 拓扑修正）；React app（frontend/out）部署于 gh-pages（演示面，无后端可达）。浏览器完整登录链建议小马用本地 Python 服务手工复验（`YULEOSH_AUTH_DISABLED=1` 或真实凭据），API 链已由 wire 测试全量覆盖。

## 5. 发现并修复的既有 bug（4 项，均有独立 commit 说明）

1. **`_handle_api` 双响应**（v3.4.0 引入，wire 实测 `{...}HTTP/1.0 200 OK...null` 拼接）—— 所有 `/api/auth/*`、`/api/org/*` 路由响应损坏；P1 修复（Set-Cookie 正确落在首个响应）。
2. **自动建组织流程永远 401**（v3.8.0 起）—— login/register 页 needs_org → createOrg 从未携带 org_setup token（页面未 setToken 且 request() 无 token 可发）；P4 修复：needs_org 的 signin 将 org_setup token 写入 `yuleosh_at` cookie（30min Max-Age；该 token 无法通过 verify_token 鉴权任何 API——sub=0 无 user 行），org/create 经既有 cookie 回退读取 → 纯 cookie 链可用。
3. **refresh 轮换失效根因**（P3 自测发现）—— JWT payload 对同秒完全确定（同 user/org/iat/exp → 同 token → 同 sha256 行），refresh 重签时 delete 后 INSERT OR REPLACE 又把同一行插回；加 `jti` 随机唯一修复。
4. **`_serve_file` 双 Content-Length**（P5 引入，Chrome `ERR_RESPONSE_HEADERS_MULTIPLE_CONTENT_LENGTH` 实测）—— nonce 改写前后各设一次；修复为改写后单次设置。

## 6. ⚠️ 契约前提修正（请小明/小马知悉）

**「产物零引用」仅对 frontend/out 成立，生产路由实际服务 legacy Python 模板页**：
- `/` → `ui/marketing/index.html`（引用 cdn.tailwindcss + fonts.googleapis）
- `/dashboard` → `ui/pages/dashboard-v5.html`（引用 fonts.googleapis）
- `/onboarding` → `ui/pages/onboarding.html`（引用 cdn.tailwindcss + fonts.googleapis）
- `/pricing`、`/en/*`、`/pipeline-flow` 同理

**处理**：CSP 按模板字节扫描（`_LEGACY_EXTERNAL`）追加模板实际引用的外域（Google Fonts → style-src/font-src；Tailwind CDN → script-src），即 T2.2 例外条款「实际在用，注明用途」；frontend/out（Next.js 产物，零外域引用）保持严格 nonce 策略；nginx 不设 CSP（单一来源 Python）。`js.stripe.com` 无任何模板引用，扫描器保留但永不触发。若小明裁决 legacy 模板也应外域清零（需同步替换模板资源引用，属视觉变更），可另开单处理。

**React app 接线说明**：frontend/out 在 Python 路由未接线（仅 /404 兜底），实际部署于 gh-pages（B7 裁决的「重建+发布」目标面）。此拓扑为 v3.8.0 既有状态，非本版引入。

## 7. T2 CSP 最终策略（Phase 1）

```
default-src 'self';
script-src 'self' 'nonce-<每请求随机>';          # 无 unsafe-inline / unsafe-eval
style-src 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline';
font-src 'self'; img-src 'self' data: blob:; connect-src 'self';
object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self';
[+ legacy 模板实际引用外域，按字节扫描追加]
```
- **B5**：nonce 方案可行（+0.5d 预算内）—— `_serve_static`/`_serve_file` 对 HTML 响应每请求注入 nonce + 改写内联 RSC `<script>`；无构建耦合。
- **B6**：`'unsafe-eval'` 已移除 —— 产物唯一 `Function("return this")` 为 core-js global 检测链兜底（`chunks/0cz1d0mv5g_q7.js`），`globalThis` 短路使该分支永不执行（Chrome 71+/FF 65+/Safari 12.1+ 均定义）；Chrome headless 实测 0 violation。无法通过构建配置消除（core-js 内部实现），以「死代码证据 + 注释」处置（B6 ② 路径，证据充分）。
- **B8**：gh-pages meta CSP 已注入（内联 RSC 脚本 sha256 hash 白名单 + style-src-attr unsafe-inline），17 页全部覆盖，线上验证生效；边界说明写入 docs/cybersecurity-baseline.md §12.5（T-T2-12-neg）。

## 8. Chrome headless 实测（T-T2-08 页面可加载性）

| 页面 | CSP violation |
|------|---------------|
| /dashboard | 0 |
| /（marketing index） | 0 |
| /pricing | 0 |
| /login | 0 |
| /onboarding | 0 |
| React out/index.html（meta CSP） | 0 |

## 9. 遗留与建议
- legacy 模板外域引用的长期方案（自托管 Tailwind/字体或模板替换）建议单独立项（Phase 2）
- `/org/setup` 静态页仍读 `localStorage('osh_token')`（legacy 独立流，不在 frontend/src 范围），建议后续清理
- desktop（B4=Bearer）零改造；服务端 cookie 能力已就位，desktop 未来可切
- CSP report-to/report-uri（SHOULD-T2.9）：无上报后端，本版省略

## 10. 验收矩阵对照
T-T1-01~24 全部实现（正例+负例），T-T2-01~13 全部实现，T-F1-01~03 落地（裁决已记录于 spec-delta 附录 B；out/ 提交仅 P6 裁决后；gh-pages 健康已验证）。详见各测试文件：
`tests/test_v390_t1_cookies.py`（16）/ `test_v390_t1_cookie_fallback.py`（20）/ `test_v390_t1_refresh.py`（10）/ `test_v390_t2_csp.py`（18），合计 **64 个新用例**。
