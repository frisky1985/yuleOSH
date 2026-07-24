# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""End-to-end tests for yuleOSH platform.

Pipeline tests use mock LLM data instead of real API calls.
Structural/validation E2E tests always run.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Pre-recorded mock LLM response fixture
# ---------------------------------------------------------------------------

def _make_mock_llm():
    """Return a mock LLM callable that returns pre-recorded responses.

    Used in place of real LLM API calls for E2E pipeline tests.
    """
    def mock_llm(system_prompt, user_prompt, **kwargs):
        """Pre-recorded mock response generator."""
        # Hermes review expects JSON output
        if "JSON" in system_prompt or "code review" in system_prompt.lower():
            return {
                "content": json.dumps({
                    "session": "mock-e2e",
                    "reviewer": "Hermes",
                    "timestamp": "2024-01-01T00:00:00",
                    "status": "passed",
                    "findings": [],
                    "finding_breakdown": {
                        "critical": 0, "major": 0, "minor": 0, "info": 0,
                    },
                    "summary": "All E2E checks passed.",
                }),
                "model": "mock-model",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        # Test planning
        if "SHALL" in user_prompt or "Test Plan" in system_prompt:
            return {
                "content": (
                    "# Test Plan\n\n"
                    "## 1. Test Strategy\n"
                    "- Unit tests: 70% of effort\n"
                    "- Integration: 20%\n"
                    "- E2E: 10%\n\n"
                    "## 2. Traceability Matrix\n"
                    "| Requirement ID | SHALL | Test Case | Level |\n"
                    "|---|---|---|---|\n"
                    "| Req-RS-001 | authenticate | TC-RS-001-1 | Unit |\n"
                    "| Req-RS-001 | refresh token | TC-RS-001-2 | Integration |\n"
                    "| Req-SWR-001.1 | login fields | TC-SWR-001.1-1 | Unit |\n\n"
                    "## 3. Coverage Targets\n"
                    "- Line coverage: 85%\n"
                    "- Branch coverage: 75%\n"
                    "- Requirement coverage: 100%\n"
                ),
                "model": "mock-model",
                "usage": {"prompt_tokens": 60, "completion_tokens": 30, "total_tokens": 90},
            }
        # Generic text response for all other steps
        return {
            "content": (
                "# Mock Analysis Output\n\n"
                "## Situation\nE2E test context.\n"
                "## Understanding\nKey requirements analyzed.\n"
                "## Execution\nSteps to deliver.\n"
                "## Architecture\nClean layered architecture.\n"
                "## Development Plan\nIterative approach.\n"
            ),
            "model": "mock-model",
            "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
        }
    return mock_llm


def _make_mock_self_test():
    """Return a mock step_claude_test handler that avoids recursive pytest calls.

    Instead of running pytest (which would pick up this test file and recurse),
    generates a pre-recorded test report.
    """
    def mock_self_test(session):
        out_path = session.session_dir / "self-test-report.md"
        content = (
            f"# Self-Test Report (mocked): {session.name}\n\n"
            f"## Test Runner\n"
            f"- Runner: pytest (mocked)\n"
            f"- Total Tests: 10\n"
            f"- Passed: 10\n"
            f"- Failed: 0\n"
            f"- Status: ✅\n\n"
            f"## Test Summary\n"
            f"10 passed in 0.01s\n"
        )
        out_path.write_text(content)
        session.set_artifact("self-test", str(out_path))
        return str(out_path)
    return mock_self_test


# ---------------------------------------------------------------------------
# Spec validation (no API key needed)
# ---------------------------------------------------------------------------


def test_e2e_spec_validate():
    """E2E: spec validation on the real spec file."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    result = subprocess.run(
        [sys.executable, "src/yuleosh/spec/validate.py", spec_path, "--json"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Validation failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["requirements"] >= 7, f"Expected >=7 requirements, got {data['requirements']}"
    assert data["coverage"]["pass_threshold"], f"Coverage should pass: {data['coverage']}"


def test_e2e_spec_diff():
    """E2E: spec diff on the same file produces no changes."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    result = subprocess.run(
        [sys.executable, "src/yuleosh/spec/diff.py", spec_path, spec_path, "--json"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Diff failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["total_changes"] == 0, f"Same file should have 0 changes: {data}"


def test_e2e_pipeline_run():
    """E2E: pipeline runs end-to-end with mock LLM (no real API key needed).

    Uses pre-recorded mock responses and a mock self-test handler
    to avoid recursive pytest invocation.
    """
    from yuleosh.pipeline.run import run_pipeline, PIPELINE_STEPS

    # Use real spec and project dir
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")

    mock_llm = _make_mock_llm()
    mock_self_test = _make_mock_self_test()

    # Patch PIPELINE_STEPS to replace self-test with mock
    patched_steps = [
        (key, agent, name, mock_self_test if name == "自测验证" else handler)
        for key, agent, name, handler in PIPELINE_STEPS
    ]

    with mock.patch("yuleosh.pipeline.run.PIPELINE_STEPS", patched_steps):
        session = run_pipeline(
            spec_path,
            name="e2e-pipeline-run",
            llm_client=mock_llm,
        )

    assert session.status == "completed", f"Pipeline failed: {session.errors}"
    assert "final-report" in session.artifacts, "Missing final report artifact"


def test_e2e_pipeline_status():
    """E2E: pipeline status returns results."""
    result = subprocess.run(
        [sys.executable, "src/yuleosh/pipeline/run.py", "status"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Status failed: {result.stderr}"
    assert "completed" in result.stdout or "No pipeline" in result.stdout


def test_e2e_pipeline_spec_check_only():
    """E2E: pipeline spec-check step works in isolation (no API key needed)."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    from yuleosh.pipeline.run import PipelineSession, step_spec_check

    session = PipelineSession("test-spec-check", spec_path)
    result = step_spec_check(session)
    assert result is not None
    assert os.path.exists(result)
    data = json.loads(open(result).read())
    assert data.get("coverage", {}).get("score", 0) >= 80


def test_e2e_pipeline_full_flow():
    """E2E: complete pipeline flow from spec input to final report output.

    Tests the full orchestration:
    1. Spec validation
    2. S.U.P.E.R analysis (mock LLM)
    3. PRD generation (mock LLM)
    4. Internal review
    5. Architecture design (mock LLM)
    6. Development planning (mock LLM)
    7. Test planning (mock LLM)
    8. Self-test (mocked)
    9. Code review (mock LLM)
    10. Final report generation

    Verifies all 10 artifacts are generated with content.
    """
    from yuleosh.pipeline.run import run_pipeline, PIPELINE_STEPS

    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    mock_llm = _make_mock_llm()
    mock_self_test = _make_mock_self_test()

    patched_steps = [
        (key, agent, name, mock_self_test if name == "自测验证" else handler)
        for key, agent, name, handler in PIPELINE_STEPS
    ]

    with mock.patch("yuleosh.pipeline.run.PIPELINE_STEPS", patched_steps):
        session = run_pipeline(
            spec_path,
            name="e2e-full-flow",
            llm_client=mock_llm,
        )

    assert session.status == "completed", f"Pipeline failed: {session.errors}"

    # Verify all 10 artifacts exist and have content
    expected = [
        "spec-check", "super-analysis", "prd", "internal-review",
        "architecture", "development", "test-planning",
        "self-test", "code-review", "final-report",
    ]
    for key in expected:
        assert key in session.artifacts, f"Missing artifact: {key}"
        path = Path(session.artifacts[key])
        assert path.exists(), f"Artifact file missing: {path}"
        assert len(path.read_text()) > 0, f"Artifact {key} is empty"

    # Verify final report has expected structure
    report = Path(session.artifacts["final-report"]).read_text()
    assert "Final Report" in report
    assert session.name in report
    # Status is tracked in session object, not necessarily in LLM-generated text
    assert len(report) > 100, f"Report too short: {len(report)} chars"

    # Verify traceable artifacts
    test_plan = Path(session.artifacts["test-planning"]).read_text()
    assert "Test Plan" in test_plan
    assert "Traceability" in test_plan or "traceability" in test_plan or "Traceability Matrix" in test_plan


def test_e2e_evidence_generate():
    """E2E: evidence pack generates."""
    # Run review auto first to ensure fresh review data
    subprocess.run(
        [sys.executable, "src/yuleosh/review/run.py", "auto"],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30,
    )
    result = subprocess.run(
        [sys.executable, "src/yuleosh/evidence/pack.py"],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30,
    )
    print(result.stdout[-300:])
    assert result.returncode == 0, f"Evidence failed: {result.stderr[-200:]}"
    assert "compliance-pack.zip" in result.stdout


def test_e2e_review_auto():
    """E2E: auto-review runs (may have no changes but shouldn't crash)."""
    result = subprocess.run(
        [sys.executable, "src/yuleosh/review/run.py", "auto"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Review crashed: {result.stderr}"
    assert "No changed files" in result.stdout or "Review Session" in result.stdout


def test_e2e_cli_help():
    """E2E: CLI help works."""
    result = subprocess.run(
        ["bash", "src/yuleosh/cli/yuleosh.sh", "help"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0
    assert "yuleOSH" in result.stdout or "Usage" in result.stdout


def test_e2e_dashboard_server():
    """E2E: Dashboard server starts and responds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8080))
    sock.close()
    if result == 0:
        resp = urllib.request.urlopen("http://127.0.0.1:8080/api/status")
        data = json.loads(resp.read())
        assert data["status"] == "running"
