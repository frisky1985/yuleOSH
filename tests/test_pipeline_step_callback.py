"""Option B 验证: 编排器每步实时回写看板 (checkpoint) 的确定性单测。

覆盖三层:
1. _invoke_step_callback — 每步触发 + 吞异常 (绝不影响主链路)。
2. _publish_orchestrator_checkpoint(emit_run_done=False) — 增量状态 + emit checkpoint,
   但不 emit run_done; 进度按已完成步比例计算。
3. _execute_step — 每步 return 前用『已增量更新』的 session 调 step_callback。
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from yuleosh.pipeline.orchestrator import (
    _execute_step, _invoke_step_callback, _propagate_step_verdict,
)
from yuleosh.api.pipeline import (
    _publish_orchestrator_checkpoint, _make_orchestrator_step_callback,
)


class _FakeSession:
    def __init__(self):
        self.steps = []
        self.step_key = None

    def add_step(self, name, agent, action):
        self.steps.append({"step": len(self.steps) + 1, "name": name,
                           "status": "pending", "errors": []})
        return self.steps[-1]

    def start_step(self, i):
        if i < len(self.steps):
            self.steps[i]["status"] = "running"

    def complete_step(self, i, path):
        if i < len(self.steps):
            self.steps[i]["status"] = "completed"
            self.steps[i]["output_path"] = path

    def fail_step(self, i, err):
        if i < len(self.steps):
            self.steps[i]["status"] = "failed"
            self.steps[i]["errors"].append(err)

    def set_artifact(self, k, path):
        pass


class TestInvokeStepCallback(unittest.TestCase):
    def test_called_once_with_session(self):
        seen = []
        _invoke_step_callback(lambda s: seen.append(s), "SESS")
        self.assertEqual(seen, ["SESS"])

    def test_none_is_noop(self):
        # 不应抛错
        _invoke_step_callback(None, "SESS")

    def test_swallows_callback_exception(self):
        def boom(_s):
            raise RuntimeError("boom")
        # 绝不能把异常透传到主链路
        _invoke_step_callback(boom, "SESS")


class TestPublishCheckpointPerStep(unittest.TestCase):
    def _fake_session(self):
        s = _FakeSession()
        s.add_step("step-a", "a", "A")
        s.add_step("step-b", "b", "B")
        s.steps[0]["status"] = "completed"   # 1/2 已完成
        s.steps[1]["status"] = "pending"
        return s

    @patch("yuleosh.realtime.emit_pipeline_run_done")
    @patch("yuleosh.realtime.emit_pipeline_checkpoint")
    @patch("yuleosh.engine.checkpoint.CheckpointEngine")
    @patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS",
           [("step-a", "a", "A", lambda s: None),
            ("step-b", "b", "B", lambda s: None)])
    def test_running_no_run_done_emits_progress(self, _ckpt, _emit, _run_done):
        sess = self._fake_session()
        _publish_orchestrator_checkpoint(
            "/tmp/proj", "run1", "demo", "running",
            "2026-01-01T00:00:00", "2026-01-01T00:00:01", sess,
            emit_run_done=False,
        )
        _emit.assert_called_once()
        _kw = _emit.call_args.kwargs
        self.assertEqual(_kw["status"], "running")
        self.assertAlmostEqual(_kw["progress_pct"], 50.0, places=1)
        _run_done.assert_not_called()   # 每步不推 run_done

    @patch("yuleosh.realtime.emit_pipeline_run_done")
    @patch("yuleosh.realtime.emit_pipeline_checkpoint")
    @patch("yuleosh.engine.checkpoint.CheckpointEngine")
    @patch("yuleosh.pipeline.step_handlers.PIPELINE_STEPS",
           [("step-a", "a", "A", lambda s: None),
            ("step-b", "b", "B", lambda s: None)])
    def test_completed_emits_run_done_progress_100(self, _ckpt, _emit, _run_done):
        sess = self._fake_session()
        sess.steps[1]["status"] = "completed"  # 现在 2/2
        _publish_orchestrator_checkpoint(
            "/tmp/proj", "run1", "demo", "completed",
            "2026-01-01T00:00:00", "2026-01-01T00:00:01", sess,
            emit_run_done=True,
        )
        _emit.assert_called_once()
        self.assertAlmostEqual(_emit.call_args.kwargs["progress_pct"], 100.0, places=1)
        _run_done.assert_called_once()   # 终态推 run_done


class TestExecuteStepInvokesCallback(unittest.TestCase):
    def test_callback_called_with_incremental_session(self):
        sess = _FakeSession()
        sess.add_step("t", "agent", "T")
        seen = []
        out = Path(tempfile.gettempdir()) / "step_out.md"

        def handler(_s):
            return str(out)

        with patch("yuleosh.pipeline.orchestrator._propagate_step_verdict",
                   return_value="ok"), \
             patch("yuleosh.realtime.emit_pipeline_stage_start"), \
             patch("yuleosh.realtime.emit_pipeline_stage_end"), \
             patch("yuleosh.realtime.emit_pipeline_file_produced"):
            _execute_step(
                sess, 0, "t", "agent", "T", handler,
                "/tmp/spec.md", "/tmp/proj", 0,
                step_callback=seen.append,
            )
        self.assertEqual(len(seen), 1)
        # 回调触发时 session.steps[0] 已是 completed (增量状态)
        self.assertEqual(seen[0].steps[0]["status"], "completed")
        self.assertEqual(sess.steps[0]["status"], "completed")


class TestMakeStepCallback(unittest.TestCase):
    def test_factory_returns_callable(self):
        rec = {"started_at": "2026-01-01T00:00:00"}
        cb = _make_orchestrator_step_callback("/tmp/proj", "run1", "demo", rec)
        self.assertTrue(callable(cb))
        # 不应抛 (内部 publish 在 mock 下)
        with patch("yuleosh.api.pipeline._publish_orchestrator_checkpoint") as m:
            cb(_FakeSession())
            m.assert_called_once()
            self.assertFalse(m.call_args.kwargs["emit_run_done"])


if __name__ == "__main__":
    unittest.main()
