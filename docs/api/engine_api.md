# 编排引擎 (`engine`) API 参考

> 代码根:`src/yuleosh/engine/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`engine` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/engine.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |
| `from yuleosh.engine.checkpoint import CheckpointEngine` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_resolve_spec_path` | `(project_dir: str, spec_path: str | None)` | 解析 spec 路径：显式传入优先，否则取项目下默认 docs/spec.md。 | `engine/agent_checkpoint.py:28` |
| `_make_session_factory` | `(project_dir: str, spec_path: str | None, mock_mode: bool)` | 构造真实 PipelineSession 的工厂（B1-2）。 | `engine/agent_checkpoint.py:39` |
| `create_agent_pipeline` | `(project_dir: str, spec_path: str | None, mock_mode: bool)` | 创建 Agent 流水线的 Checkpoint 版本。 | `engine/agent_checkpoint.py:73` |
| `list_injection_points` | `(engine: CheckpointEngine | None, project_dir: str)` | 打印所有注入点（即所有步骤）。 | `engine/agent_checkpoint.py:96` |
| `main` | `()` | — | `engine/agent_checkpoint.py:112` |
| `_wrap` | `(handler, project_dir: str, layer: float)` | 将 (project_dir, ci) 签名的 handler 包装成无参 Callable，每个调用创建独立 CIResult。 | `engine/ci_checkpoint.py:54` |
| `_bool_wrap` | `(handler, project_dir: str, layer: float)` | 包装返回 bool 的 handler，True 表示通过，异常表示失败。每个调用创建独立 CIResult。 | `engine/ci_checkpoint.py:64` |
| `create_ci_pipeline` | `(layer: float, project_dir: str)` | 创建 CI 某一层的 CheckpointPipeline。 | `engine/ci_checkpoint.py:77` |
| `_dummy_memory_check` | `(project_dir: str, ci)` | 内存安全检查存根 — 与原 layers.py 逻辑一致。 | `engine/ci_checkpoint.py:196` |
| `_detect_hil_target_dummy` | `(project_dir: str, ci)` | HIL 目标检测 — 简化版以支持 checkpoint。 | `engine/ci_checkpoint.py:212` |
| `_hil_tests_wrapper` | `(project_dir: str, ci)` | HIL 测试闭包 — 兼容 checkpoint 签名。 | `engine/ci_checkpoint.py:217` |
| `_save_hil_report_stub` | `(project_dir: str, ci)` | HIL 报告保存存根。 | `engine/ci_checkpoint.py:222` |
| `_run_e2e_tests` | `(project_dir: str, ci)` | E2E 测试运行。 | `engine/ci_checkpoint.py:232` |
| `_run_version_check` | `(project_dir: str, ci)` | 版本检查。 | `engine/ci_checkpoint.py:267` |
| `_run_evidence_pack` | `(project_dir: str, ci)` | 证据包生成。 | `engine/ci_checkpoint.py:286` |
| `main` | `()` | — | `engine/ci_checkpoint.py:304` |
| `register` | `()` | 向 executor 工厂注册 container 后端（EI-M2A 接线）。 | `engine/container_executor.py:260` |
| `make_executor` | `(name: str, **kwargs)` | 执行器工厂（EI-M1A.1）。 | `engine/executor.py:95` |
| `_osh_home` | `(project_dir: str | Path)` | 项目根目录（OSH_HOME env 优先，回退 project_dir）。 | `engine/project_venv.py:37` |
| `resolve_venv_dir` | `(project_dir: str | Path)` | 计算项目 venv 目录（不创建）。 | `engine/project_venv.py:42` |
| `_requirements_paths` | `(project_dir: Path)` | 候选依赖清单：requirements.txt 优先，其次 pyproject.toml。 | `engine/project_venv.py:52` |
| `_deps_signature` | `(project_dir: Path)` | 依赖清单内容 hash（EI-M1B.4: 变化触发重装）。 | `engine/project_venv.py:62` |
| `_sig_file` | `(venv_dir: Path)` | — | `engine/project_venv.py:71` |
| `ensure_venv` | `(project_dir: str | Path, python: str | None)` | 确保项目 venv 存在（幂等），返回 venv 目录。 | `engine/project_venv.py:75` |
| `install_dependencies` | `(project_dir: str | Path, venv_dir: str | Path, timeout_s: int)` | 按依赖清单安装到项目 venv（EI-M1B.2/.4）。 | `engine/project_venv.py:98` |
| `ensure_project_venv` | `(project_dir: str | Path, install: bool)` | 一键 ensure + install（EI-M1B 主入口）。 | `engine/project_venv.py:138` |
| `quota_manifest` | `(prefix: str, tenant: str, requests_mem: str, limits_mem: str, max_jobs: int)` | per-tenant ResourceQuota manifest（EI-M2C.3）。 | `engine/runner_spec.py:124` |
| `_resolve_session_dir` | `(project_dir: str, session_name: str | None, run_id: str | None)` | 解析 session 目录（与 PipelineSession._ensure_session_dir 同路径规则）。 | `engine/subprocess_executor.py:51` |
| `_find_step` | `(step_id: str)` | 按 step_id 在 PIPELINE_STEPS 中查找，返回 (step_key, name, handler)。 | `engine/subprocess_executor.py:77` |
| `_make_worker_session` | `(project_dir: str, step_def: dict, mock_mode: bool, session_name: str | None, run_id: str | None)` | 在 worker 进程中构造 PipelineSession（与 agent_checkpoint._make_session_factory 同语义）。 | `engine/subprocess_executor.py:88` |
| `worker_main` | `(argv: list[str] | None)` | 子进程入口：执行单个步骤，把 StepResult JSON 打到 stdout。 | `engine/subprocess_executor.py:134` |
| `_python_executable` | `()` | 返回当前解释器路径（保证 worker 与主进程同环境）。 | `engine/subprocess_executor.py:208` |
| `_run_step_in_subprocess` | `(step_def: dict, project_dir: str, mock_mode: bool, spec_path: str | None, timeout_s: int, session_name: str | None, run_id: str | None, artifacts: dict | None, python_executable: str | None)` | 提交单步到子进程并解析结果。 | `engine/subprocess_executor.py:213` |
| `make_subprocess_runner` | `(project_dir: str, mock_mode: bool, spec_path: str | None, timeout_s: int, session_name: str | None, run_id: str | None)` | 构造 CheckpointEngine 可用的 runner 钩子（B2-1 additive）。 | `engine/subprocess_executor.py:298` |
| `main` | `()` | — | `engine/subprocess_executor.py:335` |
| `tenant_config_dir` | `(tenant_dir: str | Path)` | 租户 config 目录。 | `engine/tenant_security.py:47` |
| `tenant_audit_dir` | `(tenant_dir: str | Path)` | 租户 audit 目录。 | `engine/tenant_security.py:52` |
| `_read_legacy_credentials` | `(tenant_dir: str | Path)` | 读取遗留明文 credentials.json（向后兼容，仅作兜底）。 | `engine/tenant_security.py:57` |
| `_write_legacy_credentials` | `(tenant_dir: str | Path, creds: dict[str, str])` | 写遗留明文 credentials.json（仅 OLLAMA_HOST 等非机密项或保险库降级）。 | `engine/tenant_security.py:72` |
| `load_credentials` | `(tenant_dir: str | Path)` | 读取租户凭据用于容器 env 注入（EI-M2B.2）。 | `engine/tenant_security.py:90` |
| `write_credentials` | `(tenant_dir: str | Path, creds: dict[str, str])` | 写租户凭据（SEC-PK：API key 经加密保险库落盘，绝不写明文文件）。 | `engine/tenant_security.py:118` |
| `audit_container_start` | `(tenant_dir: str | Path, tenant_id: str, project_name: str, step_id: str, image: str, limits: dict, network: bool)` | 记录容器启动审计（EI-M2B.3）。 | `engine/tenant_security.py:153` |
| `list_container_audit` | `(tenant_dir: str | Path, limit: int)` | 读取容器启动审计（倒序，最新在前）。 | `engine/tenant_security.py:179` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `StepStatus` | `(str, Enum)` | 单个步骤的状态。 | `engine/checkpoint.py:44` |
| `StepRecord` | `()` | 单个步骤的执行记录。 | `engine/checkpoint.py:54` |
| `CheckpointState` | `()` | 流水线的完整 checkpoint 状态。 | `engine/checkpoint.py:68` |
| `CheckpointEngine` | `()` | 流水线引擎，支持全量/注入/恢复三种模式。 | `engine/checkpoint.py:134` |
| `ContainerExecutor` | `(Executor)` | 容器执行器（EI-M2A）：docker run 封装，每步骤独立容器。 | `engine/container_executor.py:43` |
| `Executor` | `()` | 步骤执行器接口。 | `engine/executor.py:30` |
| `LocalExecutor` | `(Executor)` | 本地子进程执行器（EI-M1A.2）。 | `engine/executor.py:49` |
| `StepResult` | `()` | 适配层统一的步骤执行结果。 | `engine/handler_adapter.py:26` |
| `HandlerAdapter` | `()` | 把 session 风格 / no-arg 风格 handler 统一适配为 StepResult。 | `engine/handler_adapter.py:42` |
| `RunnerSpec` | `()` | 单次 pipeline 步骤的 k8s Job 配置。 | `engine/runner_spec.py:18` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CheckpointState.to_dict` | `(self)` | — | `engine/checkpoint.py:78` |
| `CheckpointState.from_dict` | `(cls, data: dict)` | — | `engine/checkpoint.py:103` |
| `CheckpointEngine.__init__` | `(self, pipeline_name: str, project_dir: str, session_factory: Callable | None, runner: Callable | None, state_backend: str)` | Args: | `engine/checkpoint.py:149` |
| `CheckpointEngine.add_step` | `(self, step_id: str, name: str, handler: Callable | None, agent: str)` | 注册一个流水线步骤。 | `engine/checkpoint.py:185` |
| `CheckpointEngine.get_step_ids` | `(self)` | 返回所有已注册的步骤 ID（按注册顺序）。 | `engine/checkpoint.py:195` |
| `CheckpointEngine.find_step_index` | `(self, step_id: str)` | 按 step_id 查找 index。找不到时抛出 ValueError。 | `engine/checkpoint.py:199` |
| `CheckpointEngine.request_stop` | `(self)` | 请求停止当前运行（写停止标志文件，幂等）。 | `engine/checkpoint.py:217` |
| `CheckpointEngine.clear_stop` | `(self)` | 清除停止标志（新运行开始时调用，防残留）。 | `engine/checkpoint.py:224` |
| `CheckpointEngine.stop_requested` | `(self)` | 停止标志是否存在（步骤边界检查）。 | `engine/checkpoint.py:234` |
| `CheckpointEngine.run` | `(self, inject_at: str | None, resume: bool, selected: list[str] | None)` | 运行流水线。 | `engine/checkpoint.py:242` |
| `CheckpointEngine.status` | `(self)` | 读取持久化的 checkpoint 状态（只读）。 | `engine/checkpoint.py:298` |
| `CheckpointEngine.clear_state` | `(project_dir: str, backend: str)` | 清除 checkpoint 状态（json 或 sqlite，B2-3）。 | `engine/checkpoint.py:306` |
| `CheckpointEngine.record_run` | `(self, run_id: str, op: str, mode: str | None, selected_steps: list[str] | None, status: str, started_at: str)` | Insert a pipeline run record with running status. | `engine/checkpoint.py:778` |
| `CheckpointEngine.finish_run` | `(self, run_id: str, status: str, finished_at: str, snapshot: dict | None)` | Update a run record with final status + full checkpoint snapshot. | `engine/checkpoint.py:803` |
| `CheckpointEngine.publish_state` | `(self, run_id: str, op: str, mode: str | None, status: str, started_at: str, finished_at: str, state: 'CheckpointState')` | 把外部流水线（如编排器一键跑）的最终状态发布为 checkpoint 运行记录。 | `engine/checkpoint.py:822` |
| `CheckpointEngine.list_runs` | `(self, limit: int)` | Return recent runs (newest first), without the heavy snapshot field. | `engine/checkpoint.py:844` |
| `CheckpointEngine.get_run` | `(self, run_id: str)` | Return a single run record including its checkpoint snapshot. | `engine/checkpoint.py:864` |
| `ContainerExecutor.__init__` | `(self, project_dir: str, tenant_dir: str | None, image: str, memory_limit: str | None, cpus: float | None, network_enabled: bool, proxy_env: dict[str, str] | None, extra_env: dict[str, str] | None, mock_mode: bool, timeout_s: int, run_id: str | None, tenant_id: str | None)` | — | `engine/container_executor.py:55` |
| `ContainerExecutor.limits_for_plan` | `(plan: str)` | 从 tenant plan 映射 (memory_limit, cpus)。 | `engine/container_executor.py:83` |
| `ContainerExecutor.docker_available` | `()` | docker CLI 是否存在（不在容器内运行也视为可用，交由 run 报错）。 | `engine/container_executor.py:99` |
| `ContainerExecutor.execute` | `(self, step_def: dict, artifacts: dict | None)` | — | `engine/container_executor.py:132` |
| `Executor.execute` | `(self, step_def: dict, artifacts: dict | None)` | — | `engine/executor.py:41` |
| `Executor.as_runner` | `(self)` | — | `engine/executor.py:45` |
| `LocalExecutor.__init__` | `(self, project_dir: str, mock_mode: bool, spec_path: str | None, timeout_s: int, session_name: str | None, run_id: str | None, venv_dir: str | None)` | — | `engine/executor.py:57` |
| `LocalExecutor.execute` | `(self, step_def: dict, artifacts: dict | None)` | — | `engine/executor.py:86` |
| `HandlerAdapter.__init__` | `(self, handler: Callable, fallback_safe: bool)` | — | `engine/handler_adapter.py:55` |
| `RunnerSpec.job_name` | `(self)` | Job 名称（EI-M2C.1 命名规则）。 | `engine/runner_spec.py:35` |
| `RunnerSpec.resolve_pvc` | `(self)` | 租户 PVC 名（EI-M2C.2）：显式优先，否则 <prefix>-<tenant>-data。 | `engine/runner_spec.py:39` |
| `RunnerSpec.pod_labels` | `(self)` | Pod 标签（NetworkPolicy 选择器用，EI-M2C.3）。 | `engine/runner_spec.py:43` |
| `RunnerSpec.worker_args` | `(self)` | worker 命令参数。 | `engine/runner_spec.py:52` |
| `RunnerSpec.resources` | `(self)` | 容器资源声明（限额映射）。 | `engine/runner_spec.py:63` |
| `RunnerSpec.as_manifest` | `(self)` | 生成 Job manifest dict（供 kubectl/客户端提交）。 | `engine/runner_spec.py:76` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OLLAMA_HOST` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |
| `OSH_SESSIONS_DIR` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.engine`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/ui/routes/pipeline_routes.py:727
from yuleosh.engine.checkpoint import CheckpointEngine

# src/yuleosh/plan/cli.py:186
from yuleosh.engine.checkpoint import CheckpointEngine

# src/yuleosh/api/pipeline.py:236
from yuleosh.engine.checkpoint import (

```

> 共 3 个文件引用本子系统；完整调用图见 `docs/modules/engine.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 11 处生产引用(Grep `yuleosh.engine` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/engine/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
