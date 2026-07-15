"""
Extended tests for yuleosh.ci.yaml_validator — push coverage ≥ 60%.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestCheckType:
    """Cover yaml_validator._check_type branches."""

    def test_str_type_ok(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type("hello", "str", "x") == []

    def test_str_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type(42, "str", "x")
        assert len(errs) == 1
        assert "expected str" in errs[0]

    def test_int_type_ok(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type(42, "int", "x") == []

    def test_int_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type("hello", "int", "x")
        assert len(errs) == 1

    def test_float_type_ok_int(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type(42, "float", "x") == []

    def test_float_type_ok_float(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type(3.14, "float", "x") == []

    def test_float_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type("abc", "float", "x")
        assert len(errs) == 1

    def test_bool_type_ok(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type(True, "bool", "x") == []

    def test_bool_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type("yes", "bool", "x")
        assert len(errs) == 1

    def test_dict_type_ok(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type({"a": 1}, "dict", "x") == []

    def test_dict_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type([], "dict", "x")
        assert len(errs) == 1

    def test_list_type_ok(self):
        from yuleosh.ci.yaml_validator import _check_type
        assert _check_type([1, 2], "list", "x") == []

    def test_list_type_fail(self):
        from yuleosh.ci.yaml_validator import _check_type
        errs = _check_type({}, "list", "x")
        assert len(errs) == 1


class TestValidateAgainstSchema:
    """Cover misc branches of _validate_against_schema."""

    def test_non_dict_data(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        errs = _validate_against_schema("not dict", {"ci": {"type": "dict"}})
        assert any("expected dict" in e for e in errs)

    def test_dict_with_keys(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        errs = _validate_against_schema(
            {"ci": {"layers": [1, 2, 3]}},
            {"ci": {"type": "dict", "keys": {"layers": {"type": "list", "items": "int"}}}},
        )
        assert errs == []

    def test_list_type_mismatch_with_allowed_values(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        errs = _validate_against_schema(
            {"ci": {"enabled": False}},
            {"ci": {"type": "dict", "keys": {"enabled": {"type": "bool"}}}},
        )
        assert errs == []

    def test_values_check_invalid(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        schema = {"mode": {"type": "str", "values": ["safe", "fast"]}}
        errs = _validate_against_schema({"mode": "invalid"}, schema)
        assert any("not in" in e for e in errs)

    def test_values_check_ok(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        schema = {"mode": {"type": "str", "values": ["safe", "fast"]}}
        errs = _validate_against_schema({"mode": "safe"}, schema)
        assert errs == []

    def test_field_not_present_skips(self):
        """Optional field not in data — no error."""
        from yuleosh.ci.yaml_validator import _validate_against_schema
        schema = {"optional_field": {"type": "int"}}
        errs = _validate_against_schema({}, schema)
        assert errs == []

    def test_list_items_check(self):
        from yuleosh.ci.yaml_validator import _validate_against_schema
        schema = {"names": {"type": "list", "items": "str"}}
        errs = _validate_against_schema({"names": ["a", 42, "c"]}, schema)
        str_errs = [e for e in errs if "expected str" in e]
        assert len(str_errs) == 1  # only the 42 fails


class TestValidateCiConfig:
    """Cover validate_ci_config branches."""

    def test_file_not_found(self):
        from yuleosh.ci.yaml_validator import validate_ci_config
        result = validate_ci_config("/nonexistent/path.yaml")
        assert result["valid"] is False
        assert "File not found" in result["errors"][0]

    def test_yaml_parse_error(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("{{invalid: yaml: ")
        result = validate_ci_config(str(f))
        assert result["valid"] is False
        assert any("parse" in e.lower() for e in result["errors"])

    def test_io_error(self):
        from yuleosh.ci.yaml_validator import validate_ci_config
        # Use a mock to simulate OSError on open
        with mock.patch("builtins.open", side_effect=OSError("permission denied")):
            with mock.patch("os.path.isfile", return_value=True):
                result = validate_ci_config("/tmp/ci-config.yaml")
                assert result["valid"] is False
                assert any("IO error" in e or "permission" in e.lower() for e in result["errors"])

    def test_root_not_dict(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("just a string")
        result = validate_ci_config(str(f))
        assert result["valid"] is False
        assert "Root must be a dict" in result["errors"][0]

    def test_unknown_top_level_key(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("unknown_field: 42\nci:\n  layers: [1]")
        result = validate_ci_config(str(f))
        assert any("unexpected key" in e for e in result["errors"])

    def test_valid_minimal(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("ci:\n  layers: [1, 2]\n  layer_dependencies: {}\n")
        result = validate_ci_config(str(f))
        assert result["valid"] is True

    def test_valid_full(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("""\
ci:
  layers: [1, 2, 25, 3]
  layer_dependencies: {1: [], 2: [1]}
coverage:
  threshold_line: 80.0
  threshold_condition: 75.0
  strict: false
  c_fail_under: 80
  module_thresholds: {}
docsync:
  enabled: true
  rules:
    - "*.md"
  mode: relaxed
  exempt_paths: []
  critical_docs: []
  staleness_days: 30
  audit: {}
misra:
  enabled: true
  addon: misra
  fail_on_required: true
  fail_on_violation: true
  fail_on_advisory: false
  fail_threshold: 100
  violations_per_kloc: 5.0
  cppcheck_std: c23
  active_profile: safety
  rule_texts_path: misra-rules.yaml
  suppress_rules: []
  rules: {}
  deviations: []
  alm: {}
  profiles: {}
  exclude_paths: []
  code_categories: {}
hardware_test: {}
""")
        result = validate_ci_config(str(f))
        assert result["valid"] is True, f"Errors: {result['errors']}"

    def test_invalid_docsync_type(self, tmp_path):
        """docsync.enabled should be bool, not string."""
        from yuleosh.ci.yaml_validator import validate_ci_config
        f = tmp_path / "ci-config.yaml"
        f.write_text("docsync:\n  enabled: 'yes'\n")
        result = validate_ci_config(str(f))
        assert result["valid"] is False
        assert any("bool" in e for e in result["errors"])


class TestValidateMisraRules:
    """Cover validate_misra_rules branches."""

    def test_file_not_found(self):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        result = validate_misra_rules("/nonexistent.yaml")
        assert result["valid"] is False

    def test_yaml_parse_error(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("{{bad: yaml")
        result = validate_misra_rules(str(f))
        assert result["valid"] is False

    def test_root_not_dict(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("[1, 2, 3]")
        result = validate_misra_rules(str(f))
        assert result["valid"] is False

    def test_skips_meta_block(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("meta:\n  version: 1.0\n")
        result = validate_misra_rules(str(f))
        assert result["valid"] is True  # No rules to validate

    def test_rule_not_dict(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("R1: just a string\n")
        result = validate_misra_rules(str(f))
        assert result["valid"] is False

    def test_valid_rule(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("""\
R1:
  severity: required
  category: safety
  description: Test rule
  title: Test
  spec_ref: spec1
  check_method: static
  auto_checkable: false
  mcu: all
  profile: safety
""")
        result = validate_misra_rules(str(f))
        assert result["valid"] is True

    def test_invalid_severity_value(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_misra_rules
        f = tmp_path / "misra-rules.yaml"
        f.write_text("""\
R1:
  severity: invalid_value
  category: safety
  description: Test
  title: Test
  spec_ref: spec1
  check_method: static
  auto_checkable: true
  mcu: all
  profile: safety
""")
        result = validate_misra_rules(str(f))
        assert result["valid"] is False


class TestValidateAll:
    """Cover validate_all branches."""

    def test_both_missing(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_all
        result = validate_all(str(tmp_path))
        assert result["valid"] is False
        assert "ci-config" in result["errors"]
        assert "misra-rules" in result["errors"]

    def test_both_valid(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_all
        # Create both files
        ci_dir = tmp_path / ".yuleosh"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "ci-config.yaml").write_text("ci:\n  layers: [1]\n  layer_dependencies: {}\n")
        (tmp_path / "misra-rules.yaml").write_text("meta:\n  version: 1\n")
        result = validate_all(str(tmp_path))
        assert result["valid"] is True
