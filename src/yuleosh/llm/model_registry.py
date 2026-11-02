# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Model registry — 外部化模型路由配置（P2.1）。

将硬编码的 TASK_ROUTES / PROVIDER_MODEL_MAP / TASK_RISK_LEVELS 等路由表
外部化为 YAML 配置文件，支持运行时动态添加模型、调整路由策略。

设计:
- 默认配置: src/yuleosh/llm/model_registry.yaml（内置）
- 用户覆盖: .yuleosh/model-registry.yaml（项目级）
- 环境变量: YULEOSH_MODEL_REGISTRY 指定自定义路径
- 合并策略: 用户配置 > 内置配置（同名 key 覆盖）

配置结构:
  models:
    <model_name>:
      provider: <provider_name>
      context_window: <int>
      risk_level: <L0-L4>
      capabilities: [<cap1>, <cap2>]
      pricing: {input_per_1k: <float>, output_per_1k: <float>}

  task_routes:
    <task_type>: <model_name>

  agent_routes:
    <agent_name>:
      model: <model_name>
      task_type: <task_type>
      risk_level: <L0-L4>
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("llm.model_registry")

# 内置配置文件路径
_BUILTIN_REGISTRY = Path(__file__).parent / "model_registry.yaml"


@dataclass
class ModelInfo:
    """模型元数据。"""

    name: str
    provider: str
    context_window: int = 32768
    risk_level: str = "L0"  # L0-L4
    capabilities: list[str] = field(default_factory=list)
    input_per_1k: float = 0.0
    output_per_1k: float = 0.0
    is_local: bool = False
    is_lora: bool = False
    lora_base_model: str = ""  # LoRA 基础模型


@dataclass
class ModelRegistry:
    """模型注册表（单例）。"""

    models: dict[str, ModelInfo] = field(default_factory=dict)
    task_routes: dict[str, str] = field(default_factory=dict)
    agent_routes: dict[str, dict] = field(default_factory=dict)

    _instance: Optional["ModelRegistry"] = None

    @classmethod
    def get_instance(cls) -> "ModelRegistry":
        """获取单例（懒加载）。"""
        if cls._instance is None:
            cls._instance = cls._load()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试用）。"""
        cls._instance = None

    @classmethod
    def _load(cls) -> "ModelRegistry":
        """加载模型注册表（内置 + 用户覆盖）。"""
        registry = cls()

        # 1. 加载内置配置
        if _BUILTIN_REGISTRY.exists():
            registry._load_file(_BUILTIN_REGISTRY)

        # 2. 加载环境变量指定的配置
        env_path = os.environ.get("YULEOSH_MODEL_REGISTRY")
        if env_path:
            p = Path(env_path)
            if p.exists():
                registry._load_file(p)

        # 3. 加载项目级配置
        project_cfg = Path(".yuleosh/model-registry.yaml")
        if project_cfg.exists():
            registry._load_file(project_cfg)

        log.info(
            "Model registry loaded: %d models, %d task routes, %d agent routes",
            len(registry.models),
            len(registry.task_routes),
            len(registry.agent_routes),
        )
        return registry

    def _load_file(self, path: Path) -> None:
        """从 YAML 文件加载配置。"""
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not data:
                return

            # 加载模型定义
            for name, info in (data.get("models") or {}).items():
                self.models[name] = ModelInfo(
                    name=name,
                    provider=info.get("provider", "unknown"),
                    context_window=info.get("context_window", 32768),
                    risk_level=info.get("risk_level", "L0"),
                    capabilities=info.get("capabilities", []),
                    input_per_1k=info.get("pricing", {}).get("input_per_1k", 0.0),
                    output_per_1k=info.get("pricing", {}).get("output_per_1k", 0.0),
                    is_local=info.get("is_local", False),
                    is_lora=info.get("is_lora", False),
                    lora_base_model=info.get("lora_base_model", ""),
                )

            # 加载任务路由
            for task, model in (data.get("task_routes") or {}).items():
                self.task_routes[task] = model

            # 加载 agent 路由
            for agent, route in (data.get("agent_routes") or {}).items():
                self.agent_routes[agent] = route

        except Exception as e:
            log.warning("Failed to load model registry from %s: %s", path, e)

    def get_model(self, name: str) -> Optional[ModelInfo]:
        """获取模型信息。"""
        return self.models.get(name)

    def get_task_model(self, task_type: str) -> Optional[str]:
        """获取任务类型对应的默认模型。"""
        return self.task_routes.get(task_type)

    def get_agent_route(self, agent_name: str) -> Optional[dict]:
        """获取 agent 路由配置。"""
        return self.agent_routes.get(agent_name)

    def list_models(self, provider: str | None = None) -> list[ModelInfo]:
        """列出所有模型（可按 provider 过滤）。"""
        if provider:
            return [m for m in self.models.values() if m.provider == provider]
        return list(self.models.values())

    def list_local_models(self) -> list[ModelInfo]:
        """列出所有本地模型。"""
        return [m for m in self.models.values() if m.is_local]

    def list_lora_models(self) -> list[ModelInfo]:
        """列出所有 LoRA 模型。"""
        return [m for m in self.models.values() if m.is_lora]
