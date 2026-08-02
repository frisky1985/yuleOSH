# Spec — yuleOSH v3.7.0（Track1 Warning 批量 + Track4 杂项）

> 版本: v3.7.0 · 基线: v3.6.1 (28ef25a) · 日期: 2026-08-02
> 方法: OpenSpec（SHALL/SHOULD/MAY + GIVEN/WHEN/THEN）
> 依据: `~/.openclaw/workspace/plans/yuleOSH-v3.7-roadmap.md`（方案 A 已确认）+ `reviews/ultra-full-2026-08-02/implementation-plan.md`（Fix 4-10 + Fix 12 + M 项）
> 上游裁决: 小明（需求）· 开发: 小克 · 复验: 小马（本文档为复验依据）
> 范围说明: Track2 架构收敛 → v3.8.0；Track3 前端安全 → v3.9.0。本文档不涉及。

---

## 0. 需求编号规则

- 每项需求编号 `SHALL-Wx.n`（Track1）/ `SHALL-Mx.n`（Track4），x = 项号，n = 条款序号。
- 测试 ID 规则见 `acceptance-matrix.md`（`T-Wx.n-xxx` / `T-Mx.n-xxx`），负例统一后缀 `-neg`。
- 验收判定：**所有 SHALL 条款有对应测试（正例 + 负例）且全绿**，方视为该项完成。

---

## 1. Track1 — Warning 批量修复（7 项）

### W1: do_GET 异常不静默降级（来源 COR-C2 / Fix 4）

**现状问题**（实测 server.py:348-359）：`do_GET` 的 except 分支调用 `self._serve_static("/")`，任何非 `/api/v1/` 路径抛异常都静默返回 200 首页 HTML，错误被完全掩盖；且日志无 `exc_info`。对比 `do_POST`/`do_DELETE` 已统一 JSON 500（P1-7），do_GET 未同步。

**SHALL 条款**

- **SHALL-W1.1**: do_GET 捕获到未处理异常时，若请求路径以 `/api/` 开头，必须返回 `{"error": "Internal server error"}` + HTTP 500（与 do_POST 行为一致），不得返回 200 首页 HTML。
- **SHALL-W1.2**: do_GET 捕获到未处理异常时，若请求路径非 `/api/` 前缀（页面/静态路径），必须返回 HTTP 500 + 简单错误页（如 `<h1>500 Internal Server Error</h1>`），不得返回 200 首页 HTML。
- **SHALL-W1.3**: do_GET 异常分支必须输出 `logging.error(..., exc_info=True)` 完整堆栈日志，不得仅记录 `type(e).__name__` 或省略堆栈。
- **SHALL-W1.4**: do_GET 的 `finally` 审计路径（`log_audit`）必须继续执行；`_response_status` 在异常场景下必须反映 500（或审计字段可区分异常态），不得回落到默认 200。
- **SHALL-W1.5**: `/` 路径（空 path 或恰好 `/`）正常请求仍走静态首页服务，不得因 W1.1/W1.2 被误伤（兜底 200 仅限路径本身为空，且不抛异常的正常路径）。
- **SHOULD-W1.6**: 异常响应体包含非敏感稳定错误文案（与 `json_error("Internal server error", 500)` 同源），不泄漏路径/异常类型/模块内部细节。

**GIVEN/WHEN/THEN**

- GIVEN 一个以 `/api/xxx` 为路径的 GET 请求，WHEN `handle_get` 抛出未处理异常，THEN 响应为 HTTP 500 且 body 为 JSON `{"error": "Internal server error"}`，且服务端日志含完整 traceback。
- GIVEN 一个非 API 页面路径（如 `/dashboard`）的 GET 请求，WHEN 路由处理抛出未处理异常，THEN 响应为 HTTP 500 错误页（非 200 首页），日志含 exc_info。
- GIVEN 一个正常 GET 请求（无异常），WHEN 处理成功，THEN 行为与 v3.6.1 完全一致（无回归）。
- GIVEN 请求路径为 `/`，WHEN 正常处理，THEN 仍返回首页（兜底语义不破坏）。

---

### W2: signin 限流加锁 + IP 表清理（来源 COR-W2 / SEC-W2 / Fix 5）

**现状问题**（实测 auth_extended.py:80-140）：`_SIGNIN_RATE_LIMIT` / `_SIGNIN_IP_LIMIT` 为普通 dict；`_check_ip_rate_limit` 内自增为读-改-写竞态，并发可绕过 10 次/5min 上限；`_SIGNIN_IP_LIMIT` **完全没有清理逻辑**（无限增长 DoS），`_SIGNIN_RATE_LIMIT` 有 >1000 条概率清理。preview.py 已用 `_ThreadSafeDict`，此处未同步。

**SHALL 条款**

- **SHALL-W2.1**: `_SIGNIN_RATE_LIMIT` 与 `_SIGNIN_IP_LIMIT` 必须改为线程安全容器（复用 preview.py `_ThreadSafeDict` 或同语义实现：get/pop/`__setitem__`/`__contains__`/`clear`/items 全部持锁），check 与 record 之间的读改写必须在同一锁下原子完成。
- **SHALL-W2.2**: 并发场景下限流语义不得放宽：单进程内，N 个线程并发提交同一 email 的错误密码，最终失败计数不得超过 `_MAX_SIGNIN_ATTEMPTS + ε`（ε 为单次窗口内允许的最小余量，验收以"并发 20 线程 → 计数 ≤ 10+2"为判据），且后续请求必须被阻断。
- **SHALL-W2.3**: `_SIGNIN_IP_LIMIT` 必须引入与 email 表同款概率清理（如 >2000 条时按比例清理过期窗口条目），杜绝无限增长；清理不得影响未过期条目的限流判定。
- **SHALL-W2.4**: 现有限流单测（test_auth_extended_handlers.py、test_backlog_p1_v350.py 相关用例）必须保持全绿；测试直接操作模块级状态的写法（如 `_SIGNIN_RATE_LIMIT[email] = ...`、`.clear()`）在新容器下必须继续可用（容器需提供 `__setitem__` 与 `clear`）。
- **SHALL-W2.5**: 正确密码不计数、统一枚举消息等 P1-2 既有语义不得改变（check/record 分离语义保持）。
- **MAY-W2.6**: 若实现层将 check+record 合并为单一原子操作，可保留现有函数签名不变（`_check_rate_limit` / `_record_failed_attempt` / `_check_ip_rate_limit`），仅在内部加锁；不得破坏调用方。

**GIVEN/WHEN/THEN**

- GIVEN 单进程运行的服务，WHEN 20 个线程并发对同一 email 提交错误密码，THEN 服务端失败计数 ≤ 12 且第 11+ 次请求被限流拒绝（HTTP 429 或等效阻断）。
- GIVEN `_SIGNIN_IP_LIMIT` 已有 >2000 条记录（含大量过期），WHEN 新 IP 触发清理路径，THEN 表大小回落且未过期条目的判定不受影响。
- GIVEN 正确密码登录，WHEN 校验通过，THEN 不消耗限流计数（与 v3.6.1 行为一致）。

---

### W3: swe6 check 去模拟化（来源 COR-C3 / Fix 6）

**现状问题**（实测 cli/main.py:1849-1859）：`checks` 列表硬编码 `("测试用例定义", True, "存在 (从 spec 解析)")`、`("测试环境配置", True, "已定义 (Dev/SIL)")` 等，永远 True；`--report` 中 `test_cases: 5` 亦为硬编码。SWE.6 合规报告对客户/审计方是假阳性。

**SHALL 条款**

- **SHALL-W3.1**: "测试用例定义"检查项必须真实解析 spec 文件（复用 `yuleosh.spec.validate.parse_spec`，以 `SpecDocument.scenarios` 或 requirements 中可识别用例条目计数），不再硬编码 True。
- **SHALL-W3.2**: 当 spec 解析成功且提取到用例时，检查项结果为通过，详情必须展示真实数字（如 `"3 个 (解析自 spec)"`）。
- **SHALL-W3.3**: 当 spec 无法解析（格式非法/无用例条目/解析异常）时，检查项结果必须为不通过或显式标注 `"unknown (manual)"`，**不得**报 True。
- **SHALL-W3.4**: "测试环境配置"检查项必须基于真实文件存在性判定（如 `.osh/ci-config.yaml`），不得硬编码 True。
- **SHALL-W3.5**: `--report` 生成的 swe6-report.json 中 `test_cases` 字段必须来自真实解析结果；来源必须注明（如 `"source": "parsed from spec"` / `"manual"`），不得出现无来源的硬编码数字。
- **SHALL-W3.6**: spec 文件不存在时仍报错退出（既有行为保持）。
- **SHOULD-W3.7**: 其余检查项（追溯矩阵、测试报告等）若无法真实判定，必须标注 "probe (manual verification required)" 而非无条件 ✅。

**GIVEN/WHEN/THEN**

- GIVEN 一个含 3 个用例条目的合法 spec 文件，WHEN 执行 `yuleosh swe6 check`，THEN 输出"测试用例定义 ✅ 3 个 (解析自 spec)"且 `--report` 中 `test_cases == 3`。
- GIVEN 一个不含用例条目/非法的 spec 文件，WHEN 执行 `yuleosh swe6 check`，THEN "测试用例定义"不得为 ✅，报告标注 unknown/manual。
- GIVEN `.osh/ci-config.yaml` 缺失，WHEN 执行 `yuleosh swe6 check`，THEN "测试环境配置"为 ❌（不再恒 ✅）。

---

### W4: session 迁移加 hex 校验（来源 COR-W3 / Fix 7）

**现状问题**（实测 store.py:164-176）：迁移条件 `WHERE length(token) != 64` 假设"64 字符 = sha256 hexdigest"，但恰好 64 字符的明文 JWT（短 payload 时可能）不会被迁移，明文滞留 DB。

**SHALL 条款**

- **SHALL-W4.1**: 会话 token 迁移逻辑必须校验 token 是否为合法 sha256 hex（`re.fullmatch(r"[0-9a-f]{64}", token)`），仅跳过**已是 64 位 hex** 的 token；恰好 64 字符但含非 hex 字符（如 base64url 的 `-`、`_`）的明文 token 必须被迁移为 hash。
- **SHALL-W4.2**: 迁移后 DB 中不得残留任何非 hex-64 的明文 token（对既有库做全量扫描断言）。
- **SHALL-W4.3**: 已迁移为 hash 的 token 不得被重复迁移（幂等）；`_session_token_hash` 对已 hash 值再次 hash 不得发生（跳过逻辑正确）。
- **SHALL-W4.4**: 迁移逻辑对空 token / NULL token 必须安全跳过或清理，不得抛异常中断建库。
- **SHOULD-W4.5**: 建议采用 Python 侧过滤（读全量 → 正则过滤 → 批量 UPDATE），避免 SQLite `GLOB` 对旧版本兼容性的依赖；两条路径任选其一，验收以行为为准。

**GIVEN/WHEN/THEN**

- GIVEN 一个恰为 64 字符的明文 JWT（含 `-`/`_`/`.` 等非 hex 字符），WHEN 打开 store 触发迁移，THEN 该 token 被改写为 sha256 hex，原明文不再存在。
- GIVEN 一个已是 64 位 hex 的 token，WHEN 打开 store 触发迁移，THEN 该行不变（幂等）。
- GIVEN 一个 40 字符明文 JWT，WHEN 迁移，THEN 与 v3.6.1 行为一致被 hash。

---

### W5: sandbox 插件兼容性评估 + extra_read_dirs 白名单（来源 COR-W5 / Fix 8）

**现状问题**（实测 plugins/sandbox.py:139-167）：P2-2 修复把读模式也纳入目录白名单（"读默认允许 → 收紧为同样受控"），行为变更后插件读取插件目录外文件（如 `/etc/os-release`、工具链路径）一律 `SandboxViolation`，既有插件兼容性未评估。

**SHALL 条款**

- **SHALL-W5.1**: 必须审查 `plugins/` 下全部插件对 `open()` 的用法，产出插件→外部读取需求清单（哪些插件需要读哪些目录/文件），审查结论写入本 spec 的 delta 文档（spec-delta.md 附录）。
- **SHALL-W5.2**: `_restricted_open` 必须支持显式白名单扩展 `extra_read_dirs`（可选参数，默认空）；插件读取白名单内目录文件时放行，读取白名单外仍 `SandboxViolation`。
- **SHALL-W5.3**: 白名单扩展仅影响**读模式**；写模式必须保持严格（仅插件自身目录），任何插件不得通过 extra_read_dirs 获得写权限。
- **SHALL-W5.4**: 既有安全属性不得回退：路径校验仍为 `resolve() + relative_to`（防前缀绕过/符号链接逃逸），白名单目录也必须 resolve 后校验。
- **SHALL-W5.5**: 审查后确认**无需外部读取**的插件：行为与 v3.6.1（P2-2 后）完全一致，零回归；确认**需要外部读取**的插件：必须通过白名单显式放行并在插件 manifest/文档中声明，禁止静默放宽全局读权限。
- **SHALL-W5.6**: 现有 sandbox 测试（test_backlog_p1_v350.py:563-590 区域）保持全绿；新增 extra_read_dirs 放行用例与白名单外拒绝负例。

**GIVEN/WHEN/THEN**

- GIVEN 某插件 manifest 声明 `extra_read_dirs=["/etc"]`，WHEN 插件读取 `/etc/os-release`，THEN 放行；读取 `/var/log/syslog`（白名单外）THEN 仍 `SandboxViolation`。
- GIVEN 无白名单声明的插件，WHEN 读取插件目录外文件，THEN `SandboxViolation`（与 v3.6.1 收紧后行为一致，不回归）。
- GIVEN 插件尝试向 `/tmp/x` 写入，WHEN 即便该插件有读白名单，THEN 仍被拒绝（读写权限隔离）。
- GIVEN 插件读取 `/etc/../etc/passwd` 或符号链接指向白名单外的文件，WHEN resolve 后校验，THEN 拒绝（resolve+relative_to 保留）。

---

### W6: preview 缓存 owner 隔离（来源 SEC-W4 / Fix 9）

**现状问题**（实测 preview.py:512-520, 657-665）：`_repo_cache` 键为 `sha256(repo_url)`，任何知道 repo URL 的用户可命中他人预览结果；预览报告含仓库代码结构信息，跨用户可读。

**SHALL 条款**

- **SHALL-W6.1**: `_repo_cache` 键必须从 `url_hash` 改为 `(user_key, url_hash)` 元组；创建与命中路径必须使用同一键构造逻辑。
- **SHALL-W6.2**: `user_key` 必须从当前请求身份派生：已登录用户 → 会话用户 ID（`current_user`/`get_session_user` 可解析值）；未登录 → 客户端 IP 的 hash（与限流同维）；同一用户两次请求必须得到相同 user_key。
- **SHALL-W6.3**: 用户 A 的预览结果不得被用户 B 命中（构造两用户同 repo_url 用例，断言 B 不命中 A 的缓存，即使结果已 completed 且在 TTL 内）。
- **SHALL-W6.4**: 同一用户对同一 repo_url 的缓存命中语义保持（TTL、completed 状态、preview_id 返回格式不变）。
- **SHALL-W6.5**: 缓存淘汰/清理逻辑（`_cleanup_expired_results`、`_preview_request_log` 等）不得因键结构变化而失效；既有 preview 限流（_ThreadSafeDict）保持。
- **SHALL-W6.6**: `preview_id` 读取路径（GET /assess/<id>）不依赖 `_repo_cache`，必须保持 v3.6.1 行为（id 已含随机性，读取路径不受键变更影响）。

**GIVEN/WHEN/THEN**

- GIVEN 用户 A（user_id=1）POST 提交 repo_url=X 并完成分析，WHEN 用户 B（user_id=2）POST 相同 repo_url=X，THEN B 不得命中 A 的缓存（返回新分析或独立缓存条目），且 B 的 preview_id 与 A 不同。
- GIVEN 用户 A 再次 POST repo_url=X，WHEN 结果在 TTL 内且 completed，THEN A 命中自己缓存（`cached: true`）。
- GIVEN 未登录用户（IP 相同）两次 POST repo_url=X，WHEN IP 相同，THEN 命中同 IP 自己的缓存（同 user_key）。

---

### W7: 批量 subprocess timeout + demo_uart 去 shell（来源 SEC-W6 / Fix 10）

**现状问题**（实测）：src/ 全库 123 处 `subprocess.run` 无 timeout，CLI/CI 内部调用遇网络/挂起 git 无限阻塞；`src/cli/commands/demo_uart.py:106` 仍 `shell=True` + `"-j$(sysctl -n hw.logicalcpu 2>/dev/null || echo 4)"` shell 插值。

**SHALL 条款**

- **SHALL-W7.1**: `demo_uart.py` 的 make 调用必须改为 argv 形式（`["make", "-j", str(os.cpu_count() or 4)]`），`shell=True` 必须移除；不得再出现 shell 插值。
- **SHALL-W7.2**: `ci/*`、`pipeline/*`、`evidence/*`、`cli/*` 下所有 subprocess 调用（除已带 timeout 的 hot path：api/dashboard.py:521=300s、api/ci.py:39=180s、api/review.py:36=120s、ci/runner.py 等）必须补 `timeout=`：普通命令 ≥30s，编译/打包类 ≥120s（上限 300s）。
- **SHALL-W7.3**: 超时行为必须显式处理（`subprocess.TimeoutExpired` 捕获 → 明确失败/报错路径），不得让超时异常冒泡为未处理崩溃；被超时终止的子进程必须被清理（kill 进程组或等效）。
- **SHALL-W7.4**: 本次改动不得改变各命令的正常返回语义与退出码（仅对"无限挂起"变为"超时失败"这一行为变更）。
- **SHALL-W7.5**: 全量回归必须通过（重点 `test_pipeline_async_runner.py`、`test_ci_*`、`test_cli_*`）；超时时间不得设得过短导致正常构建（如大项目 make）误杀。
- **SHOULD-W7.6**: 新增至少一个超时负例（monkeypatch 子进程 sleep 超过 timeout → 断言超时失败路径被触发）。

**GIVEN/WHEN/THEN**

- GIVEN `yuleosh demo uart --build` 在 host 模式执行，WHEN make 正常完成，THEN 返回码/输出与 v3.6.1 一致（无 shell 依赖下仍成功）。
- GIVEN 某 subprocess 调用挂起超过 timeout，WHEN 执行该命令，THEN 在 timeout 后显式失败（错误信息含超时提示），不无限阻塞。
- GIVEN 正常 CI/pipeline 流程，WHEN 所有子进程在 timeout 内完成，THEN 行为与 v3.6.1 完全一致（无回归）。

---

## 2. Track4 — 杂项（4 项）

### M1: 后端 XSS 消毒换 html.parser 白名单（来源 ARC-W6 / Fix 12）

**现状问题**（实测 kb/models.py:160-200）：`_strip_html` 为正则黑名单（删 script/iframe/svg/math 等危险标签 + 事件属性 + javascript: 协议 + 实体混淆），黑名单模式存在嵌套/变体混淆漏网可能；前端 escape-first 是主防线，后端为纵深防御。Fix 12 提供两个方向：① 换 html.parser 白名单（剥离所有标签、保留文本）；② 保持正则但补嵌套混淆用例。

**SHALL 条款**

- **SHALL-M1.1**: `_strip_html` 必须能剥离/中和嵌套混淆的恶意构造（如 `<scr<script>ipt>`、大小写/空白变体、双编码实体），输出中不得残留可执行 HTML/事件属性/危险协议。二选一实现，验收以行为为准。
- **SHALL-M1.2**（若选 html.parser 白名单）: 解析必须剥离**所有**标签但保留标签内文本内容（如 `<b>hello</b>` → `hello`）；文本中的 `<` 字面量（如代码样例 `<vector>`、`<int>`）不得被误删为空洞。
- **SHALL-M1.3**（若选正则+补用例）: 现有 test_kb_sanitize_xss.py 必须全绿，并新增 ≥5 个嵌套/混淆负例（双编码、嵌套标签、属性内混淆、`<svg><script>`、大小写混写实体）。
- **SHALL-M1.4**: 无论哪条路径，现有合法内容行为不得回归：KB 文章/FMEA/lesson 中正常 markdown 文本、代码块、非 HTML 特殊字符保持可用（test_kb_sanitize_xss.py 全部既有正例保持）。
- **SHALL-M1.5**: 消毒应用于写入路径的既有调用点（`sanitize_kb_article_fields` / `sanitize_lesson_fields` / `sanitize_fmea_fields`）不变量保持（输入 dict → 输出 dict，字段逐一消毒）。
- **SHOULD-M1.6**: 新实现应在文档/注释中说明白名单/黑名单取舍与已知限制；若选 html.parser，需注明其不是安全边界（纵深防御，前端 escape-first 仍是主防线）。

**GIVEN/WHEN/THEN**

- GIVEN 提交含 `<scr<script>ipt>alert(1)</scr</script>ipt>` 的 KB 字段，WHEN 消毒，THEN 输出无可执行 script 残留。
- GIVEN 提交含 `&#106;&#97;vascript:alert(1)` 双编码实体，WHEN 消毒，THEN 无 `javascript:` 协议残留。
- GIVEN 提交含 `<b>粗体</b>` 与代码样例 `<vector>`，WHEN 消毒，THEN 输出含 `粗体` 与 `vector` 文本（不丢内容）。
- GIVEN 既有 test_kb_sanitize_xss.py 全部用例，WHEN 在新实现下运行，THEN 全绿。

---

### M2: 静态资源 Cache-Control immutable（来源 SEC-P2）

**现状问题**（实测 server.py:254-262 `_serve_static`）：静态资源（JS bundle 等）无 Cache-Control/ETag，每次全量传输；frontend/out 为预构建产物，bundle 体积不小。

**SHALL 条款**

- **SHALL-M2.1**: 文件名带内容 hash（`[name].[hash].js` 等 `_next/static/` 构建产物）的静态资源响应必须带 `Cache-Control: public, max-age=31536000, immutable`。
- **SHALL-M2.2**: HTML 文档（`.html`、`/`、`/index.html`）**不得**加长缓存头（必须 `no-cache` 或等价，保证更新可见）。
- **SHALL-M2.3**: 无法确认内容 hash 的常规资源（无 hash 的 css/js/png 等）不得使用 immutable；可加短 max-age 或保持无缓存头（二选一，验收以"HTML 不缓存 + hash 资源 immutable + 无 hash 资源不 immutable"为判据）。
- **SHALL-M2.4**: 缓存头改动不得影响 404/500 错误路径与 Content-Type/安全头（`_add_security_headers` 保持）。
- **SHOULD-M2.5**: 判定"是否 hash 文件名"应使用稳定规则（如文件名匹配 `/^[a-zA-Z0-9_-]{8,}\.(css|js|woff2?|png|svg)$/` 且位于 `_next/static/` 或等价构建目录），避免对用户上传资源误加 immutable。

**GIVEN/WHEN/THEN**

- GIVEN 请求 `/_next/static/chunks/app-3f2a9b.js`（hash 名），WHEN `_serve_static` 响应，THEN 含 `Cache-Control: public, max-age=31536000, immutable`。
- GIVEN 请求 `/` 或 `/index.html`，WHEN 响应，THEN 不含 immutable（HTML 不缓存）。
- GIVEN 请求无 hash 的 `logo.png`，WHEN 响应，THEN 不得带 immutable。

---

### M3: AUTH_ENABLED 双定义合并单一来源（来源 v3.6.1 P2-①）

**现状问题**（实测）：`src/yuleosh/ui/auth.py:36` 定义 `AUTH_ENABLED = not _AUTH_DISABLED`（`_AUTH_DISABLED` 读 `YULEOSH_AUTH_DISABLED.lower() in ("1","true","yes")`）；`src/yuleosh/ui/server.py:70` 独立重算 `AUTH_ENABLED = os.environ.get("YULEOSH_AUTH_DISABLED", "").lower() not in (...)`。两处逻辑重复，未来改一处漏一处。另 `api_routes.py:37` 有 ImportError 局部 fallback `AUTH_ENABLED = False`（非定义，但需确认不产生第三语义）。

**SHALL 条款**

- **SHALL-M3.1**: `AUTH_ENABLED` 必须只有一个定义来源（`ui/auth.py`），`server.py` 通过 `from yuleosh.ui.auth import AUTH_ENABLED` 引用，不得在 server.py 独立重算 env。
- **SHALL-M3.2**: 合并后行为不变：默认 fail-closed（未设 `YULEOSH_AUTH_DISABLED` → AUTH_ENABLED=True）；`YULEOSH_AUTH_DISABLED=1|true|yes`（大小写不敏感）→ False；其余值 → True。
- **SHALL-M3.3**: `api_routes.py:37` 的 ImportError fallback 必须审查：若为死代码可删除；若为真实降级路径，必须注释说明且不得与单一来源冲突（不得产生"AUTH_ENABLED=False"的第三语义）。
- **SHALL-M3.4**: 合并后 `_check_auth`、健康检查、登录流程等所有引用点行为与 v3.6.1 一致（全量回归）。
- **SHOULD-M3.5**: 新增测试验证 env 三态（未设 / `1` / `true` / `yes` / 其他值）下两处引用值一致（或直接断言 server.py 引用同一对象）。

**GIVEN/WHEN/THEN**

- GIVEN 环境变量 `YULEOSH_AUTH_DISABLED` 未设置，WHEN server 启动，THEN `server.AUTH_ENABLED is ui.auth.AUTH_ENABLED` 且均为 True（fail-closed）。
- GIVEN `YULEOSH_AUTH_DISABLED=yes`，WHEN server 启动，THEN AUTH_ENABLED=False（dev 模式放行）。
- GIVEN 修改 `ui/auth.py` 的判定逻辑，WHEN server 重启，THEN server 侧自动跟随（无第二份逻辑可遗忘）。

---

### M4: 公开路径白名单支持 query 串匹配（来源 v3.6.1 P2-②）

**现状问题**（实测 server.py:304 `_check_auth`）：`if self.path in _PUBLIC_PATHS or self.path.startswith(_PUBLIC_PREFIXES)`——`self.path` 含 query 串时（如 `/api/health?x=1`）不在白名单精确集合中 → 被误判为需鉴权 → 401。前端/监控带 query 访问公开端点会失败。

**SHALL 条款**

- **SHALL-M4.1**: `_check_auth` 的白名单匹配必须剥离 query 串（`urllib.parse.urlsplit(self.path).path`）后再与 `_PUBLIC_PATHS` 匹配；`/api/health?token=abc` 必须与 `/api/health` 同判公开。
- **SHALL-M4.2**: 前缀白名单（`/static/`、`/assets/`、`/_next/`）必须继续以 path 部分前缀匹配（带 query 的资源请求不被误拒）。
- **SHALL-M4.3**: 带 query 的**非公开**路径（如 `/api/project/list?x=1`）必须仍然需要鉴权（query 不得被用来绕过白名单判定）。
- **SHALL-M4.4**: 鉴权失败响应语义不变（API → 401 JSON；页面 → 登录页/302，与 v3.6.1 一致）。
- **SHOULD-M4.5**: 新增测试覆盖：公开路径+query → 放行；非公开路径+query → 401；前缀路径+query → 放行。

**GIVEN/WHEN/THEN**

- GIVEN 请求 `/api/health?source=monitor&v=2`，WHEN `_check_auth` 判定，THEN 放行（200）。
- GIVEN 请求 `/api/project/list?org=1`（未带凭据），WHEN `_check_auth` 判定，THEN 401（query 不产生白名单绕过）。
- GIVEN 请求 `/static/app.js?cb=123`，WHEN `_check_auth` 判定，THEN 放行。

---

## 3. 全局约束（适用全部 W/M 项）

- **SHALL-G.1**: 所有行为变更项（W2/W5/W6 为高关注）必须附带正例 + 负例测试，测试 ID 见 acceptance-matrix.md。
- **SHALL-G.2**: 全量回归基线（v3.6.1）9794 passed / 0 failed 不得下降（新增测试只增不减）；覆盖率 ≥84.10% 不降。
- **SHALL-G.3**: 不引入新依赖（标准库优先；html.parser 为 stdlib）；不修改 frontend/ 产物（Track3 范围外）。
- **SHALL-G.4**: 每项修复的代码须注明来源（`W-x`/`M-x` 注释），与 v3.5.0/v3.6.1 既有 P1-x/W-xx 注释风格一致。
- **SHALL-G.5**: 变更不得破坏公开 API 契约：/api/v1/* 响应结构、错误码语义、CLI 子命令名与退出码、既有测试全部保持。
- **SHOULD-G.6**: 小克开发过程中对 spec 有歧义处先问小马，不得自行扩大范围（尤其 W5 插件白名单、M1 双路径选型需先与上游确认）。

## 4. 明确不在本版范围（防范围蔓延）

- Track2 架构收敛（认证三套合一、审计统一、路由双轨、Store 抽象、cli 拆分、dashboard 拆组件）→ v3.8.0
- Track3 前端安全（token cookie 迁移、CSP）→ v3.9.0
- yuleASR-Configurator 安全项 → 另行排期
- SEC-W3 JWT secret 默认值确认 → 实施阶段第一优先核查项（若发现硬编码默认值，升级为 critical 并立即上报）
- COR-W4 preview zip 解压二次校验（suggestion，可选跟进）
