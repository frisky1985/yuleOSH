# ADR-002: Pipeline Parallel Groups (方案 A)

**Status**: Accepted
**Date**: 2026-08-19 (decision), 2026-08-24 (documented)
**Deciders**: 老板 (PM), 小克 (arch)
**Related**: TASK_STATUS P2-4, docs/planning/d2-parallel-brainstorm-2026-08-19.md

---

## Context

The 24-step pipeline had a wall-clock time of ~17min. Dependency graph
analysis (source-verified, 2026-08-19) identified three high-value
parallel groups that could reduce wall-clock by ~80-90s (~8-9%) without
changing logical execution order or gate semantics.

## Decision

### Method A: Selective parallelism — P1+P2+P3 only

Three parallel groups declared in `orchestrator.py:PARALLEL_GROUPS`:

| Group | Members | Rationale |
|-------|---------|-----------|
| P1 | prd ∥ architecture | architecture only reads spec+src, never reads prd output |
| P2 | arch-review ∥ development | development reads architecture/prd/super-analysis, never reads arch-review |
| P3 | development-review ∥ codegen-deploy ∥ claude-review | all three depend only on development artifacts, mutually independent |

**Excluded from P3**: `internal-code-review` — its `maybe_skip_code_review`
reads the codegen-deploy report which is written at handler end. Running
them in parallel would read stale/missing report → false-skip. Consumers
of deployment state must run after the producer (aligns with the
"interchange safety ⟺ neither consumes the other's output" principle).

**Excluded**: P4 (misra-review ∥ integration-test ∥ qemu-verify) — each
<10s, low ROI.

### Implementation contract

- Parallel group members write to **different artifact keys** (no write conflicts)
- Session state updates (add_step/start_step/complete_step/_save) protected by `threading.Lock`
- **Failure semantics**: any member failed/block → wait for all members to finish → aggregate worst status → interrupt subsequent steps (consistent with verify-loop merge semantics)
- Gate semantics unchanged: block/failed verdicts propagate identically

## Consequences

- `PARALLEL_GROUPS` constant in `orchestrator.py` is the single source of truth
- `_GROUP_LOOKUP` dict auto-derived for O(1) membership check
- ThreadPoolExecutor used for concurrent dispatch within groups
- Thread-safe session counters (token usage += / step list append)
- Baseline: 24-step ~17min → target ~15.5min
