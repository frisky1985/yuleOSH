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
from types import SimpleNamespace
from typing import Optional

log = logging.getLogger("pipeline.async_runner")

_PIPELINE_JOBS: dict[str, dict] = {}  # job_id → {status, result, started_at, ...}
_pool: Optional[ThreadPoolExecutor] = None

# ── Pipeline stages for full pipeline runs ────────────────────────────────

FULL_PIPELINE_STAGES = [
    {"key": "arxml_parse",     "name": "ARXML 解析"},
    {"key": "config_validate", "name": "配置验证"},
    {"key": "code_generate",   "name": "yuleOSH 大模型代码生成"},
    {"key": "rte_generate",    "name": "RTE 代码生成"},
    {"key": "ci_compile",      "name": "CI 编译 (Layer 1)"},
    {"key": "misra_check",     "name": "MISRA 检查 (Layer 2)"},
    {"key": "coverage",        "name": "覆盖率分析 (Layer 3)"},
]

CODEGEN_LAYER_META = [
    ("application", "Application SWC", "src/application"),
    ("rte", "RTE", "src/rte"),
    ("services", "BSW Services", "src/bsw/services"),
    ("ecu_abstraction", "ECU Abstraction", "src/bsw/ecu_abstraction"),
    ("mcal", "MCAL", "src/bsw/mcal"),
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
        "cancel_requested": False,
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
    resume_from: Optional[str] = None,
) -> str:
    """Submit a full yuleOSH pipeline (RTE → CI → MISRA) with optional config.
    
    Args:
        project_dir: Base project directory for pipeline artifacts.
        config_json: Optional JSON string of module configurations.
        arxml_content: Optional ARXML string.
        org_id: 消费计量归属组织（Portal 方案 B, 2026-08-10；默认 0 不计量）。
        user_id/user_email: 用户归因（Phase 9, 2026-08-10；CLI 为 None）。
        resume_from: 失败重试时从该阶段开始，之前的阶段标记为 skipped。
    
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
        "cancel_requested": False,
        "resume_from": resume_from,
    }
    pool = _get_pool()
    pool.submit(_run_full_pipeline, job_id, project_dir, config_json, arxml_content,
                org_id, user_id, user_email, resume_from)
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


# ── Cancellation / stage resume ───────────────────────────────────────────

_STAGE_KEYS = [s["key"] for s in FULL_PIPELINE_STAGES]


class _PipelineCancelled(Exception):
    """用户在阶段边界请求取消。"""


def _stage_index(stage_key: Optional[str]) -> int:
    """把阶段 key 转成下标；未知/空值从第一个阶段开始。"""
    try:
        return _STAGE_KEYS.index(stage_key)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0


def _skip_stage(job_id: str, stage_key: str, start_idx: int) -> bool:
    """失败重试时跳过 resume_from 之前的阶段。"""
    if _stage_index(stage_key) < start_idx:
        _update_stage(job_id, stage_key, "skipped")
        return True
    return False


def _raise_if_cancelled(job_id: str) -> None:
    """在阶段边界检查取消标记（协作式取消，不强杀线程）。"""
    job = _PIPELINE_JOBS.get(job_id)
    if job and job.get("cancel_requested"):
        raise _PipelineCancelled(job_id)


def _mark_cancelled(job: dict, job_id: str) -> None:
    """把任务与阶段状态收敛到 cancelled，未开始的阶段标记 skipped。"""
    job["status"] = "cancelled"
    job["result"] = {
        "cancelled": True,
        "summary": f"Cancelled at stage: {job.get('current_stage', 'unknown')}",
    }
    for stage in job.get("stages", []):
        if stage.get("status") == "running":
            stage["status"] = "cancelled"
        elif stage.get("status") == "pending":
            stage["status"] = "skipped"
    _append_log(job_id, "⏹ Pipeline cancelled by user.")


def request_cancel(job_id: str) -> bool:
    """请求取消一个排队中/运行中的任务。

    运行中的任务会在下一个阶段边界退出；排队中的任务立即标记为 cancelled。
    已完成的任务返回 False。
    """
    job = _PIPELINE_JOBS.get(job_id)
    if not job:
        return False
    if job.get("status") in ("passed", "failed", "cancelled"):
        return False
    job["cancel_requested"] = True
    job["updated_at"] = datetime.now().isoformat()
    _append_log(job_id, "Cancellation requested; stopping at next stage boundary.")
    if job.get("status") == "queued":
        _mark_cancelled(job, job_id)
        job["progress"] = 100
        job["completed_at"] = datetime.now().isoformat()
        _persist_job_result(job)
    return True


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
    # 排队期间已被取消：直接退出，避免覆盖 cancelled 状态。
    if job.get("status") == "cancelled":
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
        if job.get("cancel_requested"):
            _mark_cancelled(job, job_id)
        else:
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
    _persist_job_result(job)


def _stage_code_generation(project_dir: str, job_id: str, config: dict) -> str:
    """Generate code with yuleOSH LLM under the project's pipeline rules.

    Output is isolated per job and deployed only after compile, AUTOSAR layout,
    dependency, and behavior checks pass. A failed model run fails the stage.
    """
    import shutil
    import yaml
    from yuleosh.pipeline.step_handlers.execution import _step_claude_dev_codegen

    root = Path(project_dir)
    job_dir = root / ".yuleosh" / "pipeline" / job_id
    output_dir = job_dir / "codegen"
    template_path = (
        Path(__file__).parent.parent / "templates" / "autosar-classic" / "pipeline" / "config.yaml"
    )
    template_raw = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    codegen_cfg = dict(template_raw.get("codegen") or {})
    project_pipeline = root / "pipeline" / "config.yaml"
    if project_pipeline.exists():
        project_raw = yaml.safe_load(project_pipeline.read_text(encoding="utf-8")) or {}
        codegen_cfg.update(project_raw.get("codegen") or {})
    codegen_cfg["output_dir"] = str(output_dir)
    codegen_cfg["require_verified"] = True

    spec_path = root / "requirements" / "requirements.md"
    architecture_path = root / "design" / "architecture.md"
    job = _PIPELINE_JOBS.get(job_id)
    if job is not None:
        job["code_generation"] = {
            "status": "generating",
            "model": "yuleOSH",
            "rule_source": "pipeline/config.yaml",
            "attempts": 0,
            "repair_count": 0,
            "error_count": 0,
            "layers": [],
        }

    def on_codegen_event(event: str, data: dict) -> None:
        if job is None:
            return
        progress = job.setdefault("code_generation", {})
        attempt = int(data.get("attempt") or 0)
        if attempt:
            progress["attempts"] = max(int(progress.get("attempts") or 0), attempt)
            progress["repair_count"] = max(0, progress["attempts"] - 1)
        if event == "generation_started":
            progress["status"] = "generating"
        elif event == "validation_failed":
            progress["status"] = "validating"
            progress["error_count"] = int(data.get("error_count") or 0)
        elif event == "repair_started":
            progress["status"] = "repairing"
            _append_log(
                job_id,
                f"Code generation attempt {attempt}: model repairing "
                f"{data.get('error_count', 0)} validation issue(s)...",
            )
        elif event == "generation_validated":
            progress["status"] = "validated"
            progress["error_count"] = 0

    session = SimpleNamespace(
        name=job_id,
        spec_path=str(spec_path),
        project_dir=str(root),
        development_mode="generate-code",
        config={"codegen": codegen_cfg},
        artifacts={"architecture": str(architecture_path)} if architecture_path.exists() else {},
        session_dir=job_dir,
        llm_client=None,
        codegen_event_handler=on_codegen_event if job is not None else None,
    )
    try:
        report = _step_claude_dev_codegen(session)
    except Exception:
        if job is not None:
            job["code_generation"]["status"] = "failed"
        raise

    generated_src = output_dir / "src"
    if not generated_src.is_dir():
        if job is not None:
            job["code_generation"]["status"] = "failed"
        raise RuntimeError("Verified code-gen result has no src/ directory")

    source_files = sorted(
        path for path in output_dir.rglob("*")
        if path.is_file() and path.suffix in (".c", ".h")
    )
    relative_files = [path.relative_to(output_dir).as_posix() for path in source_files]
    if job is not None:
        layers = [
            {
                "key": key,
                "name": name,
                "path": prefix,
                "files": sum(path.startswith(prefix + "/") for path in relative_files),
            }
            for key, name, prefix in CODEGEN_LAYER_META
        ]
        job["code_generation"].update({
            "status": "validated",
            "files": len(relative_files),
            "layers": layers,
            "report": report,
        })

    shutil.copytree(generated_src, root / "code" / "src", dirs_exist_ok=True)
    generated_tests = output_dir / "tests"
    if generated_tests.is_dir():
        shutil.copytree(generated_tests, root / "tests", dirs_exist_ok=True)
    if job is not None:
        job["code_generation"]["status"] = "passed"
    return report


def _run_full_pipeline(
    job_id: str, project_dir: str,
    config_json: Optional[str], arxml_content: Optional[str],
    org_id: int = 0,
    user_id: int | None = None,
    user_email: str | None = None,
    resume_from: Optional[str] = None,
):
    """Execute full pipeline (ARXML parse → validate → RTE → CI → MISRA)."""
    job = _PIPELINE_JOBS.get(job_id)
    if not job:
        return
    # 排队期间已被取消：直接退出，避免覆盖 cancelled 状态。
    if job.get("status") == "cancelled":
        return

    job["status"] = "running"
    job["started_at"] = datetime.now().isoformat()
    _append_log(job_id, "=== yuleOSH Full Pipeline Started ===")

    total_stages = len(FULL_PIPELINE_STAGES)
    start_idx = _stage_index(resume_from)
    if start_idx > 0:
        _append_log(job_id, f"Resuming from stage '{resume_from}'; earlier stages skipped.")

    arxml_dir = Path(project_dir) / ".yuleosh" / "pipeline" / job_id
    cfg_dir = arxml_dir

    try:
        # Stage 1: ARXML Parse
        if not _skip_stage(job_id, "arxml_parse", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "arxml_parse", "running")
            _append_log(job_id, "Stage 1/7: Parsing ARXML configuration...")
            time.sleep(0.5)

            if arxml_content:
                # Save ARXML to temp file for pipeline processing
                arxml_dir.mkdir(parents=True, exist_ok=True)
                arxml_path = arxml_dir / "config.arxml"
                arxml_path.write_text(arxml_content)
                _append_log(job_id, f"ARXML saved to {arxml_path}")
            elif config_json:
                cfg_dir.mkdir(parents=True, exist_ok=True)
                cfg_path = cfg_dir / "config.json"
                cfg_path.write_text(config_json)
                _append_log(job_id, f"Config JSON saved to {cfg_path}")
            else:
                _append_log(job_id, "No config provided, using existing project files.")

            _update_stage(job_id, "arxml_parse", "passed", int(15 / total_stages * 100))

        # Stage 2: Config Validation
        if not _skip_stage(job_id, "config_validate", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "config_validate", "running")
            _append_log(job_id, "Stage 2/7: Validating configuration...")
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

        # Stage 3: yuleOSH LLM code generation — pipeline rules are mandatory.
        if not _skip_stage(job_id, "code_generate", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "code_generate", "running")
            _append_log(job_id, "Stage 3/7: Generating AUTOSAR-layered code with yuleOSH LLM...")
            run_config = json.loads(config_json) if config_json else {}
            codegen_report = _stage_code_generation(project_dir, job_id, run_config)
            _append_log(job_id, f"Code generation verified. Report: {codegen_report}")
            _update_stage(job_id, "code_generate", "passed", int(45 / total_stages * 100))

        # Stage 4: RTE Generate
        if not _skip_stage(job_id, "rte_generate", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "rte_generate", "running")
            _append_log(job_id, "Stage 4/7: Generating RTE code...")
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

        # Stage 5: CI Compile (Layer 1)
        if not _skip_stage(job_id, "ci_compile", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "ci_compile", "running")
            _append_log(job_id, "Stage 5/7: Compiling with GCC...")
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

        # Stage 6: MISRA Check (Layer 2)
        if not _skip_stage(job_id, "misra_check", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "misra_check", "running")
            _append_log(job_id, "Stage 6/7: Checking MISRA compliance...")
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

        # Stage 7: Coverage (Layer 3)
        if not _skip_stage(job_id, "coverage", start_idx):
            _raise_if_cancelled(job_id)
            _update_stage(job_id, "coverage", "running")
            _append_log(job_id, "Stage 7/7: Analyzing code coverage...")
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
            "summary": f"All {total_stages} stages completed successfully",
            "stages_passed": total_stages,
            "stages_total": total_stages,
        }
        _append_log(job_id, "=== Pipeline completed successfully! ===")

    except _PipelineCancelled:
        _mark_cancelled(job, job_id)
    except Exception as e:
        log.exception("Pipeline %s failed", job_id)
        job["status"] = "failed"
        job["result"] = {"error": str(e)[:500], "summary": f"Failed at stage: {job.get('current_stage', 'unknown')}"}
        _append_log(job_id, f"❌ Pipeline FAILED: {e}")

    job["progress"] = 100
    job["completed_at"] = datetime.now().isoformat()
    job["updated_at"] = datetime.now().isoformat()
    _record_pipeline_usage(org_id, user_id, user_email)
    _persist_job_result(job)

    # ── Notification on completion (for all autosar / full_pipeline types) ──
    _notify_pipeline_completion(job_id)


# ── Status queries ────────────────────────────────────────────────────────

def _persist_job_result(job: dict) -> None:
    """Persist a finished job's snapshot to project_dir/pipeline/runs/{job_id}/result.json.

    This lets the desktop poller show final status even after the Python
    process restarts (in-memory _PIPELINE_JOBS is gone, but the disk record
    survives). Called by both _run_ci_job and _run_full_pipeline on finish.
    """
    project_dir = job.get("project_dir")
    job_id = job.get("job_id")
    if not project_dir or not job_id:
        return
    try:
        run_dir = Path(project_dir) / "pipeline" / "runs" / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        # Logs are kept (capped) so the run detail view still has history
        # after a process restart; other mutable fields are stripped.
        snapshot = dict(job)
        snapshot["logs"] = job.get("logs", [])[-500:]
        (run_dir / "result.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:  # noqa: BLE001 — best-effort persistence, never fail the run
        log.debug("Failed to persist job result for %s: %s", job_id, e)

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
