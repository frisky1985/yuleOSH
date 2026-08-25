#!/usr/bin/env python3

# @tests src/yuleosh/ci/run.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests for ci/config.py — default threshold, strict mode, parsing.
"""

import tempfile
from pathlib import Path

from yuleosh.ci.config import (
    load_ci_config,
    CoverageConfig,
    DEFAULT_COVERAGE_THRESHOLD_LINE,
    DEFAULT_COVERAGE_THRESHOLD_COND,
    DEFAULT_STRICT,
)


class TestCiConfigDefaults:
    """Coverage-boosting tests for ci/config defaults."""

    def test_default_threshold_line_is_50(self):
        """Default threshold_line is now 50 (was 5)."""
        assert DEFAULT_COVERAGE_THRESHOLD_LINE == 50.0

    def test_default_threshold_cond_is_50(self):
        """Default threshold_condition is now 50 (was 5)."""
        assert DEFAULT_COVERAGE_THRESHOLD_COND == 50.0

    def test_default_strict_is_true(self):
        """Default strict is now True (was False)."""
        assert DEFAULT_STRICT is True

    def test_load_ci_config_no_file_uses_defaults(self):
        """No config file returns config with new defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_ci_config(tmp)
            assert cfg.coverage.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE
            assert cfg.coverage.threshold_condition == DEFAULT_COVERAGE_THRESHOLD_COND
            assert cfg.coverage.strict == DEFAULT_STRICT

    def test_load_ci_config_with_custom_values(self):
        """Custom values in config override defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("""
coverage:
  threshold_line: 80.0
  threshold_condition: 60.0
  strict: false
  module_thresholds:
    src/core: 90.0
""")
            cfg = load_ci_config(str(project_dir))
            assert cfg.coverage.threshold_line == 80.0
            assert cfg.coverage.threshold_condition == 60.0
            assert cfg.coverage.strict is False
            assert cfg.coverage.module_thresholds["src/core"] == 90.0
