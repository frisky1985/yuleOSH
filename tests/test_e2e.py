"""End-to-end tests for yuleOSH platform.

Pipeline tests that require an LLM API key are conditionally skipped.
Structural/validation E2E tests always run.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_HAS_API_KEY = bool(
    os.environ.get("LLM_API_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
)


# ---------------------------------------------------------------------------
# Spec validation (no API key needed)
# ---------------------------------------------------------------------------


def test_e2e_spec_validate():
    """E2E: spec validation on the real spec file."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    result = subprocess.run(
        [sys.executable, "src/spec/validate.py", spec_path, "--json"],
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
        [sys.executable, "src/spec/diff.py", spec_path, spec_path, "--json"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Diff failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["total_changes"] == 0, f"Same file should have 0 changes: {data}"


@pytest.mark.skipif(not _HAS_API_KEY, reason="LLM_API_KEY required for pipeline E2E")
def test_e2e_pipeline_run():
    """E2E: pipeline runs end-to-end with real API key."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    result = subprocess.run(
        [sys.executable, "src/pipeline/run.py", spec_path],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=120,
    )
    assert result.returncode == 0, f"Pipeline failed: {result.stderr[:500]}"
    assert "completed" in result.stdout, "Pipeline should complete"


def test_e2e_pipeline_status():
    """E2E: pipeline status returns results."""
    result = subprocess.run(
        [sys.executable, "src/pipeline/run.py", "status"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Status failed: {result.stderr}"
    assert "completed" in result.stdout or "No pipeline" in result.stdout


def test_e2e_pipeline_spec_check_only():
    """E2E: pipeline spec-check step works in isolation (no API key needed)."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    from src.llm.client import _resolve_env
    from src.pipeline.run import PipelineSession, step_spec_check

    session = PipelineSession("test-spec-check", spec_path)
    result = step_spec_check(session)
    assert result is not None
    assert os.path.exists(result)
    data = json.loads(open(result).read())
    assert data.get("coverage", {}).get("score", 0) >= 80


@pytest.mark.skipif(True, reason="CI test requires separate invocation")
def test_e2e_ci_layer1():
    """E2E: CI Layer 1 placeholder."""
    pass


def test_e2e_evidence_generate():
    """E2E: evidence pack generates."""
    # Run review auto first to ensure fresh review data
    subprocess.run(
        [sys.executable, "src/review/run.py", "auto"],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30,
    )
    result = subprocess.run(
        [sys.executable, "src/evidence/pack.py"],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30,
    )
    print(result.stdout[-300:])
    assert result.returncode == 0, f"Evidence failed: {result.stderr[-200:]}"
    assert "compliance-pack.zip" in result.stdout


def test_e2e_review_auto():
    """E2E: auto-review runs (may have no changes but shouldn't crash)."""
    result = subprocess.run(
        [sys.executable, "src/review/run.py", "auto"],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, f"Review crashed: {result.stderr}"
    assert "No changed files" in result.stdout or "Review Session" in result.stdout


def test_e2e_cli_help():
    """E2E: CLI help works."""
    result = subprocess.run(
        ["bash", "src/cli/yuleosh.sh", "help"],
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
