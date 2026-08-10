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
from urllib.parse import parse_qs, urlparse

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

    # Portal 方案 B (2026-08-10): 消费计量归属触发用户所在组织。
    _org_id = user.get("org_id", 0) or 0

    try:
        if pipeline_type == "full" or pipeline_type == "full_pipeline":
            job_id = submit_full_pipeline(
                project_dir=str(resolved),
                config_json=config_json,
                arxml_content=arxml_content,
                org_id=_org_id,
            )
        else:
            job_id = submit_pipeline(
                project_dir=str(resolved),
                layer=layer,
                org_id=_org_id,
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


def handle_pipeline_usage(handler: BaseHTTPRequestHandler, path: str) -> dict:
    """GET /api/v1/pipeline/usage — Pipeline LLM token consumption by run.

    Portal 方案 B (2026-08-10): 扫描 ``{OSH_HOME}/.osh/sessions/*/session.json``
    聚合每次 run 的 token 消费（session.to_dict 已持久化 org_id/token_usage_*）。

    角色分层: admin 看全量; member 只看本 org（org_id 匹配）的 run。
    损坏容错: 坏 json / 缺文件跳过，不抛异常。
    """
    from yuleosh.ui.routes.tenant_routes import _require_auth
    user = _require_auth(handler)
    if not user:
        return {"ok": False, "error": "Authentication required"}
    role = user.get("role", "member") or "member"
    org_id = user.get("org_id", 0) or 0

    osh_home = Path(os.environ.get("OSH_HOME", ".")).resolve()
    sessions_root = osh_home / ".osh" / "sessions"
    runs: list[dict] = []
    total_tokens = 0
    total_calls = 0

    if sessions_root.exists():
        dirs = [p for p in sessions_root.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for sdir in dirs:
            sj = sdir / "session.json"
            if not sj.exists():
                continue
            try:
                data = json.loads(sj.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            run_org = data.get("org_id", 0) or 0
            # 角色分层: member 只看本组织 run（org_id=0 的旧 run 仅 admin 可见）
            if role != "admin" and run_org != org_id:
                continue
            tok = data.get("token_usage_total", 0) or 0
            steps = data.get("token_usage_steps", []) or []
            runs.append({
                "name": data.get("name", sdir.name),
                "status": data.get("status", "unknown"),
                "created_at": data.get("created_at", ""),
                "org_id": run_org,
                "token_total": tok,
                "llm_calls": len(steps),
                "steps": steps[-20:],
            })
            total_tokens += tok
            total_calls += len(steps)

    return {
        "ok": True,
        "runs": runs,
        "total_tokens": total_tokens,
        "total_llm_calls": total_calls,
        "role": role,
    }


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


def _scan_project_checkpoints(project_dir: str) -> list[dict]:
    """扫描单个项目目录下的全部 pipeline checkpoint 记录。

    B5.2-项目分组（2026-08-10）：从 sqlite checkpoint_state 表 + JSON 兜底
    文件扫描所有 pipeline，返回名称 + 状态 + 更新时间（列表序，新→旧）。

    只读视图，损坏容错（坏 db / 坏 json 不抛异常，返回已收集部分）。
    """
    project = Path(project_dir)
    pipelines: dict[str, dict] = {}

    # ── 1. sqlite 后端：checkpoint_state 表全量列出 ──
    try:
        import sqlite3
        db_path = project / ".yuleosh" / "checkpoint-state.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            try:
                conn.execute("PRAGMA busy_timeout=5000")
                rows = conn.execute(
                    "SELECT pipeline_name, state_json, updated_at "
                    "FROM checkpoint_state"
                ).fetchall()
                for name, state_json, updated_at in rows:
                    try:
                        state = json.loads(state_json)
                    except (json.JSONDecodeError, TypeError):
                        state = {}
                    pipelines[name] = {
                        "name": name,
                        "status": state.get("status", "unknown"),
                        "updated_at": updated_at or state.get("updated_at"),
                        "created_at": state.get("created_at"),
                        "step_count": len(state.get("steps", [])),
                        "backend": "sqlite",
                    }
            finally:
                conn.close()
    except Exception as e:  # noqa: BLE001 — 看板接口必须容错
        log.warning("pipeline list sqlite read failed (%s): %s", project_dir, e)

    # ── 2. JSON 兜底：checkpoint-state.json 单文件（agent-pipeline）──
    try:
        json_path = project / ".yuleosh" / "checkpoint-state.json"
        if json_path.exists():
            state = json.loads(json_path.read_text(encoding="utf-8"))
            name = state.get("pipeline_name", "agent-pipeline")
            if name not in pipelines:
                pipelines[name] = {
                    "name": name,
                    "status": state.get("status", "unknown"),
                    "updated_at": state.get("updated_at"),
                    "created_at": state.get("created_at"),
                    "step_count": len(state.get("steps", [])),
                    "backend": "json",
                }
    except Exception as e:  # noqa: BLE001
        log.warning("pipeline list json fallback failed (%s): %s", project_dir, e)

    # 按更新时间倒序（最新在前）
    return sorted(
        pipelines.values(),
        key=lambda p: p.get("updated_at") or "",
        reverse=True,
    )


def _iter_project_dirs(osh_home: str) -> list[Path]:
    """发现 OSH_HOME 下含 pipeline checkpoint 状态的项目目录（B5.2）。

    遍历规则：
      - OSH_HOME 本身是一个候选项目（根 .yuleosh/ 下可能有状态）
      - 子目录含 .yuleosh/checkpoint-state.db|json 的算独立项目（深度 ≤ 3）
      - 跳过 .git / node_modules / __pycache__ / .venv 等无关目录
      - 损坏/不可读目录跳过（不抛异常）
    """
    home = Path(osh_home)
    found: list[Path] = []
    if not home.exists():
        return found

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}

    def _has_checkpoint(p: Path) -> bool:
        y = p / ".yuleosh"
        return (y / "checkpoint-state.db").exists() or (y / "checkpoint-state.json").exists()

    try:
        for root, dirs, _files in os.walk(home):
            root_path = Path(root)
            try:
                rel = root_path.relative_to(home)
            except ValueError:
                rel = Path("")
            depth = len(rel.parts)

            # 剪枝：深度 > 3 的目录不再下钻；无关目录直接跳过
            dirs[:] = [d for d in dirs if d not in skip]
            if depth > 3:
                dirs[:] = []
                continue

            if _has_checkpoint(root_path):
                found.append(root_path)
    except OSError as e:  # 发现阶段容错
        log.warning("pipeline list project discovery failed: %s", e)

    return found


def handle_pipeline_list(handler: BaseHTTPRequestHandler, path: str) -> dict:
    """GET /api/v1/pipeline/list — 列出可用 pipeline（看板选择器数据源）。

    B5-看板（2026-08-10）：从 sqlite checkpoint_state 表 + JSON 兜底文件
    扫描 pipeline 记录，返回名称 + 状态 + 更新时间，供前端下拉选择。
    只读视图，401 fail-closed，损坏容错。

    B5.2-项目分组（2026-08-10）：不传 project_dir 时自动发现 OSH_HOME 下
    所有含 checkpoint 状态的项目目录，按项目分组返回（projects[]）；
    显式传 project_dir 时保持单项目视图（pipelines[] 兼容旧前端）。

    Query params:
        project_dir: 项目目录（默认自动发现 OSH_HOME 下全部项目）
    """
    parsed = urlparse(path)
    qs = parse_qs(parsed.query)
    project_dir = (qs.get("project_dir") or [None])[0]

    # Auth（与其它 pipeline 接口一致，fail-closed）
    from yuleosh.ui.routes.tenant_routes import _require_auth
    user = _require_auth(handler)
    if not user:
        return {"ok": False, "error": "Authentication required"}

    osh_home = os.environ.get("OSH_HOME", "")

    # 显式 project_dir → 单项目视图（pipelines 兼容旧前端，另附 projects 分组）
    if project_dir:
        pipes = _scan_project_checkpoints(project_dir)
        return {
            "ok": True,
            "pipelines": pipes,
            "projects": [
                {
                    "name": Path(project_dir).name or project_dir,
                    "path": str(Path(project_dir)),
                    "pipelines": pipes,
                    "count": len(pipes),
                }
            ],
            "count": len(pipes),
        }

    # 自动发现：扫 OSH_HOME 下全部项目目录
    projects: list[dict] = []
    seen: set[str] = set()
    for pdir in _iter_project_dirs(osh_home):
        try:
            pipes = _scan_project_checkpoints(str(pdir))
        except Exception as e:  # noqa: BLE001 — 单项目失败不拖垮整体
            log.warning("pipeline list project scan failed (%s): %s", pdir, e)
            continue
        if not pipes:
            continue
        key = str(pdir)
        if key in seen:
            continue
        seen.add(key)
        projects.append(
            {
                "name": pdir.name or str(pdir),
                "path": key,
                "pipelines": pipes,
                "count": len(pipes),
            }
        )

    # 全量扁平列表（按更新时间倒序）
    flat = [p for proj in projects for p in proj["pipelines"]]
    ordered = sorted(
        flat,
        key=lambda p: p.get("updated_at") or "",
        reverse=True,
    )

    return {
        "ok": True,
        "pipelines": ordered,
        "projects": projects,
        "count": len(ordered),
    }


def handle_pipeline_checkpoint(handler: BaseHTTPRequestHandler, path: str) -> dict:
    """GET /api/v1/pipeline/checkpoint — CheckpointEngine 33 步实时状态（看板数据源）。

    B3-看板（2026-08-08）：从 CheckpointEngine 持久化状态（sqlite 优先，
    JSON 兜底）读取当前/最近一次 pipeline 的步骤级状态，供前端看板渲染。
    这是只读视图 —— 状态真相源始终是 CheckpointEngine（B2-3 sqlite）。

    Query params:
        project_dir: 项目目录（默认取 OSH_HOME）
        pipeline:    指定 pipeline 名（默认 agent-pipeline-* 最新一条）
    """
    parsed = urlparse(path)
    qs = parse_qs(parsed.query)
    project_dir = (qs.get("project_dir") or [None])[0]
    pipeline_name = (qs.get("pipeline") or [None])[0]

    # Auth（与其它 pipeline 接口一致，fail-closed）
    from yuleosh.ui.routes.tenant_routes import _require_auth
    user = _require_auth(handler)
    if not user:
        return {"ok": False, "error": "Authentication required"}

    if not project_dir:
        project_dir = os.environ.get("OSH_HOME", "")

    try:
        from yuleosh.engine.checkpoint import CheckpointEngine
        engine = CheckpointEngine(
            pipeline_name or "agent-pipeline",
            project_dir or ".",
            state_backend="sqlite",
        )
        state = engine.status()
        if state is None:
            # sqlite 无记录 → 尝试 JSON 后端兜底
            engine = CheckpointEngine(
                pipeline_name or "agent-pipeline",
                project_dir or ".",
                state_backend="json",
            )
            state = engine.status()
    except Exception as e:  # noqa: BLE001 — 看板接口必须容错
        log.warning("checkpoint status read failed: %s", e)
        return {"ok": False, "error": f"Failed to read checkpoint: {e}"}

    # B5-操作状态同步：当前 pipeline 是否有控制操作（retry/resume/rerun）在跑
    try:
        from yuleosh.api import pipeline as api_pipeline
        op_active = bool(api_pipeline._ENGINE_OP_ACTIVE.get(pipeline_name or "agent-pipeline"))
    except Exception:  # noqa: BLE001 — 读不到就视为无操作，看板不崩
        op_active = False

    if state is None:
        return {"ok": True, "state": None, "steps": [], "op_active": op_active}

    steps = state.get("steps", [])
    return {
        "ok": True,
        "state": {
            "pipeline_name": state.get("pipeline_name"),
            "status": state.get("status"),
            "inject_at": state.get("inject_at"),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
        },
        "steps": steps,
        "op_active": op_active,
        "count": len(steps),
    }
