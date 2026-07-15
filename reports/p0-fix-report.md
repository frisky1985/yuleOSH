# P0 Security Fix Report

**Date**: 2026-07-10  
**Author**: Subagent  
**Scope**: Fix 3 P0 security issues identified by UltraReview

---

## P0-01: CORS Wildcard (`Access-Control-Allow-Origin: *`)

### Problem
`Access-Control-Allow-Origin: *` was hardcoded in ~35 locations across the codebase (server.py, router.py, route helpers, response helpers, API modules), exposing the API to arbitrary cross-origin requests in all environments.

### Fix

**New module**: `src/yuleosh/api/cors.py`
- Detects development mode via `YULEOSH_ENV=development` → returns `*`
- In production mode: validates the request `Origin` against an allowed-origins list
- Always permits `localhost:18789` (desktop client)
- Configurable via:
  - `YULEOSH_ENV` env var (`development`|`production`)
  - `YULEOSH_CORS_ALLOWED_ORIGINS` env var (comma-separated)
  - `.yuleosh/config.yml` config file

**Modified files**:
| File | Changes |
|------|---------|
| `src/yuleosh/api/cors.py` | **New** — CORS configuration module |
| `.yuleosh/config.yml` | **New** — CORS and DB config |
| `src/yuleosh/api/router.py` | `_respond` uses `get_cors_origin()`; adds `Vary: Origin` header |
| `src/yuleosh/ui/server.py` | All 14 `Access-Control-Allow-Origin` → `_add_cors_header()` |
| `src/yuleosh/ui/routes/helpers.py` | Added `_add_cors_header()` function; updated `_send_gzipped_json()` |
| `src/yuleosh/ui/routes/handler_helpers.py` | Updated rate-limit & OPTIONS handlers |
| `src/yuleosh/ui/routes/response_helpers.py` | Updated all response functions |
| `src/yuleosh/ui/routes/auth_routes.py` | Updated CORS headers |
| `src/yuleosh/ui/routes/page_routes.py` | Updated CORS headers |
| `src/yuleosh/api/demo.py` | Updated CORS via `get_cors_origin()` |
| `src/yuleosh/api/evidence.py` | Updated CORS via `get_cors_origin()` |

### Verification
- Development mode: `YULEOSH_ENV=development` → `Access-Control-Allow-Origin: *`
- Production mode: validated against allowed list + `localhost:18789`
- ✅ All 139 tests pass

---

## P0-02: Postgres Default Credentials Hardcoded

### Problem
`store_pg.py` hardcoded `postgresql://yuleosh:yuleosh@localhost:5432/yuleosh` as default DSN when `YULEOSH_DB_URL` was not set, exposing default credentials.

### Fix

**Modified file**: `src/yuleosh/store_py`

- Removed the hardcoded default credentials
- When `YULEOSH_DB_URL` is not set **and** no `dsn` parameter is passed, raises a clear `ValueError`:
  ```
  PostgreSQL connection string is required. Set the YULEOSH_DB_URL environment variable, e.g.:
    export YULEOSH_DB_URL=postgresql://user:password@host:5432/database
  Or pass the dsn parameter to PostgresStore(dsn=...)
  ```
- When DSN is provided explicitly (e.g., `PostgresStore(dsn=...)` or from `store.py`'s `PostgresStore.__new__` call), no error is raised — the provided DSN is used directly

### Verification
- Call without DSN and without env var → `ValueError` with descriptive message
- Call with explicit DSN → works as before
- Call with `YULEOSH_DB_URL` env var → works as before
- ✅ 87 store_pg tests pass (2 `PostgresStore()`-without-arg tests fixed to mock env var)

---

## P0-03: Error Stack Leak to Client

### Problem
`router.py` returned `json_error(f"Internal error: {e}", 500)` exposing internal exception details (file paths, variable values, API structure) to the HTTP client.

### Fix

**Modified file**: `src/yuleosh/api/router.py`

- Adds structured logging with full traceback via `logger.error(..., exc_info=True)`
- Log format includes: module name, HTTP method, request path, exception type, exception message
- Response to client changed from `f"Internal error: {e}"` to `"Internal server error"` (generic, no leak)
- Removes bare `import traceback` / `traceback.print_exc()` from the except block — now uses proper `logging` with structured data

### Before (vulnerable):
```python
except Exception as e:
    import traceback
    traceback.print_exc()
    _respond(handler, *json_error(f"Internal error: {e}", 500))
```

### After (fixed):
```python
except Exception as e:
    logger.error(
        "Unhandled exception in API dispatch [module=%s] [method=%s] [path=%s]: %s: %s",
        resource, method, path, type(e).__name__, e,
        exc_info=True
    )
    _respond(handler, *json_error("Internal server error", 500))
```

### Verification
- Log output contains full traceback, module name, HTTP method, path, exception type
- Client response is always `{"ok": false, "error": "Internal server error"}` with status 500
- ✅ All 139 tests pass

---

## Summary

| P0 | Issue | Severity | Files Changed | Tests |
|----|-------|----------|---------------|-------|
| 01 | CORS wildcard | High | 10 files + 2 new | 139/139 ✅ |
| 02 | Default DB credentials | High | 1 file + 2 test fixes | 87/87 ✅ |
| 03 | Error stack leak | High | 1 file | 139/139 ✅ |

**Total tests**: 139 passed, 0 failed (including store_pg, store_pg_smoke, store_pg_deep, api_router_ext, api_core, api_extra_smoke)
