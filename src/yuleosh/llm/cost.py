#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/cost.py — LLM call audit logging.

Logs every LLM invocation to `.osh/logs/llm_calls.jsonl` with
timestamp, model, token counts, cost, and duration.

Provides daily summary and per-task aggregation.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

log = logging.getLogger("llm.cost")


@dataclass
class LLMCallLog:
    """A single LLM API call audit record."""

    timestamp: str
    task_type: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    cost: float
    duration_s: float
    status: str  # "success" | "failed: ..."
    task_id: Optional[str] = None
    user_id: Optional[str] = None


class CostLogger:
    """LLM call audit log writer and aggregator."""

    # Default log directory (under project root)
    _log_dir: Optional[str] = None

    @classmethod
    def init(cls, project_dir: str):
        """Set the project log directory."""
        cls._log_dir = os.path.join(project_dir, ".osh", "logs")
        Path(cls._log_dir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def _ensure_log_path(cls) -> str:
        """Return the log file path, creating directory if needed."""
        if cls._log_dir is None:
            cls._log_dir = ".osh/logs"
        log_dir = Path(cls._log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / "llm_calls.jsonl")

    @classmethod
    def log(cls, entry: LLMCallLog):
        """Append a single LLM call record to the JSONL log.

        Args:
            entry: Fully populated LLMCallLog instance.
        """
        log_path = cls._ensure_log_path()
        with open(log_path, "a") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False, default=str) + "\n")

    @classmethod
    def log_dict(cls, **kwargs):
        """Convenience: create LLMCallLog from keyword args and write."""
        entry = LLMCallLog(**kwargs)
        cls.log(entry)

    # ------------------------------------------------------------------
    # Provider fallback event log (provider_fallback.py)
    # ------------------------------------------------------------------

    _fallback_log_path: str | None = None

    @classmethod
    def _ensure_fallback_log_path(cls) -> str:
        """Return the provider fallback event log path, creating dirs if needed."""
        if cls._fallback_log_path is None:
            if cls._log_dir is None:
                cls._log_dir = ".osh/logs"
            log_dir = Path(cls._log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            cls._fallback_log_path = str(log_dir / "provider_fallback_events.jsonl")
        return cls._fallback_log_path

    @classmethod
    def log_fallback_event(
        cls,
        from_provider: str,
        to_provider: str,
        reason: str,
        duration_s: float = 0.0,
        error: str = "",
    ) -> None:
        """Append a provider degradation event to the audit log.

        Args:
            from_provider: Provider that failed (or the primary provider).
            to_provider: Provider degraded to ("(abort)" if chain stopped,
                "(none)" if chain exhausted).
            reason: degradation reason (connection_error/timeout/http_5xx/
                rate_limit/budget_exceeded/skeleton/no_key/non_degradable).
            duration_s: time spent on the failed attempt.
            error: exception message from the failed attempt (optional).
        """
        path = cls._ensure_fallback_log_path()
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "from_provider": from_provider,
            "to_provider": to_provider,
            "reason": reason,
            "duration_s": duration_s,
            "error": error,
        }
        with open(path, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    @classmethod
    def get_daily_summary(cls, date_str: Optional[str] = None) -> dict:
        """Aggregate call statistics for a specific date.

        Args:
            date_str: ISO date string (e.g. "2026-07-05").
                      Defaults to today.

        Returns:
            Dict with total_calls, total_cost, model_breakdown, etc.
        """
        if date_str is None:
            date_str = date.today().isoformat()

        log_path = cls._ensure_log_path()
        if not os.path.exists(log_path):
            return {"date": date_str, "total_calls": 0, "total_cost": 0.0}

        summary = {
            "date": date_str,
            "total_calls": 0,
            "successful": 0,
            "failed": 0,
            "total_cost": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_duration_s": 0.0,
            "model_breakdown": defaultdict(lambda: {"calls": 0, "cost": 0.0}),
            "task_type_breakdown": defaultdict(lambda: {"calls": 0, "cost": 0.0}),
        }

        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = record.get("timestamp", "")
                    if not ts.startswith(date_str):
                        continue

                    summary["total_calls"] += 1
                    status = record.get("status", "unknown")
                    if status == "success":
                        summary["successful"] += 1
                    else:
                        summary["failed"] += 1

                    summary["total_cost"] += record.get("cost", 0)
                    summary["total_tokens_in"] += record.get("tokens_in", 0)
                    summary["total_tokens_out"] += record.get("tokens_out", 0)
                    summary["total_duration_s"] += record.get("duration_s", 0)

                    model = record.get("model", "unknown")
                    summary["model_breakdown"][model]["calls"] += 1
                    summary["model_breakdown"][model]["cost"] += record.get("cost", 0)

                    task_type = record.get("task_type", "unknown")
                    summary["task_type_breakdown"][task_type]["calls"] += 1
                    summary["task_type_breakdown"][task_type]["cost"] += record.get("cost", 0)

                except (json.JSONDecodeError, KeyError):
                    continue

        # Convert defaultdicts to regular dicts
        summary["model_breakdown"] = dict(summary["model_breakdown"])
        summary["task_type_breakdown"] = dict(summary["task_type_breakdown"])

        return summary

    @classmethod
    def get_task_cost(cls, task_id: str) -> float:
        """Sum LLM cost for a specific pipeline task.

        Args:
            task_id: Pipeline task identifier.

        Returns:
            Total USD cost for all LLM calls in this task.
        """
        log_path = cls._ensure_log_path()
        if not os.path.exists(log_path):
            return 0.0

        total = 0.0
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("task_id") == task_id:
                        total += record.get("cost", 0)
                except json.JSONDecodeError:
                    continue

        return total
