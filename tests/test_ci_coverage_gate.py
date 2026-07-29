#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests for ci/runner.py — check_coverage_gate()
"""

import json
import tempfile
from pathlib import Path

from yuleosh.ci.runner import (
    check_coverage_gate,
    _compute_module_coverage,
)


class TestCoverageGate:
    """Coverage-boosting tests for ci/runner coverage gate."""

    def test_no_coverage_data_passes(self):
        """No coverage data → gate passes with a warning."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = tmp
            # No ci-config.yaml — defaults will be used
            passed, messages = check_coverage_gate(project_dir, coverage_data=None)
            assert passed is True

    def test_coverage_above_threshold_passes(self):
        """Coverage above global threshold passes."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            # Write a ci-config.yaml with strict:true and high threshold
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("coverage:\n  threshold_line: 50.0\n  threshold_condition: 50.0\n  strict: true\n")
            data = {"line_rate": 80.0, "branch_rate": 70.0, "files": []}
            passed, messages = check_coverage_gate(str(project_dir), data)
            assert passed is True

    def test_coverage_below_threshold_strict_fails(self):
        """Coverage below threshold with strict:true fails."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("coverage:\n  threshold_line: 80.0\n  threshold_condition: 80.0\n  strict: true\n")
            data = {"line_rate": 50.0, "branch_rate": 40.0, "files": []}
            passed, messages = check_coverage_gate(str(project_dir), data)
            assert passed is False

    def test_coverage_below_threshold_non_strict_warns(self):
        """Coverage below threshold with strict:false warns but passes."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("coverage:\n  threshold_line: 80.0\n  threshold_condition: 80.0\n  strict: false\n")
            data = {"line_rate": 30.0, "branch_rate": 20.0, "files": []}
            passed, messages = check_coverage_gate(str(project_dir), data)
            assert passed is True
            assert any("advisory-only" in msg for msg in messages)

    def test_override_strict_bypasses(self):
        """--override-strict bypasses strict mode blocking."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("coverage:\n  threshold_line: 80.0\n  threshold_condition: 80.0\n  strict: true\n")
            data = {"line_rate": 30.0, "branch_rate": 20.0, "files": []}
            passed, messages = check_coverage_gate(str(project_dir), data, override_strict=True)
            assert passed is True

    def test_module_threshold_check(self):
        """Module-level threshold check works."""
        files = [
            {"file": "src/core/main.c", "line_rate": 0.5, "branch_rate": 0.5,
             "lines": {"found": 100, "hit": 30}, "functions": {"found": 5, "hit": 2}},
            {"file": "src/core/utils.c", "line_rate": 0.8, "branch_rate": 0.7,
             "lines": {"found": 50, "hit": 40}, "functions": {"found": 3, "hit": 3}},
        ]
        cov = _compute_module_coverage(files, "src/core")
        # 30+40=70 hit / 100+50=150 found = 46.67%
        assert cov is not None
        assert abs(cov - 46.67) < 0.1

    def test_module_threshold_no_match(self):
        """Module with no matching files returns None."""
        files = [{"file": "other/file.c", "lines": {"found": 10, "hit": 5}}]
        cov = _compute_module_coverage(files, "src/core")
        assert cov is None

    def test_module_threshold_zero_found(self):
        """Module with zero found lines returns None."""
        files = [{"file": "src/core/empty.c", "lines": {"found": 0, "hit": 0}}]
        cov = _compute_module_coverage(files, "src/core")
        assert cov is None

    def test_low_threshold_warning(self):
        """threshold_line below 50 emits a warning."""
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            ci_cfg = project_dir / ".yuleosh" / "ci-config.yaml"
            ci_cfg.parent.mkdir(parents=True)
            ci_cfg.write_text("coverage:\n  threshold_line: 5.0\n  threshold_condition: 5.0\n  strict: false\n")
            data = {"line_rate": 50.0, "branch_rate": 50.0, "files": []}
            passed, messages = check_coverage_gate(str(project_dir), data)
            assert any("recommended minimum" in msg for msg in messages)
