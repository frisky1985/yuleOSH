
# @tests src/yuleosh/pipeline/llm_gateway.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for H3-2: Auto ChangeSet capture/restore in call_step_llm."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.llm_gateway import (
    _capture_llm_changeset,
    _restore_llm_changeset,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def session(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n")
    s = PipelineSession(name="test-cs", spec_path=str(spec))
    s.session_dir = tmp_path / ".osh" / "sessions" / "test-cs"
    s.session_dir.mkdir(parents=True, exist_ok=True)
    s.project_dir = str(tmp_path)
    s.token_usage_total = 0
    s.token_usage_steps = []
    return s


def _make_artifact_file(project_dir: Path, rel: str, content: str) -> Path:
    p = project_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── _capture_llm_changeset ────────────────────────────────────────────────────

class TestCaptureChangeset:
    def test_captures_existing_artifact(self, session, tmp_path):
        art = _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/code-review.json", '{"status":"ok"}'
        )
        session.artifacts["code-review"] = str(art)
        cs = _capture_llm_changeset(session)
        assert any("code-review.json" in k for k in cs)

    def test_existing_file_stores_bytes(self, session, tmp_path):
        art = _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/arch.json", '{"x":1}'
        )
        session.artifacts["arch"] = str(art)
        cs = _capture_llm_changeset(session)
        rel = next(k for k in cs if "arch.json" in k)
        assert cs[rel] == b'{"x":1}'

    def test_nonexistent_file_stores_none(self, session, tmp_path):
        ghost = tmp_path / ".yuleosh" / "artifacts" / "ghost.json"
        session.artifacts["ghost"] = str(ghost)
        cs = _capture_llm_changeset(session)
        rel = next((k for k in cs if "ghost.json" in k), None)
        assert rel is not None
        assert cs[rel] is None

    def test_empty_artifacts_returns_empty(self, session):
        session.artifacts = {}
        cs = _capture_llm_changeset(session)
        assert isinstance(cs, dict)

    def test_ignores_non_artifact_extensions(self, session, tmp_path):
        (tmp_path / ".yuleosh" / "artifacts").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".yuleosh" / "artifacts" / "binary.bin").write_bytes(b"\x00\x01")
        session.artifacts = {}
        cs = _capture_llm_changeset(session)
        assert not any("binary.bin" in k for k in cs)

    def test_scans_artifact_dir(self, session, tmp_path):
        _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/report.md", "# Report\n"
        )
        session.artifacts = {}
        cs = _capture_llm_changeset(session)
        assert any("report.md" in k for k in cs)


# ── _restore_llm_changeset ────────────────────────────────────────────────────

class TestRestoreChangeset:
    def test_restores_original_content(self, session, tmp_path):
        art = _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/report.json", '{"old": true}'
        )
        rel = str(art.relative_to(tmp_path))
        cs = {rel: b'{"old": true}'}
        # Overwrite with new content
        art.write_text('{"new": true}', encoding="utf-8")
        _restore_llm_changeset(session, cs)
        assert json.loads(art.read_text()) == {"old": True}

    def test_deletes_new_files_on_rollback(self, session, tmp_path):
        new_file = tmp_path / ".yuleosh" / "artifacts" / "new_artifact.json"
        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text("{}", encoding="utf-8")
        rel = str(new_file.relative_to(tmp_path))
        cs = {rel: None}  # None = file was new before the step
        _restore_llm_changeset(session, cs)
        assert not new_file.exists()

    def test_empty_changeset_is_noop(self, session, tmp_path):
        # Should not raise
        _restore_llm_changeset(session, {})

    def test_missing_project_dir_degrades_gracefully(self, session):
        session.project_dir = "/nonexistent/dir"
        cs = {".yuleosh/artifacts/x.json": b"{}"}
        # Should not raise — just log warnings
        _restore_llm_changeset(session, cs)


# ── Integration: auto-rollback on LLM failure ────────────────────────────────

class TestAutoRollbackOnLLMFailure:
    def test_artifact_restored_on_llm_error(self, session, tmp_path, monkeypatch):
        """When LLM call raises, existing artifact must be restored."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        art = _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/pre-existing.json", '{"before": true}'
        )
        session.artifacts["pre-existing"] = str(art)

        # Overwrite to simulate mid-step mutation
        def _bad_llm(*args, **kwargs):
            art.write_text('{"after_mutation": true}', encoding="utf-8")
            raise RuntimeError("LLM down")

        from yuleosh.pipeline.llm_gateway import call_step_llm
        with patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync",
                   side_effect=_bad_llm):
            with pytest.raises(PipelineStepError):
                call_step_llm(session, "system", "user")

        # Artifact must be restored to pre-call state
        assert json.loads(art.read_text()) == {"before": True}

    def test_no_rollback_on_success(self, session, tmp_path, monkeypatch):
        """On success, changed content is NOT rolled back."""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        art = _make_artifact_file(
            tmp_path, ".yuleosh/artifacts/result.json", '{"old": true}'
        )
        session.artifacts["result"] = str(art)

        def _good_llm(*args, **kwargs):
            art.write_text('{"new": true}', encoding="utf-8")
            return {"content": "output", "usage": {}}

        from yuleosh.pipeline.llm_gateway import call_step_llm
        with patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync",
                   side_effect=_good_llm):
            call_step_llm(session, "system", "user")

        # New content must persist after successful call
        assert json.loads(art.read_text()) == {"new": True}
