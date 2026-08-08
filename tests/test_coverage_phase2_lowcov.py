# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Coverage Phase 2 (2026-08-08): raise repo coverage 84% → 85%.

Targets the lowest-coverage modules with focused unit tests:
  - ci/layers.py (re-export + profile-aware gate helpers)
  - ci/layers/layer_validator.py (validate/format layer results)
  - ci/layers/layer_executor.py (dependency + timeout helpers)
  - api/kg.py (KG API handlers)
  - ci/cron_c_coverage_verify.py (standalone entry)
"""

import json
import sys
import time
from pathlib import Path
from typing import ClassVar
from unittest import mock

import pytest

from yuleosh.ci.layers import (
    _detect_project_language,
    _LayerTimeout,
    check_coverage_gate_with_profile,
    check_layer_dependency,
    get_latest_layer_result,
    get_profile_label,
)
from yuleosh.ci.layers.layer_validator import (
    format_layer_summary,
    validate_layer_result,
)

# ══════════════════════════════════════════════════════════════════════
# ci/layers.py — re-export + profile-aware helpers
# ══════════════════════════════════════════════════════════════════════


class TestLayersReExport:
    def test_all_symbols_reexported(self):
        """The legacy module must still expose the split package's symbols."""
        from yuleosh.ci import layers

        for name in (
            "run_layer1", "run_layer2", "run_layer3",
            "validate_layer_result", "format_layer_summary",
            "check_layer_dependency", "get_latest_layer_result",
            "layer_dependencies",
        ):
            assert hasattr(layers, name), f"missing re-export: {name}"

    def test_check_coverage_gate_with_profile_empty(self, tmp_path):
        """Empty profile delegates to the standard gate."""
        with mock.patch("yuleosh.ci.runner.check_coverage_gate",
                        return_value=(True, ["ok"])) as m:
            ok, msgs = check_coverage_gate_with_profile(str(tmp_path), None)
            assert ok is True
            assert "ok" in msgs
            m.assert_called_once_with(str(tmp_path), None, override_strict=False)

    def test_check_coverage_gate_with_profile_applies(self, tmp_path):
        """Non-empty profile applies profile config before the gate."""
        with mock.patch("yuleosh.ci.config._get_ci_config",
                        return_value=mock.MagicMock()), \
             mock.patch("yuleosh.ci.config.load_ci_profile_into_config") as load, \
             mock.patch("yuleosh.ci.runner.check_coverage_gate",
                        return_value=(False, ["blocked"])):
            ok, msgs = check_coverage_gate_with_profile(
                str(tmp_path), {"line_rate": 50}, override_strict=True, profile="ci"
            )
            assert ok is False
            load.assert_called_once()
            assert msgs == ["blocked"]

    def test_get_profile_label(self, tmp_path):
        """Profile label reads ci_profile attr; falls back to 'ci'."""
        with mock.patch("yuleosh.ci.config._get_ci_config",
                        return_value=mock.MagicMock(ci_profile="production")):
            assert get_profile_label(str(tmp_path)) == "production"

    def test_get_profile_label_fallback(self, tmp_path):
        """On error, label falls back to 'ci'."""
        with mock.patch("yuleosh.ci.config._get_ci_config",
                        side_effect=RuntimeError("boom")):
            assert get_profile_label(str(tmp_path)) == "ci"


# ══════════════════════════════════════════════════════════════════════
# ci/layers/layer_validator.py
# ══════════════════════════════════════════════════════════════════════


class TestLayerValidator:
    def test_validate_missing_file(self, tmp_path):
        result = validate_layer_result(str(tmp_path / "nope.json"))
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_validate_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        result = validate_layer_result(str(p))
        assert result["valid"] is False
        assert "error" in result

    def test_validate_ok(self, tmp_path):
        p = tmp_path / "layer.json"
        p.write_text(json.dumps({
            "status": "passed",
            "layer": "L1",
            "commit": "0123456789abcdef",
            "stages": [{"name": "s1"}, {"name": "s2"}],
            "errors": [],
        }))
        result = validate_layer_result(str(p))
        assert result["valid"] is True
        assert result["status"] == "passed"
        assert result["stage_count"] == 2
        assert result["error_count"] == 0
        assert result["layer"] == "L1"
        assert result["commit"] == "0123456789abcdef"

    def test_format_invalid(self):
        s = format_layer_summary({"valid": False, "error": "gone"})
        assert "invalid" in s
        assert "gone" in s

    def test_format_passed(self):
        s = format_layer_summary({
            "valid": True, "status": "passed", "layer": "L1",
            "commit": "0123456789abcdef", "stage_count": 3, "error_count": 0,
        })
        assert "✅" in s
        assert "PASSED" in s
        assert "L1" in s
        assert "01234567" in s  # commit truncated to 8

    def test_format_failed(self):
        s = format_layer_summary({
            "valid": True, "status": "failed", "layer": "L2",
            "commit": "feedface01234567", "stage_count": 1, "error_count": 2,
        })
        assert "❌" in s
        assert "FAILED" in s
        assert "2 errors" in s


# ══════════════════════════════════════════════════════════════════════
# ci/layers/layer_executor.py — dependency/timeout helpers
# ══════════════════════════════════════════════════════════════════════


class TestLayerExecutor:
    def test_check_layer_dependency_ok(self, tmp_path):
        # L2 depends on L1; with a passed L1 result, gate passes (None)
        with mock.patch("yuleosh.ci.layers.layer_config._get_ci_config",
                        side_effect=FileNotFoundError("no config")), \
             mock.patch("yuleosh.ci.layers.layer_config.get_latest_layer_result",
                        return_value={"status": "passed"}):
            assert check_layer_dependency(2, str(tmp_path)) is None

    def test_check_layer_dependency_no_result(self, tmp_path):
        # Missing prerequisite result blocks the layer
        with mock.patch("yuleosh.ci.layers.layer_config._get_ci_config",
                        side_effect=FileNotFoundError("no config")), \
             mock.patch("yuleosh.ci.layers.layer_config.get_latest_layer_result",
                        return_value=None):
            msg = check_layer_dependency(2, str(tmp_path))
            assert msg is not None
            assert "Layer 1" in msg

    def test_check_layer_dependency_failed_result(self, tmp_path):
        # Prerequisite result exists but did not pass
        with mock.patch("yuleosh.ci.layers.layer_config._get_ci_config",
                        side_effect=FileNotFoundError("no config")), \
             mock.patch("yuleosh.ci.layers.layer_config.get_latest_layer_result",
                        return_value={"status": "failed"}):
            msg = check_layer_dependency(2, str(tmp_path))
            assert msg is not None
            assert "blocked" in msg

    def test_check_layer_dependency_config_driven(self, tmp_path):
        # Config-driven: missing dependency -> blocking message
        cfg = mock.MagicMock()
        cfg.layer_dependencies.get.return_value = ["L99"]
        with mock.patch("yuleosh.ci.layers.layer_config._get_ci_config",
                        return_value=cfg), \
             mock.patch("yuleosh.ci.layers.layer_config.get_latest_layer_result",
                        return_value=None):
            msg = check_layer_dependency(2, str(tmp_path))
            assert msg is not None
            assert "L99" in msg

    def test_get_latest_layer_result_missing(self, tmp_path):
        with mock.patch("yuleosh.ci.layers.layer_config._get_ci_config",
                        side_effect=FileNotFoundError("no config")):
            assert get_latest_layer_result(1, str(tmp_path)) is None

    def test_layer_timeout_exception(self):
        err = _LayerTimeout("L1 timed out after 30s")
        assert "30s" in str(err)

    def test_detect_project_language_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        assert _detect_project_language(str(tmp_path)) == "python"

    def test_detect_project_language_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module x\n")
        assert _detect_project_language(str(tmp_path)) == "go"

    def test_detect_project_language_unknown(self, tmp_path):
        # Default fallback is C (embedded-oriented default)
        assert _detect_project_language(str(tmp_path)) == "c"


# ══════════════════════════════════════════════════════════════════════
# api/kg.py — KG API dispatcher
# ══════════════════════════════════════════════════════════════════════


class TestKgApiDispatcher:
    # NOTE: handle_kg is wrapped by @require_auth at import time, so patching
    # yuleosh.api.kg.require_auth at runtime has no effect. The sanctioned
    # bypass is the current_user kwarg (see middleware.require_auth).
    _AUTH: ClassVar[dict] = {"current_user": {"user_id": 1, "org_id": 1}}

    def test_empty_tail_400(self):
        from yuleosh.api.kg import handle_kg
        resp = handle_kg("GET", "", {}, {}, **self._AUTH)
        assert resp is not None
        assert "resource required" in str(resp)

    def test_unknown_top_resource_404(self):
        from yuleosh.api.kg import handle_kg
        resp = handle_kg("GET", "bogus/x", {}, {}, **self._AUTH)
        assert resp is not None
        assert "404" in str(resp) or "Unknown" in str(resp)

    def test_query_unknown_resource_404(self):
        from yuleosh.api.kg import handle_kg
        resp = handle_kg("GET", "query/bogus", {}, {}, **self._AUTH)
        assert resp is not None
        assert "404" in str(resp) or "Unknown" in str(resp)

    def test_impact_wrong_method_405(self):
        from yuleosh.api.kg import handle_kg
        resp = handle_kg("GET", "query/impact", {}, {}, **self._AUTH)
        assert resp is not None
        assert "405" in str(resp) or "POST required" in str(resp)

    def test_impact_delegates(self):
        from yuleosh.api.kg import handle_kg
        with mock.patch("yuleosh.api.kg_impact.handle_kg_impact") as m:
            result = handle_kg("POST", "query/impact", {"files": ["a.c"]}, {},
                               **self._AUTH)
            m.assert_called_once()
            assert result is None


# ══════════════════════════════════════════════════════════════════════
# plan/cli.py — plan command helpers
# ══════════════════════════════════════════════════════════════════════


class TestPlanCli:
    def test_get_latest_plan_id_empty(self, tmp_path):
        from yuleosh.plan.cli import _get_latest_plan_id
        assert _get_latest_plan_id(str(tmp_path)) is None

    def test_load_plan_missing(self, tmp_path):
        from yuleosh.plan.cli import _load_plan
        assert _load_plan(str(tmp_path), "nonexistent") is None

    def test_save_and_load_roundtrip(self, tmp_path):
        from yuleosh.plan.cli import _load_plan, _save_plan
        from yuleosh.plan.models import Plan
        plan = Plan(
            title="Test",
            objective="do the thing",
            background="bg",
            technical_approach="ta",
        )
        plan_id = _save_plan(str(tmp_path), plan)
        assert plan_id
        loaded = _load_plan(str(tmp_path), plan_id)
        assert loaded is not None
        assert loaded.title == "Test"

    def test_handle_generate(self, tmp_path):
        from yuleosh.plan.cli import _handle_generate
        # generate without a real generator -> fallback behavior returns code
        rc = _handle_generate(str(tmp_path), "build a thing", as_json=True)
        assert isinstance(rc, int)

    def test_handle_list_empty(self, tmp_path):
        from yuleosh.plan.cli import _handle_list
        with mock.patch("builtins.print"):
            rc = _handle_list(str(tmp_path))
        assert rc == 0


# ══════════════════════════════════════════════════════════════════════
# ci/cron_c_coverage_verify.py — weekly cron entry
# ══════════════════════════════════════════════════════════════════════


class TestCronCCoverageVerify:
    def test_run_weekly_verification_success(self, tmp_path):
        from yuleosh.ci.cron_c_coverage_verify import run_weekly_verification
        fake = {
            "success": True,
            "line_rate": 87.5,
            "branch_rate": 80.0,
            "gate_passed": True,
            "gcda_files_found": 12,
            "warnings": [],
        }
        with mock.patch(
            "yuleosh.ci.verify_c_coverage_gate.verify_c_coverage_gate",
            return_value=fake,
        ):
            summary = run_weekly_verification(str(tmp_path))
        assert summary["success"] is True
        assert summary["line_rate"] == 87.5
        assert summary["p0_alert"] is False
        assert summary["gate_passed"] is True
        report = tmp_path / ".yuleosh" / "reports" / "c-coverage-weekly-cron.json"
        assert report.exists()
        import json as _json
        data = _json.loads(report.read_text())
        assert data["cron_timestamp"] == summary["cron_timestamp"]

    def test_run_weekly_verification_p0_alert(self, tmp_path):
        from yuleosh.ci.cron_c_coverage_verify import run_weekly_verification
        fake = {
            "success": False,
            "line_rate": None,
            "branch_rate": None,
            "gate_passed": None,
            "gcda_files_found": 0,
            "warnings": ["no gcda"],
        }
        with mock.patch(
            "yuleosh.ci.verify_c_coverage_gate.verify_c_coverage_gate",
            return_value=fake,
        ):
            summary = run_weekly_verification(str(tmp_path))
        assert summary["p0_alert"] is True
        assert summary["success"] is False
        assert summary["warnings"] == ["no gcda"]

    def test_main_exit_codes(self, tmp_path):
        from yuleosh.ci import cron_c_coverage_verify as mod
        # success -> 0
        with mock.patch.object(mod, "run_weekly_verification",
                               return_value={
                                   "success": True, "line_rate": 90.0,
                                   "gate_passed": True, "gcda_files_found": 5,
                                   "p0_alert": False, "cron_timestamp": "t",
                                   "warnings": [],
                               }), \
             mock.patch.object(sys, "argv", ["cron", "--project", str(tmp_path)]):
            with pytest.raises(SystemExit) as e:
                mod.main()
            assert e.value.code == 0
        # gate failed -> 1
        with mock.patch.object(mod, "run_weekly_verification",
                               return_value={
                                   "success": True, "line_rate": 50.0,
                                   "gate_passed": False, "gcda_files_found": 5,
                                   "p0_alert": False, "cron_timestamp": "t",
                                   "warnings": [],
                               }), \
             mock.patch.object(sys, "argv", ["cron", "--project", str(tmp_path)]):
            with pytest.raises(SystemExit) as e:
                mod.main()
            assert e.value.code == 1
        # p0 alert -> 2
        with mock.patch.object(mod, "run_weekly_verification",
                               return_value={
                                   "success": False, "line_rate": None,
                                   "gate_passed": None, "gcda_files_found": 0,
                                   "p0_alert": True, "cron_timestamp": "t",
                                   "warnings": [],
                               }), \
             mock.patch.object(sys, "argv", ["cron", "--project", str(tmp_path)]):
            with pytest.raises(SystemExit) as e:
                mod.main()
            assert e.value.code == 2


# ══════════════════════════════════════════════════════════════════════
# memory/cli.py — fact store + session search CLI
# ══════════════════════════════════════════════════════════════════════


class TestMemoryCli:
    def _store(self):
        store = mock.MagicMock()
        store.remember.return_value = {
            "id": 1, "category": "general", "entity": "",
            "trust": 0.5, "content": "fact content",
        }
        store.recall.return_value = [
            {"id": 1, "content": "fact", "tags": "t", "entity": "e",
             "category": "general", "trust": 0.5, "recall_count": 1,
             "updated_at": "now"},
        ]
        store.list_facts.return_value = []
        store.stats.return_value = {
            "facts": 1, "sessions": 0, "by_category": {"general": 1},
        }
        store.log_session.return_value = {
            "id": 1, "kind": "note", "created_at": "now",
        }
        store.search_sessions.return_value = [
            {"id": 1, "kind": "note", "session_key": "k",
             "created_at": "now", "snippet": "snippet"},
        ]
        return store

    def _args(self, memory_sub, **kw):
        import argparse
        ns = argparse.Namespace(memory_sub=memory_sub)
        for k, v in kw.items():
            setattr(ns, k, v)
        return ns

    def test_remember(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store), \
             mock.patch("yuleosh.knowledge.indexer.KnowledgeIndexer",
                        side_effect=ImportError("no indexer")):
            rc = handle_memory_command(
                self._args("remember", content="fact content",
                           entity="", category="general",
                           tags="a,b", trust=0.5))
        assert rc == 0
        out = capsys.readouterr().out
        assert "✅ Remembered" in out

    def test_recall_empty(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        store.recall.return_value = []
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(
                self._args("recall", query="q", entity=None,
                           category=None, limit=20))
        assert rc == 0
        assert "No facts match" in capsys.readouterr().out

    def test_recall_hits(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(
                self._args("recall", query="q", entity=None,
                           category=None, limit=20))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Recalled 1 fact" in out

    def test_forget_found(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        store.forget.return_value = True
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(self._args("forget", id=1))
        assert rc == 0
        assert "Forgotten fact" in capsys.readouterr().out

    def test_forget_missing(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        store.forget.return_value = False
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(self._args("forget", id=99))
        assert rc == 0
        assert "No fact with id" in capsys.readouterr().out

    def test_list_empty(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        store.list_facts.return_value = []
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(
                self._args("list", category=None, entity=None,
                           limit=50, offset=0))
        assert rc == 0
        assert "No facts stored" in capsys.readouterr().out

    def test_stats(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(self._args("stats"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Memory statistics" in out

    def test_log(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_memory_command(
                self._args("log", content="note", key="k", kind="note"))
        assert rc == 0
        assert "Logged session note" in capsys.readouterr().out

    def test_context_empty(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store), \
             mock.patch("yuleosh.memory.llm_context.MemoryContextAssembler") as m:
            m.return_value.assemble.return_value = ""
            rc = handle_memory_command(
                self._args("context", query="q", max_facts=5,
                           max_sessions=3, max_chars=2000))
        assert rc == 0
        assert "No project memory context" in capsys.readouterr().out

    def test_context_hits(self, capsys):
        from yuleosh.memory.cli import handle_memory_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store), \
             mock.patch("yuleosh.memory.llm_context.MemoryContextAssembler") as m:
            m.return_value.assemble.return_value = "context body"
            rc = handle_memory_command(
                self._args("context", query="q", max_facts=5,
                           max_sessions=3, max_chars=2000))
        assert rc == 0
        out = capsys.readouterr().out
        assert "context body" in out

    def test_session_search_empty(self, capsys):
        from yuleosh.memory.cli import handle_session_command
        store = self._store()
        store.search_sessions.return_value = []
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_session_command(
                self._args("search", query="q", limit=20, session_sub="search"))
        assert rc == 0
        assert "No session logs match" in capsys.readouterr().out

    def test_session_search_hits(self, capsys):
        from yuleosh.memory.cli import handle_session_command
        store = self._store()
        with mock.patch("yuleosh.memory.cli.MemoryStore", return_value=store):
            rc = handle_session_command(
                self._args("search", query="q", limit=20, session_sub="search"))
        assert rc == 0
        out = capsys.readouterr().out
        assert "session log(s) matching" in out


# ══════════════════════════════════════════════════════════════════════
# plan/cli.py — plan command routing (extra coverage)
# ══════════════════════════════════════════════════════════════════════


class TestPlanCliRouting:
    def _make_plan(self):
        from yuleosh.plan.models import Plan
        return Plan(
            title="Test Plan",
            objective="objective",
            background="bg",
            technical_approach="ta",
        )

    def test_show_latest_no_plans(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show="latest",
            apply=False, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value=None):
            rc = handle_plan_command(args)
        assert rc == 1
        assert "No saved plans" in capsys.readouterr().out

    def test_show_plan_not_found(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show="p1",
            apply=False, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=None):
            rc = handle_plan_command(args)
        assert rc == 1
        assert "not found" in capsys.readouterr().out

    def test_show_plan_ok(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show="latest",
            apply=False, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=plan), \
             mock.patch("yuleosh.plan.cli.PlanAgent") as agent_cls:
            agent_cls.return_value.to_markdown.return_value = "# Plan"
            rc = handle_plan_command(args)
        assert rc == 0
        assert "# Plan" in capsys.readouterr().out

    def test_list_via_command(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=True, show=None,
            apply=False, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._handle_list", return_value=0) as m:
            rc = handle_plan_command(args)
        assert rc == 0
        m.assert_called_once()

    def test_apply_no_plans(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value=None):
            rc = handle_plan_command(args)
        assert rc == 1
        assert "No saved plans" in capsys.readouterr().out

    def test_apply_plan_not_found(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=None):
            rc = handle_plan_command(args)
        assert rc == 1

    def test_apply_no_steps(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=plan), \
             mock.patch("yuleosh.plan.output.to_pipeline_steps",
                        return_value=[]), \
             mock.patch("yuleosh.plan.cli.PlanAgent") as agent_cls:
            agent_cls.return_value.to_markdown.return_value = "# Plan"
            rc = handle_plan_command(args)
        assert rc == 0

    def test_apply_engine_ok(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        steps = [{"step_id": "s1", "name": "Step 1", "agent": "code"}]
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=plan), \
             mock.patch("yuleosh.plan.output.to_pipeline_steps",
                        return_value=steps), \
             mock.patch("yuleosh.engine.checkpoint.CheckpointEngine") as eng_cls:
            eng_cls.return_value.run.return_value = True
            rc = handle_plan_command(args)
        assert rc == 0

    def test_apply_engine_failed(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        steps = [{"step_id": "s1", "name": "Step 1", "agent": "code"}]
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=plan), \
             mock.patch("yuleosh.plan.output.to_pipeline_steps",
                        return_value=steps), \
             mock.patch("yuleosh.engine.checkpoint.CheckpointEngine") as eng_cls:
            eng_cls.return_value.run.return_value = False
            rc = handle_plan_command(args)
        assert rc == 1

    def test_apply_engine_exception(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=True, description=[], json=False)
        steps = [{"step_id": "s1", "name": "Step 1", "agent": "code"}]
        with mock.patch("yuleosh.plan.cli._get_latest_plan_id",
                        return_value="p1"), \
             mock.patch("yuleosh.plan.cli._load_plan", return_value=plan), \
             mock.patch("yuleosh.plan.output.to_pipeline_steps",
                        return_value=steps), \
             mock.patch("yuleosh.engine.checkpoint.CheckpointEngine",
                        side_effect=RuntimeError("boom")):
            rc = handle_plan_command(args)
        assert rc == 1
        assert "Execution failed" in capsys.readouterr().err

    def test_generate_no_description(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=False, description=[], json=False)
        rc = handle_plan_command(args)
        assert rc == 1
        assert "Please provide a task description" in capsys.readouterr().out

    def test_generate_ok(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        plan = self._make_plan()
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=False, description=["build", "it"], json=False)
        with mock.patch("yuleosh.plan.cli.PlanAgent") as agent_cls:
            agent_cls.return_value.plan.return_value = plan
            agent_cls.return_value.to_markdown.return_value = "# MD"
            rc = handle_plan_command(args)
        assert rc == 0
        assert "# MD" in capsys.readouterr().out

    def test_generate_error(self, capsys):
        import argparse

        from yuleosh.plan.cli import handle_plan_command
        args = argparse.Namespace(
            project_dir=".", list_plans=False, show=None,
            apply=False, description=["build"], json=False)
        with mock.patch("yuleosh.plan.cli.PlanAgent",
                        side_effect=RuntimeError("gen failed")):
            rc = handle_plan_command(args)
        assert rc == 1
        assert "Plan generation failed" in capsys.readouterr().err


# ══════════════════════════════════════════════════════════════════════
# yuleosh/__main__.py — python -m entry point
# ══════════════════════════════════════════════════════════════════════


class TestMainModule:
    def test_main_entry_runs(self, capsys):
        import runpy
        with mock.patch("sys.exit") as exit_mock, \
             mock.patch("yuleosh.cli.main.main", return_value=0) as main_mock:
            runpy.run_module("yuleosh", run_name="__main__")
            main_mock.assert_called_once()
            exit_mock.assert_called_once_with(0)


# ══════════════════════════════════════════════════════════════════════
# pipeline/step_handlers/handler_base.py — retry / checkpoint / base handler
# ══════════════════════════════════════════════════════════════════════


class TestHandlerBase:
    def _session(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        return PipelineSession(
            name="sess", spec_path=str(tmp_path / "spec.md"),
        )

    # -- retry decorator -------------------------------------------------
    def test_retry_success_first_try(self):
        from yuleosh.pipeline.step_handlers.handler_base import retry
        calls = []

        @retry(max_attempts=2, base_delay=0.001)
        def fn():
            calls.append(1)
            return "ok"

        assert fn() == "ok"
        assert len(calls) == 1

    def test_retry_succeeds_after_failure(self):
        from yuleosh.pipeline.step_handlers.handler_base import retry
        calls = []

        @retry(max_attempts=3, base_delay=0.001)
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient")
            return "recovered"

        with mock.patch("yuleosh.pipeline.step_handlers.handler_base.time.sleep"):
            assert fn() == "recovered"
        assert len(calls) == 3

    def test_retry_exhausted_raises(self):
        from yuleosh.pipeline.step_handlers.handler_base import retry
        calls = []

        @retry(max_attempts=2, base_delay=0.001)
        def fn():
            calls.append(1)
            raise ValueError("boom")

        with mock.patch("yuleosh.pipeline.step_handlers.handler_base.time.sleep"), \
             pytest.raises(ValueError):
            fn()
        assert len(calls) == 3  # 1 initial + 2 retries

    def test_retry_ignores_non_matching_exception(self):
        from yuleosh.pipeline.step_handlers.handler_base import retry
        calls = []

        @retry(max_attempts=2, base_delay=0.001,
               exceptions=(RuntimeError,))
        def fn():
            calls.append(1)
            raise ValueError("not retried")

        with pytest.raises(ValueError):
            fn()
        assert len(calls) == 1

    # -- CheckpointManager ----------------------------------------------
    def test_checkpoint_missing(self, tmp_path):
        from yuleosh.pipeline.step_handlers.handler_base import CheckpointManager
        cp = CheckpointManager(tmp_path, "step1")
        assert cp.exists is False
        assert cp.load() is None
        cp.clear()  # no-op on missing file

    def test_checkpoint_save_load_clear(self, tmp_path):
        from yuleosh.pipeline.step_handlers.handler_base import CheckpointManager
        cp = CheckpointManager(tmp_path, "step1")
        cp.save({"result_path": "/tmp/out.json"})
        assert cp.exists is True
        data = cp.load()
        assert data["result_path"] == "/tmp/out.json"
        assert "timestamp" in data
        cp.clear()
        assert cp.exists is False

    def test_checkpoint_ttl_expired(self, tmp_path):
        from yuleosh.pipeline.step_handlers.handler_base import CheckpointManager
        cp = CheckpointManager(tmp_path, "step1", ttl_seconds=1)
        cp.save()
        # Simulate old file
        import os
        old = time.time() - 10
        os.utime(cp._checkpoint_path, (old, old))
        assert cp.exists is False

    def test_checkpoint_corrupt_json(self, tmp_path):
        from yuleosh.pipeline.step_handlers.handler_base import CheckpointManager
        cp = CheckpointManager(tmp_path, "step1")
        cp._checkpoint_path.write_text("{not json")
        assert cp.exists is True
        assert cp.load() is None

    # -- BaseHandler template method ------------------------------------
    def test_handler_normal_execution(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "my-step"

            def execute(self, session):
                return "result.json"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        out = h(session)
        assert out == "result.json"

    def test_handler_pre_check_skips(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "my-step"

            def execute(self, session):
                raise AssertionError("should not run")

            def pre_check(self, session):
                return "missing dep"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        out = h(session)
        assert out.endswith("my-step.json")

    def test_handler_should_skip(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "my-step"

            def execute(self, session):
                raise AssertionError("should not run")

            def should_skip(self, session):
                return True

        h = H()
        session = self._session(tmp_path, monkeypatch)
        out = h(session)
        assert out.endswith("my-step.json")

    def test_handler_checkpoint_hit(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "cp-step"
            use_checkpoint = True

            def execute(self, session):
                raise AssertionError("should not run on checkpoint hit")

        h = H()
        session = self._session(tmp_path, monkeypatch)
        from yuleosh.pipeline.step_handlers.handler_base import CheckpointManager
        CheckpointManager(session.session_dir, "cp-step").save(
            {"result_path": "cached.json"})
        out = h(session)
        assert out == "cached.json"

    def test_handler_checkpoint_saved(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "cp-step"
            use_checkpoint = True

            def execute(self, session):
                return "out.json"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        out = h(session)
        assert out == "out.json"
        cp_file = session.session_dir / ".checkpoint_cp-step"
        assert cp_file.exists()

    def test_handler_retry_flow(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler
        calls = []

        class H(BaseHandler):
            step_name = "retry-step"
            max_retries = 3

            def execute(self, session):
                calls.append(1)
                if len(calls) < 2:
                    raise ConnectionError("transient")
                return "ok.json"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        with mock.patch("yuleosh.pipeline.step_handlers.handler_base.time.sleep"):
            out = h(session)
        assert out == "ok.json"
        assert len(calls) == 2

    def test_handler_soft_failure_wraps(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "fail-step"

            def execute(self, session):
                raise ValueError("hard failure")

        h = H()
        session = self._session(tmp_path, monkeypatch)
        with pytest.raises(PipelineStepError) as ei:
            h(session)
        assert "fail-step" in str(ei.value)

    def test_handler_pipeline_error_passthrough(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "err-step"

            def execute(self, session):
                raise PipelineStepError("already wrapped")

        h = H()
        session = self._session(tmp_path, monkeypatch)
        with pytest.raises(PipelineStepError) as ei:
            h(session)
        assert "already wrapped" in str(ei.value)

    # -- helper methods --------------------------------------------------
    def test_track_llm_usage(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "llm-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        usage = h.track_llm_usage(
            session, {"usage": {"total_tokens": 42}}, "llm-step")
        assert usage == {"total_tokens": 42}
        assert session.token_usage_total == 42
        assert session.token_usage_steps[-1]["step"] == "llm-step"

    def test_call_llm_no_prompts(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "llm-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        with pytest.raises(PipelineStepError) as ei:
            h.call_llm(session)
        assert "prompts not configured" in str(ei.value)

    def test_call_llm_ok(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "llm-step"

            def get_llm_prompts(self, session):
                return ("sys", "user")

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        with mock.patch("yuleosh.pipeline.step_handlers.handler_base._call_llm",
                        return_value={"usage": {"total_tokens": 7}}) as m:
            result = h.call_llm(session, temperature=0.2)
        assert result["usage"]["total_tokens"] == 7
        m.assert_called_once()
        assert session.token_usage_total == 7

    def test_write_output_str(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "w-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        p = h.write_output(session, "plain text", "notes.txt")
        assert Path(p).read_text() == "plain text"

    def test_write_output_dict(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "w-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        p = h.write_output(session, {"a": 1})
        data = json.loads(Path(p).read_text())
        assert data == {"a": 1}

    def test_report_status(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "r-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        p = h.report_status(session, "failed", findings=["f1"],
                            summary="sum", extra={"k": "v"})
        data = json.loads(Path(p).read_text())
        assert data["status"] == "failed"
        assert data["finding_count"] == 1
        assert data["findings"] == ["f1"]
        assert data["k"] == "v"

    def test_report_status_no_findings(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import BaseHandler

        class H(BaseHandler):
            step_name = "r-step"

            def execute(self, session):
                return "x"

        h = H()
        session = self._session(tmp_path, monkeypatch)
        p = h.report_status(session, "ok")
        data = json.loads(Path(p).read_text())
        assert data["finding_count"] == 0
        assert "findings" not in data

    def test_as_handler_success(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.handler_base import as_handler

        @as_handler(step_name="func-step")
        def step_fn(session):
            return "done.json"

        session = self._session(tmp_path, monkeypatch)
        assert step_fn(session) == "done.json"

    def test_as_handler_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers.handler_base import as_handler

        @as_handler(step_name="func-step")
        def step_fn(session):
            raise ValueError("bad")

        session = self._session(tmp_path, monkeypatch)
        with pytest.raises(PipelineStepError):
            step_fn(session)


# ══════════════════════════════════════════════════════════════════════
# pipeline/step_handlers/c_coverage_gate.py — coverage gate step
# ══════════════════════════════════════════════════════════════════════


class TestCCoverageGateStep:
    def _session(self, tmp_path, monkeypatch, mock_mode=False):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        s = PipelineSession(
            name="cgate", spec_path=str(tmp_path / "spec.md"),
        )
        s.mock_mode = mock_mode
        return s

    def _ok_phase(self):
        return {"success": True, "build_dir": "x", "line_rate": 90.0}

    def test_mock_mode_skips(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch, mock_mode=True)
        out = mod.coverage_gate_step(session)
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert data["skipped"] is True
        assert data["gate_passed"] is False

    def test_build_phase_fails(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch)
        with mock.patch.object(mod, "_phase_build_coverage",
                               return_value={"success": False}), \
             pytest.raises(PipelineStepError):
            mod.coverage_gate_step(session)

    def test_gcovr_phase_fails(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch)
        with mock.patch.object(mod, "_phase_build_coverage",
                               return_value=self._ok_phase()), \
             mock.patch.object(mod, "_phase_run_tests",
                               return_value={"success": False}), \
             mock.patch.object(mod, "_phase_run_gcovr",
                               return_value={"success": False}), \
             pytest.raises(PipelineStepError):
                mod.coverage_gate_step(session)

    def test_all_phases_ok(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch)
        with mock.patch.object(mod, "_phase_build_coverage",
                               return_value=self._ok_phase()), \
             mock.patch.object(mod, "_phase_run_tests",
                               return_value={"success": True}), \
             mock.patch.object(mod, "_phase_run_gcovr",
                               return_value={"success": True}), \
             mock.patch.object(mod, "_phase_check_gate",
                               return_value={"success": True, "line_rate": 90.0}):
            out = mod.coverage_gate_step(session)
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert data["gate_passed"] is True

    def test_gate_phase_fails_raises(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch)
        with mock.patch.object(mod, "_phase_build_coverage",
                               return_value=self._ok_phase()), \
             mock.patch.object(mod, "_phase_run_tests",
                               return_value={"success": True}), \
             mock.patch.object(mod, "_phase_run_gcovr",
                               return_value={"success": True}), \
             mock.patch.object(mod, "_phase_check_gate",
                               return_value={"success": False,
                                             "error": "line rate too low"}), \
             pytest.raises(PipelineStepError):
                mod.coverage_gate_step(session)

    def test_unexpected_error_wrapped(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineStepError
        from yuleosh.pipeline.step_handlers import c_coverage_gate as mod
        session = self._session(tmp_path, monkeypatch)
        with mock.patch.object(mod, "_phase_build_coverage",
                               side_effect=RuntimeError("boom")), \
             pytest.raises(PipelineStepError):
            mod.coverage_gate_step(session)

    def test_get_fail_under_default(self, tmp_path):
        from yuleosh.pipeline.step_handlers.c_coverage_gate import _get_fail_under
        assert _get_fail_under(str(tmp_path)) == 70

    def test_get_fail_under_top_level(self, tmp_path):
        from yuleosh.pipeline.step_handlers.c_coverage_gate import _get_fail_under
        cfg = tmp_path / ".yuleosh.yaml"
        cfg.write_text("coverage:\n  c_fail_under: 85\n")
        assert _get_fail_under(str(tmp_path)) == 85

    def test_get_fail_under_ci_style(self, tmp_path):
        from yuleosh.pipeline.step_handlers.c_coverage_gate import _get_fail_under
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("ci:\n  coverage:\n    c_fail_under: 60\n")
        assert _get_fail_under(str(tmp_path)) == 60

    def test_get_fail_under_bad_yaml_falls_back(self, tmp_path):
        from yuleosh.pipeline.step_handlers.c_coverage_gate import _get_fail_under
        cfg = tmp_path / ".yuleosh.yaml"
        cfg.write_text(": : : not yaml")
        assert _get_fail_under(str(tmp_path)) == 70

    def test_write_results(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.c_coverage_gate import _write_results
        session = self._session(tmp_path, monkeypatch)
        out = _write_results(session, {"gate_passed": True})
        assert Path(out).exists()
        assert json.loads(Path(out).read_text())["gate_passed"] is True


# ══════════════════════════════════════════════════════════════════════
# pipeline/async_runner.py — async pipeline scheduler
# ══════════════════════════════════════════════════════════════════════


class TestAsyncRunner:
    def _fresh_jobs(self, monkeypatch):
        import yuleosh.pipeline.async_runner as mod
        monkeypatch.setattr(mod, "_PIPELINE_JOBS", {})
        return mod

    def test_submit_pipeline_creates_job(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool") as pool:
            job_id = mod.submit_pipeline("/proj", layer=1)
        assert job_id in mod._PIPELINE_JOBS
        assert mod._PIPELINE_JOBS[job_id]["status"] == "queued"
        pool.return_value.submit.assert_called_once()

    def test_submit_full_pipeline_creates_job(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool") as pool:
            job_id = mod.submit_full_pipeline("/proj", config_json="{}")
        assert job_id in mod._PIPELINE_JOBS
        assert mod._PIPELINE_JOBS[job_id]["type"] == "full_pipeline"
        pool.return_value.submit.assert_called_once()

    def test_run_ci_job_layer1_pass(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=1)
        with mock.patch.dict("sys.modules", {
            "yuleosh.ci": mock.MagicMock(run_layer1=lambda p: "compiled"),
        }):
            mod._run_ci_job(job_id, "/proj", 1)
        job = mod._PIPELINE_JOBS[job_id]
        assert job["status"] == "passed"
        assert job["progress"] == 100

    def test_run_ci_job_layer2_dict_result(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=2)
        fake_ci = mock.MagicMock()
        fake_ci.run_layer2.return_value = "misra ok"
        with mock.patch.dict("sys.modules", {"yuleosh.ci": fake_ci}):
            mod._run_ci_job(job_id, "/proj", 2)
        assert mod._PIPELINE_JOBS[job_id]["status"] == "passed"

    def test_run_ci_job_layer3(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=3)
        fake_ci = mock.MagicMock()
        fake_ci.run_layer3.return_value = {"coverage": 90}
        with mock.patch.dict("sys.modules", {"yuleosh.ci": fake_ci}):
            mod._run_ci_job(job_id, "/proj", 3)
        assert mod._PIPELINE_JOBS[job_id]["status"] == "passed"

    def test_run_ci_job_default_all(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=99)
        fake_run = mock.MagicMock()
        fake_run.run_all.return_value = "all done"
        with mock.patch.dict("sys.modules", {
            "yuleosh.ci.run": fake_run,
        }):
            mod._run_ci_job(job_id, "/proj", 99)
        assert mod._PIPELINE_JOBS[job_id]["status"] == "passed"

    def test_run_ci_job_failure_explicit(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=1)
        fake_ci = mock.MagicMock()
        fake_ci.run_layer1.side_effect = RuntimeError("compile broke")
        with mock.patch.dict("sys.modules", {"yuleosh.ci": fake_ci}):
            mod._run_ci_job(job_id, "/proj", 1)
        job = mod._PIPELINE_JOBS[job_id]
        assert job["status"] == "failed"
        assert "compile broke" in job["result"]

    def test_run_ci_job_missing_job(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        mod._run_ci_job("nonexistent", "/proj", 1)  # no-op

    def test_full_pipeline_arxml_path(self, tmp_path, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            job_id = mod.submit_full_pipeline(
                str(tmp_path), arxml_content="<arxml/>")
        arxml_dir = tmp_path / ".yuleosh" / "pipeline" / job_id
        with mock.patch.object(mod, "_update_stage"), \
             mock.patch.object(mod, "_notify_pipeline_completion"), \
             mock.patch.object(mod.time, "sleep"):
            mod._run_full_pipeline(job_id, str(tmp_path), None, "<arxml/>")
        assert (arxml_dir / "config.arxml").exists()
        job = mod._PIPELINE_JOBS[job_id]
        assert job["status"] == "passed"

    def test_full_pipeline_config_json(self, tmp_path, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            job_id = mod.submit_full_pipeline(str(tmp_path), config_json='{"a":1}')
        cfg_dir = tmp_path / ".yuleosh" / "pipeline" / job_id
        with mock.patch.object(mod, "_update_stage"), \
             mock.patch.object(mod, "_notify_pipeline_completion"), \
             mock.patch.object(mod.time, "sleep"):
            mod._run_full_pipeline(job_id, str(tmp_path), '{"a":1}', None)
        assert (cfg_dir / "config.json").exists()
        assert mod._PIPELINE_JOBS[job_id]["status"] == "passed"

    def test_full_pipeline_no_config(self, tmp_path, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            job_id = mod.submit_full_pipeline(str(tmp_path))
        with mock.patch.object(mod, "_update_stage"), \
             mock.patch.object(mod, "_notify_pipeline_completion"), \
             mock.patch.object(mod.time, "sleep"):
            mod._run_full_pipeline(job_id, str(tmp_path), None, None)
        assert mod._PIPELINE_JOBS[job_id]["status"] == "passed"

    def test_full_pipeline_failure(self, tmp_path, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            job_id = mod.submit_full_pipeline(str(tmp_path), config_json="{}")
        with mock.patch.object(mod, "_update_stage"), \
             mock.patch.object(mod, "_notify_pipeline_completion"), \
             mock.patch.object(mod.time, "sleep"), \
             mock.patch("yuleosh.ci.run_layer1",
                        side_effect=RuntimeError("compile fail")):
            mod._run_full_pipeline(job_id, str(tmp_path), "{}", None)
        job = mod._PIPELINE_JOBS[job_id]
        assert job["status"] == "failed"
        assert "compile fail" in str(job["result"])

    def test_get_job_status(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=1)
        assert mod.get_job_status(job_id) is not None
        assert mod.get_job_status("nope") is None

    def test_list_jobs_sorted(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            mod.submit_pipeline("/proj", layer=1)
        jobs = mod.list_jobs()
        assert len(jobs) == 1

    def test_get_pipeline_stats(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        with mock.patch.object(mod, "_get_pool"):
            mod.submit_pipeline("/proj", layer=1)
        st = mod.get_pipeline_stats()
        assert st["total"] == 1
        assert st["queued"] == 1

    def test_notify_completion_writes_file(self, tmp_path, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        job_id = mod.submit_pipeline("/proj", layer=1)
        job = mod._PIPELINE_JOBS[job_id]
        job["status"] = "passed"
        job["type"] = "ci_layer"
        mod._notify_pipeline_completion(job_id)
        notify_dir = tmp_path / "reports" / "pipeline-notify"
        files = list(notify_dir.glob("*.json"))
        assert len(files) >= 1

    def test_notify_skips_non_terminal(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        job_id = mod.submit_pipeline("/proj", layer=1)
        mod._notify_pipeline_completion(job_id)  # status=queued -> no-op

    def test_get_pool_singleton(self, monkeypatch):
        mod = self._fresh_jobs(monkeypatch)
        monkeypatch.setattr(mod, "_pool", None)
        p1 = mod._get_pool()
        p2 = mod._get_pool()
        assert p1 is p2


# ══════════════════════════════════════════════════════════════════════
# ui/routes/billing_routes.py — billing usage API
# ══════════════════════════════════════════════════════════════════════


class TestBillingRoutes:
    def _handler(self, token="tok123"):
        h = mock.MagicMock()
        h.headers = {"Authorization": "Bearer " + token}
        return h

    def _user(self, slug="acme"):
        return {"user_id": 1, "org_slug": slug, "role": "admin"}

    # -- dispatcher ------------------------------------------------------
    def test_dispatcher_usage(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "handle_get_usage",
                               return_value=({}, 200)) as m:
            resp = mod.handle_billing("GET", "usage", {}, {}, handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_plan(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "handle_get_plan",
                               return_value=({}, 200)) as m:
            resp = mod.handle_billing("GET", "plan", {}, {}, handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_upgrade(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "handle_upgrade_plan",
                               return_value=({}, 200)) as m:
            resp = mod.handle_billing("POST", "upgrade", {}, {}, handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_method_not_allowed(self):
        from yuleosh.ui.routes import billing_routes as mod
        resp = mod.handle_billing("DELETE", "usage", {}, {}, handler=self._handler())
        assert resp[1] == 405

    def test_dispatcher_unknown_sub(self):
        from yuleosh.ui.routes import billing_routes as mod
        resp = mod.handle_billing("GET", "bogus", {}, {}, handler=self._handler())
        assert resp[1] == 405

    # -- auth helpers ----------------------------------------------------
    def test_get_token_missing(self):
        from yuleosh.ui.routes.billing_routes import _get_token
        h = mock.MagicMock()
        h.headers = {}
        assert _get_token(h) is None

    def test_get_token_bearer(self):
        from yuleosh.ui.routes.billing_routes import _get_token
        assert _get_token(self._handler("abc")) == "abc"

    def test_require_auth_no_token(self):
        from yuleosh.ui.routes.billing_routes import _require_auth
        h = mock.MagicMock()
        h.headers = {}
        assert _require_auth(h) is None

    def test_require_auth_ok(self):
        from yuleosh.ui.routes import billing_routes as mod
        from yuleosh.ui.routes.billing_routes import _require_auth
        with mock.patch.object(mod, "get_session_user", return_value=self._user()):
            assert _require_auth(self._handler())["org_slug"] == "acme"

    def test_auth_error_missing_token(self):
        from yuleosh.ui.routes.billing_routes import _auth_error
        h = mock.MagicMock()
        h.headers = {}
        resp, code = _auth_error(h)
        assert code == 401
        assert "Authorization required" in resp["error"]

    def test_auth_error_invalid_session(self):
        from yuleosh.ui.routes.billing_routes import _auth_error
        resp, code = _auth_error(self._handler("badtoken"))
        assert code == 401
        assert "Invalid session" in resp["error"]

    # -- usage -----------------------------------------------------------
    def test_usage_no_auth(self):
        from yuleosh.ui.routes import billing_routes as mod
        h = mock.MagicMock()
        h.headers = {}
        _, code = mod.handle_get_usage("GET", "usage", {}, {}, handler=h)
        assert code == 401

    def test_usage_forbidden(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=False):
            _, code = mod.handle_get_usage("GET", "usage", {}, {},
                                              handler=self._handler())
        assert code == 403

    def test_usage_no_org(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user",
                               return_value={"user_id": 1, "org_slug": ""}), \
             mock.patch("yuleosh.rbac.check_role", return_value=True):
            _, code = mod.handle_get_usage("GET", "usage", {}, {},
                                              handler=self._handler())
        assert code == 404

    def test_usage_ok(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch.object(mod, "UsageMeter") as meter_cls:
            meter_cls.return_value.get_usage_summary.return_value = {"calls": 5}
            resp, code = mod.handle_get_usage("GET", "usage", {}, {},
                                              handler=self._handler())
        assert code == 200
        assert resp["calls"] == 5

    # -- plan ------------------------------------------------------------
    def test_plan_ok(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch.object(mod, "BillingManager") as billing_cls:
            billing_cls.return_value.get_subscription.return_value = {
                "plan": "pro", "status": "active", "mock": True}
            resp, code = mod.handle_get_plan("GET", "plan", {}, {},
                                             handler=self._handler())
        assert code == 200
        assert resp["current_plan"] == "pro"
        assert len(resp["available_plans"]) == 3

    # -- upgrade ---------------------------------------------------------
    def test_upgrade_no_auth(self):
        from yuleosh.ui.routes import billing_routes as mod
        h = mock.MagicMock()
        h.headers = {}
        _, code = mod.handle_upgrade_plan("POST", "upgrade", {}, {}, handler=h)
        assert code == 401

    def test_upgrade_forbidden(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=False):
            _, code = mod.handle_upgrade_plan(
                "POST", "upgrade", {"plan": "pro"}, {}, handler=self._handler())
        assert code == 403

    def test_upgrade_invalid_plan(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=True):
            _, code = mod.handle_upgrade_plan(
                "POST", "upgrade", {"plan": "platinum"}, {}, handler=self._handler())
        assert code == 400

    def test_upgrade_checkout_error(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch.object(mod, "BillingManager") as billing_cls:
            billing_cls.return_value.create_checkout_session.return_value = {
                "error": "stripe down"}
            _, code = mod.handle_upgrade_plan(
                "POST", "upgrade", {"plan": "pro"}, {}, handler=self._handler())
        assert code == 400

    def test_upgrade_ok(self):
        from yuleosh.ui.routes import billing_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch.object(mod, "BillingManager") as billing_cls:
            billing_cls.return_value.create_checkout_session.return_value = {
                "checkout_url": "https://stripe/x"}
            resp, code = mod.handle_upgrade_plan(
                "POST", "upgrade", {"plan": "enterprise"}, {}, handler=self._handler())
        assert code == 200
        assert "checkout_url" in resp


# ══════════════════════════════════════════════════════════════════════
# ui/routes/tenant_routes.py — multi-tenant API (SAAS-1 / A3)
# ══════════════════════════════════════════════════════════════════════


class TestTenantRoutes:
    """Coverage for src/yuleosh/ui/routes/tenant_routes.py (104 stmts)."""

    def _handler(self, token="tok123"):
        h = mock.MagicMock()
        h.headers = {"Authorization": "Bearer " + token}
        return h

    def _user(self, role="admin", slug="acme"):
        return {"user_id": 1, "org_slug": slug, "role": role}

    def _tenant(self, plan="pro", slug="acme", name="Acme"):
        from yuleosh.tenant.model import Tenant
        return Tenant(id=slug, name=name, plan=plan)

    def _patch_store(self, mod, tenant=None, projects=None, updated=None,
                     listed=None):
        """Patch TenantStore inside tenant_routes with a fake store."""
        store = mock.MagicMock()
        store.get.return_value = tenant
        store.list_projects.return_value = projects if projects is not None else []
        store.update.return_value = updated if updated is not None else tenant
        store.list_tenants.return_value = listed if listed is not None else []
        store.save_project.return_value = {"slug": "p1"}
        return mock.patch.object(mod, "TenantStore", return_value=store), store

    # -- dispatcher ------------------------------------------------------
    def test_dispatcher_get_info(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "handle_tenant_info",
                               return_value=({}, 200)) as m:
            resp = mod.handle_tenant("GET", "acme", {}, {}, handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_get_projects(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "handle_tenant_projects",
                               return_value=({}, 200)) as m:
            resp = mod.handle_tenant("GET", "acme/projects", {}, {},
                                     handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_get_usage(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "handle_usage_check",
                               return_value=({}, 200)) as m:
            resp = mod.handle_tenant("GET", "acme/usage", {}, {},
                                     handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_put_update(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "handle_tenant_update",
                               return_value=({}, 200)) as m:
            resp = mod.handle_tenant("PUT", "acme", {"name": "X"}, {},
                                     handler=self._handler())
        assert resp == ({}, 200)
        m.assert_called_once()

    def test_dispatcher_post_projects(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "handle_tenant_project_create",
                               return_value=({}, 201)) as m:
            resp = mod.handle_tenant("POST", "acme/projects", {"slug": "p1"}, {},
                                     handler=self._handler())
        assert resp == ({}, 201)
        m.assert_called_once()

    def test_dispatcher_unknown_405(self):
        from yuleosh.ui.routes import tenant_routes as mod
        resp, code = mod.handle_tenant("DELETE", "acme", {}, {},
                                       handler=self._handler())
        assert code == 405
        assert "Method not allowed" in resp["error"]

    def test_dispatcher_unknown_sub_405(self):
        from yuleosh.ui.routes import tenant_routes as mod
        _, code = mod.handle_tenant("GET", "acme/bogus", {}, {},
                                       handler=self._handler())
        assert code == 405

    # -- auth helpers ----------------------------------------------------
    def test_get_bearer_token_ok(self):
        from yuleosh.ui.routes.tenant_routes import _get_bearer_token
        assert _get_bearer_token(self._handler("abc")) == "abc"

    def test_get_bearer_token_missing(self):
        from yuleosh.ui.routes.tenant_routes import _get_bearer_token
        h = mock.MagicMock()
        h.headers = {}
        assert _get_bearer_token(h) is None

    def test_get_bearer_token_not_bearer(self):
        from yuleosh.ui.routes.tenant_routes import _get_bearer_token
        h = mock.MagicMock()
        h.headers = {"Authorization": "Basic abc"}
        assert _get_bearer_token(h) is None

    def test_require_auth_no_token(self):
        from yuleosh.ui.routes.tenant_routes import _require_auth
        h = mock.MagicMock()
        h.headers = {}
        assert _require_auth(h) is None

    def test_require_auth_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        from yuleosh.ui.routes.tenant_routes import _require_auth
        with mock.patch.object(mod, "get_session_user", return_value=self._user()):
            user = _require_auth(self._handler())
        assert user["org_slug"] == "acme"

    def test_auth_error_missing(self):
        from yuleosh.ui.routes.tenant_routes import _auth_error
        h = mock.MagicMock()
        h.headers = {}
        resp, code = _auth_error(h)
        assert code == 401
        assert "Authorization required" in resp["error"]

    def test_auth_error_invalid_session(self):
        from yuleosh.ui.routes.tenant_routes import _auth_error
        resp, code = _auth_error(self._handler("badtoken"))
        assert code == 401
        assert "Invalid or expired session" in resp["error"]

    # -- handle_tenant_info ---------------------------------------------
    def test_info_no_auth(self):
        from yuleosh.ui.routes import tenant_routes as mod
        h = mock.MagicMock()
        h.headers = {}
        _, code = mod.handle_tenant_info("GET", "acme", {}, {}, handler=h)
        assert code == 401

    def test_info_no_slug(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()):
            resp, code = mod.handle_tenant_info("GET", "", {}, {},
                                                handler=self._handler())
        assert code == 400
        assert "slug required" in resp["error"]

    def test_info_not_found(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=None)[0]:
            resp, code = mod.handle_tenant_info("GET", "acme", {}, {},
                                                handler=self._handler())
        assert code == 404
        assert "Tenant not found" in resp["error"]

    def test_info_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant()
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=tenant)[0]:
            resp, code = mod.handle_tenant_info("GET", "acme", {}, {},
                                                handler=self._handler())
        assert code == 200
        assert resp["id"] == "acme"
        assert resp["name"] == "Acme"
        assert resp["plan"] == "pro"
        assert "limits" in resp

    # -- handle_tenant_update --------------------------------------------
    def test_update_no_auth(self):
        from yuleosh.ui.routes import tenant_routes as mod
        h = mock.MagicMock()
        h.headers = {}
        _, code = mod.handle_tenant_update("PUT", "acme", {"name": "X"}, {},
                                              handler=h)
        assert code == 401

    def test_update_non_admin(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user",
                               return_value=self._user(role="member")):
            resp, code = mod.handle_tenant_update(
                "PUT", "acme", {"name": "X"}, {}, handler=self._handler())
        assert code == 403
        assert "Admin role required" in resp["error"]

    def test_update_value_error(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()):
            store = mock.MagicMock()
            store.update.side_effect = ValueError("Tenant 'acme' not found.")
            with mock.patch.object(mod, "TenantStore", return_value=store):
                resp, code = mod.handle_tenant_update(
                    "PUT", "acme", {"name": "X"}, {}, handler=self._handler())
        assert code == 400
        assert "not found" in resp["error"]

    def test_update_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant()
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, updated=tenant)[0]:
            resp, code = mod.handle_tenant_update(
                "PUT", "acme", {"name": "Acme2"}, {}, handler=self._handler())
        assert code == 200
        assert resp["id"] == "acme"
        assert resp["plan"] == "pro"

    # -- handle_tenant_list ----------------------------------------------
    def test_list_admin(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant()
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, listed=[tenant])[0]:
            resp, code = mod.handle_tenant_list("GET", "", {}, {},
                                                handler=self._handler())
        assert code == 200
        assert len(resp["tenants"]) == 1
        assert resp["tenants"][0]["id"] == "acme"

    def test_list_non_admin_sees_own_org(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant()
        store = mock.MagicMock()
        store.get.return_value = tenant
        store.list_tenants.return_value = []  # must NOT be called
        with mock.patch.object(mod, "get_session_user",
                               return_value=self._user(role="member")), \
             mock.patch.object(mod, "TenantStore", return_value=store):
            resp, code = mod.handle_tenant_list("GET", "", {}, {},
                                                handler=self._handler())
        assert code == 200
        assert len(resp["tenants"]) == 1
        assert resp["tenants"][0]["id"] == "acme"
        store.list_tenants.assert_not_called()

    def test_list_non_admin_no_tenant(self):
        from yuleosh.ui.routes import tenant_routes as mod
        store = mock.MagicMock()
        store.get.return_value = None
        with mock.patch.object(mod, "get_session_user",
                               return_value=self._user(role="member")), \
             mock.patch.object(mod, "TenantStore", return_value=store):
            resp, code = mod.handle_tenant_list("GET", "", {}, {},
                                                handler=self._handler())
        assert code == 200
        assert resp["tenants"] == []

    # -- handle_tenant_projects ------------------------------------------
    def test_projects_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, projects=[{"slug": "p1"}])[0]:
            resp, code = mod.handle_tenant_projects(
                "GET", "acme/projects", {}, {}, handler=self._handler())
        assert code == 200
        assert resp["projects"] == [{"slug": "p1"}]

    # -- handle_tenant_project_create ------------------------------------
    def test_create_limit_reached(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant(plan="free")  # max_projects = 1
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=tenant,
                               projects=[{"slug": "p1"}])[0]:
            resp, code = mod.handle_tenant_project_create(
                "POST", "acme/projects", {"slug": "p2"}, {},
                handler=self._handler())
        assert code == 403
        assert "Project limit reached" in resp["error"]

    def test_create_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant(plan="pro")  # max_projects = 10
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=tenant, projects=[])[0]:
            resp, code = mod.handle_tenant_project_create(
                "POST", "acme/projects", {"slug": "p1"}, {},
                handler=self._handler())
        assert code == 201
        assert "project" in resp

    # -- handle_usage_check ----------------------------------------------
    def test_usage_not_found(self):
        from yuleosh.ui.routes import tenant_routes as mod
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=None)[0]:
            resp, code = mod.handle_usage_check("GET", "acme/usage", {}, {},
                                                handler=self._handler())
        assert code == 404
        assert "Tenant not found" in resp["error"]

    def test_usage_ok(self):
        from yuleosh.ui.routes import tenant_routes as mod
        tenant = self._tenant(plan="pro")
        with mock.patch.object(mod, "get_session_user", return_value=self._user()), \
             self._patch_store(mod, tenant=tenant,
                               projects=[{"slug": "p1"}, {"slug": "p2"}])[0]:
            resp, code = mod.handle_usage_check("GET", "acme/usage", {}, {},
                                                handler=self._handler())
        assert code == 200
        assert resp["tenant"] == "acme"
        assert resp["plan"] == "pro"
        assert resp["usage"]["projects"] == 2
        assert resp["usage"]["projects_limit"] == 10
