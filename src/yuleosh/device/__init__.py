#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""设备管理层（Device Management Layer）。

平台级资源层：管理 HIL 目标板/测试设备池 —— 注册、状态、锁、调度、
健康看门狗、并行执行。位于单板操作层（hardware.HardwareDeployer）之上，
pipeline hil-test step 之下。

用法::

    from yuleosh.device import DeviceManager

    mgr = DeviceManager(db_path="~/.yuleosh/device.db")
    dev = mgr.allocator.acquire(platform="s32k", job_id="run-123")
    try:
        ...  # 通过 hardware.HardwareDeployer 刷写/测试
    finally:
        mgr.allocator.release(dev.id, job_id="run-123")
"""

from __future__ import annotations

from .models import (
    Allocation,
    AllocationStatus,
    Device,
    DeviceEvent,
    DeviceEventType,
    DeviceState,
)
from .registry import DeviceRegistry
from .allocator import Allocator, AllocationError, DeviceUnavailableError

__all__ = [
    "DeviceManager",
    "DeviceRegistry",
    "Allocator",
    "AllocationError",
    "DeviceUnavailableError",
    "Device",
    "DeviceState",
    "Allocation",
    "AllocationStatus",
    "DeviceEvent",
    "DeviceEventType",
]


class DeviceManager:
    """设备管理层门面。

    组合 Registry + Allocator（watchdog/pool 由调用方按需装配），
    提供单个入口完成设备池生命周期管理。
    """

    def __init__(self, db_path=None, default_ttl: int = 1800):
        self.registry = DeviceRegistry(db_path=db_path)
        self.allocator = Allocator(self.registry, default_ttl=default_ttl)

    # ── 便捷转发（窄接口） ──────────────────────────────────

    def list_devices(self) -> list[Device]:
        return self.registry.list_devices()

    def add_device(self, *args, **kwargs) -> Device:
        return self.registry.add_device(*args, **kwargs)

    def remove_device(self, device_id: str) -> bool:
        return self.registry.remove_device(device_id)

    def get_device(self, device_id: str) -> Device | None:
        return self.registry.get_device(device_id)

    def check(self, device_id: str) -> Device | None:
        """单设备健康检查（未来接 watchdog 探测逻辑）。"""
        return self.registry.get_device(device_id)

    def list_events(self, device_id: str | None = None, limit: int = 100):
        return self.registry.list_events(device_id=device_id, limit=limit)
