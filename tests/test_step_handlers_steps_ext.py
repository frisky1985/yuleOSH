# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for pipeline step handler entry-point functions with mocking.

Covers:
  - step_review_arch  (review_arch.py)
  - step_review_code  (review_code.py)
  - step_c_unit_test  (test_c_unit.py)
  - step_integration_test  (test_integration.py)
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch, call

import pytest

from yuleosh.pipeline.step_handlers.review_arch import step_review_arch
from yuleosh.pipeline.step_handlers.review_code import step_review_code
from yuleosh.pipeline.step_handlers.test_c_unit import step_c_unit_test
from yuleosh.pipeline.step_handlers.test_integration import step_integration_test


# ══════════════════════════════════════════════════════════════════════════
# Fixtures: mock PipelineSession
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_session(tmp_path: Path):
    session = MagicMock()
    session.name = "test-session"
    session.spec_path = str(tmp_path / "spec.md")
    session.session_dir = tmp_path / "session"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    session.token_usage_total = 0
    session.token_usage_steps = []
    session.artifacts = {}
    return session


@pytest.fixture
def spec_file(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Test Spec\nModule X does Y.")
    return spec


# ══════════════════════════════════════════════════════════════════════════
# step_review_arch
# ══════════════════════════════════════════════════════════════════════════

class TestStepReviewArch:
    def test_no_architecture_artifact(self, mock_session, spec_file, tmp_path):
        """When no architecture artifact exists, step completes without LLM call."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.review_arch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="main.c\nutils.c\n", returncode=0)

            with patch("yuleosh.pipeline.step_handlers.review_arch._run_arch_review") as mock_review:
                mock_result = MagicMock()
                mock_result.findings = []
                mock_result.status = "passed"
                mock_result.summary = "All clear"
                mock_review.return_value = mock_result

                result = step_review_arch(mock_session)
                assert isinstance(result, str)
                assert os.path.exists(result)

                with open(result) as f:
                    report = json.load(f)
                assert report["status"] == "passed"
                assert report["finding_count"] == 0
                # No architecture artifact → llm_review should be "(No architecture artifact to review)"
                assert "No architecture artifact" in report["llm_review"]

    def test_with_architecture_artifact(self, mock_session, spec_file, tmp_path):
        """When architecture artifact exists, LLM review is attempted."""
        mock_session.spec_path = str(spec_file)
        arch_file = tmp_path / "arch.md"
        arch_file.write_text("# Architecture Design\nModule X has components A, B, C.")
        mock_session.artifacts = {"architecture": str(arch_file)}

        with patch("yuleosh.pipeline.step_handlers.review_arch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

            with patch("yuleosh.pipeline.step_handlers.review_arch._run_arch_review") as mock_review:
                mock_result = MagicMock()
                mock_result.findings = []
                mock_result.status = "passed"
                mock_result.summary = "All good"
                mock_review.return_value = mock_result

                with patch("yuleosh.pipeline.step_handlers.review_arch._call_llm") as mock_llm:
                    mock_llm.return_value = {
                        "content": "LLM review: architecture looks good.",
                        "usage": {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
                    }

                    result = step_review_arch(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert report["status"] == "passed"
                    assert "LLM review:" in report["llm_review"]
                    assert mock_session.token_usage_total == 100

    def test_with_critical_finding(self, mock_session, spec_file):
        """Critical findings should set status to 'failed'."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.review_arch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

            with patch("yuleosh.pipeline.step_handlers.review_arch._run_arch_review") as mock_review:
                from yuleosh.review.run import ReviewFinding
                finding = MagicMock()
                finding.severity = "critical"
                finding.to_dict.return_value = {"severity": "critical", "message": "Missing safety requirement"}

                mock_result = MagicMock()
                mock_result.findings = [finding]
                mock_result.status = "failed"
                mock_result.summary = "Critical issues found"
                mock_review.return_value = mock_result

                result = step_review_arch(mock_session)
                with open(result) as f:
                    report = json.load(f)
                assert report["status"] == "failed"
                assert report["finding_breakdown"]["critical"] == 1

    def test_git_diff_failure_non_fatal(self, mock_session, spec_file):
        """If git diff fails, the step should still complete (non-fatal)."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.review_arch.subprocess.run") as mock_run:
            # Make git diff raise
            mock_run.side_effect = FileNotFoundError("git not found")

            with patch("yuleosh.pipeline.step_handlers.review_arch._run_arch_review") as mock_review:
                mock_result = MagicMock()
                mock_result.findings = []
                mock_result.status = "passed"
                mock_result.summary = "OK"
                mock_review.return_value = mock_result

                result = step_review_arch(mock_session)
                assert isinstance(result, str)
                assert os.path.exists(result)

    def test_llm_failure_non_fatal(self, mock_session, spec_file, tmp_path):
        """If LLM call fails, the step should still complete with a note."""
        mock_session.spec_path = str(spec_file)
        arch_file = tmp_path / "arch.md"
        arch_file.write_text("# Architecture")
        mock_session.artifacts = {"architecture": str(arch_file)}

        with patch("yuleosh.pipeline.step_handlers.review_arch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)

            with patch("yuleosh.pipeline.step_handlers.review_arch._run_arch_review") as mock_review:
                mock_result = MagicMock()
                mock_result.findings = []
                mock_result.status = "passed"
                mock_result.summary = "OK"
                mock_review.return_value = mock_result

                with patch("yuleosh.pipeline.step_handlers.review_arch._call_llm") as mock_llm:
                    mock_llm.side_effect = RuntimeError("LLM unavailable")

                    result = step_review_arch(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert "unavailable" in report["llm_review"]


# ══════════════════════════════════════════════════════════════════════════
# step_review_code
# ══════════════════════════════════════════════════════════════════════════

class TestStepReviewCode:
    def test_basic_flow(self, mock_session, spec_file):
        """Basic flow with spec and no artifacts."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.review_code.os.walk") as mock_walk:
            mock_walk.return_value = []

            with patch("yuleosh.pipeline.step_handlers.review_code._call_llm") as mock_llm:
                mock_llm.return_value = {
                    "content": '```json\n{"status": "passed", "findings": [], "summary": "OK"}\n```',
                    "usage": {"total_tokens": 50},
                }

                result = step_review_code(mock_session)
                assert isinstance(result, str)
                assert os.path.exists(result)

                with open(result) as f:
                    report = json.load(f)
                assert report["status"] == "passed"
                assert report["step"] == "internal-code-review"

    def test_llm_failure_raises(self, mock_session, spec_file):
        """If LLM call fails, step should raise PipelineStepError."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.review_code.os.walk") as mock_walk:
            mock_walk.return_value = []

            with patch("yuleosh.pipeline.step_handlers.review_code._call_llm") as mock_llm:
                mock_llm.side_effect = RuntimeError("LLM down")

                from yuleosh.pipeline.session import PipelineStepError
                with pytest.raises(PipelineStepError):
                    step_review_code(mock_session)

    def test_with_artifacts(self, mock_session, spec_file, tmp_path):
        """When artifacts (architecture, development) exist, they should be read."""
        mock_session.spec_path = str(spec_file)
        arch_file = tmp_path / "arch.md"
        arch_file.write_text("# Arch")
        dev_file = tmp_path / "dev.md"
        dev_file.write_text("# Dev Plan")
        mock_session.artifacts = {
            "architecture": str(arch_file),
            "development": str(dev_file),
        }
        # Create source dir inside project for os.walk
        src_dir = tmp_path / "src"
        src_dir.mkdir(exist_ok=True)
        main_py = src_dir / "main.py"
        main_py.write_text("print('hello')")

        # Mock OSH_HOME to point to our tmp_path
        with patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            with patch("yuleosh.pipeline.step_handlers.review_code.os.walk") as mock_walk:
                mock_walk.return_value = [(str(src_dir), [], ["main.py"])]

                with patch.object(Path, "read_text", return_value="print('hello')"):
                    with patch("yuleosh.pipeline.step_handlers.review_code._call_llm") as mock_llm:
                        mock_llm.return_value = {
                            "content": '```json\n{"status": "passed", "findings": [], "summary": "OK"}\n```',
                            "usage": {"total_tokens": 75},
                        }

                        result = step_review_code(mock_session)
                        with open(result) as f:
                            report = json.load(f)
                        assert report["status"] == "passed"


# ══════════════════════════════════════════════════════════════════════════
# step_c_unit_test
# ══════════════════════════════════════════════════════════════════════════

class TestStepCUnitTest:
    def test_no_c_files_skips(self, mock_session, tmp_path):
        """When no .c files exist, the step should skip gracefully."""
        # Make project_dir point to tmp_path with no .c files
        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(tmp_path)):
            result = step_c_unit_test(mock_session)
            assert isinstance(result, str)
            assert os.path.exists(result)
            with open(result) as f:
                report = json.load(f)
            assert report["status"] == "skipped"
            assert "No C source files" in report["reason"]

    def test_has_c_files_no_tests(self, mock_session, tmp_path):
        """When .c files exist but no test framework, status is 'unknown'."""
        # Create a .c file in project_dir
        proj_dir = tmp_path / "myproj"
        proj_dir.mkdir()
        (proj_dir / "main.c").write_text("int main() { return 0; }")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            result = step_c_unit_test(mock_session)
            with open(result) as f:
                report = json.load(f)
            assert report["c_files"] > 0
            assert report["test_runner"] == "none"
            assert report["status"] == "unknown"

    def test_unity_runner_success(self, mock_session, tmp_path):
        """When Unity tests exist and pass, status is 'passed'."""
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        (proj_dir / "main.c").write_text("int main() { return 0; }")

        unity_dir = proj_dir / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        (unity_dir / "Makefile").write_text("all:\n\techo ok\n")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            with patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="OK (1 test, 1 assertion, 0 failed, 0 ignored)\n",
                    stderr="",
                    returncode=0,
                )
                result = step_c_unit_test(mock_session)
                with open(result) as f:
                    report = json.load(f)
                assert report["status"] == "passed"
                assert report["test_runner"] == "unity"
                assert report["passed"] > 0

    def test_unity_runner_failure(self, mock_session, tmp_path):
        """When Unity tests fail, status is 'failed'."""
        proj_dir = tmp_path / "proj2"
        proj_dir.mkdir()
        (proj_dir / "module.c").write_text("int foo() { return 0; }")

        unity_dir = proj_dir / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        (unity_dir / "Makefile").write_text("all:\n\techo fail\n")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            with patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="FAIL (1 test, 1 assertion, 1 failed, 0 ignored)\n",
                    stderr="",
                    returncode=1,
                )
                result = step_c_unit_test(mock_session)
                with open(result) as f:
                    report = json.load(f)
                assert report["status"] == "failed"
                assert report["test_runner"] == "unity"

    def test_unity_make_not_found(self, mock_session, tmp_path):
        """If 'make' is not found, fall through to next runner."""
        proj_dir = tmp_path / "proj3"
        proj_dir.mkdir()
        (proj_dir / "test.c").write_text("int test() { return 0; }")

        unity_dir = proj_dir / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        (unity_dir / "Makefile").write_text("all:\n\techo\n")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            with patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run") as mock_run:
                mock_run.side_effect = FileNotFoundError("make not found")
                result = step_c_unit_test(mock_session)
                with open(result) as f:
                    report = json.load(f)
                # Should fall through to "none" since no other runner is available
                assert report["test_runner"] == "none"
                assert report["status"] == "unknown"

    def test_unity_timeout(self, mock_session, tmp_path):
        """Unity timeout should be handled gracefully."""
        proj_dir = tmp_path / "proj4"
        proj_dir.mkdir()
        (proj_dir / "code.c").write_text("int f() { return 0; }")

        unity_dir = proj_dir / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        (unity_dir / "Makefile").write_text("all:\n\techo\n")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            with patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run") as mock_run:
                import subprocess
                mock_run.side_effect = subprocess.TimeoutExpired("make", 120)
                result = step_c_unit_test(mock_session)
                with open(result) as f:
                    report = json.load(f)
                assert report["test_runner"] == "unity-timeout"
                assert "TIMEOUT" in report["output"]

    def test_parse_unity_counts_integration(self, mock_session, tmp_path):
        """Test that _parse_unity_counts is actually called."""
        proj_dir = tmp_path / "proj5"
        proj_dir.mkdir()
        (proj_dir / "main.c").write_text("int main() { return 0; }")

        unity_dir = proj_dir / "tests" / "unity"
        unity_dir.mkdir(parents=True)
        (unity_dir / "Makefile").write_text("all:\n\techo\n")

        with patch("yuleosh.pipeline.step_handlers.test_c_unit.os.environ.get", return_value=str(proj_dir)):
            with patch("yuleosh.pipeline.step_handlers.test_c_unit.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="OK (1 test, 1 assertion, 0 failed, 0 ignored)\nOK (1 test, 1 assertion, 0 failed, 0 ignored)\n",
                    stderr="",
                    returncode=0,
                )
                result = step_c_unit_test(mock_session)
                with open(result) as f:
                    report = json.load(f)
                assert report["passed"] == 2
                assert report["failed"] == 0


# ══════════════════════════════════════════════════════════════════════════
# step_integration_test
# ══════════════════════════════════════════════════════════════════════════

class TestStepIntegrationTest:
    def test_no_test_framework(self, mock_session, spec_file):
        """When no test framework is available, status is 'unknown'."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.test_integration._parse_scenarios") as mock_parse:
            mock_parse.return_value = ["scenario1", "scenario2"]
            with patch("yuleosh.pipeline.step_handlers.test_integration._parse_spec") as mock_spec:
                mock_spec.return_value = {}
                with patch("yuleosh.pipeline.step_handlers.test_integration.subprocess.run") as mock_run:
                    # pytest not found
                    mock_run.side_effect = FileNotFoundError("pytest not found")

                    result = step_integration_test(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert report["test_runner"] == "none"
                    assert report["status"] == "unknown"
                    assert len(report["spec_scenarios"]) == 2

    def test_pytest_runner_success(self, mock_session, spec_file):
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.test_integration._parse_scenarios") as mock_parse:
            mock_parse.return_value = []
            with patch("yuleosh.pipeline.step_handlers.test_integration._parse_spec") as mock_spec:
                mock_spec.return_value = {}
                with patch("yuleosh.pipeline.step_handlers.test_integration.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="3 passed, 0 failed in 0.5s\n",
                        stderr="",
                        returncode=0,
                    )
                    result = step_integration_test(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert report["test_runner"] == "pytest-integration"
                    assert report["status"] == "passed"
                    assert report["passed"] == 3

    def test_pytest_runner_failure(self, mock_session, spec_file):
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.test_integration._parse_scenarios") as mock_parse:
            mock_parse.return_value = []
            with patch("yuleosh.pipeline.step_handlers.test_integration._parse_spec") as mock_spec:
                mock_spec.return_value = {}
                with patch("yuleosh.pipeline.step_handlers.test_integration.subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(
                        stdout="2 passed, 1 failed in 0.5s\n",
                        stderr="",
                        returncode=1,
                    )
                    result = step_integration_test(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert report["status"] == "failed"
                    assert report["failed"] == 1

    def test_pytest_timeout(self, mock_session, spec_file):
        """pytest timeout should be handled."""
        mock_session.spec_path = str(spec_file)

        with patch("yuleosh.pipeline.step_handlers.test_integration._parse_scenarios") as mock_parse:
            mock_parse.return_value = []
            with patch("yuleosh.pipeline.step_handlers.test_integration._parse_spec") as mock_spec:
                mock_spec.return_value = {}
                with patch("yuleosh.pipeline.step_handlers.test_integration.subprocess.run") as mock_run:
                    import subprocess
                    mock_run.side_effect = subprocess.TimeoutExpired("pytest", 180)
                    result = step_integration_test(mock_session)
                    with open(result) as f:
                        report = json.load(f)
                    assert report["test_runner"] == "pytest-integration-timeout"
                    assert "TIMEOUT" in report["output"]

    def test_go_runner(self, mock_session, spec_file, tmp_path):
        """Go test runner as fallback."""
        mock_session.spec_path = str(spec_file)
        proj_dir = tmp_path / "go_proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "go.mod").write_text("module test\n")
        # Create tests dir so pytest block enters (and consumes FileNotFoundError)
        (proj_dir / "tests").mkdir(exist_ok=True)
        mock_session.session_dir = tmp_path / "session2"
        mock_session.session_dir.mkdir(exist_ok=True)

        with patch("yuleosh.pipeline.step_handlers.test_integration._parse_scenarios") as mock_parse:
            mock_parse.return_value = []
            with patch("yuleosh.pipeline.step_handlers.test_integration._parse_spec") as mock_spec:
                mock_spec.return_value = {}
                with patch("yuleosh.pipeline.step_handlers.test_integration.os.environ.get", return_value=str(proj_dir)):
                    with patch("yuleosh.pipeline.step_handlers.test_integration.subprocess.run") as mock_run:
                        # First call (pytest) raises FileNotFoundError, second (go) succeeds
                        mock_run.side_effect = [
                            FileNotFoundError("pytest not found"),
                            MagicMock(stdout="ok  github.com/example/pkg\n", stderr="", returncode=0),
                        ]
                        result = step_integration_test(mock_session)
                        with open(result) as f:
                            report = json.load(f)
                        assert report["test_runner"] == "go-integration"
                        assert report["passed"] == 1
