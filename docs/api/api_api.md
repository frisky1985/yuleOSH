# Web API 层 (`api`) API 参考

> 代码根:`src/yuleosh/api/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`api` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/api.md` 若存在)。

## 2. HTTP 端点

`api` 包是 Web API 层自身,按资源分包(`api/<resource>.py` 各含 `handle_<resource>`),由 `api/router.py` 的 `ROUTES` / `_LAZY_HANDLERS` 注册。
**完整端点清单(方法 + 路径 + 处理函数 `文件:行`)见 `docs/modules/api.md` §2 路由模型(约 60+ 端点)**。

本包不新增独立顶层路由资源;各 `handle_*` 的内部子路径分发见对应模块文档(如 `docs/modules/pipeline.md`、`docs/modules/review.md`、`docs/modules/evidence.md` 等)。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `resolve_osh_home` | `(current: str | None)` | Resolve the effective ``OSH_HOME`` **at call time**. | `api/__init__.py:31` |
| `json_ok` | `(data: Any)` | Return a success JSON response. | `api/__init__.py:83` |
| `json_error` | `(msg: str | dict, status: int)` | Return an error JSON response (W-07 contract fix). | `api/__init__.py:88` |
| `read_body` | `(handler)` | Read and parse the request body based on Content-Type header. | `api/__init__.py:109` |
| `get_store` | `()` | Get the shared Store instance. | `api/__init__.py:163` |
| `internal_error` | `(module: str, e: BaseException, status: int)` | Log ``e`` under ``api.<module>`` and return a generic error tuple. | `api/_errors.py:17` |
| `handle_apikeys` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to api key sub-resources. | `api/apikeys.py:22` |
| `_generate_key` | `(body: dict)` | POST /api/v1/apikeys — generate a new API key. | `api/apikeys.py:34` |
| `_list_keys` | `()` | GET /api/v1/apikeys — list all API keys. | `api/apikeys.py:72` |
| `_revoke_key` | `(path_tail: str)` | DELETE /api/v1/apikeys/{id} — revoke an API key by ID. | `api/apikeys.py:85` |
| `_sessions_root` | `()` | Primary root directory holding per-run session folders. | `api/artifacts.py:114` |
| `_discover_nested_session_roots` | `(home: Path)` | Every ``<dir>/.osh/sessions`` under ``home`` (bounded to depth 5). | `api/artifacts.py:125` |
| `_ordered_unique` | `(paths)` | De-duplicate paths, keeping first-seen order. | `api/artifacts.py:155` |
| `_sessions_roots` | `()` | All roots that may contain per-run session dirs. | `api/artifacts.py:171` |
| `_q` | `(query: dict, key: str, default: str)` | Get a query parameter value (tolerates parse_qs list values). | `api/artifacts.py:215` |
| `_safe_run_id` | `(run_id: str)` | Reject run ids that could address paths outside the sessions dir. | `api/artifacts.py:223` |
| `_session_dir` | `(run_id: str)` | Return the session directory for a run, or None when unknown. | `api/artifacts.py:229` |
| `_session_meta` | `(session_dir: Path)` | Parse session.json for a run; {} when absent/corrupt (no crash). | `api/artifacts.py:244` |
| `_project_for_session` | `(session_dir: Path)` | Derive project_dir from a session_dir (``<project>/.osh/sessions/<run_id>``). | `api/artifacts.py:254` |
| `_iter_sessions` | `()` | Yield (run_id, session_dir, session_meta) for every session dir. | `api/artifacts.py:271` |
| `_session_matches_project` | `(meta: dict, project: str)` | Filter sessions by project fields in session.json (exact match). | `api/artifacts.py:291` |
| `_artifact_files` | `(session_dir: Path)` | List artifact files in a session dir (metadata + non-document files excluded). | `api/artifacts.py:302` |
| `_resolve_within` | `(session_dir: Path, rel_path: str)` | Resolve an artifact path and enforce it stays inside session_dir. | `api/artifacts.py:343` |
| `handle_artifacts` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/artifacts/... requests. | `api/artifacts.py:364` |
| `_artifacts_list` | `(query: dict)` | GET /api/v1/artifacts/list — artifact tree per pipeline run. | `api/artifacts.py:385` |
| `_artifacts_preview` | `(query: dict)` | GET /api/v1/artifacts/preview — read-only preview of one artifact. | `api/artifacts.py:464` |
| `_artifacts_evidence_pack` | `(query: dict)` | GET /api/v1/artifacts/evidence-pack — evidence pack file list for a run. | `api/artifacts.py:512` |
| `log_request` | `(method: str, path: str, status_code: int, ip: str, duration_ms: float)` | Record an API request in the audit log. | `api/audit.py:20` |
| `_ensure_table` | `()` | Create the audit_log table if it does not exist. | `api/audit.py:33` |
| `handle_audit` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | GET /api/v1/audit — list recent audit entries (admin/auditor only). | `api/audit.py:51` |
| `_extract_token` | `(headers: dict)` | Extract Bearer token from request headers. | `api/auth.py:71` |
| `_user_response` | `(user: dict, org: dict)` | Build the v1 user info response dict, stripping sensitive fields. | `api/auth.py:89` |
| `_login_user` | `(email: str, password: str, store: Store)` | Attempt to authenticate a user across all orgs. | `api/auth.py:103` |
| `handle_auth` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Auth REST API handler — register, login, me, logout. | `api/auth.py:129` |
| `_handle_register` | `(body: dict)` | Register a new user with email, password, and organization name. | `api/auth.py:155` |
| `_handle_login` | `(body: dict)` | Login with email and password. | `api/auth.py:185` |
| `_handle_me` | `(handler)` | Get current user info from JWT in Authorization header. | `api/auth.py:253` |
| `_handle_logout` | `(handler)` | Logout — invalidate the session token. | `api/auth.py:289` |
| `handle_ci` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to CI sub-resources. | `api/ci.py:20` |
| `_run_ci_layer` | `(layer: str)` | POST /api/v1/ci/run/{layer} — run a CI layer. | `api/ci.py:34` |
| `_list_ci_runs` | `()` | GET /api/v1/ci/runs — list all CI runs. | `api/ci.py:61` |
| `handle_compliance` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/compliance/... requests. | `api/compliance.py:31` |
| `_get_compliance_overview` | `()` | Build the compliance overview data for the dashboard. | `api/compliance.py:47` |
| `is_development` | `()` | Return True if running in development mode. | `api/cors.py:29` |
| `get_allowed_origins` | `()` | Return the full set of allowed origins. | `api/cors.py:34` |
| `get_cors_origin` | `(request_origin: Optional[str])` | Return the value for Access-Control-Allow-Origin header. | `api/cors.py:50` |
| `origin_is_allowed` | `(request_origin: Optional[str])` | Check if the given Origin is allowed (production mode always True). | `api/cors.py:77` |
| `_evidence_home` | `()` | Effective ``OSH_HOME`` for the evidence paths — resolved **at call time**. | `api/dashboard.py:42` |
| `_mock_note` | `()` | Return the demo data annotation. | `api/dashboard.py:280` |
| `handle_dashboard` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/dashboard/... requests. | `api/dashboard.py:287` |
| `_dashboard_projects` | `(query: dict, org_id: Any)` | GET /api/v1/dashboard/projects — list projects for the current org. | `api/dashboard.py:373` |
| `_dashboard_swe_status` | `(query: dict)` | GET /api/v1/dashboard/swe-status — SWE.1~SWE.6 compliance status. | `api/dashboard.py:423` |
| `_load_gap_items` | `()` | Load gap items from audit-manifest, with mock fallback. | `api/dashboard.py:455` |
| `_dashboard_gap_analysis` | `(query: dict)` | GET /api/v1/dashboard/gap-analysis — gap analysis for compliance. | `api/dashboard.py:528` |
| `_build_gap_detail` | `(item: dict)` | Augment a gap item with related info for the detail view. | `api/dashboard.py:577` |
| `_dashboard_gap_detail` | `(gap_id: str)` | GET /api/v1/dashboard/gap-analysis/{gap_id} — gap detail. | `api/dashboard.py:681` |
| `_dashboard_gap_run` | `(gap_id: str, body: dict)` | POST /api/v1/dashboard/gap-analysis/{gap_id}/run — trigger a remediation run. | `api/dashboard.py:700` |
| `_simulate_gap_run` | `(gap_id: str, run_id: str)` | Simulate a remediation run in the background. | `api/dashboard.py:751` |
| `_dashboard_gap_run_status` | `(gap_id: str, query: dict)` | GET /api/v1/dashboard/gap-analysis/{gap_id}/status — poll most-recent run. | `api/dashboard.py:805` |
| `_dashboard_gap_run_stream` | `(gap_id: str, query: dict, handler: Any)` | GET .../gap-analysis/{gap_id}/status/stream — SSE 推送单条修复进度。 | `api/dashboard.py:822` |
| `_dashboard_gap_batch_run` | `(body: dict)` | POST /api/v1/dashboard/gap-analysis/batch-run — bulk remediation. | `api/dashboard.py:856` |
| `_run_gap_batch` | `(batch_id: str, gap_ids: list[str])` | Sequentially remediate each gap in the batch, updating progress. | `api/dashboard.py:907` |
| `_dashboard_gap_batch_status` | `(batch_id: str)` | GET /api/v1/dashboard/gap-analysis/batch/{batch_id} — batch progress. | `api/dashboard.py:956` |
| `_dashboard_evidence_generate` | `(body: dict, query: dict)` | POST /api/v1/dashboard/evidence/generate — trigger evidence pack generation. | `api/dashboard.py:976` |
| `_run_evidence_task` | `(task_id: str, project_dir: str)` | Background worker for evidence pack generation (T11-SSE). | `api/dashboard.py:1033` |
| `_simulate_evidence_completion` | `(task_id: str)` | Simulate evidence generation completion when the actual command is not available. | `api/dashboard.py:1124` |
| `_public_task` | `(task: dict)` | Strip private bookkeeping keys (``_thread`` …) before serialising. | `api/dashboard.py:1152` |
| `_sse_stream` | `(handler: Any, event: str, snapshot_fn, is_done, interval: float, max_seconds: float)` | Generic SSE pump shared by the evidence / gap-batch streams (T11-SSE). | `api/dashboard.py:1161` |
| `_dashboard_evidence_status` | `(query: dict)` | GET /api/v1/dashboard/evidence/status — poll evidence pack generation status. | `api/dashboard.py:1206` |
| `_dashboard_evidence_stream` | `(query: dict, handler: Any)` | GET /api/v1/dashboard/evidence/stream — SSE 推送证据包生成进度（T11-SSE）。 | `api/dashboard.py:1221` |
| `_dashboard_llm_health` | `(query: dict)` | GET /api/v1/dashboard/llm-health — LLM provider 健康诊断（项⑪）。 | `api/dashboard.py:1248` |
| `_dashboard_gap_batch_stream` | `(batch_id: str, handler: Any)` | GET .../gap-analysis/batch/{batch_id}/stream — SSE 推送批量修复进度。 | `api/dashboard.py:1272` |
| `_dashboard_coverage` | `(query: dict)` | GET /api/v1/dashboard/coverage — coverage data for the dashboard. | `api/dashboard.py:1300` |
| `_get_query_param` | `(query: dict, key: str, default: str)` | Get a query parameter value. | `api/dashboard.py:1394` |
| `_find_latest_manifest` | `(project_id: str)` | Find the latest audit-manifest.json in the evidence directory. | `api/dashboard.py:1402` |
| `_build_swe_from_manifest` | `(swe_data: dict)` | Build SWE status response from audit-manifest data. | `api/dashboard.py:1415` |
| `_dashboard_misra_trend` | `(query: dict)` | GET /api/v1/dashboard/misra-trend — MISRA violation trend, distribution, and recent items. | `api/dashboard.py:1456` |
| `_estimate_swe_completed` | `(project: dict)` | Count completed SWE areas from the evidence pack manifest when available. | `api/dashboard.py:1605` |
| `handle_dashboard_v2` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/dashboard-v2/... requests. | `api/dashboard_v2.py:76` |
| `_overview` | `(query: dict, org_id: Any)` | GET /api/v1/dashboard-v2/overview — 数据座舱聚合。 | `api/dashboard_v2.py:106` |
| `_dimension_status` | `(score: float)` | 维度健康状态：>=80 good / >=60 warning / 其余 critical。 | `api/dashboard_v2.py:177` |
| `_misra_score` | `(violations: int)` | MISRA 维度分（0-100）：每个违规扣 5 分，20 个及以上归零。 | `api/dashboard_v2.py:186` |
| `_load_coverage` | `()` | 覆盖率 line_rate —— 复用现有 dashboard._dashboard_coverage。 | `api/dashboard_v2.py:193` |
| `_load_test_pass_rate` | `()` | 测试通过率 —— store.ci_runs 最近 TEST_PASS_RUN_LIMIT 次运行。 | `api/dashboard_v2.py:212` |
| `_load_misra_violations` | `()` | MISRA 违规数 —— .yuleosh/reports/misra-trend.jsonl 最近一条记录。 | `api/dashboard_v2.py:228` |
| `_find_manifest` | `()` | 定位最新 audit-manifest.json（对齐 dashboard.py 的候选路径）。 | `api/dashboard_v2.py:250` |
| `_load_traceability_score` | `()` | 需求追溯维度分（0-100）—— audit-manifest.traceability。 | `api/dashboard_v2.py:264` |
| `_load_evidence_score` | `()` | 证据完整性维度分（0-100）—— audit-manifest.integrity.total_artifacts。 | `api/dashboard_v2.py:296` |
| `_load_pipelines` | `()` | 流水线列表 —— store.pipelines（pipelines 表当前无 org 列，全局数据）。 | `api/dashboard_v2.py:312` |
| `_load_projects_count` | `(org_id: Any)` | 项目数 —— store.list_org_projects(org_id) 按当前用户组织过滤。 | `api/dashboard_v2.py:322` |
| `_load_device_summary` | `()` | 设备状态汇总 —— DeviceRegistry.list_devices() 按 state 聚合。 | `api/dashboard_v2.py:334` |
| `_recent_pipelines` | `(query: dict, org_id: Any)` | GET /api/v1/dashboard-v2/recent-pipelines — 最近 10 条流水线。 | `api/dashboard_v2.py:359` |
| `_device_status` | `(query: dict)` | GET /api/v1/dashboard-v2/device-status — 设备状态汇总（device.db）。 | `api/dashboard_v2.py:391` |
| `_classify_test_layer` | `(stage_name: str)` | 把 ci stage 名归类到三层测试之一（unit/integration/qualification）。 | `api/dashboard_v2.py:403` |
| `_tests_summary` | `(query: dict)` | GET /api/v1/dashboard-v2/tests-summary — 三层测试汇总。 | `api/dashboard_v2.py:412` |
| `_is_demo_enabled` | `()` | Check if demo pipeline is enabled (DEMO-REQ-003). | `api/demo.py:141` |
| `_generate_pipeline` | `(step_limit: int | None)` | Generate a mock pipeline response. | `api/demo.py:147` |
| `_generate_evidence_zip` | `(pipeline_id: str)` | Generate a mock evidence pack ZIP (DEMO-REQ-006). | `api/demo.py:190` |
| `_check_demo_rate_limit` | `(ip: str)` | Check rate limit per IP. Returns (allowed, retry_after_seconds). | `api/demo.py:255` |
| `handle_demo` | `(method: str, path_tail: str, body: dict, query: dict, handler: BaseHTTPRequestHandler)` | Route to /api/v1/demo/* endpoints (DEMO-REQ-002 through DEMO-REQ-006). | `api/demo.py:277` |
| `generate_demo_spec` | `(user_input: str)` | Generate a minimal OpenSpec markdown from a one-line requirement. | `api/demo_quick.py:40` |
| `_demo_mock_llm` | `(system_prompt: str, user_prompt: str, **kwargs)` | Mock LLM client returning plausible demo content. | `api/demo_quick.py:54` |
| `run_demo_pipeline_steps` | `(spec_path: str, project_dir: Path)` | Run all 10 pipeline steps directly with mock LLM. | `api/demo_quick.py:71` |
| `run_demo_pipeline` | `(user_input: str, work_dir: str)` | Run the full demo pipeline: spec gen -> pipeline -> evidence. | `api/demo_quick.py:120` |
| `main` | `(user_input: str, work_dir: str)` | CLI entry point for ``yuleosh demo quick <requirement>``. | `api/demo_quick.py:224` |
| `create_demo_project` | `(example: str, work_dir: str)` | Create the demo project directory with spec, tests, and minimal src. | `api/demo_wow.py:216` |
| `_write_demo_test` | `(test_path: Path, example: str)` | Write demo test file with Covers markers for traceability. | `api/demo_wow.py:294` |
| `run_wow_demo` | `(example: str, work_dir: str, do_build: bool)` | Run the full Wow Moment demo pipeline. | `api/demo_wow.py:477` |
| `main` | `(example: str, work_dir: str, do_build: bool)` | CLI entry point for ``yuleosh demo wow``. | `api/demo_wow.py:697` |
| `_device_db_path` | `()` | 设备 DB 路径：YULEOSH_DEVICE_DB 环境变量优先，否则 ~/.yuleosh/device.db。 | `api/device_ui.py:42` |
| `_get_registry` | `()` | 构造（或复用）DeviceRegistry 实例。 | `api/device_ui.py:49` |
| `_device_brief` | `(dev: Device)` | 设备列表/详情视图字段（UI 卡片所需最小集）。 | `api/device_ui.py:58` |
| `handle_device_ui` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/device-ui/... requests (module ⑥). | `api/device_ui.py:72` |
| `_device_list` | `()` | GET /api/v1/device-ui/list — 设备状态列表。 | `api/device_ui.py:103` |
| `_device_stats` | `()` | GET /api/v1/device-ui/stats — 按状态聚合的利用率汇总。 | `api/device_ui.py:114` |
| `_device_acquire` | `(device_id: str, body: dict, current_user: dict)` | POST /api/v1/device-ui/{id}/acquire — 手动分配设备。 | `api/device_ui.py:135` |
| `_device_release` | `(device_id: str, body: dict)` | POST /api/v1/device-ui/{id}/release — 释放设备。 | `api/device_ui.py:181` |
| `_device_events` | `(device_id: str)` | GET /api/v1/device-ui/{id}/events — 看门狗事件时间线（最近 50 条）。 | `api/device_ui.py:216` |
| `_parse_topics` | `(raw: Any)` | ``?topics=a,b,c`` → ``{'a','b','c'}``；空或缺省 → 所有 topic。 | `api/events.py:43` |
| `_write_sse` | `(handler, payload_text: str)` | 写一帧 SSE，捕获客户端断开（BrokenPipeError / ConnectionResetError）。 | `api/events.py:56` |
| `handle_events` | `(method: str, path_tail: str, body, query, handler)` | ``GET /api/v1/events/stream`` —— SSE 订阅入口。 | `api/events.py:71` |
| `_qp` | `(query: dict, key: str, default: str)` | Get a query parameter value (list-safe, like logs._qp). | `api/evidence.py:21` |
| `_ev_home` | `()` | Effective ``OSH_HOME`` for evidence paths — resolved **at call time**. | `api/evidence.py:29` |
| `handle_evidence` | `(method: str, path_tail: str, body: dict, query: dict, handler, **kwargs)` | Route to evidence sub-resources. | `api/evidence.py:44` |
| `_snapshot_pack` | `()` | Copy the freshly generated compliance-pack.zip to a timestamped version | `api/evidence.py:59` |
| `snapshot_bundle` | `(bundle_dir: str, osh_home: str | None)` | Zip an evidence *bundle directory* (e.g. `.yuleosh/evidence-bundle`) | `api/evidence.py:82` |
| `_generate_evidence` | `(body: dict)` | POST /api/v1/evidence/generate — run evidence generation. | `api/evidence.py:120` |
| `_list_evidence_files` | `()` | GET /api/v1/evidence/files — list generated evidence files. | `api/evidence.py:159` |
| `_list_evidence_history` | `()` | GET /api/v1/evidence/history — list versioned evidence pack snapshots. | `api/evidence.py:176` |
| `_download_pack` | `(handler, query: dict | None)` | GET /api/v1/evidence/pack — download compliance ZIP pack. | `api/evidence.py:207` |
| `_download_file` | `(handler, query: dict | None)` | GET /api/v1/evidence/file?name=<bare_name> — download one evidence file. | `api/evidence.py:273` |
| `handle_health` | `(method: str, **kwargs)` | GET /api/v1/health — return full system health status. | `api/health.py:27` |
| `_check_db` | `(store: Store)` | Verify database connectivity with SELECT 1. | `api/health.py:63` |
| `_check_store` | `(store: Store)` | Return counts from all store tables. | `api/health.py:75` |
| `_check_disk` | `()` | Check disk space on the .yuleosh/ directory. | `api/health.py:100` |
| `_auth_enabled` | `()` | — | `api/health.py:124` |
| `_extract_v1` | `(path: str)` | Strip /api/v1/ prefix, return the resource path. | `api/health.py:132` |
| `_get_kb_store` | `()` | Get or create the KbStore instance. | `api/kb.py:23` |
| `handle_kb` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route KB requests to sub-resource handlers. | `api/kb.py:29` |
| `_parse_id` | `(tail: str)` | Parse resource ID from path tail. Returns (id, remaining_path). | `api/kb.py:57` |
| `_handle_articles` | `(method: str, tail: str, body: dict, query: dict)` | — | `api/kb.py:68` |
| `_handle_lessons` | `(method: str, tail: str, body: dict, query: dict)` | — | `api/kb.py:123` |
| `_handle_fmea` | `(method: str, tail: str, body: dict, query: dict)` | — | `api/kb.py:191` |
| `_handle_hybrid_search` | `(method: str, tail: str, body: dict, query: dict, **kwargs)` | GET /api/v1/kb/search?q=... — 混合检索（EI-M4A: JWT 租户 SQL 层强制过滤）。 | `api/kb.py:250` |
| `_handle_unified_search` | `(method: str, tail: str, body: dict, query: dict, **kwargs)` | GET /api/v1/kb/unified?q=... — 三源联合召回（EI-M4B.1/.2）。 | `api/kb.py:327` |
| `_get_query_param` | `(query: dict, key: str, default: str)` | Get a single query parameter value. | `api/kb.py:403` |
| `handle_kg` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Main dispatcher for /api/v1/kg/* routes. Requires authentication. | `api/kg.py:22` |
| `_handle_impact` | `(handler, body: dict)` | Handle POST /api/v1/kg/query/impact. | `api/kg.py:45` |
| `handle_kg_impact` | `(handler, params: dict)` | Handler for POST /api/v1/kg/query/impact. | `api/kg_impact.py:44` |
| `_write_ok` | `(handler, data: dict)` | Write a 200 JSON response. | `api/kg_impact.py:122` |
| `_write_error` | `(handler, status: int, message: str)` | Write an error JSON response. | `api/kg_impact.py:132` |
| `_sessions_root` | `()` | Session 根目录：``OSH_SESSIONS_DIR`` 优先，否则 ``OSH_HOME/.osh/sessions``。 | `api/logs.py:53` |
| `_qp` | `(query: dict, key: str, default: str)` | Get a query parameter value (list-safe, like dashboard._get_query_param). | `api/logs.py:62` |
| `_detect_level` | `(line: str)` | 轻量级别识别：行内匹配 ERROR/FATAL/WARN/DEBUG/TRACE/INFO token。 | `api/logs.py:70` |
| `_load_session_meta` | `(run_dir: Path)` | 读取 run 的 session.json 元数据（缺失/损坏时降级为目录名）。 | `api/logs.py:79` |
| `_file_updated_at` | `(fp: Path)` | — | `api/logs.py:104` |
| `_meta_haystack` | `(meta: dict)` | 把 run 元数据拼成小写 haystack，供 project/pipeline 子串过滤。 | `api/logs.py:111` |
| `_to_dt` | `(s: Optional[str])` | 把 ISO/带时区字符串解析为 datetime（无时区按 UTC）。解析失败返回 None。 | `api/logs.py:116` |
| `_parse_window` | `(s: Optional[str], end_of_day: bool)` | 解析时间窗口参数（since/until）。 | `api/logs.py:129` |
| `handle_logs` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/logs... requests (module ⑦). | `api/logs.py:147` |
| `_collect_logs` | `(query: dict, limit: int)` | 按过滤条件扫描日志行，返回 ``(结果列表, 是否因达到 limit 被截断)``。 | `api/logs.py:167` |
| `_logs_search` | `(query: dict)` | GET /api/v1/logs — 跨 run 日志检索（子串匹配，轻量实现）。 | `api/logs.py:238` |
| `_logs_export` | `(query: dict)` | GET /api/v1/logs/export — 全量导出（过滤参数同 /logs，但忽略 limit）。 | `api/logs.py:268` |
| `_logs_pipeline` | `(query: dict)` | GET /api/v1/logs/pipeline?run=xxx — 单个 run 的全部日志。 | `api/logs.py:292` |
| `_logs_summary` | `(query: dict)` | GET /api/v1/logs/summary?project=xxx[&since=YYYY-MM-DD] — 每 run 的日志统计。 | `api/logs.py:338` |
| `_now_iso` | `()` | — | `api/loops.py:25` |
| `_hours_ago` | `(h: int)` | — | `api/loops.py:29` |
| `_days_ago` | `(d: int)` | — | `api/loops.py:33` |
| `get_loop1_data` | `()` | 返回缺陷→需求回溯轨迹数据。 | `api/loops.py:39` |
| `get_loop2_data` | `()` | 返回现场→FMEA 影响链数据。 | `api/loops.py:184` |
| `get_loop3_data` | `()` | 返回 KPI→RCA→改进状态数据。 | `api/loops.py:308` |
| `get_loop4_data` | `()` | 返回 KG 置信度分布数据。 | `api/loops.py:409` |
| `get_loop_data` | `(loop_id: int)` | 获取指定 Loop 的数据。 | `api/loops.py:495` |
| `get_all_loops_data` | `()` | 获取所有 Loop 的摘要数据。 | `api/loops.py:507` |
| `_scan_evidence` | `(proj_dir: Path, req_ids_upper: list[str])` | Return the set of requirement ids that appear in the project's | `api/matrix.py:56` |
| `_scan_artifact_coverage` | `(proj_dir: Path, req_ids_upper: list[str])` | One-pass scan of the whole project: req_id -> set of artifact types | `api/matrix.py:92` |
| `_empty_summary` | `()` | — | `api/matrix.py:131` |
| `_build_matrix` | `(reqs: list[dict], evidence_hits: set[str], artifact_coverage: dict[str, set[str]])` | Flatten ``generate_lrt`` requirement rows into a compact matrix row. | `api/matrix.py:144` |
| `_summarize` | `(rows: list[dict])` | — | `api/matrix.py:177` |
| `_build_gaps` | `(rows: list[dict])` | — | `api/matrix.py:194` |
| `handle_matrix` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Route /api/v1/matrix/... requests. | `api/matrix.py:220` |
| `_matrix` | `(query: dict, gaps_only: bool)` | GET /api/v1/matrix[?project=xxx] — build the traceability matrix. | `api/matrix.py:233` |
| `handle_me` | `(method: str, path_tail: str, body: Optional[dict], query: dict, handler: Any, **kwargs)` | Route /api/v1/me/* requests (current user account management). | `api/me.py:34` |
| `_get_account` | `(current_user: dict)` | Return the full account profile for the current user. | `api/me.py:58` |
| `_delete_account` | `(current_user: dict, body: dict)` | Soft-delete the current user account. | `api/me.py:111` |
| `_q` | `(query: dict, key: str, default: Any)` | Query param accessor — router passes lists (parse_qs), tests pass scalars. | `api/members.py:90` |
| `handle_members` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Route /api/v1/members/... requests (role management). | `api/members.py:99` |
| `_list_members` | `(org_id: Any, query: dict)` | GET /api/v1/members — org member list from the store users table. | `api/members.py:132` |
| `_invite_member` | `(org_id: Any, body: dict, current_user: dict)` | POST /api/v1/members/invite — invite {email, role} into the org. | `api/members.py:153` |
| `_update_role` | `(org_id: Any, user_id_str: str, body: dict, current_user: dict)` | PATCH /api/v1/members/{id} — change a member's role {role}. | `api/members.py:190` |
| `_delete_member` | `(org_id: Any, user_id_str: str, current_user: dict)` | DELETE /api/v1/members/{id} — 移除一名成员（仅 Owner/Admin）。 | `api/members.py:229` |
| `_default_matrix` | `()` | Build the design-doc default matrix as {role: {module: level}}. | `api/members.py:260` |
| `_roles_matrix` | `(current_user: dict)` | GET /api/v1/members/roles — role × module permission matrix. | `api/members.py:271` |
| `_roles_audit` | `(current_user: dict)` | GET /api/v1/members/roles/audit — 权限矩阵变更审计日志（T7）。 | `api/members.py:305` |
| `_update_roles` | `(current_user: dict, body: dict)` | PATCH /api/v1/members/roles — update the permission matrix. | `api/members.py:322` |
| `_apply_org_llm_override` | `(user: dict)` | Pin the org's LLM provider/model for the current request (v9). | `api/middleware.py:25` |
| `_resolve_local_dev_user` | `()` | AUTH_DISABLED 本地开发模式：构造一个 admin 用户注入，使依赖 | `api/middleware.py:45` |
| `_decode_token` | `(token: str)` | Decode and validate a JWT token. Returns payload or None. | `api/middleware.py:76` |
| `_extract_token` | `(headers)` | Extract Bearer token from request headers, falling back to the | `api/middleware.py:88` |
| `require_auth` | `(handler)` | Decorator: enforces JWT auth on a route handler. | `api/middleware.py:115` |
| `handle_notify` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to notification sub-resources. | `api/notify.py:11` |
| `_get_config` | `()` | GET /api/v1/notify/config — return current notification config. | `api/notify.py:23` |
| `_put_config` | `(body: dict)` | PUT /api/v1/notify/config — update notification config. | `api/notify.py:31` |
| `_check_trigger_throttle` | `()` | Return True if a new submission is allowed (sliding window). | `api/pipeline.py:31` |
| `_request_path` | `(kwargs: dict, path_tail: str)` | Return the request path WITH its query string. | `api/pipeline.py:45` |
| `handle_pipeline` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to pipeline sub-resources. | `api/pipeline.py:61` |
| `_publish_orchestrator_checkpoint` | `(project_dir: str, run_id: str, name: str, status: str, started_at: str, finished_at: str, session, emit_run_done: bool)` | 把编排器一次运行的结果回写为 CheckpointEngine 看板状态（打通两条链路）。 | `api/pipeline.py:222` |
| `_make_orchestrator_step_callback` | `(project_dir: str, run_id: str, name: str, rec: dict)` | 每步完成回调工厂: 实时把当前 session 步状态回写为看板 (不推 run_done)。 | `api/pipeline.py:314` |
| `_run_orchestrator_job` | `(run_id: str, spec_abs: str, project_dir: str, name: str)` | 后台线程：以 OSH_HOME=project_dir 运行编排器（聚焦源码 + 产物落在项目目录）。 | `api/pipeline.py:332` |
| `_build_starter_spec` | `(name: str)` | Minimal starter spec used when a project_dir has no spec.md yet. | `api/pipeline.py:381` |
| `_run_pipeline` | `(body: dict)` | POST /api/v1/pipeline/run — 一键运行某 spec 的真实编排器（后台）。 | `api/pipeline.py:415` |
| `_list_orchestrator_runs` | `()` | GET /api/v1/pipeline/jobs — 列出后台编排器运行任务（一键跑的运行记录）。 | `api/pipeline.py:524` |
| `_trigger_pipeline` | `(body: dict)` | POST /api/v1/pipeline/trigger — start a pipeline run. | `api/pipeline.py:532` |
| `_list_pipeline_steps` | `()` | GET /api/v1/pipeline/steps — list all pipeline step definitions. | `api/pipeline.py:599` |
| `_list_pipelines` | `()` | GET /api/v1/pipeline/status — list all pipeline sessions. | `api/pipeline.py:618` |
| `_resolve_pipeline_ctx` | `(body: dict)` | Resolve (pipeline_name, project_dir) from request body. | `api/pipeline.py:650` |
| `_run_engine_op` | `(pipeline_name: str, project_dir: str, op: str, step_id: str, selected: list[str] | None)` | 后台线程执行 CheckpointEngine 控制操作（retry/resume/rerun）。 | `api/pipeline.py:670` |
| `_retry_pipeline` | `(body: dict)` | POST /api/v1/pipeline/retry — retry from a specific step OR run selected steps. | `api/pipeline.py:764` |
| `_resume_pipeline` | `(body: dict)` | POST /api/v1/pipeline/resume — resume from first pending/failed step. | `api/pipeline.py:820` |
| `_rerun_pipeline` | `(body: dict)` | POST /api/v1/pipeline/rerun — 全量重跑（从头开始，_prepare_full）。 | `api/pipeline.py:851` |
| `_stop_pipeline` | `(body: dict)` | POST /api/v1/pipeline/stop — 请求停止当前运行（步骤边界生效）。 | `api/pipeline.py:886` |
| `handle_pipeline_steps` | `(method: str, **kwargs)` | GET /api/v1/pipeline/steps — return all pipeline step definitions. | `api/pipeline_steps.py:9` |
| `_parse_multipart_body` | `(handler: BaseHTTPRequestHandler)` | Extract binary file data from a multipart/form-data request. | `api/preview.py:117` |
| `_extract_zip_from_multipart` | `(raw: bytes, content_type: str)` | Extract the ZIP file content from a multipart body. | `api/preview.py:132` |
| `_is_valid_zip` | `(data: bytes)` | Check if data is a valid ZIP archive. | `api/preview.py:174` |
| `_validate_git_url` | `(url: str)` | Validate a git URL. Returns (valid, error_message). | `api/preview.py:179` |
| `_run_analysis` | `(source_dir: str | Path)` | Run the code analysis in a thread-safe manner. | `api/preview.py:201` |
| `_analyze_in_background` | `(preview_id: str, source_dir: Path)` | Run analysis in a background thread and store the result. | `api/preview.py:214` |
| `_handle_zip_upload` | `(preview_id: str, zip_data: bytes, handler)` | Handle ZIP upload analysis (PREVIEW-REQ-001A). | `api/preview.py:253` |
| `_handle_git_url` | `(preview_id: str, repo_url: str, handler)` | Handle git repo URL analysis (PREVIEW-REQ-001B). | `api/preview.py:338` |
| `_get_dir_size` | `(path: Path)` | Get total size of directory in bytes. | `api/preview.py:428` |
| `_check_preview_rate_limit` | `(ip: str, is_authenticated: bool)` | Check rate limit per IP (PREVIEW-REQ-005).  Atomic under lock. | `api/preview.py:452` |
| `_is_authed` | `(handler)` | Real authentication check for preview rate-limit tiers (P1-4). | `api/preview.py:486` |
| `_get_user_key` | `(handler)` | Derive the preview-cache owner key from the request identity (W-6). | `api/preview.py:510` |
| `_get_cached_preview` | `(repo_url: str, user_key: str)` | Check if a cached assessment result exists (PREVIEW-REQ-007). | `api/preview.py:549` |
| `_cleanup_expired_results` | `()` | Periodic cleanup of expired assessment results (PREVIEW-REQ-006). | `api/preview.py:575` |
| `handle_preview` | `(method: str, path_tail: str, body: dict, query: dict, handler: BaseHTTPRequestHandler)` | Route handler for /api/v1/preview/assess* endpoints. | `api/preview.py:605` |
| `handle_project` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to project sub-resources. | `api/project.py:19` |
| `_list_projects` | `(store)` | GET /api/v1/project — list all projects. | `api/project.py:44` |
| `_get_project` | `(store, name: str)` | GET /api/v1/project/{name} — get a specific project. | `api/project.py:54` |
| `_create_project` | `(store, body: dict, user: dict | None)` | POST /api/v1/project — create a new project. | `api/project.py:64` |
| `_lookup_org_project` | `(store, org_id: int, slug: str, name: str)` | Find an org-scoped project row. | `api/project.py:112` |
| `_ensure_user_project_spec` | `(proj: dict | None, name: str)` | Write a starter ``docs/spec.md`` under ``OSH_HOME/projects/<id>`` so a | `api/project.py:127` |
| `_build_user_spec_md` | `(name: str)` | Minimal starter spec for a user-created project so its pipeline can run. | `api/project.py:152` |
| `_build_demo_spec_yaml` | `(demo: dict)` | Render a demo project's spec YAML from its catalog entry. | `api/project.py:229` |
| `_write_demo_spec` | `(name: str, slug: str)` | Write a minimal sample spec YAML for the demo project; return its path. | `api/project.py:252` |
| `_migrate_existing_test_projects` | `(store, org_id: int)` | Promote the earlier E2E test shells (slug demo-pipe-x / demo-pipe-y) | `api/project.py:279` |
| `_seed_demo_project` | `(store, body: dict, user: dict | None)` | POST /api/v1/project/seed-demo — inject the ready-to-run demo catalog. | `api/project.py:299` |
| `_project_stats` | `(store)` | GET /api/v1/project/stats — aggregate project statistics. | `api/project.py:343` |
| `_resolve_project_dir` | `(project: str)` | Resolve ``OSH_HOME/projects/<project>`` with a path-traversal guard. | `api/projects_stats.py:55` |
| `_scan_evidence_count` | `(project_name: str)` | Count ASPICE document files in every session belonging to the project. | `api/projects_stats.py:77` |
| `handle_projects_stats` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Route ``GET /api/v1/projects-stats/stats`` requests. | `api/projects_stats.py:130` |
| `check_rate_limit` | `(ip: str)` | Check if the given IP has exceeded the rate limit. | `api/ratelimit.py:39` |
| `get_remaining` | `(ip: str)` | Return how many requests the IP can still make in the current window. | `api/ratelimit.py:64` |
| `reset` | `()` | Clear all rate-limit state (useful in tests). | `api/ratelimit.py:73` |
| `_env_limit` | `()` | Read the rate limit from env, falling back to the default. | `api/ratelimit_shared.py:52` |
| `default_db_path` | `()` | Resolve the default SQLite db path (env YULEOSH_RATE_DB → OSH_HOME → temp). | `api/ratelimit_shared.py:57` |
| `check_rate_limit_shared` | `(key: str, limit: int | None, window_seconds: int, db_path: str | None)` | Shared-store counterpart of ``api/ratelimit.check_rate_limit``. | `api/ratelimit_shared.py:226` |
| `get_remaining_shared` | `(key: str, limit: int | None, window_seconds: int, db_path: str | None)` | Shared-store counterpart of ``api/ratelimit.get_remaining``. | `api/ratelimit_shared.py:249` |
| `reset_shared` | `(db_path: str | None)` | Clear all shared rate-limit state (useful in tests). | `api/ratelimit_shared.py:260` |
| `_q` | `(query: dict, key: str, default: Any)` | Query param accessor — router passes lists (parse_qs), tests pass scalars. | `api/requirements.py:65` |
| `handle_requirements` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Route /api/v1/requirements/... requests. | `api/requirements.py:74` |
| `_resolve_project_dir` | `(project: str)` | Resolve OSH_HOME/projects/<project> with a path-traversal guard. | `api/requirements.py:95` |
| `_find_spec_files` | `(proj_dir: Path)` | Find spec*.md files for a project. | `api/requirements.py:115` |
| `_clean_stmt` | `(line: str)` | Strip markdown list markers / bold from a statement line. | `api/requirements.py:132` |
| `_parse_scenarios` | `(gwt_lines: list[tuple[str, str]])` | Group GIVEN/WHEN/THEN/AND lines into scenario dicts. | `api/requirements.py:140` |
| `_finalize` | `(current: dict, reqs: list[dict], seen: set)` | Flush a parsed requirement block into the result list (dedup by id). | `api/requirements.py:172` |
| `_parse_spec_text` | `(text: str, reqs: list[dict], seen: set)` | Regex-parse one spec file into requirement dicts (lightweight). | `api/requirements.py:195` |
| `_parse_requirements` | `(spec_files: list[Path])` | — | `api/requirements.py:230` |
| `_iter_project_files` | `(proj_dir: Path)` | Yield text-ish files under proj_dir, skipping dot/skip dirs. | `api/requirements.py:247` |
| `_is_text_file` | `(path: Path)` | — | `api/requirements.py:260` |
| `_classify_artifact` | `(path: Path, proj_dir: Path)` | Classify a referencing file as design / code / test / evidence. | `api/requirements.py:264` |
| `_referencing_artifacts` | `(proj_dir: Path, req_id: str, exclude_spec: bool)` | Scan proj_dir for files containing req_id (case-insensitive). | `api/requirements.py:277` |
| `_list_requirements` | `(query: dict)` | GET /api/v1/requirements — requirement list parsed from spec files. | `api/requirements.py:303` |
| `_trace` | `(req_id: str, query: dict)` | GET /api/v1/requirements/{req_id}/trace — traceability. | `api/requirements.py:324` |
| `_gaps` | `(query: dict)` | GET /api/v1/requirements/gaps — test/evidence gap analysis. | `api/requirements.py:341` |
| `handle_review` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to review sub-resources. | `api/review.py:20` |
| `_run_auto_review` | `(body: dict)` | POST /api/v1/review/auto — auto-review changed files. | `api/review.py:33` |
| `_run_task_review` | `(body: dict)` | POST /api/v1/review/task — review a specific task. | `api/review.py:56` |
| `_list_reviews` | `()` | GET /api/v1/review/list — list all review sessions. | `api/review.py:85` |
| `dispatch` | `(handler: BaseHTTPRequestHandler, path: str)` | Dispatch an API request to the appropriate handler. | `api/router.py:119` |
| `_respond` | `(handler: BaseHTTPRequestHandler, data: dict, status: int)` | Send a JSON response with security headers and CORS. | `api/router.py:217` |
| `handle_secrets` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to secret sub-resources. | `api/secrets.py:31` |
| `_set_secret` | `(body: dict)` | POST /api/v1/secrets — encrypt and store a provider secret. | `api/secrets.py:43` |
| `_list_secrets` | `()` | GET /api/v1/secrets — list metadata only (never plaintext). | `api/secrets.py:83` |
| `_delete_secret` | `(path_tail: str)` | DELETE /api/v1/secrets/{id} — delete a stored secret. | `api/secrets.py:92` |
| `handle_spec` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to spec sub-resources. | `api/spec.py:18` |
| `_validate` | `(method: str, body: dict)` | POST /api/v1/spec/validate — validate an OpenSpec file. | `api/spec.py:27` |
| `_diff` | `(method: str, body: dict)` | POST /api/v1/spec/diff — diff two OpenSpec files. | `api/spec.py:72` |
| `handle_stats` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Route to stats sub-resources. | `api/stats.py:20` |
| `_overview` | `()` | GET /api/v1/stats/overview — aggregated counts of everything. | `api/stats.py:33` |
| `_trends` | `(query: dict)` | GET /api/v1/stats/trends — daily or weekly trends. | `api/stats.py:59` |
| `_extract_token` | `(headers: dict)` | Extract Bearer token from request headers. | `api/subscription.py:38` |
| `_get_authenticated_org` | `(headers: dict)` | Get org_id from JWT token. Returns (org_id, user_id, org_slug) or raises. | `api/subscription.py:51` |
| `handle_subscription` | `(method: str, path_tail: str, body: dict, query: dict, **kwargs)` | Subscription REST API handler. | `api/subscription.py:80` |
| `_handle_sub_status` | `(handler)` | Get subscription status, trial info, and usage summary. | `api/subscription.py:106` |
| `_handle_sub_upgrade` | `(body: dict, handler)` | Create a Stripe Checkout session for upgrading. | `api/subscription.py:180` |
| `_handle_sub_cancel` | `(body: dict, handler)` | Cancel the current subscription (at period end). | `api/subscription.py:218` |
| `_handle_stripe_webhook` | `(body: dict, handler)` | Handle Stripe webhook events. | `api/subscription.py:272` |
| `_sessions_root` | `()` | Root directory holding per-run session folders. | `api/tests.py:70` |
| `_q` | `(query: dict, key: str, default: str)` | Get a query parameter value (tolerates parse_qs list values). | `api/tests.py:80` |
| `_safe_run_id` | `(run_id: str)` | Reject run ids that could address paths outside the sessions dir. | `api/tests.py:88` |
| `_session_meta` | `(session_dir: Path)` | Parse session.json for a run; {} when absent/corrupt (no crash). | `api/tests.py:94` |
| `_iter_sessions` | `()` | Yield (run_id, session_dir, session_meta) for every session dir. | `api/tests.py:104` |
| `_session_matches_project` | `(meta: dict, project: str)` | Filter sessions by project fields in session.json (exact match). | `api/tests.py:119` |
| `_first` | `(data: dict, keys: tuple[str, ...], default: Any)` | Return the first present value among candidate keys. | `api/tests.py:130` |
| `_as_int` | `(value: Any, default: int)` | — | `api/tests.py:138` |
| `_as_float` | `(value: Any, default: float)` | — | `api/tests.py:145` |
| `_extract_case_names` | `(data: dict)` | Collect test case names from common result-list shapes. | `api/tests.py:152` |
| `_parse_test_artifact` | `(path: Path, layer: str)` | Parse one test artifact JSON into a normalized run record. | `api/tests.py:179` |
| `_find_test_artifacts` | `(session_dir: Path, layer: str)` | Parse every test artifact of a layer present in a session dir. | `api/tests.py:211` |
| `_layer_note` | `(layer: str)` | — | `api/tests.py:224` |
| `_latest_layer_record` | `(layer: str)` | Latest parsed test artifact record for a .osh/sessions layer (newest first). | `api/tests.py:259` |
| `_ci_dir` | `()` | — | `api/tests.py:275` |
| `_newest_json` | `(ci_dir: Path, prefix: str)` | (data, mtime) of the newest ``prefix-*.json`` file, or None. | `api/tests.py:279` |
| `_hil_status` | `()` | Aggregate HIL (Layer 2.5) status from real .osh/ci artifacts. | `api/tests.py:300` |
| `_session_layer_record` | `(layer: str, project: str)` | Latest layer record filtered by project (None when absent). | `api/tests.py:355` |
| `_tests_layers` | `(query: dict)` | GET /api/v1/tests/layers — four-layer overview incl. HIL (Layer 2.5). | `api/tests.py:365` |
| `handle_tests` | `(method: str, path_tail: str, body: dict, query: dict, handler: Any, **kwargs)` | Handle /api/v1/tests/... requests. | `api/tests.py:422` |
| `_tests_cases` | `(query: dict)` | GET /api/v1/tests — test case listing with pass/fail/skip counts. | `api/tests.py:446` |
| `_tests_runs` | `(query: dict)` | GET /api/v1/tests/runs — execution history across all sessions. | `api/tests.py:499` |
| `_coverage_from_c_coverage` | `(data: dict)` | Extract line/branch rate from a c-coverage.json style report. | `api/tests.py:536` |
| `_coverage_from_coveragepy` | `(data: dict)` | Extract line/branch rate from a coverage.py JSON report. | `api/tests.py:549` |
| `_tests_coverage` | `(query: dict)` | GET /api/v1/tests/coverage — latest coverage summary. | `api/tests.py:561` |
| `handle_me` | `(method: str, path_tail: str, body: Optional[dict], query: dict, handler: Any, **kwargs)` | GET /api/v1/me/usage — current user usage summary for the cockpit panel. | `api/usage.py:29` |
| `handle_org` | `(method: str, path_tail: str, body: Optional[dict], query: dict, handler: Any, **kwargs)` | GET/PUT /api/v1/org/llm-config — org-pinned LLM provider/model. | `api/usage.py:61` |
| `validate_spec_path` | `(spec_path: Optional[str])` | Validate that a spec_path input is safe and refers to an existing file. | `api/validate.py:18` |
| `validate_pagination` | `(query: dict)` | Extract and validate pagination parameters from a query dict. | `api/validate.py:49` |
| `validate_json_body` | `(body: Any)` | Validate that the request body is a non-empty dict. | `api/validate.py:75` |
| `_verify_github_signature` | `(payload: Optional[bytes], signature_header: str)` | Verify X-Hub-Signature-256 HMAC-SHA256 against the raw payload. | `api/webhooks.py:32` |
| `_read_raw_body` | `(handler)` | Read the raw request body bytes for signature verification. | `api/webhooks.py:50` |
| `_build_repo_path_map` | `()` | Build a mapping of known repo names to their on-disk paths. | `api/webhooks.py:78` |
| `handle_webhooks` | `(method: str, path_tail: str, body: dict, query: dict, handler, **kwargs)` | Handle webhook-related API calls. | `api/webhooks.py:96` |
| `_handle_github_push` | `(payload: dict, handler)` | Process a GitHub push event payload and trigger pipeline via API. | `api/webhooks.py:136` |
| `_trigger_pipeline` | `(project_dir: str, repo_name: str, project_type: str, branch: str, commit_hash: str, commit_message: str)` | Trigger yuleOSH pipeline for the given commit. | `api/webhooks.py:216` |
| `_push_to_dashboard` | `(job_id: str, repo_name: str, branch: str, commit_hash: str, project_type: str)` | Push pipeline trigger event to dashboard store. | `api/webhooks.py:283` |
| `_get_org_id_from_handler` | `(handler)` | Extract org_id from JWT in the Authorization header. | `api/wizard.py:11` |
| `handle_wizard` | `(method: str, **kwargs)` | Handle wizard-related API calls. | `api/wizard.py:32` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `BadRequest` | `(Exception)` | Raised when a request body cannot be parsed. | `api/__init__.py:74` |
| `_PathTraversal` | `(Exception)` | Raised when a requested artifact path escapes its session directory. | `api/artifacts.py:99` |
| `_ThreadSafeDict` | `()` | A dict wrapper that serializes all access with a lock. | `api/preview.py:38` |
| `RateLimitStore` | `()` | Shared sliding-window rate-limit store backed by a single SQLite db. | `api/ratelimit_shared.py:68` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_ThreadSafeDict.__init__` | `(self)` | — | `api/preview.py:40` |
| `_ThreadSafeDict.get` | `(self, key, default)` | — | `api/preview.py:44` |
| `_ThreadSafeDict.clear` | `(self)` | Remove all entries (test isolation / state reset). | `api/preview.py:48` |
| `_ThreadSafeDict.pop` | `(self, key, default)` | — | `api/preview.py:53` |
| `_ThreadSafeDict.items` | `(self)` | — | `api/preview.py:73` |
| `_ThreadSafeDict.keys` | `(self)` | — | `api/preview.py:77` |
| `_ThreadSafeDict.get_and_update` | `(self, key, updater)` | Atomically get an entry and apply an update function. | `api/preview.py:81` |
| `RateLimitStore.__init__` | `(self, db_path: str | None, limit: int | None, window_seconds: int | None, clock: Callable[[], float] | None)` | — | `api/ratelimit_shared.py:83` |
| `RateLimitStore.check` | `(self, key: str, limit: int | None, window_seconds: int | None)` | Record one request for ``key``; return (allowed, remaining). | `api/ratelimit_shared.py:123` |
| `RateLimitStore.get_remaining` | `(self, key: str, limit: int | None, window_seconds: int | None)` | Return how many requests ``key`` can still make in the window. | `api/ratelimit_shared.py:174` |
| `RateLimitStore.window_remaining_seconds` | `(self, key: str, window_seconds: int)` | Seconds until the current window slides for ``key`` (0 when absent/expired). | `api/ratelimit_shared.py:198` |
| `RateLimitStore.reset` | `(self)` | Clear all rate-limit state (useful in tests). | `api/ratelimit_shared.py:216` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `LLM_API_KEY` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |
| `OSH_NO_ROOTS_CACHE` | _(见源码)_ |
| `STRIPE_SECRET_KEY` | _(见源码)_ |
| `YULEOSH_AUDIT_ROOT` | _(见源码)_ |
| `YULEOSH_CORS_ALLOWED_ORIGINS` | _(见源码)_ |
| `YULEOSH_DEMO_ENABLED` | _(见源码)_ |
| `YULEOSH_DEVICE_DB` | _(见源码)_ |
| `YULEOSH_ENV` | _(见源码)_ |
| `YULEOSH_LLM_PROVIDER` | _(见源码)_ |
| `YULEOSH_RATE_DB` | _(见源码)_ |
| `YULEOSH_RATE_LIMIT` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.api import <公共符号>
# 详见 docs/modules/api.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 25 处生产引用(Grep `yuleosh.api` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/api/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
