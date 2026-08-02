# Acceptance Matrix — yuleOSH v3.7.0

> 版本: v3.7.0 · 基线: v3.6.1 (28ef25a) · 日期: 2026-08-02
> 用途: 小克开发测试清单 + 小马复验对照表。**负例（-neg）为必选项**。
> 规则: 每项至少 1 正例 + 1 负例；测试 ID 命名 `T-<Wx|Mx>-<n>-<描述>`；复验勾选 ✅ 表示小马独立跑通。

---

## Track1 验收

### W1 — do_GET 异常不静默降级（来源 COR-C2 / Fix 4）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W1-01-api-json500 | API 路径异常 | 注入 `handle_get` 对 `/api/xxx` 抛异常 | HTTP 500，body=`{"error": "Internal server error"}` | 正例 |
| T-W1-02-page-500page | 页面路径异常 | 注入 `handle_get` 对 `/dashboard` 抛异常 | HTTP 500，HTML 错误页（非 200 首页） | 正例 |
| T-W1-03-exc-info-log | 日志含堆栈 | 捕获异常后查 caplog | `logging.error(..., exc_info=True)`，含 traceback | 正例 |
| T-W1-04-audit-500 | 审计状态 | 异常后查 `_response_status`/审计记录 | 记录为 500 而非 200 | 正例 |
| T-W1-05-normal-noregress | 正常 GET 无回归 | 正常 `/api/health`、`/dashboard` | 行为与 v3.6.1 一致 | 回归 |
| T-W1-06-root-ok | 根路径兜底 | GET `/` 正常处理 | 返回首页（兜底仅限正常路径） | 回归 |
| T-W1-07-neg-no-200-html | **负例：API 异常不得 200** | 同 T-W1-01 | 断言状态码 ≠ 200 且 body 非首页 HTML | 负例 |

### W2 — signin 限流加锁 + IP 表清理（来源 COR-W2 / SEC-W2 / Fix 5）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W2-01-threadpool-race | 并发不超限 | ThreadPoolExecutor 20 线程同 email 错密码 | 计数 ≤ 12，后续阻断 | 正例 |
| T-W2-02-ip-cleanup | IP 表清理 | 造 >2000 条（含过期）触发概率清理 | 表收缩，未过期条目不受影响 | 正例 |
| T-W2-03-existing-tests | 既有测试兼容 | `test_auth_extended_handlers.py` / `test_backlog_p1_v350.py` 限流用例 | 全绿（`dict[key]=v`/`.clear()` 可用） | 回归 |
| T-W2-04-correct-password | 正确密码不计数 | 正确密码登录 | 不消耗限流预算 | 回归 |
| T-W2-05-unified-message | 枚举消息统一 | 未知用户/无密码/错密码 | 同文案（P1-2 语义） | 回归 |
| T-W2-06-neg-race-bypass | **负例：竞态不得绕过** | 并发 20 线程超阈值后继续提交 | 全部被拒（无绕过） | 负例 |
| T-W2-07-neg-ip-unbounded | **负例：IP 表不无限增长** | 大量不同 IP 触发 | 表大小有上界（清理生效） | 负例 |

### W3 — swe6 check 去模拟化（来源 COR-C3 / Fix 6）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W3-01-real-count | 真实解析计数 | 临时 spec 含 3 个用例 → `swe6 check` | 输出"3 个 (解析自 spec)" | 正例 |
| T-W3-02-report-source | 报告注明来源 | `--report` 生成 json | `test_cases==3` 且含来源字段 | 正例 |
| T-W3-03-unparseable | 不可解析 | 非法/无用例 spec | 用例项非 ✅，标 unknown/manual | 正例(负向) |
| T-W3-04-ci-config-missing | 环境配置真实性 | `.osh/ci-config.yaml` 缺失 | "测试环境配置"为 ❌ | 正例(负向) |
| T-W3-05-spec-missing | spec 缺失 | spec 文件不存在 | 报错 exit 1（既有行为） | 回归 |
| T-W3-06-neg-hardcoded-true | **负例：无硬编码 True** | 构造无用例 spec | 断言不存在恒 True 检查项 | 负例 |

### W4 — session 迁移加 hex 校验（来源 COR-W3 / Fix 7）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W4-01-64-char-plaintext | 64 字符明文 JWT 迁移 | 插入含 `-`/`_` 的 64 字符 token → 重开 store | 被 hash，明文消失 | 正例 |
| T-W4-02-hex-skip-idempotent | 已 hash 幂等 | 64 位 hex token → 重开 store | 行不变，不重复 hash | 正例 |
| T-W4-03-short-plaintext | 40 字符明文 | 40 字符 JWT → 重开 | 被 hash（v3.6.1 行为保持） | 回归 |
| T-W4-04-null-safe | NULL token | 插入 NULL token → 重开 | 不抛异常，安全处理 | 正例 |
| T-W4-05-neg-no-plaintext | **负例：DB 无明文残留** | 全量扫描 user_sessions | 无非 hex-64 明文 token | 负例 |

### W5 — sandbox 插件兼容性 + extra_read_dirs（来源 COR-W5 / Fix 8）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W5-01-extra-dirs-allowed | 白名单放行 | 插件声明 extra_read_dirs=[/etc] → 读 /etc/os-release | 放行 | 正例 |
| T-W5-02-outside-rejected | 白名单外拒绝 | 同插件读 /var/log/syslog | SandboxViolation | 负例 |
| T-W5-03-write-strict | 写权限隔离 | 有读白名单插件写 /tmp/x | 拒绝（读写隔离） | 负例 |
| T-W5-04-resolve-strict | resolve 校验保留 | 读 `/etc/../etc/passwd`、symlink 逃逸 | 拒绝 | 负例 |
| T-W5-05-existing-tests | 既有测试 | `test_backlog_p1_v350.py:563-590` | 全绿（收紧语义不回归） | 回归 |
| T-W5-06-audit-done | 插件审计完成 | 附录 A 清单回填（开发交付物） | 全部插件 open() 用法已评估 | 交付物 |
| T-W5-07-neg-no-global-relax | **负例：不全局放宽** | 无白名单插件读外部文件 | SandboxViolation | 负例 |

### W6 — preview 缓存 owner 隔离（来源 SEC-W4 / Fix 9）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W6-01-user-isolation | 两用户隔离 | 用户 A、B 同 repo_url，A 先完成 | B 不命中 A 缓存，preview_id 不同 | 正例 |
| T-W6-02-same-user-hit | 同用户命中 | 用户 A 再次同 repo_url（TTL 内 completed） | `cached: true` | 正例 |
| T-W6-03-ip-user-key | 未登录同 IP | 未登录同 IP 两次同 URL | 命中（同 IP user_key） | 正例 |
| T-W6-04-read-path-stable | 读取路径不变 | GET /assess/<id>（不依赖缓存键） | 行为与 v3.6.1 一致 | 回归 |
| T-W6-05-cleanup-ok | 清理逻辑不失效 | 触发 `_cleanup_expired_results` | 键结构变化后正常淘汰 | 回归 |
| T-W6-06-neg-cross-user | **负例：跨用户不得命中** | A 完成 + B 同 URL 请求 | 断言 B 响应 `cached` 非 true 或独立 preview_id | 负例 |

### W7 — 批量 subprocess timeout + demo_uart 去 shell（来源 SEC-W6 / Fix 10）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-W7-01-demo-uart-argv | demo_uart 去 shell | 执行 demo uart build（host） | 成功，无 shell=True；`-j` 为数字 argv | 正例 |
| T-W7-02-no-shell-inspect | 无 shell 残留 | grep demo_uart.py | 无 `shell=True`、无 `$(` 插值 | 正例 |
| T-W7-03-timeout-fail | 超时显式失败 | monkeypatch 子进程 sleep > timeout | TimeoutExpired 被捕获，明确失败提示 | 负例 |
| T-W7-04-timeout-normal | 正常不超时 | 正常 CI/pipeline 子进程 | 行为与 v3.6.1 一致 | 回归 |
| T-W7-05-full-sweep | 全库无裸 subprocess | grep src/ 无 timeout 的 subprocess.run | 全部补 timeout（已豁免 hot path 除外） | 交付物 |
| T-W7-06-pipeline-async | async runner 回归 | `test_pipeline_async_runner.py` | 全绿 | 回归 |
| T-W7-07-neg-hang | **负例：挂起不无限阻塞** | 子进程永挂 | timeout 后失败返回，不挂死线程 | 负例 |

---

## Track4 验收

### M1 — 后端 XSS 消毒（来源 ARC-W6 / Fix 12）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-M1-01-nested-script | 嵌套混淆 | `<scr<script>ipt>alert(1)</scr</script>ipt>` | 无 script 残留 | 负例 |
| T-M1-02-double-encoded | 双编码实体 | `&#106;&#97;vascript:alert(1)` | 无 javascript: 协议 | 负例 |
| T-M1-03-mixed-case | 大小写混写 | `<ScRiPt>...</ScRiPt>`、`<SVG><script>` | 全部剥离 | 负例 |
| T-M1-04-text-preserved | 文本保留 | `<b>粗体</b>` + 代码样例 `<vector>`/`<int>` | 输出含"粗体"与"vector"文本 | 正例 |
| T-M1-05-existing-positive | 既有正例 | `test_kb_sanitize_xss.py` 全量 | 全绿 | 回归 |
| T-M1-06-sanitize-fields | 写入路径不变 | `sanitize_kb_article_fields` 等三函数 | dict→dict 消毒不变量保持 | 回归 |
| T-M1-07-neg-event-attrs | **负例：事件属性残留** | `onerror`/`onload` 带混淆空白 | 无事件属性残留 | 负例 |

### M2 — 静态资源 Cache-Control immutable（来源 SEC-P2）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-M2-01-hash-immutable | hash 资源 | GET `/_next/static/chunks/app-3f2a9b.js` | `Cache-Control: public, max-age=31536000, immutable` | 正例 |
| T-M2-02-html-no-cache | HTML 不缓存 | GET `/`、`/index.html` | 无 immutable（no-cache 或等价） | 正例 |
| T-M2-03-nonhash-no-immutable | 无 hash 资源 | GET `logo.png` | 不得 immutable | 负例 |
| T-M2-04-404-500-ok | 错误路径不受影响 | 404/500 路径 | 响应头语义不变 | 回归 |
| T-M2-05-security-headers | 安全头保留 | 任意静态资源 | `_add_security_headers` 仍生效 | 回归 |

### M3 — AUTH_ENABLED 单一来源（来源 v3.6.1 P2-①）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-M3-01-single-source | 单一来源 | 断言 server.AUTH_ENABLED is auth.AUTH_ENABLED（同对象/同值） | 一致 | 正例 |
| T-M3-02-env-unset | env 未设 | 未设 YULEOSH_AUTH_DISABLED | AUTH_ENABLED=True（fail-closed） | 回归 |
| T-M3-03-env-disabled | env 关闭 | `YULEOSH_AUTH_DISABLED=yes|1|true` | False | 回归 |
| T-M3-04-env-other | env 其他值 | `YULEOSH_AUTH_DISABLED=0|off|foo` | True（非 1/true/yes 均 True） | 回归 |
| T-M3-05-no-dup-def | 无重复定义 | grep server.py 无独立 AUTH_ENABLED 计算 | 仅 auth.py 定义 | 交付物 |
| T-M3-06-neg-third-semantics | **负例：无第三语义** | api_routes.py fallback 审查 | 不产生 AUTH_ENABLED=False 独立语义 | 负例 |

### M4 — 公开路径白名单 query 串匹配（来源 v3.6.1 P2-②）

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-M4-01-public-with-query | 公开+query 放行 | `/api/health?source=monitor&v=2` | 200（放行） | 正例 |
| T-M4-02-private-with-query | 非公开+query 拒 | `/api/project/list?org=1`（无凭据） | 401 | 负例 |
| T-M4-03-prefix-with-query | 前缀+query | `/static/app.js?cb=123` | 放行 | 正例 |
| T-M4-04-plain-public | 无 query 公开 | `/api/health` | 放行（既有行为） | 回归 |
| T-M4-05-neg-query-bypass | **负例：query 不绕过鉴权** | 非公开路径任意 query | 仍 401 | 负例 |

### M5 — SEC-W3 JWT secret 治理（老板 08-02 23:29 钦定同步，已核实无默认值）

> 现状核实：`api/auth.py:35-41` + `ui/auth_extended.py:40-46` 均 fail-fast（无 YULEOSH_JWT_SECRET 即导入失败），无硬编码兜底。本项转为治理锁定。

| 测试 ID | 场景 | 输入/步骤 | 预期 | 类型 |
|---------|------|-----------|------|------|
| T-M5-01-no-env-import-fail | 无 env 导入拒绝 | 移除 YULEOSH_JWT_SECRET 后 import yuleosh.api.auth / ui.auth_extended | 抛异常（RuntimeError/SystemExit）提示设置 env | 负例 |
| T-M5-02-with-env-ok | 有 env 正常 | 设置 YULEOSH_JWT_SECRET 后导入 + 签发/验证 token | 正常 | 正例 |
| T-M5-03-single-source | 两处单一来源 | grep 全仓确认无硬编码 fallback（无 `"dev-secret"` 类兜底） | 无兜底 | 交付物 |
| T-M5-04-deploy-doc | 部署文档提示 | PRODUCTION_DEPLOY.md/.env.example 含 YULEOSH_JWT_SECRET 生成说明 | 已含 | 交付物 |

---

## 全局验收（G 项）

| 测试 ID | 场景 | 预期 | 类型 |
|---------|------|------|------|
| T-G-01-full-regression | 全量回归 | ≥ 9794 passed / 0 failed（只增不减） | 回归 |
| T-G-02-coverage | 覆盖率 | ≥84.10% 不降 | 回归 |
| T-G-03-no-new-deps | 无新依赖 | 标准库优先（html.parser 为 stdlib） | 交付物 |
| T-G-04-source-comment | 来源注释 | 每项修复代码注明 W-x/M-x | 交付物 |
| T-G-05-api-contract | API 契约 | /api/v1/* 响应结构、错误码、CLI 子命令不变 | 回归 |
| T-G-06-behavior-change-3 | 行为变更三件套 | W2/W5/W6 专项回归 + 兼容适配记录 | 交付物 |

---

## 验收通过判定

1. 上表所有 **必选**（正例 + 负例 + 回归）测试全绿；
2. T-G-01/T-G-02 通过；
3. W5 插件审计清单（spec-delta 附录 A）回填且小马核验；
4. M1 选型（A/B）经小明确认记录；
5. SEC-W3 核查结论记录在案（异常则升级）；
6. 小马独立复验（非小克自测）签字；
7. 小明终审确认 → 版本关闭。

## 复验记录（小马填写）

| 日期 | 复验人 | 结果 | 备注 |
|------|--------|------|------|
|      |        |      |      |

---

## 开发完成记录（小克填写，2026-08-02）

> 实现于 commit `（见 v3.7.0 commit message）`（HEAD 基于 28ef25a）。
> 全部 73 项矩阵测试已实施：正例 + 负例（-neg 必选）全绿；来源注释 `W-x`/`M-x` 标注于代码。

### 新增/适配测试文件对照

| 测试文件 | 覆盖矩阵项 | 说明 |
|----------|-----------|------|
| `tests/test_v370_track1_track4.py`（新增，79 用例） | T-W1-01..07, T-W2-01..07, T-W3-01..06, T-W4-01..05, T-W5-01..07, T-W6-01..06, T-W7-01..07, T-M1-01..07, T-M2-01..05, T-M3-01..06, T-M4-01..05, T-M5-01..04 + 补充分支（TC-* 标题计数/ci-config 存在/API-key&Bearer user_key/`<vector/>`/IP 过期重置/迁移幂等） | v3.7.0 验收主文件（含全部 -neg 负例 + M5 SEC-W3 治理锁定 + 覆盖率补充分支） |
| `tests/test_api_services_extended.py`（适配 3 用例） | T-W6 相关（TestPreviewCache） | W-6 缓存键签名 `(user_key, url_hash)` 适配 |
| `tests/test_api_preview_unit.py`（适配 5 用例） | T-W6 相关（TestRepoCache / POST cached） | W-6 键签名适配 + `_get_user_key` IP 维度 |
| `tests/test_ui_server_deep.py`（适配 1 用例） | T-W1-07-neg（test_get_root_exception_fallback） | 旧断言“异常降级 200 首页”改为 W-1 新语义（500 + 不调 _serve_static） |

### 行为变更三件套专项回归（T-G-06）

| 项 | 兼容适配记录 | 专项回归 |
|----|-------------|---------|
| W2 限流容器化 | `_ThreadSafeDict` 复制到 auth_extended（含 `__len__`/`keys()`/`items()` 兼容面）；内部读写统一走 `._dict` + `._lock` 防重入死锁；测试直操模块级 dict 的既有写法（`d[k]=v`/`.clear()`/`in`/`len`）全部兼容 | `test_auth_extended_handlers.py`、`test_ui_auth_extended_ext.py`、`test_backlog_p1_v350.py` 限流用例全绿 + T-W2-01/06/07 |
| W5 sandbox 白名单 | 插件审计完成（附录 A）：无内置插件需外部读取 → 零行为变化；`extra_read_dirs` 经构造参数或 manifest `permissions.extra_read_dirs` 显式声明，仅读模式；resolve+relative_to 保留 | `test_backlog_p1_v350.py:563-590`、`test_plugins.py`、`test_plugins_smoke*.py` 全绿 + T-W5-01..07 |
| W6 缓存 owner 隔离 | 键 `url_hash` → `(user_key, url_hash)`；user_key = 会话 user_id / API key id / IP sha256；读取路径（GET /assess/<id>）与清理逻辑不依赖键结构，零变化 | `test_api_preview_unit.py`、`test_api_services_extended.py` 全绿 + T-W6-01..06 |

### 交付物清单（T-W5-06 / T-W7-05 / T-G-03/04/05）

- W5 插件审计清单 → spec-delta.md 附录 A（已回填）
- W7 全库无裸 subprocess：src/yuleosh 全库 14 行窗口审计仅 1 处豁免（`cross/sil_runner.py:285` Popen 长驻进程自带生命周期超时，且不在 SHALL-W7.2 范围目录）；demo_uart 已去 shell（argv 形式 + `-j` 数字）
- 无新依赖（html.parser / threading / re 均为 stdlib）
- 每项修复代码注明来源 `W-x`/`M-x`
- SEC-W3 核查 → spec-delta.md 附录 B（已核实无默认值，转治理锁定）
- M1 选型：路线 A html.parser 白名单（spec 已钦定，SHOULD-G.6 满足）

### 遗留项（不在本版范围）

- NAT 同 IP 匿名用户共享 preview 缓存 user_key（W6 已知限制，Track2 认证收敛后换 user_id）
- `_serve_file` 页面路径无 Cache-Control 头（M2 只覆盖 `_serve_static`；页面走 HTML 不缓存语义，前端跟踪）
- `do_POST`/`do_DELETE` 审计 `_response_status` 仍为 200（P1-7 既有行为，W1 仅覆盖 do_GET）
