#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
LoRA 训练脚本（P2.2）。

支持两种训练后端:
1. Hugging Face PEFT (GPU) — 完整 LoRA 训练，需要 CUDA
2. Ollama (CPU) — 简化版 LoRA，使用量化模型

设计要点:
- 训练数据: JSONL 格式（data_prep.py 输出）
- 基础模型: 可配置（默认 qwen2.5-coder:14b）
- LoRA 参数: rank, alpha, dropout（可调整）
- 输出: LoRA adapter 权重 + 配置

使用场景:
- 项目特定代码风格微调
- 领域知识增强（MISRA/ASPICE）
- 降低幻觉（代码库锚定）

依赖:
- GPU 训练: transformers, peft, torch, datasets
- CPU 训练: ollama (本地服务)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("lora.trainer")


# ═══════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class LoraConfig:
    """LoRA 训练配置。"""

    # 基础模型
    base_model: str = "qwen2.5-coder:14b"
    
    # LoRA 参数
    rank: int = 8  # LoRA rank (r)
    alpha: int = 32  # LoRA alpha (scaling factor)
    dropout: float = 0.1  # LoRA dropout
    
    # 训练参数
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    max_seq_length: int = 2048
    
    # 输出
    output_dir: str = "./lora_output"
    
    # 后端选择
    backend: str = "ollama"  # "ollama" | "peft"
    
    # 设备（PEFT 后端）
    device: str = "auto"  # "auto" | "cuda" | "cpu"


@dataclass
class TrainingReport:
    """训练报告。"""

    success: bool = False
    backend: str = ""
    base_model: str = ""
    adapter_path: str = ""
    num_samples: int = 0
    num_epochs: int = 0
    training_time_s: float = 0.0
    metrics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Ollama 后端（CPU 训练）
# ═══════════════════════════════════════════════════════════════════════

def _train_with_ollama(
    train_data: Path,
    config: LoraConfig,
) -> TrainingReport:
    """使用 Ollama 训练 LoRA adapter（CPU 友好）。

    Ollama 支持通过 Modelfile 创建自定义 LoRA 模型。
    注意: Ollama 的 LoRA 支持有限，主要用于推理时加载 adapter。
    真正的训练需要 Hugging Face PEFT 或 llama.cpp。
    
    这里我们创建一个简化的 "fine-tuning" 流程:
    1. 将训练数据转换为 Ollama 可理解的格式
    2. 创建 Modelfile 指定基础模型和 adapter
    3. 使用 ollama create 构建自定义模型
    
    实际生产中，建议使用 PEFT 后端进行完整训练。
    """
    report = TrainingReport(backend="ollama", base_model=config.base_model)
    
    try:
        # 检查 Ollama 是否可用
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            report.errors.append("Ollama not available or not running")
            return report
        
        # 创建临时 Modelfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Modelfile", delete=False) as f:
            f.write(f"FROM {config.base_model}\n")
            f.write(f"# LoRA adapter training data: {train_data}\n")
            f.write(f"# Note: Ollama does not support true LoRA training.\n")
            f.write(f"# This is a placeholder for adapter-based inference.\n")
            f.write(f"PARAMETER temperature 0.3\n")
            f.write(f"PARAMETER top_p 0.95\n")
            modelfile_path = f.name
        
        # 构建自定义模型名
        model_name = f"{config.base_model}-lora-custom"
        
        # 创建模型（这会复制基础模型，实际 LoRA 需要 PEFT）
        log.info("Creating custom Ollama model: %s", model_name)
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", modelfile_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if result.returncode != 0:
            report.errors.append(f"ollama create failed: {result.stderr}")
            return report
        
        # 清理临时文件
        Path(modelfile_path).unlink()
        
        report.success = True
        report.adapter_path = model_name
        report.num_samples = sum(1 for _ in train_data.open())
        log.info("Ollama model created: %s (note: true LoRA requires PEFT backend)", model_name)
        
    except subprocess.TimeoutExpired:
        report.errors.append("Ollama training timed out")
    except Exception as e:
        report.errors.append(f"Ollama training failed: {e}")
        log.exception("Ollama training error")
    
    return report


# ═══════════════════════════════════════════════════════════════════════
# PEFT 后端（GPU 训练）
# ═══════════════════════════════════════════════════════════════════════

def _train_with_peft(
    train_data: Path,
    config: LoraConfig,
) -> TrainingReport:
    """使用 Hugging Face PEFT 训练 LoRA adapter（需要 GPU）。

    完整训练流程:
    1. 加载基础模型和 tokenizer
    2. 准备 LoRA 配置
    3. 加载训练数据
    4. 训练（使用 Trainer API）
    5. 保存 adapter 权重
    """
    report = TrainingReport(backend="peft", base_model=config.base_model)
    
    try:
        # 检查依赖
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import LoraConfig as PeftLoraConfig, get_peft_model
            from datasets import load_dataset
        except ImportError as e:
            report.errors.append(f"Missing dependencies: {e}. Install with: pip install transformers peft torch datasets")
            return report
        
        # 检查 GPU
        if config.device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = config.device
        
        if device == "cpu":
            log.warning("Training on CPU will be very slow. Consider using Ollama backend or GPU.")
        
        log.info("Loading base model: %s on %s", config.base_model, device)
        
        # 加载 tokenizer 和模型
        tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            config.base_model,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map=device if device == "cuda" else None,
            trust_remote_code=True,
        )
        
        # 配置 LoRA
        peft_config = PeftLoraConfig(
            r=config.rank,
            lora_alpha=config.alpha,
            lora_dropout=config.dropout,
            bias="none",
            task_type="CAUSAL_LM",
        )
        
        # 应用 LoRA
        model = get_peft_model(model, peft_config)
        log.info("LoRA adapter applied. Trainable parameters: %d", model.get_nb_trainable_parameters()[0])
        
        # 加载训练数据
        log.info("Loading training data from %s", train_data)
        dataset = load_dataset("json", data_files=str(train_data), split="train")
        
        # 预处理数据
        def preprocess_function(examples):
            # 构建 instruction-input-output 格式
            prompts = [
                f"### Instruction:\n{inst}\n\n### Input:\n{inp}\n\n### Output:\n{out}"
                for inst, inp, out in zip(
                    examples["instruction"],
                    examples["input"],
                    examples["output"],
                )
            ]
            tokenized = tokenizer(
                prompts,
                truncation=True,
                max_length=config.max_seq_length,
                padding="max_length",
                return_tensors="pt",
            )
            tokenized["labels"] = tokenized["input_ids"].clone()
            return tokenized
        
        tokenized_dataset = dataset.map(preprocess_function, batched=True)
        
        # 训练配置
        from transformers import TrainingArguments, Trainer
        
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        training_args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=config.num_epochs,
            per_device_train_batch_size=config.batch_size,
            learning_rate=config.learning_rate,
            logging_steps=10,
            save_steps=100,
            save_total_limit=2,
            fp16=device == "cuda",
        )
        
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            tokenizer=tokenizer,
        )
        
        # 开始训练
        log.info("Starting training for %d epochs", config.num_epochs)
        import time
        t0 = time.time()
        train_result = trainer.train()
        training_time = time.time() - t0
        
        # 保存 adapter
        adapter_path = output_dir / "lora_adapter"
        model.save_pretrained(str(adapter_path))
        tokenizer.save_pretrained(str(adapter_path))
        
        report.success = True
        report.adapter_path = str(adapter_path)
        report.num_samples = len(dataset)
        report.num_epochs = config.num_epochs
        report.training_time_s = training_time
        report.metrics = {
            "train_loss": train_result.metrics.get("train_loss", 0.0),
            "train_runtime": train_result.metrics.get("train_runtime", 0.0),
        }
        
        log.info("Training complete. Adapter saved to %s", adapter_path)
        log.info("Metrics: %s", report.metrics)
        
    except Exception as e:
        report.errors.append(f"PEFT training failed: {e}")
        log.exception("PEFT training error")
    
    return report


# ═══════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════

def train_lora(
    train_data: Path,
    config: LoraConfig | None = None,
) -> TrainingReport:
    """训练 LoRA adapter。

    Args:
        train_data: 训练数据路径（JSONL 格式）
        config: LoRA 训练配置

    Returns:
        TrainingReport: 训练报告
    """
    if config is None:
        config = LoraConfig()
    
    if not train_data.exists():
        report = TrainingReport()
        report.errors.append(f"Training data not found: {train_data}")
        return report
    
    log.info("Starting LoRA training with backend=%s", config.backend)
    log.info("Base model: %s", config.base_model)
    log.info("Training data: %s (%d samples)", train_data, sum(1 for _ in train_data.open()))
    
    if config.backend == "ollama":
        return _train_with_ollama(train_data, config)
    elif config.backend == "peft":
        return _train_with_peft(train_data, config)
    else:
        report = TrainingReport()
        report.errors.append(f"Unknown backend: {config.backend}")
        return report


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    if len(sys.argv) < 2:
        print("Usage: python -m yuleosh.lora.trainer <train_data.jsonl> [--backend ollama|peft]")
        sys.exit(1)
    
    train_data = Path(sys.argv[1])
    
    # 解析参数
    backend = "ollama"
    if "--backend" in sys.argv:
        idx = sys.argv.index("--backend")
        if idx + 1 < len(sys.argv):
            backend = sys.argv[idx + 1]
    
    config = LoraConfig(backend=backend)
    report = train_lora(train_data, config)
    
    print(f"\nTraining complete:")
    print(f"  Success: {report.success}")
    print(f"  Backend: {report.backend}")
    print(f"  Base model: {report.base_model}")
    print(f"  Adapter path: {report.adapter_path}")
    print(f"  Samples: {report.num_samples}")
    print(f"  Epochs: {report.num_epochs}")
    print(f"  Training time: {report.training_time_s:.1f}s")
    if report.metrics:
        print(f"  Metrics: {report.metrics}")
    if report.errors:
        print(f"  Errors: {len(report.errors)}")
        for err in report.errors:
            print(f"    - {err}")
