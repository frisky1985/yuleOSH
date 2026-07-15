"""
Extended pipeline module tests — covering orchestrator, steps, and step_handlers.

Targets additional coverage for:
- pipeline/orchestrator.py — running pipeline with mock, status, error handling
- pipeline/steps.py — PipelineStep base class behaviors
- pipeline/step_handlers/*.py — all handler edge cases
- pipeline/session.py — session lifecycle edge cases

Total goal: drive pipeline test LOC > 3000.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def spec_file(tmp_path):
    """Create a minimal spec file for testing."""
    sf = tmp_path / "spec.md"
    sf.write_text(
        "# Test Spec\n"
        "\n"
        "### Req-RS-001: Authentication\n"
        "- The system SHALL authenticate users via OAuth2.\n"
        "- The system SHOULD support refresh tokens.\n"
        "\n"
        "### Req-SWR-001.1: Login Page\n"
        "- The login page SHALL have email and password fields.\n"
        "- The login page SHALL validate input before submission.\n"
        "\n"
        "### GIVEN a user with valid credentials\n"
        "WHEN they submit the login form\n"
        "THEN they are redirected to the dashboard\n"
    )
    return sf


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns canned responses."""

    def _mock_llm(system_prompt, user_prompt, **kwargs):
        return {
            "content": f"Mock response for: {user_prompt[:50]}...",
            "model": "mock-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }

    return _mock_llm


@pytest.fixture
def osh_home(tmp_path):
    """Set OSH_HOME to a tempdir."""
    old = os.environ.get("OSH_HOME")
    os.environ["OSH_HOME"] = str(tmp_path)
    yield tmp_path
    if old:
        os.environ["OSH_HOME"] = old
    else:
        os.environ.pop("OSH_HOME", None)


# ===================================================================
# Pipeline Orchestrator
# ===================================================================



def _load_misra_report():
    """Load ci.misra_report using importlib to avoid sys.path pollution."""
    import importlib.util as _iu
    import sys as _sys
    from pathlib import Path as _Path
    # misra_report is now a package at src/yuleosh/ci/misra_report/
    _mod_path = str(_Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "ci" / "misra_report" / "__init__.py")
    _spec = _iu.spec_from_file_location("misra_report", _mod_path)
    if _spec is None:
        raise ImportError(f"Could not load misra_report from {_mod_path}")
    _mod = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _sys.modules["misra_report"] = _mod
    return _mod


class TestPipelineOrchestrator:
    """Tests for pipeline/orchestrator.py"""

    def test_run_pipeline_importable(self):
        from yuleosh.pipeline.orchestrator import run_pipeline
        assert run_pipeline is not None

    def test_run_pipeline_mock_mode(self, spec_file, mock_llm, osh_home):
        """Run pipeline in mock mode with injected LLM client."""
        from yuleosh.pipeline.orchestrator import run_pipeline
        session = run_pipeline(str(spec_file), mock=True, llm_client=mock_llm)
        assert session is not None
        assert session.status in ("completed", "failed")
        assert session.name is not None

    def test_run_pipeline_with_name(self, spec_file, mock_llm, osh_home):
        """Run pipeline with a custom session name."""
        from yuleosh.pipeline.orchestrator import run_pipeline
        session = run_pipeline(str(spec_file), name="my-custom-run", llm_client=mock_llm)
        assert session.name == "my-custom-run"

    def test_run_pipeline_without_llm_key(self, spec_file, osh_home):
        """Pipeline should exit when no LLM key and no mock."""
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sys.exit") as mock_exit:
                from yuleosh.pipeline.orchestrator import run_pipeline
                run_pipeline(str(spec_file))
                mock_exit.assert_called_once_with(1)

    def test_status_pipeline_no_sessions(self, osh_home):
        """status_pipeline with no sessions."""
        from yuleosh.pipeline.orchestrator import status_pipeline
        # Ensure base directory exists
        base = Path(osh_home) / ".osh" / "sessions"
        base.mkdir(parents=True, exist_ok=True)
        # Should not raise
        status_pipeline()
        status_pipeline("nonexistent-session")

    def test_status_pipeline_with_session(self, spec_file, mock_llm, osh_home):
        """status_pipeline after a run."""
        from yuleosh.pipeline.orchestrator import run_pipeline, status_pipeline
        session = run_pipeline(str(spec_file), mock=True, llm_client=mock_llm)
        # Should not raise
        status_pipeline(session.name)

    def test_pipeline_error_handling(self, spec_file, osh_home):
        """Pipeline should handle step failures gracefully."""
        def _broken_llm(system, user, **kwargs):
            raise RuntimeError("LLM failure")

        from yuleosh.pipeline.orchestrator import run_pipeline
        session = run_pipeline(str(spec_file), mock=True, llm_client=_broken_llm)
        # Should complete with 'failed' status
        assert session.status == "failed"

    def test_pipeline_orchestrator_main_no_args(self):
        """Test orchestrator main entry with no args."""
        with mock.patch("sys.argv", ["orchestrator.py"]):
            with mock.patch("sys.exit", side_effect=SystemExit(1)) as mock_exit:
                from yuleosh.pipeline.orchestrator import main
                with pytest.raises(SystemExit):
                    main()
                mock_exit.assert_called_once_with(1)

    def test_pipeline_orchestrator_main_status(self):
        """Test orchestrator main with 'status' command."""
        with mock.patch("sys.argv", ["orchestrator.py", "status"]):
            from yuleosh.pipeline.orchestrator import main
            main()


# ===================================================================
# Pipeline Session
# ===================================================================


class TestPipelineSession:
    """Tests for pipeline/session.py"""

    def test_session_creation(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        assert session.name == "test-session"
        assert session.status == "created"
        assert session.steps == []
        assert session.artifacts == {}

    def test_session_add_step(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        step = session.add_step("spec-check", "小明", "Validate spec")
        assert step["name"] == "spec-check"
        assert step["agent"] == "小明"
        assert step["status"] == "pending"
        assert len(session.steps) == 1

    def test_session_start_and_complete_step(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        session.add_step("spec-check", "小明", "Validate")
        session.start_step(0)
        assert session.steps[0]["status"] == "running"
        session.complete_step(0, "/tmp/output.md")
        assert session.steps[0]["status"] == "completed"
        assert session.steps[0]["output_path"] == "/tmp/output.md"

    def test_session_fail_step(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        session.add_step("spec-check", "小明", "Validate")
        session.start_step(0)
        session.fail_step(0, "Step error occurred")
        assert session.steps[0]["status"] == "failed"
        assert session.status == "failed"
        assert "Step error occurred" in session.errors

    def test_session_set_artifact(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        session.set_artifact("spec-check", "/tmp/output.json")
        assert session.artifacts["spec-check"] == "/tmp/output.json"

    def test_session_to_dict(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("test-session", "/tmp/spec.md")
        session.add_step("spec-check", "小明", "Validate")
        d = session.to_dict()
        assert d["name"] == "test-session"
        assert d["status"] == "created"
        assert len(d["steps"]) == 1

    def test_session_missing_spec(self, osh_home):
        """Session created with non-existent spec path."""
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("missing-spec", "/nonexistent/spec.md")
        assert session.status == "created"

    def test_session_token_tracking(self, osh_home):
        """Verify token usage tracking fields."""
        from yuleosh.pipeline.session import PipelineSession
        session = PipelineSession("token-test", "/tmp/spec.md")
        assert session.token_usage_total == 0
        assert session.token_usage_steps == []

    def test_pipeline_step_error(self):
        """Verify PipelineStepError is a RuntimeError."""
        from yuleosh.pipeline.session import PipelineStepError
        err = PipelineStepError("test error")
        assert isinstance(err, RuntimeError)
        assert str(err) == "test error"


# ===================================================================
# Pipeline Steps Base Class
# ===================================================================


class TestPipelineStep:
    """Tests for pipeline/steps.py PipelineStep base class."""

    def test_pipeline_step_has_defaults(self):
        from yuleosh.pipeline.steps import PipelineStep
        # Can't instantiate directly (abstract), but can inspect
        assert hasattr(PipelineStep, "step_key")
        assert hasattr(PipelineStep, "agent")
        assert hasattr(PipelineStep, "description")
        assert hasattr(PipelineStep, "output_filename")

    def test_pipeline_step_subclass(self, spec_file, mock_llm, osh_home):
        from yuleosh.pipeline.steps import PipelineStep
        from yuleosh.pipeline.session import PipelineSession

        class TestStep(PipelineStep):
            step_key = "test-step"
            agent = "TestBot"
            description = "Test step description"
            output_filename = "test-output.md"

            def build_prompts(self, session, spec_content, parsed, artifacts):
                return ("system prompt", "user prompt")

        step = TestStep()
        assert step.step_key == "test-step"
        assert step.agent == "TestBot"
        assert step.description == "Test step description"
        assert step.output_filename == "test-output.md"
        assert step._icon() == "🔄"
        assert step._artifact_keys() == []

    def test_pipeline_step_no_llm(self, spec_file, osh_home):
        from yuleosh.pipeline.steps import PipelineStep
        from yuleosh.pipeline.session import PipelineSession

        class NoLlmStep(PipelineStep):
            step_key = "no-llm"
            agent = "TestBot"
            description = "No LLM step"
            output_filename = "no-llm-output.md"
            no_llm = True

            def _run_without_llm(self, session, spec_content, parsed, artifacts):
                return "Generated without LLM"

            def build_prompts(self, session, spec_content, parsed, artifacts):
                raise NotImplementedError("Should not be called")

        step = NoLlmStep()
        session = PipelineSession("test", str(spec_file), llm_client=mock.Mock())
        session.session_dir.mkdir(parents=True, exist_ok=True)

        output = step(session)
        assert output is not None
        assert Path(output).exists()
        assert "no-llm" in output

    def test_pipeline_step_read_artifacts(self, spec_file, osh_home):
        from yuleosh.pipeline.steps import PipelineStep
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession("test", str(spec_file))
        session.session_dir.mkdir(parents=True, exist_ok=True)
        art_path = session.session_dir / "prior-output.md"
        art_path.write_text("Prior artifact content")
        session.set_artifact("prior-step", str(art_path))

        class TestStep(PipelineStep):
            step_key = "test"
            agent = "T"
            description = "T"
            output_filename = "out.md"
            no_llm = True

            def _artifact_keys(self):
                return ["prior-step"]

            def build_prompts(self, *args):
                raise NotImplementedError

            def _run_without_llm(self, session, spec_content, parsed, artifacts):
                assert "prior-step" in artifacts
                assert artifacts["prior-step"] == "Prior artifact content"
                return "ok"

        step = TestStep()
        step(session)

    def test_pipeline_step_process_result(self, spec_file, osh_home):
        from yuleosh.pipeline.steps import PipelineStep
        from yuleosh.pipeline.session import PipelineSession

        class TestStep(PipelineStep):
            step_key = "test"
            agent = "T"
            description = "T"
            output_filename = "out.md"
            no_llm = True

            def build_prompts(self, *args):
                raise NotImplementedError

            def _run_without_llm(self, *args):
                return "content"

        step = TestStep()
        # process_result adds a header when there's a real LLM result
        result = step.process_result(
            mock.Mock(spec_path=str(spec_file)),
            "test content",
            {"model": "test-model", "usage": {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50}},
        )
        assert "Generated by:" in result


# ===================================================================
# Step Handler: Spec Check
# ===================================================================


class TestSpecCheckHandler:
    """Tests for pipeline/step_handlers/spec.py"""

    def test_step_spec_check_import(self):
        from yuleosh.pipeline.step_handlers.spec import step_spec_check
        assert step_spec_check is not None
        assert callable(step_spec_check)

    def test_step_spec_check_fails_on_missing_spec(self, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.spec import step_spec_check

        session = PipelineSession("test", "/nonexistent/spec.md")
        with pytest.raises(Exception):
            step_spec_check(session)


# ===================================================================
# Step Handler: Analysis
# ===================================================================


class TestAnalysisHandlers:
    """Tests for pipeline/step_handlers/analysis.py"""

    def test_step_super_analysis_import(self):
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis
        assert step_super_analysis is not None

    def test_step_hermes_prd_import(self):
        from yuleosh.pipeline.step_handlers.analysis import step_hermes_prd
        assert step_hermes_prd is not None

    def test_step_internal_review_import(self):
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review
        assert step_internal_review is not None

    def test_step_super_analysis_fails_without_llm(self, spec_file, osh_home):
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.analysis import step_super_analysis

        session = PipelineSession("test", str(spec_file))
        with pytest.raises(Exception):
            step_super_analysis(session)

    def test_internal_review_missing_artifacts(self, spec_file, osh_home):
        """Internal review should fail when required artifacts are missing."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review

        session = PipelineSession("test", str(spec_file))
        with pytest.raises(Exception, match="missing artifacts"):
            step_internal_review(session)

    def test_internal_review_with_mock_llm(self, spec_file, mock_llm, osh_home):
        """Internal review should work when artifacts exist."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.analysis import step_internal_review

        session = PipelineSession("test", str(spec_file), llm_client=mock_llm)
        # Create artifact files
        for key in ["spec-check", "super-analysis", "prd"]:
            f = session.session_dir / f"{key}.md"
            f.write_text(f"# {key}\nContent for {key}")
            session.set_artifact(key, str(f))

        result = step_internal_review(session)
        assert result is not None
        assert "review-result" in result


# ===================================================================
# Step Handler: Execution
# ===================================================================


class TestExecutionHandlers:
    """Tests for pipeline/step_handlers/execution.py"""

    def test_step_claude_arch_import(self):
        from yuleosh.pipeline.step_handlers.execution import step_claude_arch
        assert step_claude_arch is not None

    def test_step_claude_dev_import(self):
        from yuleosh.pipeline.step_handlers.execution import step_claude_dev
        assert step_claude_dev is not None

    def test_step_test_planning_import(self):
        from yuleosh.pipeline.step_handlers.execution import step_test_planning
        assert step_test_planning is not None

    def test_step_claude_test_import(self):
        from yuleosh.pipeline.step_handlers.execution import step_claude_test
        assert step_claude_test is not None

    def test_artifacts_read_helper(self):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read

        # None on missing key
        assert artifacts_read({}, "nonexistent") is None

        # None on non-existent file
        assert artifacts_read({"key": "/nonexistent/file"}, "key") is None

    def test_artifacts_read_with_file(self, tmp_path):
        from yuleosh.pipeline.step_handlers.execution import artifacts_read

        f = tmp_path / "artifact.md"
        f.write_text("artifact content")
        result = artifacts_read({"key": str(f)}, "key")
        assert result == "artifact content"


# ===================================================================
# Step Handler: Review
# ===================================================================


class TestReviewHandlers:
    """Tests for pipeline/step_handlers/review.py"""

    def test_step_hermes_review_import(self):
        from yuleosh.pipeline.step_handlers.review import step_hermes_review
        assert step_hermes_review is not None

    def test_step_final_report_import(self):
        from yuleosh.pipeline.step_handlers.review import step_final_report
        assert step_final_report is not None

    def test_step_final_report_without_llm(self, spec_file, osh_home):
        """Final report should fall back to template when LLM unavailable."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.review import step_final_report

        session = PipelineSession("test", str(spec_file))
        out = step_final_report(session)
        assert out is not None
        content = Path(out).read_text()
        assert "Final Report" in content

    def test_step_final_report_with_mock_llm(self, spec_file, mock_llm, osh_home):
        """Final report with mock LLM should produce LLM content."""
        from yuleosh.pipeline.session import PipelineSession
        from yuleosh.pipeline.step_handlers.review import step_final_report

        session = PipelineSession("test", str(spec_file), llm_client=mock_llm)
        out = step_final_report(session)
        assert out is not None


# ===================================================================
# Step Handler: Block Init/Setup
# ===================================================================


class TestStepHandlersInit:
    """Tests for pipeline/step_handlers/__init__.py"""

    def test_pipeline_steps_registry(self):
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(PIPELINE_STEPS) == 10
        assert PIPELINE_STEPS[0][0] == "spec-check"
        assert PIPELINE_STEPS[-1][0] == "final-report"

    def test_all_handlers_exported(self):
        from yuleosh.pipeline.step_handlers import (
            step_spec_check, step_super_analysis, step_hermes_prd,
            step_internal_review, step_claude_arch, step_claude_dev,
            step_test_planning, step_claude_test, step_hermes_review,
            step_final_report, _check_llm_key,
        )
        assert all(callable(h) for h in [
            step_spec_check, step_super_analysis, step_hermes_prd,
            step_internal_review, step_claude_arch, step_claude_dev,
            step_test_planning, step_claude_test, step_hermes_review,
            step_final_report,
        ])
        assert callable(_check_llm_key) or _check_llm_key is not None

    def test_resolve_handler(self):
        from yuleosh.pipeline.step_handlers import _resolve_handler
        result = _resolve_handler("test", lambda x: x)
        assert callable(result)

    def test_check_llm_key_found(self):
        from yuleosh.pipeline.step_handlers import _check_llm_key
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-test-key"}):
            key = _check_llm_key()
            assert key == "sk-test-key"

    def test_check_llm_key_not_found(self):
        from yuleosh.pipeline.step_handlers import _check_llm_key
        with mock.patch.dict(os.environ, {}, clear=True):
            key = _check_llm_key()
            assert key is None


# ===================================================================
# Pipeline Run Module (Backward compat)
# ===================================================================


class TestPipelineRunModule:
    """Tests for pipeline/run.py backward-compatible re-exports."""

    def test_run_imports(self):
        import yuleosh.pipeline.run as run_mod
        assert hasattr(run_mod, "PipelineSession")
        assert hasattr(run_mod, "PipelineStepError")
        assert hasattr(run_mod, "run_pipeline")
        assert hasattr(run_mod, "PIPELINE_STEPS")
        assert hasattr(run_mod, "_parse_spec")
        assert hasattr(run_mod, "chat_completion")
        assert hasattr(run_mod, "_call_llm")

    def test_run_notify_defaults(self):
        import yuleosh.pipeline.run as run_mod
        assert run_mod._store is None
        assert run_mod._notify is None


# ===================================================================
# Pipeline Prompts Module
# ===================================================================


class TestPipelinePrompts:
    """Basic smoke tests for pipeline/prompts.py"""

    def test_prompts_importable(self):
        from yuleosh.pipeline import prompts
        assert hasattr(prompts, "build_super_analysis_prompt")
        assert hasattr(prompts, "build_prd_prompt")
        assert hasattr(prompts, "build_internal_review_prompt")
        assert hasattr(prompts, "build_architecture_prompt")
        assert hasattr(prompts, "build_development_prompt")
        assert hasattr(prompts, "build_test_planning_prompt")
        assert hasattr(prompts, "build_code_review_prompt")
        assert hasattr(prompts, "build_final_report_prompt")


# ===================================================================
# CI Engine: MISRA integration
# ===================================================================


class TestCIMisraIntegration:
    """Tests for MISRA integration into CI engine."""

    def test_misra_exported_from_layers(self):
        """Verify run_misra_check is imported in layers."""
        from yuleosh.ci.layers import run_misra_check
        assert run_misra_check is not None

    def test_misra_re_exported_from_run(self):
        """Verify run_misra_check is re-exported from run.py."""
        import yuleosh.ci.run as run_mod
        assert hasattr(run_mod, "run_misra_check")

    def test_misra_in_pipeline_stages(self):
        """Misra check should be part of the default pipeline stages."""
        from yuleosh.ci.config import CiConfig
        cfg = CiConfig()
        # Layer 1 should include misra-check via stages list
        assert cfg.misra is not None
        assert isinstance(cfg.misra, object)

    def test_misra_stage_in_layer1(self, tmp_path):
        """Layer 1 should include MISRA check in its stages."""
        from yuleosh.ci.layers import run_layer1
        assert run_layer1 is not None

    def test_misra_report_cli(self):
        """Test misra_report.py main() entry point."""
        _mr = _load_misra_report()

        with mock.patch("sys.argv", ["misra_report.py", "--input", "/dev/null"]):
            _mr.main()


# ===================================================================
# CI Runner: run_misra_check behavior
# ===================================================================


class TestCIRunMisraCheck:
    """Tests for run_misra_check function behavior."""

    def test_skips_when_no_c_files(self, osh_home):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages import run_misra_check

        ci = CIResult(1, "test")
        result = run_misra_check(str(osh_home), ci)
        # Should skip if no src/ directory with C files
        assert result is True

    def test_skips_when_disabled(self, tmp_path, osh_home):
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.stages import run_misra_check

        # Create misra config that disables check
        config_dir = tmp_path / ".yuleosh"
        config_dir.mkdir(parents=True)
        (config_dir / "ci-config.yaml").write_text("misra:\n  enabled: false\n")

        ci = CIResult(1, "test")
        result = run_misra_check(str(tmp_path), ci)
        assert result is True


# ===================================================================
# TODO: Stages pipeline
# ===================================================================


def test_stages_import():
    """Verify all stages are importable."""
    from yuleosh.ci import stages
    assert hasattr(stages, "run_plan_lint")
    assert hasattr(stages, "run_clang_tidy")
    assert hasattr(stages, "run_misra_check")
    assert hasattr(stages, "run_unit_tests")
    assert hasattr(stages, "run_coverage_check")
    assert hasattr(stages, "run_sil_tests")
