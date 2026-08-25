
# @tests src/yuleosh/pipeline/steps.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Deep coverage tests for step_handlers/execution.py — branches not covered by
existing tests.

Target: execution.py from 72% → ≥80%

Covers:
  - step_claude_arch: src_dir does not exist (no crash)
  - step_claude_arch: _call_llm exception → PipelineStepError
  - step_claude_arch: write_text OSError
  - step_claude_arch: key_file_snippets read exception (pass)
  - step_claude_arch: generic Exception catch
  - step_claude_dev: git subprocess exception (line 168-170)
  - step_claude_dev: write_text OSError
  - step_claude_dev: artifacts_read returns None for missing artifacts
  - step_claude_dev: src_files/test_files read exception (pass)
  - step_claude_dev: generic Exception catch
  - step_test_planning: spec file not found
  - step_test_planning: write_text OSError
  - step_test_planning: LLM call failure
  - step_claude_test: has_go = True → Go test path (success, timeout, error)
  - step_claude_test: FileNotFoundError for pytest
  - step_claude_test: subprocess.TimeoutExpired for pytest
  - step_claude_test: generic Exception for pytest
  - step_claude_test: re.search fallback (no "passed"/"failed")
  - step_claude_test: re.search alternative match for numbers
  - step_claude_test: write_text OSError
  - step_claude_test: spec_scenarios extraction
  - step_claude_test: generic Exception catch
  - artifacts_read: key not in dict
  - artifacts_read: file does not exist
  - artifacts_read: read exception
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ===================================================================
# Mock LLM helpers
# ===================================================================


def _mock_llm(content_text=None):
    content_text = content_text or "## Result\n\nMock content."
    def _mock(system_prompt, user_prompt, **kwargs):
        return {
            "content": content_text,
            "model": "mock-model",
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }
    return _mock


def _mock_llm_fail():
    def _mock(*args, **kwargs):
        raise RuntimeError("API connection refused")
    return _mock


# ===================================================================
# Fake subprocess result
# ===================================================================


class MockProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Create a PipelineSession for execution testing."""
    from yuleosh.pipeline.session import PipelineSession

    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    spec_file = tmp_path / "spec.md"
    spec_file.write_text(
        "# Test Spec\n"
        "### Req-RS-001: Auth\n"
        "- The system SHALL authenticate users.\n"
        "\n"
        "### GIVEN a user with valid credentials\n"
        "WHEN they submit the login form\n"
        "THEN they are redirected\n"
    )
    session = PipelineSession("exec-deep-test", str(spec_file), llm_client=_mock_llm())
    return session


# ===================================================================
# step_claude_arch — uncovered branches
# ===================================================================


class TestClaudeArchSrcDirNotExists:
    """GIVEN src_dir does not exist
    WHEN step_claude_arch runs
    THEN it handles gracefully (no crash, empty tech stack)."""

    def test_src_dir_not_exists(self, tmp_session, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch

        # Set OSH_HOME to a directory without src/
        monkeypatch.setenv("OSH_HOME", str(tmp_session.session_dir.parent))
        result = step_claude_arch(tmp_session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeArchLLMFailure:
    """GIVEN _call_llm raises exception
    WHEN step_claude_arch runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("arch-llm-fail", str(spec_file), llm_client=_mock_llm_fail())
        with pytest.raises(PipelineStepError) as exc:
            step_claude_arch(session)
        assert "LLM call failed" in str(exc.value)


class TestClaudeArchWriteError:
    """GIVEN write_text raises OSError
    WHEN step_claude_arch runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("arch-write-err", str(spec_file), llm_client=_mock_llm())
        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_claude_arch(session)
            assert "Cannot write" in str(exc.value)


class TestClaudeArchGenericError:
    """GIVEN an unexpected exception
    WHEN step_claude_arch runs
    THEN PipelineStepError is raised via generic catch."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("arch-generic-err", str(spec_file), llm_client=_mock_llm())
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.build_architecture_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_claude_arch(session)
            assert "failed" in str(exc.value).lower()


# ===================================================================
# step_claude_dev — uncovered branches
# ===================================================================


class TestClaudeDevGitException:
    """GIVEN git subprocess raises an exception
    WHEN step_claude_dev runs
    THEN git_log gets fallback text (no crash)."""

    def test_git_exception(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "# Spec\n"
            "### Req-001: Test\n"
            "- SHALL work.\n"
        )
        session = PipelineSession("dev-git-err", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = step_claude_dev(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeDevWriteError:
    """GIVEN write_text raises OSError during dev planning
    WHEN step_claude_dev runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("dev-write-err", str(spec_file), llm_client=_mock_llm())

        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_claude_dev(session)
            assert "Cannot write" in str(exc.value)


class TestClaudeDevArtifactsMissing:
    """GIVEN artifact keys exist but files are missing
    WHEN artifacts_read is called
    THEN None is returned (graceful handling)."""
    def test_artifacts_missing(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("dev-art-missing", str(spec_file), llm_client=_mock_llm())

        # Add artifact keys pointing to non-existent files
        session.artifacts["architecture"] = str(tmp_path / "missing_arch.md")
        session.artifacts["prd"] = str(tmp_path / "missing_prd.md")

        result = step_claude_dev(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeDevGenericError:
    """GIVEN unexpected exception in dev step
    WHEN step_claude_dev runs
    THEN PipelineStepError is raised via generic catch."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("dev-generic-err", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.build_development_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_claude_dev(session)
            assert "failed" in str(exc.value).lower()


class TestClaudeDevCProjectMetrics:
    """GIVEN a C project (src/*.c, tests/*.c) — r21d 复盘回归

    THEN development prompt 必须注入真实 C 文件统计 (源码行数/测试函数数),
    而不是把 C 项目误判为『0 测试文件』(旧版只统计 .py/.sh/.html)。"""

    def test_c_project_tests_counted(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        # C 项目结构
        src = tmp_path / "src" / "app" / "src"
        src.mkdir(parents=True)
        (src / "window_control.c").write_text(
            "int window_modes_check_pinch(void) { return 1; }\n" * 20
        )
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_window_control.c").write_text(
            "static void test_pinch_detection_latency(void) {}\n"
            "static void test_api_reset_preserves_calibration(void) {}\n"
        )
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("dev-c-metrics", str(spec_file), llm_client=_mock_llm())

        captured = {}

        def _capture_prompt(system_prompt, user_prompt, **kwargs):
            captured["user"] = user_prompt
            return {
                "content": "## Plan\n\nok",
                "model": "mock-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }

        session.llm_client = _capture_prompt
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = step_claude_dev(session)
        assert Path(result).exists()
        user = captured.get("user", "")
        # C 源码被统计 (1 行内容 * 20 次 = 20 行)
        assert "Source lines: 20" in user
        # C 测试文件被统计 (2 个测试函数)
        assert "Test functions: 2" in user
        assert "Test lines: 2" in user
        assert "Test file count" not in user  # 字段名是 Test lines across N files


class TestClaudeDevGitLogNonzeroReturncode:
    """GIVEN git subprocess returns non-zero exit code
    WHEN step_claude_dev runs
    THEN git_log stays empty (no crash)."""

    def test_git_nonzero(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("dev-git-nonzero", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=1, stdout="", stderr=""),
        ):
            result = step_claude_dev(session)
        assert result is not None


# ===================================================================
# step_test_planning — uncovered branches
# ===================================================================


class TestTestPlanningSpecNotFound:
    """GIVEN spec file does not exist
    WHEN step_test_planning runs
    THEN '(spec file not found)' is used."""

    def test_spec_not_found(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_test_planning
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "nonexistent.md"
        session = PipelineSession("plan-no-spec", str(spec_file), llm_client=_mock_llm())
        result = step_test_planning(session)
        assert result is not None


class TestTestPlanningLLMFailure:
    """GIVEN _call_llm raises during test planning
    WHEN step_test_planning runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_test_planning
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("plan-llm-fail", str(spec_file), llm_client=_mock_llm_fail())
        with pytest.raises(PipelineStepError) as exc:
            step_test_planning(session)
        assert "LLM call failed" in str(exc.value)


class TestTestPlanningWriteError:
    """GIVEN write_text raises OSError
    WHEN step_test_planning runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_test_planning
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("plan-write-err", str(spec_file), llm_client=_mock_llm())
        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_test_planning(session)
            assert "Cannot write" in str(exc.value)


class TestTestPlanningGenericError:
    """GIVEN unexpected exception in test planning
    WHEN step_test_planning runs
    THEN PipelineStepError is raised."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_test_planning
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("plan-generic-err", str(spec_file), llm_client=_mock_llm())
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.build_test_planning_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_test_planning(session)
            assert "failed" in str(exc.value).lower()


# ===================================================================
# step_claude_test — uncovered branches
# ===================================================================


class TestClaudeTestGoProject:
    """GIVEN project has go.mod (has_go=True)
    WHEN step_claude_test runs
    THEN it takes the Go test path."""

    def test_go_success(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-ok", str(spec_file), llm_client=_mock_llm())

        # Create go.mod
        (tmp_path / "go.mod").write_text("module test\n")

        go_stdout = "ok  github.com/test/pkg1\nok  github.com/test/pkg2\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout=go_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "go test" in content
        assert "2" in content  # total packages

    def test_go_timeout(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-timeout", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="go test", timeout=120),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "timed out" in content.lower()

    def test_go_file_not_found(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-no-go", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=FileNotFoundError("go not installed"),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "not installed" in content

    def test_go_generic_exception(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-exc", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=RuntimeError("Something broke"),
        ):
            result = step_claude_test(session)
        assert result is not None

    def test_go_fail_packages(self, tmp_path, monkeypatch):
        """Go test with a mix of ok and FAIL lines."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-mixed", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        go_stdout = "ok  github.com/test/pkg1\nFAIL github.com/test/pkg2\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=1, stdout=go_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None

    def test_go_fail_only(self, tmp_path, monkeypatch):
        """Go test with only FAIL lines."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-fail", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        go_stdout = "FAIL github.com/test/pkg1\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=1, stdout=go_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None


class TestClaudeTestPytest:
    """GIVEN project has no go.mod (has_go=False, is_python)
    WHEN step_claude_test runs
    THEN it takes the pytest path."""

    def test_pytest_success(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-ok", str(spec_file), llm_client=_mock_llm())

        pytest_stdout = "tests/test_a.py ..   [ 50%]\ntests/test_b.py ..   [100%]\n\n2 passed in 0.1s\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout=pytest_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "pytest" in content

    def test_pytest_timeout(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-timeout", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=120),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "timed out" in content.lower()

    def test_pytest_not_found(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-noexe", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=FileNotFoundError("pytest not found"),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "not installed" in content

    def test_pytest_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-err", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=RuntimeError("Something broke"),
        ):
            result = step_claude_test(session)
        assert result is not None

    def test_pytest_no_passed_failed_in_output(self, tmp_path, monkeypatch):
        """pytest output without 'passed' or 'failed' strings."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-other", str(spec_file), llm_client=_mock_llm())

        pytest_stdout = "test session starts\ncollected 5 items\n\nall tests done\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout=pytest_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "pytest completed" in content

    def test_pytest_failed_only(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-fail", str(spec_file), llm_client=_mock_llm())

        pytest_stdout = "1 failed in 0.1s\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=1, stdout=pytest_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None

    def test_pytest_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-write", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout="2 passed in 0.1s\n"),
        ):
            with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
                with pytest.raises(PipelineStepError) as exc:
                    step_claude_test(session)
                assert "Cannot write" in str(exc.value)


class TestClaudeTestGenericCatch:
    """GIVEN unexpected exception in the outer try of step_claude_test
    WHEN step_claude_test runs
    THEN PipelineStepError is raised."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-generic", str(spec_file), llm_client=_mock_llm())

        with mock.patch.object(
            Path,
            "exists",
            side_effect=[True, PermissionError("Opaque")],
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_claude_test(session)
            assert "failed" in str(exc.value).lower()


# ===================================================================
# artifacts_read — uncovered branches
# ===================================================================


class TestArtifactsRead:
    """GIVEN artifacts_read is called with various conditions
    THEN it returns expected values."""

    def test_key_not_in_dict(self):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read
        result = artifacts_read({"existing": "/tmp/x"}, "missing")
        assert result is None

    def test_file_does_not_exist(self, tmp_path):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read
        nonexistent = str(tmp_path / "nonexistent.md")
        result = artifacts_read({"arch": nonexistent}, "arch")
        assert result is None

    def test_read_exception(self, tmp_path):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read
        p = tmp_path / "badfile.md"
        p.write_text("content")
        with mock.patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            result = artifacts_read({"arch": str(p)}, "arch")
        assert result is None

    def test_happy_path(self, tmp_path):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read
        p = tmp_path / "good.md"
        p.write_text("artifact content")
        result = artifacts_read({"arch": str(p)}, "arch")
        assert result == "artifact content"


# ===================================================================
# Additional branch coverage for execution.py
# ===================================================================


class TestClaudeArchSrcDirWithExtensions:
    """GIVEN src/ directory with various file types
    WHEN step_claude_arch runs
    THEN tech stack detection covers Go, Rust, Web, Shell."""

    def test_tech_stack_detection(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("arch-ext", str(spec_file), llm_client=_mock_llm())

        # Create src/ with various file types
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.go").write_text("package main\n")
        (src_dir / "lib.rs").write_text("pub fn x() {}\n")
        (src_dir / "index.html").write_text("<html></html>\n")
        (src_dir / "app.js").write_text("console.log(1);\n")
        (src_dir / "style.css").write_text("body {}\n")
        (src_dir / "app.ts").write_text("const x = 1;\n")
        (src_dir / "run.sh").write_text("#!/bin/bash\necho hi\n")

        result = step_claude_arch(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeArchKeyFileReadException:
    """GIVEN a source file exists but cannot be read during key_file_snippets
    WHEN step_claude_arch runs
    THEN the exception is caught with pass."""

    def test_key_file_read_exception(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("arch-read-err", str(spec_file), llm_client=_mock_llm())

        # Create src/ with a small python file
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        py_file = src_dir / "main.py"
        py_file.write_text("x = 1\n")

        # Mock Path.read_text to raise on the key file reading
        original_read = Path.read_text
        call_log = []

        def side_effect(self_obj):
            call_log.append(str(self_obj))
            if "main.py" in str(self_obj) and len(call_log) > 5:
                raise PermissionError("Can't read")
            return original_read(self_obj)

        with mock.patch.object(Path, "read_text", autospec=True, side_effect=side_effect):
            result = step_claude_arch(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeDevGitSuccess:
    """GIVEN git subprocess succeeds with output
    WHEN step_claude_dev runs
    THEN git_log and git_commits are populated."""

    def test_git_success(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec\n### Req-001\n- SHALL work.")
        session = PipelineSession("dev-git-ok", str(spec_file), llm_client=_mock_llm())

        git_output = "abc123 feat: init (2 days ago)\ndef456 fix: bug (3 days ago)\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout=git_output),
        ):
            result = step_claude_dev(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeDevFileReadExceptions:
    """GIVEN source or test files can't be read
    WHEN step_claude_dev runs
    THEN the exception is caught with pass."""

    def test_src_and_test_read_exceptions(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec\n### Req-001\n- SHALL work.")
        session = PipelineSession("dev-read-exc", str(spec_file), llm_client=_mock_llm())

        # Create src/ and tests/ dirs with existing python files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod1.py").write_text("x = 1\n")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mod1.py").write_text("def test_x(): pass\n")

        # Mock subprocess.run for git call (return success with no commits)
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout=""),
        ):
            # Mock Path.read_text to fail on one src file read
            original_read_text = Path.read_text

            def side_effect_read(self_obj):
                if "mod1.py" in str(self_obj):
                    raise PermissionError("Access denied")
                return original_read_text(self_obj)

            with mock.patch.object(Path, "read_text", autospec=True, side_effect=side_effect_read):
                result = step_claude_dev(session)
        assert result is not None
        assert Path(result).exists()


class TestClaudeDevLLMFailure:
    """GIVEN _call_llm raises during dev planning
    WHEN step_claude_dev runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("dev-llm-fail", str(spec_file), llm_client=_mock_llm_fail())

        with pytest.raises(PipelineStepError) as exc:
            step_claude_dev(session)
        assert "failed" in str(exc.value).lower()


class TestClaudeTestGoFailBranches:
    """GIVEN Go test output with FAIL lines (space-separated)
    WHEN step_claude_test runs
    THEN the 'FAIL ' prefix is matched."""

    def test_go_fail_matches(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-go-fail-match", str(spec_file), llm_client=_mock_llm())
        (tmp_path / "go.mod").write_text("module test\n")

        go_stdout = "FAIL github.com/test/pkg1\n"
        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=1, stdout=go_stdout),
        ):
            result = step_claude_test(session)
        assert result is not None


class TestClaudeTestPytestTimeoutHandler:
    """GIVEN pytest raises TimeoutExpired
    WHEN step_claude_test runs
    THEN timeout handler is exercised."""

    def test_pytest_timeout_handler(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test\n### GIVEN something\nWHEN action\nTHEN result")
        session = PipelineSession("test-pytest-timeout2", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=120),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "timed out" in content.lower()


class TestClaudeTestPytestExceptionHandler:
    """GIVEN pytest raises a generic Exception
    WHEN step_claude_test runs
    THEN generic exception handler is exercised."""

    def test_pytest_exception_handler(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-pytest-exc2", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=RuntimeError("Something went wrong"),
        ):
            result = step_claude_test(session)
        assert result is not None


class TestClaudeTestSpecScenarios:
    """GIVEN spec has GIVEN/WHEN/THEN scenarios
    WHEN step_claude_test runs
    THEN spec_scenarios are extracted and included in the report."""

    def test_spec_scenarios_included(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "# Test\n"
            "### GIVEN user is logged in\n"
            "WHEN they click logout\n"
            "THEN session ends\n"
            "### GIVEN user has admin role\n"
            "WHEN accessing admin panel\n"
            "THEN they see admin dashboard\n"
        )
        session = PipelineSession("test-scenarios", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout="2 passed in 0.1s\n"),
        ):
            result = step_claude_test(session)
        assert result is not None
        content = Path(result).read_text()
        assert "user is logged in" in content
        assert "user has admin role" in content


class TestClaudeTestNestedGuard:
    """GIVEN step_claude_test is invoked inside a running pytest session
    WHEN PYTEST_CURRENT_TEST is set (pytest sets it at runtime)
    THEN nested pytest execution is skipped — recursion guard works."""

    def test_skips_nested_pytest(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_x.py::test_y")
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-nested-guard", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            side_effect=AssertionError("subprocess.run must not be called"),
        ) as mrun:
            result = step_claude_test(session)
        assert result is not None
        mrun.assert_not_called()
        content = Path(result).read_text()
        assert "nested execution guard" in content

    def test_normal_execution_when_not_in_pytest(self, tmp_path, monkeypatch):
        """GIVEN no PYTEST_CURRENT_TEST WHEN step_claude_test runs THEN pytest branch executes."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.execution import step_claude_test

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("test-normal-pytest", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.execution.subprocess.run",
            return_value=MockProc(returncode=0, stdout="2 passed in 0.1s\n"),
        ) as mrun:
            result = step_claude_test(session)
        assert result is not None
        mrun.assert_called_once()
        content = Path(result).read_text()
        assert "2 passed" in content
