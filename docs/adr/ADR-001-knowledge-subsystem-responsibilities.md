# ADR-001: Knowledge Subsystem Responsibilities

**Status**: Accepted
**Date**: 2026-08-24
**Deciders**: 小克 (arch), 小马 (quality)
**Related**: TASK_STATUS P1-2a–P1-2e

---

## Context

yuleOSH has three active knowledge subsystems whose boundaries were previously
informal. A dead-code layer (`src/knowledge/store_*.py`) was also present,
creating confusion about where knowledge storage belongs.

## Decision

### 1. Responsibility Matrix (P1-2b)

| Subsystem | Path | Responsibility | Backend |
|-----------|------|----------------|---------|
| knowledge_graph | `src/yuleosh/knowledge_graph/` | Traceability graph: requirement ↔ code ↔ test edges, impact analysis, merge gate | SQLite (default) + PostgreSQL (`YULEOSH_DB_URL`) |
| kb | `src/yuleosh/kb/` | RAG vector + FTS5 retrieval: articles, lessons, FMEA entries | SQLite only (`YULEOSH_KB_DB`) |
| memory | `src/yuleosh/memory/` | LLM session memory: fact store, distill/reflect/feedback loop | SQLite only (`YULEOSH_MEMORY_DB`) |

**Rule**: No new `store_*.py` may be created outside these three subsystems.
CI gate (P1-2f) will block new store modules not registered in this matrix.

### 2. Article Dual-Storage (P1-2c)

`KnowledgeArticle` (`knowledge_management/models.py`) and `KbArticle`
(`kb/models.py`) **are not duplicates** — they serve distinct layers:

| Aspect | KnowledgeArticle | KbArticle |
|--------|-----------------|-----------|
| Layer | Loop-engine feedback (spec compliance) | User-facing RAG (API/hooks/CLI) |
| Call sites | 1 production (`loop_engine/cli.py`) | 30+ production |
| Schema | 25+ fields (ASIL, status lifecycle, version, confidence, DTC, code paths) | 9 fields (title, content, source, tags, timestamps) |
| Backend | SQLite via `KBStore` | SQLite via `KbStore` |

**Decision**: Keep both. Document the coexistence rationale here.
The loop-engine may use the richer `KnowledgeArticle` for spec-compliant
lifecycle management; `KbArticle` remains the read-path for RAG retrieval.

### 3. PostgreSQL / SQLite Dual Backend (P1-2d)

`knowledge_graph` has dual backends (SQLite default + PostgreSQL production):

- **Selection**: `YULEOSH_DB_URL` env var (presence → PostgreSQL)
- **SQLite**: `KGStore` in `store.py`, Python BFS traversal
- **PostgreSQL**: `KGStorePG` in `store_pg.py`, RECURSIVE CTE traversal

Both are **live and tested** (SQLite via `test_knowledge_graph.py`,
PostgreSQL via `test_kg_store_pg_unit.py`).

`kb/` and `memory/` are **SQLite-only by design** — no `_pg` variants exist
and none are planned. The top-level `Store`/`PostgresStore` pair
(`src/yuleosh/store*.py`) is a separate multi-tenant concern.

**Decision**: Keep the dual backend. Dead `_pg` private re-exports in
`__init__.py` (aliased with `_` prefix, never imported externally) have been
removed to slim the import surface.

## Consequences

- `src/knowledge/` dead-code layer deleted (P1-2a): 3 Python files (2441 lines)
  + 2 Go files + 1 SQL migration
- New store modules must register in this matrix (P1-2e CI gate)
- `knowledge_management/` is recognized as a loop-engine-internal module,
  not a general-purpose knowledge store
