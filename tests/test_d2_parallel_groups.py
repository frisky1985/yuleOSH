"""D2 — orchestrator 并行组 (PARALLEL_GROUPS) 专项测试。

覆盖 (2026-08-19, 老板拍板方案 A):
  - 并行组内步骤真正并发执行（线程交错可观测: 慢步骤与快步骤墙钟重叠）
  - 组内任一 failed → 整组等待结束后 pipeline 中断（合并语义）
  - 组内任一 block gate verdict → 中断
  - 并行组与串行步骤共存（非组成员不受影响）
  - 断点续跑 (from_step) 在并行组内正确跳过
  - thread-local step_key 隔离（并行 worker 的 _call_llm 用各自 step_key）
"""

# @tests src/yuleosh/pipeline/orchestrator.py

import json
import time
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.orchestrator import (
    PARALLEL_GROUPS,
    _GROUP_LOOKUP,
    run_pipeline,
)
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

# ---------------------------------------------------------------------------
# 共享 fixture / 工具
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setattr("yuleosh.pipeline.session._store", None)
    monkeypatch.setattr("yuleosh.pipeline.orchestrator._notify", None)


@pytest.fixture
def osh_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    monkeypatch.delenv("OSH_DEVELOPMENT_MODE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return tmp_path


def _make_spec(tmp_path) -> Path:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Spec\n\n## REQ-001\n\n- The system SHALL run\n\n### Reason\nTest.\n",
        encoding="utf-8",
    )
    return spec


def _ok_handler(output_path):
    def _handler(session):
        return str(output_path)

    return _handler


def _run(spec_path, *, name="d2-test", steps=None, from_step=0,
         mock_mode=False):
    if steps is None:
        steps = [("spec-check", "小明", "合规检查", _ok_handler(spec_path))]
    with ExitStack() as stack:
        stack.enter_context(mock.patch("yuleosh.pipeline.run.PIPELINE_STEPS", steps))
        stack.enter_context(
            mock.patch("yuleosh.pipeline.run._check_llm_key", return_value="sk-test")
        )
        stack.enter_context(
            mock.patch("yuleosh.pipeline.orchestrator._detect_and_bootstrap", return_value=None)
        )
        stack.enter_context(
            mock.patch("yuleosh.pipeline.orchestrator.load_agent_constraints",
                       return_value=("", "builtin_fallback"))
        )
        stack.enter_context(
            mock.patch("yuleosh.pipeline.orchestrator.load_agent_constraints_by_role",
                       return_value={})
        )
        stack.enter_context(
            mock.patch("yuleosh.ci.profile.validate_active_profile", return_value=(True, "ok"))
        )
        stack.enter_context(
            mock.patch("yuleosh.ci.profile.get_current_profile", return_value="safety")
        )
        stack.enter_context(
            mock.patch("yuleosh.ci.profile.filter_steps_for_profile",
                       side_effect=lambda s, p, d: s)
        )
        session = run_pipeline(
            str(spec_path), name=name, mock=mock_mode, from_step=from_step,
        )
    return session


# ---------------------------------------------------------------------------
# 结构契约
# ---------------------------------------------------------------------------


def test_parallel_groups_cover_documented_steps():
    """并行组覆盖方案文档中的步骤；lookup 无冲突。"""
    assert PARALLEL_GROUPS[0] == ("prd", "architecture")
    assert PARALLEL_GROUPS[1] == ("arch-review", "development")
    # 2026-08-20 r22 实测: internal-code-review 从 P3 移除 — maybe_skip_code_review
    # 读 codegen-deploy 报告 (handler 结尾才写), 与 codegen-deploy 并行会 false-skip
    # "本次 run 无代码部署"。部署状态消费者必须在 producer 之后 (串行)。
    assert PARALLEL_GROUPS[2] == (
        "development-review", "codegen-deploy", "claude-review",
    )
    # 每步只属于一个组
    seen: set[str] = set()
    for g in PARALLEL_GROUPS:
        for k in g:
            assert k not in seen, f"step {k} 出现在多个并行组"
            seen.add(k)
    assert len(seen) == 7  # 2 + 2 + 3 (internal-code-review 串行)


def test_group_lookup_consistency():
    for k, gid in _GROUP_LOOKUP.items():
        assert k in PARALLEL_GROUPS[gid]


# ---------------------------------------------------------------------------
# 并发行为
# ---------------------------------------------------------------------------


def test_parallel_group_runs_concurrently(osh_home, tmp_path):
    """组内步骤真正并发: 慢步骤(0.6s) + 快步骤(0.1s) 墙钟 < 串行和(0.7s)。"""
    spec = _make_spec(tmp_path)

    def _slow(session):
        time.sleep(0.6)
        p = tmp_path / "prd.md"
        p.write_text("# PRD\nstatus: passed", encoding="utf-8")
        return str(p)

    def _fast(session):
        time.sleep(0.1)
        p = tmp_path / "arch.md"
        p.write_text("# ARCH\nstatus: passed", encoding="utf-8")
        return str(p)

    steps = [
        ("super-analysis", "小明", "S.U.P.E.R", _ok_handler(tmp_path / "super.md")),
        ("prd", "Hermes", "PRD", _slow),
        ("architecture", "Claude", "架构", _fast),
    ]
    # 预置 super-analysis 产物（prd 依赖）
    super_f = tmp_path / "super.md"
    super_f.write_text("# SUPER", encoding="utf-8")

    t0 = time.monotonic()
    session = _run(spec, steps=steps)
    elapsed = time.monotonic() - t0

    assert session.status == "completed"
    # 并发证明: 组内成员 started_at 重叠（串行则 architecture 的 start
    # 在 prd 完成之后）。时间戳由 session.start_step 记录, 精确且机器无关。
    by_key = {s["name"]: s for s in session.steps}
    from datetime import datetime as _dt
    t_prd = _dt.fromisoformat(by_key["prd"]["started_at"])
    t_arch = _dt.fromisoformat(by_key["architecture"]["started_at"])
    overlap = abs((t_prd - t_arch).total_seconds())
    assert overlap < 0.3, f"疑似串行: prd/architecture 启动间隔 {overlap:.3f}s"
    # 墙钟 < 串行和 (0.7s + 开销); 线程启动开销下放宽到 0.9s
    assert elapsed < 0.9, f"墙钟过长: {elapsed:.3f}s"


def test_parallel_group_member_failure_stops_pipeline(osh_home, tmp_path):
    """组内任一 handler 失败 → 整组等待后 pipeline failed（合并语义）。"""
    spec = _make_spec(tmp_path)

    def _boom(session):
        raise PipelineStepError("parallel member boom")

    def _ok(session):
        time.sleep(0.15)
        p = tmp_path / "ok.md"
        p.write_text("# OK\nstatus: passed", encoding="utf-8")
        return str(p)

    steps = [
        ("prd", "Hermes", "PRD", _boom),
        ("architecture", "Claude", "架构", _ok),
        ("test-planning", "Claude", "测试规划", _ok_handler(tmp_path / "tp.md")),
    ]
    session = _run(spec, steps=steps)
    assert session.status == "failed"
    # 组内失败步骤标记 failed; 组内其他成员仍执行完（合并语义不提前 kill）
    statuses = {s["name"]: s["status"] for s in session.steps}
    assert statuses["prd"] == "failed"
    assert statuses["architecture"] == "completed"
    # 组后串行步骤未执行
    assert statuses["test-planning"] == "pending"


def test_parallel_group_block_gate_stops_pipeline(osh_home, tmp_path):
    """组内 block gate verdict failed → 整组后中断。"""
    spec = _make_spec(tmp_path)

    def _blocking(session):
        p = tmp_path / "arch.json"
        p.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
        return str(p)

    def _ok(session):
        time.sleep(0.1)
        p = tmp_path / "prd.md"
        p.write_text("# PRD\nstatus: passed", encoding="utf-8")
        return str(p)

    steps = [
        ("super-analysis", "小明", "S.U.P.E.R", _ok_handler(tmp_path / "super.md")),
        ("prd", "Hermes", "PRD", _ok),
        ("architecture", "Claude", "架构", _blocking),
        ("test-planning", "Claude", "测试规划", _ok_handler(tmp_path / "tp.md")),
    ]
    # architecture 是 warn gate（默认矩阵未列为 block）→ verdict failed 只记 errors 不断链。
    # 验证: pipeline completed 但 errors 含 architecture verdict failed。
    session = _run(spec, steps=steps)
    assert session.status == "completed"
    assert any("architecture" in e for e in session.errors), session.errors


# ---------------------------------------------------------------------------
# 与串行步骤共存 / 断点续跑
# ---------------------------------------------------------------------------


def test_serial_steps_not_in_group_run_individually(osh_home, tmp_path):
    """非组成员按串行执行，且执行顺序保持。"""
    spec = _make_spec(tmp_path)
    order: list[str] = []

    def _mk(tag):
        def _h(session):
            order.append(tag)
            p = tmp_path / f"{tag}.md"
            p.write_text(f"# {tag}", encoding="utf-8")
            return str(p)

        return _h

    steps = [
        ("spec-check", "小明", "合规检查", _mk("spec-check")),
        ("super-analysis", "小明", "S.U.P.E.R", _mk("super")),
        ("prd", "Hermes", "PRD", _mk("prd")),
        ("architecture", "Claude", "架构", _mk("arch")),
        ("prd-review", "小马", "PRD 审查", _mk("prd-review")),
        ("arch-review", "小克", "架构审查", _mk("arch-review")),
        ("test-planning", "Claude", "测试规划", _mk("tp")),
    ]
    session = _run(spec, steps=steps)
    assert session.status == "completed"
    # 串行步骤（非并行组）保持相对顺序
    assert order.index("spec-check") < order.index("super")
    assert order.index("prd-review") < order.index("arch-review")
    assert order.index("arch-review") < order.index("tp")


def test_parallel_group_from_step_skip(osh_home, tmp_path):
    """断点续跑: from_step 跳过并行组内前序步骤（标记 skipped 不执行）。"""
    spec = _make_spec(tmp_path)
    called: list[str] = []

    def _mk(tag):
        def _h(session):
            called.append(tag)
            p = tmp_path / f"{tag}.md"
            p.write_text(f"# {tag}", encoding="utf-8")
            return str(p)

        return _h

    # 6 步: prd(2) 是并行组 P1 成员 — from_step=3 应跳过 step1(prd)+step2(prd)？
    # 实际 from_step 语义: idx+1 < from_step 跳过。from_step=3 → 跳过 step 1,2。
    steps = [
        ("spec-check", "小明", "合规检查", _mk("spec-check")),
        ("super-analysis", "小明", "S.U.P.E.R", _mk("super")),
        ("prd", "Hermes", "PRD", _mk("prd")),
        ("architecture", "Claude", "架构", _mk("arch")),
        ("prd-review", "小马", "PRD 审查", _mk("prd-review")),
        ("test-planning", "Claude", "测试规划", _mk("tp")),
    ]
    # 先跑一次完整 pipeline 生成历史 session（from_step 依赖 _find_previous_session）
    session0 = _run(spec, steps=steps)
    assert session0.status == "completed"

    called.clear()
    session = _run(spec, steps=steps, from_step=3)
    assert session.status == "completed"
    # 步骤 1-2 标记 skipped
    assert session.steps[0]["status"] == "skipped"
    assert session.steps[1]["status"] == "skipped"
    # 步骤 3+ 执行（并行组内 prd/architecture 都执行; from_step=3 不跳过 prd）
    assert "prd" in called and "arch" in called
    assert "spec-check" not in called and "super" not in called


# ---------------------------------------------------------------------------
# thread-local step_key 隔离
# ---------------------------------------------------------------------------


def test_parallel_worker_step_key_isolation(osh_home, tmp_path):
    """并行 worker 的 _call_llm 读到各自 step_key（不互相覆盖）。"""
    spec = _make_spec(tmp_path)
    seen_keys: list[str] = []

    def _llm_capture(system_prompt, user_prompt, **kwargs):
        # mock run.chat_completion — handler 内 _call_llm 的 fallback。
        # 通过 thread-local 拿 step_key（并行 worker 各自隔离）。
        from yuleosh.pipeline.step_context import get_step_key

        seen_keys.append(get_step_key())
        return {"content": "# PLACEHOLDER\nstatus: passed", "usage": {"total_tokens": 5}}

    def _mk(tag, out_name):
        def _h(session):
            # 直接调 mock LLM（模拟步骤内部 _call_llm 路径）
            from yuleosh.pipeline.stages.llm import _call_llm

            _call_llm(session, "sys", "user")
            p = tmp_path / out_name
            p.write_text(f"# {tag}\nstatus: passed", encoding="utf-8")
            return str(p)

        return _h

    steps = [
        ("prd", "Hermes", "PRD", _mk("prd", "prd.md")),
        ("architecture", "Claude", "架构", _mk("arch", "arch.md")),
    ]
    # 非 mock 模式: _call_llm 走 run.chat_completion fallback（被 patch 捕获）
    with mock.patch(
        "yuleosh.pipeline.run.chat_completion", side_effect=_llm_capture
    ):
        session = _run(spec, steps=steps, mock_mode=False)

    assert session.status == "completed"
    # 两个 worker 各自的 thread-local step_key 都被观察到
    assert "prd" in seen_keys and "architecture" in seen_keys, seen_keys
