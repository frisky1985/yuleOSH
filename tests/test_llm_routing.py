# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""方案 C (C3) — agent → model 路由表 + L3/L4 禁下钻硬规则测试。

覆盖:
  - AGENT_MODEL_ROUTES 登记完整性（每个 agent 标签都有条目、默认值=现状）;
  - resolve_config 传 agent 标签命中路由（model/provider/task_type 正确）;
  - 未知 agent 标签回退原逻辑;
  - L3/L4 判定任务禁止下钻小模型（env 覆盖小模型 → 回退默认 + warning）;
  - L0/L1/L2 允许下钻; 未显式传 task_type 时保持既有 env 语义。
"""

import os
from unittest import mock

from yuleosh.agent_registry import AGENT_ROLES
from yuleosh.llm.client import (
    AGENT_MODEL_ROUTES,
    SMALL_MODELS,
    TASK_RISK_LEVELS,
    TASK_ROUTES,
    resolve_config,
)
from yuleosh.llm.providers.base import TASK_BUDGETS

# ---------------------------------------------------------------------------
# AGENT_MODEL_ROUTES / TASK_RISK_LEVELS 登记完整性
# ---------------------------------------------------------------------------


class TestAgentModelRoutes:
    """路由表登记完整性。"""

    def test_every_agent_has_route(self):
        """每个 agent 标签都有路由条目，且字段齐全。"""
        assert AGENT_ROLES, "AGENT_ROLES 不应为空"
        for agent in AGENT_ROLES:
            assert agent in AGENT_MODEL_ROUTES, f"缺少 agent 路由: {agent}"
            entry = AGENT_MODEL_ROUTES[agent]
            for key in ("model", "provider", "task_type", "risk_level"):
                assert entry.get(key), f"{agent} 路由缺字段 {key}"

    def test_route_defaults_match_current_mapping(self):
        """默认值=现状：全部 deepseek-v4/deepseek，不改变现有 TASK_ROUTES。"""
        for entry in AGENT_MODEL_ROUTES.values():
            assert entry["model"] == "deepseek-v4"
            assert entry["provider"] == "deepseek"
        # 既有 task_type → model 映射原样保留（golden 兼容）
        assert TASK_ROUTES["code_generation"] == "deepseek-v4"
        assert TASK_ROUTES["architecture_design"] == "claude-4-sonnet"
        assert TASK_ROUTES["misra_review"] == "claude-4-sonnet"

    def test_route_task_type_registered_and_consistent(self):
        """路由 task_type 都有风险等级，且与条目 risk_level 一致。"""
        for agent, entry in AGENT_MODEL_ROUTES.items():
            assert entry["task_type"] in TASK_RISK_LEVELS, (
                f"{agent} 路由 task_type 无风险等级: {entry['task_type']}"
            )
            assert TASK_RISK_LEVELS[entry["task_type"]] == entry["risk_level"]

    def test_all_task_routes_have_risk_level(self):
        """TASK_ROUTES 每个 key 都登记了风险等级（合法取值 L0-L4）。"""
        for task_type in TASK_ROUTES:
            assert task_type in TASK_RISK_LEVELS, f"缺风险等级: {task_type}"
            assert TASK_RISK_LEVELS[task_type] in ("L0", "L1", "L2", "L3", "L4")

    def test_small_models_are_known(self):
        """SMALL_MODELS 非空且含 deepseek-chat（硬规则判据）。"""
        assert isinstance(SMALL_MODELS, tuple)
        assert "deepseek-chat" in SMALL_MODELS


# ---------------------------------------------------------------------------
# resolve_config — agent 标签路由
# ---------------------------------------------------------------------------


class TestResolveConfigAgentRouting:
    """resolve_config 传 agent 标签命中 AGENT_MODEL_ROUTES。"""

    def test_agent_label_routes_to_entry(self):
        """task_type='小克' → 命中路由（model/provider/task_type 正确）。"""
        cfg = resolve_config("hi", None, "小克", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "code_generation"

    def test_agent_label_qa_route(self):
        """task_type='小马' → misra_review，预算/RAG 跟随映射后的 task_type。"""
        cfg = resolve_config("hi", None, "小马", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "misra_review"
        assert cfg.max_cost_usd == TASK_BUDGETS["misra_review"]["max_cost_usd"]
        assert cfg.rag_enabled is True

    def test_agent_label_budget_from_route_task(self):
        """task_type='Claude' → architecture_design 预算（0.80，max_tokens 封顶 4096）。"""
        cfg = resolve_config("hi", None, "Claude", None)
        assert cfg.task_type == "architecture_design"
        assert cfg.max_cost_usd == TASK_BUDGETS["architecture_design"]["max_cost_usd"]
        assert cfg.max_tokens == 4096  # resolve_config 对 max_tokens 统一封顶 4096

    def test_agent_label_budget_key_exists(self):
        """TASK_BUDGETS 中 agent 标签 key 与路由 task_type 预算一致。"""
        for agent, entry in AGENT_MODEL_ROUTES.items():
            assert agent in TASK_BUDGETS
            task_budget = TASK_BUDGETS.get(
                entry["task_type"], TASK_BUDGETS["code_generation"]
            )
            assert TASK_BUDGETS[agent] == task_budget

    def test_unknown_agent_label_falls_back(self):
        """未知 agent 标签回退原逻辑（deepseek-v4/deepseek，task_type 原样保留）。"""
        cfg = resolve_config("hi", None, "神秘agent", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "神秘agent"


# ---------------------------------------------------------------------------
# L3/L4 禁下钻硬规则
# ---------------------------------------------------------------------------


class TestL3L4NoDownshift:
    """L3/L4 判定任务（审查 / 设计决策）禁止下钻小模型（防幻觉）。"""

    def test_l4_blocks_small_model_env(self, caplog):
        """code_generation(L4) + LLM_MODEL=deepseek-chat → 回退默认 + warning。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "code_generation", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert "禁止下钻" in caplog.text

    def test_l3_blocks_small_model_env(self, caplog):
        """misra_review(L3) + LLM_MODEL=deepseek-chat → 回退 claude-4-sonnet。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "misra_review", None)
        assert cfg.model == "claude-4-sonnet"
        assert cfg.provider == "anthropic"
        assert "禁止下钻" in caplog.text

    def test_agent_route_l4_blocks_downshift(self):
        """agent 路由 L4（小克→code_generation）+ 小模型 env → 回退路由默认。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "mock"}, clear=False):
            cfg = resolve_config("hi", None, "小克", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "code_generation"

    def test_agent_route_l3_blocks_downshift(self):
        """agent 路由 L3（小马→misra_review）+ 小模型 env → 回退路由默认。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "小马", None)
        assert cfg.model == "deepseek-v4"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "misra_review"

    def test_l4_non_small_model_env_allowed(self):
        """L4 + 非小模型 env（claude-4-sonnet）→ 允许，不误伤。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "claude-4-sonnet"}, clear=False):
            cfg = resolve_config("hi", None, "code_generation", None)
        assert cfg.model == "claude-4-sonnet"
        assert cfg.provider == "anthropic"

    def test_l4_provider_env_default_not_blocked(self):
        """L4 + YULEOSH_LLM_PROVIDER=mock（默认模型 deepseek-v4 非小模型）→ 放行。"""
        with mock.patch.dict(os.environ, {"YULEOSH_LLM_PROVIDER": "mock"}, clear=False):
            cfg = resolve_config("hi", None, "code_generation", None)
        assert cfg.provider == "mock"
        assert cfg.model == "deepseek-v4"


# ---------------------------------------------------------------------------
# L0/L1/L2 允许下钻
# ---------------------------------------------------------------------------


class TestLowRiskAllowsDownshift:
    """低风险任务允许下钻小模型；未显式传 task_type 保持既有语义。"""

    def test_l2_allows_downshift(self):
        """test_generation(L2) + LLM_MODEL=deepseek-chat → 直接生效。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "test_generation", None)
        assert cfg.model == "deepseek-chat"
        assert cfg.provider == "deepseek"

    def test_l1_allows_downshift(self):
        """simple_summary(L1) + LLM_MODEL=deepseek-chat → 直接生效。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "simple_summary", None)
        assert cfg.model == "deepseek-chat"
        assert cfg.provider == "deepseek"

    def test_agent_route_l1_allows_downshift(self):
        """agent 路由 L1（QEMU→simple_summary）+ 小模型 env → 允许下钻。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, "QEMU", None)
        assert cfg.model == "deepseek-chat"
        assert cfg.provider == "deepseek"
        assert cfg.task_type == "simple_summary"

    def test_task_type_none_keeps_legacy_env_behavior(self):
        """未显式传 task_type → 保持既有 LLM_MODEL env 覆盖语义（golden 兼容）。"""
        with mock.patch.dict(os.environ, {"LLM_MODEL": "deepseek-chat"}, clear=False):
            cfg = resolve_config("hi", None, None, None)
        assert cfg.model == "deepseek-chat"
        assert cfg.provider == "deepseek"
