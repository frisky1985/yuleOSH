# Spec-Delta — yuleOSH v3.7.0 变更点分析

> 版本: v3.7.0 · 基线: v3.6.1 (28ef25a) · 日期: 2026-08-02
> 用途: 小克开发变更清单 + 小马复验对照 + 老板风险知情
> 行号为 HEAD=28ef25a 实测（部分与评审报告行号有偏移，以实测为准）

---

## 0. 变更总览

| ID | 变更文件 | 行为变化 | 兼容性影响 | 风险等级 |
|----|----------|----------|-----------|---------|
| W1 | `src/yuleosh/ui/server.py`（do_GET） | 异常不再降级 200 首页 → JSON 500 / 500 页 | 低（仅异常路径） | 🟡 中 |
| W2 | `src/yuleosh/ui/auth_extended.py`（80-140） | 限流容器加锁 + IP 表加清理 | **中高（测试直操模块级 dict）** | 🟠 高 |
| W3 | `src/yuleosh/cli/main.py`（1849-1859） | swe6 报告去模拟化 | 低（CLI 输出/报告字段变化） | 🟡 中 |
| W4 | `src/yuleosh/store.py`（164-176） | 迁移加 hex 校验 | 低（幂等） | 🟢 低 |
| W5 | `src/yuleosh/plugins/sandbox.py`（139-167）+ plugins/* | extra_read_dirs 白名单 | **中高（插件行为收紧）** | 🟠 高 |
| W6 | `src/yuleosh/api/preview.py`（512-520, 657-665） | 缓存键加 user_key | **中（缓存语义变化）** | 🟠 高 |
| W7 | `src/` subprocess 全库 + `src/cli/commands/demo_uart.py`（106） | 批量 timeout + 去 shell | 低（正常路径不变） | 🟡 中 |
| M1 | `src/yuleosh/kb/models.py`（160-200） | XSS 消毒换白名单/补用例 | 中（文本内容保留语义） | 🟡 中 |
| M2 | `src/yuleosh/ui/server.py`（_serve_static 254-262） | 静态资源缓存头 | 低 | 🟢 低 |
| M3 | `src/yuleosh/ui/auth.py`（36）/ `server.py`（70）/ `api_routes.py`（37） | AUTH_ENABLED 单一来源 | 低（逻辑不变） | 🟢 低 |
| M4 | `src/yuleosh/ui/server.py`（_check_auth 304） | 白名单剥离 query 匹配 | 低（修复误拒） | 🟢 低 |

---

## 1. Track1 变更明细

### W1: do_GET 异常不静默降级

**文件**: `src/yuleosh/ui/server.py:348-359`（do_GET；评审报告称 319-329，实测 348）

**现状代码**:
```python
def do_GET(self) -> None:
    from yuleosh.ui.routes.handler_helpers import handle_get, log_audit
    self._request_start_time = time.time()
    try:
        handle_get(self)
    except Exception as e:
        logging.error("GET %s: %s", self.path, e)   # 无 exc_info
        self._serve_static("/")                       # 静默降级 200 首页
    finally:
        self._response_status = getattr(self, "_response_status", 200)
        log_audit(self)
```

**变更**:
1. `except` 分支：`logging.error(..., exc_info=True)`。
2. `self._serve_static("/")` → 按路径分流：
   - `self.path.startswith("/api/")` → `self._json_response({"error": "Internal server error"}, 500)`（与 do_POST 同款）。
   - 否则 → `send_response(500)` + text/html 简单错误页。
3. `finally` 中 `_response_status`：异常路径需反映 500（可设标志或在 except 内设置 `self._response_status = 500`），避免审计记录 200。

**兼容性影响**: 仅影响异常路径（此前 200 假成功，现 500 真失败）。正常路径零变化。前端若依赖"出错时收到 200 首页"的隐式兜底（如 SPA 路由 fallback），需注意：SPA 路由 fallback 应在 handler 正常路径处理，不依赖异常分支。

**风险与回归**: 低。需确认 `handle_get` 正常路径中对 SPA fallback（非 /api/ 页面路由找不到时返回 index.html）已有处理——若 fallback 逻辑放在 handler 内则不受影响；若依赖 do_GET 异常兜底，则要移到正常路径。回归测试重点 `test_ui_server_deep.py`。

### W2: signin 限流加锁 + IP 表清理

**文件**: `src/yuleosh/ui/auth_extended.py:80-140`

**现状**: `_SIGNIN_RATE_LIMIT` / `_SIGNIN_IP_LIMIT` 为普通 dict；`_check_ip_rate_limit` 内自增竞态；`_SIGNIN_IP_LIMIT` 无清理。

**变更**:
1. 两表换 `_ThreadSafeDict`（复用 `src/yuleosh/api/preview.py:38` 同款实现或抽公共模块——**注意**：抽公共模块属小重构，若放 `api/` 会引入 ui→api 依赖方向问题，建议复制同款实现到 auth_extended 或放 `ui/` 下公共位置，由小克决定但需小马确认不破坏分层）。
2. `_check_ip_rate_limit` 内读-改-写、`_record_failed_attempt` 的读改写均在锁内原子完成。
3. `_SIGNIN_IP_LIMIT` 加概率清理（>2000 条时清理过期窗口条目，对齐 email 表 `>1000` 概率清理模式）。

**行为变化（重点）**:
- 并发下限流从"可绕过"→"严格生效"。单线程语义不变：10 次/5min email、30 次/5min IP。
- **测试兼容性**（高风险点）: `tests/test_auth_extended_handlers.py:76-81` 直接 `_SIGNIN_RATE_LIMIT[email] = (10, ...)` 模块级赋值；`test_backlog_p1_v350.py` 中相关用例可能直接操作 dict。`_ThreadSafeDict` 已实现 `__setitem__`/`__getitem__`/`clear`/`pop`/`__contains__`/`items`，故 `dict[key]=v`、`d.clear()`、`in d` 语法均兼容；但 `len(d)`、`.get(key, default)` 语义也需确认（preview 版有 get）。`hash(email) % 11` 概率清理逻辑在容器化后需访问 `._dict` 内部（preview 版用 `._dict`/`._lock` 私有访问避免重入死锁——**必须沿用**，不得在持锁方法内再调用持锁方法）。

**风险**: 中高。现有测试若用 `assert len(_SIGNIN_RATE_LIMIT) == N` 之类会破坏（_ThreadSafeDict 无 `__len__`，preview 版未实现）。小克需 grep 全部测试对这两个 dict 的用法，逐一适配（可给 `_ThreadSafeDict` 补 `__len__`/`keys()` 等以最小化测试改动，需小马确认 API 面）。

### W3: swe6 check 去模拟化

**文件**: `src/yuleosh/cli/main.py:1849-1859`（`cmd_swe6_check`）

**现状**: `checks` 列表 6 项中 5 项硬编码 True；`--report` 分支 `test_cases: 5` 硬编码。

**变更**:
1. "测试用例定义": 调 `yuleosh.spec.validate.parse_spec(spec_path)`（实测存在，返回 `SpecDocument`，含 `requirements`/`scenarios` 列表，`to_dict()` 有 `scenario_count`/`requirement_count`/`total_shall`），用例数取 `len(doc.scenarios)`（或 requirements 中可识别用例条目——小克需确认语义，建议以 scenarios 为准并在报告中注明字段名）。
2. "测试环境配置": `Path(spec_path).parent / ".osh/ci-config.yaml"`（或 spec 同级 `.osh/`）exists 判定。
3. `--report`: `test_cases` 取解析值；解析失败 → `None` → JSON 中 `"test_cases": null` + `"test_cases_source": "unknown (manual)"`。
4. 其余无法真实判定的项标 `"probe (manual verification required)"`。

**行为变化**: CLI 文本输出与 swe6-report.json 内容变化（从恒真到真实值）。**兼容性**: 若外部脚本解析 swe6-report.json 的 `test_cases` 字段期望 int，需兼容 null（文档注明）；CLI 退出码语义不变（spec 缺失仍 exit 1）。

**风险**: 中。`parse_spec` 是既有函数（227 行），复用无新依赖；但"用例条目"判定口径需与 spec 格式（markdown 表格 SHALL 语法）对齐，小克需先跑一次现有 spec 验证计数合理。

### W4: session 迁移加 hex 校验

**文件**: `src/yuleosh/store.py:164-176`

**现状**: `SELECT ... WHERE length(token) != 64` → 恰好 64 字符明文 JWT 漏网。

**变更**: Python 侧过滤（推荐）:
```python
legacy = self.conn.execute("SELECT id, token FROM user_sessions").fetchall()
for row in legacy:
    if re.fullmatch(r"[0-9a-f]{64}", row["token"]):
        continue
    self.conn.execute("UPDATE user_sessions SET token=? WHERE id=?",
                      (_session_token_hash(row["token"]), row["id"]))
```

**行为变化**: 恰好 64 字符但非 hex 的明文 token 从"漏网"→"被迁移"。已 hash 行不变（幂等）。

**兼容性**: 低。`_session_token_hash` 已存在；迁移在 `__init__` 建库路径执行，新增全表扫描仅迁移窗口内发生一次（表小，可接受）。

**风险**: 低。需注意 token 为 NULL 的行：`re.fullmatch` 对 None 会抛 TypeError → 需先判空（SHALL-W4.4）。

### W5: sandbox 插件兼容性评估 + extra_read_dirs 白名单

**文件**: `src/yuleosh/plugins/sandbox.py:139-167` + `plugins/` 全部插件

**现状**: `_restricted_open` 读模式也收紧到插件目录内（P2-2），无扩展机制。

**变更**:
1. 审计 plugins/ 下插件 open() 用法（**前置步骤，产出清单**——见下方附录 A）。
2. `_restricted_open` 支持 `extra_read_dirs: list[Path]`：resolve 后依次尝试 `allowed_dir` 与各 extra 目录的 `relative_to`；全部失败才 `SandboxViolation`。
3. 白名单来源：插件 manifest（如 `manifest["sandbox"]["extra_read_dirs"]`）或插件注册参数——由小克设计，需小马确认接口。
4. 写模式保持严格（仅插件目录），extra_read_dirs 只作用于读。

**行为变化（重点）**: 收紧后的默认拒绝行为保持（P2-2 后语义）；仅显式声明白名单的插件恢复外部读取。**若审计发现既有插件实际依赖读外部文件但未声明，开发阶段就会暴露（SandboxViolation）**——这正是本项的目的：把隐式破坏变成显式声明。

**兼容性**: 高关注。现有测试 `test_backlog_p1_v350.py:563-590`（sandbox 拒绝用例）必须保持；新增放行用例。

**风险**: 高。若某插件（如编译器集成）需要读系统工具链目录，白名单会引入新的攻击面（extra_read_dirs 目录内容可被插件读取）。缓解：白名单最小化 + 文档化 + 写权限隔离（SHALL-W5.3）。

### W6: preview 缓存 owner 隔离

**文件**: `src/yuleosh/api/preview.py:512-520`（`_get_cached_preview`）、`657-665`（写入 `_repo_cache[url_hash] = preview_id`）

**现状**: 键为 `url_hash`（跨用户共享）。

**变更**:
1. `_get_cached_preview(repo_url, user_key)` → `_repo_cache.get((user_key, url_hash))`。
2. 写入路径同键。
3. `handle_preview` 内派生 `user_key`：从 `handler` 提取会话（复用文件内 498-499 行 `get_session_user(auth[7:])` 的 Bearer 解析）→ `user_id`；无登录 → `sha256(ip)`。

**行为变化（重点）**: 
- 跨用户缓存不再命中（安全修复）；同用户同 URL 仍命中（缓存收益保留）。
- 未登录用户缓存维度从"全局"→"IP"（IP 共享场景如 NAT 下同 IP 用户仍互见——**已知限制**，比全局好但非完美；文档注明，后续 Track2 认证收敛后可换 user_id）。
- 缓存 TTL/淘汰逻辑不变。

**兼容性**: 中。`preview_id` 读取路径（GET /assess/<id>）不依赖缓存键，无变化；测试中若存在跨"用户"构造缓存命中的用例需适配（新增 user_key 参数）。

**风险**: 高关注（缓存语义变化）。并发写入同键：`_ThreadSafeDict` 持锁，安全。内存增长：键从 1 元变 2 元，量级不变（用户数×URL 数，仍受 TTL 淘汰约束）。

### W7: 批量 subprocess timeout + demo_uart 去 shell

**文件**: `src/cli/commands/demo_uart.py:106` + `src/yuleosh/ci/*`、`pipeline/*`、`evidence/*`、`cli/*` 全库 subprocess 调用

**变更**:
1. demo_uart: `subprocess.run(["make", "-j", str(os.cpu_count() or 4)], cwd=..., capture_output=True, text=True)` 去 shell=True。
2. 批量补 `timeout=30`（普通）/ 编译打包类 `timeout=120-300`；`TimeoutExpired` 捕获 → 显式失败（stderr 提示超时），进程清理（`subprocess.run` 超时会自动 kill 子进程，但 shell=True 遗留的进程组需 killpg——去 shell 后无此问题）。
3. 已带 timeout 的 hot path 不动（api/dashboard.py:521=300s、api/ci.py:39=180s、api/review.py:36=120s）。

**行为变化**: 无限挂起 → 超时失败。正常路径零变化。

**兼容性**: 低。CLI 退出码/输出在正常路径不变。注意 demo_uart 的 `-j` 参数从 shell 插值 `sysctl` 变为 `os.cpu_count()`，值可能不同（sysctl hw.logicalcpu vs os.cpu_count）——均为逻辑核数，行为等价。

**风险**: 中。超时值需覆盖真实场景（大项目 make 可能 >30s，编译类必须 120s+）；小克需 grep 全部 `subprocess.run` 逐一过，防漏。

---

## 2. Track4 变更明细

### M1: 后端 XSS 消毒换 html.parser 白名单

**文件**: `src/yuleosh/kb/models.py:160-200`（`_strip_html`）

**现状**: 正则黑名单（10 个配对标签 + 8 个 void 标签 + 4 种事件属性 + javascript:/vbscript:/实体混淆）。

**变更（选型）**: 二选一，**需先与小明确认选型**（SHOULD-G.6）：
- **路线 A（推荐，Fix 12 首选）**: `html.parser.HTMLParser` 子类，`handle_data` 收集文本，剥离全部标签。**关键细节**：`<vector>`/`<int>` 这类非标准标签会被当作标签剥离其标签壳但保留其中文本？——不：`<vector>` 无闭合时 parser 视作 open tag，`handle_data` 不触发；需特殊处理"裸 `<` 后非合法标签名"的文本（如代码样例 `<vector>`），否则 `vector` 会被吞。**处理方案**: 自定义 parser 在 `handle_data` 收集文本 + `handle_starttag`/`handle_endtag` 丢弃标签 + 对"以 `<` 开头但非标签"的片段按文本保留（可用 `html.unescape` 后按 `>` 切分或采用"替换 `<` 为 `&lt;`"策略）。**验收口径**: 输出含 `vector` 文本（SHALL-M1.2）。
- **路线 B**: 保持正则 + 补嵌套混淆用例（双编码/嵌套/混合大小写/属性混淆 ≥5 个负例）。

**行为变化**: 路线 A 下，合法 HTML 标签（如 `<b>粗体</b>`）从"保留标签"→"剥离标签保留文本"（KB 字段本就是 markdown 文本，标签非受支持特性，行为可接受）；路线 B 无行为变化。两者均需保证 `test_kb_sanitize_xss.py` 既有正例全绿。

**兼容性**: 中。`sanitize_*_fields` 调用点不变；仅内部实现/测试变化。前端 escape-first 主防线不变。

**风险**: 中。html.parser 对畸形 HTML 的容错（未闭合标签、嵌套错误）需测试覆盖；`html.unescape` 双解码风险（实体解码后出现新 `<`）需负例。

### M2: 静态资源 Cache-Control immutable

**文件**: `src/yuleosh/ui/server.py` `_serve_static`（254-262 区域，实测 `send_header("Content-Type", ...)` 后加头位置）

**变更**: 按文件名规则判定 hash 资源 → `Cache-Control: public, max-age=31536000, immutable`；HTML → `no-cache`；其他 → 短 max-age（如 `max-age=3600`）或不加。判定规则见 SHALL-M2.5。

**兼容性**: 低。HTTP 头新增，不改变响应体。风险：误判用户上传资源为 immutable 导致更新不可见 → 判定规则需保守（限 `_next/static/` 等构建目录）。

### M3: AUTH_ENABLED 双定义合并

**文件**: `src/yuleosh/ui/auth.py:36`（主定义）、`src/yuleosh/ui/server.py:70`（重复定义）、`src/yuleosh/ui/routes/api_routes.py:37`（ImportError fallback）

**现状**:
- auth.py: `_AUTH_DISABLED = os.environ.get("YULEOSH_AUTH_DISABLED", "").lower() in ("1","true","yes")`; `AUTH_ENABLED = not _AUTH_DISABLED`
- server.py:70: `AUTH_ENABLED = os.environ.get("YULEOSH_AUTH_DISABLED", "").lower() not in ("1","true","yes")` — 与 auth.py 语义**等价**但独立实现。
- api_routes.py:37: `from yuleosh.ui.auth import AUTH_ENABLED` 的 `except ImportError: AUTH_ENABLED = False` — 局部 fallback（函数内局部变量），非模块级定义。

**变更**: server.py 删独立定义，改 `from yuleosh.ui.auth import AUTH_ENABLED`；api_routes.py fallback 审查（ImportError 实为循环导入保护——`ui/auth.py` 是否导入 `ui/routes/api_routes.py`？若存在循环导入，合并时需处理导入顺序，见风险）。

**行为变化**: 无（两处语义已等价）。纯去重。

**风险**: **循环导入风险**（中）：server.py 在模块顶层 `from yuleosh.ui.auth import AUTH_ENABLED`，而 `ui/auth.py` 若在顶层导入 server 侧模块会循环。实测 server.py:458 已在函数内使用 AUTH_ENABLED 且 server.py 顶层已 import 其他 ui 模块——小克需确认导入图无环；若顶层导入有环，可在 `_check_auth` 内延迟导入。api_routes.py:37 的 fallback 若保留须注明"仅防循环导入，非第三语义"。

### M4: 公开路径白名单支持 query 串匹配

**文件**: `src/yuleosh/ui/server.py:304`（`_check_auth`）

**现状**: `if self.path in _PUBLIC_PATHS or self.path.startswith(_PUBLIC_PREFIXES):` — query 未剥离。

**变更**: 
```python
from urllib.parse import urlsplit
path_only = urlsplit(self.path).path
if path_only in _PUBLIC_PATHS or path_only.startswith(_PUBLIC_PREFIXES):
    return True
```

**行为变化**: 带 query 的公开路径从"误判 401"→"放行"；带 query 的非公开路径仍 401（防绕过）。**安全关键**：必须用 `path_only`（不含 query）判定，query 只用于放行已公开路径，不得用于放行非公开路径。

**兼容性**: 低。纯修复。

---

## 3. 兼容性影响汇总表（按调用方）

| 调用方 | 受影响项 | 影响 |
|--------|----------|------|
| 前端页面（SPA） | W1 | 异常路径 200→500；正常路径无感 |
| 前端租户流程（Bearer JWT 调 legacy 端点） | W6/M4 | 带 query 公开端点放行；preview 缓存同用户可命中 |
| 监控/健康检查（带 query） | M4 | `/api/health?x=1` 从 401→200 |
| CLI 用户/脚本 | W3, W7 | swe6 报告内容真实化（test_cases 可能为 null）；挂起命令超时失败 |
| 插件开发者 | W5 | 外部读取需显式白名单声明 |
| 运维（部署） | W2, M3 | 无部署变化；AUTH_ENABLED 语义不变 |
| DB 既有数据 | W4 | 迁移窗口内多扫一次全表（一次性，量小） |
| 测试套件 | W2 最甚 | 直接操作模块级 dict 的用例需适配容器 API |

---

## 4. 附录 A：W5 插件审计清单（前置交付物，小克开发第一步）

> 审计完成（2026-08-02，小克）：`grep -rn "open(" src/yuleosh/plugins/` + 逐一核对读取目标。
> 审计范围：`plugins/` 包全部 Python 文件 + `tests/fixtures/plugins/` 下全部样例插件。

| 插件 | open() 用法 | 需外部读取？ | 白名单建议 |
|------|------------|-------------|-----------|
| `plugins/__init__.py:58`（PluginManifest.from_file） | 读自身 `manifest.json`（插件管理器，非沙箱内代码） | 否（管理器自身 IO，不经 `_restricted_open`） | — |
| `plugins/__init__.py:194`（install tarfile） | 解包插件归档（管理器安装路径，非沙箱内代码） | 否 | — |
| `plugins/registry.py:250,257`（urlopen） | 拉取远端插件注册表/下载（管理器，非沙箱内代码） | 否 | — |
| `plugins/sandbox.py:150`（`_restricted_open`） | 沙箱受限 open 本身 | —（机制提供方） | — |
| 样例插件 `tests/fixtures/plugins/sample-target-plugin/main.py` | 无任何 open()/文件 IO | 否 | 无需白名单 |
| 样例插件 `sample-skill` / `invalid-plugin` | 无入口代码 | 否 | — |

**结论（SHALL-W5.1 满足）**：仓库内无任何经沙箱执行的插件需要读取插件目录外文件；既有插件（样例）零外部读取需求，`extra_read_dirs` 机制为未来插件提供显式声明通道（manifest `permissions.extra_read_dirs` 或构造参数），不静默放宽全局读权限。既有沙箱测试（test_backlog_p1_v350.py:563-590）全绿。

> 审计完成后回填此表，小马据此复验 SHALL-W5.1 是否满足。

---

## 5. 附录 B：SEC-W3 核查结论（2026-08-02 已核实，转治理锁定）

- `src/yuleosh/api/auth.py:35-41`：`_YULEOSH_JWT_SECRET_ENV = os.environ.get("YULEOSH_JWT_SECRET")` — 无默认值；未设置即 `RuntimeError`（fail-fast）。✅ 无硬编码兜底。
- `src/yuleosh/ui/auth_extended.py:40-46`：同上 fail-fast。✅ 无硬编码兜底。
- 全仓 grep：无 `"dev-secret"` / `"test-secret"` 类默认值兜底。✅
- **结论**：不升级 critical。本版以回归测试锁定（T-M5-01：无 env 导入即失败）+ 部署文档已含生成说明（`deploy/PRODUCTION_DEPLOY.md` 的 `openssl rand -hex 32`、`deploy/.env.example`、`deploy/.env.production.example`）。
