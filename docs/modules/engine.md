# 模块设计速写：engine（Checkpoint Pipeline 编排引擎）

> 包：`src/yuleosh/engine/` ｜ 规模：11 .py ≈ 2777 行
> 定位：`pipeline` 包 step handlers 的「检查点 / 编排外壳层」

## 职责
通用 Checkpoint Pipeline Engine：支持任意点注入(inject) + 自动续跑(resume) + 停止(stop) + 选中重跑(selected)，配套本地/容器执行器、产物交接、sqlite 状态后端（供看板读 24 步进度）。证据：`engine/__init__.py:4-8`、`engine/checkpoint.py:5-19`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `engine/checkpoint.py` (875) | 核心引擎 | `CheckpointEngine` `:134`；`run` `:242`；`status` `:298`；`request_stop` `:217`；`publish_state` `:822`；`StepStatus`/`StepRecord`/`CheckpointState` `:44/:53/:67` |
| `engine/handler_adapter.py` (130) | handler 适配 | `HandlerAdapter` `:42`；`StepResult` `:25` |
| `engine/executor.py` (113) | 执行器接口 | `make_executor` `:95`；`LocalExecutor` `:49`；`ContainerExecutor` `:43` |
| `engine/subprocess_executor.py` (363) | 子进程隔离 | `make_subprocess_runner` `:298`；`worker_main` `:134` |
| `engine/container_executor.py` (264) | 容器执行器 | `ContainerExecutor` `:43`；`register` `:260` |
| `engine/agent_checkpoint.py` (195) | 24 步封装 | `create_agent_pipeline` `:73` |
| `engine/ci_checkpoint.py` (328) | CI 层封装 | `create_ci_pipeline` `:77` |
| `engine/project_venv.py` (148) | venv 隔离 | `ensure_project_venv` `:138` |
| `engine/tenant_security.py` (195) | 容器凭据注入 | `load_credentials` `:90`；`audit_container_start` `:153` |
| `engine/runner_spec.py` (144) | K8s spec | `RunnerSpec` `:18`；`quota_manifest` `:124` |

## 公共 API / 入口点
- `CheckpointEngine(...)`：`run`/`status`/`request_stop`/`clear_state`/`add_step`/`publish_state`/`list_runs`/`get_run`（`checkpoint.py`）
- `create_agent_pipeline`（`agent_checkpoint.py:73`）、`create_ci_pipeline`（`ci_checkpoint.py:77`）
- `make_executor`（`executor.py:95`）、`make_subprocess_runner`（`subprocess_executor.py:298`）、`HandlerAdapter`（`handler_adapter.py:42`）

## 生产接线（真实调用方）
- `api/pipeline.py:236` 导入；`:288` `engine.publish_state(...)`；`:686-707` rerun/resume 构造 `CheckpointEngine(sqlite)` + `add_step(HandlerAdapter(handler))`；`:903-908` `request_stop()` 实现看板停止
- `ui/routes/pipeline_routes.py` 多处构造/读 `CheckpointEngine`（`:727,:756,:817,:940,:988,:1052,:1110`）
- `plan/cli.py:186` `CheckpointEngine`
- 独立 CLI：`cli/yuleosh.sh:36-51` `python3 -m yuleosh.engine.agent_checkpoint`；`:84` `engine.ci_checkpoint`

## 运行时触发方式
- Web/API 主路径：`api/pipeline.py` 的 rerun/retry/resume/selected + 看板停止走 `CheckpointEngine`；一键跑先经 `pipeline.orchestrator` 再 `publish_state` 回写看板（`:222-288`）。
- 看板实时读引擎状态。

## 环境变量 / 配置
- `OSH_SESSIONS_DIR`（`subprocess_executor.py:66`，覆盖 `OSH_HOME`）、`OSH_HOME`（`:70`、venv 根 `project_venv.py:39`）
- 容器后端注入：`OSH_HOME=/work`、`YULEOSH_MOCK`（`container_executor.py:115-116`）、`OLLAMA_HOST`（`tenant_security.py:109`）；凭据白名单经 `secret_vault`/`credentials.json`（`tenant_security.py:30-36,90-115`）
- 引擎依赖 `project_dir/.yuleosh/checkpoint-state.json`（`checkpoint.py:146`）与可选 `checkpoint-state.db`（sqlite，`:179`）

## 与 pipeline 关系（重叠 vs 区分）
- **依赖方向**：engine 依赖 `pipeline`（实现层）——`agent_checkpoint.py:19-22` import `pipeline.session.PipelineSession` + `pipeline.step_handlers.PIPELINE_STEPS`（24 步注册表，`pipeline/step_handlers/__init__.py:17-22`）。
- **区分**：`pipeline` 提供业务步骤 + `pipeline.run.run_pipeline`（CLI `pipeline run` 走此）。engine 叠加检查点/续跑/注入/停止 + 进程/容器隔离 + sqlite 看板。两条并行链路：① CLI `pipeline run`→orchestrator→`publish_state`；② 看板 rerun/resume→`CheckpointEngine`。

## 偏差 / 死代码 / ORPHAN（设计文档必记）
- **D1：ContainerExecutor + tenant_security + runner_spec 生产 ORPHAN**——`agent_checkpoint.py:126-128` 的 `--executor` 仅接受 `["inline","subprocess","local"]`，**不含 `"container"`**；仅 `make_executor("container")`（`executor.py:108`）能触发，无任何生产调用者。
- **D2：`runner_spec.py` ORPHAN**——grep `RunnerSpec|quota_manifest` 全仓仅自身定义（`:18`、`:124`）。
- **D3：`container_executor.register()` 空操作死代码**（`:260-264`）。
- **D4：ci_checkpoint L2.5/3 桩实现**——`_dummy_memory_check` `:196`、`_detect_hil_target_dummy` `:212`、`_hil_tests_wrapper` `:217`（`return _record_hil_results(ci,[])`）、`_run_evidence_pack` `:286-297` 用 `from evidence import pack` 明文导入且整体 try/except 吞错（与 L1/L2 不对称）。
- `CheckpointEngine._execute_steps` 内 `handler is None` 直接标 PASSED（`:525-533`），可被无 handler 占位测试误用。

## 规模
11 .py ≈ 2777 行。
