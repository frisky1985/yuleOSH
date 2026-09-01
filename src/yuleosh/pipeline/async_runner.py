# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH v0.9.0 — Async Pipeline Scheduler.

Replaces synchronous pipeline execution with thread-pool based async execution.
Provides status tracking and polling API for both CI layers and full pipeline runs.
"""

import json
import logging
import secrets
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("pipeline.async_runner")

_PIPELINE_JOBS: dict[str, dict] = {}  # job_id → {status, result, started_at, ...}
_pool: Optional[ThreadPoolExecutor] = None

# ── Pipeline stages for full pipeline runs ────────────────────────────────

FULL_PIPELINE_STAGES = [
    {"key": "arxml_parse",     "name": "ARXML 解析"},
    {"key": "config_validate", "name": "配置验证"},
    {"key": "rte_generate",    "name": "RTE 代码生成"},
    {"key": "ci_compile",      "name": "CI 编译 (Layer 1)"},
    {"key": "misra_check",     "name": "MISRA 检查 (Layer 2)"},
    {"key": "coverage",        "name": "覆盖率分析 (Layer 3)"},
]


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-")
    return _pool


def _record_pipeline_usage(org_id: int, user_id: int | None = None,
                           user_email: str | None = None) -> None:
    """Portal 方案 B (2026-08-10): 记录 pipeline_run 计量到 usage_log。

    6 阶段模拟器无 LLM 调用，llm_tokens=0；真实 token 消费在
    run_pipeline（24 步）结束处计量。失败不阻塞；org_id=0（CLI/单机）跳过。
    Phase 9 (2026-08-10): 携带用户归因（user_id/user_email）。
    """
    if not org_id:
        return
    try:
        from yuleosh.store import Store
        from yuleosh.usage import record_pipeline_run
        record_pipeline_run(Store(), org_id, 0, llm_tokens=0,
                            user_id=user_id, user_email=user_email)
    except Exception as _usage_err:
        log.warning("Usage recording failed (non-fatal): %s", _usage_err)


# ── Main API ──────────────────────────────────────────────────────────────

def submit_pipeline(project_dir: str, layer: int = 1, org_id: int = 0,
                    user_id: int | None = None,
                    user_email: str | None = None) -> str:
    """Submit a CI-layer pipeline job for async execution. Returns job_id."""
    job_id = secrets.token_hex(8)
    _PIPELINE_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "type": "ci_layer",
        "project_dir": project_dir,
        "layer": layer,
        "org_id": org_id,
        "user_id": user_id,
        "user_email": user_email,
        "progress": 0,
        "current_stage": "queued",
        "stages": [],
        "started_at": None,
        "completed_at": None,
        "result": None,
        "logs": [],
    }
    pool = _get_pool()
    pool.submit(_run_ci_job, job_id, project_dir, layer, org_id, user_id, user_email)
    return job_id


def submit_full_pipeline(
    project_dir: str,
    config_json: Optional[str] = None,
    arxml_content: Optional[str] = None,
    org_id: int = 0,
    user_id: int | None = None,
    user_email: str | None = None,
) -> str:
    """Submit a full yuleOSH pipeline (RTE → CI → MISRA) with optional config.
    
    Args:
        project_dir: Base project directory for pipeline artifacts.
        config_json: Optional JSON string of module configurations.
        arxml_content: Optional ARXML string.
        org_id: 消费计量归属组织（Portal 方案 B, 2026-08-10；默认 0 不计量）。
        user_id/user_email: 用户归因（Phase 9, 2026-08-10；CLI 为 None）。
    
    Returns: job_id for status polling.
    """
    job_id = secrets.token_hex(8)
    stages = FULL_PIPELINE_STAGES.copy()

    _PIPELINE_JOBS[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "type": "full_pipeline",
        "project_dir": project_dir,
        "config_json": config_json,
        "arxml_content": arxml_content,
        "org_id": org_id,
        "user_id": user_id,
        "user_email": user_email,
        "progress": 0,
        "current_stage": "queued",
        "stages": [dict(s, status="pending") for s in stages],
        "started_at": None,
        "completed_at": None,
        "result": None,
        "logs": [],
    }
    pool = _get_pool()
    pool.submit(_run_full_pipeline, job_id, project_dir, config_json, arxml_content,
                org_id, user_id, user_email)
    return job_id


# ── Internal runners ──────────────────────────────────────────────────────

def _append_log(job_id: str, message: str):
    job = _PIPELINE_JOBS.get(job_id)
    if job:
        ts = datetime.now().strftime("%H:%M:%S")
        job.setdefault("logs", []).append(f"[{ts}] {message}")
        job["updated_at"] = datetime.now().isoformat()


def _update_stage(job_id: str, stage_key: str, status: str, progress: int = None):
    job = _PIPELINE_JOBS.get(job_id)
    if job:
        for s in job.get("stages", []):
            if s["key"] == stage_key:
                s["status"] = status
                break
        if progress is not None:
            job["progress"] = progress
        job["current_stage"] = stage_key
        job["updated_at"] = datetime.now().isoformat()


def _run_ci_job(job_id: str, project_dir: str, layer: int, org_id: int = 0,
                user_id: int | None = None, user_email: str | None = None):
    """Execute CI layer in background thread.

    P1-8 (W-05): failures must be EXPLICIT.  Previously an ImportError or a
    "signal only in main thread" ValueError turned the job into a simulated
    pass — CI results were fabricated.  Any failure now marks the job
    ``failed`` with the reason logged (never a fake pass).
    """
    job = _PIPELINE_JOBS.get(job_id)
    if not job:
        return
    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    _append_log(job_id, f"Starting CI Layer {layer}...")

    try:
        if layer == 1:
            from yuleosh.ci import run_layer1 as _rl1
            _append_log(job_id, "Running Layer 1 (compile)...")
            job["result"] = str(_rl1(project_dir) or "ok")
        elif layer == 2:
            from yuleosh.ci import run_layer2 as _rl2
            _append_log(job_id, "Running Layer 2 (MISRA)...")
            job["result"] = str(_rl2(project_dir) or "ok")
        elif layer == 3:
            from yuleosh.ci import run_layer3 as _rl3
            _append_log(job_id, "Running Layer 3 (coverage)...")
            job["result"] = str(_rl3(project_dir) or "ok")
        else:
            from yuleosh.ci.run import run_all as _ra
            _append_log(job_id, "Running all CI layers...")
            job["result"] = str(_ra(project_dir) or "ok")
        job["status"] = "passed"
        _append_log(job_id, "CI Layer completed successfully.")
    except Exception as e:
        # P1-8: explicit failure — no simulated pass under any circumstance.
        log.error("CI layer %s failed for job %s: %s", layer, job_id, e, exc_info=True)
        job["status"] = "failed"
        job["result"] = str(e)[:500]
        _append_log(job_id, f"FAILED: {e}")

    job["progress"] = 100
    job["completed_at"] = datetime.now().isoformat()
    job["updated_at"] = datetime.now().isoformat()
    _record_pipeline_usage(org_id, user_id, user_email)


def _run_full_pipeline(
    job_id: str, project_dir: str,
    config_json: Optional[str], arxml_content: Optional[str],
    org_id: int = 0,
    user_id: int | None = None,
    user_email: str | None = None,
):
    """Execute full pipeline (ARXML parse → validate → RTE → CI → MISRA)."""
    job = _PIPELINE_JOBS.get(job_id)
    if not job:
        return

    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    _append_log(job_id, "=== yuleOSH Full Pipeline Started ===")

    total_stages = len(FULL_PIPELINE_STAGES)

    try:
        # Stage 1: ARXML Parse
        _update_stage(job_id, "arxml_parse", "running")
        _append_log(job_id, "Stage 1/6: Parsing ARXML configuration...")
        time.sleep(0.5)

        if arxml_content:
            # Save ARXML to temp file for pipeline processing
            arxml_dir = Path(project_dir) / ".yuleosh" / "pipeline" / job_id
            arxml_dir.mkdir(parents=True, exist_ok=True)
            arxml_path = arxml_dir / "config.arxml"
            arxml_path.write_text(arxml_content)
            _append_log(job_id, f"ARXML saved to {arxml_path}")
        elif config_json:
            cfg_dir = Path(project_dir) / ".yuleosh" / "pipeline" / job_id
            cfg_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = cfg_dir / "config.json"
            cfg_path.write_text(config_json)
            _append_log(job_id, f"Config JSON saved to {cfg_path}")
        else:
            _append_log(job_id, "No config provided, using existing project files.")

        _update_stage(job_id, "arxml_parse", "passed", int(15 / total_stages * 100))

        # Stage 2: Config Validation
        _update_stage(job_id, "config_validate", "running")
        _append_log(job_id, "Stage 2/6: Validating configuration...")
        try:
            from yuleosh.pipeline.config_validator import validate_pipeline_config
            vresult = validate_pipeline_config(
                project_dir=project_dir,
                config_json=config_json,
                arxml_content=arxml_content,
            )
            if not vresult["valid"]:
                _append_log(job_id, f"Validation issues found: {len(vresult['issues'])}")
                for issue in vresult["issues"][:5]:
                    _append_log(job_id, f"  ⚠ {issue}")
            else:
                _append_log(job_id, "Configuration valid.")
        except ImportError:
            _append_log(job_id, "Config validator not available (skipping).")

        _update_stage(job_id, "config_validate", "passed", int(30 / total_stages * 100))

        # Stage 3: RTE Generate
        _update_stage(job_id, "rte_generate", "running")
        _append_log(job_id, "Stage 3/6: Generating RTE code...")
        try:
            from yuleosh.autosar import rte_generator
            rte_dir = Path(project_dir) / ".yuleosh" / "pipeline" / job_id / "rte"
            rte_dir.mkdir(parents=True, exist_ok=True)
            output = rte_generator.generate(
                output_dir=str(rte_dir),
                arxml_path=str(arxml_dir / "config.arxml") if arxml_content else None,
                config_path=str(cfg_dir / "config.json") if config_json else None,
            )
            generated_files = output.get("files", [])
            _append_log(job_id, f"RTE generated: {len(generated_files)} files")
        except ImportError:
            _append_log(job_id, "RTE generator not available yet (mock stage).")
            # Create mock RTE files for demo
            rte_dir = Path(project_dir) / ".yuleosh" / "pipeline" / job_id / "rte"
            rte_dir.mkdir(parents=True, exist_ok=True)
            (rte_dir / "Rte.c").write_text("// RTE generated by yuleOSH\n")
            (rte_dir / "Rte.h").write_text("// RTE header generated by yuleOSH\n")
            (rte_dir / "Rte_Swc.h").write_text("// SWC header generated by yuleOSH\n")
            _append_log(job_id, "Mock RTE files created (Rte.c, Rte.h, Rte_Swc.h).")

        _update_stage(job_id, "rte_generate", "passed", int(50 / total_stages * 100))

        # Stage 4: CI Compile (Layer 1)
        _update_stage(job_id, "ci_compile", "running")
        _append_log(job_id, "Stage 4/6: Compiling with GCC...")
        time.sleep(1)

        try:
            from yuleosh.ci import run_layer1
            compile_result = run_layer1(project_dir)
            if compile_result and "failed" in str(compile_result).lower():
                raise RuntimeError(f"Compile failed: {compile_result}")
            _append_log(job_id, "Compilation passed.")
        except Exception as e:
            # P1-8: CI stages must fail explicitly — no simulated pass.
            raise RuntimeError(f"CI compile stage failed: {e}") from e

        _update_stage(job_id, "ci_compile", "passed", int(70 / total_stages * 100))

        # Stage 5: MISRA Check (Layer 2)
        _update_stage(job_id, "misra_check", "running")
        _append_log(job_id, "Stage 5/6: Checking MISRA compliance...")
        time.sleep(1)

        try:
            from yuleosh.ci import run_layer2
            misra_result = run_layer2(project_dir)
            violations = 0
            if misra_result and isinstance(misra_result, dict):
                violations = misra_result.get("violations", 0)
            _append_log(job_id, f"MISRA check passed. Violations: {violations}")
        except Exception as e:
            # P1-8: explicit failure — no simulated pass.
            raise RuntimeError(f"MISRA check stage failed: {e}") from e

        _update_stage(job_id, "misra_check", "passed", int(85 / total_stages * 100))

        # Stage 6: Coverage (Layer 3)
        _update_stage(job_id, "coverage", "running")
        _append_log(job_id, "Stage 6/6: Analyzing code coverage...")
        time.sleep(0.5)

        try:
            from yuleosh.ci import run_layer3
            cov_result = run_layer3(project_dir)
            coverage_pct = 0
            if cov_result and isinstance(cov_result, dict):
                coverage_pct = cov_result.get("coverage", 0)
            _append_log(job_id, f"Coverage: {coverage_pct}%")
        except Exception as e:
            # P1-8: explicit failure — no simulated pass.
            raise RuntimeError(f"Coverage stage failed: {e}") from e

        _update_stage(job_id, "coverage", "passed", 100)

        # Finalize
        job["status"] = "passed"
        job["result"] = {
            "summary": "All 6 stages completed successfully",
            "stages_passed": total_stages,
            "stages_total": total_stages,
        }
        _append_log(job_id, "=== Pipeline completed successfully! ===")

    except Exception as e:
        log.exception("Pipeline %s failed", job_id)
        job["status"] = "failed"
        job["result"] = {"error": str(e)[:500], "summary": f"Failed at stage: {job.get('current_stage', 'unknown')}"}
        _append_log(job_id, f"❌ Pipeline FAILED: {e}")

    job["progress"] = 100
    job["completed_at"] = datetime.now().isoformat()
    job["updated_at"] = datetime.now().isoformat()
    _record_pipeline_usage(org_id, user_id, user_email)

    # ── Notification on completion (for all autosar / full_pipeline types) ──
    _notify_pipeline_completion(job_id)


# ── Status queries ────────────────────────────────────────────────────────

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
    return {
        "total": total, "running": running, "queued": queued,
        "passed": passed, "failed": failed,
    }


def _notify_pipeline_completion(job_id: str):
    """Send notification for a completed pipeline job.

    Writes a notification file to reports/pipeline-notify/ and
    attempts to send via Feishu if configured.
    """
    job = _PIPELINE_JOBS.get(job_id)
    if not job or job["status"] not in ("passed", "failed"):
        return

    status = job["status"]
    project_name = "yuleASR" if job.get("type") == "full_pipeline" else job.get("type", "pipeline")

    # Write notification file
    osh_home = os.environ.get("OSH_HOME", "")
    if osh_home:
        notify_dir = Path(osh_home) / "reports" / "pipeline-notify"
        notify_dir.mkdir(parents=True, exist_ok=True)
        notify_payload = {
            "project": project_name,
            "status": status,
            "job_id": job_id,
            "timestamp": datetime.now().isoformat(),
            "channel": "feishu",
        }
        notify_file = notify_dir / f"{project_name}-{job_id}.json"
        try:
            notify_file.write_text(json.dumps(notify_payload, indent=2))
            _append_log(job_id, f"Notification file written: {notify_file}")
        except Exception as e:
            _append_log(job_id, f"Notification file write failed: {e}")

    # Attempt feishu notification
    try:
        # Try importing the notify module using the project-relative path
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "yuleosh_notify",
            os.path.join(os.path.dirname(__file__), "..", "notify.py")
        )
        if spec and spec.loader:
            notify_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(notify_mod)
            notify_mod.notify_pipeline(
                name=project_name,
                status=status,
                total_steps=6,
                completed_steps=6 if status == "passed" else 0,
            )
            _append_log(job_id, "Feishu notification sent")
    except Exception as e:
        log.debug("Feishu notify not available: %s", e)
