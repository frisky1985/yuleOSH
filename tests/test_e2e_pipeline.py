# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""E2E integration tests for the full pipeline - all dependencies mocked.

Covers:
  - AC-01-01: Normal path (valid spec → pipeline → evidence)
  - AC-01-03: Pipeline step coverage ≥80%
  - AC-01-04: Invalid spec input (exception path)
  - AC-01-05: Mock failure (LLM call exception → graceful degradation)
  - AC-01-06: Execution time ≤30s (SHOULD)
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ======================================================================
# Fixtures
# ======================================================================

SPEC_CONTENT_VALID = """# Test Specification

> REQ-001: Pipeline Processing

### Req Pipe-01: Pipeline Processing
- The system SHALL process pipelines
- The system SHALL retry on failure

### Req Auth-01: User Authentication
- The system SHALL authenticate users

### GIVEN a valid spec WHEN run THEN pass
"""

SPEC_CONTENT_INVALID_EMPTY = "# Empty spec\n"


def _make_fake_llm(content: str = "mock analysis result") -> callable:
    """Build a fake LLM client that returns deterministic content."""
    def fake_llm(system_prompt: str, user_prompt: str, **kwargs) -> dict:
        return {
            "content": content,
            "model": "test-model",
            "usage": {
                "total_tokens": 50,
                "prompt_tokens": 20,
                "completion_tokens": 30,
            },
        }
    return fake_llm


def _make_fake_llm_exception() -> callable:
    """Build a fake LLM client that raises on first call."""
    call_count = [0]

    def fake_llm(system_prompt: str, user_prompt: str, **kwargs) -> dict:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Mock LLM failure")
        # Subsequent calls succeed
        return _make_fake_llm()(system_prompt, user_prompt, **kwargs)

    return fake_llm


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for spec validation step (step_spec_check)."""
    with mock.patch("subprocess.run") as mrun:
        mrun.return_value.returncode = 0
        mrun.return_value.stdout = json.dumps({
            "valid": True,
            "error_count": 0,
            "issues": [],
            "coverage": {"score": 85.0},
        })
        mrun.return_value.stderr = ""
        yield mrun


@pytest.fixture
def mock_all_deps():
    """Disable store and notifications so pipeline runs purely in-memory + on-disk."""
    with mock.patch("yuleosh.pipeline.stages._store", None), \
         mock.patch("yuleosh.pipeline.session._store", None), \
         mock.patch("yuleosh.pipeline.orchestrator._notify", None):
        yield


# ======================================================================
# AC-01-01: Normal path - valid spec through full pipeline
# ======================================================================

class TestE2ENormal:
    """S2-REQ-001: E2E 全流程正常路径 (AC-01-01, AC-01-03)."""

    def test_e2e_valid_spec_to_evidence(self, tmp_path, mock_all_deps, mock_subprocess_run):
        """GIVEN valid OpenSpec WHEN pipeline runs THEN steps complete."""
        from yuleosh.pipeline.run import run_pipeline

        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_CONTENT_VALID)

        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            session = run_pipeline(
                spec_path=str(spec),
                name="e2e-test",
                llm_client=_make_fake_llm(),
                mock=True,
            )
    
        # Session completed
        assert session.status == "completed", f"Expected completed, got {session.status}"

        # All steps completed
        for step in session.steps:
            assert step["status"] == "completed", f"Step {step['name']} not completed: {step['status']}"

        # All 10 pipeline steps executed
        assert len(session.steps) == 10, f"Expected 10 steps, got {len(session.steps)}"

        # Artifacts set for all step keys (AC-01-03: step coverage 10/10 = 100%)
        expected_keys = {
            "spec-check", "super-analysis", "prd", "internal-review",
            "architecture", "development", "test-planning", "self-test",
            "code-review", "final-report",
        }
        assert session.artifacts.keys() >= expected_keys, (
            f"Missing artifacts: {expected_keys - session.artifacts.keys()}"
        )

        # Output files exist on disk
        for key, path in session.artifacts.items():
            assert os.path.exists(path), f"Artifact file missing: {key} -> {path}"

        # Session saved to disk
        session_json = session.session_dir / "session.json"
        assert session_json.exists(), "Session JSON not persisted"

        # Token usage tracked
        assert session.token_usage_total > 0
        assert len(session.token_usage_steps) > 0

    def test_e2e_ci_layers_each_report_status(self, tmp_path, mock_all_deps):
        """GIVEN ci layers WHEN run_all executes THEN each layer reports passed."""
        from yuleosh.ci.run import run_all

        project_dir = str(tmp_path)

        # Create minimal ci dir so helpers don't crash
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)

        # Mock all subprocess calls to succeed
        with mock.patch("subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = "{}"
            mrun.return_value.stderr = ""

            # Mock coverage JSON to exist so run_coverage_check doesn't crash
            cov_json = tmp_path / "coverage.json"
            cov_json.write_text(json.dumps({
                "totals": {"percent_covered": 100.0, "percent_covered_condition": 100.0}
            }))

            # Mock git — don't patch _save_layer_result, let it persist for dep chain
            with mock.patch("yuleosh.ci.runner.git_commit_hash", return_value="abc1234"):
                # L1 needs tests directory
                tests_dir = tmp_path / "tests"
                tests_dir.mkdir(exist_ok=True)
                (tests_dir / "test_dummy.py").write_text("def test_pass(): pass")

                result = run_all(project_dir=project_dir)
                assert result, "run_all should return True (all layers passed)"

    # ======================================================================
    # AC-01-03: Step coverage ≥80%
    # ======================================================================

    def test_e2e_step_coverage_ge_80(self, tmp_path, mock_all_deps, mock_subprocess_run):
        """SHOULD cover ≥80% of pipeline steps."""
        from yuleosh.pipeline.run import run_pipeline, PIPELINE_STEPS

        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_CONTENT_VALID)

        session = run_pipeline(
            spec_path=str(spec),
            name="step-cov-test",
            llm_client=_make_fake_llm(),
            mock=True,
        )

        total_steps = len(PIPELINE_STEPS)
        completed = sum(1 for s in session.steps if s["status"] == "completed")
        ratio = completed / total_steps

        assert ratio >= 0.8, (
            f"Step coverage {ratio:.0%} ({completed}/{total_steps}) < 80%"
        )


# ======================================================================
# AC-01-04: Invalid spec input - exception path
# ======================================================================

class TestE2EError:
    """S2-REQ-001 异常路径 (AC-01-04, AC-01-05)."""

    def test_e2e_invalid_spec_path_not_found(self, tmp_path, mock_all_deps):
        """GIVEN spec file doesn't exist WHEN pipeline runs THEN reports error."""
        from yuleosh.pipeline.run import run_pipeline

        nonexistent = tmp_path / "no-such-spec.md"
        session = run_pipeline(
            spec_path=str(nonexistent),
            name="e2e-invalid-path",
            llm_client=_make_fake_llm(),
            mock=True,
        )
        # Pipeline should handle gracefully - session failed but no crash
        assert session.status == "failed"
        assert len(session.errors) > 0

    def test_e2e_llm_exception_graceful_degradation(self, tmp_path, mock_all_deps, mock_subprocess_run):
        """GIVEN LLM raises exception WHEN pipeline runs THEN step fails gracefully."""
        from yuleosh.pipeline.run import run_pipeline

        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_CONTENT_VALID)

        session = run_pipeline(
            spec_path=str(spec),
            name="e2e-llm-fail",
            llm_client=_make_fake_llm_exception(),
            mock=True,
        )

        # Pipeline stops at first step that calls LLM (super-analysis, step index 1)
        assert session.status == "failed"
        # Some steps completed before the failure
        completed = [s for s in session.steps if s["status"] == "completed"]
        failed = [s for s in session.steps if s["status"] == "failed"]
        assert len(completed) >= 1, "At least spec-check should complete"
        assert len(failed) == 1, "Exactly one step should fail"
        assert len(session.errors) > 0

    def test_e2e_empty_spec_no_crash(self, tmp_path, mock_all_deps, mock_subprocess_run):
        """GIVEN empty spec WHEN pipeline runs THEN doesn't crash."""
        from yuleosh.pipeline.run import run_pipeline

        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_CONTENT_INVALID_EMPTY)

        # Mock subprocess to return errors so spec check fails
        with mock.patch("subprocess.run") as mrun:
            mrun.return_value.returncode = 0
            mrun.return_value.stdout = json.dumps({
                "valid": False,
                "error_count": 0,
                "issues": [],
                "coverage": {"score": 0},
            })
            mrun.return_value.stderr = ""
            session = run_pipeline(
                spec_path=str(spec),
                name="e2e-empty-spec",
                llm_client=_make_fake_llm(),
                mock=True,
            )
            # Either completed or failed - no crash
            assert session.status in ("completed", "failed")


# ======================================================================
# AC-01-06: Performance gate (SHOULD)
# ======================================================================

class TestE2EPerformance:
    """S2-REQ-001.6: E2E execution time ≤30s (SHOULD)."""

    def test_e2e_runtime_under_30s(self, tmp_path, mock_all_deps, mock_subprocess_run):
        """Fully mocked pipeline should complete within 30 seconds."""
        from yuleosh.pipeline.run import run_pipeline

        spec = tmp_path / "spec.md"
        spec.write_text(SPEC_CONTENT_VALID)

        start = time.monotonic()
        session = run_pipeline(
            spec_path=str(spec),
            name="e2e-perf",
            llm_client=_make_fake_llm(),
            mock=True,
        )
        elapsed = time.monotonic() - start

        assert session.status == "completed"
        assert elapsed <= 30, f"E2E test took {elapsed:.1f}s, exceeds 30s limit"
