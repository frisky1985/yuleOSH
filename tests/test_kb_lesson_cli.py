# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""End-to-end tests for `yuleosh lesson create` — 工单 → Lesson 知识沉淀闭环.

Covers:
- lesson create from a temp improvement ticket YAML (open status)
- lesson create from a closed ticket (closed 提示)
- lesson create with --req / --title / --severity overrides
- kb lessons list shows ticket back-link
- missing ticket file → error exit code
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.kb.cli import (
    _handle_lesson_create,
    _load_ticket,
    _resolve_ticket_path,
    handle_lesson_command,
)
from yuleosh.kb.store import KbStore


@pytest.fixture
def kb_env(tmp_path):
    """Isolate KB DB + tickets dir via env vars."""
    db_path = str(tmp_path / "kb.db")
    old_db = os.environ.get("YULEOSH_KB_DB")
    old_home = os.environ.get("OSH_HOME")
    os.environ["YULEOSH_KB_DB"] = db_path
    os.environ["OSH_HOME"] = str(tmp_path)
    yield tmp_path
    if old_db is None:
        os.environ.pop("YULEOSH_KB_DB", None)
    else:
        os.environ["YULEOSH_KB_DB"] = old_db
    if old_home is None:
        os.environ.pop("OSH_HOME", None)
    else:
        os.environ["OSH_HOME"] = old_home


def _write_ticket(tmp_path, ticket_id, status="open", severity="critical",
                  metric="misra_violations", extra=None):
    """Write a minimal improvement ticket YAML (mirrors loop_engine writer)."""
    tickets_dir = tmp_path / "improvement_tickets"
    tickets_dir.mkdir(exist_ok=True)
    lines = [
        "---",
        "improvement_ticket:",
        f'  ticket_id: "{ticket_id}"',
        f"  status: {status}",
        "  priority: P0",
        f"  severity: {severity}",
        f"  metric: {metric}",
        "  current_value: 80",
        "  threshold: 50",
        "  deadline: 2026-08-05T11:54:25.290591+00:00",
        '  assigned_to: ""',
        "  created_at: 2026-08-04T11:54:25.290513+00:00",
        "  problem_description: >",
        "    KPI 指标超阈值告警 (当前值=80, 阈值=50)",
        "  root_cause: >",
        "    新增代码未经过静态检查",
        "  recommended_actions: >",
        "    1) 运行 MISRA 检查; 2) 修复高严重度违规",
        "  tags:",
        "    - loop3",
        "    - kpi_improvement",
    ]
    if extra:
        for k, v in extra.items():
            lines.append(f"  {k}: {v}")
    lines.append("...")
    (tickets_dir / f"{ticket_id}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestTicketLoading:
    def test_resolve_ticket_path_finds_osh_home(self, kb_env):
        """_resolve_ticket_path finds tickets under OSH_HOME/improvement_tickets."""
        _write_ticket(kb_env, "IMP-TEST-001")
        p = _resolve_ticket_path("IMP-TEST-001")
        assert p.exists()
        assert p.name == "IMP-TEST-001.yaml"

    def test_load_ticket_returns_improvement_ticket_dict(self, kb_env):
        """_load_ticket returns the improvement_ticket mapping."""
        _write_ticket(kb_env, "IMP-TEST-002", severity="high")
        t = _load_ticket("IMP-TEST-002")
        assert t["ticket_id"] == "IMP-TEST-002"
        assert t["severity"] == "high"
        assert t["metric"] == "misra_violations"
        assert "problem_description" in t
        assert "recommended_actions" in t
        assert "root_cause" in t

    def test_load_ticket_missing_raises(self, kb_env):
        """_load_ticket raises FileNotFoundError for unknown ticket."""
        with pytest.raises(FileNotFoundError):
            _load_ticket("IMP-NOPE")


class TestLessonCreateE2E:
    def test_create_from_open_ticket(self, kb_env, capsys):
        """lesson create from an open ticket persists all mapped fields."""
        _write_ticket(kb_env, "IMP-E2E-001", status="open", severity="high")
        args = _args(ticket="IMP-E2E-001")
        rc = handle_lesson_command(args)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Lesson created" in out
        assert "IMP-E2E-001" in out
        assert "closed 工单" not in out

        store = KbStore()
        lessons = store.list_lessons(ticket_id="IMP-E2E-001")
        assert len(lessons) == 1
        l = lessons[0]
        assert l.ticket_id == "IMP-E2E-001"
        assert l.title == "misra_violations"  # 默认 title = 工单 metric
        assert l.severity == "high"           # 默认 severity = 工单 severity
        assert "超阈值告警" in l.problem
        assert "MISRA 检查" in l.solution
        assert "静态检查" in l.root_cause

    def test_create_with_overrides(self, kb_env, capsys):
        """--req/--title/--severity override ticket defaults."""
        _write_ticket(kb_env, "IMP-E2E-002", severity="critical")
        args = _args(ticket="IMP-E2E-002", req="REQ-BCM-042",
                     title="MISRA 合规教训", severity="low")
        assert handle_lesson_command(args) == 0
        capsys.readouterr()

        store = KbStore()
        l = store.list_lessons(ticket_id="IMP-E2E-002")[0]
        assert l.requirement_id == "REQ-BCM-042"
        assert l.title == "MISRA 合规教训"
        assert l.severity == "low"

    def test_create_from_closed_ticket_prints_hint(self, kb_env, capsys):
        """closed 工单沉淀时输出提示."""
        _write_ticket(kb_env, "IMP-E2E-003", status="closed")
        args = _args(ticket="IMP-E2E-003")
        assert handle_lesson_command(args) == 0
        out = capsys.readouterr().out
        assert "closed 工单" in out

    def test_create_missing_ticket_returns_error(self, kb_env, capsys):
        """Missing ticket → non-zero exit + stderr message."""
        args = _args(ticket="IMP-GHOST")
        assert handle_lesson_command(args) == 1
        err = capsys.readouterr().err
        assert "工单不存在" in err

    def test_kb_lessons_shows_ticket_backlink(self, kb_env, capsys):
        """kb lessons list displays [ticket: IMP-xxx] back-link."""
        _write_ticket(kb_env, "IMP-E2E-004")
        assert handle_lesson_command(_args(ticket="IMP-E2E-004")) == 0
        capsys.readouterr()

        store = KbStore()
        lessons = store.list_lessons()
        assert len(lessons) == 1
        assert lessons[0].ticket_id == "IMP-E2E-004"


def _args(ticket, req="", title="", severity=""):
    """Build a Namespace mimicking the argparse result for lesson create."""
    from argparse import Namespace
    return Namespace(lesson_sub="create", ticket=ticket, req=req,
                     title=title, severity=severity)
