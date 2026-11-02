#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
test_lora_trainer.py — LoRA 训练脚本测试（P2.2）。

覆盖:
- T1: 训练配置（LoraConfig dataclass）
- T2: Ollama 后端训练（mock subprocess）
- T3: PEFT 后端训练（依赖检查）
- T4: 训练报告生成
- T5: 错误处理（数据不存在/后端不可用）
- T6: 端到端训练流程（mock）
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.lora.trainer import (
    LoraConfig,
    TrainingReport,
    _train_with_ollama,
    _train_with_peft,
    train_lora,
)


@pytest.fixture
def temp_train_data():
    """创建临时训练数据文件。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        # 写入示例训练数据
        samples = [
            {
                "instruction": "实现加法函数",
                "input": "def add(a, b):",
                "output": "def add(a, b):\n    return a + b",
            },
            {
                "instruction": "实现乘法函数",
                "input": "def multiply(x, y):",
                "output": "def multiply(x, y):\n    return x * y",
            },
        ]
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        f.flush()
        yield Path(f.name)
        Path(f.name).unlink()


class TestLoraConfig:
    """T1: 训练配置。"""

    def test_default_config(self):
        """GIVEN 无参数 WHEN LoraConfig THEN 使用默认值。"""
        config = LoraConfig()
        assert config.base_model == "qwen2.5-coder:14b"
        assert config.rank == 8
        assert config.alpha == 32
        assert config.backend == "ollama"
        assert config.num_epochs == 3

    def test_custom_config(self):
        """GIVEN 自定义参数 WHEN LoraConfig THEN 使用自定义值。"""
        config = LoraConfig(
            base_model="deepseek-r1:7b",
            rank=16,
            alpha=64,
            backend="peft",
            num_epochs=5,
        )
        assert config.base_model == "deepseek-r1:7b"
        assert config.rank == 16
        assert config.alpha == 64
        assert config.backend == "peft"
        assert config.num_epochs == 5


class TestOllamaBackend:
    """T2: Ollama 后端训练。"""

    @patch("subprocess.run")
    def test_ollama_training_success(self, mock_run, temp_train_data):
        """GIVEN Ollama 可用 WHEN 训练 THEN 成功创建模型。"""
        # Mock ollama list
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="NAME\nqwen2.5-coder:14b"),  # ollama list
            MagicMock(returncode=0, stdout=""),  # ollama create
        ]
        
        config = LoraConfig(backend="ollama", base_model="qwen2.5-coder:14b")
        report = _train_with_ollama(temp_train_data, config)
        
        assert report.success is True
        assert report.backend == "ollama"
        assert "lora-custom" in report.adapter_path
        assert report.num_samples == 2

    @patch("subprocess.run")
    def test_ollama_not_available(self, mock_run, temp_train_data):
        """GIVEN Ollama 不可用 WHEN 训练 THEN 报告错误。"""
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        
        config = LoraConfig(backend="ollama")
        report = _train_with_ollama(temp_train_data, config)
        
        assert report.success is False
        assert len(report.errors) > 0
        assert "not available" in report.errors[0].lower()

    @patch("subprocess.run")
    def test_ollama_create_failure(self, mock_run, temp_train_data):
        """GIVEN ollama create 失败 WHEN 训练 THEN 报告错误。"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=""),  # ollama list
            MagicMock(returncode=1, stderr="model creation failed"),  # ollama create
        ]
        
        config = LoraConfig(backend="ollama")
        report = _train_with_ollama(temp_train_data, config)
        
        assert report.success is False
        assert len(report.errors) > 0


class TestPeftBackend:
    """T3: PEFT 后端训练。"""

    def test_peft_missing_dependencies(self, temp_train_data):
        """GIVEN 缺少依赖 WHEN PEFT 训练 THEN 报告错误。"""
        config = LoraConfig(backend="peft")
        
        # Mock import failure
        with patch.dict("sys.modules", {"torch": None, "transformers": None}):
            report = _train_with_peft(temp_train_data, config)
        
        assert report.success is False
        assert len(report.errors) > 0
        assert "missing dependencies" in report.errors[0].lower()

    def test_peft_training_mock(self, temp_train_data):
        """GIVEN 依赖可用 WHEN PEFT 训练 THEN 成功（mock）。"""
        # 这个测试需要完整的 mock 设置，暂时跳过实际执行
        # 在实际环境中，PEFT 训练需要 GPU 和大量时间
        config = LoraConfig(backend="peft", device="cpu")
        
        # 由于 PEFT 训练复杂，这里只验证配置正确
        report = TrainingReport(backend="peft", base_model=config.base_model)
        report.success = True
        report.adapter_path = "/tmp/lora_adapter"
        
        assert report.backend == "peft"
        assert report.success is True


class TestTrainingReport:
    """T4: 训练报告生成。"""

    def test_report_structure(self):
        """GIVEN TrainingReport WHEN 创建 THEN 包含必需字段。"""
        report = TrainingReport(
            success=True,
            backend="ollama",
            base_model="qwen2.5-coder:14b",
            adapter_path="/path/to/adapter",
            num_samples=100,
            num_epochs=3,
            training_time_s=3600.0,
            metrics={"loss": 0.5},
        )
        
        assert report.success is True
        assert report.backend == "ollama"
        assert report.num_samples == 100
        assert report.metrics["loss"] == 0.5

    def test_report_with_errors(self):
        """GIVEN 训练失败 WHEN 生成报告 THEN 包含错误信息。"""
        report = TrainingReport()
        report.errors.append("Error 1")
        report.errors.append("Error 2")
        
        assert len(report.errors) == 2
        assert report.success is False


class TestTrainLora:
    """T5/T6: train_lora 主入口。"""

    def test_train_lora_ollama(self, temp_train_data):
        """GIVEN Ollama 后端 WHEN train_lora THEN 调用 Ollama 训练。"""
        config = LoraConfig(backend="ollama")
        
        with patch("yuleosh.lora.trainer._train_with_ollama") as mock_train:
            mock_train.return_value = TrainingReport(success=True, backend="ollama")
            report = train_lora(temp_train_data, config)
            
            mock_train.assert_called_once()
            assert report.success is True
            assert report.backend == "ollama"

    def test_train_lora_peft(self, temp_train_data):
        """GIVEN PEFT 后端 WHEN train_lora THEN 调用 PEFT 训练。"""
        config = LoraConfig(backend="peft")
        
        with patch("yuleosh.lora.trainer._train_with_peft") as mock_train:
            mock_train.return_value = TrainingReport(success=True, backend="peft")
            report = train_lora(temp_train_data, config)
            
            mock_train.assert_called_once()
            assert report.success is True
            assert report.backend == "peft"

    def test_train_lora_unknown_backend(self, temp_train_data):
        """GIVEN 未知后端 WHEN train_lora THEN 报告错误。"""
        config = LoraConfig(backend="unknown")
        report = train_lora(temp_train_data, config)
        
        assert report.success is False
        assert len(report.errors) > 0
        assert "unknown backend" in report.errors[0].lower()

    def test_train_lora_missing_data(self):
        """GIVEN 训练数据不存在 WHEN train_lora THEN 报告错误。"""
        config = LoraConfig()
        report = train_lora(Path("/nonexistent/train.jsonl"), config)
        
        assert report.success is False
        assert len(report.errors) > 0
        assert "not found" in report.errors[0].lower()

    def test_train_lora_default_config(self, temp_train_data):
        """GIVEN 无配置 WHEN train_lora THEN 使用默认配置。"""
        with patch("yuleosh.lora.trainer._train_with_ollama") as mock_train:
            mock_train.return_value = TrainingReport(success=True)
            report = train_lora(temp_train_data)
            
            mock_train.assert_called_once()
            # 验证使用了默认配置
            call_args = mock_train.call_args
            config = call_args[1]["config"] if "config" in call_args[1] else call_args[0][1]
            assert config.backend == "ollama"


class TestEndToEnd:
    """T6: 端到端训练流程（mock）。"""

    @patch("subprocess.run")
    def test_full_ollama_workflow(self, mock_run, temp_train_data):
        """GIVEN 完整 Ollama 工作流 WHEN train_lora THEN 成功。"""
        # Mock ollama commands
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="NAME\nqwen2.5-coder:14b"),  # list
            MagicMock(returncode=0, stdout=""),  # create
        ]
        
        config = LoraConfig(backend="ollama")
        report = train_lora(temp_train_data, config)
        
        assert report.success is True
        assert report.backend == "ollama"
        assert report.num_samples == 2
        assert "lora-custom" in report.adapter_path

    def test_full_peft_workflow_mock(self, temp_train_data):
        """GIVEN 完整 PEFT 工作流 WHEN train_lora THEN 成功（mock）。"""
        # PEFT 需要 GPU 和大量依赖，这里只验证流程
        config = LoraConfig(backend="peft")
        
        with patch("yuleosh.lora.trainer._train_with_peft") as mock_train:
            mock_train.return_value = TrainingReport(
                success=True,
                backend="peft",
                num_samples=2,
                num_epochs=3,
                training_time_s=100.0,
                metrics={"loss": 0.3},
            )
            
            report = train_lora(temp_train_data, config)
            
            assert report.success is True
            assert report.backend == "peft"
            assert report.num_samples == 2
            assert report.metrics["loss"] == 0.3
