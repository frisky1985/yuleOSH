# Changelog

本文件记录 yuleOSH 的版本变更。版本号遵循语义化版本（SemVer）。

## [Unreleased]

### 修复

- **证据包不再漏进源码仓库（`OSH_HOME` 双真值收口）**
  （`api/__init__.py`、`api/evidence.py`、`api/dashboard.py`、`tests/conftest.py`）
  - **根因**：`OSH_HOME` 在各 API 模块里是 **import 期快照**（`api/__init__.py:23`、`dashboard.py:39`），而 `os.environ["OSH_HOME"]` 可以在运行时被改 —— 同一进程里存在**两份真值**。dashboard 的证据生成把 bundle 位置交给 `dashboard.OSH_HOME`、把写入目标交给 `evidence.snapshot_bundle` 内部的 `from . import OSH_HOME`（即 `api.OSH_HOME`）；两个快照一旦分叉，测试的隔离就失效，生成的证据包落进**仓库**。实测两处落点：`.osh/evidence/` 累积 46 个空壳包（33×174B + 13×~890B）外加 `compliance-pack.zip`；`src/.osh/evidence/` 同类空壳（`parent.parent.parent` 从 `api/` 往上三层，`api.PROJECT_ROOT` 实为 `src`），自 09-02 起漏了两周。空壳的形态特征即「只含 37 字节的 `audit-manifest.json`」，且删掉后每次跑测试还会再长。
  - **修复**：新增 `api.resolve_osh_home(current)` 做**调用时**解析，优先级「本模块常量被显式覆盖 > 运行时 env > import 期快照」，把测试中长期并存的两套隔离手法（`monkeypatch.setenv` 232 处 / `monkeypatch.setattr` 82 处）都认下来。不能简单地「env 优先」：`tests/test_api.py` 在**收集期**就用 `os.environ.setdefault` 把 env 钉在仓库根，env 优先会反过来废掉 `setattr` 那一类隔离（实测 28 项失败）。
  - `evidence.py` 的 6 处落盘 / 读取位置改走 `_ev_home()`；`snapshot_bundle(bundle_dir, osh_home=None)` 新增 `osh_home` 参数，**dashboard 显式传入自己的解析结果** —— 这是消除跨模块分叉的关键一步。`dashboard.py` 的证据路径（`_load_gap_items` / `_find_latest_manifest` / evidence generate 守卫 / worker 落盘）同源化；纯只读且自洽的 coverage / misra / projects 路径**未动**，控制爆炸半径。
  - **自愈网**：`conftest.py` 在 `pytest_configure` 记录仓库两处 evidence 目录的包集合，`pytest_sessionfinish` 清掉**本会话新增**的包并逐条打印路径（`OSH_ALLOW_EVIDENCE_WRITES=1` 可关闭，零开销）。与既有的 MagicMock 落盘拦截同一模式。
  - **验证（严格同序对照）**：68 个测试文件 / 1669 项 —— 改动前 `14 failed / 1651 passed`，改动后完全一致，**0 回归**（14 项为既存失败）。泄漏维度：同一批跑完，基线新增 3 个包（174B / 891B / 174B，与历史空壳同形），修复后 **0 个**。新增 `tests/test_osh_home_resolution.py`（13 项：判定规则 + 两处落点 + dashboard 跨模块同源）；撤掉修复后 12/13 变红，非空转。
  - 顺带清理：`src/.osh/evidence/` 的 14 个空壳包已移除（移入回收站）。
  - 顺带发现（**未修**，不属本缺陷）：`tests/test_v361_critical_fixes.py::TestErrorMasking::test_pipeline_run_masks_details` 是既存失败 —— 用例把 `spec.md` 直接放在 `OSH_HOME` 根，而 `_run_pipeline` 由 `resolved.parent.parent` 反推 `project_dir` 时会越出 `OSH_HOME`，守卫按设计返回 403，断言却期望 500（错误脱敏）。修法是把 spec 放到 `<proj>/docs/spec.md`。

- **run 结论不再绕过门禁证据（根治「表面全绿」）**
  （`pipeline/gates.py`、`pipeline/orchestrator.py`、`pipeline/session.py`）
  - **证据时效性判定（新增 `stale` 状态）**：每个步骤产物自带 `session` 字段，记录产出它的 run。该字段与本轮 `session.name` 不符 → 门禁判 `stale`（复用了旧轮次的验证证据），而不是静默按 `passed` / `skipped` 计。`REUSABLE_STEPS`（`spec-check` / `codegen-deploy`）跨 run 复用是设计允许的，豁免此判定。
  - **无证据不再等于通过**：`_worst_status([])` 由 `passed` 改为 `not-run` —— 本轮没有该门禁的任何步骤记录时，如实报告「未执行」，不再 fail-open。
  - **run 级结论由门禁证据决定**：新增 `classify_run_outcome()`，GREEN 需同时满足「session completed + 有可读的门禁汇总 + 全部非咨询门禁 passed + 无步骤错误」。此前只校验前两项，导致 `G7` 整门 skipped 的 run 仍打印 `GREEN — all gates passed`。三色分级相应改为 GREEN / **UNVERIFIED** / RED，并列出未被验证的门禁。
  - **显式声明「不适用」**：部分门禁在特定配置下确实不适用（planning 模式没有代码生成类验证），但「步骤跳过了」不足以证明这一点 —— 同一个信号也覆盖「没人跑它」。因此由调用方显式声明（`session.config["na_gates"]` 或环境变量 `OSH_NA_GATES=G3,G8`），声明只豁免 `skipped` / `not-run`，**不豁免 `stale` / `failed`**。
  - 门禁汇总新增 `not_run_gates` / `stale_gates` 字段；`session.json` 新增 `gate_verdict`（`outcome` / `reason` / `worst_gate_status` / `blocking_gates` / `declared_na`），API 与 dashboard 可直接读取，无需解析控制台输出。
  - 动因：run `57fa80e754ed` 24/24 步 `completed`、`G7` 全 skipped、其中三个产物还是两天前 run 的，却打印 `GREEN — all gates passed`。

### 变更

- **sessions 根独立可配 + 分层保留（`OSH_SESSIONS_DIR`）**
  （`pipeline/session.py`、`engine/subprocess_executor.py`、`api/{artifacts,logs,tests}.py`、`pipeline/session_prune.py`、`tests/conftest.py`）
  - **新增 `OSH_SESSIONS_DIR`**：把 sessions 根从 `<OSH_HOME>/.osh/sessions` 解耦出来。优先级 `OSH_SESSIONS_DIR` > `OSH_HOME` > cwd；写入侧（`PipelineSession` / `subprocess_executor._resolve_session_dir`）与读取侧（三个 API 模块）共用 `resolve_sessions_root()`，不再各写一份而漂移。用途一：把 run 证据放到独立卷；用途二：测试隔离（见下）。**未设置时行为与原先完全一致**。
  - **修复测试泄漏**：`test_api.py` 在模块导入期把 `OSH_HOME` 钉到仓库根（进程级），于是每个构造过 `PipelineSession` 的测试都往仓库自己的 `.osh/sessions` 漏一个目录 —— 实测累积 **3611 个**，占历史上出现过的全部 session 的 **99.6%**。`conftest.py` 现在把 `OSH_SESSIONS_DIR` 指向一个临时根并在 `pytest_sessionfinish` 回收，**不动 `OSH_HOME`**，因此 `test_api.py` 依赖的相对路径解析不受影响（早期直接抢占 `OSH_HOME` 的做法曾坏掉 11 个测试）。临时根保持 `<project>/.osh/sessions` 层级，因为 `to_dict` 靠向上三层反推 `project_dir`。
  - **新增 `pipeline/session_prune.py`**：按「可再生性」而非体积做分层保留 —— T0 运行态（空目录 / `created` 中止）整体回收；T1 汇总层（`session.json` / `gate-summary.json`）与 T2 LLM 产物（本地 4B 跑一轮 1.5–2 小时，不可再生）永久保留；T3 确定性证据（`VOLATILE_STEPS` 产物，分钟级可重跑）只保留在最近 `keep_last` 个 run 里。默认 `dry_run=True`，可用 `python -m yuleosh.pipeline.session_prune <project> --keep-last N [--apply]`。
  - 动因：单次 24 步真实 run 只写 51 个文件 / 89 KB（字节维度十年内都不构成风险），真正的代价是**目录数** —— `api/artifacts.py` 每次请求都要 `os.walk(OSH_HOME)` + 全量 `iterdir` + 逐个读 `session.json`，随历史线性退化。
  - 顺带记录一个**未修**的相邻缺陷：`gates._ARTIFACT_CANDIDATES` 漏了 `qualification-test.json`（G10 步骤的实际产物名）与 `c-coverage-gate.json`，因此这些门禁读不到产物里的真实 verdict、只能退回 `session.steps` 的状态。本模块用一份显式补集兜住了清理场景，但门禁本身仍待修。

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
