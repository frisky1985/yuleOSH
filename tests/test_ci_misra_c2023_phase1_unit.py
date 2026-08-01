"""Unit tests for yuleosh.ci.misra_c2023_phase1 (v3.4.2 Wave 1 C5).

Covers:
  - Rule table constants sanity
  - C2023UpgradeReport defaults
  - upgrade_rules_yaml(): missing file, dry-run, full upgrade (meta version,
    backward compat mapping, removed rules, report fields)
  - run_pilot_scan(): default modules, no sources, subprocess success,
    FileNotFoundError / TimeoutExpired / generic error, report file written
  - main(): missing rules file → SystemExit; dry-run completes
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from yuleosh.ci import misra_c2023_phase1 as M


BASE_RULES_YAML = """\
meta:
  version: "2023-preview"
  backward_compat:
    mapping:
      "Dir-4.6":
        c2023_id: "Dir-1.1"
"""


# ── Constants / dataclass ─────────────────────────────────────────────

class TestConstantsAndReport:
    def test_new_rules_has_directives(self):
        """GIVEN C2023_NEW_RULES THEN contains new/modified directives."""
        assert "Dir-1.1" in M.C2023_NEW_RULES
        assert M.C2023_NEW_RULES["Dir-1.1"]["status"] == "new"

    def test_removed_rules(self):
        """GIVEN C2023_REMOVED_RULES THEN Rule-5.6 present."""
        assert "Rule-5.6" in M.C2023_REMOVED_RULES

    def test_updated_rules(self):
        """GIVEN C2023_UPDATED_RULES THEN Rule-1.3 present."""
        assert M.C2023_UPDATED_RULES["Rule-1.3"]["change"] == "modified"

    def test_report_defaults(self):
        """GIVEN C2023UpgradeReport THEN defaults applied."""
        r = M.C2023UpgradeReport()
        assert r.new_version == "2023-full"
        assert r.status == "completed"
        assert r.new_rules_added == []
        assert r.pilot_modules == []


# ── upgrade_rules_yaml ────────────────────────────────────────────────

class TestUpgradeRulesYaml:
    def test_missing_file(self, tmp_path, caplog):
        """GIVEN missing rules file WHEN upgrade THEN failed status."""
        with mock.patch("yuleosh.ci.misra_c2023_phase1.log") as mlog:
            report = M.upgrade_rules_yaml(str(tmp_path / "nope.yaml"))
        assert report.status == "failed"
        mlog.error.assert_called()

    def test_dry_run_no_write(self, tmp_path):
        """GIVEN dry_run WHEN upgrade THEN file unchanged, dry-run status."""
        path = tmp_path / "rules.yaml"
        path.write_text(BASE_RULES_YAML)
        report = M.upgrade_rules_yaml(str(path), dry_run=True)
        assert report.status == "dry-run"
        assert "2023-preview" in path.read_text()  # not upgraded
        assert report.old_version == "2023-preview"
        assert report.new_rules_added
        assert report.removed_rules
        assert report.updated_rules

    def test_full_upgrade(self, tmp_path):
        """GIVEN rules file WHEN upgrade THEN version bumped + mapping updated."""
        path = tmp_path / "rules.yaml"
        path.write_text(BASE_RULES_YAML)
        report = M.upgrade_rules_yaml(str(path))
        data = __import__("yaml").safe_load(path.read_text())
        assert data["meta"]["version"] == "2023-full"
        assert "upgraded_at" in data["meta"]
        compat = data["meta"]["backward_compat"]["mapping"]
        assert "Dir-4.12" in compat  # added mapping for new rule
        assert compat["Dir-4.6"]["change"] == "removed"  # renumbered rule marked
        assert report.status == "completed"
        assert report.new_rules_added
        assert "Rule-5.6" in report.removed_rules[0]

    def test_upgrade_empty_file(self, tmp_path):
        """GIVEN empty rules file WHEN upgrade THEN meta created."""
        path = tmp_path / "rules.yaml"
        path.write_text("")
        report = M.upgrade_rules_yaml(str(path))
        data = __import__("yaml").safe_load(path.read_text())
        assert data["meta"]["version"] == "2023-full"
        assert report.old_version == "unknown"


# ── run_pilot_scan ────────────────────────────────────────────────────

class TestRunPilotScan:
    def test_default_modules_no_sources(self, tmp_path, caplog):
        """GIVEN empty yuleASR dir WHEN pilot THEN zero files + report."""
        with mock.patch("yuleosh.ci.misra_c2023_phase1.log") as mlog:
            result = M.run_pilot_scan(str(tmp_path))
        assert result["modules"] == ["eth", "icu"]
        assert result["summary"]["files_checked"] == 0
        assert result["summary"]["total_violations"] == 0
        assert (tmp_path / ".yuleosh" / "reports" / "misra-c2023-pilot.json").exists()
        mlog.warning.assert_called()

    def test_scan_with_sources(self, tmp_path):
        """GIVEN sources + mocked cppcheck WHEN pilot THEN violations counted."""
        src = tmp_path / "src" / "bsw" / "mcal" / "eth"
        src.mkdir(parents=True)
        (src / "eth.c").write_text("int main(void){return 0;}\n")
        fake_run = mock.MagicMock()
        fake_run.return_value = mock.MagicMock(returncode=0,
                                               stdout="misra warning R10.3\nmisra error\n",
                                               stderr="")
        with mock.patch("yuleosh.ci.misra_c2023_phase1.subprocess.run", fake_run):
            result = M.run_pilot_scan(str(tmp_path), modules=["eth"])
        mod = result["module_results"]["eth"]
        assert mod["file_count"] == 1
        assert mod["misra_violations"] == 2
        assert result["summary"]["total_violations"] == 2
        fake_run.assert_called_once()

    def test_cppcheck_not_found(self, tmp_path):
        """GIVEN cppcheck missing WHEN pilot THEN error recorded."""
        src = tmp_path / "src" / "bsw" / "mcal" / "eth"
        src.mkdir(parents=True)
        (src / "eth.c").write_text("x")
        with mock.patch("yuleosh.ci.misra_c2023_phase1.subprocess.run",
                        side_effect=FileNotFoundError("cppcheck")):
            result = M.run_pilot_scan(str(tmp_path), modules=["eth"])
        assert result["module_results"]["eth"]["error"] == "cppcheck not found"

    def test_cppcheck_timeout(self, tmp_path):
        """GIVEN cppcheck timeout WHEN pilot THEN timeout error recorded."""
        src = tmp_path / "src" / "bsw" / "mcal" / "eth"
        src.mkdir(parents=True)
        (src / "eth.c").write_text("x")
        with mock.patch("yuleosh.ci.misra_c2023_phase1.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("cppcheck", 60)):
            result = M.run_pilot_scan(str(tmp_path), modules=["eth"])
        assert result["module_results"]["eth"]["error"] == "timeout"

    def test_cppcheck_generic_error(self, tmp_path):
        """GIVEN cppcheck generic failure WHEN pilot THEN error string stored."""
        src = tmp_path / "src" / "bsw" / "mcal" / "eth"
        src.mkdir(parents=True)
        (src / "eth.c").write_text("x")
        with mock.patch("yuleosh.ci.misra_c2023_phase1.subprocess.run",
                        side_effect=RuntimeError("boom")):
            result = M.run_pilot_scan(str(tmp_path), modules=["eth"])
        assert result["module_results"]["eth"]["error"] == "boom"

    def test_output_dir_custom(self, tmp_path):
        """GIVEN custom output_dir WHEN pilot THEN report written there."""
        out = tmp_path / "custom"
        result = M.run_pilot_scan(str(tmp_path), output_dir=str(out))
        assert (out / "misra-c2023-pilot.json").exists()
        assert result["summary"]["files_checked"] == 0


# ── main CLI ──────────────────────────────────────────────────────────

class TestMain:
    def test_missing_rules_exits(self, tmp_path, monkeypatch, capsys):
        """GIVEN no rules file WHEN main THEN SystemExit(1)."""
        monkeypatch.setattr(sys, "argv", ["misra_c2023_phase1"])
        monkeypatch.setenv("OSH_HOME", str(tmp_path / "empty"))
        with pytest.raises(SystemExit) as exc:
            M.main()
        assert exc.value.code == 1

    def test_dry_run_flow(self, tmp_path, monkeypatch, capsys):
        """GIVEN rules file + --dry-run WHEN main THEN completes."""
        rules = tmp_path / "misra-rules.yaml"
        rules.write_text(BASE_RULES_YAML)
        monkeypatch.setattr(sys, "argv", ["misra_c2023_phase1", "--dry-run",
                                          "--rules", str(rules)])
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        M.main()
        out = capsys.readouterr().out
        assert "MISRA C:2023 Phase 1 Upgrade" in out
        assert "Dry-run complete" in out
