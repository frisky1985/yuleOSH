"""Tests for pipeline LLM gateway (方案 C, C4+C5).

Covers:
- call_step_llm 统一入口：usage 记录、task_type 解析、温度/长度透传
- mock 模式占位（不调 LLM）
- pipeline 总量预算（warning 不阻断 / ENFORCE=1 阻断）
- 失败统一包装 PipelineStepError
- role-scoped constraints 组装（A1-A4 角色隔离）
- 灰度迁移 YULEOSH_LLM_GATEWAY_STEPS（命中走 gateway，其余走旧路径）
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.pipeline.llm_gateway import (
    MOCK_PLACEHOLDER,
    call_step_llm,
    resolve_step_role,
)
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages.llm import _call_llm, _gateway_step_keys

# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def session(tmp_path, monkeypatch):
    """Real PipelineSession with isolated OSH_HOME."""
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    monkeypatch.delenv("YULEOSH_LLM_GATEWAY_STEPS", raising=False)
    monkeypatch.delenv("YULEOSH_PIPELINE_TOKEN_BUDGET_ENFORCE", raising=False)
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n")
    s = PipelineSession("gateway-test", str(spec))
    s.pipeline_knowledge_step_key = "arch-review"  # 小克 → developer
    s.agent_shared_baseline = "共享安全基线"
    return s


def _fake_call_sync_return(content="ok", total=150):
    return {
        "content": content,
        "model": "deepseek-v4",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": total},
    }


# ── call_step_llm 正常路径 ─────────────────────────────────────────────

class TestCallStepLlm:

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_normal_returns_content_and_records_usage(self, mock_call_sync, session):
        mock_call_sync.return_value = _fake_call_sync_return(content="hello", total=150)
        out = call_step_llm(session, "sys", "usr")
        assert out == "hello"
        assert session.token_usage_total == 150
        assert session.token_usage_steps == [
            {"step": "arch-review", "usage": {
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            }},
        ]

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_temperature_max_tokens_passed_through(self, mock_call_sync, session):
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr", temperature=0.7, max_tokens=512)
        _, kwargs = mock_call_sync.call_args
        assert kwargs["config"].temperature == 0.7
        assert kwargs["config"].max_tokens == 512

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_task_type_resolved_from_step_role(self, mock_call_sync, session):
        """arch-review 步骤 → 小克 → developer 角色 → task_type='developer'."""
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr")
        _, kwargs = mock_call_sync.call_args
        assert kwargs["task_type"] == "developer"

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_task_type_explicit_override(self, mock_call_sync, session):
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr", task_type="misra_review")
        _, kwargs = mock_call_sync.call_args
        assert kwargs["task_type"] == "misra_review"

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_unknown_step_role_is_none(self, mock_call_sync, session):
        session.pipeline_knowledge_step_key = "no-such-step"
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr")
        _, kwargs = mock_call_sync.call_args
        assert kwargs["task_type"] is None


# ── mock 模式 ──────────────────────────────────────────────────────────

class TestMockMode:

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_mock_mode_returns_placeholder_without_llm(self, mock_call_sync, session):
        session.mock_mode = True
        out = call_step_llm(session, "sys", "usr")
        assert out == MOCK_PLACEHOLDER
        mock_call_sync.assert_not_called()
        assert session.token_usage_total == 0
        assert session.token_usage_steps == []


# ── pipeline 总量预算 ──────────────────────────────────────────────────

class TestBudget:

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_budget_exceeded_warns_but_returns(self, mock_call_sync, session, monkeypatch, caplog):
        import yuleosh.pipeline.llm_gateway as gw
        monkeypatch.setattr(gw, "PIPELINE_TOKEN_BUDGET", 100)
        mock_call_sync.return_value = _fake_call_sync_return(content="still-here", total=150)
        with caplog.at_level(logging.WARNING, logger="pipeline.llm_gateway"):
            out = call_step_llm(session, "sys", "usr")
        assert out == "still-here"  # 超限不阻断
        assert session.token_usage_total == 150
        assert "exceeded" in caplog.text

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_budget_enforce_raises(self, mock_call_sync, session, monkeypatch):
        import yuleosh.pipeline.llm_gateway as gw
        monkeypatch.setattr(gw, "PIPELINE_TOKEN_BUDGET", 100)
        monkeypatch.setenv("YULEOSH_PIPELINE_TOKEN_BUDGET_ENFORCE", "1")
        mock_call_sync.return_value = _fake_call_sync_return(total=150)
        with pytest.raises(PipelineStepError, match="budget exceeded"):
            call_step_llm(session, "sys", "usr")

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_budget_within_limit_no_warning(self, mock_call_sync, session, monkeypatch, caplog):
        import yuleosh.pipeline.llm_gateway as gw
        monkeypatch.setattr(gw, "PIPELINE_TOKEN_BUDGET", 1000)
        mock_call_sync.return_value = _fake_call_sync_return(total=150)
        with caplog.at_level(logging.WARNING, logger="pipeline.llm_gateway"):
            call_step_llm(session, "sys", "usr")
        assert "exceeded" not in caplog.text

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_accumulated_total_counts_across_calls(self, mock_call_sync, session):
        mock_call_sync.return_value = _fake_call_sync_return(total=100)
        call_step_llm(session, "sys", "usr")
        call_step_llm(session, "sys", "usr")
        assert session.token_usage_total == 200
        assert len(session.token_usage_steps) == 2


# ── 失败包装 ───────────────────────────────────────────────────────────

class TestFailure:

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_llm_failure_raises_pipeline_step_error(self, mock_call_sync, session):
        mock_call_sync.side_effect = RuntimeError("boom transport down")
        with pytest.raises(PipelineStepError) as exc:
            call_step_llm(session, "sys", "usr")
        assert "boom transport down" in str(exc.value)
        assert "arch-review" in str(exc.value)


# ── role-scoped constraints 组装（A1-A4）───────────────────────────────

class TestRoleScopedConstraints:

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_only_current_role_constraints_injected(self, mock_call_sync, session):
        session.agent_constraints_by_role = {
            "developer": "小克专属：必须写单元测试",
            "pm": "小明专属：必须写 PRD",
            "qa": "小马专属：必须跑回归",
        }
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr")
        _, kwargs = mock_call_sync.call_args
        sys_prompt = kwargs["system_prompt"]
        # 当前步骤 arch-review → 小克 → developer：只注入小克约束 + 共享基线
        assert "小克专属：必须写单元测试" in sys_prompt
        assert "共享安全基线" in sys_prompt
        assert "小明专属" not in sys_prompt
        assert "小马专属" not in sys_prompt
        assert "usr" == kwargs["prompt"]

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_legacy_agent_constraints_path(self, mock_call_sync, session):
        """无 by_role dict 时回退 session.agent_constraints（向后兼容）。"""
        session.agent_constraints_by_role = {}
        session.agent_constraints = "旧版整体约束"
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr")
        _, kwargs = mock_call_sync.call_args
        assert "旧版整体约束" in kwargs["system_prompt"]

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_no_constraints_passthrough(self, mock_call_sync, session):
        session.agent_constraints_by_role = {}
        session.agent_constraints = ""
        session.agent_shared_baseline = ""
        mock_call_sync.return_value = _fake_call_sync_return()
        call_step_llm(session, "sys", "usr")
        _, kwargs = mock_call_sync.call_args
        assert kwargs["system_prompt"] == "sys"


# ── resolve_step_role ──────────────────────────────────────────────────

class TestResolveStepRole:

    def test_role_for_known_step(self, session):
        session.pipeline_knowledge_step_key = "spec-check"  # 小明 → pm
        assert resolve_step_role(session) == "pm"

    def test_role_none_for_unknown_step(self, session):
        session.pipeline_knowledge_step_key = "nope"
        assert resolve_step_role(session) is None

    def test_role_none_for_empty_step(self, session):
        session.pipeline_knowledge_step_key = ""
        assert resolve_step_role(session) is None


# ── 灰度迁移 (C5) ──────────────────────────────────────────────────────

class TestGrayscale:

    def test_gateway_step_keys_parsing(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_LLM_GATEWAY_STEPS", "spec-check, prd ,  test-planning")
        assert _gateway_step_keys() == {"spec-check", "prd", "test-planning"}

    def test_gateway_step_keys_unset(self, monkeypatch):
        monkeypatch.delenv("YULEOSH_LLM_GATEWAY_STEPS", raising=False)
        assert _gateway_step_keys() == set()

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_gateway_step_routes_to_gateway(self, mock_call_sync, session, monkeypatch):
        """YULEOSH_LLM_GATEWAY_STEPS 命中时走 gateway（旧 llm_client 不被调）。"""
        monkeypatch.setenv("YULEOSH_LLM_GATEWAY_STEPS", "spec-check")
        session.pipeline_knowledge_step_key = "spec-check"
        old_client = MagicMock(return_value={"content": "old-path"})
        session.llm_client = old_client
        mock_call_sync.return_value = _fake_call_sync_return(content="gateway-ok", total=42)

        result = _call_llm(session, "sys", "usr")

        assert result == {"content": "gateway-ok"}
        old_client.assert_not_called()
        mock_call_sync.assert_called_once()
        assert session.token_usage_total == 42

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_other_step_keeps_old_path(self, mock_call_sync, session, monkeypatch):
        """未命中名单的步骤仍走旧路径（session.llm_client / chat_completion）。"""
        monkeypatch.setenv("YULEOSH_LLM_GATEWAY_STEPS", "spec-check")
        session.pipeline_knowledge_step_key = "arch-review"
        session.mock_mode = True  # 跳过 knowledge injection，保持测试干净
        old_client = MagicMock(return_value={"content": "old-path"})
        session.llm_client = old_client

        result = _call_llm(session, "sys", "usr")

        assert result == {"content": "old-path"}
        old_client.assert_called_once()
        mock_call_sync.assert_not_called()

    def test_env_unset_defaults_to_old_path(self, session, monkeypatch):
        """不设 YULEOSH_LLM_GATEWAY_STEPS 时默认全部走旧路径。"""
        monkeypatch.delenv("YULEOSH_LLM_GATEWAY_STEPS", raising=False)
        session.mock_mode = True
        old_client = MagicMock(return_value={"content": "old-path"})
        session.llm_client = old_client
        result = _call_llm(session, "sys", "usr")
        assert result == {"content": "old-path"}
        old_client.assert_called_once()

    @patch("yuleosh.pipeline.llm_gateway.LLMClient.call_sync")
    def test_gateway_step_mock_mode_placeholder(self, mock_call_sync, session, monkeypatch):
        """灰度步骤 + mock 模式：gateway 返回占位，不调 LLM。"""
        monkeypatch.setenv("YULEOSH_LLM_GATEWAY_STEPS", "spec-check")
        session.pipeline_knowledge_step_key = "spec-check"
        session.mock_mode = True
        result = _call_llm(session, "sys", "usr")
        assert result == {"content": MOCK_PLACEHOLDER}
        mock_call_sync.assert_not_called()
