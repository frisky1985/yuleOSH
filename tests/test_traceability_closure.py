#!/usr/bin/env python3
"""
Tests: traceability report「需求↔问题↔知识」闭环 (closure) 扩展。

覆盖:
  1. _load_improvement_tickets 解析 YAML 工单 (requirement_id / status)
  2. _build_closure_stats 每需求 open tickets + lessons 统计
  3. lesson 经工单 (IMP-xxx 引用) 的间接知识关联
  4. cmd_traceability_report 端到端：报告 JSON 含 closure 一节 + 控制台表格
  5. 优雅降级：无工单目录 / 无 kb 库 / 空项目均不报错
  6. 未关联工单与 lessons 计入 orphan
"""

import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from yuleosh.cli.commands.traceability import (
    _build_closure_stats,
    _load_improvement_tickets,
    _load_kb_lessons,
    cmd_traceability_report,
)
from yuleosh.kb.store import KbStore


# ── fixtures ────────────────────────────────────────────────────────────

FAKE_REPORT = {
    "coverage_summary": {"requirements_total": 2, "test_coverage_pct": 80.0},
    "recommendations": [],
    "lrm": {"requirements": [
        {"req_id": "REQ-MISRA-S1", "id": "SHALL-1", "has_code": True,
         "has_test": True, "has_review": True, "section": "S1"},
        {"req_id": "REQ-UART-2", "id": "SHALL-2", "has_code": True,
         "has_test": True, "has_review": False, "section": "S2"},
    ]},
}


@pytest.fixture
def project_dir(tmp_path):
    """临时项目目录：improvement_tickets/ + .yuleosh/reports/。"""
    p = tmp_path / "proj"
    (p / "improvement_tickets").mkdir(parents=True)
    (p / ".yuleosh" / "reports").mkdir(parents=True)
    return str(p)


@pytest.fixture
def kb_db(tmp_path):
    """临时 KB SQLite 库（通过 YULEOSH_KB_DB 注入）。"""
    db_path = str(tmp_path / "kb.db")
    store = KbStore(db_path)
    yield db_path
    store.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def sample_requirements():
    """模拟 report['lrm']['requirements']（req_id 为 spec 定义 ID）。"""
    return [
        {"req_id": "REQ-MISRA-S1", "id": "SHALL-1", "has_code": True},
        {"req_id": "REQ-UART-2", "id": "SHALL-2", "has_test": True},
    ]


def _write_ticket(project_dir, name, **fields):
    """写入一张工单 YAML 并返回路径。"""
    lines = [f"id: {name}"]
    for k, v in fields.items():
        if isinstance(v, list):
            rendered = ", ".join(f'"{i}"' for i in v)
            lines.append(f"{k}: [{rendered}]")
        else:
            lines.append(f"{k}: {v}")
    path = os.path.join(project_dir, "improvement_tickets", f"{name}.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ── 1. 工单 YAML 解析 ──────────────────────────────────────────────────


class TestLoadImprovementTickets:
    def test_parses_requirement_id_and_status(self, project_dir):
        _write_ticket(project_dir, "IMP-2026-08-04-misra_vi",
                      title="MISRA 违规修复", status="open",
                      requirement_id="REQ-MISRA-S1")
        _write_ticket(project_dir, "IMP-2026-08-05-uart",
                      title="UART 修复", status="closed",
                      requirement_id="REQ-UART-2")

        tickets = _load_improvement_tickets(project_dir)
        assert len(tickets) == 2
        by_id = {t["id"]: t for t in tickets}
        assert by_id["IMP-2026-08-04-misra_vi"]["open"] is True
        assert by_id["IMP-2026-08-04-misra_vi"]["requirement_ids"] == ["REQ-MISRA-S1"]
        assert by_id["IMP-2026-08-05-uart"]["open"] is False

    def test_requirement_id_list_and_missing_ok(self, project_dir):
        _write_ticket(project_dir, "IMP-2026-08-06-multi",
                      status="in_progress",
                      requirement_id=["REQ-MISRA-S1", "REQ-UART-2"])
        _write_ticket(project_dir, "IMP-2026-08-07-nolink", status="open")

        tickets = _load_improvement_tickets(project_dir)
        by_id = {t["id"]: t for t in tickets}
        assert by_id["IMP-2026-08-06-multi"]["requirement_ids"] == [
            "REQ-MISRA-S1", "REQ-UART-2"]
        assert by_id["IMP-2026-08-07-nolink"]["requirement_ids"] == []

    def test_missing_dir_returns_empty(self, tmp_path):
        assert _load_improvement_tickets(str(tmp_path / "nonexistent")) == []

    def test_bad_yaml_skipped(self, project_dir):
        bad = os.path.join(project_dir, "improvement_tickets", "IMP-2026-08-08-bad.yaml")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("id: [unclosed\n  : : :\n")
        _write_ticket(project_dir, "IMP-2026-08-04-misra_vi",
                      status="open", requirement_id="REQ-MISRA-S1")
        tickets = _load_improvement_tickets(project_dir)
        assert len(tickets) == 1
        assert tickets[0]["id"] == "IMP-2026-08-04-misra_vi"


# ── 2/3. 闭环统计（含经工单的间接知识） ────────────────────────────────


class TestBuildClosureStats:
    def test_ticket_and_lesson_counts(self, sample_requirements):
        tickets = [
            {"id": "IMP-2026-08-04-misra_vi", "status": "open", "open": True,
             "requirement_ids": ["REQ-MISRA-S1"]},
            {"id": "IMP-2026-08-05-uart", "status": "closed", "open": False,
             "requirement_ids": ["REQ-UART-2"]},
        ]
        lessons = [
            {"id": 1, "title": "MISRA 指针误用", "project_id": "REQ-MISRA-S1",
             "severity": "high", "requirement_ids": ["REQ-MISRA-S1"],
             "ticket_ids": []},
            {"id": 2, "title": "UART 波特率", "project_id": "",
             "severity": "medium",
             "requirement_ids": ["REQ-UART-2"], "ticket_ids": []},
        ]
        closure = _build_closure_stats(sample_requirements, tickets, lessons)
        by_id = {r["req_id"]: r for r in closure["requirements"]}

        # REQ-MISRA-S1: 1 open ticket + 1 lesson
        assert by_id["REQ-MISRA-S1"]["open_tickets"] == 1
        assert by_id["REQ-MISRA-S1"]["total_tickets"] == 1
        assert by_id["REQ-MISRA-S1"]["lessons"] == 1
        # REQ-UART-2: 1 closed ticket + 1 lesson
        assert by_id["REQ-UART-2"]["open_tickets"] == 0
        assert by_id["REQ-UART-2"]["total_tickets"] == 1
        assert by_id["REQ-UART-2"]["lessons"] == 1

        s = closure["summary"]
        assert s["requirements_total"] == 2
        assert s["with_tickets"] == 2
        assert s["with_lessons"] == 2
        assert s["closed_loop"] == 2
        assert s["open_tickets_total"] == 1
        assert s["tickets_total"] == 2

    def test_lesson_linked_via_ticket(self, sample_requirements):
        """lesson 文本引用 IMP-xxx → 经工单关联到需求（间接知识）。"""
        tickets = [
            {"id": "IMP-2026-08-04-misra_vi", "status": "open", "open": True,
             "requirement_ids": ["REQ-MISRA-S1"]},
        ]
        lessons = [
            {"id": 1, "title": "MISRA 整改经验", "project_id": "",
             "severity": "medium", "requirement_ids": [],
             "ticket_ids": ["IMP-2026-08-04-misra_vi"]},
        ]
        closure = _build_closure_stats(sample_requirements, tickets, lessons)
        by_id = {r["req_id"]: r for r in closure["requirements"]}
        assert by_id["REQ-MISRA-S1"]["lessons"] == 0
        assert by_id["REQ-MISRA-S1"]["lessons_via_tickets"] == 1
        assert closure["summary"]["closed_loop"] == 1

    def test_orphans_tracked(self, sample_requirements):
        tickets = [
            {"id": "IMP-2026-08-09-lonely", "status": "open", "open": True,
             "requirement_ids": ["REQ-UNKNOWN-9"]},
        ]
        lessons = [
            {"id": 7, "title": "无关知识", "project_id": "other-project",
             "severity": "low", "requirement_ids": [], "ticket_ids": []},
        ]
        closure = _build_closure_stats(sample_requirements, tickets, lessons)
        assert closure["summary"]["orphan_tickets"] == 1
        assert closure["summary"]["orphan_lessons"] == 1
        assert closure["orphan_tickets"][0]["id"] == "IMP-2026-08-09-lonely"
        assert closure["orphan_lessons"][0]["id"] == 7
        # 已知需求不受影响
        assert closure["summary"]["open_tickets_total"] == 0

    def test_empty_inputs(self):
        closure = _build_closure_stats([], [], [])
        assert closure["requirements"] == []
        assert closure["summary"]["requirements_total"] == 0
        assert closure["summary"]["orphan_tickets"] == 0


# ── 4. 端到端：CLI report 输出含闭环统计 ───────────────────────────────


class TestReportEndToEnd:
    def test_report_json_and_console_contain_closure(self, project_dir, kb_db, capsys):
        # 工单
        _write_ticket(project_dir, "IMP-2026-08-04-misra_vi",
                      title="MISRA 违规修复", status="open",
                      requirement_id="REQ-MISRA-S1")
        _write_ticket(project_dir, "IMP-2026-08-05-uart",
                      title="UART 修复", status="closed",
                      requirement_id="REQ-UART-2")
        # KB lessons
        store = KbStore(kb_db)
        store.create_lesson({"title": "MISRA 指针误用", "problem": "",
                             "solution": "", "root_cause": "",
                             "project_id": "REQ-MISRA-S1", "severity": "high"})
        store.create_lesson({"title": "UART 整改经验", "problem": "",
                             "solution": "由 IMP-2026-08-05-uart 总结",
                             "root_cause": "", "project_id": "",
                             "severity": "medium"})
        store.close()

        args = SimpleNamespace(project_dir=project_dir, spec=None)
        old_env = os.environ.get("YULEOSH_KB_DB")
        os.environ["YULEOSH_KB_DB"] = kb_db
        try:
            with patch("yuleosh.alm.traceability.generate_traceability_report",
                       return_value=FAKE_REPORT):
                cmd_traceability_report(args)
        finally:
            if old_env is None:
                os.environ.pop("YULEOSH_KB_DB", None)
            else:
                os.environ["YULEOSH_KB_DB"] = old_env

        # JSON 报告含 closure 一节
        report_path = os.path.join(project_dir, ".yuleosh", "reports",
                                   "traceability-report.json")
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        closure = data["closure"]
        by_id = {r["req_id"]: r for r in closure["requirements"]}
        assert by_id["REQ-MISRA-S1"]["open_tickets"] == 1
        assert by_id["REQ-MISRA-S1"]["total_tickets"] == 1
        assert by_id["REQ-MISRA-S1"]["lessons"] == 1
        assert by_id["REQ-UART-2"]["open_tickets"] == 0
        assert by_id["REQ-UART-2"]["lessons_via_tickets"] == 1  # 经工单 IMP-2026-08-05-uart
        assert closure["summary"]["closed_loop"] == 2
        assert closure["summary"]["orphan_tickets"] == 0
        assert closure["summary"]["orphan_lessons"] == 0

        # 控制台表格
        out = capsys.readouterr().out
        assert "问题与知识闭环" in out
        assert "REQ-MISRA-S1" in out
        assert "闭环" in out


# ── 5. 优雅降级 ────────────────────────────────────────────────────────


class TestGracefulDegradation:
    def test_no_tickets_no_kb(self, tmp_path, capsys):
        """空项目（无工单目录、无 kb 库）→ 空统计不报错。"""
        empty = tmp_path / "empty"
        empty.mkdir()
        args = SimpleNamespace(project_dir=str(empty), spec=None)

        old_env = os.environ.get("YULEOSH_KB_DB")
        if old_env is not None:
            os.environ.pop("YULEOSH_KB_DB")
        try:
            with patch("yuleosh.alm.traceability.generate_traceability_report",
                       return_value=FAKE_REPORT):
                cmd_traceability_report(args)
        finally:
            if old_env is not None:
                os.environ["YULEOSH_KB_DB"] = old_env

        out = capsys.readouterr().out
        assert "问题与知识闭环" in out
        report_path = os.path.join(str(empty), ".yuleosh", "reports",
                                   "traceability-report.json")
        with open(report_path, encoding="utf-8") as f:
            data = json.load(f)
        s = data["closure"]["summary"]
        assert s["tickets_total"] == 0
        assert s["lessons_total"] == 0
        assert s["open_tickets_total"] == 0
        assert s["orphan_tickets"] == 0

    def test_load_kb_lessons_missing_db(self, tmp_path):
        """无 kb 库文件且无 env → 返回空列表。"""
        old_env = os.environ.get("YULEOSH_KB_DB")
        if old_env is not None:
            os.environ.pop("YULEOSH_KB_DB")
        try:
            assert _load_kb_lessons(str(tmp_path)) == []
        finally:
            if old_env is not None:
                os.environ["YULEOSH_KB_DB"] = old_env

    def test_project_dir_missing(self):
        """项目目录不存在 → 空统计不报错。"""
        assert _load_improvement_tickets("/nonexistent/xyz") == []
        closure = _build_closure_stats([], [], [])
        assert closure["summary"]["requirements_total"] == 0


# ── 6. 结构化字段关联（kb 新增 ticket_id/requirement_id 列） ───────────


class TestStructuredLessonFields:
    def test_structured_fields_consumed(self, tmp_path, sample_requirements):
        """lesson.ticket_id / lesson.requirement_id 结构化字段参与闭环。"""
        db_path = str(tmp_path / "kb.db")
        store = KbStore(db_path)
        store.create_lesson({"title": "MISRA 结构化知识", "problem": "",
                             "solution": "", "root_cause": "",
                             "project_id": "", "severity": "medium",
                             "ticket_id": "IMP-2026-08-04-misra_vi",
                             "requirement_id": "REQ-MISRA-S1"})
        store.close()

        tickets = [
            {"id": "IMP-2026-08-04-misra_vi", "status": "open", "open": True,
             "requirement_ids": ["REQ-MISRA-S1"]},
        ]

        old_env = os.environ.get("YULEOSH_KB_DB")
        os.environ["YULEOSH_KB_DB"] = db_path
        try:
            lessons = _load_kb_lessons(str(tmp_path))
        finally:
            if old_env is None:
                os.environ.pop("YULEOSH_KB_DB", None)
            else:
                os.environ["YULEOSH_KB_DB"] = old_env
        if os.path.exists(db_path):
            os.unlink(db_path)

        assert len(lessons) == 1
        assert lessons[0]["requirement_ids"] == ["REQ-MISRA-S1"]
        assert lessons[0]["ticket_ids"] == ["IMP-2026-08-04-misra_vi"]

        closure = _build_closure_stats(sample_requirements, tickets, lessons)
        by_id = {r["req_id"]: r for r in closure["requirements"]}
        # requirement_id 直接命中 + 经 ticket_id 间接命中
        assert by_id["REQ-MISRA-S1"]["lessons"] == 1
        assert by_id["REQ-MISRA-S1"]["lessons_via_tickets"] == 1
        assert closure["summary"]["closed_loop"] == 1
