"""yuleOSH v0.9.0 — Async Pipeline Scheduler.

Replaces synchronous pipeline execution with thread-pool based async execution.
Provides status tracking and polling API.
"""
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

_PIPELINE_JOBS: dict[str, dict] = {}  # job_id → {status, result, started_at, completed_at}
_pool: Optional["ThreadPoolExecutor"] = None


def _get_pool():
    from concurrent.futures import ThreadPoolExecutor
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-")
    return _pool


def submit_pipeline(project_dir: str, layer: int = 1) -> str:
    """Submit a pipeline job for async execution. Returns job_id."""
    import secrets
    job_id = secrets.token_hex(8)

    _PIPELINE_JOBS[job_id] = {
        "status": "queued",
        "project_dir": project_dir,
        "layer": layer,
        "started_at": None,
        "completed_at": None,
        "result": None,
    }

    pool = _get_pool()
    pool.submit(_run_pipeline_job, job_id, project_dir, layer)

    return job_id


def _run_pipeline_job(job_id: str, project_dir: str, layer: int):
    """Execute pipeline in background thread."""
    _PIPELINE_JOBS[job_id]["status"] = "running"
    _PIPELINE_JOBS[job_id]["started_at"] = datetime.now().isoformat()
    _PIPELINE_JOBS[job_id]["updated_at"] = datetime.now().isoformat()

    try:
        from ci.run import run_all
        if layer == 0:
            result = run_all(project_dir)
        else:
            result = _run_single_layer(project_dir, layer)
        _PIPELINE_JOBS[job_id]["status"] = "passed"
        _PIPELINE_JOBS[job_id]["result"] = str(result)
    except Exception as e:
        _PIPELINE_JOBS[job_id]["status"] = "failed"
        _PIPELINE_JOBS[job_id]["result"] = str(e)[:500]

    _PIPELINE_JOBS[job_id]["completed_at"] = datetime.now().isoformat()
    _PIPELINE_JOBS[job_id]["updated_at"] = datetime.now().isoformat()


def _run_single_layer(project_dir: str, layer: int):
    """Run a single CI layer (1, 2, 25, or 3)."""
    from ci.run import run_layer1, run_layer2, run_layer3, run_layer_25
    runners = {1: run_layer1, 2: run_layer2, 25: run_layer_25, 3: run_layer3}
    runner = runners.get(layer)
    if runner:
        return runner(project_dir)
    return f"Unknown layer: {layer}"


def get_job_status(job_id: str) -> Optional[dict]:
    """Get current status of a pipeline job."""
    return _PIPELINE_JOBS.get(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    """List recent pipeline jobs, newest first."""
    jobs = list(_PIPELINE_JOBS.values())
    jobs.sort(key=lambda j: j.get("started_at") or "", reverse=True)
    return jobs[:limit]


def get_pipeline_stats() -> dict:
    """Get aggregate pipeline statistics."""
    total = len(_PIPELINE_JOBS)
    running = sum(1 for j in _PIPELINE_JOBS.values() if j["status"] == "running")
    queued = sum(1 for j in _PIPELINE_JOBS.values() if j["status"] == "queued")
    passed = sum(1 for j in _PIPELINE_JOBS.values() if j["status"] == "passed")
    failed = sum(1 for j in _PIPELINE_JOBS.values() if j["status"] == "failed")
    return {"total": total, "running": running, "queued": queued,
            "passed": passed, "failed": failed}
