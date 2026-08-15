#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""健康看门狗 —— 定期探测设备，掉线自动标记并释放占用。

探测由 hardware 层（HardwareDeployer / flasher）执行：通过 openocd/jlink
探测 target 是否可达。看门狗本身不关心探测细节 —— 只关心"探测成功/失败"
（依赖注入，便于 mock 单测）。

策略：
  - 探测成功 → 更新 last_seen，保持状态
  - 连续失败 1-2 次 → OFFLINE + 自动释放 active allocation（回 ONLINE 前提是恢复）
  - 连续失败 ≥3 次 → FAULT（不再进入分配池，需人工）
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from .models import Device, DeviceEventType, DeviceState
from .registry import DeviceRegistry

log = logging.getLogger("yuleosh.device.watchdog")

# 探测结果协议：Callable(device) -> bool
ProbeFn = Callable[[Device], bool]


class DeviceWatchdog:
    """设备健康看门狗。

    Parameters
    ----------
    registry : DeviceRegistry
        设备注册表。
    probe : ProbeFn
        探测函数，返回 True=在线。默认恒 True（需接入真实 flasher 探测）。
    interval : float
        探测周期秒数。
    fail_threshold : int
        连续失败多少次标记 OFFLINE（默认 2）。
    fault_threshold : int
        连续失败多少次标记 FAULT（默认 3，须 ≥ fail_threshold）。
    auto_release : bool
        掉线时是否自动释放 active allocation（默认 True）。
    """

    def __init__(
        self,
        registry: DeviceRegistry,
        probe: Optional[ProbeFn] = None,
        interval: float = 60.0,
        fail_threshold: int = 2,
        fault_threshold: int = 3,
        auto_release: bool = True,
    ):
        if fault_threshold < fail_threshold:
            raise ValueError("fault_threshold must be >= fail_threshold")
        self.registry = registry
        self.probe = probe or (lambda dev: True)
        self.interval = interval
        self.fail_threshold = fail_threshold
        self.fault_threshold = fault_threshold
        self.auto_release = auto_release
        self._consecutive_failures: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── 生命周期 ─────────────────────────────────────────────

    def start(self) -> None:
        """后台线程周期探测（守护线程，随进程退出）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="device-watchdog", daemon=True
        )
        self._thread.start()
        log.info("watchdog started (interval=%.0fs)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception as e:  # pragma: no cover - defensive
                log.warning("watchdog scan failed: %s", e)
            self._stop.wait(self.interval)

    # ── 单轮扫描（可单测直接调用） ──────────────────────────

    def scan_once(self) -> dict:
        """探测所有 ONLINE/BUSY/OFFLINE 设备，返回 {device_id: state} 变更表。

        OFFLINE 设备继续探测 —— 连续失败到 fault_threshold 才升级 FAULT；
        恢复探测成功则回 ONLINE（recovered）。
        """
        changes: dict[str, str] = {}
        for dev in self.registry.list_devices():
            if dev.state not in (DeviceState.ONLINE, DeviceState.BUSY,
                                 DeviceState.OFFLINE):
                # FAULT/UNKNOWN 不主动探测（恢复由人工/上层处理）
                continue
            ok = self._safe_probe(dev)
            if ok:
                was_failing = dev.id in self._consecutive_failures
                self._consecutive_failures.pop(dev.id, None)
                if dev.state == DeviceState.OFFLINE:
                    # 掉线设备恢复 → 回 ONLINE
                    self.registry.update_device_state(
                        dev.id, DeviceState.ONLINE, current_job=None,
                        last_seen=_now_iso(),
                    )
                    self.registry.record_event(
                        dev.id, DeviceEventType.RECOVERED,
                        "watchdog probe recovered",
                    )
                    changes[dev.id] = DeviceState.ONLINE.value
                else:
                    self.registry.update_device_state(
                        dev.id, dev.state, last_seen=_now_iso()
                    )
                if was_failing:
                    log.info("device %s probe recovered", dev.name)
            else:
                fails = self._consecutive_failures.get(dev.id, 0) + 1
                self._consecutive_failures[dev.id] = fails
                if fails >= self.fault_threshold:
                    self._mark_fault(dev)
                    changes[dev.id] = DeviceState.FAULT.value
                elif fails >= self.fail_threshold:
                    self._mark_offline(dev)
                    changes[dev.id] = DeviceState.OFFLINE.value
                # else: 继续观察
        return changes

    def _safe_probe(self, dev: Device) -> bool:
        try:
            return bool(self.probe(dev))
        except Exception as e:  # 探测异常 = 不可达
            log.debug("probe %s failed: %s", dev.name, e)
            return False

    # ── 状态迁移 ─────────────────────────────────────────────

    def _mark_offline(self, dev: Device) -> None:
        if self.auto_release:
            self._release_active_allocation(dev)
        self.registry.update_device_state(dev.id, DeviceState.OFFLINE,
                                          current_job=None)
        self.registry.record_event(
            dev.id, DeviceEventType.OFFLINE,
            f"probe failed {self.fail_threshold} consecutive times",
        )
        log.warning("device %s marked OFFLINE", dev.name)

    def _mark_fault(self, dev: Device) -> None:
        if self.auto_release:
            self._release_active_allocation(dev)
        self.registry.update_device_state(dev.id, DeviceState.FAULT,
                                          current_job=None)
        self.registry.record_event(
            dev.id, DeviceEventType.FAULT,
            f"probe failed {self.fault_threshold} consecutive times",
        )
        log.error("device %s marked FAULT — manual intervention required",
                  dev.name)

    def _release_active_allocation(self, dev: Device) -> None:
        alloc = self.registry.get_allocation_for_device(dev.id)
        if alloc is None:
            return
        self.registry.release_allocation(alloc.id, job_id=alloc.job_id)
        log.warning("auto-released allocation %s for device %s",
                    alloc.id, dev.name)

    # ── 人工恢复 ─────────────────────────────────────────────

    def recover(self, device_id: str) -> bool:
        """人工确认设备恢复：清失败计数 → ONLINE。"""
        dev = self.registry.get_device(device_id)
        if dev is None:
            return False
        self._consecutive_failures.pop(device_id, None)
        self.registry.update_device_state(device_id, DeviceState.ONLINE,
                                          current_job=None,
                                          last_seen=_now_iso())
        self.registry.record_event(device_id, DeviceEventType.RECOVERED,
                                   "manual recovery")
        log.info("device %s recovered", dev.name)
        return True


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
