# 前端/UI 服务 (`ui`) API 参考

> 代码根:`src/yuleosh/ui/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`ui` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/ui.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `"tenant": ("yuleosh.ui.routes.tenant_routes", "handle_tenant"),` |
| `"tenants": ("yuleosh.ui.routes.tenant_routes", "handle_tenant_list"),` |
| `"billing": ("yuleosh.ui.routes.billing_routes", "handle_billing"),` |
| `"projects": ("yuleosh.ui.routes.project_routes", "handle_projects"),` |
| `from yuleosh.ui.auth_cookies import token_cookie_headers` |
| `IMPORTANT: These functions reference yuleosh.ui.server module-level` |
| ``from yuleosh.ui import server` so that unit test patches on` |
| `yuleosh.ui.server.* affect dispatch behavior correctly.` |
| `from yuleosh.ui.routes.http_response import (` |
| `References yuleosh.ui.server.check_rate_limit for test-patch compat.` |
| `from yuleosh.ui import server as _s` |
| `from yuleosh.ui import server as _s` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats` |
| `from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs_history` |
| `from yuleosh.ui.static_serving import _resolve_static_file` |
| `from yuleosh.ui import server as _s` |
| `from yuleosh.ui.routes.pipeline_routes import handle_pipeline_trigger` |
| `from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify` |
| `from yuleosh.ui import server as _s` |
| `from yuleosh.ui.auth_extended import get_session_user` |
| `from yuleosh.ui.auth_extended import resolve_session` |
| `from yuleosh.ui.routes.http_response import (` |
| `from yuleosh.ui.routes.auth_routes import (` |
| `from yuleosh.ui.routes.page_routes import (` |
| `from yuleosh.ui.routes.api_routes import (` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.http_response import _send_security_headers` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.routes.http_response import _send_security_headers` |
| `from yuleosh.ui.routes.tenant_routes import _require_auth` |
| `from yuleosh.ui.auth_extended import get_session_user` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `api_v1_dispatch` | `(handler: BaseHTTPRequestHandler, path: str)` | Dispatch /api/v1/* requests to the modular router. | `ui/api_dispatch.py:17` |
| `_get_health` | `(self)` | — | `ui/api_dispatch.py:50` |
| `_get_status` | `(self)` | — | `ui/api_dispatch.py:54` |
| `_list_evidence` | `(self)` | — | `ui/api_dispatch.py:58` |
| `_get_reviews` | `(self)` | — | `ui/api_dispatch.py:62` |
| `_get_ci_results` | `(self)` | — | `ui/api_dispatch.py:66` |
| `_handle_api` | `(self, action: str)` | — | `ui/api_dispatch.py:70` |
| `_handle_login` | `(self)` | — | `ui/api_dispatch.py:79` |
| `_generate_session_token` | `()` | — | `ui/auth.py:48` |
| `_session_sig` | `(token: str)` | HMAC-sign a session token with the API key so sessions can't be forged. | `ui/auth.py:52` |
| `create_session` | `()` | Create a new session. Returns (token, cookie_value). | `ui/auth.py:58` |
| `validate_session` | `(cookie_val: str)` | Validate a signed session cookie. Returns True if valid. | `ui/auth.py:66` |
| `cleanup_sessions` | `()` | Remove expired sessions from memory. | `ui/auth.py:89` |
| `is_authenticated` | `(headers: dict)` | Check if the request carries a valid API key, session cookie, or | `ui/auth.py:192` |
| `get_login_page` | `(error: str)` | Return the login page HTML with optional error message. | `ui/auth.py:251` |
| `_secure_enabled` | `()` | True when the Secure attribute should be set. | `ui/auth_cookies.py:36` |
| `make_auth_cookie` | `(name: str, value: str, max_age: Optional[int])` | Build a tenant auth Set-Cookie header value. | `ui/auth_cookies.py:50` |
| `token_cookie_headers` | `(access: str, refresh: str)` | Set-Cookie header values for a fresh access+refresh pair (T1.1). | `ui/auth_cookies.py:68` |
| `org_setup_cookie_headers` | `(setup_token: str)` | Set-Cookie for the needs_org (pre-user) flow (T1 v3.9.0, T-T1-19). | `ui/auth_cookies.py:78` |
| `clear_cookie_headers` | `()` | Set-Cookie header values that delete both tenant cookies (T1.6). | `ui/auth_cookies.py:93` |
| `read_cookie_value` | `(headers, name: str)` | Extract a cookie value from request headers (dict or object). | `ui/auth_cookies.py:101` |
| `_validate_password_strength` | `(password: str)` | Validate password strength. Returns list of error messages (empty = valid). | `ui/auth_extended.py:67` |
| `_check_rate_limit` | `(email: str)` | Check whether the email is currently blocked. Returns True if blocked. | `ui/auth_extended.py:163` |
| `_record_failed_attempt` | `(email: str)` | Record one FAILED signin attempt for the email (P1-2). | `ui/auth_extended.py:189` |
| `_check_and_record_failed_attempt` | `(email: str)` | Atomically check the email budget AND record a failure (W-2). | `ui/auth_extended.py:210` |
| `_check_ip_rate_limit` | `(ip: str)` | Per-IP signin attempt cap (P1-2). Returns True if blocked. | `ui/auth_extended.py:238` |
| `_cleanup_stale_rate_entries` | `()` | Remove rate-limit entries older than the window. | `ui/auth_extended.py:271` |
| `_cleanup_stale_ip_entries` | `()` | Remove IP-limit entries older than the IP window (W-2). | `ui/auth_extended.py:283` |
| `_hash_password` | `(password: str)` | Hash password with bcrypt (12 rounds). Returns hashed string. | `ui/auth_extended.py:293` |
| `_verify_password` | `(password: str, hashed: str)` | Verify password against bcrypt hash. Constant-time comparison. | `ui/auth_extended.py:299` |
| `_generate_token` | `(user_id: int, org_id: int, email: str, purpose: Optional[str], ttl_hours: float)` | Generate a signed JWT with embedded user/org claims and expiration. | `ui/auth_extended.py:312` |
| `_decode_token` | `(token: str)` | Decode and validate JWT. Returns payload dict or None if invalid/expired. | `ui/auth_extended.py:341` |
| `_slugify` | `(text: str)` | — | `ui/auth_extended.py:351` |
| `_is_refresh_token` | `(payload: dict)` | T1 (v3.9.0): True when the JWT is a refresh token (purpose="refresh"). | `ui/auth_extended.py:355` |
| `_issue_token_pair` | `(store: Store, user_id: int, org_id: int, email: str)` | T1 (v3.9.0): issue an access + refresh token pair (dual httpOnly cookies). | `ui/auth_extended.py:367` |
| `verify_token` | `(token: str)` | Unified bearer-token verify (A1, SHALL-A1.2). | `ui/auth_extended.py:387` |
| `resolve_session` | `(handler)` | Resolve the current user from a request handler, cookie-aware. | `ui/auth_extended.py:449` |
| `get_session_user` | `(token: str)` | Resolve a bearer token to a user dict with org info. | `ui/auth_extended.py:482` |
| `register` | `(body: dict)` | Unified v1 register — org + admin user + token (A1, SHALL-A1.4). | `ui/auth_extended.py:521` |
| `ensure_demo_account` | `(store: 'Store')` | Ensure the demo account exists with the documented credentials. | `ui/auth_extended.py:575` |
| `ensure_view_test_accounts` | `(store: 'Store')` | Seed two role-based test accounts so the dual dashboard view can be | `ui/auth_extended.py:625` |
| `_seed_view_account` | `(store: 'Store', org_id: int, email: str, role: str, password: str)` | Create or repair a single view-test account (idempotent). | `ui/auth_extended.py:649` |
| `handle_signin` | `(body: dict, ip: str)` | POST /api/auth/signin — Password-based signin/signup. | `ui/auth_extended.py:667` |
| `handle_org_create` | `(body: dict, session_token: str)` | POST /api/org/create - Create organization and first project. | `ui/auth_extended.py:761` |
| `handle_refresh` | `(refresh_token: str)` | POST /api/auth/refresh — issue a new access+refresh pair (T1.5). | `ui/auth_extended.py:823` |
| `handle_session_info` | `(session_token: str)` | GET /api/auth/session - Get current session info. | `ui/auth_extended.py:871` |
| `handle_logout` | `(session_token: str)` | POST /api/auth/logout - Invalidate session. | `ui/auth_extended.py:894` |
| `handle_project_list` | `(session_token: str)` | GET /api/project/list - List projects for user's org. | `ui/auth_extended.py:906` |
| `handle_project_create` | `(body: dict, session_token: str)` | POST /api/project/create - Create a new project in user's org. | `ui/auth_extended.py:923` |
| `handle_org_info` | `(session_token: str)` | GET /api/org/info - Get org info including member list. | `ui/auth_extended.py:948` |
| `_create_login_response` | `(store: Store, user: dict)` | Create a session for the user and return the response. | `ui/auth_extended.py:977` |
| `main` | `(host: str | None, port: int | None)` | — | `ui/http_app.py:23` |
| `_format_csp` | `(directives: dict)` | Serialize a {directive: [sources]} dict into a CSP header value. | `ui/http_security.py:43` |
| `_base_csp_directives` | `(nonce: str)` | The strict base policy — single source for every HTML response. | `ui/http_security.py:50` |
| `_csp_for_html` | `(nonce: str, html: bytes)` | Build the CSP for one HTML response. | `ui/http_security.py:97` |
| `_inject_csp_nonce` | `(html: bytes)` | Rewrite inline <script> tags with a per-request nonce (B5 ①). | `ui/http_security.py:119` |
| `check_rate_limit_memory` | `(client_ip: str, max_requests: int, window: float)` | In-memory rate limit check — kept for tests / single-process fallback. | `ui/http_security.py:141` |
| `check_rate_limit` | `(client_ip: str, max_requests: int, window: float)` | Check if client_ip is within rate limits.  Returns (allowed, retry_after). | `ui/http_security.py:159` |
| `_add_security_headers` | `(self)` | — | `ui/http_security.py:190` |
| `_static_export_dir` | `()` | Locate the Next.js export dir (frontend/out/), or None when absent. | `ui/static_serving.py:31` |
| `_resolve_static_file` | `(path: str)` | Resolve a URL path to a real file under frontend/out/, or None. | `ui/static_serving.py:55` |
| `_serve_static` | `(self, path: str)` | Serve a static file from frontend/out/. | `ui/static_serving.py:95` |
| `_is_immutable_asset` | `(file_path: Path)` | True for content-hashed build artifacts (M-2). | `ui/static_serving.py:157` |
| `_serve_file` | `(self, file_path: Path, content_type: str)` | Serve a file by its absolute path. | `ui/static_serving.py:175` |
| `_serve_page` | `(self, template_name: str, context: dict)` | Render a dashboard template page. | `ui/static_serving.py:203` |
| `handle_status` | `(handler: BaseHTTPRequestHandler)` | Return basic server status. | `ui/routes/api_routes.py:17` |
| `handle_health` | `(handler: BaseHTTPRequestHandler)` | Return health check data. | `ui/routes/api_routes.py:34` |
| `list_evidence` | `(handler: BaseHTTPRequestHandler)` | List evidence files from the .osh/evidence directory. | `ui/routes/api_routes.py:64` |
| `list_reviews` | `(handler: BaseHTTPRequestHandler)` | List review sessions from the .osh/reviews directory. | `ui/routes/api_routes.py:87` |
| `list_ci_results` | `(handler: BaseHTTPRequestHandler)` | List CI layer results from the .osh/ci directory. | `ui/routes/api_routes.py:110` |
| `handle_pipeline_status` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/status/{job_id} | `ui/routes/api_routes.py:122` |
| `handle_usage` | `(handler: BaseHTTPRequestHandler)` | Get current org usage summary. | `ui/routes/api_routes.py:136` |
| `handle_auth_check` | `(handler: BaseHTTPRequestHandler)` | Check authentication. Returns True if allowed, False if denied (response sent). | `ui/routes/auth_routes.py:17` |
| `handle_auth_login` | `(handler: BaseHTTPRequestHandler)` | Handle POST /_auth/login — validate API key and set session cookie. | `ui/routes/auth_routes.py:57` |
| `handle_api_action` | `(handler: BaseHTTPRequestHandler, action: str)` | Dispatch to tenant auth or org/project handlers. | `ui/routes/auth_routes.py:91` |
| `_read_body` | `(handler: BaseHTTPRequestHandler)` | Read and parse the request body (P1-5: unified clamped read_body). | `ui/routes/auth_routes.py:195` |
| `_auth_cookie_headers` | `(result: dict)` | T1 (v3.9.0): convert a login response's tokens into Set-Cookie values. | `ui/routes/auth_routes.py:209` |
| `_clear_cookie_headers` | `()` | T1 (v3.9.0): Set-Cookie values that delete both tenant cookies. | `ui/routes/auth_routes.py:226` |
| `_get_bearer_token` | `(handler: BaseHTTPRequestHandler)` | Extract bearer token from Authorization header, with cookie fallback. | `ui/routes/auth_routes.py:232` |
| `_send_json_response` | `(handler: BaseHTTPRequestHandler, data, status: int, set_cookies: Optional[list])` | Send a JSON response via handler's standard mechanism. | `ui/routes/auth_routes.py:248` |
| `_send_json_error` | `(handler: BaseHTTPRequestHandler, message: str, status: int)` | Send an error JSON response. | `ui/routes/auth_routes.py:276` |
| `_get_token` | `(handler)` | — | `ui/routes/billing_routes.py:28` |
| `_require_auth` | `(handler)` | — | `ui/routes/billing_routes.py:35` |
| `_auth_error` | `(handler)` | 401 — exact legacy body for a missing vs invalid session. | `ui/routes/billing_routes.py:40` |
| `_get_tenant_slug` | `(user_info: dict)` | — | `ui/routes/billing_routes.py:47` |
| `handle_billing` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | Dispatcher for /api/v1/billing/* (A3, B7). | `ui/routes/billing_routes.py:51` |
| `handle_get_usage` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/billing/usage — Get current month usage. | `ui/routes/billing_routes.py:69` |
| `handle_get_plan` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/billing/plan — Get current plan and available plans. | `ui/routes/billing_routes.py:150` |
| `handle_upgrade_plan` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | POST /api/v1/billing/upgrade — Upgrade tenant plan. | `ui/routes/billing_routes.py:193` |
| `rate_limit_check` | `(handler)` | Check rate limiting. Sends 429 if denied, returns False. | `ui/routes/handler_helpers.py:36` |
| `_send_auth_denied` | `(handler)` | Respond to an unauthenticated request (SEC-C3 fail-closed). | `ui/routes/handler_helpers.py:63` |
| `_api_v1_full_path` | `(parsed, path: str)` | Re-attach the query string to the normalized path before v1 dispatch. | `ui/routes/handler_helpers.py:85` |
| `handle_get` | `(handler)` | Route and serve all GET requests (non-API-v1 routes). | `ui/routes/handler_helpers.py:101` |
| `handle_post` | `(handler)` | Route and serve all POST requests (non-API-v1 routes). | `ui/routes/handler_helpers.py:283` |
| `handle_delete` | `(handler)` | Route and serve all DELETE requests. | `ui/routes/handler_helpers.py:339` |
| `handle_options` | `(handler)` | Serve OPTIONS preflight response. | `ui/routes/handler_helpers.py:367` |
| `log_audit` | `(handler)` | Persist the current request to the audit_log table. | `ui/routes/handler_helpers.py:392` |
| `_compute_etag` | `(content: bytes)` | Return a weak ETag for the given content. | `ui/routes/http_response.py:18` |
| `_format_http_datetime` | `(timestamp: float)` | Format a Unix timestamp as an HTTP-date string (RFC 7231). | `ui/routes/http_response.py:23` |
| `_parse_http_datetime` | `(date_str: str)` | Parse an HTTP-date string back to a Unix timestamp. | `ui/routes/http_response.py:30` |
| `_send_gzipped_json` | `(handler, data: dict, status: int)` | Send a JSON response with gzip compression and CORS headers. | `ui/routes/http_response.py:41` |
| `_add_cors_header` | `(handler)` | Set Access-Control-Allow-Origin based on request Origin and env. | `ui/routes/http_response.py:58` |
| `_send_security_headers` | `(handler)` | Send security headers on the given handler. | `ui/routes/http_response.py:71` |
| `serve_page` | `(handler: BaseHTTPRequestHandler, name: str, context: dict)` | Serve an HTML page from the pages/ directory, with simple template substitution. | `ui/routes/page_routes.py:23` |
| `serve_file` | `(handler: BaseHTTPRequestHandler, filepath: Path, mime: str)` | Serve a static file with caching and security headers. | `ui/routes/page_routes.py:72` |
| `_send_html_response` | `(handler: BaseHTTPRequestHandler, content: str, status: int)` | Send an HTML response. | `ui/routes/page_routes.py:113` |
| `_send_json_error` | `(handler: BaseHTTPRequestHandler, message: str, status: int)` | Send an error JSON response. | `ui/routes/page_routes.py:124` |
| `handle_pipeline_trigger` | `(handler: BaseHTTPRequestHandler, body: bytes)` | POST /api/v1/pipeline/trigger — Start a new pipeline run. | `ui/routes/pipeline_routes.py:32` |
| `handle_pipeline_status` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/status/<job_id> — Get job status. | `ui/routes/pipeline_routes.py:127` |
| `handle_pipeline_runs` | `(handler: BaseHTTPRequestHandler)` | GET /api/v1/pipeline/runs — List recent pipeline runs. | `ui/routes/pipeline_routes.py:160` |
| `handle_pipeline_stats` | `(handler: BaseHTTPRequestHandler)` | GET /api/v1/pipeline/stats — Aggregate pipeline statistics. | `ui/routes/pipeline_routes.py:182` |
| `handle_pipeline_usage` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/usage — Pipeline LLM token consumption by run. | `ui/routes/pipeline_routes.py:189` |
| `handle_yuleasr_status` | `(handler: BaseHTTPRequestHandler)` | GET /api/v1/pipeline/yuleasr-status — yuleASR BSW project live status. | `ui/routes/pipeline_routes.py:249` |
| `handle_yuleasr_notify` | `(handler: BaseHTTPRequestHandler, body: bytes)` | POST /api/v1/pipeline/yuleasr-notify — Send yuleASR pipeline result notification. | `ui/routes/pipeline_routes.py:354` |
| `_scan_project_checkpoints` | `(project_dir: str)` | 扫描单个项目目录下的全部 pipeline checkpoint 记录。 | `ui/routes/pipeline_routes.py:414` |
| `_iter_project_dirs` | `(osh_home: str)` | 发现 OSH_HOME 下含 pipeline checkpoint 状态的项目目录（B5.2）。 | `ui/routes/pipeline_routes.py:481` |
| `_iter_runnable_projects` | `(osh_home: str)` | 发现 OSH_HOME 下含 ``docs/spec.md`` 的可运行项目（一键跑数据源）。 | `ui/routes/pipeline_routes.py:524` |
| `handle_pipeline_list` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/list — 列出可用 pipeline（看板选择器数据源）。 | `ui/routes/pipeline_routes.py:577` |
| `handle_pipeline_checkpoint` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/checkpoint — CheckpointEngine 24 步实时状态（看板数据源）。 | `ui/routes/pipeline_routes.py:698` |
| `handle_pipeline_runs_history` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/checkpoint/runs — 列出某 pipeline 的历史运行记录。 | `ui/routes/pipeline_routes.py:801` |
| `_load_run_row` | `(engine, run_id: str)` | 读取单条运行记录（含快照）；异常时返回 None（看板容错）。 | `ui/routes/pipeline_routes.py:830` |
| `_parse_snapshot` | `(row: dict)` | 把 run 记录的 snapshot 字段解析成 checkpoint state dict。 | `ui/routes/pipeline_routes.py:839` |
| `_resolve_artifact_path` | `(path_str: str, project_dir: str)` | 产物路径解析：相对路径按 project_dir 补齐。 | `ui/routes/pipeline_routes.py:852` |
| `_inside_osh_home` | `(path: Path)` | 产物必须落在 OSH_HOME 内（防任意文件读取 / 打包外泄）。 | `ui/routes/pipeline_routes.py:858` |
| `_run_evidence` | `(row: dict, project_dir: str)` | 把一次运行整理成「证据包」摘要：执行记录 + 产物清单。 | `ui/routes/pipeline_routes.py:868` |
| `handle_pipeline_evidence` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/evidence — 证据包历史（每次运行一条，含产物清单）。 | `ui/routes/pipeline_routes.py:922` |
| `handle_pipeline_evidence_download` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/evidence/download?run_id=xxx — 打包下载证据包（zip）。 | `ui/routes/pipeline_routes.py:961` |
| `_latest_checkpoint_payload` | `(project_dir: str, pipeline_name: str)` | 读取最新 checkpoint 状态（state + steps + op_active），HTTP 与 SSE 共用。 | `ui/routes/pipeline_routes.py:1049` |
| `handle_pipeline_checkpoint_stream` | `(handler: BaseHTTPRequestHandler, path: str)` | GET /api/v1/pipeline/checkpoint/stream — SSE 推送 checkpoint 状态。 | `ui/routes/pipeline_routes.py:1088` |
| `_get_token` | `(handler)` | — | `ui/routes/project_routes.py:38` |
| `_require_auth` | `(handler)` | — | `ui/routes/project_routes.py:45` |
| `_auth_error` | `(handler)` | 401 — exact legacy body for a missing vs invalid session. | `ui/routes/project_routes.py:50` |
| `_get_tenant_slug` | `(user_info: dict)` | Get tenant slug from user info, falling back to org info. | `ui/routes/project_routes.py:57` |
| `_new_project` | `(name: str, description: str, owner: str)` | — | `ui/routes/project_routes.py:69` |
| `handle_projects` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | Dispatcher for /api/v1/projects (plural, A3/B7). | `ui/routes/project_routes.py:88` |
| `handle_list_projects` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/projects — List projects for the caller's tenant. | `ui/routes/project_routes.py:109` |
| `handle_get_project` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/projects/{slug} — Get project detail. | `ui/routes/project_routes.py:123` |
| `handle_create_project` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | POST /api/v1/projects — Create a new project. | `ui/routes/project_routes.py:151` |
| `handle_update_project` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | POST /api/v1/projects/{slug} — Update project or move kanban items. | `ui/routes/project_routes.py:188` |
| `_get_bearer_token` | `(handler)` | — | `ui/routes/tenant_routes.py:26` |
| `_require_auth` | `(handler)` | Extract and validate session. Returns user info dict or None. | `ui/routes/tenant_routes.py:33` |
| `_auth_error` | `(handler)` | 401 — exact legacy body for a missing vs invalid session (SHALL-A3.4). | `ui/routes/tenant_routes.py:51` |
| `handle_tenant` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | Dispatcher for /api/v1/tenant/* (A3, B7). | `ui/routes/tenant_routes.py:60` |
| `handle_tenant_info` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/tenant/{slug} — Get tenant info. | `ui/routes/tenant_routes.py:90` |
| `handle_tenant_update` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | PUT /api/v1/tenant/{slug} — Update tenant settings. | `ui/routes/tenant_routes.py:114` |
| `handle_tenant_list` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/tenants — List all tenants (admin only). | `ui/routes/tenant_routes.py:137` |
| `handle_tenant_projects` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/tenant/{slug}/projects — List projects for a tenant. | `ui/routes/tenant_routes.py:160` |
| `handle_tenant_project_create` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | POST /api/v1/tenant/{slug}/projects — Create a project. | `ui/routes/tenant_routes.py:173` |
| `handle_usage_check` | `(method: str, path_tail: str, body: dict, query: dict, handler)` | GET /api/v1/tenant/{slug}/usage — Check current usage vs limits. | `ui/routes/tenant_routes.py:196` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_ThreadSafeDict` | `()` | A dict wrapper that serializes all access with a lock. | `ui/auth_extended.py:94` |
| `HTTPServer` | `(ThreadingHTTPServer)` | Thread-per-request HTTP server for the dashboard (T10). | `ui/server.py:76` |
| `OSHHandler` | `(BaseHTTPRequestHandler)` | HTTP request handler for the yuleOSH dashboard. | `ui/server.py:179` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_ThreadSafeDict.__init__` | `(self)` | — | `ui/auth_extended.py:108` |
| `_ThreadSafeDict.get` | `(self, key, default)` | — | `ui/auth_extended.py:112` |
| `_ThreadSafeDict.clear` | `(self)` | Remove all entries (test isolation / state reset). | `ui/auth_extended.py:116` |
| `_ThreadSafeDict.pop` | `(self, key, default)` | — | `ui/auth_extended.py:121` |
| `_ThreadSafeDict.items` | `(self)` | — | `ui/auth_extended.py:145` |
| `_ThreadSafeDict.keys` | `(self)` | — | `ui/auth_extended.py:149` |
| `OSHHandler.__init__` | `(self, *args, **kwargs)` | — | `ui/server.py:182` |
| `OSHHandler.do_GET` | `(self)` | — | `ui/server.py:262` |
| `OSHHandler.do_POST` | `(self)` | — | `ui/server.py:290` |
| `OSHHandler.do_DELETE` | `(self)` | — | `ui/server.py:307` |
| `OSHHandler.do_PUT` | `(self)` | Route PUT requests (e.g. /api/v1/org/llm-config). | `ui/server.py:322` |
| `OSHHandler.do_PATCH` | `(self)` | Route PATCH requests (e.g. /api/v1/members/{id}, members/roles). | `ui/server.py:341` |
| `OSHHandler.do_OPTIONS` | `(self)` | — | `ui/server.py:360` |
| `OSHHandler.log_message` | `(self, format, *args)` | Override default stderr logging with module-level logger. | `ui/server.py:364` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `HOME` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |
| `OSH_HOST` | _(见源码)_ |
| `OSH_PORT` | _(见源码)_ |
| `YULEASR_HOME` | _(见源码)_ |
| `YULEOSH_API_KEY` | _(见源码)_ |
| `YULEOSH_AUTH_DISABLED` | _(见源码)_ |
| `YULEOSH_DEV_JWT_SECRET` | _(见源码)_ |
| `YULEOSH_HOST` | _(见源码)_ |
| `YULEOSH_JWT_SECRET` | _(见源码)_ |
| `YULEOSH_PORT` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.ui import <公共符号>
# 详见 docs/modules/ui.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 18 处生产引用(Grep `yuleosh.ui` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/ui/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_
