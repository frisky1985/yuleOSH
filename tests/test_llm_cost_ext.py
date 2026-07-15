# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for yuleosh.llm.cost — CostLogger, LLMCallLog, daily summaries."""

import json
import os
import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.llm.cost import CostLogger, LLMCallLog


# ---------------------------------------------------------------------------
# LLMCallLog dataclass
# ---------------------------------------------------------------------------

class TestLLMCallLog:
    """GIVEN LLMCallLog WHEN constructed THEN fields match."""

    def test_minimal(self):
        """GIVEN only required fields WHEN LLMCallLog THEN fields set."""
        entry = LLMCallLog(
            timestamp="2026-07-11T12:00:00",
            task_type="code_gen",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=100,
            tokens_out=50,
            cost=0.002,
            duration_s=1.5,
            status="success",
        )
        assert entry.timestamp == "2026-07-11T12:00:00"
        assert entry.task_type == "code_gen"
        assert entry.model == "deepseek-v4"
        assert entry.cost == 0.002
        assert entry.status == "success"
        assert entry.task_id is None
        assert entry.user_id is None

    def test_full(self):
        """GIVEN all fields WHEN LLMCallLog THEN task_id and user_id set."""
        entry = LLMCallLog(
            timestamp="2026-07-11T12:00:00",
            task_type="code_gen",
            model="gpt-4o",
            provider="openai",
            tokens_in=200,
            tokens_out=100,
            cost=0.005,
            duration_s=2.0,
            status="success",
            task_id="task-123",
            user_id="user-456",
        )
        assert entry.task_id == "task-123"
        assert entry.user_id == "user-456"


# ---------------------------------------------------------------------------
# CostLogger.log / log_dict
# ---------------------------------------------------------------------------

class TestCostLoggerLog:
    """GIVEN CostLogger WHEN log/log_dict called THEN writes JSONL."""

    def test_log_writes_jsonl(self, tmp_path):
        """GIVEN LLMCallLog WHEN log THEN JSONL line appended."""
        log_dir = tmp_path / ".osh" / "logs"
        CostLogger._log_dir = str(log_dir)
        entry = LLMCallLog(
            timestamp="2026-07-11T12:00:00",
            task_type="test",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=10,
            tokens_out=5,
            cost=0.001,
            duration_s=0.5,
            status="success",
        )
        CostLogger.log(entry)
        log_path = log_dir / "llm_calls.jsonl"
        assert log_path.exists()
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["task_type"] == "test"
        assert record["model"] == "deepseek-v4"
        assert record["cost"] == 0.001

    def test_log_appends_existing(self, tmp_path):
        """GIVEN existing log WHEN log called THEN appends new line."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "llm_calls.jsonl"
        log_path.write_text('{"timestamp":"2026-07-11T12:00:00","task_type":"prev"}\n')

        CostLogger._log_dir = str(log_dir)
        entry = LLMCallLog(
            timestamp="2026-07-11T13:00:00",
            task_type="new",
            model="deepseek-v4",
            provider="deepseek",
            tokens_in=10, tokens_out=5,
            cost=0.001, duration_s=0.5,
            status="success",
        )
        CostLogger.log(entry)
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_log_dict_convenience(self, tmp_path):
        """GIVEN kwargs WHEN log_dict THEN creates LLMCallLog and writes."""
        log_dir = tmp_path / ".osh" / "logs"
        CostLogger._log_dir = str(log_dir)
        CostLogger.log_dict(
            timestamp="2026-07-11T14:00:00",
            task_type="review",
            model="claude-4-sonnet",
            provider="anthropic",
            tokens_in=500,
            tokens_out=200,
            cost=0.015,
            duration_s=3.0,
            status="success",
            task_id="rev-001",
        )
        log_path = log_dir / "llm_calls.jsonl"
        assert log_path.exists()
        record = json.loads(log_path.read_text().strip())
        assert record["task_type"] == "review"
        assert record["task_id"] == "rev-001"
        assert record["model"] == "claude-4-sonnet"

    def test_log_creates_dir(self, tmp_path):
        """GIVEN non-existent log dir WHEN log THEN dir created."""
        log_dir = tmp_path / "deep" / "nested" / "logs"
        assert not log_dir.exists()
        CostLogger._log_dir = str(log_dir)
        entry = LLMCallLog(
            timestamp="2026-07-11T12:00:00", task_type="t",
            model="m", provider="p",
            tokens_in=1, tokens_out=1,
            cost=0.0, duration_s=0.1,
            status="success",
        )
        CostLogger.log(entry)
        assert log_dir.exists()
        assert (log_dir / "llm_calls.jsonl").exists()

    def test_init_sets_log_dir(self, tmp_path):
        """GIVEN project_dir WHEN init THEN _log_dir set and dir created."""
        project_dir = str(tmp_path / "my-project")
        CostLogger.init(project_dir)
        expected = str(Path(project_dir) / ".osh" / "logs")
        assert CostLogger._log_dir == expected
        assert Path(expected).exists()


# ---------------------------------------------------------------------------
# CostLogger.get_daily_summary
# ---------------------------------------------------------------------------

class TestCostLoggerDailySummary:
    """GIVEN log file with entries WHEN get_daily_summary THEN aggregates."""

    def test_empty_log(self, tmp_path):
        """GIVEN no log file WHEN get_daily_summary THEN zero counts."""
        CostLogger._log_dir = str(tmp_path)
        summary = CostLogger.get_daily_summary("2026-07-11")
        assert summary["total_calls"] == 0
        assert summary["total_cost"] == 0.0

    def test_single_day_aggregation(self, tmp_path):
        """GIVEN entries for one day WHEN get_daily_summary THEN aggregates."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        log_path = log_dir / "llm_calls.jsonl"
        lines = [
            json.dumps({"timestamp": "2026-07-11T10:00:00", "task_type": "code_gen",
                        "model": "deepseek-v4", "cost": 0.002, "tokens_in": 100,
                        "tokens_out": 50, "duration_s": 1.0, "status": "success"}),
            json.dumps({"timestamp": "2026-07-11T11:00:00", "task_type": "code_gen",
                        "model": "deepseek-v4", "cost": 0.001, "tokens_in": 50,
                        "tokens_out": 25, "duration_s": 0.5, "status": "success"}),
            json.dumps({"timestamp": "2026-07-12T10:00:00", "task_type": "review",
                        "model": "claude-4-sonnet", "cost": 0.015, "tokens_in": 500,
                        "tokens_out": 200, "duration_s": 3.0, "status": "success"}),
        ]
        log_path.write_text("\n".join(lines) + "\n")

        CostLogger._log_dir = str(log_dir)
        summary = CostLogger.get_daily_summary("2026-07-11")
        assert summary["total_calls"] == 2
        assert summary["successful"] == 2
        assert summary["total_cost"] == 0.003
        assert summary["total_tokens_in"] == 150
        assert summary["total_tokens_out"] == 75
        assert summary["total_duration_s"] == 1.5
        assert "deepseek-v4" in summary["model_breakdown"]
        assert summary["model_breakdown"]["deepseek-v4"]["calls"] == 2

    def test_daily_summary_defaults_today(self, tmp_path):
        """GIVEN no date_str WHEN get_daily_summary THEN uses today's date."""
        CostLogger._log_dir = str(tmp_path)
        today = date.today().isoformat()
        summary = CostLogger.get_daily_summary()
        assert summary["date"] == today

    def test_daily_summary_counts_failed(self, tmp_path):
        """GIVEN failed entries WHEN get_daily_summary THEN failed counted."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        lines = [
            json.dumps({"timestamp": "2026-07-11T10:00:00", "task_type": "code_gen",
                        "model": "m", "cost": 0.0, "tokens_in": 0, "tokens_out": 0,
                        "duration_s": 0.1, "status": "success"}),
            json.dumps({"timestamp": "2026-07-11T10:01:00", "task_type": "code_gen",
                        "model": "m", "cost": 0.0, "tokens_in": 0, "tokens_out": 0,
                        "duration_s": 0.2, "status": "failed: timeout"}),
        ]
        (log_dir / "llm_calls.jsonl").write_text("\n".join(lines) + "\n")
        CostLogger._log_dir = str(log_dir)
        summary = CostLogger.get_daily_summary("2026-07-11")
        assert summary["successful"] == 1
        assert summary["failed"] == 1

    def test_daily_summary_skips_corrupt_lines(self, tmp_path):
        """GIVEN corrupt JSON lines WHEN get_daily_summary THEN skips gracefully."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        lines = [
            '{"timestamp": "2026-07-11T10:00:00", "cost": 0.001}',
            "this is not json",
            '{"timestamp": "2026-07-11T10:01:00", "cost": 0.002}',
        ]
        (log_dir / "llm_calls.jsonl").write_text("\n".join(lines) + "\n")
        CostLogger._log_dir = str(log_dir)
        summary = CostLogger.get_daily_summary("2026-07-11")
        assert summary["total_calls"] == 2

    def test_daily_summary_task_type_breakdown(self, tmp_path):
        """GIVEN multiple task types WHEN get_daily_summary THEN breakdown populated."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        lines = [
            json.dumps({"timestamp": "2026-07-11T10:00:00", "task_type": "code_gen",
                        "model": "m", "cost": 0.001, "tokens_in": 10, "tokens_out": 5,
                        "duration_s": 0.5, "status": "success"}),
            json.dumps({"timestamp": "2026-07-11T11:00:00", "task_type": "review",
                        "model": "m", "cost": 0.002, "tokens_in": 20, "tokens_out": 10,
                        "duration_s": 1.0, "status": "success"}),
        ]
        (log_dir / "llm_calls.jsonl").write_text("\n".join(lines) + "\n")
        CostLogger._log_dir = str(log_dir)
        summary = CostLogger.get_daily_summary("2026-07-11")
        assert "code_gen" in summary["task_type_breakdown"]
        assert "review" in summary["task_type_breakdown"]
        assert summary["task_type_breakdown"]["code_gen"]["calls"] == 1
        assert summary["task_type_breakdown"]["code_gen"]["cost"] == 0.001


# ---------------------------------------------------------------------------
# CostLogger.get_task_cost
# ---------------------------------------------------------------------------

class TestCostLoggerTaskCost:
    """GIVEN log entries WHEN get_task_cost THEN sums cost for task."""

    def test_get_task_cost_matches(self, tmp_path):
        """GIVEN entries with task_id WHEN get_task_cost THEN sum returned."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        lines = [
            json.dumps({"timestamp": "2026-07-11T10:00:00", "task_type": "code_gen",
                        "model": "m", "cost": 0.001, "task_id": "task-001",
                        "status": "success"}),
            json.dumps({"timestamp": "2026-07-11T10:01:00", "task_type": "code_gen",
                        "model": "m", "cost": 0.003, "task_id": "task-001",
                        "status": "success"}),
            json.dumps({"timestamp": "2026-07-11T10:02:00", "task_type": "review",
                        "model": "m", "cost": 0.010, "task_id": "task-002",
                        "status": "success"}),
        ]
        (log_dir / "llm_calls.jsonl").write_text("\n".join(lines) + "\n")
        CostLogger._log_dir = str(log_dir)
        total = CostLogger.get_task_cost("task-001")
        assert total == pytest.approx(0.004)

    def test_get_task_cost_no_match(self, tmp_path):
        """GIVEN no matching task_id WHEN get_task_cost THEN 0.0."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "llm_calls.jsonl").write_text(
            '{"task_id": "task-other", "cost": 0.005}\n'
        )
        CostLogger._log_dir = str(log_dir)
        total = CostLogger.get_task_cost("task-missing")
        assert total == 0.0

    def test_get_task_cost_no_log_file(self, tmp_path):
        """GIVEN no log file WHEN get_task_cost THEN 0.0."""
        CostLogger._log_dir = str(tmp_path)
        assert CostLogger.get_task_cost("any") == 0.0

    def test_get_task_cost_skips_corrupt(self, tmp_path):
        """GIVEN corrupt JSON WHEN get_task_cost THEN skips."""
        log_dir = tmp_path / ".osh" / "logs"
        log_dir.mkdir(parents=True)
        (log_dir / "llm_calls.jsonl").write_text(
            '{"task_id": "t1", "cost": 0.001}\nnot json\n{"task_id": "t1", "cost": 0.002}\n'
        )
        CostLogger._log_dir = str(log_dir)
        total = CostLogger.get_task_cost("t1")
        assert total == pytest.approx(0.003)
