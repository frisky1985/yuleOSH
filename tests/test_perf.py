# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Performance tests for yuleOSH pipeline and CI.

These tests verify that core operations complete within time budgets.
They should be run separately from the main test suite to avoid
environment-sensitive failures on slow CI runners.

Usage:
    pytest tests/test_perf.py -v
"""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.pipeline.run import (
    _parse_spec,
    PipelineSession,
    PIPELINE_STEPS,
    step_spec_check,
    step_super_analysis,
    step_hermes_prd,
)
from yuleosh.ci.run import find_test_files, run_plan_lint, CIResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

OSH_HOME = os.environ.get("OSH_HOME", os.path.join(os.path.dirname(__file__), ".."))


def _make_spec_with_requirements(tmpdir: str, count: int) -> str:
    """Create a spec file with `count` requirements, each with SHALL statements."""
    spec_path = os.path.join(tmpdir, "perf_spec.md")
    lines = [
        "# Performance Test Spec",
        "",
        "## Requirements",
        "",
    ]
    for i in range(count):
        lines.append(f"### Req-{i:04d}: Performance requirement {i}")
        lines.append("")
        for j in range(3):
            lines.append(f"- The system SHALL handle scenario {j} for Req-{i}.")
        lines.append("")
    for i in range(count // 2):
        lines.append(f"### GIVEN scenario {i}")
        lines.append(f"### WHEN action {i}")
        lines.append(f"### THEN outcome {i}")
        lines.append("")
    with open(spec_path, "w") as f:
        f.write("\n".join(lines))
    return spec_path


def _make_test_files(tmpdir: str, count: int) -> list[str]:
    """Create `count` test files in a tests/ subdirectory."""
    tests_dir = os.path.join(tmpdir, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    files = []
    for i in range(count):
        fname = os.path.join(tests_dir, f"test_perf_{i:04d}.py")
        with open(fname, "w") as f:
            f.write(f"""\
\"\"\"Perf test {i}.\"\"\"
def test_{i}():
    assert 1 + 1 == 2
""")
        files.append(fname)
    return files


# ------------------------------------------------------------------
# Pipeline perf test
# ------------------------------------------------------------------

def test_pipeline_10_requirements_under_30s():
    """Pipeline with 10 requirements must complete in < 30 seconds.

    This tests that _parse_spec, step creation, and iteration over
    PIPELINE_STEPS are performant.  It does not run actual subprocess
    steps (spec validation, test runner) since those depend on the
    environment.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = _make_spec_with_requirements(tmpdir, 10)

        t0 = time.perf_counter()

        # Test parsing performance
        parsed = _parse_spec(spec_path)
        assert len(parsed["requirements"]) == 10, f"Expected 10 requirements, got {len(parsed['requirements'])}"

        # Test session creation and step iteration
        session = PipelineSession("perf-test", spec_path)
        for step_key, agent, step_name, _handler in PIPELINE_STEPS:
            session.add_step(step_key, agent, step_name)

        elapsed = time.perf_counter() - t0
        assert elapsed < 30.0, (
            f"Pipeline with 10 requirements took {elapsed:.2f}s, "
            f"expected < 30s"
        )


# ------------------------------------------------------------------
# CI scan perf test
# ------------------------------------------------------------------

def test_ci_scan_7_test_files_under_5s():
    """CI test file discovery with 7 test files must complete in < 5 seconds."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _make_test_files(tmpdir, 7)

        t0 = time.perf_counter()

        # Test file discovery
        files = find_test_files(tmpdir)
        assert len(files) == 7, f"Expected 7 test files, found {len(files)}"

        # Test CIResult creation and plan-lint run
        ci = CIResult(1, "a1b2c3")
        run_plan_lint(tmpdir, ci)

        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0, (
            f"CI scan with 7 test files took {elapsed:.2f}s, "
            f"expected < 5s"
        )
