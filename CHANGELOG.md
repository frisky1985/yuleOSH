# Changelog

本文件记录 yuleOSH 的版本变更。版本号遵循语义化版本（SemVer）。

## [Unreleased]

### 新增

- **LLM token 级流式输出（dashboard「LLM 实时输出」面板）**
  （`llm/streaming.py`、`llm/client.py`、`llm/providers/{base,deepseek,openai,ollama}.py`、`realtime.py`、前端 `llm-stream-bus.ts` / `llm-live-output-panel.tsx`）
  - pipeline run 内（`LLMCallContext`）自动开启：provider 逐 token delta 经 `StepStreamEmitter` 合并节流后以 ephemeral `llm_delta` 事件直推 SSE，前端面板逐字增长；不进 replay 历史，不会挤出 `stage_start` 等关键事件。CLI/单测直调（无 ContextVar）与默认 `stream=False` 路径行为字节级不变。
  - DeepSeek / OpenAI provider 走 OpenAI 兼容 SSE（`stream_options.include_usage` 末帧补 usage，本地端点自动省略）；**Ollama provider 采用原生 `/api/chat` NDJSON 流式（方案 A），保留 `options.num_ctx` 透传** —— 方案 B（改走 `/v1/chat/completions` 复用 SSE 解析器）会丢失 num_ctx，长输入撞 `exceed_context_size_error` 的坑是前人刻意修过的，不拿稳定性换演示效果。实测本地 `qwen2.5-coder:14b`：请求体 `stream=true` + `num_ctx=32768`，首 delta 前触发 `on_stream_start`，逐 delta 回调，usage 取 `done` 帧 `prompt_eval_count/eval_count`。
  - 降级语义诚实：首个 delta 前失败可指数退避重试；已收 delta 后失败/零内容一律抛 `RuntimeError`（半截输出绝不静默当成功），由 `provider_fallback` 链或 legacy `chat_completion` 非流式重试兜底；端点不支持 SSE 时整段结果一次性补发，面板不只收到空帧。
  - 评审修复（详见 `docs/planning/llm-streaming-review-handoff-09-26.md`）：**P0-1** `OpenAIProvider.chat()` 补上流式分流分支（此前 body 带 `stream=true` 却走整段 `json.loads`，必现解析失败并白耗重试）；**P0-2** `OllamaProvider` 解除 `stream: False` 写死（此前本地 4B 路径拿不到任何 delta，面板永远空转）；**P1-3** `chat_completion` emitter 生命周期包 `try/finally`（此前失败路径不 close，前端「流式输出中」永久转圈）。P2：本地端点判定收口 `streaming.is_local_endpoint`、`stream_chat_response` docstring 写明降级责任方、`LLMConfig` 流式 Callable 字段 `field(compare=False, repr=False)` 隔离。
  - 复评后修复（R1/R2，2026-09-27）：`LLMClient.call` 曾**原地改写调用方传入的 `LLMConfig` 实例**（写入 `stream=True` + 两个回调），`finally` 里又**硬编码**还原成 `stream=False / on_chunk=None / on_stream_start=None`。两个后果：① 调用方显式传入的 `stream=True` 被静默降级（既有用例的 config 原值恰为 `False`，**无法区分**「还原原值」与「强制置假」两种语义）；② 并发复用同一 config 实例时相互踩踏 —— 先返回者的 `finally` 把后返回者的 `on_chunk` 清空，后者剩余 delta 全丢。现改为 `dataclasses.replace(...)` 生成**带回调的副本**交给 provider 链，调用方实例全程只读，`finally` 只需关闭 emitter。可达性核查：②在当前代码库不可达（`llm_gateway.py` / `anchoring.py` 均每次新建 config），按防御性修复处理。
  - 新增 `tests/test_llm_streaming.py`（49 项，全部 mock 网络；P0-1/P0-2/P1-3 与 R1/R2 各带 RED→GREEN 回归用例）与前端 `llm-stream-bus.test.ts`。

### 修复

- **门禁证据可达性与完整性指纹补全（P0-A/B/C）**
  （`pipeline/gates.py`、`cli/commands/consistency.py`、`pipeline/session_prune.py`）
  - **P0-A 门禁读不到自己的产物**：`_ARTIFACT_CANDIDATES` 只列了 4/11 个「产物名 ≠ `<step_key>.json`」的步骤，另外 7 步（`super-analysis`→`startup-analysis.md`、`prd`→`prd.md`、`architecture`→`architecture.md`、`development`→`development-plan.md`、`test-planning`→`test-plan.md`、`test-qualification`→`qualification-test.json`、`final-report`→`final-report.md`）的产物**从未被门禁打开**。最尖锐的是 G10：`ci/gate_policy.py` 把 `test-qualification` 列为 `GATE_BLOCK`，而它的唯一证据 `qualification-test.json` 门禁根本没读过 —— 判罚所依据的裁决，门禁自己没看。实测 run `57fa80e754ed`：门禁可达的步骤 **17/24 → 24/24**。
  - 同时新增 `_scan_artifact_step_map()`：按产物自报的 `step` 字段归属证据，覆盖「名字与 step_key 无关」的子产物（`c-coverage-gate.json`、`review-*.json`、`embedded-*.json`）。实测该兜底在本 run 上未带来候选表之外的额外证据，属**冗余保险**；**候选表对 Markdown 产物仍是唯一通路**（md 无 `step` 字段可扫）。这一区分由变异注入确认：删 `prd` / `final-report` 条目测试转红，删 `test-qualification` 条目**不**转红（被 step 兜底接住）。
  - **P0-B 完整性指纹残缺**：`artifact_hashes` 只对 `<step_key>.json` 取哈希、从不查候选表，且门禁层没有会话级索引 —— 实测同一 run 的指纹只覆盖 **14/50** 个产物，**35 个**（含 GATE_BLOCK 的 `c-coverage-gate.json`、12 个 `review-*.json`、`embedded-*.json`、`ctest-junit.xml`）无任何防篡改保护，G5/G8/G9/G10 四个门禁的 `artifact_hashes` **全为空**。现补三处：门禁哈希改走 `_artifact_paths()`；新增 `artifact_index()` 会话级索引（递归、排除 `gate-summary.json` 自身与每轮必变的 `session.json`、跳过点文件）→ 覆盖 **49** 个。
  - 同族第二个缺口一并修掉：`cli/commands/consistency.py` 的指纹读的是 `gate-summary.json` 里**冻结**的哈希 —— 两次快照比对只能发现「重新跑过」，发现不了「跑完之后就地改过文件」，而后者恰是「完整性指纹」要防的（实测：改 `c-coverage-gate.json` 后指纹不动）。现改为**现场重扫目录**优先（`artifact_source=live_scan`），冻结快照退为兜底（旧格式 `gate-summary.json` 仍可读，`artifact_source=gate_artifact_hashes`）。
  - **P0-C 产物缺失与产物通过不可区分**：步骤自报 `completed` 而找不到任何产物时，状态被原样保留 → **删掉产物，门禁照样绿**。现降级为 `not-run`（无证据），`REUSABLE_STEPS`（`spec-check` / `codegen-deploy`）因复用是设计允许而豁免。run `57fa80e754ed` 上实测：24 步证据齐备，**0 步降级**，run 结论仍为 `unverified`（阻塞 G3/G7/G8/G9）—— 即本修复**不改变历史 run 的结论**，堵的是将来的误判。
  - 用新逻辑重算同一 run，还检出旧逻辑漏掉的两处：`G6` `passed`→`stale`、`G7` `skipped`→`stale`，原因是 `c-unit-test.json` / `misra-review.json` / `integration-test.json` 的 `session` 字段仍是旧 run `gpio-verify-4b-deadlockfix` —— 与上面的步骤缓存分级指向同一事实（`gate-summary.json` 写于 09-22，早于 `stale` 判定引入）。
  - 新增 `tests/test_gate_artifact_coverage.py`（26 项）；`test_gate_status_aggregation.py` 增加 `_write_all_artifacts()`，使「全部步骤完成」这一前提包含真实证据；`test_consistency_cli.py` 的「产物变化」类断言改为改真实产物字节（改 summary 里的冻结哈希已不再有意义）。**变异注入**：撤 P0-A（md 条目）/ P0-B（哈希回退旧写法）/ P0-C（去掉降级）分别转红。

- **证据包不再漏进源码仓库（`OSH_HOME` 双真值收口）**
  （`api/__init__.py`、`api/evidence.py`、`api/dashboard.py`、`tests/conftest.py`）
  - **根因**：`OSH_HOME` 在各 API 模块里是 **import 期快照**（`api/__init__.py:23`、`dashboard.py:39`），而 `os.environ["OSH_HOME"]` 可以在运行时被改 —— 同一进程里存在**两份真值**。dashboard 的证据生成把 bundle 位置交给 `dashboard.OSH_HOME`、把写入目标交给 `evidence.snapshot_bundle` 内部的 `from . import OSH_HOME`（即 `api.OSH_HOME`）；两个快照一旦分叉，测试的隔离就失效，生成的证据包落进**仓库**。实测两处落点：`.osh/evidence/` 累积 46 个空壳包（33×174B + 13×~890B）外加 `compliance-pack.zip`；`src/.osh/evidence/` 同类空壳（`parent.parent.parent` 从 `api/` 往上三层，`api.PROJECT_ROOT` 实为 `src`），自 09-02 起漏了两周。空壳的形态特征即「只含 37 字节的 `audit-manifest.json`」，且删掉后每次跑测试还会再长。
  - **修复**：新增 `api.resolve_osh_home(current)` 做**调用时**解析，优先级「本模块常量被显式覆盖 > 运行时 env > import 期快照」，把测试中长期并存的两套隔离手法（`monkeypatch.setenv` 232 处 / `monkeypatch.setattr` 82 处）都认下来。不能简单地「env 优先」：`tests/test_api.py` 在**收集期**就用 `os.environ.setdefault` 把 env 钉在仓库根，env 优先会反过来废掉 `setattr` 那一类隔离（实测 28 项失败）。
  - `evidence.py` 的 6 处落盘 / 读取位置改走 `_ev_home()`；`snapshot_bundle(bundle_dir, osh_home=None)` 新增 `osh_home` 参数，**dashboard 显式传入自己的解析结果** —— 这是消除跨模块分叉的关键一步。`dashboard.py` 的证据路径（`_load_gap_items` / `_find_latest_manifest` / evidence generate 守卫 / worker 落盘）同源化；纯只读且自洽的 coverage / misra / projects 路径**未动**，控制爆炸半径。
  - **自愈网**：`conftest.py` 在 `pytest_configure` 记录仓库两处 evidence 目录的包集合，`pytest_sessionfinish` 清掉**本会话新增**的包并逐条打印路径（`OSH_ALLOW_EVIDENCE_WRITES=1` 可关闭，零开销）。与既有的 MagicMock 落盘拦截同一模式。
  - **验证（严格同序对照）**：68 个测试文件 / 1669 项 —— 改动前 `14 failed / 1651 passed`，改动后完全一致，**0 回归**（14 项为既存失败）。泄漏维度：同一批跑完，基线新增 3 个包（174B / 891B / 174B，与历史空壳同形），修复后 **0 个**。新增 `tests/test_osh_home_resolution.py`（13 项：判定规则 + 两处落点 + dashboard 跨模块同源）；撤掉修复后 12/13 变红，非空转。
  - 顺带清理：`src/.osh/evidence/` 的 14 个空壳包已移除（移入回收站）。
  - 顺带修正：`tests/test_v361_critical_fixes.py::TestErrorMasking::test_pipeline_run_masks_details` 的**断言契约**。该用例长期处于既存失败，原因是它断言 `_run_pipeline` 返回 `500 + "Internal server error"`，而 `_run_pipeline` 自编排器改为后台执行后就是**异步**接口 —— 同步阶段只做校验与排队并立即返回 `run_id`，编排器内的异常由 `_run_orchestrator_job` 兜底、经 `_errors.internal_error` 记录，**不经过本函数的返回值**，故该 500 断言不可能成立（原先它只是碰巧从别处拿到 403 而“看起来接近”）。现改为验证真实存在的同步契约：`spec` 与 `project_dir` 越出 `OSH_HOME` 时返回 **403 + 静态文案**，不回显任何内部路径。生产代码未改动。

- **run 结论不再绕过门禁证据（根治「表面全绿」）**
  （`pipeline/gates.py`、`pipeline/orchestrator.py`、`pipeline/session.py`）
  - **证据时效性判定（新增 `stale` 状态）**：每个步骤产物自带 `session` 字段，记录产出它的 run。该字段与本轮 `session.name` 不符 → 门禁判 `stale`（复用了旧轮次的验证证据），而不是静默按 `passed` / `skipped` 计。`REUSABLE_STEPS`（`spec-check` / `codegen-deploy`）跨 run 复用是设计允许的，豁免此判定。
  - **无证据不再等于通过**：`_worst_status([])` 由 `passed` 改为 `not-run` —— 本轮没有该门禁的任何步骤记录时，如实报告「未执行」，不再 fail-open。
  - **run 级结论由门禁证据决定**：新增 `classify_run_outcome()`，GREEN 需同时满足「session completed + 有可读的门禁汇总 + 全部非咨询门禁 passed + 无步骤错误」。此前只校验前两项，导致 `G7` 整门 skipped 的 run 仍打印 `GREEN — all gates passed`。三色分级相应改为 GREEN / **UNVERIFIED** / RED，并列出未被验证的门禁。
  - **显式声明「不适用」**：部分门禁在特定配置下确实不适用（planning 模式没有代码生成类验证），但「步骤跳过了」不足以证明这一点 —— 同一个信号也覆盖「没人跑它」。因此由调用方显式声明（`session.config["na_gates"]` 或环境变量 `OSH_NA_GATES=G3,G8`），声明只豁免 `skipped` / `not-run`，**不豁免 `stale` / `failed`**。
  - 门禁汇总新增 `not_run_gates` / `stale_gates` 字段；`session.json` 新增 `gate_verdict`（`outcome` / `reason` / `worst_gate_status` / `blocking_gates` / `declared_na`），API 与 dashboard 可直接读取，无需解析控制台输出。
  - 动因：run `57fa80e754ed` 24/24 步 `completed`、`G7` 全 skipped、其中三个产物还是两天前 run 的，却打印 `GREEN — all gates passed`。

### 变更

- **移除误跟踪的 CI 产物 `src/.osh/ci/layer1-91df2f15.json`**（`git rm --cached`）
  - 该文件是 2026-07-10 一次**失败**的 layer1 运行记录（内容里还留着他人机器的路径 `.../stefan/.openclaw/workspace/...`），08-22 `ceb3e494` 误提交入仓库。`git rm --cached` 从索引移除后，路径重新落入 `.gitignore:136` 的 `.osh/` 规则覆盖范围（`git check-ignore --no-index` 已验证），不会再被误提交。

- **sessions 根独立可配 + 分层保留（`OSH_SESSIONS_DIR`）**
  （`pipeline/session.py`、`engine/subprocess_executor.py`、`api/{artifacts,logs,tests}.py`、`pipeline/session_prune.py`、`tests/conftest.py`）
  - **新增 `OSH_SESSIONS_DIR`**：把 sessions 根从 `<OSH_HOME>/.osh/sessions` 解耦出来。优先级 `OSH_SESSIONS_DIR` > `OSH_HOME` > cwd；写入侧（`PipelineSession` / `subprocess_executor._resolve_session_dir`）与读取侧（三个 API 模块）共用 `resolve_sessions_root()`，不再各写一份而漂移。用途一：把 run 证据放到独立卷；用途二：测试隔离（见下）。**未设置时行为与原先完全一致**。
  - **修复测试泄漏**：`test_api.py` 在模块导入期把 `OSH_HOME` 钉到仓库根（进程级），于是每个构造过 `PipelineSession` 的测试都往仓库自己的 `.osh/sessions` 漏一个目录 —— 实测累积 **3611 个**，占历史上出现过的全部 session 的 **99.6%**。`conftest.py` 现在把 `OSH_SESSIONS_DIR` 指向一个临时根并在 `pytest_sessionfinish` 回收，**不动 `OSH_HOME`**，因此 `test_api.py` 依赖的相对路径解析不受影响（早期直接抢占 `OSH_HOME` 的做法曾坏掉 11 个测试）。临时根保持 `<project>/.osh/sessions` 层级，因为 `to_dict` 靠向上三层反推 `project_dir`。
  - **新增 `pipeline/session_prune.py`**：按「可再生性」而非体积做分层保留 —— T0 运行态（空目录 / `created` 中止）整体回收；T1 汇总层（`session.json` / `gate-summary.json`）与 T2 LLM 产物（本地 4B 跑一轮 1.5–2 小时，不可再生）永久保留；T3 确定性证据（`VOLATILE_STEPS` 产物，分钟级可重跑）只保留在最近 `keep_last` 个 run 里。默认 `dry_run=True`，可用 `python -m yuleosh.pipeline.session_prune <project> --keep-last N [--apply]`。
  - 动因：单次 24 步真实 run 只写 51 个文件 / 89 KB（字节维度十年内都不构成风险），真正的代价是**目录数** —— `api/artifacts.py` 每次请求都要 `os.walk(OSH_HOME)` + 全量 `iterdir` + 逐个读 `session.json`，随历史线性退化。
  - 顺带记录一个相邻缺陷（**已于 2026-09-23 修复**，见本节末的「门禁证据可达性与完整性指纹补全」）：`gates._ARTIFACT_CANDIDATES` 曾漏了 `qualification-test.json`（G10 步骤的实际产物名）等 7 项，因此这些门禁读不到产物里的真实 verdict、只能退回 `session.steps` 的状态。本模块当时用一份显式补集兜住了清理场景。

- **步骤缓存分级：验证证据每轮重跑**（`pipeline/step_cache.py`、`pipeline/orchestrator.py`）
  - 缓存语义由「确定性步骤可缓存」改为按「是否属于本轮验证证据」分级：
    - `REUSABLE_STEPS`（`spec-check` / `codegen-deploy`）—— 输入/生成物类，输入未变时仍按指纹跨 run 复用；
    - `VOLATILE_STEPS`（`c-unit-test`、`misra-review`、`integration-test`、`qemu-verify`、`coverage-review`、`review-critical-safety`、`fault-injection`、`merge-gate`、`test-qualification`）—— 测试与验证结果类，**不再跨 run 复用**。
  - 每轮 pipeline 启动时自动清空验证结果类历史缓存（`purge_verification_cache`），并在控制台显式打印清理条数；调试可用 `OSH_KEEP_VERIFICATION_CACHE=1` 跳过。
  - 动因：验证步骤复用上一轮产物会把 RED/GREEN 固化成假象 —— `integration-test` / `misra-review` 曾命中旧缓存（`status=skipped`）导致 G7（SWE.5 集成）被判 skipped，而 run 仍报 `completed`。
  - 新增 `must_rerun()` / `purge_step_cache()` / `purge_verification_cache()`；`CACHEABLE_STEPS` 保留为 `REUSABLE_STEPS` 的兼容别名。

## [4.2.0] — 2026-09-02

自 `v4.1.0` 以来的功能增量版本（82 笔提交）。主线：合规交付闭环、日志中心、双角色视图与实时化改造。

### 新增功能

**证据与合规交付**
- 证据文件支持**单文件下载**：新增 `GET /api/v1/evidence/file`（bare name 校验 + symlink 越界防护，按扩展名映射 Content-Type），审计时无需下载整包再解压
- 证据文件列表默认折叠为前 10 条，超出可展开 / 收起（总数仍可见）
- 证据包历史版本快照与按版本下载（`GET /api/v1/evidence/pack?version=`）
- dashboard 真实证据生成结果并入历史快照

**日志中心**
- 摘要面板：按 run 折叠、时间范围切换（近 7/30/90 天 / 全部）、排序与状态筛选、run 状态徽标
- 检索结果：关键字高亮、导出 CSV、区分「导出当前」与「导出全部」、单条日志一键复制
- 新增全量导出端点 `GET /api/v1/logs/export`；run 展开显示日志文件列表；错误一键汇集（点击 run 联动检索）

**追溯与账户**
- 新增追溯矩阵端点 `GET /api/v1/matrix`（需求 ↔ 代码 ↔ 测试 ↔ 步骤 ↔ 证据）与前端追溯矩阵页
- 新增 `GET /api/v1/me/account` 账户信息查询与注销端点
- 决策者组合视图与合规就绪评分

**角色与导航**
- 登录按角色分流应用骨架（决策顶栏 / 工程左栏），视图严格按角色分流，移除 `?view` / localStorage 污染
- 抽出 `@/lib/role-view` 作为角色→视图单一事实来源；工程师视图新增窄屏抽屉（< 768px 可导航、可登出）
- 决策顶栏补「证据包」入口、工程师侧栏补「设备」「日志」入口（修复工程向页面不可达）
- 顶栏分组重排为 4 大类 + 可见组名标签；用户菜单升级 + 4 个 Dialog；顶栏 URL 携带 tab 同步激活
- 登录页演示账号面板展示决策者 / 工程师两角色账号与视图徽标，支持一键填入

**任务与进度**
- 长任务进度从单条进度条升级为「阶段步骤」可视化
- 任务型轮询改指数退避（1s → 5s）并抽出共享工具
- 阶段看板门禁高亮 + Loop Engineering 实时卡

### 修复
- **P0 生产缺陷**：`handler_helpers` 只把 `parsed.path` 交给 v1 dispatch，导致 GET 查询参数全部丢失（证据 / 差距 run 轮询的 `?task_id`、`?run_id` 失效，差距分析分页与 severity 过滤被忽略）→ 新增 `_api_v1_full_path` 将 query 拼回
- `handle_delete` 补 `/api/v1` 分发，修复所有 DELETE 端点不可达
- tenant 路由 Bearer-only 与前端 cookie 鉴权不匹配导致浏览器 / local-dev 报 401
- 切换账号后会话身份残留
- 登录 401 未透传真实错误文案
- 用户菜单脱离 base-ui Menu 状态机改纯 DOM 实现；顶栏与菜单下拉项改 `onClick`（修复 `onSelect` 失效）
- 应用外壳提升到 layout，点击左栏仅切换右侧内容

### 优化
- 工程视角侧栏按 V-model 开发主线重排并加分组分隔（入口 / 开发主线 / 基础设施 / 可观测性 / 合规交付），追溯矩阵图标与「项目需求」区分

### 基础设施
- SSE 替代轮询：后端通用 `_sse_stream` 泵 + 3 个端点（证据 / 批量修复 / 单条差距 run），前端 `subscribeSSE` 助手（EventSource 优先，连接失败自动降级轮询）
- LLM provider 健康诊断：`GET /api/v1/dashboard/llm-health`（配置检查 + `?live=1` 在线探测 + key 脱敏），前端新增 LLM 链路状态卡片
- 抽离共享 `apiFetch`，消除 9 处重复并统一 401 处理
- 双角色视图 Playwright 防回归闭环 + 零依赖登录烟雾脚本 `scripts/smoke_login.mjs`

## [4.1.0] — 2026-08-31

自 `v4.0.0` 以来的功能增量版本。包含头脑风暴清单 T1–T11 全量落地、Dashboard UX 重构与 HIL 测试分层可视化。

### 新增功能

**Dashboard UX 重构**
- 新建项目弹窗与「加载示例项目」按钮（创建项目双写 `org_projects` + `seed-demo` 一键示例）
- 加载示例项目升级为示例画廊弹窗，并标记示例项目
- 「我的用量」面板与模型设置弹窗（`/me/usage`、`/org/llm-config` 接口，组织级 LLM 模型配置 + 单用户用量统计，v9 迁移）
- 运行控制面板：勾选阶段 + 重跑 / 续跑 / 停止，运行 Pipeline 入口
- 差距分析支持逐条分析与运行，以及批量分析 + 批量修复（自动执行）

**头脑风暴 T1–T11**
- T1 勾选持久化（localStorage）
- T2 运行中锁定（遮罩 + 禁用）
- T3 状态徽章合并至进度行
- T4 多次运行历史（下拉切换）
- T5 成员移除
- T6 邀请「待接受」态（琥珀徽章）
- T7 权限矩阵批量编辑 + 审计日志（`role_permission_audit` 表 + 迁移 v11 + diff 日志）
- T8 生成进度可视化（阶段条）
- T9 证据包历史列表 + zip 下载
- T10 SSE 替代 1.5s 轮询（前端 EventSource + 后端 ThreadingHTTPServer 长连接）
- T11 真实 LLM 链路（PRICING_TABLE 补 `deepseek-chat` 别名；外部供应商凭证待充值后恢复）

**其他**
- 权限矩阵可编辑（前端编辑 + 后端 PATCH 派发修复）
- 成员列表超过 3 人折叠；运行控制按钮三色区分；TopNav 抽出共享组件（5 组导航归类）
- 测试分层总览（HIL CI Layer 2.5 可视化）：首页卡片 + 独立详情页 `/dashboard/test-layers` + 后端聚合接口 `GET /api/v1/tests/layers`

### 修复
- tenant 路由鉴权兼容前端 cookie（`_require_auth` 本地放行），修复浏览器 / local-dev 报 401
- pipeline 路由分发修复（`api_v1_dispatch` 抢占 `/api/v1/*` 致子路由 404）
- CheckpointEngine `list_runs` 行工厂缺失导致 `dict(r)` 报错
- 单线程服务器致 SSE 阻塞全站 → 改用 `ThreadingHTTPServer`

### 基础设施
- 后端 `ThreadingHTTPServer` 支持并发 SSE
- HIL 文档层级修正（`docs/guides/hil-strategy.md` 第 3.3 节「CI Layer 3」→ 独立「CI Layer 2.5」）

## [4.0.0] — 历史版本

首个标注版本。详见提交历史 `git log v4.0.0`。
