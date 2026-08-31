#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from yuleosh.engine.handler_adapter import HandlerAdapter

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
    started_at: str | None = None
    completed_at: str | None = None
    duration_s: float = 0.0
    error: str | None = None
    output_path: str | None = None


@dataclass
class CheckpointState:
    """流水线的完整 checkpoint 状态。"""
    pipeline_name: str
    profile: str = "default"
    steps: list[StepRecord] = field(default_factory=list)
    inject_at: str | None = None   # 注入点
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
    def from_dict(cls, data: dict) -> CheckpointState:
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
    STOP_FLAG_FILENAME = ".yuleosh/checkpoint-stop.flag"

    def __init__(self, pipeline_name: str, project_dir: str = ".",
                 session_factory: Callable | None = None,
                 runner: Callable | None = None,
                 state_backend: str = "json"):
        """
        Args:
            pipeline_name: 流水线名称。
            project_dir: 项目目录（checkpoint 状态文件所在位置）。
            session_factory: 可选。接收 step_def dict、返回 session 对象的工厂
                （B1-1，additive）。提供时，HandlerAdapter 分支用它构造真实
                session（如 PipelineSession）；为 None 时保持原有
                SimpleNamespace 行为（旧用例不碎）。
            runner: 可选。接收 step_def dict、返回 StepResult 的执行器钩子
                （B2-1，additive）。提供时（如 subprocess runner），步骤在
                执行器侧运行，本进程不再直接调 handler；为 None 时保持
                原有内联逻辑（默认路径不变）。
            state_backend: 状态持久化后端（B2-3，additive）。
                "json"（默认，保持 .yuleosh/checkpoint-state.json 行为不变）
                或 "sqlite"（WAL + busy_timeout + connection-per-call，
                多进程并发写不损坏）。
        """
        self.pipeline_name = pipeline_name
        self.project_dir = os.path.abspath(project_dir)
        self.session_factory = session_factory
        self.runner = runner
        self.state_backend = state_backend
        self._step_defs: list[dict[str, Any]] = []  # [{step_id, name, handler, agent}]
        self._state: CheckpointState | None = None
        self._stop_triggered = False
        self._state_path = Path(self.project_dir) / self.STATE_FILENAME
        self._state_db_path = Path(self.project_dir) / ".yuleosh/checkpoint-state.db"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_step(self, step_id: str, name: str, handler: Callable | None,
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
    # Stop control (B4-看板停止语义, 2026-08-10)
    # ------------------------------------------------------------------
    # 同步执行器没有"暂停"原语；B1「停止」语义 = 步骤边界检查停止标志：
    #   1. API 写 checkpoint-stop.flag（request_stop）
    #   2. _execute_steps 每步开始前检查标志，发现则不再执行后续步骤
    #   3. 剩余步骤保持 PENDING（不标 SKIPPED），之后可 resume 续跑
    #   4. state.status = "stopped"（新增终态，看板显示 ⏹）

    def request_stop(self) -> None:
        """请求停止当前运行（写停止标志文件，幂等）。"""
        flag = Path(self.project_dir) / self.STOP_FLAG_FILENAME
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        log.info("stop requested for %s (%s)", self.pipeline_name, flag)

    def clear_stop(self) -> None:
        """清除停止标志（新运行开始时调用，防残留）。"""
        flag = Path(self.project_dir) / self.STOP_FLAG_FILENAME
        try:
            if flag.exists():
                flag.unlink()
                log.info("cleared stop flag for %s", self.pipeline_name)
        except OSError as e:  # 清标志失败不阻塞运行
            log.warning("clear stop flag failed: %s", e)

    def stop_requested(self) -> bool:
        """停止标志是否存在（步骤边界检查）。"""
        return (Path(self.project_dir) / self.STOP_FLAG_FILENAME).exists()

    # ------------------------------------------------------------------
    # Public run / status
    # ------------------------------------------------------------------

    def run(self, inject_at: str | None = None,
            resume: bool = False,
            selected: list[str] | None = None) -> bool:
        """
        运行流水线。

        Args:
            inject_at: 注入点 step_id。从此步骤开始执行，之前步骤标记为 SKIPPED。
            resume: 从上次中断位置继续（读取存储的状态）。
            selected: 仅运行指定的步骤 id 列表（如 ["step-3", "step-7"]），
                列表外的步骤标记为 SKIPPED。优先级高于 resume/inject_at。
                用于 UI「勾选某几项阶段重跑」。

        Returns:
            True 表示全部步骤通过，False 表示有步骤失败或用户请求停止。
        """
        # 新运行开始时清除上一次可能残留的停止标志（幂等）
        self.clear_stop()
        self._stop_triggered = False

        steps_to_run: list[dict] = []
        start_idx = 0

        # ---- 确定模式 ----
        if selected:
            steps_to_run, start_idx = self._prepare_selected(selected)
        elif resume:
            steps_to_run, start_idx = self._prepare_resume()
        elif inject_at:
            steps_to_run, start_idx = self._prepare_inject(inject_at)
        else:
            steps_to_run, start_idx = self._prepare_full()

        # ---- 无步骤可执行（空引擎或全部已完成的情况） ----
        if not steps_to_run:
            # 注入点不存在时 _prepare_inject 设置了 state.status=failed
            return not (self._state and self._state.status == "failed")

        # ---- 执行剩余的步骤 ----
        self._save_state()
        all_passed = self._execute_steps(steps_to_run)

        # ---- 用户请求停止：保持剩余 PENDING，状态标 stopped（可 resume）----
        if self._stop_triggered and self._state is not None:
            self._state.status = "stopped"
            self._state.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_state()
            # 停止已生效，清除标志（下次 run/resume 从干净状态开始）
            self.clear_stop()
            print("⏹ 已按请求停止（剩余步骤保持待执行，可 resume 续跑）")
            return False

        # ---- 写入最终状态 ----
        self._finalize(all_passed, inject_at, resume, start_idx)
        return all_passed

    def status(self) -> dict | None:
        """读取持久化的 checkpoint 状态（只读）。"""
        state = self._load_state()
        if not state:
            return None
        return state.to_dict()

    @staticmethod
    def clear_state(project_dir: str = ".", backend: str = "json") -> None:
        """清除 checkpoint 状态（json 或 sqlite，B2-3）。

        Args:
            project_dir: 项目目录。
            backend: "json"（默认，删 checkpoint-state.json）
                    或 "sqlite"（清 checkpoint-state.db 表）。
        """
        if backend == "sqlite":
            import sqlite3
            db_path = Path(project_dir) / ".yuleosh/checkpoint-state.db"
            if db_path.exists():
                try:
                    conn = sqlite3.connect(str(db_path), timeout=10.0)
                    conn.execute("PRAGMA busy_timeout=10000")
                    conn.execute("DELETE FROM checkpoint_state")
                    conn.commit()
                    conn.close()
                    log.info("Cleared sqlite checkpoint state at %s", db_path)
                except sqlite3.Error as e:
                    log.warning("Failed to clear sqlite checkpoint state: %s", e)
            return
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

    def _prepare_selected(self, step_ids: list[str]) -> tuple[list[dict], int]:
        """选中模式：仅执行 step_ids 中的步骤，其余标记为 SKIPPED。

        用于 UI「勾选某几项阶段重跑」。step_ids 必须都是合法 step_id，
        任一不存在即抛 ValueError（与 find_step_index 行为一致）。
        """
        selected_set = set(step_ids or [])
        if not selected_set:
            # 空列表视为全量（不跳过任何步骤）
            return self._prepare_full()
        for sid in selected_set:
            self.find_step_index(sid)  # 非法 step_id → ValueError

        state = CheckpointState(
            pipeline_name=self.pipeline_name,
            inject_at=None,
            created_at=datetime.now().isoformat(),
            status="running",
        )
        for s in self._step_defs:
            if s["step_id"] in selected_set:
                state.steps.append(StepRecord(
                    step_id=s["step_id"],
                    name=s["name"],
                    agent=s.get("agent", ""),
                    status=StepStatus.PENDING,
                ))
            else:
                state.steps.append(StepRecord(
                    step_id=s["step_id"],
                    name=s["name"],
                    agent=s.get("agent", ""),
                    status=StepStatus.SKIPPED,
                ))
        self._state = state
        steps_to_run = [s for s in self._step_defs if s["step_id"] in selected_set]
        print(f"🎯 选中模式: 仅运行 {len(steps_to_run)}/{len(self._step_defs)} 个步骤")
        return steps_to_run, 0

    # ------------------------------------------------------------------
    # Internal: execution
    # ------------------------------------------------------------------

    def _execute_steps(self, steps_to_run: list[dict]) -> bool:
        """依次执行步骤列表，返回是否全部通过。"""
        all_passed = True

        for i, step_def in enumerate(steps_to_run):
            # B4-停止语义：步骤边界检查停止标志（用户点 ⏹ 停止后不再执行后续步骤）
            if self.stop_requested():
                self._stop_triggered = True
                print("⏹ 检测到停止请求，不再执行后续步骤")
                break

            abs_idx = self.find_step_index(step_def["step_id"])
            record = self._state.steps[abs_idx]

            record.status = StepStatus.RUNNING
            record.started_at = datetime.now().isoformat()
            self._save_state()

            agent_tag = f"{step_def.get('agent', '')}: " if step_def.get('agent') else ""
            print(f"\n  [{abs_idx + 1}/{len(self._step_defs)}] {agent_tag}{step_def['name']}")

            t0 = datetime.now()
            handler = step_def.get("handler")
            if self.runner is not None:
                # B2-1: runner 模式下，步骤一律由 runner 执行（即使 handler 为
                # None —— runner 侧根据 step_id 解析真实 handler）。
                pass
            elif handler is None:
                # 没有 handler — 以模拟通过测试场景时自动标记为 PASSED
                # (agent_checkpoint 的 handler 由外部注入)
                record.status = StepStatus.PASSED
                record.completed_at = datetime.now().isoformat()
                record.duration_s = (datetime.now() - t0).total_seconds()
                self._save_state()
                print("    ⏭️  (no handler — marked passed)")
                continue

            try:
                t0 = datetime.now()
                if self.runner is not None:
                    # B2-1: 外部执行器（如 subprocess）——步骤在独立进程臂运行，
                    # 结果以 StepResult 回传；主进程不直接调 handler。
                    # B2-产物交接：把已完成步骤的 artifacts 注册表（step_id →
                    # output_path）传给 runner，供 worker 预填 session.artifacts
                    # （subprocess 模式下 session 不跨进程共享，前序产物必须
                    # 通过显式注册表交接）。
                    artifacts = self._completed_artifacts()
                    result = self.runner(step_def, artifacts)
                    output_path = result.output_path
                    if result.verdict == "failed":
                        raise RuntimeError(
                            result.error or f"step '{step_def['step_id']}' failed"
                        )
                    if result.verdict == "warn":
                        log.warning(
                            "step %s returned warn: %s",
                            step_def["step_id"], result.error,
                        )
                elif isinstance(handler, HandlerAdapter):
                    # 适配层：真实 pipeline handler 均为 session 风格（handler(session)）
                    if self.session_factory is not None:
                        # B1-1: 注入真实 session（如 PipelineSession）。
                        # 工厂接收 step_def dict，返回 session 或任意对象。
                        session = self.session_factory(step_def)
                    else:
                        # 默认行为（additive 红线）：不传 session_factory 时
                        # 保持原有 SimpleNamespace 兼容路径。
                        session = SimpleNamespace(
                            step_id=step_def.get("step_id"),
                            name=step_def.get("name"),
                            agent=step_def.get("agent", ""),
                            project_dir=self.project_dir,
                        )
                    output_path = handler(session).output_path
                    # B1-1 增强：注册产物到 session（对齐 orchestrator 的
                    # set_artifact 交接语义——真实 handler 依赖
                    # session.artifacts 读取前序步骤产物）。SimpleNamespace
                    # 无 set_artifact，自动跳过（additive 兼容）。
                    if (
                        output_path
                        and hasattr(session, "set_artifact")
                        and callable(session.set_artifact)
                    ):
                        try:
                            session.set_artifact(
                                step_def.get("step_id"), str(output_path)
                            )
                        except Exception as e:  # noqa: BLE001
                            log.warning(
                                "set_artifact failed for %s: %s",
                                step_def.get("step_id"), e,
                            )
                else:
                    # 旧语义：无参 handler() 保持兼容（此处 handler 非 None：
                    # 前面的 `elif handler is None` 已拦截并 continue）
                    output_path = handler()  # type: ignore[union-attr]
                t1 = datetime.now()

                # B2-2: 产物一致性门禁 —— 步骤声称完成时必须产出真实文件。
                # 缺失 / 空文件 → 该步 FAILED（error 含 artifact），不再静默 PASS。
                # output_path 为 None 的步骤（无产物步骤，如纯 gate）不强制。
                if output_path:
                    _artifact_path = Path(str(output_path))
                    if not _artifact_path.exists():
                        raise RuntimeError(
                            f"artifact consistency: output_path '{output_path}' "
                            f"does not exist (step {step_def['step_id']})"
                        )
                    if _artifact_path.stat().st_size == 0:
                        raise RuntimeError(
                            f"artifact consistency: output_path '{output_path}' "
                            f"is empty (step {step_def['step_id']})"
                        )

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

    def _completed_artifacts(self) -> dict[str, str]:
        """构建已完成步骤的 artifacts 注册表（step_id → output_path）。

        B2-产物交接：runner 模式（subprocess）下 session 不跨进程共享，
        前序步骤产物必须通过显式注册表传给 worker，worker 预填
        session.artifacts 后真实 handler 才能读取（如 development-review 读
        development-plan 产物）。仅包含 PASSED 且有 output_path 的步骤。
        """
        artifacts: dict[str, str] = {}
        if not self._state:
            return artifacts
        for rec in self._state.steps:
            if rec.status == StepStatus.PASSED and rec.output_path:
                artifacts[rec.step_id] = rec.output_path
        return artifacts

    def _finalize(self, all_passed: bool, inject_at: str | None,
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
        """持久化当前状态到所选后端（json 默认 / sqlite opt-in，B2-3）。"""
        if self.state_backend == "sqlite":
            self._save_state_sqlite()
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_path, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2)

    def _load_state(self) -> CheckpointState | None:
        """从所选后端读取状态（json 默认 / sqlite opt-in，B2-3）。"""
        if self.state_backend == "sqlite":
            return self._load_state_sqlite()
        if not self._state_path.exists():
            return None
        try:
            with open(self._state_path) as f:
                return CheckpointState.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log.warning("Corrupted checkpoint state file: %s (%s)", self._state_path, e)
            return None

    # -- sqlite backend (B2-3) ----------------------------------------

    def _sqlite_conn(self):
        """创建 sqlite 连接：WAL + busy_timeout + connection-per-call。

        每个调用独立连接（不跨调用持有），多进程并发写同一 db 时
        busy_timeout 让写者等待锁而不是抛 'database is locked'。
        """
        import sqlite3
        self._state_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._state_db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row  # 行可按列名取，便于 dict(row)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _save_state_sqlite(self) -> None:
        import sqlite3
        if self._state is None:
            return
        conn = self._sqlite_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoint_state (
                    pipeline_name TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    op TEXT,
                    mode TEXT,
                    selected_steps TEXT,
                    status TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    snapshot TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO checkpoint_state "
                "(pipeline_name, state_json, updated_at) VALUES (?, ?, ?)",
                (
                    self.pipeline_name,
                    json.dumps(self._state.to_dict(), ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        except sqlite3.Error as e:
            log.warning("sqlite checkpoint save failed: %s", e)
        finally:
            conn.close()

    def _load_state_sqlite(self) -> CheckpointState | None:
        import sqlite3
        conn = self._sqlite_conn()
        try:
            cur = conn.execute(
                "SELECT state_json FROM checkpoint_state WHERE pipeline_name=?",
                (self.pipeline_name,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return CheckpointState.from_dict(json.loads(row[0]))
        except (sqlite3.Error, json.JSONDecodeError, KeyError,
                TypeError, ValueError) as e:
            log.warning("Corrupted sqlite checkpoint state: %s", e)
            return None
        finally:
            conn.close()

    # -- run history (dashboard 看板 → 多次运行回看) --------------------

    def record_run(self, run_id: str, op: str, mode: str | None,
                   selected_steps: list[str] | None, status: str, started_at: str) -> None:
        """Insert a pipeline run record with running status."""
        conn = self._sqlite_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY, op TEXT, mode TEXT,
                    selected_steps TEXT, status TEXT, started_at TEXT,
                    finished_at TEXT, snapshot TEXT
                )
            """)
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, op, mode, selected_steps, status, started_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    run_id, op, mode,
                    json.dumps(selected_steps or [], ensure_ascii=False),
                    status, started_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def finish_run(self, run_id: str, status: str, finished_at: str,
                   snapshot: dict | None = None) -> None:
        """Update a run record with final status + full checkpoint snapshot."""
        conn = self._sqlite_conn()
        try:
            if snapshot is not None:
                conn.execute(
                    "UPDATE pipeline_runs SET status=?, finished_at=?, snapshot=? WHERE run_id=?",
                    (status, finished_at, json.dumps(snapshot, ensure_ascii=False), run_id),
                )
            else:
                conn.execute(
                    "UPDATE pipeline_runs SET status=?, finished_at=? WHERE run_id=?",
                    (status, finished_at, run_id),
                )
            conn.commit()
        finally:
            conn.close()

    def list_runs(self, limit: int = 50) -> list[dict]:
        """Return recent runs (newest first), without the heavy snapshot field."""
        conn = self._sqlite_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY, op TEXT, mode TEXT,
                    selected_steps TEXT, status TEXT, started_at TEXT,
                    finished_at TEXT, snapshot TEXT
                )
            """)
            rows = conn.execute(
                "SELECT run_id, op, mode, status, started_at, finished_at, selected_steps "
                "FROM pipeline_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_run(self, run_id: str) -> dict | None:
        """Return a single run record including its checkpoint snapshot."""
        conn = self._sqlite_conn()
        try:
            row = conn.execute(
                "SELECT run_id, op, mode, status, started_at, finished_at, snapshot "
                "FROM pipeline_runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
