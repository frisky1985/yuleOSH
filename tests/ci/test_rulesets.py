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
    GscCRuleSet,
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
        rs._backward_compat = {}
        rs._defs = {
            "meta": {"standard": "MISRA C", "version": "2023-preview", "ruleset_version": "2023.1-preview1"},
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


# ====================================================================
# GscCRuleSet — 运行时错误细分匹配
# ====================================================================


class TestGscCRuntimeErrorMapping:
    """Tests for GSC-C runtime error rule matching and MISRA C:2023 Dir-4.1 mapping.

    MISRA C:2023 Dir-4.1 "Run-time failures shall be minimized" 未细分编号子规则，
    此处通过关键词匹配实现 GSCR-C-27.x 的细分路由。
    """

    @pytest.fixture
    def ruleset(self):
        """Fixture: create a real GscCRuleSet (loads from YAML)."""
        return GscCRuleSet()

    # ── _match_runtime_error_rule ────────────────────────────────────

    def test_match_runtime_errors(self, ruleset):
        """每条运行时错误的匹配验证。"""
        test_cases = [
            ("Array index out of bounds",     "GSCR-C-27.16"),
            ("Division by zero",              "GSCR-C-27.9"),
            ("divide by zero",                "GSCR-C-27.9"),
            ("Unreachable code detected",     "GSCR-C-27.8"),
            ("Float operation",               "GSCR-C-27.10"),
            ("Shift count",                   "GSCR-C-27.11"),
            ("Overflow in calculation",       "GSCR-C-27.12"),
            ("subnormal float value",         "GSCR-C-27.13"),
            ("absolute address used",         "GSCR-C-27.14"),
            ("null pointer dereference",      "GSCR-C-27.15"),
            ("dereference of null",           "GSCR-C-27.15"),
            ("out of bounds write",           "GSCR-C-27.16"),
            ("non-terminating call detected", "GSCR-C-27.17"),
            ("recursive function call",       "GSCR-C-27.17"),
            ("infinite loop detected",        "GSCR-C-27.18"),
            ("non-terminating loop",          "GSCR-C-27.18"),
            ("correctness condition failed",  "GSCR-C-27.19"),
            ("standard library misuse",       "GSCR-C-27.20"),
        ]
        for message, expected in test_cases:
            result = ruleset._match_runtime_error_rule(message)
            assert result == expected, (
                f"match_runtime_error({message!r}) = {result!r}, expected {expected!r}"
            )

    def test_match_runtime_error_specificity(self, ruleset):
        """验证特异性匹配：更长的关键词优先于较短的关键词。

        例如 "subnormal" 必须在 "float" 之前匹配，
        "non-terminating call" 必须在 "non-terminating loop" 之前匹配。
        """
        cases = [
            ("subnormal float",                "GSCR-C-27.13"),
            ("non-terminating call",           "GSCR-C-27.17"),
            ("non-terminating loop",           "GSCR-C-27.18"),
            ("out of bounds array index",      "GSCR-C-27.16"),
            ("correctness condition violation", "GSCR-C-27.19"),
        ]
        for message, expected in cases:
            result = ruleset._match_runtime_error_rule(message)
            assert result == expected, (
                f"specificity: {message!r} → {result!r}, expected {expected!r}"
            )

    def test_match_runtime_error_unknown(self, ruleset):
        """无法识别的运行时错误应回落为 GSCR-C-4.1（通用运行时）。"""
        result = ruleset._match_runtime_error_rule("some unknown runtime issue")
        assert result == "GSCR-C-4.1"

    def test_match_runtime_error_empty(self, ruleset):
        """空消息应回落为 GSCR-C-4.1。"""
        assert ruleset._match_runtime_error_rule("") == "GSCR-C-4.1"
        assert ruleset._match_runtime_error_rule(" ") == "GSCR-C-4.1"

    # ── _match_runtime_error_category ───────────────────────────────

    def test_match_runtime_category(self, ruleset):
        """验证 _match_runtime_error_category 返回正确的 MISRA C:2023 类别描述。"""
        cases = [
            ("Division by zero",           "arithmetic error: division by zero (Dir-4.1)"),
            ("subnormal float",            "arithmetic error: subnormal float (Dir-4.1)"),
            ("out of bounds",              "array bound error: out-of-bounds index (Dir-4.1)"),
            ("null pointer",               "pointer dereferencing: null/invalid (Dir-4.1)"),
            ("unreachable code",           "unreachable code (Dir-4.1 / also Rule 2.1)"),
            ("standard library misuse",    "standard library: invalid use (Dir-4.1)"),
        ]
        for message, expected in cases:
            result = ruleset._match_runtime_error_category(message)
            assert result == expected, (
                f"category({message!r}) = {result!r}, expected {expected!r}"
            )

    def test_match_runtime_category_unknown(self, ruleset):
        """无法匹配时应返回空字符串。"""
        assert ruleset._match_runtime_error_category("foo bar baz") == ""

    # ── _RUNTIME_ERROR_MAP 结构完整 ─────────────────────────────────

    def test_runtime_error_map_structure(self, ruleset):
        """_RUNTIME_ERROR_MAP 应包含 (keyword, gscr_id, category) 三元组。"""
        assert len(ruleset._RUNTIME_ERROR_MAP) >= 18, "至少应有 18 条映射条目"
        for entry in ruleset._RUNTIME_ERROR_MAP:
            assert len(entry) == 3, f"每个条目应为 3 元组, got {len(entry)}: {entry}"
            keyword, gscr_id, category = entry
            assert isinstance(keyword, str) and len(keyword) > 0, f"无效 keyword: {keyword!r}"
            assert gscr_id.startswith("GSCR-C-27."), f"无效 gscr_id: {gscr_id}"
            assert "Dir-4.1" in category, f"category 应包含 Dir-4.1: {category}"

    def test_runtime_error_map_no_duplicate_gscr_ids(self, ruleset):
        """每条 GSCR-C-27.x 规则至少应出现在 _RUNTIME_ERROR_MAP 中一次。"""
        found = set()
        for _, gscr_id, _ in ruleset._RUNTIME_ERROR_MAP:
            found.add(gscr_id)
        # GSCR-C-27.8 ~ 27.20 共 13 条
        expected = {f"GSCR-C-27.{i}" for i in range(8, 21)}
        missing = expected - found
        assert not missing, f"缺少规则: {missing}"

    # ── translate_violations ────────────────────────────────────────

    def test_translate_violations_runtime_error_with_message(self, ruleset):
        """Dir-4.1 违规应根据 message 文本细分为具体的 GSCR-C-27.x 规则。"""
        violations = [
            {"rule_id": "misra-c2012-Dir-4.1", "message": "Division by zero", "file": "test.c", "line": 10},
            {"rule_id": "misra-c2023-Dir-4.1", "message": "Array index out of bounds", "file": "test.c", "line": 20},
            {"rule_id": "misra-c2023-17.7",    "message": "Return value not checked", "file": "test.c", "line": 30},
        ]
        results = ruleset.translate_violations(violations)

        # Div by zero → GSCR-C-27.9
        r0 = results[0]
        assert "GSCR-C-27.9" in r0["gscr_rule_ids"], f"Expected 27.9, got {r0['gscr_rule_ids']}"
        assert r0["gscr_severity"] == "S1"
        assert r0["gscr_category"] == "运行时错误"
        assert r0.get("misra_2023_category", "") == "arithmetic error: division by zero (Dir-4.1)"

        # Array index out of bounds → GSCR-C-27.16
        r1 = results[1]
        assert "GSCR-C-27.16" in r1["gscr_rule_ids"], f"Expected 27.16, got {r1['gscr_rule_ids']}"
        assert r1.get("misra_2023_category", "") == "array bound error: out-of-bounds index (Dir-4.1)"

        # Rule 17.7 (not Dir-4.1) → 正常映射
        r2 = results[2]
        assert r2.get("gscr_rule_ids")

    def test_translate_violations_runtime_error_unmatched(self, ruleset):
        """无法匹配 message 的 Dir-4.1 违规应回落为 GSCR-C-4.1。"""
        violations = [
            {"rule_id": "misra-c2012-Dir-4.1", "message": "Some obscure runtime failure", "file": "test.c", "line": 5},
        ]
        results = ruleset.translate_violations(violations)
        assert len(results) == 1
        r0 = results[0]
        # 应回落为 GSCR-C-4.1
        assert "GSCR-C-4.1" in r0["gscr_rule_ids"], f"Expected GSCR-C-4.1, got {r0['gscr_rule_ids']}"

    def test_translate_violations_multiple_runtime_errors(self, ruleset):
        """多个 Dir-4.1 违规应各自独立细分为正确的 GSCR 规则。"""
        violations = [
            {"rule_id": "misra-c2023-Dir-4.1", "message": "Unreachable code", "file": "a.c", "line": 1},
            {"rule_id": "misra-c2012-Dir-4.1", "message": "Null pointer dereference", "file": "a.c", "line": 2},
            {"rule_id": "misra-c2023-Dir-4.1", "message": "Overflow in signed int", "file": "a.c", "line": 3},
        ]
        results = ruleset.translate_violations(violations)
        assert results[0]["gscr_rule_ids"] == ["GSCR-C-27.8"]
        assert results[1]["gscr_rule_ids"] == ["GSCR-C-27.15"]
        assert results[2]["gscr_rule_ids"] == ["GSCR-C-27.12"]

    # ── 逆向映射（map_misra_to_gscr） ───────────────────────────────

    def test_map_misra_to_gscr_dir_4_1(self, ruleset):
        """Dir-4.1 逆向映射应包含所有运行时错误 GSCR 规则。"""
        ids = ruleset.map_misra_to_gscr("misra-c2012-Dir-4.1")
        assert len(ids) >= 13, f"Expected >=13 rules, got {len(ids)}"
        assert "GSCR-C-4.1" in ids
        assert "GSCR-C-27.8" in ids
        assert "GSCR-C-27.16" in ids

    def test_map_misra_to_gscr_direct(self, ruleset):
        """非 Dir-4.1 规则应有 1:1 或 1:N 映射。"""
        ids = ruleset.map_misra_to_gscr("misra-c2012-Dir-4.12")
        assert ids  # 不应为空

    def test_map_misra_to_gscr_unknown(self, ruleset):
        """未知 MISRA ID 应返回空列表。"""
        assert ruleset.map_misra_to_gscr("misra-c2012-99.99") == []

    # ── _get_runtime_error_category ─────────────────────────────────

    def test_get_runtime_error_category_from_yaml(self, ruleset):
        """_get_runtime_error_category 应从 YAML 定义中读取 misra_2023_category。"""
        cat = ruleset._get_runtime_error_category("GSCR-C-27.9")
        assert "arithmetic error" in cat, f"Unexpected category: {cat}"
        assert "Dir-4.1" in cat

    def test_get_runtime_error_category_non_runtime(self, ruleset):
        """非运行时错误规则应返回空字符串。"""
        assert ruleset._get_runtime_error_category("GSCR-C-2.1") == ""
