# yuleOSH Coverage — Phase 1 Report

> **Date**: 2026-07-30  
> **Baseline commit**: 04ae01d  
> **Previous coverage**: ~11.23%  
> **Phase 1 target**: ≥30%  
> **Achieved**: **31%** ✅

---

## 1. Coverage Summary

| Metric | Value |
|---|---|
| Total statements | 41,893 |
| Missed statements | 27,461 |
| Covered statements | **14,432** |
| Branch coverage | Partially (1,034 branches missed) |
| **Overall line rate** | **31%** |

## 2. New Test Files Added

| Test File | Module | Coverage Gain |
|---|---|---|
| `tests/test_spec_version_unit.py` | `yuleosh.spec.version` | 93% |
| `tests/test_spec_validate_unit.py` | `yuleosh.spec.validate` | 86% |
| `tests/test_spec_parse_unit.py` | `yuleosh.spec.validate` (parse_spec) | (combined above) |
| `tests/test_spec_merge_unit.py` | `yuleosh.spec.merge` | 68% |
| `tests/test_spec_diff_unit.py` | `yuleosh.spec.diff` | 7% |
| `tests/test_ci_config_unit.py` | `yuleosh.ci.config` | 68% |
| `tests/test_ci_result_unit.py` | `yuleosh.ci.result` | 68% |
| `tests/test_plan_models_unit.py` | `yuleosh.plan.models` | 96% |
| `tests/test_engine_checkpoint_unit.py` | `yuleosh.engine.checkpoint` | 61% |
| `tests/test_project_detection_unit.py` | `yuleosh.project_detection` | 24% |
| `tests/test_store_interface_unit.py` | `yuleosh.store_interface` | (abstract) |
| `tests/test_llm_cost_unit.py` | `yuleosh.llm.cost` | 40% |

## 3. Key Module Coverage

| Module | Coverage |
|---|---|
| `yuleosh.spec.version` | **93%** ✅ |
| `yuleosh.spec.validate` | **86%** ✅ |
| `yuleosh.spec.merge` | **68%** ✅ |
| `yuleosh.spec.__init__` | **100%** ✅ |
| `yuleosh.plan.models` | **96%** ✅ |
| `yuleosh.knowledge_graph.models` | **96%** ✅ |
| `yuleosh.llm.providers.base` | **93%** ✅ |
| `yuleosh.llm.providers.mock` | **97%** ✅ |
| `yuleosh.ci.config` | **68%** ✅ |
| `yuleosh.ci.result` | **68%** ✅ |
| `yuleosh.engine.checkpoint` | **61%** ✅ |
| `yuleosh.store` | **46%** ✅ |
| `yuleosh.ci.profiles` | **45%** ✅ |
| `yuleosh.llm.cost` | **40%** ✅ |
| `yuleosh.project_detection` | **24%** 🟡 |
| `yuleosh.spec.diff` | **7%** 🔴 (CLI entry point) |

## 4. Remaining Bottlenecks (0% modules)

These modules have zero coverage and need Phase 2/3 attention:

| Module | Size (stmts) | Complexity |
|---|---|---|
| `pipeline/` (all submodules) | ~2,200+ | High (orchestrator) |
| `api/` (all submodules) | ~2,000+ | Medium (HTTP handlers) |
| `knowledge_graph/` (core logic) | ~3,500+ | High |
| `evidence/` | ~2,500+ | Medium |
| `cross/` (hardware) | ~1,200+ | High (HW deps) |
| `hardware/` | ~600+ | High (HW deps) |
| `loop_engine/` | ~2,200+ | High |
| `cli/` | ~2,100+ | Medium |
| `ci/stages/` | ~1,500+ | Medium |
| `ci/rulesets/` | ~600+ | Medium |
| `report/` | ~900+ | Low |

## 5. CI Configuration Changes

- `pyproject.toml`: `fail_under` raised from **5** → **30** ✅
- Phase 1 gate: `--fail-under=30` (soft gate with `continue-on-error=true` if CI job exists)
- Phase 2 target: 50%
- Phase 3 target: 70% (hard gate)

## 6. Test Stats

| Metric | Value |
|---|---|
| Total tests | 1,144 (excl. 7,878 deselected) |
| Passed | 1,129 |
| Failed (pre-existing) | 15 (API, LLM client, UI server — unrelated to new tests) |
| New tests added | 208 |

## 7. Source Code Fixes

While writing tests, the following bugs were found and fixed:
- `spec/validate.py` `req_pattern`: Fixed regex `Requirement` → `Requirement(?!s)\b` to prevent matching `## Requirements` as a requirement header
- `spec/merge.py` `_normalize_shall_text`: Added `rstrip('.,;:!?')` for consistent comparison (trailing punctuation caused false negatives in conflict detection)
