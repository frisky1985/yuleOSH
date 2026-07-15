"""
Extended tests for yuleosh.ci.rulesets — push coverage ≥ 60%.
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# =====================================================================
# BaseRuleSet
# =====================================================================

class TestBaseRuleSetValidate:
    """Cover BaseRuleSet.validate() branches."""

    def _make_ruleset(self, rules):
        """Create a minimal concrete ruleset for testing."""
        from yuleosh.ci.rulesets.base import BaseRuleSet
        class TestRS(BaseRuleSet):
            _name = "test"
            _display_name = "Test"
            def supported_tools(self): return []
            def get_tool_config(self, t): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, r): return "advisory"
            def rule_definitions(self): return {"rules": rules}
        return TestRS()

    def test_no_rules(self):
        rs = self._make_ruleset({})
        errs = rs.validate()
        assert any("No rules defined" in e for e in errs)

    def test_missing_required_fields(self):
        rs = self._make_ruleset({
            "R1": {"title": "x"},  # missing severity, category, etc
        })
        errs = rs.validate()
        assert any("missing required field" in e for e in errs)

    def test_invalid_severity(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S9",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": True,
            }
        })
        errs = rs.validate()
        assert any("invalid severity" in e for e in errs)

    def test_mapped_misra_ids_valid(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S0",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": True,
                "mapped_misra_ids": ["misra-c2023-17.7"],
            }
        })
        errs = rs.validate()
        assert errs == []

    def test_mapped_misra_ids_invalid(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S1",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": True,
                "mapped_misra_ids": ["bad-format"],
            }
        })
        errs = rs.validate()
        assert any("invalid mapped_misra_id" in e for e in errs)

    def test_no_mapping_no_refs(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S2",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": True,
            }
        })
        errs = rs.validate()
        assert any("missing references" in e for e in errs)

    def test_no_mapping_has_refs(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S2",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": True,
                "references": "some ref",
            }
        })
        errs = rs.validate()
        assert errs == []

    def test_auto_checkable_not_bool(self):
        rs = self._make_ruleset({
            "R1": {
                "title": "x", "severity": "S0",
                "category": "safety", "description_en": "desc",
                "check_method": "static", "auto_checkable": "yes",
                "mapped_misra_ids": ["misra-c2023-17.7"],
            }
        })
        errs = rs.validate()
        assert any("auto_checkable" in e for e in errs)


class TestBaseRuleSetValidMisraId:
    """Cover _valid_misra_id_format."""

    def test_standard_rule(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-c2023-17.7")
        assert BaseRuleSet._valid_misra_id_format("misra-c2012-14.1")

    def test_directive(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-c2023-dir-4.1")
        assert BaseRuleSet._valid_misra_id_format("misra-c2012-Dir-4.1")

    def test_mandatory_rule(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-c2023-mrule-21.2")

    def test_cwe(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-c2012-cwe-416")

    def test_triple_version_c(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-c2012-0.1.2")
        assert BaseRuleSet._valid_misra_id_format("misra-c2023-dir-0.3.1")

    def test_cpp_rules(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert BaseRuleSet._valid_misra_id_format("misra-cpp2008-0.1.2")
        assert BaseRuleSet._valid_misra_id_format("misra-cpp2023-7.5.1")

    def test_invalid(self):
        from yuleosh.ci.rulesets.base import BaseRuleSet
        assert not BaseRuleSet._valid_misra_id_format("")
        assert not BaseRuleSet._valid_misra_id_format("misra-c2004-1.0")
        assert not BaseRuleSet._valid_misra_id_format("not-misra")
        assert not BaseRuleSet._valid_misra_id_format("misra-c2023-abc")


# =====================================================================
# GscCppRuleSet
# =====================================================================

class TestGscCppRuleSet:
    """Cover GscCppRuleSet implementation."""

    def test_name(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert rs.name == "gscr-cpp"

    def test_display_name(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert "GSCR C++" in rs.display_name

    def test_supported_tools(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        tools = rs.supported_tools()
        assert "clang-tidy" in tools
        assert "cppcheck" in tools

    def test_get_tool_config_clang(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        cfg = rs.get_tool_config("clang-tidy")
        assert "checks" in cfg
        assert "extra_args" in cfg

    def test_get_tool_config_cppcheck(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        cfg = rs.get_tool_config("cppcheck")
        assert "addon" in cfg
        assert "enable" in cfg

    def test_get_tool_config_unknown(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert rs.get_tool_config("unknown") == {}

    def test_get_report_template_config(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        cfg = rs.get_report_template_config()
        assert "GSCR C++" in cfg["report_title"]

    def test_classify_rule_empty(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert rs.classify_rule("") == "project_specific"

    def test_classify_rule_unknown(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        # Unknown rule falls through to default
        result = rs.classify_rule("NONEXISTENT-001")
        assert result in ("advisory", "project_specific", "required", "critical")

    def test_map_misra_to_gscr_no_mapping(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        result = rs.map_misra_to_gscr("misra-cpp2023-0.0.1")
        assert result == []

    def test_translate_violations_empty(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert rs.translate_violations([]) == []

    def test_translate_violations_unmapped(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        result = rs.translate_violations([{"rule_id": "unknown"}])
        assert len(result) == 1
        assert result[0]["gscr_rule_ids"] == []
        assert "未映射" in result[0]["gscr_category"]

    def test_get_rule_count_structure(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        counts = rs.get_rule_count()
        assert "total" in counts
        assert "S0" in counts
        assert "S1" in counts
        assert "S2" in counts
        assert "auto_checkable" in counts
        assert "manual_review" in counts
        assert counts["total"] >= 0

    def test_get_gscr_rule_not_found(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        assert rs.get_gscr_rule("NONEXISTENT") == {}

    def test_list_rules_by_severity(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        result = rs.list_rules_by_severity("S0")
        assert isinstance(result, list)

    def test_list_rules_by_category(self):
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        result = rs.list_rules_by_category("safety")
        assert isinstance(result, list)

    @mock.patch("yuleosh.ci.rulesets.gscr_cpp.Path.exists")
    @mock.patch("builtins.open")
    @mock.patch("yaml.safe_load")
    def test_rule_definitions_loads_yaml(self, mock_yaml, mock_open, mock_exists):
        mock_exists.return_value = True
        mock_yaml.return_value = {"meta": {"version": "1"}, "rules": {"R1": {"title": "test"}}}
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        defs = rs.rule_definitions()
        assert "rules" in defs

    @mock.patch("yuleosh.ci.rulesets.gscr_cpp.Path.exists")
    def test_rules_file_not_found(self, mock_exists):
        mock_exists.return_value = False
        from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
        rs = GscCppRuleSet()
        defs = rs.rule_definitions()
        assert defs == {"meta": {}, "rules": {}}

    @mock.patch("yuleosh.ci.rulesets.gscr_cpp.Path.exists")
    @mock.patch("yaml.safe_load")
    def test_yaml_import_error(self, mock_load, mock_exists):
        mock_exists.return_value = True
        # Simulate no yaml module
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No yaml")
            return real_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=mock_import):
            # Force reload the module with the yaml import mocked
            from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
            rs = GscCppRuleSet()
            # The _load_rule_definitions method tries to import yaml
            defs = rs.rule_definitions()
            assert defs == {"meta": {}, "rules": {}}


# =====================================================================
# Composite RuleSet
# =====================================================================

class TestGscrCompositeRuleSet:
    """Cover GscrCompositeRuleSet implementation."""

    def test_name(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        assert rs.name == "gscr"

    def test_display_name(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        assert "GSCR" in rs.display_name

    def test_supported_tools(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        tools = rs.supported_tools()
        assert "cppcheck" in tools
        assert "clang-tidy" in tools

    def test_get_tool_config_cppcheck(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        cfg = rs.get_tool_config("cppcheck")
        assert "addon" in cfg

    def test_get_tool_config_clang_tidy(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        cfg = rs.get_tool_config("clang-tidy")
        assert "checks" in cfg

    def test_get_tool_config_unknown(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        assert rs.get_tool_config("unknown") == {}

    def test_classify_rule_delegates_to_c(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        # Test a rule that's likely in C ruleset
        result = rs.classify_rule("c001")
        assert isinstance(result, str)

    def test_classify_rule_delegates_to_cpp(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        # Test unknown rule — falls through both
        result = rs.classify_rule("__unknown_rule__")
        assert result in ("advisory", "project_specific")

    def test_get_gscr_rule_c(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.get_gscr_rule("__nonexistent__")
        assert result == {}

    def test_map_misra_to_gscr(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.map_misra_to_gscr("misra-c2023-1.0")
        assert isinstance(result, list)

    def test_validate(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        errs = rs.validate()
        assert isinstance(errs, list)

    def test_get_rule_count(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        counts = rs.get_rule_count()
        assert "total" in counts
        assert "C" in counts
        assert "C++" in counts

    def test_translate_violations_empty(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.translate_violations([])
        assert result == []

    def test_translate_violations_c(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.translate_violations([
            {"rule_id": "misra-c2023-17.7"},
        ])
        assert len(result) == 1

    def test_translate_violations_cpp(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.translate_violations([
            {"rule_id": "misra-cpp2023-0.1.2"},
        ])
        assert len(result) == 1

    def test_translate_violations_other_no_mapping(self):
        from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
        rs = GscrCompositeRuleSet()
        result = rs.translate_violations([
            {"rule_id": "unknown-rule-id"},
        ])
        assert len(result) == 1
        assert result[0]["gscr_rule_ids"] == []
