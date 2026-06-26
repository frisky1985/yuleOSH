#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Checkpoint Pipeline Engine — 支持任意点注入 + 自动续跑的通用流水线引擎。

支持三种运行模式：
  1. 全量模式：从头到尾执行所有步骤
  2. 注入模式：从指定步骤开始执行（skip 之前的步骤）
  3. 恢复模式：从上一次中断/失败的步骤继续执行

用法示例::

    engine = CheckpointEngine("my-pipeline", project_dir=".")
    engine.add_step("step-1", "第一步", handler_fn, agent="小明")
    engine.add_step("step-2", "第二步", handler_fn, agent="小克")
    engine.run(inject_at="step-2")   # 从第二步开始
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("engine.checkpoint")


# ---------------------------------------------------------------------------
# Enums / Records
# ---------------------------------------------------------------------------


class StepStatus(str, Enum):
    """单个步骤的状态。"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"   # injection point 之前的步骤


@dataclass
class StepRecord:
    """单个步骤的执行记录。"""
    step_id: str
    name: str
    agent: str = ""
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_s: float = 0.0
    error: Optional[str] = None
    output_path: Optional[str] = None


@dataclass
class CheckpointState:
    """流水线的完整 checkpoint 状态。"""
    pipeline_name: str
    profile: str = "default"
    steps: list[StepRecord] = field(default_factory=list)
    inject_at: Optional[str] = None   # 注入点
    created_at: str = ""
    updated_at: str = ""
    status: str = "created"  # created | running | completed | failed

    def to_dict(self) -> dict:
        return {
            "pipeline_name": self.pipeline_name,
            "profile": self.profile,
            "inject_at": self.inject_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.name,
                    "agent": s.agent,
                    "status": s.status.value,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                    "duration_s": s.duration_s,
                    "error": s.error,
                    "output_path": s.output_path,
                }
                for s in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CheckpointState":
        steps = []
        for s_data in data.get("steps", []):
            s = StepRecord(
                step_id=s_data["step_id"],
                name=s_data.get("name", ""),
                agent=s_data.get("agent", ""),
                status=StepStatus(s_data.get("status", "pending")),
                started_at=s_data.get("started_at"),
                completed_at=s_data.get("completed_at"),
                duration_s=s_data.get("duration_s", 0.0),
                error=s_data.get("error"),
                output_path=s_data.get("output_path"),
            )
            steps.append(s)
        return cls(
            pipeline_name=data.get("pipeline_name", ""),
            profile=data.get("profile", "default"),
            inject_at=data.get("inject_at"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=data.get("status", "created"),
            steps=steps,
        )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CheckpointEngine:
    """
    流水线引擎，支持全量/注入/恢复三种模式。

    使用方式::

        engine = CheckpointEngine("my-pipeline", project_dir=".")
        engine.add_step("step-1", "第一步", handler_fn, agent="小明")
        engine.add_step("step-2", "第二步", handler_fn, agent="小克")
        engine.run(inject_at="step-2")  # 从第二步开始
    """

    STATE_FILENAME = ".yuleosh/checkpoint-state.json"

    def __init__(self, pipeline_name: str, project_dir: str = "."):
        self.pipeline_name = pipeline_name
        self.project_dir = os.path.abspath(project_dir)
        self._step_defs: list[dict[str, Any]] = []  # [{step_id, name, handler, agent}]
        self._state: Optional[CheckpointState] = None
        self._state_path = Path(self.project_dir) / self.STATE_FILENAME

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_step(self, step_id: str, name: str, handler: Optional[Callable],
                 agent: str = "") -> None:
        """注册一个流水线步骤。"""
        self._step_defs.append({
            "step_id": step_id,
            "name": name,
            "handler": handler,
            "agent": agent,
        })

    def get_step_ids(self) -> list[str]:
        """返回所有已注册的步骤 ID（按注册顺序）。"""
        return [s["step_id"] for s in self._step_defs]

    def find_step_index(self, step_id: str) -> int:
        """按 step_id 查找 index。找不到时抛出 ValueError。"""
        for i, s in enumerate(self._step_defs):
            if s["step_id"] == step_id:
                return i
        raise ValueError(
            f"Step '{step_id}' not found. Available: {self.get_step_ids()}"
        )

    # ------------------------------------------------------------------
    # Public run / status
    # ------------------------------------------------------------------

    def run(self, inject_at: Optional[str] = None,
            resume: bool = False) -> bool:
        """
        运行流水线。

        Args:
            inject_at: 注入点 step_id。从此步骤开始执行，之前步骤标记为 SKIPPED。
            resume: 从上次中断位置继续（读取存储的状态）。

        Returns:
            True 表示全部步骤通过，False 表示有步骤失败。
        """
        steps_to_run: list[dict] = []
        start_idx = 0

        # ---- 确定模式 ----
        if resume:
            steps_to_run, start_idx = self._prepare_resume()
        elif inject_at:
            steps_to_run, start_idx = self._prepare_inject(inject_at)
        else:
            steps_to_run, start_idx = self._prepare_full()

        # ---- 无步骤可执行（空引擎或全部已完成的情况） ----
        if not steps_to_run:
            # 注入点不存在时 _prepare_inject 设置了 state.status=failed
            if self._state and self._state.status == "failed":
                return False
            return True

        # ---- 执行剩余的步骤 ----
        self._save_state()
        all_passed = self._execute_steps(steps_to_run)

        # ---- 写入最终状态 ----
        self._finalize(all_passed, inject_at, resume, start_idx)
        return all_passed

    def status(self) -> Optional[dict]:
        """读取持久化的 checkpoint 状态（只读）。"""
        state = self._load_state()
        if not state:
            return None
        return state.to_dict()

    @staticmethod
    def clear_state(project_dir: str = ".") -> None:
        """清除 checkpoint 状态文件。"""
        path = Path(project_dir) / CheckpointEngine.STATE_FILENAME
        if path.exists():
            path.unlink()
            log.info("Cleared checkpoint state at %s", path)

    # ------------------------------------------------------------------
    # Internal: mode preparation
    # ------------------------------------------------------------------

    def _prepare_resume(self) -> tuple[list[dict], int]:
        """恢复模式：从上次中断/失败的步骤继续。"""
        previous = self._load_state()
        if not previous:
            print("⚠️  没有找到上次的 checkpoint，将执行全量流水线。")
            state = CheckpointState(
                pipeline_name=self.pipeline_name,
                created_at=datetime.now().isoformat(),
                status="running",
            )
            for s in self._step_defs:
                state.steps.append(StepRecord(
                    step_id=s["step_id"],
                    name=s["name"],
                    agent=s.get("agent", ""),
                    status=StepStatus.PENDING,
                ))
            self._state = state
            return self._step_defs, 0

        # 找到第一个 pending 或 failed 的步骤
        start_idx = -1
        for i, rec in enumerate(previous.steps):
            if rec.status in (StepStatus.PENDING, StepStatus.FAILED):
                start_idx = i
                break

        if start_idx == -1:
            print("✅ 所有步骤已完成，无需续跑。")
            # 保留已有 state 以便 status() 可读
            self._state = previous
            return [], start_idx

        # 重建 state
        self._state = previous
        steps_to_run = self._step_defs[start_idx:]
        print(f"🔄 从步骤 '{self._step_defs[start_idx]['step_id']}' 继续"
              f" ({start_idx + 1}/{len(self._step_defs)})")
        return steps_to_run, start_idx

    def _prepare_inject(self, inject_at: str) -> tuple[list[dict], int]:
        """注入模式：从指定步骤开始，之前的标记为 SKIPPED。"""
        try:
            start_idx = self.find_step_index(inject_at)
        except ValueError as e:
            print(f"❌ {e}")
            # 设置一个空的 state 以避免后续 _save_state() 崩溃
            self._state = CheckpointState(
                pipeline_name=self.pipeline_name,
                inject_at=inject_at,
                created_at=datetime.now().isoformat(),
                status="failed",
                steps=[
                    StepRecord(
                        step_id=s["step_id"],
                        name=s["name"],
                        agent=s.get("agent", ""),
                        status=StepStatus.FAILED,
                        error=f"Injection point '{inject_at}' not found",
                    )
                    for s in self._step_defs
                ],
            )
            return [], -1

        state = CheckpointState(
            pipeline_name=self.pipeline_name,
            inject_at=inject_at,
            created_at=datetime.now().isoformat(),
            status="running",
        )
        for i in range(len(self._step_defs)):
            if i < start_idx:
                state.steps.append(StepRecord(
                    step_id=self._step_defs[i]["step_id"],
                    name=self._step_defs[i]["name"],
                    agent=self._step_defs[i]["agent"],
                    status=StepStatus.SKIPPED,
                ))
            else:
                state.steps.append(StepRecord(
                    step_id=self._step_defs[i]["step_id"],
                    name=self._step_defs[i]["name"],
                    agent=self._step_defs[i]["agent"],
                    status=StepStatus.PENDING,
                ))
        self._state = state
        steps_to_run = self._step_defs[start_idx:]
        print(f"🎯 注入点: '{inject_at}' ({start_idx + 1}/{len(self._step_defs)})")
        print(f"   已跳过 {start_idx} 个步骤")
        return steps_to_run, start_idx

    def _prepare_full(self) -> tuple[list[dict], int]:
        """全量模式：从头开始。"""
        state = CheckpointState(
            pipeline_name=self.pipeline_name,
            created_at=datetime.now().isoformat(),
            status="running",
        )
        for s in self._step_defs:
            state.steps.append(StepRecord(
                step_id=s["step_id"],
                name=s["name"],
                agent=s["agent"],
                status=StepStatus.PENDING,
            ))
        self._state = state
        print(f"🚀 全量模式 — {len(self._step_defs)} 个步骤")
        if not self._step_defs:
            # 空引擎 — 返回空列表以避免 _save_state 崩溃
            self._state = CheckpointState(
                pipeline_name=self.pipeline_name,
                created_at=datetime.now().isoformat(),
                status="completed",
            )
            return [], 0
        return self._step_defs, 0

    # ------------------------------------------------------------------
    # Internal: execution
    # ------------------------------------------------------------------

    def _execute_steps(self, steps_to_run: list[dict]) -> bool:
        """依次执行步骤列表，返回是否全部通过。"""
        all_passed = True

        for i, step_def in enumerate(steps_to_run):
            abs_idx = self.find_step_index(step_def["step_id"])
            record = self._state.steps[abs_idx]

            record.status = StepStatus.RUNNING
            record.started_at = datetime.now().isoformat()
            self._save_state()

            agent_tag = f"{step_def.get('agent', '')}: " if step_def.get('agent') else ""
            print(f"\n  [{abs_idx + 1}/{len(self._step_defs)}] {agent_tag}{step_def['name']}")

            t0 = datetime.now()
            handler = step_def.get("handler")
            if handler is None:
                # 没有 handler — 以模拟通过测试场景时自动标记为 PASSED
                # (agent_checkpoint 的 handler 由外部注入)
                record.status = StepStatus.PASSED
                record.completed_at = datetime.now().isoformat()
                record.duration_s = (datetime.now() - t0).total_seconds()
                self._save_state()
                print(f"    ⏭️  (no handler — marked passed)")
                continue

            try:
                t0 = datetime.now()
                output_path = handler()
                t1 = datetime.now()

                record.status = StepStatus.PASSED
                record.completed_at = datetime.now().isoformat()
                record.duration_s = (t1 - t0).total_seconds()
                record.output_path = str(output_path) if output_path else None
                self._save_state()

                print(f"    ✅ 通过 ({record.duration_s:.1f}s)")

            except Exception as e:
                t1 = datetime.now()
                record.status = StepStatus.FAILED
                record.completed_at = datetime.now().isoformat()
                record.duration_s = (t1 - t0).total_seconds()
                record.error = str(e)
                self._save_state()

                print(f"    ❌ 失败: {e}")
                all_passed = False
                break

        return all_passed

    def _finalize(self, all_passed: bool, inject_at: Optional[str],
                  resume: bool, start_idx: int) -> None:
        """写入最终状态并打印摘要。"""
        self._state.status = "completed" if all_passed else "failed"
        self._state.updated_at = datetime.now().isoformat()
        self._save_state()

        # 摘要
        passed = sum(1 for s in self._state.steps if s.status == StepStatus.PASSED)
        skipped = sum(1 for s in self._state.steps if s.status == StepStatus.SKIPPED)
        failed = sum(1 for s in self._state.steps if s.status == StepStatus.FAILED)
        total = len(self._state.steps)

        print(f"\n{'=' * 50}")
        print(f"流水线: {'✅ ALL PASSED 🎉' if all_passed else '❌ FAILED'}")
        print(f"  总步骤: {total}")
        print(f"  通过:   {passed}")
        print(f"  跳过:   {skipped}")
        print(f"  失败:   {failed}")
        if inject_at:
            print(f"  注入点: {inject_at}")
        if resume and start_idx > 0:
            print(f"  恢复点: 步骤 {start_idx + 1}")

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def _load_state(self) -> Optional[CheckpointState]:
        if not self._state_path.exists():
            return None
        try:
            with open(self._state_path) as f:
                return CheckpointState.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log.warning("Corrupted checkpoint state file: %s (%s)", self._state_path, e)
            return None
