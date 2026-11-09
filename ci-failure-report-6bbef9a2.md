# CI 失败用例清单 — yuleOSH CI / test (3.12)

- 运行：`42502700694`，job `128798981290`，提交 `6bbef9a2`
- 结果：**50 failed / 73 errors / 14617 passed / 84 skipped**，耗时 8m24s
- 结论：主因是测试隔离缺陷（`session._store` 被误删），**非本次合并引入**；main 自 `2026-10-17` 起 CI 持续红色

## 一、失败分组

| 组 | 用例数 | 表现 | 根因 |
| --- | --- | --- | --- |
| A. `_store` 丢失 | 22 failed + 73 errors | `NameError: name '_store' is not defined`（session.py:297）；setup 阶段 `AttributeError: module 'yuleosh.pipeline.session' has no attribute '_store'` | `tests/conftest.py` 的 `_isolate_process_state` teardown 执行 `delattr(session, "_store")`，但该符号是 `session.py` 导入期创建的单例，删除后无人重建 |
| B. `SystemExit: 1` | 13 | `run_pipeline` 进程退出 | 疑似与 A 同源（session 持久化失败导致管线中止），待单独确认 |
| C. 向量库 | 6 | `DID NOT RAISE` / `assert False` / `IndexError` | `test_kb_vector_ei_m3c.py` 依赖 faiss/嵌入模型，CI 环境缺失或降级 |
| D. 零散 | 9 | 断言不符 | 见下方完整列表 |

## 二、A 组证据链

```
src/yuleosh/pipeline/session.py:297   if _store:   → NameError
tests/conftest.py:326-334             delattr(holder, "_store")  ← 每个测试 teardown 都执行
```

`session.py:34-45` 在模块导入时创建 `_store`（失败则置 `None`），运行期没有任何惰性重建逻辑，因此第一个测试结束后该全局即永久缺失。

## 三、50 个 FAILED 用例

### `_store` NameError / AttributeError（22）
- tests/test_coverage_phase9_billing_user.py::TestSessionRunId::test_save_persists_run_dir
- tests/test_coverage_phase9_billing_user.py::TestStatusPipelineCompat::test_status_pipeline_matches_by_json_name
- tests/test_gate_status_aggregation.py::TestSessionMockProvenance::test_mock_mode_survives_persistence
- tests/test_gate_status_aggregation.py::TestSessionMockProvenance::test_real_run_defaults_to_false
- tests/test_pipeline_extended.py::TestPipelineSession::test_session_fail_step
- tests/test_pipeline_extended.py::TestPipelineSession::test_session_start_and_complete_step
- tests/test_pipeline_session.py::TestPipelineSessionIntegration::test_lifecycle_equality
- tests/test_pipeline_session.py::TestPipelineSessionPersistence::test_calling_save_persist_multiple_times_overwrites
- tests/test_pipeline_session.py::TestPipelineSessionPersistence::test_save_writes_session_json
- tests/test_pipeline_session.py::TestPipelineSessionPersistence::test_store_failure_is_non_fatal
- tests/test_pipeline_session.py::TestPipelineSessionPersistence::test_to_dict_with_steps
- tests/test_pipeline_session.py::TestPipelineSessionSteps::test_complete_step_marks_completed
- tests/test_pipeline_session.py::TestPipelineSessionSteps::test_fail_step_multiple_errors
- tests/test_pipeline_session.py::TestPipelineSessionSteps::test_fail_step_records_error
- tests/test_pipeline_session.py::TestPipelineSessionSteps::test_start_step_marks_running
- tests/test_pipeline_session_ext.py::TestPipelineSession::test_complete_step
- tests/test_pipeline_session_ext.py::TestPipelineSession::test_fail_step
- tests/test_pipeline_session_ext.py::TestPipelineSession::test_save_to_disk
- tests/test_pipeline_session_ext.py::TestPipelineSession::test_start_step
- tests/test_sessions_root_isolation.py::TestNoRepoLeak::test_creating_a_session_leaves_repo_untouched
- tests/test_step_handlers_review_deep.py::TestFinalReportHappyPath::test_happy_path
- tests/test_step_handlers_review_deep.py::TestFinalReportLLMFallback::test_llm_failure_fallback

### SystemExit: 1（13）
- tests/test_pipeline_errors.py::test_pipeline_llm_failure_stops_pipeline
- tests/test_pipeline_errors.py::test_pipelinesteperror_not_swallowed_by_fallback
- tests/test_pipeline_extended.py::TestPipelineOrchestrator::test_pipeline_error_handling
- tests/test_pipeline_extended.py::TestPipelineOrchestrator::test_pipeline_orchestrator_main_status
- tests/test_pipeline_extended.py::TestPipelineOrchestrator::test_run_pipeline_mock_mode
- tests/test_pipeline_extended.py::TestPipelineOrchestrator::test_run_pipeline_with_name
- tests/test_pipeline_extended.py::TestPipelineOrchestrator::test_status_pipeline_with_session
- tests/test_pipeline_resume_evidence_chain.py::TestResumeRestoresOnlyPriorArtifacts::test_resume_from_step_11_excludes_later_artifacts
- tests/test_pipeline_resume_evidence_chain.py::TestResumeRestoresOnlyPriorArtifacts::test_resume_from_step_11_excludes_self_test
- tests/test_pipeline_step_cache.py::TestRunStartPurgeIntegration::test_reusable_step_still_reuses_cache
- tests/test_pipeline_step_cache.py::TestRunStartPurgeIntegration::test_verification_step_reruns_despite_cached_artifact
- tests/test_pipeline_terminal_status.py::test_pipeline_blocked_step_marks_run_failed
- tests/test_pipeline_terminal_status.py::test_pipeline_failed_step_marks_run_failed_and_persists

### 向量库（6）
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_dim_guard
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_load_extension
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_search_content_hash_filter
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_search_nearest
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_upsert_and_count
- tests/test_kb_vector_ei_m3c.py::TestVectorStore::test_upsert_idempotent

### 其他（9）
- tests/test_agent_constraints.py::TestLLMContextInjection::test_call_llm_no_constraints — 上下文断言多出 "Fix examples:"
- tests/test_api_router_ext.py::TestRouter::test_routes_contains_all_resources — 资源集合不一致
- tests/test_pipeline_deploy_anchor.py::TestFindPreviousSession::test_finds_latest_same_spec — assert None is not None
- tests/test_pipeline_review_misra_ci.py::TestCheckReportStaleness::test_stale_report_with_required_violations_stays_failed — AssertionError: passed
- tests/test_pipeline_review_misra_ci.py::TestCheckReportStaleness::test_stale_when_report_older_than_src — AssertionError: passed
- tests/test_step_handlers_review_deep.py::TestFinalReportWriteErrorAfterTemplate::test_write_error_after_template — NameError: _store
- tests/test_test_qualification.py::TestStepTestQualification::test_pipeline_error_propagated — DID NOT RAISE
- tests/test_v380_a3_routes_unify.py::TestA3BodyAndAuth::test_auth_equiv_require_auth — assert None is not None
- tests/test_v380_a5_cli_split.py::TestA5NoSysPath::test_no_sys_path_insert_in_tests — conftest.py:28 残留 sys.path.insert

## 四、73 个 ERROR（全部为 setup 阶段 AttributeError: _store）

| 文件 | 数量 |
| --- | --- |
| tests/test_coverage_phase7_orchestrator_o3.py | 52 |
| tests/test_d2_parallel_groups.py | 8 |
| tests/test_agent_pipeline_inline.py | 8 |
| tests/test_gate_policy.py | 5 |

## 五、修复建议

1. `tests/conftest.py:326-334`：不再对 `yuleosh.pipeline.session` 删除 `_store`（导入期单例，删除不可逆）；KG store 的清理保留。
2. C 组：CI 安装 faiss 或对该文件加 `pytest.importorskip`。
3. 修完后重跑受影响的 5 个文件验证，再推一次 CI 全量。
