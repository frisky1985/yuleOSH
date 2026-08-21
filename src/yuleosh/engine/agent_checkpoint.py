#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Agent Pipeline 的 Checkpoint 封装。

将 PIPELINE_STEPS（33 步）适配到 CheckpointEngine，
支持任意 agent step 注入 + 自动续跑。
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from yuleosh.engine.checkpoint import CheckpointEngine
from yuleosh.engine.handler_adapter import HandlerAdapter
from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

# 项目内默认 spec 路径（相对 project_dir）
_DEFAULT_SPEC_NAME = "docs/spec.md"


def _resolve_spec_path(project_dir: str, spec_path: str | None) -> str:
    """解析 spec 路径：显式传入优先，否则取项目下默认 docs/spec.md。

    不做存在性校验 —— PipelineSession 只记录路径、不要求文件存在
    （spec 缺失时由具体 handler 侧体现，session 构造永不因此失败）。
    """
    if spec_path:
        return str(Path(spec_path))
    return str(Path(project_dir) / _DEFAULT_SPEC_NAME)


def _make_session_factory(project_dir: str, spec_path: str | None,
                          mock_mode: bool = False) -> Callable[[dict], PipelineSession]:
    """构造真实 PipelineSession 的工厂（B1-2）。

    工厂接收 step_def dict（CheckpointEngine._execute_steps 透传），返回
    PipelineSession 实例：

    - name: agent-pipeline-<时间戳>（与 orchestrator 的 run-<时间戳> 同风格）
    - spec_path: 调用方传入或项目默认 docs/spec.md（不校验存在）
    - llm_client: None（B1 阶段不接 LLM，由调用方后续注入）
    - mock_mode: 由调用方控制（CLI --mock / 测试直接传参）
    - project_dir: 覆盖为调用方传入的项目目录（PipelineSession 默认取
      OSH_HOME，这里与 CheckpointEngine.project_dir 对齐）
    - step_id / step_name / agent: 附上当前 step 上下文，方便 handler 读取
    """
    resolved_spec = _resolve_spec_path(project_dir, spec_path)
    abs_project_dir = os.path.abspath(project_dir)

    def _factory(step_def: dict) -> PipelineSession:
        session = PipelineSession(
            name=f"agent-pipeline-{time.strftime('%Y%m%d-%H%M%S')}",
            spec_path=resolved_spec,
            llm_client=None,
        )
        session.project_dir = abs_project_dir
        session.mock_mode = bool(mock_mode)
        session.step_id = step_def.get("step_id")
        session.step_name = step_def.get("name")
        session.agent = step_def.get("agent", "")
        return session

    return _factory


def create_agent_pipeline(project_dir: str,
                          spec_path: str | None = None,
                          mock_mode: bool = False) -> CheckpointEngine:
    """
    创建 Agent 流水线的 Checkpoint 版本。

    与 PIPELINE_STEPS 定义严格对齐（33 步）。每个 handler 均用
    HandlerAdapter 包装（fallback_safe=False 默认 —— 异常绝不静默降质），
    并在 engine 上注入 session_factory：运行时 HandlerAdapter 分支会收到
    构造好的真实 PipelineSession（而非 SimpleNamespace）。
    """
    engine = CheckpointEngine(
        "agent-pipeline",
        project_dir,
        session_factory=_make_session_factory(project_dir, spec_path, mock_mode),
    )

    for step_key, agent, step_name, handler in PIPELINE_STEPS:
        engine.add_step(step_key, step_name, HandlerAdapter(handler), agent=agent)

    return engine


def list_injection_points(engine: CheckpointEngine | None = None,
                          project_dir: str = ".") -> None:
    """打印所有注入点（即所有步骤）。"""
    if engine is None:
        engine = create_agent_pipeline(project_dir)
    steps = engine._step_defs
    print(f"\n📌 Pipeline Injection Points ({len(steps)} steps):")
    for i, s in enumerate(steps):
        agent_tag = f"{s.get('agent', '')}: " if s.get('agent') else ""
        print(f"  Step {i+1:2d}:  {s['step_id']:22s} — {agent_tag}{s['name']}")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Agent Pipeline Checkpoint Runner")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "status", "list-steps"],
                        help="命令: run / status / list-steps")
    parser.add_argument("spec", nargs="?", default="docs/spec.md",
                        help="Spec 文件路径")
    parser.add_argument("--inject-at", help="注入点 step_id")
    parser.add_argument("--resume", action="store_true",
                        help="从 checkpoint 恢复")
    parser.add_argument("--project-dir", default=os.getcwd(),
                        help="项目目录")
    parser.add_argument("--clear", action="store_true",
                        help="清除 checkpoint 状态")
    parser.add_argument("--executor", default="inline",
                        choices=["inline", "subprocess", "local"],
                        help="执行器: inline（当前进程直跑）/ local（默认子进程，Executor 接口，EI-M1A）/ subprocess（B2 旧名，等价 local）")
    parser.add_argument("--venv", action="store_true",
                        help="项目 venv 隔离（EI-M1B）: 自动创建/复用 .osh/venvs/<project> 并安装依赖")
    parser.add_argument("--mock", action="store_true",
                        help="mock 模式（session.mock_mode=True，gate 类步骤跳过真实扫描）")
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)

    if args.clear:
        CheckpointEngine.clear_state(project_dir)
        print("✅ Checkpoint state cleared.")
        return

    if args.command == "list-steps":
        engine = create_agent_pipeline(project_dir)
        list_injection_points(engine)
        return

    if args.command == "status":
        engine = CheckpointEngine("agent-pipeline", project_dir)
        state = engine.status()
        if state is None:
            print("📭 没有 checkpoint 状态。")
            return
        print(f"\n📊 Pipeline Status: {state['status']}")
        print(f"   Pipeline: {state['pipeline_name']}")
        print(f"   Created:  {state['created_at']}")
        print(f"   Updated:  {state['updated_at']}")
        if state.get("inject_at"):
            print(f"   Inject:   {state['inject_at']}")
        print()
        for i, s in enumerate(state["steps"]):
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️",
                    "running": "🔄", "pending": "⬜"}.get(s["status"], "❓")
            dur = f" ({s['duration_s']:.1f}s)" if s["duration_s"] else ""
            err = f" — {s['error']}" if s.get("error") else ""
            print(f"  {icon} [{i+1:2d}] {s['name']}{dur}{err}")
        return

    # ── run ──
    engine = create_agent_pipeline(project_dir, args.spec, mock_mode=args.mock)
    if args.executor in ("subprocess", "local"):
        # EI-M1A: 统一走 Executor 接口（LocalExecutor = subprocess 语义）。
        # 固定 session 名（时间戳级）：主进程与所有 worker 共用同一
        # 会话目录，产物交接链依赖路径一致。
        import time as _time

        from yuleosh.engine.executor import make_executor
        session_name = f"agent-pipeline-{_time.strftime('%Y%m%d-%H%M%S')}"
        executor_kwargs = dict(
            project_dir=project_dir, mock_mode=args.mock,
            spec_path=args.spec, session_name=session_name,
        )
        if args.venv:
            # EI-M1B: 项目 venv 隔离 —— 自动创建/复用 + 安装依赖，
            # worker 用 venv python 执行（PATH/VIRTUAL_ENV 注入见 LocalExecutor）。
            from yuleosh.engine.project_venv import ensure_project_venv
            venv_dir = ensure_project_venv(project_dir)
            executor_kwargs["venv_dir"] = str(venv_dir)
        executor = make_executor("local", **executor_kwargs)
        engine.runner = executor.as_runner()
    result = engine.run(inject_at=args.inject_at, resume=args.resume)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
