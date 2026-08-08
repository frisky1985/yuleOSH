"""方案 B1-3 / B1-4 — agent_checkpoint 内联 mock 全链测试。

B1-3（内联 mock 全链）:
  - 经 orchestrator.run_pipeline(spec_path, mock=True) 跑完整 33 步 pipeline，
    零真实 LLM 调用（红线守护：run shim 的 chat_completion 被替换为爆炸函数，
    任何绕过 session.llm_client 的真实调用都会让 fixture 直接炸掉）。
  - 断言 status=completed / errors=[] / 33 步全部 completed / 关键产物落盘 /
    session.json 持久化 / token usage 走 mock client 记账。

B1-4（resume 续跑）:
  - CheckpointEngine：第 2 步注入失败 → run() 返回 False → 修好后
    run(resume=True) 从失败步续跑 → 3 步全过。
  - 边界：无 checkpoint 的 resume / 全部完成后的 resume / inject_at+resume /
    失败 checkpoint 状态落盘 / HandlerAdapter（session 风格）续跑。

依赖标注:
  - 除 TestAgentCheckpointEngineFullMock 外，全部用例不依赖 B1-1/B1-2，
    当前即可全绿。
  - TestAgentCheckpointEngineFullMock 依赖 B1-1（CheckpointEngine.session_factory
    构造真实 PipelineSession）+ B1-2（agent_checkpoint 用 HandlerAdapter 包装），
    另一 worker 未落地时自动 skip，落地后自动点亮。
"""

import inspect
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.engine.checkpoint import CheckpointEngine
from yuleosh.engine.handler_adapter import HandlerAdapter
from yuleosh.pipeline.orchestrator import _mock_llm_client, run_pipeline
from yuleosh.pipeline.step_handlers import PIPELINE_STEPS


def _real_artifact(tmp_path, name: str) -> str:
    """B2-2: 产物门禁要求 output_path 真实存在 —— 测试创建真实产物文件。"""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    return str(p)

# ---------------------------------------------------------------------------
# 共享常量 / fixture
# ---------------------------------------------------------------------------

# 最小合法 OpenSpec spec：REQ 带 SHALL + Reason，spec-check 门禁（真实子进程
# 校验）必须 error_count == 0，否则第一步就把 pipeline 阻断。
MINI_SPEC = """# Spec

## REQ-001: Minimal pipeline spec

- The system SHALL run the pipeline end to end
- The system SHALL produce a final report

### Reason
Test fixture spec for inline mock pipeline tests (B1-3).
"""

# 已知 artifact 值不是真实文件的两个 step（文档化，B1-3 断言里显式豁免）:
#   - qemu-run: should_skip 分支只返回 build_output_path，不写文件；
#   - review-critical-safety: mock 分支返回 dict（str(dict) 不是文件），
#     真实报告写在 critical-safety-report.json。
KNOWN_NONFILE_ARTIFACTS = {"qemu-run", "review-critical-safety"}

# 关键产物清单（session_dir 下必须存在）
KEY_ARTIFACTS = [
    "session.json",
    "spec-check.json",
    "startup-analysis.md",
    "prd.md",
    "prd-review.json",
    "architecture.md",
    "arch-review.json",
    "development-plan.md",
    "devplan-review.json",
    "test-plan.md",
    "self-test-report.md",
    "code-review.json",
    "misra-review.json",
    "coverage-review.json",
    "c-coverage-gate.json",
    "critical-safety-report.json",
    "fault-injection-report.md",
    "merge-gate-report.json",
    "final-report.md",
]

EXPECTED_STEP_COUNT = 33


@pytest.fixture(scope="module")
def mock_full_session(tmp_path_factory):
    """跑一次完整 33 步 mock pipeline，模块内共享（全链 E2E 只跑一遍）。

    红线守护：把 run shim 的 chat_completion 换成爆炸函数 —— mock 模式下
    任何真实 LLM 调用都会触发 AssertionError，fixture 记录调用次数供断言。
    """
    import yuleosh.pipeline.run as run_shim

    real_llm_calls: list = []

    def _no_real_llm(*args, **kwargs):  # pragma: no cover - 触发即测试失败
        real_llm_calls.append(args)
        raise AssertionError("mock 模式调用了真实 LLM（chat_completion）！")

    tmp = tmp_path_factory.mktemp("b1-inline-full")
    spec_path = tmp / "spec.md"
    spec_path.write_text(MINI_SPEC, encoding="utf-8")

    old_home = os.environ.get("OSH_HOME")
    os.environ["OSH_HOME"] = str(tmp)
    try:
        with mock.patch.object(run_shim, "chat_completion", _no_real_llm):
            session = run_pipeline(str(spec_path), name="b1-inline-full", mock=True)
    finally:
        if old_home is None:
            os.environ.pop("OSH_HOME", None)
        else:
            os.environ["OSH_HOME"] = old_home

    return session, real_llm_calls


# ---------------------------------------------------------------------------
# B1-3: 内联 mock 全链（orchestrator.run_pipeline(mock=True)）
# ---------------------------------------------------------------------------


class TestB13InlineMockFullChain:
    """mock 模式完整 33 步 pipeline：completed / 无错误 / 产物齐全。"""

    def test_mock_pipeline_completes_33_steps(self, mock_full_session):
        """全链跑通：status=completed、errors 为空、33 步全部 completed。"""
        s, _ = mock_full_session
        assert s.status == "completed"
        assert s.errors == []
        assert len(s.steps) == EXPECTED_STEP_COUNT
        assert all(step["status"] == "completed" for step in s.steps)

    def test_mock_pipeline_matches_pipeline_steps_registry(self, mock_full_session):
        """步骤与 PIPELINE_STEPS 注册表严格对齐（step_key 顺序一致）。"""
        s, _ = mock_full_session
        registry_keys = [key for key, _, _, _ in PIPELINE_STEPS]
        assert registry_keys == [step["name"] for step in s.steps]
        assert len(registry_keys) == EXPECTED_STEP_COUNT

    def test_mock_pipeline_zero_real_llm_calls(self, mock_full_session):
        """红线：mock 模式零真实 LLM 调用；token 全部走 mock client 记账。"""
        s, real_llm_calls = mock_full_session
        assert real_llm_calls == []
        # mock client 每次返回 usage（1000+500 tokens），LLM 步骤确实走注入的 client
        assert s.token_usage_total > 0
        assert len(s.token_usage_steps) >= 8

    def test_mock_pipeline_session_persisted_to_disk(self, mock_full_session):
        """session.json 落盘且内容完整（status/steps 与内存一致）。"""
        s, _ = mock_full_session
        sess_file = Path(s.session_dir) / "session.json"
        assert sess_file.exists()
        data = json.loads(sess_file.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert len(data["steps"]) == EXPECTED_STEP_COUNT
        assert data["errors"] == []
        assert data["spec_path"] == s.spec_path

    def test_mock_pipeline_key_artifacts_exist(self, mock_full_session):
        """关键产物全部落盘（spec-check / 分析 / 设计 / 测试 / 报告 / 门禁）。"""
        s, _ = mock_full_session
        missing = [
            name for name in KEY_ARTIFACTS
            if not (Path(s.session_dir) / name).exists()
        ]
        assert missing == [], f"缺少关键产物: {missing}"

    def test_mock_pipeline_artifact_registry_consistent(self, mock_full_session):
        """artifacts 注册表 33 项，除两个已知豁免外全部指向真实文件。"""
        s, _ = mock_full_session
        assert len(s.artifacts) == EXPECTED_STEP_COUNT
        broken = [
            key for key, path in s.artifacts.items()
            if key not in KNOWN_NONFILE_ARTIFACTS
            and not Path(str(path)).exists()
        ]
        assert broken == [], f"artifacts 指向不存在的文件: {broken}"

    def test_mock_pipeline_spec_check_clean(self, mock_full_session):
        """spec-check.json 是有效 JSON 且 error_count == 0（真实校验子进程）。"""
        s, _ = mock_full_session
        raw = (Path(s.session_dir) / "spec-check.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert data["error_count"] == 0
        assert data["requirements"] >= 1

    def test_mock_pipeline_final_report_written(self, mock_full_session):
        """final-report.md 由（mock）LLM 生成并包含报告标题。"""
        s, _ = mock_full_session
        report = (Path(s.session_dir) / "final-report.md").read_text(encoding="utf-8")
        assert "Final Report" in report


# ---------------------------------------------------------------------------
# B1-4: resume 续跑（CheckpointEngine — 简单 3 步场景）
# ---------------------------------------------------------------------------


class TestB14Resume:
    """注入失败 → resume → 从失败/未完成步骤续跑，最终全过。"""

    def _engine(self, tmp_path, name="b1-resume"):
        return CheckpointEngine(name, str(tmp_path))

    def test_resume_reruns_from_failed_step(self, tmp_path):
        """第 2 步注入失败 → run=False；修好后 resume → 3 步全过。"""
        engine = self._engine(tmp_path)
        calls: list[str] = []
        state = {"fail": True}

        def h1():
            calls.append("s1")
            return _real_artifact(tmp_path, "out1.json")

        def h2():
            calls.append("s2")
            if state["fail"]:
                raise RuntimeError("注入失败: step2 boom")
            return _real_artifact(tmp_path, "out2.json")

        def h3():
            calls.append("s3")
            return _real_artifact(tmp_path, "out3.json")

        engine.add_step("s1", "第一步", h1, agent="小明")
        engine.add_step("s2", "第二步", h2, agent="小克")
        engine.add_step("s3", "第三步", h3, agent="小马")

        assert engine.run() is False
        recs = engine.status()
        assert recs is not None
        recs = recs["steps"]
        assert [r["status"] for r in recs] == ["passed", "failed", "pending"]
        assert "boom" in (recs[1]["error"] or "")

        state["fail"] = False
        assert engine.run(resume=True) is True

        final = engine.status()
        assert final is not None
        assert final["status"] == "completed"
        assert [r["status"] for r in final["steps"]] == ["passed", "passed", "passed"]
        # s1 只跑一次；s2 失败一次 + 续跑一次；s3 只在续跑时执行
        assert calls == ["s1", "s2", "s2", "s3"]

    def test_resume_passed_steps_not_rerun(self, tmp_path):
        """已完成步骤不重跑：失败发生在第 2 步，resume 只续跑 2/3。"""
        engine = self._engine(tmp_path)
        calls: list[str] = []
        state = {"fail": True}

        def h1():
            calls.append("s1")
            return _real_artifact(tmp_path, "o1.json")

        def h2():
            calls.append("s2")
            if state["fail"]:
                raise RuntimeError("boom")
            return _real_artifact(tmp_path, "o2.json")

        def h3():
            calls.append("s3")
            return _real_artifact(tmp_path, "o3.json")

        engine.add_step("s1", "一", h1)
        engine.add_step("s2", "二", h2)
        engine.add_step("s3", "三", h3)

        assert engine.run() is False
        state["fail"] = False
        assert engine.run(resume=True) is True
        assert calls == ["s1", "s2", "s2", "s3"]

    def test_resume_all_completed_returns_true_no_rerun(self, tmp_path):
        """全部完成后 resume → True 且不重跑任何步骤。"""
        engine = self._engine(tmp_path)
        calls: list[int] = []

        def h():
            calls.append(1)
            return _real_artifact(tmp_path, "o.json")

        engine.add_step("s1", "一", h)
        engine.add_step("s2", "二", h)
        engine.add_step("s3", "三", h)

        assert engine.run() is True
        assert engine.run(resume=True) is True
        assert calls == [1, 1, 1]

    def test_resume_without_checkpoint_runs_full(self, tmp_path):
        """无历史 checkpoint 的 resume → 等价全量执行（打印警告路径）。"""
        engine = self._engine(tmp_path)
        calls: list[str] = []

        def h():
            calls.append("x")
            return _real_artifact(tmp_path, "o.json")

        engine.add_step("s1", "一", h)
        engine.add_step("s2", "二", h)
        engine.add_step("s3", "三", h)

        assert engine.run(resume=True) is True
        state = engine.status()
        assert state is not None
        assert state["status"] == "completed"
        assert [r["status"] for r in state["steps"]] == ["passed", "passed", "passed"]
        assert calls == ["x", "x", "x"]

    def test_inject_at_then_resume_no_rerun(self, tmp_path):
        """注入模式跑完后 resume → 无待跑步骤，不重跑。"""
        engine = self._engine(tmp_path)
        calls: list[str] = []

        def handler():
            calls.append("x")
            return _real_artifact(tmp_path, "o.json")

        engine.add_step("s1", "一", handler)
        engine.add_step("s2", "二", handler)
        engine.add_step("s3", "三", handler)

        assert engine.run(inject_at="s2") is True
        assert calls == ["x", "x"]
        recs = engine.status()
        assert recs is not None
        recs = recs["steps"]
        assert [r["status"] for r in recs] == ["skipped", "passed", "passed"]

        assert engine.run(resume=True) is True
        assert calls == ["x", "x"]  # 注入点之前的 skipped 不视为待跑

    def test_resume_with_session_style_adapter_handlers(self, tmp_path):
        """agent_checkpoint 真实路径：HandlerAdapter 包装的 session 风格 handler
        注入失败 → resume → 全过（SimpleNamespace session 透传 step_id）。"""
        engine = self._engine(tmp_path, name="b1-resume-adapter")
        calls: list[str] = []
        state = {"fail": True}

        def handler(session):
            calls.append(session.step_id)
            if session.step_id == "s2" and state["fail"]:
                raise RuntimeError("adapter boom")
            return _real_artifact(tmp_path, "o.json")

        engine.add_step("s1", "一", HandlerAdapter(handler))
        engine.add_step("s2", "二", HandlerAdapter(handler))
        engine.add_step("s3", "三", HandlerAdapter(handler))

        assert engine.run() is False
        state["fail"] = False
        assert engine.run(resume=True) is True

        final = engine.status()
        assert final is not None
        assert final["status"] == "completed"
        assert [r["status"] for r in final["steps"]] == ["passed", "passed", "passed"]
        assert calls == ["s1", "s2", "s2", "s3"]

    def test_failed_run_persists_checkpoint_state(self, tmp_path):
        """失败后 checkpoint 状态文件落盘：status=failed + 失败步 error 可读。"""
        engine = self._engine(tmp_path, name="b1-resume-state")
        state = {"fail": True}

        def h1():
            return _real_artifact(tmp_path, "o1.json")

        def h2():
            if state["fail"]:
                raise RuntimeError("persist-me")
            return _real_artifact(tmp_path, "o2.json")

        def h3():
            return _real_artifact(tmp_path, "o3.json")

        engine.add_step("s1", "一", h1)
        engine.add_step("s2", "二", h2)
        engine.add_step("s3", "三", h3)

        assert engine.run() is False

        state_file = Path(tmp_path) / ".yuleosh" / "checkpoint-state.json"
        assert state_file.exists()
        raw = json.loads(state_file.read_text(encoding="utf-8"))
        assert raw["status"] == "failed"
        assert raw["steps"][1]["status"] == "failed"
        assert "persist-me" in raw["steps"][1]["error"]


# ---------------------------------------------------------------------------
# B1-2 依赖：agent_checkpoint 引擎驱动真实 33 步 mock pipeline（最终形态）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    "session_factory"
    not in inspect.signature(CheckpointEngine.__init__).parameters,
    reason="依赖 B1-1/B1-2: CheckpointEngine.session_factory + agent_checkpoint ",
)
class TestAgentCheckpointEngineFullMock:
    """B1-2 最终形态：CheckpointEngine + 真实 PipelineSession 驱动 33 步 mock 全链。"""

    def test_engine_drives_33_steps_mock(self, tmp_path):
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline
        from yuleosh.pipeline.session import PipelineSession

        spec_path = tmp_path / "spec.md"
        spec_path.write_text(MINI_SPEC, encoding="utf-8")

        engine = create_agent_pipeline(str(tmp_path), str(spec_path))
        assert len(engine.get_step_ids()) == EXPECTED_STEP_COUNT

        # B1-2 落地后 create_agent_pipeline 内部已用 HandlerAdapter 包装；
        # 若只落地 B1-1（session_factory），这里补包装保证测试可跑。
        for step in engine._step_defs:
            if not isinstance(step["handler"], HandlerAdapter):
                step["handler"] = HandlerAdapter(step["handler"])

        # 适配 B1-1 的 session_factory 签名（step_id 或 step_def dict 均兼容）
        # 注意：跨步骤共享同一个 session 实例，保证 session.artifacts 累积
        # （真实 handler 依赖前序产物；B1-1 增强后 engine 自动 set_artifact）。
        shared = PipelineSession("agent-inline-shared", str(spec_path))
        shared.mock_mode = True
        shared.project_dir = str(tmp_path)
        shared.llm_client = _mock_llm_client()

        def _session_factory(*args, **kwargs):
            step_id = kwargs.get("step_id", "step")
            if args:
                first = args[0]
                if isinstance(first, dict):
                    step_id = first.get("step_id", step_id)
                else:
                    step_id = str(first)
            shared.pipeline_knowledge_step_key = step_id
            return shared

        engine.session_factory = _session_factory

        assert engine.run() is True
        state = engine.status()
        assert state is not None
        assert state["status"] == "completed"
        assert len(state["steps"]) == EXPECTED_STEP_COUNT
        assert all(s["status"] == "passed" for s in state["steps"])

    def test_engine_mock_33_steps_resume_after_failure(self, tmp_path):
        """B1-2 最终形态 + B1-4：33 步 mock 全链注入失败 → resume → 全过。"""
        from yuleosh.engine.agent_checkpoint import create_agent_pipeline
        from yuleosh.pipeline.session import PipelineSession

        spec_path = tmp_path / "spec.md"
        spec_path.write_text(MINI_SPEC, encoding="utf-8")

        engine = create_agent_pipeline(str(tmp_path), str(spec_path))
        for step in engine._step_defs:
            if not isinstance(step["handler"], HandlerAdapter):
                step["handler"] = HandlerAdapter(step["handler"])

        # 在 prd 步注入一次性失败
        injected = {"step_id": "prd", "fail": True}

        # 跨步骤共享同一 session（artifacts 累积），与 orchestrator 语义一致。
        shared = PipelineSession("agent-inline-shared", str(spec_path))
        shared.mock_mode = True
        shared.project_dir = str(tmp_path)
        shared.llm_client = _mock_llm_client()

        def _session_factory(*args, **kwargs):
            step_id = kwargs.get("step_id", "step")
            if args:
                first = args[0]
                step_id = (
                    first.get("step_id", step_id) if isinstance(first, dict)
                    else str(first)
                )
            shared.pipeline_knowledge_step_key = step_id
            return shared

        engine.session_factory = _session_factory

        # 在 prd 步包一层抛错 handler（模拟真实步骤失败）；其余步骤原样透传
        for step in engine._step_defs:
            inner = step["handler"]
            adapter = inner if isinstance(inner, HandlerAdapter) else HandlerAdapter(inner)
            if step["step_id"] != injected["step_id"]:
                step["handler"] = adapter
                continue

            def make_boom(adapter_):
                def wrapped(session):
                    if injected["fail"]:
                        raise RuntimeError("injected prd failure")
                    return adapter_(session)

                return HandlerAdapter(wrapped)

            step["handler"] = make_boom(adapter)

        assert engine.run() is False
        state = engine.status()
        assert state is not None
        assert state["status"] == "failed"
        failed_idx = next(
            i for i, s in enumerate(state["steps"]) if s["status"] == "failed"
        )
        assert state["steps"][failed_idx]["step_id"] == "prd"

        injected["fail"] = False
        assert engine.run(resume=True) is True
        final = engine.status()
        assert final is not None
        assert final["status"] == "completed"
        assert all(s["status"] == "passed" for s in final["steps"])
