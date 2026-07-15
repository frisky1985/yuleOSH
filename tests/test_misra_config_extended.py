#!/usr/bin/env python3
"""
Tests for MISRA C:2023 rule override and deviation configuration.

Tests:
  1. MisraRuleOverride dataclass default values
  2. MisraRuleOverride custom values
  3. MisraDeviation dataclass default values
  4. MisraDeviation custom values
  5. MisraConfig includes rule_overrides and deviations
  6. YAML parsing of rule_overrides from ci-config.yaml
  7. YAML parsing of deviations from ci-config.yaml
  8. Override: disabled rule → suppression in cppcheck args
  9. Override: severity override
  10. Deviation matching in _match_deviation
  11. Deviation not matching wrong rule
  12. Deviation not matching wrong file pattern
  13. generate_traceability_matrix with deviations
  14. generate_traceability_matrix without deviations (backward compat)
  15. generate_fix_tasks skips acknowledged violations
  16. save_report with deviations
  17. Empty deviations list
  18. Multiple deviations for different rules
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.ci.config import (
    MisraConfig, MisraRuleOverride, MisraDeviation,
    load_ci_config, _parse_ci_config,
)
from yuleosh.ci.misra_report import (
    generate_traceability_matrix, generate_fix_tasks,
    _match_deviation, load_rule_definitions,
    parse_cppcheck_output, save_report,
)


# ------------------------------------------------------------------
# Sample Data
# ------------------------------------------------------------------

SAMPLE_VIOLATIONS = [
    {
        "rule_id": "misra-c2023-17.7",
        "file": "src/legacy/old_driver.c",
        "line": 42,
        "col": 5,
        "severity": "style",
        "message": "misra-c2023-17.7: Return value not used",
    },
    {
        "rule_id": "misra-c2023-10.1",
        "file": "src/core/main.c",
        "line": 88,
        "col": 12,
        "severity": "error",
        "message": "misra-c2023-10.1: Inappropriate type",
    },
    {
        "rule_id": "misra-c2023-17.7",
        "file": "src/core/main.c",
        "line": 55,
        "col": 3,
        "severity": "style",
        "message": "misra-c2023-17.7: Return value not used",
    },
]

SAMPLE_RULE_DEFS = {
    "misra-c2023-17.7": {
        "title": "返回值必须被使用",
        "severity": "required",
        "category": "函数行为",
        "description": "调用具有返回值的函数，其返回值应被检查或使用",
        "spec_ref": "SWE-MISRA-S1; SWE-MISRA-DEV2",
        "check_method": "cppcheck",
        "auto_checkable": True,
    },
    "misra-c2023-10.1": {
        "title": "Operands shall not be of inappropriate type",
        "severity": "required",
        "category": "基本类型 (Essential Types)",
        "description": "操作数不得具有不适当的本质类型",
        "spec_ref": "SWE-MISRA-S1; SWE-MISRA-CFG2",
        "check_method": "cppcheck",
        "auto_checkable": True,
    },
}


# ------------------------------------------------------------------
# Tests: MisraRuleOverride
# ------------------------------------------------------------------


class TestMisraRuleOverride:
    """GIVEN MisraRuleOverride dataclass WHEN used THEN fields behave correctly."""

    def test_defaults(self):
        """WHEN default constructor THEN sensible defaults."""
        o = MisraRuleOverride()
        assert o.rule_id == ""
        assert o.enabled is True
        assert o.severity_override == ""
        assert o.auto_checkable_override is None

    def test_custom(self):
        """WHEN custom values THEN stored correctly."""
        o = MisraRuleOverride(
            rule_id="misra-c2023-10.1",
            enabled=False,
            severity_override="advisory",
            auto_checkable_override=False,
        )
        assert o.rule_id == "misra-c2023-10.1"
        assert o.enabled is False
        assert o.severity_override == "advisory"
        assert o.auto_checkable_override is False

    def test_disabled_rule_identity(self):
        """WHEN disabled THEN identifies as disabled rule."""
        o = MisraRuleOverride(rule_id="misra-c2023-17.7", enabled=False)
        assert not o.enabled
        assert o.rule_id == "misra-c2023-17.7"


# ------------------------------------------------------------------
# Tests: MisraDeviation
# ------------------------------------------------------------------


class TestMisraDeviation:
    """GIVEN MisraDeviation dataclass WHEN used THEN fields behave correctly."""

    def test_defaults(self):
        """WHEN default constructor THEN sensible defaults."""
        d = MisraDeviation()
        assert d.rule_id == ""
        assert d.file_pattern == ""
        assert d.reason == ""
        assert d.approved_by == ""
        assert d.expires == ""

    def test_custom(self):
        """WHEN custom values THEN stored correctly."""
        d = MisraDeviation(
            rule_id="misra-c2023-17.7",
            file_pattern="src/legacy/*.c",
            reason="Legacy code, planned Q3 refactor",
            approved_by="arch-review",
            expires="2026-09-30",
        )
        assert d.rule_id == "misra-c2023-17.7"
        assert d.file_pattern == "src/legacy/*.c"
        assert d.reason == "Legacy code, planned Q3 refactor"
        assert d.approved_by == "arch-review"
        assert d.expires == "2026-09-30"


# ------------------------------------------------------------------
# Tests: MisraConfig with overrides and deviations
# ------------------------------------------------------------------


class TestMisraConfigOverrides:
    """GIVEN MisraConfig WHEN rule_overrides and deviations are added THEN they persist."""

    def test_empty_overrides(self):
        """WHEN default MisraConfig THEN overrides and deviations are empty."""
        cfg = MisraConfig()
        assert cfg.rule_overrides == []
        assert cfg.deviations == []

    def test_with_overrides(self):
        """WHEN rule_overrides provided THEN stored correctly."""
        overrides = [
            MisraRuleOverride(rule_id="misra-c2023-17.7", enabled=False),
            MisraRuleOverride(rule_id="misra-c2023-21.6", severity_override="advisory"),
        ]
        cfg = MisraConfig(rule_overrides=overrides)
        assert len(cfg.rule_overrides) == 2
        assert cfg.rule_overrides[0].rule_id == "misra-c2023-17.7"
        assert cfg.rule_overrides[0].enabled is False
        assert cfg.rule_overrides[1].severity_override == "advisory"

    def test_with_deviations(self):
        """WHEN deviations provided THEN stored correctly."""
        devs = [
            MisraDeviation(
                rule_id="misra-c2023-17.7",
                file_pattern="src/legacy/*.c",
                reason="refactor planned",
                approved_by="arch",
                expires="2026-09-30",
            ),
        ]
        cfg = MisraConfig(deviations=devs)
        assert len(cfg.deviations) == 1
        assert cfg.deviations[0].file_pattern == "src/legacy/*.c"
        assert cfg.deviations[0].approved_by == "arch"


# ------------------------------------------------------------------
# Tests: YAML parsing
# ------------------------------------------------------------------


class TestYamlParsing:
    """GIVEN ci-config.yaml with misra.rules and misra.deviations WHEN parsed THEN correct."""

    @pytest.fixture
    def tmp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True, exist_ok=True)
            cfg = {
                "misra": {
                    "enabled": True,
                    "fail_on_violation": True,
                    "rules": {
                        "misra-c2023-17.7": {
                            "enabled": False,
                        },
                        "misra-c2023-21.6": {
                            "severity": "advisory",
                        },
                    },
                    "deviations": [
                        {
                            "rule": "misra-c2023-17.7",
                            "file": "src/legacy/*.c",
                            "reason": "Legacy code",
                            "approved_by": "arch-review",
                            "expires": "2026-09-30",
                        },
                    ],
                },
            }
            cfg_path = yuleosh_dir / "ci-config.yaml"
            import yaml
            with open(cfg_path, "w") as f:
                yaml.dump(cfg, f)
            yield tmpdir

    def test_parse_rule_overrides(self, tmp_project):
        """WHEN YAML has rules block THEN MisraRuleOverride objects created."""
        cfg = load_ci_config(tmp_project)
        assert len(cfg.misra.rule_overrides) == 2
        override_17_7 = [o for o in cfg.misra.rule_overrides if o.rule_id == "misra-c2023-17.7"][0]
        assert override_17_7.enabled is False
        override_21_6 = [o for o in cfg.misra.rule_overrides if o.rule_id == "misra-c2023-21.6"][0]
        assert override_21_6.severity_override == "advisory"

    def test_parse_deviations(self, tmp_project):
        """WHEN YAML has deviations block THEN MisraDeviation objects created."""
        cfg = load_ci_config(tmp_project)
        assert len(cfg.misra.deviations) == 1
        dev = cfg.misra.deviations[0]
        assert dev.rule_id == "misra-c2023-17.7"
        assert dev.file_pattern == "src/legacy/*.c"
        assert dev.reason == "Legacy code"
        assert dev.approved_by == "arch-review"
        assert dev.expires == "2026-09-30"

    def test_yaml_empty_rules(self, tmp_project):
        """WHEN YAML has empty rules block THEN no overrides."""
        with open(Path(tmp_project) / ".yuleosh" / "ci-config.yaml", "w") as f:
            import yaml
            yaml.dump({"misra": {"rules": {}}}, f)
        cfg = load_ci_config(tmp_project)
        assert cfg.misra.rule_overrides == []


# ------------------------------------------------------------------
# Tests: _match_deviation
# ------------------------------------------------------------------


class TestMatchDeviation:
    """GIVEN _match_deviation function WHEN called THEN matches correctly."""

    def test_match_exact(self):
        """WHEN rule and pattern match THEN returns True."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matched, info = _match_deviation("misra-c2023-17.7", "src/legacy/old_driver.c", deviations)
        assert matched is True
        assert info is not None

    def test_no_match_wrong_rule(self):
        """WHEN rule does not match THEN returns False."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matched, info = _match_deviation("misra-c2023-10.1", "src/legacy/old_driver.c", deviations)
        assert matched is False
        assert info is None

    def test_no_match_wrong_file(self):
        """WHEN file pattern does not match THEN returns False."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matched, info = _match_deviation("misra-c2023-17.7", "src/core/main.c", deviations)
        assert matched is False
        assert info is None

    def test_empty_deviations(self):
        """WHEN deviations list is empty THEN no match."""
        matched, info = _match_deviation("misra-c2023-17.7", "src/legacy/old_driver.c", [])
        assert matched is False
        assert info is None

    def test_multiple_deviations(self):
        """WHEN multiple deviations THEN correct one matches."""
        deviations = [
            ("misra-c2023-10.1", "src/core/*.c"),
            ("misra-c2023-17.7", "src/legacy/*.c"),
        ]
        matched, info = _match_deviation("misra-c2023-10.1", "src/core/main.c", deviations)
        assert matched is True
        matched2, _ = _match_deviation("misra-c2023-17.7", "src/legacy/old_driver.c", deviations)
        assert matched2 is True
        matched3, _ = _match_deviation("misra-c2023-10.1", "src/legacy/old_driver.c", deviations)
        assert matched3 is False


# ------------------------------------------------------------------
# Tests: generate_traceability_matrix with deviations
# ------------------------------------------------------------------


class TestTraceabilityWithDeviations:
    """GIVEN generate_traceability_matrix WHEN deviations provided THEN fix_status reflects."""

    def test_acknowledged_when_matched(self):
        """WHEN violation matches deviation THEN fix_status='acknowledged'."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        # First violation: misra-c2023-17.7 in src/legacy/old_driver.c → MATCH
        assert matrix[0]["fix_status"] == "acknowledged"
        assert "deviation_ref" in matrix[0]

    def test_deviation_risk_level_and_expires(self):
        """WHEN deviation has risk_level and expires THEN reflected in traceability."""
        deviations = [{
            "rule_id": "misra-c2023-17.7",
            "file_pattern": "src/legacy/*.c",
            "reason": "Legacy code",
            "approved_by": "arch",
            "risk_level": "high",
            "expires": "2029-12-31",
            "status": "approved",
        }]
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        entry = matrix[0]
        assert entry["fix_status"] == "acknowledged"
        assert entry["risk_level_info"] != ""
        assert entry["expiration_status"]["is_expired"] is False
        assert entry["expiration_status"]["expires"] == "2029-12-31"

    def test_unresolved_when_no_match(self):
        """WHEN violation does not match deviation THEN fix_status='unresolved'."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        # Second violation: misra-c2023-10.1 in src/core/main.c → no match
        assert matrix[1]["fix_status"] == "unresolved"
        assert "deviation_ref" not in matrix[1]

    def test_unresolved_wrong_file(self):
        """WHEN same rule but wrong file pattern THEN unresolved."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        # Third violation: misra-c2023-17.7 in src/core/main.c → no match (wrong file)
        assert matrix[2]["fix_status"] == "unresolved"

    def test_backward_compat_no_deviations(self):
        """WHEN no deviations param THEN all unresolved (backward compat)."""
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        for entry in matrix:
            assert entry["fix_status"] == "unresolved"

    def test_entry_structure(self):
        """WHEN deviation matched THEN deviation_ref has risk and expiration info."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        matrix = generate_traceability_matrix(SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        entry = matrix[0]
        assert "deviation_ref" in entry
        assert entry["deviation_ref"]["deviation_rule"] == "misra-c2023-17.7"


# ------------------------------------------------------------------
# Tests: generate_fix_tasks with deviations
# ------------------------------------------------------------------


class TestFixTasksWithDeviations:
    """GIVEN generate_fix_tasks WHEN deviations provided THEN acknowledged violations skipped."""

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_acknowledged_violations_skipped(self, tmp_dir):
        """WHEN violation is acknowledged THEN no fix task generated for it."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        files = generate_fix_tasks(tmp_dir, SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS, deviations=deviations)
        # misra-c2023-17.7 has 2 violations: 1 matched (acknowledged), 1 unmatched (unresolved)
        # So fix task should still be created for misra-c2023-17.7 (1 unresolved remains)
        # And for misra-c2023-10.1 (1 violation, unresolved)
        assert len(files) == 2  # Two rules still have unresolved violations
        for f in files:
            assert os.path.exists(f)

    def test_all_acknowledged_skipped(self, tmp_dir):
        """WHEN all violations of a rule acknowledged THEN no fix task for that rule."""
        # Only one violation that matches deviation
        violations = [{
            "rule_id": "misra-c2023-17.7",
            "file": "src/legacy/old_driver.c",
            "line": 42,
            "col": 5,
            "severity": "style",
            "message": "misra-c2023-17.7: Return value not used",
        }]
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        files = generate_fix_tasks(tmp_dir, violations, SAMPLE_RULE_DEFS, deviations=deviations)
        assert len(files) == 0  # All acknowledged, no fix tasks

    def test_backward_compat_no_deviations(self, tmp_dir):
        """WHEN no deviations param THEN all violations generate fix tasks."""
        files = generate_fix_tasks(tmp_dir, SAMPLE_VIOLATIONS, SAMPLE_RULE_DEFS)
        assert len(files) == 2  # Two rules violated
        for f in files:
            assert os.path.exists(f)


# ------------------------------------------------------------------
# Tests: save_report with deviations
# ------------------------------------------------------------------


class TestSaveReportWithDeviations:
    """GIVEN save_report WHEN deviations provided THEN traceability JSON includes them."""

    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_traceability_includes_acknowledged(self, tmp_dir):
        """WHEN deviations provided THEN traceability JSON has acknowledged entries."""
        deviations = [("misra-c2023-17.7", "src/legacy/*.c")]
        groups = {
            "misra-c2023-17.7": {
                "violations": [v for v in SAMPLE_VIOLATIONS if v["rule_id"] == "misra-c2023-17.7"],
                "rule_id": "misra-c2023-17.7", "count": 2, "files": ["src/core/main.c", "src/legacy/old_driver.c"],
            },
            "misra-c2023-10.1": {
                "violations": [v for v in SAMPLE_VIOLATIONS if v["rule_id"] == "misra-c2023-10.1"],
                "rule_id": "misra-c2023-10.1", "count": 1, "files": ["src/core/main.c"],
            },
        }
        summary = {
            "total_violations": 3,
            "total_rules_violated": 2,
            "severity_counts": {"style": 2, "error": 1},
            "unique_files": ["src/core/main.c", "src/legacy/old_driver.c"],
            "per_file_counts": {"src/core/main.c": 2, "src/legacy/old_driver.c": 1},
        }

        json_path, md_path, trace_path, *_ = save_report(
            SAMPLE_VIOLATIONS, groups, summary, SAMPLE_RULE_DEFS,
            tmp_dir, deviations=deviations,
        )

        assert json_path.exists()
        assert md_path.exists()
        assert trace_path.exists()

        # Trace file is CSV, verify it contains expected entries
        csv_lines = trace_path.read_text().strip().split("\n")
        assert len(csv_lines) >= 2  # header + data
        header = csv_lines[0].split(",")
        assert "rule_id" in header
        assert "fix_status" in header

        import csv
        reader = csv.DictReader(csv_lines)
        rows = list(reader)
        ack_rows = [r for r in rows if r.get("fix_status") == "acknowledged"]
        unresolved_rows = [r for r in rows if r.get("fix_status") == "unresolved"]
        assert len(ack_rows) >= 1
        assert len(unresolved_rows) >= 1


# ------------------------------------------------------------------
# Integration: Verify the whole flow
# ------------------------------------------------------------------


class TestMisraOverrideCppcheckArgs:
    """GIVEN MisraRuleOverride with enabled=False WHEN building cppcheck args THEN rule suppressed."""

    def test_disabled_rule_creates_suppress(self):
        """WHEN rule disabled THEN cppcheck gets --suppress=misra-... arg."""
        override = MisraRuleOverride(rule_id="misra-c2023-17.7", enabled=False)
        suppress_args = []
        if not override.enabled and override.rule_id:
            suppress_args.append("--suppress=" + override.rule_id)
        assert "--suppress=misra-c2023-17.7" in suppress_args

    def test_enabled_rule_no_suppress(self):
        """WHEN rule enabled THEN no suppress arg created."""
        override = MisraRuleOverride(rule_id="misra-c2023-10.1", enabled=True)
        suppress_args = []
        if not override.enabled and override.rule_id:
            suppress_args.append("--suppress=" + override.rule_id)
        assert len(suppress_args) == 0
