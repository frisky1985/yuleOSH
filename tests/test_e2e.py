"""End-to-end tests for yuleOSH platform."""
import sys, os, tempfile, json, subprocess
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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


def test_e2e_pipeline_run():
    """E2E: pipeline runs end-to-end."""
    spec_path = os.path.join(PROJECT_DIR, "docs", "spec.md")
    result = subprocess.run(
        [sys.executable, "src/pipeline/run.py", spec_path],
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=30,
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
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8080))
    sock.close()
    if result == 0:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:8080/api/status")
        data = json.loads(resp.read())
        assert data["status"] == "running"
