
# @tests src/yuleosh/codegen/engine.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for LLM determinism constraints (Q4-d).

Verifies that code_generation task type always uses temperature=0.0 and
seed=42, while other task types retain temperature=0.3 / seed=None.
"""

import pytest

from yuleosh.llm.client import resolve_config


def _config(task_type: str):
    """Resolve LLMConfig with config=None for a given task_type."""
    return resolve_config(
        prompt="test prompt",
        system_prompt=None,
        task_type=task_type,
        config=None,
    )


class TestCodegenDeterminism:

    def test_code_generation_temperature_is_zero(self):
        """code_generation task must use temperature=0.0 for determinism."""
        config = _config("code_generation")
        assert config.temperature == 0.0, (
            f"Expected temperature=0.0 for code_generation, got {config.temperature}"
        )

    def test_code_generation_seed_is_42(self):
        """code_generation task must use seed=42 for reproducibility."""
        config = _config("code_generation")
        assert config.seed == 42, (
            f"Expected seed=42 for code_generation, got {config.seed}"
        )

    def test_non_codegen_task_keeps_temperature_03(self):
        """Non-codegen tasks keep temperature=0.3 (creativity preserved)."""
        for task_type in ("code_review", "test_generation", "simple_summary"):
            config = _config(task_type)
            assert config.temperature == pytest.approx(0.3), (
                f"Expected temperature=0.3 for {task_type}, got {config.temperature}"
            )

    def test_non_codegen_task_seed_is_none(self):
        """Non-codegen tasks do not pin seed (no determinism constraint)."""
        for task_type in ("code_review", "test_generation", "simple_summary"):
            config = _config(task_type)
            assert config.seed is None, (
                f"Expected seed=None for {task_type}, got {config.seed}"
            )

    def test_code_generation_task_type_in_config(self):
        """Returned config must carry task_type='code_generation' field."""
        config = _config("code_generation")
        assert config.task_type == "code_generation"

    def test_same_codegen_config_is_reproducible(self):
        """Calling resolve_config twice for code_generation yields same params."""
        c1 = _config("code_generation")
        c2 = _config("code_generation")
        assert c1.temperature == c2.temperature
        assert c1.seed == c2.seed
        assert c1.model == c2.model

    def test_explicit_config_not_overridden(self):
        """When config is provided explicitly, it is used as-is (not forced to seed=42)."""
        from yuleosh.llm.providers.base import LLMConfig
        explicit = LLMConfig(temperature=0.7, seed=99, task_type="code_generation")
        result = resolve_config(
            prompt="test",
            system_prompt=None,
            task_type="code_generation",
            config=explicit,
        )
        # Explicit config should pass through unchanged
        assert result.temperature == pytest.approx(0.7)
        assert result.seed == 99

