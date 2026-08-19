#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests for external agent step handlers (codex-verify / claude-review).

Covers:
  - agent_registry role mapping (Codex → verifier, step → agent)
  - mock mode → SKIPPED report, no subprocess call
  - CLI missing → SKIPPED report, no subprocess call
  - codex verification PASS / FAIL (blocking with PipelineStepError)
  - claude review agree / disagree (blocking with PipelineStepError)
  - invalid JSON output → honest failure (never fake pass)
  - subprocess timeout → PipelineStepError
  - report JSON structure (status/defects/verdict)
"""

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.agent_registry import (
    AGENT_ROLES,
    resolve_agent_for_step,
    resolve_agent_role,
)
from yuleosh.pipeline.session import PipelineStepError
from yuleosh.pipeline.step_handlers import (
    PIPELINE_STEPS,
    step_claude_review,
    step_codex_verify,
)
from yuleosh.pipeline.step_handlers.external_agents import (
    _build_claude_review_prompt,
    _official_shall_block,
)

# ── fixtures ──────────────────────────────────────────────────────────

class FakeSession:
    """Minimal PipelineSession stand-in for handler tests."""

    def __init__(self, tmp_path: Path, mock_mode: bool = False, spec: str = "# Spec\n"):
        self.name = "test-session"
        self.session_dir = tmp_path
        self.spec_path = tmp_path / "docs" / "spec.md"
        self.spec_path.parent.mkdir(parents=True, exist_ok=True)
        self.spec_path.write_text(spec, encoding="utf-8")
        self.artifacts = {}
        self.mock_mode = mock_mode
        self.errors = []
        self.token_usage_total = 0
        self.token_usage_steps = []


@pytest.fixture
def session(tmp_path):
    return FakeSession(tmp_path)


def _make_result(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ── agent registry ────────────────────────────────────────────────────

class TestAgentRegistry:
    def test_codex_role_registered(self):
        assert AGENT_ROLES["Codex"] == "verifier"

    def test_claude_role_architect(self):
        assert AGENT_ROLES["Claude"] == "architect"

    def test_step_agent_map_codex_verify(self):
        assert resolve_agent_for_step("codex-verify") == "Codex"
        assert resolve_agent_role("Codex") == "verifier"

    def test_step_agent_map_claude_review(self):
        assert resolve_agent_for_step("claude-review") == "Claude"
        assert resolve_agent_role("Claude") == "architect"

    def test_steps_registered_in_pipeline(self):
        keys = [s[0] for s in PIPELINE_STEPS]
        assert "codex-verify" in keys
        assert "claude-review" in keys
        # codex-verify 紧跟 self-test；claude-review 在 test-planning 后
        assert keys.index("codex-verify") == keys.index("self-test") + 1
        assert keys.index("claude-review") == keys.index("test-planning") + 1

    def test_handlers_exported(self):
        assert callable(step_codex_verify)
        assert callable(step_claude_review)


# ── codex-verify ──────────────────────────────────────────────────────

class TestCodexVerify:
    def test_mock_mode_skips(self, session, tmp_path):
        session.mock_mode = True
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli") as m:
            path = step_codex_verify(session)
            m.assert_not_called()
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"
        assert report["step"] == "codex-verify"

    def test_cli_missing_skips(self, session, tmp_path):
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value=None):
            path = step_codex_verify(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"
        assert "not installed" in report["reason"]

    def test_pass_writes_report(self, session, tmp_path):
        stdout = json.dumps({
            "passed": True,
            "summary": "all tests pass",
            "defects": [],
            "test_results": {"runner": "pytest", "passed": 10, "failed": 0},
        })
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/codex"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout=stdout)):
            path = step_codex_verify(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "passed"
        assert report["defect_count"] == 0
        assert report["test_results"]["passed"] == 10

    def test_fail_raises_and_writes_defects(self, session, tmp_path):
        stdout = json.dumps({
            "passed": False,
            "summary": "2 unit tests failing",
            "defects": [
                {"severity": "critical", "file": "src/a.py", "line": 42,
                 "message": "crash on empty input", "evidence": "pytest -q: 2 failed"},
            ],
            "test_results": {"runner": "pytest", "passed": 8, "failed": 2},
        })
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                           return_value="/usr/bin/codex"), \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                           return_value=_make_result(stdout=stdout)):
            step_codex_verify(session)
        assert "FAILED" in str(exc.value)
        assert "1 defect" in str(exc.value)
        # 缺陷报告必须落盘（主 agent 读取修复）
        report_path = tmp_path / "codex-verify.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "failed"
        assert len(report["defects"]) == 1

    def test_invalid_json_fails_honestly(self, session, tmp_path):
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/codex"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout="not json at all")):
            step_codex_verify(session)
        assert "not valid JSON" in str(exc.value)

    def test_nonzero_exit_raises(self, session, tmp_path):
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/codex"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stderr="boom", returncode=1)):
            step_codex_verify(session)
        assert "exited 1" in str(exc.value)

    def test_timeout_raises(self, session, tmp_path):
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/codex"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        side_effect=subprocess.TimeoutExpired(cmd="codex", timeout=600)):
            step_codex_verify(session)
        assert "timed out" in str(exc.value)

    def test_env_key_injected(self, session, tmp_path):
        """DEEPSEEK_API_KEY 从 ~/.hermes/.env 注入 codex 子进程。"""
        stdout = json.dumps({"passed": True, "summary": "ok", "defects": [],
                             "test_results": {}})
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/codex"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._load_env_key",
                        return_value="sk-test-key") as load_key, \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout=stdout)) as run_cli:
            step_codex_verify(session)
        load_key.assert_called_once_with("DEEPSEEK_API_KEY")
        # _run_cli 收到 extra_env 带 key
        _, kwargs = run_cli.call_args
        assert kwargs["extra_env"]["DEEPSEEK_API_KEY"] == "sk-test-key"


# ── claude-review ─────────────────────────────────────────────────────

class TestClaudeReview:
    def test_mock_mode_skips(self, session, tmp_path):
        session.mock_mode = True
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli") as m:
            path = step_claude_review(session)
            m.assert_not_called()
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"

    def test_cli_missing_skips(self, session, tmp_path):
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value=None):
            path = step_claude_review(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "skipped"
        assert "not installed" in report["reason"]

    def test_agree_passes(self, session, tmp_path):
        stdout = json.dumps({
            "verdict": "agree",
            "summary": "direction aligned",
            "blockers": [],
            "suggestions": ["add error handling"],
            "brainstorm": "consider retry semantics",
        })
        with mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/claude"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout=stdout)):
            path = step_claude_review(session)
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        assert report["status"] == "passed"
        assert report["verdict"] == "agree"

    def test_disagree_blocks(self, session, tmp_path):
        stdout = json.dumps({
            "verdict": "disagree",
            "summary": "architecture over-engineered",
            "blockers": [
                {"severity": "major", "item": "unnecessary abstraction layer",
                 "rationale": "spec has no extension requirement"},
            ],
            "suggestions": ["simplify"],
            "brainstorm": "",
        })
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                           return_value="/usr/bin/claude"), \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                           return_value=_make_result(stdout=stdout)):
            step_claude_review(session)
        assert "NOT agreed" in str(exc.value)
        report_path = tmp_path / "claude-review.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["status"] == "failed"
        assert report["verdict"] == "disagree"
        assert len(report["blockers"]) == 1

    def test_invalid_json_fails_honestly(self, session, tmp_path):
        with pytest.raises(PipelineStepError) as exc, \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/claude"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout="not json")):
            step_claude_review(session)
        assert "not valid JSON" in str(exc.value)

    def test_missing_verdict_blocks(self, session, tmp_path):
        """无 verdict 字段 → 诚实失败（默认 disagree），不假装通过。"""
        stdout = json.dumps({"summary": "no verdict given"})
        with pytest.raises(PipelineStepError), \
                mock.patch("yuleosh.pipeline.step_handlers.external_agents._find_cli",
                        return_value="/usr/bin/claude"), \
             mock.patch("yuleosh.pipeline.step_handlers.external_agents._run_cli",
                        return_value=_make_result(stdout=stdout)):
            step_claude_review(session)


# ── helpers ───────────────────────────────────────────────────────────

class TestParseHelpers:
    def test_parse_json_direct(self):
        from yuleosh.pipeline.step_handlers.external_agents import _parse_json_output
        assert _parse_json_output('{"a": 1}') == {"a": 1}

    def test_parse_json_with_noise(self):
        from yuleosh.pipeline.step_handlers.external_agents import _parse_json_output
        noisy = 'Here you go:\n```json\n{"passed": true}\n```\n'
        parsed = _parse_json_output(noisy)
        assert parsed == {"passed": True}

    def test_parse_json_embedded(self):
        from yuleosh.pipeline.step_handlers.external_agents import _parse_json_output
        parsed = _parse_json_output('prefix {"verdict": "agree"} suffix')
        assert parsed == {"verdict": "agree"}

    def test_parse_json_invalid(self):
        from yuleosh.pipeline.step_handlers.external_agents import _parse_json_output
        assert _parse_json_output("no braces here") is None

    def test_build_codex_prompt_has_project(self):
        from yuleosh.pipeline.step_handlers.external_agents import _build_codex_prompt
        prompt = _build_codex_prompt("# spec", "(artifacts)", "/tmp/proj")
        assert "角色 verifier" in prompt
        assert "/tmp/proj" in prompt
        assert "defects" in prompt

    def test_build_claude_review_prompt_injects_official_shall(self):
        """claude-review prompt 注入官方 SHALL 清单（单一事实来源）。

        Regression: r22 实测 PRD 头 SHALLs: 85（LLM 自报）vs spec 结构化
        提取 41 → claude-review 判 major blocker（SHALL 计数跨文档不一致）。
        注入后评审 agent 有单一参照，不再被 PRD 自报数字误导。
        """
        spec = (
            "# Test Spec\n\n"
            "### Req-SW-001: State Machine\n"
            "- The system SHALL manage window states.\n"
            "- The system SHALL stop motor on fault.\n\n"
            "### Req-SW-002: Commands\n"
            "- The system SHALL support manual commands.\n"
        )
        prompt = _build_claude_review_prompt(spec, "(no artifacts)", "/tmp/proj")
        assert "官方 SHALL 清单" in prompt
        assert "共 3 条" in prompt
        assert "Req-SW-001" in prompt

    def test_official_shall_block_empty_spec(self):
        block = _official_shall_block("# No requirements here\n")
        assert "未提取到 SHALL" in block
