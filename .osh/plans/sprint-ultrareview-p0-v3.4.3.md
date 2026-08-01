# Sprint Contract — v3.4.3 ultra-review P0 安全修复

> 创建: 2026-08-01 20:30 | 负责人: 小克 👨💻（开发）/ 小马 🐴（评估）/ 小明 🔥（终审）
> 背景: 小马 ultra-review 全量深度检查（6.2/10），发现 4×P0 + 11×P1 + 8×P2（23 项）。本轮只修 P0（安全/架构阻塞），P1/P2 进 backlog。检查报告: `~/.openclaw/workspace/reports/ultra-review-2026-08-01/`（implementation-plan.md 含精确改法）

---

## ✅ 完成状态（2026-08-01 21:xx，小克 sub-agent）

| 项 | 状态 | 证据 |
|----|------|------|
| P0-1 v1 路由接线 | ✅ | 真实 server 启动 + curl：`/api/v1/health`→JSON 200；无 token→JSON 401；未知→JSON 404；缺 JWT secret 时 JSON 500（不再 HTML） |
| P0-2 require_auth fail-closed | ✅ | 无 handler→401；显式 current_user 注入→放行（测试通道）；无 token→401 |
| P0-3 webhook HMAC 校验 | ✅ | 有效签名→200；无效签名→401；secret 未配置→401（fail-closed） |
| P0-4 pipeline trigger 鉴权+路径白名单 | ✅ | 无 token→401；`/etc`→403；`../` 逃逸→403；type/layer 白名单→400；1MB 上限→400；节流→429；合法→job_id |
| 全量回归 | ✅ | 基线 9512 passed/0 failed → 本轮 **9543 passed / 0 failed**（CI 等价命令，351s） |
| 覆盖率 | ✅ | 基线 83% → 本轮 **83%**（TOTAL 43300 stmts，无下降） |
| backlog | ✅ | `.osh/plans/backlog-p1p2-ultrareview-v3.4.3.md`（11×P1 + 8×P2，不修） |
| commit + push | ✅ | 见下方修复对照表 |

---

## 1. P0 清单（全部修复）

### P0-1: v1 模块化路由未接线（三审一致 ★★★ + 小马运行时验证）
- 现象: 真实启动 server 探测 `/api/v1/health`、`/api/v1/dashboard/projects` 等返回 200+HTML 404 页而非 JSON；前端 dashboard/KB 不可用
- 代码现状: `api_v1_dispatch` 存在于 ui/server.py:123，被 handler_helpers.py:71/281 调用；但小马运行时探测不可达
- 任务: **先复现**（真实启动 server + curl 探测）→ 定位断点 → 修复接线（或明确下线 v1 二选一，需说明理由）→ 补"真实 server 启动 + JSON 探测"集成测试
- ⚠️ 注意: tests/test_ui_server.py 有 3 个相关单测通过，需解释"单测绿但运行时 404"的矛盾（可能测试固化缺陷）

### P0-2: require_auth fail-open 后门
- 现象: middleware.py 缺 handler 上下文时注入 test-unit 假用户放行（生产路径会被放大）
- 任务: 改为 fail-closed（默认拒绝），测试依赖该行为的用例同步修正（区分测试环境注入 vs 生产拒绝）

### P0-3: GitHub webhook 无签名校验
- 现象: 无 X-Hub-Signature-256、无鉴权，伪造事件可触发完整流水线
- 任务: 加 HMAC-SHA256 签名校验（配置 secret）+ 测试（有效签名放行/无效签名 401）

### P0-4: POST /api/v1/pipeline/trigger 未鉴权 + 任意路径写文件
- 现象: project_dir/arxml_content 请求体可控无校验，可写任意路径；未鉴权（当前真实可达端点）
- 任务: 加鉴权 + project_dir 路径白名单/规范化校验 + 输入长度限制 + 测试

## 2. Done 标准（验收矩阵）
- [x] 4×P0 全部修复，每个有对应测试（含"真实 server 启动 + JSON 探测"集成测试覆盖 P0-1）
- [x] 全量回归无新增失败（基线 9512 passed / 0 failed → 本轮 9543 passed / 0 failed）
- [x] 覆盖率不下降（基线 83% → 本轮 83%）
- [x] 修复只改必要代码，不做范围外重构；P1/P2 记录进 backlog 文件（不修）
- [x] commit + push origin/main，报告含每项修复说明 + 测试证据

## 3. 范围外（不做）
- P1/P2 修复（11+8 项）——进 backlog 下一轮
- 前端功能开发

## 4. 时间盒
- 开发 ≤ 2.5h（小克 sub-agent）
- 评估 ≤ 30min（小马复验）

## 5. 验收方式
- 小克修完给修复对照表（每项：复现→修法→测试证据）
- 小马独立复验（运行时探测 + 全量回归）→ 评分 → 小明终审

---

## 6. 修复对照表（小克交付，2026-08-01）

### P0-1: v1 模块化路由未接线 ✅
- **复现**: 真实启动 server（`python3 -m yuleosh.ui.server`）后 curl 探测 `/api/v1/health` → **200 + text/html 落地页**（52616B HTML）；`/api/v1/*` 全部一样。单测绿的矛盾根因：`tests/conftest.py` 把 `YULEOSH_JWT_SECRET` 注入环境，掩盖了**真实运行时缺 secret → `from yuleosh.api.router import dispatch` 导入即抛 → `handle_get` 异常 → `do_GET` catch-all 转 `_serve_static("/")` → HTML 200** 的链路；且旧 `api_v1_dispatch` 桩恒 False，单测把缺陷固化（断言 False）。
- **修法**: ① `server.py::api_v1_dispatch` 由恒 False 桩改为真实委托 `router.dispatch`；② `handler_helpers.py` `handle_get`/`handle_post` 顶部（healthcheck 之前）插入 v1 分发；③ **补上最后一环**（前一轮 sub-agent 遗漏）：`/api/v1/*` 路径在 dispatch 失败时**绝不回退 HTML**，改为写 JSON 500（fail-closed），消灭"200+HTML"症状——缺 secret 时现在返回 `{"ok": false, "error": "API dispatch failed: ..."}` 500。
- **测试证据**: `tests/test_server_integration.py` 新增 `TestServerMisconfigured`（2 个**真实 subprocess server** 测试：无 secret 时 `/api/v1/health` 与未知路径均 JSON 非 HTML）+ 既有 `test_api_v1_health_json`/`test_api_v1_spec_json`/`test_api_v1_unknown_json_404`（真实线程 server，JSON 200/401/404）；`tests/test_ui_server.py` 3 个单测改为断言委托。实测: 有 secret → 200 JSON / 401 JSON / 404 JSON；无 secret → 500 JSON。

### P0-2: require_auth fail-open 后门 ✅
- **复现**: `middleware.py:66-75` 缺 handler 上下文时注入 `test-unit` 假用户放行——任何漏传 handler 的调用链在生产被放大为静默放行。
- **修法**: 删除假用户注入分支，改为 **fail-closed 401**（`json_error(..., 401)`）；仅保留显式 `current_user` kwarg 作为测试注入通道（router.dispatch 只传 `handler=`，该通道 HTTP 不可达）。连带按 implementation-plan 对齐 `auth_extended.handle_signin`：无 password_hash 用户拒绝登录（统一文案防枚举）、org-setup token 绑定 email（`handle_org_create` 校验 body.email == token.email）。
- **测试证据**: `tests/test_api_middleware_ext.py` 改 `test_require_auth_no_handler`（断言 401 而非注入）+ 新增 `test_require_auth_explicit_current_user`；`tests/test_ui_auth_extended_ext.py` 更新 44 行；真实 server 实测无 token 访问 `/api/v1/spec/validate` → 401 JSON。

### P0-3: GitHub webhook 无签名校验 ✅
- **复现**: `webhooks.py` 无任何鉴权——伪造 POST 即可触发完整流水线。
- **修法**: 新增 `_verify_github_signature`（HMAC-SHA256，`hmac.compare_digest` 常量时间比较）；secret 读 `YULEOSH_GITHUB_WEBHOOK_SECRET`，未配置/缺签名/不匹配一律 401（fail-closed）；`api/__init__.py::read_body` 把原始字节暂存 `handler._raw_body` 供签名校验（防 router 读走后 rfile 为空）。
- **测试证据**: `tests/test_api_webhooks_ext.py` 新增 `_signed` 助手 + `test_github_push_bad_signature`（无效 HMAC→401）；真实 server 实测：有效签名→200 `{"ok": true}`，无效签名→401 `{"ok": false, "error": "Invalid webhook signature"}`。

### P0-4: pipeline trigger 未鉴权 + 任意路径写文件 ✅
- **复现**: `POST /api/v1/pipeline/trigger`（当前真实可达端点）无鉴权，`project_dir`/`arxml_content` 全由请求体控制 → 任意路径写文件 + 线程池 DoS。
- **修法**: 双入口都加固——`api/pipeline.py::_trigger_pipeline`（router 路径，`handle_pipeline` 已有 `@require_auth`）+ `ui/routes/pipeline_routes.py::handle_pipeline_trigger`（UI 路径，新增 `tenant_routes._require_auth`）：① `project_dir` resolve 后必须位于 `OSH_HOME` 内（`relative_to` 校验，防 `../` 逃逸）；② `type` 白名单（full/full_pipeline/ci）、`layer` 白名单（1/2/3）；③ `arxml_content`/`config_json` 1MB 上限；④ 滑动窗口节流（10 次/60s，防线程池 DoS）。
- **测试证据**: `tests/test_pipeline_trigger_security.py`（新增，17 测试）：无 token→401、坏 token→401、`/etc`→403、`../` 逃逸→403、合法 full/ci→job_id、`type=evil`→400、`layer=99`→400、arxml/config 超限→400、缺 project_dir→400、节流→429、router 集成无 token→401。

