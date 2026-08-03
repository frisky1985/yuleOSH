# Spec-Delta — yuleOSH v3.9.0 变更点分析

> 版本: v3.9.0 · 基线: v3.8.0 (7e864e2) · 日期: 2026-08-03
> 用途: 小克开发变更清单 + 小马复验对照 + 老板风险知情
> 行号: HEAD=6d40b98 实测（部分与评审报告行号有偏移，以实测为准）
> ⚠️ 本版为前端安全版：T1 认证携带方式变更（localStorage JWT → 双 httpOnly cookie）改动面横跨前后端，第 1 节给出详细迁移步骤与回滚方案。

---

## 0. 变更总览

| ID | 变更文件 | 行为变化 | 兼容性影响 | 风险等级 |
|----|----------|----------|-----------|---------|
| T1 | `frontend/src/lib/api.ts` + 4 个页面 + `ui/auth_extended.py` + `api/middleware.py` + `ui/routes/auth_routes.py` + `store.py` | 认证携带方式：localStorage JWT → httpOnly 双 cookie（access 短期 + refresh） | **高（登录链、双链互认、桌面跨端口、API 客户端）** | 🔴 高 |
| T2 | `deploy/nginx/nginx.conf` + `ui/server.py` + `ui/routes/helpers.py` + `api/router.py` | CSP 头策略：清遗留放行 + 基础指令加固 + unsafe-inline/eval 收窄 | 中（页面可加载性必须保持） | 🟠 高 |
| F1 | 产物策略（out/ 与 gh-pages） | 待小明裁决（B6 遗留联动） | 中（发布面） | 🟡 中 |

---

## 1. T1 — token cookie 迁移（🔴 最高风险）

### 1.1 现状调用点清单（grep 证据，HEAD=6d40b98）

**前端（localStorage 存取面）**：
- `frontend/src/lib/api.ts`：`TOKEN_KEY`(:8)、`getToken`(:77-82)、`setToken`(:84-88)、`clearToken`(:90-94)、`redirectToLogin`(:96-101)、`request()` Bearer 注入(:111-118)、401→redirect(:121-128)、logout clearToken(:199)、导出(:572-575)
- 页面调用点：`login/page.tsx`（:76,87,139,153 setToken）、`register/page.tsx`（:15 import、:97 setToken）、`onboarding/page.tsx`（:17 import、:68,95,121 getToken 拼 Bearer）、`dashboard/page.tsx`（:54 import、:320 getToken、:553 getToken 判渲染）
- 测试面：`frontend/src/__tests__/api.test.ts`（11 用例，大量 localStorage 断言）、`login.test.tsx`（8 用例，mock setToken）

**后端（签发/校验面）**：
- 签发：`ui/auth_extended.py._generate_token`(:298-311，exp = now + 72h)、`_create_login_response`(:725-729)、`handle_signin`(:463-554)、`handle_org_create`(:557-614)、`register`(:400-460)
- 会话：`store.py.create_session`(:496-513，sha256 落库)、`get_session`(:515-522)、`delete_session`(:524-527)；`user_sessions` 表(:133-139)
- 读取：`api/middleware.py._extract_token`(:45-56，仅 Authorization)、`ui/routes/auth_routes.py._get_bearer_token`(:147-158，仅 Authorization)
- 既有 cookie 先例：`ui/auth.py.create_session`/`validate_session`(:58-82)、`auth_routes.py` Set-Cookie `osh_session`(:76-79，HttpOnly; SameSite=Lax; Path=/; Max-Age=86400)

### 1.2 文件级变更清单

| 文件 | 变更 | 删除/新增 |
|------|------|-----------|
| `frontend/src/lib/api.ts` | `setToken`/`clearToken` 去 localStorage（降级内存或删除）；`request()` 去手工 Bearer（浏览器自动带 cookie）；401 处理保留 redirectToLogin 兜底；新增 refresh 重试逻辑（401→refresh→重放一次）；`TOKEN_KEY` 常量语义变更或移除 | 删 localStorage 写入；新增 refresh 流程 |
| `frontend/src/app/login/page.tsx` | `setToken(result.token)` 4 处 → 删除（cookie 由服务端 Set-Cookie，前端不再落盘）；needs_org 分支逻辑保留 | 删 4 处 setToken |
| `frontend/src/app/register/page.tsx` | 同上（:97） | 删 1 处 |
| `frontend/src/app/onboarding/page.tsx` | `getToken()` 拼 Bearer 3 处 → 去手工头（cookie 自动携带）；保留 fetch 结构 | 删 Bearer 拼接 |
| `frontend/src/app/dashboard/page.tsx` | `getToken()` 判会话（:320,553）→ 改为无 token 依赖的会话判定（如直接调 session 端点或信任 cookie 存在性） | 语义改造 |
| `frontend/src/__tests__/api.test.ts` | localStorage 断言全部改为 cookie/无 token 语义；新增 refresh 用例 | 大量修改 |
| `frontend/src/__tests__/login.test.tsx` | mock setToken 相关断言适配 | 适配 |
| `src/yuleosh/ui/auth_extended.py` | `_create_login_response`/`handle_org_create`/`register` 返回新增 cookie 下发所需信息（或由路由层统一 Set-Cookie）；新增 refresh 实现（端点或函数）；`SESSION_TTL_HOURS` 拆分 access/refresh 两档（或新增 `ACCESS_TTL_HOURS`） | 新增 refresh；常量拆分 |
| `src/yuleosh/ui/routes/auth_routes.py` | `_get_bearer_token` 支持 cookie 回退；`handle_api_action` 对 signin/org_create 成功响应 Set-Cookie 双 cookie；logout 响应清 cookie；新增 `/api/auth/refresh` 路由（若走独立端点方案） | 新增 cookie 读写 |
| `src/yuleosh/api/middleware.py` | `_extract_token` 支持 cookie 回退（无 Authorization 时读 `yuleosh_at`） | 新增回退 |
| `src/yuleosh/store.py` | `create_session` 支持不同 TTL（access/refresh 两行或一表两字段）；`get_session` 不变 | 参数化 TTL |
| `src/yuleosh/ui/auth.py` | `is_authenticated` 委托链追加租户 cookie 判定（在 Bearer 之前或之后，语义等价即可） | 追加分支 |
| `src/yuleosh/api/cors.py` / `ui/routes/helpers.py` | 若桌面走 cookie 模式：`Access-Control-Allow-Credentials: true` + 具体 Origin（不得 `*`）；`Access-Control-Allow-Headers` 确认含 Cookie（实际浏览器不发自定义头则无需） | 视 B4 裁决 |

### 1.3 行为变化

1. **登录成功响应新增 `Set-Cookie`**（access + refresh 双 httpOnly cookie）—— JSON body 不变（token 字段保留，兼容旧前端与 API 客户端）。**这是纯增量**，v3.8.0 客户端无感知。
2. **前端不再把 JWT 写 localStorage** —— XSS 窃取面关闭（S-P2-03 落地）。行为变化：刷新页面后会话由 cookie 保持（不再读 localStorage）。
3. **access token 寿命从 72h 收窄**（建议 ≤30min）—— 会话存活依赖 refresh 续期；若 refresh 机制未就绪，用户 30min 后需重新登录（**上线顺序：先 refresh 后收窄 TTL**，见 1.5）。
4. **middleware/auth_routes 接受 cookie 携带的 token** —— 对"无 Authorization 头的浏览器请求"从 401 变为 200（行为扩展，鉴权判定语义不变）。
5. **桌面跨端口拓扑**：若走 cookie 模式，fetch 需 `credentials: 'include'` + CORS Allow-Credentials（现状 dev 模式 `*` 与 credentials 不兼容，需改造）；若走 Bearer 模式则无变化（B4 裁决）。
6. **logout 清 cookie** —— 从"仅删 DB session"变为"删 DB session + 清双 cookie"。

### 1.4 兼容性影响（按调用方）

| 调用方 | 影响 |
|--------|------|
| 前端 SPA（登录链） | 行为不变（token 字段仍返回）；存储方式变 cookie；无感续期新增 |
| 旧版前端（未升级 bundle） | **兼容**：Set-Cookie 被浏览器忽略接收即可，旧逻辑仍走 Bearer（token 字段保留） |
| API 客户端（curl/集成） | 零变化（继续 Bearer；cookie 不强制） |
| legacy X-API-Key / osh_session | 零变化（独立机制保留） |
| 桌面 app（18789→18788） | 若 B4 走 cookie：需 credentials + CORS 改造；若走 Bearer：零变化 |
| 测试套件 | `test_onboarding_e2e.py` 系 + `test_v380_a1_auth_unify.py` + `test_security.py` 需全绿；新增 cookie 用例 |
| DB 既有 session | `user_sessions` 表结构若扩展需迁移（可空列/新表，避免破坏既有行） |

### 1.5 迁移步骤（开发顺序，每步独立 commit）

> 每步完成后跑局部回归：`tests/test_api_auth_deep.py tests/test_auth_extended.py tests/test_onboarding_e2e.py tests/test_security.py tests/test_v380_a1_auth_unify.py -q`

- **Step 0（前置）**：抽出 cookie 名/属性常量（`yuleosh_at`/`yuleosh_rt` + HttpOnly/SameSite/Path/Secure 策略），全部 Set-Cookie 走同一 helper（单一来源，避免拼写漂移）。
- **Step 1（后端签发时下发 cookie）**：signin/org_create/register 成功响应 Set-Cookie access+refresh；**token 字段保留返回**。回归：登录链 E2E + 新增 cookie 存在性用例。**本步行为纯增量，最安全。**
- **Step 2（后端 cookie 回退读取）**：middleware `_extract_token` 与 auth_routes `_get_bearer_token` 支持无 Authorization 时读 access cookie；`is_authenticated` 链追加租户 cookie 分支。回归：双链互认 + 负例（伪造 cookie 401）。**本步是行为风险最大单点**（所有浏览器请求的鉴权路径）。
- **Step 3（refresh 续期）**：实现 refresh（端点或滑动），前端 401→refresh→重放。回归：续期正例 + refresh 失效负例。
- **Step 4（前端去 localStorage）**：api.ts + 4 页面改造，删除 setToken/getToken 的 localStorage 语义。回归：前端 jest + 手工浏览器登录链。
- **Step 5（TTL 收窄）**：access TTL 72h→裁决值；refresh TTL 落地。回归：过期/续期边界用例。
- **Step 6（收尾）**：全量回归 9953+/0 + 覆盖率 ≥84.14% + 前端 build/tsc/jest + 手工浏览器验证。

### 1.6 回滚方案

| 步骤 | 回滚方式 | 影响面 |
|------|----------|--------|
| Step 1 | revert commit → 不再 Set-Cookie（浏览器忽略旧 cookie 无副作用） | 零（JSON body 未变） |
| Step 2 | revert → middleware 恢复仅 Authorization（v3.8.0 原状） | 零（cookie 回退消失，前端仍走 Bearer 直到 Step 4） |
| Step 3 | revert → refresh 端点消失（前端 refresh 调用 404 → 走 redirectToLogin 兜底） | 低（回到 72h token，功能可用） |
| Step 4 | revert → 前端恢复 localStorage（需同步恢复 Step 1 的 cookie 或同时回退 Step 1-3） | 中（**Step 4 与 Step 1 必须同进退**：前端若不再存 token 而后端不设 cookie 则登录链断） |
| Step 5 | revert → TTL 恢复 72h | 低 |

- **关键回滚耦合**：Step 1（后端设 cookie）与 Step 4（前端去 localStorage）是**一对**——回滚其一必须回滚另一个，否则登录链断裂（前端无 token 可发、后端无 cookie 可验）。中间态（Step 2/3 已上、Step 4 未上）是安全的（前端仍走 Bearer）。
- 风险兜底：Step 2 前打 tag（如 `v3.9.0-t1-step2-before`），便于快速 diff。

### 1.7 前端登录链兼容验证方案

1. **自动化**：`test_onboarding_e2e.py` 系扩展 cookie 模式用例：signin（断言 Set-Cookie）→ org/create → session（无 Authorization 头）→ project/list → stats/overview（无 Authorization 头）全链路 200。
2. **交叉验证**：cookie 携带的 token 与 Bearer 携带的同一 token 解析同一 user（middleware 双路径等价）。
3. **负例**：篡改/伪造 access cookie → 401（fail-closed）；refresh 过期 → 401 + cookie 清除。
4. **手工**（小马复验）：浏览器登录 → 建组织 → dashboard 数据加载 → 刷新页面会话保持（cookie）→ 登出后 cookie 消失。

---

## 2. T2 — CSP Phase 1（🟠 高）

### 2.1 现状（grep 证据）

- **nginx（唯一页面级 CSP）**：`deploy/nginx/nginx.conf:88` —— `script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://js.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-src 'self' https://js.stripe.com; img-src 'self' data: blob:; connect-src 'self' https://api.stripe.com; object-src 'none'; base-uri 'self';`
- **产物实测**：`frontend/out/` 中 `cdn.tailwindcss.com`/`js.stripe.com`/`fonts.googleapis.com`/`fonts.gstatic.com` **零引用** → 放行清单是遗留，可清。
- **Python 侧**：`ui/server.py._add_security_headers`(:193-197) 无 CSP；`ui/routes/helpers.py:73` 与 `api/router.py:210` 仅 JSON 响应 `default-src 'self'`。
- **静态导出内联脚本**：每页 6 个 `<script>` 内联块（`self.__next_f.push([...])`，RSC flight data）；`index.html` 31 个内联 `style=` 属性。
- **'unsafe-eval' 依赖**：`frontend/out/_next/static/chunks/0cz1d0mv5g_q7.js` 含 `Function("return this")`（runtime global-this 兜底）。
- **XSS 基线**：v3.6.1 X-01（`frontend/src/lib/markdown.ts` escapeHtml 先转义 + `kb/models._strip_html` 服务端消毒）已就位。

### 2.2 文件级变更清单

| 文件 | 变更 |
|------|------|
| `deploy/nginx/nginx.conf:88` | CSP 重写：删 4 个外域放行；`script-src` 用 nonce/hash 或最小 `'unsafe-inline'`（B5 裁决）；`style-src-attr 'unsafe-inline'`（若保留内联样式）；补 `object-src 'none'; base-uri 'self'; frame-ancestors 'self'` 等 |
| `src/yuleosh/ui/server.py` | `_add_security_headers`（或新增 `_add_csp_header`）对 HTML 响应带 CSP；策略常量与 nginx 同源（如 `CSP_POLICY` 常量） |
| `src/yuleosh/ui/routes/helpers.py:73` / `api/router.py:210` | JSON 响应 CSP 保持或对齐新策略（JSON 场景 `default-src 'self'` 即可，无需改）；若抽公共常量则两处引用同一来源 |
| `frontend/out/`（若 B7 重建） | 重建后验证内联脚本 hash/nonce 与新产物匹配 |
| 文档 | `docs/cybersecurity-baseline.md` CSP 行更新（现 :226 附近 XSS 条目） |

### 2.3 行为变化与兼容性

- **行为变化**：页面级 CSP 从"nginx 宽放行"变为"收窄 + 明确指令"；Python 侧 HTML 响应从"无 CSP"变为"有 CSP"（纯增量 HTTP 头）。
- **兼容风险点**：① 内联 RSC 脚本若 nonce 方案，Python 服务端需在 `_serve_static` 输出前改写 HTML（注入 nonce 属性）—— 实现复杂度 + 性能（每请求正则改写，需基准）；② hash 方案需构建产物与 CSP 同步（重建耦合）；③ `Function("return this")` 若移除 'unsafe-eval' 需验证 runtime 不执行（或改造构建配置）。
- **GitHub Pages 边界**：静态托管无自定义响应头 → CSP 头方案在 gh-pages 不生效（B8 裁决 meta CSP 或文档注明）。

---

## 3. 兼容性影响汇总表（按调用方）

| 调用方 | 受影响项 | 影响 |
|--------|----------|------|
| 前端 SPA（登录链） | T1 | 存储方式变 cookie；无感续期；行为不变（token 字段保留） |
| API 客户端（/api/v1/* + /api/auth/*） | T1 | Bearer 零变化；cookie 为增量 |
| legacy X-API-Key / osh_session | T1 | 零变化（独立机制） |
| 桌面 app（跨端口） | T1 | B4 裁决：cookie（需 credentials+CORS 改造）或 Bearer（零变化） |
| 浏览器页面加载 | T2 | CSP 收紧，需验证无 violation；外域资源零引用不受影响 |
| 部署（nginx） | T2 | nginx.conf 变更，重载生效；`add_header` 作用域需确认（location 级继承） |
| DB 既有数据 | T1 | user_sessions 表扩展需向后兼容（新列可空/新表） |
| 测试套件 | T1 最甚 | 前端 api.test.ts 大改；后端新增 cookie/refresh 用例；X-01 测试保持全绿 |

---

## 4. 附录 A：T1/T2 复验用原始命令

```bash
# T1: 前端 localStorage 残留（迁移后应为零）
grep -rn "localStorage.*yuleosh_token\|TOKEN_KEY" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v __tests__

# T1: 手工 Bearer 注入残留（迁移后应为零）
grep -rn "Authorization.*Bearer" frontend/src/ --include="*.ts" --include="*.tsx" | grep -v __tests__

# T1: 服务端 cookie 回退存在
grep -rn "yuleosh_at\|yuleosh_rt\|osh_session" src/yuleosh/ --include="*.py" | grep -v __pycache__

# T2: 外域放行清零
grep -n "cdn.tailwindcss\|js.stripe.com\|fonts.googleapis\|fonts.gstatic" deploy/nginx/nginx.conf src/yuleosh/ui/server.py

# T2: Python HTML 响应 CSP 存在
grep -rn "Content-Security-Policy" src/yuleosh/ui/server.py

# 全量回归（CI 等价口径，v3.8.0 基线 9953/0）
python3 -m pytest tests/ -q \
  --ignore=tests/test_e2e.py --ignore=tests/test_e2e_pipeline.py \
  --ignore=tests/test_alpha01_full_flow.py --ignore=tests/test_alpha02_onboarding.py \
  --ignore=tests/test_onboarding_e2e.py --ignore=tests/ci/test_e2e_report_pipeline.py

# 前端
cd frontend && npm run build && npx tsc --noEmit && npm test
```

## 5. 附录 B：待小明裁决事项（阻塞性，先裁决再开发）

> ✅ **裁决结果（2026-08-03 老板确认「按推荐」）**：8 项全部按推荐方案落定，见下表「裁决」列。

| # | 事项 | 选项 | 影响 | 建议 | 裁决 |
|---|------|------|------|------|------|
| B1 | cookie 命名与属性 | access `yuleosh_at` + refresh `yuleosh_rt`（建议）；或单 cookie `yuleosh_token` | T1 实现 | 双 cookie 命名，避免与 osh_session 混淆 | | ✅ 双 cookie：yuleosh_at + yuleosh_rt
| B2 | refresh 机制形态 | ① 独立端点 `POST /api/auth/refresh`（推荐，显式可控）② 滑动续期（signin 重签） | T1 续期语义 | ① 独立端点（便于限流与轮换） | | ✅ 独立端点 POST /api/auth/refresh
| B3 | CSRF 深度 | ① SameSite=Lax + JSON 头（基线，推荐 Phase 1）② 加 Origin 校验 ③ Strict | T1 安全面 | ①（登录链跨站风险已由 SameSite 覆盖，Phase 2 再评估） | | ✅ SameSite=Lax + JSON 头基线（Phase 1）
| B4 | 桌面跨端口携带方式 | ① cookie + credentials:'include' + CORS Allow-Credentials（改造面）② desktop 保持 Bearer（推荐，零改造） | 桌面兼容 | ② desktop 保持 Bearer；cookie 模式服务端能力照做，desktop 不强制切换 | | ✅ desktop 保持 Bearer（零改造）
| B5 | CSP script-src 内联方案 | ① nonce（服务端 HTML 改写，最强）② hash（构建耦合）③ 保留最小 `'unsafe-inline'` + 注释（最快，Phase 2 再收） | T2 实现量与安全收益 | ③ 保底 + ① 若小克评估可行（估时 +0.5d） | | ✅ 保底最小 unsafe-inline + 小克评估 nonce（可行则 +0.5d）
| B6 | 'unsafe-eval' 处置 | ① 构建配置消除 `Function("return this")` 后移除 ② 保留 + 注释证据 | T2 收窄度 | ① 先试（webpack output.globalObject 等价项），失败则 ② | | ✅ 先试构建消除 Function("return this")，失败则保留+注释
| B7 | 前端产物策略（F1） | ① 源码验收不重建（延续 B6）② 重建+发布 GitHub Pages ③ 重建不发布 | 发布面 | ② 推荐（v3.9 动前端，线上产物应同步；但需小明确认 gh-pages 更新流程） | | ✅ 重建产物并发布 GitHub Pages
| B8 | GitHub Pages CSP 覆盖 | ① HTML meta CSP（等价降级）② 文档注明边界不设 | T2 覆盖边界 | ① 若重建产物则顺带；否则 ② | | ✅ 重建则顺带 HTML meta CSP，否则文档注明边界
