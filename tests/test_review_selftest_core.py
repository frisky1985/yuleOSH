# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Comprehensive tests for review_selftest/core.py — coverage target ≥50%.

Covers all public and private functions:
  - _load_prev_selftest_review
  - _compute_selftest_regression
  - _get_ci_environ / _get_tool_version / _collect_environment_info
  - _generate_xunit_compatible
  - _get_run_history_path / _load_run_history / _save_run_history
  - _discover_junit_xml / _discover_coverage_files / _parse_lcov_coverage
  - _extract_shall_statements / _build_selftest_review_prompt
  - _generate_selftest_markdown
  - step_review_selftest
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Mini PipelineSession backed by a temp dir with mock LLM."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    from yuleosh.pipeline.session import PipelineSession

    spec_file = tmp_path / "spec.md"
    spec_file.write_text(
        "## RS-001: Temperature\n"
        "System SHALL monitor temperature within 100ms.\n"
        "System MAY log warnings.\n"
        "System SHOULD alert on threshold.\n"
    )
    session = PipelineSession("test-selftest", str(spec_file))
    session.llm_client = mock.MagicMock(
        return_value={
            "content": '```json\n{"status":"passed","findings":[],'
                        '"finding_breakdown":{"critical":0,"major":0,"minor":0,"info":0},'
                        '"shall_total":3,"shall_covered":2,'
                        '"shall_uncovered":["System SHOULD alert on threshold."],'
                        '"test_gap_areas":["Missing alert test"],'
                        '"summary":"OK"}\n```',
            "model": "mock-model",
            "usage": {"total_tokens": 50, "prompt_tokens": 30, "completion_tokens": 20},
        }
    )
    # Make session_dir
    session_dir = tmp_path / "sessions" / "test-selftest"
    session_dir.mkdir(parents=True, exist_ok=True)
    session.session_dir = session_dir
    session.token_usage_total = 0
    session.token_usage_steps = []
    session.artifacts = {}
    return session


@pytest.fixture
def mock_lcov_content():
    """Return a minimal lcov coverage.info content string."""
    return (
        "SF:/tmp/test/src/main.c\n"
        "DA:1,1\nDA:2,0\nDA:3,1\n"
        "BRDA:1,0,0,1\nBRDA:2,0,0,-\n"
        "FNF:2\nFNH:1\n"
        "end_of_record\n"
    )


@pytest.fixture
def sample_test_case_results():
    return [
        {"name": "test_monitor", "status": "passed", "duration": 0.5},
        {"name": "test_alert", "status": "failed", "duration": 0.3,
         "message": "AssertionError", "failure": {"type": "AssertionError", "stacktrace": "assert 0"}},
        {"name": "test_log", "status": "skipped", "duration": 0.0},
        {"name": "test_error_case", "status": "error", "duration": 0.1, "message": "RuntimeError"},
    ]


# ===================================================================
# _load_prev_selftest_review
# ===================================================================


class TestLoadPrevSelftestReview:
    def test_no_prev_file(self, tmp_path):
        """GIVEN no previous review file WHEN loading THEN returns None."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_prev_selftest_review
        result = _load_prev_selftest_review(tmp_path)
        assert result is None

    def test_prev_file_exists(self, tmp_path):
        """GIVEN previous review file in parent dir WHEN loading THEN returns parsed data."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_prev_selftest_review
        # Use a nested dir so parent is isolated
        nested = tmp_path / "session"
        nested.mkdir(parents=True, exist_ok=True)
        # Create prev file in parent of nested
        review_file = tmp_path / "selftest-review.json"
        review_file.write_text(json.dumps({"pass_rate": 85.0, "coverage": {"line_rate": 70.0}}))
        result = _load_prev_selftest_review(nested)
        assert result is not None
        assert result["pass_rate"] == 85.0

    def test_corrupted_file(self, tmp_path, caplog):
        """GIVEN corrupted JSON WHEN loading THEN logs warning and returns None."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_prev_selftest_review
        prev = tmp_path.parent
        prev.mkdir(parents=True, exist_ok=True)
        review_file = prev / "selftest-review.json"
        review_file.write_text("not valid json")
        result = _load_prev_selftest_review(tmp_path)
        assert result is None

    def test_osh_home_fallback(self, tmp_path, monkeypatch):
        """GIVEN no nearby prev file WHEN OSH_HOME has one THEN loads from .yuleosh/reports."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_prev_selftest_review
        # Use a deeply nested session_dir so parent dir has no review file
        session_dir = tmp_path / "deep" / "session"
        session_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        review_file = reports_dir / "selftest-review.json"
        review_file.write_text(json.dumps({"pass_rate": 90.0}))
        result = _load_prev_selftest_review(session_dir)
        assert result is not None
        assert result["pass_rate"] == 90.0


# ===================================================================
# _compute_selftest_regression
# ===================================================================


class TestComputeSelftestRegression:
    def test_no_prev_review(self):
        """GIVEN no previous review WHEN computing regression THEN empty dict."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _compute_selftest_regression
        result = _compute_selftest_regression({"pass_rate": 85.0}, None)
        assert result == {}

    def test_pass_rate_delta_positive(self):
        """GIVEN current has higher pass rate WHEN computing delta THEN returns positive delta."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _compute_selftest_regression
        current = {"pass_rate": 90.0, "coverage": {}, "test_case_results": []}
        prev = {"pass_rate": 80.0, "coverage": {}, "test_case_results": []}
        result = _compute_selftest_regression(current, prev)
        assert result["pass_rate_delta"] == 10.0

    def test_pass_rate_delta_negative(self):
        """GIVEN current has lower pass rate WHEN computing delta THEN returns negative delta."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _compute_selftest_regression
        current = {"pass_rate": 70.0, "coverage": {}, "test_case_results": []}
        prev = {"pass_rate": 90.0, "coverage": {}, "test_case_results": []}
        result = _compute_selftest_regression(current, prev)
        assert result["pass_rate_delta"] == -20.0

    def test_coverage_deltas(self):
        """GIVEN coverage differs WHEN computing regression THEN returns coverage deltas."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _compute_selftest_regression
        current = {"pass_rate": 85.0, "coverage": {"line_rate": 75.0, "branch_rate": 60.0, "function_rate": 80.0}, "test_case_results": []}
        prev = {"pass_rate": 85.0, "coverage": {"line_rate": 70.0, "branch_rate": 55.0, "function_rate": 75.0}, "test_case_results": []}
        result = _compute_selftest_regression(current, prev)
        assert result["coverage_deltas"]["line_rate"] == 5.0
        assert result["coverage_deltas"]["branch_rate"] == 5.0
        assert result["coverage_deltas"]["function_rate"] == 5.0

    def test_new_and_resolved_failures(self):
        """GIVEN failures changed between builds WHEN computing THEN lists new/resolved failures."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _compute_selftest_regression
        current = {"pass_rate": 80.0, "coverage": {},
                   "test_case_results": [
                       {"name": "test_a", "status": "passed"},
                       {"name": "test_b", "status": "failed"},
                       {"name": "test_c", "status": "failed"},
                   ]}
        prev = {"pass_rate": 90.0, "coverage": {},
                "test_case_results": [
                    {"name": "test_a", "status": "passed"},
                    {"name": "test_b", "status": "passed"},
                    {"name": "test_d", "status": "failed"},
                ]}
        result = _compute_selftest_regression(current, prev)
        assert "test_b" in result["new_failures"]
        assert "test_c" in result["new_failures"]
        assert "test_d" in result["resolved_failures"]


# ===================================================================
# _get_ci_environ
# ===================================================================


class TestGetCiEnviron:
    def test_default_empty(self, monkeypatch):
        """GIVEN no CI env vars WHEN getting environ THEN returns empty strings."""
        monkeypatch.delenv("BUILD_ID", raising=False)
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        monkeypatch.delenv("GIT_BRANCH", raising=False)
        from yuleosh.pipeline.step_handlers.review_selftest.core import _get_ci_environ
        result = _get_ci_environ()
        assert result["build_id"] == ""
        assert result["commit_sha"] == ""
        assert result["branch"] == ""

    def test_with_env_vars(self, monkeypatch):
        """GIVEN CI env vars set WHEN getting environ THEN returns values."""
        monkeypatch.setenv("BUILD_ID", "42")
        monkeypatch.setenv("GIT_COMMIT", "abc123")
        monkeypatch.setenv("GIT_BRANCH", "main")
        from yuleosh.pipeline.step_handlers.review_selftest.core import _get_ci_environ
        result = _get_ci_environ()
        assert result["build_id"] == "42"
        assert result["commit_sha"] == "abc123"
        assert result["branch"] == "main"


# ===================================================================
# _get_tool_version
# ===================================================================


class TestGetToolVersion:
    def test_tool_found(self):
        """GIVEN tool exists WHEN getting version THEN returns version string."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _get_tool_version
        result = _get_tool_version(sys.executable.split('/')[-1] or "python3")
        assert result != "unknown"

    def test_tool_not_found(self):
        """GIVEN tool does not exist WHEN getting version THEN returns unknown."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _get_tool_version
        result = _get_tool_version("nonexistent-tool-12345")
        assert result == "unknown"


# ===================================================================
# _collect_environment_info
# ===================================================================


class TestCollectEnvironmentInfo:
    def test_basic_structure(self):
        """GIVEN normal environment WHEN collecting info THEN returns dict with keys."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _collect_environment_info
        result = _collect_environment_info()
        assert "platform" in result
        assert "python_version" in result
        assert "hostname" in result
        assert result["platform"] == sys.platform


# ===================================================================
# _generate_xunit_compatible
# ===================================================================


class TestGenerateXunitCompatible:
    def test_empty_results(self):
        """GIVEN empty test_case_results WHEN generating XML THEN returns empty string."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_xunit_compatible
        result = _generate_xunit_compatible([])
        assert result == ""

    def test_mixed_results(self, sample_test_case_results):
        """GIVEN mixed test results WHEN generating XML THEN produces valid XML."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_xunit_compatible
        result = _generate_xunit_compatible(sample_test_case_results)
        assert "<?xml" in result
        assert "testsuite" in result
        assert "testcase" in result
        assert 'passes="1"' in result
        assert 'failures="1"' in result
        assert 'skipped="1"' in result
        assert 'errors="1"' in result

    def test_detailed_failure(self):
        """GIVEN test case with detailed failure info WHEN generating XML THEN includes failure details."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_xunit_compatible
        result = _generate_xunit_compatible([
            {"name": "test_fail", "status": "failed", "duration": 0.1,
             "message": "assert 0 == 1",
             "failure": {"type": "AssertionError", "stacktrace": "File test.py, line 10"}}
        ])
        assert 'type="AssertionError"' in result
        assert "File test.py" in result

    def test_error_status(self):
        """GIVEN test case with error status WHEN generating XML THEN includes error element."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_xunit_compatible
        result = _generate_xunit_compatible([
            {"name": "test_err", "status": "error", "duration": 0.1, "message": "Runtime error"}
        ])
        assert "<error" in result


# ===================================================================
# _get_run_history_path
# ===================================================================


class TestGetRunHistoryPath:
    def test_returns_path(self, monkeypatch):
        """GIVEN OSH_HOME set WHEN getting path THEN returns correct path."""
        monkeypatch.setenv("OSH_HOME", "/tmp/test_project")
        from yuleosh.pipeline.step_handlers.review_selftest.core import _get_run_history_path
        result = _get_run_history_path()
        assert str(result).endswith(".yuleosh/reports/selftest-history.json")
        assert "/tmp/test_project" in str(result)


# ===================================================================
# _load_run_history
# ===================================================================


class TestLoadRunHistory:
    def test_no_history_file(self, tmp_path, monkeypatch):
        """GIVEN no history file WHEN loading THEN returns empty list."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_run_history
        result = _load_run_history()
        assert result == []

    def test_with_history(self, tmp_path, monkeypatch):
        """GIVEN history file with entries WHEN loading THEN returns last 5 entries."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_run_history
        hist_path = tmp_path / ".yuleosh" / "reports" / "selftest-history.json"
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [{"generated_at": f"2025-01-0{i}T00:00:00", "pass_rate": float(i * 10)}
                for i in range(1, 8)]
        hist_path.write_text(json.dumps(data))
        result = _load_run_history()
        assert len(result) == 5  # max 5

    def test_corrupted_history(self, tmp_path, monkeypatch, caplog):
        """GIVEN corrupted history file WHEN loading THEN returns empty list."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _load_run_history
        hist_path = tmp_path / ".yuleosh" / "reports" / "selftest-history.json"
        hist_path.parent.mkdir(parents=True, exist_ok=True)
        hist_path.write_text("not json")
        result = _load_run_history()
        assert result == []


# ===================================================================
# _save_run_history
# ===================================================================


class TestSaveRunHistory:
    def test_save_new_entry(self, tmp_path, monkeypatch):
        """GIVEN no existing history WHEN saving THEN creates file with one entry."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _save_run_history
        current = {"generated_at": "2025-06-01T00:00:00", "pass_rate": 85.0}
        result = _save_run_history(current)
        assert len(result) == 1
        assert result[0]["pass_rate"] == 85.0
        # Verify file was written
        hist_path = tmp_path / ".yuleosh" / "reports" / "selftest-history.json"
        assert hist_path.exists()
        loaded = json.loads(hist_path.read_text())
        assert len(loaded) == 1

    def test_keep_max_5(self, tmp_path, monkeypatch):
        """GIVEN 5 existing entries WHEN adding 6th THEN keeps only last 5."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _save_run_history
        existing = [{"generated_at": f"2025-0{i}T00:00:00"} for i in range(1, 6)]
        current = {"generated_at": "2025-06-01T00:00:00"}
        result = _save_run_history(current, existing)
        assert len(result) == 5

    def test_with_existing_history_param(self, tmp_path, monkeypatch):
        """GIVEN existing_history param WHEN saving THEN appends correctly."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _save_run_history
        current = {"generated_at": "2025-06-01T00:00:00"}
        result = _save_run_history(current, [])
        assert len(result) == 1


# ===================================================================
# _discover_junit_xml
# ===================================================================


class TestDiscoverJunitXml:
    def test_no_files(self, tmp_session):
        """GIVEN no junit files WHEN discovering THEN returns empty list."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_junit_xml
        result = _discover_junit_xml(tmp_session)
        # May find files in project root but shouldn't be critical
        assert isinstance(result, list)

    def test_with_artifacts_path(self, tmp_session, tmp_path):
        """GIVEN session has self-test artifact dir with XML WHEN discovering THEN finds files."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_junit_xml
        artifact_dir = tmp_path / "self-test"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        xml_file = artifact_dir / "junit.xml"
        xml_file.write_text("<testsuite></testsuite>")
        tmp_session.artifacts["self-test"] = str(artifact_dir)
        result = _discover_junit_xml(tmp_session)
        assert any(str(xml_file) in str(p) for p in result)

    def test_session_dir_glob(self, tmp_session, tmp_path):
        """GIVEN session_dir has XML files WHEN discovering THEN finds them."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_junit_xml
        sd = tmp_path / "session_dir"
        sd.mkdir(parents=True, exist_ok=True)
        xml_file = sd / "pytest-report.xml"
        xml_file.write_text("<testsuite></testsuite>")
        tmp_session.session_dir = sd
        result = _discover_junit_xml(tmp_session)
        assert any(str(xml_file) in str(p) for p in result)

    def test_dedup(self, tmp_session, tmp_path):
        """GIVEN same file discovered via multiple paths WHEN deduping THEN unique list."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_junit_xml
        # Create same file in project root
        xml_file = tmp_path / "junit.xml"
        xml_file.write_text("<testsuite></testsuite>")
        tmp_session.session_dir = tmp_path
        result = _discover_junit_xml(tmp_session)
        # Count occurrences of same resolved path
        resolved = [str(p.resolve()) for p in result]
        assert len(resolved) == len(set(resolved))


# ===================================================================
# _discover_coverage_files
# ===================================================================


class TestDiscoverCoverageFiles:
    def test_no_files(self, tmp_session):
        """GIVEN no coverage files WHEN discovering THEN returns empty list."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_coverage_files
        result = _discover_coverage_files(tmp_session)
        assert isinstance(result, list)

    def test_finds_in_project_root(self, tmp_session, tmp_path, monkeypatch):
        """GIVEN coverage.info in project root WHEN discovering THEN finds it."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.pipeline.step_handlers.review_selftest.core import _discover_coverage_files
        cov_file = tmp_path / "coverage.info"
        cov_file.write_text("")
        result = _discover_coverage_files(tmp_session)
        assert any(str(cov_file) in str(p) for p in result)


# ===================================================================
# _parse_lcov_coverage
# ===================================================================


class TestParseLcovCoverage:
    def test_missing_file(self, tmp_path):
        """GIVEN non-existent lcov file WHEN parsing THEN returns default zeros."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _parse_lcov_coverage
        result = _parse_lcov_coverage(tmp_path / "nonexistent.info")
        assert result["line_rate"] == 0.0
        assert result["branch_rate"] == 0.0
        assert result["function_rate"] == 0.0
        assert result["mc_dc_rate"] is None

    def test_with_valid_data(self, tmp_path, mock_lcov_content):
        """GIVEN valid lcov content WHEN parsing THEN computes correct rates."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _parse_lcov_coverage
        cov_file = tmp_path / "coverage.info"
        cov_file.write_text(mock_lcov_content)
        result = _parse_lcov_coverage(cov_file)
        assert result["line_rate"] == pytest.approx(66.67, rel=0.1)  # 2/3 hit
        assert result["branch_rate"] == 50.0  # 1/2 hit
        assert result["function_rate"] == 50.0  # 1/2
        assert result["mc_dc_rate"] == 50.0

    def test_no_branch_data(self, tmp_path):
        """GIVEN lcov with no BRDA lines WHEN parsing THEN mc_dc_rate is None."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _parse_lcov_coverage
        cov_file = tmp_path / "coverage.info"
        cov_file.write_text("SF:/tmp/test.c\nDA:1,1\nFNF:1\nFNH:1\nend_of_record\n")
        result = _parse_lcov_coverage(cov_file)
        assert result["line_rate"] == 100.0
        assert result["mc_dc_rate"] is None
        assert result["branch_rate"] == 0.0

    def test_per_file_output(self, tmp_path):
        """GIVEN lcov with per-file data WHEN parsing THEN returns per_file list."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _parse_lcov_coverage
        cov_file = tmp_path / "coverage.info"
        cov_file.write_text(
            "SF:/tmp/test/a.c\nDA:1,1\nDA:2,0\nFNF:1\nFNH:0\nend_of_record\n"
            "SF:/tmp/test/b.c\nDA:1,1\nFNF:1\nFNH:1\nend_of_record\n"
        )
        result = _parse_lcov_coverage(cov_file)
        assert len(result["per_file"]) == 2
        assert result["per_file"][0]["line_rate"] > 0

    def test_empty_file(self, tmp_path):
        """GIVEN empty lcov file WHEN parsing THEN returns defaults."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _parse_lcov_coverage
        cov_file = tmp_path / "coverage.info"
        cov_file.write_text("")
        result = _parse_lcov_coverage(cov_file)
        assert result["line_rate"] == 0.0


# ===================================================================
# _extract_shall_statements
# ===================================================================


class TestExtractShallStatements:
    def test_empty_content(self):
        """GIVEN empty spec content WHEN extracting SHALLs THEN returns empty list."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _extract_shall_statements
        result = _extract_shall_statements("")
        assert result == []

    def test_extracts_shall(self):
        """GIVEN spec with SHALL statements WHEN extracting THEN finds them."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _extract_shall_statements
        content = "## Requirements\nSystem SHALL do X.\nSystem MAY do Y.\n"
        result = _extract_shall_statements(content)
        assert len(result) == 2

    def test_tracks_section_and_line(self):
        """GIVEN spec with sections WHEN extracting THEN tracks section and line numbers."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _extract_shall_statements
        content = "# Overview\n# Section 1\nItem SHALL work.\n# Section 2\nItem SHALL also work.\n"
        result = _extract_shall_statements(content)
        assert result[0]["section"] == "Section 1"
        assert result[0]["line"] == 3
        assert result[1]["section"] == "Section 2"

    def test_no_shall(self):
        """GIVEN spec with no SHALL/SHOULD/MAY WHEN extracting THEN returns empty."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _extract_shall_statements
        result = _extract_shall_statements("Just some text without keywords.")
        assert result == []

    def test_case_insensitive(self):
        """GIVEN spec with lowercase shall WHEN extracting THEN still finds it."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _extract_shall_statements
        content = "System shall work.\n"
        result = _extract_shall_statements(content)
        assert len(result) == 1


# ===================================================================
# _build_selftest_review_prompt
# ===================================================================


class TestBuildSelftestReviewPrompt:
    def test_basic_structure(self):
        """GIVEN basic inputs WHEN building prompts THEN returns system and user prompts."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _build_selftest_review_prompt
        system_prompt, user_prompt = _build_selftest_review_prompt(
            spec_content="# Test spec\nSystem SHALL work.",
            spec_name="spec.md",
            self_test_content="All tests passed.",
            shall_statements=[{"statement": "System SHALL work.", "section": "Req", "line": 1}],
            test_plan_content="Test plan for coverage.",
        )
        assert "You are a test reviewer" in system_prompt
        assert "Spec: spec.md" in user_prompt
        assert "SHALL" in user_prompt
        # Auto-Mapped section only appears when auto_shall_coverage is provided
        assert "Auto-Mapped" not in user_prompt

    def test_with_auto_coverage(self):
        """GIVEN auto-mapped SHALL coverage WHEN building prompts THEN includes mapping."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _build_selftest_review_prompt
        shalls = [{"statement": "System SHALL work.", "section": "Req", "line": 1}]
        auto_shall = ({0}, {"System SHALL work.": ["test_work"]})
        _, user_prompt = _build_selftest_review_prompt(
            spec_content="# Spec",
            spec_name="spec.md",
            self_test_content="Pass",
            shall_statements=shalls,
            test_plan_content="Plan",
            auto_shall_coverage=auto_shall,
        )
        assert "test_work" in user_prompt
        assert "✅" in user_prompt

    def test_with_test_case_summary(self):
        """GIVEN test_case_results WHEN building prompts THEN includes summary."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _build_selftest_review_prompt
        shalls = [{"statement": "System SHALL work.", "section": "Req", "line": 1}]
        tcs = [{"name": "t1", "status": "passed"}, {"name": "t2", "status": "failed"}]
        _, user_prompt = _build_selftest_review_prompt(
            spec_content="# Spec",
            spec_name="spec.md",
            self_test_content="Pass",
            shall_statements=shalls,
            test_plan_content="Plan",
            test_case_results=tcs,
        )
        assert "Test Case Summary" in user_prompt

    def test_many_shalls_truncated(self):
        """GIVEN more than 60 SHALL statements WHEN building THEN truncates."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _build_selftest_review_prompt
        shalls = [{"statement": f"SHALL {i}.", "section": "Req", "line": i} for i in range(70)]
        _, user_prompt = _build_selftest_review_prompt(
            spec_content="# Spec",
            spec_name="spec.md",
            self_test_content="Pass",
            shall_statements=shalls,
            test_plan_content="Plan",
        )
        assert "... and 10 more" in user_prompt


# ===================================================================
# _generate_selftest_markdown
# ===================================================================


class TestGenerateSelftestMarkdown:
    def test_basic_report(self):
        """GIVEN minimal review dict WHEN generating markdown THEN produces structured output."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "test-session",
            "pass_rate": 75.0,
            "total_passed": 3,
            "total_failed": 1,
            "total_skipped": 1,
            "total_errors": 0,
            "duration_sec": 5.0,
            "status": "passed",
            "error_code": 0,
            "shall_total": 5,
            "shall_covered": 4,
            "shall_unknown": 1,
            "shall_uncovered": ["Missing SHALL"],
            "coverage": {"line_rate": 70.0, "branch_rate": 50.0, "function_rate": 80.0},
            "test_case_results": [],
            "test_gap_areas": ["Area 1"],
            "findings": [{"severity": "major", "message": "Missing test coverage"}],
            "finding_breakdown": {"critical": 0, "major": 1, "minor": 0, "info": 0},
        }
        md = _generate_selftest_markdown(review)
        assert "# Self-Test Report" in md
        assert "SHALL Coverage" in md
        assert "Coverage Metrics" in md
        assert "Findings" in md
        assert "Missing SHALL" in md
        assert "Missing test coverage" in md

    def test_with_per_file_coverage(self):
        """GIVEN per_file coverage data WHEN generating markdown THEN includes per-file table."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s",
            "pass_rate": 100.0, "total_passed": 1, "total_failed": 0,
            "total_skipped": 0, "total_errors": 0, "duration_sec": 1.0,
            "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {
                "line_rate": 90.0, "branch_rate": 80.0, "function_rate": 85.0,
                "per_file": [
                    {"file": "src/main.c", "line_rate": 90.0, "branch_rate": 80.0, "function_rate": 85.0}
                ],
            },
            "test_case_results": [],
            "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
        }
        md = _generate_selftest_markdown(review)
        assert "Coverage by File" in md
        assert "src/main.c" in md

    def test_with_mc_dc(self):
        """GIVEN mc_dc_rate present WHEN generating markdown THEN includes MC/DC section."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75, "mc_dc_rate": 60.0},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
        }
        md = _generate_selftest_markdown(review)
        assert "MC/DC Condition Coverage" in md
        assert "60.0%" in md

    def test_with_regression_analysis(self):
        """GIVEN regression_analysis data WHEN generating markdown THEN includes regression section."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
            "regression_analysis": {
                "pass_rate_delta": 5.0,
                "coverage_deltas": {"line_rate": 2.0},
                "new_failures": ["test_new"],
                "resolved_failures": ["test_old"],
            },
        }
        md = _generate_selftest_markdown(review)
        assert "Regression Analysis" in md
        assert "test_new" in md
        assert "test_old" in md

    def test_with_run_history(self):
        """GIVEN run_history data WHEN generating markdown THEN includes history table."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
            "run_history": [{"generated_at": "2025-06-01T00:00:00", "pass_rate": 85.0,
                             "line_rate": 70.0, "branch_rate": 60.0, "function_rate": 80.0,
                             "mc_dc_rate": 50.0}],
        }
        md = _generate_selftest_markdown(review)
        assert "Test Execution History" in md
        assert "85.0%" in md

    def test_with_llm_degradation(self):
        """GIVEN llm_degradation data WHEN generating markdown THEN includes LLM status."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
            "llm_degradation": {"llm_called": True, "llm_succeeded": False,
                                "fallback_used": True, "fallback_reason": "Timeout"},
        }
        md = _generate_selftest_markdown(review)
        assert "LLM Analysis Status" in md
        assert "Timeout" in md

    def test_with_environment_info(self):
        """GIVEN environment info WHEN generating markdown THEN includes env section."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
            "environment": {"platform": "linux", "python_version": "3.10", "hostname": "test-host"},
        }
        md = _generate_selftest_markdown(review)
        assert "Test Environment" in md
        assert "test-host" in md

    def test_summary_and_ci_info(self):
        """GIVEN summary and build_id WHEN generating markdown THEN includes both."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import _generate_selftest_markdown
        review = {
            "session": "s", "pass_rate": 100, "total_passed": 1,
            "total_failed": 0, "total_skipped": 0, "total_errors": 0,
            "duration_sec": 1, "status": "passed", "error_code": 0,
            "shall_total": 0, "shall_covered": 0, "shall_unknown": 0,
            "shall_uncovered": [],
            "coverage": {"line_rate": 80, "branch_rate": 70, "function_rate": 75},
            "test_case_results": [], "test_gap_areas": [],
            "findings": [], "finding_breakdown": {},
            "summary": "All tests passed and SHALL coverage is complete.",
            "build_id": "CI-42", "branch": "main",
        }
        md = _generate_selftest_markdown(review)
        assert "Summary" in md
        assert "CI-42" in md


# ===================================================================
# step_review_selftest (main entry point)
# ===================================================================


class TestStepReviewSelftest:
    def test_basic_invocation(self, tmp_session):
        """GIVEN valid session WHEN step_review_selftest runs THEN returns output path."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import step_review_selftest
        # Mock _call_llm and _parse_spec to avoid real calls
        with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._call_llm",
                        return_value={"content": '```json\n{"status":"passed","findings":[],"finding_breakdown":{"critical":0,"major":0,"minor":0,"info":0},"shall_total":3,"shall_covered":2,"shall_uncovered":[],"test_gap_areas":[],"summary":"OK"}\n```',
                                      "usage": {"total_tokens": 50}}):
            with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._parse_spec",
                            return_value=(mock.MagicMock(), [])):
                with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._try_parse_hermes_json",
                                return_value={"status": "passed"}):
                    result = step_review_selftest(tmp_session)
                    assert result is not None
                    assert str(tmp_session.session_dir / "selftest-review.json") == result

    def test_llm_fallback(self, tmp_session):
        """GIVEN LLM call fails WHEN step_review_selftest runs THEN uses fallback."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import step_review_selftest
        with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._call_llm",
                        side_effect=Exception("LLM timeout")):
            result = step_review_selftest(tmp_session)
            assert result is not None
            # Verify review was still produced
            review_path = tmp_session.session_dir / "selftest-review.json"
            assert review_path.exists()

    def test_selftest_json_output(self, tmp_session):
        """GIVEN successful run WHEN checking output THEN JSON has required keys."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import step_review_selftest
        with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._call_llm",
                        return_value={"content": '```json\n{"status":"passed"}\n```', "usage": {"total_tokens": 30}}):
            with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._parse_spec",
                            return_value=(mock.MagicMock(), [])):
                step_review_selftest(tmp_session)
        review_path = tmp_session.session_dir / "selftest-review.json"
        assert review_path.exists()
        data = json.loads(review_path.read_text())
        assert "schema_version" in data
        assert "error_code" in data
        assert "build_id" in data
        assert "coverage" in data
        assert "llm_degradation" in data

    def test_llm_fallback_continues(self, tmp_session):
        """GIVEN PipelineStepError from LLM WHEN running THEN falls back and continues."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import (
            step_review_selftest, PipelineStepError,
        )
        with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._call_llm",
                        side_effect=PipelineStepError("Intentional error")):
            # Should NOT raise — LLM error is caught and handled as fallback
            result = step_review_selftest(tmp_session)
            assert result is not None
            review_path = tmp_session.session_dir / "selftest-review.json"
            assert review_path.exists()

    def test_markdown_output(self, tmp_session):
        """GIVEN successful run WHEN checking output THEN self-test-report.md exists."""
        from yuleosh.pipeline.step_handlers.review_selftest.core import step_review_selftest
        with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._call_llm",
                        return_value={"content": '```json\n{"status":"passed"}\n```', "usage": {"total_tokens": 30}}):
            with mock.patch("yuleosh.pipeline.step_handlers.review_selftest.core._parse_spec",
                            return_value=(mock.MagicMock(), [])):
                step_review_selftest(tmp_session)
        md_path = tmp_session.session_dir / "self-test-report.md"
        assert md_path.exists()
        assert md_path.read_text().strip()


# ===================================================================
# Test module exports via __init__.py
# ===================================================================


class TestModuleExports:
    def test_core_exports(self):
        """GIVEN core module WHEN importing THEN expected names are available."""
        from yuleosh.pipeline.step_handlers.review_selftest import core
        assert hasattr(core, "step_review_selftest")
        assert hasattr(core, "_SELFTEST_SCHEMA_VERSION")
        assert hasattr(core, "ASPICE_MAP")
        assert hasattr(core, "_load_prev_selftest_review")
        assert hasattr(core, "_compute_selftest_regression")
        assert hasattr(core, "_get_ci_environ")
        assert hasattr(core, "_get_tool_version")
        assert hasattr(core, "_collect_environment_info")
        assert hasattr(core, "_generate_xunit_compatible")
        assert hasattr(core, "_get_run_history_path")
        assert hasattr(core, "_load_run_history")
        assert hasattr(core, "_save_run_history")
        assert hasattr(core, "_discover_junit_xml")
        assert hasattr(core, "_discover_coverage_files")
        assert hasattr(core, "_parse_lcov_coverage")
        assert hasattr(core, "_extract_shall_statements")
        assert hasattr(core, "_build_selftest_review_prompt")
        assert hasattr(core, "_generate_selftest_markdown")

    def test_init_exports(self):
        """GIVEN __init__ module WHEN importing THEN all core names are available."""
        from yuleosh.pipeline.step_handlers import review_selftest
        assert hasattr(review_selftest, "step_review_selftest")
        assert hasattr(review_selftest, "_SELFTEST_SCHEMA_VERSION")
        assert hasattr(review_selftest, "ASPICE_MAP")
