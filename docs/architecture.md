# yuleOSH v0.8.0 — Architecture & Security Model

## System Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Nginx (SSL)                       │
│                   :443 → :8080                       │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                 yuleOSH Server                       │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Web UI   │ │ REST API │ │ Pipeline Engine        │ │
│  │ (HTML)   │ │ (v1)     │ │ (SDD→DDD→TDD→CI→Evi)  │ │
│  └──────────┘ └──────────┘ └───────────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Auth     │ │ Evidence │ │ LLM Agent              │ │
│  │ (JWT+Key)│ │ Engine   │ │ (Prompt→Code→Test)     │ │
│  └──────────┘ └──────────┘ └───────────────────────┘ │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                    Storage                           │
│  ┌──────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Store.db │ │ Sessions │ │ Evidence / CI Reports  │ │
│  │ (SQLite) │ │ (.osh/)  │ │ (.osh/evidence/)      │ │
│  └──────────┘ └──────────┘ └───────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

## Module Map

| Module | Path | Role |
|:-------|:-----|:-----|
| **UI** | `src/ui/` | Web dashboard + HTML pages |
| **API** | `src/api/` | REST API v1 (14 resources) |
| **Pipeline** | `src/pipeline/` | SDD→DDD→TDD workflow engine |
| **CI** | `src/ci/` | 4-layer CI/CD (L1→L2→L2.5→L3) |
| **LLM** | `src/llm/` | OpenAI-compatible LLM client |
| **Spec** | `src/spec/` | OpenSpec parser + validator + diff |
| **Evidence** | `src/evidence/` | Traceability + acceptance matrix |
| **Cross** | `src/cross/` | ARM/RISC-V cross-compilation + HIL |
| **Store** | `src/store.py` | Multi-tenant SQLite database |

## Security Model

### Authentication Layers

| Layer | Method | Use Case |
|:------|:-------|:---------|
| **JWT Bearer** | `Authorization: Bearer <token>` | Browser UI + API for users |
| **API Key** | `X-API-Key: <key>` | CI/CD machine-to-machine |
| **Session Cookie** | `osh_session=<cookie>` | Legacy browser auth (backward compat) |

### Password Security
- bcrypt hashing with 12 rounds
- Constant-time comparison via bcrypt.checkpw
- Minimum 8 characters enforced
- Rate limited: 10 attempts per 5 minutes per email

### Token Security
- JWT signed with HS256 (HMAC-SHA256)
- Secret: minimum 32 random bytes (auto-generated if not set)
- Claims: sub, org, email, iat (issued at), exp (72h)
- Expired/invalid tokens rejected silently

### HTTP Security Headers
- `Content-Security-Policy: default-src 'self'`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Access-Control-Allow-Origin: *` (for API routes)

### Multi-Tenant Isolation
- Users belong to organizations (org_id foreign key)
- Projects belong to organizations
- API keys scoped to organizations
- Session tokens scoped to user + organization
- DB queries filtered by org_id

### Rate Limiting
| Endpoint | Limit |
|:---------|:------|
| `/api/auth/signin` | 10 req / 5 min per email |
| `/api/v1/*` | Via `src/api/ratelimit.py` |

## Data Flow

```
User Request
  → Nginx (SSL termination)
    → auth_extended.py (JWT validation / signin)
      → Store.py (SQLite queries, org-scoped)
        → Pipeline/CI/Evidence (core engine)
          → Response (JSON/HTML/zip)
```

## Deployment

See [deploy-guide.md](./deploy-guide.md) for Docker Compose + Nginx + SSL setup.
