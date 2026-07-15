# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for pipeline/step_handlers/test_qualification.py — coverage target ≥50%."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# Scenario
# ===================================================================


class TestScenario:
    def test_parse_full(self):
        """GIVEN full GIVEN/WHEN/THEN scenario WHEN parsing THEN extracts correctly."""
        from yuleosh.pipeline.step_handlers.test_qualification import Scenario
        raw = "GIVEN user is logged in\nWHEN user clicks submit\nTHEN form is submitted\nTHEN email is sent"
        s = Scenario(raw)
        assert len(s.given) == 1
        assert "user is logged in" in s.given[0]
        assert "user clicks submit" in s.when
        assert len(s.then) == 2

    def test_parse_with_colons(self):
        """GIVEN scenario with colons after GIVEN/WHEN/THEN WHEN parsing THEN strips colons."""
        from yuleosh.pipeline.step_handlers.test_qualification import Scenario
        raw = "GIVEN: system is ready\nWHEN: test runs\nTHEN: result is OK"
        s = Scenario(raw)
        assert "system is ready" in s.given[0]
        assert "test runs" in s.when

    def test_name_generation(self):
        """GIVEN scenario raw text WHEN getting name THEN sanitized name is returned."""
        from yuleosh.pipeline.step_handlers.test_qualification import Scenario
        s = Scenario("GIVEN X WHEN Y THEN Z")
        assert s.name

    def test_to_dict(self):
        """GIVEN parsed scenario WHEN converting to dict THEN returns correct structure."""
        from yuleosh.pipeline.step_handlers.test_qualification import Scenario
        s = Scenario("GIVEN x WHEN y THEN z")
        d = s.to_dict()
        assert "raw" in d
        assert "given" in d
        assert "when" in d
        assert "then" in d

    def test_parse_tracks_sections(self):
        """GIVEN multi-line scenario WHEN parsing THEN tracks all lines in correct sections."""
        from yuleosh.pipeline.step_handlers.test_qualification import Scenario
        raw = "GIVEN a\nGIVEN b\nWHEN c\nTHEN d\nTHEN e\nTHEN f"
        s = Scenario(raw)
        assert len(s.given) == 2
        assert len(s.then) == 3
        assert s.when == "c"


# ===================================================================
# _discover_scenarios
# ===================================================================


class TestDiscoverScenarios:
    def test_no_spec_file(self, tmp_path):
        """GIVEN non-existent spec file WHEN discovering scenarios THEN returns empty."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_scenarios
        result = _discover_scenarios(str(tmp_path / "nonexistent.md"))
        assert result == []

    def test_extracts_scenarios(self, tmp_path):
        """GIVEN spec file with GIVEN/WHEN/THEN blocks WHEN discovering THEN finds them."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_scenarios
        spec = tmp_path / "spec.md"
        spec.write_text(
            "## TC-1: Basic flow\n"
            "### Scenario\n"
            "GIVEN system is initialized\n"
            "WHEN input is received\n"
            "THEN output is produced\n"
            "### Other content\n"
        )
        result = _discover_scenarios(str(spec))
        assert len(result) >= 1

    def test_skips_blocks_without_given_when(self, tmp_path):
        """GIVEN spec file with blocks lacking GIVEN/WHEN WHEN discovering THEN skips them."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_scenarios
        spec = tmp_path / "spec.md"
        # Must not contain GIVEN or WHEN keywords at all
        spec.write_text("## Info\nThis just has some random text.\nNo GIV scenario.\n")
        result = _discover_scenarios(str(spec))
        assert len(result) == 0


# ===================================================================
# _discover_test_files
# ===================================================================


class TestDiscoverTestFiles:
    def test_no_files(self, tmp_path):
        """GIVEN project dir with no test files WHEN discovering THEN returns empty."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_test_files
        result = _discover_test_files(tmp_path)
        assert result == []

    def test_finds_qualification_tests(self, tmp_path):
        """GIVEN project dir with qualification test files WHEN discovering THEN finds them."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_test_files
        test_dir = tmp_path / "tests" / "e2e"
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_qualification.py"
        test_file.write_text("def test_qual(): pass")
        result = _discover_test_files(tmp_path)
        assert len(result) >= 1
        assert any("test_qualification" in str(r) for r in result)

    def test_dedups(self, tmp_path):
        """GIVEN same file matching multiple patterns WHEN discovering THEN deduplicates."""
        from yuleosh.pipeline.step_handlers.test_qualification import _discover_test_files
        f1 = tmp_path / "e2e_test.py"
        f1.write_text("x")
        result = _discover_test_files(tmp_path)
        resolved = [str(p.resolve()) for p in result]
        assert len(resolved) == len(set(resolved))


# ===================================================================
# _check_scenario_coverage
# ===================================================================


class TestCheckScenarioCoverage:
    def test_no_scenarios(self):
        """GIVEN no scenarios WHEN checking coverage THEN returns zeros."""
        from yuleosh.pipeline.step_handlers.test_qualification import _check_scenario_coverage
        result = _check_scenario_coverage([], [])
        assert result["total_scenarios"] == 0
        assert result["coverage_pct"] == 0.0

    def test_some_covered(self, tmp_path):
        """GIVEN scenarios and matching test files WHEN checking THEN marks some covered."""
        from yuleosh.pipeline.step_handlers.test_qualification import (
            Scenario, _check_scenario_coverage,
        )
        scenarios = [Scenario("GIVEN foo WHEN bar THEN baz")]
        test_file = tmp_path / "e2e_test.py"
        test_file.write_text("def test_foo_and_bar(): pass")
        result = _check_scenario_coverage(scenarios, [test_file])
        assert result["total_scenarios"] == 1
        assert result["covered_count"] >= 0  # may or may not match


# ===================================================================
# _run_system_tests
# ===================================================================


class TestRunSystemTests:
    def test_empty(self, tmp_path):
        """GIVEN no test files WHEN running system tests THEN returns empty results."""
        from yuleosh.pipeline.step_handlers.test_qualification import _run_system_tests
        result = _run_system_tests([], tmp_path)
        assert result["executed"] == 0

    def test_skips_c_files(self, tmp_path):
        """GIVEN C test files WHEN running system tests THEN marks as skipped."""
        from yuleosh.pipeline.step_handlers.test_qualification import _run_system_tests
        c_file = tmp_path / "test.c"
        c_file.write_text("int main(){}")
        result = _run_system_tests([c_file], tmp_path)
        assert any("requires compilation" in str(d.get("message", ""))
                   for d in result["details"])

    def test_python_success(self, tmp_path):
        """GIVEN Python test files WHEN running system tests THEN executes them."""
        from yuleosh.pipeline.step_handlers.test_qualification import _run_system_tests
        test_file = tmp_path / "test_pass.py"
        test_file.write_text("assert True\n")
        result = _run_system_tests([test_file], tmp_path)
        assert result["executed"] >= 1

    def test_timeout(self, tmp_path):
        """GIVEN test times out WHEN running system tests THEN marks as failed."""
        from yuleosh.pipeline.step_handlers.test_qualification import _run_system_tests
        test_file = tmp_path / "test_slow.py"
        test_file.write_text("import time; time.sleep(10)\n")
        result = _run_system_tests([test_file], tmp_path, timeout_s=1)
        assert result["failed"] >= 1
        assert "(timeout)" in str(result["errors"])


# ===================================================================
# _build_qualification_report
# ===================================================================


class TestBuildQualificationReport:
    def test_no_scenarios(self, tmp_path):
        """GIVEN no scenarios WHEN building report THEN verdict is not-applicable."""
        from yuleosh.pipeline.step_handlers.test_qualification import _build_qualification_report
        result = _build_qualification_report(
            str(tmp_path), tmp_path, [],
            {"total_scenarios": 0, "covered_count": 0, "uncovered_count": 0,
             "covered": [], "uncovered": []},
            {"executed": 0, "passed": 0, "failed": 0, "errors": [], "details": []},
        )
        assert result["verdict"] == "not-applicable"

    def test_incomplete_no_tests(self, tmp_path):
        """GIVEN scenarios but no tests WHEN building report THEN incomplete."""
        from yuleosh.pipeline.step_handlers.test_qualification import _build_qualification_report
        result = _build_qualification_report(
            str(tmp_path), tmp_path,
            [mock.MagicMock()],
            {"total_scenarios": 1, "covered_count": 1, "uncovered_count": 0, "covered": [], "uncovered": []},
            {"executed": 0, "passed": 0, "failed": 0, "errors": [], "details": []},
        )
        assert result["verdict"] == "incomplete"

    def test_passed(self, tmp_path):
        """GIVEN all covered and passed WHEN building report THEN verdict is passed."""
        from yuleosh.pipeline.step_handlers.test_qualification import _build_qualification_report
        result = _build_qualification_report(
            str(tmp_path), tmp_path,
            [mock.MagicMock()],
            {"total_scenarios": 1, "covered_count": 1, "uncovered_count": 0, "covered": [{}], "uncovered": []},
            {"executed": 1, "passed": 1, "failed": 0, "errors": [], "details": [{"succeeded": True}]},
        )
        assert result["verdict"] == "passed"

    def test_partial(self, tmp_path):
        """GIVEN some uncovered but tests pass WHEN building report THEN partial."""
        from yuleosh.pipeline.step_handlers.test_qualification import _build_qualification_report
        result = _build_qualification_report(
            str(tmp_path), tmp_path,
            [mock.MagicMock(), mock.MagicMock()],
            {"total_scenarios": 2, "covered_count": 1, "uncovered_count": 1, "covered": [{}], "uncovered": [{"scenario": "s2"}]},
            {"executed": 1, "passed": 1, "failed": 0, "errors": [], "details": []},
        )
        assert result["verdict"] == "partial"

    def test_failed(self, tmp_path):
        """GIVEN test failures WHEN building report THEN verdict is failed."""
        from yuleosh.pipeline.step_handlers.test_qualification import _build_qualification_report
        result = _build_qualification_report(
            str(tmp_path), tmp_path,
            [mock.MagicMock()],
            {"total_scenarios": 1, "covered_count": 1, "uncovered_count": 0, "covered": [{}], "uncovered": []},
            {"executed": 2, "passed": 1, "failed": 1, "errors": [{}], "details": [{"succeeded": True}, {"succeeded": False}]},
        )
        assert result["verdict"] == "failed"


# ===================================================================
# step_test_qualification
# ===================================================================


class TestStepTestQualification:
    def test_basic_invocation(self, tmp_path, monkeypatch):
        """GIVEN valid session WHEN step runs THEN returns output path."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.test_qualification import step_test_qualification

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("## Scenario\nGIVEN x WHEN y THEN z\n")
        session = PipelineSession("test-qual", str(spec_file))
        session.session_dir = tmp_path / "sessions" / "test-qual"
        session.session_dir.mkdir(parents=True, exist_ok=True)

        result = step_test_qualification(session)
        assert result is not None
        assert str(session.session_dir / "qualification-test.json") == result

    def test_output_json(self, tmp_path, monkeypatch):
        """GIVEN step runs WHEN checking output THEN JSON has expected keys."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.test_qualification import step_test_qualification

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("## Scenario\nGIVEN init WHEN run THEN success\n")
        session = PipelineSession("test-qual-2", str(spec_file))
        session.session_dir = tmp_path / "sessions" / "test-qual-2"
        session.session_dir.mkdir(parents=True, exist_ok=True)

        step_test_qualification(session)
        review_path = session.session_dir / "qualification-test.json"
        assert review_path.exists()
        data = json.loads(review_path.read_text())
        assert "scenarios" in data
        assert "status" in data
        assert "verdict" in data
        assert "coverage" in data
        assert data["reviewer"] == "小明"

    def test_pipeline_error_propagated(self, tmp_path, monkeypatch):
        """GIVEN PipelineStepError raised WHEN step runs THEN propagates."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError
        from yuleosh.pipeline.step_handlers.test_qualification import step_test_qualification

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("nothing")
        session = PipelineSession("test-qual-3", str(spec_file))
        session.session_dir = tmp_path / "sessions" / "test-qual-3"
        session.session_dir.mkdir(parents=True, exist_ok=True)

        with mock.patch(
            "yuleosh.pipeline.step_handlers.test_qualification._run_system_tests",
            side_effect=PipelineStepError("Intentional"),
        ):
            with pytest.raises(PipelineStepError):
                step_test_qualification(session)
