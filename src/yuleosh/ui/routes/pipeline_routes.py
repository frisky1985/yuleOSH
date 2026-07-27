# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard — Pipeline API route handlers.

Endpoints:
    POST /api/v1/pipeline/trigger      — Trigger a new pipeline run
    GET  /api/v1/pipeline/status/<id>  — Get pipeline job status
    GET  /api/v1/pipeline/runs         — List recent pipeline runs
    GET  /api/v1/pipeline/stats        — Pipeline aggregate statistics

Request/response are JSON.
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

log = logging.getLogger("routes.pipeline")


def handle_pipeline_trigger(handler: BaseHTTPRequestHandler, body: bytes) -> dict:
    """POST /api/v1/pipeline/trigger — Start a new pipeline run.

    Request body (JSON):
        {
            "config_json": "...",     # Optional: JSON string of config
            "arxml_content": "...",   # Optional: ARXML string
            "project_dir": "...",     # Optional: project dir override
            "type": "full" | "ci",    # Pipeline type (default: full)
            "layer": 1                # CI layer (1/2/3, default: 1, only for type=ci)
        }
    """
    try:
        data = json.loads(body) if body else {}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid JSON body: {e}"}

    config_json = data.get("config_json")
    arxml_content = data.get("arxml_content")
    project_dir = data.get("project_dir", os.environ.get("OSH_HOME", ""))
    pipeline_type = data.get("type", "full")
    layer = data.get("layer", 1)

    if not project_dir:
        return {"ok": False, "error": "project_dir is required or set OSH_HOME"}

    from yuleosh.pipeline.async_runner import submit_pipeline, submit_full_pipeline

    try:
        if pipeline_type == "full" or pipeline_type == "full_pipeline":
            job_id = submit_full_pipeline(
                project_dir=project_dir,
                config_json=config_json,
                arxml_content=arxml_content,
            )
        else:
            job_id = submit_pipeline(
                project_dir=project_dir,
                layer=layer,
            )

        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "type": pipeline_type,
            "poll_url": f"/api/v1/pipeline/status/{job_id}",
        }
    except Exception as e:
        log.exception("Pipeline trigger failed")
        return {"ok": False, "error": str(e)}


def handle_pipeline_status(handler: BaseHTTPRequestHandler, path: str) -> dict:
    """GET /api/v1/pipeline/status/<job_id> — Get job status."""
    # Extract job_id from path: /api/v1/pipeline/status/<job_id>
    parts = path.strip("/").split("/")
    # parts = ['api', 'v1', 'pipeline', 'status', '<job_id>']
    job_id = parts[-1] if len(parts) >= 5 else ""

    if not job_id:
        return {"ok": False, "error": "Missing job_id"}, 404

    from yuleosh.pipeline.async_runner import get_job_status
    status = get_job_status(job_id)

    if status is None:
        return {"ok": False, "error": f"Job not found: {job_id}"}, 404

    return {
        "ok": True,
        "job": {
            "job_id": status.get("job_id"),
            "status": status.get("status"),
            "type": status.get("type"),
            "progress": status.get("progress", 0),
            "current_stage": status.get("current_stage"),
            "stages": status.get("stages", []),
            "logs": status.get("logs", []),
            "started_at": status.get("started_at"),
            "completed_at": status.get("completed_at"),
            "result": status.get("result"),
        }
    }


def handle_pipeline_runs(handler: BaseHTTPRequestHandler) -> dict:
    """GET /api/v1/pipeline/runs — List recent pipeline runs."""
    from yuleosh.pipeline.async_runner import list_jobs
    jobs = list_jobs(limit=20)
    return {
        "ok": True,
        "runs": [
            {
                "job_id": j.get("job_id"),
                "status": j.get("status"),
                "type": j.get("type"),
                "progress": j.get("progress", 0),
                "current_stage": j.get("current_stage"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
            }
            for j in jobs
        ],
        "count": len(jobs),
    }


def handle_pipeline_stats(handler: BaseHTTPRequestHandler) -> dict:
    """GET /api/v1/pipeline/stats — Aggregate pipeline statistics."""
    from yuleosh.pipeline.async_runner import get_pipeline_stats
    stats = get_pipeline_stats()
    return {"ok": True, **stats}
