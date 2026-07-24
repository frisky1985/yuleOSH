#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("pipeline.session")


# ------------------------------------------------------------------
# Store reference (lazy init — only when store module is available)
# ------------------------------------------------------------------

try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from store import Store  # noqa: E402
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
    pass


# ------------------------------------------------------------------
# Session
# ------------------------------------------------------------------

class PipelineSession:
    """Represents a running pipeline session."""

    def __init__(
        self,
        name: str,
        spec_path: str,
        llm_client: Optional[Callable] = None,
    ):
        self.name = name
        self.spec_path = str(Path(spec_path).resolve())
        self.project_dir = str(Path(os.environ.get("OSH_HOME", ".")).resolve())
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
        # Token usage tracking across all steps
        self.token_usage_total: int = 0
        self.token_usage_steps: list[dict] = []

    def _ensure_session_dir(self) -> Path:
        """Ensure the session directory exists and return its path."""
        base = Path(os.environ.get("OSH_HOME", "."))
        sdir = base / ".osh" / "sessions" / self.name
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
        """Register a generated artifact and persist session state."""
        self.artifacts[key] = str(path)
        self._save(persist=False)

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
            "spec_path": self.spec_path,
            "status": self.status,
            "current_step": self.current_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": self.steps,
            "artifacts": self.artifacts,
            "errors": self.errors,
        }


# ------------------------------------------------------------------
# Store reference (populated by the first importer that sets it up)
# ------------------------------------------------------------------

