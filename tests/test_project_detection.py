"""Tests for project_detection.py — .yuleosh.yaml auto-detection."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.project_detection import detect_project, resolve_pipeline_config


class TestProjectDetection:
    """Test project type auto-detection from .yuleosh.yaml."""

    def test_no_yaml_file(self, tmp_path):
        """No .yuleosh.yaml returns None."""
        result = detect_project(str(tmp_path))
        assert result is None

    def test_invalid_yaml(self, tmp_path):
        """Invalid YAML returns None."""
        yaml_path = tmp_path / ".yuleosh.yaml"
        yaml_path.write_text("{{invalid: yaml: broken")
        result = detect_project(str(tmp_path))
        assert result is None

    def test_empty_yaml(self, tmp_path):
        """Empty YAML returns None."""
        yaml_path = tmp_path / ".yuleosh.yaml"
        yaml_path.write_text("")
        result = detect_project(str(tmp_path))
        assert result is None

    def test_autosar_project(self, tmp_path):
        """yuleASR autosar project is correctly detected."""
        content = """\
project:
  name: yuleASR-BSW
  type: autosar
  language: c
  target: s32k312

pipeline:
  template: autosar
  ci_layers:
    L1: [spec-parse, plan-lint, unit-test, misra-check]
    L2: [cross-compile, qemu-run, static-analysis, c-coverage-gate]
    L3: [system-verification, compliance-report, evidence-pack]

cross_compile:
  target: arm-cortex-m7
  toolchain_prefix: arm-none-eabi-
  arch_flags: [-mcpu=cortex-m7, -mthumb, -mfpu=fpv5-sp-d16, -mfloat-abi=hard]
  linker_script: src/platform/s32k312/linker/s32k312.ld

misra:
  ruleset: c2023
  fail_on_error: true
  exclude_paths: [tests/**, third_party/**]

coverage:
  c_fail_under: 70
"""
        yaml_path = tmp_path / ".yuleosh.yaml"
        yaml_path.write_text(content)

        result = detect_project(str(tmp_path))
        assert result is not None
        assert result["name"] == "yuleASR-BSW"
        assert result["type"] == "autosar"
        assert result["language"] == "c"
        assert result["target"] == "s32k312"
        assert result["pipeline_template"] == "autosar"

        # Check ci_layers
        layers = result["ci_layers"]
        assert isinstance(layers, dict)
        assert "L1" in layers
        assert "L2" in layers
        assert layers["L2"] == [
            "cross-compile", "qemu-run", "static-analysis", "c-coverage-gate"
        ]

        # Check cross_compile
        cross = result["cross_compile"]
        assert cross["target"] == "arm-cortex-m7"

        # Check coverage
        coverage = result["coverage"]
        assert coverage["c_fail_under"] == 70

        # Check misra
        misra = result["misra"]
        assert misra["ruleset"] == "c2023"
        assert misra["fail_on_error"] is True

    def test_unknown_type(self, tmp_path):
        """Unknown project type returns basic info."""
        content = """\
project:
  name: test-project
  type: unknown-type
  language: python
"""
        yaml_path = tmp_path / ".yuleosh.yaml"
        yaml_path.write_text(content)

        result = detect_project(str(tmp_path))
        assert result is not None
        assert result["name"] == "test-project"
        assert result["type"] == "unknown-type"
        assert result["pipeline_template"] == ""  # no mapping

    def test_resolve_pipeline_config_no_yaml(self, tmp_path):
        """resolve_pipeline_config returns None if no .yuleosh.yaml."""
        result = resolve_pipeline_config(str(tmp_path))
        assert result is None
