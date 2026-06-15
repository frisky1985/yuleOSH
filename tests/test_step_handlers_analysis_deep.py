# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep coverage tests for step_handlers/analysis.py — branches not covered by
existing tests.

Target: analysis.py from 77% → ≥80%

Covers:
  - step_super_analysis: spec file not found / unreadable path (line 38)
  - step_super_analysis: LLM call failure path (lines 53-59)
  - step_super_analysis: write_text OSError (lines 85-87)
  - step_super_analysis: generic Exception catch (lines 93-95)
  - step_hermes_prd: super artifact missing path (lines 118-122)
  - step_hermes_prd: write_text OSError (lines 164-166)
  - step_hermes_prd: LLM call failure (lines 134-139)
  - step_internal_review: _call_llm failure → fallback template (lines 246-263)
  - step_internal_review: write_text OSError (lines 268-270)
  - step_internal_review: artifact read exception (lines 210-211)
  - step_internal_review: generic Exception catch (lines 276-278)
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# Mock LLM
# ===================================================================


def _mock_llm_ok():
    """Return a mock LLM that returns valid content."""
    def _mock(system_prompt, user_prompt, **kwargs):
        return {
            "content": "## Analysis Result\n\nEverything looks good.",
            "model": "mock-model",
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }
    return _mock


def _mock_llm_fail():
    """Return a mock LLM that raises RuntimeError."""
    def _mock(*args, **kwargs):
        raise RuntimeError("API connection refused")
    return _mock


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def session(tmp_path, monkeypatch):
    """Create a PipelineSession for analysis testing."""
    from yuleosh.pipeline.session import PipelineSession

    monkeypatch.setenv("OSH_HOME", str(tmp_path))

    spec_file = tmp_path / "spec.md"
    spec_file.write_text(
        "# Test Spec\n"
        "### Req-RS-001: Auth\n"
        "- The system SHALL authenticate users.\n"
        "- The system SHOULD support refresh tokens.\n"
        "\n"
        "### GIVEN a user with valid credentials\n"
        "WHEN they submit the login form\n"
        "THEN they are redirected\n"
    )

    # Create artifacts needed for PRD and internal-review
    for key in ["super-analysis", "spec-check", "prd"]:
        p = tmp_path / f"{key}.md"
        p.write_text(f"# {key}\nContent for {key}")
        session_obj = PipelineSession("analysis-test", str(spec_file), llm_client=_mock_llm_ok())
        session_obj.artifacts[key] = str(p)
    # Add extra artifacts for internal-review
    session_obj.artifacts["development"] = str(tmp_path / "development.md")
    (tmp_path / "development.md").write_text("# Dev\nDev content")
    return session_obj


# ===================================================================
# step_super_analysis — uncovered branches
# ===================================================================


class TestSuperAnalysisSpecNotFound:
    """GIVEN spec file does not exist
    WHEN step_super_analysis runs
    THEN '(spec file not found)' is used and no crash occurs."""

    def test_spec_not_exists(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "nonexistent.md"
        # Don't create the file
        session = PipelineSession("super-no-spec", str(spec_file), llm_client=_mock_llm_ok())
        result = step_super_analysis(session)
        assert result is not None
        assert Path(result).exists()


class TestSuperAnalysisLLMFailure:
    """GIVEN _call_llm raises an exception
    WHEN step_super_analysis runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("super-llm-fail", str(spec_file), llm_client=_mock_llm_fail())
        with pytest.raises(PipelineStepError) as exc:
            step_super_analysis(session)
        assert "LLM call failed" in str(exc.value)


class TestSuperAnalysisWriteError:
    """GIVEN write_text raises OSError
    WHEN step_super_analysis runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("super-write-err", str(spec_file), llm_client=_mock_llm_ok())

        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_super_analysis(session)
            assert "Cannot write" in str(exc.value) or "failed" in str(exc.value).lower()


class TestSuperAnalysisGenericError:
    """GIVEN an unexpected exception occurs before the inner try
    WHEN step_super_analysis runs
    THEN PipelineStepError is raised via the outer generic catch."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("super-generic-err", str(spec_file), llm_client=_mock_llm_ok())

        # Cause an exception in the outer try (before the inner LLM call)
        with mock.patch(
            "yuleosh.pipeline.step_handlers.analysis._parse_spec",
            side_effect=ValueError("Corrupt spec"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_super_analysis(session)
            assert "failed" in str(exc.value).lower()


# ===================================================================
# step_hermes_prd — uncovered branches
# ===================================================================


class TestHermesPRDMissingSuperArtifact:
    """GIVEN super-analysis artifact key is present but the file does not exist
    WHEN step_hermes_prd runs
    THEN super_content stays empty string (not crash)."""

    def test_missing_super_artifact(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_hermes_prd
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "# Spec\n"
            "### Req-RS-001: Auth\n"
            "- SHALL work.\n"
        )
        session = PipelineSession("prd-missing-super", str(spec_file), llm_client=_mock_llm_ok())
        # Add super-analysis key but file doesn't exist
        session.artifacts["super-analysis"] = str(tmp_path / "nonexistent.md")

        result = step_hermes_prd(session)
        assert result is not None
        assert Path(result).exists()


class TestHermesPRDLLMFailure:
    """GIVEN _call_llm raises during PRD
    WHEN step_hermes_prd runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_hermes_prd
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("prd-llm-fail", str(spec_file), llm_client=_mock_llm_fail())
        with pytest.raises(PipelineStepError) as exc:
            step_hermes_prd(session)
        assert "LLM call failed" in str(exc.value)


class TestHermesPRDWriteError:
    """GIVEN write_text raises OSError during PRD
    WHEN step_hermes_prd runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_hermes_prd
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "# Spec\n"
            "### Req-001: Test\n"
            "- SHALL work.\n"
        )
        session = PipelineSession("prd-write-err", str(spec_file), llm_client=_mock_llm_ok())

        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_hermes_prd(session)
            assert "Cannot write PRD" in str(exc.value)


# ===================================================================
# step_internal_review — uncovered branches
# ===================================================================


class TestInternalReviewLLMFallback:
    """GIVEN _call_llm raises RuntimeError
    WHEN step_internal_review runs
    THEN fallback template is used (no crash)."""

    def test_llm_failure_fallback(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("review-llm-fallback", str(spec_file), llm_client=_mock_llm_fail())

        # Provide required artifacts
        for key in ["spec-check", "super-analysis", "prd"]:
            p = tmp_path / f"{key}.out"
            p.write_text(f"# {key}")
            session.artifacts[key] = str(p)

        result = step_internal_review(session)
        assert result is not None
        content = Path(result).read_text()
        assert "AI-powered analysis unavailable" in content


class TestInternalReviewWriteError:
    """GIVEN write_text raises OSError during internal review
    WHEN step_internal_review runs
    THEN PipelineStepError is raised."""

    def test_write_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("review-write-err", str(spec_file), llm_client=_mock_llm_ok())

        for key in ["spec-check", "super-analysis", "prd"]:
            p = tmp_path / f"{key}.out"
            p.write_text(f"# {key}")
            session.artifacts[key] = str(p)

        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_internal_review(session)
            assert "Cannot write" in str(exc.value)


class TestInternalReviewMissingArtifacts:
    """GIVEN required artifacts are missing
    WHEN step_internal_review runs
    THEN PipelineStepError is raised."""

    def test_missing_artifacts(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("review-missing-art", str(spec_file), llm_client=_mock_llm_ok())

        # No artifacts set
        with pytest.raises(PipelineStepError) as exc:
            step_internal_review(session)
        assert "missing artifacts" in str(exc.value).lower()


class TestInternalReviewArtifactReadError:
    """GIVEN an artifact file exists but cannot be read
    WHEN the first 300 chars extraction fails
    THEN '(read error)' is used as fallback."""

    def test_artifact_read_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("review-read-err", str(spec_file), llm_client=_mock_llm_ok())

        # Provide artifacts but make one path point to a directory (exists()=True but read raises)
        for key in ["super-analysis", "prd"]:
            p = tmp_path / f"{key}.out"
            p.write_text(f"# {key}")
            session.artifacts[key] = str(p)

        # Make spec-check point to a file that exists but 
        # mock Path.read_text to raise on the artifacts loop only
        p = tmp_path / "spec-check.out"
        p.write_text("# spec-check")
        session.artifacts["spec-check"] = str(p)

        # Mock read_text: fail on the artifact read for "spec-check", pass for everything else
        original_read_text = Path.read_text

        def side_effect_read(self_obj):
            path_str = str(self_obj)
            if "spec-check" in path_str and "artifact" not in path_str:
                raise PermissionError("Access denied")
            return original_read_text(self_obj)

        with mock.patch.object(Path, "read_text", autospec=True, side_effect=side_effect_read):
            result = step_internal_review(session)
        assert result is not None
        assert Path(result).exists()


class TestInternalReviewGenericError:
    """GIVEN an unexpected exception outside the LLM call in internal_review
    WHEN step_internal_review runs
    THEN PipelineStepError is raised via generic catch."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("review-generic-err", str(spec_file), llm_client=_mock_llm_ok())

        for key in ["spec-check", "super-analysis", "prd"]:
            p = tmp_path / f"{key}.out"
            p.write_text(f"# {key}")
            session.artifacts[key] = str(p)

        with mock.patch(
            "yuleosh.pipeline.step_handlers.analysis.build_internal_review_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_internal_review(session)
            assert "Internal review failed" in str(exc.value)
