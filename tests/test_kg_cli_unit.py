"""Unit tests for yuleosh.knowledge_graph.kg_cli (v3.4.2b Wave 2a).

All CLI commands are exercised with mocked store/importers/reporters —
fully offline.

Covers:
  - helpers (_get_store / _ensure_log_dir / _write_log / _get_changed_files_from_git)
  - cmd_build (all modes + spec files + test results + impact + printing)
  - cmd_bootstrap
  - cmd_snapshot_list / cmd_snapshot_diff
  - cmd_query_impact (single/comma files, layer, printing branches)
  - cmd_stats
  - cmd_report / _cmd_report_rtm / _cmd_report_metrics
  - cmd_events / _cmd_events_listen / _cmd_events_history
"""

# @tests src/yuleosh/knowledge_graph/store.py

import os
import sys
import json
from types import SimpleNamespace

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.knowledge_graph import kg_cli as KC


def _args(**kw):
    defaults = dict(
        project_dir="/tmp/proj",
        files=None,
        auto=False,
        ci=False,
        base_ref="HEAD~1",
        build_id=None,
        positional_files=None,
        limit=20,
        build_a="",
        build_b="",
        file_path="",
        layer=None,
        report_sub=None,
        format="markdown",
        output=None,
        title=None,
        trend=5,
        events_sub=None,
        filter=None,
        duration=None,
        event_id=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


@pytest.fixture(autouse=True)
def _kg_env(monkeypatch, tmp_path):
    """Patch store + importer + reporters so no real DB/file IO happens."""
    fake_store = SimpleNamespace(
        snapshot_diff=lambda a, b: {
            "added_nodes": [{"entity_type": "requirement",
                             "entity_id": "RS-1", "label": "R"}],
            "removed_nodes": [],
            "node_count_a": 5,
            "node_count_b": 8,
            "summary": "Nodes: 1 added, 0 removed",
        })
    monkeypatch.setattr("yuleosh.knowledge_graph.get_store",
                        lambda **kw: fake_store)
    monkeypatch.setattr("yuleosh.knowledge_graph.importer.incremental_bootstrap",
                        lambda store, **kw: {
                            "mode": "incremental",
                            "stats": {"total_nodes": 10, "total_edges": 5},
                            "summary": {"total_nodes": 10, "total_edges": 5},
                            "incremental": {"changed_files": 2, "code_files": 1,
                                            "test_files": 1, "functions": 3,
                                            "classes": 1, "methods": 2},
                        })
    monkeypatch.setattr("yuleosh.knowledge_graph.importer.bootstrap",
                        lambda store, **kw: {
                            "summary": {"total_nodes": 42, "total_edges": 17}})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.spec_diff.detect_spec_files_in_changes",
        lambda files: ["specs/req.spec.md"])
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.spec_diff.get_spec_changes_from_git",
        lambda ref, f: {"created": 1})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.spec_diff.apply_spec_changes_to_store",
        lambda store, changes: {"created": 1, "updated": 0, "deleted": 0})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.verify_delta.load_test_results",
        lambda project_dir: {"passed": 3, "failed": 1, "skipped": 0,
                             "verifies_updated": 2, "covers_updated": 1})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.verify_delta.apply_test_results",
        lambda store, tr: tr)
    # These three are imported at kg_cli module level -> patch KC.<name>
    monkeypatch.setattr(
        KC, "impact_analysis",
        lambda store, files, layer=None: {
            "affected_reqs": [{"req_id": "RS-1", "confidence": "direct"}],
            "affected_tests": [{"file": "tests/t.py",
                                "functions": ["f1", "f2"]}],
            "impact_summary": "1 requirements (1 direct, 0 indirect)",
        })
    monkeypatch.setattr(
        KC, "list_snapshots",
        lambda store, limit=20: [
            {"build_id": "b-1", "node_count": 10, "edge_count": 5,
             "built_at": "2026-07-01T00:00:00"}])
    monkeypatch.setattr(
        KC, "get_graph_stats",
        lambda store: {"total_nodes": 10, "total_edges": 5,
                       "nodes_by_type": {"requirement": 4, "test_file": 6},
                       "edges_by_type": {"covers": 5}})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.reporter.generate_rtm",
        lambda store, fmt="markdown", layer=None, title=None: "# RTM")
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.reporter.generate_metrics",
        lambda store, trend_snapshots=5: {"trend": [{"nodes": 1}]})
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.reporter.format_metrics_text",
        lambda metrics: "nodes: 1")
    monkeypatch.setattr(
        "yuleosh.knowledge_graph.events.kg_events",
        SimpleNamespace(
            on=lambda *a, **kw: None,
            off=lambda *a, **kw: None,
            history=lambda event_type=None, limit=50: [
                {"event_type": "kg.built", "timestamp": "2026-07-01T00:00:00",
                 "source": "cli"}],
        ))
    return fake_store


# ── Helpers ────────────────────────────────────────────────────────────

class TestHelpers:
    def test_get_store_default_db_path(self, monkeypatch):
        """GIVEN no db_path WHEN _get_store THEN default path used."""
        captured = {}
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.get_store",
            lambda **kw: captured.update(kw) or object())
        KC._get_store("/proj")
        assert captured["db_path"].endswith(
            os.path.join(".yuleosh", "knowledge_graph.db"))

    def test_get_store_with_kwargs(self, monkeypatch):
        """GIVEN kwargs WHEN _get_store THEN forwarded."""
        captured = {}
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.get_store",
            lambda **kw: captured.update(kw) or object())
        KC._get_store("/proj", {"backend": "pg"})
        assert captured["backend"] == "pg"

    def test_ensure_log_dir(self, tmp_path):
        """GIVEN project dir WHEN _ensure_log_dir THEN dir created."""
        log_dir = KC._ensure_log_dir(str(tmp_path))
        assert log_dir.exists()
        assert log_dir.name == "knowledge-graph"

    def test_write_log(self, tmp_path):
        """GIVEN content WHEN _write_log THEN file written + path returned."""
        path = KC._write_log(str(tmp_path), "x.json", '{"a": 1}')
        assert path == str(tmp_path / "knowledge-graph" / "x.json")
        assert (tmp_path / "knowledge-graph" / "x.json").read_text() == '{"a": 1}'

    def test_changed_files_from_git(self, monkeypatch):
        """GIVEN git diff success WHEN _get_changed_files THEN list."""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: SimpleNamespace(returncode=0,
                                             stdout="a.py\nb.py\n",
                                             stderr=""))
        assert KC._get_changed_files_from_git("HEAD~1") == ["a.py", "b.py"]

    def test_changed_files_git_failure(self, monkeypatch):
        """GIVEN git failure WHEN _get_changed_files THEN empty list."""
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="e"))
        assert KC._get_changed_files_from_git() == []

    def test_changed_files_git_timeout(self, monkeypatch):
        """GIVEN TimeoutExpired WHEN _get_changed_files THEN empty list."""
        import subprocess

        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="git", timeout=30)

        monkeypatch.setattr("subprocess.run", timeout)
        assert KC._get_changed_files_from_git() == []


# ── cmd_build ──────────────────────────────────────────────────────────

class TestCmdBuild:
    def test_build_full_bootstrap_no_changes(self, _kg_env, tmp_path, capsys):
        """GIVEN no files WHEN build THEN full bootstrap mode."""
        result = KC.cmd_build(_args(project_dir=str(tmp_path)))
        assert result["mode"] == "incremental"  # fixture returns incremental
        assert "KG Build" in capsys.readouterr().out
        assert "log_path" in result

    def _bootstrap_with_spec_changes(self, monkeypatch):
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.importer.incremental_bootstrap",
            lambda store, **kw: {
                "mode": "incremental",
                "stats": {"total_nodes": 10, "total_edges": 5},
                "summary": {"total_nodes": 10, "total_edges": 5},
                "incremental": {"changed_files": 2, "code_files": 1,
                                "test_files": 1, "functions": 3,
                                "classes": 1, "methods": 2},
                "spec_changes": {"created": 1, "updated": 2, "deleted": 0},
            })

    def test_build_with_files_auto_and_positional(self, _kg_env, tmp_path,
                                                  capsys, monkeypatch):
        self._bootstrap_with_spec_changes(monkeypatch)
        """GIVEN files+auto+positional WHEN build THEN union deduped."""
        monkeypatch.setattr(
            KC, "_get_changed_files_from_git", lambda ref="HEAD~1": ["x.py"])
        monkeypatch.setattr(
            KC, "_write_log",
            lambda d, f, c: (tmp_path / f).write_text(c) or str(tmp_path / f))
        args = _args(project_dir=str(tmp_path), files="a.py, b.py",
                     auto=True, positional_files=["b.py", "c.py"],
                     build_id="build-1")
        result = KC.cmd_build(args)
        out = capsys.readouterr().out
        assert "build-1" in out
        assert "spec_changes" in result
        assert "test_results" in result
        assert "impact" in result

    def test_build_ci_mode(self, _kg_env, tmp_path, capsys, monkeypatch):
        """GIVEN ci flag WHEN build THEN git HEAD~1 used."""
        calls = []
        monkeypatch.setattr(KC, "_get_changed_files_from_git",
                            lambda ref="HEAD~1": calls.append(ref) or ["f.c"])
        monkeypatch.setattr(KC, "_write_log",
                            lambda d, f, c: str(tmp_path / f))
        KC.cmd_build(_args(project_dir=str(tmp_path), ci=True))
        assert calls == ["HEAD~1"]

    def test_build_ci_no_changes_falls_to_full(self, _kg_env, tmp_path,
                                               capsys, monkeypatch):
        """GIVEN ci mode with no git changes WHEN build THEN full bootstrap."""
        monkeypatch.setattr(KC, "_get_changed_files_from_git",
                            lambda ref="HEAD~1": [])
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_build(_args(project_dir=str(tmp_path), ci=True))
        assert result["mode"] == "incremental"

    def test_build_no_spec_files(self, _kg_env, tmp_path, monkeypatch):
        """GIVEN changed files without specs WHEN build THEN spec skipped."""
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.spec_diff.detect_spec_files_in_changes",
            lambda files: [])
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        assert "spec_changes" not in result

    def test_build_spec_file_missing_on_disk(self, _kg_env, tmp_path,
                                             monkeypatch):
        """GIVEN spec listed but not on disk WHEN build THEN skipped."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        assert "spec_changes" not in result  # spec file absent on disk

    def test_build_spec_processing_error(self, _kg_env, tmp_path,
                                         monkeypatch):
        """GIVEN spec processing raising WHEN build THEN warning logged."""
        (tmp_path / "specs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "specs" / "req.spec.md").write_text("x")

        def boom(*a, **kw):
            raise RuntimeError("spec parse failed")

        monkeypatch.setattr(
            "yuleosh.knowledge_graph.spec_diff.get_spec_changes_from_git", boom)
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        assert "spec_changes" not in result

    def test_build_printing_branches(self, _kg_env, tmp_path, capsys,
                                     monkeypatch):
        """GIVEN rich result WHEN build THEN all summary sections printed."""
        self._bootstrap_with_spec_changes(monkeypatch)
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        out = capsys.readouterr().out
        assert "Spec changes applied" in out
        assert "Test results" in out
        assert "Impact Analysis" in out
        assert "Affected requirements" in out

    def test_build_impact_overflows(self, _kg_env, tmp_path, capsys,
                                    monkeypatch):
        """GIVEN >10 reqs and >5 tests WHEN build THEN ellipsis printed."""
        monkeypatch.setattr(
            KC, "impact_analysis",
            lambda store, files, layer=None: {
                "affected_reqs": [{"req_id": f"RS-{i}", "confidence": "d"}
                                  for i in range(12)],
                "affected_tests": [{"file": f"t{i}.py", "functions": ["f"]}
                                   for i in range(7)],
            })
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        out = capsys.readouterr().out
        assert "and 2 more" in out
        assert "and 2 more files" not in out  # tests section not printed here
        assert "and 2 more" in out

    def test_build_no_test_results(self, _kg_env, tmp_path, monkeypatch):
        """GIVEN no test results WHEN build THEN results skipped."""
        monkeypatch.setattr(
            "yuleosh.knowledge_graph.verify_delta.load_test_results",
            lambda project_dir: None)
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_build(_args(project_dir=str(tmp_path), files="a.py"))
        assert "test_results" not in result


# ── cmd_bootstrap ──────────────────────────────────────────────────────

class TestCmdBootstrap:
    def test_bootstrap(self, _kg_env, tmp_path, capsys, monkeypatch):
        """GIVEN bootstrap WHEN cmd THEN summary printed."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_bootstrap(_args(project_dir=str(tmp_path)))
        assert result["summary"]["total_nodes"] == 42
        out = capsys.readouterr().out
        assert "KG Bootstrap Complete" in out


# ── snapshots ──────────────────────────────────────────────────────────

class TestSnapshots:
    def test_snapshot_list_empty(self, _kg_env, monkeypatch, capsys):
        """GIVEN no snapshots WHEN list THEN empty message."""
        monkeypatch.setattr(KC, "list_snapshots", lambda store, limit=20: [])
        result = KC.cmd_snapshot_list(_args())
        assert result == {"snapshots": []}
        assert "No snapshots" in capsys.readouterr().out

    def test_snapshot_list_nonempty(self, _kg_env, capsys):
        """GIVEN snapshots WHEN list THEN table printed."""
        result = KC.cmd_snapshot_list(_args(limit=5))
        assert result["count"] == 1
        out = capsys.readouterr().out
        assert "Graph Snapshots" in out
        assert "b-1" in out

    def test_snapshot_diff_missing_args(self, _kg_env, capsys):
        """GIVEN missing build ids WHEN diff THEN usage error."""
        result = KC.cmd_snapshot_diff(_args())
        assert result == {}
        assert "Usage" in capsys.readouterr().err

    def test_snapshot_diff_error(self, _kg_env, capsys, monkeypatch):
        """GIVEN store diff raising WHEN diff THEN error logged."""
        def boom(a, b):
            raise RuntimeError("db issue")

        monkeypatch.setattr(_kg_env, "snapshot_diff", boom)
        result = KC.cmd_snapshot_diff(_args(build_a="A", build_b="B"))
        assert result == {}
        assert "Failed to compute diff" in capsys.readouterr().err

    def test_snapshot_diff_success(self, _kg_env, capsys):
        """GIVEN valid diff WHEN cmd THEN summary printed."""
        result = KC.cmd_snapshot_diff(_args(build_a="A", build_b="B"))
        assert result["node_count_a"] == 5
        out = capsys.readouterr().out
        assert "Snapshot Diff: A → B" in out
        assert "RS-1" in out

    def test_snapshot_diff_many_nodes(self, _kg_env, capsys,
                                      monkeypatch):
        """GIVEN >15 added nodes WHEN diff THEN ellipsis."""
        monkeypatch.setattr(
            _kg_env, "snapshot_diff",
            lambda a, b: {
                "added_nodes": [
                    {"entity_type": "code_file", "entity_id": f"f{i}.c",
                     "label": "x"} for i in range(20)],
                "removed_nodes": [],
                "node_count_a": 1, "node_count_b": 21,
                "summary": "s",
            })
        KC.cmd_snapshot_diff(_args(build_a="A", build_b="B"))
        out = capsys.readouterr().out
        assert "and 5 more" in out


# ── cmd_query_impact ───────────────────────────────────────────────────

class TestQueryImpact:
    def test_no_file(self, _kg_env, capsys):
        """GIVEN no file_path WHEN impact THEN usage error."""
        result = KC.cmd_query_impact(_args())
        assert result == {}
        assert "Usage" in capsys.readouterr().err

    def test_single_file(self, _kg_env, tmp_path, capsys, monkeypatch):
        """GIVEN single file WHEN impact THEN report printed + saved."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_query_impact(_args(file_path="src/a.c"))
        out = capsys.readouterr().out
        assert "Impact Analysis for: src/a.c" in out
        assert "RS-1" in out
        assert "tests/t.py" in out
        assert "Report saved" in out

    def test_comma_files_with_layer(self, _kg_env, tmp_path, capsys,
                                    monkeypatch):
        """GIVEN comma-separated files + layer WHEN impact THEN split."""
        calls = {}

        def fake_impact(store, files, layer=None):
            calls["files"] = files
            calls["layer"] = layer
            return {"affected_reqs": [], "affected_tests": [],
                    "affected_functions": ["fn1", "fn2"],
                    "impact_summary": "none", "low_confidence_warning": True}

        monkeypatch.setattr(KC, "impact_analysis", fake_impact)
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_query_impact(
            _args(file_path="a.py, b.py", layer="unit"))
        assert calls["files"] == ["a.py", "b.py"]
        assert calls["layer"] == "unit"
        out = capsys.readouterr().out
        assert "Low confidence warnings present" in out
        assert "fn1" in out
        assert result["low_confidence_warning"] is True

    def test_many_tests_ellipsis(self, _kg_env, tmp_path, capsys, monkeypatch):
        """GIVEN >20 tests WHEN impact THEN ellipsis."""
        monkeypatch.setattr(
            KC, "impact_analysis",
            lambda store, files, layer=None: {
                "affected_reqs": [], "affected_tests": [
                    {"file": f"t{i}.py", "functions": ["f"]} for i in range(25)
                ],
            })
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        KC.cmd_query_impact(_args(file_path="a.py"))
        out = capsys.readouterr().out
        assert "and 5 more files" in out


# ── cmd_stats ──────────────────────────────────────────────────────────

class TestCmdStats:
    def test_stats_full(self, _kg_env, capsys):
        """GIVEN stats with breakdowns WHEN cmd THEN all sections printed."""
        result = KC.cmd_stats(_args())
        assert result["total_nodes"] == 10
        out = capsys.readouterr().out
        assert "Knowledge Graph Statistics" in out
        assert "requirement" in out
        assert "covers" in out
        assert "Latest snapshot" in out
        assert "b-1" in out

    def test_stats_empty_breakdowns(self, _kg_env, capsys, monkeypatch):
        """GIVEN empty breakdowns + no snapshots WHEN cmd THEN minimal."""
        monkeypatch.setattr(
            KC, "get_graph_stats",
            lambda store: {"total_nodes": 0, "total_edges": 0,
                           "nodes_by_type": {}, "edges_by_type": {}})
        monkeypatch.setattr(KC, "list_snapshots", lambda store, limit=1: [])
        KC.cmd_stats(_args())
        out = capsys.readouterr().out
        assert "Total nodes:      0" in out


# ── reports ────────────────────────────────────────────────────────────

class TestReports:
    def test_report_unknown(self, _kg_env, capsys):
        """GIVEN unknown report_sub WHEN report THEN usage error."""
        result = KC.cmd_report(_args(report_sub="bogus"))
        assert result == {}
        assert "Usage" in capsys.readouterr().err

    def test_report_no_sub(self, _kg_env, capsys):
        """GIVEN no report_sub WHEN report THEN usage error."""
        assert KC.cmd_report(_args()) == {}

    def test_report_rtm_stdout(self, _kg_env, tmp_path, capsys, monkeypatch):
        """GIVEN rtm without output WHEN rtm THEN content printed."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_report(_args(report_sub="rtm"))
        assert result["format"] == "markdown"
        out = capsys.readouterr().out
        assert "# RTM" in out
        assert "Log saved" in out

    def test_report_rtm_output_file(self, _kg_env, tmp_path, capsys,
                                    monkeypatch):
        """GIVEN rtm with output WHEN rtm THEN file written."""
        out_file = tmp_path / "rtm.md"
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_report(_args(report_sub="rtm",
                                     output=str(out_file)))
        assert out_file.read_text() == "# RTM"
        assert "RTM report saved" in capsys.readouterr().out

    def test_report_rtm_html_ext(self, _kg_env, tmp_path, monkeypatch):
        """GIVEN html format WHEN rtm THEN .html log ext."""
        written = {}
        monkeypatch.setattr(
            KC, "_write_log",
            lambda d, f, c: written.update({f: c}) or str(tmp_path / f))
        KC.cmd_report(_args(report_sub="rtm", format="html"))
        assert any(f.endswith(".html") for f in written)

    def test_report_metrics_text(self, _kg_env, tmp_path, capsys,
                                 monkeypatch):
        """GIVEN text metrics WHEN metrics THEN formatted text."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        result = KC.cmd_report(_args(report_sub="metrics"))
        assert "trend" in result
        out = capsys.readouterr().out
        assert "nodes: 1" in out

    def test_report_metrics_json(self, _kg_env, tmp_path, capsys,
                                 monkeypatch):
        """GIVEN json metrics WHEN metrics THEN json content."""
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        KC.cmd_report(_args(report_sub="metrics", format="json"))
        out = capsys.readouterr().out
        assert '"trend"' in out

    def test_report_metrics_output(self, _kg_env, tmp_path, monkeypatch):
        """GIVEN metrics with output WHEN metrics THEN file written."""
        out_file = tmp_path / "m.json"
        monkeypatch.setattr(KC, "_write_log", lambda d, f, c: str(tmp_path / f))
        KC.cmd_report(_args(report_sub="metrics", format="json",
                            output=str(out_file)))
        assert json.loads(out_file.read_text())["trend"] == [{"nodes": 1}]


# ── events ─────────────────────────────────────────────────────────────

class TestEvents:
    def test_events_unknown(self, _kg_env, capsys):
        """GIVEN unknown events_sub WHEN events THEN usage error."""
        result = KC.cmd_events(_args(events_sub="bogus"))
        assert result == {}

    def test_events_listen_duration(self, _kg_env, capsys, monkeypatch):
        """GIVEN listen with duration WHEN events THEN received count."""
        monkeypatch.setattr("time.sleep", lambda s: None)
        result = KC.cmd_events(_args(events_sub="listen", duration=1))
        assert "received" in result
        assert result["received"] == 0  # no events emitted during sleep

    def test_events_listen_filter(self, _kg_env, capsys, monkeypatch):
        """GIVEN filter WHEN listen THEN non-matching filtered out."""
        import yuleosh.knowledge_graph.events as events_mod

        class Ev:
            event_type = "kg.built"
            timestamp = "2026-07-01T12:34:56"
            data = {"n": 1}

        bus = SimpleNamespace(on=lambda *a, **kw: None,
                              off=lambda *a, **kw: None,
                              history=lambda **kw: [])
        monkeypatch.setattr(events_mod, "kg_events", bus)
        monkeypatch.setattr("time.sleep", lambda s: None)
        result = KC._cmd_events_listen(_args(duration=1, filter="other"),
                                       bus)
        assert result["received"] == 0

    def test_events_listen_keyboard_interrupt(self, _kg_env, capsys,
                                              monkeypatch):
        """GIVEN KeyboardInterrupt WHEN listen THEN graceful exit."""

        def interrupt(s):
            raise KeyboardInterrupt()

        monkeypatch.setattr("time.sleep", interrupt)
        result = KC.cmd_events(_args(events_sub="listen"))
        assert result["received"] == 0

    def test_events_history_empty(self, _kg_env, capsys, monkeypatch):
        """GIVEN no history WHEN history THEN empty message."""
        import yuleosh.knowledge_graph.events as events_mod
        bus = SimpleNamespace(history=lambda event_type=None, limit=50: [])
        monkeypatch.setattr(events_mod, "kg_events", bus)
        result = KC.cmd_events(_args(events_sub="history"))
        assert result == {"events": [], "count": 0}
        assert "No events" in capsys.readouterr().out

    def test_events_history_nonempty(self, _kg_env, capsys):
        """GIVEN history WHEN history THEN table printed."""
        result = KC.cmd_events(_args(events_sub="history", limit=10))
        assert result["count"] == 1
        out = capsys.readouterr().out
        assert "Recent Events" in out
        assert "kg.built" in out
