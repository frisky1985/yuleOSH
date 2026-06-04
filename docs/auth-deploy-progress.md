# Auth & Production Deployment — Progress Report

## Summary

Implemented authentication and production deployment infrastructure for yuleOSH.

| Task | Status | Notes |
|------|--------|-------|
| API Key Auth | ✅ Done | `src/ui/auth.py` with session cookie support |
| Login Page | ✅ Done | Dark-themed login page matching dashboard |
| Healthcheck | ✅ Done | `GET /api/health` — accessible without auth |
| Multi-stage Docker | ✅ Done | Builder + Runtime stages, non-root user |
| Docker Compose | ✅ Done | Restart policy, healthcheck, auth env var |
| Startup Script | ✅ Done | `bin/yuleosh-server` with dep checks |

---

## Task 1: API Key Authentication

**Files created:**
- `src/ui/auth.py` — Auth module

**How it works:**

1. Set `YULEOSH_API_KEY` environment variable to enable authentication
2. API requests require `X-API-Key` header matching the configured key
3. Browser requests get a login page at `/` and `/_auth/login`
4. Successful login creates a signed session cookie (`osh_session`) valid for 24h
5. Session tokens are HMAC-signed with the API key to prevent forgery
6. `/api/health` is always publicly accessible (for Docker healthchecks)

**Integration into server.py:**
- `do_GET()` and `do_POST()` check auth on every request
- Unauthenticated API calls get `401 {"error": "unauthorized"}`
- Unauthenticated browser requests get the login page
- Login form POSTs to `/_auth/login`

**Tests verified:**
- Valid API key authenticates ✅
- Wrong API key rejected ✅
- Empty headers rejected when auth enabled ✅
- Session cookies created and validated ✅
- Login page renders with error messages ✅
- Healthcheck bypasses auth ✅
- Dashboard serves correctly with session cookie ✅

---

## Task 2: Production Docker

**Files updated:**
- `Dockerfile` — Multi-stage build with security hardening
- `docker-compose.yml` — Healthcheck, restart policy, auth support

**Dockerfile improvements:**
- **Multi-stage:** Builder stage installs deps, runtime stage is minimal
- **Non-root user:** Runs as `osh` user (UID 1001) — no root in container
- **Healthcheck:** `HEALTHCHECK` instruction using `/api/health`
- **Layer caching:** Dependency files copied separately before source
- **Labels:** Maintainer, description, version

**docker-compose.yml improvements:**
- **restart: unless-stopped** — auto-restart on crash
- **healthcheck** — pings `/api/health` every 30s
- **YULEOSH_API_KEY** — commented out with docs for easy production enablement
- **PYTHONUNBUFFERED=1** — ensures logs are unbuffered

**Example production usage:**
```bash
YULEOSH_API_KEY="my-secret-key" docker compose up -d
```

---

## Task 3: Startup Script

**File created:**
- `bin/yuleosh-server` (executable)

**Features:**
- Auto-detects `OSH_HOME` (or uses parent directory of script)
- Loads config from `/etc/yuleosh.conf`, `~/.yuleosh.conf`, `.yuleosh.conf`
- Checks Python availability
- Verifies yuleOSH modules import correctly
- Creates required `.osh/` directories (reviews, ci, evidence)
- Starts the dashboard server

**Usage:**
```bash
export YULEOSH_API_KEY="your-key"
bin/yuleosh-server
```

---

## Test Results

```
33 passed in 0.03s  (unit tests)
 8 passed, 1 skipped in 0.56s  (e2e tests)
```

All existing tests pass. No regressions.
