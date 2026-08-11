"""O3 — yuleOSH orchestrator.run_pipeline (L271-480) 全覆盖分支测试。

覆盖目标（src/yuleosh/pipeline/orchestrator.py，零 src/ 改动）:
  - run_pipeline: mock / 非 mock 模式、llm_client 注入、LLM key 缺失 sys.exit、
    project 自动检测（autosar / 非 autosar）、agent constraints 加载与按角色合并、
    profile 校验四分支（valid / invalid / ImportError / 运行时异常）、
    filter 后空步骤 sys.exit、默认 name 生成、OSH_DEVELOPMENT_MODE、
    步骤循环（final-report 特判、成功路径、PipelineStepError/RuntimeError 阻断、
    template fallback 成功 / abort 转 PipelineStepError）、token usage 汇总、
    _notify 调用与异常、orchestrator crash sys.exit。
  - 同组辅助函数（run_pipeline 直接调用）:
      _run_step_with_fallback（成功 / PipelineStepError 重抛 / fallback 写盘 / abort）
      _propagate_step_verdict（空路径 / 非 json / 非 dict / 无 status / failed /
                              重复 failed / retry / warning / 越界 idx）

红线遵守: 零 src/ 改动、零网络 / 子进程 / 时间依赖 —— LLM 与外部模块全部
mock.patch 注入；Store / notify 副作用在 autouse fixture 中屏蔽。
"""

import builtins
import json
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.llm.fallback import FallbackResult
from yuleosh.pipeline.orchestrator import (
    _mock_llm_client,
    _propagate_step_verdict,
    _run_step_with_fallback,
    run_pipeline,
)
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

# ---------------------------------------------------------------------------
# 共享 fixture / 工具
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """屏蔽真实 Store(SQLite) 写入与真实 notify 副作用，保证测试隔离。"""
    monkeypatch.setattr("yuleosh.pipeline.session._store", None)
    monkeypatch.setattr("yuleosh.pipeline.orchestrator._notify", None)


@pytest.fixture
def osh_home(tmp_path, monkeypatch):
    """隔离 OSH_HOME；清掉可能影响 _check_llm_key 的 key 环境变量。"""
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
    """步骤 handler：返回一个已存在的产物路径。"""

    def _handler(session):
        return str(output_path)

    return _handler


def _identity_filter(steps, profile, project_dir=""):
    """默认 profile 过滤：原样返回（等价 safety 全量 profile）。"""
    return steps


def _run(
    spec_path,
    *,
    name="o3-test",
    steps=None,
    mock_mode=False,
    llm_client=None,
    profile=None,
    detect=None,
    constraints=("constraints", "builtin_fallback"),
    by_role=None,
    valid_profile=(True, "ok"),
    get_profile="safety",
    filter_result=None,
    check_key_value="sk-test",
    no_profile_module=False,
):
    """以全 mock 环境驱动 run_pipeline（LLM/检测/profile/约束全部注入假实现）。"""
    if steps is None:
        steps = [("spec-check", "小明", "合规检查", _ok_handler(spec_path))]
    if by_role is None:
        by_role = {}

    with ExitStack() as stack:
        stack.enter_context(mock.patch("yuleosh.pipeline.run.PIPELINE_STEPS", steps))
        stack.enter_context(
            mock.patch("yuleosh.pipeline.run._check_llm_key", return_value=check_key_value)
        )
        stack.enter_context(
            mock.patch("yuleosh.pipeline.orchestrator._detect_and_bootstrap", return_value=detect)
        )
        stack.enter_context(
            mock.patch("yuleosh.pipeline.orchestrator.load_agent_constraints", return_value=constraints)
        )
        stack.enter_context(
            mock.patch(
                "yuleosh.pipeline.orchestrator.load_agent_constraints_by_role",
                return_value=by_role,
            )
        )
        if not no_profile_module:
            if callable(valid_profile):
                stack.enter_context(
                    mock.patch(
                        "yuleosh.ci.profile.validate_active_profile",
                        side_effect=valid_profile,
                    )
                )
            else:
                stack.enter_context(
                    mock.patch(
                        "yuleosh.ci.profile.validate_active_profile",
                        return_value=valid_profile,
                    )
                )
            stack.enter_context(
                mock.patch("yuleosh.ci.profile.get_current_profile", return_value=get_profile)
            )
            if filter_result is not None:
                stack.enter_context(
                    mock.patch(
                        "yuleosh.ci.profile.filter_steps_for_profile",
                        return_value=filter_result,
                    )
                )
            else:
                stack.enter_context(
                    mock.patch(
                        "yuleosh.ci.profile.filter_steps_for_profile",
                        side_effect=_identity_filter,
                    )
                )
        return run_pipeline(
            str(spec_path),
            name=name,
            mock=mock_mode,
            llm_client=llm_client,
            profile=profile,
        )


# ---------------------------------------------------------------------------
# run_pipeline: mock / llm_client / key 检查
# ---------------------------------------------------------------------------


def test_mock_mode_generates_mock_client(osh_home, tmp_path, capsys):
    """mock=True 且无 llm_client → 内部生成 mock client（L291-294）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("ok", encoding="utf-8")
    session = _run(
        spec,
        steps=[("spec-check", "小明", "合规检查", _ok_handler(out))],
        mock_mode=True,
    )
    assert session.mock_mode is True
    assert session.llm_client is not None
    assert "MOCK mode" in capsys.readouterr().out
    assert session.steps[0]["status"] == "completed"


def test_mock_mode_with_injected_client(osh_home, tmp_path):
    """mock=True 且注入 llm_client → 不生成 mock client（L292 False 分支）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("ok", encoding="utf-8")
    fake = mock.Mock(return_value={"content": "x"})
    session = _run(
        spec,
        steps=[("spec-check", "小明", "合规检查", _ok_handler(out))],
        mock_mode=True,
        llm_client=fake,
    )
    assert session.llm_client is fake


def test_non_mock_missing_key_exits(osh_home, tmp_path):
    """非 mock、无 client、key 缺失 → sys.exit(1)（L295-299）。"""
    spec = _make_spec(tmp_path)
    with pytest.raises(SystemExit) as ei:
        _run(spec, check_key_value=None)
    assert ei.value.code == 1


def test_non_mock_injected_client_skips_key_check(osh_home, tmp_path):
    """非 mock 但注入 client → 跳过 key 检查（L295 elif False 分支）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("ok", encoding="utf-8")
    fake = mock.Mock(return_value={"content": "x"})
    session = _run(
        spec,
        steps=[("spec-check", "小明", "合规检查", _ok_handler(out))],
        llm_client=fake,
    )
    assert session.llm_client is fake
    # E2E 修复 (2026-08-11): 单步无 final-report 正常跑完 → completed
    assert session.status == "completed"


# ---------------------------------------------------------------------------
# run_pipeline: project 检测 / agent constraints
# ---------------------------------------------------------------------------


def test_detected_project_autosar(osh_home, tmp_path, capsys):
    """project_info 为 autosar → 打印模板加载信息（L303-306）。"""
    spec = _make_spec(tmp_path)
    _run(
        spec,
        detect={"name": "demo", "type": "autosar", "config_source": "cfg-path"},
    )
    out = capsys.readouterr().out
    assert "Detected project: demo (type: autosar)" in out
    assert "AUTOSAR template auto-loaded" in out


def test_detected_project_non_autosar(osh_home, tmp_path, capsys):
    """project_info 非 autosar → L305 条件为 False。"""
    spec = _make_spec(tmp_path)
    _run(spec, detect={"name": "demo", "type": "generic"})
    out = capsys.readouterr().out
    assert "Detected project: demo" in out
    assert "AUTOSAR template auto-loaded" not in out


def test_constraints_by_role_combined(osh_home, tmp_path):
    """按角色约束存在 → 拼接共享基线 + 各角色约束（L316-320）。"""
    spec = _make_spec(tmp_path)
    session = _run(spec, by_role={"pm": "PM rules"})
    assert session.agent_constraints_by_role == {"pm": "PM rules"}
    assert "PM rules" in session.agent_constraints
    assert session.agent_shared_baseline


def test_empty_agent_constraints_skips_label(osh_home, tmp_path, capsys):
    """agent_constraints 为空串 → L321 条件为 False，不打印来源标签。"""
    spec = _make_spec(tmp_path)
    session = _run(spec, constraints=("", "agents_dir"))
    assert session.agent_constraints == ""
    assert "Agent constraints" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("agents_dir", ".yuleosh/agents/"),
        ("ci_config", "ci-config.yaml default"),
        ("builtin_fallback", "built-in default"),
        ("unknown_source", "Agent constraints loaded"),
    ],
)
def test_constraints_source_label(osh_home, tmp_path, capsys, source, label):
    """constraints 来源标签映射 + 未知来源兜底（L322-328）。"""
    spec = _make_spec(tmp_path)
    _run(spec, constraints=("constraints", source))
    assert label in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_pipeline: profile 校验四分支 + 过滤
# ---------------------------------------------------------------------------


def test_profile_invalid_falls_back_to_safety(osh_home, tmp_path):
    """profile 校验失败 → 回退 safety（L336-339）。"""
    spec = _make_spec(tmp_path)
    session = _run(spec, valid_profile=(False, "profile not found"))
    assert session.profile == "safety"


def test_profile_valid_uses_override(osh_home, tmp_path, capsys):
    """profile 校验通过 + 显式 profile 覆盖 → 打印活动 profile（L340-341）。"""
    spec = _make_spec(tmp_path)
    session = _run(spec, profile="ci", valid_profile=(True, "ci profile valid"))
    assert session.profile == "ci"
    assert "Active profile: 'ci'" in capsys.readouterr().out


def test_profile_filtered_to_empty_exits(osh_home, tmp_path):
    """过滤后无剩余步骤 → sys.exit(1)（L343-345）。"""
    spec = _make_spec(tmp_path)
    with pytest.raises(SystemExit) as ei:
        _run(spec, filter_result=[])
    assert ei.value.code == 1


def test_profile_import_error_uses_safety(osh_home, tmp_path):
    """yuleosh.ci.profile 导入失败 → except ImportError（L346-348）。"""
    spec = _make_spec(tmp_path)
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "yuleosh.ci.profile":
            raise ImportError("no profile module")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=_fake_import):
        session = _run(spec, no_profile_module=True)
    assert session.profile == "safety"


def test_profile_generic_exception_uses_safety(osh_home, tmp_path):
    """profile 校验抛运行时异常 → except Exception（L349-351）。"""
    spec = _make_spec(tmp_path)

    def _boom(project_dir):
        raise RuntimeError("profile module exploded")

    session = _run(spec, valid_profile=_boom)
    assert session.profile == "safety"


# ---------------------------------------------------------------------------
# run_pipeline: 会话创建 / 步骤循环
# ---------------------------------------------------------------------------


def test_default_name_generated(osh_home, tmp_path):
    """name=None → 自动生成 run-<时间戳> 名称（L354-355）。"""
    spec = _make_spec(tmp_path)
    session = _run(spec, name=None)
    assert session.name.startswith("run-")


def test_env_dev_mode(osh_home, tmp_path, monkeypatch, capsys):
    """OSH_DEVELOPMENT_MODE 设置 → session.development_mode（L370-373）。"""
    monkeypatch.setenv("OSH_DEVELOPMENT_MODE", "generate-code")
    spec = _make_spec(tmp_path)
    session = _run(spec)
    assert session.development_mode == "generate-code"
    assert "development_mode from env: generate-code" in capsys.readouterr().out


def test_pipeline_success_with_final_report(osh_home, tmp_path):
    """final-report 步骤 → status=completed、两次 _save 落盘（L397-427）。"""
    spec = _make_spec(tmp_path)
    out1 = tmp_path / "a.md"
    out1.write_text("x", encoding="utf-8")
    out2 = tmp_path / "final.md"
    out2.write_text("y", encoding="utf-8")
    steps = [
        ("spec-check", "小明", "合规检查", _ok_handler(out1)),
        ("final-report", "小明", "最终报告", _ok_handler(out2)),
    ]
    session = _run(spec, steps=steps)
    assert session.status == "completed"
    assert len(session.steps) == 2
    assert all(s["status"] == "completed" for s in session.steps)
    # Phase 9: session 目录按 run_id 命名（不再按 name）
    assert (tmp_path / ".osh" / "sessions" / session.run_id / "session.json").exists()


def test_pipeline_without_final_report_status_completed(osh_home, tmp_path, capsys):
    """无 final-report（如 minimal 白名单档）→ 循环正常跑完即 completed。

    修复前 (2026-08-11): status 只在 final-report 步骤前置位，白名单档
    永远停在 created → CLI exit(1) 误判失败。修复后: 未失败且未跑
    final-report 时，循环结束统一置 completed，走 🎉 打印。
    """
    spec = _make_spec(tmp_path)
    out = tmp_path / "a.md"
    out.write_text("x", encoding="utf-8")
    session = _run(spec, steps=[("spec-check", "小明", "合规检查", _ok_handler(out))])
    assert session.status == "completed"
    assert "Pipeline: completed 🎉" in capsys.readouterr().out


def test_completed_with_verdict_errors(osh_home, tmp_path, capsys):
    """review-linker 产物带 failed verdict → completed 但有 errors（warn 档）。

    用 review-linker（默认 warn 档）验证「completed 但有 errors」的
    warn 语义（方向3 门禁矩阵：warn 档失败进 errors 但不断链）。
    """
    spec = _make_spec(tmp_path)
    verdict_file = tmp_path / "review-linker.json"
    verdict_file.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    steps = [
        ("review-linker", "小克", "链接脚本审查", _ok_handler(verdict_file)),
        ("final-report", "小明", "最终报告", _ok_handler(tmp_path / "final.md")),
    ]
    session = _run(spec, steps=steps)
    assert session.status == "completed"
    assert session.errors
    assert "Completed with step verdict failures" in capsys.readouterr().out


def test_completed_final_report_info_verdict_no_errors(osh_home, tmp_path, capsys):
    """方向3: final-report（info 档）failed verdict → completed 且 errors 为空。"""
    spec = _make_spec(tmp_path)
    verdict_file = tmp_path / "final-report.json"
    verdict_file.write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    steps = [("final-report", "小明", "最终报告", _ok_handler(verdict_file))]
    session = _run(spec, steps=steps)
    assert session.status == "completed"
    assert session.errors == []  # info 档失败不进 errors


def test_step_pipeline_error_blocks_pipeline(osh_home, tmp_path):
    """handler 抛 PipelineStepError → fail_step + break（L417-424）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "a.md"
    out.write_text("x", encoding="utf-8")

    def _boom(session):
        raise PipelineStepError("gate failed")

    steps = [
        ("spec-check", "小明", "合规检查", _boom),
        ("prd", "Hermes", "PRD", _ok_handler(out)),
    ]
    session = _run(spec, steps=steps)
    assert session.status == "failed"
    assert len(session.steps) == 1  # 后续步骤未执行
    assert session.steps[0]["status"] == "failed"
    assert session.errors == ["gate failed"]


def test_step_runtime_error_goes_through_fallback(osh_home, tmp_path):
    """普通 RuntimeError → 走 fallback；abort 后转 PipelineStepError 阻断。

    PipelineStepError 是 RuntimeError 的子类；普通 RuntimeError 在
    _run_step_with_fallback 的通用 except 被捕获并尝试 fallback，
    fallback abort 时转成 PipelineStepError 由 run_pipeline 捕获阻断。
    """
    spec = _make_spec(tmp_path)

    def _boom(session):
        raise RuntimeError("runtime boom")

    fb = FallbackResult(status="abort", output="", level=5)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.apply_fallback_chain", return_value=fb
    ):
        session = _run(spec, steps=[("spec-check", "小明", "合规检查", _boom)])
    assert session.status == "failed"
    assert "Step [spec-check] failed" in session.errors[0]


def test_step_generic_failure_uses_template_fallback(osh_home, tmp_path):
    """handler 抛普通异常 + fallback 成功 → 写 {step_key}-fallback.md（L599-617）。"""
    spec = _make_spec(tmp_path)

    def _boom(session):
        raise ValueError("llm exploded")

    fb = FallbackResult(status="fallback", output="# Fallback content", level=4)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.apply_fallback_chain", return_value=fb
    ):
        session = _run(spec, steps=[("prd", "Hermes", "PRD", _boom)])
    assert session.steps[0]["status"] == "completed"
    fb_path = session.session_dir / "prd-fallback.md"
    assert fb_path.exists()
    assert fb_path.read_text(encoding="utf-8") == "# Fallback content"


def test_step_fallback_abort_fails_step(osh_home, tmp_path):
    """handler 抛普通异常 + fallback 非 fallback → PipelineStepError（L619）。"""
    spec = _make_spec(tmp_path)

    def _boom(session):
        raise ValueError("llm exploded")

    fb = FallbackResult(status="abort", output="", level=5)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.apply_fallback_chain", return_value=fb
    ):
        session = _run(spec, steps=[("prd", "Hermes", "PRD", _boom)])
    assert session.status == "failed"
    assert "Step [prd] failed" in session.errors[0]


def test_token_usage_summary(osh_home, tmp_path, capsys):
    """token_usage_total > 0 → 打印 usage 明细（L444-461）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "a.md"
    out.write_text("x", encoding="utf-8")

    def _token_handler(session):
        session.token_usage_total = 1500
        session.token_usage_steps = [
            {
                "step": "spec-check",
                "usage": {"total_tokens": 1000, "prompt_tokens": 400, "completion_tokens": 600},
            },
            {"step": "prd", "usage": {}},
        ]
        return str(out)

    _run(spec, steps=[("spec-check", "小明", "合规检查", _token_handler)])
    out_txt = capsys.readouterr().out
    assert "📊 Token Usage: 1500 total tokens (2 LLM calls)" in out_txt
    assert "spec-check: 1000 tokens (prompt 400, completion 600)" in out_txt
    assert "prd: 0 tokens (prompt 0, completion 0)" in out_txt


def test_notify_called_on_completion(osh_home, tmp_path):
    """_notify 存在 → 完成时以关键字参数调用（L464-472）。"""
    spec = _make_spec(tmp_path)
    out1 = tmp_path / "a.md"
    out1.write_text("x", encoding="utf-8")
    out2 = tmp_path / "final.md"
    out2.write_text("y", encoding="utf-8")
    steps = [
        ("spec-check", "小明", "合规检查", _ok_handler(out1)),
        ("final-report", "小明", "最终报告", _ok_handler(out2)),
    ]
    notify = mock.Mock()
    with mock.patch("yuleosh.pipeline.orchestrator._notify", notify):
        _run(spec, steps=steps)
    notify.assert_called_once()
    kwargs = notify.call_args.kwargs
    assert kwargs["name"] == "o3-test"
    assert kwargs["status"] == "completed"
    assert kwargs["total_steps"] == 2
    assert kwargs["completed_steps"] == 2
    assert kwargs["errors"] == []


def test_notify_exception_logged(osh_home, tmp_path):
    """_notify 抛异常 → 仅 log warning，不中断（L473-474）。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "final.md"
    out.write_text("y", encoding="utf-8")

    def _bad_notify(**kwargs):
        raise RuntimeError("notify down")

    with mock.patch("yuleosh.pipeline.orchestrator._notify", _bad_notify):
        session = _run(spec, steps=[("final-report", "小明", "最终报告", _ok_handler(out))])
    assert session.status == "completed"


def test_pipeline_crash_exits(osh_home, tmp_path):
    """会话构造崩溃 → log critical + sys.exit(1)（L477-480）。"""
    spec = _make_spec(tmp_path)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.PipelineSession",
        side_effect=RuntimeError("session exploded"),
    ), pytest.raises(SystemExit) as ei:
        _run(spec)
    assert ei.value.code == 1


# ---------------------------------------------------------------------------
# _propagate_step_verdict 各分支
# ---------------------------------------------------------------------------


@pytest.fixture
def vp_session(osh_home):
    session = PipelineSession("vp-test", str(osh_home / "spec.md"))
    session.add_step("spec-check", "小明", "合规检查")
    return session


def _write_json(tmp_path, name, data) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_verdict_empty_output_path(vp_session, tmp_path):
    """output_path 为空 → 直接返回（L544-545）。"""
    _propagate_step_verdict(vp_session, 0, "spec-check", "")
    assert vp_session.errors == []
    assert vp_session.steps[0]["status"] == "pending"


def test_verdict_missing_file(vp_session, tmp_path):
    """产物文件不存在 → 直接返回（L547 前半）。"""
    _propagate_step_verdict(vp_session, 0, "spec-check", str(tmp_path / "nope.json"))
    assert vp_session.errors == []


def test_verdict_non_json_suffix(vp_session, tmp_path):
    """非 .json 后缀 → 直接返回（L547 后半）。"""
    p = _write_json(tmp_path, "out.md", {"status": "failed"})
    _propagate_step_verdict(vp_session, 0, "spec-check", str(p))
    assert vp_session.errors == []


def test_verdict_non_dict_json(vp_session, tmp_path):
    """JSON 内容非 dict → 直接返回（L550-551）。"""
    p = _write_json(tmp_path, "out.json", ["not", "a", "dict"])
    _propagate_step_verdict(vp_session, 0, "spec-check", str(p))
    assert vp_session.errors == []


def test_verdict_no_status(vp_session, tmp_path):
    """JSON 无 status 字段 → verdict 为空返回（L552-554）。"""
    p = _write_json(tmp_path, "out.json", {"title": "x"})
    _propagate_step_verdict(vp_session, 0, "spec-check", str(p))
    assert vp_session.errors == []


def test_verdict_failed(vp_session, tmp_path):
    """verdict=failed → 步骤标记 failed + errors 记录（warn 档默认行为）。

    用 review-linker（默认 warn 档）而非 spec-check（info 档）——
    方向3 门禁矩阵后 spec-check 失败不再进 errors。
    """
    p = _write_json(tmp_path, "out.json", {"status": "failed"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert vp_session.steps[0]["status"] == "failed"
    assert vp_session.steps[0]["completed_at"] is not None
    assert vp_session.errors == ["[review-linker] step verdict: FAILED (out.json)"]
    assert vp_session.updated_at


def test_verdict_failed_duplicate_not_appended(vp_session, tmp_path):
    """重复 failed verdict → errors 不重复追加（warn 档默认行为）。"""
    p = _write_json(tmp_path, "out.json", {"status": "failed"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert len(vp_session.errors) == 1


def test_verdict_retry(vp_session, tmp_path):
    """verdict=retry → errors 记录 informational（L566-569）。"""
    p = _write_json(tmp_path, "out.json", {"status": "retry"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert vp_session.errors == ["[review-linker] step verdict: RETRY (out.json)"]
    assert vp_session.steps[0]["status"] == "pending"


def test_verdict_warning(vp_session, tmp_path):
    """verdict=warning → 同 retry 分支。"""
    p = _write_json(tmp_path, "out.json", {"status": "warning"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert vp_session.errors == ["[review-linker] step verdict: WARNING (out.json)"]


def test_verdict_unknown_status_ignored(vp_session, tmp_path):
    """verdict 既非 failed 也非 retry/warn 集合 → 静默忽略（L566 False 分支）。"""
    p = _write_json(tmp_path, "out.json", {"status": "in_progress"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert vp_session.errors == []
    assert vp_session.steps[0]["status"] == "pending"


def test_verdict_retry_duplicate_not_appended(vp_session, tmp_path):
    """重复 retry verdict → errors 不重复追加（L568 False 分支）。"""
    p = _write_json(tmp_path, "out.json", {"status": "retry"})
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    _propagate_step_verdict(vp_session, 0, "review-linker", str(p))
    assert len(vp_session.errors) == 1


def test_verdict_failed_out_of_range_idx(vp_session, tmp_path):
    """step_idx 越界 → 跳过步骤状态修改但仍记录错误（warn 档）。"""
    p = _write_json(tmp_path, "out.json", {"status": "failed"})
    _propagate_step_verdict(vp_session, 5, "review-linker", str(p))
    assert vp_session.errors == ["[review-linker] step verdict: FAILED (out.json)"]


def test_verdict_failed_info_gate_no_errors(vp_session, tmp_path):
    """方向3: info 档（spec-check）verdict=failed → 不进 errors，仅 step detail。"""
    p = _write_json(tmp_path, "out.json", {"status": "failed"})
    _propagate_step_verdict(vp_session, 0, "spec-check", str(p))
    assert vp_session.errors == []
    assert vp_session.steps[0]["status"] == "failed"
    assert "[spec-check] step verdict: FAILED" in vp_session.steps[0].get("detail", "")


def test_verdict_failed_block_gate_interrupts(vp_session, tmp_path):
    """方向3: block 档（review-critical-safety）verdict=failed → 返回 block + session failed。"""
    p = _write_json(tmp_path, "out.json", {"status": "failed"})
    r = _propagate_step_verdict(vp_session, 0, "review-critical-safety", str(p))
    assert r == "block"
    assert vp_session.status == "failed"
    assert vp_session.errors


# ---------------------------------------------------------------------------
# _mock_llm_client（mock 模式客户端本体）
# ---------------------------------------------------------------------------


def test_mock_llm_client_callback_shape():
    """mock client 返回 OpenAI 风格 dict（content/model/usage）（L248-258）。"""
    client = _mock_llm_client()
    result = client("system prompt", "user prompt", temperature=0.0)
    assert isinstance(result, dict)
    assert "Mock Response" in result["content"]
    assert result["model"] == "mock-mode"
    assert result["usage"]["total_tokens"] == 1500


# ---------------------------------------------------------------------------
# _run_step_with_fallback 各分支
# ---------------------------------------------------------------------------


@pytest.fixture
def rwf_session(osh_home):
    return PipelineSession("rwf-test", str(osh_home / "spec.md"))


def test_run_step_success(rwf_session, tmp_path):
    """handler 正常返回 → 返回其字符串输出（L590-592）。"""
    out = tmp_path / "o.md"
    out.write_text("x", encoding="utf-8")
    result = _run_step_with_fallback(
        _ok_handler(out),
        rwf_session,
        "spec-check",
        "合规检查",
        str(tmp_path / "spec.md"),
    )
    assert result == str(out)


def test_run_step_pipeline_error_reraises(rwf_session, tmp_path):
    """handler 抛 PipelineStepError → 不 fallback，直接重抛（L593-598）。"""
    def _boom(session):
        raise PipelineStepError("gate failed")

    with pytest.raises(PipelineStepError):
        _run_step_with_fallback(
            _boom, rwf_session, "spec-check", "合规检查", str(tmp_path / "spec.md")
        )


def test_run_step_generic_error_template_fallback(rwf_session, tmp_path):
    """handler 抛普通异常 + fallback → 写 {step_key}-fallback.md 并返回（L599-617）。"""
    def _boom(session):
        raise ValueError("llm exploded")

    fb = FallbackResult(status="fallback", output="# FB", level=4)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.apply_fallback_chain", return_value=fb
    ):
        result = _run_step_with_fallback(
            _boom, rwf_session, "prd", "PRD", str(tmp_path / "spec.md")
        )
    expected = rwf_session.session_dir / "prd-fallback.md"
    assert result == str(expected)
    assert expected.read_text(encoding="utf-8") == "# FB"


def test_run_step_generic_error_abort_raises(rwf_session, tmp_path):
    """handler 抛普通异常 + fallback abort → PipelineStepError（L619）。"""
    def _boom(session):
        raise ValueError("llm exploded")

    fb = FallbackResult(status="abort", output="", level=5)
    with mock.patch(
        "yuleosh.pipeline.orchestrator.apply_fallback_chain", return_value=fb
    ), pytest.raises(PipelineStepError):
        _run_step_with_fallback(
            _boom, rwf_session, "prd", "PRD", str(tmp_path / "spec.md")
        )


# ---------------------------------------------------------------------------
# E2E 回归 (2026-08-11): 白名单档无 final-report 时 status 必须为 completed
# ---------------------------------------------------------------------------

def test_whitelist_profile_without_final_report_marks_completed(osh_home, tmp_path):
    """minimal 等白名单档裁剪掉 final-report → 循环正常跑完即 completed。

    修复前: session.status 只在 final-report 步骤前置位，白名单档永远停在
    "created" → CLI `yuleosh pipeline run` 的 sys.exit(1) 误判失败。
    修复后: 循环结束后若未跑 final-report 且未失败 → 标记 completed。
    """
    spec = _make_spec(tmp_path)
    out1 = tmp_path / "out1.md"
    out1.write_text("ok", encoding="utf-8")
    out2 = tmp_path / "out2.md"
    out2.write_text("ok", encoding="utf-8")
    steps = [
        ("spec-check", "小明", "合规检查", _ok_handler(out1)),
        ("merge-gate", "小马", "KG Merge Gate", _ok_handler(out2)),
    ]
    session = _run(
        spec,
        steps=steps,
        mock_mode=True,
        profile="minimal",
    )
    assert session.status == "completed"
    assert [s["name"] for s in session.steps] == ["spec-check", "merge-gate"]


def test_profile_with_final_report_still_completed(osh_home, tmp_path):
    """含 final-report 的档（safety）保持原有语义：final-report 步骤前置位。"""
    spec = _make_spec(tmp_path)
    out = tmp_path / "out.md"
    out.write_text("ok", encoding="utf-8")
    steps = [
        ("spec-check", "小明", "合规检查", _ok_handler(out)),
        ("final-report", "小明", "最终报告", _ok_handler(out)),
    ]
    session = _run(spec, steps=steps, mock_mode=True, profile="safety")
    assert session.status == "completed"
    assert session.steps[-1]["name"] == "final-report"
