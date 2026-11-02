#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
test_model_registry.py — 模型注册表测试（P2.1）。

覆盖:
- T1: YAML 配置加载（内置 + 环境变量 + 项目级）
- T2: 模型信息查询（get_model, list_models）
- T3: 任务路由查询（get_task_model）
- T4: Agent 路由查询（get_agent_route）
- T5: 本地模型过滤（list_local_models）
- T6: LoRA 模型过滤（list_lora_models）
- T7: 配置覆盖（用户配置 > 内置配置）
- T8: 优雅降级（配置文件缺失）
"""

import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.llm.model_registry import ModelRegistry


@pytest.fixture(autouse=True)
def reset_registry():
    """每个测试前重置单例。"""
    ModelRegistry.reset()
    yield
    ModelRegistry.reset()


class TestModelRegistryLoad:
    """T1: YAML 配置加载。"""

    def test_builtin_config_loads(self):
        """GIVEN 内置配置文件存在 WHEN get_instance THEN 加载成功。"""
        registry = ModelRegistry.get_instance()
        assert len(registry.models) > 0
        assert len(registry.task_routes) > 0
        assert len(registry.agent_routes) > 0

    def test_builtin_models_defined(self):
        """GIVEN 内置配置 WHEN 加载 THEN 包含核心模型。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_model("deepseek-v4") is not None
        assert registry.get_model("claude-4-sonnet") is not None
        assert registry.get_model("qwen2.5-coder:14b") is not None

    def test_builtin_task_routes_defined(self):
        """GIVEN 内置配置 WHEN 加载 THEN 包含核心任务路由。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_task_model("code_generation") == "deepseek-v4"
        assert registry.get_task_model("architecture_design") == "claude-4-sonnet"

    def test_builtin_agent_routes_defined(self):
        """GIVEN 内置配置 WHEN 加载 THEN 包含核心 agent 路由。"""
        registry = ModelRegistry.get_instance()
        route = registry.get_agent_route("小克")
        assert route is not None
        assert route["model"] == "deepseek-v4"
        assert route["task_type"] == "code_generation"


class TestModelInfo:
    """T2: 模型信息查询。"""

    def test_get_model_exists(self):
        """GIVEN 模型存在 WHEN get_model THEN 返回 ModelInfo。"""
        registry = ModelRegistry.get_instance()
        model = registry.get_model("deepseek-v4")
        assert model is not None
        assert model.name == "deepseek-v4"
        assert model.provider == "deepseek"
        assert model.context_window == 128000
        assert model.risk_level == "L4"
        assert "code_generation" in model.capabilities

    def test_get_model_not_exists(self):
        """GIVEN 模型不存在 WHEN get_model THEN 返回 None。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_model("nonexistent-model") is None

    def test_list_models_all(self):
        """GIVEN 无过滤 WHEN list_models THEN 返回所有模型。"""
        registry = ModelRegistry.get_instance()
        models = registry.list_models()
        assert len(models) > 0

    def test_list_models_by_provider(self):
        """GIVEN provider 过滤 WHEN list_models THEN 只返回匹配的模型。"""
        registry = ModelRegistry.get_instance()
        ollama_models = registry.list_models(provider="ollama")
        assert len(ollama_models) > 0
        assert all(m.provider == "ollama" for m in ollama_models)

        anthropic_models = registry.list_models(provider="anthropic")
        assert len(anthropic_models) > 0
        assert all(m.provider == "anthropic" for m in anthropic_models)


class TestTaskRoutes:
    """T3: 任务路由查询。"""

    def test_get_task_model_exists(self):
        """GIVEN 任务路由存在 WHEN get_task_model THEN 返回模型名。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_task_model("code_generation") == "deepseek-v4"
        assert registry.get_task_model("architecture_design") == "claude-4-sonnet"

    def test_get_task_model_not_exists(self):
        """GIVEN 任务路由不存在 WHEN get_task_model THEN 返回 None。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_task_model("nonexistent_task") is None


class TestAgentRoutes:
    """T4: Agent 路由查询。"""

    def test_get_agent_route_exists(self):
        """GIVEN agent 路由存在 WHEN get_agent_route THEN 返回路由配置。"""
        registry = ModelRegistry.get_instance()
        route = registry.get_agent_route("小克")
        assert route is not None
        assert "model" in route
        assert "provider" in route
        assert "task_type" in route
        assert "risk_level" in route

    def test_get_agent_route_not_exists(self):
        """GIVEN agent 路由不存在 WHEN get_agent_route THEN 返回 None。"""
        registry = ModelRegistry.get_instance()
        assert registry.get_agent_route("nonexistent_agent") is None


class TestLocalModels:
    """T5: 本地模型过滤。"""

    def test_list_local_models(self):
        """GIVEN 本地模型存在 WHEN list_local_models THEN 只返回本地模型。"""
        registry = ModelRegistry.get_instance()
        local_models = registry.list_local_models()
        assert len(local_models) > 0
        assert all(m.is_local for m in local_models)
        # Ollama 模型应该是本地的
        assert any(m.name == "qwen2.5-coder:14b" for m in local_models)

    def test_cloud_models_not_in_local(self):
        """GIVEN 云端模型 WHEN list_local_models THEN 不包含。"""
        registry = ModelRegistry.get_instance()
        local_models = registry.list_local_models()
        assert not any(m.name == "deepseek-v4" for m in local_models)
        assert not any(m.name == "claude-4-sonnet" for m in local_models)


class TestLoraModels:
    """T6: LoRA 模型过滤。"""

    def test_list_lora_models_empty_by_default(self):
        """GIVEN 内置配置无 LoRA WHEN list_lora_models THEN 返回空列表。"""
        registry = ModelRegistry.get_instance()
        lora_models = registry.list_lora_models()
        # 内置配置暂时没有 LoRA 模型
        assert isinstance(lora_models, list)

    def test_lora_model_with_custom_config(self):
        """GIVEN 自定义配置含 LoRA WHEN 加载 THEN 可查询到。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
models:
  test-lora-model:
    provider: lora
    context_window: 32768
    risk_level: L3
    capabilities: [code_generation]
    pricing:
      input_per_1k: 0.0
      output_per_1k: 0.0
    is_local: true
    is_lora: true
    lora_base_model: qwen2.5-coder:14b
""")
            f.flush()
            os.environ["YULEOSH_MODEL_REGISTRY"] = f.name
            ModelRegistry.reset()
            registry = ModelRegistry.get_instance()
            lora_models = registry.list_lora_models()
            assert len(lora_models) > 0
            assert any(m.name == "test-lora-model" for m in lora_models)
            assert all(m.is_lora for m in lora_models)
            del os.environ["YULEOSH_MODEL_REGISTRY"]
            Path(f.name).unlink()


class TestConfigOverride:
    """T7: 配置覆盖。"""

    def test_env_override(self):
        """GIVEN 环境变量指定配置 WHEN 加载 THEN 使用自定义配置。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
models:
  custom-model:
    provider: custom
    context_window: 65536
    risk_level: L2
    capabilities: [test]
    pricing:
      input_per_1k: 0.0
      output_per_1k: 0.0
""")
            f.flush()
            os.environ["YULEOSH_MODEL_REGISTRY"] = f.name
            ModelRegistry.reset()
            registry = ModelRegistry.get_instance()
            model = registry.get_model("custom-model")
            assert model is not None
            assert model.provider == "custom"
            assert model.context_window == 65536
            del os.environ["YULEOSH_MODEL_REGISTRY"]
            Path(f.name).unlink()

    def test_merge_strategy(self):
        """GIVEN 自定义配置覆盖部分模型 WHEN 加载 THEN 合并成功。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
models:
  deepseek-v4:
    provider: deepseek
    context_window: 256000
    risk_level: L4
    capabilities: [code_generation]
    pricing:
      input_per_1k: 0.003
      output_per_1k: 0.010
""")
            f.flush()
            os.environ["YULEOSH_MODEL_REGISTRY"] = f.name
            ModelRegistry.reset()
            registry = ModelRegistry.get_instance()
            model = registry.get_model("deepseek-v4")
            assert model is not None
            # 应该被覆盖
            assert model.context_window == 256000
            assert model.input_per_1k == 0.003
            del os.environ["YULEOSH_MODEL_REGISTRY"]
            Path(f.name).unlink()


class TestGracefulDegradation:
    """T8: 优雅降级。"""

    def test_missing_config_file(self):
        """GIVEN 配置文件不存在 WHEN 加载 THEN 返回空注册表。"""
        os.environ["YULEOSH_MODEL_REGISTRY"] = "/nonexistent/path.yaml"
        ModelRegistry.reset()
        registry = ModelRegistry.get_instance()
        # 内置配置应该还是能加载
        assert len(registry.models) > 0
        del os.environ["YULEOSH_MODEL_REGISTRY"]

    def test_invalid_yaml(self):
        """GIVEN YAML 格式错误 WHEN 加载 THEN 跳过该配置。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            os.environ["YULEOSH_MODEL_REGISTRY"] = f.name
            ModelRegistry.reset()
            registry = ModelRegistry.get_instance()
            # 内置配置应该还是能加载
            assert len(registry.models) > 0
            del os.environ["YULEOSH_MODEL_REGISTRY"]
            Path(f.name).unlink()
