# yuleOSH v0.8.0 — REST API Reference

> Base URL: `https://your-domain.com`
> All POST/PUT bodies are JSON. Auth: `Authorization: Bearer <JWT>` or `X-API-Key: <key>`

## Authentication

| Method | Path | Body | Response |
|:-------|:-----|:-----|:---------|
| POST | `/api/auth/signin` | `{email, password}` | `{token, redirect, role, org_id}` |
| GET | `/api/auth/session` | Header: Bearer token | `{user_id, org_id, email, role, projects}` |
| POST | `/api/auth/logout` | Header: Bearer token | `{status: "ok"}` |

### Password Requirements
- Minimum 8 characters
- Hashed with bcrypt (12 rounds)
- Rate limited: 10 attempts per 5 minutes per email

### Signin Flows

**New User (no org):**
```bash
curl -X POST /api/auth/signin -H "Content-Type: application/json" \
  -d '{"email":"user@example.com"}'
# → {"token":"eyJ...", "redirect":"/org/setup", "needs_org":true}
```

**Returning User:**
```bash
curl -X POST /api/auth/signin -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"MySecret123"}'
# → {"token":"eyJ...", "redirect":"/project/select", "role":"admin"}
```

## Organizations

| Method | Path | Body | Auth |
|:-------|:-----|:-----|:----:|
| POST | `/api/org/create` | `{org_name, org_slug, project_name, project_slug, email, [password]}` | Bearer |
| GET | `/api/org/info` | — | Bearer |

```bash
curl -X POST /api/org/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"org_name":"MyOrg","org_slug":"my-org","project_name":"App","project_slug":"app","email":"user@example.com","password":"MySecret123"}'
# → {"token":"eyJ...", "redirect":"/project/select", "org_id":1}
```

## Projects

| Method | Path | Body | Auth |
|:-------|:-----|:-----|:----:|
| GET | `/api/project/list` | — | Bearer |
| POST | `/api/project/create` | `{name, slug}` | Bearer |

## Pipeline

| Method | Path | Body | Auth |
|:-------|:-----|:-----|:----:|
| GET | `/api/v1/pipeline/status` | — | API Key |
| POST | `/api/v1/pipeline/run` | `{steps, project}` | API Key |

## CI/CD

| Method | Path | Description |
|:-------|:-----|:------------|
| GET | `/api/v1/ci/layer/{n}` | CI layer n results |
| POST | `/api/v1/ci/run` | Trigger CI pipeline |
| GET | `/api/v1/ci/status` | Overall CI status |

## Spec & Requirements

| Method | Path | Description |
|:-------|:-----|:------------|
| GET | `/api/v1/spec` | Current spec document |
| POST | `/api/v1/spec/validate` | Validate spec.md |
| GET | `/api/v1/spec/diff` | Compare two spec versions |

## Evidence & Traceability

| Method | Path | Description |
|:-------|:-----|:------------|
| GET | `/api/v1/evidence` | Evidence pack (zip download) |
| GET | `/api/v1/evidence/traceability` | Traceability matrix |
| GET | `/api/v1/evidence/acceptance` | Acceptance matrix |
| GET | `/api/v1/evidence/coverage` | Code coverage report |

## Review

| Method | Path | Description |
|:-------|:-----|:------------|
| GET | `/api/v1/review` | Review list |
| POST | `/api/v1/review` | Trigger review |

## Stats & Health

| Method | Path | Description |
|:-------|:-----|:------------|
| GET | `/api/health` | `{status, version, tenant_auth}` |
| GET | `/api/status` | Detailed system status |
| GET | `/api/v1/stats` | Project statistics |
| GET | `/api/v1/stats/coverage` | Coverage percentages |

## Notifications

| Method | Path | Description |
|:-------|:-----|:------------|
| POST | `/api/v1/notify/config` | Configure notification channels |
| GET | `/api/v1/notify/config` | Get current config |

## Error Codes

| Code | Meaning |
|:-----|:--------|
| 200 | Success |
| 400 | Bad request (missing/invalid fields) |
| 401 | Unauthorized (invalid token/password) |
| 404 | Not found (org/project not found) |
| 409 | Conflict (slug already taken) |
| 429 | Rate limited (too many signin attempts) |
| 500 | Internal server error |
