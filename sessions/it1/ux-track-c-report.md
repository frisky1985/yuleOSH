# yuleOSH UX Track C: API 文档 + 路由可发现性

**Date:** 2026-06-08  
**Sprint:** v0.3.0  
**Status:** ✅ Complete

---

## C-1: CLI help 加上 ui 命令

**File:** `yuleosh_cli.py`

Added `yuleosh ui` to the module-level docstring:

```
    yuleosh ui                              — Start dashboard server (:8080)
```

**Verification:**
```
$ yuleosh --help
...
    yuleosh ui                              — Start dashboard server (:8080)
```

The existing `if cmd == "ui":` handler in `main()` was already present; only the docstring needed updating.

---

## C-2: 启动 server 时输出 API 路由

**File:** `src/ui/server.py`

Modified `main()` to dynamically read the ROUTES dictionary from `src.api.router` and print a formatted route table at startup.

**Dynamic approach selected:**
- Imports `ROUTES` dict from `src.api.router` (13 endpoints)
- Iterates in sorted order
- Uses handler `__doc__` when it's descriptive (e.g. health, audit) or falls back to the route name for generic docstrings
- Falls back to a hardcoded list if the dynamic import fails

**Example startup output:**
```
🚀 yuleOSH Dashboard
   ────────────────────────────────────
   Dashboard:   http://localhost:8080/
   API v1:      http://localhost:8080/api/v1/

   API Endpoints:
     /api/v1/apikeys                       — /api/v1/apikeys
     /api/v1/audit                         — GET /api/v1/audit — list recent audit entries (admin only).
     /api/v1/ci                            — /api/v1/ci
     /api/v1/evidence                      — /api/v1/evidence
     /api/v1/health                        — GET /api/v1/health — return full system health status.
     /api/v1/notify                        — /api/v1/notify
     /api/v1/pipeline                      — /api/v1/pipeline
     /api/v1/project                       — /api/v1/project
     /api/v1/review                        — /api/v1/review
     /api/v1/spec                          — /api/v1/spec
     /api/v1/stats                         — /api/v1/stats
     /api/v1/webhooks                      — /api/v1/webhooks
     /api/v1/wizard                        — /api/v1/wizard
   Press Ctrl+C to stop.
```

The route listing stays in sync with `ROUTES` dict — adding a new entry there automatically appears in the startup output.

---

## Tests

All 534 existing tests pass with no regressions:

```
$ pytest tests/ -v --tb=short
============================= 534 passed in 17.74s =============================
```

## Files Changed

| File | Change |
|------|--------|
| `yuleosh_cli.py` | Added `yuleosh ui` to docstring |
| `src/ui/server.py` | Dynamic API route listing in `main()` |
