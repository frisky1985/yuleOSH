# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Deep coverage tests for step_handlers/review.py — branches not covered by
existing tests.

Target: review.py from 70% → ≥80%

Covers:
  - step_hermes_review: src_dir not existing → skip source file scan
  - step_hermes_review: json.dump OSError / IOError
  - step_hermes_review: _try_parse_hermes_json fallback producing retry status
  - step_hermes_review: LLM call failure
  - step_hermes_review: generic Exception catch
  - step_final_report: _call_llm failure → template fallback
  - step_final_report: write_text OSError after LLM
  - step_final_report: write_text OSError after template fallback
  - step_final_report: artifact read exception
  - step_final_report: generic Exception catch
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# Mock LLM helpers
# ===================================================================


def _mock_llm(content_text=None):
    content_text = content_text or json.dumps({
        "session": "test-session",
        "reviewer": "Hermes",
        "timestamp": "2024-01-01T00:00:00",
        "status": "passed",
        "findings": [],
        "finding_breakdown": {"critical": 0, "major": 0, "minor": 0, "info": 0},
        "summary": "All checks passed.",
    })
    def _mock(system_prompt, user_prompt, **kwargs):
        return {
            "content": content_text,
            "model": "mock-model",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    return _mock


def _mock_llm_plain(plain_text=None):
    plain_text = plain_text or "I think the code looks good."
    def _mock(*args, **kwargs):
        return {
            "content": plain_text,
            "model": "mock-model",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
    return _mock


def _mock_llm_fail():
    def _mock(*args, **kwargs):
        raise RuntimeError("API connection refused")
    return _mock


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def session_with_src(tmp_path, monkeypatch):
    """Create session with src/ dir and artifacts for review testing."""
    from yuleosh.pipeline.session import PipelineSession

    monkeypatch.setenv("OSH_HOME", str(tmp_path))

    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Test Spec\nSome content")

    # Create src dir with a python file
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("x = 1\n")

    # Create artifacts
    for key in ["architecture", "development", "self-test", "prd", "super-analysis", "review-result"]:
        p = tmp_path / f"{key}.md"
        p.write_text(f"# {key}\nContent")
        session = PipelineSession("review-test", str(spec_file), llm_client=_mock_llm())
        session.artifacts[key] = str(p)

    session.artifacts["spec-check"] = str(tmp_path / "spec-check.json")
    (tmp_path / "spec-check.json").write_text(json.dumps({"coverage": {"score": 100}, "error_count": 0}))

    return session


@pytest.fixture
def session_without_src(tmp_path, monkeypatch):
    """Create session without src/ dir."""
    from yuleosh.pipeline.session import PipelineSession

    monkeypatch.setenv("OSH_HOME", str(tmp_path))

    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Test Spec")

    session = PipelineSession("review-no-src", str(spec_file), llm_client=_mock_llm())
    for key in ["architecture", "development", "self-test", "prd", "super-analysis", "review-result"]:
        p = tmp_path / f"{key}.md"
        p.write_text(f"# {key}")
        session.artifacts[key] = str(p)
    session.artifacts["spec-check"] = str(tmp_path / "spec-check.json")
    (tmp_path / "spec-check.json").write_text(json.dumps({"coverage": {"score": 100}, "error_count": 0}))
    return session


# ===================================================================
# step_hermes_review — uncovered branches
# ===================================================================


class TestHermesReviewSrcDirNotExists:
    """GIVEN src_dir does not exist
    WHEN step_hermes_review runs
    THEN it handles gracefully (empty source_files list)."""

    def test_no_src_dir(self, session_without_src):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review

        result = step_hermes_review(session_without_src)
        assert result is not None
        assert Path(result).exists()


class TestHermesReviewJSONDumpError:
    """GIVEN json.dump raises OSError
    WHEN step_hermes_review runs
    THEN PipelineStepError is raised."""

    def test_json_dump_oserror(self, session_with_src):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review
        from yuleosh.pipeline.session import PipelineStepError

        with mock.patch("yuleosh.pipeline.step_handlers.review.json.dump", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_hermes_review(session_with_src)
            assert "Cannot write" in str(exc.value)


class TestHermesReviewNonJSONResponse:
    """GIVEN LLM returns non-JSON text
    WHEN step_hermes_review runs
    THEN _try_parse_hermes_json fallback produces status='retry'."""

    def test_non_json_response(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")

        session = PipelineSession("review-nonjson", str(spec_file), llm_client=_mock_llm_plain())
        # Create src dir
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")

        for key in ["architecture", "development", "self-test", "prd", "super-analysis", "review-result"]:
            p = tmp_path / f"{key}.md"
            p.write_text(f"# {key}")
            session.artifacts[key] = str(p)
        session.artifacts["spec-check"] = str(tmp_path / "spec-check.json")
        (tmp_path / "spec-check.json").write_text(json.dumps({"coverage": {"score": 100}, "error_count": 0}))

        result = step_hermes_review(session)
        assert result is not None
        with open(result) as f:
            data = json.load(f)
        assert data["status"] == "retry"
        assert "_raw_llm_output" in data


class TestHermesReviewLLMFailure:
    """GIVEN _call_llm raises exception during review
    WHEN step_hermes_review runs
    THEN PipelineStepError is raised."""

    def test_llm_failure(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("review-llm-fail", str(spec_file), llm_client=_mock_llm_fail())
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1\n")

        with pytest.raises(PipelineStepError) as exc:
            step_hermes_review(session)
        assert "LLM call failed" in str(exc.value)


class TestHermesReviewGenericError:
    """GIVEN unexpected exception in review outer try
    WHEN step_hermes_review runs
    THEN PipelineStepError is raised."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Test")
        session = PipelineSession("review-generic", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.review.build_code_review_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_hermes_review(session)
            assert "failed" in str(exc.value).lower()


# ===================================================================
# step_final_report — uncovered branches
# ===================================================================


class TestFinalReportLLMFallback:
    """GIVEN _call_llm raises RuntimeError or PipelineStepError
    WHEN step_final_report runs
    THEN template fallback is used."""

    def test_llm_failure_fallback(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-llm-fallback", str(spec_file), llm_client=_mock_llm_fail())

        # Add some steps and artifacts
        session.add_step("spec-check", "小明", "Check")
        session.start_step(0)
        session.complete_step(0, "/tmp/out.json")
        session.artifacts["spec-check"] = str(tmp_path / "sc.md")
        (tmp_path / "sc.md").write_text("# spec-check")

        result = step_final_report(session)
        assert result is not None
        content = Path(result).read_text()
        assert "AI-powered summary unavailable" in content


class TestFinalReportWriteErrorAfterLLM:
    """GIVEN LLM succeeds but write_text raises OSError
    WHEN step_final_report runs
    THEN PipelineStepError is raised."""

    def test_write_error_after_llm(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-write-llm", str(spec_file), llm_client=_mock_llm())

        with mock.patch.object(Path, "write_text", side_effect=OSError("Disk full")):
            with pytest.raises(PipelineStepError) as exc:
                step_final_report(session)
            assert "Cannot write" in str(exc.value)


class TestFinalReportWriteErrorAfterTemplate:
    """GIVEN LLM fails AND write_text for template raises OSError
    WHEN step_final_report runs
    THEN PipelineStepError is raised from the template fallback."""

    def test_write_error_after_template(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-write-tpl", str(spec_file), llm_client=_mock_llm_fail())

        session.add_step("spec-check", "小明", "Check")
        session.start_step(0)
        session.complete_step(0, "/tmp/out.json")
        session.artifacts["spec-check"] = str(tmp_path / "sc.md")
        (tmp_path / "sc.md").write_text("# spec-check")

        # LLM fails → template fallback → write_text on template output should raise
        call_count = [0]

        def side_effect_write(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 1:
                raise OSError("Disk full on template write")
            return None

        with mock.patch.object(Path, "write_text", side_effect=side_effect_write):
            with pytest.raises(PipelineStepError) as exc:
                step_final_report(session)
            assert "Cannot write" in str(exc.value)


class TestFinalReportArtifactReadError:
    """GIVEN an artifact file cannot be read
    WHEN building artifact_summaries in step_final_report
    THEN '(cannot read)' is used as fallback."""

    def test_artifact_read_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-read-err", str(spec_file), llm_client=_mock_llm())

        # Add artifact that can't be read
        session.artifacts["spec-check"] = str(tmp_path / "sc.md")
        (tmp_path / "sc.md").write_text("content")

        with mock.patch.object(Path, "read_text", side_effect=PermissionError("Access denied")):
            result = step_final_report(session)
        assert result is not None
        assert Path(result).exists()


class TestFinalReportGenericError:
    """GIVEN unexpected exception in final report outer try
    WHEN step_final_report runs
    THEN PipelineStepError is raised."""

    def test_generic_error(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-generic", str(spec_file), llm_client=_mock_llm())

        with mock.patch(
            "yuleosh.pipeline.step_handlers.review.build_final_report_prompt",
            side_effect=ValueError("Unexpected"),
        ):
            with pytest.raises(PipelineStepError) as exc:
                step_final_report(session)
            assert "failed" in str(exc.value).lower()


class TestFinalReportHappyPath:
    """GIVEN everything works
    WHEN step_final_report runs
    THEN it returns the output path."""

    def test_happy_path(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        from yuleosh.pipeline.session import PipelineSession

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Spec")
        session = PipelineSession("report-happy", str(spec_file), llm_client=_mock_llm())

        session.add_step("spec-check", "小明", "Check")
        session.start_step(0)
        session.complete_step(0, "/tmp/out.json")
        session.artifacts["spec-check"] = str(tmp_path / "sc.md")
        (tmp_path / "sc.md").write_text("# spec-check content")

        result = step_final_report(session)
        assert result is not None
        content = Path(result).read_text()
        assert "Final Report" in content
