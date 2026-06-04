# yuleOSH Dogfooding Gaps — Fix Report

> Generated: 2026-06-04T16:04
> Fixes applied to the 5 critical gaps identified during self-dogfooding.

---

## ✅ GAP-1: Evidence Pack 硬编码 docs/spec.md

**File**: `src/evidence/pack.py`

**Fix**: `generate_evidence()` now accepts an optional `spec_path` parameter and forwards it to `collect_requirements()`. The CLI `main()` also accepts a spec path argument.

```python
def generate_evidence(project_dir: str = None, spec_path: str = None):
    collector.collect_requirements(spec_path=spec_path)
```

When no spec_path is given, it falls back to the existing default (`docs/spec.md` under project_dir).

**Test**: `python3 src/evidence/pack.py self/spec.md` — now correctly collects requirements from any spec path.

---

## ✅ GAP-2: Pipeline 步骤仅生成空模板

**Files**: `src/pipeline/run.py`

**Fixes applied to 5 step handlers:**

### `step_super_analysis`
- Now reads actual requirements from the spec file (via `_read_spec_requirements`)
- Includes requirement count, SHALL statement count, scenario count in the report
- Lists all 9 pipeline steps in the Execution section
- Each requirement shows its SHALL count

### `step_hermes_prd`
- Maps all spec SHALL statements into the PRD as actionable checklist items
- Lists scenarios mapped to test strategy
- Shows both requirement and scenario counts

### `step_claude_arch`
- Discovers actual source directories and files
- Counts files by type
- Detects tech stack (Python, Shell, Web, Go, Rust)
- Lists directory structure and source file inventory
- Generates a real ADR based on detected technology

### `step_claude_dev`
- Counts lines of code (source + test + total)
- Enumerates source and test file counts
- Runs `git log` to show recent commit history
- Computes test-to-source ratio

### `step_claude_test`
- Runs real test command (`pytest` for Python, `go test` for Go projects)
- Parses test output to extract pass/fail counts
- Includes full test output in the report
- Lists spec scenarios

### Status Race Condition Fix
- `session.status` is set to `"completed"` **before** `step_final_report` executes
- Final report now correctly shows `"completed"` instead of `"created"` or `"running"`

**Helper functions added**:
- `_read_spec_requirements(spec_path)` — parses `### Req-XXX:` headers and collects SHALL/SHOULD statements
- `_count_spec_scenarios(spec_path)` — parses `### Scenario:` headers

---

## ✅ GAP-3: Docstring 和类型改进

**Files**: `src/pipeline/run.py`, `src/review/run.py`

Added comprehensive docstrings to all previously undocumented methods:

| File | Methods fixed |
|------|---------------|
| `src/pipeline/run.py` | `_ensure_session_dir`, `add_step`, `start_step`, `complete_step`, `fail_step`, `set_artifact`, `_save`, `to_dict`, `status_pipeline` |
| `src/review/run.py` | `ReviewFinding.to_dict`, `ReviewResult.add_finding`, `ReviewResult.to_dict`, `ReviewSession.add_review`, `ReviewSession.save`, `ReviewSession.to_dict` |

---

## ✅ GAP-4: `self/` 目录不应被 Git 追踪

**File**: `.gitignore`

Added:
```
self/
```

This ensures dogfooding projects (the `self/` directory) remain local-only and are not committed to the repository.

---

## ✅ GAP-5: 项目统计应排除 `self/`

**File**: `src/cli/stats.py`

Added a shared `EXCLUDED_DIRS` set:
```python
EXCLUDED_DIRS = {"self", ".osh", "__pycache__", ".git", "node_modules", "venv", ".venv"}
```

Applied to both `os.walk` calls:
- `count_source_lines()` — excludes `self/`, `.osh/`, and other build artifacts
- `count_tests()` — excludes `self/`, `.osh/`, and cache directories

This prevents stats from counting dogfooding artifacts in project metrics.

---

## Summary

| Gap | Severity | Status | Files Changed |
|:----|:--------:|:------:|:--------------|
| GAP-1: Evidence pack hardcoded spec path | High | ✅ Fixed | `src/evidence/pack.py` |
| GAP-2: Pipeline step empty templates | High | ✅ Fixed | `src/pipeline/run.py` |
| GAP-3: Missing docstrings/types | Medium | ✅ Fixed | `src/pipeline/run.py`, `src/review/run.py` |
| GAP-4: `self/` tracked by git | Medium | ✅ Fixed | `.gitignore` |
| GAP-5: Stats includes `self/` | Medium | ✅ Fixed | `src/cli/stats.py` |

**Tests**: 33/33 passing (no regressions)
**Pipeline**: All 9 steps produce meaningful content with real project data
