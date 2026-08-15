#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""设备并行池 —— 多设备并发执行 HIL 任务。

每个任务 = 一块设备 + 一个可调用函数（通常内部走
hardware.HardwareDeployer 刷写/测试）。池负责：分配 → 执行 → 释放 →
汇总结果。不关心任务内部逻辑（依赖注入，便于单测）。

用法::

    from yuleosh.device import DeviceManager
    from yuleosh.device.pool import DevicePool

    pool = DevicePool(mgr.allocator)

    def run_test(dev):
        # dev 是已分配设备
        return {"ok": True, "device": dev.name}

    results = pool.run([
        {"platform": "s32k", "job_id": "t1", "fn": run_test},
        {"platform": "s32k", "job_id": "t2", "fn": run_test},
    ])
"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from .models import Device
from .allocator import Allocator

log = logging.getLogger("yuleosh.device.pool")

TaskFn = Callable[[Device], object]


class DevicePool:
    """多设备并行执行器。

    Parameters
    ----------
    allocator : Allocator
        资源分配器。
    max_workers : int
        并发上限（受物理设备数约束，默认 4）。
    acquire_timeout : float
        每个任务等待设备的最长秒数（默认 120）。
    """

    def __init__(
        self,
        allocator: Allocator,
        max_workers: int = 4,
        acquire_timeout: float = 120.0,
    ):
        self.allocator = allocator
        self.max_workers = max_workers
        self.acquire_timeout = acquire_timeout

    # ── 主入口 ───────────────────────────────────────────────

    def run(self, tasks: list[dict]) -> list[dict]:
        """并发执行任务列表。

        Parameters
        ----------
        tasks : list[dict]
            每个 dict 含:
              - platform: str          设备平台
              - job_id: str            任务标识
              - fn: TaskFn             执行函数（收 Device 返回结果）
              - preferred_device: str, optional
              - ttl_seconds: int, optional

        Returns
        -------
        list[dict]
            与 tasks 等长的结果列表：
              {task, ok, result|error, device}
        """
        if not tasks:
            return []
        results: list[dict] = [None] * len(tasks)  # type: ignore[list-item]

        def _run_one(idx: int, task: dict) -> None:
            results[idx] = self._run_single(task)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(tasks))) as ex:
            futures: list[Future] = []
            for idx, task in enumerate(tasks):
                futures.append(ex.submit(_run_one, idx, task))
            for f in futures:
                f.result()  # 传播异常（_run_single 已兜底）

        return results

    # ── 单任务 ───────────────────────────────────────────────

    def _run_single(self, task: dict) -> dict:
        platform = task.get("platform")
        job_id = task.get("job_id", "pool-task")
        fn = task.get("fn")
        if not callable(fn):
            return {"task": task, "ok": False,
                    "error": "task missing callable 'fn'", "device": None}

        dev = self.allocator.acquire(
            platform=platform,
            job_id=job_id,
            timeout=self.acquire_timeout,
            preferred_device=task.get("preferred_device"),
        )
        if dev is None:
            return {"task": task, "ok": False,
                    "error": f"no device available (platform={platform})",
                    "device": None}

        try:
            result = fn(dev)
            return {"task": task, "ok": True, "result": result,
                    "device": dev.id}
        except Exception as e:
            log.exception("task %s failed on device %s", job_id, dev.name)
            return {"task": task, "ok": False, "error": str(e),
                    "device": dev.id}
        finally:
            try:
                self.allocator.release(dev.id, job_id=job_id)
            except Exception as e:  # 释放失败不掩盖任务结果
                log.warning("release failed for %s: %s", dev.id, e)
