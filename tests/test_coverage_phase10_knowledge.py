# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Phase 10 coverage boost — CLI / knowledge domain low-coverage files.

Target modules (Phase 10 baseline):
  - src/yuleosh/kb/cli.py                         (59%)  → handle_kb_command 全子命令 + ingest-misra + cppcheck 解析
  - src/yuleosh/knowledge/cli.py                  (54%)  → pending/approve/reject/audit 全分支
  - src/yuleosh/cli/onboard.py                    (70%)  → 错误路径 / EOF / KG bootstrap / repo clone
  - src/yuleosh/knowledge_graph/coverage_importer.py      → sqlite/json 读取 + verifies 边映射全策略
  - src/yuleosh/knowledge_graph/bootstrap.py              → RTM 解析边界 + scan_code_directory

风格：直测函数/分支，外部命令（subprocess/git）全部 mock，文件 IO 全部落在 tmp_path，
DB 隔离用 YULEOSH_KB_DB / OSH_HOME env（monkeypatch 自动恢复），KG 用 :memory: store。
不设 YULEOSH_JWT_SECRET、不用 sys-path 注入。
"""

import builtins
import json
import os
import sqlite3
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.kb.cli import (
    _classify_misra_category,
    _collect_source_files,
    _extract_rule_id,
    _handle_ingest_misra,
    _handle_lesson_create,
    _load_ticket,
    _parse_cppcheck_output,
    _resolve_ticket_path,
    handle_kb_command,
    handle_lesson_command,
)
from yuleosh.kb.store import KbStore
from yuleosh.knowledge.cli import (
    _cmd_approve,
    _cmd_audit,
    _cmd_pending,
    _cmd_reject,
    handle_knowledge_command,
)
from yuleosh.knowledge.indexer import KnowledgeIndexer

import yuleosh.cli.onboard as onboard_mod
import yuleosh.kb.cli as kb_cli_mod
import yuleosh.knowledge.cli as knowledge_cli_mod
from yuleosh.cli.onboard import (
    _detect_project_type,
    _progress_bar,
    _spinner_text,
    _step_compliance_check,
    _step_dashboard,
    _step_kg_bootstrap,
    _step_project_info,
    _step_summary,
    cmd_onboard,
    handle_onboard_command,
)
from yuleosh.knowledge_graph import coverage_importer as ci_mod
from yuleosh.knowledge_graph import bootstrap as boot_mod
from yuleosh.knowledge_graph.models import Edge, Node
from yuleosh.knowledge_graph.store import KGStore


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def kb_db(tmp_path, monkeypatch):
    """Isolate KB DB via YULEOSH_KB_DB (OSH_HOME left alone)."""
    monkeypatch.setenv("YULEOSH_KB_DB", str(tmp_path / "kb.db"))
    return tmp_path


@pytest.fixture
def lesson_env(tmp_path, monkeypatch):
    """Isolate KB DB + OSH_HOME for lesson create tests."""
    monkeypatch.setenv("YULEOSH_KB_DB", str(tmp_path / "kb.db"))
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return tmp_path


def _write_ticket(tmp_path, ticket_id, status="open", severity="high",
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
        "  problem_description: >",
        "    KPI 指标超阈值告警",
        "  root_cause: >",
        "    新增代码未经过静态检查",
        "  recommended_actions: >",
        "    1) 运行 MISRA 检查; 2) 修复高严重度违规",
    ]
    if extra:
        for k, v in extra.items():
            lines.append(f"  {k}: {v}")
    lines.append("...")
    (tickets_dir / f"{ticket_id}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_kg_store():
    """Reset the KG store singleton before/after each test."""
    KGStore.reset()
    yield
    KGStore.reset()


@pytest.fixture
def kg_store():
    """A fresh in-memory KGStore (not registered in the singleton map)."""
    store = KGStore.__new__(KGStore, "phase10")
    store.db_path = ":memory:"
    store.conn = sqlite3.connect(":memory:")
    store.conn.row_factory = sqlite3.Row
    store._migrate()
    yield store
    store.conn.close()


# ═══════════════════════════════════════════════════════════════════════
# kb/cli.py — handle_kb_command 子命令分发
# ═══════════════════════════════════════════════════════════════════════

class TestKbHandleCommand:
    def test_kb_list_empty(self, kb_db, capsys):
        rc = handle_kb_command(Namespace(kb_sub="list", limit=20, offset=0))
        assert rc == 0
        assert "No articles found." in capsys.readouterr().out

    def test_kb_list_with_articles(self, kb_db, capsys):
        store = KbStore()
        store.create_article({"title": "Brake Spec", "content": "x" * 130,
                              "source": "manual", "source_ref": "r1", "tags": "brake"})
        rc = handle_kb_command(Namespace(kb_sub="list", limit=20, offset=0))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Brake Spec" in out
        assert "[brake]" in out        # tags
        assert "(manual)" in out       # source
        assert "1 article(s)" in out

    def test_kb_create(self, kb_db, capsys):
        rc = handle_kb_command(Namespace(
            kb_sub="create", title="New Article", content="body",
            source="import", source_ref="ref-1", tags="t1,t2"))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Article created" in out
        a = KbStore().list_articles()[0]
        assert a.title == "New Article"
        assert a.source_ref == "ref-1"
        assert a.tags == "t1,t2"

    def test_kb_search_found(self, kb_db, capsys):
        KbStore().create_article({"title": "Brake FMEA", "content": "hello world",
                                  "source": "manual", "tags": ""})
        rc = handle_kb_command(Namespace(kb_sub="search", query="brake", limit=20))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Search results for 'brake'" in out
        assert "Brake FMEA" in out

    def test_kb_search_no_results(self, kb_db, capsys):
        rc = handle_kb_command(Namespace(kb_sub="search", query="zzz", limit=20))
        out = capsys.readouterr().out
        assert rc == 0
        assert "No results for 'zzz'." in out

    def test_kb_lessons_empty(self, kb_db, capsys):
        rc = handle_kb_command(Namespace(
            kb_sub="lessons", project="", severity="", ticket="", limit=20))
        assert rc == 0
        assert "No lessons found." in capsys.readouterr().out

    def test_kb_lessons_with_data(self, kb_db, capsys):
        KbStore().create_lesson({
            "title": "Lesson One", "problem": "p" * 130, "solution": "s",
            "root_cause": "rc", "severity": "high", "project_id": "BCM",
            "ticket_id": "IMP-1", "requirement_id": "REQ-1"})
        rc = handle_kb_command(Namespace(
            kb_sub="lessons", project="", severity="", ticket="", limit=20))
        out = capsys.readouterr().out
        assert rc == 0
        assert "Lesson One" in out
        assert "[BCM]" in out
        assert "[ticket: IMP-1]" in out
        assert "[req: REQ-1]" in out
        assert "Severity: high" in out

    def test_kb_lesson_subcommand_dispatches(self, kb_db, capsys):
        """kb lesson (without sub-subcommand) → usage + rc 1 (covers 245-246)."""
        rc = handle_kb_command(Namespace(kb_sub="lesson"))
        assert rc == 1
        assert "Usage: yuleosh lesson create" in capsys.readouterr().out

    def test_kb_fmea_empty(self, kb_db, capsys):
        rc = handle_kb_command(Namespace(kb_sub="fmea", sort="rpn", asc=False, limit=20))
        assert rc == 0
        assert "No FMEA entries found." in capsys.readouterr().out

    def test_kb_fmea_with_data(self, kb_db, capsys):
        KbStore().create_fmea({
            "item": "brake_pedal", "failure_mode": "no response", "effect": "crash",
            "cause": "worn seal", "severity": 9, "occurence": 5, "detection": 3,
            "rpn": 135, "recommendation": "replace seal"})
        rc = handle_kb_command(Namespace(kb_sub="fmea", sort="rpn", asc=False, limit=20))
        out = capsys.readouterr().out
        assert rc == 0
        assert "brake_pedal" in out
        assert "S:9 O:5 D:3  RPN: 135" in out

    def test_kb_fmea_asc_sort(self, kb_db, capsys):
        KbStore().create_fmea({"item": "x", "failure_mode": "fm", "effect": "ef",
                               "cause": "c", "severity": 1, "occurence": 1,
                               "detection": 1, "rpn": 1, "recommendation": "r"})
        rc = handle_kb_command(Namespace(kb_sub="fmea", sort="severity", asc=True, limit=20))
        assert rc == 0
        assert "sorted by severity" in capsys.readouterr().out


class TestKbTicketLoadingEdgeCases:
    def test_resolve_ticket_path_without_osh_home_uses_cwd(self, tmp_path, monkeypatch):
        """OSH_HOME unset → cwd candidate used (covers 207->209)."""
        monkeypatch.delenv("OSH_HOME", raising=False)
        cwd_dir = tmp_path / "cwd"
        (cwd_dir / "improvement_tickets").mkdir(parents=True)
        (cwd_dir / "improvement_tickets" / "IMP-CWD.yaml").write_text("x")
        monkeypatch.chdir(cwd_dir)
        p = _resolve_ticket_path("IMP-CWD")
        assert p == cwd_dir / "improvement_tickets" / "IMP-CWD.yaml"

    def test_resolve_ticket_path_osh_home_miss_then_cwd_hit(self, tmp_path, monkeypatch):
        """OSH_HOME candidate missing → falls through to cwd candidate."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path / "empty_home"))
        cwd_dir = tmp_path / "cwd2"
        (cwd_dir / "improvement_tickets").mkdir(parents=True)
        (cwd_dir / "improvement_tickets" / "IMP-FALL.yaml").write_text("x")
        monkeypatch.chdir(cwd_dir)
        p = _resolve_ticket_path("IMP-FALL")
        assert p == cwd_dir / "improvement_tickets" / "IMP-FALL.yaml"

    def test_load_ticket_invalid_yaml_raises_value_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        (tmp_path / "improvement_tickets").mkdir()
        (tmp_path / "improvement_tickets" / "IMP-BAD.yaml").write_text(
            "improvement_ticket: [unclosed\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML 解析失败"):
            _load_ticket("IMP-BAD")

    def test_load_ticket_missing_node_raises_value_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        (tmp_path / "improvement_tickets").mkdir()
        (tmp_path / "improvement_tickets" / "IMP-NODE.yaml").write_text(
            "foo: bar\n", encoding="utf-8")
        with pytest.raises(ValueError, match="缺少 improvement_ticket 节点"):
            _load_ticket("IMP-NODE")

    def test_handle_lesson_command_usage(self, capsys):
        rc = handle_lesson_command(Namespace(lesson_sub=None))
        assert rc == 1
        assert "Usage: yuleosh lesson create" in capsys.readouterr().out

    def test_lesson_create_indexer_hook_returns_none(self, lesson_env, capsys):
        """Indexer record() returns None (duplicate) → hook silently skipped."""
        _write_ticket(lesson_env, "IMP-HOOK-NONE")
        with mock.patch("yuleosh.knowledge.indexer.KnowledgeIndexer") as m_cls:
            m_cls.return_value.record.return_value = None
            rc = _handle_lesson_create(Namespace(
                ticket="IMP-HOOK-NONE", req="", title="", severity=""))
        assert rc == 0
        assert "已自动入待生效" not in capsys.readouterr().out

    def test_lesson_create_indexer_hook_raises_nonfatal(self, lesson_env, capsys):
        """Indexer hook failure is non-fatal for lesson creation."""
        _write_ticket(lesson_env, "IMP-HOOK-RAISE")
        with mock.patch("yuleosh.knowledge.indexer.KnowledgeIndexer") as m_cls:
            m_cls.return_value.record.side_effect = RuntimeError("boom")
            rc = _handle_lesson_create(Namespace(
                ticket="IMP-HOOK-RAISE", req="", title="", severity=""))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Lesson created" in out


# ═══════════════════════════════════════════════════════════════════════
# kb/cli.py — cppcheck / MISRA 解析与 ingest
# ═══════════════════════════════════════════════════════════════════════

class TestParseCppcheckOutput:
    def test_empty_and_skip_lines_ignored(self):
        text = "\n\nChecking src/a.c ...\nActive checkers: 4\n"
        assert _parse_cppcheck_output(text) == []

    def test_unmatched_line_ignored(self):
        assert _parse_cppcheck_output("just some random text\n") == []

    def test_colon_format_with_col_and_rule(self):
        text = "src/a.c:5:5: error: msg [misra-c2012-17.7]\n"
        v = _parse_cppcheck_output(text)
        assert len(v) == 1
        assert v[0]["rule_id"] == "misra-c2023-17.7"
        assert v[0]["file"] == "src/a.c"
        assert v[0]["line"] == 5
        assert v[0]["col"] == 5
        assert v[0]["severity"] == "error"

    def test_colon_format_without_col(self):
        text = "src/b.c:9: warning: msg (17.7)\n"
        v = _parse_cppcheck_output(text)
        assert len(v) == 1
        assert v[0]["col"] == 0
        assert v[0]["rule_id"] == "misra-c2023-17.7"

    def test_bracket_format(self):
        text = "[src/c.c:3:2] (error) msg [misra-c2012-10.1]\n"
        v = _parse_cppcheck_output(text)
        assert len(v) == 1
        assert v[0]["rule_id"] == "misra-c2023-10.1"
        assert v[0]["line"] == 3

    def test_diagnostic_id_fallback_maps_to_misra(self):
        """cppcheck diagnostic id in trailing brackets → CPPCHECK_TO_MISRA_MAP."""
        text = "src/d.c:1: error: msg [staticness]\n"
        v = _parse_cppcheck_output(text)
        assert len(v) == 1
        assert v[0]["rule_id"] == "misra-c2023-8.7"

    def test_unmapped_diagnostic_id_skipped(self):
        text = "src/e.c:1: error: msg [someUnknownDiag]\n"
        assert _parse_cppcheck_output(text) == []


class TestExtractRuleId:
    def test_bracket_dir_rule(self):
        assert _extract_rule_id("[misra-c2023-dir-4.2]") == "misra-c2023-dir-4.2"

    def test_bracket_plain_rule(self):
        assert _extract_rule_id("[misra-c2012-17.7]") == "misra-c2023-17.7"

    def test_paren_rule(self):
        assert _extract_rule_id("msg (17.7)") == "misra-c2023-17.7"

    def test_paren_dir_rule(self):
        assert _extract_rule_id("msg (dir-4.2)") == "misra-c2023-dir-4.2"

    def test_misra_text_rule(self):
        assert _extract_rule_id("MISRA C2012-17.7 violation") == "misra-c2023-17.7"

    def test_misra_dir_text_rule(self):
        assert _extract_rule_id("MISRA dir-4.2 violation") == "misra-c2023-dir-4.2"

    def test_rule_text_with_subrule(self):
        assert _extract_rule_id("Rule 17.7") == "misra-c2023-17.7"

    def test_rule_text_integer_fallback(self):
        assert _extract_rule_id("Rule: 17") == "misra-c2023-17.0"

    def test_no_match_returns_none(self):
        assert _extract_rule_id("nothing here") is None


class TestClassifyMisraCategory:
    def test_none_is_advisory(self):
        assert _classify_misra_category(None) == "advisory"

    def test_no_numeric_part_is_advisory(self):
        assert _classify_misra_category("misra-c2023-dir-4.2") == "required"
        assert _classify_misra_category("abc") == "advisory"

    def test_low_number_is_required(self):
        assert _classify_misra_category("misra-c2023-10.3") == "required"

    def test_high_number_is_advisory(self):
        assert _classify_misra_category("misra-c2023-17.7") == "advisory"

    def test_float_conversion_error_is_advisory(self, monkeypatch):
        def _bad_float(*a, **k):
            raise ValueError("no float for you")
        monkeypatch.setattr(builtins, "float", _bad_float)
        assert _classify_misra_category("misra-c2023-10.3") == "advisory"


class TestIngestMisra:
    def _args(self, **kw):
        base = dict(kb_sub="ingest-misra", input=None, files=None,
                    src_dir="src", dry_run=False)
        base.update(kw)
        return Namespace(**base)

    def test_input_file_missing(self, kb_db, capsys):
        rc = _handle_ingest_misra(self._args(input="nope.txt"), KbStore())
        assert rc == 1
        assert "Input file not found" in capsys.readouterr().err

    def test_input_file_creates_article(self, kb_db, tmp_path, capsys):
        report = tmp_path / "misra.txt"
        report.write_text("src/a.c:5:5: error: msg [misra-c2012-10.1]\n", encoding="utf-8")
        rc = _handle_ingest_misra(self._args(input=str(report)), KbStore())
        out = capsys.readouterr().out
        assert rc == 0
        assert "Ingested 1 violation(s)" in out
        articles = KbStore().list_articles()
        assert len(articles) == 1
        assert articles[0].title.startswith("MISRA-misra-c2023-10.1:")
        assert "misra,required,rule-misra-c2023-10-1" in articles[0].tags

    def test_no_source_files_found(self, kb_db, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        rc = _handle_ingest_misra(self._args(), KbStore())
        assert rc == 1
        assert "No source files found" in capsys.readouterr().err

    def test_explicit_files_cppcheck_empty_output(self, kb_db, capsys):
        with mock.patch.object(kb_cli_mod, "_run_cppcheck_for_ingest", return_value=""):
            rc = _handle_ingest_misra(self._args(files=["a.c"]), KbStore())
        assert rc == 1

    def test_no_violations_parsed(self, kb_db, capsys):
        with mock.patch.object(kb_cli_mod, "_run_cppcheck_for_ingest",
                               return_value="Checking src/a.c ...\nActive checkers: 1\n"):
            rc = _handle_ingest_misra(self._args(files=["a.c"]), KbStore())
        out = capsys.readouterr().out
        assert rc == 0
        assert "No MISRA violations found." in out

    def test_dry_run_skips_write(self, kb_db, capsys):
        with mock.patch.object(kb_cli_mod, "_run_cppcheck_for_ingest", return_value="x"), \
             mock.patch.object(kb_cli_mod, "_parse_cppcheck_output",
                               return_value=[{"rule_id": "misra-c2023-10.1", "file": "a.c",
                                              "line": 1, "severity": "error",
                                              "message": "m"}]):
            rc = _handle_ingest_misra(self._args(files=["a.c"], dry_run=True), KbStore())
        out = capsys.readouterr().out
        assert rc == 0
        assert "Dry-run mode" in out
        assert KbStore().count_articles() == 0

    def test_unknown_rule_id_tags(self, kb_db, capsys):
        with mock.patch.object(kb_cli_mod, "_run_cppcheck_for_ingest", return_value="x"), \
             mock.patch.object(kb_cli_mod, "_parse_cppcheck_output",
                               return_value=[{"rule_id": None, "file": "a.c",
                                              "line": 1, "severity": "error",
                                              "message": "m"}]):
            rc = _handle_ingest_misra(self._args(files=["a.c"]), KbStore())
        assert rc == 0
        capsys.readouterr()
        assert KbStore().list_articles()[0].tags == "misra,advisory"


class TestRunCppcheckAndCollect:
    def test_run_cppcheck_success(self):
        result = mock.Mock(returncode=0, stderr="err-out", stdout="std-out")
        with mock.patch.object(kb_cli_mod.subprocess, "run", return_value=result) as m:
            out = kb_cli_mod._run_cppcheck_for_ingest(["a.c"])
        assert out == "err-out\nstd-out"
        assert m.call_args.args[0][0] == "cppcheck"

    def test_run_cppcheck_not_found(self, capsys):
        with mock.patch.object(kb_cli_mod.subprocess, "run",
                               side_effect=FileNotFoundError):
            out = kb_cli_mod._run_cppcheck_for_ingest(["a.c"])
        assert out == ""
        assert "cppcheck not found" in capsys.readouterr().err

    def test_run_cppcheck_timeout(self, capsys):
        with mock.patch.object(kb_cli_mod.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("cppcheck", 120)):
            out = kb_cli_mod._run_cppcheck_for_ingest(["a.c"])
        assert out == ""
        assert "cppcheck timed out" in capsys.readouterr().err

    def test_collect_source_files_with_project_root(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.c").write_text("int x;")
        (tmp_path / "src" / "b.h").write_text("")
        files = _collect_source_files("src", str(tmp_path))
        assert sorted(Path(f).name for f in files) == ["a.c", "b.h"]

    def test_collect_source_files_missing_dir(self, tmp_path):
        assert _collect_source_files("src", str(tmp_path / "nope")) == []


# ═══════════════════════════════════════════════════════════════════════
# knowledge/cli.py — pending / approve / reject / audit
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def knowledge_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return tmp_path


def _kargs(tmp_path, **kw):
    base = dict(osh_home=str(tmp_path))
    base.update(kw)
    return Namespace(**base)


class TestKnowledgeCli:
    def test_unknown_subcommand_usage(self, knowledge_env, capsys):
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="bogus"))
        assert rc == 2
        assert "Usage: yuleosh knowledge" in capsys.readouterr().err

    def test_pending_empty(self, knowledge_env, capsys):
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="pending"))
        assert rc == 0
        assert "没有待生效沉淀" in capsys.readouterr().out

    def test_pending_with_items(self, knowledge_env, capsys):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        entry = idx.record(kind="lesson_create", content="lesson about brakes",
                           source="ticket:IMP-1", meta={"ticket_id": "IMP-1"})
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="pending"))
        out = capsys.readouterr().out
        assert rc == 0
        assert "lesson_create" in out
        assert entry["hash"] in out

    def test_approve_requires_item_or_all(self, knowledge_env, capsys):
        rc = _cmd_approve(KnowledgeIndexer(project_dir=knowledge_env), None, False)
        assert rc == 2
        assert "请指定条目" in capsys.readouterr().err

    def test_approve_no_match(self, knowledge_env, capsys):
        rc = _cmd_approve(KnowledgeIndexer(project_dir=knowledge_env), "deadbeef", False)
        assert rc == 1
        assert "没有匹配的待生效条目" in capsys.readouterr().out

    def test_approve_by_hash(self, knowledge_env, capsys):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        entry = idx.record(kind="memory_remember", content="remember this")
        rc = _cmd_approve(idx, entry["hash"], False)
        out = capsys.readouterr().out
        assert rc == 0
        assert "已确认 1 条" in out
        assert idx.list_pending() == []
        assert len(idx.list_active()) == 1

    def test_approve_all(self, knowledge_env, capsys):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        idx.record(kind="kb_article_created", content="a1")
        idx.record(kind="kb_article_created", content="a2")
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="approve",
                                             item=None, all=True))
        assert rc == 0
        assert "已确认 2 条" in capsys.readouterr().out

    def test_reject_requires_item_or_all(self, knowledge_env, capsys):
        rc = _cmd_reject(KnowledgeIndexer(project_dir=knowledge_env), None, False)
        assert rc == 2
        assert "请指定条目" in capsys.readouterr().err

    def test_reject_no_match(self, knowledge_env, capsys):
        rc = _cmd_reject(KnowledgeIndexer(project_dir=knowledge_env), "deadbeef", False)
        assert rc == 1
        assert "没有匹配的待生效条目" in capsys.readouterr().out

    def test_reject_by_index(self, knowledge_env, capsys):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        entry = idx.record(kind="skill_created", content="a skill")
        rc = _cmd_reject(idx, "0", False)
        out = capsys.readouterr().out
        assert rc == 0
        assert "已否决 1 条" in out
        assert idx.list_pending() == []
        assert entry["hash"] not in [a["hash"] for a in idx.list_active()]

    def test_audit_empty(self, knowledge_env, capsys):
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="audit", limit=50))
        assert rc == 0
        assert "审计日志为空" in capsys.readouterr().out

    def test_audit_with_entries(self, knowledge_env, capsys):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        entry = idx.record(kind="lesson_create", content="audit me")
        idx.approve(item_id=entry["hash"])
        rc = handle_knowledge_command(_kargs(knowledge_env, knowledge_sub="audit", limit=10))
        out = capsys.readouterr().out
        assert rc == 0
        assert "approve" in out
        assert "lesson_create" in out

    def test_audit_limit_respected(self, knowledge_env):
        idx = KnowledgeIndexer(project_dir=knowledge_env)
        entries = idx.audit_log(limit=5)
        assert isinstance(entries, list)
        assert len(entries) == 0


# ═══════════════════════════════════════════════════════════════════════
# cli/onboard.py
# ═══════════════════════════════════════════════════════════════════════

class TestOnboardHelpers:
    def test_progress_bar_zero_total(self):
        assert _progress_bar(0, 0) == ""

    def test_progress_bar_normal(self):
        bar = _progress_bar(15, 30, width=10, suffix="done")
        assert "%" in bar
        assert "done" in bar

    def test_spinner_text_done(self, capsys):
        _spinner_text("KG 初始化", done=True)
        assert "完成" in capsys.readouterr().out

    def test_spinner_text_running(self, capsys):
        _spinner_text("KG 初始化")
        assert "⏳" in capsys.readouterr().out

    def test_detect_project_type_missing_dir(self, tmp_path):
        res = _detect_project_type(str(tmp_path / "ghost"))
        assert res == {"project_type": "unknown", "detected_frameworks": [],
                       "source_count": 0, "test_count": 0}

    def test_detect_project_type_mcu(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.c").write_text("void f(void) { S32K312 }")
        res = _detect_project_type(str(tmp_path))
        assert res["project_type"] == "mcu"
        assert "MCU (S32K312)" in res["detected_frameworks"]

    def test_detect_project_type_autosar_second_file_skips(self, tmp_path):
        """Second AUTOSAR file hits the 'already detected' branch."""
        for i in range(2):
            (tmp_path / f"f{i}.c").write_text("int Std_Types.h;")
        res = _detect_project_type(str(tmp_path))
        assert res["project_type"] == "autosar"
        assert res["detected_frameworks"].count("AUTOSAR CP") == 1

    def test_detect_project_type_unreadable_file(self, tmp_path):
        f = tmp_path / "unreadable.c"
        f.write_text("int x;")
        os.chmod(f, 0)
        try:
            res = _detect_project_type(str(tmp_path))
        finally:
            os.chmod(f, 0o644)
        assert "source_count" in res

    def test_detect_project_type_test_frameworks(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_fw1.py").write_text("def test_a():\n    assert_int_equal(1, 1)\n    import pytest\n")
        (tests / "test_fw2.py").write_text("def test_b():\n    CU_ASSERT(1)\n")
        res = _detect_project_type(str(tmp_path))
        fw = res["detected_frameworks"]
        assert "CUnit" in fw
        assert "cmocka" in fw
        assert "pytest" in fw
        assert res["project_type"] == "python"


class TestOnboardSteps:
    def test_step_project_info_eof_defaults(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(builtins, "input", lambda *a: (_ for _ in ()).throw(EOFError()))
        info = _step_project_info(None, None, None)
        assert info == {"name": "my-project", "project_type": "migration",
                        "oem_template": "generic"}

    def test_step_project_info_invalid_inputs_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(builtins, "input", lambda *a: "bogus")
        info = _step_project_info(None, None, None)
        assert info["project_type"] == "migration"
        assert info["oem_template"] == "generic"

    def test_step_kg_bootstrap_success(self, tmp_path, capsys):
        fake_store = mock.Mock()
        fake_store.get_all_nodes.return_value = [1, 2, 3]
        fake_store.get_all_edges.return_value = [1, 2]
        with mock.patch("yuleosh.knowledge_graph.get_store", return_value=fake_store), \
             mock.patch("yuleosh.knowledge_graph.coverage_importer.import_coverage_from_default") as m_cov, \
             mock.patch("yuleosh.knowledge_graph.code_scanner.scan_directory") as m_scan:
            stats = _step_kg_bootstrap(str(tmp_path), {"source_count": 5, "test_count": 2})
        assert stats == {"nodes": 3, "edges": 2}
        m_cov.assert_called_once()
        m_scan.assert_called_once_with(fake_store, str(tmp_path))
        out = capsys.readouterr().out
        assert "节点: 3" in out

    def test_step_kg_bootstrap_count_iterable(self, tmp_path):
        fake_store = mock.Mock()
        fake_store.get_all_nodes.return_value = iter([1, 2])
        fake_store.get_all_edges.return_value = iter([1])
        with mock.patch("yuleosh.knowledge_graph.get_store", return_value=fake_store), \
             mock.patch("yuleosh.knowledge_graph.coverage_importer.import_coverage_from_default"), \
             mock.patch("yuleosh.knowledge_graph.code_scanner.scan_directory"):
            stats = _step_kg_bootstrap(str(tmp_path), {"source_count": 5, "test_count": 2})
        assert stats == {"nodes": 2, "edges": 1}

    def test_step_kg_bootstrap_stats_exception_fallback(self, tmp_path):
        fake_store = mock.Mock()
        fake_store.get_all_nodes.side_effect = RuntimeError("db locked")
        with mock.patch("yuleosh.knowledge_graph.get_store", return_value=fake_store), \
             mock.patch("yuleosh.knowledge_graph.coverage_importer.import_coverage_from_default"), \
             mock.patch("yuleosh.knowledge_graph.code_scanner.scan_directory"):
            stats = _step_kg_bootstrap(str(tmp_path), {"source_count": 5, "test_count": 2})
        assert stats == {"nodes": 7, "edges": 5}

    def test_step_kg_bootstrap_import_error(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setitem(sys.modules, "yuleosh.knowledge_graph", None)
        stats = _step_kg_bootstrap(str(tmp_path), {"source_count": 0, "test_count": 0})
        assert stats == {"nodes": 0, "edges": 0}
        assert "KG 模块不可用" in capsys.readouterr().out

    def test_step_kg_bootstrap_generic_error(self, tmp_path, capsys):
        with mock.patch("yuleosh.knowledge_graph.get_store",
                        side_effect=RuntimeError("boom")):
            stats = _step_kg_bootstrap(str(tmp_path), {"source_count": 0, "test_count": 0})
        assert stats == {"nodes": 0, "edges": 0}
        assert "KG 初始化失败" in capsys.readouterr().out

    def test_step_compliance_report_save_failure(self, tmp_path, capsys):
        report = {"summary": {"passed": 3, "partial": 1, "failed": 0, "total_bps": 4},
                  "swe_sections": {"swe.1": {"id": "SWE.1",
                                             "base_practices": [{"status": "✅"},
                                                                {"status": "❌"}]}}}
        fake_checker = mock.Mock()
        fake_checker.run.return_value = report
        fake_checker.generate_report_markdown.side_effect = OSError("disk full")
        with mock.patch("yuleosh.compliance.compliance_checker.ComplianceChecker",
                        return_value=fake_checker):
            summary = _step_compliance_check(str(tmp_path))
        assert summary == report["summary"]
        assert "合规报告保存失败" in capsys.readouterr().out

    def test_step_dashboard_generate_evidence_failure(self, tmp_path, capsys):
        with mock.patch("yuleosh.evidence.pack.generate_evidence",
                        side_effect=RuntimeError("boom")):
            info = _step_dashboard(str(tmp_path))
        assert info["status"] == "pending"
        assert "面板生成失败" in capsys.readouterr().out

    def test_step_dashboard_trend_failure(self, tmp_path, capsys):
        with mock.patch("yuleosh.ci.coverage_trend.show_coverage_trend",
                        side_effect=RuntimeError("no data")):
            _step_dashboard(str(tmp_path))
        assert "覆盖趋势将在首次 CI 运行后可用" in capsys.readouterr().out

    def test_step_dashboard_config_write_failure(self, tmp_path, monkeypatch, capsys):
        def _bad_dumps(*a, **k):
            raise RuntimeError("serialize fail")
        monkeypatch.setattr(onboard_mod.json, "dumps", _bad_dumps)
        info = _step_dashboard(str(tmp_path))  # 410-411 except → pass
        assert info["dashboard_url"] == "http://localhost:8080"

    def test_step_summary_no_report(self, tmp_path, capsys):
        result = _step_summary(str(tmp_path), {"name": "p"}, {"project_type": "c"},
                               {"nodes": 0, "edges": 0}, {}, {}, 65.0)
        out = capsys.readouterr().out
        assert "运行 yuleosh ev check --save" in out
        assert result["report_path"] is None
        assert result["elapsed_seconds"] == 65.0
        assert "1m 5s" in out

    def test_step_summary_mcu_hints(self, tmp_path, capsys):
        _step_summary(str(tmp_path), {"name": "p"}, {"project_type": "mcu"},
                      {"nodes": 0, "edges": 0}, {}, {}, 1.0)
        out = capsys.readouterr().out
        assert "检查 MCU 配置文件" in out
        assert "配置 cppcheck MISRA 规则集" in out


class TestOnboardCmd:
    def _patch_steps(self, monkeypatch):
        monkeypatch.setattr(onboard_mod, "_step_project_info",
                            lambda *a, **k: {"name": "demo", "project_type": "new",
                                             "oem_template": "generic"})
        monkeypatch.setattr(onboard_mod, "_step_code_analysis",
                            lambda *a, **k: {"source_count": 0, "test_count": 0,
                                             "detected_frameworks": [],
                                             "project_type": "unknown"})
        monkeypatch.setattr(onboard_mod, "_step_kg_bootstrap",
                            lambda *a, **k: {"nodes": 0, "edges": 0})
        monkeypatch.setattr(onboard_mod, "_step_compliance_check",
                            lambda *a, **k: {"passed": 0})
        monkeypatch.setattr(onboard_mod, "_step_dashboard",
                            lambda *a, **k: {"dashboard_url": "http://localhost:8080",
                                             "status": "pending"})
        monkeypatch.setattr(onboard_mod, "_step_summary", lambda *a, **k: {})

    def test_cmd_onboard_repo_clone(self, tmp_path, monkeypatch, capsys):
        self._patch_steps(monkeypatch)
        with mock.patch.object(onboard_mod.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stderr="")) as m_run:
            result = cmd_onboard(project_dir=str(tmp_path), repo="git@github.com:u/proj.git")
        assert result["project_info"]["name"] == "demo"
        args = m_run.call_args.args[0]
        assert args[:2] == ["git", "clone"]
        assert "已克隆到" in capsys.readouterr().out

    def test_cmd_onboard_repo_clone_timeout(self, tmp_path, monkeypatch):
        self._patch_steps(monkeypatch)
        with mock.patch.object(onboard_mod.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git clone", 120)), \
             pytest.raises(SystemExit):
            cmd_onboard(project_dir=str(tmp_path), repo="https://github.com/u/p.git")

    def test_cmd_onboard_repo_clone_failure(self, tmp_path, monkeypatch):
        self._patch_steps(monkeypatch)
        with mock.patch.object(onboard_mod.subprocess, "run",
                               return_value=mock.Mock(returncode=1, stderr="auth fail")), \
             pytest.raises(SystemExit):
            cmd_onboard(project_dir=str(tmp_path), repo="https://github.com/u/p.git")

    def test_cmd_onboard_repo_dir_exists(self, tmp_path, monkeypatch, capsys):
        self._patch_steps(monkeypatch)
        target = tmp_path / "existing"
        target.mkdir()
        with mock.patch.object(onboard_mod.subprocess, "run") as m_run:
            cmd_onboard(project_dir=str(tmp_path), repo="https://github.com/u/existing.git")
        m_run.assert_not_called()
        assert "目录已存在" in capsys.readouterr().out

    def test_handle_onboard_command_dispatch(self, tmp_path, monkeypatch):
        monkeypatch.setattr(onboard_mod, "_step_code_analysis",
                            lambda *a, **k: {"source_count": 0, "test_count": 0,
                                             "detected_frameworks": [],
                                             "project_type": "unknown"})
        monkeypatch.setattr(onboard_mod, "_step_kg_bootstrap",
                            lambda *a, **k: {"nodes": 0, "edges": 0})
        monkeypatch.setattr(onboard_mod, "_step_compliance_check",
                            lambda *a, **k: {"passed": 0})
        monkeypatch.setattr(onboard_mod, "_step_dashboard",
                            lambda *a, **k: {"dashboard_url": "http://localhost:8080",
                                             "status": "pending"})
        monkeypatch.setattr(onboard_mod, "_step_summary", lambda *a, **k: {})
        args = Namespace(dir=str(tmp_path), name="n", project_type="new",
                         oem_template="generic", repo=None)
        result = handle_onboard_command(args)
        assert result["project_info"]["name"] == "n"
        assert "analysis" in result


# ═══════════════════════════════════════════════════════════════════════
# knowledge_graph/coverage_importer.py
# ═══════════════════════════════════════════════════════════════════════

def _make_coverage_db(path, has_arcs=False, files=None, lines=None, arcs=None):
    """Build a .coverage-style SQLite db at *path*."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER, path TEXT);
        CREATE TABLE line (file_id INTEGER, lineno INTEGER);
        CREATE TABLE arc (file_id INTEGER, fromno INTEGER, tono INTEGER);
    """)
    conn.execute("INSERT INTO meta VALUES ('version', '7.0.0')")
    conn.execute("INSERT INTO meta VALUES ('has_arcs', ?)", ("1" if has_arcs else "0",))
    files = files or [("f1", "/proj/src/mod.py")]
    for fid, path_ in files:
        conn.execute("INSERT INTO file VALUES (?, ?)", (fid, path_))
    if has_arcs:
        for fid, frm, to in (arcs or []):
            conn.execute("INSERT INTO arc VALUES (?, ?, ?)", (fid, frm, to))
    else:
        for fid, lineno in (lines or [(1, 2), (1, 3)]):
            conn.execute("INSERT INTO line VALUES (?, ?)", (fid, lineno))
    conn.commit()
    conn.close()


class TestReadCoverageSqlite:
    def test_missing_db_returns_empty(self, tmp_path, caplog):
        assert ci_mod._read_coverage_sqlite(str(tmp_path / "nope")) == {}

    def test_line_based(self, tmp_path):
        db = tmp_path / ".coverage"
        _make_coverage_db(str(db), files=[("f1", "/proj/src/mod.py")],
                          lines=[("f1", 2), ("f1", 3), ("f2", 99)])
        result = ci_mod._read_coverage_sqlite(str(db))
        assert result == {"/proj/src/mod.py": {2, 3}}  # f2 无 file 行 → 跳过

    def test_arc_based(self, tmp_path):
        db = tmp_path / ".coverage"
        _make_coverage_db(str(db), has_arcs=True,
                          files=[("f1", "/proj/src/mod.py"), ("f2", "/proj/x.py")],
                          arcs=[("f1", 5, 6), ("f1", 0, 7), ("f2", 8, 9), ("f9", 1, 1)])
        result = ci_mod._read_coverage_sqlite(str(db))
        assert result == {"/proj/src/mod.py": {5, 6, 7}, "/proj/x.py": {8, 9}}

    def test_corrupt_db_returns_empty(self, tmp_path, caplog):
        db = tmp_path / ".coverage"
        db.write_text("this is not a sqlite db")
        with caplog.at_level("WARNING"):
            assert ci_mod._read_coverage_sqlite(str(db)) == {}
        assert "Failed to read coverage SQLite DB" in caplog.text


class TestReadCoverageJson:
    def test_missing_json_returns_empty(self, tmp_path):
        assert ci_mod._read_coverage_json(str(tmp_path / "nope.json")) == {}

    def test_valid_json(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({
            "meta": {},
            "files": {
                "/proj/a.py": {"executed_lines": [1, 2]},
                "/proj/b.py": {"executed_lines": []},
                "/proj/c.py": "not-a-dict",
            },
        }))
        result = ci_mod._read_coverage_json(str(p))
        assert result == {"/proj/a.py": {1, 2}}

    def test_top_level_files_dict(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"/proj/a.py": {"executed_lines": [1]}}))
        assert ci_mod._read_coverage_json(str(p)) == {"/proj/a.py": {1}}

    def test_non_dict_data_returns_empty(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps([1, 2, 3]))
        assert ci_mod._read_coverage_json(str(p)) == {}

    def test_corrupt_json_returns_empty(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("{not json")
        assert ci_mod._read_coverage_json(str(p)) == {}


class TestImportCoverage:
    def _seed_code_and_test(self, store, src_rel="src/yuleosh/store.py",
                            tst_rel="tests/test_store.py"):
        cfn_id = store.upsert_node(Node(
            entity_type="code_function",
            entity_id=f"{src_rel}::do_thing",
            label="do_thing",
            properties={"file_path": src_rel, "start_line": 1, "end_line": 10}))
        tfn_id = store.upsert_node(Node(
            entity_type="test_function",
            entity_id=f"{tst_rel}::test_do_thing",
            label="test_do_thing",
            properties={"file_path": tst_rel}))
        return cfn_id, tfn_id

    def test_no_coverage_data(self, kg_store, tmp_path):
        result = ci_mod.import_coverage(kg_store, str(tmp_path / ".coverage"), str(tmp_path))
        assert result == {"files": 0, "covered_functions": 0, "verifies_edges": 0}

    def test_no_code_functions(self, kg_store, tmp_path):
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({"files": {f"{tmp_path}/src/mod.py": {"executed_lines": [1]}}}))
        result = ci_mod.import_coverage(kg_store, str(cov), str(tmp_path))
        assert result["files"] == 1
        assert result["covered_functions"] == 0

    def test_full_flow_creates_verifies_edge(self, kg_store, tmp_path):
        cfn_id, tfn_id = self._seed_code_and_test(kg_store)
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({
            "files": {f"{tmp_path}/src/yuleosh/store.py": {"executed_lines": [1, 2, 3]}}}))
        result = ci_mod.import_coverage(kg_store, str(cov), str(tmp_path))
        assert result["files"] == 1
        assert result["covered_functions"] == 1
        assert result["verifies_edges"] == 1
        edges = kg_store.get_outgoing_edges(tfn_id)
        assert len(edges) == 1
        edge, target = edges[0]
        assert edge.edge_type == "verifies"
        assert target.id == cfn_id
        assert edge.properties["covered_lines"] == [1, 2, 3]
        assert edge.properties["source"] == "coverage_importer"

    def test_uncovered_lines_produce_no_edges(self, kg_store, tmp_path):
        self._seed_code_and_test(kg_store)
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({
            "files": {f"{tmp_path}/src/yuleosh/store.py": {"executed_lines": [50, 60]}}}))
        result = ci_mod.import_coverage(kg_store, str(cov), str(tmp_path))
        assert result == {"files": 1, "covered_functions": 0, "verifies_edges": 0}

    def test_path_outside_project_kept_as_abs(self, kg_store, tmp_path):
        project_base = str(tmp_path / "proj")
        abs_src = str(tmp_path / "elsewhere" / "mod.py")
        kg_store.upsert_node(Node(
            entity_type="code_function", entity_id=f"{abs_src}::f",
            label="f", properties={"file_path": abs_src, "start_line": 1, "end_line": 5}))
        kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_mod.py::tf",
            label="tf", properties={"file_path": "tests/test_mod.py"}))
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({"files": {abs_src: {"executed_lines": [2]}}}))
        result = ci_mod.import_coverage(kg_store, str(cov), project_base)
        assert result["verifies_edges"] == 1

    def test_json_coverage_dispatch(self, kg_store, tmp_path):
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({"files": {}}))
        with mock.patch.object(ci_mod, "_read_coverage_json", return_value={}) as mj, \
             mock.patch.object(ci_mod, "_read_coverage_sqlite") as ms:
            ci_mod.import_coverage(kg_store, str(cov), str(tmp_path))
        mj.assert_called_once()
        ms.assert_not_called()


class TestInferTestToSourceMapping:
    def test_method1_requirement_covers_both(self, kg_store):
        req_id = kg_store.upsert_node(Node(entity_type="requirement", entity_id="RS-1",
                                           label="RS-1"))
        tf_id = kg_store.upsert_node(Node(entity_type="test_file",
                                          entity_id="tests/test_engine.py",
                                          label="tests/test_engine.py"))
        cf_id = kg_store.upsert_node(Node(entity_type="code_file",
                                          entity_id="src/engine.py",
                                          label="src/engine.py"))
        kg_store.upsert_edge(Edge(source_id=req_id, target_id=tf_id, edge_type="covers"))
        kg_store.upsert_edge(Edge(source_id=req_id, target_id=cf_id, edge_type="covers"))
        mapping = ci_mod._infer_test_to_source_mapping(kg_store, ".")
        assert mapping.get("tests/test_engine.py") == "src/engine.py"

    def test_method2_naming_convention(self, kg_store):
        kg_store.upsert_node(Node(entity_type="code_file", entity_id="src/yuleosh/foo.py",
                                  label="src/yuleosh/foo.py"))
        kg_store.upsert_node(Node(entity_type="test_file", entity_id="tests/test_foo.py",
                                  label="tests/test_foo.py"))
        mapping = ci_mod._infer_test_to_source_mapping(kg_store, ".")
        assert mapping.get("tests/test_foo.py") == "src/yuleosh/foo.py"

    def test_method2_test_prefix_and_alt_path(self, kg_store):
        kg_store.upsert_node(Node(entity_type="code_file", entity_id="src/yuleosh/bar.py",
                                  label="src/yuleosh/bar.py"))
        # testbar.py → bar.py（test 前缀，无下划线）
        kg_store.upsert_node(Node(entity_type="test_file", entity_id="tests/testbar.py",
                                  label="tests/testbar.py"))
        # tests/ 父目录 → src/yuleosh/<name>
        kg_store.upsert_node(Node(entity_type="test_file", entity_id="tests/test_bar.py",
                                  label="tests/test_bar.py"))
        mapping = ci_mod._infer_test_to_source_mapping(kg_store, ".")
        assert mapping.get("tests/testbar.py") == "src/yuleosh/bar.py"
        assert mapping.get("tests/test_bar.py") == "src/yuleosh/bar.py"

    def test_unmatching_test_file_skipped(self, kg_store):
        kg_store.upsert_node(Node(entity_type="test_file", entity_id="tests/test_zzz.py",
                                  label="tests/test_zzz.py"))
        kg_store.upsert_node(Node(entity_type="code_file", entity_id="src/aaa.py",
                                  label="src/aaa.py"))
        assert ci_mod._infer_test_to_source_mapping(kg_store, ".") == {}

    def test_existing_mapping_not_overwritten(self, kg_store):
        kg_store.upsert_node(Node(entity_type="code_file", entity_id="src/foo.py",
                                  label="src/foo.py"))
        kg_store.upsert_node(Node(entity_type="test_file", entity_id="tests/test_foo.py",
                                  label="tests/test_foo.py"))
        kg_store.upsert_node(Node(entity_type="requirement", entity_id="RS-2", label="RS-2"))
        # 先跑一次建立 mapping
        m1 = ci_mod._infer_test_to_source_mapping(kg_store, ".")
        # 第二次：mapping 已存在 → method2 跳过（348-349），且不被覆盖
        m2 = ci_mod._infer_test_to_source_mapping(kg_store, ".")
        assert m1 == m2
        assert m2["tests/test_foo.py"] == "src/foo.py"


class TestFindRelevantTestFunctions:
    def test_strategy1_inverted_mapping(self, kg_store):
        tfn_id = kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_a.py::tf",
            label="tf", properties={"file_path": "tests/test_a.py"}))
        mapping = {"tests/test_a.py": "src/a.py"}
        tests_by_file = {"tests/test_a.py": [kg_store.get_node("test_function",
                                                               "tests/test_a.py::tf")]}
        result = ci_mod._find_relevant_test_functions(
            kg_store, "src/a.py", mapping, tests_by_file)
        assert [n.id for n in result] == [tfn_id]

    def test_strategy2_requirement_covers_both(self, kg_store):
        tfn_id = kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_b.py::tf",
            label="tf", properties={"file_path": "tests/test_b.py"}))
        req_id = kg_store.upsert_node(Node(entity_type="requirement", entity_id="RS-3",
                                           label="RS-3"))
        cf_id = kg_store.upsert_node(Node(entity_type="code_file",
                                          entity_id="src/b.py", label="src/b.py"))
        kg_store.upsert_edge(Edge(source_id=req_id, target_id=tfn_id, edge_type="covers"))
        kg_store.upsert_edge(Edge(source_id=req_id, target_id=cf_id, edge_type="covers"))
        result = ci_mod._find_relevant_test_functions(kg_store, "src/b.py", {}, {})
        assert [n.id for n in result] == [tfn_id]

    def test_strategy3_module_name_match(self, kg_store):
        tfn_id = kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_store.py::tf",
            label="tf", properties={"file_path": "tests/test_store.py"}))
        result = ci_mod._find_relevant_test_functions(kg_store, "src/yuleosh/store.py", {}, {})
        assert [n.id for n in result] == [tfn_id]

    def test_strategy3_no_underscore_variant(self, kg_store):
        tfn_id = kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/teststore.py::tf",
            label="tf", properties={"file_path": "tests/teststore.py"}))
        result = ci_mod._find_relevant_test_functions(kg_store, "src/yuleosh/store.py", {}, {})
        assert [n.id for n in result] == [tfn_id]

    def test_no_match_returns_empty(self, kg_store):
        kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_zzz.py::tf",
            label="tf", properties={"file_path": "tests/test_zzz.py"}))
        assert ci_mod._find_relevant_test_functions(kg_store, "src/other.py", {}, {}) == []

    def test_dedup_via_seen_ids(self, kg_store):
        """Strategy 3 不重复添加已在 seen_ids 中的函数。"""
        tfn_id = kg_store.upsert_node(Node(
            entity_type="test_function", entity_id="tests/test_c.py::tf",
            label="tf", properties={"file_path": "tests/test_c.py"}))
        mapping = {"tests/test_c.py": "src/c.py"}
        tests_by_file = {"tests/test_c.py": [kg_store.get_node("test_function",
                                                               "tests/test_c.py::tf")]}
        result = ci_mod._find_relevant_test_functions(
            kg_store, "src/c.py", mapping, tests_by_file)
        assert len(result) == 1
        assert result[0].id == tfn_id


class TestImportCoverageFromDefault:
    def test_found_json(self, kg_store, tmp_path):
        cov = tmp_path / ".coverage.json"
        cov.write_text(json.dumps({"files": {}}))
        with mock.patch.object(ci_mod, "import_coverage",
                               return_value={"files": 1, "covered_functions": 0,
                                             "verifies_edges": 0}) as m:
            result = ci_mod.import_coverage_from_default(kg_store, str(tmp_path))
        m.assert_called_once_with(kg_store, str(cov), str(tmp_path))
        assert result["files"] == 1

    def test_found_sqlite(self, kg_store, tmp_path):
        _make_coverage_db(str(tmp_path / ".coverage"))
        with mock.patch.object(ci_mod, "import_coverage",
                               return_value={"files": 1, "covered_functions": 0,
                                             "verifies_edges": 0}) as m:
            ci_mod.import_coverage_from_default(kg_store, str(tmp_path))
        m.assert_called_once_with(kg_store, str(tmp_path / ".coverage"), str(tmp_path))

    def test_not_found(self, kg_store, tmp_path, caplog):
        with caplog.at_level("WARNING"):
            result = ci_mod.import_coverage_from_default(kg_store, str(tmp_path))
        assert result == {"files": 0, "covered_functions": 0, "verifies_edges": 0}
        assert "No coverage data found in any default location" in caplog.text


# ═══════════════════════════════════════════════════════════════════════
# knowledge_graph/bootstrap.py
# ═══════════════════════════════════════════════════════════════════════

class TestParseRtmTable:
    def test_trailing_empty_cells_popped(self):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| RS-001 | s1 | f1 | fn1 | ✅ | \n")
        rows = boot_mod._parse_rtm_table(text)
        assert len(rows) == 1
        assert rows[0]["shall_id"] == "RS-001"
        assert rows[0]["status"] == "✅"

    def test_separator_row_skipped(self):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| - | - | - | - | - |\n"
                "| RS-001 | s | f | fn | ✅ |\n")
        rows = boot_mod._parse_rtm_table(text)
        assert len(rows) == 1

    def test_row_before_header_logs_debug(self, caplog):
        text = ("| RS-001 | pre-header row |\n\n"
                "| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| RS-002 | s | f | fn | ✅ |\n")
        with caplog.at_level("DEBUG", logger="yuleosh.knowledge_graph.bootstrap"):
            rows = boot_mod._parse_rtm_table(text)
        assert len(rows) == 1
        assert rows[0]["shall_id"] == "RS-002"

    def test_empty_shall_id_skipped_with_warning(self, caplog):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "|  | s | f | fn | ✅ |\n"
                "| RS-003 | s | f | fn | ✅ |\n")
        with caplog.at_level("WARNING"):
            rows = boot_mod._parse_rtm_table(text)
        assert [r["shall_id"] for r in rows] == ["RS-003"]

    def test_bad_format_shall_id_skipped_with_warning(self, caplog):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| !!!bad | s | f | fn | ✅ |\n"
                "| RS-004 | s | f | fn | ✅ |\n")
        with caplog.at_level("WARNING"):
            rows = boot_mod._parse_rtm_table(text)
        assert [r["shall_id"] for r in rows] == ["RS-004"]

    def test_non_standard_shall_id_accepted(self):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| SWR-1 | s | f | fn | ✅ |\n")
        rows = boot_mod._parse_rtm_table(text)
        assert rows[0]["shall_id"] == "SWR-1"

    def test_too_few_columns_skipped(self, caplog):
        text = ("| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
                "| RS-005 | s |\n")
        with caplog.at_level("WARNING"):
            rows = boot_mod._parse_rtm_table(text)
        assert rows == []


class TestParseShallId:
    def test_sub_id(self):
        assert boot_mod._parse_shall_id("RS-001-01") == ("RS-001", "01")

    def test_no_sub_id(self):
        assert boot_mod._parse_shall_id("RS-001") == ("RS", "001")

    def test_dotted_parent(self):
        assert boot_mod._parse_shall_id("SWR-001.1-02") == ("SWR-001.1", "02")


class TestImportFromReqTestJson:
    def test_missing_file(self, kg_store, tmp_path):
        result = boot_mod.import_from_req_test_json(kg_store, str(tmp_path / "nope.json"))
        assert result == {"requirements": 0, "test_files": 0, "edges": 0}

    def test_non_list_mapping_skipped(self, kg_store, tmp_path):
        p = tmp_path / "mapping.json"
        p.write_text(json.dumps({"mappings": {"RS-001": "not-a-list",
                                              "RS-002": []}}))
        result = boot_mod.import_from_req_test_json(kg_store, str(p))
        assert result["requirements"] == 1  # RS-002 (空列表) 建 req, RS-001 跳过
        assert result["edges"] == 0

    def test_non_str_test_file_skipped(self, kg_store, tmp_path):
        p = tmp_path / "mapping.json"
        p.write_text(json.dumps({"mappings": {"RS-003": [123, "tests/t.py"]}}))
        result = boot_mod.import_from_req_test_json(kg_store, str(p))
        assert result["requirements"] == 1
        assert result["test_files"] == 1  # 只有 str 的 tf 被建
        assert result["edges"] == 1


class TestImportFromRtmMd:
    def test_missing_file(self, kg_store, tmp_path):
        result = boot_mod.import_from_rtm_md(kg_store, str(tmp_path / "nope.md"))
        assert result == {"requirements": 0, "test_files": 0, "test_functions": 0,
                          "edges": 0}

    def test_row_without_test_function(self, kg_store, tmp_path):
        md = tmp_path / "rtm.md"
        md.write_text(
            "| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
            "| RS-009 | docs/spec.md | tests/test_zz.py |  |  |\n",
            encoding="utf-8")
        result = boot_mod.import_from_rtm_md(kg_store, str(md))
        assert result == {"requirements": 1, "test_files": 1, "test_functions": 0,
                          "edges": 1}

    def test_row_with_test_function(self, kg_store, tmp_path):
        md = tmp_path / "rtm.md"
        md.write_text(
            "| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |\n"
            "| RS-010 | docs/spec.md | tests/test_aa.py | test_run | ✅ |\n",
            encoding="utf-8")
        result = boot_mod.import_from_rtm_md(kg_store, str(md))
        assert result["requirements"] == 1
        assert result["test_functions"] == 1
        assert result["edges"] == 3  # req→tf covers + tf→tfn contains + req→tfn covers

    def test_empty_shall_id_row_skipped(self, kg_store, tmp_path, monkeypatch):
        """Mocked parser returning empty shall_id exercises the 241 guard."""
        monkeypatch.setattr(boot_mod, "_parse_rtm_table", lambda text: [
            {"shall_id": "", "spec_source": "", "test_file": "", "test_function": "",
             "status": ""}])
        md = tmp_path / "rtm.md"
        md.write_text("x")
        result = boot_mod.import_from_rtm_md(kg_store, str(md))
        assert result["requirements"] == 0


class TestScanCodeDirectory:
    def test_no_dirs_returns_zeros(self, kg_store, tmp_path):
        empty = tmp_path / "empty_proj"
        empty.mkdir()
        result = boot_mod.scan_code_directory(kg_store, str(empty))
        assert result == {"code_files": 0, "test_files": 0, "edges": 0}

    def test_scans_src_and_tests(self, kg_store, tmp_path):
        src = tmp_path / "src" / "yuleosh"
        src.mkdir(parents=True)
        (src / "mod.py").write_text("def foo():\n    pass\n")
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_mod.py").write_text("def test_foo():\n    assert True\n")
        result = boot_mod.scan_code_directory(kg_store, str(tmp_path))
        # 扫描两次（src + 项目根），实体 upsert 幂等但计数按遍历累加
        assert result["code_files"] >= 1
        assert result["test_files"] >= 1
        assert result["edges"] >= 2
        assert kg_store.get_node("code_function", "src/yuleosh/mod.py::foo") is not None
        assert kg_store.get_node("test_function", "tests/test_mod.py::test_foo") is not None

    def test_test_named_file_in_src_is_test_file(self, kg_store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "test_util.py").write_text("def test_util():\n    pass\n")
        result = boot_mod.scan_code_directory(kg_store, str(tmp_path))
        assert result["test_files"] >= 1
        assert kg_store.get_node("test_file", "src/test_util.py") is not None

    def test_unreadable_source_file_tolerated(self, kg_store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        f = src / "mod.py"
        f.write_text("def foo():\n    pass\n")
        os.chmod(f, 0)
        try:
            result = boot_mod.scan_code_directory(kg_store, str(tmp_path))
        finally:
            os.chmod(f, 0o644)
        assert result["code_files"] >= 1
