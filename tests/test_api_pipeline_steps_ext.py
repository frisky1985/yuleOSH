"""Tests for api/pipeline_steps.py — Pipeline steps list endpoint."""

import pytest
from unittest.mock import patch
from yuleosh.api.pipeline_steps import handle_pipeline_steps


class TestPipelineSteps:
    """Test pipeline_steps endpoint."""

    def test_list_steps(self):
        """GET returns all pipeline step definitions."""
        mock_steps = [
            ("spec-check", "小明", "Spec Check", lambda s: None),
            ("super-analysis", "小明", "S.U.P.E.R Analysis", lambda s: None),
        ]

        with patch(
            "yuleosh.pipeline.step_handlers.PIPELINE_STEPS",
            mock_steps,
        ):
            result, code = handle_pipeline_steps("GET")
            assert code == 200
            data = result["data"]
            assert data["count"] == 2
            assert data["steps"][0]["key"] == "spec-check"

    def test_empty_steps(self):
        """GET with empty PIPELINE_STEPS."""
        with patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS", []):
            result, code = handle_pipeline_steps("GET")
            assert code == 200
            assert result["data"]["count"] == 0
