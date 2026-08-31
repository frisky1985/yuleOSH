
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
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_checkpoint
        full_path = f"/api/v1/pipeline/{path_tail}"
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
        full_path = f"/api/v1/pipeline/{path_tail}"
        handler = kwargs.get("handler")
        if handler is None:
            return json_error("handler required", 500)
        result = handle_pipeline_list(handler, full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail.startswith("status/") and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        full_path = f"/api/v1/pipeline/{path_tail}"
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

    return json_error(f"Unknown pipeline resource: {path_tail}", 404)


def _run_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/run — run pipeline for a spec.

    SECURITY: resolves path safely and validates it's within project root.
    """
    spec_path = body.get("spec", "")
    name = body.get("name")

    if not spec_path:
        return json_error("'spec' is required")

    from . import OSH_HOME
    project_root = Path(OSH_HOME).resolve()
    if Path(spec_path).is_absolute():
        resolved = Path(spec_path).resolve()
    else:
        resolved = (project_root / spec_path.lstrip("/")).resolve()

    # SECURITY: path traversal guard — resolved path MUST be inside project root
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return json_error("Spec path must be within project directory", 403)

    if not resolved.exists():
        return json_error(f"Spec file not found: {resolved}")

    if not resolved.is_file():
        return json_error("Spec path is not a file", 400)

    try:
        result = subprocess.run(
            [sys.executable, "src/pipeline/run.py", str(resolved)],
            capture_output=True, text=True, timeout=300,
            cwd=os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent),
        )
        return json_ok({
            "spec": str(resolved),
            "name": name or resolved.stem,
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "session_dir": str(Path(resolved).parent / ".osh" / "sessions"),
        })
    except subprocess.TimeoutExpired:
        return json_error("Pipeline timed out after 300s", 504)
    except Exception as e:
        # SEC-C2: never echo internal exception details to the client.
        return internal_error("pipeline", e)


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
# 防止用户点 N 次重试导致 33 步流水线并发执行、sqlite 状态互相覆盖。
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
        engine = CheckpointEngine(
            pipeline_name, project_dir,
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
