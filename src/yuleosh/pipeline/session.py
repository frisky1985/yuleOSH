#!/usr/bin/env python3

# @req RS-001  @req SWR-001.1
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Session — session state management and persistence.

Exports:
  PipelineSession — session data, step tracking, disk persistence
  PipelineStepError — hard-failure exception (stops pipeline)

Zero dependency on other pipeline modules.  Only depends on stdlib.
"""

import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

log = logging.getLogger("pipeline.session")


# ------------------------------------------------------------------
# Store reference (lazy init — only when store module is available)
# ------------------------------------------------------------------

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from store import Store
    _store = Store()
except Exception as e:
    logging.getLogger("pipeline.session").warning("Store init failed: %s", e)
    _store = None
finally:
    # Keep sys.path clean — remove the temp insertion
    _p = os.path.join(os.path.dirname(__file__), "..")
    while _p in sys.path:
        sys.path.remove(_p)


# ------------------------------------------------------------------
# Exception — no silent degradation
# ------------------------------------------------------------------

class PipelineStepError(RuntimeError):
    """Raised when a pipeline step encounters a hard failure.

    Replaces silent degradation (try/except/pass) with an explicit,
    interruptible error that stops the pipeline.
    """


# ------------------------------------------------------------------
# Session
# ------------------------------------------------------------------

class PipelineSession:
    """Represents a running pipeline session."""

    def __init__(
        self,
        name: str,
        spec_path: str,
        llm_client: Callable | None = None,
        agent_constraints: str | None = None,
        development_mode: str | None = None,
        config: dict | None = None,
        org_id: int = 0,
        user_id: int | None = None,
        user_email: str | None = None,
        run_id: str | None = None,
    ):
        self.name = name
        self.spec_path = str(Path(spec_path).resolve())
        self.project_dir = str(Path(os.environ.get("OSH_HOME", ".")).resolve())
        # Portal 方案 B (2026-08-10): 消费计量归属组织（JWT org_id，CLI 默认 0）。
        self.org_id: int = org_id
        # Phase 9 (2026-08-10): 用户归因 + run 唯一标识。
        #   user_id/user_email — 触发用户（JWT 上下文；CLI 为 None）。
        #   run_id — 每次运行唯一（uuid4 hex 短码），目录命名以此为准，
        #     根治同名 pipeline 跨用户/跨次覆盖 session.json 的问题。
        self.user_id: int | None = user_id
        self.user_email: str | None = user_email
        self.run_id: str = run_id or uuid4().hex[:12]
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.status = "created"  # created -> running -> completed | failed
        self.current_step = 0
        self.steps: list[dict] = []
        self.artifacts: dict = {}
        self.errors: list[str] = []
        self.session_dir = self._ensure_session_dir()
        self.artifacts_dir = str(self.session_dir)
        self.llm_client = llm_client
        # Agent constraints loaded from .yuleosh/agents/ or default spec
        self.agent_constraints = agent_constraints or ""
        # A1-A4 (2026-08-08): per-role agent constraints (role isolation).
        #   agent_constraints_by_role — dict[role, text] scanned from
        #     .yuleosh/agents/*.md (see yuleosh.agent_registry).  Empty
        #     dict means "legacy path" (use self.agent_constraints).
        #   agent_shared_baseline — role-agnostic minimal safety baseline
        #     injected alongside the current step's role constraints.
        self.agent_constraints_by_role: dict = {}
        self.agent_shared_baseline: str = ""
        # Token usage tracking across all steps
        self.token_usage_total: int = 0
        self.token_usage_steps: list[dict] = []
        # D2 (2026-08-19): 并行组执行时多线程同时累加 token usage —
        # += 是读-加-写三步非原子, 需要锁保护。
        self._usage_lock = threading.RLock()
        # D3 codegen: "planning" (default) or "generate-code".
        # Accepts None (default planning), "generate-code", or "planning".
        self.development_mode: str | None = development_mode
        # Arbitrary session config (e.g. {"codegen": {...}}).
        self.config: dict = config or {}
        # Mock mode flag — set by run_pipeline(..., mock=True).
        # When True, LLM outputs are placeholders and code-quality gates
        # (coverage, critical safety) SHALL skip real scanning.
        self.mock_mode: bool = False
        # 方向2 (2026-08-11): diff 裁剪决策（OSH_DIFF_SKIP=1 时由 orchestrator 写入）
        # G2: skip 显式报告 —— 每个决策 {step, reason} 进 session，禁止静默消失。
        self.diff_skip_decisions: list[dict] = []
        # 9.3.1 (2026-08-19 第九轮): 上下文安全强制化 — context_guard 水位
        # 检查结果（normal/reference/over_limit + 估算 tokens + 触发原因）。
        # 由 stages/llm.py _call_llm 写入, 报告 JSON 可见, 不静默降质。
        self.context_guard: dict | None = None
        # B1/B2 (2026-08-08): current step context — set by
        # agent_checkpoint._make_session_factory / subprocess worker so
        # handlers can read which step they're running as.  Declared here
        # for type-checker cleanliness (assigned dynamically otherwise).
        self.step_id: str = ""
        self.step_name: str = ""
        self.agent: str = ""
        # B2-2 (2026-08-08): artifact consistency markers —
        # {artifact_key: "missing"|"empty"} set by set_artifact soft check.
        self.artifact_missing: dict = {}
        # 方案 A (2026-08-07): pipeline knowledge injection state.
        # pipeline_knowledge_step_key — current step key (set by orchestrator).
        # pipeline_knowledge_config — cached .yuleosh/pipeline-knowledge.yaml.
        self.pipeline_knowledge_step_key: str = ""
        # 断点续跑 (2026-08-12): --from-step N 时记录起点 (0 = 从头跑)。
        self.from_step: int = 0
        # Type is yuleosh.pipeline.knowledge_injection.PipelineKnowledgeConfig
        # (avoid import cycle; cached by _call_llm on first use).
        self.pipeline_knowledge_config: object = None

    def _ensure_session_dir(self) -> Path:
        """Ensure the session directory exists and return its path.

        Phase 9 (2026-08-10): directory is named by run_id (unique per run)
        instead of pipeline name — two runs of the same pipeline (or by two
        users) no longer overwrite each other's session.json.
        """
        base = Path(os.environ.get("OSH_HOME", "."))
        sdir = base / ".osh" / "sessions" / self.run_id
        sdir.mkdir(parents=True, exist_ok=True)
        return sdir

    def add_step(self, step_name: str, agent: str, action: str) -> dict:
        """Add a new step to the pipeline and return it."""
        step = {
            "step": len(self.steps) + 1,
            "name": step_name,
            "agent": agent,
            "action": action,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "output_path": None,
            "errors": [],
        }
        self.steps.append(step)
        return step

    def start_step(self, step_idx: int) -> None:
        """Mark a step as running and record the start timestamp."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "running"
            self.steps[step_idx]["started_at"] = datetime.now().isoformat()
            self.current_step = step_idx
            self._save(persist=False)

    def complete_step(self, step_idx: int, output_path: str) -> None:
        """Mark a step as completed with its output path."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "completed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["output_path"] = output_path
            self.updated_at = datetime.now().isoformat()
            self._save(persist=False)

    def fail_step(self, step_idx: int, error: str) -> None:
        """Fail a step, record the error, and set session status to failed."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "failed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["errors"].append(error)
            self.errors.append(error)
            self.status = "failed"
            self.updated_at = datetime.now().isoformat()
            self._save()

    def set_artifact(self, key: str, path: str) -> None:
        """Register a generated artifact and persist session state.

        B2-2 (2026-08-08): consistency check — a registered artifact whose
        file is missing or empty is flagged (non-fatal warning + marker).
        Hard enforcement lives in CheckpointEngine (step FAILED); this is a
        soft check so orchestrator-path callers aren't broken by missing
        files that later steps may legitimately generate.
        """
        self.artifacts[key] = str(path)
        # B2-2 soft check: flag missing/empty artifacts without raising.
        _ap = Path(str(path))
        if not _ap.exists():
            self.artifact_missing[key] = "missing"
        elif _ap.stat().st_size == 0:
            self.artifact_missing[key] = "empty"
        else:
            self.artifact_missing.pop(key, None)
        self._save(persist=False)

    def add_token_usage(self, step_key: str, usage: dict) -> None:
        """Thread-safe token usage accumulation (D2 parallel groups).

        并行组执行时多个 worker 线程同时调用; ``+=`` 与 ``append`` 需要
        原子性 — 用 _usage_lock 保护, 防止丢失更新/交叉写入。
        """
        with self._usage_lock:
            self.token_usage_total += int(usage.get("total_tokens", 0) or 0)
            self.token_usage_steps.append({"step": step_key, "usage": usage})

    def _save(self, persist: bool = True) -> None:
        """Persist session state to disk (JSON) and SQLite store.

        Args:
            persist: If True, write to disk & store.  Set False for
                     intermediate calls to avoid file I/O churn.
        """
        if not persist:
            return
        data = self.to_dict()
        with open(self.session_dir / "session.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Also persist to SQLite
        if _store:
            try:
                _store.save_pipeline(self.name, data)
            except Exception as e:
                log.warning(f"Store save_pipeline failed (non-fatal): {e}")

    def to_dict(self) -> dict:
        """Serialize session to a dictionary for storage."""
        return {
            "name": self.name,
            "run_id": self.run_id,
            "spec_path": self.spec_path,
            "status": self.status,
            "current_step": self.current_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": self.steps,
            "artifacts": self.artifacts,
            "errors": self.errors,
            "org_id": self.org_id,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "token_usage_total": self.token_usage_total,
            "token_usage_steps": self.token_usage_steps,
            # Evidence-chain provenance (2026-09-03): a mock run produces
            # placeholder artifacts.  Without this flag a consumer of the
            # evidence pack cannot tell mock output from a real LLM run.
            "mock_mode": bool(getattr(self, "mock_mode", False)),
        }


# ------------------------------------------------------------------
# Store reference (populated by the first importer that sets it up)
# ------------------------------------------------------------------

