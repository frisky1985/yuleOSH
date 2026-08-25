"""HandlerAdapter 兼容矩阵测试（PR0 — CheckpointEngine 签名适配层）。

覆盖矩阵：
  1. no-arg 风格：正常返回 / 抛异常（fallback_safe=True→failed+stamped，False→传播）
  2. session 风格：正常返回 / 抛异常（同上）／ ctx/context 别名
  3. invalid 签名构造即 ValueError（fail fast）
  4. 非法 verdict 拒绝（ValueError）
  5. CheckpointEngine 集成：适配层接入 run/resume 全绿，旧 no-arg 路径不碎
"""

# @tests src/yuleosh/agent_registry.py

import pytest

from yuleosh.engine.checkpoint import CheckpointEngine, StepStatus
from yuleosh.engine.handler_adapter import HandlerAdapter, StepResult

# ---------------------------------------------------------------------------
# no-arg 风格
# ---------------------------------------------------------------------------


class TestNoArgStyle:
    def test_noarg_normal_return_str(self):
        """no-arg 正常返回字符串 → passed + output_path。"""

        def handler():
            return "/tmp/out.json"

        result = HandlerAdapter(handler)(session=None)
        assert result.verdict == "passed"
        assert result.output_path == "/tmp/out.json"
        assert result.error is None
        assert result.fallback_stamped is False

    def test_noarg_normal_return_none(self):
        """no-arg 返回 None → passed + output_path=None。"""

        def handler():
            return None

        result = HandlerAdapter(handler)(session=None)
        assert result.verdict == "passed"
        assert result.output_path is None

    def test_noarg_exception_fallback_safe(self):
        """no-arg 抛异常 + fallback_safe=True → failed + fallback_stamped，不抛。"""

        def handler():
            raise RuntimeError("noarg boom")

        adapter = HandlerAdapter(handler, fallback_safe=True)
        result = adapter(session=None)
        assert result.verdict == "failed"
        assert result.fallback_stamped is True
        assert "noarg boom" in (result.error or "")
        assert result.output_path is None

    def test_noarg_exception_re_raise(self):
        """no-arg 抛异常 + fallback_safe=False → 原异常传播（绝不静默降质）。"""

        def handler():
            raise RuntimeError("noarg boom")

        adapter = HandlerAdapter(handler, fallback_safe=False)
        with pytest.raises(RuntimeError, match="noarg boom"):
            adapter(session=None)


# ---------------------------------------------------------------------------
# session 风格
# ---------------------------------------------------------------------------


class TestSessionStyle:
    def test_session_normal_return_str(self):
        """session 风格正常返回 → passed + output_path，session 被透传。"""
        seen = {}

        def handler(session):
            seen["session"] = session
            return "/tmp/session-out.json"

        sess = {"step_id": "s1"}
        result = HandlerAdapter(handler)(session=sess)
        assert result.verdict == "passed"
        assert result.output_path == "/tmp/session-out.json"
        assert seen["session"] is sess

    def test_session_normal_return_stepresult(self):
        """session 风格直接返回 StepResult → 原样透传。"""

        def handler(session):
            return StepResult(verdict="warn", output_path="/tmp/w.json",
                              error="low coverage")

        result = HandlerAdapter(handler)(session=object())
        assert result.verdict == "warn"
        assert result.output_path == "/tmp/w.json"
        assert result.error == "low coverage"

    def test_session_exception_fallback_safe(self):
        """session 风格抛异常 + fallback_safe=True → failed + stamped，不抛。"""

        def handler(session):
            raise ValueError("session boom")

        adapter = HandlerAdapter(handler, fallback_safe=True)
        result = adapter(session=object())
        assert result.verdict == "failed"
        assert result.fallback_stamped is True
        assert "session boom" in (result.error or "")

    def test_session_exception_re_raise(self):
        """session 风格抛异常 + fallback_safe=False → 原异常传播。"""

        def handler(session):
            raise ValueError("session boom")

        adapter = HandlerAdapter(handler, fallback_safe=False)
        with pytest.raises(ValueError, match="session boom"):
            adapter(session=object())

    def test_ctx_and_context_aliases(self):
        """首参名为 ctx / context 同样判定为 session 风格。"""
        seen = []

        def handler_ctx(ctx):
            seen.append("ctx")
            return "/tmp/ctx.json"

        def handler_context(context):
            seen.append("context")
            return "/tmp/context.json"

        assert HandlerAdapter(handler_ctx)(session=object()).output_path == "/tmp/ctx.json"
        assert HandlerAdapter(handler_context)(session=object()).output_path == "/tmp/context.json"
        assert seen == ["ctx", "context"]


# ---------------------------------------------------------------------------
# 签名校验（fail fast）
# ---------------------------------------------------------------------------


class TestSignatureValidation:
    def test_invalid_signature_raises_on_construct(self):
        """首参不是 session/ctx/context → 构造时即抛 ValueError（fail fast）。"""

        def handler(x):  # 非法首参名
            return x

        with pytest.raises(ValueError, match="session/ctx/context|签名不受支持"):
            HandlerAdapter(handler)

    def test_plain_function_with_many_params_raises(self):
        """多位置参数且首参非 session → invalid。"""

        def handler(a, b, c):
            return a

        with pytest.raises(ValueError):
            HandlerAdapter(handler)

    def test_non_callable_raises(self):
        """非可调用对象 → 构造时 TypeError。"""
        with pytest.raises(TypeError, match="可调用"):
            HandlerAdapter("not-a-callable")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 非法 verdict 拒绝
# ---------------------------------------------------------------------------


class TestVerdictValidation:
    def test_invalid_verdict_constructor_rejected(self):
        """直接构造 StepResult 传非法 verdict → ValueError。"""
        with pytest.raises(ValueError, match="非法 verdict"):
            StepResult(verdict="maybe")

    def test_invalid_verdict_dict_return_rejected(self):
        """handler 返回 dict 且 verdict 非法 → 规范化时 ValueError。"""

        def handler():
            return {"verdict": "maybe", "output_path": "/tmp/x"}

        with pytest.raises(ValueError, match="非法 verdict"):
            HandlerAdapter(handler)(session=None)


# ---------------------------------------------------------------------------
# CheckpointEngine 集成（旧测试兼容 + 新适配层）
# ---------------------------------------------------------------------------


class TestEngineIntegration:
    def _artifact(self, tmp_path, name):
        """B2-2: 产物门禁要求 output_path 真实存在。"""
        p = tmp_path / name
        p.write_text("{}", encoding="utf-8")
        return str(p)

    def test_legacy_noarg_handler_still_works(self, tmp_path):
        """旧用例：无参 handler 不经适配层，engine 行为不变。"""
        engine = CheckpointEngine("legacy", str(tmp_path))

        def handler():
            return self._artifact(tmp_path, "legacy.json")

        engine.add_step("s1", "旧步骤", handler)
        assert engine.run() is True
        rec = engine._state.steps[0]
        assert rec.status == StepStatus.PASSED
        assert rec.output_path == str(tmp_path / "legacy.json")

    def test_session_handler_via_adapter_runs_green(self, tmp_path):
        """新适配层：session 风格 handler 经 HandlerAdapter 注册后 run 全绿。"""
        engine = CheckpointEngine("adapter", str(tmp_path))

        def handler(session):
            assert session.step_id == "s1"
            assert session.agent == "小明"
            return self._artifact(tmp_path, "adapter.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler), agent="小明")
        assert engine.run() is True
        rec = engine._state.steps[0]
        assert rec.status == StepStatus.PASSED
        assert rec.output_path == str(tmp_path / "adapter.json")

    def test_resume_with_adapter_continues(self, tmp_path):
        """恢复模式：首次全量成功，第二次 resume 返回 True（无待跑步骤）。"""
        engine = CheckpointEngine("resume-adapter", str(tmp_path))
        calls = []

        def handler(session):
            calls.append(session.step_id)
            return self._artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler))
        engine.add_step("s2", "第二步", HandlerAdapter(handler))
        assert engine.run() is True
        assert calls == ["s1", "s2"]
        # 全部完成后再 resume → 无需续跑
        assert engine.run(resume=True) is True
        assert calls == ["s1", "s2"]

    def test_inject_at_with_adapter(self, tmp_path):
        """注入模式：session 风格适配层从指定步骤开始。"""
        engine = CheckpointEngine("inject-adapter", str(tmp_path))
        calls = []

        def handler(session):
            calls.append(session.step_id)
            return self._artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler))
        engine.add_step("s2", "第二步", HandlerAdapter(handler))
        engine.add_step("s3", "第三步", HandlerAdapter(handler))
        assert engine.run(inject_at="s2") is True
        assert calls == ["s2", "s3"]
        recs = engine._state.steps
        assert recs[0].status == StepStatus.SKIPPED
        assert recs[1].status == StepStatus.PASSED
