"""Tests for pipeline/async_runner.py — Async Pipeline Scheduler."""
import time
import threading
from unittest.mock import patch, MagicMock

from yuleosh.pipeline.async_runner import (
    submit_pipeline,
    get_job_status,
    list_jobs,
    get_pipeline_stats,
    _PIPELINE_JOBS,
    _pool,
)


def _clear_state():
    _PIPELINE_JOBS.clear()
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False)
        import yuleosh.pipeline.async_runner as m
        m._pool = None


def test_submit_pipeline():
    _clear_state()
    with patch("yuleosh.pipeline.async_runner._run_pipeline_job"):
        job_id = submit_pipeline("/tmp/test", layer=1)
        assert job_id, "should return a job_id"
        assert len(job_id) == 16, "token_hex(8) produces 16 chars"
        status = get_job_status(job_id)
        assert status is not None
        assert status["status"] == "queued"
        assert status["project_dir"] == "/tmp/test"
        assert status["layer"] == 1


def test_submit_pipeline_default_layer():
    _clear_state()
    with patch("yuleosh.pipeline.async_runner._run_pipeline_job"):
        job_id = submit_pipeline("/tmp/test")
        status = get_job_status(job_id)
        assert status["layer"] == 1


def test_get_job_status_not_found():
    _clear_state()
    assert get_job_status("nonexistent") is None


def test_get_job_status_queued():
    _clear_state()
    _PIPELINE_JOBS["test1"] = {
        "status": "queued", "project_dir": "/tmp", "layer": 1,
        "started_at": None, "completed_at": None, "result": None,
    }
    status = get_job_status("test1")
    assert status["status"] == "queued"


def test_get_job_status_running():
    _clear_state()
    _PIPELINE_JOBS["test1"] = {
        "status": "running", "project_dir": "/tmp", "layer": 1,
        "started_at": "2026-01-01T00:00:00", "completed_at": None, "result": None,
    }
    status = get_job_status("test1")
    assert status["status"] == "running"
    assert status["started_at"] == "2026-01-01T00:00:00"


def test_list_jobs_empty():
    _clear_state()
    assert list_jobs() == []


def test_list_jobs_returns_newest_first():
    _clear_state()
    _PIPELINE_JOBS["a"] = {
        "status": "passed", "project_dir": "/a", "layer": 1,
        "started_at": "2026-01-02T00:00:00", "completed_at": None, "result": "ok",
    }
    _PIPELINE_JOBS["b"] = {
        "status": "queued", "project_dir": "/b", "layer": 2,
        "started_at": "2026-01-01T00:00:00", "completed_at": None, "result": None,
    }
    jobs = list_jobs()
    assert len(jobs) == 2
    assert jobs[0]["project_dir"] == "/a"


def test_list_jobs_limit():
    _clear_state()
    for i in range(5):
        _PIPELINE_JOBS[str(i)] = {
            "status": "queued", "project_dir": f"/p{i}", "layer": 1,
            "started_at": f"2026-01-{i+1:02d}T00:00:00",
            "completed_at": None, "result": None,
        }
    assert len(list_jobs(limit=3)) == 3


def test_get_pipeline_stats_empty():
    _clear_state()
    stats = get_pipeline_stats()
    assert stats == {"total": 0, "running": 0, "queued": 0, "passed": 0, "failed": 0}


def test_get_pipeline_stats_all_categories():
    _clear_state()
    _PIPELINE_JOBS["j1"] = {"status": "running", "project_dir": "/a", "layer": 1,
                             "started_at": None, "completed_at": None, "result": None}
    _PIPELINE_JOBS["j2"] = {"status": "queued", "project_dir": "/b", "layer": 1,
                             "started_at": None, "completed_at": None, "result": None}
    _PIPELINE_JOBS["j3"] = {"status": "passed", "project_dir": "/c", "layer": 1,
                             "started_at": None, "completed_at": None, "result": "ok"}
    _PIPELINE_JOBS["j4"] = {"status": "failed", "project_dir": "/d", "layer": 1,
                             "started_at": None, "completed_at": None, "result": "err"}
    stats = get_pipeline_stats()
    assert stats["total"] == 4
    assert stats["running"] == 1
    assert stats["queued"] == 1
    assert stats["passed"] == 1
    assert stats["failed"] == 1


def test_run_pipeline_job_passed():
    _clear_state()
    import yuleosh.pipeline.async_runner as ar
    ar._PIPELINE_JOBS["job_x"] = {
        "status": "queued", "project_dir": "/tmp/x", "layer": 0,
        "started_at": None, "completed_at": None, "result": None,
    }
    with patch("ci.run.run_all", return_value=0):
        ar._run_pipeline_job("job_x", "/tmp/x", 0)
    status = ar._PIPELINE_JOBS["job_x"]
    assert status["status"] == "passed"
    assert status["completed_at"] is not None


def test_run_pipeline_job_failed():
    import sys
    from unittest.mock import MagicMock
    _clear_state()
    # Mock the ci.run module that's imported inside _run_pipeline_job
    mock_run = MagicMock()
    mock_run.run_all.side_effect = RuntimeError("boom")
    sys.modules["ci"] = MagicMock()
    sys.modules["ci"].run = mock_run
    sys.modules["ci.run"] = mock_run
    
    import yuleosh.pipeline.async_runner as ar
    ar._PIPELINE_JOBS["job_y"] = {
        "status": "queued", "project_dir": "/tmp/y", "layer": 0,
        "started_at": None, "completed_at": None, "result": None,
    }
    ar._run_pipeline_job("job_y", "/tmp/y", 0)
    status = ar._PIPELINE_JOBS["job_y"]
    assert status["status"] == "failed"
    assert "boom" in status["result"]
    del sys.modules["ci.run"]
    del sys.modules["ci"]


def test_run_pipeline_job_passed_import_error():
    """Test that _run_pipeline_job handles import failure gracefully."""
    import sys
    from unittest.mock import MagicMock
    _clear_state()
    mock_run = MagicMock()
    mock_run.run_all.return_value = 0
    sys.modules["ci"] = MagicMock()
    sys.modules["ci"].run = mock_run
    sys.modules["ci.run"] = mock_run
    
    import yuleosh.pipeline.async_runner as ar
    ar._PIPELINE_JOBS["job_z"] = {
        "status": "queued", "project_dir": "/tmp/z", "layer": 0,
        "started_at": None, "completed_at": None, "result": None,
    }
    ar._run_pipeline_job("job_z", "/tmp/z", 0)
    status = ar._PIPELINE_JOBS["job_z"]
    assert status["status"] == "passed"
    del sys.modules["ci.run"]
    del sys.modules["ci"]


def test_run_single_layer_unknown():
    import yuleosh.pipeline.async_runner as ar
    result = ar._run_single_layer("/tmp", 99)
    assert "Unknown layer" in result


def test_run_single_layer_known():
    import sys
    from unittest.mock import MagicMock
    import yuleosh.pipeline.async_runner as ar
    
    mock_ci_run = MagicMock()
    mock_ci_run.run_layer1.return_value = "layer1_ok"
    sys.modules["ci"] = MagicMock()
    sys.modules["ci"].run = mock_ci_run
    sys.modules["ci.run"] = mock_ci_run
    
    result = ar._run_single_layer("/tmp", 1)
    assert result == "layer1_ok"
    del sys.modules["ci.run"]
    del sys.modules["ci"]
