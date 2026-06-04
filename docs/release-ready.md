# yuleOSH v0.1.0 — Release Ready 🚀

> **y**ou **u**nify **L**ifecyc**E** of **O**penSpec + **S**uperpowers + **H**arness Engineering

---

## Version Summary

| Field | Value |
|:------|:------|
| Version | **0.1.0** |
| Status | **Production Ready** |
| License | MIT |
| Python | ≥3.10 |
| Last CI | `0bd7050` — Layer 1 All Stages Passed ✅ |
| Tests | 41 passed, 1 skipped |
| Coverage | 48% line, 48% condition (threshold: 40%) |
| Evidence Pack | ✅ Generated (5 artifacts + compliance ZIP) |

## What's Included

### Core Platform

- **OpenSpec Engine** — Parse, validate, diff, and coverage-check requirement specifications (`src/spec/`)
- **Agent Pipeline** — Automated AI agent workflow orchestration (`src/pipeline/`)
- **CI/CD 3-Layer System** — ASPICE-aligned verification pipeline (`src/ci/`)
  - Layer 1: Development Verification (commit)
  - Layer 2: Integration Verification (MR)
  - Layer 3: System Verification (release)
- **Review Engine** — Automated code review with finding classification (`src/review/`)
- **Evidence Engine** — Traceability matrix, coverage reports, compliance ZIP (`src/evidence/`)
- **Dashboard Server** — Web UI with auth support (`src/ui/server.py`)
- **SQLite Store** — Persistent storage for pipelines, CI results, reviews (`src/store.py`)
- **CLI** — `yuleosh` command with subcommands: spec, pipeline, ci, review, evidence, stats, template

### Deployment

- **Docker** — Multi-stage Dockerfile with non-root user (`osh:1001`) and healthcheck
- **Docker Compose** — Volume-mapped persistence, port 8080, restart policy
- **Install Script** — Production-grade `install.sh` with OS detection, version checks, preflight diagnostics
- **Auth** — API key authentication via `YULEOSH_API_KEY` environment variable

### Documentation

- `README.md` — Overview, architecture, quick start
- `docs/spec.md` — OpenSpec specification
- `docs/startup-analysis.md` — S.U.P.E.R analysis
- `docs/schedule.md` — Release schedule
- `docs/cli-design.md` — CLI command reference
- `docs/usage.md` — Detailed usage guide
- `docs/auth-deploy-progress.md` — Auth & deployment progress

### Quality

| Metric | Result |
|:-------|:-------|
| Unit Tests | 41 ✅ |
| Coverage (line) | 48% ✅ (threshold 40%) |
| Coverage (condition) | 48% ✅ (threshold 40%) |
| plan-lint | ✅ Passed |
| clang-tidy | ⏭️ Skipped (no C/C++) |
| Evidence Pack | ✅ 5 artifacts |
| Compliance ZIP | ✅ Generated |

## How to Deploy

### Option A: Docker Compose (Recommended for Production)

```bash
# Clone
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH

# Create required directories
mkdir -p projects .yuleosh

# Set a strong API key (required for production)
export YULEOSH_API_KEY="your-secure-random-key-here"

# Start
docker compose up -d

# Verify
curl -H "X-API-Key: $YULEOSH_API_KEY" http://localhost:8080/api/health
```

Open **http://localhost:8080** in your browser.

### Option B: Direct Install

```bash
# One-line install
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash

# Or with specific version
YULEOSH_VERSION=0.1.0 curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash

# Start server
export YULEOSH_API_KEY="your-key"
yuleosh

# Or directly
python3 src/ui/server.py
```

### Option C: Development

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
pip install -e .
yuleosh init .
yuleosh help
```

### Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `YULEOSH_API_KEY` | (none) | API key for auth. **Required for production.** |
| `YULEOSH_DB` | `$OSH_HOME/.yuleosh/store.db` | SQLite database path |
| `OSH_PORT` | `8080` | Dashboard server port |
| `YULEOSH_DIR` | `$HOME/.yuleosh` | Install directory (install.sh) |
| `PYTHONUNBUFFERED` | `1` | Disable Python stdout buffering |

## Known Limitations

1. **Coverage threshold is MVP** (40%) — target 70%+ for production release. Currently 48%.
2. **Single-user auth** — API key is the only auth mechanism. No multi-user/role support yet.
3. **No HTTPS** — Server runs on HTTP. Use a reverse proxy (nginx/caddy) in production.
4. **Docker image size** — `python:3.13-slim` is ~150MB. Alpine-based could be smaller.
5. **No database migration** — SQLite schema is auto-created; no migration path for schema changes.
6. **Dashboard is basic** — Web UI serves as a monitoring view; full CRUD via CLI is primary workflow.
7. **No ARM64 Docker image** — Only x86_64 tested. ARM/Raspberry Pi not validated.
8. **Single process** — No horizontal scaling. Dashboard + CI run in the same process.
9. **No email/webhook notifications** — CI results are file-based; no push notifications.
10. **No internationalization** — UI and docs are in Chinese/English mixed.

## Evidence Artifacts

Generated evidence (`.osh/evidence/`):

| Artifact | Format | Purpose |
|:---------|:-------|:--------|
| `traceability-matrix.md` | Markdown | Requirements ↔ Implementation ↔ Tests |
| `requirement-coverage.md` | Markdown | Requirement coverage per spec item |
| `code-coverage-report.md` | Markdown | Code line/condition coverage |
| `review-log-summary.md` | Markdown | Review session summaries |
| `review-log.json` | JSON | Raw review records |
| `compliance-pack.zip` | ZIP | All evidence bundled for ASPICE audit |

## Quick Commands

```bash
yuleosh spec validate docs/spec.md        # Validate specification
yuleosh pipeline run docs/spec.md          # Run agent pipeline
yuleosh ci run 1                           # Layer 1: dev verification
yuleosh ci run 2                           # Layer 2: integration
yuleosh ci run 3                           # Layer 3: system
yuleosh review auto                        # Auto review
yuleosh review task "feature-x" feature    # Review a task
yuleosh evidence pack                      # Generate compliance pack
yuleosh stats                              # Project statistics
yuleosh template init my-project           # Initialize from template
```

---

*Generated: 2026-06-04 | Version: 0.1.0 | Commit: 0bd7050*
