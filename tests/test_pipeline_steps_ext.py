"""Tests for pipeline/steps.py — PipelineStep base and stage helpers."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from yuleosh.pipeline.steps import PipelineStep
from yuleosh.pipeline.session import PipelineSession, PipelineStepError


class TestPipelineStepBase:
    """Test PipelineStep abstract base class."""

    def test_build_prompts_not_implemented(self):
        """Base class raises NotImplementedError."""
        step = PipelineStep()
        with pytest.raises(NotImplementedError):
            step.build_prompts(None, "", {}, {})

    def test_default_metadata(self):
        """Default metadata values."""
        step = PipelineStep()
        assert step.step_key == ""
        assert step.agent == ""
        assert step.description == ""
        assert step.output_filename == ""
        assert step.no_llm is False
        assert step.max_tokens is None

    def test_process_result_default(self):
        """Default process_result prepends metadata header."""
        step = PipelineStep()
        session = MagicMock()
        session.spec_path = "/tmp/test.md"

        with patch("yuleosh.pipeline.steps._parse_spec") as mock_parse:
            mock_parse.return_value = {"requirements": [], "scenarios": []}

            result = step.process_result(
                session, "Content body",
                {"model": "gpt-4", "usage": {"total_tokens": 100}},
            )
            assert "Content body" in result
            assert "gpt-4" in result
            assert "Source spec" in result

    def test_call_llm_step_success(self):
        """Call a step with LLM runs build_prompts + _call_llm."""

        class TestStep(PipelineStep):
            step_key = "test-step"
            agent = "TestAgent"
            description = "Test"
            output_filename = "test.md"

            def build_prompts(self, session, spec_content, parsed, artifacts):
                return ("system prompt", "user prompt")

        step = TestStep()

        mock_out = MagicMock()
        mock_out.write_text.return_value = None

        session = MagicMock()
        session.spec_path = "/tmp/test.md"
        session.session_dir = mock_out
        session.token_usage_total = 0
        session.token_usage_steps = []
        session.artifacts = {}

        with patch("yuleosh.pipeline.steps.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = "# Spec\nSHALL x"
            mock_path.exists.return_value = True
            mock_path_cls.return_value = mock_path

            with patch("yuleosh.pipeline.steps._parse_spec") as mock_parse:
                mock_parse.return_value = {"requirements": [], "scenarios": []}

                with patch("yuleosh.pipeline.steps._call_llm") as mock_llm:
                    mock_llm.return_value = {
                        "content": "LLM output",
                        "model": "gpt-4",
                        "usage": {"total_tokens": 100, "prompt_tokens": 50},
                    }

                    result = step(session)
                    assert result is not None

    def test_call_no_llm_step(self):
        """Call a step with no_llm=True does not call LLM."""

        class NoLLMStep(PipelineStep):
            step_key = "no-llm"
            agent = "Test"
            description = "No LLM"
            output_filename = "out.md"
            no_llm = True

            def _run_without_llm(self, session, spec_content, parsed, artifacts):
                return "Generated without LLM"

        step = NoLLMStep()

        mock_out = MagicMock()
        mock_out.write_text.return_value = None

        session = MagicMock()
        session.spec_path = "/tmp/test.md"
        session.session_dir = mock_out
        session.artifacts = {}

        with patch("yuleosh.pipeline.steps.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = "# Spec"
            mock_path.exists.return_value = True
            mock_path_cls.return_value = mock_path

            with patch("yuleosh.pipeline.steps._parse_spec") as mock_parse:
                mock_parse.return_value = {"requirements": [], "scenarios": []}

                result = step(session)
                assert result is not None

    def test_call_llm_failure_raises(self):
        """LLM failure raises PipelineStepError."""

        class TestStep(PipelineStep):
            step_key = "fail"
            agent = "Test"
            description = "Fail"
            output_filename = "fail.md"

            def build_prompts(self, session, spec_content, parsed, artifacts):
                return ("sys", "usr")

        step = TestStep()
        session = MagicMock()
        session.spec_path = "/tmp/test.md"

        with patch("yuleosh.pipeline.steps.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = "# Spec"
            mock_path.exists.return_value = True
            mock_path_cls.return_value = mock_path

            with patch("yuleosh.pipeline.steps._parse_spec") as mock_parse:
                mock_parse.return_value = {"requirements": [], "scenarios": []}

                with patch("yuleosh.pipeline.steps._call_llm") as mock_llm:
                    mock_llm.side_effect = Exception("API down")

                    with pytest.raises(PipelineStepError):
                        step(session)

    def test_read_artifacts(self):
        """_read_artifacts reads artifact content."""
        step = PipelineStep()
        session = MagicMock()
        session.artifacts = {"analysis": "/tmp/analysis.md"}

        with patch("yuleosh.pipeline.steps.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = "## Analysis\nContent"
            mock_path_cls.return_value = mock_path

            contents = step._read_artifacts(session, ["analysis"])
            assert contents["analysis"] == "## Analysis\nContent"

    def test_read_artifacts_missing(self):
        """_read_artifacts handles missing artifact keys."""
        step = PipelineStep()
        session = MagicMock()
        session.artifacts = {}
        contents = step._read_artifacts(session, ["nonexistent"])
        assert contents == {}

    def test_icon_default(self):
        """Default icon returns emoji."""
        step = PipelineStep()
        assert step._icon() == "🔄"

    def test_artifact_keys_default(self):
        """Default artifact_keys returns empty list."""
        step = PipelineStep()
        assert step._artifact_keys() == []

    def test_run_without_llm_not_implemented(self):
        """_run_without_llm raises NotImplementedError by default."""
        step = PipelineStep()
        step.no_llm = True
        with pytest.raises(NotImplementedError):
            step._run_without_llm(None, "", {}, {})

    def test_write_failure(self):
        """OSError during write raises PipelineStepError."""

        class TestStep(PipelineStep):
            step_key = "write-fail"
            agent = "Test"
            description = "Write Fail"
            output_filename = "fail.md"

            def build_prompts(self, session, spec_content, parsed, artifacts):
                return ("sys", "usr")

        step = TestStep()
        session = MagicMock()
        session.spec_path = "/tmp/test.md"

        # Make session_dir such that session_dir/output_filename write fails
        mock_output = MagicMock()
        mock_output.write_text.side_effect = OSError("Disk full")
        mock_session_dir = MagicMock()
        mock_session_dir.__truediv__.return_value = mock_output
        session.session_dir = mock_session_dir

        with patch("yuleosh.pipeline.steps.Path") as mock_path_cls:
            mock_path = MagicMock()
            mock_path.read_text.return_value = "# Spec"
            mock_path.exists.return_value = True
            mock_path_cls.return_value = mock_path

            with patch("yuleosh.pipeline.steps._parse_spec") as mock_parse:
                mock_parse.return_value = {"requirements": [], "scenarios": []}

                with patch("yuleosh.pipeline.steps._call_llm") as mock_llm:
                    mock_llm.return_value = {
                        "content": "output", "model": "gpt-4", "usage": {},
                    }

                    with pytest.raises(PipelineStepError):
                        step(session)
