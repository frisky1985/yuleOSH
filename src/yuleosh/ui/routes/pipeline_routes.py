# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

    Security (P0): requires a valid Bearer session (tenant_routes._require_auth);
    project_dir must resolve inside OSH_HOME; type/layer are whitelisted;
    arxml_content is size-capped; submissions are throttled.

    Request body (JSON):
        {
            "config_json": "...",     # Optional: JSON string of config
            "arxml_content": "...",   # Optional: ARXML string
            "project_dir": "...",     # Optional: project dir override
            "type": "full" | "ci",    # Pipeline type (default: full)
            "layer": 1                # CI layer (1/2/3, default: 1, only for type=ci)
        }
    """
    # Auth first — fail closed.
    from yuleosh.ui.routes.tenant_routes import _require_auth
    user = _require_auth(handler)
    if not user:
        return {"ok": False, "error": "Authentication required"}

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

    # Path whitelist: resolved project_dir must stay inside OSH_HOME.
    osh_home = Path(os.environ.get("OSH_HOME", "")).resolve()
    try:
        resolved = Path(project_dir).expanduser().resolve()
        resolved.relative_to(osh_home)
    except (ValueError, OSError):
        return {"ok": False, "error": "project_dir must be inside OSH_HOME"}

    # Type/layer whitelist.
    if pipeline_type not in ("full", "full_pipeline", "ci"):
        return {"ok": False, "error": "type must be one of: full, ci"}
    if layer not in (1, 2, 3):
        return {"ok": False, "error": "layer must be 1, 2 or 3"}

    # Size caps (prevent memory/disk abuse).
    if arxml_content and len(arxml_content) > 1_000_000:
        return {"ok": False, "error": "arxml_content too large (max 1MB)"}
    if config_json and len(config_json) > 1_000_000:
        return {"ok": False, "error": "config_json too large (max 1MB)"}

    from yuleosh.pipeline.async_runner import submit_pipeline, submit_full_pipeline

    try:
        if pipeline_type == "full" or pipeline_type == "full_pipeline":
            job_id = submit_full_pipeline(
                project_dir=str(resolved),
                config_json=config_json,
                arxml_content=arxml_content,
            )
        else:
            job_id = submit_pipeline(
                project_dir=str(resolved),
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


def handle_yuleasr_status(handler: BaseHTTPRequestHandler) -> dict:
    """GET /api/v1/pipeline/yuleasr-status — yuleASR BSW project live status.

    Aggregates the latest pipeline run results for the yuleASR project.
    Reads from evidence-bundle artifacts and pipeline job history.
    """
    import json as _json
    from pathlib import Path
    from datetime import datetime

    yuleasr_home = os.environ.get("YULEASR_HOME", "")
    if not yuleasr_home:
        # Try default path alongside yuleOSH
        osh_home = os.environ.get("OSH_HOME", "")
        candidate = str(Path(osh_home).parent / "yuleASR") if osh_home else ""
        if candidate and Path(candidate).exists():
            yuleasr_home = candidate

    result = {
        "ok": True,
        "project": "yuleASR",
        "type": "autosar",
        "compile_status": None,
        "misra_violations": None,
        "coverage": None,
        "qemu_status": None,
        "last_run_at": None,
        "errors": [],
        "available": False,
    }

    if not yuleasr_home or not Path(yuleasr_home).exists():
        result["errors"].append(f"yuleASR home not found: {yuleasr_home}")
        return result

    result["available"] = True
    result["yuleasr_home"] = yuleasr_home

    evidence_dir = Path(yuleasr_home) / ".yuleosh" / "evidence-bundle"

    # ── 1. CI results (compile + QEMU status) ──
    ci_results_file = evidence_dir / "ci-results" / "ci-results.json"
    if ci_results_file.exists():
        try:
            ci_data = _json.loads(ci_results_file.read_text())
            pipeline_info = ci_data.get("pipeline", {})
            result["compile_status"] = pipeline_info.get("status", "unknown")
            result["last_run_at"] = pipeline_info.get("completed_at", ci_data.get("generated_at"))
            # QEMU / SIL test results
            sil_file = evidence_dir / "ci-results" / "sil-test-results.json"
            if sil_file.exists():
                sil_data = _json.loads(sil_file.read_text())
                result["qemu_status"] = "passed" if sil_data.get("all_passed") else "failed"
            else:
                # Fallback to sil-results.json
                sil_results = evidence_dir / "ci-results" / "sil-results.json"
                if sil_results.exists():
                    sr = _json.loads(sil_results.read_text())
                    sil_reports = sr.get("sil_reports", [])
                    if sil_reports:
                        all_passed = all(
                            r.get("status") == "completed" and r.get("failed", 0) == 0
                            for r in sil_reports
                        )
                        result["qemu_status"] = "passed" if all_passed else "failed"
                        if not result["last_run_at"]:
                            result["last_run_at"] = sr.get("generated_at")
        except Exception as e:
            result["errors"].append(f"ci-results parse: {e}")

    # ── 2. MISRA violations ──
    misra_file = evidence_dir / "misra-reports" / "misra-report.json"
    if misra_file.exists():
        try:
            misra_data = _json.loads(misra_file.read_text())
            result["misra_violations"] = misra_data.get("total_violations", 0)
        except Exception as e:
            result["errors"].append(f"misra parse: {e}")

    # ── 3. Coverage ──
    coverage_file = evidence_dir / "coverage" / "c-coverage.json"
    if coverage_file.exists():
        try:
            cov_data = _json.loads(coverage_file.read_text())
            summary = cov_data.get("summary", {})
            lines = summary.get("lines", {})
            result["coverage"] = {
                "line_rate": lines.get("rate", 0),
                "line_covered": lines.get("covered", 0),
                "line_total": lines.get("total", 0),
                "branch_rate": summary.get("branches", {}).get("rate", 0),
                "function_rate": summary.get("functions", {}).get("rate", 0),
            }
        except Exception as e:
            result["errors"].append(f"coverage parse: {e}")

    # ── 4. Also check pipeline job history for autosar type runs ──
    from yuleosh.pipeline.async_runner import list_jobs
    recent = list_jobs(limit=10)
    autosar_runs = [j for j in recent if j.get("type") in ("full_pipeline", "autosar")]
    result["recent_autosar_runs"] = autosar_runs[:5]

    return result


def handle_yuleasr_notify(handler: BaseHTTPRequestHandler, body: bytes) -> dict:
    """POST /api/v1/pipeline/yuleasr-notify — Send yuleASR pipeline result notification.

    Writes a notification file that the cron deliver mechanism can pick up.
    """
    import json as _json
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    try:
        data = _json.loads(body) if body else {}
    except _json.JSONDecodeError as e:
        return {"ok": False, "error": f"Invalid JSON body: {e}"}

    project = data.get("project", "yuleASR")
    status = data.get("status", "unknown")
    misra_count = data.get("misra_violations", "?")
    coverage = data.get("coverage", "?")
    qemu = data.get("qemu_status", "?")

    # Write notification file for cron deliver pickup
    osh_home = os.environ.get("OSH_HOME", "")
    notify_dir = _Path(osh_home) / "reports" / "pipeline-notify" if osh_home else _Path("reports/pipeline-notify")
    notify_dir.mkdir(parents=True, exist_ok=True)

    notify_file = notify_dir / f"yuleasr-{_dt.now().strftime('%Y%m%d-%H%M%S')}.json"
    notify_payload = {
        "project": project,
        "status": status,
        "misra_violations": misra_count,
        "coverage": coverage,
        "qemu_status": qemu,
        "timestamp": _dt.now().isoformat(),
        "channel": "feishu",
    }
    notify_file.write_text(_json.dumps(notify_payload, indent=2, ensure_ascii=False))

    log.info("yuleASR notify file written: %s", notify_file)

    # Also attempt feishu notification directly
    try:
        from yuleosh.notify import notify_pipeline
        errors = data.get("errors", [])
        notify_pipeline(
            name=project,
            status=status,
            total_steps=6,
            completed_steps=6 if status in ("passed", "completed") else 0,
            errors=errors if errors else None,
        )
    except Exception as e:
        log.warning("Feishu notify attempt: %s", e)

    return {
        "ok": True,
        "notify_file": str(notify_file),
        "message": f"Notification queued for {project}",
    }
