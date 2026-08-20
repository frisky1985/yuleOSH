"""Tests for pipeline deploy-anchor (审查锚定) + resume + INCOMPLETE verdict.

Covers (2026-08-12 sprint):
  1. deploy_state — codegen 部署状态判定 (no-report/deployed/skipped)
  2. maybe_skip_code_review — 无部署时审查 honest-skip
  3. 真实审查 handler (review-memory) 在无部署时输出 status=skipped
  4. _propagate_step_verdict — INCOMPLETE 按 gate 强度处置
  5. _find_previous_session — 断点续跑的上一 session 查找
"""

import json
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. deploy_state
# ---------------------------------------------------------------------------

class TestDeployState:
    def _write_report(self, project_dir, status, deployed=None):
        report_dir = Path(project_dir) / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": status, "deployed": deployed or []}),
            encoding="utf-8",
        )

    def test_no_report_is_conservative(self, tmp_path):
        """无报告 → 保守 True (审查照常, 不因缺报告误 skip)。"""
        from yuleosh.pipeline.deploy_state import has_deployed_code
        assert has_deployed_code(tmp_path) is True

    def test_deployed_status(self, tmp_path):
        from yuleosh.pipeline.deploy_state import (
            has_deployed_code, deployed_files, deploy_status,
        )
        self._write_report(tmp_path, "deployed", ["src/app/window_control.c"])
        assert deploy_status(tmp_path) == "deployed"
        assert has_deployed_code(tmp_path) is True
        assert deployed_files(tmp_path) == ["src/app/window_control.c"]

    def test_skipped_codegen_failed(self, tmp_path):
        from yuleosh.pipeline.deploy_state import (
            has_deployed_code, deployed_files,
        )
        self._write_report(tmp_path, "skipped_codegen_failed")
        assert has_deployed_code(tmp_path) is False
        assert deployed_files(tmp_path) == []

    def test_skipped_api_mismatch(self, tmp_path):
        from yuleosh.pipeline.deploy_state import has_deployed_code
        self._write_report(tmp_path, "skipped_api_mismatch")
        assert has_deployed_code(tmp_path) is False

    def test_skipped_planning_mode(self, tmp_path):
        from yuleosh.pipeline.deploy_state import has_deployed_code
        self._write_report(tmp_path, "skipped")
        assert has_deployed_code(tmp_path) is False


# ---------------------------------------------------------------------------
# 2. maybe_skip_code_review
# ---------------------------------------------------------------------------

class FakeSession:
    def __init__(self, project_dir, session_dir):
        self.name = "test-run"
        self.project_dir = str(project_dir) if project_dir is not None else None
        self.session_dir = Path(session_dir)
        self.spec_path: str = ""
        self.mock_mode: bool = False


class TestMaybeSkipCodeReview:
    def test_no_deploy_returns_skip_report(self, tmp_path):
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "skipped_codegen_failed", "deployed": []})
        )
        session = FakeSession(tmp_path, tmp_path / ".osh" / "sessions" / "s1")
        session.session_dir.mkdir(parents=True)

        out = maybe_skip_code_review(session, "review-memory", reviewer="小克")
        assert out is not None
        data = json.loads(Path(out).read_text())
        assert data["status"] == "skipped"
        assert data["deploy_status"] == "skipped_codegen_failed"
        assert "无代码部署" in data["reason"]

    def test_deployed_returns_none(self, tmp_path):
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed", "deployed": ["src/app.c"]})
        )
        session = FakeSession(tmp_path, tmp_path / ".osh" / "sessions" / "s1")
        assert maybe_skip_code_review(session, "review-memory") is None

    def test_no_project_dir_ignores_cwd_stray_report(self, tmp_path, monkeypatch):
        """无 project_dir 时不得回退 cwd 读杂散报告 (2026-08-20 污染复盘)。

        仓库根目录残留 .yuleosh/reports/codegen-deploy.json (status=skipped)
        曾导致全量 step-handler 测试误 skip 47+ 项。无项目目录时审查照常。
        """
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review

        # cwd 伪造一个 status=skipped 的杂散报告
        stray = Path.cwd() / ".yuleosh" / "reports"
        stray.mkdir(parents=True, exist_ok=True)
        stray_f = stray / "codegen-deploy.json"
        stray_f.write_text(
            json.dumps({"status": "skipped", "deployed": []}), encoding="utf-8"
        )
        try:
            session = FakeSession(None, tmp_path / ".osh" / "sessions" / "s1")
            session.project_dir = None  # 模拟未设置 project_dir
            assert maybe_skip_code_review(session, "review-memory") is None
        finally:
            stray_f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 3. 真实 handler 锚定 — review-memory 在无部署时输出 skipped
# ---------------------------------------------------------------------------

class TestReviewHandlerAnchor:
    def test_review_memory_skipped_when_no_deploy(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review_memory import step_review_memory

        # 项目目录: OSH_HOME 指向 tmp_path, 无 src/ (扫描会空)
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        # 部署报告: 无部署
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "skipped_codegen_failed", "deployed": []})
        )
        sess_dir = tmp_path / ".osh" / "sessions" / "s1"
        sess_dir.mkdir(parents=True)

        session = FakeSession(tmp_path, sess_dir)
        session.spec_path = str(tmp_path / "spec.md")
        session.mock_mode = False

        out = step_review_memory(session)
        data = json.loads(Path(out).read_text())
        assert data["status"] == "skipped"
        assert data["deploy_status"] == "skipped_codegen_failed"

    def test_review_memory_runs_when_deployed(self, tmp_path, monkeypatch):
        from yuleosh.pipeline.step_handlers.review_memory import step_review_memory

        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        report_dir = tmp_path / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "codegen-deploy.json").write_text(
            json.dumps({"status": "deployed", "deployed": ["src/app.c"]})
        )
        # 给一点源码, 让静态扫描有对象
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "main.c").write_text("#include <stdio.h>\nint main(void){return 0;}\n")

        sess_dir = tmp_path / ".osh" / "sessions" / "s1"
        sess_dir.mkdir(parents=True)
        session = FakeSession(tmp_path, sess_dir)
        session.spec_path = str(tmp_path / "spec.md")
        session.mock_mode = False

        out = step_review_memory(session)
        data = json.loads(Path(out).read_text())
        assert data["status"] != "skipped"  # 有部署 → 真审查


# ---------------------------------------------------------------------------
# 4. _propagate_step_verdict — INCOMPLETE
# ---------------------------------------------------------------------------

class TestPropagateIncomplete:
    def _mk_session(self, tmp_path):
        from yuleosh.pipeline.session import PipelineSession
        sess = PipelineSession("t", str(tmp_path / "spec.md"))
        sess.session_dir = tmp_path / ".osh" / "sessions" / "r1"
        sess.session_dir.mkdir(parents=True, exist_ok=True)
        return sess

    def test_incomplete_block_gate_interrupts(self, tmp_path):
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        sess = self._mk_session(tmp_path)
        sess.add_step("test-qualification", "小明", "合格性测试")
        out = sess.session_dir / "qualification-test.json"
        out.write_text(json.dumps({"status": "incomplete", "step": "test-qualification"}))

        result = _propagate_step_verdict(sess, 0, "test-qualification", str(out))
        assert result == "block"          # block gate → 中断
        assert sess.status == "failed"
        assert any("INCOMPLETE" in e for e in sess.errors)
        assert sess.steps[0]["status"] == "failed"

    def test_incomplete_warn_records_error(self, tmp_path):
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        sess = self._mk_session(tmp_path)
        sess.add_step("review-memory", "小克", "内存安全审查")
        out = sess.session_dir / "memory-review.json"
        out.write_text(json.dumps({"status": "incomplete", "step": "review-memory"}))

        result = _propagate_step_verdict(sess, 0, "review-memory", str(out))
        assert result is None             # warn → 不断链
        assert sess.status != "failed"
        assert any("INCOMPLETE" in e for e in sess.errors)

    def test_skipped_verdict_not_recorded(self, tmp_path):
        """skipped verdict 不进 errors (审查锚定 skip 后不假红)。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        sess = self._mk_session(tmp_path)
        sess.add_step("review-memory", "小克", "内存安全审查")
        out = sess.session_dir / "memory-review.json"
        out.write_text(json.dumps({"status": "skipped", "step": "review-memory"}))

        _propagate_step_verdict(sess, 0, "review-memory", str(out))
        assert sess.errors == []


# ---------------------------------------------------------------------------
# 5. _find_previous_session — 断点续跑
# ---------------------------------------------------------------------------

class TestFindPreviousSession:
    def test_finds_latest_same_spec(self, tmp_path):
        from yuleosh.pipeline.orchestrator import _find_previous_session

        spec = str(tmp_path / "spec.md")
        (tmp_path / "spec.md").write_text("# spec")
        base = tmp_path / ".osh" / "sessions"
        # 两个 session: 一个旧、一个新, 同 spec
        for rid, ts in [("r1", "2026-08-12T01:00:00"), ("r2", "2026-08-12T02:00:00")]:
            d = base / rid
            d.mkdir(parents=True)
            (d / "session.json").write_text(json.dumps({
                "spec_path": spec, "updated_at": ts, "artifacts": {},
            }))
        # 一个不同 spec 的 session (不应匹配)
        d3 = base / "r3"
        d3.mkdir(parents=True)
        (d3 / "session.json").write_text(json.dumps({
            "spec_path": str(tmp_path / "other.md"), "updated_at": "2026-08-12T03:00:00",
        }))

        found = _find_previous_session(spec, str(tmp_path))
        assert found is not None
        assert found[1].name == "r2"     # 最新同 spec

    def test_no_match_returns_none(self, tmp_path):
        from yuleosh.pipeline.orchestrator import _find_previous_session
        assert _find_previous_session(str(tmp_path / "nope.md"), str(tmp_path)) is None
