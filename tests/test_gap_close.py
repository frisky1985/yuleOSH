
# @tests src/yuleosh/pipeline/orchestrator.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""tests for `yuleosh gap close` — ASPICE 差距 → 改进工单（受控生成）.

Covers:
- 交互确认: input 'y' → 生成工单；'n' → 跳过
- --yes → 全部生成
- --list → 只列出不生成
- 生成的 YAML 含 requirement_id/tags/priority/severity 正确映射
- 与 kb lesson create 衔接: 生成的 GAP-*.yaml 可被 kb._load_ticket 读取（格式兼容）
"""

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from yuleosh.cli.commands.gap import (
    _build_gap_ticket,
    _load_gap_details,
    cmd_gap_close,
    write_gap_ticket,
)


def _sample_gaps():
    """2-3 个 gap，含 ❌ / ⚠️ 状态。"""
    return [
        {
            "swe_id": "SWE.1",
            "swe_title": "Requirements Elicitation",
            "bp_id": "SWE.1.BP2",
            "bp_title": "需求可追溯性",
            "status": "❌",
            "failed_checks": 2,
            "total_checks": 3,
            "missing_items": ["需求唯一标识缺失", "需求→设计追溯缺失"],
            "fix_steps": ["补充需求 ID 并登记", "建立需求→设计追溯矩阵"],
        },
        {
            "swe_id": "SWE.4",
            "swe_title": "Software Unit Verification",
            "bp_id": "SWE.4.BP2",
            "bp_title": "单元测试覆盖率",
            "status": "⚠️",
            "failed_checks": 1,
            "total_checks": 4,
            "missing_items": ["单元测试覆盖率 < 80%"],
            "fix_steps": ["补充关键模块单元测试用例"],
        },
    ]


def _gap_json(project_dir="proj", gaps=None):
    """构造 aspice_gap_check(output_format='json') 的返回值（JSON 字符串）。"""
    data = {
        "project_dir": project_dir,
        "standard": "ASPICE",
        "version": "3.1",
        "generated_at": "2026-08-07T10:00:00+00:00",
        "summary": {"failed": 1, "partial": 1, "passed": 10},
        "gaps": gaps if gaps is not None else _sample_gaps(),
    }
    return json.dumps(data, ensure_ascii=False)


def _args(project_dir, yes=False, no=False, list_only=False, req=""):
    return SimpleNamespace(
        project_dir=str(project_dir), yes=yes, no=no, list=list_only, req=req,
    )


def _list_ticket_files(tmp_path):
    tickets_dir = tmp_path / "improvement_tickets"
    if not tickets_dir.exists():
        return []
    return sorted(tickets_dir.glob("GAP-*.yaml"))


@pytest.fixture
def mock_gap_check():
    with patch("yuleosh.evidence.aspice_check.aspice_gap_check",
               return_value=_gap_json()) as m:
        yield m


class TestGapCloseInteractive:
    def test_input_y_generates_tickets(self, tmp_path, monkeypatch, mock_gap_check, capsys):
        """交互模式 input 'y' → 生成全部工单。"""
        monkeypatch.setattr("builtins.input", lambda prompt: "y")
        rc = cmd_gap_close(_args(tmp_path))
        assert rc == 0
        files = _list_ticket_files(tmp_path)
        assert len(files) == 2
        assert all(f.name.startswith("GAP-") for f in files)
        out = capsys.readouterr().out
        assert "GAP-" in out and "汇总" in out

    def test_input_n_skips_all(self, tmp_path, monkeypatch, mock_gap_check):
        """交互模式 input 'n' → 全部跳过，不生成。"""
        monkeypatch.setattr("builtins.input", lambda prompt: "n")
        rc = cmd_gap_close(_args(tmp_path))
        assert rc == 0
        assert _list_ticket_files(tmp_path) == []

    def test_input_mixed_y_n(self, tmp_path, monkeypatch, mock_gap_check):
        """交互模式: 第一个 'y' 第二个 'n' → 只生成 1 个。"""
        answers = iter(["y", "n"])
        monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
        cmd_gap_close(_args(tmp_path))
        files = _list_ticket_files(tmp_path)
        assert len(files) == 1
        assert "SWE.1.BP2" in files[0].name


class TestGapCloseFlags:
    def test_yes_generates_all(self, tmp_path, mock_gap_check, capsys):
        """--yes → 跳过确认，全部生成。"""
        rc = cmd_gap_close(_args(tmp_path, yes=True))
        assert rc == 0
        files = _list_ticket_files(tmp_path)
        assert len(files) == 2

    def test_no_skips_all(self, tmp_path, mock_gap_check):
        """--no → 全部跳过，不生成。"""
        rc = cmd_gap_close(_args(tmp_path, no=True))
        assert rc == 0
        assert _list_ticket_files(tmp_path) == []

    def test_list_only_no_generation(self, tmp_path, mock_gap_check, capsys):
        """--list → 只列出差距，不生成工单。"""
        rc = cmd_gap_close(_args(tmp_path, list_only=True))
        assert rc == 0
        assert _list_ticket_files(tmp_path) == []
        out = capsys.readouterr().out
        assert "[SWE.1] SWE.1.BP2" in out
        assert "缺口 2 项" in out
        assert "--list 模式" in out

    def test_no_gaps_reports_success(self, tmp_path):
        """无差距时直接提示，不生成工单。"""
        with patch("yuleosh.evidence.aspice_check.aspice_gap_check",
                   return_value=_gap_json(gaps=[])):
            rc = cmd_gap_close(_args(tmp_path, yes=True))
        assert rc == 0
        assert _list_ticket_files(tmp_path) == []


class TestTicketMapping:
    def test_priority_severity_mapping(self):
        """❌ → P1/high；⚠️ → P2/medium。"""
        gaps = _sample_gaps()
        t_fail = _build_gap_ticket(gaps[0], created_at="2026-08-07T10:00:00+00:00")
        assert t_fail["priority"] == "P1"
        assert t_fail["severity"] == "high"
        t_partial = _build_gap_ticket(gaps[1], created_at="2026-08-07T10:00:00+00:00")
        assert t_partial["priority"] == "P2"
        assert t_partial["severity"] == "medium"

    def test_ticket_id_prefix_and_metric(self):
        """ticket_id 用 GAP-{date}-{bp_id}，metric=bp_id。"""
        t = _build_gap_ticket(_sample_gaps()[0], created_at="2026-08-07T10:00:00+00:00")
        assert t["ticket_id"] == "GAP-2026-08-07-SWE.1.BP2"
        assert t["metric"] == "SWE.1.BP2"

    def test_tags_include_gap_aspice_bp_swe(self):
        t = _build_gap_ticket(_sample_gaps()[0])
        assert t["tags"] == ["gap", "aspice", "SWE.1.BP2", "SWE.1"]

    def test_requirement_id_default_empty(self):
        t = _build_gap_ticket(_sample_gaps()[0])
        assert t["requirement_id"] == ""
        assert t["requirements"] == []

    def test_requirement_id_from_req_flag(self):
        t = _build_gap_ticket(_sample_gaps()[0], req="REQ-101")
        assert t["requirement_id"] == "REQ-101"
        assert t["requirements"] == ["REQ-101"]

    def test_problem_description_uses_missing_items(self):
        t = _build_gap_ticket(_sample_gaps()[0])
        assert "需求唯一标识缺失" in t["problem_description"]
        assert "需求→设计追溯缺失" in t["problem_description"]

    def test_recommended_actions_from_fix_steps(self):
        t = _build_gap_ticket(_sample_gaps()[0])
        assert "补充需求 ID 并登记" in t["recommended_actions"]

    def test_root_cause_contains_bp_and_failed_checks(self):
        t = _build_gap_ticket(_sample_gaps()[0])
        assert "SWE.1.BP2" in t["root_cause"]
        assert "2/3" in t["root_cause"]


class TestTicketYaml:
    def test_yaml_parseable_with_improvement_ticket_root(self, tmp_path):
        """YAML 结构与 rca_engine 一致（improvement_ticket 根节点 + requirement 字段）。"""
        t = _build_gap_ticket(_sample_gaps()[0], req="REQ-101",
                              created_at="2026-08-07T10:00:00+00:00")
        path = write_gap_ticket(t, output_dir=str(tmp_path))
        assert os.path.exists(path)

        content = open(path, encoding="utf-8").read()
        assert "improvement_ticket:" in content
        assert 'ticket_id: "GAP-2026-08-07-SWE.1.BP2"' in content
        assert 'requirement_id: "REQ-101"' in content
        assert "requirements: ['REQ-101']" in content

        data = yaml.safe_load(content)
        ticket = data["improvement_ticket"]
        assert ticket["ticket_id"] == "GAP-2026-08-07-SWE.1.BP2"
        assert ticket["priority"] == "P1"
        assert ticket["severity"] == "high"
        assert ticket["metric"] == "SWE.1.BP2"
        assert ticket["status"] == "open"
        assert ticket["requirement_id"] == "REQ-101"
        assert ticket["requirements"] == ["REQ-101"]
        assert ticket["tags"] == ["gap", "aspice", "SWE.1.BP2", "SWE.1"]

    def test_cli_generated_yaml_fields(self, tmp_path, mock_gap_check):
        """--req 经 CLI 写入 YAML：requirement_id/tags/priority 映射正确。"""
        cmd_gap_close(_args(tmp_path, yes=True, req="REQ-2026"))
        files = _list_ticket_files(tmp_path)
        assert len(files) == 2

        by_name = {f.name: f for f in files}
        fail_file = by_name[[n for n in by_name if "SWE.1.BP2" in n][0]]
        partial_file = by_name[[n for n in by_name if "SWE.4.BP2" in n][0]]

        t_fail = yaml.safe_load(fail_file.read_text(encoding="utf-8"))["improvement_ticket"]
        assert t_fail["priority"] == "P1" and t_fail["severity"] == "high"
        assert t_fail["requirement_id"] == "REQ-2026"
        assert "gap" in t_fail["tags"] and "aspice" in t_fail["tags"]

        t_partial = yaml.safe_load(partial_file.read_text(encoding="utf-8"))["improvement_ticket"]
        assert t_partial["priority"] == "P2" and t_partial["severity"] == "medium"
        assert t_partial["tags"] == ["gap", "aspice", "SWE.4.BP2", "SWE.4"]


class TestLessonLoopClosure:
    def test_gap_ticket_readable_by_kb_lesson_loader(self, tmp_path, monkeypatch, mock_gap_check):
        """生成的 GAP 工单可被 kb lesson create 的 _load_ticket 读取（工单↔知识闭环）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        cmd_gap_close(_args(tmp_path, yes=True, req="REQ-007"))

        from yuleosh.kb.cli import _load_ticket

        files = _list_ticket_files(tmp_path)
        assert len(files) == 2
        # kb._load_ticket 按 OSH_HOME/improvement_tickets/{ticket_id}.yaml 定位
        ticket = _load_ticket(files[0].stem)
        assert ticket["ticket_id"] == files[0].stem
        assert ticket["metric"] in ("SWE.1.BP2", "SWE.4.BP2")
        assert ticket["requirement_id"] == "REQ-007"
        assert "gap" in ticket["tags"]
        # lesson create 依赖的字段齐全
        for field in ("problem_description", "root_cause", "recommended_actions",
                      "severity", "priority", "status"):
            assert field in ticket

    def test_load_gap_details_parses_json(self, mock_gap_check):
        """_load_gap_details 正确解析 aspice_gap_check 的 JSON 输出。"""
        gaps = _load_gap_details("proj")
        assert len(gaps) == 2
        assert gaps[0]["bp_id"] == "SWE.1.BP2"
        assert gaps[0]["status"] == "❌"
        assert gaps[0]["missing_items"] == ["需求唯一标识缺失", "需求→设计追溯缺失"]
