"""P1 渐进执行模式测试 — 覆盖状态机、pause/resume、持久化、一键模式兼容。

核心测试策略：patch 掉耗时 stage 函数（_stage_wait_pipeline / _stage_collect /
_stage_reports / _stage_pack），专注测 run_incremental_stage 的**编排逻辑**：
  - 状态初始化 / 读取 / 写回
  - waiting_confirm + confirm 的分支行为
  - target_stage 校验（不能回退）
  - 异常时 status=failed + error 持久化
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """隔离的 OSH 项目目录。"""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    return str(tmp_path)


@pytest.fixture
def stub_stages():
    """Mock 掉 4 个 stage 函数，只做 _advance_state 推进。

    用法::
        with patch.object(pack_mod, "_stage_wait_pipeline", side_effect=stub_wait), \\
             patch.object(pack_mod, "_stage_collect", side_effect=stub_collect), \\
             ...:
            run_incremental_stage(...)
    """
    from yuleosh.evidence.pack import _advance_state

    def _stub_wait(dir_, state, **kw):
        return _advance_state(state, "collect", status="waiting_confirm")

    def _stub_collect(dir_, state, **kw):
        return _advance_state(state, "reports", status="waiting_confirm")

    def _stub_reports(dir_, state, **kw):
        return _advance_state(state, "pack", status="waiting_confirm")

    def _stub_pack(dir_, state, **kw):
        return _advance_state(state, "done", status="done")

    return {
        "_stage_wait_pipeline": _stub_wait,
        "_stage_collect": _stub_collect,
        "_stage_reports": _stub_reports,
        "_stage_pack": _stub_pack,
    }


# ---------- 状态机基础 ----------

class TestIncrementalStateMachine:
    def test_stage_order_is_linear(self):
        from yuleosh.evidence.pack import STAGE_ORDER, STAGE_LABELS
        assert STAGE_ORDER == ("wait_pipeline", "collect", "reports", "pack", "done")
        assert all(s in STAGE_LABELS for s in STAGE_ORDER)

    def test_initial_state(self, project_dir):
        from yuleosh.evidence.pack import _initial_state, _load_state
        state = _load_state(project_dir)
        assert state["stage"] == "wait_pipeline"
        assert state["status"] == "pending"
        assert state["completed_stages"] == []
        assert state["version"] == "1"

    def test_save_and_load_roundtrip(self, project_dir):
        from yuleosh.evidence.pack import _save_state, _load_state, _initial_state
        state = _initial_state()
        state["stage"] = "collect"
        state["status"] = "waiting_confirm"
        state["completed_stages"] = ["wait_pipeline"]
        _save_state(project_dir, state)

        loaded = _load_state(project_dir)
        assert loaded["stage"] == "collect"
        assert loaded["status"] == "waiting_confirm"
        assert loaded["completed_stages"] == ["wait_pipeline"]

    def test_corrupt_state_file_falls_back_to_initial(self, project_dir):
        from yuleosh.evidence.pack import _state_path, _load_state
        p = _state_path(project_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("not-json-at-all{{{")
        state = _load_state(project_dir)
        assert state["status"] == "pending"
        assert state["stage"] == "wait_pipeline"

    def test_advance_state_proceeds(self):
        from yuleosh.evidence.pack import _advance_state, _initial_state
        state = _initial_state()
        state["stage"] = "wait_pipeline"
        next_state = _advance_state(state, "collect", status="waiting_confirm")
        assert next_state["stage"] == "collect"
        assert next_state["status"] == "waiting_confirm"
        assert "wait_pipeline" in next_state["completed_stages"]


# ---------- GET status ----------

class TestGetStatus:
    def test_no_session_returns_initial_with_progress(self, project_dir):
        from yuleosh.evidence.pack import get_incremental_status
        status = get_incremental_status(project_dir)
        assert status["stage"] == "wait_pipeline"
        assert status["progress_pct"] == 0
        assert "stage_label" in status
        assert isinstance(status["progress_pct"], int)

    def test_progress_midway(self, project_dir):
        from yuleosh.evidence.pack import _save_state, get_incremental_status
        state = {"stage": "reports", "status": "waiting_confirm", "version": "1",
                 "started_at": None, "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect"],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)
        status = get_incremental_status(project_dir)
        assert status["progress_pct"] == 50  # 5 stages → 25% each, reports=3rd → 50%

    def test_done_is_100_percent(self, project_dir):
        from yuleosh.evidence.pack import _save_state, get_incremental_status
        state = {"stage": "done", "status": "done", "version": "1",
                 "started_at": None, "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect", "reports", "pack"],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)
        status = get_incremental_status(project_dir)
        assert status["progress_pct"] == 100

    def test_running_stage_progress(self, project_dir):
        from yuleosh.evidence.pack import _save_state, get_incremental_status
        state = {"stage": "pack", "status": "running", "version": "1",
                 "started_at": None, "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect", "reports"],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)
        status = get_incremental_status(project_dir)
        assert status["progress_pct"] == 75


# ---------- Reset ----------

class TestResetState:
    def test_reset_deletes_state_and_pickle(self, project_dir):
        from yuleosh.evidence.pack import _save_state, reset_incremental_state, _state_path
        state = {"stage": "reports", "status": "waiting_confirm", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect"],
                 "artifacts_so_far": ["/tmp/a.md"], "error": None}
        _save_state(project_dir, state)
        pickle_path = Path(project_dir) / ".osh" / "evidence" / ".collector.pkl"
        pickle_path.write_bytes(b"dummy")

        reset_incremental_state(project_dir)

        assert not _state_path(project_dir).exists()
        assert not pickle_path.exists()

    def test_reset_returns_initial(self, project_dir):
        from yuleosh.evidence.pack import reset_incremental_state
        state = reset_incremental_state(project_dir)
        assert state["stage"] == "wait_pipeline"
        assert state["status"] == "pending"


# ---------- run_incremental_stage 核心编排 ----------

class TestRunIncrementalStage:
    def _patch_stages(self, stub_stages):
        """返回一个上下文管理器列表，patch 所有 4 个 stage 函数。"""
        patches = []
        import yuleosh.evidence.pack as pack_mod
        for name, stub in stub_stages.items():
            patches.append(patch.object(pack_mod, name, stub))
        return patches

    def test_waiting_confirm_without_confirm_returns_current(self, project_dir):
        """waiting_confirm + confirm=False + 无 target_stage → 仅查询，不推进。"""
        from yuleosh.evidence.pack import run_incremental_stage, _save_state
        state = {"stage": "collect", "status": "waiting_confirm", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline"],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)

        result = run_incremental_stage(project_dir, confirm=False)
        assert result["stage"] == "collect"
        assert result["status"] == "waiting_confirm"
        assert result["completed_stages"] == ["wait_pipeline"]

    def test_target_stage_before_current_rejected(self, project_dir):
        """target_stage 早于当前 stage → ValueError，即使 waiting_confirm 也不能绕过。"""
        from yuleosh.evidence.pack import run_incremental_stage, _save_state
        state = {"stage": "reports", "status": "waiting_confirm", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect"],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)

        with pytest.raises(ValueError, match="不能早于"):
            run_incremental_stage(project_dir, target_stage="collect")

    def test_full_run_to_done(self, project_dir, stub_stages):
        """端到端：wait_pipeline → collect → reports → pack → done（全部 stub）。"""
        from yuleosh.evidence.pack import run_incremental_stage
        patches = self._patch_stages(stub_stages)
        # 一个 with 里展开所有 patch
        cm = patches[0]
        for p in patches[1:]:
            cm = cm.__enter__() if False else None  # 不用这个，用 contextlib.ExitStack

        # 简化：直接用上下文管理器嵌套
        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            result = run_incremental_stage(project_dir, target_stage="done")

        assert result["status"] == "done"
        assert result["stage"] == "done"
        assert result["completed_stages"] == ["wait_pipeline", "collect", "reports", "pack"]

    def test_single_stage_run(self, project_dir, stub_stages):
        """指定 target_stage='collect' → 只跑 wait_pipeline + collect。"""
        from yuleosh.evidence.pack import run_incremental_stage
        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            result = run_incremental_stage(project_dir, target_stage="collect")

        assert result["stage"] == "reports"  # collect 完 → waiting_confirm 在 reports
        assert result["status"] == "waiting_confirm"
        assert result["completed_stages"] == ["wait_pipeline", "collect"]

    def test_exception_sets_failed_status(self, project_dir):
        """stage 抛异常 → status=failed + error 落盘。"""
        from yuleosh.evidence.pack import run_incremental_stage, _load_state

        def _boom(*args, **kwargs):
            raise RuntimeError("intentional stage failure")

        with patch("yuleosh.evidence.pack._stage_wait_pipeline", _boom):
            with pytest.raises(RuntimeError, match="intentional stage failure"):
                run_incremental_stage(project_dir)

        state = _load_state(project_dir)
        assert state["status"] == "failed"
        assert "intentional stage failure" in state["error"]

    def test_pause_and_resume(self, project_dir, stub_stages):
        """模拟 pause 然后 resume（confirm=True 推进到下一 stage 并执行）。"""
        from yuleosh.evidence.pack import run_incremental_stage, _save_state

        # 造一个 waiting_confirm（collect 刚跑完）
        state = {"stage": "reports", "status": "waiting_confirm", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": ["wait_pipeline", "collect"],
                 "artifacts_so_far": ["trace.md"], "error": None}
        _save_state(project_dir, state)

        # Step 1: 只查询
        q = run_incremental_stage(project_dir, confirm=False)
        assert q["status"] == "waiting_confirm"
        assert q["stage"] == "reports"

        # Step 2: confirm=True → 执行当前待确认阶段 reports → 推进到 pack
        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            resumed = run_incremental_stage(project_dir, confirm=True)

        # 跑完 reports → stage=pack，等待确认 pack
        assert resumed["stage"] == "pack"
        assert resumed["status"] == "waiting_confirm"
        assert "reports" in resumed["completed_stages"]
        assert "pack" not in resumed["completed_stages"]

    def test_no_target_stages_runs_one(self, project_dir, stub_stages):
        """target_stage=None → 只跑当前一个 stage。"""
        from yuleosh.evidence.pack import run_incremental_stage, _save_state

        state = {"stage": "wait_pipeline", "status": "running", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": [],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)

        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            result = run_incremental_stage(project_dir)  # 无 target_stage

        # 只跑了 wait_pipeline → 推进到 collect 的 waiting_confirm
        assert result["stage"] == "collect"
        assert result["status"] == "waiting_confirm"
        assert result["completed_stages"] == ["wait_pipeline"]


# ---------- generate_evidence 兼容性 ----------

class TestGenerateEvidenceCompat:
    def test_incremental_true_uses_engine(self, project_dir, stub_stages):
        from yuleosh.evidence.pack import generate_evidence, _state_path

        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            artifacts = generate_evidence(project_dir=project_dir, incremental=True)

        assert isinstance(artifacts, list)
        assert _state_path(project_dir).exists()
        state = json.loads(_state_path(project_dir).read_text())
        assert state["status"] == "done"
        assert state["stage"] == "done"

    def test_incremental_false_skips_engine(self, project_dir, stub_stages):
        """incremental=False → 跳过 run_incremental_stage，走原有一键路径（默认）。"""
        from yuleosh.evidence.pack import generate_evidence, _state_path

        # 原有一键路径会调 EvidenceCollector → 需要 mock 掉
        from unittest.mock import MagicMock
        mock_collector = MagicMock()
        mock_collector.project_dir = project_dir
        mock_collector.requirements = [{}]
        mock_collector.reviews = []
        mock_collector.ci_results = []
        mock_collector.sil_reports = []
        mock_collector.evidence_dir = Path(project_dir) / ".osh" / "evidence"
        mock_collector.generate_traceability_matrix.return_value = "trace.md"
        mock_collector.generate_requirement_coverage.return_value = "coverage.md"
        mock_collector.generate_code_coverage_report.return_value = "codecov.md"
        mock_collector.generate_acceptance_matrix.return_value = "acceptance.md"
        mock_collector.aggregate_review_logs.return_value = "reviews.md"

        with patch("yuleosh.evidence.pack._check_pipeline_not_running", return_value=True), \
             patch("yuleosh.evidence.pack.EvidenceCollector", return_value=mock_collector), \
             patch("yuleosh.evidence.pack.pack_compliance_zip", return_value="compliance-pack.zip"):
            artifacts = generate_evidence(project_dir=project_dir, incremental=False)

        assert isinstance(artifacts, list)
        # 原有一键路径不调用 run_incremental_stage → 不写 .state.json
        assert not _state_path(project_dir).exists()


# ---------- CLI 入口 ----------

class TestCLI:
    def test_status_command(self, project_dir, capsys):
        from yuleosh.evidence.pack import main
        import sys
        sys.argv = ["pack", "status"]
        main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["stage"] == "wait_pipeline"
        assert "progress_pct" in data

    def test_reset_command(self, project_dir, capsys):
        from yuleosh.evidence.pack import main
        import sys
        sys.argv = ["pack", "reset"]
        main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["stage"] == "wait_pipeline"
        assert data["status"] == "pending"

    def test_stage_command_target(self, project_dir, stub_stages, capsys):
        from yuleosh.evidence.pack import main
        import sys
        # 需要把 sys.argv 改成 [module_name, "stage", "collect"]
        sys.argv = ["pack", "stage", "collect"]

        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            main()

        out = capsys.readouterr().out
        data = json.loads(out)
        # 跑到 collect → 推进到 reports 的 waiting_confirm
        assert data["stage"] == "reports"
        assert data["completed_stages"] == ["wait_pipeline", "collect"]

    def test_resume_command_confirm(self, project_dir, stub_stages, capsys):
        from yuleosh.evidence.pack import main, _save_state
        import sys
        # 先造一个 waiting_confirm 状态
        state = {"stage": "wait_pipeline", "status": "waiting_confirm", "version": "1",
                 "started_at": "2026-10-18T00:00:00", "current_stage_started_at": None,
                 "completed_stages": [],
                 "artifacts_so_far": [], "error": None}
        _save_state(project_dir, state)

        sys.argv = ["pack", "resume", "--confirm"]
        with patch("yuleosh.evidence.pack._stage_wait_pipeline", stub_stages["_stage_wait_pipeline"]), \
             patch("yuleosh.evidence.pack._stage_collect", stub_stages["_stage_collect"]), \
             patch("yuleosh.evidence.pack._stage_reports", stub_stages["_stage_reports"]), \
             patch("yuleosh.evidence.pack._stage_pack", stub_stages["_stage_pack"]):
            main()

        out = capsys.readouterr().out
        data = json.loads(out)
        # confirm → 执行 wait_pipeline → 推进到 collect（待确认）
        assert "wait_pipeline" in data["completed_stages"]
        assert data["stage"] == "collect"
