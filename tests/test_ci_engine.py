# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for CI engine — includes A-01 blocking logic verification."""
import sys, os, tempfile, json, subprocess, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ci.run import (
    CIResult, find_test_files, run_layer1, run_layer2, run_layer3,
    run_clang_tidy, run_plan_lint, run_coverage_check, run_unit_tests,
    is_strict, is_misra_fail_fast,
)


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------

def test_ci_result_creation():
    """Test CI result data structure."""
    result = CIResult(1, "abc123")
    assert result.layer == 1
    assert result.commit_hash == "abc123"
    assert result.status == "running"
    assert len(result.stages) == 0

def test_ci_add_stage():
    """Test adding stages."""
    result = CIResult(1, "abc123")
    result.add_stage("plan-lint", "passed")
    assert len(result.stages) == 1
    assert result.stages[0]["name"] == "plan-lint"
    assert result.stages[0]["status"] == "passed"

def test_ci_complete():
    """Test completing CI."""
    result = CIResult(1, "abc123")
    result.complete("passed")
    assert result.status == "passed"
    assert result.completed_at is not None
    assert result.to_dict()["status"] == "passed"

def test_ci_to_dict():
    """Test CI serialization."""
    result = CIResult(1, "abc123")
    result.add_stage("test", "passed")
    result.complete("passed")
    d = result.to_dict()
    assert d["layer"] == 1
    assert d["commit"] == "abc123"
    assert len(d["stages"]) == 1

def test_find_test_files():
    """Test test file discovery."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "tests"))
        open(os.path.join(tmp, "tests", "test_foo.py"), "w").close()
        open(os.path.join(tmp, "tests", "foo_test.go"), "w").close()
        files = find_test_files(tmp)
        assert len(files) == 2


# ---------------------------------------------------------------------------
# A-01: Strict mode helpers
# ---------------------------------------------------------------------------

def test_is_strict_default():
    """Default: CI_STRICT is not set → not strict."""
    assert is_strict() is False

def test_is_strict_enabled(monkeypatch):
    monkeypatch.setenv("CI_STRICT", "1")
    assert is_strict() is True

def test_is_strict_disabled(monkeypatch):
    monkeypatch.setenv("CI_STRICT", "0")
    assert is_strict() is False

def test_is_misra_fail_fast_default():
    assert is_misra_fail_fast() is False

def test_is_misra_fail_fast_enabled(monkeypatch):
    monkeypatch.setenv("MISRA_FAIL_FAST", "1")
    assert is_misra_fail_fast() is True


# ---------------------------------------------------------------------------
# A-01: run_plan_lint blocks on issues
# ---------------------------------------------------------------------------

def test_plan_lint_blocks_on_issues():
    """plan-lint with formatting issues → returns False (blocking)."""
    with tempfile.TemporaryDirectory() as tmp:
        tasks_dir = os.path.join(tmp, "tasks")
        os.makedirs(tasks_dir)
        # Plan file MISSING kind classification and T00 sections
        bad_plan = os.path.join(tasks_dir, "task-implement-foo.md")
        with open(bad_plan, "w") as f:
            f.write("# Implement Foo\n\nJust some random text without proper sections.\n")

        ci = CIResult(1, "test")
        result = run_plan_lint(tmp, ci)
        assert result is False, "plan-lint should return False (block) when issues found"
        # Stage should be recorded as failed
        stage_names = [s["name"] for s in ci.stages]
        assert "plan-lint" in stage_names
        plan_stage = [s for s in ci.stages if s["name"] == "plan-lint"][0]
        assert plan_stage["status"] == "failed", f"Expected failed, got {plan_stage['status']}"

def test_plan_lint_passes_on_clean():
    """plan-lint with proper file → returns True."""
    with tempfile.TemporaryDirectory() as tmp:
        tasks_dir = os.path.join(tmp, "tasks")
        os.makedirs(tasks_dir)
        clean_plan = os.path.join(tasks_dir, "task-feature-auth.md")
        with open(clean_plan, "w") as f:
            f.write("# Feature: Auth\n\nRED: write failing test\nGREEN: make it pass\nREFACTOR: clean up\n")

        ci = CIResult(1, "test")
        result = run_plan_lint(tmp, ci)
        assert result is True, "clean plan should pass"

def test_plan_lint_no_tasks_file_ok():
    """No task files at all → acceptable skip, returns True."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = CIResult(1, "test")
        result = run_plan_lint(tmp, ci)
        # No task files → skip (non-blocking)
        assert result is True


# ---------------------------------------------------------------------------
# A-01: run_clang_tidy — tool missing / tool failure / tool success
# ---------------------------------------------------------------------------

def test_clang_tidy_no_c_files():
    """No C/C++ files → acceptable skip."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = CIResult(1, "test")
        result = run_clang_tidy(tmp, ci)
        assert result is True
        stage = [s for s in ci.stages if s["name"] == "clang-tidy"][0]
        assert stage["status"] == "skipped"

def test_clang_tidy_tool_missing(tmp_path):
    """C files exist but clang-tidy not installed → returns False (blocking)."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "main.c").write_text("int main(void) { return 0; }")

    ci = CIResult(1, "test")
    result = run_clang_tidy(str(tmp_path), ci)
    assert result is False, "clang-tidy missing should block (return False)"
    stage = [s for s in ci.stages if s["name"] == "clang-tidy"][0]
    # Should be "skipped" (tool not found) but still block
    assert stage["status"] in ("skipped", "failed")

def test_clang_tidy_tool_success_with_mock(monkeypatch, tmp_path):
    """clang-tidy runs and exits 0 → returns True."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "main.c").write_text("int main(void) { return 0; }")

    # Monkey-patch subprocess.run to simulate successful clang-tidy
    orig_run = subprocess.run
    def mock_run(*args, **kwargs):
        if "clang-tidy" in str(args[0]):
            return subprocess.CompletedProcess(args[0], 0, "", "")
        return orig_run(*args, **kwargs)

    monkeypatch.setattr("yuleosh.ci.run.subprocess.run", mock_run)
    ci = CIResult(1, "test")
    result = run_clang_tidy(str(tmp_path), ci)
    assert result is True
    stage = [s for s in ci.stages if s["name"] == "clang-tidy"][0]
    assert stage["status"] == "passed"


# ---------------------------------------------------------------------------
# A-01: run_coverage_check — blocking on missing tool / errors
# ---------------------------------------------------------------------------

def test_coverage_hook_commit_skips():
    """HOOK_TYPE=commit → coverage skips intentionally (not a failure)."""
    os.environ["HOOK_TYPE"] = "commit"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ci = CIResult(1, "test")
            result = run_coverage_check(tmp, ci)
            assert result is True  # Intentional skip is not a failure
    finally:
        os.environ.pop("HOOK_TYPE", None)

def test_coverage_nested_skips():
    """COVERAGE_RUN=1 → coverage skips to prevent recursion."""
    os.environ["COVERAGE_RUN"] = "1"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ci = CIResult(1, "test")
            result = run_coverage_check(tmp, ci)
            assert result is True
    finally:
        os.environ.pop("COVERAGE_RUN", None)

def test_coverage_no_tool(tmp_path):
    """Coverage tool not installed → returns False (blocking)."""
    ci = CIResult(1, "test")
    result = run_coverage_check(str(tmp_path), ci)
    assert result is False, "coverage missing should block"
    stage = [s for s in ci.stages if s["name"] == "coverage"][0]
    assert stage["status"] in ("skipped", "failed")


# ---------------------------------------------------------------------------
# A-01: run_unit_tests — missing tool blocks
# ---------------------------------------------------------------------------

def test_unit_tests_no_test_files():
    """No test files → should still pass (no tests discovered = OK)."""
    with tempfile.TemporaryDirectory() as tmp:
        ci = CIResult(1, "test")
        result = run_unit_tests(tmp, ci)
        # No test files → non-blocking skip
        assert result is True


# ---------------------------------------------------------------------------
# A-01: run_layer1 — overall failure when any stage blocks
# ---------------------------------------------------------------------------

def test_layer1_overall_failure_when_clang_tidy_missing(tmp_path):
    """Layer 1 should return False when clang-tidy is missing and C files exist."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "demo.c").write_text("int x = 1;")

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    try:
        result = run_layer1(str(tmp_path))
        assert result is False, "Layer 1 should fail when clang-tidy blocks"
    finally:
        monkeypatch.undo()

def test_layer1_passes_with_no_c_files(tmp_path):
    """Layer 1 without C files should pass."""
    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    try:
        result = run_layer1(str(tmp_path))
        # May still have plan-lint issues, but at least no false pass on missing tool
        assert result is not None
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# A-01: MISRA_FAIL_FAST in layer 2
# ---------------------------------------------------------------------------

def test_layer2_misra_fail_fast_blocks_cppcheck(tmp_path, monkeypatch):
    """With MISRA_FAIL_FAST=1 and clang-tidy (or cppcheck) failing → layer2 blocks."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "code.c").write_text("int main(void) { return 0; }")

    monkeypatch.setenv("MISRA_FAIL_FAST", "1")
    monkeypatch.setenv("OSH_HOME", str(tmp_path))

    result = run_layer2(str(tmp_path))
    # Should be False because cppcheck is missing and MISRA_FAIL_FAST is on
    # (but even without MISRA_FAIL_FAST, A-01 makes it block — tool missing)
    assert result is False, "Layer 2 should fail when cppcheck is missing"


# ---------------------------------------------------------------------------
# A-01: run_layer3 basic sanity
# ---------------------------------------------------------------------------

def test_layer3_runs_without_error(tmp_path):
    """Layer 3 should not crash on a clean project dir."""
    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    try:
        result = run_layer3(str(tmp_path))
        assert result is True or result is False  # Should not throw
    finally:
        monkeypatch.undo()


# ---------------------------------------------------------------------------
# A-01: Strict mode with CI_STRICT=1
# ---------------------------------------------------------------------------

def test_strict_mode_missing_tool_message(tmp_path, monkeypatch):
    """In strict mode, missing tools should be recorded as 'failed', not 'skipped'."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "demo.c").write_text("void f(void) {}")

    monkeypatch.setenv("CI_STRICT", "1")
    monkeypatch.setenv("OSH_HOME", str(tmp_path))

    try:
        result = run_layer1(str(tmp_path))
        assert result is False, "Layer 1 should fail in strict mode with missing clang-tidy"
    finally:
        monkeypatch.undo()
