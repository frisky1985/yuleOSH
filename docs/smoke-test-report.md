# yuleOSH v0.1.0 — Smoke Test Report 🧪

> **Date:** 2026-06-05
> **Environment:** macOS (arm64), Python 3.13
> **Commit:** 54210a0
> **Status:** ✅ ALL PASSED

---

## 1. Smoke Test Results

### 1.1 Spec Validation

```bash
$ python3 src/spec/validate.py docs/spec.md
```

| Metric | Result |
|:-------|:-------|
| Requirements Parsed | **7** |
| Scenarios Parsed | **3** |
| Total SHALLs | **20** |
| Coverage Score | **100.0%** |
| Threshold (80%) | ✅ PASS |

**Verdict:** ✅ PASS

---

### 1.2 Agent Pipeline

```bash
$ python3 src/pipeline/run.py docs/spec.md
```

| Step | Agent | Description | Result |
|:-----|:------|:------------|:-------|
| 1/9 | 小明 | OpenSpec 合规检查 | ✅ Passed |
| 2/9 | 小明 | S.U.P.E.R 启动分析 | ✅ Passed |
| 3/9 | Hermes | 产品需求分析 | ✅ Passed |
| 4/9 | 小明 | 内部评审 | ✅ Passed |
| 5/9 | Claude | 架构设计 | ✅ Passed |
| 6/9 | Claude | 开发实现 | ✅ Passed |
| 7/9 | Claude | 自测验证 | ✅ Passed |
| 8/9 | Hermes | 代码审查 | ✅ Passed |
| 9/9 | 小明 | 最终报告 | ✅ Passed |

- **Session:** `run-20260605-005318`
- **Errors:** 0
- **Duration:** ~0.25s

**Verdict:** ✅ PASS

---

### 1.3 CI Layer 1: Development Verification

```bash
$ python3 src/ci/run.py 1
```

| Stage | Result | Details |
|:------|:-------|:--------|
| plan-lint | ⚠️ Warnings (non-blocking) | Sprint 2/3 plans missing kind/task sections |
| clang-tidy | ⏭️ Skipped | No C/C++ files |
| Unit Tests (8 test files) | ✅ ALL PASSED | evidence_engine ✓ perf ✓ spec_engine ✓ spec_ext ✓ store ✓ e2e ✓ review ✓ ci ✓ |
| Coverage Check | ✅ PASS | 39.8% line / 39.8% condition (threshold: 38%) |

**Verdict:** ✅ PASS (ALL STAGES)

---

### 1.4 Evidence Pack Generation

```bash
$ python3 src/evidence/pack.py
```

| Artifact | Format | Status |
|:---------|:-------|:-------|
| Traceability Matrix | Markdown | ✅ Generated |
| Requirement Coverage | Markdown | ✅ Generated |
| Code Coverage Report | Markdown | ✅ Generated |
| Review Log Summary | Markdown | ✅ Generated |
| Review Log (Raw) | JSON | ✅ Generated |
| Compliance Pack | ZIP | ✅ Generated |

- **Input:** 7 requirements, 3 scenarios, 4 review sessions, 17 CI results
- **Output directory:** `.osh/evidence/`
- **Artifacts:** 5

**Verdict:** ✅ PASS

---

### 1.5 Unit Tests (pytest)

```bash
$ python3 -m pytest tests/ --ignore=tests/test_e2e.py -q
```

| Result | Count |
|:-------|:------|
| Passed | **35** |
| Failed | **0** |
| Skipped | **0** |

**Verdict:** ✅ PASS

---

### 1.6 Full Test Suite (all 44 tests)

```bash
$ python3 -m pytest tests/ -q
```

| Result | Count |
|:-------|:------|
| Passed | **43** |
| Failed | **0** |
| Skipped | **1** (test_e2e_dashboard_server) |

**Note:** `test_e2e_dashboard_server` is skipped because it requires a running dashboard server. All 43 executable tests pass.

**Verdict:** ✅ PASS

---

## 2. Comprehensive Results Summary

| # | Test | Status |
|:-:|:-----|:------:|
| 1 | Spec Validation (`src/spec/validate.py`) | ✅ |
| 2 | Agent Pipeline (`src/pipeline/run.py`) | ✅ |
| 3 | CI Layer 1 (`src/ci/run.py 1`) | ✅ |
| 4 | Evidence Pack (`src/evidence/pack.py`) | ✅ |
| 5 | Pytest (without e2e, 35 tests) | ✅ |
| 6 | Full Pytest Suite (43 passed, 1 skipped) | ✅ |

**Overall Verdict:** ✅ **ALL SMOKE TESTS PASSED** — yuleOSH v0.1.0 is launch-ready.

---

*Generated: 2026-06-05 00:53 CST | Smoke Test Suite: T8-1*
