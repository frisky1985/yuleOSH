#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
"""
Tests for yuleOSH Preview — Config Recommender.

Covers all framework branches, safety-critical gates, and edge cases.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.preview.config_recommender import _recommend_template


# ══════════════════════════════════════════════════════════════════════════════
# Framework detection
# ══════════════════════════════════════════════════════════════════════════════


class TestRecommendTemplate:
    """Comprehensive tests for _recommend_template."""

    def test_no_frameworks(self):
        """GIVEN no frameworks detected WHEN _recommend_template THEN returns generic-embedded-c."""
        result = _recommend_template([], {}, [])
        assert result["recommended_template"] == "generic-embedded-c"
        assert len(result["steps"]) >= 7

    def test_freertos(self):
        """GIVEN FreeRTOS framework WHEN _recommend_template THEN returns freertos-misra."""
        frameworks = [{"name": "FreeRTOS", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "freertos-misra"

    def test_zephyr(self):
        """GIVEN Zephyr framework WHEN _recommend_template THEN returns zephyr-rtos."""
        frameworks = [{"name": "Zephyr", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "zephyr-rtos"

    def test_autosar(self):
        """GIVEN AUTOSAR framework WHEN _recommend_template THEN returns autosar-classic."""
        frameworks = [{"name": "AUTOSAR", "detected": True, "matched_patterns": 1, "sample_files": ["Rte.h"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "autosar-classic"

    def test_stm32_hal(self):
        """GIVEN STM32 HAL framework WHEN _recommend_template THEN returns stm32-hal."""
        frameworks = [{"name": "STM32 HAL", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "stm32-hal"

    def test_esp_idf(self):
        """GIVEN ESP-IDF framework WHEN _recommend_template THEN returns esp32-idf."""
        frameworks = [{"name": "ESP-IDF", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "esp32-idf"

    def test_arm_cmsis(self):
        """GIVEN ARM CMSIS framework WHEN _recommend_template THEN returns arm-cmsis."""
        frameworks = [{"name": "ARM CMSIS", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "arm-cmsis"

    def test_linux_kernel(self):
        """GIVEN Linux Kernel framework WHEN _recommend_template THEN returns generic-embedded-c."""
        frameworks = [{"name": "Linux Kernel", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        assert result["recommended_template"] == "generic-embedded-c"

    # ── Safety-critical gates ───────────────────────────────────────────

    def test_dynamic_memory_triggers_safety_gates(self):
        """GIVEN dynamic memory risk WHEN _recommend_template THEN adds MISRA + Safety Review steps."""
        risks = [{
            "risk_level": "high",
            "description": "Dynamic memory allocation detected (5 malloc/free calls)",
            "occurrences": 5,
        }]
        result = _recommend_template([], {}, risks)
        step_names = [s["name"] for s in result["steps"]]
        assert "MISRA Static Analysis" in step_names
        assert "Safety Review" in step_names

    def test_recursion_triggers_safety_gates(self):
        """GIVEN recursion risk WHEN _recommend_template THEN adds MISRA + Safety Review steps."""
        risks = [{
            "risk_level": "medium",
            "description": "Recursive function calls detected (2 instances)",
            "occurrences": 2,
        }]
        result = _recommend_template([], {}, risks)
        step_names = [s["name"] for s in result["steps"]]
        assert "MISRA Static Analysis" in step_names
        assert "Safety Review" in step_names

    def test_long_function_triggers_safety_gates(self):
        """GIVEN max_function_lines > 100 WHEN _recommend_template THEN adds safety gates."""
        complexity = {"max_function_lines": 150}
        result = _recommend_template([], complexity, [])
        step_names = [s["name"] for s in result["steps"]]
        assert "MISRA Static Analysis" in step_names
        assert "Safety Review" in step_names

    def test_combined_risks(self):
        """GIVEN dynamic memory + recursion WHEN _recommend_template THEN adds safety gates once."""
        risks = [
            {"description": "Dynamic memory allocation detected (5 malloc/free calls)"},
            {"description": "Recursive function calls detected (2 instances)"},
        ]
        result = _recommend_template([], {}, risks)
        step_names = [s["name"] for s in result["steps"]]
        # Should only appear once despite two triggers
        assert step_names.count("MISRA Static Analysis") == 1

    def test_no_risks_no_long_functions(self):
        """GIVEN no risks and short functions WHEN _recommend_template THEN skips safety gates."""
        result = _recommend_template([], {"max_function_lines": 20}, [])
        step_names = [s["name"] for s in result["steps"]]
        assert "MISRA Static Analysis" not in step_names
        assert "Safety Review" not in step_names

    # ── Output structure ────────────────────────────────────────────────

    def test_output_structure(self):
        """GIVEN valid inputs WHEN _recommend_template THEN returns correct structure."""
        result = _recommend_template([], {}, [])
        assert "recommended_template" in result
        assert "steps" in result
        assert "ci_layers" in result
        assert "review_gates" in result
        assert "yaml_snippet" in result

    def test_review_gates(self):
        """GIVEN valid inputs WHEN _recommend_template THEN includes review gates."""
        result = _recommend_template([], {}, [])
        assert len(result["review_gates"]) == 2
        assert result["review_gates"][0]["type"] == "internal"
        assert result["review_gates"][1]["type"] == "compliance"

    def test_ci_layers(self):
        """GIVEN valid inputs WHEN _recommend_template THEN includes L1 and L2."""
        result = _recommend_template([], {}, [])
        assert result["ci_layers"]["L1"]["unit_test"] is True
        assert result["ci_layers"]["L2"]["cross_compile"] is True

    def test_cross_compile_step_with_framework(self):
        """GIVEN frameworks present WHEN _recommend_template THEN adds cross-compile step."""
        frameworks = [{"name": "FreeRTOS", "detected": True, "matched_patterns": 1, "sample_files": ["main.c"]}]
        result = _recommend_template(frameworks, {}, [])
        step_names = [s["name"] for s in result["steps"]]
        assert any("Cross-Compile" in s for s in step_names)

    def test_yaml_snippet_generated(self):
        """GIVEN any inputs WHEN _recommend_template THEN yaml_snippet is non-empty."""
        result = _recommend_template([], {}, [])
        assert "pipeline config" in result["yaml_snippet"]
        assert "ci_layers" in result["yaml_snippet"]

    def test_yaml_snippet_contains_template_name(self):
        """GIVEN specific framework WHEN _recommend_template THEN yaml includes template name."""
        frameworks = [{"name": "AUTOSAR", "detected": True, "matched_patterns": 1, "sample_files": ["Rte.h"]}]
        result = _recommend_template(frameworks, {}, [])
        assert "autosar-classic" in result["yaml_snippet"]
