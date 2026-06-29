# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.pipeline.step_handlers.review_code — step_review_code."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_code import step_review_code


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session(tmp_path):
    """Build a minimal PipelineSession with a temp project structure."""
    spec_file = tmp_path / "test_spec.md"
    spec_file.write_text("# Test Spec\nReq-001: shall blink LED\n")

    session = PipelineSession(
        name="test-code-review",
        spec_path=str(spec_file),
    )
    session.session_dir = tmp_path / ".osh" / "sessions" / "test-code-review"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _setup_codebase(base: Path):
    """Create a minimal source tree for code review."""
    src = base / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "main.py").write_text(
        "import os\nimport sys\n\n"
        "def main():\n"
        "    x = 42\n"
        "    print('hello')\n"
        "    return x\n"
    )
    (src / "driver.py").write_text(
        "class Driver:\n"
        "    def init(self):\n"
        "        pass\n"
        "    def read(self):\n"
        "        return 0\n"
    )


def _setup_artifact(session, key: str, content: str):
    """Place an artifact file and register it in the session."""
    art_path = session.session_dir / f"{key}.md"
    art_path.write_text(content)
    session.artifacts[key] = str(art_path)
    session.set_artifact(key, str(art_path))


def _fake_llm_ok() -> dict:
    """Return a realistic valid LLM review response as JSON within markdown."""
    review = {
        "status": "passed",
        "findings": [
            {"severity": "minor", "category": "style",
             "file": "src/main.py", "line": 3, "message": "Missing docstring"},
        ],
        "finding_breakdown": {"critical": 0, "major": 0, "minor": 1, "info": 0},
        "test_blind_spots": ["Error handling in main()"],
        "summary": "Code is mostly clean with minor style issues.",
    }
    return {
        "content": f"```json\n{json.dumps(review)}\n```",
        "usage": {"total_tokens": 800, "prompt_tokens": 600, "completion_tokens": 200},
        "model": "test-model",
    }


def _fake_llm_fail() -> dict:
    """Return an LLM response with failures."""
    review = {
        "status": "failed",
        "findings": [
            {"severity": "critical", "category": "error-handling",
             "file": "src/main.py", "line": 5, "message": "Unhandled exception"},
            {"severity": "major", "category": "consistency",
             "file": "src/driver.py", "line": 2, "message": "Deviates from arch"},
        ],
        "finding_breakdown": {"critical": 1, "major": 1, "minor": 0, "info": 0},
        "test_blind_spots": ["Edge cases in driver.read()"],
        "summary": "Found critical issues requiring fixes.",
    }
    return {
        "content": f"```json\n{json.dumps(review)}\n```",
        "usage": {"total_tokens": 900, "prompt_tokens": 600, "completion_tokens": 300},
        "model": "test-model",
    }


# =============================================================================
# Tests
# =============================================================================

class TestStepReviewCode:
    """Test suite for step_review_code — AI-powered code implementation review."""

    # ── Happy path ──────────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_happy_path_passed(self, mock_environ, mock_call_llm,
                                mock_session, tmp_path):
        """GIVEN a project with source code and artifacts
           WHEN step_review_code runs with passing review
           THEN it returns a JSON report with 'passed' status."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture",
                        "# Architecture\n## Layers\n- HAL\n- App")
        _setup_artifact(mock_session, "development",
                        "# Dev Plan\n## Tasks\n- T1: implement HAL")

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)

        report_path = Path(result)
        assert report_path.name == "internal-code-review.json"
        report = json.loads(report_path.read_text())
        assert report["status"] == "passed"
        assert report["reviewer"] == "小克"
        assert len(report["findings"]) == 1

    # ── LLM returns failures ────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_llm_returns_failures(self, mock_environ, mock_call_llm,
                                   mock_session, tmp_path):
        """GIVEN the LLM review finds critical issues
           WHEN step_review_code processes the response
           THEN the report shows 'failed' status with findings."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = _fake_llm_fail()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())

        assert report["status"] == "failed"
        assert len(report["findings"]) == 2
        assert report["finding_breakdown"]["critical"] == 1
        assert report["finding_breakdown"]["major"] == 1

    # ── LLM call fails ──────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_llm_call_failure(self, mock_environ, mock_call_llm,
                               mock_session, tmp_path):
        """GIVEN the LLM call raises an exception
           WHEN step_review_code runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        mock_call_llm.side_effect = RuntimeError("API error")

        with pytest.raises(PipelineStepError, match="LLM call failed"):
            step_review_code(mock_session)

    # ── No architecture/development artifacts ───────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_no_artifacts(self, mock_environ, mock_call_llm,
                           mock_session, tmp_path):
        """GIVEN no architecture or development artifacts exist
           WHEN step_review_code runs
           THEN it still proceeds with empty strings for artifact content."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        # No artifacts set up

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] in ("passed",)

    # ── Spec file not found ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_spec_file_missing(self, mock_environ, mock_call_llm,
                                mock_session, tmp_path):
        """GIVEN the spec file does not exist on disk
           WHEN step_review_code runs
           THEN it uses a placeholder and proceeds."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        Path(mock_session.spec_path).unlink()

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] == "passed"

    # ── Output write error ──────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_output_write_error(self, mock_environ, mock_call_llm,
                                 mock_session, tmp_path):
        """GIVEN writing the review output file fails
           WHEN step_review_code runs
           THEN it raises PipelineStepError."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        mock_call_llm.return_value = _fake_llm_ok()

        # Make the session dir unwritable
        mock_session.session_dir = tmp_path / "nonexistent" / "deep"

        with pytest.raises(PipelineStepError):
            step_review_code(mock_session)

    # ── Token usage tracked ─────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_token_usage_tracked(self, mock_environ, mock_call_llm,
                                  mock_session, tmp_path):
        """GIVEN LLM usage info is returned
           WHEN step_review_code completes
           THEN session token totals are updated."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = _fake_llm_ok()

        step_review_code(mock_session)

        assert mock_session.token_usage_total > 0
        assert any(s["step"] == "internal-code-review"
                   for s in mock_session.token_usage_steps)

    # ── Malformed LLM response ──────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_malformed_llm_response(self, mock_environ, mock_call_llm,
                                     mock_session, tmp_path):
        """GIVEN the LLM returns non-JSON text
           WHEN step_review_code parses the response
           THEN it falls back to _try_parse_hermes_json and produces a retry report."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = {
            "content": "This is not JSON at all. Just some text.",
            "usage": {"total_tokens": 100},
            "model": "test",
        }

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())

        # Should have defaults filled in
        assert "reviewer" in report
        assert "step" in report
        assert "session" in report

    # ── Source code scanning ────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_source_files_scanned(self, mock_environ, mock_call_llm,
                                   mock_session, tmp_path):
        """GIVEN a project with multiple source files
           WHEN step_review_code builds the prompt
           THEN the source file info is included for LLM analysis."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)

        mock_call_llm.return_value = _fake_llm_ok()

        step_review_code(mock_session)

        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        assert "src/main.py" in user_prompt
        assert "src/driver.py" in user_prompt

    # ── Multi-language source files ─────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_multi_language_source_files(self, mock_environ, mock_call_llm,
                                          mock_session, tmp_path):
        """GIVEN source files in multiple languages (.c, .go, .js)
           WHEN step_review_code scans the project
           THEN all relevant file types are discovered."""
        mock_environ.get.return_value = str(tmp_path)
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "main.c").write_text("int main() { return 0; }")
        (src / "app.go").write_text("package main")
        (src / "ui.js").write_text("function render() {}")

        mock_call_llm.return_value = _fake_llm_ok()

        step_review_code(mock_session)

        call_args = mock_call_llm.call_args
        _, _, user_prompt = call_args[0]
        assert "main.c" in user_prompt
        assert "app.go" in user_prompt
        assert "ui.js" in user_prompt

    # ── No src directory ────────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_no_src_directory(self, mock_environ, mock_call_llm,
                               mock_session, tmp_path):
        """GIVEN no src/ directory exists
           WHEN step_review_code runs
           THEN it proceeds with an empty source file list."""
        mock_environ.get.return_value = str(tmp_path)
        # No src/ created

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["status"] == "passed"

    # ── Test blind spots in report ──────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_test_blind_spots_in_report(self, mock_environ, mock_call_llm,
                                         mock_session, tmp_path):
        """GIVEN the LLM identifies test blind spots
           WHEN step_review_code processes the response
           THEN blind spots are included in the output report."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())

        assert "test_blind_spots" in report
        assert len(report["test_blind_spots"]) >= 1

    # ── Finding breakdown accuracy ──────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_finding_breakdown_accuracy(self, mock_environ, mock_call_llm,
                                         mock_session, tmp_path):
        """GIVEN the LLM response has findings at various severities
           WHEN step_review_code parses the response
           THEN the finding_breakdown matches the actual findings."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = _fake_llm_fail()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())

        findings = report["findings"]
        expected = {"critical": 0, "major": 0, "minor": 0, "info": 0}
        for f in findings:
            sev = f["severity"]
            if sev in expected:
                expected[sev] += 1
        assert report["finding_breakdown"] == expected

    # ── Exception wrapping ──────────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_general_exception_wrapping(self, mock_environ, mock_session):
        """GIVEN an unexpected exception in the handler
           WHEN step_review_code runs
           THEN it is wrapped in PipelineStepError."""
        mock_environ.get.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(PipelineStepError, match="Code review step failed"):
            step_review_code(mock_session)

    # ── Session name in report ──────────────────────────────────────────────

    @patch("yuleosh.pipeline.step_handlers.review_code._call_llm")
    @patch("yuleosh.pipeline.step_handlers.review_code.os.environ")
    def test_session_name_in_report(self, mock_environ, mock_call_llm,
                                     mock_session, tmp_path):
        """GIVEN a session with a specific name
           WHEN step_review_code runs
           THEN the report contains the session name."""
        mock_environ.get.return_value = str(tmp_path)
        _setup_codebase(tmp_path)
        _setup_artifact(mock_session, "architecture", "# Arch")

        mock_call_llm.return_value = _fake_llm_ok()

        result = step_review_code(mock_session)
        report = json.loads(Path(result).read_text())
        assert report["session"] == mock_session.name
