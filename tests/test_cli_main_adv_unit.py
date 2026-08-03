"""
Unit tests for yuleosh.cli.main — Wave 2b (advanced command groups).

Covers: traceability (report/export/matrix), MISRA (deviate/trend/profile/
report/summary/html), KPI CI alert, SWE.6 (status/check), review diff,
and main() dispatch branches that were previously untested.

Patches target lazy-import binding sites; OSH_HOME patched via
monkeypatch.setattr(main_module, "OSH_HOME", ...).
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


@pytest.fixture
def main_module():
    import yuleosh.cli.main as m
    return m


@pytest.fixture
def osh_home(main_module, tmp_path, monkeypatch):
    """Point main_module.OSH_HOME at a temp dir and restore afterwards."""
    monkeypatch.setattr(main_module, "OSH_HOME", str(tmp_path))
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════
# Traceability commands
# ═══════════════════════════════════════════════════════════════════════


class TestTraceability:
    def test_report_with_recs(self, main_module, osh_home):
        r = {"coverage_summary": {"requirements_total": 5, "test_coverage_pct": 80.0,
                                  "code_coverage": 70, "review_coverage": 60,
                                  "total_gaps": 1, "orphaned_tests": 2},
             "recommendations": ["Add tests for RS-002"]}
        with patch("yuleosh.alm.traceability.generate_traceability_report", return_value=r) as mc:
            with patch("builtins.print"):
                main_module.cmd_traceability_report(
                    SimpleNamespace(project_dir=str(osh_home), spec=None))
            mc.assert_called_once()
            # generator is mocked; verify the output_dir wiring instead of dir side effects
            kwargs = mc.call_args.kwargs
            assert kwargs["output_dir"] == os.path.join(str(osh_home), ".yuleosh", "reports")

    def test_report_minimal(self, main_module, osh_home):
        r = {"coverage_summary": {"test_coverage_pct": 50.0}, "recommendations": []}
        with patch("yuleosh.alm.traceability.generate_traceability_report", return_value=r):
            with patch("builtins.print"):
                main_module.cmd_traceability_report(
                    SimpleNamespace(project_dir=str(osh_home), spec="spec.md"))

    def test_export(self, main_module, osh_home):
        with patch("yuleosh.knowledge_graph.get_store", return_value=MagicMock()):
            with patch("yuleosh.evidence.oem_templates.export_traceability_matrix",
                       return_value="# Matrix") as mc:
                with patch("builtins.print"):
                    main_module.cmd_traceability_export(
                        SimpleNamespace(project_dir=str(osh_home), template="generic",
                                        output_format="markdown", layer=None,
                                        no_evidence=False))
                mc.assert_called_once()
        assert (osh_home / ".yuleosh" / "reports" / "traceability-generic-matrix.md").exists()

    def test_export_csv(self, main_module, osh_home):
        with patch("yuleosh.knowledge_graph.get_store", return_value=MagicMock()):
            with patch("yuleosh.evidence.oem_templates.export_traceability_matrix",
                       return_value="a,b"):
                with patch("builtins.print"):
                    main_module.cmd_traceability_export(
                        SimpleNamespace(project_dir=str(osh_home), template="vw",
                                        output_format="csv", layer="unit",
                                        no_evidence=True))
        assert (osh_home / ".yuleosh" / "reports" / "traceability-vw-matrix.csv").exists()

    def test_matrix_with_build_id(self, main_module, osh_home):
        r = {"lrm": {"generated_at": "2026-01-01T00:00:00", "requirements": [
            {"req_id": "BLD-1", "id": "S1", "has_code": True, "has_test": True,
             "has_review": True, "section": "S", "step_handlers": ["h1"]},
            {"req_id": "OTHER-2", "id": "S2", "has_code": False, "has_test": False,
             "has_review": False, "section": "", "step_handlers": []},
        ]}, "gap_analysis": {"gaps": [
            {"type": "no_test", "req_id": "OTHER-2", "statement": "x" * 60}]}}
        with patch("yuleosh.alm.traceability.generate_lrt", return_value=r):
            with patch("builtins.print"):
                main_module.cmd_traceability_matrix(
                    SimpleNamespace(project_dir=str(osh_home), spec=None, build_id="BLD"))

    def test_matrix_no_build_id(self, main_module, osh_home):
        r = {"lrm": {"generated_at": "2026-01-01T00:00:00", "requirements": [],
                      "summary": {}}, "gap_analysis": {"gaps": []}}
        with patch("yuleosh.alm.traceability.generate_lrt", return_value=r):
            with patch("builtins.print"):
                main_module.cmd_traceability_matrix(
                    SimpleNamespace(project_dir=str(osh_home), spec=None, build_id=None))


# ═══════════════════════════════════════════════════════════════════════
# MISRA deviate
# ═══════════════════════════════════════════════════════════════════════


def _dev(rule_id="Rule-17.7", file_pattern="src/legacy/*.c", status="open",
         approved_by="alice", expires="2026-12-31", reason="legacy"):
    d = MagicMock()
    d.rule_id = rule_id
    d.file_pattern = file_pattern
    d.reason = reason
    d.approved_by = approved_by
    d.expires = expires
    d.status = status
    return d


class TestMisraDeviate:
    def test_list_empty(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = []
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_deviate(SimpleNamespace(deviate_sub="list", json=False))
                assert any("No deviation" in str(c) for c in mp.call_args_list)

    def test_list_table(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_deviate(SimpleNamespace(deviate_sub="list", json=False))
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "Rule-17.7" in out

    def test_list_json(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_deviate(SimpleNamespace(deviate_sub="list", json=True))
                out = " ".join(str(c) for c in mp.call_args_list)
                assert '"rule_id": "Rule-17.7"' in out

    def test_approve_ok(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("yuleosh.ci.config.update_deviation_status", return_value=True) as mc:
                with patch("builtins.print"):
                    main_module.cmd_misra_deviate(
                        SimpleNamespace(deviate_sub="approve",
                                        dev_id="Rule-17.7:src/legacy/*.c"))
                mc.assert_called_once_with(str(osh_home), "Rule-17.7", "src/legacy/*.c", "approved")

    def test_approve_rule_only(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("yuleosh.ci.config.update_deviation_status", return_value=True):
                with patch("builtins.print"):
                    main_module.cmd_misra_deviate(
                        SimpleNamespace(deviate_sub="approve", dev_id="Rule-17.7"))

    def test_approve_invalid_id(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with pytest.raises(SystemExit):
                main_module.cmd_misra_deviate(
                    SimpleNamespace(deviate_sub="approve", dev_id=""))

    def test_approve_not_found(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with pytest.raises(SystemExit):
                main_module.cmd_misra_deviate(
                    SimpleNamespace(deviate_sub="approve", dev_id="Nope-1:x"))

    def test_approve_update_fail(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("yuleosh.ci.config.update_deviation_status", return_value=False):
                with pytest.raises(SystemExit):
                    main_module.cmd_misra_deviate(
                        SimpleNamespace(deviate_sub="approve", dev_id="Rule-17.7"))

    def test_reject_ok(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = [_dev()]
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("yuleosh.ci.config.update_deviation_status", return_value=True) as mc:
                with patch("builtins.print"):
                    main_module.cmd_misra_deviate(
                        SimpleNamespace(deviate_sub="reject", dev_id="Rule-17.7"))
                mc.assert_called_once_with(str(osh_home), "Rule-17.7", "src/legacy/*.c", "rejected")

    def test_unknown_sub(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.deviations = []
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with pytest.raises(SystemExit):
                main_module.cmd_misra_deviate(SimpleNamespace(deviate_sub="nope", json=False))


class TestParseDevId:
    def test_with_colon(self, main_module):
        assert main_module._parse_dev_id("R-1:src/*.c") == ("R-1", "src/*.c")

    def test_rule_only(self, main_module):
        assert main_module._parse_dev_id("R-1") == ("R-1", "")

    def test_empty(self, main_module):
        assert main_module._parse_dev_id("") == ("", "")


class TestCliAddDeviation:
    def test_config_missing(self, main_module, tmp_path):
        with pytest.raises(SystemExit):
            main_module._cli_add_deviation(str(tmp_path), "R-1", "src/*.c")

    def test_create_ok(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("misra:\n  deviations: []\n")
        with patch("builtins.print"):
            main_module._cli_add_deviation(str(tmp_path), "R-1", "src/*.c",
                                           reason="r", approved_by="bob",
                                           expires="2027-01-01", status="open")
        raw = __import__("yaml").safe_load(cfg.read_text())
        assert raw["misra"]["deviations"][0]["rule"] == "R-1"

    def test_create_yaml_error(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("{broken: [")
        import yaml
        with patch.object(yaml, "safe_load", side_effect=yaml.YAMLError("bad")):
            with pytest.raises(SystemExit):
                main_module._cli_add_deviation(str(tmp_path), "R-1", "src/*.c")

    def test_create_write_error(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("misra: {}\n")
        import yaml
        with patch.object(yaml, "dump", side_effect=OSError("disk full")):
            with pytest.raises(SystemExit):
                main_module._cli_add_deviation(str(tmp_path), "R-1", "src/*.c")


class TestInteractiveAddDeviation:
    def test_config_missing(self, main_module, tmp_path):
        with pytest.raises(SystemExit):
            main_module._interactive_add_deviation(str(tmp_path))

    def test_eof_cancelled(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("misra: {}\n")
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(SystemExit):
                main_module._interactive_add_deviation(str(tmp_path))

    def test_missing_rule(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("misra: {}\n")
        with patch("builtins.input", side_effect=["", "", "", "", ""]):
            with pytest.raises(SystemExit):
                main_module._interactive_add_deviation(str(tmp_path))

    def test_add_ok(self, main_module, tmp_path):
        cfg = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg.parent.mkdir(parents=True)
        cfg.write_text("misra: {}\n")
        with patch("builtins.input", side_effect=["R-2", "src/x.c", "why", "carol", "2027-06-01"]):
            with patch("builtins.print"):
                main_module._interactive_add_deviation(str(tmp_path))
        raw = __import__("yaml").safe_load(cfg.read_text())
        assert raw["misra"]["deviations"][0]["status"] == "pending"


# ═══════════════════════════════════════════════════════════════════════
# MISRA trend / profile / report
# ═══════════════════════════════════════════════════════════════════════


class TestMisraTrend:
    def test_trend_cmd(self, main_module, osh_home):
        with patch("yuleosh.ci.misra_trend.show_trend", return_value="T") as mc:
            with patch("builtins.print"):
                main_module.cmd_misra_trend(
                    SimpleNamespace(lines=30, days=30, json=True))
            mc.assert_called_once()


class TestMisraProfile:
    def test_list_with_rules_file(self, main_module, osh_home):
        (osh_home / "misra-rules.yaml").write_text(
            "meta: {}\nR-1:\n  profile: safety\nR-2:\n  profile: performance\nR-3:\n  profile: extra\n")
        cfg = MagicMock()
        prof = MagicMock()
        prof.name = "Safety"
        prof.rule_overrides = ["R-1"]
        prof.deviations = [_dev()]
        cfg.misra.profiles = {"safety": prof}
        cfg.misra.active_profile = "safety"
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_profile_list()
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "safety" in out

    def test_list_no_rules_file(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.profiles = {}
        cfg.misra.active_profile = "safety"
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print"):
                main_module.cmd_misra_profile_list()

    def test_set_no_profiles(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.profiles = {}
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_profile_set("safety")
                assert any("No MISRA profiles" in str(c) for c in mp.call_args_list)

    def test_set_unknown(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.profiles = {"safety": MagicMock(name="Safety")}
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print") as mp:
                main_module.cmd_misra_profile_set("nope")
                assert any("not found" in str(c) for c in mp.call_args_list)

    def test_set_config_missing(self, main_module, osh_home):
        cfg = MagicMock()
        cfg.misra.profiles = {"safety": MagicMock(name="Safety")}
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print"):
                main_module.cmd_misra_profile_set("safety")

    def test_set_ok(self, main_module, osh_home):
        cfg_path = osh_home / ".yuleosh" / "ci-config.yaml"
        cfg_path.parent.mkdir(parents=True)
        cfg_path.write_text("misra:\n  active_profile: testing\n")
        cfg = MagicMock()
        cfg.misra.profiles = {"safety": MagicMock(name="Safety")}
        with patch("yuleosh.ci.config.load_ci_config", return_value=cfg):
            with patch("builtins.print"):
                main_module.cmd_misra_profile_set("safety")
        raw = __import__("yaml").safe_load(cfg_path.read_text())
        assert raw["misra"]["active_profile"] == "safety"


class TestMisraReport:
    def _write_report(self, osh_home, data):
        rdir = osh_home / ".yuleosh" / "reports"
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "misra-report.json").write_text(json.dumps(data))

    def test_no_report(self, main_module, osh_home):
        with pytest.raises(SystemExit):
            main_module.cmd_misra_report(SimpleNamespace(format="summary"))

    def test_bad_json(self, main_module, osh_home):
        rdir = osh_home / ".yuleosh" / "reports"
        rdir.mkdir(parents=True)
        (rdir / "misra-report.json").write_text("{bad")
        with pytest.raises(SystemExit):
            main_module.cmd_misra_report(SimpleNamespace(format="summary"))

    def test_format_html(self, main_module, osh_home):
        self._write_report(osh_home, {"summary": {"total_violations": 3,
                                                  "total_rules_violated": 2,
                                                  "unique_files": ["a.c"],
                                                  "severity_counts": {"error": 1, "warning": 2},
                                                  "per_file_counts": {"a.c": 3}},
                                      "groups": {"R-1": {"title": "T", "count": 3,
                                                          "severity_category": "required",
                                                          "violations": [{"file": "a.c", "line": 1,
                                                                          "col": 2, "message": "m" * 90}]}}})
        with patch("builtins.print"):
            main_module.cmd_misra_report(SimpleNamespace(format="html"))
        assert (osh_home / ".yuleosh" / "reports" / "misra-report.html").exists()

    def test_format_json(self, main_module, osh_home):
        self._write_report(osh_home, {"summary": {"total_violations": 3}})
        with patch("builtins.print") as mp:
            main_module.cmd_misra_report(SimpleNamespace(format="json"))
            assert any("total_violations" in str(c) for c in mp.call_args_list)

    def test_format_markdown_missing(self, main_module, osh_home):
        self._write_report(osh_home, {"summary": {}})
        with pytest.raises(SystemExit):
            main_module.cmd_misra_report(SimpleNamespace(format="markdown"))

    def test_format_markdown_ok(self, main_module, osh_home):
        self._write_report(osh_home, {"summary": {}})
        (osh_home / ".yuleosh" / "reports" / "misra-report.md").write_text("# MD")
        with patch("builtins.print"):
            main_module.cmd_misra_report(SimpleNamespace(format="markdown"))

    def test_format_summary(self, main_module, osh_home):
        self._write_report(osh_home, {"summary": {
            "total_violations": 4, "total_rules_violated": 3,
            "unique_files": ["a.c", "b.c"],
            "severity_counts": {"error": 1, "warning": 2, "performance": 1},
            "per_file_counts": {"a.c": 3, "b.c": 1}},
            "groups": {"R-1": {"title": "T", "count": 3, "severity_category": "required"}},
            "tool": "cppcheck", "generated_at": "2026-01-01T00:00:00"})
        with patch("builtins.print") as mp:
            main_module.cmd_misra_report(SimpleNamespace(format="summary"))
            out = " ".join(str(c) for c in mp.call_args_list)
            assert "Total violations" in out


# ═══════════════════════════════════════════════════════════════════════
# KPI CI alert (MP-16)
# ═══════════════════════════════════════════════════════════════════════


class TestKpiCiAlert:
    def test_no_warnings(self, main_module, osh_home):
        with patch("yuleosh.ci.kpi._load_latest_misra_entry", return_value=None):
            with patch("yuleosh.ci.kpi._load_latest_coverage_entry", return_value=None):
                with patch("builtins.print") as mp:
                    main_module.cmd_kpi_ci_alert(SimpleNamespace(json=False))
                    assert any("无告警" in str(c) for c in mp.call_args_list)

    def test_warnings_text(self, main_module, osh_home):
        with patch("yuleosh.ci.kpi._load_latest_misra_entry",
                   return_value={"total_violations": 100}):
            with patch("yuleosh.ci.kpi._load_latest_coverage_entry",
                       return_value={"line_rate": "30%"}):
                with patch("yuleosh.ci.kpi.DEFAULT_THRESHOLDS",
                           {"misra_total_violations": 50, "c_line_coverage_pct": 80.0}):
                    with patch("builtins.print") as mp:
                        main_module.cmd_kpi_ci_alert(SimpleNamespace(json=False))
                        out = " ".join(str(c) for c in mp.call_args_list)
                        assert "CRITICAL" in out

    def test_warnings_json(self, main_module, osh_home):
        with patch("yuleosh.ci.kpi._load_latest_misra_entry",
                   return_value={"total_violations": 60}):
            with patch("yuleosh.ci.kpi._load_latest_coverage_entry",
                       return_value={"line_rate": 70.0}):
                with patch("yuleosh.ci.kpi.DEFAULT_THRESHOLDS",
                           {"misra_total_violations": 50, "c_line_coverage_pct": 80.0}):
                    with patch("builtins.print") as mp:
                        main_module.cmd_kpi_ci_alert(SimpleNamespace(json=True))
                        out = " ".join(str(c) for c in mp.call_args_list)
                        assert '"total_warnings"' in out


# ═══════════════════════════════════════════════════════════════════════
# SWE.6 commands
# ═══════════════════════════════════════════════════════════════════════


class TestSwe6:
    def test_status_text(self, main_module, osh_home):
        with patch("builtins.print") as mp:
            main_module.cmd_swe6_status(SimpleNamespace(json=False))
            out = " ".join(str(c) for c in mp.call_args_list)
            assert "SWE.6" in out

    def test_status_json(self, main_module, osh_home):
        with patch("builtins.print") as mp:
            main_module.cmd_swe6_status(SimpleNamespace(json=True))
            out = " ".join(str(c) for c in mp.call_args_list)
            assert '"规范定义' in out

    def test_check_missing_spec(self, main_module, osh_home):
        with pytest.raises(SystemExit):
            main_module.cmd_swe6_check(SimpleNamespace(report=False))

    def test_check_ok(self, main_module, osh_home):
        (osh_home / "docs").mkdir()
        (osh_home / "docs" / "swe6-confirmation-spec.md").write_text("# SWE6")
        with patch("builtins.print"):
            main_module.cmd_swe6_check(SimpleNamespace(report=False))

    def test_check_with_report(self, main_module, osh_home):
        (osh_home / "docs").mkdir()
        (osh_home / "docs" / "swe6-confirmation-spec.md").write_text("# SWE6")
        lrt = {"lrm": {"summary": {"total": 3, "coverage_pct": 66.7}}}
        # Real product path: main.py's __import__("yuleosh.alm.traceability",
        # fromlist=["generate_lrt"]) must work natively (regression: the old
        # ``from_list`` typo made report generation always fail).
        with patch("yuleosh.alm.traceability.generate_lrt", return_value=lrt):
            with patch("builtins.print"):
                main_module.cmd_swe6_check(SimpleNamespace(report=True))
        assert (osh_home / ".yuleosh" / "reports" / "swe6-report.json").exists()

    def test_check_report_exception(self, main_module, osh_home):
        (osh_home / "docs").mkdir()
        (osh_home / "docs" / "swe6-confirmation-spec.md").write_text("# SWE6")
        with patch("yuleosh.alm.traceability.generate_lrt",
                   side_effect=RuntimeError("boom")):
            with patch("builtins.print") as mp:
                main_module.cmd_swe6_check(SimpleNamespace(report=True))
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "boom" in out


# ═══════════════════════════════════════════════════════════════════════
# Review diff
# ═══════════════════════════════════════════════════════════════════════


class TestReviewDiff:
    REVIEW_A = {"review_type": "auto", "status": "completed", "generated_at": "2026-01-01T00:00:00",
                "findings": [{"file": "a.c", "line": 10, "message": "M1"}]}
    REVIEW_B = {"review_type": "auto", "status": "completed", "generated_at": "2026-01-02T00:00:00",
                "findings": [{"file": "a.c", "line": 10, "message": "M1"},
                             {"file": "b.c", "line": 3, "message": "M2"}]}

    def test_diff_from_files(self, main_module, tmp_path):
        fa = tmp_path / "a.json"
        fb = tmp_path / "b.json"
        fa.write_text(json.dumps(self.REVIEW_A))
        fb.write_text(json.dumps(self.REVIEW_B))
        with patch("builtins.print"):
            main_module.cmd_review_diff(
                SimpleNamespace(review_a=str(fa), review_b=str(fb), json=False))

    def test_diff_json(self, main_module, tmp_path):
        fa = tmp_path / "a.json"
        fa.write_text(json.dumps(self.REVIEW_A))
        with patch("builtins.print") as mp:
            main_module.cmd_review_diff(
                SimpleNamespace(review_a=str(fa), review_b=None, json=True))
            out = " ".join(str(c) for c in mp.call_args_list)
            assert "findings_added" in out

    def test_diff_from_session(self, main_module, osh_home):
        sd = osh_home / ".yuleosh" / "sessions" / "sess-1"
        sd.mkdir(parents=True)
        (sd / "result.json").write_text(json.dumps(self.REVIEW_A))
        with patch("builtins.print"):
            main_module.cmd_review_diff(
                SimpleNamespace(review_a="sess-1", review_b=None, json=False))

    def test_diff_from_latest_dir(self, main_module, osh_home):
        ld = osh_home / ".osh" / "reviews" / "latest"
        ld.mkdir(parents=True)
        (ld / "review.json").write_text(json.dumps(self.REVIEW_A))
        with patch("builtins.print"):
            main_module.cmd_review_diff(
                SimpleNamespace(review_a="review", review_b=None, json=False))

    def test_not_found(self, main_module, osh_home):
        with pytest.raises(SystemExit):
            main_module.cmd_review_diff(
                SimpleNamespace(review_a="nope", review_b=None, json=False))


# ═══════════════════════════════════════════════════════════════════════
# main() dispatch — previously untested branches
# ═══════════════════════════════════════════════════════════════════════


class TestMainDispatchTails:
    def test_init_with_template(self, main_module):
        with patch("yuleosh.templates.ecus.init_project") as mc:
            with patch.object(sys, "argv",
                              ["yuleosh", "init", "--template", "bcm",
                               "--name", "p1", "/tmp/d", "--output", "/tmp/o"]):
                main_module.main()
                mc.assert_called_once()
                args, kwargs = mc.call_args
                assert args[0] == "bcm"

    def test_init_with_template_defaults(self, main_module):
        with patch("yuleosh.templates.ecus.init_project") as mc:
            with patch.object(sys, "argv", ["yuleosh", "init", "--template", "bcm"]):
                with patch("os.path.basename", return_value="x"):
                    main_module.main()
                    mc.assert_called_once()

    def test_init_autosar_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_init_autosar") as mc:
            with patch.object(sys, "argv",
                              ["yuleosh", "init-autosar", "asr", "--dir", "/tmp"]):
                main_module.main()
                mc.assert_called_once()

    def test_project_init(self, main_module):
        with patch("yuleosh.cli.main.cmd_template_init") as mc:
            with patch.object(sys, "argv",
                              ["yuleosh", "project", "init", "--template", "generic", "pd"]):
                main_module.main()
                mc.assert_called_once()

    def test_project_init_default_dir(self, main_module):
        with patch("yuleosh.cli.main.cmd_template_init") as mc:
            with patch.object(sys, "argv", ["yuleosh", "project", "init"]):
                main_module.main()
                mc.assert_called_once()

    def test_template_list_ecus_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_ecu_template_list") as mc:
            with patch.object(sys, "argv", ["yuleosh", "template", "list-ecus"]):
                main_module.main()
                mc.assert_called_once()

    def test_template_init_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_template_init") as mc:
            with patch.object(sys, "argv",
                              ["yuleosh", "template", "init", "p", "--from", "g"]):
                main_module.main()
                mc.assert_called_once()

    def test_spec_merge_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_spec_merge") as mc:
            with patch.object(sys, "argv",
                              ["yuleosh", "spec", "merge", "d.md", "--dry-run"]):
                main_module.main()
                mc.assert_called_once()

    def test_review_diff_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_review_diff") as mc:
            with patch.object(sys, "argv", ["yuleosh", "review", "diff", "a", "b"]):
                main_module.main()
                mc.assert_called_once()

    def test_coverage_trend_dispatch(self, main_module):
        with patch("yuleosh.cli.main._cmd_coverage_trend") as mc:
            with patch.object(sys, "argv", ["yuleosh", "coverage", "trend"]):
                main_module.main()
                mc.assert_called_once()

    def test_demo_wow(self, main_module):
        with patch("yuleosh.api.demo_wow.main") as mc:
            with patch.object(sys, "argv", ["yuleosh", "demo", "wow"]):
                main_module.main()
                mc.assert_called_once()

    def test_demo_quick(self, main_module):
        with patch("yuleosh.api.demo_quick.main") as mc:
            with patch.object(sys, "argv", ["yuleosh", "demo", "quick", "req"]):
                main_module.main()
                mc.assert_called_once()

    def test_demo_uart_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_demo_uart", side_effect=SystemExit(0)):
            with patch.object(sys, "argv", ["yuleosh", "demo", "uart"]):
                with pytest.raises(SystemExit):
                    main_module.main()

    def test_ev_check(self, main_module, tmp_path):
        with patch("yuleosh.evidence.aspice_check.aspice_gap_check",
                   return_value="# Report") as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "ev", "check", "--project-dir",
                                   str(tmp_path), "--save"]):
                    main_module.main()
                    mc.assert_called_once()
        assert (tmp_path / ".osh" / "evidence" / "aspice-gap-report.md").exists()

    def test_ev_check_no_save(self, main_module, tmp_path):
        with patch("yuleosh.evidence.aspice_check.aspice_gap_check", return_value="# R"):
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "ev", "check", "--project-dir", str(tmp_path)]):
                    main_module.main()
        assert not (tmp_path / ".osh" / "evidence").exists()

    def test_evidence_pack_dispatch(self, main_module):
        with patch("yuleosh.evidence.evidence_check.pack_evidence_bundle",
                   return_value={"manifest": {}}):
            with patch("builtins.print"):
                with patch.object(sys, "argv", ["yuleosh", "evidence", "pack"]):
                    main_module.main()

    def test_evidence_check_valid(self, main_module):
        result = {"valid": True, "checks": [{"status": "PASS", "check": "c", "detail": "d"}],
                  "warnings": ["w"], "errors": []}
        with patch("yuleosh.evidence.evidence_check.check_evidence_integrity",
                   return_value=result):
            with patch("builtins.print"):
                with patch.object(sys, "argv", ["yuleosh", "evidence", "check", "/tmp/b"]):
                    main_module.main()

    def test_evidence_check_json(self, main_module):
        result = {"valid": True, "checks": [], "warnings": [], "errors": []}
        with patch("yuleosh.evidence.evidence_check.check_evidence_integrity",
                   return_value=result):
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "evidence", "check", "/tmp/b", "--json"]):
                    main_module.main()

    def test_evidence_check_invalid(self, main_module):
        result = {"valid": False, "checks": [], "warnings": [],
                  "errors": ["missing manifest"]}
        with patch("yuleosh.evidence.evidence_check.check_evidence_integrity",
                   return_value=result):
            with patch("builtins.print"):
                with patch.object(sys, "argv", ["yuleosh", "evidence", "check", "/tmp/b"]):
                    with pytest.raises(SystemExit):
                        main_module.main()

    def test_evidence_legacy(self, main_module):
        with patch("yuleosh.cli.main.cmd_evidence_pack") as mc:
            with patch.object(sys, "argv", ["yuleosh", "evidence"]):
                main_module.main()
            mc.assert_called_once()

    def test_audit_evidence_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_audit_evidence") as mc:
            with patch.object(sys, "argv", ["yuleosh", "audit", "evidence"]):
                main_module.main()
                mc.assert_called_once()

    def test_audit_sync_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_audit_sync_check") as mc:
            with patch.object(sys, "argv", ["yuleosh", "audit", "sync-check"]):
                main_module.main()
                mc.assert_called_once()

    def test_traceability_dispatch(self, main_module):
        for sub in ("report", "matrix", "export"):
            with patch("yuleosh.cli.main.cmd_traceability_" + sub) as mc:
                with patch.object(sys, "argv", ["yuleosh", "traceability", sub]):
                    main_module.main()
                    mc.assert_called_once()

    def test_config_profile_audit(self, main_module):
        with patch("yuleosh.ci.profile.get_profile_audit_log", return_value="LOG") as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "config", "profile", "audit", "--limit", "10", "--json"]):
                    main_module.main()
                    mc.assert_called_once()

    def test_hook_dispatch(self, main_module):
        with patch("yuleosh.hooks.cli.handle_hook_command", return_value=0) as mc:
            with patch.object(sys, "argv", ["yuleosh", "hook", "install"]):
                with pytest.raises(SystemExit):
                    main_module.main()
                mc.assert_called_once()

    def test_plan_dispatch(self, main_module):
        with patch("yuleosh.plan.cli.handle_plan_command", return_value=0) as mc:
            with patch.object(sys, "argv", ["yuleosh", "plan", "--list"]):
                with pytest.raises(SystemExit):
                    main_module.main()
                mc.assert_called_once()

    def test_kb_dispatch(self, main_module):
        with patch("yuleosh.kb.cli.handle_kb_command", return_value=0) as mc:
            with patch.object(sys, "argv", ["yuleosh", "kb", "search", "q"]):
                with pytest.raises(SystemExit):
                    main_module.main()
                mc.assert_called_once()

    def test_kpi_process_status(self, main_module):
        with patch("yuleosh.ci.kpi.get_process_stability_summary",
                   return_value="STABLE") as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv", ["yuleosh", "kpi", "process", "status"]):
                    main_module.main()
                    mc.assert_called_once()

    def test_kpi_process_baseline(self, main_module):
        with patch("yuleosh.ci.kpi.generate_process_baseline_report",
                   return_value="/tmp/report.md") as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "kpi", "process", "baseline", "--label", "L1"]):
                    main_module.main()
                    mc.assert_called_once()

    def test_kpi_ci_alert_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_kpi_ci_alert") as mc:
            with patch.object(sys, "argv", ["yuleosh", "kpi", "ci-alert"]):
                main_module.main()
                mc.assert_called_once()

    def test_kpi_defect_escape_record(self, main_module):
        result = {"escape_rate": 10.0, "escaped_defects": 1, "total_defects": 10,
                  "stage": "customer"}
        with patch("yuleosh.ci.kpi.record_defect_escape", return_value=result) as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv",
                                  ["yuleosh", "kpi", "defect-escape", "record",
                                   "--total", "10", "--escaped", "1"]):
                    main_module.main()
                    mc.assert_called_once()

    def test_kpi_defect_escape_status(self, main_module):
        with patch("yuleosh.ci.kpi.get_defect_escape_summary", return_value="SUM") as mc:
            with patch("builtins.print"):
                with patch.object(sys, "argv", ["yuleosh", "kpi", "defect-escape", "status"]):
                    main_module.main()
                    mc.assert_called_once()

    def test_autosar_gen_stub_dispatch(self, main_module):
        with patch("yuleosh.autosar.stubgen._handle_gen_stub_command") as mc:
            with patch.object(sys, "argv", ["yuleosh", "autosar", "gen-stub", "t"]):
                main_module.main()
                mc.assert_called_once()

    def test_swe6_check_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_swe6_check") as mc:
            with patch.object(sys, "argv", ["yuleosh", "swe6", "check"]):
                main_module.main()
                mc.assert_called_once()

    def test_skills_dispatch(self, main_module):
        with patch("yuleosh.skills.cli.handle_skills_command", return_value=0) as mc:
            with patch.object(sys, "argv", ["yuleosh", "skills", "list"]):
                with pytest.raises(SystemExit):
                    main_module.main()
                mc.assert_called_once()

    def test_misra_profile_set_dispatch(self, main_module):
        with patch("yuleosh.cli.main.cmd_misra_profile_set") as mc:
            with patch.object(sys, "argv", ["yuleosh", "misra", "profile", "set", "safety"]):
                main_module.main()
                mc.assert_called_once()

    def test_onboard_dispatch(self, main_module):
        with patch("yuleosh.cli.onboard.handle_onboard_command") as mc:
            with patch.object(sys, "argv", ["yuleosh", "onboard"]):
                main_module.main()
                mc.assert_called_once()

    def test_loop_dispatch(self, main_module):
        with patch("yuleosh.loop_engine.cli.handle_loop_command", return_value=0) as mc:
            with patch.object(sys, "argv", ["yuleosh", "loop", "status"]):
                with pytest.raises(SystemExit):
                    main_module.main()
                mc.assert_called_once()

    def test_ui_dispatch(self, main_module):
        with patch("yuleosh.ui.server.main") as mc:
            with patch.object(sys, "argv", ["yuleosh", "ui"]):
                main_module.main()
                mc.assert_called_once()
