# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Subprocess step executor — 方案 B2 右臂：进程级隔离执行器。

设计（B2-1）:
  - 每步在独立子进程执行（worker），结果以 JSON 回传主进程。
  - worker 复用 HandlerAdapter 包装（与 inline 同语义），不改 33 个 handler。
  - 主进程 CheckpointEngine 通过 ``runner`` 钩子（additive）接入本模块，
    不传 runner 时保持原 inline 逻辑（默认路径不变）。
  - 步骤按依赖顺序串行提交（顺序语义靠 checkpoint 状态保证），
    但每步都是独立进程臂 —— 杜绝 agent 间状态/约束污染。

用法::

    # worker（子进程入口）
    python -m yuleosh.engine.subprocess_executor worker \\
        --step-id spec-check --project-dir /path --mock

    # 主进程提交器
    from yuleosh.engine.subprocess_executor import make_subprocess_runner
    runner = make_subprocess_runner(project_dir=".", mock_mode=True)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yuleosh.engine.handler_adapter import HandlerAdapter, StepResult
from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

log = logging.getLogger("engine.subprocess_executor")


# ---------------------------------------------------------------------------
# Step resolution
# ---------------------------------------------------------------------------


def _resolve_session_dir(project_dir: str,
                         session_name: str | None) -> Path:
    """解析 session 目录（与 PipelineSession._ensure_session_dir 同路径规则）。

    主进程侧写入 artifacts.json 时使用，保证与 worker 侧
    PipelineSession.session_dir 指向同一目录。
    """
    base = Path(os.environ.get("OSH_HOME", project_dir))
    name = session_name or f"agent-pipeline-{time.strftime('%Y%m%d-%H%M%S')}"
    return base / ".osh" / "sessions" / name


def _find_step(step_id: str) -> tuple[str, str, Any]:
    """按 step_id 在 PIPELINE_STEPS 中查找，返回 (step_key, name, handler)。"""
    for step_key, agent, step_name, handler in PIPELINE_STEPS:
        if step_key == step_id:
            return step_key, step_name, handler
    raise ValueError(
        f"Step '{step_id}' not found in PIPELINE_STEPS. "
        f"Available: {[s[0] for s in PIPELINE_STEPS]}"
    )


def _make_worker_session(project_dir: str, step_def: dict,
                         mock_mode: bool = False,
                         session_name: str | None = None) -> PipelineSession:
    """在 worker 进程中构造 PipelineSession（与 agent_checkpoint._make_session_factory 同语义）。

    worker 无法跨进程传递 llm_client —— mock 模式下 worker 侧直接注入
    _mock_llm_client()（B2-1：subprocess mock 全链依赖占位 LLM 响应）；
    真实 LLM 模式需调用方注入真实 client（标注需 API key）。

    session_name 固定（B2-1）：主进程 CheckpointEngine 与所有 worker 必须
    共用同一会话目录（.osh/sessions/<name>），产物交接链（后续步骤经
    session.session_dir 读取前序产物）依赖路径一致性。若为 None，则按
    时间戳生成（单步独立调试场景）。
    """
    spec_path = step_def.get("spec_path") or str(
        Path(project_dir) / "docs/spec.md"
    )
    session = PipelineSession(
        name=session_name or f"agent-pipeline-{time.strftime('%Y%m%d-%H%M%S')}",
        spec_path=spec_path,
        llm_client=None,
    )
    session.project_dir = os.path.abspath(project_dir)
    session.mock_mode = bool(mock_mode)
    if session.mock_mode:
        # mock 全链：注入占位 LLM client（与 orchestrator.run_pipeline(mock=True)
        # 语义一致），否则 LLM 依赖步骤在 worker 里尝试真实调用。
        from yuleosh.pipeline.orchestrator import _mock_llm_client
        session.llm_client = _mock_llm_client()
    session.step_id = step_def.get("step_id")
    session.step_name = step_def.get("name")
    session.agent = step_def.get("agent", "")
    return session


# ---------------------------------------------------------------------------
# Worker entry (child process)
# ---------------------------------------------------------------------------


def worker_main(argv: list[str] | None = None) -> int:
    """子进程入口：执行单个步骤，把 StepResult JSON 打到 stdout。

    stdout 最后一行是 ``{"verdict": ..., "output_path": ..., "error": ...}``，
    主进程只解析最后一行（前面的 print 是 handler 自身的日志）。
    """
    parser = argparse.ArgumentParser(description="yuleOSH step worker")
    parser.add_argument("--step-id", required=True, help="步骤 id")
    parser.add_argument("--project-dir", default=".", help="项目目录")
    parser.add_argument("--mock", action="store_true", help="mock 模式")
    parser.add_argument("--spec-path", default=None, help="spec 路径（可选）")
    parser.add_argument("--session-name", default=None,
                        help="固定 session 名（B2-1：与主进程共用会话目录）")
    args = parser.parse_args(argv)

    step_key, step_name, handler = None, None, None
    adapter = None
    try:
        step_key, step_name, handler = _find_step(args.step_id)
        adapter = HandlerAdapter(handler, fallback_safe=False)
    except Exception as e:  # noqa: BLE001 — worker 必须回传失败而非崩溃
        payload = {"verdict": "failed", "output_path": None,
                   "error": str(e), "fallback_stamped": False}
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    step_def = {
        "step_id": step_key,
        "name": step_name,
        "agent": "",
        "spec_path": args.spec_path,
    }
    session = _make_worker_session(
        args.project_dir, step_def, mock_mode=args.mock,
        session_name=args.session_name,
    )

    # B2-产物交接：读取主进程写入的 artifacts.json 预填 session.artifacts
    # （subprocess 模式下 session 不跨进程共享，前序产物经此交接）。
    if args.session_name:
        artifacts_path = session.session_dir / "artifacts.json"
        if artifacts_path.exists():
            try:
                session.artifacts.update(
                    json.loads(artifacts_path.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load artifacts.json: %s", e)

    result: StepResult
    try:
        result = adapter(session)
    except Exception as e:  # noqa: BLE001 — worker 必须回传失败而非崩溃
        result = StepResult(verdict="failed", error=str(e))

    payload = {
        "verdict": result.verdict,
        "output_path": result.output_path,
        "error": result.error,
        "fallback_stamped": result.fallback_stamped,
    }
    # 确保 JSON 行是 stdout 最后一行
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result.verdict == "passed" else 1


# ---------------------------------------------------------------------------
# Main-process runner (subprocess submission)
# ---------------------------------------------------------------------------


def _python_executable() -> str:
    """返回当前解释器路径（保证 worker 与主进程同环境）。"""
    return sys.executable


def _run_step_in_subprocess(step_def: dict, project_dir: str,
                            mock_mode: bool, spec_path: str | None,
                            timeout_s: int = 600,
                            session_name: str | None = None,
                            artifacts: dict | None = None) -> StepResult:
    """提交单步到子进程并解析结果。

    artifacts（B2-产物交接）：前序步骤的产物注册表（step_id → output_path）。
    通过 session 目录下的 artifacts.json 传给 worker（命令行传 dict 太长）；
    worker 读取后预填 session.artifacts，真实 handler 才能读取前序产物。
    """
    cmd = [
        _python_executable(), "-m", "yuleosh.engine.subprocess_executor",
        "worker",
        "--step-id", step_def["step_id"],
        "--project-dir", project_dir,
    ]
    if mock_mode:
        cmd.append("--mock")
    if spec_path:
        cmd.extend(["--spec-path", spec_path])
    if session_name:
        cmd.extend(["--session-name", session_name])

    # 产物交接：写 artifacts.json 到 session 目录（主进程侧）
    if artifacts:
        session_dir = _resolve_session_dir(project_dir, session_name)
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "artifacts.json").write_text(
                json.dumps(artifacts, ensure_ascii=False), encoding="utf-8",
            )
        except OSError as e:
            log.warning("Failed to write artifacts.json: %s", e)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=project_dir,
            check=False,  # worker 失败通过 returncode + JSON 回传，不抛
        )
    except subprocess.TimeoutExpired:
        return StepResult(
            verdict="failed",
            error=f"step {step_def['step_id']} timed out after {timeout_s}s",
        )
    except OSError as e:
        return StepResult(verdict="failed", error=f"subprocess spawn failed: {e}")

    # stdout 最后一行是结果 JSON（handler 自身 print 在前面）
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return StepResult(
            verdict="failed",
            error=f"worker 无输出 (exit={proc.returncode}, stderr={proc.stderr[-500:]})",
        )
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        return StepResult(
            verdict="failed",
            error=f"worker 输出非 JSON: {e} (last line={lines[-1][-200:]})",
        )

    return StepResult(
        verdict=payload.get("verdict", "failed"),
        output_path=payload.get("output_path"),
        error=payload.get("error"),
        fallback_stamped=bool(payload.get("fallback_stamped", False)),
    )


def make_subprocess_runner(project_dir: str, mock_mode: bool = False,
                           spec_path: str | None = None,
                           timeout_s: int = 600,
                           session_name: str | None = None) -> Callable[[dict, dict], StepResult]:
    """构造 CheckpointEngine 可用的 runner 钩子（B2-1 additive）。

    签名：``runner(step_def, artifacts)`` —— CheckpointEngine 调用时传入
    已完成步骤的 artifacts 注册表（B2-产物交接）；主进程不直接调 handler，
    由子进程 worker 执行。

    session_name（B2-1）：固定会话名，让所有 worker 与主进程共用同一
    session 目录（产物交接链依赖路径一致）。None 时 worker 按时间戳生成。
    """
    abs_project_dir = os.path.abspath(project_dir)

    def _runner(step_def: dict, artifacts: dict | None = None) -> StepResult:
        return _run_step_in_subprocess(
            step_def, abs_project_dir, mock_mode, spec_path, timeout_s,
            session_name, artifacts,
        )

    return _runner


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="yuleOSH subprocess executor")
    sub = parser.add_subparsers(dest="command")
    worker_p = sub.add_parser("worker", help="子进程 worker 入口")
    worker_p.add_argument("--step-id", required=True)
    worker_p.add_argument("--project-dir", default=".")
    worker_p.add_argument("--mock", action="store_true")
    worker_p.add_argument("--spec-path", default=None)
    worker_p.add_argument("--session-name", default=None)
    args = parser.parse_args()

    if args.command == "worker":
        argv = ["--step-id", args.step_id,
                "--project-dir", args.project_dir]
        if args.mock:
            argv.append("--mock")
        if args.spec_path:
            argv.extend(["--spec-path", args.spec_path])
        if args.session_name:
            argv.extend(["--session-name", args.session_name])
        sys.exit(worker_main(argv))
    parser.print_help()


if __name__ == "__main__":
    main()
