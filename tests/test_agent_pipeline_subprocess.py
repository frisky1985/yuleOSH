"""方案 B2 测试 — subprocess 执行器 + 产物一致性门禁 + sqlite 状态隔离。

覆盖矩阵：
  1. B2-1: subprocess runner 单步执行（worker 子进程 + 结果 JSON 回传）
  2. B2-1: agent_checkpoint --executor=subprocess --mock 跑通 33 步全链
  3. B2-2: 产物门禁三分支 — 存在→PASS / 缺失→FAIL(error 含 artifact) / 空文件→FAIL
  4. B2-3: sqlite 后端 save/load 往返；并发写不抛 database is locked
  5. B2-4: subprocess 模式 resume 从失败步续跑
"""

# @tests src/yuleosh/agent_registry.py

import json
import os
import sys
import threading
from pathlib import Path

from yuleosh.engine.checkpoint import CheckpointEngine, StepStatus
from yuleosh.engine.handler_adapter import HandlerAdapter
from yuleosh.engine.subprocess_executor import (
    make_subprocess_runner,
    worker_main,
)
from yuleosh.pipeline.session import PipelineSession

# ---------------------------------------------------------------------------
# B2-1: subprocess runner
# ---------------------------------------------------------------------------

MINI_SPEC = """# Spec

## REQ-001: Minimal pipeline spec

- The system SHALL run the pipeline end to end
- The system SHALL produce a final report

### Reason
Test fixture spec for subprocess pipeline tests (B2-1).
"""

# B1 已知豁免：qemu-run / review-critical-safety 的产物不是真实文件
# （mock 分支返回 dict / pre-check 假路径）。B2-2 门禁修复了 BaseHandler
# 的 skip 分支（写真实 skipped 报告），qemu-run 现在也应产出真实文件；
# 若仍失败，作为已知豁免文档化。
KNOWN_NONFILE_ARTIFACTS = {"review-critical-safety"}


def _make_spec(tmp_path) -> Path:
    """创建真实 spec 文件（spec-check 步骤需要；放 docs/ 匹配 worker fallback）。"""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    spec = docs / "spec.md"
    spec.write_text(MINI_SPEC, encoding="utf-8")
    return spec


class TestSubprocessRunner:
    def test_worker_main_returns_passed_json(self, tmp_path):
        """worker 入口：spec-check 步骤在 mock 模式执行并回传 passed JSON。"""
        spec = _make_spec(tmp_path)
        out = tmp_path / "worker.out"
        with out.open("w") as f:
            old_stdout = sys.stdout
            sys.stdout = f
            try:
                rc = worker_main(["--step-id", "spec-check",
                                  "--project-dir", str(tmp_path),
                                  "--spec-path", str(spec),
                                  "--mock"])
            finally:
                sys.stdout = old_stdout
        assert rc == 0
        payload = json.loads(out.read_text().strip().splitlines()[-1])
        assert payload["verdict"] == "passed"
        assert payload["output_path"]

    def test_make_subprocess_runner_single_step(self, tmp_path):
        """runner 钩子：提交一步到子进程并拿到 StepResult。"""
        _make_spec(tmp_path)
        runner = make_subprocess_runner(str(tmp_path), mock_mode=True)
        step_def = {"step_id": "spec-check", "name": "OpenSpec 合规检查", "agent": "小明"}
        result = runner(step_def)
        assert result.verdict == "passed"
        assert result.output_path

    def test_make_subprocess_runner_unknown_step_fails(self, tmp_path):
        """未知 step_id → runner 返回 failed（不抛异常）。"""
        _make_spec(tmp_path)
        runner = make_subprocess_runner(str(tmp_path), mock_mode=True)
        result = runner({"step_id": "no-such-step", "name": "x", "agent": ""})
        assert result.verdict == "failed"
        assert "not found" in (result.error or "")

    def test_engine_with_runner_runs_pipeline(self, tmp_path, monkeypatch):
        """CheckpointEngine + subprocess runner：3 步全链全绿。"""
        monkeypatch_osh(tmp_path, monkeypatch)
        spec = _make_spec(tmp_path)
        engine = CheckpointEngine(
            "b2-subproc", str(tmp_path),
            runner=make_subprocess_runner(
                str(tmp_path), mock_mode=True, spec_path=str(spec),
                session_name="b2-subproc-3step",
            ),
        )
        # 用真实 PIPELINE_STEPS 里的 handler 无法在测试里构造轻量步骤，
        # 这里用 runner 直接驱动 3 个真实步骤（mock 模式不依赖项目文件）。
        for sid in ("spec-check", "super-analysis", "prd"):
            engine.add_step(sid, sid, None)  # handler 为 None → runner 侧执行
        # runner 分支不检查 handler，直接走 runner
        engine._step_defs = [
            {"step_id": "spec-check", "name": "spec", "agent": "小明", "handler": None},
            {"step_id": "super-analysis", "name": "super", "agent": "小明", "handler": None},
            {"step_id": "prd", "name": "prd", "agent": "Hermes", "handler": None},
        ]
        assert engine.run() is True
        assert [s.status for s in engine._state.steps] == [
            StepStatus.PASSED, StepStatus.PASSED, StepStatus.PASSED,
        ]

    def test_cli_subprocess_33_steps_mock(self, tmp_path, monkeypatch):
        """CLI: --executor=subprocess --mock 跑通 33 步全链（主进程 checkpoint 完整）。"""
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline
        from yuleosh.engine.subprocess_executor import make_subprocess_runner

        monkeypatch_osh(tmp_path, monkeypatch)
        spec = _make_spec(tmp_path)
        engine = create_agent_pipeline(str(tmp_path), str(spec), mock_mode=True)
        engine.runner = make_subprocess_runner(
            str(tmp_path), mock_mode=True, spec_path=str(spec),
            session_name="b2-subproc-shared",
        )
        assert engine.run() is True
        state = engine.status()
        assert state is not None
        assert state["status"] == "completed"
        # 行为一致性：subprocess 模式跑出的步骤数必须与注册表同步（单一事实源）
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(state["steps"]) == len(PIPELINE_STEPS)
        assert all(s["status"] == "passed" for s in state["steps"])


def monkeypatch_osh(tmp_path, monkeypatch=None):
    """把 OSH_HOME 指到 tmp_path，隔离 session 目录。

    B2 修复（2026-08-08）：必须通过 pytest monkeypatch 设置并在测试后恢复，
    否则 os.environ 污染泄漏到后续测试（test_api.py temp_spec_file 用
    OSH_HOME 定位 docs/spec.md → 全量跑 11 errors）。
    """
    if monkeypatch is not None:
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
    else:
        os.environ["OSH_HOME"] = str(tmp_path)

# ---------------------------------------------------------------------------
# B2-2: artifact consistency gate
# ---------------------------------------------------------------------------


class TestArtifactGate:
    def _engine(self, tmp_path):
        return CheckpointEngine("gate", str(tmp_path))

    def test_artifact_exists_passes(self, tmp_path):
        """产物存在且非空 → PASSED。"""
        engine = self._engine(tmp_path)
        out = tmp_path / "real.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        assert engine.run() is True
        assert engine._state.steps[0].status == StepStatus.PASSED

    def test_artifact_missing_fails(self, tmp_path):
        """产物路径不存在 → FAILED（error 含 artifact）。"""
        engine = self._engine(tmp_path)
        missing = tmp_path / "ghost.json"

        def handler(session):
            return str(missing)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        assert engine.run() is False
        rec = engine._state.steps[0]
        assert rec.status == StepStatus.FAILED
        assert "artifact" in (rec.error or "")

    def test_artifact_empty_fails(self, tmp_path):
        """产物文件为空 → FAILED（error 含 artifact）。"""
        engine = self._engine(tmp_path)
        empty = tmp_path / "empty.json"
        empty.write_text("", encoding="utf-8")

        def handler(session):
            return str(empty)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        assert engine.run() is False
        rec = engine._state.steps[0]
        assert rec.status == StepStatus.FAILED
        assert "artifact" in (rec.error or "")

    def test_no_output_path_no_gate(self, tmp_path):
        """output_path 为 None → 不强制产物（无产物步骤）。"""
        engine = self._engine(tmp_path)

        def handler(session):
            return None

        engine.add_step("s1", "一", HandlerAdapter(handler))
        assert engine.run() is True
        assert engine._state.steps[0].status == StepStatus.PASSED

    def test_set_artifact_soft_check_marks_missing(self, tmp_path, monkeypatch):
        """set_artifact 软校验：缺失文件标记 artifact_missing，不抛异常。"""
        monkeypatch_osh(tmp_path, monkeypatch)
        session = PipelineSession(
            name="b2-soft", spec_path=str(tmp_path / "spec.md"),
        )
        session.project_dir = str(tmp_path)
        session.set_artifact("k1", str(tmp_path / "nope.json"))
        assert session.artifact_missing["k1"] == "missing"

        real = tmp_path / "real.json"
        real.write_text("x", encoding="utf-8")
        session.set_artifact("k2", str(real))
        assert "k2" not in session.artifact_missing


# ---------------------------------------------------------------------------
# B2-3: sqlite state isolation
# ---------------------------------------------------------------------------


class TestSqliteState:
    def test_sqlite_save_load_roundtrip(self, tmp_path):
        """sqlite 后端：run 全绿后 status() 能从 db 读回完整状态。"""
        engine = CheckpointEngine("b2-sqlite", str(tmp_path), state_backend="sqlite")
        out = tmp_path / "r.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        engine.add_step("s2", "二", HandlerAdapter(handler))
        assert engine.run() is True

        # 新实例从 sqlite 读回
        reader = CheckpointEngine("b2-sqlite", str(tmp_path), state_backend="sqlite")
        state = reader.status()
        assert state is not None
        assert state["status"] == "completed"
        assert len(state["steps"]) == 2
        assert [s["status"] for s in state["steps"]] == ["passed", "passed"]

    def test_sqlite_concurrent_writes_no_lock(self, tmp_path):
        """并发写 sqlite 状态：多线程同时 save 不抛 database is locked。"""
        engine = CheckpointEngine("b2-conc", str(tmp_path), state_backend="sqlite")
        out = tmp_path / "r.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        engine.run()  # 先建立 state

        errors: list[Exception] = []
        barrier = threading.Barrier(4)

        def writer():
            try:
                barrier.wait(timeout=10)
                for _ in range(5):
                    engine._save_state()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert errors == []

        # 状态仍可读回（未被并发写损坏）
        reader = CheckpointEngine("b2-conc", str(tmp_path), state_backend="sqlite")
        assert reader.status() is not None

    def test_clear_state_sqlite(self, tmp_path):
        """clear_state(backend=sqlite) 清空表。"""
        engine = CheckpointEngine("b2-clear", str(tmp_path), state_backend="sqlite")
        out = tmp_path / "r.json"
        out.write_text("{}", encoding="utf-8")

        def handler(session):
            return str(out)

        engine.add_step("s1", "一", HandlerAdapter(handler))
        engine.run()
        CheckpointEngine.clear_state(str(tmp_path), backend="sqlite")
        reader = CheckpointEngine("b2-clear", str(tmp_path), state_backend="sqlite")
        assert reader.status() is None


# ---------------------------------------------------------------------------
# B2-4: resume in subprocess mode
# ---------------------------------------------------------------------------


class TestSubprocessResume:
    def test_resume_from_failed_step_subprocess(self, tmp_path):
        """subprocess 模式：注入失败 → resume 从失败步续跑。

        用 runner 模拟：第 2 步 runner 先返回 failed，修好后 resume 全过。
        """
        engine = CheckpointEngine("b2-sub-resume", str(tmp_path))
        fail = {"on": True}
        calls: list[str] = []

        def fake_runner(step_def, artifacts=None):
            calls.append(step_def["step_id"])
            if step_def["step_id"] == "s2" and fail["on"]:
                from yuleosh.engine.handler_adapter import StepResult
                return StepResult(verdict="failed", error="injected subprocess fail")
            out = tmp_path / f"{step_def['step_id']}.json"
            out.write_text("{}", encoding="utf-8")
            from yuleosh.engine.handler_adapter import StepResult
            return StepResult(verdict="passed", output_path=str(out))

        engine.runner = fake_runner
        for sid in ("s1", "s2", "s3"):
            engine.add_step(sid, sid, None)

        assert engine.run() is False
        recs = engine.status()
        assert recs is not None
        assert [r["status"] for r in recs["steps"]] == ["passed", "failed", "pending"]

        fail["on"] = False
        assert engine.run(resume=True) is True
        final = engine.status()
        assert [r["status"] for r in final["steps"]] == ["passed", "passed", "passed"]
        assert calls == ["s1", "s2", "s2", "s3"]
