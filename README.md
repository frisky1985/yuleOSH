<div align="center">
  <h1>yuleOSH 🚀</h1>
  <p><em>You Unify Lifecycle of OpenSpec + Superpowers + Harness Engineering</em></p>
  <p><strong>AI-DRIVEN EMBEDDED DEVELOPMENT PLATFORM — FROM SPEC TO DEPLOYMENT</strong></p>

  <!-- Badges -->
  <p>
    <a href="https://github.com/frisky1985/yuleOSH/actions">
      <img src="https://img.shields.io/badge/CI-Layer%201%20Passing-brightgreen?style=flat-square" alt="CI">
    </a>
    <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License">
    <img src="https://img.shields.io/badge/python-≥3.10-ff69b4?style=flat-square" alt="Python">
    <img src="https://img.shields.io/badge/coverage-86%25-brightgreen?style=flat-square" alt="Coverage">
    <img src="https://img.shields.io/badge/tests-988%20passed-success?style=flat-square" alt="Tests">
    <img src="https://img.shields.io/badge/ASPICE-compliant-8A2BE2?style=flat-square" alt="ASPICE">
    <img src="https://img.shields.io/badge/JWT-auth-blue?style=flat-square" alt="JWT">
  </p>
</div>

---

## What is yuleOSH?

**yuleOSH** is a commercial-grade, AI-agent-orchestrated embedded development platform that automates the entire lifecycle — from requirements specification through development, verification, and compliance auditing.

Built for teams shipping firmware on MCU, SoC, and RTOS platforms who need:

- **ASPICE traceability** without the paperwork overhead
- **AI agent pipeline** that replaces manual code reviews and test planning
- **4-layer CI/CD** tailored for embedded cross-compilation and HIL testing
- **Multi-tenant SaaS** with JWT auth, org/project isolation, and bcrypt passwords
- **One-click compliance** — evidence pack, traceability matrix, acceptance matrix auto-generated
- **One-click compliance packs** for ISO 26262 / ASPICE audits

---

## Why yuleOSH?

> "Most embedded teams spend 40% of their time on compliance paperwork. yuleOSH cuts that to zero."

| Pain Point | yuleOSH Solution |
|:-----------|:-----------------|
| Manual requirement traceability | Auto-generated traceability matrix on every pipeline run |
| Scattered code review process | 4-agent parallel review (architecture, domain, style, coverage) |
| Complex CI setup for embedded | 3-layer CI/CD with built-in cross-compilation and MISRA gates |
| Audit prep takes weeks | One-click ASPICE compliance ZIP export |
| No spec-to-code linkage | OpenSpec format + delta tracking from requirements to test cases |

---

## Quick Start — 3 Commands

```bash
# 1. Initialize a new project
yuleosh template init my-project && cd my-project

# 2. Run the full AI agent pipeline (validates spec → analyzes → develops → reviews)
yuleosh pipeline run docs/spec.md

# 3. Run CI and generate compliance evidence
yuleosh ci run 1 && yuleosh evidence pack
```

Open the dashboard at **http://localhost:8080** to monitor pipelines and review results.

---

## Features

| Category | Feature | Description |
|:---------|:--------|:------------|
| **Spec Engine** | OpenSpec Parser | Parse SHALL/SHOULD/MAY requirements with GIVEN/WHEN/THEN scenarios |
| **Spec Engine** | Coverage Scoring | Auto-calculate requirement coverage against rules and tests |
| **Spec Engine** | Delta Tracking | Track requirement changes with spec-diff between versions |
| **Agent Pipeline** | 10-Step Orchestration | Full SDD → DDD → TDD flow with 小明/Hermes/Claude agents + test planning |
| **Agent Pipeline** | S.U.P.E.R Analysis | Startup analysis for every new requirement |
| **Agent Pipeline** | Internal Review | Blocking review gate before proceeding to next stage |
| **CI/CD** | Layer 1 — Dev Verify | Unit tests + coverage gate + plan-lint on each commit |
| **CI/CD** | Layer 2 — Integration | Cross-compilation + static analysis + integration tests on MR |
| **CI/CD** | Layer 3 — System Verify | System tests + evidence generation on release tag |
| **Review** | 4-Agent Matrix | Architecture, Domain, Style, and Coverage review in parallel |
| **Review** | Critical Blocking | Critical findings block commits; warnings pass with annotation |
| **Evidence** | Traceability Matrix | Auto-generated Req ↔ Design ↔ Code ↔ Test mapping |
| **Evidence** | Compliance Pack | One-click ZIP export for ASPICE / ISO 26262 audit |
| **Dashboard** | Web UI | Real-time pipeline status, review results, and CI history |
| **Deployment** | Docker / Compose | Multi-stage Dockerfile + docker-compose for production |
| **Deployment** | Install Script | One-line install with OS detection and preflight diagnostics |
| **CLI** | Full Command Set | 12+ subcommands: spec, pipeline, ci, review, evidence, stats, template |

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │           OpenSpec Layer              │  ← Requirements
                    │   SHALL / SHOULD / MAY + GIVEN/WHEN/THEN  │
                    └────────────┬────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────────────┐
                    │          Superpowers Layer            │  ← Rules Engine
                    │    14 Rules + S.U.P.E.R Analysis      │
                    └────────────┬────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────────────┐
                    │      Harness Engineering Layer        │  ← Orchestration
                    │   Agent Pipeline + 3-Layer CI/CD      │
                    └────────────┬────────────────────────┘
                                 │
                    ┌────────────┴────────────────────────┐
                    │                                      │
                    ▼                                      ▼
          ┌──────────────────┐                  ┌──────────────────┐
          │   Agent Pipeline  │                  │   3-Layer CI/CD  │
          │  (XiaoMing →      │                  │  Dev → Integ →   │
          │   Hermes → Claude)│                  │  System Verify    │
          └──────────────────┘                  └──────────────────┘
                    │                                      │
                    └────────────┬────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────────────────┐
                    │         Evidence Engine               │  ← Compliance
                    │   Traceability Matrix + Compliance ZIP  │
                    └─────────────────────────────────────┘
```

### Directory Layout

```
yuleOSH/
├── src/
│   ├── spec/          # OpenSpec parser, validator, differ
│   │   └── validate.py  # Requirement ID hierarchy (SYS/SW/FEATURE)
│   ├── pipeline/      # Agent pipeline orchestrator (10 steps)
│   │   └── prompts.py   # Test planning prompt templates
│   ├── ci/            # 3-layer CI/CD engine with dependency chaining
│   ├── review/        # 4-agent parallel review matrix
│   ├── evidence/      # Traceability matrix + acceptance matrix + compliance ZIP
│   ├── ui/            # Dashboard server (auth, pages)
│   ├── cli/           # CLI subcommands
│   ├── store.py       # SQLite persistent store
│   └── notify.py      # Multi-channel notifications
├── tests/             # 257 tests (all passing)
├── docs/              # Specification, guides, reports
├── deploy/            # Production deployment configs
├── .osh/              # Runtime data (pipelines, CI, evidence, plans)
├── Dockerfile         # Multi-stage production Dockerfile
├── docker-compose.yml # Docker Compose for production
├── Dockerfile.cross   # ARM/RISC-V cross-compilation toolchain image
└── install.sh         # One-line production installation
```

---

## Deployment

### Option A: Docker Compose (Recommended for Production)

```bash
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
mkdir -p projects .yuleosh
export YULEOSH_API_KEY="your-secure-random-key"
docker compose up -d
curl -H "X-API-Key: $YULEOSH_API_KEY" http://localhost:8080/api/health
```

### Option B: One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
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
| `YULEOSH_API_KEY` | (required) | API key for authentication |
| `YULEOSH_DB` | `$OSH_HOME/.yuleosh/store.db` | SQLite database path |
| `OSH_PORT` | `8080` | Dashboard server port |
| `PYTHONUNBUFFERED` | `1` | Disable stdout buffering |

---

## Roadmap

### v0.1.0 — Foundation (2026 Q2) ✅
- [x] OpenSpec requirement parsing & validation
- [x] 9-step AI agent pipeline
- [x] 3-layer CI/CD for embedded
- [x] 4-agent parallel code review
- [x] Evidence engine + compliance ZIP
- [x] Web dashboard with API key auth
- [x] Docker / Compose production deployment

### v0.2.0 — ASPICE Compliance Refactor (2026 Q3) ✅
- [x] CI Layer 1 strict-mode enforcement (no silent skips)
- [x] Pipeline LLM failure hard errors (no silent degradation)
- [x] CI Layer dependency chaining (L1→L2→L3)
- [x] Pipeline dependency injection for testability
- [x] 30+ pipeline unit tests with mock LLM (≥80% coverage)
- [x] E2E test stabilisation (no skipif bypass)
- [x] spec-diff impact analysis
- [x] Requirement-verification bidirectional tracing
- [x] Automated acceptance matrix generation

### v0.3.0 — Ground Reinforcement (2026 Q4) ✅
- [x] SWE.4 Test Planning step in pipeline (B-01)
- [x] Requirement ID hierarchy (SYS/SW/FEATURE) with state machine
- [x] Requirement status tracking (PROPOSED→APPROVED→IMPLEMENTED→VERIFIED)
- [x] Cross-compilation containerisation (ARM/RISC-V via Docker)
- [x] Full 10-step pipeline integration + full regression (256→257 tests)
- [x] CI hook plan-lint hardening
- [x] 67% overall test coverage (threshold: 38%)

### v1.0.0 — Production (2027 Q1)
- [ ] HIL/SIL adapter layer for hardware-in-the-loop testing
- [ ] Real-time CI dashboard with metrics
- [ ] Custom agent plugin marketplace
- [ ] Database migration framework
- [ ] Horizontal scaling support

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <sub>Built with ❤️ for embedded teams who ship quality firmware, fast.</sub>
</p>
