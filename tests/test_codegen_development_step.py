#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for the DevelopmentStep generate-code mode + step_claude_dev handler.

Verifies the default pipeline behavior is unchanged (planning) and that the
D3 mode (constructor arg or session.development_mode) produces code files
under ``artifacts/generated-code/`` with a report.
"""

import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_classes import DevelopmentStep
from yuleosh.pipeline.step_handlers.execution import step_claude_dev


def _session(tmp_path, name="dev-session", dev_mode=None, spec_body="SHALL: work"):
    spec = tmp_path / "spec.md"
    spec.write_text(spec_body)
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        session = PipelineSession(
            name=name,
            spec_path=str(spec),
            development_mode=dev_mode,
        )
    return session


def _ok_llm(system, user, **kw):
    return {
        "content": (
            "### FILE: src/hello.py\n"
            "```python\ndef hello():\n    return 'hi'\n```\n"
        ),
        "usage": {"total_tokens": 20, "prompt_tokens": 10, "completion_tokens": 10},
        "model": "test-model",
    }


class TestDevelopmentStepDefaultBehavior:
    def test_default_mode_is_planning(self):
        step = DevelopmentStep()
        assert step.mode == "planning"
        assert step.output_filename == "development-plan.md"
        assert step.step_key == "development"
        assert "architecture" in step._artifact_keys()

    def test_default_call_runs_planning_not_codegen(self, tmp_path):
        """Legacy behavior: __call__ writes development-plan.md via base."""
        session = _session(tmp_path, dev_mode=None)
        session.llm_client = _ok_llm
        step = DevelopmentStep()
        out = step(session)
        assert Path(out).name == "development-plan.md"
        assert not (tmp_path / "artifacts").exists()

    def test_constructor_mode_generate_code(self, tmp_path):
        session = _session(tmp_path)
        session.llm_client = _ok_llm
        step = DevelopmentStep(mode="generate-code")
        out = step(session)
        report = Path(out)
        assert report.name == "codegen-report.md"
        assert "generated-code" in str(report)
        assert (report.parent / "src" / "hello.py").exists()
        # development-plan.md still written as pointer note
        assert (session.session_dir / "development-plan.md").exists()
        assert "✅ verified" in report.read_text()

    def test_session_mode_enables_codegen(self, tmp_path):
        session = _session(tmp_path, dev_mode="generate-code")
        session.llm_client = _ok_llm
        step = DevelopmentStep()  # default planning constructor
        out = step(session)
        assert Path(out).name == "codegen-report.md"

    def test_session_mode_planning_wins_over_codegen_constructor(self, tmp_path):
        """session.development_mode is authoritative."""
        session = _session(tmp_path, dev_mode="planning")
        session.llm_client = _ok_llm
        step = DevelopmentStep(mode="generate-code")
        out = step(session)
        assert Path(out).name == "development-plan.md"


class TestStepClaudeDevCodegen:
    def test_handler_codegen_branch(self, tmp_path):
        session = _session(tmp_path, dev_mode="generate-code")
        session.llm_client = _ok_llm
        out = step_claude_dev(session)
        report = Path(out)
        assert report.name == "codegen-report.md"
        assert (report.parent / "src" / "hello.py").exists()
        assert report.read_text().startswith("# Code Generation Report")

    def test_handler_default_planning_unchanged(self, tmp_path):
        session = _session(tmp_path, dev_mode=None)
        session.llm_client = _ok_llm
        out = step_claude_dev(session)
        assert Path(out).name == "development-plan.md"
        assert "Development Plan" in Path(out).read_text()

    def test_handler_repair_loop(self, tmp_path):
        """Broken first attempt → repaired on retry (via real py_compile)."""
        calls = {"n": 0}

        def flaky(system, user, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                body = "def broken(:\n"
            else:
                body = "def fixed():\n    return 42\n"
            return {"content": f"### FILE: src/x.py\n```python\n{body}```\n",
                    "usage": {"total_tokens": 5}}

        session = _session(tmp_path, dev_mode="generate-code")
        session.llm_client = flaky
        out = step_claude_dev(session)
        assert calls["n"] == 2
        assert "verified" in Path(out).read_text()
        assert "def fixed()" in (Path(out).parent / "src" / "x.py").read_text()


class TestCodegenSessionConfig:
    def test_session_config_codegen_skills_used(self, tmp_path):
        spec = tmp_path / "spec.md"
        spec.write_text("SHALL: do the thing")
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            session = PipelineSession(
                name="cfg-session", spec_path=str(spec),
                development_mode="generate-code",
                config={"codegen": {"skills": ["python-testing"], "max_retries": 1}},
            )
        session.llm_client = _ok_llm
        step = DevelopmentStep()
        out = step(session)
        assert Path(out).name == "codegen-report.md"

    def test_session_development_mode_default_none(self, tmp_path):
        session = _session(tmp_path)
        assert session.development_mode is None
        assert session.config == {}
