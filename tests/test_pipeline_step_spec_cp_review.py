"""spec-cp-review pipeline step tests.

Covers the Change Proposal review step:
- no pending CPs → skipped report
- mock mode → mock skip
- pending CP + LLM approve → passed report
- pending CP + LLM reject/needs-work → PipelineStepError (blocked)
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.spec_cp_review import step_spec_cp_review
from yuleosh.spec.changes import propose_change


def _make_session(tmp_path: Path, spec_path: Path | None = None, mock_mode: bool = False, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
    spec = spec_path or (tmp_path / "spec.md")
    if not spec.exists():
        spec.write_text("# Spec\n- REQ-001 SHALL work\n", encoding="utf-8")
    session = PipelineSession(
        name="test-run",
        spec_path=str(spec),
    )
    session.mock_mode = mock_mode
    return session


def test_no_pending_cps_skips(tmp_path: Path, monkeypatch):
    """GIVEN no change proposals WHEN step THEN skipped report."""
    session = _make_session(tmp_path, monkeypatch=monkeypatch)
    out = step_spec_cp_review(session)
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["status"] == "skipped"
    assert data["pending_count"] == 0


def test_mock_mode_skips_even_with_pending(tmp_path: Path, monkeypatch):
    """GIVEN pending CP + mock mode WHEN step THEN mock skip (no LLM)."""
    propose_change(tmp_path, "cp-001", title="threshold config")
    session = _make_session(tmp_path, mock_mode=True, monkeypatch=monkeypatch)
    out = step_spec_cp_review(session)
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["status"] == "skipped"
    assert data["pending_count"] == 1


def test_pending_cp_approved_passes(tmp_path: Path, monkeypatch):
    """GIVEN pending CP + LLM approves WHEN step THEN passed report."""
    propose_change(tmp_path, "cp-001", title="threshold config", affects="window")
    session = _make_session(tmp_path, monkeypatch=monkeypatch)

    def fake_llm(system_prompt, user_prompt, **kwargs):
        assert "challenge" in system_prompt.lower()  # grill-me spirit
        return {"content": json.dumps({
            "change_id": "cp-001",
            "verdict": "approve",
            "rationale": "aligned with spec",
            "blockers": [],
        })}

    session.llm_client = fake_llm
    out = step_spec_cp_review(session)
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    assert data["status"] == "passed"
    assert data["reviews"][0]["verdict"] == "approve"


def test_pending_cp_rejected_blocks(tmp_path: Path, monkeypatch):
    """GIVEN pending CP + LLM rejects WHEN step THEN PipelineStepError."""
    propose_change(tmp_path, "cp-001", title="risky change")
    session = _make_session(tmp_path, monkeypatch=monkeypatch)

    def fake_llm(system_prompt, user_prompt, **kwargs):
        return {"content": json.dumps({
            "change_id": "cp-001",
            "verdict": "reject",
            "rationale": "contradicts existing contract",
            "blockers": ["overlaps with guardrail G-03"],
        })}

    session.llm_client = fake_llm
    with pytest.raises(PipelineStepError) as exc:
        step_spec_cp_review(session)
    assert "cp-001" in str(exc.value)
    # report still written for evidence
    report_path = Path(session.session_dir) / "spec-cp-review.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "blocked"
    assert data["blocking_change_ids"] == ["cp-001"]


def test_mixed_verdicts_blocks_only_non_approved(tmp_path: Path, monkeypatch):
    """GIVEN two pending CPs, one needs-work WHEN step THEN blocked on that one."""
    propose_change(tmp_path, "cp-001", title="good change")
    propose_change(tmp_path, "cp-002", title="unclear change")
    session = _make_session(tmp_path, monkeypatch=monkeypatch)

    def fake_llm(system_prompt, user_prompt, **kwargs):
        verdict = "needs-work" if "cp-002" in user_prompt else "approve"
        return {"content": json.dumps({
            "change_id": verdict,
            "verdict": verdict,
            "rationale": "x",
            "blockers": [],
        })}

    session.llm_client = fake_llm
    with pytest.raises(PipelineStepError) as exc:
        step_spec_cp_review(session)
    assert "cp-002" in str(exc.value)


def test_non_json_llm_output_blocks(tmp_path: Path, monkeypatch):
    """GIVEN LLM returns non-JSON WHEN step THEN PipelineStepError (not silent pass)."""
    propose_change(tmp_path, "cp-001", title="x")
    session = _make_session(tmp_path, monkeypatch=monkeypatch)

    def fake_llm(system_prompt, user_prompt, **kwargs):
        return {"content": "I think this is fine, approve."}  # not JSON

    session.llm_client = fake_llm
    with pytest.raises(PipelineStepError) as exc:
        step_spec_cp_review(session)
    assert "JSON" in str(exc.value)
