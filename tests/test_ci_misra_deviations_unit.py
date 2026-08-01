"""Unit tests for yuleosh.ci.misra_deviations (v3.4.2 Wave 1 C5).

Covers:
  - Deviation dataclass: to_dict/from_dict (canonical + legacy keys)
  - AUTOSAR baseline deviations sanity
  - load_deviations_from_report(): missing file, legacy/current keys
  - compute_known_rate(): no report, with raw violations, target met
  - register_batch_deviations(): missing config, dedupe, batch write
  - update_misra_report_deviations(): missing report creation, existing sync,
    deviation serialization variants
  - generate_autosar_deviations()
  - main(): --status, --report --dry-run, --autosar --dry-run, no-args help
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from yuleosh.ci import misra_deviations as MD
from yuleosh.ci.misra_deviations import Deviation


# ── Deviation dataclass ───────────────────────────────────────────────

class TestDeviation:
    def test_defaults(self):
        """GIVEN minimal deviation WHEN constructed THEN defaults filled."""
        d = Deviation(rule="misra-c2023-10.1", file="src/a.c")
        assert d.reason == ""
        assert d.expires == "2099-12-31"
        assert d.status == "open"

    def test_to_dict_roundtrip(self):
        """GIVEN deviation WHEN to_dict/from_dict THEN fields preserved."""
        d = Deviation(rule="r", file="f", reason="why", approved_by="architect",
                      expires="2027-01-01", status="approved")
        d2 = Deviation.from_dict(d.to_dict())
        assert d2.rule == "r" and d2.file == "f"
        assert d2.status == "approved" and d2.approved_by == "architect"

    def test_from_dict_legacy_keys(self):
        """GIVEN legacy keys WHEN from_dict THEN mapped to canonical fields."""
        d = Deviation.from_dict({"deviation_rule": "r1", "file_pattern": "**/*.c",
                                 "reason": "legacy"})
        assert d.rule == "r1"
        assert d.file == "**/*.c"

    def test_baseline_nonempty(self):
        """GIVEN AUTOSAR baseline THEN non-empty and approved."""
        assert len(MD.AUTOSAR_BASELINE_DEVIATIONS) > 10
        assert all(d.status == "approved" for d in MD.AUTOSAR_BASELINE_DEVIATIONS)
        assert MD.BASELINE_DEVIATION_COUNT == len(MD.AUTOSAR_BASELINE_DEVIATIONS)


# ── load_deviations_from_report ───────────────────────────────────────

class TestLoadDeviationsFromReport:
    def test_missing_report(self, tmp_path):
        """GIVEN missing report WHEN load THEN [] + warning."""
        with mock.patch("yuleosh.ci.misra_deviations.log") as mlog:
            result = MD.load_deviations_from_report(str(tmp_path / "nope.json"))
        assert result == []
        mlog.warning.assert_called()

    def test_load_with_legacy_keys(self, tmp_path):
        """GIVEN report with legacy keys WHEN load THEN parsed."""
        path = tmp_path / "report.json"
        path.write_text(json.dumps({"deviations": [
            {"deviation_rule": "r1", "file_pattern": "f1", "reason": "x",
             "approved_by": "a", "expires": "2028-01-01", "status": "approved"},
        ]}))
        devs = MD.load_deviations_from_report(str(path))
        assert len(devs) == 1
        assert devs[0].rule == "r1" and devs[0].file == "f1"

    def test_load_with_current_keys(self, tmp_path):
        """GIVEN report with current keys WHEN load THEN parsed."""
        path = tmp_path / "report.json"
        path.write_text(json.dumps({"deviations": [
            {"rule": "r2", "file": "f2"},
        ]}))
        devs = MD.load_deviations_from_report(str(path))
        assert devs[0].rule == "r2" and devs[0].file == "f2"


# ── compute_known_rate ────────────────────────────────────────────────

class _Misra:
    def __init__(self, deviations):
        self.deviations = deviations


class _Cfg:
    def __init__(self, deviations):
        self.misra = _Misra(deviations)


def _write_report(tmp_path, total=0, violations_raw=None):
    p = tmp_path / ".yuleosh" / "reports"
    p.mkdir(parents=True)
    report = {"summary": {"total_violations": total},
              "violations_raw": violations_raw or [],
              "groups": {}}
    (p / "misra-report.json").write_text(json.dumps(report))


class TestComputeKnownRate:
    def test_no_report(self, tmp_path):
        """GIVEN no report WHEN compute THEN zeros + rate from deviations."""
        devs = [Deviation(rule="r1", file="f")]
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=_Cfg(devs)):
            info = MD.compute_known_rate(str(tmp_path))
        assert info["total_violations"] == 0
        assert info["registered_deviations"] == 1
        assert info["known_rate"] == 100.0
        assert info["target_met"] is True

    def test_with_violations_unknown(self, tmp_path):
        """GIVEN report w/ unknown violations WHEN compute THEN rate < 100."""
        _write_report(tmp_path, total=5, violations_raw=[
            {"rule_id": "misra-1.1"}, {"rule_id": "misra-2.2"}])
        devs = [Deviation(rule="misra-1.1", file="f")]
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=_Cfg(devs)):
            info = MD.compute_known_rate(str(tmp_path))
        assert info["total_violations"] == 5
        assert info["known_violations"] == 1
        assert info["unknown_violations"] == 1
        assert info["known_rate"] == pytest.approx(1 / 6 * 100, abs=0.01)
        assert info["target_met"] is False

    def test_no_cfg(self, tmp_path):
        """GIVEN load_ci_config None WHEN compute THEN zero deviations."""
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=None):
            info = MD.compute_known_rate(str(tmp_path))
        assert info["registered_deviations"] == 0
        assert info["known_rate"] == 0.0


# ── register_batch_deviations ─────────────────────────────────────────

class TestRegisterBatch:
    def test_missing_config(self, tmp_path):
        """GIVEN no ci-config.yaml WHEN register THEN 0 + error log."""
        with mock.patch("yuleosh.ci.misra_deviations.log") as mlog:
            n = MD.register_batch_deviations(str(tmp_path), [Deviation("r", "f")])
        assert n == 0
        mlog.error.assert_called()

    def test_registers_new(self, tmp_path):
        """GIVEN config + new deviations WHEN register THEN appended + written."""
        cfg_path = tmp_path / ".yuleosh"
        cfg_path.mkdir(parents=True)
        cfg = {"misra": {"deviations": []}}
        (cfg_path / "ci-config.yaml").write_text(yaml.dump(cfg))
        n = MD.register_batch_deviations(
            str(tmp_path), [Deviation("r1", "f1"), Deviation("r2", "f2")])
        assert n == 2
        raw = yaml.safe_load((cfg_path / "ci-config.yaml").read_text())
        assert len(raw["misra"]["deviations"]) == 2

    def test_dedup_skips_existing(self, tmp_path):
        """GIVEN existing (rule, file) WHEN register THEN skipped."""
        cfg_path = tmp_path / ".yuleosh"
        cfg_path.mkdir(parents=True)
        cfg = {"misra": {"deviations": [{"rule": "r1", "file": "f1"}]}}
        (cfg_path / "ci-config.yaml").write_text(yaml.dump(cfg))
        n = MD.register_batch_deviations(
            str(tmp_path), [Deviation("r1", "f1"), Deviation("r1", "f1")])
        assert n == 0
        n2 = MD.register_batch_deviations(
            str(tmp_path), [Deviation("r1", "f1"), Deviation("r9", "f9")])
        assert n2 == 1

    def test_deduplicate_false(self, tmp_path):
        """GIVEN deduplicate=False WHEN register THEN duplicates allowed."""
        cfg_path = tmp_path / ".yuleosh"
        cfg_path.mkdir(parents=True)
        cfg = {"misra": {"deviations": []}}
        (cfg_path / "ci-config.yaml").write_text(yaml.dump(cfg))
        n = MD.register_batch_deviations(
            str(tmp_path), [Deviation("r1", "f1"), Deviation("r1", "f1")],
            deduplicate=False)
        assert n == 2


# ── update_misra_report_deviations ────────────────────────────────────

class TestUpdateReport:
    def test_missing_report_creates(self, tmp_path):
        """GIVEN no misra-report.json WHEN update THEN created with deviations."""
        devs = [Deviation("r1", "f1", reason="why", approved_by="a")]
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=_Cfg(devs)):
            n = MD.update_misra_report_deviations(str(tmp_path))
        assert n == 1
        report_path = tmp_path / ".yuleosh" / "reports" / "misra-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["deviations"][0]["rule"] == "r1"

    def test_existing_report_updated(self, tmp_path):
        """GIVEN existing report WHEN update THEN deviations replaced."""
        p = tmp_path / ".yuleosh" / "reports"
        p.mkdir(parents=True)
        (p / "misra-report.json").write_text(json.dumps({"old": True}))
        devs = [Deviation("r2", "f2")]
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=_Cfg(devs)):
            n = MD.update_misra_report_deviations(str(tmp_path))
        assert n == 1
        data = json.loads((p / "misra-report.json").read_text())
        assert data["old"] is True
        assert len(data["deviations"]) == 1

    def test_variant_serialization(self, tmp_path):
        """GIVEN mixed deviation types WHEN update THEN each serialized."""
        class LegacyLike:
            rule = "rL"
            file = "fL"
            reason = "x"
            approved_by = "a"
            expires = "2028-01-01"
            status = "open"

        devs = [Deviation("r1", "f1"),
                {"rule": "r2", "file": "f2"},
                LegacyLike(),
                "plain-string"]
        with mock.patch("yuleosh.ci.config.load_ci_config",
                        return_value=_Cfg(devs)):
            n = MD.update_misra_report_deviations(str(tmp_path))
        assert n == 4
        data = json.loads(
            (tmp_path / ".yuleosh" / "reports" / "misra-report.json").read_text())
        assert len(data["deviations"]) == 4
        assert data["deviations"][0]["rule"] == "r1"
        assert data["deviations"][2]["rule"] == "rL"
        assert data["deviations"][3] == "plain-string"


class TestGenerate:
    def test_generate_autosar(self):
        """GIVEN generate_autosar_deviations WHEN called THEN baseline returned."""
        devs = MD.generate_autosar_deviations()
        assert len(devs) == MD.BASELINE_DEVIATION_COUNT
        assert all(isinstance(d, Deviation) for d in devs)


# ── main CLI ──────────────────────────────────────────────────────────

class TestMain:
    def test_status(self, tmp_path, monkeypatch, capsys):
        """GIVEN --status WHEN main THEN known rate printed."""
        monkeypatch.setattr(sys, "argv", ["misra_deviations", str(tmp_path), "--status"])
        with mock.patch("yuleosh.ci.misra_deviations.compute_known_rate",
                        return_value={"total_violations": 1, "registered_deviations": 2,
                                      "known_violations": 1, "unknown_violations": 0,
                                      "known_rate": 66.67, "target_met": False}):
            MD.main()
        out = capsys.readouterr().out
        assert "MISRA Known Rate" in out
        assert "66.67%" in out

    def test_report_dry_run(self, tmp_path, monkeypatch, capsys):
        """GIVEN --report + --dry-run WHEN main THEN prints deviations."""
        report = tmp_path / "r.json"
        report.write_text(json.dumps({"deviations": [{"rule": "r1", "file": "f1"}]}))
        monkeypatch.setattr(sys, "argv", ["misra_deviations", str(tmp_path),
                                          "--report", str(report), "--dry-run"])
        MD.main()
        out = capsys.readouterr().out
        assert "Deviations from report: 1" in out

    def test_autosar_dry_run(self, tmp_path, monkeypatch, capsys):
        """GIVEN --autosar --dry-run WHEN main THEN prints baseline count."""
        monkeypatch.setattr(sys, "argv", ["misra_deviations", str(tmp_path),
                                          "--autosar", "--dry-run"])
        MD.main()
        out = capsys.readouterr().out
        assert "AUTOSAR baseline deviations" in out

    def test_no_args_help(self, tmp_path, monkeypatch, capsys):
        """GIVEN no args WHEN main THEN help printed."""
        monkeypatch.setattr(sys, "argv", ["misra_deviations"])
        MD.main()
        out = capsys.readouterr().out
        assert "usage:" in out.lower()
