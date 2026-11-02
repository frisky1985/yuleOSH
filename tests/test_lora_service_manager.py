#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
test_lora_service_manager.py — 模型服务管理器测试（P2.3）。

覆盖:
- T1: Ollama 服务管理（is_running, list_models, pull_model）
- T2: vLLM 服务管理（is_running, list_models）
- T3: 统一服务管理器（discover_services, health_check）
- T4: 模型可用性检查（ensure_model_available）
- T5: 服务信息查询（get_service_info）
- T6: 错误处理（服务不可用）
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.lora.service_manager import (
    BackendType,
    ModelServiceManager,
    OllamaServiceManager,
    ServiceInfo,
    ServiceStatus,
    VllmServiceManager,
)


class TestOllamaServiceManager:
    """T1: Ollama 服务管理。"""

    @patch("subprocess.run")
    def test_is_running_success(self, mock_run):
        """GIVEN Ollama 运行 WHEN is_running THEN True。"""
        mock_run.return_value = MagicMock(returncode=0)
        manager = OllamaServiceManager()
        assert manager.is_running() is True

    @patch("subprocess.run")
    def test_is_running_failure(self, mock_run):
        """GIVEN Ollama 未运行 WHEN is_running THEN False。"""
        mock_run.return_value = MagicMock(returncode=1)
        manager = OllamaServiceManager()
        assert manager.is_running() is False

    @patch("subprocess.run")
    def test_list_models(self, mock_run):
        """GIVEN Ollama 有模型 WHEN list_models THEN 返回模型列表。"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NAME\nqwen2.5-coder:14b\ndeepseek-r1:7b\n",
        )
        manager = OllamaServiceManager()
        models = manager.list_models()
        assert len(models) == 2
        assert "qwen2.5-coder:14b" in models
        assert "deepseek-r1:7b" in models

    @patch("subprocess.run")
    def test_list_models_empty(self, mock_run):
        """GIVEN Ollama 无模型 WHEN list_models THEN 返回空列表。"""
        mock_run.return_value = MagicMock(returncode=0, stdout="NAME\n")
        manager = OllamaServiceManager()
        models = manager.list_models()
        assert models == []

    @patch("subprocess.run")
    def test_pull_model_success(self, mock_run):
        """GIVEN 模型不存在 WHEN pull_model THEN 成功拉取。"""
        mock_run.return_value = MagicMock(returncode=0)
        manager = OllamaServiceManager()
        result = manager.pull_model("qwen2.5-coder:14b")
        assert result is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_pull_model_failure(self, mock_run):
        """GIVEN 拉取失败 WHEN pull_model THEN 返回 False。"""
        mock_run.return_value = MagicMock(returncode=1)
        manager = OllamaServiceManager()
        result = manager.pull_model("nonexistent-model")
        assert result is False

    def test_get_service_info(self):
        """GIVEN Ollama 服务 WHEN get_service_info THEN 返回 ServiceInfo。"""
        manager = OllamaServiceManager()
        with patch.object(manager, "is_running", return_value=True):
            with patch.object(manager, "list_models", return_value=["model1"]):
                info = manager.get_service_info()
                assert info.backend == BackendType.OLLAMA
                assert info.status == ServiceStatus.RUNNING
                assert "model1" in info.loaded_models


class TestVllmServiceManager:
    """T2: vLLM 服务管理。"""

    @patch("urllib.request.urlopen")
    def test_is_running_success(self, mock_urlopen):
        """GIVEN vLLM 运行 WHEN is_running THEN True。"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=None)
        mock_urlopen.return_value = mock_resp
        
        manager = VllmServiceManager()
        assert manager.is_running() is True

    @patch("urllib.request.urlopen")
    def test_is_running_failure(self, mock_urlopen):
        """GIVEN vLLM 未运行 WHEN is_running THEN False。"""
        mock_urlopen.side_effect = Exception("Connection refused")
        manager = VllmServiceManager()
        assert manager.is_running() is False

    @patch("urllib.request.urlopen")
    def test_list_models(self, mock_urlopen):
        """GIVEN vLLM 有模型 WHEN list_models THEN 返回模型列表。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": [{"id": "model1"}, {"id": "model2"}]
        }).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=None)
        mock_urlopen.return_value = mock_resp
        
        manager = VllmServiceManager()
        models = manager.list_models()
        assert len(models) == 2
        assert "model1" in models
        assert "model2" in models

    def test_get_service_info(self):
        """GIVEN vLLM 服务 WHEN get_service_info THEN 返回 ServiceInfo。"""
        manager = VllmServiceManager()
        with patch.object(manager, "is_running", return_value=True):
            with patch.object(manager, "list_models", return_value=["model1"]):
                info = manager.get_service_info()
                assert info.backend == BackendType.VLLM
                assert info.status == ServiceStatus.RUNNING


class TestModelServiceManager:
    """T3: 统一服务管理器。"""

    def test_discover_services_both_running(self):
        """GIVEN 两个服务都运行 WHEN discover_services THEN 报告成功。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "is_running", return_value=True):
            with patch.object(manager.vllm, "is_running", return_value=True):
                report = manager.discover_services()
                assert report.success is True
                assert report.services_discovered == 2
                assert report.healthy_services == 2

    def test_discover_services_one_running(self):
        """GIVEN 一个服务运行 WHEN discover_services THEN 部分成功。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "is_running", return_value=True):
            with patch.object(manager.vllm, "is_running", return_value=False):
                report = manager.discover_services()
                assert report.success is True
                assert report.services_discovered == 1
                assert report.healthy_services == 1

    def test_discover_services_none_running(self):
        """GIVEN 无服务运行 WHEN discover_services THEN 报告失败。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "is_running", return_value=False):
            with patch.object(manager.vllm, "is_running", return_value=False):
                report = manager.discover_services()
                assert report.success is False
                assert report.services_discovered == 0

    def test_health_check(self):
        """GIVEN 服务管理器 WHEN health_check THEN 返回健康状态。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "is_running", return_value=True):
            with patch.object(manager.vllm, "is_running", return_value=False):
                health = manager.health_check()
                assert health["ollama"] is True
                assert health["vllm"] is False

    def test_list_all_models(self):
        """GIVEN 服务管理器 WHEN list_all_models THEN 返回所有模型。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "list_models", return_value=["ollama_model"]):
            with patch.object(manager.vllm, "list_models", return_value=["vllm_model"]):
                models = manager.list_all_models()
                assert "ollama" in models
                assert "vllm" in models
                assert "ollama_model" in models["ollama"]
                assert "vllm_model" in models["vllm"]


class TestModelAvailability:
    """T4: 模型可用性检查。"""

    def test_ensure_model_available_exists(self):
        """GIVEN 模型存在 WHEN ensure_model_available THEN True。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "list_models", return_value=["qwen2.5-coder:14b"]):
            result = manager.ensure_model_available("qwen2.5-coder:14b", BackendType.OLLAMA)
            assert result is True

    def test_ensure_model_available_not_exists_pull_success(self):
        """GIVEN 模型不存在 WHEN ensure_model_available THEN 拉取成功。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "list_models", return_value=[]):
            with patch.object(manager.ollama, "pull_model", return_value=True) as mock_pull:
                result = manager.ensure_model_available("new-model", BackendType.OLLAMA)
                assert result is True
                mock_pull.assert_called_once_with("new-model")

    def test_ensure_model_available_not_exists_pull_failure(self):
        """GIVEN 模型不存在 WHEN ensure_model_available THEN 拉取失败。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "list_models", return_value=[]):
            with patch.object(manager.ollama, "pull_model", return_value=False):
                result = manager.ensure_model_available("nonexistent", BackendType.OLLAMA)
                assert result is False

    def test_ensure_model_available_vllm(self):
        """GIVEN vLLM 后端 WHEN ensure_model_available THEN 检查模型列表。"""
        manager = ModelServiceManager()
        with patch.object(manager.vllm, "list_models", return_value=["model1"]):
            result = manager.ensure_model_available("model1", BackendType.VLLM)
            assert result is True


class TestServiceInfo:
    """T5: 服务信息查询。"""

    def test_get_service_info_ollama(self):
        """GIVEN Ollama 后端 WHEN get_service_info THEN 返回正确信息。"""
        manager = ModelServiceManager()
        with patch.object(manager.ollama, "is_running", return_value=True):
            with patch.object(manager.ollama, "list_models", return_value=["model1"]):
                info = manager.get_service_info(BackendType.OLLAMA)
                assert info.backend == BackendType.OLLAMA
                assert info.status == ServiceStatus.RUNNING
                assert info.host == "http://127.0.0.1:11434"

    def test_get_service_info_vllm(self):
        """GIVEN vLLM 后端 WHEN get_service_info THEN 返回正确信息。"""
        manager = ModelServiceManager()
        with patch.object(manager.vllm, "is_running", return_value=False):
            info = manager.get_service_info(BackendType.VLLM)
            assert info.backend == BackendType.VLLM
            assert info.status == ServiceStatus.STOPPED
            assert info.host == "http://127.0.0.1:8000"


class TestErrorHandling:
    """T6: 错误处理。"""

    def test_ollama_service_unreachable(self):
        """GIVEN Ollama 不可达 WHEN 操作 THEN 优雅降级。"""
        manager = OllamaServiceManager()
        with patch("subprocess.run", side_effect=Exception("Connection refused")):
            assert manager.is_running() is False
            assert manager.list_models() == []

    def test_vllm_service_unreachable(self):
        """GIVEN vLLM 不可达 WHEN 操作 THEN 优雅降级。"""
        manager = VllmServiceManager()
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            assert manager.is_running() is False
            assert manager.list_models() == []

    def test_unknown_backend(self):
        """GIVEN 未知后端 WHEN get_service_info THEN 抛出 ValueError。"""
        manager = ModelServiceManager()
        with pytest.raises(ValueError, match="Unknown backend"):
            manager.get_service_info("unknown")
