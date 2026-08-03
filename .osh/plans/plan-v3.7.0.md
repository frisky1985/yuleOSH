# Plan — yuleOSH v3.7.0 — Track1 Warning×7 + Track4 杂项×4

> 日期: 2026-08-02 · 依据: `.osh/specs/v3.7.0/`（spec / spec-delta / startup-analysis / acceptance-matrix）
> 决策: 老板方案 A（Track1+Track4 → v3.7.0；Track2 → v3.8.0；Track3 → v3.9.0）；M1 路线 A（html.parser）小明拍板
> 状态: 实施完成，待小马复验

## 修复对照表（11 项）

| 项 | Review 来源 | 文件 | 改动 | 测试 |
|----|------------|------|------|------|
| W1 | COR-C2 / Fix 4 | `src/yuleosh/ui/server.py::do_GET` | 异常不再静默降级 200 首页：API 路径 → `{"error": "Internal server error"}` + 500；页面路径 → `<h1>500 Internal Server Error</h1>` 500 页；`logging.error(..., exc_info=True)`；`_response_status=500` 供审计 | T-W1-01~07 |
| W2 | COR-W2 / SEC-W2 / Fix 5 | `src/yuleosh/ui/auth_extended.py` | `_SIGNIN_RATE_LIMIT`/`_SIGNIN_IP_LIMIT` 换 `_ThreadSafeDict`（含 `__len__`/`keys()` 兼容面）；check/record 读改写持锁原子；新增 `_check_and_record_failed_attempt` 合并 check+record（并发 20 线程计数 ≤10+2）；`_SIGNIN_IP_LIMIT` 加 >2000 概率清理 | T-W2-01~07 |
| W3 | COR-C3 / Fix 6 | `src/yuleosh/cli/main.py::cmd_swe6_check` | "测试用例定义"真实解析 spec（复用 `yuleosh.spec.validate.parse_spec`，`len(doc.scenarios)`）；"测试环境配置"查 `.osh/ci-config.yaml` 存在性；`--report` 的 `test_cases` 取真实值 + `test_cases_source` 注明来源；无法判定项标 `probe (manual verification required)`（⚠️ 非 ✅） | T-W3-01~06 |
| W4 | COR-W3 / Fix 7 | `src/yuleosh/store.py` | 迁移改 Python 侧 `re.fullmatch(r"[0-9a-f]{64}")`：恰好 64 字符非 hex 明文 token 也被 hash；NULL/空 token 安全跳过；幂等 | T-W4-01~05 |
| W5 | COR-W5 / Fix 8 | `src/yuleosh/plugins/sandbox.py` + plugins 审计 | `_restricted_open` 支持 `extra_read_dirs`（构造参数 + manifest `permissions.extra_read_dirs`），仅读模式；写模式仍严格插件目录；resolve+relative_to 保留；附录 A 审计完成：无既有插件需外部读取 | T-W5-01~07 |
| W6 | SEC-W4 / Fix 9 | `src/yuleosh/api/preview.py` | `_repo_cache` 键改 `(user_key, url_hash)`；`_get_user_key(handler)`：会话 user_id / API key id / 匿名 IP sha256；读取路径 GET /assess/<id> 不依赖缓存键 | T-W6-01~06 |
| W7 | SEC-W6 / Fix 10 | `src/cli/commands/demo_uart.py` + `cli/main.py`、`cli/onboard.py`、`pipeline/step_handlers/fault_inject.py` | demo_uart 去 shell=True（argv `["make","-j",str(os.cpu_count() or 4)]`）；10 处 subprocess 补 timeout（30s git / 120s 编译网络 / 300s 构建测试），TimeoutExpired 显式失败处理；sil_runner Popen 豁免（生命周期 timeout + SIGKILL，cross/ 目录） | T-W7-01~07 |
| M1 | ARC-W6 / Fix 12 | `src/yuleosh/kb/models.py::_strip_html` | 换 html.parser 白名单（路线 A）：已知标签剥壳留文本；危险标签整块丢弃（含内容）；未知标签（代码样例 `<vector>`/`<int>`）干净则按字面保留、含危险子串则丢弃；末尾保留正则纵深后处理；文档注明非安全边界（前端 escape-first 仍是主防线） | T-M1-01~07 |
| M2 | SEC-P2 | `src/yuleosh/ui/server.py::_serve_static` | `_is_immutable_asset`（`_next/static/` 或 `static/` + 8+ 位 hash 文件名）→ `Cache-Control: public, max-age=31536000, immutable`；HTML → `no-cache`；无 hash 资源 → `max-age=3600` 不 immutable | T-M2-01~05 |
| M3 | v3.6.1 P2-① | `src/yuleosh/ui/server.py`、`ui/routes/api_routes.py` | server.py 删独立 env 计算，`from yuleosh.ui.auth import AUTH_ENABLED` 单一来源（无循环导入：ui/auth.py 纯 stdlib）；api_routes.py fallback 注释说明（仅防导入失败，非第三语义） | T-M3-01~06 |
| M4 | v3.6.1 P2-② | `src/yuleosh/ui/server.py::_check_auth` | `urllib.parse.urlsplit(self.path).path` 剥离 query 后匹配白名单；query 仅用于放行已公开路径，非公开路径带任意 query 仍 401 | T-M4-01~05 |

## 行为变更三件套（W2/W5/W6）专项回归

- W2: `tests/test_auth_extended_handlers.py` + `test_ui_auth_extended_ext.py` + `test_backlog_p1_v350.py`（TestSigninHardening）+ `test_api_auth_coverage.py` + `test_api_supplementary.py` 全绿；模块级 dict 直操兼容（`dict[key]=v` / `.clear()` / `in` / `len`）
- W5: `tests/test_backlog_p1_v350.py`（TestSandboxPathGuard）+ `test_plugins*.py` 全绿；新增白名单放行/拒绝/写隔离/resolve 逃逸用例
- W6: `tests/test_api_preview_unit.py` 缓存用例适配 `(user_key, url_hash)` 键；读取路径回归

## 测试

- 新增 `tests/test_v370_track1_track4.py`（79 用例，ID 对齐 acceptance-matrix.md T-Wx/Mx，负例 -neg 全含；含 M5 SEC-W3 治理锁定 4 项 + W3 补充 TC-* 计数/ci-config 存在用例）
- 适配既有测试: `test_ui_server_deep.py`（do_GET 异常不再 `_serve_static`）、`test_api_preview_unit.py`、`test_api_services_extended.py`（W6 缓存键 tuple）
- 行为差异记录（复验注意）: M4 矩阵示例 `/api/project/list` 实为 _PUBLIC_PATHS 白名单项（租户 JWT 自鉴权端点），负例改用真正 gated 的 `/api/evidence`、`/api/ci-results` 验证"query 不放行非公开路径"

## 回归（最终，commit 2e0eef5）

- 全量: `pytest tests/`（忽略 6 个 E2E 文件）→ **9873 passed / 0 failed**（基线 9794，+79 只增不减）
- 覆盖率 **84.10%**（≥84.10% 不降）
- 前端链路: `test_v344_p0ab_integration.py` 21 passed + jest 3 suites 29 tests 全绿（未动 frontend/）
- SEC-W3 核查: **NORMAL**（见下）
- commit: `2e0eef5 feat(v3.7.0): Track1 Warning 批量 7 项 + Track4 杂项 5 项（含 M5 SEC-W3 治理锁定）` 已 push origin/main

## SEC-W3 核查记录（第一优先）

- `src/yuleosh/api/auth.py:35-41` + `src/yuleosh/ui/auth_extended.py:40-46`: `YULEOSH_JWT_SECRET` 未设置即 `RuntimeError`（fail-closed），**无硬编码默认值** ✅
- `src/yuleosh/api/subscription.py:60`、`api/wizard.py:21`: fallback 为 `secrets.token_urlsafe(32)` **随机值**（非硬编码），符合"未设置即随机→记录确认"
- 结论: **NORMAL，无需升级**。minor observation（不入本版）: subscription/wizard 每次调用生成新随机 secret，跨调用验签会失败——属既有行为，建议 Track2 统一走 auth.py 单一来源

## 风险与遗留

- W6 未登录用户缓存维度为 IP（NAT 同 IP 用户仍互见）— 已知限制，Track2 认证收敛后换 user_id
- M1 html.parser 是纵深防御非安全边界，前端 escape-first 仍是主防线（SHOULD-M1.6 已注明）
- W2 内存限流仍为进程内（S-P2-02），多 worker 部署需 Redis/DB 限流（既有 NOTE 不变）
- M4 契约与代码白名单示例路径差异已记录（见测试节），判定以 SHALL-M4.3 语义为准
