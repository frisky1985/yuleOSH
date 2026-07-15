"""Tests for pipeline/step_classes.py — PipelineStep subclasses."""

import pytest
import json
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from yuleosh.pipeline.step_classes import (
    SuperAnalysisStep,
    PrdStep,
    ArchitectureStep,
    DevelopmentStep,
    TestPlanningStep,
    HermesReviewStep,
    get_step_instance,
    register_step,
)


class TestSteps:
    """Test step class implementations."""

    def test_super_analysis_step_metadata(self):
        step = SuperAnalysisStep()
        assert step.step_key == "super-analysis"
        assert step.agent == "小明"
        assert step.output_filename == "startup-analysis.md"
        assert step.no_llm is False

    def test_prd_step_metadata(self):
        step = PrdStep()
        assert step.step_key == "prd"
        assert step.agent == "Hermes"
        assert len(step._artifact_keys()) == 1
        assert "super-analysis" in step._artifact_keys()

    def test_architecture_step_metadata(self):
        step = ArchitectureStep()
        assert step.step_key == "architecture"
        assert step.max_tokens == 4096
        assert step.output_filename == "architecture.md"

    def test_development_step_metadata(self):
        step = DevelopmentStep()
        assert step.step_key == "development"
        assert len(step._artifact_keys()) == 3

    def test_test_planning_step_metadata(self):
        step = TestPlanningStep()
        assert step.step_key == "test-planning"
        assert len(step._artifact_keys()) == 2

    def test_hermes_review_step_metadata(self):
        step = HermesReviewStep()
        assert step.step_key == "code-review"
        assert step.max_tokens == 4096
        assert len(step._artifact_keys()) == 6

    def test_get_step_instance(self):
        step = get_step_instance("super-analysis")
        assert step is not None
        assert isinstance(step, SuperAnalysisStep)

        step = get_step_instance("unknown")
        assert step is None

    def test_register_step(self):
        mock_step = MagicMock()
        mock_step.step_key = "custom-step"
        register_step("custom-step", mock_step)
        assert get_step_instance("custom-step") is mock_step

    def test_architecture_build_prompts(self, tmp_path):
        """ArchitectureStep.build_prompts with source tree."""
        # Create some source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("print('hello')")

        with patch("os.environ.get") as mock_env:
            mock_env.return_value = str(tmp_path)

            step = ArchitectureStep()
            session = MagicMock()
            session.spec_path = "/tmp/spec.md"
            session.name = "arch-test"
            spec_content = "# Arch Spec"
            parsed = {"requirements": [], "scenarios": []}
            artifacts = {}

            system, user = step.build_prompts(
                session, spec_content, parsed, artifacts
            )
            assert "Architecture Decision Records" in system
            assert "arch-test" in user

    def test_architecture_process_result(self):
        """ArchitectureStep.process_result returns raw content."""
        step = ArchitectureStep()
        result = step.process_result(None, "## Architecture Content", {"model": "claude"})
        assert result == "## Architecture Content"

    def test_hermes_process_result(self):
        """HermesReviewStep.process_result parses JSON."""
        step = HermesReviewStep()
        content = '{"status": "passed", "findings": []}'
        session = MagicMock()
        session.name = "review-test"
        result = step.process_result(session, content, {"model": "claude"})
        parsed = json.loads(result)
        assert parsed["status"] == "passed"
        assert parsed["reviewer"] == "Hermes"

    def test_hermes_process_invalid_json(self):
        """HermesReviewStep handles invalid JSON gracefully."""
        step = HermesReviewStep()
        content = "Not JSON at all"
        session = MagicMock()
        session.name = "review-test"
        result = step.process_result(session, content, {})
        parsed = json.loads(result)
        # Invalid JSON gets a retry status and embedded raw output
        assert parsed["status"] in ("passed", "retry")
        assert "findings" in parsed
