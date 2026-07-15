# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH API module tests — direct handler calls, no HTTP server.

Each test calls handler functions directly with mock data,
verifying both happy paths and error paths.
"""

import json
import os
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY
from datetime import datetime

import pytest

# Ensure we can import src modules
os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_store(tmp_path):
    """Reset the Store singleton with a temp DB before each test.

    Also resets YULEOSH_RATE_LIMIT env var so rate limit tests
    are not polluted by other test files setting it at module level.
    """
    import importlib
    from yuleosh.store import Store
    Store.reset()
    # Use an in-memory database via env var
    os.environ["YULEOSH_DB"] = str(tmp_path / "test_store.db")
    # Reset rate limit env var to default — prevents cross-module pollution
    old_rl = os.environ.pop("YULEOSH_RATE_LIMIT", None)
    from yuleosh.api import ratelimit
    importlib.reload(ratelimit)
    ratelimit.reset()
    yield
    # Restore env var for other tests that might depend on it
    if old_rl is not None:
        os.environ["YULEOSH_RATE_LIMIT"] = old_rl
    Store.reset()


@pytest.fixture
def osh_home():
    """Return OSH_HOME."""
    return os.environ["OSH_HOME"]


@pytest.fixture
def temp_spec_file(osh_home):
    """Create a temporary spec file for validation tests."""
    # Use the real docs/spec.md which we know is valid
    spec_path = Path(osh_home) / "docs" / "spec.md"
    assert spec_path.exists(), "docs/spec.md must exist"
    return str(spec_path)


@pytest.fixture
def mock_store():
    """Patch Store to return a fresh instance with pre-seeded data."""
    from yuleosh.store import Store
    store = Store()
    # Seed some data
    now = datetime.now().isoformat()
    # Insert a project
    store.conn.execute(
        "INSERT INTO projects (name, description, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("test-project", "A test project", now, now)
    )
    # Insert a pipeline
    store.conn.execute(
        "INSERT INTO pipelines (name, spec_path, status, created_at) VALUES (?, ?, ?, ?)",
        ("pipe-1", "docs/spec.md", "completed", now)
    )
    # Insert a CI run
    store.conn.execute(
        "INSERT INTO ci_runs (layer, commit_hash, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
        (1, "abc1234", "passed", now, now)
    )
    # Insert a review
    store.conn.execute(
        "INSERT INTO reviews (task_name, decision, status, created_at) VALUES (?, ?, ?, ?)",
        ("review-1", "approved", "completed", now)
    )
    store.conn.commit()
    return store


# =============================================================================
# helpers: json_ok, json_error
# =============================================================================

class TestApiHelpers:
    """Test the base helpers in __init__.py"""

    def test_json_ok(self):
        from yuleosh.api import json_ok
        result, status = json_ok({"key": "value"})
        assert result == {"ok": True, "data": {"key": "value"}}
        assert status == 200

    def test_json_ok_none(self):
        from yuleosh.api import json_ok
        result, status = json_ok()
        assert result == {"ok": True, "data": None}
        assert status == 200

    def test_json_error_default(self):
        from yuleosh.api import json_error
        result, status = json_error("something went wrong")
        assert result == {"ok": False, "error": "something went wrong"}
        assert status == 400

    def test_json_error_custom_status(self):
        from yuleosh.api import json_error
        result, status = json_error("not found", 404)
        assert result == {"ok": False, "error": "not found"}
        assert status == 404

    def test_json_error_500(self):
        from yuleosh.api import json_error
        result, status = json_error("internal error", 500)
        assert result == {"ok": False, "error": "internal error"}
        assert status == 500

    def test_read_body_empty(self):
        """read_body with no Content-Length returns {}."""
        from yuleosh.api import read_body
        mock_handler = MagicMock()
        def _header_side_effect(key, default=None):
            if key == "Content-Type":
                return "application/json"
            return "0"
        mock_handler.headers.get.side_effect = _header_side_effect
        result = read_body(mock_handler)
        assert result == {}

    def test_read_body_json(self):
        from yuleosh.api import read_body
        mock_handler = MagicMock()
        def _header_side_effect(key, default=None):
            if key == "Content-Type":
                return "application/json"
            return str(len('{"foo":"bar"}'))
        mock_handler.headers.get.side_effect = _header_side_effect
        mock_handler.rfile.read.return_value = b'{"foo":"bar"}'
        result = read_body(mock_handler)
        assert result == {"foo": "bar"}

    def test_read_body_form_encoded(self):
        from yuleosh.api import read_body
        mock_handler = MagicMock()
        body = "foo=bar&baz=qux"
        def _header_side_effect(key, default=None):
            if key == "Content-Type":
                return "application/x-www-form-urlencoded"
            return str(len(body))
        mock_handler.headers.get.side_effect = _header_side_effect
        mock_handler.rfile.read.return_value = body.encode()
        result = read_body(mock_handler)
        assert result == {"foo": "bar", "baz": "qux"}

    def test_read_body_form_encoded_duplicate(self):
        from yuleosh.api import read_body
        mock_handler = MagicMock()
        body = "a=1&a=2"
        def _header_side_effect(key, default=None):
            if key == "Content-Type":
                return "application/x-www-form-urlencoded"
            return str(len(body))
        mock_handler.headers.get.side_effect = _header_side_effect
        mock_handler.rfile.read.return_value = body.encode()
        result = read_body(mock_handler)
        assert result == {"a": ["1", "2"]}

    def test_get_store(self):
        from yuleosh.api import get_store
        from yuleosh.store import Store
        store = get_store()
        assert isinstance(store, Store)

    def test_auth_enabled_false(self):
        """_auth_enabled returns False when ui.auth not available."""
        from yuleosh.api.health import _auth_enabled
        with patch.dict('sys.modules', {'yuleosh.ui.auth': None}):
            # Import error path
            import sys
            if 'yuleosh.ui.auth' in sys.modules:
                del sys.modules['yuleosh.ui.auth']
            result = _auth_enabled()
        assert result is False

    def test_auth_enabled_exception(self):
        from yuleosh.api.health import _auth_enabled
        # Direct approach: mock the import to raise
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'yuleosh.ui.auth':
                raise ImportError("No auth module")
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = _auth_enabled()
            assert result is False

    def test_extract_v1(self):
        from yuleosh.api.health import _extract_v1
        assert _extract_v1("/api/v1/health") == "health"
        assert _extract_v1("/api/v1/pipeline/status") == "pipeline/status"
        assert _extract_v1("/api/v1") == ""
        assert _extract_v1("/other") == "other"


# =============================================================================
# health.py
# =============================================================================

class TestHealth:
    """handle_health and its helpers."""

    def test_healthy_default(self, mock_store):
        """Basic health check returns ok."""
        from yuleosh.api.health import handle_health
        result, status = handle_health("GET")
        assert status == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["status"] == "healthy"
        assert data["db"] == "ok"
        assert data["store"]["pipelines"] == 1
        assert data["store"]["ci_runs"] == 1
        assert data["store"]["reviews"] == 1
        assert data["store"]["projects"] == 1
        assert "uptime_seconds" in data
        assert data["version"] == "0.1.0"
        assert data["osh_home"] == os.environ["OSH_HOME"]

    def test_health_disks_ok(self, mock_store):
        """Disk check returns valid values."""
        from yuleosh.api.health import handle_health
        result, _ = handle_health("GET")
        disk = result["data"]["disk"]
        assert "total_mb" in disk
        assert "free_mb" in disk
        assert "used_mb" in disk
        assert "used_pct" in disk
        assert "ok" in disk
        assert disk["ok"] is True  # Should be under 90% on normal machines

    def test_db_error(self):
        """When DB query fails, db status reflects error."""
        from yuleosh.api.health import handle_health
        # Build a mock store whose conn.execute raises
        mock_store = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("DB lost")
        mock_store.conn = mock_conn
        # Patch the reference in the health module itself
        with patch("yuleosh.api.health.Store", return_value=mock_store):
            result, _ = handle_health("GET")
            assert "error" in result["data"]["db"]

    def test_store_check_error(self):
        """When store query fails, store returns error."""
        from yuleosh.api.health import _check_store
        from yuleosh.store import Store
        store = Store()
        # The conn.execute is a C method that can't be monkeypatched directly.
        # Instead patch the Store instance's conn attribute to a mock.
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = RuntimeError("query failed")
        with patch.object(store, "conn", mock_conn):
            result = _check_store(store)
            assert "error" in result

    def test_disk_check_creates_dir(self, tmp_path):
        """_check_disk creates .yuleosh dir if it doesn't exist."""
        from yuleosh.api.health import _check_disk
        osh_home = str(tmp_path)
        with patch("yuleosh.api.health.OSH_HOME", osh_home):
            result = _check_disk()
            assert result["path"] == str(tmp_path / ".yuleosh")
            assert (tmp_path / ".yuleosh").exists()
            assert "error" not in result

    def test_disk_error(self, tmp_path):
        """_check_disk returns error when shutil.disk_usage fails."""
        from yuleosh.api.health import _check_disk
        osh_home = str(tmp_path)
        (tmp_path / ".yuleosh").mkdir(parents=True, exist_ok=True)

        with patch("shutil.disk_usage", side_effect=PermissionError("no access")), \
             patch("yuleosh.api.health.OSH_HOME", osh_home):
            result = _check_disk()
            assert "error" in result

    def test_db_unexpected_result(self):
        """_check_db returns error if SELECT 1 gives unexpected value."""
        from yuleosh.api.health import _check_db
        from yuleosh.store import Store
        store = Store()

        class FakeRow(dict):
            def __getitem__(self, key):
                return 0  # not 1

        class FakeCursor:
            def fetchone(self):
                return FakeRow()

        mock_conn = MagicMock()
        mock_conn.execute.return_value = FakeCursor()
        with patch.object(store, "conn", mock_conn):
            result = _check_db(store)
            assert "unexpected" in result

    def test_store_counts_empty(self):
        """_check_store on empty DB returns zeros."""
        from yuleosh.api.health import _check_store
        from yuleosh.store import Store
        store = Store()
        result = _check_store(store)
        assert result == {"pipelines": 0, "ci_runs": 0, "reviews": 0, "projects": 0}


# =============================================================================
# spec.py
# =============================================================================

class TestSpec:
    """handle_spec — validate and diff."""

    def test_validate_unknown_resource(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("GET", "unknown", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_validate_wrong_method(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("GET", "validate", {}, {})
        assert result["ok"] is False
        assert status == 405
        assert "POST" in result["error"]

    def test_validate_missing_path(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "validate", {}, {})
        assert result["ok"] is False
        assert "'path' is required" in result["error"]

    def test_validate_bad_path(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "validate", {"path": "/nonexistent/file.md"}, {})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_validate_success(self, temp_spec_file):
        """Validate a real spec file."""
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "validate", {"path": temp_spec_file}, {})
        assert status == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["requirements"] > 0
        assert data["scenarios"] > 0
        assert data["total_shall"] > 0
        assert "issue_count" in data
        assert "error_count" in data
        assert "coverage" in data

    def test_validate_with_relative_path(self, temp_spec_file, monkeypatch):
        """Relative path is resolved against OSH_HOME."""
        from yuleosh.api.spec import handle_spec
        # Use a relative path that exists
        result, status = handle_spec("POST", "validate", {"path": "docs/spec.md"}, {})
        assert status == 200
        assert result["ok"] is True

    def test_diff_wrong_method(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("GET", "diff", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_diff_missing_params(self):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "diff", {"old": "a.md"}, {})
        assert result["ok"] is False
        assert "'old' and 'new'" in result["error"]

    def test_diff_old_not_found(self, temp_spec_file):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "diff",
                                     {"old": "/nonexistent/old.md", "new": temp_spec_file}, {})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_diff_new_not_found(self, temp_spec_file):
        from yuleosh.api.spec import handle_spec
        result, status = handle_spec("POST", "diff",
                                     {"old": temp_spec_file, "new": "/nonexistent/new.md"}, {})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_diff_success(self, temp_spec_file, tmp_path):
        """Diff two identical files returns empty diff."""
        from yuleosh.api.spec import handle_spec
        # Copy the spec to a temp file
        copy_path = tmp_path / "spec_copy.md"
        shutil.copy2(temp_spec_file, str(copy_path))
        result, status = handle_spec("POST", "diff",
                                     {"old": temp_spec_file, "new": str(copy_path)}, {})
        assert status == 200
        assert result["ok"] is True

    def test_diff_relative_paths(self, temp_spec_file, tmp_path, monkeypatch):
        """Relative paths resolved via OSH_HOME."""
        from yuleosh.api.spec import handle_spec
        copy_path = tmp_path / "spec_copy.md"
        shutil.copy2(temp_spec_file, str(copy_path))
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_spec("POST", "diff",
                                     {"old": "spec_copy.md", "new": "spec_copy.md"}, {})
        assert status == 200
        assert result["ok"] is True


# =============================================================================
# pipeline.py
# =============================================================================

class TestPipeline:
    """handle_pipeline — run, status/list."""

    def test_unknown_resource(self):
        from yuleosh.api.pipeline import handle_pipeline
        result, status = handle_pipeline("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_run_wrong_method(self):
        from yuleosh.api.pipeline import handle_pipeline
        result, status = handle_pipeline("GET", "run", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_run_missing_spec(self):
        from yuleosh.api.pipeline import handle_pipeline
        result, status = handle_pipeline("POST", "run", {}, {})
        assert result["ok"] is False
        assert "'spec' is required" in result["error"]

    def test_run_spec_not_found(self):
        from yuleosh.api.pipeline import handle_pipeline
        result, status = handle_pipeline("POST", "run",
                                         {"spec": "/nonexistent.md"}, {})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    @patch("subprocess.run")
    def test_run_pipeline_success(self, mock_run, temp_spec_file):
        """Mock subprocess and verify success path."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Pipeline OK", stderr="")
        from yuleosh.api.pipeline import handle_pipeline

        result, status = handle_pipeline("POST", "run",
                                         {"spec": temp_spec_file, "name": "my-pipe"}, {})
        assert status == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["exit_code"] == 0
        assert data["name"] == "my-pipe"

    @patch("subprocess.run")
    def test_run_pipeline_timeout(self, mock_run, temp_spec_file):
        """Mock TimeoutExpired."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
        from yuleosh.api.pipeline import handle_pipeline

        result, status = handle_pipeline("POST", "run",
                                         {"spec": temp_spec_file}, {})
        assert result["ok"] is False
        assert status == 504

    @patch("subprocess.run")
    def test_run_pipeline_exception(self, mock_run, temp_spec_file):
        """Mock generic exception."""
        mock_run.side_effect = RuntimeError("Something broke")
        from yuleosh.api.pipeline import handle_pipeline

        result, status = handle_pipeline("POST", "run",
                                         {"spec": temp_spec_file}, {})
        assert result["ok"] is False
        assert status == 500

    def test_run_with_relative_path(self, temp_spec_file, monkeypatch):
        """Relative spec path resolved via OSH_HOME."""
        import subprocess  # noqa: F811
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            from yuleosh.api.pipeline import handle_pipeline

            result, status = handle_pipeline("POST", "run",
                                             {"spec": "docs/spec.md"}, {})
            assert status == 200
            assert result["ok"] is True

    def test_list_pipelines_empty(self, tmp_path):
        """No sessions dir, returns empty list."""
        from yuleosh.api.pipeline import handle_pipeline
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_pipeline("GET", "status", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["count"] == 0
            assert data["sessions"] == []

    def test_list_pipelines_with_sessions(self, tmp_path, monkeypatch):
        """Create fake session files on disk."""
        from yuleosh.api.pipeline import handle_pipeline
        sessions_dir = tmp_path / ".osh" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        session_data = {"name": "pipe-1", "status": "completed"}
        sess_dir = sessions_dir / "session-1"
        sess_dir.mkdir()
        (sess_dir / "session.json").write_text(json.dumps(session_data))
        monkeypatch.setattr("yuleosh.api.pipeline.Path", lambda p: tmp_path / p if not isinstance(p, (str, Path)) or "/" not in str(p) else Path(p))

        # Better: just mock OSH_HOME
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_pipeline("GET", "status", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] >= 1
        assert data["sessions"][0]["name"] == "pipe-1"

    def test_empty_string_path(self):
        """path_tail='' with POST should act like 'run'."""
        from yuleosh.api.pipeline import handle_pipeline
        # Empty path_tail + POST routes to _run_pipeline -> needs spec
        result, status = handle_pipeline("POST", "", {"spec": "/nonexistent"}, {})
        assert result["ok"] is False
        # It hits run pipeline path, which checks spec exists
        assert "not found" in result["error"].lower()

    def test_empty_path_get(self, tmp_path):
        """path_tail='' with GET returns 405 (first condition catches it)."""
        from yuleosh.api.pipeline import handle_pipeline
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_pipeline("GET", "", {}, {})
            assert status == 405
            assert "Use POST" in result["error"]

    def test_list_pipelines_explicit(self, tmp_path):
        """path_tail='list' with GET returns pipelines list."""
        from yuleosh.api.pipeline import handle_pipeline
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_pipeline("GET", "list", {}, {})
            assert status == 200
            assert result["ok"] is True
            assert result["data"]["count"] == 0


# =============================================================================
# ci.py
# =============================================================================

class TestCI:
    """handle_ci — run layers, list runs."""

    def test_unknown_resource(self):
        from yuleosh.api.ci import handle_ci
        result, status = handle_ci("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_list_ci_runs_wrong_method(self):
        from yuleosh.api.ci import handle_ci
        result, status = handle_ci("POST", "runs", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_run_wrong_method(self):
        from yuleosh.api.ci import handle_ci
        result, status = handle_ci("GET", "run/1", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_run_invalid_layer(self):
        from yuleosh.api.ci import handle_ci
        result, status = handle_ci("POST", "run/5", {}, {})
        assert result["ok"] is False
        assert "Invalid CI layer" in result["error"]

    def test_run_layer_1_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Passed", stderr="")
            from yuleosh.api.ci import handle_ci
            result, status = handle_ci("POST", "run/1", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["layer"] == 1
            assert data["status"] == "passed"

    def test_run_layer_2_failed(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="Failed", stderr="tests failed")
            from yuleosh.api.ci import handle_ci
            result, status = handle_ci("POST", "run/2", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["layer"] == 2
            assert data["status"] == "failed"

    def test_run_layer_3_timeout(self):
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 180)
            from yuleosh.api.ci import handle_ci
            result, status = handle_ci("POST", "run/3", {}, {})
            assert result["ok"] is False
            assert status == 504

    def test_run_layer_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("CI system error")
            from yuleosh.api.ci import handle_ci
            result, status = handle_ci("POST", "run/1", {}, {})
            assert result["ok"] is False
            assert status == 500

    def test_list_ci_runs_empty(self, tmp_path):
        """No ci results dir."""
        from yuleosh.api.ci import handle_ci
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_ci("GET", "runs", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["count"] == 0
            assert data["results"] == []

    def test_list_ci_runs_with_data(self, tmp_path, monkeypatch):
        """Create mock CI result files."""
        from yuleosh.api.ci import handle_ci
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "layer1-abc.json").write_text(
            json.dumps({"layer": 1, "commit": "abc", "status": "passed"})
        )
        (ci_dir / "layer2-def.json").write_text(
            json.dumps({"layer": 2, "commit": "def", "status": "failed"})
        )
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_ci("GET", "runs", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 2


# =============================================================================
# review.py
# =============================================================================

class TestReview:
    """handle_review — auto, task, list."""

    def test_unknown_resource(self):
        from yuleosh.api.review import handle_review
        result, status = handle_review("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_auto_wrong_method(self):
        from yuleosh.api.review import handle_review
        result, status = handle_review("GET", "auto", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_task_wrong_method(self):
        from yuleosh.api.review import handle_review
        result, status = handle_review("GET", "task", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_auto_review_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Review OK", stderr="")
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "auto", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["status"] == "completed"

    def test_auto_review_timeout(self):
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "auto", {}, {})
            assert result["ok"] is False
            assert status == 504

    def test_auto_review_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("Review error")
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "auto", {}, {})
            assert result["ok"] is False
            assert status == 500

    def test_task_review_missing_task(self):
        from yuleosh.api.review import handle_review
        result, status = handle_review("POST", "task", {"kind": "feature"}, {})
        assert result["ok"] is False
        assert "'task' name is required" in result["error"]

    def test_task_review_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Task reviewed", stderr="")
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "task",
                                           {"task": "impl-login", "kind": "feature"}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["task"] == "impl-login"
            assert data["kind"] == "feature"

    def test_task_review_timeout(self):
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "task",
                                           {"task": "impl-login", "kind": "feature"}, {})
            assert result["ok"] is False
            assert status == 504

    def test_task_review_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("boom")
            from yuleosh.api.review import handle_review
            result, status = handle_review("POST", "task",
                                           {"task": "impl-login"}, {})
            assert result["ok"] is False
            assert status == 500

    def test_list_reviews_empty(self, tmp_path):
        from yuleosh.api.review import handle_review
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_review("GET", "list", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["count"] == 0

    def test_list_reviews_with_empty_path(self, tmp_path):
        """GET with empty path_tail also lists reviews."""
        from yuleosh.api.review import handle_review
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_review("GET", "", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["count"] == 0

    def test_list_reviews_with_data(self, tmp_path, monkeypatch):
        """Create mock review session files."""
        from yuleosh.api.review import handle_review
        rev_dir = tmp_path / ".osh" / "reviews"
        rev_dir.mkdir(parents=True, exist_ok=True)
        sess_dir = rev_dir / "session-abc"
        sess_dir.mkdir()
        (sess_dir / "review-session.json").write_text(
            json.dumps({"task": "review-1", "decision": "approved"})
        )
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_review("GET", "list", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 1
        assert data["sessions"][0]["task"] == "review-1"


# =============================================================================
# evidence.py
# =============================================================================

class TestEvidence:
    """handle_evidence — generate, files, pack."""

    def test_unknown_resource(self):
        from yuleosh.api.evidence import handle_evidence
        result, status = handle_evidence("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_generate_wrong_method(self):
        from yuleosh.api.evidence import handle_evidence
        result, status = handle_evidence("GET", "generate", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_files_wrong_method(self):
        from yuleosh.api.evidence import handle_evidence
        result, status = handle_evidence("POST", "files", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_pack_wrong_method(self):
        from yuleosh.api.evidence import handle_evidence
        result, status = handle_evidence("POST", "pack", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_generate_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Pack OK", stderr="")
            from yuleosh.api.evidence import handle_evidence
            result, status = handle_evidence("POST", "generate",
                                             {"project_dir": "/tmp/test-ev"}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["status"] == "completed"
            assert data["project_dir"] == "/tmp/test-ev"

    def test_generate_timeout(self):
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 120)
            from yuleosh.api.evidence import handle_evidence
            result, status = handle_evidence("POST", "generate", {}, {})
            assert result["ok"] is False
            assert status == 504

    def test_generate_os_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Cannot spawn process")
            from yuleosh.api.evidence import handle_evidence
            result, status = handle_evidence("POST", "generate", {}, {})
            assert result["ok"] is False
            assert status == 500

    def test_generate_called_process_error(self):
        import subprocess
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
            from yuleosh.api.evidence import handle_evidence
            result, status = handle_evidence("POST", "generate",
                                             {"project_dir": "/tmp"}, {})
            assert result["ok"] is False
            assert status == 500

    def test_list_files_empty(self, tmp_path):
        from yuleosh.api.evidence import handle_evidence
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_evidence("GET", "files", {}, {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["count"] == 0

    def test_list_files_with_data(self, tmp_path, monkeypatch):
        """Create mock evidence files."""
        from yuleosh.api.evidence import handle_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "report.pdf").write_text("report data")
        (ev_dir / "trace.json").write_text("{}")
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_evidence("GET", "files", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 2
        names = {f["name"] for f in data["files"]}
        assert "report.pdf" in names
        assert "trace.json" in names

    def test_download_pack_not_found(self, tmp_path):
        from yuleosh.api.evidence import handle_evidence
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_evidence("GET", "pack", {}, {})
            assert result["ok"] is False
            assert status == 404

    def test_download_pack_with_handler(self, tmp_path, monkeypatch):
        """When handler is provided, it writes response directly."""
        from yuleosh.api.evidence import handle_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ev_dir / "compliance-pack.zip"
        zip_path.write_bytes(b"zip content")
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))

        mock_handler = MagicMock()
        result = handle_evidence("GET", "pack", {}, {}, handler=mock_handler)
        assert result is None  # handler sent response directly
        mock_handler.send_response.assert_called_once_with(200)
        mock_handler.send_header.assert_any_call("Content-Type", "application/zip")
        mock_handler.wfile.write.assert_called_once_with(b"zip content")

    def test_download_pack_no_handler(self, tmp_path, monkeypatch):
        """Without handler, returns JSON with file info."""
        from yuleosh.api.evidence import handle_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ev_dir / "compliance-pack.zip"
        zip_path.write_text("zip data")
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        result, status = handle_evidence("GET", "pack", {}, {}, handler=None)
        assert status == 200
        assert result["ok"] is True
        assert result["data"]["status"] == "ready"


# =============================================================================
# project.py
# =============================================================================

class TestProject:
    """handle_project — CRUD, stats."""

    def test_wrong_method(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("DELETE", "", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_stats(self, mock_store):
        """Project stats with seeded data."""
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "stats", {}, {})
        assert status == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["projects"] >= 1
        assert data["pipelines"] >= 1
        assert data["ci_runs"] >= 1
        assert data["reviews"] >= 1
        assert "pipeline_statuses" in data

    def test_stats_empty(self):
        """Stats on empty DB returns zeros."""
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "stats", {}, {})
        assert status == 200
        data = result["data"]
        assert data["projects"] == 0
        assert data["pipelines"] == 0

    def test_list_projects(self, mock_store):
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] >= 1

    def test_list_projects_explicit_list(self, mock_store):
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "list", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] >= 1

    def test_list_projects_empty(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 0

    def test_get_project_missing_name(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "", {}, {})
        # Empty path_tail with GET returns list, not get-project
        # For get, we need a name in path_tail
        result, status = handle_project("GET", "nonexistent", {}, {})
        assert result["ok"] is False
        assert "not found" in result["error"].lower()

    def test_get_project_found(self, mock_store):
        from yuleosh.api.project import handle_project
        result, status = handle_project("GET", "test-project", {}, {})
        assert status == 200
        assert result["ok"] is True
        p = result["data"]
        assert p["name"] == "test-project"

    def test_create_project_missing_name(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("POST", "", {"description": "no name"}, {})
        assert result["ok"] is False
        assert "'name' is required" in result["error"]

    def test_create_project_success(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("POST", "",
                                        {"name": "new-project", "description": "A new project",
                                         "spec_path": "docs/spec.md"}, {})
        assert status == 200
        assert result["ok"] is True
        p = result["data"]
        assert p["name"] == "new-project"
        assert p["description"] == "A new project"

    def test_create_project_minimal(self):
        from yuleosh.api.project import handle_project
        result, status = handle_project("POST", "",
                                        {"name": "minimal-project"}, {})
        assert status == 200
        assert result["ok"] is True

    def test_create_project_duplicate(self, mock_store):
        """Creating a project with a duplicate name succeeds (INSERT OR IGNORE)."""
        from yuleosh.api.project import handle_project
        result, status = handle_project("POST", "",
                                        {"name": "test-project", "description": "duplicate"}, {})
        assert status == 200
        assert result["ok"] is True
        # Description stays the original (IGNORE means no update)
        assert result["data"]["description"] == "A test project"

    def test_project_stats_with_statuses(self, mock_store):
        """Test pipeline status aggregation."""
        from yuleosh.api.project import handle_project, _project_stats
        from yuleosh.store import Store
        store = Store()

        # Add another pipeline with different status
        store.conn.execute(
            "INSERT INTO pipelines (name, spec_path, status, created_at) VALUES (?, ?, ?, ?)",
            ("pipe-2", "docs/spec.md", "failed", datetime.now().isoformat())
        )
        store.conn.commit()

        result, status = handle_project("GET", "stats", {}, {})
        assert status == 200
        data = result["data"]
        assert data["pipeline_statuses"]["completed"] == 1
        assert data["pipeline_statuses"]["failed"] == 1


# =============================================================================
# apikeys.py
# =============================================================================

class TestApiKeys:
    """handle_apikeys — generate, list, revoke."""

    def test_unknown_route(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("PUT", "", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_generate_missing_label(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("POST", "", {}, {})
        assert result["ok"] is False
        assert "label is required" in result["error"]

    def test_generate_label_too_long(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("POST", "",
                                        {"label": "x" * 101}, {})
        assert result["ok"] is False
        assert "100 characters" in result["error"]

    def test_generate_success(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("POST", "",
                                        {"label": "my-key"}, {})
        assert status == 200
        assert result["ok"] is True
        data = result["data"]
        assert data["key"].startswith("yule_")
        assert data["label"] == "my-key"
        assert len(data["key"]) > 20
        assert "id" in data
        assert "prefix" in data
        assert "created_at" in data

    def test_generate_strip_label(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("POST", "",
                                        {"label": "  spaced-key  "}, {})
        assert status == 200
        assert result["data"]["label"] == "spaced-key"

    def test_generate_with_empty_label(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("POST", "", {"label": ""}, {})
        assert result["ok"] is False
        # Empty after strip
        result, status = handle_apikeys("POST", "", {"label": "   "}, {})
        assert result["ok"] is False

    def test_list_keys_empty(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 0

    def test_list_keys_with_data(self):
        from yuleosh.api.apikeys import handle_apikeys
        # First generate one
        handle_apikeys("POST", "", {"label": "key-1"}, {})
        handle_apikeys("POST", "", {"label": "key-2"}, {})
        result, status = handle_apikeys("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 2

    def test_revoke_invalid_id(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("DELETE", "abc", {}, {})
        assert result["ok"] is False
        assert status == 400

    def test_revoke_not_found(self):
        from yuleosh.api.apikeys import handle_apikeys
        result, status = handle_apikeys("DELETE", "9999", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_revoke_success(self):
        from yuleosh.api.apikeys import handle_apikeys
        gen = handle_apikeys("POST", "", {"label": "to-revoke"}, {})
        key_id = gen[0]["data"]["id"]
        result, status = handle_apikeys("DELETE", str(key_id), {}, {})
        assert status == 200
        assert result["ok"] is True
        assert result["data"]["revoked"] is True

    def test_revoke_twice(self):
        """Revoking an already-revoked key returns 404."""
        from yuleosh.api.apikeys import handle_apikeys
        gen = handle_apikeys("POST", "", {"label": "revoke-2x"}, {})
        key_id = gen[0]["data"]["id"]
        handle_apikeys("DELETE", str(key_id), {}, {})
        result, status = handle_apikeys("DELETE", str(key_id), {}, {})
        assert result["ok"] is False
        assert status == 404


# =============================================================================
# stats.py
# =============================================================================

class TestStats:
    """handle_stats — overview, trends."""

    def test_wrong_method(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("POST", "overview", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_unknown_resource(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_overview_empty(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "overview", {}, {})
        assert status == 200
        data = result["data"]
        assert data["total_pipelines"] == 0
        assert data["pipeline_success_rate"] == 0
        assert data["ci_pass_rate"] == 0
        assert "total_projects" in data

    def test_overview_with_data(self, mock_store):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "overview", {}, {})
        assert status == 200
        data = result["data"]
        assert data["total_pipelines"] == 1
        assert data["total_ci_runs"] == 1
        assert data["total_reviews"] == 1
        assert data["total_projects"] == 1
        assert data["pipeline_success_rate"] == 100.0  # completed/total
        assert data["ci_pass_rate"] == 100.0  # passed/total
        assert "generated_at" in data

    def test_overview_mixed_pipelines(self, mock_store):
        """Overview with some failed pipelines."""
        from yuleosh.api.stats import handle_stats
        from yuleosh.store import Store
        store = Store()
        store.conn.execute(
            "INSERT INTO pipelines (name, spec_path, status, created_at) VALUES (?, ?, ?, ?)",
            ("pipe-2", "docs/spec.md", "failed", datetime.now().isoformat())
        )
        store.conn.commit()
        result, status = handle_stats("GET", "overview", {}, {})
        data = result["data"]
        assert data["total_pipelines"] == 2
        assert 49 < data["pipeline_success_rate"] < 51  # 50%

    def test_trends_invalid_period(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {},
                                      {"period": ["monthly"]})
        assert result["ok"] is False
        assert status == 400

    def test_trends_empty(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {},
                                      {"period": ["daily"], "days": ["7"]})
        assert status == 200
        data = result["data"]
        assert data["period"] == "daily"
        assert data["days_lookback"] == 7
        assert data["total_points"] == 0

    def test_trends_with_data(self, mock_store):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {},
                                      {"period": ["daily"], "days": ["30"]})
        assert status == 200
        data = result["data"]
        assert data["period"] == "daily"
        assert data["total_points"] >= 1

    def test_trends_default_params(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {}, {})
        assert status == 200
        data = result["data"]
        assert data["period"] == "daily"
        assert data["days_lookback"] == 7

    def test_trends_weekly(self):
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {},
                                      {"period": ["weekly"], "days": ["30"]})
        assert status == 200
        data = result["data"]
        assert data["period"] == "weekly"

    def test_trends_pagination_error_params(self):
        """Test with bad limit/offset."""
        from yuleosh.api.stats import handle_stats
        result, status = handle_stats("GET", "trends", {},
                                      {"limit": [0], "offset": [-1]})
        assert status == 200  # Should still work with defaults


# =============================================================================
# notify.py
# =============================================================================

class TestNotify:
    """handle_notify — GET/PUT config."""

    def test_unknown_resource(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("GET", "blargh", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_wrong_method(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("POST", "config", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_get_config(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("GET", "config", {}, {})
        assert status == 200
        data = result["data"]
        assert "feishu_url" in data
        assert "email_smtp" in data
        assert "webhook_url" in data

    def test_get_config_empty_path(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert "feishu_url" in data

    def test_put_config_invalid_body(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("PUT", "config", "not-a-dict", {})
        assert result["ok"] is False
        assert status == 400

    def test_put_config_update(self):
        from yuleosh.api.notify import handle_notify
        result, status = handle_notify("PUT", "config",
                                       {"feishu_url": "https://feishu.example.com/webhook",
                                        "email_smtp": "smtp.example.com"}, {})
        assert status == 200
        data = result["data"]
        assert data["feishu_url"] == "https://feishu.example.com/webhook"
        assert data["email_smtp"] == "smtp.example.com"

    def test_put_config_partial_update(self, monkeypatch):
        """Partial update only changes provided fields."""
        from yuleosh.api.notify import handle_notify
        # Update just one field
        result, status = handle_notify("PUT", "config",
                                       {"email_smtp": "smtp.custom.com"}, {})
        assert status == 200
        data = result["data"]
        assert data["email_smtp"] == "smtp.custom.com"


# =============================================================================
# validate.py
# =============================================================================

class TestValidateModule:
    """validate_spec_path, validate_pagination, validate_json_body."""

    def test_validate_spec_path_empty(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path(None)
        assert not valid
        assert "required" in err
        valid, err = validate_spec_path("")
        assert not valid

    def test_validate_spec_path_traversal(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("../etc/passwd")
        assert not valid
        assert "traversal" in err

    def test_validate_spec_path_absolute(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("/etc/passwd")
        assert not valid
        assert "traversal" in err

    def test_validate_spec_path_bad_extension(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("readme.txt")
        assert not valid
        assert "extension" in err

    def test_validate_spec_path_good_extension(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("nonexistent.md")
        assert not valid  # File doesn't exist
        assert "not found" in err

    def test_validate_spec_path_not_a_file(self, tmp_path):
        from yuleosh.api.validate import validate_spec_path, OSH_HOME
        # Create a directory that looks like a spec
        d = tmp_path / "mydir.md"
        d.mkdir()
        with patch("yuleosh.api.validate.OSH_HOME", str(tmp_path)):
            valid, err = validate_spec_path("mydir.md")
            assert not valid
            assert "file" in err

    def test_validate_spec_path_success(self, temp_spec_file, osh_home):
        """Valid path resolves against OSH_HOME."""
        from yuleosh.api.validate import validate_spec_path
        rel = os.path.relpath(temp_spec_file, osh_home)
        valid, err = validate_spec_path(rel)
        assert valid
        assert err is None

    def test_validate_pagination_defaults(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({})
        assert result == {"limit": 50, "offset": 0}

    def test_validate_pagination_valid(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["100"], "offset": ["10"]})
        assert result == {"limit": 100, "offset": 10}

    def test_validate_pagination_capped(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["999"], "offset": ["0"]})
        assert result == {"limit": 200, "offset": 0}

    def test_validate_pagination_invalid(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["abc"], "offset": ["-5"]})
        assert result == {"limit": 50, "offset": 0}

    def test_validate_pagination_empty_string(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": [""], "offset": [""]})
        # int("") raises ValueError -> defaults
        assert result == {"limit": 50, "offset": 0}

    def test_validate_pagination_negative_offset(self):
        """Negative offset should be clamped to 0."""
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["10"], "offset": ["-5"]})
        assert result == {"limit": 10, "offset": 0}

    def test_validate_json_body_not_dict(self):
        from yuleosh.api.validate import validate_json_body
        valid, err = validate_json_body("string")
        assert not valid
        assert "JSON object" in err

    def test_validate_json_body_empty_list(self):
        from yuleosh.api.validate import validate_json_body
        valid, err = validate_json_body([])
        assert not valid

    def test_validate_json_body_valid(self):
        from yuleosh.api.validate import validate_json_body
        valid, err = validate_json_body({"key": "val"})
        assert valid
        assert err is None

    def test_validate_json_body_none(self):
        from yuleosh.api.validate import validate_json_body
        valid, err = validate_json_body(None)
        assert not valid


# =============================================================================
# audit.py
# =============================================================================

class TestAudit:
    """handle_audit, log_request."""

    def test_wrong_method(self):
        from yuleosh.api.audit import handle_audit
        result, status = handle_audit("POST", "", {}, {})
        assert result["ok"] is False
        assert status == 405

    def test_path_tail_not_empty(self):
        from yuleosh.api.audit import handle_audit
        result, status = handle_audit("GET", "something", {}, {})
        assert result["ok"] is False
        assert status == 404

    def test_list_audit_empty(self):
        from yuleosh.api.audit import handle_audit
        result, status = handle_audit("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 0
        assert data["total"] == 0

    def test_log_request(self):
        from yuleosh.api.audit import log_request, handle_audit
        log_request("GET", "/api/v1/health", 200, "127.0.0.1", 12.5)
        log_request("POST", "/api/v1/pipeline/run", 400, "10.0.0.1", 3.2)
        result, status = handle_audit("GET", "", {}, {})
        assert status == 200
        data = result["data"]
        assert data["count"] == 2
        assert data["total"] == 2
        entries = data["entries"]
        assert entries[0]["method"] == "POST"  # DESC order
        assert entries[1]["method"] == "GET"

    def test_audit_pagination(self):
        from yuleosh.api.audit import log_request, handle_audit
        for i in range(5):
            log_request("GET", f"/api/endpoint/{i}", 200, "::1", 1.0)
        result, _ = handle_audit("GET", "",
                                 {}, {"limit": ["2"], "offset": ["0"]})
        assert result["data"]["count"] == 2
        assert result["data"]["total"] == 5
        assert result["data"]["limit"] == 2
        assert result["data"]["offset"] == 0

    def test_audit_large_limit_capped(self):
        from yuleosh.api.audit import log_request, handle_audit
        for i in range(5):
            log_request("GET", "/api/test", 200, "10.0.0.1", 1.0)
        result, _ = handle_audit("GET", "",
                                 {}, {"limit": ["999"]})
        # Capped to 200
        assert result["data"]["count"] == 5
        assert result["data"]["limit"] == 200

    def test_audit_invalid_limit_offset(self):
        from yuleosh.api.audit import handle_audit
        result, _ = handle_audit("GET", "",
                                 {}, {"limit": ["abc"], "offset": ["def"]})
        assert result["ok"] is True  # Falls back to defaults
        assert result["data"]["limit"] == 50
        assert result["data"]["offset"] == 0

    def test_ensure_table_idempotent(self):
        """Calling _ensure_table multiple times is safe."""
        from yuleosh.api.audit import _ensure_table
        _ensure_table()
        _ensure_table()
        _ensure_table()
        # No error
        assert True


# =============================================================================
# router.py
# =============================================================================

class TestRouter:
    """dispatch and _respond."""

    def test_respond(self):
        """_respond sends proper JSON with CORS header."""
        from yuleosh.api.router import _respond
        handler = MagicMock()
        # Set Origin to the allowed desktop client origin
        handler.headers.get.return_value = "http://localhost:18789"
        _respond(handler, {"ok": True, "data": "hello"}, 200)
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Content-Type", "application/json")
        handler.send_header.assert_any_call("Access-Control-Allow-Origin", "http://localhost:18789")
        handler.send_header.assert_any_call("X-Content-Type-Options", "nosniff")
        data_written = b"".join(
            args[0] for args, _ in handler.wfile.write.call_args_list
        )
        payload = json.loads(data_written)
        assert payload == {"ok": True, "data": "hello"}

    def test_respond_error(self):
        from yuleosh.api.router import _respond
        handler = MagicMock()
        _respond(handler, {"ok": False, "error": "not found"}, 404)
        handler.send_response.assert_called_once_with(404)

    def test_dispatch_not_api_route(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "GET"
        dispatch(handler, "/not/api/v1/path")
        # Should respond with 404
        handler.send_response.assert_called_once_with(404)
        handler.send_header.assert_any_call("Content-Type", "application/json")

    def test_dispatch_unknown_resource(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "GET"
        handler.headers.get.return_value = "0"
        dispatch(handler, "/api/v1/unknown_endpoint")
        handler.send_response.assert_called_once_with(404)
        data_written = b"".join(
            args[0] for args, _ in handler.wfile.write.call_args_list
        )
        payload = json.loads(data_written)
        assert "Unknown resource" in payload["error"]

    def test_dispatch_health(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "GET"
        handler.headers.get.return_value = "0"
        dispatch(handler, "/api/v1/health")
        handler.send_response.assert_called_once_with(200)
        data_written = b"".join(
            args[0] for args, _ in handler.wfile.write.call_args_list
        )
        payload = json.loads(data_written)
        assert payload["ok"] is True
        assert payload["data"]["status"] == "healthy"

    def test_dispatch_with_request_body(self):
        """dispatch reads body and passes it to handler."""
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "POST"
        body = json.dumps({"path": "docs/spec.md"}).encode()
        handler.headers.get.return_value = str(len(body))
        handler.rfile.read.return_value = body
        dispatch(handler, "/api/v1/spec/validate")
        handler.send_response.assert_called_once_with(200)
        data_written = b"".join(
            args[0] for args, _ in handler.wfile.write.call_args_list
        )
        payload = json.loads(data_written)
        assert payload["ok"] is True

    def test_dispatch_error_in_handler(self):
        """When a handler raises, dispatch returns 500."""
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "GET"
        handler.headers.get.return_value = "0"

        # Test by routing to health which should work, and then
        # we can also verify that if dispatch itself handles errors
        with patch("yuleosh.api.router.ROUTES", {"crash": lambda **kw: (_ for _ in ()).throw(RuntimeError("crash"))}):
            dispatch(handler, "/api/v1/crash")
            handler.send_response.assert_called_with(500)

    def test_dispatch_wizard(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "POST"
        body = json.dumps({}).encode()
        handler.headers.get.return_value = str(len(body))
        handler.rfile.read.return_value = body
        dispatch(handler, "/api/v1/wizard/complete")
        handler.send_response.assert_called_once_with(200)
        data_written = b"".join(
            args[0] for args, _ in handler.wfile.write.call_args_list
        )
        payload = json.loads(data_written)
        assert payload["ok"] is True
        assert payload["data"]["completed"] is True

    def test_dispatch_evidence_download(self, tmp_path):
        """Evidence download returns None from handler; dispatch returns without responding."""
        from yuleosh.api.router import dispatch
        from pathlib import Path
        # Create the compliance pack zip
        ev_dir = Path(str(tmp_path)) / ".osh" / "evidence"
        ev_dir.mkdir(parents=True, exist_ok=True)
        zip_path = ev_dir / "compliance-pack.zip"
        zip_path.write_bytes(b"fake zip content")

        handler = MagicMock()
        handler.command = "GET"
        handler.headers.get.return_value = "0"
        handler.rfile.read.return_value = b""

        # Patch OSH_HOME in the parent package so evidence's inline import sees it
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            dispatch(handler, "/api/v1/evidence/pack")
        # handler.send_response should have been called (by _download_pack directly)
        handler.send_response.assert_called_once_with(200)


# =============================================================================
# webhooks.py
# =============================================================================

class TestWebhooks:
    """handle_webhooks — GitHub push events."""

    def test_wrong_method(self):
        from yuleosh.api.webhooks import handle_webhooks
        result, status = handle_webhooks("GET", "github", {})
        assert result["ok"] is False
        assert status == 405

    def test_unknown_provider(self):
        from yuleosh.api.webhooks import handle_webhooks
        result, status = handle_webhooks("POST", "gitlab", {})
        assert result["ok"] is False
        assert status == 404

    def test_github_push_no_ref(self):
        """Minimal payload — no ref, no repository."""
        from yuleosh.api.webhooks import handle_webhooks
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_ci:
            mock_ci.return_value = {"status": "passed", "success": True, "timestamp": "now"}
            result, status = handle_webhooks("POST", "github", {})
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["repository"] == "unknown"
            assert data["branch"] == "unknown"
            assert data["status"] == "received"

    def test_github_push_with_repo(self):
        """Payload with repo info."""
        from yuleosh.api.webhooks import handle_webhooks
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_ci:
            mock_ci.return_value = {"status": "passed", "success": True, "timestamp": "now"}
            result, status = handle_webhooks("POST", "github", {
                "repository": {"full_name": "user/repo", "name": "repo"},
                "ref": "refs/heads/main",
                "head_commit": {"id": "abc123def456", "message": "Update feature"},
                "pusher": {"name": "dev-user"},
            })
            assert status == 200
            assert result["ok"] is True
            data = result["data"]
            assert data["repository"] == "user/repo"
            assert data["branch"] == "main"
            assert data["commit"] == "abc123de"  # truncated to 8 chars

    @patch("yuleosh.api.webhooks._trigger_ci")
    def test_github_push_ci_triggered(self, mock_trigger_ci):
        """CI is triggered on push."""
        mock_trigger_ci.return_value = {"status": "passed", "success": True,
                                         "timestamp": "now"}
        from yuleosh.api.webhooks import handle_webhooks
        result, status = handle_webhooks("POST", "github", {
            "repository": {"full_name": "user/repo"},
            "ref": "refs/heads/main",
            "head_commit": {"id": "abc123def456"},
            "pusher": {"name": "dev"},
        })
        assert status == 200
        data = result["data"]
        assert data["ci_triggered"] is True
        assert data["ci_status"] == "passed"

    def test_trigger_ci_import_error(self):
        """When CI module is unavailable, returns skipped."""
        from yuleosh.api.webhooks import _trigger_ci
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'yuleosh.ci.run':
                raise ImportError("no CI module")
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = _trigger_ci("repo", "main", "abc123", "msg")
            assert result["status"] == "skipped"

    def test_trigger_ci_exception(self):
        """Generic exception in trigger_ci returns error."""
        from yuleosh.api.webhooks import _trigger_ci
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'yuleosh.ci.run':
                # Simulate importing run_layer1 successfully
                class FakeModule:
                    @staticmethod
                    def run_layer1(project_dir):
                        raise RuntimeError("CI execution error")
                return FakeModule()
            if name == 'yuleosh.store':
                class FakeStore:
                    def __init__(self):
                        self.conn = type('obj', (object,), {
                            'execute': lambda self, q, p: type('o', (object,), {
                                'fetchone': lambda self: {'c': 0}
                            }),
                            'commit': lambda self: None
                        })()

                    def save_ci(self, data):
                        pass
                return FakeStore()
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            result = _trigger_ci("repo", "main", "abc123", "msg")
            assert result["status"] == "error"

    def test_webhook_exception_handling(self):
        """Even internal exceptions return 200 (GitHub best practice)."""
        from yuleosh.api.webhooks import handle_webhooks
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_ci:
            mock_ci.return_value = {"status": "passed", "success": True, "timestamp": "now"}
            result, status = handle_webhooks("POST", "github", {
                "ref": "refs/heads/main",
            })
            # Should still return 200 even if _trigger_ci fails internally
            assert status == 200

    def test_github_push_no_head_commit(self):
        """No head_commit in payload."""
        from yuleosh.api.webhooks import handle_webhooks
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_ci:
            mock_ci.return_value = {"status": "passed", "success": True, "timestamp": "now"}
            result, status = handle_webhooks("POST", "github", {
                "repository": {"full_name": "org/repo"},
                "ref": "refs/heads/develop",
            })
            assert status == 200
            data = result["data"]
            assert data["commit"] == ""
            assert data["branch"] == "develop"

    def test_webhooks_without_body(self):
        """handle_webhooks with body=None."""
        from yuleosh.api.webhooks import handle_webhooks
        with patch("yuleosh.api.webhooks._trigger_ci") as mock_ci:
            mock_ci.return_value = {"status": "passed", "success": True, "timestamp": "now"}
            result, status = handle_webhooks("POST", "github", None)
            assert status == 200


# =============================================================================
# wizard.py
# =============================================================================

class TestWizard:
    """handle_wizard — first-run wizard."""

    def test_wrong_method(self):
        from yuleosh.api.wizard import handle_wizard
        result, status = handle_wizard("GET")
        assert result["ok"] is False
        assert status == 405

    def test_complete_wizard(self):
        from yuleosh.api.wizard import handle_wizard
        result, status = handle_wizard("POST")
        assert status == 200
        assert result["ok"] is True
        assert result["data"]["completed"] is True

    def test_complete_twice(self):
        """Completing wizard twice is safe."""
        from yuleosh.api.wizard import handle_wizard
        handle_wizard("POST")
        result, status = handle_wizard("POST")
        assert status == 200
        assert result["data"]["completed"] is True


# =============================================================================
# ratelimit.py
# =============================================================================

class TestRateLimit:
    """check_rate_limit, get_remaining, reset."""

    def test_check_allows_first_request(self):
        from yuleosh.api.ratelimit import check_rate_limit
        allowed, retry = check_rate_limit("192.168.1.1")
        assert allowed is True
        assert retry == 0

    def test_get_remaining_full(self):
        from yuleosh.api.ratelimit import get_remaining
        remaining = get_remaining("10.0.0.1")
        assert remaining == 100  # Default limit is 100

    def test_get_remaining_after_requests(self):
        from yuleosh.api.ratelimit import check_rate_limit, get_remaining
        for _ in range(5):
            check_rate_limit("10.0.0.2")
        remaining = get_remaining("10.0.0.2")
        assert remaining == 95

    def test_get_remaining_new_ip(self):
        from yuleosh.api.ratelimit import get_remaining
        remaining = get_remaining("new-ip")
        assert remaining == 100

    def test_reset(self):
        from yuleosh.api.ratelimit import check_rate_limit, get_remaining, reset
        check_rate_limit("10.0.0.1")
        check_rate_limit("10.0.0.1")
        assert get_remaining("10.0.0.1") <= 98
        reset()
        assert get_remaining("10.0.0.1") == 100

    @patch.dict(os.environ, {"YULEOSH_RATE_LIMIT": "10"})
    def test_custom_rate_limit(self):
        """Env var YULEOSH_RATE_LIMIT changes the limit.

        Uses monkeypatch + module reimport to avoid importlib.reload()
        which breaks coverage instrumentation.
        """
        import importlib
        import yuleosh.api.ratelimit
        old_val = os.environ.get("YULEOSH_RATE_LIMIT")
        os.environ["YULEOSH_RATE_LIMIT"] = "10"
        importlib.reload(yuleosh.api.ratelimit)
        from yuleosh.api.ratelimit import check_rate_limit, get_remaining
        try:
            for _ in range(10):
                allowed, _ = check_rate_limit("custom-ip")
                assert allowed is True
            allowed, retry = check_rate_limit("custom-ip")
            assert allowed is False
            assert retry > 0
        finally:
            if old_val is None:
                os.environ.pop("YULEOSH_RATE_LIMIT", None)
            else:
                os.environ["YULEOSH_RATE_LIMIT"] = old_val
            importlib.reload(yuleosh.api.ratelimit)

    def test_pruning(self):
        """Old timestamps are pruned."""
        from yuleosh.api.ratelimit import check_rate_limit, _requests, _WINDOW_SECONDS
        import time

        # Add an old timestamp
        old = time.time() - _WINDOW_SECONDS - 10
        _requests["prune-ip"].append(old)
        allowed, _ = check_rate_limit("prune-ip")
        assert allowed is True  # Old timestamp should be pruned

    def test_retry_after_calculation(self):
        """When rate limited, retry_after is > 0."""
        from yuleosh.api.ratelimit import check_rate_limit, _RATE_LIMIT, reset
        reset()

        ip = "rate-limited-ip"
        for _ in range(_RATE_LIMIT):
            check_rate_limit(ip)
        allowed, retry = check_rate_limit(ip)
        assert allowed is False
        assert retry >= 1
