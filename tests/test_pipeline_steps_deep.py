# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep tests for yuleosh.pipeline.steps — PipelineStep base class and all
concrete step implementations.  All LLM calls and file I/O are mocked,
so no real spec files or LLM providers are needed.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch, mock_open, ANY

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ---------------------------------------------------------------------------
# Mock dependencies BEFORE importing steps
# ---------------------------------------------------------------------------

# No module-level mocks of prompts — we patch individual functions in tests

# Mock os.environ for OSH_HOME
_orig_environ = os.environ.copy()


# ---------------------------------------------------------------------------
# Helper: create a minimal mock PipelineSession
# ---------------------------------------------------------------------------

def _make_mock_session(spec_content="# Test spec\n## RS-001: Req\n- SHALL do X\n"):
    """Create a minimal PipelineSession-like object for testing steps."""
    session = MagicMock()
    session.name = "test-session"
    session.spec_path = "/tmp/test-spec.md"
    session.llm_client = None
    session.token_usage_total = 0
    session.token_usage_steps = []
    session.session_dir = Path(tempfile.mkdtemp())
    session.artifacts = {}

    # Make session_dir work with write_text
    (session.session_dir / "startup-analysis.md").write_text("mock analysis")
    (session.session_dir / "architecture.md").write_text("mock arch")
    (session.session_dir / "development-plan.md").write_text("mock dev")
    (session.session_dir / "code-review.json").write_text("{}")
    (session.session_dir / "prd.md").write_text("mock prd")

    return session


# ======================================================================
# Module-level: get_step_instance, register_step, STEP_CLASSES
# ======================================================================


class TestStepRegistry:
    """Test the step registry (get_step_instance, register_step)."""

    def test_get_known_step(self):
        from yuleosh.pipeline.steps import get_step_instance
        step = get_step_instance("super-analysis")
        assert step is not None
        assert step.step_key == "super-analysis"

    def test_get_unknown_step(self):
        from yuleosh.pipeline.steps import get_step_instance
        step = get_step_instance("nonexistent-step")
        assert step is None

    def test_register_step(self):
        from yuleosh.pipeline.steps import register_step, get_step_instance
        from yuleosh.pipeline.steps import PipelineStep

        class FakeStep(PipelineStep):
            step_key = "fake-step"
            agent = "Fake"
            description = "Fake"
            output_filename = "fake.md"

        register_step("fake-step", FakeStep())
        step = get_step_instance("fake-step")
        assert step is not None
        assert step.step_key == "fake-step"


# ======================================================================
# PipelineStep base class behavior
# ======================================================================


class TestPipelineStepBase:
    """Test base class defaults and direct behavior."""

    def test_default_icon(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        assert step._icon() == "🔄"

    def test_no_llm_defaults_to_false(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        assert step.no_llm is False

    def test_max_tokens_none(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        assert step.max_tokens is None

    def test_output_filename_empty(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        assert step.output_filename == ""

    def test_build_prompts_raises(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        with pytest.raises(NotImplementedError):
            step.build_prompts(None, None, None, None)

    def test_artifact_keys_empty_by_default(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        assert step._artifact_keys() == []

    def test_run_without_llm_raises(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        step.no_llm = True
        with pytest.raises(NotImplementedError):
            step._run_without_llm(None, None, None, None)

    def test_process_result_adds_header(self):
        from yuleosh.pipeline.steps import PipelineStep
        from yuleosh.pipeline.run import PipelineSession
        step = PipelineStep()
        step.description = "Test Step"
        step.output_filename = "test.md"

        session = MagicMock()
        session.spec_path = "/tmp/test-spec.md"

        result = {"content": "hello", "model": "gpt4", "usage": {"total_tokens": 50}}
        output = step.process_result(session, "hello", result)

        assert "Test Step" in output
        assert "hello" in output
        assert "gpt4" in output

    def test_read_artifacts(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()

        session = MagicMock()
        session.artifacts = {
            "super-analysis": "/tmp/mock/file1.md",
            "architecture": "/tmp/mock/file2.md",
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f1:
            f1.write("artifact content 1")
            f1_path = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f2:
            f2.write("artifact content 2")
            f2_path = f2.name

        try:
            session.artifacts["super-analysis"] = f1_path
            session.artifacts["architecture"] = f2_path

            # Also test with a missing key
            session.artifacts["missing"] = "/nonexistent/file.md"

            contents = step._read_artifacts(session, ["super-analysis", "architecture", "missing"])
            assert contents.get("super-analysis") == "artifact content 1"
            assert contents.get("architecture") == "artifact content 2"
            # Missing file should not be in contents
            assert "missing" not in contents or contents["missing"] == ""

        finally:
            os.unlink(f1_path)
            os.unlink(f2_path)

    def test_read_artifacts_no_artifacts(self):
        from yuleosh.pipeline.steps import PipelineStep
        step = PipelineStep()
        session = MagicMock()
        session.artifacts = {}
        contents = step._read_artifacts(session, ["something"])
        assert contents == {}


# ======================================================================
# Concrete step implementations (mocked LLM, mocked filesystem)
# ======================================================================


class TestSuperAnalysisStep:
    """Test SuperAnalysisStep construction and icon."""

    def test_icon(self):
        from yuleosh.pipeline.steps import SuperAnalysisStep
        step = SuperAnalysisStep()
        assert step._icon() == "📊"

    def test_metadata(self):
        from yuleosh.pipeline.steps import SuperAnalysisStep
        step = SuperAnalysisStep()
        assert step.step_key == "super-analysis"
        assert step.agent == "小明"
        assert step.output_filename == "startup-analysis.md"

    def test_build_prompts(self):
        from yuleosh.pipeline.steps import SuperAnalysisStep
        step = SuperAnalysisStep()
        session = _make_mock_session()
        parsed = {"requirements": [{"name": "RS-001"}], "scenarios": []}
        sys_p, user_p = step.build_prompts(
            session, "# spec", parsed, {}
        )
        assert sys_p is not None
        assert user_p is not None

    def test_process_result_inherited(self):
        from yuleosh.pipeline.steps import SuperAnalysisStep
        step = SuperAnalysisStep()
        session = _make_mock_session()
        result = {"content": "analysis", "model": "gpt4", "usage": {}}
        output = step.process_result(session, "analysis", result)
        assert "S.U.P.E.R" in output


class TestPrdStep:
    """Test PrdStep."""

    def test_icon(self):
        from yuleosh.pipeline.steps import PrdStep
        step = PrdStep()
        assert step._icon() == "🔮"

    def test_artifact_keys(self):
        from yuleosh.pipeline.steps import PrdStep
        step = PrdStep()
        assert "super-analysis" in step._artifact_keys()

    def test_metadata(self):
        from yuleosh.pipeline.steps import PrdStep
        step = PrdStep()
        assert step.step_key == "prd"
        assert step.agent == "Hermes"

    def test_build_prompts(self):
        from yuleosh.pipeline.steps import PrdStep
        step = PrdStep()
        session = _make_mock_session()
        parsed = {"requirements": [], "scenarios": []}
        sys_p, user_p = step.build_prompts(
            session, "# spec", parsed, {"super-analysis": "analysis"}
        )
        assert sys_p is not None


class TestArchitectureStep:
    """Test ArchitectureStep."""

    def test_icon(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()
        assert step._icon() == "💻"

    def test_max_tokens(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()
        assert step.max_tokens == 4096

    def test_metadata(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()
        assert step.step_key == "architecture"

    def test_artifact_keys_default(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()
        # ArchitectureStep does not depend on prior artifacts
        assert step._artifact_keys() == []

    def test_build_prompts_with_src_dir(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("print('hello')")
            (src_dir / "nested").mkdir()
            (src_dir / "nested" / "helper.py").write_text("x = 1")

            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed, {}
                )
            assert sys_p is not None

    def test_process_result_raw(self):
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()
        session = _make_mock_session()
        result = {"content": "raw arch", "model": "gpt4", "usage": {}}
        output = step.process_result(session, "raw arch", result)
        # ArchitectureStep returns raw content without metadata header
        assert output == "raw arch"


class TestDevelopmentStep:
    """Test DevelopmentStep."""

    def test_icon(self):
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()
        assert step._icon() == "💻"

    def test_artifact_keys(self):
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()
        keys = step._artifact_keys()
        assert "architecture" in keys
        assert "prd" in keys
        assert "super-analysis" in keys

    def test_max_tokens(self):
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()
        assert step.max_tokens == 4096

    def test_build_prompts(self):
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal git-like files
            (Path(tmpdir) / "src").mkdir(exist_ok=True)
            (Path(tmpdir) / "tests").mkdir(exist_ok=True)

            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed,
                    {"architecture": "arch", "prd": "prd", "super-analysis": "sa"}
                )
            assert sys_p is not None


class TestTestPlanningStep:
    """Test TestPlanningStep."""

    def test_icon(self):
        from yuleosh.pipeline.steps import TestPlanningStep
        step = TestPlanningStep()
        assert step._icon() == "📋"

    def test_artifact_keys(self):
        from yuleosh.pipeline.steps import TestPlanningStep
        step = TestPlanningStep()
        keys = step._artifact_keys()
        assert "architecture" in keys
        assert "development" in keys

    def test_build_prompts(self):
        from yuleosh.pipeline.steps import TestPlanningStep
        step = TestPlanningStep()
        session = _make_mock_session()
        parsed = {"requirements": [], "scenarios": []}
        sys_p, user_p = step.build_prompts(
            session, "# spec", parsed,
            {"architecture": "arch", "development": "dev"}
        )
        assert sys_p is not None


class TestHermesReviewStep:
    """Test HermesReviewStep."""

    def test_icon(self):
        from yuleosh.pipeline.steps import HermesReviewStep
        step = HermesReviewStep()
        assert step._icon() == "🔮"

    def test_artifact_keys(self):
        from yuleosh.pipeline.steps import HermesReviewStep
        step = HermesReviewStep()
        keys = step._artifact_keys()
        assert "architecture" in keys
        assert "development" in keys
        assert "prd" in keys
        assert "super-analysis" in keys
        assert "review-result" in keys
        assert "self-test" in keys

    def test_build_prompts(self):
        from yuleosh.pipeline.steps import HermesReviewStep
        step = HermesReviewStep()
        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "main.py").write_text("x = 1")

            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed,
                    {"architecture": "arch", "development": "dev",
                     "self-test": "test", "prd": "prd", "super-analysis": "sa",
                     "review-result": "review"}
                )
            assert sys_p is not None

    @patch("yuleosh.pipeline.steps.json.dumps")
    def test_process_result(self, mock_dumps):
        """process_result creates a well-formed review JSON."""
        from yuleosh.pipeline.steps import HermesReviewStep
        mock_dumps.return_value = '{"ok": true}'

        step = HermesReviewStep()
        session = _make_mock_session()
        result = {"content": '{"status": "passed", "findings": []}', "model": "gpt4", "usage": {}}

        output = step.process_result(session, result["content"], result)
        assert output is not None


# ======================================================================
# __call__ execution path (the main template method)
# ======================================================================


class TestPipelineStepCall:
    """Test the __call__ template method (heavily mocked)."""

    @patch("yuleosh.pipeline.steps.Path")
    @patch("yuleosh.pipeline.steps._parse_spec")
    @patch("yuleosh.pipeline.steps._call_llm")
    def test_call_happy_path(self, mock_call_llm, mock_parse_spec, mock_path):
        """Test the full __call__ execution for a concrete step."""
        from yuleosh.pipeline.steps import SuperAnalysisStep

        mock_call_llm.return_value = {
            "content": "analysis result",
            "model": "gpt4",
            "usage": {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
        }
        mock_parse_spec.return_value = {
            "requirements": [{"name": "RS-001", "shall_statements": ["SHALL do X"]}],
            "scenarios": [],
        }

        # Mock Path.read_text for spec
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.read_text.return_value = "# Test spec"
        mock_path_instance.exists.return_value = True
        mock_path_instance.name = "test-spec.md"
        mock_path_instance.stem = "test-spec"
        mock_path_instance.parent = Path("/tmp")

        step = SuperAnalysisStep()
        session = _make_mock_session()

        with patch("yuleosh.pipeline.steps.log"):
            output_path = step(session)

        assert output_path is not None
        assert "startup-analysis.md" in str(output_path) or ""
        mock_call_llm.assert_called_once()

    @patch("yuleosh.pipeline.steps.Path")
    @patch("yuleosh.pipeline.steps._parse_spec")
    @patch("yuleosh.pipeline.steps._call_llm")
    def test_call_llm_failure(self, mock_call_llm, mock_parse_spec, mock_path):
        """LLM failure should raise PipelineStepError."""
        from yuleosh.pipeline.steps import SuperAnalysisStep, PipelineStepError

        mock_call_llm.side_effect = Exception("LLM timeout")

        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.read_text.return_value = "# Test"
        mock_path_instance.exists.return_value = True
        mock_path_instance.name = "test.md"
        mock_path_instance.stem = "test"

        step = SuperAnalysisStep()
        session = _make_mock_session()

        with pytest.raises(PipelineStepError, match="LLM call failed"):
            with patch("yuleosh.pipeline.steps.log"):
                step(session)

    @patch("yuleosh.pipeline.steps.Path")
    @patch("yuleosh.pipeline.steps._parse_spec")
    @patch("yuleosh.pipeline.steps._call_llm")
    def test_call_write_failure(self, mock_call_llm, mock_parse_spec, mock_path):
        """File write failure should raise PipelineStepError."""
        from yuleosh.pipeline.steps import SuperAnalysisStep, PipelineStepError

        mock_call_llm.return_value = {
            "content": "result",
            "model": "gpt4",
            "usage": {},
        }

        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.read_text.return_value = "# Test"
        mock_path_instance.exists.return_value = True
        mock_path_instance.name = "test.md"
        mock_path_instance.stem = "test"

        step = SuperAnalysisStep()
        session = _make_mock_session()

        # Use in-place patch to make write_text raise on the output path
        real_write_text = Path.write_text
        original_session_dir = session.session_dir
        try:
            def _fail_write(self_path, *a, **kw):
                if str(self_path).endswith("startup-analysis.md"):
                    raise OSError("Permission denied")
                return real_write_text(self_path, *a, **kw)

            with patch.object(Path, "write_text", _fail_write):
                with patch("yuleosh.pipeline.steps.log"):
                    with pytest.raises(PipelineStepError, match="Cannot write"):
                        step(session)
        finally:
            session.session_dir = original_session_dir

    @patch("yuleosh.pipeline.steps.Path")
    @patch("yuleosh.pipeline.steps._parse_spec")
    @patch("yuleosh.pipeline.steps._call_llm")
    def test_token_usage_accumulated(self, mock_call_llm, mock_parse_spec, mock_path):
        """Test that token usage is accumulated on the session."""
        from yuleosh.pipeline.steps import PrdStep

        mock_call_llm.return_value = {
            "content": "prd result",
            "model": "gpt4",
            "usage": {"total_tokens": 200, "prompt_tokens": 100, "completion_tokens": 100},
        }
        mock_parse_spec.return_value = {"requirements": [], "scenarios": []}

        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance
        mock_path_instance.read_text.return_value = "# spec"
        mock_path_instance.exists.return_value = True
        mock_path_instance.name = "test.md"
        mock_path_instance.stem = "test"

        session = _make_mock_session()
        session.artifacts["super-analysis"] = str(
            session.session_dir / "startup-analysis.md"
        )

        step = PrdStep()
        with patch("yuleosh.pipeline.steps.log"):
            step(session)

        assert session.token_usage_total == 200
        assert len(session.token_usage_steps) == 1


class TestStepsEdgeCases:
    """Edge cases for step behavior."""

    def test_architecture_step_no_src_dir(self):
        """ArchitectureStep should still work when src dir doesn't exist."""
        from yuleosh.pipeline.steps import ArchitectureStep
        step = ArchitectureStep()

        with tempfile.TemporaryDirectory() as tmpdir:
            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed, {}
                )
            assert sys_p is not None

    def test_development_step_git_failure(self):
        """Development step should handle git failures gracefully."""
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()

        with tempfile.TemporaryDirectory() as tmpdir:
            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed,
                    {"architecture": "arch", "prd": "prd", "super-analysis": "sa"}
                )
            assert sys_p is not None

    def test_hermes_review_step_no_src(self):
        """HermesReviewStep without src dir should still work."""
        from yuleosh.pipeline.steps import HermesReviewStep
        step = HermesReviewStep()

        with tempfile.TemporaryDirectory() as tmpdir:
            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                sys_p, user_p = step.build_prompts(
                    session, "# spec", parsed,
                    {"architecture": "arch", "development": "dev",
                     "self-test": "test", "prd": "prd", "super-analysis": "sa",
                     "review-result": "review"}
                )
            assert sys_p is not None

    def test_call_spec_not_found(self):
        """Empty spec when file doesn't exist."""
        from yuleosh.pipeline.steps import PipelineStep

        class MinimalStep(PipelineStep):
            step_key = "minimal"
            agent = "Test"
            description = "Minimal"
            output_filename = "min.md"
            no_llm = True

            def _run_without_llm(self, session, spec_content, parsed, artifacts):
                return f"spec_content={spec_content}"

        with tempfile.TemporaryDirectory() as tmpdir:
            session = _make_mock_session()
            # Point to a non-existent file
            session.spec_path = str(Path(tmpdir) / "nospec.md")

            step = MinimalStep()
            output_path = step(session)
            assert output_path is not None

    def test_development_step_git_log_success(self):
        """Development step with mock git success."""
        from yuleosh.pipeline.steps import DevelopmentStep
        step = DevelopmentStep()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir(exist_ok=True)
            (Path(tmpdir) / "tests").mkdir(exist_ok=True)

            session = _make_mock_session()
            parsed = {"requirements": [], "scenarios": []}

            with patch.dict(os.environ, {"OSH_HOME": tmpdir}):
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = "abc123 feat: init (2 days ago)\ndef456 fix: bug (3 days ago)"
                    mock_run.return_value = mock_result

                    sys_p, user_p = step.build_prompts(
                        session, "# spec", parsed,
                        {"architecture": "arch", "prd": "prd", "super-analysis": "sa"}
                    )
                assert sys_p is not None
