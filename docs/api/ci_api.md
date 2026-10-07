# 持续集成 (`ci`) API 参考

> 代码根:`src/yuleosh/ci/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`ci` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/ci.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .ci import handle_ci` |
| `"ci": handle_ci,` |
| `"type": "full" | "ci",    # Pipeline type (default: full)` |
| `if pipeline_type not in ("full", "full_pipeline", "ci"):` |
| `ci_dir = Path(OSH_HOME) / ".osh" / "ci"` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_ensure_trace_dir` | `(project_dir: str)` | Ensure the trace file directory exists. | `ci/agent_traceability.py:44` |
| `_get_git_commit` | `(project_dir: str)` | Get the full git commit hash. | `ci/agent_traceability.py:51` |
| `_generate_review_id` | `(layer: int)` | Generate a unique review session ID. | `ci/agent_traceability.py:64` |
| `record_review` | `(project_dir: str, review_type: str, findings: Optional[list[dict]], commit: str, build_id: str, agent_name: str, extra: Optional[dict[str, Any]])` | Record an agent review session with bidirectional traceability. | `ci/agent_traceability.py:79` |
| `get_reviews_for_commit` | `(project_dir: str, commit: str, limit: int)` | Find all review sessions associated with a commit (G-47 §19.1). | `ci/agent_traceability.py:175` |
| `get_commits_for_review` | `(project_dir: str, review_id: str)` | Find all entries for a specific review session (G-47 §19.1). | `ci/agent_traceability.py:220` |
| `get_findings_for_file` | `(project_dir: str, file_path: str, limit: int)` | Find all review findings targeting a specific file (G-47 §19.2). | `ci/agent_traceability.py:259` |
| `get_reviews_by_build` | `(project_dir: str, build_id: str)` | Find all review sessions associated with a build (G-47 §19.3). | `ci/agent_traceability.py:319` |
| `show_traceability` | `(project_dir: str, as_json: bool, limit: int)` | Display recent traceability entries as formatted table or JSON. | `ci/agent_traceability.py:364` |
| `validate_traceability_file` | `(project_dir: str)` | Validate the traceability JSONL file integrity. | `ci/agent_traceability.py:430` |
| `_cli_main` | `()` | Simple CLI for agent traceability operations. | `ci/agent_traceability.py:461` |
| `_ensure_meta_dir` | `(project_dir: str)` | Ensure the metadata file directory exists. | `ci/build_metadata.py:65` |
| `_get_git_commit` | `(project_dir: str)` | Get the full git commit hash. | `ci/build_metadata.py:72` |
| `_get_git_files_changed` | `(project_dir: str)` | Count files changed in the most recent commit. | `ci/build_metadata.py:85` |
| `_get_tool_versions` | `(project_dir: str)` | Capture versions of key tools used in the build pipeline. | `ci/build_metadata.py:100` |
| `_generate_build_id` | `(project_dir: str)` | Generate a unique, sortable build ID. | `ci/build_metadata.py:137` |
| `_validate_fields` | `(entry: dict)` | Validate that all required fields are present and non-empty. | `ci/build_metadata.py:146` |
| `record_build` | `(project_dir: str, commit: str, status: str, layer: int, extra_fields: Optional[dict[str, Any]])` | Record build metadata entry (G-48 §20.1). | `ci/build_metadata.py:171` |
| `get_build_metadata` | `(project_dir: str, build_id: Optional[str], limit: int, layer: Optional[int])` | Retrieve build metadata entries (G-48 §20.3). | `ci/build_metadata.py:240` |
| `get_build_chain` | `(project_dir: str, commit: str)` | Get all build metadata entries for a specific commit (G-48 §20.4). | `ci/build_metadata.py:288` |
| `validate_metadata_integrity` | `(project_dir: str)` | Validate build metadata file integrity (G-48 §20.5). | `ci/build_metadata.py:328` |
| `show_build_metadata` | `(project_dir: str, as_json: bool, limit: int)` | Display build metadata as formatted table or JSON. | `ci/build_metadata.py:397` |
| `_cli_main` | `()` | Simple CLI for build-metadata operations. | `ci/build_metadata.py:448` |
| `validate_misra_profiles` | `(cfg: CiConfig)` | Validate MISRA profile configuration. | `ci/config.py:258` |
| `load_ci_config` | `(project_dir: Optional[str], config_path: Optional[str])` | Load CI configuration from ``.yuleosh/ci-config.yaml``. | `ci/config.py:307` |
| `_parse_ci_config` | `(raw: dict | None)` | Parse raw dict into a CiConfig dataclass. | `ci/config.py:369` |
| `_get_ci_config` | `(project_dir: str)` | Load and cache CI configuration from ``.yuleosh/ci-config.yaml``. | `ci/config.py:617` |
| `_clear_ci_config_cache` | `()` | Clear the CI config cache (used in tests). | `ci/config.py:625` |
| `load_ci_profile_into_config` | `(cfg: 'CiConfig', profile_name: str)` | Merge a named CI environment profile over the loaded config. | `ci/config.py:635` |
| `is_strict` | `()` | Check if CI is running in strict mode (CI_STRICT=1). | `ci/config.py:697` |
| `is_misra_fail_fast` | `()` | Check if MISRA_FAIL_FAST is active. | `ci/config.py:706` |
| `_deviations_to_yaml_dicts` | `(deviations: list[MisraDeviation])` | Convert MisraDeviation list to YAML-serializable dict list. | `ci/config.py:736` |
| `update_deviation_status` | `(project_dir: str, rule_id: str, file_pattern: str, new_status: str)` | Update the status of a deviation record in ci-config.yaml. | `ci/config.py:755` |
| `generate_branch_coverage_report` | `(build_dir: str, fail_under: Optional[float], fail_under_branch: Optional[float], publish_dir: Optional[str])` | Generate comprehensive coverage report with CI artifact packaging. | `ci/coverage_pipeline.py:49` |
| `_compute_module_line_coverage` | `(files: list[dict], module_prefix: str)` | Compute line coverage for all files matching a module prefix. | `ci/coverage_pipeline.py:226` |
| `_get_tool_version` | `(name: str)` | Get the version string of a tool. | `ci/coverage_pipeline.py:238` |
| `_publish_artifacts` | `(report: dict, html_dir: str, publish_dir: str)` | Publish coverage artifacts to a directory. | `ci/coverage_pipeline.py:248` |
| `save_coverage_markdown` | `(report: dict)` | Generate a Markdown coverage report summary. | `ci/coverage_pipeline.py:313` |
| `main` | `()` | CLI entry point. | `ci/coverage_pipeline.py:373` |
| `_ensure_trend_dir` | `(project_dir: str)` | Ensure the trend file directory exists and return the full path. | `ci/coverage_trend.py:35` |
| `_load_json_report` | `(project_dir: str, rel_path: str)` | Load a JSON report file, returning None on failure. | `ci/coverage_trend.py:42` |
| `_get_c_coverage` | `(project_dir: str)` | Extract C coverage metrics from ``c-coverage.json``. | `ci/coverage_trend.py:55` |
| `_get_py_coverage` | `(project_dir: str)` | Extract Python coverage metrics from ``coverage.json`` (pytest-cov). | `ci/coverage_trend.py:67` |
| `_get_git_commit` | `(project_dir: str)` | Get short git commit hash. | `ci/coverage_trend.py:97` |
| `record_coverage` | `(project_dir: str)` | Record C and Python coverage data to the trend JSONL file. | `ci/coverage_trend.py:118` |
| `show_coverage_trend` | `(project_dir: str, days: int, lines: int, as_json: bool)` | Return a Markdown table (or JSON) of the coverage trend. | `ci/coverage_trend.py:151` |
| `_parse_timestamp` | `(ts_str: str)` | Parse ISO timestamp string, returning epoch on failure. | `ci/coverage_trend.py:251` |
| `check_coverage_regression` | `(project_dir: str, line_drop_threshold: float, branch_drop_threshold: float, window: int)` | Check for coverage regression against recent history. | `ci/coverage_trend.py:268` |
| `run_weekly_verification` | `(project_path: str)` | Run the weekly C coverage gate verification. | `ci/cron_c_coverage_verify.py:28` |
| `main` | `()` | — | `ci/cron_c_coverage_verify.py:68` |
| `_check_kg_available` | `()` | Check if the KG module is importable. | `ci/dashboard_writer.py:33` |
| `_swe_status_from_kg` | `(project_dir: str | Path)` | Query KG for real ASPICE evidence, return SWE phase status dict. | `ci/dashboard_writer.py:58` |
| `write_swe_status` | `(project_dir: str | Path, spec_path: str | Path | None, force: bool)` | Write SWE.x status records (ASPICE compliance level) to dashboard DB. | `ci/dashboard_writer.py:146` |
| `write_coverage_trend` | `(project_dir: str | Path)` | Write coverage-trend record from latest test/CI run. | `ci/dashboard_writer.py:314` |
| `write_kpi_trend` | `(project_dir: str | Path, force: bool)` | Write process KPI trend record (MISRA violations, coverage, CI passes). | `ci/dashboard_writer.py:350` |
| `run_dashboard_update` | `(project_dir: str | Path, spec_path: str | Path | None, force: bool)` | Run all dashboard updates: SWE status + coverage trend + KPI trend. | `ci/dashboard_writer.py:442` |
| `_update_evidence_bundle` | `(project_dir: str | Path, result: dict)` | Mirror dashboard data into evidence-bundle/trend-data/. | `ci/dashboard_writer.py:479` |
| `main` | `()` | CLI entry point for dashboard update. | `ci/dashboard_writer.py:511` |
| `_matches_glob` | `(rel: str, pattern: str)` | Glob-style match supporting recursive ``**``. | `ci/diff_planner.py:103` |
| `collect_changed_files` | `(project_dir: Optional[str])` | Collect changed files from git (3-source union, ALL extensions). | `ci/diff_planner.py:124` |
| `plan_skips` | `(steps: list[tuple], changed_files: Optional[list[str]], gate_policy: Optional[dict], file_globs: Optional[dict])` | Plan which steps can be skipped based on changed files. | `ci/diff_planner.py:174` |
| `_any_glob_matches` | `(changed_files: list[str], globs: list[str])` | — | `ci/diff_planner.py:252` |
| `is_enabled` | `()` | 方向2 显式开启开关（默认关闭 → 零回归）。 | `ci/diff_planner.py:260` |
| `skip_summary` | `(decisions: list[SkipDecision])` | Human-readable skip summary for console/report (G2). | `ci/diff_planner.py:265` |
| `_default_file_globs` | `()` | Default step→glob mapping (can be overridden by STEP_FILE_GLOBS). | `ci/diff_planner.py:280` |
| `get_step_file_globs` | `()` | Effective file globs: external STEP_FILE_GLOBS merged over defaults. | `ci/diff_planner.py:299` |
| `resolve_gate` | `(step_key: str, policy: Optional[dict])` | Resolve the gate strength for a pipeline step. | `ci/gate_policy.py:75` |
| `load_gate_policy` | `(project_dir: Optional[str])` | Load effective gate policy for a project. | `ci/gate_policy.py:109` |
| `describe_gate_policy` | `(policy: dict)` | Human-readable summary of a gate policy (for reports/CLI). | `ci/gate_policy.py:158` |
| `run_gcov_coverage` | `(build_dir: str, src_dir: str)` | Run gcov + lcov to generate C coverage report. | `ci/gcov_coverage.py:22` |
| `parse_lcov_output` | `(lcov_file: str)` | Parse lcov .info file into structured report. | `ci/gcov_coverage.py:149` |
| `generate_c_coverage_report` | `(build_dir: str, fail_under: Optional[float], fail_under_branch: Optional[float], module_thresholds: Optional[dict[str, float]])` | Generate C coverage report and return JSON path. | `ci/gcov_coverage.py:267` |
| `_compute_module_c_coverage` | `(files: list[dict], module_prefix: str)` | Compute line coverage for C files matching a module prefix. | `ci/gcov_coverage.py:444` |
| `main` | `()` | CLI entry point. | `ci/gcov_coverage.py:456` |
| `_age_days` | `(ts: str)` | Parse ISO timestamp → age in days (float). None if unparseable. | `ci/honesty_gate.py:39` |
| `check_empty_evidence` | `(project_dir: str)` | H1: 空自报对象（仅 type+status，无实质内容）不得撑绿。 | `ci/honesty_gate.py:50` |
| `check_missing_artifacts` | `(project_dir: str)` | H3: 缺失产物不得静默跳过（有结构缺文件 → 红）。 | `ci/honesty_gate.py:75` |
| `check_result_freshness` | `(project_dir: str, max_age_days: int)` | H4: CI 结果新鲜度 — 超过 *max_age_days* 天视为失效（门禁红）。 | `ci/honesty_gate.py:94` |
| `check_misra_consistency` | `(project_dir: str)` | H8: 报告数字必须可溯源 — total_violations 与 violations_raw 一致。 | `ci/honesty_gate.py:133` |
| `check_coverage_branch_data` | `(project_dir: str)` | H9: branch gate 配置了但无 branch 数据 → 红（防 0.0>=0.0 假绿旁路）。 | `ci/honesty_gate.py:165` |
| `run_honesty_gate` | `(project_dir: str, ci)` | Run all honesty gates. Returns True if no gate failed. | `ci/honesty_gate.py:219` |
| `main` | `(argv: Optional[list])` | — | `ci/honesty_gate.py:240` |
| `upgrade_rules_yaml` | `(rules_yaml_path: str | Path, dry_run: bool)` | Upgrade misra-rules.yaml from 2023-preview to 2023-full. | `ci/misra_c2023_phase1.py:211` |
| `run_pilot_scan` | `(yuleasr_dir: str | Path, modules: list[str] | None, output_dir: str | Path | None)` | Run MISRA C:2023 pilot scan on selected BCM modules. | `ci/misra_c2023_phase1.py:306` |
| `main` | `()` | CLI: Run MISRA C:2023 Phase 1 upgrade. | `ci/misra_c2023_phase1.py:425` |
| `load_deviations_from_report` | `(report_path: str | Path)` | Load deviations from an existing misra-report.json. | `ci/misra_deviations.py:357` |
| `compute_known_rate` | `(project_dir: str | Path)` | Compute MISRA Known Rate = deviations / (violations + deviations). | `ci/misra_deviations.py:388` |
| `register_batch_deviations` | `(project_dir: str | Path, deviations: list[Deviation], deduplicate: bool)` | Register a batch of deviations in ci-config.yaml. | `ci/misra_deviations.py:456` |
| `update_misra_report_deviations` | `(project_dir: str | Path)` | Sync deviations from ci-config.yaml into misra-report.json for Known Rate tracking. | `ci/misra_deviations.py:508` |
| `generate_autosar_deviations` | `()` | Generate the full set of AUTOSAR-pattern deviations for Known Rate 99%. | `ci/misra_deviations.py:560` |
| `main` | `()` | CLI tool: batch register MISRA deviations. | `ci/misra_deviations.py:574` |
| `parse_cppcheck_layer` | `(text: str)` | Parse cppcheck MISRA addon output into a LayerResult. | `ci/misra_fusion.py:353` |
| `parse_clang_tidy_layer` | `(text: str)` | Parse clang-tidy MISRA output into a LayerResult. | `ci/misra_fusion.py:395` |
| `parse_ai_review_layer` | `(ai_json: str | dict)` | Parse AI review JSON output into a LayerResult. | `ci/misra_fusion.py:433` |
| `main` | `()` | — | `ci/misra_fusion.py:487` |
| `_ensure_trend_dir` | `(project_dir: str)` | Ensure the trend file directory exists and return the full path. | `ci/misra_trend.py:27` |
| `append_entry` | `(project_dir: str, total_violations: int, required: int, advisory: int, files_checked: int, is_delta: bool, commit: str)` | Append one trend entry to ``.yuleosh/reports/misra-trend.jsonl``. | `ci/misra_trend.py:34` |
| `show_trend` | `(project_dir: str, lines: int, days: int, as_json: bool)` | Return a Markdown table (or JSON) of the last N trend entries. | `ci/misra_trend.py:77` |
| `_parse_timestamp` | `(ts_str: str)` | Parse an ISO timestamp string, returning epoch (1970-01-01) on failure. | `ci/misra_trend.py:169` |
| `get_violations_per_kloc` | `(violations: int, kloc: float)` | Calculate violations per thousand lines of code (KLOC). | `ci/misra_trend.py:177` |
| `_print_trend_summary` | `(project_dir: str, lines: int)` | Print a condensed trend summary to CI logs (used at end of run_misra_check). | `ci/misra_trend.py:198` |
| `get_available_profiles` | `()` | Return all available profile definitions (builtin + custom). | `ci/profile.py:98` |
| `get_profile_config` | `(profile_name: str)` | Get configuration for a named profile. | `ci/profile.py:103` |
| `validate_active_profile` | `(project_dir: str)` | Validate that the active profile from ci-config.yaml is valid. | `ci/profile.py:116` |
| `filter_steps_for_profile` | `(steps: list[tuple], profile_name: str, project_dir: str)` | Filter pipeline steps based on the active profile. | `ci/profile.py:167` |
| `get_current_profile` | `(project_dir: str)` | Get the active profile name from ci-config.yaml. | `ci/profile.py:253` |
| `_ensure_audit_dir` | `(project_dir: str)` | — | `ci/profile.py:277` |
| `_get_git_commit` | `(project_dir: str)` | Get the current git commit SHA (short). | `ci/profile.py:283` |
| `_get_git_user` | `(project_dir: str)` | Get the configured git user name. | `ci/profile.py:296` |
| `record_profile_change` | `(project_dir: str, old_profile: str, new_profile: str, user: str, reason: str)` | Record a profile change to the audit log. | `ci/profile.py:309` |
| `get_profile_audit_log` | `(project_dir: str, limit: int, as_json: bool)` | Get the profile change audit log. | `ci/profile.py:362` |
| `get_ci_profile` | `(name: str)` | Retrieve a built-in CI profile by name. | `ci/profiles.py:114` |
| `list_ci_profiles` | `()` | List all available CI profiles with summary info. | `ci/profiles.py:122` |
| `resolve_ci_profile` | `(profile_name: Optional[str], ci_config_coverage_threshold_line: float, ci_config_coverage_threshold_condition: float, ci_config_strict: bool, ci_config_misra_profile: str, ci_config_module_thresholds: dict[str, float] | None)` | Merge a named CI profile over the ci-config.yaml base values. | `ci/profiles.py:138` |
| `print_profile_summary` | `()` | Print a formatted summary of all available CI profiles. | `ci/profiles.py:249` |
| `timed_stage` | `(func)` | Decorate a CI stage handler to measure and log execution time. | `ci/result.py:24` |
| `_infer_test_type` | `(tc_name: str, xml_path: Path)` | Infer test type (unit/integration/system) from test name and file path. | `ci/review_helpers.py:29` |
| `_extract_testcase` | `(tc: ET.Element, suite: ET.Element | None)` | Extract a single test case result from a <testcase> element. | `ci/review_helpers.py:77` |
| `parse_junit_xml` | `(xml_path: Path)` | Parse pytest JUnit XML file and return test_case_results list. | `ci/review_helpers.py:138` |
| `_normalize_req_id` | `(raw: str)` | SW-004 → SW004; g17 → G17; REQ-001 → REQ001 (去分隔符 + 大写)。 | `ci/review_helpers.py:210` |
| `find_test_source_files` | `(project_dir: Path)` | Discover test source files (*.py, *.c) in the project tree. | `ci/review_helpers.py:215` |
| `_extract_assertion_lines` | `(source_files: list[Path], test_name: str)` | Search test source files for a function definition matching *test_name* | `ci/review_helpers.py:235` |
| `auto_map_shall_coverage` | `(shall_statements: list[dict], test_case_results: list[dict], test_source_files: list[Path] | None)` | Automatically map SHALL statements to test cases by test function name. | `ci/review_helpers.py:320` |
| `_save_layer_result` | `(project_dir: str, ci: 'CIResult', all_passed: bool, commit: str, layer: int)` | Write CI result JSON to disk and send notification. | `ci/runner.py:31` |
| `git_commit_hash` | `()` | — | `ci/runner.py:58` |
| `get_changed_files` | `(base_ref: str)` | Get list of changed files. | `ci/runner.py:67` |
| `check_coverage_gate` | `(project_dir: str, coverage_data: Optional[dict], override_strict: bool)` | Check coverage gate with strict mode and module-level thresholds. | `ci/runner.py:84` |
| `_compute_module_coverage` | `(files: list[dict], module_prefix: str)` | Compute line coverage for a module (by file path prefix). | `ci/runner.py:195` |
| `_load_latest_coverage` | `(project_dir: str)` | Load the latest coverage report from the CI cache. | `ci/runner.py:210` |
| `_load_python_coverage` | `(project_dir: str)` | Try to load a pytest --cov JSON report from .yuleosh/reports/. | `ci/runner.py:227` |
| `run_all` | `(project_dir: Optional[str], override_strict: bool)` | Run the full CI pipeline: L1 → L2 → L2.5 → L3 with dependency gating. | `ci/runner.py:244` |
| `main` | `()` | — | `ci/runner.py:342` |
| `_resolve_cross_compile` | `(project_dir: str, cross_src: str, build_dir: str, ci: 'CIResult')` | Attempt cross-compilation via make or Docker fallback. | `ci/stage_utils.py:27` |
| `_cross_compile_via_docker` | `(project_dir: str, ci: 'CIResult')` | Cross-compile via Dockerfile.cross when make is unavailable. | `ci/stage_utils.py:74` |
| `_handle_stage_error` | `(ci, stage: str, reason: str, strict: bool)` | Record a stage error with strict-mode awareness. Returns True if blocked. | `ci/stage_utils.py:108` |
| `_run_subprocess` | `(cmd: list[str], cwd: str, timeout: int)` | Run a subprocess with unified error handling. | `ci/stage_utils.py:117` |
| `get_cache_key_for_dir` | `(project_dir: str)` | Build a cache key that changes when test files or dirs change. | `ci/stage_utils.py:139` |
| `find_test_files` | `(project_dir: str)` | Auto-discover test files with mtime-based caching. | `ci/stage_utils.py:178` |
| `_should_skip_coverage` | `()` | Check if coverage should be skipped (pre-commit hook or nested run). | `ci/stage_utils.py:209` |
| `_coverage_skip_reason` | `()` | Return the human-readable skip reason. | `ci/stage_utils.py:217` |
| `_run_coverage_and_export` | `(project_dir: str)` | Run ``coverage run`` + ``coverage json``. | `ci/stage_utils.py:224` |
| `_load_coverage_json` | `(project_dir: str)` | Parse coverage.json and return (line_pct, condition_pct). | `ci/stage_utils.py:264` |
| `_detect_hil_target` | `(project_dir: str, ci: 'CIResult', mock_mode: bool, strict: bool)` | Stage 1: Detect hardware target (real or mock). Returns True on success. | `ci/stage_utils.py:273` |
| `_run_hil_mock_tests` | `(ci: 'CIResult', hw_cfg, scripts_full: str, boot_pattern: str)` | Run simulated (mock) HIL tests — no real hardware needed. | `ci/stage_utils.py:309` |
| `_run_hil_real_tests` | `(ci: 'CIResult', hw_cfg, firmware_full: str, strict: bool, boot_pattern: str)` | Run real HIL tests — flash firmware and assert serial output. | `ci/stage_utils.py:334` |
| `_record_hil_results` | `(ci: 'CIResult', results: list[dict])` | Record HIL test results into CI stages. Returns True if all passed. | `ci/stage_utils.py:373` |
| `_save_hil_report` | `(project_dir: str, all_passed: bool, commit: str, mock_mode: bool, boot_pattern: str)` | Stage 3: Save HIL report to disk and return report dict. | `ci/stage_utils.py:385` |
| `_find_c_sources` | `(project_dir: str)` | Find C/C++ source files and cross-compile paths. | `ci/stage_utils.py:402` |
| `_cross_compile_stage` | `(project_dir: str, cross_src: str, build_dir: str, ci)` | Stage 1: Cross-compilation check. Returns True if passed/skipped. | `ci/stage_utils.py:427` |
| `_static_analysis_stage` | `(c_files: list[str], project_dir: str, ci, misra_ff: bool, strict: bool)` | Stage 2: Static analysis via cppcheck. Returns True if passed/skipped. | `ci/stage_utils.py:439` |
| `_integration_test_stage` | `(project_dir: str, ci)` | Stage 4: Integration tests. Returns True if passed/skipped. | `ci/stage_utils.py:466` |
| `load_sync_gate_config` | `(project_dir: str)` | Load the sync-gate YAML config from ``docs/.sync-gate.yaml``. | `ci/sync_check.py:47` |
| `get_changed_files` | `(project_dir: str, base_ref: str)` | Get list of changed files compared to a Git ref. | `ci/sync_check.py:70` |
| `check_mtime_freshness` | `(doc_path: str, project_dir: str)` | Check if a doc file has been modified recently (within 30 days). | `ci/sync_check.py:112` |
| `run_sync_check` | `(project_dir: str, base_ref: str)` | Run the full document sync gate check. | `ci/sync_check.py:123` |
| `save_sync_evidence` | `(project_dir: str, result: dict)` | Save sync check result to ``.yuleosh/reports/docsync-evidence.json``. | `ci/sync_check.py:234` |
| `validate_doc_yaml_schema` | `(project_dir: str)` | Validate YAML document files against expected schemas (CL2-E05). | `ci/sync_check.py:255` |
| `run_sync_check_gate` | `(project_dir: str, base_ref: str)` | Enhanced sync gate combining doc-tracking (E06) and schema validation (E05). | `ci/sync_check.py:329` |
| `print_sync_result` | `(result: dict)` | Print a human-readable summary of the sync check result. | `ci/sync_check.py:391` |
| `main` | `()` | CLI entry point for ``yuleosh audit sync-check``. | `ci/sync_check.py:478` |
| `create_driver` | `(tool: str, project_dir: str, config: Optional[dict], ruleset)` | 创建指定工具的分析驱动实例。 | `ci/tool_drivers.py:376` |
| `register_driver` | `(tool: str, driver_cls: type[BaseToolDriver])` | 注册新的工具驱动。 | `ci/tool_drivers.py:414` |
| `list_drivers` | `()` | 列出所有已注册的工具驱动名称。 | `ci/tool_drivers.py:432` |
| `_ensure_report_dir` | `(project_dir: Path)` | Ensure the .yuleosh/reports directory exists. | `ci/verify_c_coverage_gate.py:46` |
| `_log_p0_alert` | `(project_dir: Path, message: str, details: Optional[dict])` | Write a P0 alert entry to the p0-alerts.jsonl file. | `ci/verify_c_coverage_gate.py:53` |
| `_find_demo_project` | `(project_dir: Path)` | Locate the demo C project directory to use for verification. | `ci/verify_c_coverage_gate.py:69` |
| `_build_c_demo` | `(demo_dir: Path)` | Build the C demo project with --coverage flags. | `ci/verify_c_coverage_gate.py:88` |
| `_run_demo_executable` | `(exe_path: Path)` | Run the compiled demo executable to produce .gcda files. | `ci/verify_c_coverage_gate.py:192` |
| `_find_gcda_files` | `(build_dir: Path)` | Find all .gcda files produced by the demo run. | `ci/verify_c_coverage_gate.py:220` |
| `_parse_gcovr_coverage` | `(gcda_dir: Path)` | Run gcovr --json to parse .gcda coverage data. | `ci/verify_c_coverage_gate.py:230` |
| `_parse_gcov_text` | `(gcda_dir: Path)` | Parse .gcda coverage via gcov text output (fallback when gcovr unavailable). | `ci/verify_c_coverage_gate.py:263` |
| `_load_c_fail_under` | `(project_dir: Path)` | Load the c_fail_under threshold from ci-config.yaml. | `ci/verify_c_coverage_gate.py:347` |
| `verify_c_coverage_gate` | `(project_path: str)` | Run the end-to-end C coverage gate verification. | `ci/verify_c_coverage_gate.py:357` |
| `main` | `()` | CLI entry point for the verification pipeline. | `ci/verify_c_coverage_gate.py:558` |
| `_check_type` | `(value: Any, expected: str, path: str)` | Check that *value* matches *expected* type. Returns list of errors. | `ci/yaml_validator.py:119` |
| `_validate_against_schema` | `(data: dict, schema: dict, prefix: str)` | Validate *data* against a schema dict. Returns list of error strings. | `ci/yaml_validator.py:143` |
| `validate_ci_config` | `(path: str)` | Validate ``ci-config.yaml`` schema compliance. | `ci/yaml_validator.py:190` |
| `validate_misra_rules` | `(path: str)` | Validate ``misra-rules.yaml`` schema compliance. | `ci/yaml_validator.py:232` |
| `validate_all` | `(path: str)` | Full YAML validation — check both ``ci-config.yaml`` and ``misra-rules.yaml``. | `ci/yaml_validator.py:276` |
| `check_coverage_gate_with_profile` | `(project_dir: str, coverage_data: dict | None, override_strict: bool, profile: str)` | Check coverage gate using profile-aware thresholds. | `ci/layers/__init__.py:51` |
| `get_profile_label` | `(project_dir: str)` | Get the active CI profile label for display. | `ci/layers/__init__.py:98` |
| `get_latest_layer_result` | `(layer: int, project_dir: str)` | Read the most recent CI result for the given layer from .osh/ci/. | `ci/layers/layer_config.py:36` |
| `check_layer_dependency` | `(target_layer: int, project_dir: str)` | Check if all dependencies for *target_layer* are satisfied. | `ci/layers/layer_config.py:59` |
| `_detect_project_language` | `(project_dir: str)` | Detect the project language type by examining marker files. | `ci/layers/layer_config.py:94` |
| `_find_go_modules` | `(project_dir: str)` | Find all directories containing go.mod under *project_dir*. | `ci/layers/layer_executor.py:60` |
| `_run_go_build` | `(project_dir: str, ci: CIResult, timeout: int)` | Run ``go build ./...`` in every Go module (monorepo-aware). | `ci/layers/layer_executor.py:76` |
| `_run_go_vet` | `(project_dir: str, ci: CIResult, timeout: int)` | Run ``go vet ./...`` in every Go module (monorepo-aware). | `ci/layers/layer_executor.py:107` |
| `_run_go_test` | `(project_dir: str, ci: CIResult, timeout: int)` | Run ``go test ./...`` in every Go module (monorepo-aware). | `ci/layers/layer_executor.py:138` |
| `_run_embedded_misra_check` | `(project_dir: str, ci: CIResult)` | Run MISRA check for embedded C sources in mixed-language projects. | `ci/layers/layer_executor.py:169` |
| `_run_go_layer1` | `(project_dir: str, ci: CIResult, timeout: int)` | Run Layer 1 CI checks for a Go project. | `ci/layers/layer_executor.py:189` |
| `_run_python_layer1` | `(project_dir: str, ci: CIResult, timeout: int)` | Run Layer 1 CI checks for a Python project. | `ci/layers/layer_executor.py:225` |
| `_run_layer1_impl` | `(project_dir: str, ci: CIResult, timeout: int)` | Core implementation of Layer 1, called inside the timeout guard. | `ci/layers/layer_executor.py:267` |
| `run_layer1` | `(project_dir: Optional[str], timeout: Optional[int])` | Run Layer 1 CI pipeline. | `ci/layers/layer_executor.py:331` |
| `run_layer_25` | `(project_dir: Optional[str])` | CI Layer 2.5: Hardware-in-the-Loop (HIL) — runs after L2 passes. | `ci/layers/layer_executor.py:454` |
| `run_layer2` | `(project_dir: Optional[str])` | CI Layer 2: Integration Verification — runs on MR. | `ci/layers/layer_executor.py:538` |
| `run_layer3` | `(project_dir: Optional[str])` | CI Layer 3: System Verification — runs on Release. | `ci/layers/layer_executor.py:619` |
| `validate_layer_result` | `(result_path: str)` | Validate a layer result file and return summary. | `ci/layers/layer_validator.py:21` |
| `format_layer_summary` | `(summary: dict)` | Format a layer result summary for display. | `ci/layers/layer_validator.py:57` |
| `_collect_sources` | `(source_dir: Path)` | Collect BSW source files (.c + .cpp), sorted for determinism. | `ci/stages/autosar.py:49` |
| `_compiler_for` | `(src_file: Path, prefix: str)` | Pick compiler by source extension: .cpp → g++, else gcc. | `ci/stages/autosar.py:58` |
| `_std_flag_for` | `(src_file: Path)` | — | `ci/stages/autosar.py:65` |
| `run_autosar_build` | `(project_dir: str, layers: Optional[List[str]], mcal_only: bool, ecual_only: bool, services_only: bool, build_dir: str, verbose: bool)` | Build AUTOSAR BSW layers: MCAL, ECUAL, Services. | `ci/stages/autosar.py:123` |
| `run_autosar_cross_build` | `(project_dir: str, target: str, build_dir: str, toolchain_prefix: str, docker_image: Optional[str])` | Cross-compile AUTOSAR BSW for ARM Cortex-M/R targets. | `ci/stages/autosar.py:288` |
| `_cross_build_via_docker` | `(project_dir: str, target: str, arch_flags: List[str], build_dir: str, docker_image: str)` | Run AUTOSAR cross-compilation inside Docker. | `ci/stages/autosar.py:421` |
| `run_autosar_misra_check` | `(project_dir: str, layers: Optional[List[str]], cppcheck_args: Optional[List[str]], fail_on_warning: bool)` | Run MISRA-C:2023 static analysis on AUTOSAR BSW code. | `ci/stages/autosar.py:506` |
| `_run_misra_fallback` | `(project_dir: str, layers: List[str])` | Fallback MISRA analysis using yuleOSH's built-in rule engine. | `ci/stages/autosar.py:649` |
| `run_autosar_full_ci` | `(project_dir: str, target: str)` | Run full AUTOSAR CI pipeline: build → cross-compile → MISRA check. | `ci/stages/autosar.py:697` |
| `run_arxml_compliance_check` | `(project_dir: str, arxml_path: Optional[str])` | Validate AUTOSAR ARXML compliance for a generated project. | `ci/stages/autosar.py:768` |
| `register_autosar_stages` | `(existing_registry: Dict)` | Register AUTOSAR CI stages into an existing stage registry. | `ci/stages/autosar.py:844` |
| `run_c_coverage` | `(project_dir: str, ci: CIResult)` | Run C/C++ code coverage via gcov/lcov. | `ci/stages/build.py:48` |
| `_strip_comments_and_strings` | `(line: str)` | 粗略剥离字符串字面量与行注释, 用于代码模式匹配. | `ci/stages/code_style.py:110` |
| `_is_excluded_dir` | `(name: str)` | 判断目录是否应排除（全名匹配 + 前缀匹配 cmake-build*/build*）。 | `ci/stages/code_style.py:144` |
| `_iter_source_files` | `(project_dir: Path)` | 遍历项目 C 源文件, 排除构建产物/第三方目录（平台统一排除集）。 | `ci/stages/code_style.py:154` |
| `_load_rules` | `(rules_path: Path | None)` | — | `ci/stages/code_style.py:164` |
| `_check_indent_4spaces` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 1-1: 程序块缩进为 4 个空格（倍数）。 | `ci/stages/code_style.py:182` |
| `_check_line_length_80` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 1-3: 较长语句(>80 字符)应分行。排除纯注释行与长字符串字面量行。 | `ci/stages/code_style.py:202` |
| `_check_one_statement_per_line` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 1-6: 一行只写一条语句。 | `ci/stages/code_style.py:224` |
| `_check_control_braces` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 1-7: if/for/do/while 执行语句无论多少都要加 {}。 | `ci/stages/code_style.py:246` |
| `_check_no_tab` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 1-8: 对齐只使用空格, 不使用 TAB。 | `ci/stages/code_style.py:264` |
| `_check_brace_own_line` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 1-10: 程序块分界符 { } 各独占一行, 与引用语句左对齐。 | `ci/stages/code_style.py:279` |
| `_comment_ratio` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 2-1: 有效注释量 >= 20%（按注释字符/总字符估算）。 | `ci/stages/code_style.py:296` |
| `_check_comment_ratio_20` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 2-1: 源程序有效注释量必须在 20% 以上。 | `ci/stages/code_style.py:329` |
| `_check_no_single_char_var` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 3-4: 变量命名禁止取单个字符（如 i、j、k...）。 | `ci/stages/code_style.py:344` |
| `_check_type_prefix` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 3-6: 变量命名需要加数据类型前缀。 | `ci/stages/code_style.py:380` |
| `_check_macro_upper` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 3-7: 宏命名全部大写, 单词间下划线。 | `ci/stages/code_style.py:409` |
| `_check_macro_parens` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 7-1: 宏定义表达式要使用完备括号（函数宏）。 | `ci/stages/code_style.py:427` |
| `_check_macro_multi_stmt_braces` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 7-2: 宏定义多条表达式应放在大括号中。 | `ci/stages/code_style.py:450` |
| `_check_macro_param_no_mutation` | `(path: Path, rel: str, raw_lines: list[tuple[int, str]])` | 规则 7-3: 使用宏时不允许参数发生变化（++/-- 传入宏）。 | `ci/stages/code_style.py:483` |
| `_check_no_goto` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 11-18: 不要滥用 goto。 | `ci/stages/code_style.py:502` |
| `_check_const_left_compare` | `(path: Path, rel: str, stripped_lines: list[tuple[int, str]])` | 规则 11-19: 变量与常量比较时, 常量写在左边（如 if (5 == x)）。 | `ci/stages/code_style.py:517` |
| `scan_file` | `(path: Path, rules: dict | None, project_root: Path | None)` | 扫描单个 C 源文件, 返回违规列表。 | `ci/stages/code_style.py:558` |
| `scan_project` | `(project_dir: str | Path, rules: dict | None)` | 扫描整个项目的 C 源文件。 | `ci/stages/code_style.py:609` |
| `write_report` | `(project_dir: str | Path, result: ScanResult, save: bool)` | 将扫描结果写入 .yuleosh/reports/code-style-report.json。 | `ci/stages/code_style.py:621` |
| `run_code_style` | `(project_dir: str, ci, target_files: list[str] | None, block_on_violations: bool | None)` | CI stage 入口 — 运行 SWC 代码风格扫描。 | `ci/stages/code_style.py:638` |
| `_config_block_on` | `(project_dir: str)` | 从 .yuleosh/ci-config.yaml 读取 code_style.block_on (默认 False)。 | `ci/stages/code_style.py:691` |
| `format_style_rules_for_review` | `(rules_path: Path | None)` | 从 swc-c-rules.yaml 提取 manual_review 语义规则, 生成 LLM 审查注入文本. | `ci/stages/code_style.py:706` |
| `main` | `(argv: list[str] | None)` | — | `ci/stages/code_style.py:736` |
| `_find_files` | `(project_dir: str, globs: list[str])` | 在项目目录下按 glob 找文件（排除 .git/node_modules/.yuleosh 内部缓存）。 | `ci/stages/methodology_gate.py:37` |
| `_find_spec_files` | `(project_dir: str)` | 找 spec 文件（grilling 检查用）。 | `ci/stages/methodology_gate.py:52` |
| `_check_grilling` | `(project_dir: str)` | §1 grilling 对齐：最新 spec 必须含决策记录/澄清痕迹。 | `ci/stages/methodology_gate.py:93` |
| `_check_domain_model` | `(project_dir: str)` | §2 domain-modeling：CONTEXT.md 存在且不含实现细节关键词。 | `ci/stages/methodology_gate.py:128` |
| `_check_two_axis_review` | `(project_dir: str)` | §3 双轴评审：至少一份评审报告含 Standards + Spec 两轴。 | `ci/stages/methodology_gate.py:145` |
| `_check_tight_loop` | `(project_dir: str)` | §4 tight-loop 调试：至少一份调试/修复记录含复现回路证据。 | `ci/stages/methodology_gate.py:161` |
| `_check_vertical_slices` | `(project_dir: str)` | §5 垂直切片：plan 文件含 blocking edges / 切片结构。 | `ci/stages/methodology_gate.py:177` |
| `_check_handoff` | `(project_dir: str)` | §6 交接纪律：交接文档引用 artifact 而非复制。 | `ci/stages/methodology_gate.py:191` |
| `_is_methodology_project` | `(project_dir: str)` | 检测项目是否走方法论流程。 | `ci/stages/methodology_gate.py:219` |
| `run_methodology_gate` | `(project_dir: str, ci, log_fn)` | Run the methodology gate. Returns True if pipeline should continue. | `ci/stages/methodology_gate.py:238` |
| `run_docsync_gate` | `(project_dir: str, ci: CIResult)` | Run the document sync gate check (H-07). | `ci/stages/review.py:69` |
| `_categorize_file` | `(filepath: str, categories: dict)` | 根据文件路径判断代码类别，返回 (category_name, category_config)。 | `ci/stages/review_collect.py:19` |
| `_find_c_sources` | `(project_dir: str, scan_dirs: list[str])` | Walk *scan_dirs* (configurable, default src/benchmark/ref) for C/C++ files. | `ci/stages/review_collect.py:37` |
| `_collect_delta_files` | `(project_dir: str, depth: int)` | Collect changed C/C++ files from three sources (union, no dedup loss). | `ci/stages/review_collect.py:50` |
| `_expand_header_dependents` | `(project_dir: str, changed_files: list[str])` | Expand changed headers into the .c/.cpp files that include them. | `ci/stages/review_collect.py:103` |
| `_glob_to_regex` | `(pattern: str)` | Convert a glob pattern (with recursive ``**``) to an anchored regex. | `ci/stages/review_collect.py:160` |
| `_matches_glob` | `(rel: str, pattern: str)` | Glob-style match supporting recursive ``**``. | `ci/stages/review_collect.py:180` |
| `_exclude_paths` | `(files: list[str], exclude_patterns: list[str], project_dir: str)` | Filter out files matching any of the exclude patterns (glob-style). | `ci/stages/review_collect.py:199` |
| `_detect_include_paths` | `(project_dir: str)` | Auto-detect common include directories for cppcheck -I flags. | `ci/stages/review_collect.py:235` |
| `_scan_include_dirs` | `(project_dir: str)` | Walk project source dirs and collect every **/include/ directory | `ci/stages/review_collect.py:283` |
| `_get_git_commit` | `(project_dir: str)` | Get short git commit hash from the project directory. | `ci/stages/review_collect.py:352` |
| `_format_null_pointer_fix` | `(category: str, file_path: str)` | 根据代码类别生成针对性的多级指针空修复建议。 | `ci/stages/review_misra.py:34` |
| `run_misra_check` | `(project_dir: str, ci: CIResult, target_files: list[str] | None, mode: str)` | Run MISRA C:2023 static analysis via cppcheck --addon=misra. | `ci/stages/review_misra.py:71` |
| `run_unit_tests` | `(project_dir: str, ci: CIResult)` | Discover and run unit tests. | `ci/stages/test.py:48` |
| `run_coverage_check` | `(project_dir: str, ci: CIResult)` | Check test coverage meets threshold. | `ci/stages/test.py:123` |
| `run_sil_tests` | `(project_dir: str, ci: CIResult)` | Run SIL (Software-in-the-Loop) tests using QEMU emulation. | `ci/stages/test.py:243` |
| `run_c_coverage_check` | `(project_dir: str, ci: CIResult)` | C Coverage gate — block pipeline if line_rate < c_fail_under threshold. | `ci/stages/test.py:356` |
| `run_coverage_regression` | `(project_dir: str, ci: CIResult)` | Check Python coverage regression against trend history. | `ci/stages/test.py:572` |
| `run_requirements_trace` | `(project_dir: str, ci: CIResult)` | Check basic requirements traceability (SWE.5 left side). | `ci/stages/traceability.py:49` |
| `run_yaml_validation` | `(project_dir: str, ci: CIResult)` | Validate YAML configuration files (ci-config.yaml, misra-rules.yaml). | `ci/stages/validation.py:48` |
| `run_plan_lint` | `(project_dir: str, ci: CIResult)` | Run plan-lint: check task kind and T00 three-step format. | `ci/stages/validation.py:78` |
| `run_clang_tidy` | `(project_dir: str, ci: CIResult)` | Run clang-tidy on C/C++ files. | `ci/stages/validation.py:128` |
| `run_spec_validation` | `(project_dir: str, ci: CIResult)` | Validate that spec files are present and parseable (SWE.5 left side). | `ci/stages/validation.py:199` |
| `run_architecture_review` | `(project_dir: str, ci: CIResult)` | Check architecture documentation and structure (SWE.5 left side). | `ci/stages/validation.py:238` |
| `main` | `()` | — | `ci/misra_report/cli.py:69` |
| `_deviation_to_dict` | `(dev: tuple | dict | object)` | Normalize a deviation entry to a dict with common fields. | `ci/misra_report/deviation.py:56` |
| `_is_deviation_expired` | `(expires_str: str)` | Check if a deviation has expired based on its expires date. | `ci/misra_report/deviation.py:106` |
| `_match_deviation` | `(rule_id: str, file_path: str, deviations: list)` | Check if a violation matches any deviation record. | `ci/misra_report/deviation.py:122` |
| `merge_tool_results` | `(results: list[ToolResult])` | Merge multiple tool results into a unified report. | `ci/misra_report/models.py:126` |
| `_enrich_traceability_with_tests` | `(rule_defs: dict, test_dir: str | None)` | Map rules to their implementation and test IDs (R3-P0-1). | `ci/misra_report/traceability.py:58` |
| `generate_traceability_matrix` | `(violations: list[dict], rule_defs: dict, deviations: list | None, test_dir: str | None)` | Build traceability: Rule ID → File:Line → Spec Ref → Fix Status. | `ci/misra_report/traceability.py:101` |
| `generate_fix_tasks` | `(project_dir: str, violations: list[dict], rule_defs: dict, deviations: list | None)` | Generate fix task .md files for each unresolved violation. | `ci/misra_report/traceability.py:176` |
| `group_by_rule` | `(violations: list[dict])` | Group violations by rule ID. | `ci/misra_report/core/analysis.py:31` |
| `_classify_rule_type` | `(rule_id: str | None)` | Classify a MISRA rule by its type category. | `ci/misra_report/core/analysis.py:42` |
| `_extract_rules` | `(rule_defs: dict)` | Extract rule definitions from the YAML dict, filtering out meta keys. | `ci/misra_report/core/analysis.py:60` |
| `enrich_with_definitions` | `(violations: list[dict] | dict, rule_defs: dict | None)` | Enrich violations with rule definition info. | `ci/misra_report/core/analysis.py:78` |
| `compute_summary_stats` | `(violations: list[dict], groups: dict, rule_defs: dict | None, deviations: list | None)` | Compute summary statistics from violations and groups. | `ci/misra_report/core/analysis.py:134` |
| `_load_prev_report` | `(output_dir: str | Path)` | Load the previous MISRA report for diff comparison. | `ci/misra_report/core/analysis.py:185` |
| `_compute_prev_build_diff` | `(current: dict, prev: dict)` | Compute diff between current and previous MISRA reports. | `ci/misra_report/core/analysis.py:198` |
| `_compute_category_breakdown` | `(violations: list[dict])` | Compute breakdown by violation category. | `ci/misra_report/core/analysis.py:211` |
| `c2012_info` | `(rule_id: str)` | Return C:2012 severity/title for a rule ID if it is a modified rule. | `ci/misra_report/core/c2012_meta.py:80` |
| `_normalize_misra_year` | `(rule_id: str)` | Normalize MISRA rule ID to canonical year format. | `ci/misra_report/core/config.py:60` |
| `_load_ci_config` | `()` | Load CI configuration (ci_config.yaml / ci_config.json). | `ci/misra_report/core/config.py:70` |
| `_extract_excluded_rules` | `(config: dict | None)` | Extract excluded MISRA rule IDs from CI config. | `ci/misra_report/core/config.py:87` |
| `_extract_excluded_files` | `(config: dict | None)` | Extract excluded file patterns from CI config. | `ci/misra_report/core/config.py:97` |
| `load_rule_definitions` | `(rules_path: Optional[Path])` | Load MISRA rule definitions from YAML. | `ci/misra_report/core/config.py:107` |
| `_count_source_lines` | `(file_paths: list[str])` | Count total source lines across a list of file paths. | `ci/misra_report/core/config.py:127` |
| `get_tool_version` | `()` | Get MISRA checking tool version. | `ci/misra_report/core/config.py:139` |
| `get_ruleset_version` | `(rule_defs: dict)` | Get ruleset version from rule definitions. | `ci/misra_report/core/config.py:151` |
| `get_ci_environ` | `()` | Extract CI environment metadata. | `ci/misra_report/core/config.py:158` |
| `_build_rule_lookup` | `()` | Build a lookup from short rule ID to canonical YAML key. | `ci/misra_report/core/parser.py:38` |
| `_extract_file_path` | `(raw: str)` | Extract a normalized file path from cppcheck output. | `ci/misra_report/core/parser.py:103` |
| `_is_valid_source_path` | `(path: str)` | Check if a path is a valid source file. | `ci/misra_report/core/parser.py:117` |
| `parse_cppcheck_output` | `(text: str)` | Parse cppcheck plain-text output into structured violations. | `ci/misra_report/core/parser.py:126` |
| `_normalize_rule_id` | `(rule_id: str)` | Normalize MISRA rule ID to canonical format. | `ci/misra_report/core/parser.py:187` |
| `generate_json_report` | `(violations: list[dict], groups: dict, rule_defs: dict | None, output_dir: str | Path, deviation_list: Optional[list], excluded_rules: Optional[list], excluded_files: Optional[list], check_standard: str | None)` | Generate the full MISRA report as a JSON-serializable dict. | `ci/misra_report/core/reporting.py:39` |
| `_serialize_group` | `(group: list[dict] | dict)` | Serialize a group of violations (by rule) to a dict. | `ci/misra_report/core/reporting.py:91` |
| `_format_delta` | `(delta: int)` | Format integer delta with + prefix for positive values. | `ci/misra_report/core/reporting.py:103` |
| `generate_markdown_report` | `(report: dict, title: str)` | Generate a human-readable Markdown report from the JSON report dict. | `ci/misra_report/core/reporting.py:110` |
| `_deviation_to_dict` | `(d)` | Serialize a deviation object to dict. | `ci/misra_report/core/reporting.py:187` |
| `save_report` | `(violations_or_report: list | dict, groups_or_output_dir: dict | str | Path, summary_or_filename, rule_defs_or_formats, output_dir_or_none: str | Path | None, deviations: list | None, check_standard: str | None)` | Save the MISRA report to disk. | `ci/misra_report/core/reporting.py:211` |
| `save_merged_report` | `(misra_report: dict, selftest_review: dict | None, output_path: str | Path)` | Save a merged report combining MISRA analysis with self-test review. | `ci/misra_report/core/reporting.py:331` |
| `print_summary` | `(summary: dict)` | Print a human-readable summary to stdout. | `ci/misra_report/core/reporting.py:350` |
| `extract_rule_number` | `(rule_id: str)` | 从工具特定规则 ID 中提取 'X.Y' 数字部分。 | `ci/scanners/base.py:133` |
| `canonicalize_rule_id` | `(rule_id: str)` | 把任意工具输出的规则 ID 映射为 misra-rules.yaml 规范键。 | `ci/scanners/base.py:149` |
| `violations_to_dicts` | `(violations: list[Violation] | list[dict])` | 把 Violation 列表转换为 dict 列表（下游 misra_report 消费 dict 契约）。 | `ci/scanners/base.py:242` |
| `_detect_cppcheck_language` | `(project_dir: str)` | 按项目源码决定 cppcheck 语言: 含 C++ 源 → 'c++', 否则 'c'. | `ci/scanners/cppcheck_adapter.py:49` |
| `cppcheck_violations_to_dicts` | `(violations: list[Violation])` | — | `ci/scanners/cppcheck_adapter.py:267` |
| `_ensure_defect_escape_dir` | `(project_dir: str)` | Ensure the defect escape JSONL file directory exists. | `ci/kpi/defects.py:58` |
| `record_defect_escape` | `(project_dir: str, total_defects: int, escaped_defects: int, stage: str, description: str)` | Record a defect escape entry. | `ci/kpi/defects.py:64` |
| `_load_defect_escape_entries` | `(project_dir: str)` | Load all defect escape entries from the JSONL file. | `ci/kpi/defects.py:118` |
| `get_defect_escape_summary` | `(project_dir: str, days: int, as_json: bool)` | Get defect escape rate summary. | `ci/kpi/defects.py:134` |
| `_get_kg_store` | `(project_dir: str)` | Lazy-initialize a KGStore instance for the given project. | `ci/kpi/kg_source.py:24` |
| `get_kg_coverage_metrics` | `(project_dir: str)` | Extract KG coverage metrics. | `ci/kpi/kg_source.py:38` |
| `get_kg_health_metrics` | `(project_dir: str)` | Extract KG graph health metrics. | `ci/kpi/kg_source.py:71` |
| `get_kg_confidence_metrics` | `(project_dir: str)` | Extract KG confidence metrics. | `ci/kpi/kg_source.py:124` |
| `get_kg_metrics_summary` | `(project_dir: str, as_json: bool)` | Get merged KG KPI metrics summary. | `ci/kpi/kg_source.py:174` |
| `_ensure_dir` | `(project_dir: str)` | Ensure .yuleosh/ directory exists. | `ci/kpi/kpi_state.py:56` |
| `_load_latest_misra_entry` | `(project_dir: str)` | Load the most recent MISRA trend entry. | `ci/kpi/kpi_state.py:62` |
| `_load_latest_coverage_entry` | `(project_dir: str)` | Load the most recent coverage trend entry. | `ci/kpi/kpi_state.py:81` |
| `_parse_ts` | `(ts_str: str)` | Parse ISO timestamp, returning epoch on failure. | `ci/kpi/kpi_state.py:100` |
| `_load_baseline` | `(project_dir: str)` | Load the saved KPI baseline, if it exists. | `ci/kpi/kpi_state.py:111` |
| `kpi_status` | `(project_dir: str, as_json: bool, thresholds: Optional[dict[str, Any]])` | Show current KPI dashboard — violations, coverage, and trend info. | `ci/kpi/report.py:62` |
| `kpi_baseline_save` | `(project_dir: str, label: str)` | Save current KPI state as a baseline snapshot. | `ci/kpi/report.py:351` |
| `kpi_baseline_compare` | `(project_dir: str, as_json: bool)` | Compare current KPI state against the saved baseline. | `ci/kpi/report.py:460` |
| `_ensure_process_kpi_dir` | `(project_dir: str)` | Ensure the process KPI JSONL file directory exists. | `ci/kpi/stability.py:58` |
| `record_process_stability` | `(project_dir: str, build_success: bool, build_duration_s: float, layer: int, total_stages: int, passed_stages: int, misra_required_new: int, misra_total: int)` | Record a process stability KPI entry (G-49: §21.1~§21.4). | `ci/kpi/stability.py:64` |
| `_load_process_kpi_entries` | `(project_dir: str)` | Load all process KPI entries from the JSONL file. | `ci/kpi/stability.py:134` |
| `get_process_stability_summary` | `(project_dir: str, days: int, as_json: bool)` | Get a summary of process stability KPIs over the last N days. | `ci/kpi/stability.py:150` |
| `generate_process_baseline_report` | `(project_dir: str, label: str)` | Generate a process stability baseline report (≥2 weeks data required). | `ci/kpi/stability.py:283` |
| `_get_misra_trend_avg` | `(project_dir: str, days: int)` | Calculate average MISRA metrics over the last N days. | `ci/kpi/trend.py:58` |
| `_get_coverage_trend_avg` | `(project_dir: str, days: int)` | Calculate average coverage metrics over the last N days. | `ci/kpi/trend.py:97` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `MisraRuleOverride` | `()` | Per-rule override for MISRA C:2023 analysis. | `ci/config.py:50` |
| `MisraDeviation` | `()` | Deviation record for a specific MISRA rule on a file pattern. | `ci/config.py:64` |
| `MisraProfile` | `()` | A named MISRA profile with rule overrides, deviations, and filter rules. | `ci/config.py:82` |
| `AlmConfig` | `()` | ALM (Application Lifecycle Management) integration configuration. | `ci/config.py:113` |
| `MisraConfig` | `()` | MISRA C:2023 static analysis configuration (A-03). | `ci/config.py:140` |
| `CoverageConfig` | `()` | Coverage gate configuration (SWR-003.2). | `ci/config.py:193` |
| `HardwareTestConfig` | `()` | L2.5 HIL test configuration. | `ci/config.py:221` |
| `CiConfig` | `()` | Complete CI configuration for a yuleOSH project. | `ci/config.py:237` |
| `SkipDecision` | `()` | 一次步骤裁剪决策（G2: 显式报告）。 | `ci/diff_planner.py:88` |
| `C2023UpgradeReport` | `()` | Report for the C:2023 Phase 1 upgrade. | `ci/misra_c2023_phase1.py:195` |
| `Deviation` | `()` | MISRA deviation entry (mirrors ci-config.yaml format). | `ci/misra_deviations.py:44` |
| `Violation` | `()` | A single MISRA violation from any analysis layer. | `ci/misra_fusion.py:49` |
| `LayerResult` | `()` | Results from a single analysis layer. | `ci/misra_fusion.py:63` |
| `FusedViolation` | `()` | A fused/cross-validated violation across layers. | `ci/misra_fusion.py:73` |
| `FusionReport` | `()` | Complete 3-layer fusion report. | `ci/misra_fusion.py:89` |
| `CIProfile` | `()` | Configuration for a single CI environment profile. | `ci/profiles.py:39` |
| `CIResult` | `()` | Captures CI result for a single layer. | `ci/result.py:41` |
| `BaseToolDriver` | `(abc.ABC)` | 静态分析工具驱动的抽象基类。 | `ci/tool_drivers.py:37` |
| `CppcheckDriver` | `(BaseToolDriver)` | Cppcheck MISRA 分析驱动。 | `ci/tool_drivers.py:117` |
| `ClangTidyDriver` | `(BaseToolDriver)` | Clang-Tidy 分析驱动（Stub，预留接口）。 | `ci/tool_drivers.py:304` |
| `_LayerTimeout` | `(Exception)` | Raised when a CI layer exceeds its configured timeout. | `ci/layers/layer_config.py:31` |
| `Violation` | `()` | — | `ci/stages/code_style.py:67` |
| `ScanResult` | `()` | — | `ci/stages/code_style.py:89` |
| `MisraViolation` | `()` | A single MISRA rule violation. | `ci/misra_report/models.py:55` |
| `MisraSummary` | `()` | Aggregated MISRA analysis summary. | `ci/misra_report/models.py:80` |
| `ToolResult` | `()` | Result from a single MISRA analysis tool. | `ci/misra_report/models.py:109` |
| `ScannerRegistry` | `()` | 扫描器注册表（单例，模式与 RulesetRegistry 一致）。 | `ci/scanners/__init__.py:32` |
| `Violation` | `()` | 统一扫描器违规模型（对齐 misra_report 的 dict 契约）。 | `ci/scanners/base.py:52` |
| `ScannerResult` | `()` | 扫描器执行结果（原始输出 + 状态）。 | `ci/scanners/base.py:116` |
| `ScannerAdapter` | `(abc.ABC)` | 扫描器适配器抽象（三层模式 1：API/CLI 适配器）。 | `ci/scanners/base.py:185` |
| `CppcheckScannerAdapter` | `(ScannerAdapter)` | cppcheck --addon=misra 适配器（默认扫描器，C:2012 工具链）。 | `ci/scanners/cppcheck_adapter.py:67` |
| `LdraScannerAdapter` | `(ScannerAdapter)` | LDRA Testbed 适配器（CLI/文本解析）。 | `ci/scanners/ldra_adapter.py:63` |
| `McpScannerAdapter` | `(ScannerAdapter)` | MCP 网关扫描器适配器（薄封装：CLI/output_file + 宽容解析）。 | `ci/scanners/mcp_adapter.py:47` |
| `ParasoftScannerAdapter` | `(ScannerAdapter)` | Parasoft C/C++test 适配器（CLI/XML 解析，DTP REST API 后补）。 | `ci/scanners/parasoft_adapter.py:66` |
| `QacScannerAdapter` | `(ScannerAdapter)` | Helix QAC 适配器（CLI/文本解析）。 | `ci/scanners/qac_adapter.py:65` |
| `BaseRuleSet` | `(abc.ABC)` | 规则集抽象基类。 | `ci/rulesets/base.py:41` |
| `GscrCompositeRuleSet` | `(BaseRuleSet)` | GSCR 复合规则集 — 同时加载 C 和 C++ 企标规则。 | `ci/rulesets/composite.py:51` |
| `GscCRuleSet` | `(BaseRuleSet)` | GSCR C 语言企标规则集。 | `ci/rulesets/gscr_c.py:55` |
| `GscCppRuleSet` | `(BaseRuleSet)` | GSCR C++ 语言企标规则集。 | `ci/rulesets/gscr_cpp.py:47` |
| `MisraC2023RuleSet` | `(BaseRuleSet)` | MISRA C:2023 规则集。 | `ci/rulesets/misra.py:56` |
| `RulesetRegistry` | `()` | 规则集注册器（单例）。 | `ci/rulesets/registry.py:55` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CoverageConfig.effective_line` | `(self)` | — | `ci/config.py:212` |
| `CoverageConfig.effective_condition` | `(self)` | — | `ci/config.py:216` |
| `SkipDecision.to_dict` | `(self)` | — | `ci/diff_planner.py:94` |
| `Deviation.to_dict` | `(self)` | — | `ci/misra_deviations.py:53` |
| `Deviation.from_dict` | `(cls, d: dict)` | — | `ci/misra_deviations.py:57` |
| `FusionReport.merge` | `(cls, cppcheck: LayerResult, clang_tidy: LayerResult, ai_review: LayerResult)` | Merge three layers into a single cross-validated report. | `ci/misra_fusion.py:101` |
| `FusionReport.to_json` | `(self, output_path: str | Path)` | Save fused report as JSON. | `ci/misra_fusion.py:233` |
| `FusionReport.to_markdown` | `(self)` | Generate Markdown fusion report. | `ci/misra_fusion.py:246` |
| `CIResult.__init__` | `(self, layer: int, commit_hash: str)` | — | `ci/result.py:44` |
| `CIResult.add_stage` | `(self, name: str, status: str, detail: str)` | Record a stage result. | `ci/result.py:54` |
| `CIResult.complete` | `(self, status: str)` | Mark the CI layer as complete. | `ci/result.py:63` |
| `CIResult.to_dict` | `(self)` | — | `ci/result.py:68` |
| `BaseToolDriver.__init__` | `(self, project_dir: str, config: Optional[dict])` | — | `ci/tool_drivers.py:54` |
| `BaseToolDriver.name` | `(self)` | 工具名称标识符。 | `ci/tool_drivers.py:60` |
| `BaseToolDriver.parse` | `(self, raw_output: str)` | 解析工具的原始输出，返回违规列表。 | `ci/tool_drivers.py:65` |
| `BaseToolDriver.run` | `(self, target: str)` | 执行工具分析并返回原始输出。 | `ci/tool_drivers.py:76` |
| `BaseToolDriver.generate_report` | `(self, violations: list[dict])` | 从违规列表生成结构化报告。 | `ci/tool_drivers.py:92` |
| `BaseToolDriver.config` | `(self)` | 获取当前驱动配置。 | `ci/tool_drivers.py:103` |
| `BaseToolDriver.get_report_dir` | `(self)` | 获取标准报告输出目录。 | `ci/tool_drivers.py:107` |
| `CppcheckDriver.__init__` | `(self, project_dir: str, config: Optional[dict])` | — | `ci/tool_drivers.py:126` |
| `CppcheckDriver.name` | `(self)` | — | `ci/tool_drivers.py:134` |
| `CppcheckDriver.ruleset` | `(self)` | 获取当前关联的规则集实例。 | `ci/tool_drivers.py:138` |
| `CppcheckDriver.set_ruleset` | `(self, ruleset)` | 设置规则集实例。 | `ci/tool_drivers.py:142` |
| `CppcheckDriver.parse` | `(self, raw_output: str)` | 解析 cppcheck --addon=misra 输出。 | `ci/tool_drivers.py:156` |
| `CppcheckDriver.run` | `(self, target: str)` | 执行 cppcheck 分析。 | `ci/tool_drivers.py:164` |
| `CppcheckDriver.generate_report` | `(self, violations: list[dict])` | 从违规列表生成结构化 MISRA 报告。 | `ci/tool_drivers.py:236` |
| `CppcheckDriver.get_rule_definitions` | `(self)` | 加载 MISRA 规则定义。 | `ci/tool_drivers.py:278` |
| `CppcheckDriver.get_ruleset_info` | `(self)` | 获取关联规则集的元信息。 | `ci/tool_drivers.py:288` |
| `ClangTidyDriver.name` | `(self)` | — | `ci/tool_drivers.py:312` |
| `ClangTidyDriver.parse` | `(self, raw_output: str)` | 解析 clang-tidy 输出（Stub）。 | `ci/tool_drivers.py:315` |
| `ClangTidyDriver.run` | `(self, target: str)` | 执行 clang-tidy 分析（Stub）。 | `ci/tool_drivers.py:331` |
| `ClangTidyDriver.generate_report` | `(self, violations: list[dict])` | 生成 clang-tidy 结构化报告（Stub）。 | `ci/tool_drivers.py:347` |
| `Violation.to_dict` | `(self)` | — | `ci/stages/code_style.py:76` |
| `ScanResult.summary` | `(self)` | — | `ci/stages/code_style.py:94` |
| `MisraViolation.to_dict` | `(self)` | — | `ci/misra_report/models.py:66` |
| `MisraSummary.total_violations` | `(self)` | — | `ci/misra_report/models.py:87` |
| `MisraSummary.high_severity` | `(self)` | — | `ci/misra_report/models.py:91` |
| `MisraSummary.medium_severity` | `(self)` | — | `ci/misra_report/models.py:95` |
| `MisraSummary.low_severity` | `(self)` | — | `ci/misra_report/models.py:99` |
| `MisraSummary.passed` | `(self)` | — | `ci/misra_report/models.py:103` |
| `ScannerRegistry.__init__` | `(self)` | — | `ci/scanners/__init__.py:48` |
| `ScannerRegistry.register` | `(self, adapter_cls: type[ScannerAdapter], make_default: bool)` | 注册一个扫描器适配器类。 | `ci/scanners/__init__.py:71` |
| `ScannerRegistry.create` | `(self, name: str, **kwargs)` | 创建已注册适配器的实例。 | `ci/scanners/__init__.py:85` |
| `ScannerRegistry.get` | `(self, name: str | None)` | 获取适配器实例。name 缺省 = 默认（cppcheck）。 | `ci/scanners/__init__.py:95` |
| `ScannerRegistry.names` | `(self)` | 所有已注册扫描器名（排序）。 | `ci/scanners/__init__.py:100` |
| `ScannerRegistry.available` | `(self)` | 同 names()（对外命名统一）。 | `ci/scanners/__init__.py:104` |
| `ScannerRegistry.is_registered` | `(self, name: str)` | — | `ci/scanners/__init__.py:108` |
| `ScannerRegistry.reset` | `(self)` | 清空注册表并重建内置（测试用）。 | `ci/scanners/__init__.py:111` |
| `Violation.to_dict` | `(self)` | 序列化为 dict（与 parse_cppcheck_output 的 dict 契约兼容）。 | `ci/scanners/base.py:73` |
| `Violation.from_dict` | `(cls, d: dict)` | 从 dict 构造（parse_cppcheck_output 等现有解析器输出直接可用）。 | `ci/scanners/base.py:97` |
| `ScannerAdapter.detect` | `(self, project_dir: str, config: Any)` | 检测扫描器是否可用。默认 False（未配置/未安装）。 | `ci/scanners/base.py:201` |
| `ScannerAdapter.detect_hint` | `(self, project_dir: str, config: Any)` | detect 失败时的修复提示。 | `ci/scanners/base.py:205` |
| `ScannerAdapter.run` | `(self, project_dir: str, config: Any, target_files: list[str] | None, **kwargs)` | 执行扫描。config 为 MisraConfig（或 None），target_files 为待扫文件。 | `ci/scanners/base.py:210` |
| `ScannerAdapter.parse` | `(self, raw: str)` | 解析原始输出为统一违规列表。解析失败应返回 [] 并留 warning。 | `ci/scanners/base.py:223` |
| `ScannerAdapter.normalize` | `(self, violations: list[Violation], ruleset: Any)` | 映射工具特定规则 ID → misra-rules.yaml 规范 ID。 | `ci/scanners/base.py:226` |
| `CppcheckScannerAdapter.detect` | `(self, project_dir: str, config: Any)` | cppcheck 可执行文件存在即可用。 | `ci/scanners/cppcheck_adapter.py:73` |
| `CppcheckScannerAdapter.detect_hint` | `(self, project_dir: str, config: Any)` | — | `ci/scanners/cppcheck_adapter.py:82` |
| `CppcheckScannerAdapter.run` | `(self, project_dir: str, config: Any, target_files: list[str] | None, **kwargs)` | 构建并执行 cppcheck 命令（逻辑与 review_misra.py 原实现一致）。 | `ci/scanners/cppcheck_adapter.py:85` |
| `CppcheckScannerAdapter.parse` | `(self, raw: str)` | 解析 cppcheck 文本输出（复用 parse_cppcheck_output，含诚实归一化）。 | `ci/scanners/cppcheck_adapter.py:248` |
| `CppcheckScannerAdapter.normalize` | `(self, violations: list[Violation], ruleset: Any)` | cppcheck 解析已含规范 ID（parse_cppcheck_output 内归一化）， | `ci/scanners/cppcheck_adapter.py:258` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `ALM_API_TOKEN` | _(见源码)_ |
| `BRANCH_NAME` | _(见源码)_ |
| `BUILD_ID` | _(见源码)_ |
| `CI_LAYER1_TIMEOUT` | _(见源码)_ |
| `CI_STRICT` | _(见源码)_ |
| `COVERAGE_RUN` | _(见源码)_ |
| `GIT_COMMIT` | _(见源码)_ |
| `HOOK_TYPE` | _(见源码)_ |
| `JOB_NAME` | _(见源码)_ |
| `MISRA_FAIL_FAST` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |
| `WORKSPACE` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.ci`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/pipeline/orchestrator.py:451
from yuleosh.ci.profile import validate_active_profile, filter_steps_for_profile, get_current_profile

# src/yuleosh/pipeline/step_handlers/c_coverage_gate.py:470
from yuleosh.ci.gcov_coverage import generate_c_coverage_report

# src/yuleosh/pipeline/step_handlers/review_selftest/core.py:28
from yuleosh.ci.review_helpers import (

# src/yuleosh/pipeline/step_handlers/review_test_coverage.py:274
from yuleosh.ci.config import _get_ci_config

# src/yuleosh/pipeline/step_handlers/review.py:117
from yuleosh.ci.stages.code_style import format_style_rules_for_review

# src/yuleosh/pipeline/step_handlers/review_misra_ci.py:403
from yuleosh.ci.result import CIResult

# src/yuleosh/pipeline/async_runner.py:180
from yuleosh.ci import run_layer1 as _rl1

# src/yuleosh/spec/merge.py:711
from yuleosh.ci.config import load_ci_config, validate_misra_profiles

# src/yuleosh/cli/onboard.py:394
from yuleosh.ci.coverage_trend import show_coverage_trend

# src/yuleosh/cli/commands/misc.py:748
from yuleosh.ci.run import run_layer1, run_layer2, run_layer3

# src/yuleosh/cli/commands/misra.py:47
from yuleosh.ci.config import (

# src/yuleosh/cli/commands/methodology.py:159
from yuleosh.ci.stages.methodology_gate import run_methodology_gate

# src/yuleosh/cli/main.py:804
from yuleosh.ci.profile import get_profile_audit_log, record_profile_change

# src/yuleosh/hooks/pre_commit.py:327
from yuleosh.ci.stages.code_style import _load_rules, scan_file

```

> 共 14 个文件引用本子系统；完整调用图见 `docs/modules/ci.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 39 处生产引用(Grep `yuleosh.ci` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/ci/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
