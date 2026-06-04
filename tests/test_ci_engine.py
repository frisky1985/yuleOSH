"""Tests for CI engine."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ci.run import CIResult, find_test_files, run_layer1

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
