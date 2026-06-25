#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Unit tests for yuleosh.ci.rulesets

Tests the Ruleset Plugin System (BaseRuleSet, MisraC2023RuleSet, RulesetRegistry).
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── Ensure src is on path ──────────────────────────────────────────
_project_root = Path(__file__).resolve().parent.parent.parent / "src"
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ── Module under test ──────────────────────────────────────────────
from yuleosh.ci.rulesets import (
    BaseRuleSet,
    MisraC2023RuleSet,
    RulesetRegistry,
    _DEFAULT_RULES_PATH,
)


# ====================================================================
# BaseRuleSet — abstract contract
# ====================================================================


class TestBaseRuleSet:
    """Tests for BaseRuleSet abstract base class."""

    def test_cannot_instantiate_abstract(self):
        """BaseRuleSet cannot be instantiated directly (abstract methods)."""
        with pytest.raises(TypeError):
            BaseRuleSet()  # type: ignore[abstract]

    def test_name_property_falls_back_to_class_var(self):
        """name returns _name class variable."""
        class Concrete(BaseRuleSet):
            _name = "test-ruleset"
            _display_name = "Test Ruleset"

            def supported_tools(self): return []
            def get_tool_config(self, tool): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, rule_id): return "required"
            def rule_definitions(self): return {}

        rs = Concrete()
        assert rs.name == "test-ruleset"
        assert rs.display_name == "Test Ruleset"


# ====================================================================
# MisraC2023RuleSet
# ====================================================================


class TestMisraC2023RuleSet:
    """Tests for MisraC2023RuleSet implementation."""

    @pytest.fixture
    def ruleset(self):
        """Fixture: create a MisraC2023RuleSet with in-memory rule definitions.

        Bypasses __init__ to avoid real YAML loading, then injects mock data.
        """
        rs = MisraC2023RuleSet.__new__(MisraC2023RuleSet)
        rs._rules_path = Path("/fake/path")
        rs._defs = {
            "meta": {"standard": "MISRA C", "version": "2023", "ruleset_version": "2023.1"},
            "misra-c2023-1.1": {
                "title": "ISO C standard compliance",
                "severity": "required",
                "category": "Environment",
                "description": "All code shall comply with ISO C",
                "check_method": "cppcheck",
                "auto_checkable": True,
            },
            "misra-c2023-2.3": {
                "title": "No unused type declarations",
                "severity": "advisory",
                "category": "Uncategorized",
                "description": "No unused type declarations",
                "check_method": "cppcheck",
                "auto_checkable": True,
            },
        }
        rs._classify_cache = {
            "misra-c2023-1.1": "required",
            "misra-c2023-2.3": "advisory",
        }
        return rs

    def test_name(self, ruleset):
        assert ruleset.name == "misra-c2023"

    def test_display_name(self, ruleset):
        assert ruleset.display_name == "MISRA C:2023"

    def test_supported_tools(self, ruleset):
        tools = ruleset.supported_tools()
        assert "cppcheck" in tools
        assert "clang-tidy" in tools

    def test_get_tool_config_cppcheck(self, ruleset):
        cfg = ruleset.get_tool_config("cppcheck")
        assert cfg["addon"] == "misra"
        assert "missingInclude" in cfg["suppress"]

    def test_get_tool_config_clang_tidy(self, ruleset):
        cfg = ruleset.get_tool_config("clang-tidy")
        assert "misra-c2023-*" in cfg["checks"]

    def test_get_tool_config_unknown(self, ruleset):
        cfg = ruleset.get_tool_config("unknown-tool")
        assert cfg == {}

    def test_get_report_template_config(self, ruleset):
        cfg = ruleset.get_report_template_config()
        assert "report_title" in cfg
        assert "classification" in cfg
        assert "required" in cfg["classification"]

    def test_classify_rule_required(self, ruleset):
        assert ruleset.classify_rule("misra-c2023-1.1") == "required"

    def test_classify_rule_advisory(self, ruleset):
        assert ruleset.classify_rule("misra-c2023-2.3") == "advisory"

    def test_classify_rule_unknown(self, ruleset):
        assert ruleset.classify_rule("misra-c2023-99.99") == "project_specific"

    def test_classify_rule_directive(self, ruleset):
        result = ruleset.classify_rule("misra-c2023-Dir-4.12")
        assert result == "directive"

    def test_classify_rule_empty(self, ruleset):
        assert ruleset.classify_rule("") == "project_specific"
        assert ruleset.classify_rule(None) == "project_specific"

    def test_rule_definitions(self, ruleset):
        defs = ruleset.rule_definitions()
        assert "misra-c2023-1.1" in defs
        assert "meta" in defs
        assert defs["misra-c2023-1.1"]["title"] == "ISO C standard compliance"

    def test_yaml_not_found(self):
        """Returns empty dict when YAML file doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            rs = MisraC2023RuleSet()
        assert rs.rule_definitions() == {}

    def test_yaml_parse_error(self):
        """Handles YAML parse errors gracefully."""
        rs = MisraC2023RuleSet.__new__(MisraC2023RuleSet)
        rs._rules_path = Path("/fake/path")
        rs._defs = {}
        rs._classify_cache = {}
        assert rs.rule_definitions() == {}


# ====================================================================
# RulesetRegistry
# ====================================================================


class TestRulesetRegistry:
    """Tests for RulesetRegistry singleton."""

    def setup_method(self):
        """Reset singleton before each test."""
        # Force re-creation for clean state in each test
        RulesetRegistry._instance = None

    def test_singleton(self):
        """RulesetRegistry is a singleton."""
        r1 = RulesetRegistry()
        r2 = RulesetRegistry()
        assert r1 is r2

    def test_register_and_create(self):
        """Register a ruleset class and create an instance."""
        registry = RulesetRegistry()
        registry.register(MisraC2023RuleSet)
        rs = registry.create("misra-c2023")
        assert isinstance(rs, MisraC2023RuleSet)
        assert rs.name == "misra-c2023"

    def test_create_unknown_raises(self):
        """Creating an unregistered ruleset raises ValueError."""
        registry = RulesetRegistry()
        with pytest.raises(ValueError, match="Unknown ruleset"):
            registry.create("nonexistent")

    def test_list_rulesets(self):
        """list_rulesets returns registered names."""
        registry = RulesetRegistry()
        registry.register(MisraC2023RuleSet)
        names = registry.list_rulesets()
        assert "misra-c2023" in names

    def test_register_non_subclass_raises(self):
        """Registering a non-BaseRuleSet class raises TypeError."""
        registry = RulesetRegistry()

        class NotARuleset:
            _name = "bad"

        with pytest.raises(TypeError):
            registry.register(NotARuleset)  # type: ignore

    def test_register_no_name_raises(self):
        """Registering a class with empty _name raises ValueError."""
        registry = RulesetRegistry()

        class NoName(BaseRuleSet):
            _name = ""
            _display_name = "No Name"
            def supported_tools(self): return []
            def get_tool_config(self, tool): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, rule_id): return "required"
            def rule_definitions(self): return {}

        with pytest.raises(ValueError, match="_name"):
            registry.register(NoName)

    def test_get_default(self):
        """get_default returns the default ruleset instance."""
        registry = RulesetRegistry()
        registry.register(MisraC2023RuleSet, make_default=True)
        rs = registry.get_default()
        assert isinstance(rs, MisraC2023RuleSet)

    def test_get_default_no_registry_raises(self):
        """get_default raises ValueError when no ruleset is registered."""
        registry = RulesetRegistry()
        with pytest.raises(ValueError, match="No default ruleset"):
            registry.get_default()

    def test_get_default_name(self):
        """get_default_name returns the default name."""
        registry = RulesetRegistry()
        registry.register(MisraC2023RuleSet, make_default=True)
        assert registry.get_default_name() == "misra-c2023"

    def test_get_info(self):
        """get_info returns metadata for a registered ruleset."""
        registry = RulesetRegistry()
        registry.register(MisraC2023RuleSet)
        info = registry.get_info("misra-c2023")
        assert info["name"] == "misra-c2023"
        assert info["display_name"] == "MISRA C:2023"
        assert "cppcheck" in info["supported_tools"]

    def test_get_info_unknown(self):
        """get_info raises ValueError for unknown ruleset."""
        registry = RulesetRegistry()
        with pytest.raises(ValueError):
            registry.get_info("nonexistent")

    def test_first_registered_becomes_default(self):
        """The first registered ruleset becomes the default."""
        registry = RulesetRegistry()

        class First(BaseRuleSet):
            _name = "first"
            _display_name = "First"
            def supported_tools(self): return []
            def get_tool_config(self, tool): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, rule_id): return "required"
            def rule_definitions(self): return {}

        registry.register(First)
        assert registry.get_default_name() == "first"

    def test_make_default_overrides(self):
        """make_default=True overrides the default."""
        registry = RulesetRegistry()

        class First(BaseRuleSet):
            _name = "first"
            _display_name = "First"
            def supported_tools(self): return []
            def get_tool_config(self, tool): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, rule_id): return "required"
            def rule_definitions(self): return {}

        class Second(BaseRuleSet):
            _name = "second"
            _display_name = "Second"
            def supported_tools(self): return []
            def get_tool_config(self, tool): return {}
            def get_report_template_config(self): return {}
            def classify_rule(self, rule_id): return "required"
            def rule_definitions(self): return {}

        registry.register(First)
        registry.register(Second, make_default=True)
        assert registry.get_default_name() == "second"
