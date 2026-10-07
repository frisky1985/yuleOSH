# 流水线编排 (`pipeline`) API 参考

> 代码根:`src/yuleosh/pipeline/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`pipeline` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/pipeline.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .pipeline import handle_pipeline` |
| `"pipeline": handle_pipeline,` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status` |
| `result = handle_pipeline_status(handler, path)` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs` |
| `handler._json_response(handle_pipeline_runs(handler))` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats` |
| `handler._json_response(handle_pipeline_stats(handler))` |
| `from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status` |
| `from yuleosh.pipeline.config_validator import validate_pipeline_config` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint` |
| `handler._json_response(handle_pipeline_checkpoint(handler, path))` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs_history` |
| `handler._json_response(handle_pipeline_runs_history(handler, path))` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger` |
| `result = handle_pipeline_trigger(handler, body)` |
| `from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify` |
| `handle_pipeline_status,` |
| `def handle_pipeline_trigger(handler: BaseHTTPRequestHandler, body: bytes) -> dict:` |
| `from yuleosh.pipeline.async_runner import submit_pipeline, submit_full_pipeline` |
| `def handle_pipeline_status(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `from yuleosh.pipeline.async_runner import get_job_status` |
| `def handle_pipeline_runs(handler: BaseHTTPRequestHandler) -> dict:` |
| `from yuleosh.pipeline.async_runner import list_jobs` |
| `def handle_pipeline_stats(handler: BaseHTTPRequestHandler) -> dict:` |
| `from yuleosh.pipeline.async_runner import get_pipeline_stats` |
| `def handle_pipeline_usage(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `pipeline_info = ci_data.get("pipeline", {})` |
| `from yuleosh.pipeline.async_runner import list_jobs` |
| `def handle_pipeline_list(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `def handle_pipeline_checkpoint(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `pipeline_name = (qs.get("pipeline") or [None])[0]` |
| `def handle_pipeline_runs_history(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `pipeline_name = (qs.get("pipeline") or [None])[0] or "agent-pipeline"` |
| `def handle_pipeline_evidence(handler: BaseHTTPRequestHandler, path: str) -> dict:` |
| `pipeline_name = (qs.get("pipeline") or [None])[0] or "agent-pipeline"` |
| `def handle_pipeline_evidence_download(handler: BaseHTTPRequestHandler, path: str) -> None:` |
| `pipeline_name = (qs.get("pipeline") or [None])[0] or "agent-pipeline"` |
| `"pipeline": pipeline_name,` |
| `def handle_pipeline_checkpoint_stream(handler: BaseHTTPRequestHandler, path: str) -> None:` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_get_pool` | `()` | — | `pipeline/async_runner.py:38` |
| `_record_pipeline_usage` | `(org_id: int, user_id: int | None, user_email: str | None)` | Portal 方案 B (2026-08-10): 记录 pipeline_run 计量到 usage_log。 | `pipeline/async_runner.py:45` |
| `submit_pipeline` | `(project_dir: str, layer: int, org_id: int, user_id: int | None, user_email: str | None)` | Submit a CI-layer pipeline job for async execution. Returns job_id. | `pipeline/async_runner.py:66` |
| `submit_full_pipeline` | `(project_dir: str, config_json: Optional[str], arxml_content: Optional[str], org_id: int, user_id: int | None, user_email: str | None)` | Submit a full yuleOSH pipeline (RTE → CI → MISRA) with optional config. | `pipeline/async_runner.py:93` |
| `_append_log` | `(job_id: str, message: str)` | — | `pipeline/async_runner.py:141` |
| `_update_stage` | `(job_id: str, stage_key: str, status: str, progress: int)` | — | `pipeline/async_runner.py:149` |
| `_run_ci_job` | `(job_id: str, project_dir: str, layer: int, org_id: int, user_id: int | None, user_email: str | None)` | Execute CI layer in background thread. | `pipeline/async_runner.py:162` |
| `_run_full_pipeline` | `(job_id: str, project_dir: str, config_json: Optional[str], arxml_content: Optional[str], org_id: int, user_id: int | None, user_email: str | None)` | Execute full pipeline (ARXML parse → validate → RTE → CI → MISRA). | `pipeline/async_runner.py:210` |
| `get_job_status` | `(job_id: str)` | Get current status of a pipeline job. | `pipeline/async_runner.py:378` |
| `list_jobs` | `(limit: int)` | List recent pipeline jobs, newest first. | `pipeline/async_runner.py:383` |
| `get_pipeline_stats` | `()` | Get aggregate pipeline statistics. | `pipeline/async_runner.py:390` |
| `_notify_pipeline_completion` | `(job_id: str)` | Send notification for a completed pipeline job. | `pipeline/async_runner.py:403` |
| `validate_pipeline_config` | `(project_dir: str, config_json: Optional[str], arxml_content: Optional[str])` | Validate configuration for pipeline readiness. | `pipeline/config_validator.py:65` |
| `_validate_arxml_syntax` | `(arxml_content: str)` | Validate basic ARXML syntax. | `pipeline/config_validator.py:147` |
| `_extract_arxml_modules` | `(arxml_content: str)` | Extract module names from ARXML content. | `pipeline/config_validator.py:176` |
| `cli_validate` | `(args: list[str])` | CLI entry point for 'yuleosh validate-config'. | `pipeline/config_validator.py:197` |
| `_context_window` | `()` | Resolve the context window (env override or default). | `pipeline/context_guard.py:76` |
| `estimate_context_level` | `(system_prompt: str, user_prompt: str, context_window: int | None)` | Estimate the context water level of a prompt pair. | `pipeline/context_guard.py:84` |
| `reference_inject` | `(text: str, session_dir: str | Path)` | Replace oversized artifact blocks with reference pointers + summaries. | `pipeline/context_guard.py:144` |
| `truncate_with_reference_marker` | `(text: str, limit: int, path: str)` | Tail-truncate with an explicit omission marker (替代静默截断). | `pipeline/context_guard.py:184` |
| `deploy_report_path` | `(project_dir: str | Path)` | codegen-deploy 报告的绝对路径。 | `pipeline/deploy_state.py:55` |
| `load_deploy_report` | `(project_dir: str | Path)` | 读取 codegen-deploy 报告; 不存在/损坏返回 None。 | `pipeline/deploy_state.py:60` |
| `deploy_status` | `(project_dir: str | Path)` | 本次 run 的部署状态字符串 (报告 status; 无报告返回 'no-report')。 | `pipeline/deploy_state.py:74` |
| `has_deployed_code` | `(project_dir: str | Path)` | 本次 run 是否有代码部署。 | `pipeline/deploy_state.py:82` |
| `deployed_files` | `(project_dir: str | Path)` | 本次 run 部署的文件相对路径列表 (diff 聚焦输入)。 | `pipeline/deploy_state.py:103` |
| `_write_skip_report` | `(session, step_key: str, reviewer: str, reason: str, deploy_status_str: str)` | 写 status=skipped 的审查报告 (与 handler_base._write_skip_report 同语义)。 | `pipeline/deploy_state.py:115` |
| `maybe_skip_code_review` | `(session, step_key: str, reviewer: str)` | 审查锚定: 本次 run 无代码部署时 honest-skip 代码审查步骤。 | `pipeline/deploy_state.py:147` |
| `gate_for_step` | `(step_key: str)` | Return the gate dict owning ``step_key`` (None if not in any gate). | `pipeline/gates.py:142` |
| `aggregate_gate_status` | `(step_statuses: dict[str, str])` | Aggregate per-step statuses into per-gate status (worst-wins). | `pipeline/gates.py:150` |
| `_worst_status` | `(statuses: list[str])` | Worst-wins merge of statuses (see ``GATE_STATUS_ORDER``). | `pipeline/gates.py:175` |
| `_is_freshness_exempt` | `(step_key: str)` | Whether ``step_key`` may legitimately carry an older session's artifact. | `pipeline/gates.py:208` |
| `_sha256_file` | `(path: Path)` | Return SHA-256 hex digest of a file, or '' if unreadable. | `pipeline/gates.py:223` |
| `artifact_index` | `(sdir: Path, exclude: frozenset[str])` | SHA-256 of **every** artifact file under ``sdir`` (P0-B, 2026-09-23). | `pipeline/gates.py:242` |
| `_statuses_from_session_steps` | `(steps)` | Build ``{step_key: status}`` from ``session.steps`` entries. | `pipeline/gates.py:281` |
| `_artifact_paths` | `(sdir: Path | None, step_key: str)` | Return candidate artifact paths for ``step_key`` (existing ones only). | `pipeline/gates.py:342` |
| `_artifact_verdict` | `(sdir: Path | None, step_key: str, expected_session: str)` | Derive a gate verdict from a step's own artifact JSON. | `pipeline/gates.py:351` |
| `_verdict_from_json` | `(path: Path, expected_session: str)` | Read a JSON artifact and return ``stale``/``skipped``/``failed``/``""``. | `pipeline/gates.py:390` |
| `_verdict_from_text` | `(path: Path)` | Return ``skipped`` when a non-JSON artifact opens with a skip banner. | `pipeline/gates.py:415` |
| `_scan_artifact_step_map` | `(sdir: Path)` | Index artifacts by the ``step`` field they record about themselves. | `pipeline/gates.py:424` |
| `_self_reported_success` | `(status: str)` | Whether ``status`` is the orchestrator claiming a step succeeded. | `pipeline/gates.py:460` |
| `_apply_artifact_overlay` | `(step_statuses: dict[str, str], sdir: Path, expected_session: str)` | Let each step's own artifact correct — or refute — its recorded status. | `pipeline/gates.py:465` |
| `write_gate_summary` | `(session, step_statuses: dict[str, str] | None, output_path: str | None)` | Aggregate the session's step statuses into gate-summary.json. | `pipeline/gates.py:517` |
| `load_gate_summary` | `(path: str | Path)` | Read back a ``gate-summary.json`` written by :func:`write_gate_summary`. | `pipeline/gates.py:632` |
| `declared_na_gates` | `(config: dict | None)` | Return gate keys the caller explicitly declared *not applicable*. | `pipeline/gates.py:645` |
| `classify_run_outcome` | `(session_status: str, errors, gate_summary: dict | None, na_gates, config: dict | None)` | Decide the run-level verdict — the single place GREEN is granted. | `pipeline/gates.py:687` |
| `validate_gates_contract` | `(step_keys: list[str])` | R3 契约守护: GATES ↔ PIPELINE_STEPS 全覆盖/无重复/无悬挂/顺序一致。 | `pipeline/gates.py:761` |
| `guardrail_root` | `(project_dir: str | Path)` | — | `pipeline/guardrail.py:54` |
| `backup_dir` | `(project_dir: str | Path, run_id: str)` | 单次 run 的备份目录: .yuleosh/guardrail/backup-<run_id>/ | `pipeline/guardrail.py:58` |
| `save_change_set` | `(project_dir: str | Path, run_id: str, changeset: ChangeSet, deployed_after: Optional[Mapping[str, Optional[bytes]]])` | 把变更集持久化到 .yuleosh/guardrail/backup-<run_id>/。 | `pipeline/guardrail.py:77` |
| `load_change_set` | `(project_dir: str | Path, run_id: str)` | 从磁盘加载变更集; 不存在/损坏返回 None。 | `pipeline/guardrail.py:133` |
| `load_deployed_after` | `(project_dir: str | Path, run_id: str)` | 加载部署后内容 (undo 用); 无则空 dict。 | `pipeline/guardrail.py:160` |
| `find_latest_change_set` | `(project_dir: str | Path)` | 找最近一次持久化的变更集 (门禁联动用, 不含 run_id 显式传入)。 | `pipeline/guardrail.py:177` |
| `apply_change_set` | `(project_dir: str | Path, changeset: ChangeSet)` | 把变更集应用到项目: 恢复原始内容 (回滚)。staged 写入。 | `pipeline/guardrail.py:201` |
| `apply_deployed_after` | `(project_dir: str | Path, changeset: ChangeSet)` | 把部署后内容重新应用到项目 (undo 回滚 — 非部署问题恢复部署)。 | `pipeline/guardrail.py:217` |
| `_parse_test_counts_impl` | `(output: str, runner: str)` | 解析 pytest/go 测试输出 (与 test_integration._parse_test_counts 同逻辑)。 | `pipeline/guardrail.py:474` |
| `maybe_rollback_on_gate_failure` | `(session, step_key: str, gate_result: TestResult, runner: TestRunner | None)` | 门禁失败时联动回滚 (隔离验证模式)。 | `pipeline/guardrail.py:520` |
| `_mark_deploy_regression` | `(project_dir: Path, report: dict)` | 更新 codegen-deploy 报告: 部署已回滚, deployed 清空, 视为无部署。 | `pipeline/guardrail.py:671` |
| `src_has_uncommitted_changes` | `(project_dir: str | Path)` | src/ 是否有 git 未提交改动。 | `pipeline/guardrail.py:691` |
| `protect_src_enabled` | `()` | OSH_GUARD_PROTECT_SRC=1 时保护 src/ (部署前检查未提交改动)。 | `pipeline/guardrail.py:727` |
| `_safe_rel` | `(rel: str)` | 把相对路径转成安全的文件系统相对路径 (防目录穿越)。 | `pipeline/guardrail.py:737` |
| `_atomic_write` | `(path: Path, content: bytes)` | 原子写: 先写临时文件再 rename, 防半状态。 | `pipeline/guardrail.py:742` |
| `load_pipeline_knowledge_config` | `(project_dir: str | Path)` | Load ``.yuleosh/pipeline-knowledge.yaml`` under ``project_dir``. | `pipeline/knowledge_injection.py:89` |
| `_resolve_skill_names` | `(step_key: str, config: PipelineKnowledgeConfig)` | Skill names for a step: per-step override + global list. | `pipeline/knowledge_injection.py:107` |
| `_sync_rag_context` | `(query: str, sources: list[str] | None, rag_engine, top_k: int)` | Run the async RAG retrieval in a sync context (pipeline is sync). | `pipeline/knowledge_injection.py:126` |
| `_track_memory_usage` | `(prompt: str, step_key: str)` | P3 埋点：记录本次注入的 fact_ids + step_key（usage_log）。 | `pipeline/knowledge_injection.py:154` |
| `_assemble_memory` | `(prompt: str, config: PipelineKnowledgeConfig, step_key: str)` | Project memory section (non-fatal). | `pipeline/knowledge_injection.py:172` |
| `_assemble_rag` | `(prompt: str, config: PipelineKnowledgeConfig, rag_engine)` | RAG rules section (non-fatal). | `pipeline/knowledge_injection.py:189` |
| `_assemble_skills` | `(step_key: str, config: PipelineKnowledgeConfig)` | Skills section (non-fatal). | `pipeline/knowledge_injection.py:209` |
| `_assemble_active` | `(config: PipelineKnowledgeConfig, project_dir: str | Path)` | Active knowledge index section (方案 B, non-fatal). | `pipeline/knowledge_injection.py:228` |
| `assemble_pipeline_knowledge` | `(step_key: str, spec_content: str, prompt: str, config: PipelineKnowledgeConfig | None, project_dir: str | Path | None, rag_engine)` | Assemble the unified knowledge context for a pipeline step. | `pipeline/knowledge_injection.py:266` |
| `_capture_llm_changeset` | `(session: PipelineSession)` | Snapshot current LLM artifact files before the LLM step (H3-2a). | `pipeline/llm_gateway.py:66` |
| `_restore_llm_changeset` | `(session: PipelineSession, changeset: dict[str, bytes | None])` | Restore artifact files from a previously captured ChangeSet (H3-2b). | `pipeline/llm_gateway.py:111` |
| `_step_key` | `(session: PipelineSession)` | Resolve current step key — thread-local first (D2 parallel), then session. | `pipeline/llm_gateway.py:141` |
| `resolve_step_role` | `(session: PipelineSession)` | Resolve the current step's agent role for ``task_type`` routing. | `pipeline/llm_gateway.py:156` |
| `_budget_enforced` | `()` | Whether budget overrun should hard-fail instead of warning only. | `pipeline/llm_gateway.py:168` |
| `_check_pipeline_budget` | `(session: PipelineSession)` | Pipeline 总量预算检查 — 超限默认只警告；ENFORCE=1 时抛错阻断。 | `pipeline/llm_gateway.py:173` |
| `_record_usage` | `(session: PipelineSession, usage: dict)` | Record one LLM call's usage into the session (OpenAI-style dict). | `pipeline/llm_gateway.py:193` |
| `call_step_llm` | `(session: PipelineSession, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, task_type: str | None)` | Unified per-step LLM entry point (方案 C, C4). | `pipeline/llm_gateway.py:212` |
| `_detect_project_type` | `(project_dir: str)` | Read .yuleosh.yaml and detect the project type (e.g. autosar). | `pipeline/orchestrator.py:76` |
| `_ensure_autosar_pipeline_config` | `(project_dir: str, template_dir: Optional[Path])` | If project type is autosar and no `.yuleosh/ci-config.yaml` exists, | `pipeline/orchestrator.py:107` |
| `_detect_and_bootstrap` | `(project_dir: str)` | Auto-detect project type and bootstrap missing config. | `pipeline/orchestrator.py:134` |
| `load_agent_constraints` | `(project_dir: str)` | Load agent constraints from `.yuleosh/agents/` directory. | `pipeline/orchestrator.py:205` |
| `_mock_llm_client` | `()` | Create a mock LLM client for demo/testing (--mock flag). | `pipeline/orchestrator.py:263` |
| `_find_previous_session` | `(spec_path: str, project_dir: str)` | Find the most recent pipeline session for the same spec. | `pipeline/orchestrator.py:303` |
| `_print_step_timings` | `(session)` | Print per-step wall-clock timings from session.steps. | `pipeline/orchestrator.py:335` |
| `run_pipeline` | `(spec_path: str, name: Optional[str], llm_client: Optional[Callable], mock: bool, profile: Optional[str], org_id: int, user_id: int | None, user_email: str | None, from_step: int, run_id: Optional[str], step_callback: Optional[Callable])` | Run the full OSH pipeline for a given spec. | `pipeline/orchestrator.py:365` |
| `status_pipeline` | `(name: Optional[str])` | Display pipeline session status(es). | `pipeline/orchestrator.py:832` |
| `_propagate_step_verdict` | `(session: 'PipelineSession', step_idx: int, step_key: str, output_path: str)` | Propagate a step artifact's ``status`` field into session state. | `pipeline/orchestrator.py:890` |
| `_rt_run_id` | `(session)` | Realtime 事件的 run_id 取值 (Stage-6, 2026-09-05)。 | `pipeline/orchestrator.py:998` |
| `_rt_project_dir` | `(project_dir: str)` | Realtime 事件的 project_dir 取值。 | `pipeline/orchestrator.py:1014` |
| `_emit_realtime_stage_start` | `(session, step_idx: int, step_key: str, step_name: str, agent: str, project_dir: str)` | — | `pipeline/orchestrator.py:1027` |
| `_emit_realtime_stage_end` | `(session, step_idx: int, step_key: str, step_name: str, agent: str, status: str, started_at, finished_at, project_dir: str)` | — | `pipeline/orchestrator.py:1044` |
| `_emit_realtime_stage_skipped` | `(session, step_idx: int, step_key: str, step_name: str, agent: str, project_dir: str)` | — | `pipeline/orchestrator.py:1069` |
| `_emit_realtime_file_produced` | `(output_path, step_key: str, session, project_dir: str)` | 给前端看板 「文档证据即时显示」用的 file_produced 事件。 | `pipeline/orchestrator.py:1087` |
| `_invoke_step_callback` | `(step_callback, session)` | 编排器每步完成后的 best-effort 钩子 (→ API 层看板实时回写)。 | `pipeline/orchestrator.py:1112` |
| `_execute_step` | `(session: 'PipelineSession', step_idx: int, step_key: str, agent: str, step_name: str, handler: Callable, spec_path: str, project_dir: str, from_step: int, step_callback)` | Execute a single pipeline step (serial or D2 parallel worker). | `pipeline/orchestrator.py:1128` |
| `_run_parallel_group` | `(session: 'PipelineSession', members: list[tuple[int, str, str, str, Callable]], from_step: int, project_dir: str, spec_path: str, step_callback)` | Run a D2 parallel group's steps concurrently (ThreadPoolExecutor). | `pipeline/orchestrator.py:1322` |
| `_run_step_with_fallback` | `(handler: Callable, session: PipelineSession, step_key: str, step_name: str, spec_path: str)` | Run a pipeline step handler with LLM output validation and fallback. | `pipeline/orchestrator.py:1382` |
| `main` | `()` | — | `pipeline/orchestrator.py:1430` |
| `_inject_spec` | `(spec_content: str)` | Inject spec content with an explicit truncation warning (方案 B, 2026-08-17). | `pipeline/prompts.py:56` |
| `_inject_limited` | `(content: str, limit: int, what: str)` | Inject ``content`` capped at ``limit`` chars with an explicit marker. | `pipeline/prompts.py:72` |
| `get_prompt_versions` | `()` | Return a copy of the current prompt version map. | `pipeline/prompts.py:93` |
| `get_prompt_version` | `(step_key: str)` | Return the version string for a given step key. | `pipeline/prompts.py:98` |
| `build_super_analysis_prompt` | `(spec_content: str, spec_name: str, requirements: list[dict], scenarios: list[str])` | Build a S.U.P.E.R. analysis prompt. | `pipeline/prompts.py:107` |
| `build_prd_prompt` | `(spec_content: str, spec_name: str, requirements: list[dict], scenarios: list[str], super_analysis_content: str, existing_headers: str, project_asil: str)` | Build a Product Requirements Document (PRD) generation prompt. | `pipeline/prompts.py:152` |
| `build_architecture_prompt` | `(spec_content: str, spec_name: str, session_name: str, directories: list[str], source_files: list[str], tech_stack: list[str], source_tree_str: str, key_file_snippets: list[str], repo_facts: str)` | Build an architecture design prompt. | `pipeline/prompts.py:299` |
| `_trunc_ref` | `(text: str, limit: int, ref: str)` | Reference-marked truncation for prompt injection (D1). | `pipeline/prompts.py:382` |
| `build_development_prompt` | `(spec_content: str, spec_name: str, architecture_content: str, prd_content: str, super_analysis_content: str, src_lines: int, src_file_count: int, test_lines: int, test_file_count: int, test_func_count: int, coverage_summary: str, repo_facts: str, git_commits: int, git_log: str)` | Build a development planning prompt. | `pipeline/prompts.py:397` |
| `build_test_planning_prompt` | `(spec_content: str, requirements: list[dict], architecture_content: Optional[str], development_plan_content: Optional[str], repo_facts: str, claude_review_feedback: str)` | Build a test-planning prompt that generates a comprehensive test plan. | `pipeline/prompts.py:507` |
| `build_code_review_prompt` | `(spec_content: str, spec_name: str, session_name: str, artifact_contents: dict[str, str], source_files: list[dict], timestamp: str, style_rules: str)` | Build a code review prompt for Hermes. | `pipeline/prompts.py:622` |
| `build_final_report_prompt` | `(session_name: str, session_status: str, spec_path: str, steps: list[dict], errors: list[str], artifact_paths: dict[str, str], artifact_summaries: dict[str, str])` | Build a final report prompt that asks the LLM to summarize the pipeline run. | `pipeline/prompts.py:737` |
| `build_internal_review_prompt` | `(session_name: str, spec_content: str, spec_name: str, artifact_paths: dict[str, str], artifact_summaries: dict[str, str])` | Build an internal review prompt for 小明 to assess artifact quality. | `pipeline/prompts.py:814` |
| `count_test_functions` | `(path: Path)` | 统计测试函数/用例数 (静态兜底)。 | `pipeline/repo_facts.py:36` |
| `_collect_pytest_case_count` | `(project_dir: Path)` | 真实 pytest 用例数 (含参数化展开), 失败返回 0。 | `pipeline/repo_facts.py:56` |
| `detect_test_framework` | `(tests_dir: Path)` | 探测测试框架: Unity / custom-Check / pytest / unknown。 | `pipeline/repo_facts.py:78` |
| `_project_asil_from_files` | `(project_dir: Path)` | ASIL 来源: yuleosh.yaml asil 字段 → project-context.md / README 正则。 | `pipeline/repo_facts.py:115` |
| `get_project_asil` | `(project_dir: str | Path)` | 项目 ASIL 来源 (r21e 扩展): yuleosh.yaml asil → 项目文档正则。 | `pipeline/repo_facts.py:154` |
| `collect_repo_facts` | `(project_dir: str | Path)` | 收集文档步骤需要的仓库事实快照。 | `pipeline/repo_facts.py:159` |
| `format_repo_facts` | `(facts: dict)` | 把仓库事实快照格式化为 prompt 注入段落 (context-only, 禁止转述). | `pipeline/repo_facts.py:241` |
| `get_all_function_names` | `(project_dir: str | Path)` | Return all function names defined in source files under ``project_dir``. | `pipeline/repo_facts.py:318` |
| `get_all_requirement_ids` | `(project_dir: str | Path)` | Return all requirement IDs declared in the project docs. | `pipeline/repo_facts.py:351` |
| `dedupe_review_findings` | `(review: dict[str, Any])` | 去重 review findings (2026-08-20 r22 real-8, code-review 重复膨胀). | `pipeline/review_guard.py:34` |
| `numbered_source` | `(content: str)` | 给源码每行加行号前缀, 使 LLM 引用的行号必须来自真实编号。 | `pipeline/review_guard.py:90` |
| `_real_line_count` | `(content: str)` | 真实源码行数 (不带行号前缀的原文). | `pipeline/review_guard.py:104` |
| `validate_review_findings` | `(review: dict[str, Any], source_files: list[dict[str, Any]])` | 验证 review findings 的 file:line 是否指向注入源码中的真实行。 | `pipeline/review_guard.py:111` |
| `_normalize_env` | `(env)` | Return a str-keyed env dict safe for ``subprocess.Popen``. | `pipeline/safe_run.py:34` |
| `run_captured` | `(cmd, cwd, timeout: int, label: str, log_dir, env)` | Run ``cmd`` without a captured pipe. | `pipeline/safe_run.py:53` |
| `safe_subprocess_run` | `(cmd, cwd, timeout, capture_output, text, check, input, env, shell, encoding, errors, **kwargs)` | Drop-in replacement for ``subprocess.run(..., capture_output=True)``. | `pipeline/safe_run.py:136` |
| `resolve_sessions_root` | `()` | Return the root directory that holds one folder per run. | `pipeline/session.py:64` |
| `_project_dir_from_session_json` | `(session_json: Path)` | 从 session.json 路径反推 project_dir。 | `pipeline/session_index.py:56` |
| `_project_dir_of` | `(data: dict, session_json: Path)` | 解析会话归属的 project_dir（优先 session 自带，否则按路径反推）。 | `pipeline/session_index.py:66` |
| `discover_project_sessions` | `(osh_home: str | Path, max_depth: int)` | 递归发现 OSH_HOME 下的所有 pipeline 会话，并按项目分组。 | `pipeline/session_index.py:81` |
| `_parse_ts` | `(value: object)` | ISO 时间串 → epoch 秒；缺失或解析失败返回 0.0。 | `pipeline/session_prune.py:87` |
| `_read_meta` | `(sdir: Path)` | 读 session.json；缺失或损坏返回 {}（不抛）。 | `pipeline/session_prune.py:100` |
| `_session_timestamp` | `(sdir: Path, meta: dict)` | run 的时间锚点：created_at → updated_at → 目录 mtime。 | `pipeline/session_prune.py:109` |
| `_is_aborted` | `(sdir: Path, meta: dict)` | T0 判定：空目录，或状态表明从未跑起来。 | `pipeline/session_prune.py:121` |
| `deterministic_evidence_files` | `(sdir: Path)` | T3 层文件：``VOLATILE_STEPS`` 的产物（可分钟级重跑再生）。 | `pipeline/session_prune.py:134` |
| `plan_prune_root` | `(root: Path, keep_last: int)` | 算出 sessions 根目录的保留方案；不修改磁盘。 | `pipeline/session_prune.py:163` |
| `plan_prune` | `(project_dir, keep_last: int)` | 算出一个项目的 ``<project>/.osh/sessions`` 保留方案。 | `pipeline/session_prune.py:227` |
| `_apply` | `(plan: dict, dry_run: bool)` | — | `pipeline/session_prune.py:237` |
| `prune_sessions` | `(project_dir, keep_last: int, dry_run: bool)` | 按 T0–T3 分层回收一个项目的会话目录。 | `pipeline/session_prune.py:257` |
| `prune_sessions_root` | `(root, keep_last: int, dry_run: bool)` | 同 :func:`prune_sessions`，但直接给 sessions 根目录。 | `pipeline/session_prune.py:267` |
| `format_plan` | `(plan: dict)` | 把方案渲染成可读文本 —— 清理必须显式，不静默。 | `pipeline/session_prune.py:278` |
| `main` | `(argv: list[str] | None)` | — | `pipeline/session_prune.py:302` |
| `is_cacheable` | `(step_key: str)` | 该步骤是否可跨 run 复用 (输入/生成物类, REUSABLE_STEPS)。 | `pipeline/step_cache.py:123` |
| `must_rerun` | `(step_key: str)` | 该步骤是否每轮必须真实执行 (验证结果类, 不复用历史产物)。 | `pipeline/step_cache.py:128` |
| `is_llm_step` | `(step_key: str)` | 该步骤是否为 LLM 主调用步骤 (永不缓存)。 | `pipeline/step_cache.py:133` |
| `cache_enabled` | `()` | 缓存总开关: OSH_NO_CACHE=1 禁用。 | `pipeline/step_cache.py:138` |
| `_file_hash` | `(path: Path)` | SHA-256 文件哈希 (前 16 hex, 防路径泄露)。 | `pipeline/step_cache.py:148` |
| `_tree_hash` | `(root: Path)` | 递归树哈希: (相对路径 + 文件内容 hash) 排序拼接。 | `pipeline/step_cache.py:160` |
| `compute_fingerprint` | `(session, step_key: str)` | 确定性步骤指纹 — 只含代码/配置/状态, 不含文档 artifacts。 | `pipeline/step_cache.py:186` |
| `_cache_root` | `(project_dir: str | Path)` | — | `pipeline/step_cache.py:246` |
| `_output_is_failed` | `(path: Path)` | JSON 产物 status 是否属失败集合 (2026-08-17 r21c 复盘)。 | `pipeline/step_cache.py:250` |
| `_cache_dir_outputs` | `(d: Path)` | 缓存目录下 output/ 里的产物文件列表。 | `pipeline/step_cache.py:267` |
| `lookup` | `(project_dir: str | Path, step_key: str, fingerprint: str)` | 命中返回缓存目录, 未命中 None。 | `pipeline/step_cache.py:275` |
| `store` | `(project_dir: str | Path, step_key: str, fingerprint: str, output_path: str | Path)` | 把步骤输出复制进缓存 (保留原文件名), 返回缓存目录。 | `pipeline/step_cache.py:290` |
| `restore` | `(project_dir: str | Path, step_key: str, fingerprint: str, session)` | 把缓存产物恢复到 session dir, 返回恢复路径。 | `pipeline/step_cache.py:337` |
| `purge_step_cache` | `(project_dir: str | Path, step_keys: 'Optional[set[str] | frozenset[str]]', dry_run: bool)` | 删除指定步骤的全部历史缓存条目。 | `pipeline/step_cache.py:362` |
| `purge_verification_cache` | `(project_dir: str | Path)` | 每轮 pipeline 启动时调用: 清空全部验证结果类历史缓存。 | `pipeline/step_cache.py:414` |
| `_baseline_root` | `(project_dir)` | — | `pipeline/step_cache.py:480` |
| `save_baseline` | `(project_dir, session_id: str, metrics: 'BaselineMetrics')` | Persist *metrics* as the named baseline and update latest_id.txt pointer. | `pipeline/step_cache.py:484` |
| `load_latest_baseline` | `(project_dir)` | Load the most recently saved baseline, or None if not present. | `pipeline/step_cache.py:498` |
| `compare_to_baseline` | `(current: 'BaselineMetrics', baseline: 'BaselineMetrics')` | Compare *current* run metrics against *baseline*. | `pipeline/step_cache.py:515` |
| `extract_metrics_from_session` | `(session_dir: Path)` | Extract pipeline metrics from a completed session directory. | `pipeline/step_cache.py:561` |
| `_collect_seed_contract` | `(project_dir: str | Path)` | Collect public function names from existing src/ headers. | `pipeline/step_classes.py:21` |
| `_make_behavior_verify` | `(project_dir: str | Path)` | Build a behavior-verify callback for CodegenEngine. | `pipeline/step_classes.py:60` |
| `get_step_instance` | `(step_key: str)` | Return the singleton PipelineStep instance for *step_key*. | `pipeline/step_classes.py:593` |
| `register_step` | `(step_key: str, instance: PipelineStep)` | Register a custom step instance (for extensibility). | `pipeline/step_classes.py:600` |
| `set_step_key` | `(step_key: str)` | Set the current step key for the calling thread. | `pipeline/step_context.py:26` |
| `get_step_key` | `()` | Return the calling thread's current step key ('' if unset). | `pipeline/step_context.py:31` |
| `clear_step_key` | `()` | Clear the calling thread's step key (defensive; worker reuse). | `pipeline/step_context.py:36` |
| `_build_effective_system_prompt` | `(session: PipelineSession, system_prompt: str)` | Prepend agent constraints to the system prompt. | `pipeline/stages/llm.py:29` |
| `_build_role_scoped_prompt` | `(session: PipelineSession, system_prompt: str, by_role: dict)` | Inject only the current step's role constraints + shared baseline. | `pipeline/stages/llm.py:75` |
| `_gateway_step_keys` | `()` | Parse ``YULEOSH_LLM_GATEWAY_STEPS`` (comma-separated step keys). | `pipeline/stages/llm.py:122` |
| `_call_llm` | `(session: PipelineSession, system_prompt: str, user_prompt: str, **kwargs)` | Call LLM using the session's injected client or fall back to global chat_completion. | `pipeline/stages/llm.py:132` |
| `_check_llm_key` | `()` | Check for a valid LLM API key in environment variables. | `pipeline/stages/llm.py:295` |
| `_parse_jsonl_review` | `(raw: str, session_name: str)` | 解析 JSONL review 输出 (2026-08-20 r22 real-10, 截断容错根治). | `pipeline/stages/spec.py:38` |
| `_recover_truncated_review` | `(raw: str, session_name: str)` | 从被截断的 LLM review JSON 中恢复已完成内容 (2026-08-20 r22 real-8). | `pipeline/stages/spec.py:130` |
| `_get_spec_mtime` | `(spec_path: str)` | Return file mtime for cache invalidation. | `pipeline/stages/spec.py:243` |
| `_parse_spec` | `(spec_path: str)` | Parse spec file: returns requirements + scenarios, cached via SQLite. | `pipeline/stages/spec.py:255` |
| `_parse_requirements` | `(spec_path: str)` | Read requirements from a spec file. Each requirement is a dict with name and shall_statements. | `pipeline/stages/spec.py:286` |
| `_parse_scenarios` | `(spec_path: str)` | Read GIVEN/WHEN/THEN scenarios from a spec file. | `pipeline/stages/spec.py:336` |
| `_try_parse_hermes_json` | `(raw: str, session_name: str)` | Parse Hermes review JSON from LLM output with robust fallback. | `pipeline/stages/spec.py:365` |
| `timed_step` | `(handler)` | Decorate a step handler to measure and log execution time. | `pipeline/stages/step_timing.py:18` |
| `_resolve_handler` | `(step_key: str, legacy_fn)` | Return the legacy step function (Sprint 3 eliminated the dual-path). | `pipeline/step_handlers/__init__.py:157` |
| `_step_keys` | `()` | Return the ordered step keys of PIPELINE_STEPS. | `pipeline/step_handlers/__init__.py:246` |
| `_check_prd_section_coverage` | `(spec_content: str, prd_content: str)` | Return spec section IDs (SR-XXX/SW-XXX) missing from the PRD. | `pipeline/step_handlers/analysis.py:45` |
| `_prd_retry_prompt` | `(original_user_prompt: str, missing_sections: list[str])` | Build a retry prompt feeding the missing section list back to the LLM. | `pipeline/step_handlers/analysis.py:69` |
| `_prd_truncation_retry_prompt` | `(original_user_prompt: str, truncations: list[str])` | Build a retry prompt feeding truncation signals back to the LLM. | `pipeline/step_handlers/analysis.py:83` |
| `_detect_prd_truncation` | `(prd_content: str, scenario_count: int)` | Detect PRD truncation/incompleteness signals (2026-08-16). | `pipeline/step_handlers/analysis.py:99` |
| `step_super_analysis` | `(session: PipelineSession)` | Step 1: 小明 — S.U.P.E.R analysis powered by real LLM. | `pipeline/step_handlers/analysis.py:152` |
| `step_hermes_prd` | `(session: PipelineSession)` | Step 2: Hermes — AI-powered PRD generation from spec. | `pipeline/step_handlers/analysis.py:232` |
| `step_internal_review` | `(session: PipelineSession)` | Step 3: 小明 — AI-powered internal review. | `pipeline/step_handlers/analysis.py:410` |
| `record_step_verdict` | `(session, step_name: str, verdict: str, artifact_paths: 'list[str] | None')` | Write a step.verdict audit event into the SHA-256 hash chain. | `pipeline/step_handlers/audit_utils.py:21` |
| `_resolve_coverage_project_dir` | `(session: PipelineSession)` | Resolve the C project directory for the coverage gate. | `pipeline/step_handlers/c_coverage_gate.py:38` |
| `_git_commit_short` | `(project_dir: str)` | Return the short git commit hash of the project (fallback 'unknown'). | `pipeline/step_handlers/c_coverage_gate.py:56` |
| `_has_c_sources` | `(project_dir: str)` | 项目是否含 C/C++ 源码 (排除 third_party/build/.git/.osh/venv)。 | `pipeline/step_handlers/c_coverage_gate.py:71` |
| `coverage_gate_step` | `(session: PipelineSession)` | Run C coverage pipeline verification end-to-end. | `pipeline/step_handlers/c_coverage_gate.py:92` |
| `_coverage_build_stale` | `(project_dir: Path, coverage_build_dir: Path)` | True if any src/tests file is newer than the newest coverage object. | `pipeline/step_handlers/c_coverage_gate.py:241` |
| `_phase_build_coverage` | `(project_dir: str, results: dict)` | Phase 1: Build with coverage enabled. | `pipeline/step_handlers/c_coverage_gate.py:272` |
| `_phase_run_tests` | `(project_dir: str, results: dict)` | Phase 2: Run tests to generate .gcda files. | `pipeline/step_handlers/c_coverage_gate.py:366` |
| `_phase_run_gcovr` | `(project_dir: str, results: dict)` | Phase 3: Generate coverage JSON report using gcovr. | `pipeline/step_handlers/c_coverage_gate.py:436` |
| `_phase_check_gate` | `(project_dir: str, results: dict)` | Phase 4: Validate coverage against gate threshold. | `pipeline/step_handlers/c_coverage_gate.py:541` |
| `_get_fail_under` | `(project_dir: str)` | Read c_fail_under from project configuration. | `pipeline/step_handlers/c_coverage_gate.py:652` |
| `_write_results` | `(session: PipelineSession, results: dict)` | Write coverage gate results to session output file. | `pipeline/step_handlers/c_coverage_gate.py:682` |
| `step_code_review_unified` | `(session: PipelineSession)` | Step: code-review 超集 — 集成审查 + 4 嵌入式专项组（合并）。 | `pipeline/step_handlers/code_review_unified.py:36` |
| `step_claude_arch` | `(session: PipelineSession)` | Step 4: Claude — AI-powered architecture design. | `pipeline/step_handlers/execution.py:46` |
| `step_claude_dev` | `(session: PipelineSession)` | Step 5: Claude — AI-powered development. | `pipeline/step_handlers/execution.py:172` |
| `_detect_project_language` | `(project_dir: Path)` | Heuristic project language detection for codegen language_hint. | `pipeline/step_handlers/execution.py:189` |
| `_step_claude_dev_codegen` | `(session: PipelineSession)` | D3 codegen branch: spec/arch/PRD → code → verify → auto-fix. | `pipeline/step_handlers/execution.py:226` |
| `_step_claude_dev_planning` | `(session: PipelineSession)` | Legacy planning behavior (unchanged). | `pipeline/step_handlers/execution.py:368` |
| `step_codegen_deploy` | `(session: PipelineSession)` | Step: 小明 — 代码产物部署 (codegen artifacts → project src/). | `pipeline/step_handlers/execution.py:538` |
| `step_test_planning` | `(session: PipelineSession)` | Step 6: Claude — AI-powered test planning. | `pipeline/step_handlers/execution.py:855` |
| `step_claude_test` | `(session: PipelineSession)` | Step 7: Claude — Self-test with real test runner output. | `pipeline/step_handlers/execution.py:981` |
| `artifacts_read` | `(artifacts: dict[str, str], key: str)` | Read the content of a prior-step artifact if it exists. | `pipeline/step_handlers/execution.py:1194` |
| `_find_cli` | `(binary: str)` | Locate an external CLI binary, or None. | `pipeline/step_handlers/external_agents.py:80` |
| `_load_env_key` | `(key: str)` | Load an API key from ``~/.hermes/.env`` when not already exported. | `pipeline/step_handlers/external_agents.py:86` |
| `_write_report` | `(session: PipelineSession, step_key: str, report: dict)` | Write a structured step report JSON into the session dir. | `pipeline/step_handlers/external_agents.py:103` |
| `_collect_spec_and_artifacts` | `(session: PipelineSession)` | Collect spec content + existing artifact summaries for context. | `pipeline/step_handlers/external_agents.py:114` |
| `_format_artifacts_for_prompt` | `(artifacts: dict[str, str])` | Render artifact contents into a compact prompt section. | `pipeline/step_handlers/external_agents.py:150` |
| `_build_codex_prompt` | `(spec_content: str, artifacts_block: str, project_dir: str)` | Build the Codex verification prompt (Chinese, structured JSON output). | `pipeline/step_handlers/external_agents.py:172` |
| `_deploy_status_note` | `(project_dir: str)` | 读取 codegen 部署状态 — claude-review 需要知道"当前 src 是否是 | `pipeline/step_handlers/external_agents.py:217` |
| `_build_claude_review_prompt` | `(spec_content: str, artifacts_block: str, project_dir: str)` | Build the Claude review prompt (Chinese, structured JSON output). | `pipeline/step_handlers/external_agents.py:255` |
| `_official_shall_block` | `(spec_content: str, limit: int)` | 从 spec 提取官方 SHALL 清单文本（数量 + 前 N 条，供评审 prompt 注入）。 | `pipeline/step_handlers/external_agents.py:300` |
| `_run_cli` | `(cmd: list[str], timeout: int, cwd: str | None, extra_env: dict[str, str] | None)` | Run an external CLI command with timeout + merged env. Never hangs. | `pipeline/step_handlers/external_agents.py:320` |
| `_parse_json_output` | `(stdout: str)` | Extract the first JSON object from CLI stdout (tolerates noise). | `pipeline/step_handlers/external_agents.py:332` |
| `step_codex_verify` | `(session: PipelineSession)` | Step: Codex — 对产出进行真实测试验证，发现缺陷即阻断（闭环起点）。 | `pipeline/step_handlers/external_agents.py:414` |
| `step_claude_review` | `(session: PipelineSession)` | Step: Claude — 对方案/建议进行评审与头脑风暴，未一致即阻断。 | `pipeline/step_handlers/external_agents.py:533` |
| `step_fault_injection` | `(session)` | Pipeline step handler for fault injection testing. | `pipeline/step_handlers/fault_inject.py:492` |
| `retry` | `(max_attempts: int, base_delay: float, backoff: float, exceptions: tuple)` | Decorator: 重试指定异常类型，使用指数退避。 | `pipeline/step_handlers/handler_base.py:55` |
| `as_handler` | `(step_name: str, **kwargs)` | 将函数装饰为 BaseHandler 风格。 | `pipeline/step_handlers/handler_base.py:419` |
| `read_sub_status` | `(report_path: str | Path | None)` | Read a sub-handler report's status. | `pipeline/step_handlers/merged_step.py:45` |
| `merge_statuses` | `(statuses: list[str])` | Merge sub-report statuses: failed > retry > skipped > passed. | `pipeline/step_handlers/merged_step.py:86` |
| `run_substeps` | `(session: PipelineSession, step_key: str, substeps: list[tuple[str, Callable[[PipelineSession], str]]], summary_prefix: str)` | Run sub-handlers sequentially, merge statuses, write merged JSON. | `pipeline/step_handlers/merged_step.py:102` |
| `write_merged_report` | `(session: PipelineSession, step_key: str, report: dict)` | Write the merged step report JSON into the session dir. | `pipeline/step_handlers/merged_step.py:179` |
| `is_mock` | `(session)` | Return True only when the session is explicitly in mock mode. | `pipeline/step_handlers/mock_skip.py:31` |
| `write_mock_skip` | `(session, step_key: str, reason: str, report_extra: dict | None, suffix: str)` | Write a SKIPPED report for ``step_key`` and return its path. | `pipeline/step_handlers/mock_skip.py:36` |
| `write_llm_unavailable_skip` | `(session, step_key: str, reason: str)` | Write a SKIPPED report because the LLM provider is unreachable. | `pipeline/step_handlers/mock_skip.py:70` |
| `step_qemu_verify` | `(session: PipelineSession)` | Step: qemu-verify — QEMU 仿真测试 + C 覆盖率门禁（合并）。 | `pipeline/step_handlers/qemu_verify.py:28` |
| `step_hermes_review` | `(session: PipelineSession)` | Step 8: Hermes — AI-powered code review. | `pipeline/step_handlers/review.py:36` |
| `step_final_report` | `(session: PipelineSession)` | Step 9: 小明 — AI-powered final report generation. | `pipeline/step_handlers/review.py:196` |
| `step_review_arch` | `(session: PipelineSession)` | Step: 小克 — 架构设计审查。 | `pipeline/step_handlers/review_arch.py:40` |
| `_build_arch_review_prompt` | `(spec_content: str, spec_name: str, architecture_content: str)` | Build prompts for the LLM-powered architecture review. | `pipeline/step_handlers/review_arch.py:168` |
| `_find_map_file` | `(project_dir: Path)` | Find the linker map file (.map) in the build output directory. | `pipeline/step_handlers/review_build.py:35` |
| `_find_binary_files` | `(project_dir: Path)` | Discover compiled binary output files. | `pipeline/step_handlers/review_build.py:46` |
| `_parse_map_file` | `(path: Path)` | Parse a GNU ld map file into structured sections data. | `pipeline/step_handlers/review_build.py:65` |
| `_parse_size_output` | `(project_dir: Path)` | Try to run arm-none-eabi-size or read a size output file. | `pipeline/step_handlers/review_build.py:181` |
| `_check_section_sizes` | `(parsed: dict, project_dir: Path)` | Check section sizes against available memory. | `pipeline/step_handlers/review_build.py:236` |
| `_check_address_alignment` | `(parsed: dict)` | Check function/variable address alignment in the map file. | `pipeline/step_handlers/review_build.py:343` |
| `_check_unused_sections` | `(parsed: dict)` | Check for unused/discarded sections and orphan sections. | `pipeline/step_handlers/review_build.py:403` |
| `_check_binary_sizes` | `(project_dir: Path)` | Check compiled binary file sizes. | `pipeline/step_handlers/review_build.py:477` |
| `_check_size_trend` | `(parsed: dict, project_dir: Path)` | Compare current sizes against a historical baseline if available. | `pipeline/step_handlers/review_build.py:526` |
| `_check_unused_symbols` | `(parsed: dict)` | Check for unused or redundant symbols. | `pipeline/step_handlers/review_build.py:592` |
| `_static_build_review` | `(project_dir: Path)` | Run all static checks on build artifacts. | `pipeline/step_handlers/review_build.py:660` |
| `_build_build_review_prompt` | `(map_file: Path | None, binaries: dict)` | Build prompts for LLM-powered build output review. | `pipeline/step_handlers/review_build.py:710` |
| `step_review_build` | `(session: PipelineSession)` | Step: 小克 — 编译输出验证。 | `pipeline/step_handlers/review_build.py:756` |
| `step_review_code` | `(session: PipelineSession)` | Step: 小克 — 代码实现审查。 | `pipeline/step_handlers/review_code.py:39` |
| `_build_code_review_prompt` | `(spec_content: str, spec_name: str, architecture_content: str, dev_plan_content: str, source_files: list[dict])` | Build prompts for the LLM-powered code implementation review. | `pipeline/step_handlers/review_code.py:184` |
| `_strip_comment_and_strings` | `(line: str)` | 剥离 C 行内注释与字符串/字符字面量, 返回仅含代码的部分。 | `pipeline/step_handlers/review_critical_safety.py:39` |
| `_strip_block_comments` | `(lines: list[str])` | 剥离跨行 /* ... */ 块注释, 保留行数与行长(注释字符替换为空格)。 | `pipeline/step_handlers/review_critical_safety.py:60` |
| `_collect_defined_macros` | `(lines: list[str])` | 收集本翻译单元内所有 ``#define MACRO`` 宏名（对象式/函数式均可）。 | `pipeline/step_handlers/review_critical_safety.py:127` |
| `_pp_is_include_guard` | `(lines: list[str], idx: int, name: str)` | 判断 ``lines[idx]`` 的 ``#ifndef NAME`` 是否为 include-guard 惯用法 | `pipeline/step_handlers/review_critical_safety.py:140` |
| `_eval_pp_cond` | `(cond: str, defined: set[str])` | 保守评估 ``#if EXPR`` 的活跃性。 | `pipeline/step_handlers/review_critical_safety.py:153` |
| `_strip_inactive_pp` | `(lines: list[str], defined_macros: set[str])` | 空白化「证明为非活跃」的预处理器条件块（#if/#ifdef/#ifndef/#elif/#else/#endif）。 | `pipeline/step_handlers/review_critical_safety.py:178` |
| `get_build_flags` | `(enable_warnings: bool, enable_stack_protect: bool, enable_ubsan: bool, target: str)` | 生成编译器加固 flags。 | `pipeline/step_handlers/review_critical_safety.py:976` |
| `step_review_critical_safety` | `(session: PipelineSession)` | Pipeline Step: 关键安全异常阻塞检查。 | `pipeline/step_handlers/review_critical_safety.py:1023` |
| `_extract_tasks` | `(devplan_content: str)` | Extract task entries from the Development Plan. | `pipeline/step_handlers/review_development.py:44` |
| `_check_acceptance_criteria` | `(devplan_content: str)` | Check for presence of acceptance criteria / delivery standards. | `pipeline/step_handlers/review_development.py:105` |
| `_check_dependency_modeling` | `(devplan_content: str)` | Check whether task dependencies are modeled. | `pipeline/step_handlers/review_development.py:137` |
| `_check_time_estimates` | `(tasks: list[dict], devplan_content: str)` | Check whether tasks have time or effort estimates. | `pipeline/step_handlers/review_development.py:161` |
| `_check_module_coverage` | `(devplan_content: str, architecture_content: str)` | Cross-reference architecture modules against Development Plan tasks. | `pipeline/step_handlers/review_development.py:188` |
| `_assess_granularity` | `(tasks: list[dict])` | Assess whether task granularity is appropriate. | `pipeline/step_handlers/review_development.py:226` |
| `_build_devplan_review_prompt` | `(spec_content: str, spec_name: str, architecture_content: str, devplan_content: str)` | Build system + user prompts for the LLM-powered devplan review. | `pipeline/step_handlers/review_development.py:271` |
| `step_review_development` | `(session: PipelineSession)` | Step 5.5: 小克 — Development 产物审查。 | `pipeline/step_handlers/review_development.py:321` |
| `step_review_embedded_build` | `(session: PipelineSession)` | Step: embedded-build 组 — linker + startup + build 专项审查（合并）。 | `pipeline/step_handlers/review_embedded_build.py:32` |
| `step_review_embedded_peripheral` | `(session: PipelineSession)` | Step: embedded-peripheral 组 — bsp + power + mmio 专项审查（合并）。 | `pipeline/step_handlers/review_embedded_peripheral.py:29` |
| `step_review_embedded_realtime` | `(session: PipelineSession)` | Step: embedded-realtime 组 — interrupt + timing + watchdog 专项审查（合并）。 | `pipeline/step_handlers/review_embedded_realtime.py:31` |
| `step_review_embedded_runtime` | `(session: PipelineSession)` | Step: embedded-runtime 组 — rtos + memory + stack + nvm 专项审查（合并）。 | `pipeline/step_handlers/review_embedded_runtime.py:30` |
| `_find_c_sources` | `(project_dir: Path)` | Discover C/C++ sources under src/ (skip artifacts/.yuleosh/build). | `pipeline/step_handlers/review_interrupt.py:54` |
| `_scan_interrupt_safety` | `(project_dir: Path)` | 静态扫描中断风险域，返回 findings。 | `pipeline/step_handlers/review_interrupt.py:70` |
| `_build_interrupt_review_prompt` | `(project_dir: Path, findings: list[InterruptFinding])` | Build the interrupt-safety review prompt. | `pipeline/step_handlers/review_interrupt.py:170` |
| `step_review_interrupt` | `(session: PipelineSession)` | Step: 小克 — 中断系统审查 (embedded-realtime 组)。 | `pipeline/step_handlers/review_interrupt.py:208` |
| `_find_linker_scripts` | `(project_dir: Path)` | Discover linker/ scatter files in the project tree. | `pipeline/step_handlers/review_linker.py:35` |
| `_check_stack_size` | `(content: str, path: Path)` | Check stack / heap size definitions. | `pipeline/step_handlers/review_linker.py:54` |
| `_check_section_definitions` | `(content: str, path: Path)` | Check for essential section definitions. | `pipeline/step_handlers/review_linker.py:142` |
| `_check_vector_table_alignment` | `(content: str, path: Path)` | Check interrupt vector table alignment. | `pipeline/step_handlers/review_linker.py:182` |
| `_check_lma_vma_difference` | `(content: str, path: Path)` | Check if .data section has AT> for LMA/VMA separation (ARM XIP). | `pipeline/step_handlers/review_linker.py:234` |
| `_check_arm_exception_tables` | `(content: str, path: Path)` | Check for .ARM.exidx and .ARM.extab exception table sections. | `pipeline/step_handlers/review_linker.py:269` |
| `_check_heap_stack_overlap` | `(content: str, path: Path)` | Check if .heap and .stack share the same memory region without separator. | `pipeline/step_handlers/review_linker.py:392` |
| `_check_memory_regions` | `(content: str, path: Path)` | Check ROM / RAM address ranges for reasonableness. | `pipeline/step_handlers/review_linker.py:486` |
| `_static_linker_review` | `(project_dir: Path)` | Run all static checks on discovered linker scripts. | `pipeline/step_handlers/review_linker.py:559` |
| `_build_linker_review_prompt` | `(linker_contents: dict[str, str])` | Build prompts for LLM-powered linker script review. | `pipeline/step_handlers/review_linker.py:597` |
| `step_review_linker` | `(session: PipelineSession)` | Step: 小克 — 链接脚本审查。 | `pipeline/step_handlers/review_linker.py:630` |
| `_find_source_files` | `(project_dir: Path)` | Discover C / C++ / header / assembly source files. | `pipeline/step_handlers/review_memory.py:35` |
| `_check_dynamic_allocation` | `(source_files: list[Path], project_dir: Path)` | Detect malloc / calloc / realloc / free usage (embedded anti-pattern). | `pipeline/step_handlers/review_memory.py:64` |
| `_find_map_files` | `(project_dir: Path)` | Discover linker map files (compiler output) in the project tree. | `pipeline/step_handlers/review_memory.py:115` |
| `_analyze_map_file` | `(map_path: Path)` | Extract section size info from a linker map file. | `pipeline/step_handlers/review_memory.py:126` |
| `_check_global_variables` | `(source_files: list[Path], project_dir: Path)` | Estimate total global variable size using source heuristics + map file analysis. | `pipeline/step_handlers/review_memory.py:199` |
| `_check_static_recursion` | `(source_files: list[Path], project_dir: Path)` | Detect recursive functions that use static locals (risk of corruption). | `pipeline/step_handlers/review_memory.py:376` |
| `_check_circular_buffers` | `(source_files: list[Path], project_dir: Path)` | Check circular buffer / ring buffer implementations for boundary safety. | `pipeline/step_handlers/review_memory.py:465` |
| `_check_alloca_vla` | `(source_files: list[Path], project_dir: Path)` | Detect alloca() and variable-length array (VLA) usage. | `pipeline/step_handlers/review_memory.py:515` |
| `_check_stack_protection` | `(source_files: list[Path], project_dir: Path)` | Check for stack canary / stack protection mechanisms. | `pipeline/step_handlers/review_memory.py:620` |
| `_static_memory_review` | `(project_dir: Path)` | Run all static memory safety checks. | `pipeline/step_handlers/review_memory.py:672` |
| `_build_memory_review_prompt` | `(project_dir: Path)` | Build prompts for LLM-powered memory safety review. | `pipeline/step_handlers/review_memory.py:698` |
| `step_review_memory` | `(session: PipelineSession)` | Step: 小克 — 内存安全审查。 | `pipeline/step_handlers/review_memory.py:744` |
| `_read_misra_report` | `(project_dir: Path)` | Read the latest MISRA report from the standard location. | `pipeline/step_handlers/review_misra_ci.py:54` |
| `_latest_src_change_time` | `(project_dir: Path)` | 项目最新 MISRA 相关代码变更时间戳（epoch 秒）。 | `pipeline/step_handlers/review_misra_ci.py:71` |
| `_check_report_staleness` | `(project_dir: Path, report_path: Path)` | MISRA 报告新鲜度校验。 | `pipeline/step_handlers/review_misra_ci.py:95` |
| `_read_misra_trend` | `(project_dir: Path, max_entries: int)` | Read trend entries from the MISRA trend file. | `pipeline/step_handlers/review_misra_ci.py:124` |
| `_compute_trend` | `(current: dict, previous: Optional[dict])` | Compare current MISRA results with the previous run. | `pipeline/step_handlers/review_misra_ci.py:152` |
| `_classify_violations` | `(report: dict)` | Classify violations by severity and priority. | `pipeline/step_handlers/review_misra_ci.py:200` |
| `_generate_fix_recommendations` | `(classified: list[dict], trend: dict, total_violations: int)` | Generate human-readable fix recommendations. | `pipeline/step_handlers/review_misra_ci.py:233` |
| `_check_for_regression_violations` | `(current_report: dict, trend_entries: list[dict])` | Identify violations that appear to be new regressions. | `pipeline/step_handlers/review_misra_ci.py:294` |
| `step_review_misra_ci` | `(session: PipelineSession)` | Step CI.1: 小马 — MISRA CI result review. | `pipeline/step_handlers/review_misra_ci.py:345` |
| `_find_mmio_sources` | `(project_dir: Path)` | Discover MMIO-related source files grouped by category. | `pipeline/step_handlers/review_mmio.py:38` |
| `_check_clock_config` | `(files: list[Path], project_dir: Path)` | Review clock system configuration (HSE/LSE/PLL). | `pipeline/step_handlers/review_mmio.py:98` |
| `_check_gpio_config` | `(files: list[Path], project_dir: Path)` | Review GPIO pin configuration. | `pipeline/step_handlers/review_mmio.py:208` |
| `_check_nvic_config` | `(files: list[Path], project_dir: Path)` | Review NVIC (Nested Vectored Interrupt Controller) configuration. | `pipeline/step_handlers/review_mmio.py:326` |
| `_check_dma_config` | `(files: list[Path], project_dir: Path)` | Review DMA configuration. | `pipeline/step_handlers/review_mmio.py:439` |
| `_check_mmio_consistency` | `(categories: dict[str, list[Path]], project_dir: Path)` | Cross-check MMIO configuration across subsystems for consistency. | `pipeline/step_handlers/review_mmio.py:537` |
| `_build_mmio_report` | `(project_dir: Path)` | Run all MMIO checks and return unified report. | `pipeline/step_handlers/review_mmio.py:609` |
| `_render_mmio_report` | `(report: dict)` | Render MMIO review report as markdown. | `pipeline/step_handlers/review_mmio.py:653` |
| `step_review_mmio` | `(session: PipelineSession)` | Pipeline step handler for MMIO configuration review. | `pipeline/step_handlers/review_mmio.py:710` |
| `_find_c_sources` | `(project_dir: Path)` | Discover C/C++ sources under src/ (skip build/artifacts dirs). | `pipeline/step_handlers/review_nvm.py:56` |
| `_scan_nvm_safety` | `(project_dir: Path)` | 静态扫描 NVM 风险域，返回 findings。 | `pipeline/step_handlers/review_nvm.py:72` |
| `_build_nvm_review_prompt` | `(project_dir: Path, findings: list[NvmFinding])` | Build the NVM safety review prompt (aligned to spec SW-006). | `pipeline/step_handlers/review_nvm.py:156` |
| `step_review_nvm` | `(session: PipelineSession)` | Step: 小克 — NVM 存储审查 (embedded-runtime 组)。 | `pipeline/step_handlers/review_nvm.py:193` |
| `_find_power_relevant_files` | `(project_dir: Path)` | Discover files with power-management-related content. | `pipeline/step_handlers/review_power.py:36` |
| `_check_wfi_wfe_usage` | `(contents: dict[str, str])` | Check for WFI/WFE instructions in idle/sleep paths. | `pipeline/step_handlers/review_power.py:94` |
| `_check_sleep_on_exit` | `(content: str, path: Path)` | Check for SLEEPONEXIT configuration (SCB->SCR). | `pipeline/step_handlers/review_power.py:176` |
| `_check_clock_gating` | `(contents: dict[str, str])` | Check for clock gating configuration. | `pipeline/step_handlers/review_power.py:212` |
| `_check_low_power_modes` | `(contents: dict[str, str])` | Check for sleep/stop/standby mode configuration and transitions. | `pipeline/step_handlers/review_power.py:273` |
| `_check_power_regulator` | `(content: str, path: Path)` | Check voltage regulator scaling configuration. | `pipeline/step_handlers/review_power.py:335` |
| `_check_wakeup_sources` | `(contents: dict[str, str])` | Check wake-up source configuration. | `pipeline/step_handlers/review_power.py:375` |
| `_check_dvfs` | `(contents: dict[str, str])` | Check for dynamic voltage and frequency scaling configuration. | `pipeline/step_handlers/review_power.py:420` |
| `_check_peripheral_power_management` | `(contents: dict[str, str])` | Check for peripheral-specific power management patterns. | `pipeline/step_handlers/review_power.py:480` |
| `_static_power_review` | `(project_dir: Path)` | Run all static checks on power-management-related code. | `pipeline/step_handlers/review_power.py:542` |
| `_build_power_review_prompt` | `(files: dict[str, list[Path]])` | Build prompts for LLM-powered power management review. | `pipeline/step_handlers/review_power.py:596` |
| `step_review_power` | `(session: PipelineSession)` | Step: 小克 — 低功耗/能效审查. | `pipeline/step_handlers/review_power.py:642` |
| `_extract_shalls` | `(spec_content: str)` | Extract all SHALL/SHOULD/MAY statements from spec content. | `pipeline/step_handlers/review_prd.py:45` |
| `_extract_prd_requirements` | `(prd_content: str)` | Extract requirement-like statements from the PRD artifact. | `pipeline/step_handlers/review_prd.py:129` |
| `_cjk_tokens` | `(text: str)` | Split text into CJK (Chinese/Japanese/Korean) character tokens. | `pipeline/step_handlers/review_prd.py:221` |
| `_check_shall_coverage` | `(spec_shalls: list[dict], prd_requirements: list[dict])` | Check each spec SHALL for corresponding coverage in the PRD. | `pipeline/step_handlers/review_prd.py:231` |
| `_assess_testability` | `(prd_content: str)` | Assess whether the PRD content contains testable acceptance criteria. | `pipeline/step_handlers/review_prd.py:341` |
| `_check_super_analysis_consistency` | `(spec_content: str, super_content: str)` | Check consistency between spec and S.U.P.E.R analysis. | `pipeline/step_handlers/review_prd.py:371` |
| `_assess_product_view` | `(prd_content: str, spec_content: str)` | 产品视角评估（建议性，不阻断）。 | `pipeline/step_handlers/review_prd.py:427` |
| `step_review_prd` | `(session: PipelineSession)` | Step 1.5: 小马 — PRD/Super Analysis quality review. | `pipeline/step_handlers/review_prd.py:515` |
| `_find_rtos_config_files` | `(project_dir: Path)` | Discover RTOS configuration files in the project tree. | `pipeline/step_handlers/review_rtos.py:36` |
| `_parse_config_macro` | `(name: str, content: str, default)` | Extract a #define value from RTOS config headers. | `pipeline/step_handlers/review_rtos.py:77` |
| `_check_max_priorities` | `(content: str, path: Path)` | Check configMAX_PRIORITIES. | `pipeline/step_handlers/review_rtos.py:93` |
| `_check_minimal_stack` | `(content: str, path: Path)` | Check configMINIMAL_STACK_SIZE. | `pipeline/step_handlers/review_rtos.py:141` |
| `_check_interrupt_priority` | `(content: str, path: Path)` | Check interrupt priority grouping and max syscall priority. | `pipeline/step_handlers/review_rtos.py:187` |
| `_check_hooks_and_watchdog` | `(content: str, path: Path)` | Check idle hook, tick hook, and application hook configuration. | `pipeline/step_handlers/review_rtos.py:256` |
| `_check_config_assert` | `(content: str, path: Path)` | Check configASSERT definition (critical for debug builds). | `pipeline/step_handlers/review_rtos.py:323` |
| `_check_stack_overflow_hook` | `(content: str, path: Path)` | Check configCHECK_FOR_STACK_OVERFLOW setting. | `pipeline/step_handlers/review_rtos.py:390` |
| `_check_run_time_stats` | `(content: str, path: Path)` | Check configGENERATE_RUN_TIME_STATS and related timing stats. | `pipeline/step_handlers/review_rtos.py:467` |
| `_check_mutex_and_semaphore` | `(content: str, path: Path)` | Check mutual exclusion and synchronization configuration. | `pipeline/step_handlers/review_rtos.py:510` |
| `_static_rtos_review` | `(project_dir: Path)` | Run all static checks on discovered RTOS config files. | `pipeline/step_handlers/review_rtos.py:572` |
| `_build_rtos_review_prompt` | `(rtos_contents: dict[str, str])` | Build prompts for LLM-powered RTOS config review. | `pipeline/step_handlers/review_rtos.py:611` |
| `step_review_rtos` | `(session: PipelineSession)` | Step: 小克 — RTOS 配置审查。 | `pipeline/step_handlers/review_rtos.py:646` |
| `_find_source_files` | `(project_dir: Path)` | Discover C / assembly source files relevant to stack analysis. | `pipeline/step_handlers/review_stack.py:38` |
| `_find_stack_allocation` | `(source_files: list[Path], project_dir: Path)` | Detect static stack allocations and estimate usage. | `pipeline/step_handlers/review_stack.py:55` |
| `_detect_function_call_depth` | `(source_files: list[Path], project_dir: Path)` | Estimate worst-case function call depth. | `pipeline/step_handlers/review_stack.py:144` |
| `_check_interrupt_stack_budget` | `(source_files: list[Path], project_dir: Path)` | Check interrupt handler stack usage budget. | `pipeline/step_handlers/review_stack.py:236` |
| `_estimate_ram_vs_stack` | `(source_files: list[Path], project_dir: Path)` | Estimate total RAM vs allocated stack to compute utilization ratio. | `pipeline/step_handlers/review_stack.py:288` |
| `_build_stack_report` | `(project_dir: Path)` | Run all stack analysis checks and return unified report. | `pipeline/step_handlers/review_stack.py:387` |
| `_render_stack_report` | `(report: dict)` | Render stack analysis report as markdown. | `pipeline/step_handlers/review_stack.py:429` |
| `step_review_stack` | `(session: PipelineSession)` | Pipeline step handler for stack usage analysis. | `pipeline/step_handlers/review_stack.py:476` |
| `_find_startup_files` | `(project_dir: Path)` | Discover startup assembly / C files in the project tree. | `pipeline/step_handlers/review_startup.py:36` |
| `_check_reset_handler` | `(content: str, path: Path)` | Check for Reset_Handler definition. | `pipeline/step_handlers/review_startup.py:61` |
| `_check_stack_pointer_init` | `(content: str, path: Path)` | Check for initial stack pointer setup. | `pipeline/step_handlers/review_startup.py:88` |
| `_check_bss_zeroing` | `(content: str, path: Path)` | Check for BSS zero-initialization loop. | `pipeline/step_handlers/review_startup.py:120` |
| `_check_data_copy` | `(content: str, path: Path)` | Check for .data section copy from ROM to RAM. | `pipeline/step_handlers/review_startup.py:152` |
| `_check_clock_config` | `(content: str, path: Path)` | Check for system clock / PLL configuration. | `pipeline/step_handlers/review_startup.py:185` |
| `_check_main_call` | `(content: str, path: Path)` | Check that main() is eventually called. | `pipeline/step_handlers/review_startup.py:218` |
| `_check_fpu_enable` | `(content: str, path: Path)` | Check FPU enable (SCB->CPACR) for Cortex-M4/M7/M33. | `pipeline/step_handlers/review_startup.py:247` |
| `_check_system_init_timing` | `(content: str, path: Path)` | Check that SystemInit is called before main() (between BSS clear and main call). | `pipeline/step_handlers/review_startup.py:305` |
| `_check_default_handler_weak` | `(content: str, path: Path)` | Check that ISR handlers have WEAK attribute or ALIAS to Default_Handler. | `pipeline/step_handlers/review_startup.py:389` |
| `_check_cpp_constructors` | `(content: str, path: Path)` | Check for C++ static constructor/destructor support in startup code. | `pipeline/step_handlers/review_startup.py:455` |
| `_check_interrupt_state` | `(content: str, path: Path)` | Check if interrupts are properly managed before main(). | `pipeline/step_handlers/review_startup.py:562` |
| `_static_startup_review` | `(project_dir: Path)` | Run all static checks on discovered startup files. | `pipeline/step_handlers/review_startup.py:603` |
| `_build_startup_review_prompt` | `(startup_contents: dict[str, str])` | Build prompts for LLM-powered startup code review. | `pipeline/step_handlers/review_startup.py:645` |
| `step_review_startup` | `(session: PipelineSession)` | Step: 小克 — 启动代码审查。 | `pipeline/step_handlers/review_startup.py:679` |
| `_find_latest_ci_result` | `(project_dir: Path, layer: int)` | Find and parse the most recent CI layer result JSON. | `pipeline/step_handlers/review_test_coverage.py:48` |
| `_load_coverage_data` | `(project_dir: Path)` | Load coverage JSON data from the standard output location. | `pipeline/step_handlers/review_test_coverage.py:75` |
| `_read_coverage_xml` | `(project_dir: Path)` | Fallback: read coverage.xml if coverage.json is not available. | `pipeline/step_handlers/review_test_coverage.py:103` |
| `_assess_module_risk` | `(ci_result: Optional[dict], coverage_data: Optional[dict])` | Assess risk of uncovered or poorly-tested modules. | `pipeline/step_handlers/review_test_coverage.py:139` |
| `_check_test_regression` | `(ci_result: Optional[dict], previous_ci_result: Optional[dict])` | Check if test failures are new regressions vs previous run. | `pipeline/step_handlers/review_test_coverage.py:194` |
| `_read_coverage_thresholds` | `(project_dir: Path)` | Read coverage thresholds from CI config if available. | `pipeline/step_handlers/review_test_coverage.py:268` |
| `step_review_test_coverage` | `(session: PipelineSession)` | Step CI.2: 小马 — Test coverage result review. | `pipeline/step_handlers/review_test_coverage.py:296` |
| `_find_c_sources` | `(project_dir: Path)` | Discover C/C++ sources under src/ (skip build/artifacts dirs). | `pipeline/step_handlers/review_timing.py:58` |
| `_scan_timing_safety` | `(project_dir: Path)` | 静态扫描时序风险域，返回 findings。 | `pipeline/step_handlers/review_timing.py:74` |
| `_build_timing_review_prompt` | `(project_dir: Path, findings: list[TimingFinding])` | Build the timing safety review prompt. | `pipeline/step_handlers/review_timing.py:158` |
| `step_review_timing` | `(session: PipelineSession)` | Step: 小克 — 时序审查 (embedded-realtime 组)。 | `pipeline/step_handlers/review_timing.py:194` |
| `_find_c_sources` | `(project_dir: Path)` | Discover C/C++ sources under src/ (skip build/artifacts dirs). | `pipeline/step_handlers/review_watchdog.py:57` |
| `_scan_watchdog_safety` | `(project_dir: Path)` | 静态扫描看门狗风险域，返回 findings。 | `pipeline/step_handlers/review_watchdog.py:73` |
| `_build_watchdog_review_prompt` | `(project_dir: Path, findings: list[WatchdogFinding])` | Build the watchdog safety review prompt. | `pipeline/step_handlers/review_watchdog.py:156` |
| `step_review_watchdog` | `(session: PipelineSession)` | Step: 小克 — 看门狗审查 (embedded-realtime 组)。 | `pipeline/step_handlers/review_watchdog.py:192` |
| `_spec_validator_env` | `()` | Build env so the spec-validator subprocess can import yuleosh. | `pipeline/step_handlers/spec.py:29` |
| `step_spec_check` | `(session: PipelineSession)` | Step 0: 小明 — OpenSpec 合规检查 | `pipeline/step_handlers/spec.py:45` |
| `_project_dir` | `(session: PipelineSession)` | Resolve project root (session.project_dir preferred). | `pipeline/step_handlers/spec_cp_review.py:36` |
| `build_cp_review_prompt` | `(cp, spec_path: str)` | Build system/user prompts for CP review. | `pipeline/step_handlers/spec_cp_review.py:44` |
| `step_spec_cp_review` | `(session: PipelineSession)` | Step: 小明 — review pending Change Proposals (OpenSpec evolution). | `pipeline/step_handlers/spec_cp_review.py:79` |
| `_record_step_verdict` | `(session, verdict: str, artifact_paths: list)` | Write step.verdict audit event non-fatally (Q1). | `pipeline/step_handlers/test_c_unit.py:36` |
| `run_c_test_suite` | `(project_dir: str | Path, timeout_build: int, timeout_ctest: int, force_rebuild: bool)` | Run the project's C unit test suite and return a result dict. | `pipeline/step_handlers/test_c_unit.py:77` |
| `step_c_unit_test` | `(session: PipelineSession)` | Step: 小克 — C 单元测试 (Unity/Ceedling). | `pipeline/step_handlers/test_c_unit.py:374` |
| `_parse_unity_counts` | `(output: str)` | Parse Unity test runner output for pass/fail counts. | `pipeline/step_handlers/test_c_unit.py:558` |
| `_parse_ceedling_counts` | `(output: str)` | Parse Ceedling test output for pass/fail counts. | `pipeline/step_handlers/test_c_unit.py:592` |
| `_collect_include_dirs` | `(project_dir: Path)` | Collect project include directories (any dir containing a .h file). | `pipeline/step_handlers/test_c_unit.py:626` |
| `_unit_test_compile_defs` | `(c_test_files: list)` | Return -D flags so the gcc fallback builds unit tests without the app's | `pipeline/step_handlers/test_c_unit.py:650` |
| `_parse_ctest_counts` | `(output: str)` | Parse ctest summary output for pass/fail counts. | `pipeline/step_handlers/test_c_unit.py:671` |
| `_extract_req_ids` | `(text: str)` | Extract requirement IDs referenced in a block. | `pipeline/step_handlers/test_case_gen.py:109` |
| `_scenario_id` | `(index: int, when_text: str)` | Generate a stable short scenario ID. | `pipeline/step_handlers/test_case_gen.py:114` |
| `_derive_title` | `(when: str, given: list[str])` | Derive a readable test case title. | `pipeline/step_handlers/test_case_gen.py:120` |
| `_build_test_case` | `(index: int, scenario: dict[str, Any], req_ids: list[str], spec_path: str)` | — | `pipeline/step_handlers/test_case_gen.py:126` |
| `run_test_case_gen` | `(spec_path: str, session_name: str)` | Parse spec and generate structured test case skeletons. | `pipeline/step_handlers/test_case_gen.py:157` |
| `step_test_case_gen` | `(session: PipelineSession)` | Step: deterministic test case generator from spec scenarios (Q6). | `pipeline/step_handlers/test_case_gen.py:200` |
| `_write_skip` | `(session: PipelineSession, reason: str)` | — | `pipeline/step_handlers/test_case_gen.py:242` |
| `_is_project_root` | `(d)` | Heuristic: does ``d`` look like a project root we can run integration | `pipeline/step_handlers/test_integration.py:31` |
| `_cmake_cache_source_dir` | `(build_dir)` | Extract the project source dir recorded in a build dir's CMakeCache. | `pipeline/step_handlers/test_integration.py:41` |
| `_remove_stale_build_dirs` | `(project_dir)` | Remove build dirs whose CMakeCache points at a different source tree. | `pipeline/step_handlers/test_integration.py:66` |
| `step_integration_test` | `(session: PipelineSession)` | Step: 小克 — 接口/集成测试。 | `pipeline/step_handlers/test_integration.py:95` |
| `_parse_test_counts` | `(output: str, runner: str)` | Parse passed/failed test counts from runner output. | `pipeline/step_handlers/test_integration.py:496` |
| `_record_step_verdict` | `(session, verdict: str, artifact_paths: list)` | Write step.verdict audit event non-fatally (Q1). | `pipeline/step_handlers/test_python_unit.py:42` |
| `_find_python_test_files` | `(project_dir: Path)` | Return all test_*.py / *_test.py files, excluding non-source dirs. | `pipeline/step_handlers/test_python_unit.py:94` |
| `_parse_pytest_counts` | `(output: str)` | Extract passed/failed from pytest short summary line. | `pipeline/step_handlers/test_python_unit.py:109` |
| `_parse_unittest_counts` | `(output: str)` | Extract passed/failed from unittest output. | `pipeline/step_handlers/test_python_unit.py:118` |
| `run_python_test_suite` | `(project_dir: str | Path, timeout: int, python_executable: str | None)` | Discover and run Python unit tests. Returns a result dict. | `pipeline/step_handlers/test_python_unit.py:130` |
| `step_python_unit_test` | `(session: PipelineSession)` | Step: 小克 — Python 单元测试 (pytest / unittest). | `pipeline/step_handlers/test_python_unit.py:257` |
| `_record_step_verdict` | `(session, verdict: str, artifact_paths: list)` | Write step.verdict audit event non-fatally (Q1). | `pipeline/step_handlers/test_qualification.py:39` |
| `_discover_scenarios` | `(spec_path: str)` | Parse the spec file to extract GIVEN/WHEN/THEN scenarios. | `pipeline/step_handlers/test_qualification.py:137` |
| `_discover_test_files` | `(project_dir: Path)` | Discover system-level test files that match scenario names. | `pipeline/step_handlers/test_qualification.py:166` |
| `_check_scenario_coverage` | `(scenarios: list[Scenario], test_files: list[Path])` | Check which scenarios have corresponding test implementations. | `pipeline/step_handlers/test_qualification.py:207` |
| `_find_c_test_binary` | `(test_file: Path, project_dir: Path)` | Find the compiled binary for a C test source file. | `pipeline/step_handlers/test_qualification.py:281` |
| `_try_compile_c_test` | `(test_file: Path, project_dir: Path)` | 即时编译 fallback —— 构建系统无关的最后一环。 | `pipeline/step_handlers/test_qualification.py:356` |
| `_junit_report_path` | `(project_dir: Path, test_file: Path)` | JUnit XML 输出路径 — 放 .yuleosh/reports/junit-<testfile>.xml。 | `pipeline/step_handlers/test_qualification.py:417` |
| `_run_system_tests` | `(test_files: list[Path], project_dir: Path, timeout_s: int)` | Execute system-level test files and collect results. | `pipeline/step_handlers/test_qualification.py:428` |
| `_build_qualification_report` | `(spec_path: str, project_dir: Path, scenarios: list[Scenario], coverage: dict, test_results: dict)` | Build the full qualification test report. | `pipeline/step_handlers/test_qualification.py:603` |
| `step_test_qualification` | `(session: PipelineSession)` | Step: 小明 — 合格性测试 (SWE.6). | `pipeline/step_handlers/test_qualification.py:669` |
| `step_verify_loop` | `(session: PipelineSession)` | Step: verify-loop — 自测 + Codex 外部验证 + 自测结果审查（合并）。 | `pipeline/step_handlers/verify_loop.py:39` |
| `_synthesize_unity_test_cases` | `(test_source_files: list[Path])` | Synthesize test_case_results from C test source function names. | `pipeline/step_handlers/review_selftest/core.py:40` |
| `_load_prev_selftest_review` | `(session_dir: str | Path)` | Load the previous selftest-review.json for trend comparison. | `pipeline/step_handlers/review_selftest/core.py:116` |
| `_compute_selftest_regression` | `(current_review: dict, prev_review: dict | None)` | Compute regression analysis between current and previous build (R3-P0-5). | `pipeline/step_handlers/review_selftest/core.py:132` |
| `_get_ci_environ` | `()` | Extract CI environment variables for build_id, commit_sha, branch. | `pipeline/step_handlers/review_selftest/core.py:191` |
| `_get_tool_version` | `(tool_name: str)` | Try to get tool version string by running <tool_name> --version. | `pipeline/step_handlers/review_selftest/core.py:200` |
| `_collect_environment_info` | `()` | Collect environment information for the test run. | `pipeline/step_handlers/review_selftest/core.py:218` |
| `_generate_xunit_compatible` | `(test_case_results: list[dict])` | Generate a JUnit XML compatible string from test case results. | `pipeline/step_handlers/review_selftest/core.py:240` |
| `_get_run_history_path` | `()` | Get the path to the selftest-history.json file. | `pipeline/step_handlers/review_selftest/core.py:317` |
| `_load_run_history` | `()` | Load past test execution run history from disk. | `pipeline/step_handlers/review_selftest/core.py:323` |
| `_save_run_history` | `(current_run: dict, existing_history: list[dict] | None)` | Append current run to history and save to disk. | `pipeline/step_handlers/review_selftest/core.py:348` |
| `_discover_junit_xml` | `(session: PipelineSession)` | Discover JUnit XML report files in session and project directories. | `pipeline/step_handlers/review_selftest/core.py:391` |
| `_discover_coverage_files` | `(session: PipelineSession)` | Discover lcov coverage.info files in session and project directories. | `pipeline/step_handlers/review_selftest/core.py:434` |
| `_parse_lcov_coverage` | `(lcov_path: Path)` | Parse lcov coverage.info file and return structured coverage data. | `pipeline/step_handlers/review_selftest/core.py:462` |
| `_extract_shall_statements` | `(spec_content: str)` | Extract SHALL/MAY/SHOULD statements from spec content with context. | `pipeline/step_handlers/review_selftest/core.py:615` |
| `_build_selftest_review_prompt` | `(spec_content: str, spec_name: str, self_test_content: str, shall_statements: list[dict], test_plan_content: str, test_case_results: list[dict] | None, auto_shall_coverage: tuple[set[int], dict[str, list[str]]] | None)` | Build prompts for the LLM-powered self-test results review. | `pipeline/step_handlers/review_selftest/core.py:654` |
| `_generate_selftest_markdown` | `(review: dict)` | Generate a structured Markdown self-test report from the enhanced JSON data. | `pipeline/step_handlers/review_selftest/core.py:784` |
| `step_review_selftest` | `(session: PipelineSession)` | Step: 小克 — 自测结果审查（增强版）。 | `pipeline/step_handlers/review_selftest/core.py:1101` |
| `_find_bsp_files` | `(project_dir: Path)` | Discover BSP-related files grouped by category. | `pipeline/step_handlers/review_bsp/core.py:35` |
| `_check_pin_mux_gpio` | `(content: str, path: Path)` | Check GPIO pin configuration for correctness. | `pipeline/step_handlers/review_bsp/core.py:132` |
| `_check_pin_mux_conflicts` | `(content: str, path: Path)` | Check for potential pin mux conflicts by analyzing GPIO_PIN_x constants. | `pipeline/step_handlers/review_bsp/core.py:206` |
| `_check_clock_hse` | `(content: str, path: Path)` | Check HSE/LSE configuration. | `pipeline/step_handlers/review_bsp/core.py:250` |
| `_check_clock_pll` | `(content: str, path: Path)` | Check PLL configuration parameters. | `pipeline/step_handlers/review_bsp/core.py:309` |
| `_check_system_clock_frequency` | `(content: str, path: Path)` | Check SystemCoreClock or HCLK frequency setting. | `pipeline/step_handlers/review_bsp/core.py:410` |
| `_check_alloca_usage` | `(content: str, path: Path)` | Detect alloca() usage — stack-allocated memory at runtime. | `pipeline/step_handlers/review_bsp/core.py:476` |
| `_check_vla_usage` | `(content: str, path: Path)` | Detect Variable-Length Arrays (VLA) in C code. | `pipeline/step_handlers/review_bsp/core.py:513` |
| `_check_dynamic_allocation` | `(content: str, path: Path)` | Detect dynamic memory allocation (malloc/calloc/realloc/free) in BSP code. | `pipeline/step_handlers/review_bsp/core.py:570` |
| `_check_runtime_allocation_integrity` | `(files: dict[str, list[Path]])` | Run all runtime allocation checks across all BSP files. | `pipeline/step_handlers/review_bsp/core.py:639` |
| `_check_peripheral_init_order` | `(files: dict[str, list[Path]])` | Check HAL initialization order across peripheral config files. | `pipeline/step_handlers/review_bsp/core.py:692` |
| `_check_peripheral_conflict` | `(files: dict[str, list[Path]])` | Check for peripheral conflicts (shared pins, resource contention). | `pipeline/step_handlers/review_bsp/core.py:820` |
| `_check_hal_api_consistency` | `(files: dict[str, list[Path]])` | Check HAL API usage for consistency across the BSP. | `pipeline/step_handlers/review_bsp/core.py:873` |
| `_check_dma_config` | `(files: dict[str, list[Path]])` | Check DMA configuration for correctness. | `pipeline/step_handlers/review_bsp/core.py:962` |
| `_static_bsp_review` | `(project_dir: Path)` | Run all static checks on discovered BSP files. | `pipeline/step_handlers/review_bsp/core.py:1058` |
| `_build_bsp_review_prompt` | `(files: dict[str, list[Path]])` | Build prompts for LLM-powered BSP review. | `pipeline/step_handlers/review_bsp/core.py:1125` |
| `step_review_bsp` | `(session: PipelineSession)` | Step: 小克 — BSP 板级支持包验证。 | `pipeline/step_handlers/review_bsp/core.py:1167` |
| `_build_selfcheck_prompt` | `(llm_output: str, repo_facts_text: str, artifact_key: str)` | Return (system_prompt, user_prompt) for the self-check LLM call. | `pipeline/step_handlers/review_selfcheck/handler.py:78` |
| `_parse_selfcheck_result` | `(raw: str)` | Extract JSON from the LLM self-check response. | `pipeline/step_handlers/review_selfcheck/handler.py:112` |
| `_downgrade_unsupported` | `(result: dict[str, Any])` | H2-2d: annotate low/unsupported items; escalate verdict if needed. | `pipeline/step_handlers/review_selfcheck/handler.py:135` |
| `step_review_selfcheck` | `(session: PipelineSession)` | Self-check pass on the most recent LLM step output (H2-2). | `pipeline/step_handlers/review_selfcheck/handler.py:160` |
| `_write_result` | `(session: PipelineSession, project_dir: Path, result: dict[str, Any], artifact_key: str)` | Write the selfcheck result JSON and register the artifact. | `pipeline/step_handlers/review_selfcheck/handler.py:254` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `TestResult` | `()` | 测试执行结果 (统一形态, 跨 runner 可比)。 | `pipeline/guardrail.py:234` |
| `TestRunner` | `(Protocol)` | 测试执行协议 — 任何测试后端实现该接口即可被护栏复用。 | `pipeline/guardrail.py:247` |
| `CCTestRunner` | `()` | C 项目测试 runner — 包装 run_c_test_suite (ctest/unity/ceedling/gcc)。 | `pipeline/guardrail.py:261` |
| `IntegrationTestRunner` | `()` | 接口/集成测试 runner — pytest -m integration / go -tags=integration。 | `pipeline/guardrail.py:294` |
| `PytestRunner` | `()` | Python 项目测试 runner — pytest tests/。 | `pipeline/guardrail.py:382` |
| `GoRunner` | `()` | Go 项目测试 runner — go test ./...。 | `pipeline/guardrail.py:429` |
| `PipelineKnowledgeConfig` | `()` | Per-project injection switches (from pipeline-knowledge.yaml). | `pipeline/knowledge_injection.py:52` |
| `RunResult` | `()` | Minimal ``subprocess.CompletedProcess``-compatible result. | `pipeline/safe_run.py:112` |
| `PipelineStepError` | `(RuntimeError)` | Raised when a pipeline step encounters a hard failure. | `pipeline/session.py:52` |
| `PipelineSession` | `()` | Represents a running pipeline session. | `pipeline/session.py:90` |
| `GroundingViolation` | `()` | A single unverified reference found in LLM output. | `pipeline/source_grounding.py:55` |
| `GroundingReport` | `()` | Result of a grounding check on one LLM output. | `pipeline/source_grounding.py:64` |
| `SourceGroundingChecker` | `()` | Validate LLM output text against known-good repo facts. | `pipeline/source_grounding.py:92` |
| `BaselineMetrics` | `()` | Pipeline run metrics snapshot for regression comparison. | `pipeline/step_cache.py:445` |
| `SuperAnalysisStep` | `(PipelineStep)` | Step 1: 小明 — S.U.P.E.R analysis powered by real LLM. | `pipeline/step_classes.py:131` |
| `PrdStep` | `(PipelineStep)` | Step 2: Hermes — AI-powered PRD generation from spec. | `pipeline/step_classes.py:157` |
| `ArchitectureStep` | `(PipelineStep)` | Step 4: Claude — AI-powered architecture design. | `pipeline/step_classes.py:187` |
| `DevelopmentStep` | `(PipelineStep)` | Step 5: Claude — AI-powered development. | `pipeline/step_classes.py:276` |
| `TestPlanningStep` | `(PipelineStep)` | Step 6: Claude — AI-powered test planning. | `pipeline/step_classes.py:472` |
| `HermesReviewStep` | `(PipelineStep)` | Step 8: Hermes — AI-powered code review. | `pipeline/step_classes.py:504` |
| `PipelineStep` | `()` | Abstract base for a single pipeline step. | `pipeline/steps.py:48` |
| `FaultInjectTestResult` | `()` | Result of a single fault injection test. | `pipeline/step_handlers/fault_inject.py:110` |
| `FaultInjectReport` | `()` | Aggregated report from all fault injection tests. | `pipeline/step_handlers/fault_inject.py:122` |
| `FaultInjectStage` | `()` | yuleOSH pipeline stage for running Generic Fault Injection tests. | `pipeline/step_handlers/fault_inject.py:142` |
| `CheckpointManager` | `()` | 管理 pipeline step 的检查点 (checkpoint)。 | `pipeline/step_handlers/handler_base.py:100` |
| `BaseHandler` | `(ABC)` | Pipeline step handler 抽象基类。 | `pipeline/step_handlers/handler_base.py:150` |
| `CriticalViolation` | `()` | 一个关键安全违例。 | `pipeline/step_handlers/review_critical_safety.py:331` |
| `CriticalSafetyScanner` | `()` | 关键安全异常扫描器。 | `pipeline/step_handlers/review_critical_safety.py:354` |
| `_ScenarioParser` | `()` | Parse GIVEN/WHEN/THEN blocks from a spec text. | `pipeline/step_handlers/test_case_gen.py:47` |
| `QemuTestHandler` | `(BaseHandler)` | Pipeline step handler for running QEMU-based firmware tests. | `pipeline/step_handlers/test_qemu.py:66` |
| `Scenario` | `()` | A GIVEN/WHEN/THEN scenario parsed from the spec. | `pipeline/step_handlers/test_qualification.py:81` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `TestRunner.run` | `(self, project_dir: str | Path, force_rebuild: bool)` | — | `pipeline/guardrail.py:257` |
| `CCTestRunner.__init__` | `(self, timeout_build: int, timeout_ctest: int)` | — | `pipeline/guardrail.py:266` |
| `CCTestRunner.run` | `(self, project_dir: str | Path, force_rebuild: bool)` | — | `pipeline/guardrail.py:270` |
| `IntegrationTestRunner.run` | `(self, project_dir: str | Path, force_rebuild: bool)` | — | `pipeline/guardrail.py:303` |
| `PytestRunner.__init__` | `(self, timeout: int, extra_args: list[str] | None)` | — | `pipeline/guardrail.py:391` |
| `PytestRunner.run` | `(self, project_dir: str | Path, force_rebuild: bool)` | — | `pipeline/guardrail.py:395` |
| `GoRunner.__init__` | `(self, timeout: int, tags: str | None)` | — | `pipeline/guardrail.py:437` |
| `GoRunner.run` | `(self, project_dir: str | Path, force_rebuild: bool)` | — | `pipeline/guardrail.py:441` |
| `PipelineKnowledgeConfig.from_dict` | `(cls, data: dict | None)` | Build a config from a parsed YAML dict (missing keys → defaults). | `pipeline/knowledge_injection.py:69` |
| `RunResult.__init__` | `(self, returncode, stdout, stderr, args)` | — | `pipeline/safe_run.py:120` |
| `RunResult.check_returncode` | `(self)` | — | `pipeline/safe_run.py:129` |
| `PipelineSession.__init__` | `(self, name: str, spec_path: str, llm_client: Callable | None, agent_constraints: str | None, development_mode: str | None, config: dict | None, org_id: int, user_id: int | None, user_email: str | None, run_id: str | None)` | — | `pipeline/session.py:93` |
| `PipelineSession.add_step` | `(self, step_name: str, agent: str, action: str)` | Add a new step to the pipeline and return it. | `pipeline/session.py:205` |
| `PipelineSession.start_step` | `(self, step_idx: int)` | Mark a step as running and record the start timestamp. | `pipeline/session.py:221` |
| `PipelineSession.complete_step` | `(self, step_idx: int, output_path: str)` | Mark a step as completed with its output path. | `pipeline/session.py:231` |
| `PipelineSession.fail_step` | `(self, step_idx: int, error: str)` | Fail a step, record the error, and set session status to failed. | `pipeline/session.py:241` |
| `PipelineSession.set_artifact` | `(self, key: str, path: str)` | Register a generated artifact and persist session state. | `pipeline/session.py:252` |
| `PipelineSession.add_token_usage` | `(self, step_key: str, usage: dict)` | Thread-safe token usage accumulation (D2 parallel groups). | `pipeline/session.py:272` |
| `PipelineSession.to_dict` | `(self)` | Serialize session to a dictionary for storage. | `pipeline/session.py:303` |
| `GroundingReport.clean` | `(self)` | — | `pipeline/source_grounding.py:73` |
| `GroundingReport.to_dict` | `(self)` | — | `pipeline/source_grounding.py:76` |
| `SourceGroundingChecker.__init__` | `(self, source_files: list[dict[str, Any]] | None, known_function_names: set[str] | None, known_req_ids: set[str] | None)` | — | `pipeline/source_grounding.py:102` |
| `SourceGroundingChecker.check` | `(self, text: str)` | Run all enabled grounding checks on ``text``. | `pipeline/source_grounding.py:123` |
| `BaselineMetrics.to_dict` | `(self)` | — | `pipeline/step_cache.py:456` |
| `BaselineMetrics.from_dict` | `(cls, d: dict)` | — | `pipeline/step_cache.py:468` |
| `SuperAnalysisStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:141` |
| `PrdStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:170` |
| `ArchitectureStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:198` |
| `ArchitectureStep.process_result` | `(self, session, content, result)` | — | `pipeline/step_classes.py:268` |
| `DevelopmentStep.__init__` | `(self, mode: str, max_retries: int)` | — | `pipeline/step_classes.py:297` |
| `DevelopmentStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:311` |
| `TestPlanningStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:486` |
| `HermesReviewStep.build_prompts` | `(self, session, spec_content, parsed, artifacts)` | — | `pipeline/step_classes.py:521` |
| `HermesReviewStep.process_result` | `(self, session, content, result)` | — | `pipeline/step_classes.py:561` |
| `PipelineStep.build_prompts` | `(self, session: PipelineSession, spec_content: str, parsed: dict, artifacts: dict[str, str])` | Return ``(system_prompt, user_prompt)``. | `pipeline/steps.py:67` |
| `PipelineStep.process_result` | `(self, session: PipelineSession, content: str, result: dict)` | Post-process LLM output before writing to file. | `pipeline/steps.py:115` |
| `FaultInjectReport.to_dict` | `(self)` | — | `pipeline/step_handlers/fault_inject.py:134` |
| `FaultInjectStage.__init__` | `(self, build_dir: Optional[str], target: Optional[str], serial_port: Optional[str], baud_rate: int, injector_type: str, test_categories: Optional[list[str]])` | Args: | `pipeline/step_handlers/fault_inject.py:153` |
| `FaultInjectStage.build_test_firmware` | `(self, project_root: str)` | Build the firmware with FAULT_INJECT_TESTS=ON. | `pipeline/step_handlers/fault_inject.py:177` |
| `FaultInjectStage.connect_target` | `(self)` | Verify target connection (serial port or UDS). | `pipeline/step_handlers/fault_inject.py:240` |
| `FaultInjectStage.run_tests` | `(self)` | Run all configured fault injection tests. | `pipeline/step_handlers/fault_inject.py:372` |
| `FaultInjectStage.generate_report` | `(self, report: FaultInjectReport, output_path: str)` | Generate a human-readable Markdown report. | `pipeline/step_handlers/fault_inject.py:414` |
| `CheckpointManager.__init__` | `(self, session_dir: Path, step_name: str, ttl_seconds: int)` | — | `pipeline/step_handlers/handler_base.py:106` |
| `CheckpointManager.exists` | `(self)` | 检查点文件存在且未过期？ | `pipeline/step_handlers/handler_base.py:111` |
| `CheckpointManager.save` | `(self, metadata: dict | None)` | 保存检查点。 | `pipeline/step_handlers/handler_base.py:121` |
| `CheckpointManager.load` | `(self)` | 读取检查点内容。 | `pipeline/step_handlers/handler_base.py:131` |
| `CheckpointManager.clear` | `(self)` | 清除检查点。 | `pipeline/step_handlers/handler_base.py:140` |
| `BaseHandler.pre_check` | `(self, session: PipelineSession)` | 前置条件验证。返回 True=继续, 其他=跳过。 | `pipeline/step_handlers/handler_base.py:260` |
| `BaseHandler.execute` | `(self, session: PipelineSession)` | 核心业务逻辑。返回输出文件路径字符串。 | `pipeline/step_handlers/handler_base.py:265` |
| `BaseHandler.post_write` | `(self, session: PipelineSession, result_path: str)` | 结果写入后的后处理。返回最终路径。 | `pipeline/step_handlers/handler_base.py:269` |
| `BaseHandler.build_output_path` | `(self, session: PipelineSession)` | 生成输出文件路径。 | `pipeline/step_handlers/handler_base.py:273` |
| `BaseHandler.record_step_verdict` | `(self, session: 'PipelineSession', verdict: str, artifact_paths: 'list[str] | None')` | Write a step.verdict audit event into the SHA-256 hash chain (Q1). | `pipeline/step_handlers/handler_base.py:300` |
| `BaseHandler.should_skip` | `(self, session: PipelineSession)` | 跳过条件。返回 True 则跳过执行。 | `pipeline/step_handlers/handler_base.py:358` |
| `BaseHandler.get_llm_prompts` | `(self, session: PipelineSession)` | 构建 LLM prompt。返回 (system_prompt, user_prompt) 或 None。 | `pipeline/step_handlers/handler_base.py:362` |
| `BaseHandler.track_llm_usage` | `(self, session: PipelineSession, result: dict, step_label: str)` | 记录 LLM token 用量到 session。 | `pipeline/step_handlers/handler_base.py:366` |
| `BaseHandler.call_llm` | `(self, session: PipelineSession, **kwargs)` | 调用 LLM 并跟踪用量。 | `pipeline/step_handlers/handler_base.py:373` |
| `BaseHandler.write_output` | `(self, session: PipelineSession, content: Any, filename: str)` | 写入 step 输出到文件。 | `pipeline/step_handlers/handler_base.py:384` |
| `BaseHandler.report_status` | `(self, session: PipelineSession, status: str, findings: list | None, summary: str, extra: dict | None)` | 生成标准化的 step status report JSON。 | `pipeline/step_handlers/handler_base.py:397` |
| `CriticalViolation.__init__` | `(self, rule_id: str, file: str, line: int, message: str, snippet: str, fix_suggestion: str)` | — | `pipeline/step_handlers/review_critical_safety.py:333` |
| `CriticalViolation.to_dict` | `(self)` | — | `pipeline/step_handlers/review_critical_safety.py:343` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `BUILD_ID` | _(见源码)_ |
| `DEEPSEEK_API_KEY` | _(见源码)_ |
| `GIT_BRANCH` | _(见源码)_ |
| `GIT_COMMIT` | _(见源码)_ |
| `LLM_API_KEY` | _(见源码)_ |
| `LLM_MODEL` | _(见源码)_ |
| `OPENAI_API_KEY` | _(见源码)_ |
| `OSH_BEHAVIOR_GUARD` | _(见源码)_ |
| `OSH_DEVELOPMENT_MODE` | _(见源码)_ |
| `OSH_GUARD_PROTECT_SRC` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |
| `OSH_KEEP_VERIFICATION_CACHE` | _(见源码)_ |
| `OSH_NA_GATES` | _(见源码)_ |
| `OSH_NO_CACHE` | _(见源码)_ |
| `OSH_SESSIONS_DIR` | _(见源码)_ |
| `PYTEST_CURRENT_TEST` | _(见源码)_ |
| `YULEOSH_AUDIT_ROOT` | _(见源码)_ |
| `YULEOSH_CLAUDE_MAX_TURNS` | _(见源码)_ |
| `YULEOSH_CLAUDE_TIMEOUT` | _(见源码)_ |
| `YULEOSH_CODEGEN_LLM_TIMEOUT` | _(见源码)_ |
| `YULEOSH_CODEX_TIMEOUT` | _(见源码)_ |
| `YULEOSH_LLM_GATEWAY_STEPS` | _(见源码)_ |
| `YULEOSH_LLM_LOCAL_MODEL` | _(见源码)_ |
| `YULEOSH_PIPELINE_SERIAL` | _(见源码)_ |
| `YULEOSH_PIPELINE_TOKEN_BUDGET` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.pipeline import <公共符号>
# 详见 docs/modules/pipeline.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 32 处生产引用(Grep `yuleosh.pipeline` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/pipeline/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
