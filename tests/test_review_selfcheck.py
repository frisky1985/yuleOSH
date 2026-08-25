
# @tests src/yuleosh/pipeline/step_handlers/review_selfcheck/handler.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for review_selfcheck step handler (H2-2e)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.review_selfcheck.handler import (
    step_review_selfcheck,
    _build_selfcheck_prompt,
    _parse_selfcheck_result,
    _downgrade_unsupported,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def session(tmp_path):
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Spec\nREQ-UART-001: baud rate\n")
    s = PipelineSession(name="test-selfcheck", spec_path=str(spec_file))
    s.session_dir = tmp_path / ".osh" / "sessions" / "test-selfcheck"
    s.session_dir.mkdir(parents=True, exist_ok=True)
    s.token_usage_total = 0
    s.token_usage_steps = []
    return s


def _make_artifact(tmp_path: Path, key: str, content: str) -> Path:
    p = tmp_path / f"{key}.md"
    p.write_text(content)
    return p


def _fake_llm_selfcheck(verdict="passed", items=None):
    return json.dumps({
        "verdict": verdict,
        "summary": "all claims grounded",
        "items": items or [
            {"claim": "hal_init() is called at startup",
             "confidence": "high",
             "reason": "confirmed in src/hal.c:5"},
        ],
    })


# ── _build_selfcheck_prompt ───────────────────────────────────────────────────

class TestBuildSelfcheckPrompt:
    def test_returns_two_strings(self):
        sys_p, usr_p = _build_selfcheck_prompt("LLM output text", "repo facts", "code-review")
        assert isinstance(sys_p, str) and len(sys_p) > 50
        assert isinstance(usr_p, str)

    def test_artifact_key_in_user_prompt(self):
        _, usr_p = _build_selfcheck_prompt("output", "facts", "architecture")
        assert "architecture" in usr_p

    def test_llm_output_in_user_prompt(self):
        _, usr_p = _build_selfcheck_prompt("unique_output_marker", "facts", "code-review")
        assert "unique_output_marker" in usr_p

    def test_long_output_truncated(self):
        long_text = "x" * 10000
        _, usr_p = _build_selfcheck_prompt(long_text, "facts", "code-review")
        assert "truncated" in usr_p

    def test_short_output_not_truncated(self):
        _, usr_p = _build_selfcheck_prompt("short", "facts", "code-review")
        assert "truncated" not in usr_p

    def test_system_prompt_contains_schema_keywords(self):
        sys_p, _ = _build_selfcheck_prompt("x", "y", "z")
        assert "confidence" in sys_p
        assert "unsupported" in sys_p


# ── _parse_selfcheck_result ───────────────────────────────────────────────────

class TestParseSelfcheckResult:
    def test_valid_json_parsed(self):
        raw = '{"verdict": "passed", "summary": "ok", "items": []}'
        result = _parse_selfcheck_result(raw)
        assert result["verdict"] == "passed"

    def test_json_in_markdown_block_extracted(self):
        raw = 'Sure!\n```json\n{"verdict": "warning", "summary": "x", "items": []}\n```'
        result = _parse_selfcheck_result(raw)
        assert result["verdict"] == "warning"

    def test_unparseable_returns_warning_fallback(self):
        result = _parse_selfcheck_result("not json at all")
        assert result["verdict"] == "warning"
        assert "_parse_error" in result

    def test_json_embedded_in_text(self):
        raw = 'Here is my analysis: {"verdict": "failed", "summary": "bad", "items": []} done.'
        result = _parse_selfcheck_result(raw)
        assert result["verdict"] == "failed"


# ── _downgrade_unsupported ────────────────────────────────────────────────────

class TestDowngradeUnsupported:
    def test_all_high_stays_passed(self):
        r = {"verdict": "passed", "items": [
            {"confidence": "high"}, {"confidence": "medium"},
        ]}
        _downgrade_unsupported(r)
        assert r["verdict"] == "passed"
        assert r["gate_action"] == "all claims grounded"

    def test_low_item_sets_warning(self):
        r = {"verdict": "passed", "items": [
            {"confidence": "high"}, {"confidence": "low"},
        ]}
        _downgrade_unsupported(r)
        assert r["verdict"] == "warning"
        assert "low-confidence" in r["gate_action"]

    def test_unsupported_sets_failed(self):
        r = {"verdict": "passed", "items": [
            {"confidence": "high"}, {"confidence": "unsupported"},
        ]}
        _downgrade_unsupported(r)
        assert r["verdict"] == "failed"
        assert "unsupported" in r["gate_action"]

    def test_unsupported_overrides_failed_verdict(self):
        r = {"verdict": "warning", "items": [{"confidence": "unsupported"}]}
        _downgrade_unsupported(r)
        assert r["verdict"] == "failed"

    def test_empty_items_passes(self):
        r = {"items": []}
        _downgrade_unsupported(r)
        assert r["verdict"] == "passed"


# ── step_review_selfcheck integration ────────────────────────────────────────

def _make_llm_client(selfcheck_json: str):
    """Return a callable that session.llm_client can be set to."""
    def _client(system_prompt, user_prompt, **kwargs):
        return {"content": selfcheck_json, "usage": {"total_tokens": 200}}
    return _client


class TestStepReviewSelfcheck:
    def test_happy_path_with_artifact(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        artifact = _make_artifact(tmp_path, "code-review", "HAL init is in src/hal.c:5.")
        session.artifacts["code-review"] = str(artifact)
        session.llm_client = _make_llm_client(_fake_llm_selfcheck("passed"))

        result = step_review_selfcheck(session)

        out = Path(result)
        assert out.exists()
        assert out.name == "selfcheck-result.json"
        data = json.loads(out.read_text())
        assert data["verdict"] == "passed"
        assert data["checked_artifact"] == "code-review"
        assert "review-selfcheck" in session.artifacts

    def test_hallucinated_output_sets_failed(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        artifact = _make_artifact(tmp_path, "architecture", "ghost_func() defined in ghost.c:99")
        session.artifacts["architecture"] = str(artifact)
        session.llm_client = _make_llm_client(_fake_llm_selfcheck(
            verdict="failed",
            items=[{"claim": "ghost_func() exists", "confidence": "unsupported",
                    "reason": "function not found in repo"}],
        ))

        result = step_review_selfcheck(session)

        data = json.loads(Path(result).read_text())
        assert data["verdict"] == "failed"
        assert "unsupported" in data["gate_action"]

    def test_low_confidence_sets_warning(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        artifact = _make_artifact(tmp_path, "development", "Claim with low grounding.")
        session.artifacts["development"] = str(artifact)
        session.llm_client = _make_llm_client(_fake_llm_selfcheck(
            verdict="warning",
            items=[{"claim": "claim A", "confidence": "low",
                    "reason": "partial evidence"}],
        ))

        result = step_review_selfcheck(session)

        data = json.loads(Path(result).read_text())
        assert data["verdict"] == "warning"

    def test_no_artifact_skips_gracefully(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.artifacts = {}

        result = step_review_selfcheck(session)

        data = json.loads(Path(result).read_text())
        assert data["verdict"] == "passed"
        assert data.get("skipped") is True

    def test_mock_mode_skips(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session.mock_mode = True
        artifact = _make_artifact(tmp_path, "code-review", "some LLM output")
        session.artifacts["code-review"] = str(artifact)

        result = step_review_selfcheck(session)

        assert result is not None
        assert not hasattr(session, "selfcheck_result")

    def test_llm_failure_raises_pipeline_step_error(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        artifact = _make_artifact(tmp_path, "code-review", "content")
        session.artifacts["code-review"] = str(artifact)

        def _failing_client(*args, **kwargs):
            raise RuntimeError("LLM down")

        session.llm_client = _failing_client

        with pytest.raises(PipelineStepError, match="review_selfcheck failed"):
            step_review_selfcheck(session)

    def test_artifact_priority_prefers_code_review(self, session, tmp_path, monkeypatch):
        """code-review artifact takes priority over architecture per _ARTIFACT_PRIORITY."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        cr = _make_artifact(tmp_path, "code-review", "code review content")
        arch = _make_artifact(tmp_path, "architecture", "architecture content")
        session.artifacts["architecture"] = str(arch)
        session.artifacts["code-review"] = str(cr)
        session.llm_client = _make_llm_client(_fake_llm_selfcheck("passed"))

        step_review_selfcheck(session)

        out = json.loads(Path(session.artifacts["review-selfcheck"]).read_text())
        assert out["checked_artifact"] == "code-review"

    def test_selfcheck_result_stored_on_session(self, session, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        artifact = _make_artifact(tmp_path, "prd", "PRD content")
        session.artifacts["prd"] = str(artifact)
        session.llm_client = _make_llm_client(_fake_llm_selfcheck("passed"))

        step_review_selfcheck(session)

        assert hasattr(session, "selfcheck_result")
        assert session.selfcheck_result["verdict"] == "passed"
