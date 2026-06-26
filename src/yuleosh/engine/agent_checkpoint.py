#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Agent Pipeline 的 Checkpoint 封装。

将 PIPELINE_STEPS（29~30 步）适配到 CheckpointEngine，
支持任意 agent step 注入 + 自动续跑。
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Optional

from yuleosh.engine.checkpoint import CheckpointEngine
from yuleosh.pipeline.step_handlers import PIPELINE_STEPS


def _make_agent_handler(step_key: str, handler_fn) -> Callable:
    """将原始 handler 包装为无参 Callable。

    测试中使用 mock 时，handler_fn 接受 (step_key, project_dir) 签名。
    生产环境使用 step session 上下文。
    """
    def _inner():
        return handler_fn()
    _inner.__name__ = f"handler_{step_key}"
    _inner.__qualname__ = f"handler_{step_key}"
    return _inner


def create_agent_pipeline(project_dir: str,
                          spec_path: Optional[str] = None) -> CheckpointEngine:
    """
    创建 Agent 流水线的 Checkpoint 版本。

    与 PIPELINE_STEPS 定义严格对齐。handler 保持原始无参签名
    （由 PIPELINE_STEPS 定义的 handler 已经是无参的 step 函数）。
    """
    engine = CheckpointEngine("agent-pipeline", project_dir)

    for step_key, agent, step_name, handler in PIPELINE_STEPS:
        engine.add_step(step_key, step_name, handler, agent=agent)

    return engine


def list_injection_points(engine: Optional[CheckpointEngine] = None,
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
    engine = create_agent_pipeline(project_dir, args.spec)
    result = engine.run(inject_at=args.inject_at, resume=args.resume)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
