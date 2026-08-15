#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""资源分配器 —— acquire/release/排队/超时/过期回收。

策略：
  - acquire(platform, timeout): 找 ONLINE 且空闲设备（FIFO）→ 标记 BUSY
    → 写 allocation → 超时返回 None
  - release: 校验 job 归属 → 释放
  - expire_stale: 回收超过 TTL 的 active allocation（防任务崩溃后卡死）

不关心"怎么刷写"（那是 hardware 层），只管理资源状态机。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from .models import Device, DeviceEventType, DeviceState
from .registry import DeviceRegistry

log = logging.getLogger("yuleosh.device.allocator")


class AllocationError(Exception):
    """分配/释放异常（非法操作）。"""


class DeviceUnavailableError(AllocationError):
    """请求超时，无可用设备。"""


class Allocator:
    """设备分配器。

    Parameters
    ----------
    registry : DeviceRegistry
        设备注册表实例。
    default_ttl : int
        默认分配 TTL 秒数，防止任务崩溃后设备永久 BUSY。
    """

    def __init__(self, registry: DeviceRegistry, default_ttl: int = 1800):
        self.registry = registry
        self.default_ttl = default_ttl
        # 分配互斥锁：保证"检查可用 → 标记 BUSY → 写 allocation"原子，
        # 否则并发 acquire 会双分配同一设备（DevicePool 并行暴露）。
        self._lock = threading.Lock()

    # ── acquire ───────────────────────────────────────────────

    def acquire(
        self,
        platform: str | None = None,
        job_id: str = "adhoc",
        timeout: float = 120.0,
        ttl_seconds: int | None = None,
        preferred_device: str | None = None,
    ) -> Optional[Device]:
        """获取一台可用设备。

        Parameters
        ----------
        platform : str, optional
            只匹配指定平台（s32k/stm32/esp32）。
        job_id : str
            占用方标识（pipeline run id / 任务名）。
        timeout : float
            最长等待秒数；超时返回 None（不抛异常，调用方决定排队/失败）。
        ttl_seconds : int, optional
            分配 TTL；默认 self.default_ttl。
        preferred_device : str, optional
            优先指定设备 id 或 name。
        """
        ttl = ttl_seconds or self.default_ttl
        deadline = time.monotonic() + timeout

        while True:
            dev = self._try_acquire(
                platform=platform,
                job_id=job_id,
                ttl_seconds=ttl,
                preferred_device=preferred_device,
            )
            if dev is not None:
                return dev
            if time.monotonic() >= deadline:
                log.info("acquire timeout after %.0fs (platform=%s, job=%s)",
                         timeout, platform, job_id)
                return None
            time.sleep(1.0)

    def _try_acquire(
        self,
        platform: str | None,
        job_id: str,
        ttl_seconds: int,
        preferred_device: str | None,
    ) -> Optional[Device]:
        with self._lock:
            # 先清一次过期分配，避免占用名额
            self.expire_stale()

            if preferred_device:
                dev = self.registry.get_device(preferred_device)
                if dev is None:
                    dev = self.registry.get_device_by_name(preferred_device)
                if dev is not None and self._is_assignable(dev, platform):
                    return self._assign(dev, job_id, ttl_seconds)
                return None

            devices = self.registry.list_devices()
            candidates = [d for d in devices if self._is_assignable(d, platform)]
            if not candidates:
                return None
            candidates.sort(key=lambda d: d.name)
            return self._assign(candidates[0], job_id, ttl_seconds)

    @staticmethod
    def _is_assignable(dev: Device, platform: str | None) -> bool:
        if platform and dev.platform != platform:
            return False
        return dev.is_available()

    def _assign(self, dev: Device, job_id: str, ttl_seconds: int) -> Device:
        alloc = self.registry.create_allocation(dev.id, job_id, ttl_seconds)
        updated = self.registry.update_device_state(
            dev.id, DeviceState.BUSY, current_job=job_id,
        )
        self.registry.record_event(
            dev.id, DeviceEventType.BUSY,
            f"acquired by job {job_id} (alloc {alloc.id})",
        )
        log.info("acquired device %s for job %s (alloc %s)",
                 dev.name, job_id, alloc.id)
        return updated or dev

    # ── release ───────────────────────────────────────────────

    def release(self, device_id: str, job_id: str | None = None) -> bool:
        """释放设备。

        Parameters
        ----------
        device_id : str
            设备 id 或 name。
        job_id : str, optional
            占用方标识；提供时校验归属，防止误释放他人设备。
        """
        dev = self.registry.get_device(device_id)
        if dev is None:
            dev = self.registry.get_device_by_name(device_id)
        if dev is None:
            raise AllocationError(f"unknown device {device_id}")

        alloc = self.registry.get_allocation_for_device(dev.id)
        if alloc is None:
            # 无活跃分配：仅当设备恰好是 BUSY 且 job 匹配时回位
            if dev.state == DeviceState.BUSY:
                self.registry.update_device_state(dev.id, DeviceState.ONLINE,
                                                  current_job=None)
                return True
            log.info("release called on non-busy device %s (state=%s)",
                     dev.name, dev.state.value)
            return False

        if job_id is not None and alloc.job_id != job_id:
            raise AllocationError(
                f"device {dev.name} is held by job {alloc.job_id}, not {job_id}"
            )

        ok = self.registry.release_allocation(alloc.id, job_id=alloc.job_id)
        if not ok:
            return False
        self.registry.update_device_state(dev.id, DeviceState.ONLINE,
                                          current_job=None)
        self.registry.record_event(
            dev.id, DeviceEventType.RELEASED,
            f"released from job {alloc.job_id}",
        )
        log.info("released device %s (alloc %s)", dev.name, alloc.id)
        return True

    # ── stale expiry ──────────────────────────────────────────

    def expire_stale(self, now_iso: str | None = None) -> int:
        """回收超过 TTL 的 active 分配，设备回 ONLINE。

        Returns
        -------
        int
            回收数量。
        """
        count = 0
        for alloc in self.registry.get_active_allocations():
            if not alloc.is_expired(now_iso):
                continue
            self.registry.expire_allocation(alloc.id)
            dev = self.registry.get_device(alloc.device_id)
            if dev is not None and dev.current_job == alloc.job_id:
                self.registry.update_device_state(
                    dev.id, DeviceState.ONLINE, current_job=None
                )
            self.registry.record_event(
                alloc.device_id, DeviceEventType.RECOVERED,
                f"allocation expired (ttl={alloc.ttl_seconds}s)",
            )
            log.warning("expired stale allocation %s (device %s)",
                        alloc.id, alloc.device_id)
            count += 1
        return count
