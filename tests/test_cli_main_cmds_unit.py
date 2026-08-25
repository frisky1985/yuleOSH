"""
Unit tests for yuleosh.cli.main — Wave 2b (core command groups).

Covers: template list/ecu-list/template-init, init, init-autosar, spec merge,
pipeline, review, ci run, demo uart, evidence pack, coverage (c/gate/trend),
audit evidence (full bundle), audit sync-check, ev dispatch, stats.

Patches target the lazy-import binding sites used in main.py. Module-level
OSH_HOME is patched via monkeypatch.setattr(main_module, "OSH_HOME", ...)
where a function reads the module-level constant.
"""

# @tests src/yuleosh/cli/main.py

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, mock_open

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


@pytest.fixture
def main_module():
    import yuleosh.cli.main as m
    return m


@pytest.fixture
def mock_subprocess():
    with patch("yuleosh.cli.main.subprocess.run") as mock_spr:
        mock_spr.return_value.returncode = 0
        mock_spr.return_value.stdout = ""
        mock_spr.return_value.stderr = ""
        yield mock_spr


@pytest.fixture
def no_tool_deps():
    """Disable cppcheck detection to keep tests hermetic."""
    with patch("yuleosh.cli.main.shutil.which", return_value=None):
        yield


# ═══════════════════════════════════════════════════════════════════════
# Template commands
# ═══════════════════════════════════════════════════════════════════════


class TestEcuTemplateList:
    def test_ecu_list_with_data(self, main_module):
        with patch("yuleosh.templates.ecus.list_ecu_templates", return_value=[
            {"name": "bcm", "mcu": "S32K312", "asil": "ASIL_B",
             "description": "Body Control Module " + "x" * 60},
        ]):
            with patch("builtins.print") as mp:
                main_module.cmd_ecu_template_list()
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "bcm" in out

    def test_ecu_list_empty(self, main_module):
        with patch("yuleosh.templates.ecus.list_ecu_templates", return_value=[]):
            with patch("builtins.print") as mp:
                main_module.cmd_ecu_template_list()
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "No ECU templates" in out


class TestTemplateInitFull:
    def _make_template_dir(self, tmp_path):
        tdir = tmp_path / "tpl"
        (tdir / "specs").mkdir(parents=True)
        (tdir / "specs" / "spec.md").write_text("# Spec {name}")
        (tdir / "pipeline").mkdir()
        (tdir / "pipeline" / "config.yaml").write_text("stages: []")
        (tdir / "src").mkdir()
        (tdir / "src" / "main.c").write_text("int main(){}")
        (tdir / ".gitignore").write_text("*.o")
        (tdir / "template.yaml").write_text("name: tpl")
        return tdir

    def test_template_init_all_dirs(self, main_module, tmp_path, mock_subprocess):
        tdir = self._make_template_dir(tmp_path)
        with patch("yuleosh.templates.resolve_template",
                   return_value={"name": "tpl", "version": "2.0.0"}):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                with patch("yuleosh.cli.main.shutil.which", return_value="/usr/bin/cppcheck"):
                    main_module.cmd_template_init("proj", parent_dir=str(tmp_path), template_name="tpl")
        proj = tmp_path / "proj"
        assert (proj / "docs" / "spec.md").exists()
        assert (proj / "pipeline" / "config.yaml").exists()
        assert (proj / "src" / "main.c").exists()
        assert (proj / ".gitignore").exists()
        assert (proj / "tests" / ".gitkeep").exists()
        cfg = json.loads((proj / "yuleosh.yaml").read_text())
        assert cfg["template"] == "tpl"
        assert cfg["template_version"] == "2.0.0"

    def test_template_init_dir_exists(self, main_module, tmp_path):
        (tmp_path / "proj").mkdir()
        tdir = self._make_template_dir(tmp_path)
        with patch("yuleosh.templates.resolve_template", return_value={"name": "tpl"}):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                with pytest.raises(SystemExit):
                    main_module.cmd_template_init("proj", parent_dir=str(tmp_path), template_name="tpl")

    def test_template_init_tpl_dir_missing(self, main_module, tmp_path):
        with patch("yuleosh.templates.resolve_template", return_value={"name": "tpl"}):
            with patch("yuleosh.templates.get_template_dir", return_value=None):
                with pytest.raises(SystemExit):
                    main_module.cmd_template_init("proj", parent_dir=str(tmp_path), template_name="tpl")

    def test_interactive_no_templates(self, main_module, tmp_path):
        with patch("yuleosh.templates.list_templates", return_value=[]):
            with pytest.raises(SystemExit):
                main_module._interactive_template_init("p", str(tmp_path))

    def test_interactive_invalid_choice(self, main_module, tmp_path):
        with patch("yuleosh.templates.list_templates", return_value=[
            {"name": "g", "description": "Generic"}]):
            with patch("builtins.input", return_value="9"):
                with pytest.raises(SystemExit):
                    main_module._interactive_template_init("p", str(tmp_path))

    def test_interactive_eof(self, main_module, tmp_path):
        with patch("yuleosh.templates.list_templates", return_value=[
            {"name": "g", "description": "Generic"}]):
            with patch("builtins.input", side_effect=EOFError):
                with pytest.raises(SystemExit):
                    main_module._interactive_template_init("p", str(tmp_path))

    def test_interactive_ok(self, main_module, tmp_path):
        with patch("yuleosh.templates.list_templates", return_value=[
            {"name": "g", "description": "Generic"}]):
            with patch("builtins.input", return_value="1"):
                with patch("yuleosh.cli.commands.misc.cmd_template_init") as mc:
                    main_module._interactive_template_init("p", str(tmp_path))
                    mc.assert_called_once_with("p", str(tmp_path), "g")


class TestEnsureToolDeps:
    def test_cppcheck_present(self, main_module, mock_subprocess):
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "Cppcheck 2.12"
        with patch("yuleosh.cli.main.shutil.which", return_value="/usr/bin/cppcheck"):
            with patch("builtins.print"):
                main_module._ensure_tool_deps()

    def test_cppcheck_missing_no_pkg_mgr(self, main_module):
        with patch("yuleosh.cli.main.shutil.which", return_value=None):
            with patch("builtins.print") as mp:
                main_module._ensure_tool_deps()
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "cppcheck not found" in out

    def test_cppcheck_timeout(self, main_module):
        import subprocess
        with patch("yuleosh.cli.main.shutil.which", return_value="/usr/bin/cppcheck"):
            with patch("yuleosh.cli.main.subprocess.run",
                       side_effect=subprocess.TimeoutExpired("cppcheck", 5)):
                with patch("builtins.print"):
                    main_module._ensure_tool_deps()


# ═══════════════════════════════════════════════════════════════════════
# cmd_init_autosar
# ═══════════════════════════════════════════════════════════════════════


class TestInitAutosar:
    def _make_tpl(self, tmp_path):
        tdir = tmp_path / "tpl"
        (tdir / "specs").mkdir(parents=True)
        (tdir / "specs" / "spec.md").write_text("# {name}")
        (tdir / "pipeline").mkdir()
        (tdir / "pipeline" / "config.yaml").write_text("{}")
        (tdir / "src").mkdir()
        (tdir / "src" / "main.c").write_text("int main(){}")
        (tdir / ".gitignore").write_text("*.o")
        return tdir

    def test_resolve_fail(self, main_module, tmp_path):
        with patch("yuleosh.templates.resolve_template", return_value=None):
            with pytest.raises(SystemExit):
                main_module.cmd_init_autosar("asr", parent_dir=str(tmp_path))

    def test_tpl_dir_missing(self, main_module, tmp_path):
        with patch("yuleosh.templates.resolve_template", return_value={"name": "yuleasr"}):
            with patch("yuleosh.templates.get_template_dir", return_value=None):
                with pytest.raises(SystemExit):
                    main_module.cmd_init_autosar("asr", parent_dir=str(tmp_path))

    def test_project_exists(self, main_module, tmp_path):
        (tmp_path / "asr").mkdir()
        tdir = self._make_tpl(tmp_path)
        with patch("yuleosh.templates.resolve_template", return_value={"name": "yuleasr"}):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                with pytest.raises(SystemExit):
                    main_module.cmd_init_autosar("asr", parent_dir=str(tmp_path))

    def test_success_no_yuleasr(self, main_module, tmp_path, monkeypatch):
        monkeypatch.delenv("YULEASR_HOME", raising=False)
        tdir = self._make_tpl(tmp_path)
        tpl = {"name": "yuleasr", "version": "1.0",
               "yuleasr": {"modules_mcal": ["Mcu", "Dio"],
                           "modules_ecual": ["CanIf"], "modules_services": ["Com"]}}
        with patch("yuleosh.templates.resolve_template", return_value=tpl):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                main_module.cmd_init_autosar("asr", parent_dir=str(tmp_path))
        proj = tmp_path / "asr"
        assert (proj / "docs" / "spec.md").exists()
        assert (proj / "config" / "Mcu_Cfg.h").exists()
        assert (proj / "linker").exists()
        assert (proj / "arxml").exists()
        assert (proj / "tests" / ".gitkeep").exists()
        meta = json.loads((proj / "yuleosh.yaml").read_text())
        assert meta["bsw_modules"]["mcal"] == ["Mcu", "Dio"]
        assert meta["yuleasr_home"] == ""

    def test_success_with_yuleasr_home(self, main_module, tmp_path, monkeypatch):
        asr_dir = tmp_path / "yuleasr-checkout"
        asr_dir.mkdir()
        tdir = self._make_tpl(tmp_path)
        tpl = {"name": "yuleasr", "version": "1.0", "yuleasr": {}}
        with patch("yuleosh.templates.resolve_template", return_value=tpl):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                main_module.cmd_init_autosar("asr2", parent_dir=str(tmp_path),
                                             yuleasr_home=str(asr_dir))
        meta = json.loads((tmp_path / "asr2" / "yuleosh.yaml").read_text())
        assert meta["yuleasr_home"] == str(asr_dir)

    def test_yuleasr_home_env_not_found(self, main_module, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEASR_HOME", "/nonexistent/asr")
        tdir = self._make_tpl(tmp_path)
        tpl = {"name": "yuleasr", "version": "1.0", "yuleasr": {}}
        with patch("yuleosh.templates.resolve_template", return_value=tpl):
            with patch("yuleosh.templates.get_template_dir", return_value=tdir):
                with patch("builtins.print") as mp:
                    main_module.cmd_init_autosar("asr3", parent_dir=str(tmp_path))
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "not found" in out


# ═══════════════════════════════════════════════════════════════════════
# Spec / pipeline / review / ci / demo
# ═══════════════════════════════════════════════════════════════════════


class TestSpecMerge:
    def test_merge_success(self, main_module):
        with patch("yuleosh.spec.merge.cmd_spec_merge", return_value=True) as mc:
            main_module.cmd_spec_merge("delta.md", project_dir="/tmp", dry_run=True)
            mc.assert_called_once_with("delta.md", project_dir="/tmp", dry_run=True)

    def test_merge_failure(self, main_module):
        with patch("yuleosh.spec.merge.cmd_spec_merge", return_value=False):
            with pytest.raises(SystemExit):
                main_module.cmd_spec_merge("delta.md")


class TestDemoUart:
    def test_uart_dispatches(self, main_module):
        with patch("yuleosh.cli.commands.demo_uart.cmd_demo_uart", return_value=0) as mc:
            with pytest.raises(SystemExit) as e:
                main_module.cmd_demo_uart(target_dir="/tmp/d", do_build=True, skip_cmake=True)
            assert e.value.code == 0
            mc.assert_called_once_with("/tmp/d", True, True)


class TestCoverageCommands:
    def test_gate_tests_fail(self, main_module):
        with patch("yuleosh.cli.main.subprocess.run") as mr:
            first = MagicMock()
            first.returncode = 1
            first.stdout = "FAILED"
            first.stderr = "err"
            mr.return_value = first
            with pytest.raises(SystemExit):
                main_module._cmd_coverage_gate(SimpleNamespace(fail_under=50))

    def test_gate_report_fail(self, main_module):
        results = [
            MagicMock(returncode=0, stdout="100 passed", stderr=""),
            MagicMock(returncode=1, stdout="Coverage: 40%", stderr=""),
        ]
        with patch("yuleosh.cli.main.subprocess.run", side_effect=results):
            with pytest.raises(SystemExit):
                main_module._cmd_coverage_gate(SimpleNamespace(fail_under=60))

    def test_gate_pass_full(self, main_module):
        results = [
            MagicMock(returncode=0, stdout="100 passed", stderr=""),
            MagicMock(returncode=0, stdout="Coverage: 90%", stderr=""),
        ]
        with patch("yuleosh.cli.main.subprocess.run", side_effect=results):
            with patch("builtins.print"):
                main_module._cmd_coverage_gate(SimpleNamespace(fail_under=60))

    def test_trend(self, main_module):
        with patch("yuleosh.ci.coverage_trend.show_coverage_trend",
                   return_value="TREND DATA") as mc:
            with patch("builtins.print") as mp:
                main_module._cmd_coverage_trend(SimpleNamespace(days=30, lines=50, json=False))
                mc.assert_called_once()
                assert any("TREND DATA" in str(c) for c in mp.call_args_list)

    def test_coverage_c_bad_json(self, main_module):
        with patch("yuleosh.ci.gcov_coverage.generate_c_coverage_report",
                   return_value="/tmp/cov.json"):
            with patch("builtins.open", mock_open(read_data="not json")):
                with patch("yuleosh.cli.main.json.load",
                           side_effect=json.JSONDecodeError("x", "doc", 0)):
                    with patch("builtins.print"):
                        main_module._cmd_coverage_c()


class TestAuditSyncCheck:
    def test_save_false(self, main_module, mock_subprocess):
        r = {"status": "passed", "rule_results": []}
        with patch("yuleosh.ci.sync_check.run_sync_check", return_value=r):
            with patch("yuleosh.ci.sync_check.save_sync_evidence") as save_mc:
                with patch("yuleosh.ci.sync_check.print_sync_result"):
                    main_module.cmd_audit_sync_check(project_dir="/tmp", save=False)
                    save_mc.assert_not_called()

    def test_save_true(self, main_module, mock_subprocess):
        r = {"status": "passed", "rule_results": []}
        with patch("yuleosh.ci.sync_check.run_sync_check", return_value=r):
            with patch("yuleosh.ci.sync_check.save_sync_evidence", return_value="/tmp/e.json") as save_mc:
                with patch("yuleosh.ci.sync_check.print_sync_result"):
                    main_module.cmd_audit_sync_check(project_dir="/tmp", save=True)
                    save_mc.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════
# cmd_audit_evidence — full bundle collection
# ═══════════════════════════════════════════════════════════════════════


class TestAuditEvidenceFull:
    def _seed_project(self, tmp_path):
        """Create a project with every artifact type present."""
        proj = Path(tmp_path)
        ci = proj / ".osh" / "ci"
        ci.mkdir(parents=True)
        (ci / "layer1.json").write_text(json.dumps(
            {"layer": 1, "status": "passed", "stages": ["misra"]}))
        (ci / "layer2.json").write_text("not json")  # decode-error path

        reports = proj / ".yuleosh" / "reports"
        reports.mkdir(parents=True)
        (reports / "c-coverage.json").write_text(json.dumps(
            {"line_rate": 85, "branch_rate": 70, "total_files": 3}))
        (reports / "docsync-evidence.json").write_text(json.dumps(
            {"status": "passed", "rule_results": []}))
        (reports / "misra-report.json").write_text(json.dumps(
            {"summary": {"total_violations": 5, "total_rules_violated": 3}}))
        (reports / "misra-trend.json").write_text("{}")
        (reports / "traceability-report.json").write_text(json.dumps(
            {"coverage_summary": {"requirements_total": 5}}))
        (reports / "lrt-matrix.json").write_text("{}")
        rev_dir = reports / "reviews"
        rev_dir.mkdir()
        (rev_dir / "rev1.json").write_text("{}")
        (proj / ".yuleosh" / "ci-config.yaml").write_text("misra: {}")

        (proj / ".osh" / "pipeline-status.json").write_text(json.dumps({"status": "completed"}))
        ev_dir = proj / ".osh" / "evidence"
        ev_dir.mkdir()
        (ev_dir / "evidence.zip").write_bytes(b"PK\x03\x04fake")
        (ev_dir / "notes.txt").write_text("note")
        return proj

    def test_full_bundle_with_zip(self, main_module, tmp_path):
        proj = self._seed_project(tmp_path)
        with patch.object(main_module, "OSH_HOME", str(proj)):
            with patch("builtins.print"):
                evidence = main_module.cmd_audit_evidence(create_zip=True)
        assert evidence["artifacts"]
        types = {a["type"] for a in evidence["artifacts"]}
        assert "ci-layer-result" in types
        assert "c-coverage" in types
        assert "docsync-gate" in types
        assert "misra-report" in types
        assert "misra-trend" in types
        assert "pipeline-status" in types
        assert "evidence-zip" in types
        assert "ci-config" in types
        assert "traceability-report" in types
        assert "lrt-matrix" in types
        assert "review-report" in types
        assert "evidence-artifact" in types
        assert "audit-evidence-zip" in types
        assert evidence.get("zip_path")
        assert (proj / ".yuleosh" / "audit" / "audit-manifest.json").exists()

    def test_full_bundle_no_zip_custom_out(self, main_module, tmp_path):
        proj = self._seed_project(tmp_path)
        out = tmp_path / "custom-out"
        with patch.object(main_module, "OSH_HOME", str(proj)):
            with patch("builtins.print"):
                evidence = main_module.cmd_audit_evidence(output_dir=str(out), create_zip=False)
        assert "zip_path" not in evidence
        assert (out / "audit-manifest.json").exists()
        assert (out / "layer1.json").exists()

    def test_empty_project(self, main_module, tmp_path):
        with patch.object(main_module, "OSH_HOME", str(tmp_path)):
            with patch("builtins.print"):
                evidence = main_module.cmd_audit_evidence(create_zip=False)
        # 安全可审计（2026-08-07）: 证据包总是包含 audit-log-verification。
        assert [a["type"] for a in evidence["artifacts"]] == ["audit-log-verification"]

    def test_bad_ci_layer_json(self, main_module, tmp_path):
        ci = tmp_path / ".osh" / "ci"
        ci.mkdir(parents=True)
        (ci / "layer1.json").write_text("{bad json")
        with patch.object(main_module, "OSH_HOME", str(tmp_path)):
            with patch("builtins.print") as mp:
                evidence = main_module.cmd_audit_evidence(create_zip=False)
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "Cannot read" in out
        # Bad CI layer skipped, but audit-log-verification still present.
        types = [a["type"] for a in evidence["artifacts"]]
        assert "audit-log-verification" in types


# ═══════════════════════════════════════════════════════════════════════
# KPI / stats / traceability (basic happy paths via dispatch-level funcs)
# ═══════════════════════════════════════════════════════════════════════


class TestKpiBaseline:
    def test_baseline_save_json(self, main_module):
        saved = {"baseline_id": "b1", "label": "t", "saved_at": "2026-01-01T00:00:00",
                 "snapshot": {"misra": {"total_violations": 3},
                              "coverage": {"c_line_rate": 80}}}
        with patch("yuleosh.ci.kpi.kpi_baseline_save", return_value=saved) as mc:
            with patch("builtins.print"):
                main_module.cmd_kpi_baseline_save(SimpleNamespace(json=True, label="t"))
                mc.assert_called_once()

    def test_baseline_save_text(self, main_module):
        saved = {"baseline_id": "b1", "label": "", "saved_at": "2026-01-01T00:00:00",
                 "snapshot": {"misra": {"total_violations": 3},
                              "coverage": {"c_line_rate": 80}}}
        with patch("yuleosh.ci.kpi.kpi_baseline_save", return_value=saved):
            with patch("builtins.print") as mp:
                main_module.cmd_kpi_baseline_save(SimpleNamespace(json=False, label=""))
                out = " ".join(str(c) for c in mp.call_args_list)
                assert "b1" in out


class TestStats:
    def test_stats_text(self, main_module):
        with patch("yuleosh.cli.stats.cmd_stats") as mc:
            main_module.cmd_stats(json_output=False)
            mc.assert_called_once_with(to_json=False)

    def test_stats_json(self, main_module):
        with patch("yuleosh.cli.stats.cmd_stats") as mc:
            main_module.cmd_stats(json_output=True)
            mc.assert_called_once_with(to_json=True)
