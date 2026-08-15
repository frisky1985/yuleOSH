#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""设备管理层数据模型。

Device / Allocation / DeviceEvent 三类核心模型，以及状态枚举。
纯数据定义，不依赖存储/业务逻辑 —— 可独立单测。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DeviceState(str, enum.Enum):
    """设备生命周期状态。"""

    UNKNOWN = "unknown"   # 未探测
    ONLINE = "online"     # 在线可用
    BUSY = "busy"         # 被任务占用
    OFFLINE = "offline"   # 掉线
    FAULT = "fault"       # 多次探测失败，需人工介入


class AllocationStatus(str, enum.Enum):
    """分配记录状态。"""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class DeviceEventType(str, enum.Enum):
    """设备事件类型（审计/看板用）。"""

    REGISTERED = "registered"
    REMOVED = "removed"
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    RELEASED = "released"
    FAULT = "fault"
    RECOVERED = "recovered"


@dataclass
class Device:
    """一块 HIL 目标板。"""

    id: str
    name: str
    platform: str                # "s32k" / "stm32" / "esp32"
    flasher: str                 # "openocd" / "jlink" / "esptool"
    flasher_config: dict = field(default_factory=dict)
    port: Optional[str] = None   # 串口路径，如 /dev/ttyUSB0
    serial: Optional[str] = None  # USB 序列号（自动发现标识）
    state: DeviceState = DeviceState.UNKNOWN
    current_job: Optional[str] = None
    firmware_version: Optional[str] = None
    last_seen: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "flasher": self.flasher,
            "flasher_config": self.flasher_config,
            "port": self.port,
            "serial": self.serial,
            "state": self.state.value,
            "current_job": self.current_job,
            "firmware_version": self.firmware_version,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Device":
        state = d.get("state", DeviceState.UNKNOWN.value)
        try:
            state_enum = DeviceState(state)
        except ValueError:
            state_enum = DeviceState.UNKNOWN
        return cls(
            id=d["id"],
            name=d.get("name", d["id"]),
            platform=d.get("platform", ""),
            flasher=d.get("flasher", "openocd"),
            flasher_config=d.get("flasher_config", {}) or {},
            port=d.get("port"),
            serial=d.get("serial"),
            state=state_enum,
            current_job=d.get("current_job"),
            firmware_version=d.get("firmware_version"),
            last_seen=d.get("last_seen"),
            created_at=d.get("created_at", _now_iso()),
            updated_at=d.get("updated_at", _now_iso()),
        )

    def is_available(self) -> bool:
        """可分配 = 在线且未被占用。"""
        return self.state == DeviceState.ONLINE and not self.current_job


@dataclass
class Allocation:
    """一次设备占用记录。"""

    id: str
    device_id: str
    job_id: str
    acquired_at: str = field(default_factory=_now_iso)
    released_at: Optional[str] = None
    ttl_seconds: int = 1800
    status: AllocationStatus = AllocationStatus.ACTIVE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "job_id": self.job_id,
            "acquired_at": self.acquired_at,
            "released_at": self.released_at,
            "ttl_seconds": self.ttl_seconds,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Allocation":
        status = d.get("status", AllocationStatus.ACTIVE.value)
        try:
            status_enum = AllocationStatus(status)
        except ValueError:
            status_enum = AllocationStatus.ACTIVE
        return cls(
            id=d["id"],
            device_id=d["device_id"],
            job_id=d.get("job_id", ""),
            acquired_at=d.get("acquired_at", _now_iso()),
            released_at=d.get("released_at"),
            ttl_seconds=int(d.get("ttl_seconds", 1800)),
            status=status_enum,
        )

    def is_expired(self, now_iso: str | None = None) -> bool:
        """是否超过 TTL（防任务崩溃后板子卡死）。"""
        if self.status != AllocationStatus.ACTIVE:
            return False
        from datetime import datetime as _dt
        now = _dt.fromisoformat(now_iso) if now_iso else _dt.now()
        acquired = _dt.fromisoformat(self.acquired_at)
        return (now - acquired).total_seconds() > self.ttl_seconds


@dataclass
class DeviceEvent:
    """设备事件日志（审计 / 看板时间线）。"""

    id: str
    device_id: str
    event_type: DeviceEventType
    detail: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "event_type": self.event_type.value,
            "detail": self.detail,
            "created_at": self.created_at,
        }
