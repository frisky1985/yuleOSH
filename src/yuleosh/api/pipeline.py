
# @req RS-006
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Pipeline endpoints — run, status, list, get, delete."""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from . import json_error, json_ok
from ._errors import internal_error
from .middleware import require_auth

# ── Submission throttle (P0): protect the async thread pool from DoS ──
_TRIGGER_GATE_LOCK = threading.Lock()
_TRIGGER_GATE_TIMES: list[float] = []
_TRIGGER_MAX_PER_WINDOW = 10        # max pipeline submissions per window
_TRIGGER_WINDOW_SECONDS = 60.0
_MAX_ARXML_BYTES = 1_000_000        # 1 MB
_MAX_CONFIG_JSON_BYTES = 1_000_000  # 1 MB


def _check_trigger_throttle() -> bool:
    """Return True if a new submission is allowed (sliding window)."""
    global _TRIGGER_GATE_TIMES
    now = time.time()
    with _TRIGGER_GATE_LOCK:
        _TRIGGER_GATE_TIMES = [
            t for t in _TRIGGER_GATE_TIMES if now - t < _TRIGGER_WINDOW_SECONDS
        ]
        if len(_TRIGGER_GATE_TIMES) >= _TRIGGER_MAX_PER_WINDOW:
            return False
        _TRIGGER_GATE_TIMES.append(now)
        return True


def _request_path(kwargs: dict, path_tail: str) -> str:
    """Return the request path WITH its query string.

    ``handle_pipeline`` only receives ``path_tail`` — the ``?pipeline=...``
    / ``?run_id=...`` query is dropped, while downstream handlers parse it
    via ``urlparse(path).query`` (evidence download cannot work without
    ``run_id``).  Prefer ``handler.path`` (the raw request line, query
    included) and only fall back to re-joining when there is no handler
    (bare unit-test calls).
    """
    handler = kwargs.get("handler")
    raw = getattr(handler, "path", None)
    return raw or f"/api/v1/pipeline/{path_tail}"


@require_auth
def handle_pipeline(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to pipeline sub-resources."""
    if path_tail in ("", "run"):
        if method == "POST":
            return _run_pipeline(body)
        return json_error("Use POST to run pipeline", 405)

    if path_tail == "trigger":
        if method == "POST":
            return _trigger_pipeline(body)
        return json_error("Use POST to trigger pipeline", 405)

    if path_tail == "status":
        if method == "GET":
            return _list_pipelines()
        return json_error("Use GET for status", 405)

    # B5-看板 (2026-08-10): "list" 委托到 handle_pipeline_list（看板选择器
    # 数据源，见下），不能在这里被 _list_pipelines()（sessions 视图）拦截。
    # Phase 4 覆盖率攻坚发现：真实 HTTP 请求 /api/v1/pipeline/list 曾错误
    # 返回 sessions —— 前端看板选择器拿到空列表。
    if path_tail == "" and method == "GET":
        return _list_pipelines()

    if path_tail == "steps":
        if method == "GET":
            return _list_pipeline_steps()
        return json_error("Use GET for steps", 405)

    # ── P0-B: legacy pipeline sub-routes restored ───────────────────────
    # These endpoints predate the modular router (served by
    # ui/routes/pipeline_routes via handler_helpers) and were shadowed into
    # 404/401 dead code after the router wiring.  Delegate to the same
    # legacy handlers so consumers (incl. old frontends/scripts) keep
    # working: 401 without valid auth, 200 data with auth.
    if path_tail == "runs" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs
        result = handle_pipeline_runs(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "stats" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats
        result = handle_pipeline_stats(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    # Portal 方案 B (2026-08-10): pipeline LLM 消费明细（角色分层: admin 全量 / member 本 org）
    if path_tail == "usage" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_usage
        result = handle_pipeline_usage(kwargs.get("handler"), f"/api/v1/pipeline/{path_tail}")
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "yuleasr-status" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        result = handle_yuleasr_status(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "validate" and method == "GET":
        from yuleosh.pipeline.config_validator import validate_pipeline_config
        result = validate_pipeline_config(
            project_dir=os.environ.get("OSH_HOME", ""))
        return {"ok": True, **result}, 200

    if path_tail == "checkpoint" and method == "GET":
        # B3-看板 (2026-08-08): CheckpointEngine 步骤级实时状态（看板数据源）。
        # 必须用 _request_path 保留 query：handler 通过
        # urlparse(path).query 读 project_dir / pipeline / run_id。此前这里
        # 用 f"/api/v1/pipeline/{path_tail}" 硬拼，query 被整体丢弃 →
        # project_dir 恒为 None → 回退 OSH_HOME 根目录，于是看板读到的是
        # 仓库根的 checkpoint-state.db（陈旧），而不是引擎实际写入的
        # <project_dir>/.yuleosh/checkpoint-state.db，表现为「状态不刷新」。
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint
        full_path = _request_path(kwargs, path_tail)
        result = handle_pipeline_checkpoint(kwargs.get("handler"), full_path)
        return (result, 200) if isinstance(result, dict) else result

    # ── 以下路由必须注册在 handle_pipeline 内（而不是 handler_helpers 的
    #    elif 分支）：api_v1_dispatch 对所有 /api/v1/* 路径恒返回 True，
    #    handler_helpers 里的 /api/v1/... 分支永远不会被执行（死代码）。
    #    此前 checkpoint/runs 就挂在那个死分支上，实际一直 404。 ──

    if path_tail == "checkpoint/runs" and method == "GET":
        # T4-运行历史：列出某 pipeline 的历史运行（不含快照）。
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs_history
        full_path = _request_path(kwargs, path_tail)
        result = handle_pipeline_runs_history(kwargs.get("handler"), full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "checkpoint/stream" and method == "GET":
        # T10-SSE：状态变化时才推 event，替代前端 1.5s 轮询。
        # 该处理器自行写响应（长连接），必须返回 None，否则 router 会再
        # 补写一次 JSON（router 见 None 直接 return，不写响应）。
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint_stream
        handle_pipeline_checkpoint_stream(
            kwargs.get("handler"), _request_path(kwargs, path_tail))
        return None

    if path_tail == "evidence" and method == "GET":
        # T9-证据包历史：每次运行一条（执行记录 + 产物清单）。
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_evidence
        full_path = _request_path(kwargs, path_tail)
        result = handle_pipeline_evidence(kwargs.get("handler"), full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "evidence/download" and method == "GET":
        # T9-证据包下载：自行写 zip 二进制响应，返回 None 阻止 router 补写。
        from yuleosh.ui.routes.pipeline_routes import (
            handle_pipeline_evidence_download,
        )
        handle_pipeline_evidence_download(
            kwargs.get("handler"), _request_path(kwargs, path_tail))
        return None

    if path_tail == "list" and method == "GET":
        # B5-看板 (2026-08-10): 列出可用 pipeline（选择器数据源）。
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_list
        full_path = _request_path(kwargs, path_tail)
        handler = kwargs.get("handler")
        if handler is None:
            return json_error("handler required", 500)
        result = handle_pipeline_list(handler, full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail.startswith("status/") and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        full_path = _request_path(kwargs, path_tail)
        result = handle_pipeline_status(kwargs.get("handler"), full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "yuleasr-notify" and method == "POST":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        raw = json.dumps(body).encode("utf-8") if body else b"{}"
        result = handle_yuleasr_notify(kwargs.get("handler"), raw)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "retry" and method == "POST":
        return _retry_pipeline(body)

    if path_tail == "resume" and method == "POST":
        return _resume_pipeline(body)

    if path_tail == "rerun" and method == "POST":
        return _rerun_pipeline(body)

    if path_tail == "stop" and method == "POST":
        return _stop_pipeline(body)

    if path_tail == "jobs" and method == "GET":
        return _list_orchestrator_runs()

    return json_error(f"Unknown pipeline resource: {path_tail}", 404)


# ── One-click orchestrator run (background) ──────────────────────────────────
# 后端「一键跑」走真实编排器（yuleosh.pipeline.run_pipeline），它写
# project_dir/.osh/sessions/<id>/ 全量产物，前端 artifacts 面板可直接读。
# 与 CheckpointEngine(rerun) 不同：orchestrator 提供完整 session_dir，且
# LLM 长链（~1.5–2h）放进后台线程，不阻塞 HTTP 响应。
_RUN_JOBS: dict[str, dict] = {}
_RUN_JOBS_LOCK = threading.Lock()


def _publish_orchestrator_checkpoint(project_dir: str, run_id: str, name: str,
                                     status: str, started_at: str, finished_at: str,
                                     session) -> None:
    """把编排器一次运行的结果回写为 CheckpointEngine 看板状态（打通两条链路）。

    编排器路径天然不写 checkpoint_state 表，看板读不到 24 步进度。本函数把
    orchestrator 返回的 PipelineSession.steps 映射成 CheckpointState，经
    CheckpointEngine.publish_state 同时写入 checkpoint_state（最新）+ pipeline_runs
    （历史），与 _run_engine_op（rerun/retry/resume）写入完全同源。

    session: orchestrator 返回的 PipelineSession（含 steps）；为 None（如缺失 key
        触发 SystemExit）时退化为全 pending/失败的最小快照，仍保证看板有回显。
    """
    try:
        from yuleosh.engine.checkpoint import (
            CheckpointEngine, CheckpointState, StepRecord, StepStatus,
        )
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

        _status_by_key: dict[str, str] = {}
        if session is not None:
            for _s in (getattr(session, "steps", None) or []):
                _k = _s.get("name") or _s.get("step_key")
                if _k:
                    _status_by_key[_k] = _s.get("status", "pending")

        _ok_final = (status == "completed")
        _steps: list[StepRecord] = []
        for _key, _agent, _sname, _handler in PIPELINE_STEPS:
            _raw = _status_by_key.get(_key)
            if _raw == "completed":
                _enum = StepStatus.PASSED
            elif _raw == "failed":
                _enum = StepStatus.FAILED
            elif _raw == "skipped":
                _enum = StepStatus.SKIPPED
            elif _raw == "running":
                _enum = StepStatus.RUNNING
            else:
                # 编排器未跑到该步（block/异常中断）→ 按整体状态退化
                _enum = StepStatus.PASSED if _ok_final else StepStatus.PENDING
            _steps.append(StepRecord(
                step_id=_key, name=_sname, agent=_agent, status=_enum,
                completed_at=finished_at,
            ))
        _state = CheckpointState(
            pipeline_name="agent-pipeline",
            profile="default",
            steps=_steps,
            created_at=started_at,
            updated_at=finished_at,
            status=status if status in ("completed", "failed", "stopped") else "completed",
        )
        _engine = CheckpointEngine("agent-pipeline", project_dir, state_backend="sqlite")
        _engine.publish_state(run_id, "run", "full", _state.status, started_at, finished_at, _state)
        # Realtime: 编排器 checkpoint 已落, 广播 (前端左栏徽标 + 看板数字联动)
        try:
            from yuleosh.realtime import emit_pipeline_checkpoint
            _ok_pct = {"completed": 100.0, "failed": 100.0, "stopped": 100.0}.get(
                _state.status, 0.0
            )
            emit_pipeline_checkpoint(
                run_id=run_id, project_dir=project_dir,
                status=_state.status, progress_pct=_ok_pct,
            )
            # run_done: 编排器一跑完推一帧, 给「阶段看板 + 证据包」驱动刷新
            from yuleosh.realtime import emit_pipeline_run_done
            emit_pipeline_run_done(
                run_id=run_id, project_dir=project_dir,
                status=_state.status,
                summary={"step_count": len(_steps), "name": name},
            )
        except Exception as _re:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).debug("realtime emit failed: %s", _re)
    except Exception as _e:  # noqa: BLE001 — 看板回写失败绝不影响主流程
        import logging
        logging.getLogger(__name__).warning("orchestrator checkpoint publish failed: %s", _e)


def _run_orchestrator_job(run_id: str, spec_abs: str, project_dir: str, name: str) -> None:
    """后台线程：以 OSH_HOME=project_dir 运行编排器（聚焦源码 + 产物落在项目目录）。"""
    import os as _os
    rec = _RUN_JOBS.get(run_id)
    if rec is None:
        return
    prev_home = _os.environ.get("OSH_HOME")
    _os.environ["OSH_HOME"] = project_dir
    try:
        from yuleosh.pipeline.orchestrator import run_pipeline
        rec["status"] = "running"
        rec["started_at"] = datetime.now().isoformat()
        _session = None
        try:
            # Stage-6 (2026-09-05): 把 API 侧 run_id 透传给编排器 ——
            # 使 session 目录 (.osh/sessions/<run_id>) 与 SSE 事件的 run_id
            # 与 API 记账三者一致（此前编排器自生成 uuid，目录对不上）。
            _session = run_pipeline(spec_abs, name=name, run_id=run_id)
            rec["status"] = "completed"
        except SystemExit as _e:  # run_pipeline 缺 key 会 sys.exit(1)
            rec["status"] = "failed"
            rec["error"] = f"orchestrator exited: {_e}"
        except Exception as _e:  # noqa: BLE001 — 后台任务必须兜底
            rec["status"] = "failed"
            rec["error"] = str(_e)[:500]
        finally:
            if prev_home is None:
                _os.environ.pop("OSH_HOME", None)
            else:
                _os.environ["OSH_HOME"] = prev_home
            rec["finished_at"] = datetime.now().isoformat()
        # 打通「运行过程」看板：把编排器本次运行结果回写为 checkpoint 状态，
        # 否则一键跑只在 .osh/sessions 落产物、看板读不到 24 步进度。
        # 写到看板读取的位置（prev_home = 看板侧 OSH_HOME = repo 根）。
        _publish_orchestrator_checkpoint(
            prev_home or project_dir, run_id, name,
            rec["status"], rec["started_at"], rec["finished_at"], _session,
        )
    except Exception as _e:  # noqa: BLE001
        rec["status"] = "failed"
        rec["error"] = str(_e)[:500]


def _run_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/run — 一键运行某 spec 的真实编排器（后台）。

    Body: {"spec": "<spec 路径>", "project_dir": "<项目目录>", "name": "..."}
      - spec 可为相对 OSH_HOME 的路径或绝对路径，必须落在 OSH_HOME 内（防穿越）。
      - project_dir 决定 session 与源码范围，默认取 spec 父目录的父目录
        （即 <proj>/docs/spec.md → <proj>）；必须落在 OSH_HOME 内。
    HTTP 立即返回 {"run_id","session_dir","status":"running"}，编排器在后台
    线程跑完整 24 步；产物写入 project_dir/.osh/sessions/<id>，前端
    /api/v1/artifacts/list 可直接读。
    """
    spec_path = body.get("spec") or body.get("spec_path") or ""
    if not spec_path:
        return json_error("'spec' is required")

    from . import OSH_HOME
    osh_home = Path(OSH_HOME).resolve()

    # 解析 spec（防 ../ 穿越）
    try:
        if Path(spec_path).is_absolute():
            resolved = Path(spec_path).resolve()
        else:
            resolved = (osh_home / spec_path.lstrip("/")).resolve()
        resolved.relative_to(osh_home)
    except ValueError:
        return json_error("Spec path must be within OSH_HOME", 403)

    if not resolved.exists() or not resolved.is_file():
        return json_error(f"Spec file not found: {resolved}")

    # 解析 project_dir（默认 = <proj>/docs/spec.md → <proj>；必须落在 OSH_HOME 内）
    project_dir_raw = body.get("project_dir") or str(resolved.parent.parent)
    try:
        if Path(project_dir_raw).is_absolute():
            project_dir = Path(project_dir_raw).expanduser().resolve()
        else:
            project_dir = (osh_home / project_dir_raw.lstrip("/")).resolve()
        project_dir.relative_to(osh_home)
    except ValueError:
        return json_error("project_dir must be within OSH_HOME", 403)
    if not project_dir.is_dir():
        return json_error(f"project_dir is not a directory: {project_dir}", 400)

    import uuid
    run_id = uuid.uuid4().hex[:12]
    name = body.get("name") or f"run-{run_id}"
    session_dir = project_dir / ".osh" / "sessions" / run_id

    with _RUN_JOBS_LOCK:
        _RUN_JOBS[run_id] = {
            "run_id": run_id,
            "spec": str(resolved),
            "project_dir": str(project_dir),
            "name": name,
            "session_dir": str(session_dir),
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    t = threading.Thread(
        target=_run_orchestrator_job,
        args=(run_id, str(resolved), str(project_dir), name),
        daemon=True,
        name=f"orch-run-{run_id}",
    )
    t.start()
    return json_ok({
        "run_id": run_id,
        "spec": str(resolved),
        "project_dir": str(project_dir),
        "name": name,
        "session_dir": str(session_dir),
        "status": "running",
        "note": "编排器已在后台启动；产物写入 session_dir，可用 /api/v1/artifacts/list?project=<name> 查看",
    })


def _list_orchestrator_runs() -> tuple[dict, int]:
    """GET /api/v1/pipeline/jobs — 列出后台编排器运行任务（一键跑的运行记录）。"""
    with _RUN_JOBS_LOCK:
        jobs = list(_RUN_JOBS.values())
    jobs.sort(key=lambda j: j.get("started_at") or j.get("run_id"), reverse=True)
    return json_ok({"jobs": jobs, "count": len(jobs)})


def _trigger_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/trigger — start a pipeline run.

    Security (P0):
      - requires authentication (enforced by @require_auth on handle_pipeline)
      - project_dir must resolve inside OSH_HOME (blocks ../ traversal)
      - type/layer whitelist
      - arxml_content / config_json size caps
      - sliding-window submission throttle (protects the async thread pool)
    """
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    project_dir = body.get("project_dir") or os.environ.get("OSH_HOME", "")
    if not project_dir:
        return json_error("project_dir is required or set OSH_HOME", 400)

    osh_home = Path(os.environ.get("OSH_HOME", "")).resolve()
    try:
        resolved = Path(project_dir).expanduser().resolve()
        resolved.relative_to(osh_home)
    except (ValueError, OSError):
        return json_error("project_dir must be inside OSH_HOME", 403)

    pipeline_type = body.get("type", "full")
    if pipeline_type not in ("full", "full_pipeline", "ci"):
        return json_error("type must be one of: full, ci", 400)

    layer = body.get("layer", 1)
    if layer not in (1, 2, 3):
        return json_error("layer must be 1, 2 or 3", 400)

    arxml_content = body.get("arxml_content") or ""
    if len(arxml_content) > _MAX_ARXML_BYTES:
        return json_error(f"arxml_content too large (max {_MAX_ARXML_BYTES} bytes)", 400)

    config_json = body.get("config_json")
    if config_json is not None and len(config_json) > _MAX_CONFIG_JSON_BYTES:
        return json_error(f"config_json too large (max {_MAX_CONFIG_JSON_BYTES} bytes)", 400)

    if not _check_trigger_throttle():
        return json_error(
            "Too many pipeline submissions. Try again later.", 429)

    from yuleosh.pipeline.async_runner import submit_full_pipeline, submit_pipeline

    try:
        if pipeline_type in ("full", "full_pipeline"):
            job_id = submit_full_pipeline(
                project_dir=str(resolved),
                config_json=config_json,
                arxml_content=arxml_content,
            )
        else:
            job_id = submit_pipeline(project_dir=str(resolved), layer=layer)

        return json_ok({
            "job_id": job_id,
            "status": "queued",
            "type": pipeline_type,
            "poll_url": f"/api/v1/pipeline/status/{job_id}",
        })
    except Exception as e:
        # SEC-C2: never echo internal exception details to the client.
        return internal_error("pipeline", e)


def _list_pipeline_steps() -> tuple[dict, int]:
    """GET /api/v1/pipeline/steps — list all pipeline step definitions."""
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    steps = []
    for idx, (step_key, agent, name, _handler) in enumerate(PIPELINE_STEPS, start=1):
        steps.append({
            "index": idx,
            "key": step_key,
            "agent": agent,
            "name": name,
        })

    return json_ok({
        "steps": steps,
        "count": len(steps),
    })


def _list_pipelines() -> tuple[dict, int]:
    """GET /api/v1/pipeline/status — list all pipeline sessions."""
    from yuleosh.store import Store

    from . import OSH_HOME

    store = Store()
    db_sessions = store.list_pipelines()

    # Also scan filesystem sessions
    sessions_dir = Path(OSH_HOME) / ".osh" / "sessions"
    fs_sessions = []
    if sessions_dir.exists():
        for d in sorted(sessions_dir.iterdir(), reverse=True):
            if d.is_dir():
                sess_file = d / "session.json"
                if sess_file.exists():
                    data = json.loads(sess_file.read_text())
                    fs_sessions.append(data)

    return json_ok({
        "sessions": fs_sessions,
        "count": len(fs_sessions),
    })


# ── B3-看板操作（2026-08-08）: retry / resume 异步执行器 ──────────────
# 同一 pipeline 同一时刻只允许一个控制操作（重试/续跑/全量）在跑，
# 防止用户点 N 次重试导致 24 步流水线并发执行、sqlite 状态互相覆盖。
_ENGINE_OP_LOCK = threading.Lock()
_ENGINE_OP_ACTIVE: dict[str, bool] = {}  # pipeline_name → running?


def _resolve_pipeline_ctx(body: dict) -> tuple[tuple[str, str] | None, str | None]:
    """Resolve (pipeline_name, project_dir) from request body.

    Returns ((ctx, None)) on success or ((None, error_message)) on failure.
    """
    project_dir = body.get("project_dir") or os.environ.get("OSH_HOME", "")
    if not project_dir:
        return None, "project_dir is required or set OSH_HOME"

    osh_home = Path(os.environ.get("OSH_HOME", "")).resolve()
    try:
        resolved = Path(project_dir).expanduser().resolve()
        resolved.relative_to(osh_home)
    except (ValueError, OSError):
        return None, "project_dir must be inside OSH_HOME"

    pipeline_name = body.get("pipeline") or "agent-pipeline"
    return (pipeline_name, str(resolved)), None


def _run_engine_op(pipeline_name: str, project_dir: str, op: str,
                  step_id: str = "", selected: list[str] | None = None) -> None:
    """后台线程执行 CheckpointEngine 控制操作（retry/resume/rerun）。

    状态真相源始终是 CheckpointEngine（B2-3 sqlite），本函数只负责触发
    执行并释放锁；前端看板轮询 checkpoint 接口看到状态变化。

    selected: 选中模式步骤 id 列表（retry 时若提供，则只跑这些步骤，
    其余 SKIPPED；优先级高于单点 inject_at）。
    """
    import datetime as _dt
    import uuid
    engine = None
    run_id = uuid.uuid4().hex[:12]
    started = _dt.datetime.now().isoformat()
    try:
        from yuleosh.engine.checkpoint import CheckpointEngine
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        from yuleosh.engine.handler_adapter import HandlerAdapter
        from yuleosh.engine.agent_checkpoint import _make_session_factory
        # 注入真实 PipelineSession 工厂（B1-1）：否则 handler 收到 SimpleNamespace
        # （无 spec_path 等属性），step_spec_check 访问 session.spec_path 抛
        # AttributeError，导致「运行过程」看板 rerun/retry 第一步即失败。
        # 工厂每步新建真实 session，llm_client=None 走全局真实 DeepSeek 链路，
        # 与一键跑（orchestrator）语义一致。spec_path 取默认 project_dir/docs/spec.md。
        engine = CheckpointEngine(
            pipeline_name, project_dir,
            session_factory=_make_session_factory(project_dir, None, False),
            state_backend="sqlite",
        )
        # 注册真实步骤定义（与 agent_checkpoint 一致），否则 run() 无步骤可执行，
        # rerun/resume/retry/selected 都会变成空操作。
        for step_key, agent, step_name, handler in PIPELINE_STEPS:
            engine.add_step(
                step_key, step_name,
                HandlerAdapter(handler) if handler else None,
                agent=agent,
            )
        # 记录本次运行（dashboard 看板可回看历史）
        mode = (
            "selected" if (op == "retry" and selected)
            else "inject" if op == "retry"
            else "full" if op == "rerun"
            else "resume"
        )
        engine.record_run(run_id, op, mode, selected, "running", started)
        if op == "retry":
            if selected:
                engine.run(selected=selected)
            else:
                engine.run(inject_at=step_id)
        elif op == "rerun":
            # 全量重跑：无参 run() = _prepare_full()，从头开始
            engine.run()
        else:
            engine.run(resume=True)
        final = engine.status()
        final_status = (final or {}).get("status", "unknown")
        engine.finish_run(run_id, final_status, _dt.datetime.now().isoformat(), final)
        # Realtime: 引擎路径 rerun/retry/resume 完成后广播 (前端左栏徽标 + 看板联动)
        try:
            from yuleosh.realtime import emit_pipeline_checkpoint, emit_pipeline_run_done
            _steps_done = sum(
                1 for _s in (final or {}).get("steps", [])
                if _s.get("status") in ("completed", "passed", "skipped")
            )
            _steps_total = max(1, len((final or {}).get("steps", [])))
            _pct = round(_steps_done / _steps_total * 100.0, 2)
            emit_pipeline_checkpoint(
                run_id=run_id, project_dir=project_dir,
                status=final_status, progress_pct=_pct,
            )
            emit_pipeline_run_done(
                run_id=run_id, project_dir=project_dir,
                status=final_status,
                summary={"op": op, "mode": mode, "pct": _pct},
            )
        except Exception as _re:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).debug("realtime emit failed: %s", _re)
    except Exception as e:  # noqa: BLE001 — 后台任务必须兜底，不能吞进程
        import logging
        logging.getLogger(__name__).warning(
            "pipeline %s op=%s failed: %s", pipeline_name, op, e)
        if engine is not None:
            try:
                engine.finish_run(run_id, "failed", _dt.datetime.now().isoformat())
            except Exception:
                pass
    finally:
        with _ENGINE_OP_LOCK:
            _ENGINE_OP_ACTIVE.pop(pipeline_name, None)


def _retry_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/retry — retry from a specific step OR run selected steps.

    Body (二选一):
      - {"step_id": "step-3"}            → 从 step-3 单点注入（向后兼容）
      - {"step_ids": ["step-3","step-7"]} → 仅运行选中的步骤，其余 SKIPPED
                                           （UI「勾选某几项阶段重跑」）
    """
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    step_id = body.get("step_id", "")
    step_ids = body.get("step_ids") or []
    if step_ids and not isinstance(step_ids, list):
        return json_error("step_ids must be a list of step_id strings", 400)
    if not step_id and not step_ids:
        return json_error(
            "step_id or step_ids is required (retry from a step, or run selected steps)", 400)

    ctx, err = _resolve_pipeline_ctx(body)
    if err:
        return json_error(err, 400)
    pipeline_name, project_dir = ctx

    with _ENGINE_OP_LOCK:
        if _ENGINE_OP_ACTIVE.get(pipeline_name):
            return json_error(
                f"Pipeline '{pipeline_name}' already has a control operation running", 409)
        _ENGINE_OP_ACTIVE[pipeline_name] = True

    t = threading.Thread(
        target=_run_engine_op,
        args=(pipeline_name, project_dir, "retry", step_id, step_ids),
        daemon=True,
        name=f"pipeline-retry-{pipeline_name}",
    )
    t.start()
    if step_ids:
        return json_ok({
            "status": "started",
            "op": "retry",
            "mode": "selected",
            "pipeline": pipeline_name,
            "step_ids": step_ids,
            "note": "选中模式已提交，状态变化通过 /api/v1/pipeline/checkpoint 轮询",
        })
    return json_ok({
        "status": "started",
        "op": "retry",
        "mode": "inject",
        "pipeline": pipeline_name,
        "step_id": step_id,
        "note": "状态变化通过 /api/v1/pipeline/checkpoint 轮询",
    })


def _resume_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/resume — resume from first pending/failed step."""
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    ctx, err = _resolve_pipeline_ctx(body)
    if err:
        return json_error(err, 400)
    pipeline_name, project_dir = ctx

    with _ENGINE_OP_LOCK:
        if _ENGINE_OP_ACTIVE.get(pipeline_name):
            return json_error(
                f"Pipeline '{pipeline_name}' already has a control operation running", 409)
        _ENGINE_OP_ACTIVE[pipeline_name] = True

    t = threading.Thread(
        target=_run_engine_op,
        args=(pipeline_name, project_dir, "resume"),
        daemon=True,
        name=f"pipeline-resume-{pipeline_name}",
    )
    t.start()
    return json_ok({
        "status": "started",
        "op": "resume",
        "pipeline": pipeline_name,
        "note": "状态变化通过 /api/v1/pipeline/checkpoint 轮询",
    })


def _rerun_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/rerun — 全量重跑（从头开始，_prepare_full）。

    与 retry/resume 共用同一异步执行器 + 并发锁；无参 engine.run()
    即走 _prepare_full() 全量模式（B4-看板「从头重跑」按钮）。
    """
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    ctx, err = _resolve_pipeline_ctx(body)
    if err or ctx is None:
        return json_error(err or "Failed to resolve pipeline context", 400)
    pipeline_name, project_dir = ctx

    with _ENGINE_OP_LOCK:
        if _ENGINE_OP_ACTIVE.get(pipeline_name):
            return json_error(
                f"Pipeline '{pipeline_name}' already has a control operation running", 409)
        _ENGINE_OP_ACTIVE[pipeline_name] = True

    t = threading.Thread(
        target=_run_engine_op,
        args=(pipeline_name, project_dir, "rerun"),
        daemon=True,
        name=f"pipeline-rerun-{pipeline_name}",
    )
    t.start()
    return json_ok({
        "status": "started",
        "op": "rerun",
        "pipeline": pipeline_name,
        "note": "全量重跑已提交，状态变化通过 /api/v1/pipeline/checkpoint 轮询",
    })


def _stop_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/stop — 请求停止当前运行（步骤边界生效）。

    B4-停止语义（方案 B1）：同步执行器无暂停原语，停止 = 写停止标志，
    引擎在步骤边界检查，当前步骤结束后不再执行后续步骤；剩余步骤保持
    PENDING，之后可 resume 续跑。本请求是瞬时的（只写标志文件），
    不需要后台线程；若当前没有运行中的 pipeline，幂等返回 ok。
    """
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    ctx, err = _resolve_pipeline_ctx(body)
    if err or ctx is None:
        return json_error(err or "Failed to resolve pipeline context", 400)
    pipeline_name, project_dir = ctx

    try:
        from yuleosh.engine.checkpoint import CheckpointEngine
        engine = CheckpointEngine(
            pipeline_name, project_dir,
            state_backend="sqlite",
        )
        engine.request_stop()
    except Exception as e:  # noqa: BLE001 — 内部异常不外泄细节
        return internal_error("pipeline", e)

    return json_ok({
        "status": "stopping",
        "op": "stop",
        "pipeline": pipeline_name,
        "note": "停止请求已记录，当前步骤结束后生效；剩余步骤可 resume 续跑",
    })
