# KG Performance Baseline Report — P0-5 + P0-6

**Date**: 2026-07-15
**Dataset**: ~11,200 nodes, ~16,673 edges
**DB**: `.yuleosh/knowledge_graph.db`

---

## P0-5: Performance Baselines

### Query API Performance (pytest-benchmark, 3 rounds each)

| Test | Median (µs) | Mean (µs) | Rounds | Gate (2s) |
|------|-------------|-----------|--------|-----------|
| `trace_by_file_path(store.py)` | 31 | 31 | 79,580 | ✅ PASS |
| `trace_by_file_path(store_pg.py)` | 31 | 31 | 193,030 | ✅ PASS |
| `trace_by_file_path(store_interface.py)` | 31 | 31 | 183,790 | ✅ PASS |
| `trace_by_req_id(SWR-002.1-01)` | 94 | 94 | 73,980 | ✅ PASS |
| `trace_by_req_id(RS-006-10)` | 127 | 127 | 57,428 | ✅ PASS |
| `trace_by_req_id(RS-001)` | 505 | 506 | 14,712 | ✅ PASS |
| `annotate_covers_layer()` | 700 | 702 | 20,284 | ✅ PASS |
| `impact_analysis([store.py])` | 1,938 | 1,943 | 1,531 | ✅ PASS |
| `impact_analysis([store_pg.py, analyzer.py])` | 1,975 | 1,978 | 3,966 | ✅ PASS |
| `impact_analysis([test_sil_runner.py])` | 4,850 | 4,904 | 1,728 | ✅ PASS |
| `_build_implements_edges()` | 120,883 | 121,473 | 249 | ✅ PASS |
| `bootstrap()` | 16,731,012 | 16,763,260 | 4 | ✅ PASS |

### Performance Gate Verification (raw timing)

| Gate | Threshold | Result |
|------|-----------|--------|
| `trace_by_req_id` | < 2.0s | ✅ PASS (max 505µs) |
| `trace_by_file_path` | < 2.0s | ✅ PASS (max 31µs) |
| `impact_analysis` | < 2.0s | ✅ PASS (max 4.9ms) |
| `bootstrap` | < 30.0s | ✅ PASS (16.7s) |
| `_build_implements_edges` | < 10.0s | ✅ PASS (121ms) |
| `_annotate_covers_layer` | < 5.0s | ✅ PASS (700µs) |

### Key Findings

1. **SQLite BFS is extremely fast** — `trace_by_file_path` median is ~31µs
2. **Recursive chain queries are fast** — `impact_analysis` on a multi-function file takes ~2-5ms
3. **`bootstrap()` is ~17s** — well under the 30s gate, even with full RTM + JSON + code scan + coverage import + implements derivation
4. **`_build_implements_edges()` is ~121ms** — fast for 523 implements edges derived from 4282 verifies + 182 covers

---

## P0-6: Main yuleOSH Coverage Import

### Coverage Test Run

```bash
pytest tests/test_store.py tests/test_store_extended.py tests/test_api_core.py \
      tests/test_api.py tests/test_adapter_smoke.py tests/test_build_metadata.py \
      --cov=src/yuleosh --cov-report=
```

**Results**: 252 tests passed, 10.02% module coverage across `src/yuleosh/`

### Coverage Import Results

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Verifies edges | 1,563 | 4,282 | **+2,719** |
| Total edges | 15,168 | 16,673 | **+1,505** |
| Implements edges | 358 | 523 | **+165** (preserved) |

### Acceptance Criteria Verification

```python
impact_analysis(store, ['src/yuleosh/store.py'])
```

| Check | Result |
|-------|--------|
| affected_reqs | 0 |
| affected_tests | 1 file (test_store.py), 7 functions |
| affected_functions | 57 |

> **Note**: `store.py` has 0 affected_reqs because the test file `test_store.py` is not listed in `requirement-traceability-matrix.md` or `req-test-mapping.json`, so no `covers` edge links requirements to the tests that exercise `store.py`. This is a pre-existing RTM data gap.

**Working impact paths** (complete chain: covers + verifies + implements):

| Code File | Affected Reqs | Reason |
|-----------|--------------|--------|
| `src/yuleosh/adapter/dspace_adapter.py` | 1 | Chain complete via RTM |
| `src/yuleosh/adapter/vector_adapter.py` | 12 | Chain complete via RTM |
| `src/yuleosh/ci/stages/traceability.py` | 5 | Chain complete via RTM |
| `src/yuleosh/pipeline/step_handlers/test_qualification.py` | 3 | Chain complete via RTM |
| `src/yuleosh/pipeline/step_handlers/review_misra_ci.py` | 1 | Chain complete via RTM |

### Verifies Edge Distribution

The coverage import added **2,719 new verifies edges** connecting test functions to code functions across main yuleOSH modules. These edges provide traceability even when the full requirement chain is incomplete — useful for change impact (impact_analysis returns affected tests even without requirement coverage for store.py: 7 test functions found).

---

## Instructions

```bash
# Run performance gates only (no benchmarks)
pytest tests/test_kg_performance.py::TestPerfGates -v --no-cov

# Run full performance benchmarks
pytest tests/test_kg_performance.py -v --no-cov -k "benchmark"

# Record baseline
pytest tests/test_kg_performance.py --benchmark-only --benchmark-save=baseline

# Re-import coverage data after main test run
python3 -c "
from yuleosh.knowledge_graph import get_store, import_data
from pathlib import Path
store = get_store()
import_data(store, project_dir=str(Path('.')), create_snapshot=False)
"
```
