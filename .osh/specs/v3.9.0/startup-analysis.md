# Startup Analysis — yuleOSH v3.9.0（Track3 前端安全）

> 版本: v3.9.0 · 基线: v3.8.0 (7e864e2) · 日期: 2026-08-03
> 方法: Superpowers S.U.P.E.R.（Situation / Understanding / Problem / Evaluation / Resolution）
> 决策: 老板 2026-08-02 已确认方案 A（v3.8.0=Track2 架构收敛 ✅ 已发布 → v3.9.0=Track3 前端安全）；v3.8.0 spec.md:291 排期：T1 2.5d + T2 1.5d ≈ 4 天

---

## S — Situation（现状）

- yuleOSH v3.8.0 (7e864e2) 已发布：**9953 passed / 0 failed**（CI 等价口径，71 skipped / 11 xfailed），覆盖率 **84.14%**；Track2 六项架构收敛 + 附项 F1-F4 全部落地；认证三套合一（A1）完成——**这是 v3.9.0 cookie 迁移的硬前置**（单一 verify/签发/secret 已就位）。
- 前端认证现状（grep 证据）：
  - `frontend/src/lib/api.ts:8` `TOKEN_KEY="yuleosh_token"` 存 **localStorage**；`:10-17` SECURITY NOTE S-P2-03 自认"XSS 可窃取，生产应 httpOnly cookie / BFF / 短期+轮换"。
  - 登录/注册/onboarding/dashboard 4 页 10+ 处 `setToken`/`getToken` 调用。
  - 服务端 token 寿命 **72h**（`auth_extended.py:38`）；携带方式**仅 Bearer**（middleware:45-56、auth_routes:147-158 均只读 Authorization 头）。
  - 既有独立机制：`ui/auth.py` `osh_session` cookie（HttpOnly; SameSite=Lax; 24h）+ X-API-Key —— 保留（A1 裁决）。
- CSP 现状：nginx（:88）是**唯一页面级 CSP**，含 4 个产物零引用外域放行 + `'unsafe-inline'` + `'unsafe-eval'`；Python HTML 响应无 CSP；next export 每页 6 个内联 RSC script + index.html 31 个内联 style 属性；产物含 `Function("return this")`（需 unsafe-eval）。
- v3.6.1 X-01 XSS 修复（前端 escapeHtml 先转义 + 服务端 _strip_html）已就位，CSP 为第二道防线。
- 遗留注意项（TASK_STATUS）：B6 前端产物不重建是 v3.8 裁决；v3.9 动前端，产物策略需重新裁决（F1/B7）。

## U — Understanding（理解）

**v3.9.0 的本质**：前端安全加固版——把 S-P2-03 明示的"localStorage JWT 可被 XSS 窃取"风险关掉（T1），并把唯一页面级 CSP 从"宽放行"收窄到"最小必要"（T2）。**不改产品功能，改安全边界**。

**为什么现在做（时机成熟）**：
1. **A1 认证合一是硬前置**：cookie 迁移需要"单一 verify/签发/secret"——v3.8.0 A1 已把三套认证并为一套（`verify_token` 统一、`JWT_SECRET` 单一来源、middleware 薄委托）。没有 A1，cookie 迁移要在三套认证上各改一遍，改动面 ×3。**A1 已完成，本版是"站在 A1 肩膀上收安全债"**。
2. **S-P2-03 是长期挂账**：`api.ts` 注释从 v3.6 就写明风险，每次 XSS 评审都点名；X-01 修了内容层，但存储层（localStorage）与执行层（CSP）未动——防线不完整。
3. **CSP 放行面与实际引用严重不符**：4 个外域零引用 + unsafe-inline/eval 双开 = 放行面远大于需要，属于"看起来有 CSP、实际兜不住"的隐患。
4. **双 cookie + 短期 token 是行业标准做法**：HttpOnly 阻断 XSS 读取、SameSite=Lax 阻 CSRF、短期 access + refresh 轮换限制泄露窗口——三重收益。

**与既有体系的关系**：T1 是 S-P2-03 方案二（httpOnly cookie），明确不选 BFF（方案三，另立服务太重）；T2 是 X-01 的纵深补充（内容层已修、执行层补齐）。

## P — Problem（问题定义）

**一句话**：如何在 **~4 天**内完成前端认证从 localStorage JWT → 双 httpOnly cookie（短期 access + refresh）迁移与 CSP 收窄，**不破坏 9953/0 基线、覆盖率 ≥84.14% 不降、前端登录链与双链互认零回归**，且 **v3.8 遗留 B6 产物策略得到明确裁决**？

**关键矛盾**：
- **迁移（localStorage→cookie）vs 兼容（token 字段保留、Bearer 保留）**：T1 必须做到"服务端纯增量、前端逐步切换、中间态安全"——任意一步回滚不连带登录链断裂（1.6 节回滚耦合分析）。
- **收窄（CSP）vs 可加载（next export 内联脚本）**：静态导出的 6 个内联 RSC script + 31 个内联 style 属性是硬约束，CSP 不能一刀切禁内联，必须 nonce/hash/最小保留三选一（B5）。
- **桌面跨端口拓扑**：frontend(18789) → backend(18788) 是跨 origin，cookie 模式需要 credentials+CORS 改造；是否强制桌面切换（B4）影响改动面。
- **产物策略悬空**：v3.8 B6 裁决"不重建"；v3.9 动前端源码，不重新裁决会导致"源码改了、线上产物旧了"的漂移。

**非目标**：GitHub OAuth 真接入、BFF、CSP Phase 2 完全体、yuleASR-Configurator、多 worker 限流。

## E — Evaluation（方案评估）

**优先级论证**：
1. **T1（cookie 迁移）先做**：它是 S-P2-03 安全债的核心（XSS 窃取面），且 A1 前置已就位、时机成熟；改动面横跨前后端，需要最多回归验证，先做早暴露风险。
2. **T2（CSP）可与 T1 并行**：改动文件不重叠（nginx/server.py vs auth/middleware/frontend），两线独立；但**F1 产物裁决（B7）是两者的共同前置**——若裁决重建产物，T2 的 hash/nonce 方案与产物耦合，需在产物重建后验证；若裁决不重建，T2 用保留 unsafe-inline 方案最省事。
3. **F1（产物裁决）是门禁**：不裁决不开发产物相关步骤（SHALL-F1.1）。

**开发批次设计**（依赖驱动）：

| 批次 | 内容 | 依赖 | 局部回归重点 |
|------|------|------|-------------|
| P0 | 附录 B 裁决（B1-B8，小明） | 无 | —（阻塞门禁） |
| P1 | T1 Step 0-1（cookie 常量 + 签发时下发双 cookie） | B1/B2 | test_onboarding_e2e + 新增 Set-Cookie 用例 |
| P2 | T1 Step 2（cookie 回退读取 middleware/auth_routes） | P1 | test_security + test_v380_a1 + 双链互认 |
| P3 | T1 Step 3（refresh 续期） | P2 | 续期正/负例 + test_api_auth_* |
| P4 | T1 Step 4-5（前端去 localStorage + TTL 收窄） | P3 | 前端 jest + 手工浏览器链 |
| P5 | T2（CSP 清放行 + 基础指令 + unsafe 收窄） | B5/B6/B8；可与 P1-P4 并行 | nginx 配置检查 + 页面无 violation |
| P6 | F1 产物（按裁决：重建+发布 or 不重建） | B7 | npm build + tsc + gh-pages 健康 |

**每批后局部回归**：`python3 -m pytest tests/test_api_auth_deep.py tests/test_auth_extended.py tests/test_onboarding_e2e.py tests/test_security.py tests/test_v380_a1_auth_unify.py tests/test_backlog_p1_v350.py -q`；P4/P6 后各跑一次全量 + 前端 build/tsc/jest。

## R — Resolution（决议）

### 为什么做（Why）
| 类别 | 项 | 价值 |
|------|-----|------|
| 安全 | T1 | 关闭 localStorage JWT XSS 窃取面（S-P2-03）；短期 token 缩小泄露窗口；SameSite=Lax 防 CSRF |
| 安全 | T2 | 页面级 CSP 从"宽放行"收窄到"最小必要"；清 4 个零引用外域；unsafe-inline/eval 收窄 |
| 纵深防御 | T2 | 与 v3.6.1 X-01 内容层消毒并存（执行层第二道防线） |
| 信任 | T1/T2 | 客户/评审可见的"前端安全已加固"证据（SAAS 演示面） |

### 优先级（P0 顺序）
1. **附录 B 裁决**（阻塞门禁，小明）
2. **T1 Step 1-2**（后端下发 + 回退读取，纯增量，最安全）
3. **T1 Step 3**（refresh 续期，TTL 收窄的前提）
4. **T1 Step 4-5**（前端去 localStorage + TTL 收窄，安全债闭环）
5. **T2**（CSP，可与 T1 并行）
6. **F1**（产物按裁决收尾）

### 成功标准（Done 定义）
1. T1/T2 全部 SHALL 条款有正例 + 负例测试，`acceptance-matrix.md` 全部 ✅；
2. 全量回归 ≥ 9953 passed / 0 failed（CI 等价口径）只增不减；覆盖率 ≥84.14% 不降；
3. 安全债消失的代码级证据：前端 grep `localStorage.*yuleosh_token` 与 `Authorization.*Bearer` 零命中（除测试 mock）；服务端 cookie 回退就位；nginx CSP 无零引用外域；
4. 前端登录链 cookie 模式 E2E 全绿 + 双链互认（cookie vs Bearer 同一 token 判定一致）+ 负例（伪造 cookie 401）；
5. X-01 XSS 测试（markdown 10 用例 + kb_sanitize 15 用例）保持全绿（T2.6）；
6. 附录 B 八个裁决项全部经小明确认并记录；F1 产物策略裁决落地；
7. 每步独立 commit 可回滚（T1 Step 4 与 Step 1 回滚耦合已记录）。

### 风险与缓解
| 风险 | 等级 | 缓解 |
|------|------|------|
| T1 Step 4 与 Step 1 回滚耦合（前端去 token 后若后端 cookie 缺失则登录链断） | 高 | 中间态安全设计：Step 2/3 上、Step 4 未上时前端仍走 Bearer；回滚必须成对；P4 前打 tag |
| T1 middleware cookie 回退改变浏览器请求鉴权路径（行为扩展） | 高 | Step 2 独立 commit + test_security 负例全绿 + 双链互认用例 + 可单独 revert |
| T1 refresh 续期竞态（并发 401 → 多次 refresh） | 中 | 前端 refresh 互斥（单飞）；后端 refresh 端点幂等/限流（复用 _ThreadSafeDict） |
| T2 内联 RSC 脚本 nonce 改写性能/正确性 | 中 | 先评估（B5 ③ 保底）；若改写则基准测试 + 页面加载 smoke |
| T2 'unsafe-eval' 移除导致 runtime 崩（Function("return this")） | 中 | B6 ① 先试构建配置消除；失败则 ② 保留 + 证据注释 |
| T2 CSP 收紧后页面资源被拦（样式/字体/图片） | 中 | 逐页浏览器验证无 violation（T2.7）；验收矩阵含页面加载用例 |
| F1 产物裁决延迟阻塞 T2 hash 方案 | 中 | B7 先裁决；裁决前 T2 用保留 unsafe-inline 方案推进（B5 ③） |
| 桌面跨端口 cookie 改造面（credentials+CORS） | 低 | B4 建议桌面保持 Bearer（零改造）；服务端 cookie 能力照做 |

### 验收负责人
- **开发**: 小克（按 spec.md SHALL 条款 + acceptance-matrix.md 测试清单；T1 分步 commit）
- **复验**: 小马（独立跑测试 + grep 安全债消失证据 + 浏览器手工登录链 + 附录 B 核验）
- **终审**: 小明（附录 B 八项裁决、F1 产物策略、CSP 方案路线）

### 时间盒
- 预估 **~4 天**（T1 2.5d + T2 1.5d，可并行压缩）。
- 上下文安全：本 session 产出四份契约文档后结束；开发阶段小克按批次推进，每批后小马复验。
