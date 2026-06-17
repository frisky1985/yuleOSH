# Coverage Baseline v2 (Phase 0 Quality Baseline Fix)

> **Date**: 2026-06-17
> **Command**: `python3 -m pytest --cov=src/yuleosh tests/ --co -q`
> **Tests executed**: 3400 collected
> **Coverage tool**: pytest-cov with `.coveragerc` (source → `src/yuleosh`, branch enabled)

## Overall Coverage

| Metric | Value |
|:-------|:------|
| Total Coverage (line + branch) | **11.45%** |
| Statements (total) | 11,431 |
| Missed | 9,740 |
| Branches (total) | 3,434 |
| Partially covered branches | 5 |

## Comparison with v1 Baseline (2026-06-16)

| Metric | v1 Baseline (excl. E2E/LLM) | v2 Baseline (all tests) |
|:-------|:----------------------------:|:-----------------------:|
| Coverage | 29% | **11.45%** |
| Tests | 361 | 3,400 |
| Statements | 10,071 | 11,431 |

> **Note**: The v1 baseline selectively excluded E2E, LLM client, and server crunch tests. The v2 baseline includes **all 3,400 tests**, giving a more accurate picture. The gap (~17pp) reflects the large amount of new deep-test code that exercises uncovered modules.

## Module Coverage Breakdown

| Module | Coverage |
|:-------|:--------:|
| `src/yuleosh/ci/__init__.py` | 100% |
| `src/yuleosh/ci/run.py` | 96% |
| `src/yuleosh/cli/__init__.py` | 100% |
| `src/yuleosh/cross/base.py` | 82% |
| `src/yuleosh/evidence/__init__.py` | 100% |
| `src/yuleosh/llm/__init__.py` | 100% |
| `src/yuleosh/pipeline/__init__.py` | 100% |
| `src/yuleosh/pipeline/run.py` | 100% |
| `src/yuleosh/pipeline/step_handlers/__init__.py` | 100% |
| `src/yuleosh/sil/__init__.py` | 60% |
| `src/yuleosh/ci/result.py` | 38% |
| `src/yuleosh/ci/config.py` | 36% |
| `src/yuleosh/store.py` | 34% |
| `src/yuleosh/pipeline/session.py` | 31% |
| `src/yuleosh/hardware/flasher.py` | 28% |
| `src/yuleosh/ui/auth.py` | 26% |
| `src/yuleosh/cross/sil_runner.py` | 25% |
| `src/yuleosh/hardware/__init__.py` | 24% |
| `src/yuleosh/cross/jlink.py` | 24% |
| `src/yuleosh/cross/openocd.py` | 23% |
| `src/yuleosh/cross/flash.py` | 23% |
| `src/yuleosh/testgen/runner.py` | 22% |
| `src/yuleosh/hardware/integration.py` | 21% |
| `src/yuleosh/hardware/monitor.py` | 20% |
| `src/yuleosh/cross/target_config.py` | 20% |
| `src/yuleosh/cross/serial_monitor.py` | 19% |
| `src/yuleosh/pipeline/stages.py` | 17% |
| `src/yuleosh/testgen/generator.py` | 17% |
| `src/yuleosh/llm/client.py` | 16% |
| `src/yuleosh/hardware/debugger.py` | 15% |
| `src/yuleosh/evidence/pack.py` | 15% |
| `src/yuleosh/cross/sil_assert.py` | 14% |
| `src/yuleosh/ui/auth_extended.py` | 13% |
| `src/yuleosh/ci/runner.py` | 13% |
| `src/yuleosh/pipeline/orchestrator.py` | 12% |
| `src/yuleosh/pipeline/prompts.py` | 10% |
| `src/yuleosh/ci/stage_utils.py` | 9% |
| `src/yuleosh/pipeline/step_handlers/review.py` | 9% |
| `src/yuleosh/spec/validate.py` | 7% |
| `src/yuleosh/testgen/formatter.py` | 7% |
| `src/yuleosh/review/c_review.py` | 7% |
| `src/yuleosh/review/resource_predictor.py` | 8% |
| `src/yuleosh/review/run.py` | 8% |
| `src/yuleosh/pipeline/step_handlers/analysis.py` | 8% |
| `src/yuleosh/evidence/generator.py` | 8% |
| `src/yuleosh/pipeline/step_handlers/execution.py` | 6% |
| `src/yuleosh/ci/layers.py` | 6% |
| `src/yuleosh/ci/stages.py` | 6% |
| `src/yuleosh/cli/stats.py` | 0% |
| `src/yuleosh/cli/template.py` | 0% |
| `src/yuleosh/compliance/*` | 0% |
| `src/yuleosh/api/*` | 0% (most modules) |
| `src/yuleosh/preview/*` | 0% (most modules) |
| `src/yuleosh/store_pg.py` | 0% |
| `src/yuleosh/usage/*` | 0% |

## Baseline Target

- Current: **11.45%**
- Target for v1.0.1: ≥ 20%
- Target for v1.1.0: ≥ 50%

## Key Findings

1. **Large test collection (3400)**: Indicates thorough deep-testing approach across all modules
2. **Low overall %**: Many tests exist but they exercise sparse, targeted paths rather than broad coverage
3. **100% modules**: `__init__.py` files, `ci/run.py`, `cross/base.py` — clean re-exports and thin modules
4. **Under 5% clusters**: `api/*`, `preview/*`, `usage/*`, `store_pg.py`, `cli/stats.py`, `cli/template.py` — these are newer modules without deep test coverage
5. **Pipeline step_handlers**: All under 10% — these require integration-level exercise
