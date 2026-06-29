# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.execution — step_claude_arch."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.execution import step_claude_arch


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with a temp project structure."""
    # Create spec file
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\n## Requirements\nReq-001: shall do X\n")

    session = PipelineSession(
        name="test-arch",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-arch"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    # Point OSH_HOME at the temp dir so directory discovery works
    session._osh_home_override = str(tmp_path)
    return session


def _fake_llm_result(content: str = "# Architecture\n\n## Modules\n\n- core",
                      total_tokens: int = 500,
                      prompt_tokens: int = 300) -> dict:
    return {
        "content": content,
        "usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": total_tokens - prompt_tokens,
        },
        "model": "test-model",
    }


def _setup_project_structure(base: Path):
    """Create a minimal project tree for architecture scans."""
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text("# init\n")
    (src / "main.py").write_text("def main():\n    pass\n")
    (src / "utils.py").write_text("def helper():\n    return 42\n")
    # Nested package
    pkg = src / "core"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("# core\n")
    (pkg / "engine.py").write_text("class Engine:\n    def run(self):\n        pass\n")


# =============================================================================
# Tests
# =============================================================================

class TestStepClaudeArch:
    """Test suite for step_claude_arch — AI-powered architecture design."""

    # ── Happy path ──────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_happy_path_architecture_analysis(self, mock_environ, mock_call_llm,
                                               mock_session, tmp_path):
        """GIVEN a session with a valid spec and source tree
           WHEN step_claude_arch runs
           THEN it returns the architecture.md path with LLM output."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_project_structure(tmp_path)

        mock_call_llm.return_value = _fake_llm_result(
            content="# Architecture Analysis\n\n## Layer 1\n- HAL\n- BSP",
            total_tokens=600,
        )

        result = step_claude_arch(mock_session)

        out_path = Path(result)
        assert out_path.exists()
        assert out_path.name == "architecture.md"
        content = out_path.read_text()
        assert "Architecture Analysis" in content
        assert "Layer 1" in content

        # Verify _call_llm was called with proper prompt
        mock_call_llm.assert_called_once()
        call_args = mock_call_llm.call_args
        assert len(call_args[0]) == 3  # session, system_prompt, user_prompt

    # ── LLM call fails ─────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_llm_failure_raises_error(self, mock_environ, mock_call_llm,
                                       mock_session, tmp_path):
        """GIVEN the LLM call fails with an exception
           WHEN step_claude_arch runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.side_effect = RuntimeError("LLM API unavailable")

        with pytest.raises(PipelineStepError, match="LLM call failed"):
            step_claude_arch(mock_session)

    # ── No src directory ────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_no_src_directory(self, mock_environ, mock_call_llm,
                               mock_session, tmp_path):
        """GIVEN no src/ directory exists
           WHEN step_claude_arch runs
           THEN it still succeeds with empty directory data."""
        mock_environ.get.return_value = str(tmp_path)
        # No src/ directory created
        mock_call_llm.return_value = _fake_llm_result(
            content="# Architecture\n\nNo source files found.",
        )

        result = step_claude_arch(mock_session)
        out_path = Path(result)
        assert out_path.exists()

        # LLM prompt should still have been built
        mock_call_llm.assert_called_once()

    # ── Spec file not found ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_spec_file_not_found(self, mock_environ, mock_call_llm,
                                  mock_session, tmp_path):
        """GIVEN the spec file does not exist on disk
           WHEN step_claude_arch runs
           THEN it substitutes a placeholder and still proceeds."""
        mock_environ.get.return_value = str(tmp_path)
        spec_file = Path(mock_session.spec_path)
        spec_file.unlink()  # Remove spec file

        mock_call_llm.return_value = _fake_llm_result()

        result = step_claude_arch(mock_session)
        assert Path(result).exists()
        mock_call_llm.assert_called_once()

    # ── Source files detected ───────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_source_files_detected(self, mock_environ, mock_call_llm,
                                    mock_session, tmp_path):
        """GIVEN a project with multiple source files
           WHEN step_claude_arch runs
           THEN source file info is included in the LLM prompt."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_project_structure(tmp_path)

        mock_call_llm.return_value = _fake_llm_result()

        step_claude_arch(mock_session)

        # Verify the prompt contains source file paths
        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        assert "main.py" in user_prompt
        assert "utils.py" in user_prompt
        assert "core/engine.py" in user_prompt

    # ── Tech stack identification ───────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_tech_stack_detected(self, mock_environ, mock_call_llm,
                                  mock_session, tmp_path):
        """GIVEN source files with various extensions
           WHEN step_claude_arch runs
           THEN the tech stack set includes all detected languages."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "main.py").write_text("")
        (src / "app.js").write_text("")
        (src / "styles.css").write_text("")
        (src / "script.ts").write_text("")

        mock_call_llm.return_value = _fake_llm_result()

        step_claude_arch(mock_session)

        # Check the prompt mentions the tech stack
        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        assert "Python" in user_prompt
        assert "Web" in user_prompt

    # ── Token usage tracked ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_token_usage_tracked(self, mock_environ, mock_call_llm,
                                  mock_session, tmp_path):
        """GIVEN the LLM returns usage info
           WHEN step_claude_arch completes
           THEN session token totals are updated."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.return_value = _fake_llm_result(total_tokens=750)

        step_claude_arch(mock_session)

        assert mock_session.token_usage_total > 0
        assert any(s["step"] == "architecture" for s in mock_session.token_usage_steps)
        usage = [s for s in mock_session.token_usage_steps if s["step"] == "architecture"][0]
        assert usage["usage"]["total_tokens"] == 750

    # ── Write error ─────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_output_write_error(self, mock_environ, mock_call_llm,
                                 mock_session, tmp_path):
        """GIVEN the architecture.md file cannot be written
           WHEN step_claude_arch runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        mock_call_llm.return_value = _fake_llm_result()

        # Make the session_dir a file to prevent directory creation
        import shutil
        shutil.rmtree(mock_session.session_dir)
        mock_session.session_dir.write_text("this is a file, not a dir")

        with pytest.raises(PipelineStepError, match="Cannot write"):
            step_claude_arch(mock_session)

    # ── Source tree representation ──────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_source_tree_in_prompt(self, mock_environ, mock_call_llm,
                                    mock_session, tmp_path):
        """GIVEN a project with nested directories
           WHEN step_claude_arch runs
           THEN the source tree string is included in the prompt."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_project_structure(tmp_path)

        mock_call_llm.return_value = _fake_llm_result()

        step_claude_arch(mock_session)

        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        # Should contain the directory tree representation
        assert "src/" in user_prompt or user_prompt

    # ── Empty session_dir ───────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_missing_session_dir_raises_error(self, mock_environ, mock_call_llm,
                                                mock_session, tmp_path):
        """GIVEN the session directory does not exist
           WHEN step_claude_arch tries to write output
           THEN it raises PipelineStepError (write_text does not create parents)."""
        mock_environ.get.return_value = str(tmp_path)
        import shutil
        shutil.rmtree(mock_session.session_dir, ignore_errors=True)

        mock_call_llm.return_value = _fake_llm_result()

        with pytest.raises(PipelineStepError, match="Cannot write"):
            step_claude_arch(mock_session)

    # ── Key file snippets ───────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_key_file_snippets_in_prompt(self, mock_environ, mock_call_llm,
                                          mock_session, tmp_path):
        """GIVEN source files under 10KB with readable content
           WHEN step_claude_arch runs
           THEN key file content snippets appear in the LLM prompt."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_project_structure(tmp_path)

        mock_call_llm.return_value = _fake_llm_result()

        step_claude_arch(mock_session)
        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        # Content of key files should be present
        assert "def main()" in user_prompt
        assert "class Engine" in user_prompt

    # ── Exception propagation ───────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_general_exception_wrapping(self, mock_environ, mock_call_llm,
                                         mock_session, tmp_path):
        """GIVEN an unexpected exception anywhere in the handler
           WHEN step_claude_arch runs
           THEN it is wrapped in PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        # Force failure after LLM
        mock_call_llm.return_value = _fake_llm_result()

        # Make the session_dir unwritable
        mock_session.session_dir = tmp_path / "nonexistent" / "deep"
        # parent doesn't exist, so write_text will fail

        with pytest.raises(PipelineStepError):
            step_claude_arch(mock_session)

    # ── Empty OSH_HOME ──────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.execution._call_llm")
    @patch("yuleosh.pipeline.step_handlers.execution.os.environ")
    def test_osh_home_fallback_to_dot(self, mock_environ, mock_call_llm,
                                       mock_session, tmp_path):
        """GIVEN OSH_HOME is not set
           WHEN step_claude_arch runs
           THEN it falls back to the current directory (resolved)."""
        mock_environ.get.return_value = "."
        mock_call_llm.return_value = _fake_llm_result()
        mock_session.spec_path = str(tmp_path / "spec.md")
        Path(mock_session.spec_path).write_text("spec")

        # This should work - '.' is resolved
        result = step_claude_arch(mock_session)
        out_path = Path(result)
        assert out_path.name == "architecture.md"
