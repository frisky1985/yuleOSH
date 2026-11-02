#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
模型服务管理器（P2.3）。

管理 Ollama 和 vLLM 服务的部署、健康检查、模型加载/卸载。

设计要点:
- 服务发现: 自动检测本地 Ollama/vLLM 服务
- 健康检查: 定期监控服务可达性和模型可用性
- 模型管理: 加载/卸载模型，支持热切换
- 资源监控: GPU/CPU 内存使用率

使用场景:
- 自动化部署 Ollama/vLLM 服务
- 运行时切换基础模型或 LoRA adapter
- 监控服务健康状态，自动降级
- 优化资源使用（内存/GPU）
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

log = logging.getLogger("lora.service_manager")


# ═══════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════

class ServiceStatus(Enum):
    """服务状态。"""
    RUNNING = "running"
    STOPPED = "stopped"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class BackendType(Enum):
    """后端类型。"""
    OLLAMA = "ollama"
    VLLM = "vllm"


@dataclass
class ServiceInfo:
    """服务信息。"""
    backend: BackendType
    host: str
    port: int
    status: ServiceStatus = ServiceStatus.UNKNOWN
    loaded_models: list[str] = field(default_factory=list)
    available_models: list[str] = field(default_factory=list)
    gpu_memory_used_mb: int = 0
    gpu_memory_total_mb: int = 0
    uptime_s: float = 0.0
    last_check: float = 0.0


@dataclass
class ServiceManagerReport:
    """服务管理报告。"""
    success: bool = False
    services_discovered: int = 0
    healthy_services: int = 0
    errors: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Ollama 服务管理
# ═══════════════════════════════════════════════════════════════════════

class OllamaServiceManager:
    """Ollama 服务管理器。"""

    def __init__(self, host: str | None = None):
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self._start_time: Optional[float] = None

    def is_running(self) -> bool:
        """检查 Ollama 服务是否运行。"""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=5,
                # 2026-11-02: self.host 必须穿透到子进程 — ollama CLI 读
                # 进程环境 OLLAMA_HOST, 不传则永远探测本机 127.0.0.1,
                # host="http://gpu-box:11434" 的管理器会误报本地状态。
                env={**os.environ, "OLLAMA_HOST": self.host},
            )
            return result.returncode == 0
        except Exception as e:
            log.debug("Ollama service check failed: %s", e)
            return False

    def list_models(self) -> list[str]:
        """列出已加载的模型。"""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "OLLAMA_HOST": self.host},
            )
            if result.returncode != 0:
                return []
            
            # 解析输出（NAME 列）
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return []
            
            models = []
            for line in lines[1:]:  # 跳过表头
                parts = line.split()
                if parts:
                    models.append(parts[0])
            return models
        except Exception as e:
            log.warning("Failed to list Ollama models: %s", e)
            return []

    def pull_model(self, model_name: str) -> bool:
        """拉取模型（如果不存在）。"""
        try:
            log.info("Pulling Ollama model: %s", model_name)
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=True,
                text=True,
                timeout=600,  # 10 分钟超时
                env={**os.environ, "OLLAMA_HOST": self.host},
            )
            return result.returncode == 0
        except Exception as e:
            log.error("Failed to pull model %s: %s", model_name, e)
            return False

    def unload_model(self, model_name: str) -> bool:
        """卸载模型（释放内存）。"""
        # Ollama 没有直接的 unload 命令，但可以通过重启服务实现
        # 这里简化为返回 True（实际生产中需要更复杂的逻辑）
        log.info("Unload model requested: %s (no-op for Ollama)", model_name)
        return True

    def get_service_info(self) -> ServiceInfo:
        """获取服务信息。"""
        status = ServiceStatus.RUNNING if self.is_running() else ServiceStatus.STOPPED
        models = self.list_models()
        
        uptime = 0.0
        if self._start_time and status == ServiceStatus.RUNNING:
            uptime = time.time() - self._start_time
        
        return ServiceInfo(
            backend=BackendType.OLLAMA,
            host=self.host,
            port=11434,
            status=status,
            loaded_models=models,
            available_models=models,  # Ollama 的 loaded 和 available 是同一个
            uptime_s=uptime,
            last_check=time.time(),
        )


# ═══════════════════════════════════════════════════════════════════════
# vLLM 服务管理
# ═══════════════════════════════════════════════════════════════════════

class VllmServiceManager:
    """vLLM 服务管理器。"""

    def __init__(self, host: str | None = None):
        self.host = (host or os.environ.get("VLLM_HOST", "http://127.0.0.1:8000")).rstrip("/")
        self._start_time: Optional[float] = None

    def is_running(self) -> bool:
        """检查 vLLM 服务是否运行。"""
        try:
            import urllib.request
            url = f"{self.host}/v1/models"
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            log.debug("vLLM service check failed: %s", e)
            return False

    def list_models(self) -> list[str]:
        """列出已加载的模型。"""
        try:
            import urllib.request
            import json
            url = f"{self.host}/v1/models"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["id"] for m in data.get("data", [])]
        except Exception as e:
            log.warning("Failed to list vLLM models: %s", e)
            return []

    def load_model(self, model_name: str, lora_adapter: str | None = None) -> bool:
        """加载模型（vLLM 需要重启服务，这里只记录意图）。"""
        # vLLM 的模型加载需要重启服务，实际生产中需要通过 API 或命令行
        log.info("Load model requested: %s (lora=%s)", model_name, lora_adapter)
        return True

    def unload_model(self, model_name: str) -> bool:
        """卸载模型。"""
        log.info("Unload model requested: %s", model_name)
        return True

    def get_service_info(self) -> ServiceInfo:
        """获取服务信息。"""
        status = ServiceStatus.RUNNING if self.is_running() else ServiceStatus.STOPPED
        models = self.list_models()
        
        uptime = 0.0
        if self._start_time and status == ServiceStatus.RUNNING:
            uptime = time.time() - self._start_time
        
        return ServiceInfo(
            backend=BackendType.VLLM,
            host=self.host,
            port=8000,
            status=status,
            loaded_models=models,
            available_models=models,
            uptime_s=uptime,
            last_check=time.time(),
        )


# ═══════════════════════════════════════════════════════════════════════
# 统一服务管理器
# ═══════════════════════════════════════════════════════════════════════

class ModelServiceManager:
    """统一模型服务管理器。"""

    def __init__(
        self,
        ollama_host: str | None = None,
        vllm_host: str | None = None,
    ):
        self.ollama = OllamaServiceManager(host=ollama_host)
        self.vllm = VllmServiceManager(host=vllm_host)

    def discover_services(self) -> ServiceManagerReport:
        """发现并检查所有服务。"""
        report = ServiceManagerReport()
        
        # 检查 Ollama
        if self.ollama.is_running():
            report.services_discovered += 1
            report.healthy_services += 1
        else:
            report.errors.append("Ollama service not running")
        
        # 检查 vLLM
        if self.vllm.is_running():
            report.services_discovered += 1
            report.healthy_services += 1
        else:
            report.errors.append("vLLM service not running")
        
        report.success = report.healthy_services > 0
        return report

    def get_service_info(self, backend: BackendType) -> ServiceInfo:
        """获取指定后端的服务信息。"""
        if backend == BackendType.OLLAMA:
            return self.ollama.get_service_info()
        elif backend == BackendType.VLLM:
            return self.vllm.get_service_info()
        else:
            raise ValueError(f"Unknown backend: {backend}")

    def list_all_models(self) -> dict[str, list[str]]:
        """列出所有可用模型（按后端分组）。"""
        return {
            "ollama": self.ollama.list_models(),
            "vllm": self.vllm.list_models(),
        }

    def health_check(self) -> dict[str, bool]:
        """健康检查所有服务。"""
        return {
            "ollama": self.ollama.is_running(),
            "vllm": self.vllm.is_running(),
        }

    def ensure_model_available(
        self,
        model_name: str,
        backend: BackendType = BackendType.OLLAMA,
    ) -> bool:
        """确保模型可用（如果不存在则拉取）。"""
        if backend == BackendType.OLLAMA:
            models = self.ollama.list_models()
            if model_name not in models:
                log.info("Model %s not found, pulling...", model_name)
                return self.ollama.pull_model(model_name)
            return True
        elif backend == BackendType.VLLM:
            models = self.vllm.list_models()
            return model_name in models
        else:
            return False


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    manager = ModelServiceManager()
    
    # 发现服务
    report = manager.discover_services()
    print(f"\nService Discovery:")
    print(f"  Services discovered: {report.services_discovered}")
    print(f"  Healthy services: {report.healthy_services}")
    if report.errors:
        print(f"  Errors:")
        for err in report.errors:
            print(f"    - {err}")
    
    # 列出所有模型
    models = manager.list_all_models()
    print(f"\nAvailable Models:")
    for backend, model_list in models.items():
        print(f"  {backend}: {len(model_list)} models")
        for m in model_list[:5]:  # 只显示前 5 个
            print(f"    - {m}")
        if len(model_list) > 5:
            print(f"    ... and {len(model_list) - 5} more")
    
    # 健康检查
    health = manager.health_check()
    print(f"\nHealth Check:")
    for backend, is_healthy in health.items():
        status = "✓" if is_healthy else "✗"
        print(f"  {backend}: {status}")
