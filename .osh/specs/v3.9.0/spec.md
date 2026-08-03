# Spec — yuleOSH v3.9.0（Track3 前端安全）

> 版本: v3.9.0 · 基线: v3.8.0 (7e864e2) · 日期: 2026-08-03
> 方法: OpenSpec（SHALL/SHOULD/MAY + GIVEN/WHEN/THEN）
> 依据: `~/.openclaw/workspace/plans/yuleOSH-v3.7-roadmap.md`（方案 A：v3.9.0 = Track3 前端安全）+ `TASK_STATUS.md`（v3.9.0 排期：T1 双 Cookie HttpOnly access+refresh 2.5d / T2 CSP Phase 1 1.5d）+ `frontend/src/lib/api.ts` S-P2-03 SECURITY NOTE + v3.8.0 spec.md:291（Track3 排期确认）
> 上游裁决: 小明（需求）· 开发: 小克 · 复验: 小马（本文档为复验依据）
> 范围说明: Track3 前端安全 = T1 token cookie 迁移 + T2 CSP Phase 1；yuleASR-Configurator 另行排期。本文档不涉及。
> 行号证据: 全部为 HEAD=6d40b98（v3.8.0 发布后）实测，与评审报告行号可能有偏移，以实测为准。

---

## 0. 需求编号规则

- 每项需求编号 `SHALL-T1.x`（T1 子项）/ `SHALL-T2.x`（T2 子项）/ `SHALL-Fx.n`（附项），x = 项号，n = 条款序号。
- 测试 ID 规则见 `acceptance-matrix.md`（`T-T1.x-xxx` / `T-T2.x-xxx`），负例统一后缀 `-neg`。
- 验收判定：**所有 SHALL 条款有对应测试（正例 + 负例）且全绿**，方视为该项完成。
- 全局回归基线（v3.8.0）: **9953 passed / 0 failed**（CI 等价口径，71 skipped / 11 xfailed）；覆盖率 ≥ **84.14%** 不降。

---

## 1. T1 — token cookie 迁移（来源 S-P2-03，估时 2.5d）

### 现状（grep 证据，HEAD=6d40b98）

**前端侧（localStorage 存 JWT）**：

| 位置 | 行号 | 现状 |
|------|------|------|
| `frontend/src/lib/api.ts` | :8 | `TOKEN_KEY = "yuleosh_token"`（localStorage key） |
| 同上 | :10-17 | SECURITY NOTE S-P2-03：token 存 localStorage（非 httpOnly），XSS 可窃取；建议 httpOnly cookie / BFF / 短期+轮换 |
| 同上 | :77-99 | `getToken`/`setToken`/`clearToken` 读写 localStorage；`redirectToLogin` 清 token 跳 /login |
| 同上 | :111-118 | `request()` 每次请求附 `Authorization: Bearer <token>` |
| 同上 | :121-128 | 401 → `redirectToLogin()` |
| `frontend/src/app/login/page.tsx` | :76,87,139,153 | `setToken(result.token)`（登录/注册/建组织后写 localStorage） |
| `frontend/src/app/register/page.tsx` | :15,97 | `setToken(orgResult.token)` |
| `frontend/src/app/onboarding/page.tsx` | :68,95,121 | `getToken()` 手动拼 Bearer 调 /api/v1/* |
| `frontend/src/app/dashboard/page.tsx` | :320,553 | `getToken()` 判会话存在 |

**后端侧（会话机制现状）**：

| 位置 | 行号 | 机制 |
|------|------|------|
| `ui/auth_extended.py` | :38 | `SESSION_TTL_HOURS = 72`（**当前 token 72h 长寿命**） |
| 同上 | :298-311 | `_generate_token` 签发 JWT（`sub`/`org`/`email`/`iat`/`exp`，HS256） |
| 同上 | :327-378 | `verify_token`（A1 统一 verify：签名 + DB session 行 + user 行） |
| 同上 | :386-428 | `get_session_user`（含 org 解析，供页面会话） |
| 同上 | :463-554 | `handle_signin`（限流 + 密码校验 + `_create_login_response`） |
| 同上 | :557-614 | `handle_org_create`（建 org + user + 首项目 + session） |
| 同上 | :642-647 | `handle_logout`（删 DB session） |
| `store.py` | :496-527 | `create_session`/`get_session`/`delete_session`（**sha256(token) 落库**，P1-6） |
| `api/middleware.py` | :45-56 | `_extract_token` 仅从 **Authorization 头**取 Bearer |
| 同上 | :86,90 | 无 token → 401（fail-closed） |
| `ui/routes/auth_routes.py` | :147-158 | `_get_bearer_token` 仅从 **Authorization 头**取 |
| `ui/auth.py` | :58-82 | **既有** `create_session`/`validate_session`（HMAC 签名 session cookie，legacy 独立机制） |
| 同上 | :210-211 | `osh_session` cookie 校验（HttpOnly; SameSite=Lax; Path=/; Max-Age=86400，见 auth_routes.py:78-79） |
| `ui/auth.py` | :178-219 | `is_authenticated` 委托链：API key → osh_session cookie → Bearer→get_session_user |

**关键结论**：
1. **前端登录链全链路靠 localStorage JWT + Bearer 头**，S-P2-03 明示这是 XSS 窃取面。
2. **服务端已有 httpOnly cookie 先例**：legacy `osh_session`（HMAC + 内存，24h）——但它是 API-key 时代的独立机制，**不含租户 JWT 语义**，T1 不消灭它（SHALL-A1.9 保留机制）。
3. **租户 JWT 目前只有 Bearer 一种携带方式**；middleware 与 auth_routes 均无 cookie 回退读取。
4. **token 72h 长寿命**，与"短期 token 策略"（S-P2-03 建议）相悖。
5. 双 Cookie（access + refresh）是 TASK_STATUS 排期既定方向（"双 Cookie HttpOnly access+refresh"）。

### SHALL 条款

- **SHALL-T1.1（双 Cookie 下发）**: 登录成功路径（`handle_signin`、`handle_org_create`、v1 `register`）在返回 JSON 的同时，必须经响应头下发 **access + refresh 双 httpOnly cookie**（`HttpOnly; SameSite=Lax; Path=/`；生产环境（HTTPS）加 `Secure`，dev 不强制）；cookie 名不得与既有 `osh_session` 冲突（建议 `yuleosh_at` / `yuleosh_rt`，具体见附录 B1）。
- **SHALL-T1.2（access 短期化）**: access token 寿命必须显著短于现状（`SESSION_TTL_HOURS=72` 为上限基准，建议 ≤30min，具体值小明裁决）；refresh token 寿命 ≥ access（建议 7d，具体值裁决）；DB `user_sessions.expires_at` 与 refresh 寿命对齐。
- **SHALL-T1.3（前端去 localStorage）**: `frontend/src/lib/api.ts` 的 `setToken`/`clearToken` 必须停止写入/删除 localStorage 中的租户 JWT（`TOKEN_KEY` 语义移除或降级为仅内存）；`request()` 不得再手工拼 `Authorization: Bearer`（由浏览器自动携带 cookie）；登录/注册/onboarding/dashboard 页面的 `setToken`/`getToken` 调用点全部按新语义改造。
- **SHALL-T1.4（服务端 cookie 回退读取）**: `api/middleware.py._extract_token` 与 `ui/routes/auth_routes.py._get_bearer_token` 必须支持"无 Authorization 头时回退读取 access cookie"；同一合法/非法/过期 token 无论经 Bearer 还是 cookie 携带，判定结果必须一致（fail-closed 语义保持）。
- **SHALL-T1.5（refresh 续期）**: 必须提供 refresh 机制（独立端点 `POST /api/auth/refresh` 或复用 session 滑动续期，方案见附录 B2）：access 过期后前端可无感续期（401 → 自动 refresh → 重放原请求一次）；refresh 失败/过期 → 清理双 cookie → 跳 /login。
- **SHALL-T1.6（logout 全清）**: `handle_logout` 除删除 DB session 外，必须同时清除 access + refresh cookie（`Max-Age=0`）；前端 `logout()` 不再依赖 `clearToken`。
- **SHALL-T1.7（Bearer 兼容保留）**: 非浏览器客户端（curl / API 集成 / 测试）继续可用 `Authorization: Bearer <token>`；cookie 模式与 Bearer 模式对同一 token 解析出同一用户（双链互认不回退，SHALL-A1.8 延续）。
- **SHALL-T1.8（legacy 机制保留）**: `ui/auth.py` 的 X-API-Key 与 `osh_session` cookie 为独立机制，必须保留原语义；新租户 cookie 不得与 `osh_session` 混用校验路径、不得覆盖其 key。
- **SHALL-T1.9（前端登录链全链路）**: `POST /api/auth/signin` → `POST /api/org/create` → `GET /api/auth/session` → `GET /api/project/list` → dashboard 数据端点（任一 `@require_auth`）在 **cookie 模式**下全链路可用，且响应字段与 v3.8.0 逐字段一致。
- **SHALL-T1.10（CSRF 基线）**: 状态变更端点（POST signin 除外，登录本身为 CSRF 低危）依赖 `SameSite=Lax` + JSON Content-Type 防 CSRF；cookie 必须带 `SameSite=Lax`（或按附录 B3 裁决升级 Strict/Origin 校验）。
- **SHALL-T1.11（无 token 落盘）**: 迁移后前端 grep `localStorage.setItem(TOKEN_KEY)` 或等价租户 token 写入**零命中**；仅 `LOCALE_KEY` 等非敏感偏好可留 localStorage。
- **SHALL-T1.12（桌面跨端口拓扑）**: desktop 场景前端（localhost:18789）跨端口调后端（localhost:18788）时，若走 cookie 模式，fetch 必须 `credentials: 'include'` 且 CORS 响应必须 `Access-Control-Allow-Credentials: true` + 具体 Origin（不得 `*`）；若不可行，desktop 可保持 Bearer 模式（附录 B4 裁决，验收以行为为准）。
- **SHOULD-T1.13（令牌轮换）**: refresh 每次续期应签发新 refresh（轮换），旧 refresh 失效；如选滑动续期方案则 access 重签时更新 `expires_at`。本项为 SHOULD（若 B2 裁决独立 refresh 端点，本项升 SHALL）。
- **MAY-T1.14（同源跳转兼容）**: `redirectToLogin()` 保留（401 无感续期失败时兜底），但不得再依赖 localStorage 清理。

**GIVEN/WHEN/THEN**

- GIVEN 浏览器 POST `/api/auth/signin`（合法凭据），WHEN 响应返回，THEN 200 且 `Set-Cookie` 含 access+refresh 双 httpOnly cookie（HttpOnly; SameSite=Lax; Path=/），JSON body 与 v3.8.0 一致（token 字段保留）。
- GIVEN 已登录浏览器（cookie 就位），WHEN 访问 `GET /api/auth/session` 与任一 `@require_auth` 的 `/api/v1/*` 端点，THEN 200（凭 cookie 鉴权，无 Authorization 头）。
- GIVEN 同一 JWT，WHEN 分别经 `Authorization: Bearer` 与 access cookie 两种方式携带访问同一端点，THEN 判定结果一致（合法→200，伪造→401）。
- GIVEN access 过期而 refresh 有效，WHEN 前端请求 401 后调 refresh，THEN 新 access 签发、原请求重放成功（无感续期）。
- GIVEN refresh 也过期/无效，WHEN 前端调 refresh，THEN 401 + 双 cookie 被清除 + 前端跳 /login。
- GIVEN POST `/api/auth/logout`，WHEN 响应返回，THEN DB session 删除且双 cookie 清除（浏览器侧 Cookie 消失）。
- GIVEN X-API-Key 或 legacy `osh_session` cookie 请求 legacy 端点（如 `/api/evidence`），WHEN T1 迁移后访问，THEN 行为与 v3.8.0 一致（独立机制不受影响）。
- GIVEN 前端登录链完整走一遍（signin→org/create→session→project/list→dashboard），WHEN 全程无 Bearer 头（纯 cookie），THEN 全链路成功。

---

## 2. T2 — CSP Phase 1（来源 CSP，估时 1.5d）

### 现状（grep 证据，HEAD=6d40b98）

| 位置 | 行号 | 现状 |
|------|------|------|
| `deploy/nginx/nginx.conf` | :88 | CSP 头：`default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://js.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-src 'self' https://js.stripe.com; img-src 'self' data: blob:; connect-src 'self' https://api.stripe.com; object-src 'none'; base-uri 'self';` |
| `ui/server.py` | :193-197 | `_add_security_headers`：**无 CSP**（仅 X-Content-Type-Options/X-Frame-Options/X-XSS-Protection/Referrer-Policy） |
| `ui/routes/helpers.py` | :73 | API 响应 CSP：`default-src 'self'`（JSON 场景，非页面） |
| `api/router.py` | :210 | 同上 |
| `frontend/out/`（next export 产物） | 每页 | **6 个内联 `<script>`**（`self.__next_f.push(...)` RSC flight data）；`index.html` 31 个内联 `style=` 属性；dashboard 页 1 个 |
| `frontend/out/_next/static/chunks/0cz1d0mv5g_q7.js` | — | 含 `Function("return this")`（webpack/turbopack runtime global-this 兜底，**需要 'unsafe-eval'**） |
| `frontend/out/` | grep | `cdn.tailwindcss.com` / `js.stripe.com` / `fonts.googleapis.com` / `fonts.gstatic.com` **零引用**（nginx 放行清单是遗留） |
| `frontend/src/lib/markdown.ts` | :1-40 | v3.6.1 X-01 XSS 修复：`escapeHtml` 先转义后渲染（前端层） |
| `src/yuleosh/kb/models.py` | — | v3.6.1 服务端 `_strip_html` 消毒加固（写入路径双保险） |

**关键结论**：
1. **nginx CSP 是唯一页面级 CSP**，但含 4 个产物零引用的外域放行（cdn.tailwindcss / stripe / googlefonts）+ `'unsafe-inline'` + `'unsafe-eval'` —— 放行面远大于实际需要。
2. **Python 侧 HTML 响应无 CSP**（`_serve_static`/`_serve_file`），仅 JSON API 有 `default-src 'self'`。
3. **静态导出页面的内联 `<script>` 是 Next.js RSC flight data**（`self.__next_f.push`），无法直接用 `script-src 'self'` 禁内联 —— 需 nonce/hash 或最小化保留 `'unsafe-inline'`（Phase 1 = 收窄，非归零）。
4. `Function("return this")` 在产物中 → `'unsafe-eval'` 当前必需（或改造 runtime 配置移除，见 B6）。
5. v3.6.1 XSS 修复（X-01 转义 + 服务端消毒）是**内容层**防线；CSP 是**传输/执行层**第二道防线，两者并存（纵深防御）。

### SHALL 条款

- **SHALL-T2.1（Python 侧 HTML 补 CSP）**: `ui/server.py._serve_static`/`_serve_file` 对 HTML 响应必须带 CSP 头（当前缺失）；`_add_security_headers` 增加 CSP（或独立方法），策略与 nginx 同源（抽公共常量，避免双份漂移）。
- **SHALL-T2.2（清遗留外域放行）**: nginx 与 Python 的 CSP 中 `cdn.tailwindcss.com`、`js.stripe.com`、`fonts.googleapis.com`、`fonts.gstatic.com` 必须移除（产物零引用为证）；如 Stripe/fonts 后续启用，需在小明确认后单独加回并注明用途。
- **SHALL-T2.3（'unsafe-inline' 收窄）**: `script-src` 不得保留裸 `'unsafe-inline'`（除非 B5 裁决 hash/nonce 方案不可行）；Phase 1 目标：内联 RSC 脚本改为 **nonce 或 hash 白名单**（服务端 HTML 改写注入 nonce，或构建时算 hash 入 CSP），`'unsafe-inline'` 仅允许存在于 `style-src-attr`（内联 style 属性，静态导出现实依赖），并附代码注释说明用途。
- **SHALL-T2.4（'unsafe-eval' 处置）**: 评估 `Function("return this")` runtime：若能通过构建配置（`webpack`/`turbopack` 等价项）消除则移除 `'unsafe-eval'`；若不能，保留并在 CSP 注释 + spec-delta 注明**精确原因与文件证据**（B6 裁决）。
- **SHALL-T2.5（基础指令加固）**: CSP 必须含 `object-src 'none'; base-uri 'self'; frame-ancestors 'self'`（或按部署裁决 `'none'`）；`img-src 'self' data: blob:`（按产物实际引用）；`connect-src 'self'`；`form-action 'self'`。
- **SHALL-T2.6（XSS 纵深防御并存）**: CSP 落地不得回退 v3.6.1 X-01 修复（`escapeHtml` 先转义 + 服务端 `_strip_html`）；`frontend/src/__tests__/markdown.test.ts`（10 用例）与 `tests/test_kb_sanitize_xss.py`（15 用例）必须保持全绿。
- **SHALL-T2.7（页面可加载性）**: CSP 收紧后，`frontend/out/` 全部页面（index/dashboard/login/pricing 等）在浏览器加载**无 CSP violation**（console 零报错、脚本/样式/字体/图片正常渲染）；构建产物不因 CSP 变化而需重建（除非 B7 裁决重建）。
- **SHALL-T2.8（静态托管拓扑说明）**: GitHub Pages 静态托管无法自定义响应头 → Phase 1 明确：GitHub Pages 部署不承担 CSP 头（或采用 HTML meta CSP 等价方案，B8 裁决）；文档注明该拓扑的 CSP 覆盖边界。
- **SHOULD-T2.9（report 通道）**: 若部署支持，`report-uri`/`report-to` 可配（不阻塞发布；无上报后端时省略）。

**GIVEN/WHEN/THEN**

- GIVEN 浏览器 GET `/dashboard`（Python 服务，走 `_serve_static`/`_serve_file` 渲染 HTML），WHEN 响应返回，THEN 带 CSP 头（含 T2.1-T2.5 要求的指令），且页面加载无 console CSP violation。
- GIVEN 浏览器加载 `frontend/out/index.html`（含 6 内联 RSC script + 31 style 属性），WHEN 页面完全加载，THEN 交互正常（内联脚本经 nonce/hash 放行，样式经 style-src-attr 放行）。
- GIVEN nginx 生产配置，WHEN grep CSP 指令，THEN 无 cdn.tailwindcss.com / js.stripe.com / fonts.* 放行（T2.2）。
- GIVEN 注入 XSS 载荷（`<script>`/`<img onerror>`/`javascript:`）到 KB 内容，WHEN 页面渲染，THEN 载荷以惰性文本呈现且被 CSP 双保险拦截（T2.6，X-01 测试全绿）。
- GIVEN CSP 变更后重新构建前端（若重建），WHEN 检查产物，THEN 内联脚本 hash/nonce 方案与新产物匹配（无构建后失效）。

---

## 3. 附项（v3.9.0 收尾）

### F1 — 前端产物策略裁决联动（B6 遗留）

**现状**：v3.8.0 B6 裁决"前端产物不重建，以源码结构验收"；v3.9.0 T1/T2 均动前端源码（api.ts、页面、CSP），产物策略必须重新裁决。

- **SHALL-F1.1**: 小克开工前，小明必须裁决产物策略（① 源码验收 + 不重建 out/（延续 B6）② 重建 out/ 并发布 GitHub Pages ③ 仅重建不发布），裁决结果写入 spec-delta 附录 B7；未裁决前不重建产物。
- **SHALL-F1.2**: 无论产物是否重建，前端源码变更必须过 `npm run build` + `tsc --noEmit` + jest 全绿（验收矩阵 T-A6-01/02 等价项）。
- **MAY-F1.3**: 若裁决重建，GitHub Pages 更新与 tag v3.9.0 推送同日完成，且 404/安全头行为不回归。

**GIVEN/WHEN/THEN**

- GIVEN 小明裁决为"源码验收"，WHEN 开发完成，THEN out/ 不被提交，验收以源码 + 测试为准。
- GIVEN 小明裁决为"重建+发布"，WHEN tag v3.9.0 推送，THEN gh-pages 分支同步更新且线上 200 健康。

---

## 4. 全局约束（适用全部 T/F 项）

- **SHALL-G.1**: 所有行为变更项（T1 认证携带方式、T2 CSP）必须附带正例 + 负例测试，测试 ID 见 acceptance-matrix.md。
- **SHALL-G.2**: 全量回归基线（v3.8.0）**9953 passed / 0 failed**（CI 等价口径）不得下降（新增测试只增不减）；覆盖率 ≥ **84.14%** 不降。
- **SHALL-G.3**: 不引入新依赖（后端标准库优先；前端不新增 npm 依赖——cookie 读取用标准库 `http.cookies`/`SimpleCookie`，前端 fetch 原生 credentials 即可）。
- **SHALL-G.4**: 每项修复注明来源（`T1.x`/`T2.x` 注释），与既有 `W-x`/`M-x`/`A-x` 注释风格一致。
- **SHALL-G.5**: 变更不得破坏公开 API 契约：`/api/v1/*` 响应结构、错误码语义、`/api/auth/*` 登录链字段、CLI 子命令、既有测试全部保持。
- **SHOULD-G.6**: 小克开发过程中对 spec 有歧义处先问小马，不得自行扩大范围（尤其 B1-B8 待裁决项，见 spec-delta 附录 B）。
- **SHALL-G.7（依赖顺序）**: T1 与 T2 相互独立可并行；T1 内部顺序：① cookie 下发/回退读取（后端）→ ② 前端去 localStorage → ③ refresh 续期 → ④ 全量回归；T2 内部顺序：① 清遗留放行 → ② 基础指令加固 → ③ unsafe-inline/eval 收窄 → ④ 页面验证；每批后跑局部回归，收尾全量回归。

## 5. 明确不在本版范围（防范围蔓延）

- yuleASR-Configurator 安全项 → 另行排期
- W2 限流多 worker 共享存储（S-P2-02，既有 NOTE）→ 非本版
- GitHub OAuth 真接入（登录页按钮为静态占位）→ 非本版
- BFF（Backend-for-Frontend）代理方案（S-P2-03 提及的选项三）→ 非本版（双 cookie 方案替代）
- CSP Phase 2（全站 nonce 化、report-to 生产接入、Strict CSP 完全体）→ 后续版本
- 前端 1972 行 dashboard 之外的大重构 → 非本版
