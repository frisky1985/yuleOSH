# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
LoRA 微调模块（Phase 2 P2.2 + P2.3）。

提供项目代码库的 LoRA 微调基础设施：
- data_prep: 训练数据准备（从代码库提取 instruction-input-output 三元组）
- trainer: LoRA 训练脚本（支持 Ollama 和 Hugging Face PEFT 双后端）
- service_manager: 模型服务管理（Ollama/vLLM 部署、健康检查、模型热切换）

使用场景:
- 项目特定代码风格微调（如 AUTOSAR 命名规范）
- 领域知识增强（如 MISRA 规则、ASPICE 流程）
- 降低幻觉（项目代码库锚定）
- 自动化部署和监控 Ollama/vLLM 服务

依赖:
- Ollama 后端: ollama (本地服务)
- PEFT 后端: transformers, peft, torch, datasets (GPU 推荐)
"""

from yuleosh.lora.data_prep import (
    DataPrepReport,
    TrainingSample,
    prepare_training_data,
)
from yuleosh.lora.service_manager import (
    BackendType,
    ModelServiceManager,
    OllamaServiceManager,
    ServiceInfo,
    ServiceManagerReport,
    ServiceStatus,
    VllmServiceManager,
)
from yuleosh.lora.trainer import (
    LoraConfig,
    TrainingReport,
    train_lora,
)

__all__ = [
    # data_prep
    "DataPrepReport",
    "TrainingSample",
    "prepare_training_data",
    # trainer
    "LoraConfig",
    "TrainingReport",
    "train_lora",
    # service_manager
    "BackendType",
    "ModelServiceManager",
    "OllamaServiceManager",
    "VllmServiceManager",
    "ServiceInfo",
    "ServiceStatus",
    "ServiceManagerReport",
]
