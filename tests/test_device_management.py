# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""设备管理层单测：registry / allocator / watchdog / pool。

全部用临时 SQLite DB + mock 探测函数，无需真实硬件。
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from yuleosh.device import (
    AllocationStatus,
    DeviceManager,
    DeviceState,
    DeviceUnavailableError,
)
from yuleosh.device.allocator import AllocationError, Allocator
from yuleosh.device.registry import DeviceRegistry
from yuleosh.device.watchdog import DeviceWatchdog


@pytest.fixture
def registry(tmp_path: Path) -> DeviceRegistry:
    return DeviceRegistry(db_path=tmp_path / "device-test.db")


@pytest.fixture
def manager(tmp_path: Path) -> DeviceManager:
    return DeviceManager(db_path=tmp_path / "device-mgr-test.db")


# ══════════════════════════════════════════════════════════════
# registry
# ══════════════════════════════════════════════════════════════

class TestRegistry:
    def test_add_and_get(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k",
                                  flasher="jlink", port="/dev/ttyUSB0")
        got = registry.get_device(dev.id)
        assert got is not None
        assert got.name == "lab-01"
        assert got.platform == "s32k"
        assert got.state == DeviceState.UNKNOWN

    def test_add_duplicate_name_allowed_unique_id(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        d2 = registry.add_device(name="lab-01", platform="stm32")
        assert d1.id != d2.id
        assert len(registry.list_devices()) == 2

    def test_remove_device_with_active_allocation_refused(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        registry.create_allocation(dev.id, "job-1")
        assert registry.remove_device(dev.id) is False
        assert registry.get_device(dev.id) is not None

    def test_remove_device_ok(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        assert registry.remove_device(dev.id) is True
        assert registry.get_device(dev.id) is None

    def test_state_update(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        assert registry.get_device(dev.id).state == DeviceState.ONLINE

    def test_allocation_lifecycle(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        alloc = registry.create_allocation(dev.id, "job-1", ttl_seconds=100)
        assert registry.get_allocation_for_device(dev.id) is not None
        assert registry.release_allocation(alloc.id, job_id="job-1") is True
        assert registry.get_allocation_for_device(dev.id) is None
        got = registry.get_allocation(alloc.id)
        assert got.status == AllocationStatus.RELEASED

    def test_allocation_wrong_job_refused(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        alloc = registry.create_allocation(dev.id, "job-1")
        assert registry.release_allocation(alloc.id, job_id="job-2") is False

    def test_events_recorded(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        events = registry.list_events(device_id=dev.id)
        assert any(e.event_type.value == "registered" for e in events)

    def test_persistence_across_instances(self, tmp_path):
        db = tmp_path / "persist.db"
        r1 = DeviceRegistry(db_path=db)
        dev = r1.add_device(name="lab-01", platform="s32k")
        r2 = DeviceRegistry(db_path=db)
        got = r2.get_device(dev.id)
        assert got is not None
        assert got.name == "lab-01"


# ══════════════════════════════════════════════════════════════
# allocator
# ══════════════════════════════════════════════════════════════

class TestAllocator:
    def test_acquire_and_release(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        got = alloc.acquire(platform="s32k", job_id="job-1", timeout=2)
        assert got is not None
        assert got.state == DeviceState.BUSY
        assert got.current_job == "job-1"
        assert registry.get_allocation_for_device(dev.id) is not None

        assert alloc.release(dev.id, job_id="job-1") is True
        assert registry.get_device(dev.id).state == DeviceState.ONLINE
        assert registry.get_device(dev.id).current_job is None

    def test_acquire_platform_filter(self, registry):
        d1 = registry.add_device(name="s32k-01", platform="s32k")
        d2 = registry.add_device(name="stm32-01", platform="stm32")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        registry.update_device_state(d2.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        got = alloc.acquire(platform="s32k", job_id="j", timeout=2)
        assert got is not None
        assert got.id == d1.id

    def test_acquire_busy_device_not_reassigned(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        first = alloc.acquire(platform="s32k", job_id="j1", timeout=2)
        assert first is not None
        second = alloc.acquire(platform="s32k", job_id="j2", timeout=1)
        assert second is None  # 唯一设备已被占用

    def test_acquire_timeout_returns_none(self, registry):
        registry.add_device(name="lab-01", platform="s32k")  # UNKNOWN，不可分配
        alloc = Allocator(registry)
        got = alloc.acquire(platform="s32k", job_id="j", timeout=1)
        assert got is None

    def test_release_wrong_job_raises(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        alloc.acquire(platform="s32k", job_id="job-1", timeout=2)
        with pytest.raises(AllocationError):
            alloc.release(dev.id, job_id="job-2")

    def test_release_unknown_device_raises(self, registry):
        alloc = Allocator(registry)
        with pytest.raises(AllocationError):
            alloc.release("nope", job_id="j")

    def test_expire_stale_reclaims_device(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        alloc = Allocator(registry, default_ttl=1)
        alloc.acquire(platform="s32k", job_id="job-1", timeout=2)
        time.sleep(1.2)
        n = alloc.expire_stale()
        assert n == 1
        assert registry.get_device(dev.id).state == DeviceState.ONLINE
        assert registry.get_device(dev.id).current_job is None
        # 释放后可再次分配
        got = alloc.acquire(platform="s32k", job_id="job-2", timeout=2)
        assert got is not None

    def test_preferred_device(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        d2 = registry.add_device(name="lab-02", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        registry.update_device_state(d2.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        got = alloc.acquire(platform="s32k", job_id="j", timeout=2,
                            preferred_device="lab-02")
        assert got.id == d2.id


# ══════════════════════════════════════════════════════════════
# watchdog
# ══════════════════════════════════════════════════════════════

class TestWatchdog:
    def test_healthy_device_stays_online(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        wd = DeviceWatchdog(registry, probe=lambda d: True,
                            fail_threshold=2, fault_threshold=3)
        changes = wd.scan_once()
        assert changes == {}
        assert registry.get_device(dev.id).state == DeviceState.ONLINE

    def test_probe_failure_marks_offline_then_fault(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        wd = DeviceWatchdog(registry, probe=lambda d: False,
                            fail_threshold=2, fault_threshold=3)
        wd.scan_once()
        assert registry.get_device(dev.id).state == DeviceState.ONLINE
        changes = wd.scan_once()
        assert changes[dev.id] == DeviceState.OFFLINE.value
        assert registry.get_device(dev.id).state == DeviceState.OFFLINE
        wd.scan_once()
        assert registry.get_device(dev.id).state == DeviceState.FAULT

    def test_offline_auto_releases_allocation(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        alloc.acquire(platform="s32k", job_id="job-1", timeout=2)
        wd = DeviceWatchdog(registry, probe=lambda d: False,
                            fail_threshold=2, fault_threshold=3)
        wd.scan_once()
        wd.scan_once()  # → OFFLINE + auto release
        assert registry.get_allocation_for_device(dev.id) is None
        assert registry.get_device(dev.id).current_job is None

    def test_recover_manual(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.FAULT)
        wd = DeviceWatchdog(registry, probe=lambda d: False)
        assert wd.recover(dev.id) is True
        assert registry.get_device(dev.id).state == DeviceState.ONLINE

    def test_start_stop_thread(self, registry):
        dev = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(dev.id, DeviceState.ONLINE)
        wd = DeviceWatchdog(registry, probe=lambda d: True, interval=0.05)
        wd.start()
        time.sleep(0.15)
        wd.stop()
        assert registry.get_device(dev.id).last_seen is not None


# ══════════════════════════════════════════════════════════════
# pool
# ══════════════════════════════════════════════════════════════

class TestPool:
    def test_run_single_task(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        from yuleosh.device.pool import DevicePool
        pool = DevicePool(alloc, max_workers=2)

        def run(dev):
            return {"device": dev.name}

        results = pool.run([{"platform": "s32k", "job_id": "t1", "fn": run}])
        assert len(results) == 1
        assert results[0]["ok"] is True
        assert results[0]["result"]["device"] == "lab-01"
        # 任务结束后设备已释放
        assert registry.get_device(d1.id).state == DeviceState.ONLINE

    def test_run_parallel_two_devices(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        d2 = registry.add_device(name="lab-02", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        registry.update_device_state(d2.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        from yuleosh.device.pool import DevicePool
        pool = DevicePool(alloc, max_workers=2)

        def run(dev):
            return {"device": dev.name}

        results = pool.run([
            {"platform": "s32k", "job_id": "t1", "fn": run},
            {"platform": "s32k", "job_id": "t2", "fn": run},
        ])
        assert len(results) == 2
        assert all(r["ok"] for r in results)
        assert {r["result"]["device"] for r in results} == {"lab-01", "lab-02"}

    def test_run_insufficient_devices_reports_error(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        from yuleosh.device.pool import DevicePool
        pool = DevicePool(alloc, max_workers=2, acquire_timeout=1)

        def run(dev):
            return {"device": dev.name}

        # 先由外部任务占用唯一设备 → pool 任务必然无设备可用
        holder = alloc.acquire(platform="s32k", job_id="holder", timeout=2)
        assert holder is not None
        results = pool.run([{"platform": "s32k", "job_id": "t1", "fn": run}])
        assert len(results) == 1
        assert results[0]["ok"] is False
        assert "no device available" in results[0]["error"]

    def test_task_exception_reported_not_raised(self, registry):
        d1 = registry.add_device(name="lab-01", platform="s32k")
        registry.update_device_state(d1.id, DeviceState.ONLINE)
        alloc = Allocator(registry)
        from yuleosh.device.pool import DevicePool
        pool = DevicePool(alloc, max_workers=2)

        def run(dev):
            raise RuntimeError("boom")

        results = pool.run([{"platform": "s32k", "job_id": "t1", "fn": run}])
        assert results[0]["ok"] is False
        assert "boom" in results[0]["error"]
        assert registry.get_device(d1.id).state == DeviceState.ONLINE


# ══════════════════════════════════════════════════════════════
# DeviceManager 门面 + CLI 冒烟
# ══════════════════════════════════════════════════════════════

class TestDeviceManagerFacade:
    def test_manager_wires_registry_allocator(self, manager):
        dev = manager.add_device(name="lab-01", platform="s32k")
        assert dev.id
        assert manager.get_device(dev.id) is not None
        assert len(manager.list_devices()) == 1

    def test_manager_cli_smoke(self, manager, capsys):
        from yuleosh.device.cli import handle_device_command

        class Args:
            device_sub = "add"
            name = "cli-lab"
            platform = "stm32"
            flasher = "openocd"
            interface = "stlink"
            target = "stm32f4x"
            port = "/dev/ttyUSB0"
            serial = None
            online = False
            device_db = manager.registry.db_path

        handle_device_command(Args)
        out = capsys.readouterr().out
        assert "registered device cli-lab" in out

        class ListArgs:
            device_sub = "list"
            device_db = manager.registry.db_path

        handle_device_command(ListArgs)
        out2 = capsys.readouterr().out
        assert "cli-lab" in out2
