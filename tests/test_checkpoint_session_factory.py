"""方案 B1 引擎改造测试 — CheckpointEngine.session_factory 钩子（additive）。

覆盖矩阵：
  1. 不传 session_factory → HandlerAdapter 收到 SimpleNamespace（旧行为完全不变）
  2. 传入 session_factory → HandlerAdapter 收到工厂构造的对象（真实 PipelineSession）
  3. 工厂接收 step_def dict 透传（step_id / name / agent / handler）
  4. create_agent_pipeline：33 步 handler 全部是 HandlerAdapter 实例
  5. create_agent_pipeline：session_factory 构造真实 PipelineSession
     （spec_path / mock_mode / project_dir / llm_client / step 上下文）
  6. spec 不存在时 session 构造仍成功（容错，只记录路径不校验存在）
  7. mock_mode 由调用方控制（默认 False，传 True 生效）
  8. 集成：session_factory + HandlerAdapter run 全绿
"""

from pathlib import Path
from types import SimpleNamespace

from yuleosh.engine.checkpoint import CheckpointEngine, StepStatus
from yuleosh.engine.handler_adapter import HandlerAdapter
from yuleosh.pipeline.session import PipelineSession


def _real_artifact(tmp_path, name: str = "out.json") -> str:
    """B2-2: 产物门禁要求 output_path 真实存在 —— 测试创建真实产物文件。"""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return str(p)

# ---------------------------------------------------------------------------
# CheckpointEngine.session_factory 钩子（B1-1）
# ---------------------------------------------------------------------------


class TestSessionFactoryHook:
    def test_default_no_factory_keeps_simplenamespace(self, tmp_path):
        """不传 session_factory：adapter 收到 SimpleNamespace，旧行为不变。"""
        engine = CheckpointEngine("no-factory", str(tmp_path))
        assert engine.session_factory is None
        seen = {}

        def handler(session):
            seen["session"] = session
            return _real_artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler), agent="小明")
        assert engine.run() is True
        assert isinstance(seen["session"], SimpleNamespace)
        assert seen["session"].step_id == "s1"
        assert seen["session"].name == "第一步"
        assert seen["session"].agent == "小明"
        assert seen["session"].project_dir == engine.project_dir

    def test_factory_object_reaches_adapter(self, tmp_path):
        """传入 session_factory：adapter 收到工厂构造的对象（非 SimpleNamespace）。"""
        handler_seen = []

        def factory(step_def):
            return {"kind": "factory-built", "step_id": step_def["step_id"]}

        engine = CheckpointEngine("with-factory", str(tmp_path), session_factory=factory)

        def handler(session):
            handler_seen.append(session)
            return _real_artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler))
        assert engine.run() is True
        assert len(handler_seen) == 1
        assert handler_seen[0] == {"kind": "factory-built", "step_id": "s1"}
        assert not isinstance(handler_seen[0], SimpleNamespace)

    def test_factory_receives_step_def(self, tmp_path):
        """工厂收到的 step_def 与注册的 step 一致（step_id/name/agent/handler）。"""
        captured = {}

        def factory(step_def):
            captured.update(step_def)
            return object()

        engine = CheckpointEngine("stepdef", str(tmp_path), session_factory=factory)

        def handler(session):
            return _real_artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler), agent="小克")
        assert engine.run() is True
        assert captured["step_id"] == "s1"
        assert captured["name"] == "第一步"
        assert captured["agent"] == "小克"
        assert callable(captured["handler"])

    def test_factory_built_pipeline_session_full_run(self, tmp_path, monkeypatch):
        """集成：工厂构造真实 PipelineSession，run 全绿且 session 字段就绪。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        seen = {}

        def factory(step_def):
            session = PipelineSession(
                name=f"test-{step_def['step_id']}",
                spec_path=str(tmp_path / "docs" / "spec.md"),
            )
            session.project_dir = str(tmp_path)
            session.mock_mode = True
            return session

        engine = CheckpointEngine("integration", str(tmp_path), session_factory=factory)

        def handler(session):
            seen["session"] = session
            assert isinstance(session, PipelineSession)
            assert session.mock_mode is True
            assert session.project_dir == str(tmp_path)
            return _real_artifact(tmp_path, "out.json")

        engine.add_step("s1", "第一步", HandlerAdapter(handler))
        assert engine.run() is True
        assert engine._state.steps[0].status == StepStatus.PASSED
        assert seen["session"].spec_path.endswith("spec.md")

    def test_inject_and_resume_pass_through_factory(self, tmp_path):
        """注入/恢复模式同样走 session_factory（工厂被调用且 run 全绿）。"""
        factory_calls = []

        def factory(step_def):
            factory_calls.append(step_def["step_id"])
            return SimpleNamespace(step_id=step_def["step_id"])

        def handler(session):
            return _real_artifact(tmp_path, "out.json")

        engine = CheckpointEngine("modes", str(tmp_path), session_factory=factory)
        for sid in ("s1", "s2", "s3"):
            engine.add_step(sid, sid, HandlerAdapter(handler))
        assert engine.run(inject_at="s2") is True
        assert factory_calls == ["s2", "s3"]
        assert engine._state.steps[0].status == StepStatus.SKIPPED
        # 全部完成后再 resume → 无待跑步骤，工厂不再被调用
        assert engine.run(resume=True) is True
        assert factory_calls == ["s2", "s3"]


# ---------------------------------------------------------------------------
# agent_checkpoint：HandlerAdapter 包装 + 真实 PipelineSession 工厂（B1-2）
# ---------------------------------------------------------------------------


class TestAgentPipelineSessionFactory:
    def test_all_handlers_are_handler_adapters(self, tmp_path):
        """create_agent_pipeline：每个 step 的 handler 都是 HandlerAdapter 实例。"""
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline

        engine = create_agent_pipeline(str(tmp_path))
        step_defs = engine._step_defs
        # 行为一致性：工厂产物必须与注册表同步（单一事实源，不写死数字）
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        assert len(step_defs) == len(PIPELINE_STEPS)
        for s in step_defs:
            assert isinstance(s["handler"], HandlerAdapter), s["step_id"]
        # 全部为 session 风格（首参名 session/ctx/context），无 invalid
        assert all(a.style == "session" for a in (s["handler"] for s in step_defs))

    def test_factory_builds_real_pipeline_session(self, tmp_path, monkeypatch):
        """session_factory 构造真实 PipelineSession：spec/mock/project_dir 就绪。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline

        spec = str(tmp_path / "docs" / "spec.md")
        engine = create_agent_pipeline(str(tmp_path), spec_path=spec, mock_mode=True)
        assert engine.session_factory is not None

        session = engine.session_factory(
            {"step_id": "spec-check", "name": "检查", "agent": "小明"}
        )
        assert isinstance(session, PipelineSession)
        assert session.spec_path == str(Path(spec).resolve())
        assert session.mock_mode is True
        assert session.project_dir == str(tmp_path)
        assert session.llm_client is None
        assert session.step_id == "spec-check"
        assert session.step_name == "检查"
        assert session.agent == "小明"

    def test_factory_tolerates_missing_spec(self, tmp_path, monkeypatch):
        """spec 不存在时不抛错 —— session 只记录路径、不校验存在。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline

        missing = str(tmp_path / "no" / "such" / "spec.md")
        engine = create_agent_pipeline(str(tmp_path), spec_path=missing)
        session = engine.session_factory({"step_id": "x", "name": "y", "agent": ""})
        assert isinstance(session, PipelineSession)
        assert session.spec_path == str(Path(missing).resolve())
        assert not Path(session.spec_path).exists()

    def test_factory_default_spec_and_mock_control(self, tmp_path, monkeypatch):
        """默认 spec 取项目 docs/spec.md；mock_mode 由调用方控制（默认 False）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline

        engine = create_agent_pipeline(str(tmp_path))
        session = engine.session_factory({"step_id": "x", "name": "y", "agent": ""})
        assert session.spec_path == str(Path(str(tmp_path)) / "docs" / "spec.md")
        assert session.mock_mode is False

        engine_mock = create_agent_pipeline(str(tmp_path), mock_mode=True)
        s2 = engine_mock.session_factory({"step_id": "x", "name": "y", "agent": ""})
        assert s2.mock_mode is True

    def test_agent_pipeline_run_green_with_factory(self, tmp_path, monkeypatch):
        """agent_checkpoint engine：注入轻量 adapter 步骤后 run 全绿（走真实 session）。"""
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline

        engine = create_agent_pipeline(str(tmp_path), mock_mode=True)
        # 替换为轻量 handler，避免真实 handler 依赖项目文件（引擎机制验证）
        engine._step_defs = [{
            "step_id": "smoke", "name": "冒烟", "agent": "小明",
            "handler": HandlerAdapter(lambda session: _real_artifact(tmp_path, "smoke.json")),
        }]
        assert engine.run() is True
        rec = engine._state.steps[0]
        assert rec.status == StepStatus.PASSED
        assert rec.output_path == str(tmp_path / "smoke.json")
