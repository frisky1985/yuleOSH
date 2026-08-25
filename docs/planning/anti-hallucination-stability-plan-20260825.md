# Anti-Hallucination & Output Stability Optimization Plan

> **Date**: 2026-08-25
> **Status**: Approved — 需求已拆解至 TASK_STATUS H-series
> **Scope**: 幻觉防治 + 持续稳定输出标准产品能力保障

---

## 1. Current Strengths (Production-Grade)

| Layer | Mechanism | File |
|---|---|---|
| Audit trail | SHA-256 hash chain + RSA-2048 signing | `audit/model.py` |
| Output validation | 5-level fallback (raw→schema→content→semantic→template) | `llm/fallback.py` |
| Source grounding | `numbered_source()` validates file:line existence | `pipeline/review_guard.py` |
| Determinism | Content-addressed step cache + RED-cache prevention | `pipeline/step_cache.py` |
| Honesty gates | H1–H9 fake-green prevention | `ci/honesty_gate.py` |
| Loop engine | 4 feedback loops (defect→req, field→FMEA, KPI→RCA, KG self-evolve) | `loop_engine/` |
| Temperature | 0.1–0.3 across all paths; L3/L4 anti-small-model hard rule | `llm/client.py` |

---

## 2. Gap Analysis

### Anti-Hallucination Gaps

| ID | Gap | Severity | Current State |
|---|---|---|---|
| GAP-1 | `review_selfcheck` phantom task | P0 | Registered but no handler; empty RAG sources |
| GAP-2 | Source grounding only in review paths | P0 | `review_guard.py` only used by `review_code.py` / `review.py` |
| GAP-3 | RAG engine is prototype | P1 | Char n-grams; 5 sample MISRA rules; no chunking/threshold/citations |
| GAP-4 | No cross-LLM consensus | P1 | Single LLM call per task; 2/4 providers are skeletons |
| GAP-5 | No per-claim confidence | P2 | Binary pass/fail; no uncertainty markers |

### Output Stability Gaps

| ID | Gap | Severity | Current State |
|---|---|---|---|
| GAP-7 | No LLM reproducibility | P1 | No seed/penalty; temperature not in audit |
| GAP-8 | Test verification C-only | P1 | `test_c_unit.py` only; no Python/integration runner |
| GAP-9 | No external standards DB | P2 | No ISO 26262 / full MISRA corpus |
| GAP-10 | Behavior guardrails opt-in | P2 | `ChangeSet` per-handler; not automatic |

---

## 3. Recommendations (Prioritized)

| Priority | GAP | Recommendation | Effort | Impact |
|---|---|---|---|---|
| P0 | GAP-1 | Implement `review_selfcheck` handler: final LLM pass cross-checking against `repo_facts` + memory | M | Eliminates biggest anti-hallucination gap |
| P0 | GAP-2 | Extend `review_guard.py` source grounding to all LLM steps | M | Catches hallucinated references in 80% of steps |
| P1 | GAP-7 | Add `seed` + `frequency_penalty` to LLMConfig; log in audit trail | S | Reproducibility for golden tests |
| P1 | GAP-8 | Add Python test runner to pipeline | S | Close non-C verification gap |
| P2 | GAP-5 | Add `confidence` field to LLM response schema | M | Triage human review |
| P2 | GAP-6 | Wire memory trust auto-adjust on pipeline outcomes | S | Self-correcting memory |
| P2 | GAP-10 | Auto-apply ChangeSet for all LLM step handlers | M | Universal safety net |

---

## 4. Implementation Order

1. **H1-1** (GAP-7): seed/penalty — quick win, 5 lines
2. **H1-2** (GAP-6): memory trust auto-adjust — quick win
3. **H2-1** (GAP-2): extend source grounding — medium, high impact
4. **H2-2** (GAP-1): review_selfcheck handler — medium, high impact
5. **H2-3** (GAP-8): Python test runner — quick win
6. **H3-1** (GAP-5): confidence field — medium
7. **H3-2** (GAP-10): auto ChangeSet — medium

---

## 5. Success Criteria

- All LLM outputs pass source grounding before entering pipeline artifacts
- `review_selfcheck` wired as final step before gate evaluation
- LLM calls carry seed for reproducibility
- Memory trust scores adjust based on downstream pipeline outcomes
- Python test runner integrated alongside C test runner
- No hallucinated file:line references escape to gate evaluation
