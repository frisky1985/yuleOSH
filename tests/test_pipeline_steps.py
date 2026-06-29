"""Tests for yuleosh.pipeline.steps — PipelineStep base class."""

from unittest import mock
from pathlib import Path
import json

import pytest

from yuleosh.pipeline.steps import PipelineStep
from yuleosh.pipeline.session import PipelineSession


# ------------------------------------------------------------------
# Helper: concrete subclass for testing
# ------------------------------------------------------------------

class TestStep(PipelineStep):
    """Minimal concrete PipelineStep subclass."""
    step_key = "test-step"
    agent = "test-agent"
    description = "A test step"
    output_filename = "test-output.json"

    def build_prompts(self, session, spec_content, parsed, artifacts):
        return ("system prompt", "user prompt")

    def process_result(self, session, llm_output, artifacts):
        return None


# ------------------------------------------------------------------
# Basic instantiation
# ------------------------------------------------------------------

def test_pipeline_step_attributes():
    """GIVEN PipelineStep class WHEN accessing class attributes THEN values are defaults."""
    assert hasattr(PipelineStep, "step_key")
    assert hasattr(PipelineStep, "agent")
    assert hasattr(PipelineStep, "description")
    assert hasattr(PipelineStep, "output_filename")


def test_subclass_overrides():
    """GIVEN TestStep subclass WHEN checking overrides THEN values are set."""
    assert TestStep.step_key == "test-step"
    assert TestStep.agent == "test-agent"
    assert TestStep.description == "A test step"
    assert TestStep.output_filename == "test-output.json"


def test_build_prompts_returns_tuple():
    """GIVEN TestStep WHEN building prompts THEN returns tuple of 2 strings."""
    step = TestStep()
    session = mock.MagicMock(spec=PipelineSession)
    result = step.build_prompts(session, "spec", {}, {})
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], str)
    assert isinstance(result[1], str)


def test_process_result_returns_none():
    """GIVEN TestStep WHEN processing result THEN returns None."""
    step = TestStep()
    session = mock.MagicMock()
    result = step.process_result(session, "llm output", {})
    assert result is None


def test_no_llm_default():
    """GIVEN base PipelineStep WHEN checking no_llm THEN is False."""
    assert PipelineStep.no_llm is False


def test_max_tokens_default():
    """GIVEN base PipelineStep WHEN checking max_tokens THEN is None."""
    assert PipelineStep.max_tokens is None


# ------------------------------------------------------------------
# _icon / _artifact_keys
# ------------------------------------------------------------------

def test_icon_default():
    """GIVEN base instance WHEN getting icon THEN returns string."""
    step = TestStep()
    assert isinstance(step._icon(), str)


def test_artifact_keys_default():
    """GIVEN base instance WHEN getting artifact keys THEN returns empty list."""
    step = TestStep()
    keys = step._artifact_keys()
    assert isinstance(keys, list)
    assert len(keys) == 0


# ------------------------------------------------------------------
# TestStep with custom attributes
# ------------------------------------------------------------------

class CustomStep(TestStep):
    """Custom step with no LLM."""
    no_llm = True
    max_tokens = 2048


def test_custom_step_no_llm():
    """GIVEN CustomStep with no_llm=True WHEN checking THEN returns True."""
    assert CustomStep.no_llm is True


def test_custom_step_max_tokens():
    """GIVEN CustomStep with max_tokens=2048 WHEN checking THEN returns 2048."""
    assert CustomStep.max_tokens == 2048
