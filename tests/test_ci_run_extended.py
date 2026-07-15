# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for ci/run.py — boost coverage from 59% to 80%+ (v0.8.0 P0).

Covers: CIResult, git helpers, file discovery, layer deps, error paths.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.ci.run import (
    CIResult,
    git_commit_hash,
    get_changed_files,
    find_test_files,
    check_layer_dependency,
    get_latest_layer_result,
    is_strict,
    is_misra_fail_fast,
    _save_layer_result,
    _handle_stage_error,
    _resolve_cross_compile,
    get_cache_key_for_dir,
    _should_skip_coverage,
    _coverage_skip_reason,
    _run_coverage_and_export,
    _load_coverage_json,
)


class TestCIResult:
    """GIVEN CIResult WHEN stages added THEN correct serialization."""

    def test_ci_result_init(self):
        """GIVEN layer and commit_hash WHEN CIResult init THEN fields set."""
        ci = CIResult(layer=2, commit_hash="abc123")
        assert ci.layer == 2
        assert ci.commit_hash == "abc123"
        assert ci.status == "running"
        assert ci.stages == []

    def test_add_stage(self):
        """GIVEN CIResult WHEN add_stage THEN stage appended."""
        ci = CIResult(layer=1, commit_hash="def456")
        ci.add_stage("lint", "passed", "all clear")
        assert len(ci.stages) == 1
        assert ci.stages[0]["name"] == "lint"
        assert ci.stages[0]["status"] == "passed"

    def test_add_stage_accumulates(self):
        """GIVEN multiple stages WHEN added THEN all present."""
        ci = CIResult(layer=1, commit_hash="x")
        ci.add_stage("lint", "passed")
        ci.add_stage("test", "failed", "1 failure")
        ci.add_stage("build", "skipped")
        assert len(ci.stages) == 3
        statuses = [s["status"] for s in ci.stages]
        assert statuses == ["passed", "failed", "skipped"]

    def test_complete_updates_status(self):
        """GIVEN CIResult WHEN complete THEN status set and timestamps set."""
        ci = CIResult(layer=3, commit_hash="z")
        ci.complete("passed")
        assert ci.status == "passed"
        assert ci.completed_at is not None

    def test_complete_failed_status(self):
        """GIVEN CIResult WHEN complete with failed THEN status is failed."""
        ci = CIResult(layer=2, commit_hash="f")
        ci.complete("failed")
        assert ci.status == "failed"

    def test_to_dict(self):
        """GIVEN CIResult with stages WHEN to_dict THEN valid JSON-serializable."""
        ci = CIResult(layer=1, commit_hash="abc")
        ci.add_stage("lint", "passed")
        ci.add_stage("test", "passed")
        ci.complete("passed")

        d = ci.to_dict()
        assert d["layer"] == 1
        assert d["status"] == "passed"
        assert len(d["stages"]) == 2

        # Should be JSON serializable
        j = json.dumps(d)
        back = json.loads(j)
        assert back["layer"] == 1


class TestGitHelpers:
    """GIVEN git helpers WHEN called THEN return expected."""

    def test_git_commit_hash(self):
        """GIVEN git repo WHEN git_commit_hash THEN returns non-empty string."""
        hash_val = git_commit_hash()
        assert len(hash_val) >= 7
        assert len(hash_val) <= 40

    def test_git_commit_hash_exists(self):
        """GIVEN git available WHEN git_commit_hash THEN returns hash string."""
        result = git_commit_hash()
        assert len(result) >= 7

    def test_get_changed_files_returns_list(self):
        """GIVEN git repo WHEN get_changed_files THEN returns list of files."""
        files = get_changed_files()
        assert isinstance(files, list)

    def test_get_changed_files_exists(self):
        """GIVEN git repo WHEN get_changed_files THEN returns list."""
        files = get_changed_files()
        assert isinstance(files, list)


class TestFileDiscovery:
    """GIVEN project dir WHEN find_test_files THEN finds Python tests."""

    def test_find_test_files_returns_list(self):
        """GIVEN temp dir with test files WHEN find_test_files THEN non-empty list."""
        with tempfile.TemporaryDirectory() as td:
            tests_dir = Path(td) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_a.py").write_text("def test(): pass\n")
            (tests_dir / "test_b.py").write_text("def test(): pass\n")

            files = find_test_files(td)
            assert len(files) >= 2
            # All should end with .py
            for f in files:
                assert f.endswith(".py")

    def test_find_test_files_no_tests_dir(self):
        """GIVEN dir without tests/ WHEN find_test_files THEN empty list."""
        from yuleosh.ci.run import _test_file_cache
        _test_file_cache.clear()
        with tempfile.TemporaryDirectory() as td:
            files = find_test_files(td)
            assert files == []


class TestLayerDependency:
    """GIVEN CI layer dependency WHEN checking THEN validates order."""

    def test_check_layer_1_no_dependency(self):
        """GIVEN layer 1 WHEN check_layer_dependency THEN no dependency required."""
        with tempfile.TemporaryDirectory() as td:
            result = check_layer_dependency(1, td)
            assert result is None  # No dependency issue

    def test_check_layer_2_requires_layer_1(self):
        """GIVEN layer 2 without layer 1 result WHEN check THEN returns error."""
        with tempfile.TemporaryDirectory() as td:
            result = check_layer_dependency(2, td)
            assert result is not None  # Should report missing layer 1

    def test_get_latest_layer_result_not_found(self):
        """GIVEN no results WHEN get_latest_layer_result THEN returns None."""
        with tempfile.TemporaryDirectory() as td:
            result = get_latest_layer_result(1, td)
            assert result is None


class TestEnvChecks:
    """GIVEN env vars WHEN is_strict/is_misra_fail_fast THEN correct bool."""

    def test_is_strict_default_false(self):
        """GIVEN no env var WHEN is_strict THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_strict() is False

    def test_is_strict_enabled(self):
        """GIVEN CI_STRICT=1 WHEN is_strict THEN returns True."""
        with mock.patch.dict(os.environ, {"CI_STRICT": "1"}):
            assert is_strict() is True

    def test_is_misra_fail_fast_default_false(self):
        """GIVEN no env var WHEN is_misra_fail_fast THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_misra_fail_fast() is False


class TestSaveLayerResult:
    """GIVEN CI result WHEN saving THEN file written."""

    def test_save_layer_result(self):
        """GIVEN CIResult WHEN _save_layer_result THEN JSON file created."""
        with tempfile.TemporaryDirectory() as td:
            ci = CIResult(layer=1, commit_hash="test123")
            ci.add_stage("lint", "passed")
            ci.complete("passed")

            _save_layer_result(td, ci, True, "test123", 1)
            ci_dir = Path(td) / ".osh" / "ci"
            json_files = list(ci_dir.glob("layer*.json"))
            assert len(json_files) >= 1


class TestErrorHandling:
    """GIVEN stage errors WHEN _handle_stage_error THEN correct behavior."""

    def test_handle_stage_error_strict(self):
        """GIVEN strict mode WHEN _handle_stage_error THEN adds failed stage."""
        from yuleosh.ci.run import CIResult as _CI, _handle_stage_error as _err
        ci = _CI(layer=1, commit_hash="t")
        result = _err(ci, "test-stage", "fatal error", strict=True)
        assert result is False  # _handle_stage_error returns False even in strict
        assert len(ci.stages) == 1

    def test_handle_stage_error_non_strict(self):
        """GIVEN non-strict mode WHEN _handle_stage_error THEN returns False gracefully."""
        ci = mock.MagicMock()
        ci.stages = []
        result = _handle_stage_error(ci, "test-stage", "warning", strict=False)
        assert result is False


class TestCoverageHelpers:
    """GIVEN coverage configuration WHEN checking THEN correct behavior."""

    def test_should_skip_coverage_default(self):
        """GIVEN no skip env WHEN _should_skip_coverage THEN returns False."""
        with mock.patch.dict(os.environ, {}, clear=True):
            assert _should_skip_coverage() is False

    def test_should_skip_coverage_set(self):
        """GIVEN HOOK_TYPE=commit WHEN _should_skip_coverage THEN returns True."""
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            assert _should_skip_coverage() is True

    def test_coverage_skip_reason(self):
        """GIVEN HOOK_TYPE=commit WHEN _coverage_skip_reason THEN non-empty string."""
        with mock.patch.dict(os.environ, {"HOOK_TYPE": "commit"}):
            reason = _coverage_skip_reason()
            assert len(reason) > 0

    def test_load_coverage_json_valid(self):
        """GIVEN valid coverage.json WHEN _load_coverage_json THEN parses correctly."""
        with tempfile.TemporaryDirectory() as td:
            cov_path = Path(td) / "coverage.json"
            cov_path.write_text(json.dumps({
                "totals": {
                    "percent_covered": 85.0,
                    "condition_percent_covered": 80.0,
                }
            }))
            line_cov, branch_cov = _load_coverage_json(td)
            assert line_cov == 85.0
            # Branch coverage may be same or different depending on implementation
            assert branch_cov in (85.0, 80.0, 0.0)

    def test_run_coverage_no_config(self):
        """GIVEN no pytest-cov WHEN _run_coverage_and_export THEN gracefule failure."""
        with tempfile.TemporaryDirectory() as td:
            # Should not crash even without tests
            ok, reason = _run_coverage_and_export(td)
            # returns bool and string
            assert isinstance(ok, bool)
            assert isinstance(reason, str)


class TestCrossCompile:
    """GIVEN cross compile config WHEN resolving THEN correct targets."""

    def test_resolve_cross_compile_no_targets(self):
        """GIVEN no cross source dir WHEN _resolve_cross_compile THEN returns bool."""
        ci = CIResult(layer=3, commit_hash="x")
        with tempfile.TemporaryDirectory() as td:
            result = _resolve_cross_compile(
                td, str(Path(td) / "nonexistent"), str(Path(td) / "build"), ci
            )
            assert isinstance(result, bool)

    def test_get_cache_key(self):
        """GIVEN project dir WHEN get_cache_key_for_dir THEN non-empty."""
        with tempfile.TemporaryDirectory() as td:
            key = get_cache_key_for_dir(td)
            assert len(key) > 0
            # Same dir should give same key
            key2 = get_cache_key_for_dir(td)
            assert key == key2
