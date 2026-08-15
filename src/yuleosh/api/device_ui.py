#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Device Management UI API — 设备管理 UI（复用 yuleosh.device 模块，设计文档模块⑥）。

HIL 板卡池可视化与手动分配/释放：直接复用设备管理层（S1-S4 已落地）的
``DeviceRegistry``（SQLite 持久化，db 路径 ``YULEOSH_DEVICE_DB`` 或
``~/.yuleosh/device.db``），本模块只做 UI 视图与操作透传。

设计决策 6：任意登录用户（含 Developer）均可手动 acquire/release 设备做调试
（Developer 可刷板）—— 不做角色门槛，但把操作者记入事件时间线以便审计。

Mounted at /api/v1/device-ui/ in the main server router.

Endpoints:
    GET  /api/v1/device-ui/list              — 设备列表（id/name/platform/state/
                                               current_job/last_seen/firmware_version）
    GET  /api/v1/device-ui/stats             — 按状态利用率汇总（online/busy/offline/
                                               fault/unknown + total）
    POST /api/v1/device-ui/{id}/acquire      — 手动分配（body: job_id 必填, ttl_seconds?）
    POST /api/v1/device-ui/{id}/release      — 释放（body: job_id? 校验归属）
    GET  /api/v1/device-ui/{id}/events       — 看门狗事件时间线（limit=50）
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth
from yuleosh.device.models import Device, DeviceEventType, DeviceState
from yuleosh.device.registry import DeviceRegistry

log = logging.getLogger("api.device_ui")

DEFAULT_TTL_SECONDS = 1800
EVENTS_LIMIT = 50


def _device_db_path() -> str:
    """设备 DB 路径：YULEOSH_DEVICE_DB 环境变量优先，否则 ~/.yuleosh/device.db。"""
    return os.environ.get("YULEOSH_DEVICE_DB") or str(
        Path.home() / ".yuleosh" / "device.db"
    )


def _get_registry() -> DeviceRegistry:
    """构造（或复用）DeviceRegistry 实例。

    每次请求新建实例：registry 连接为 per-call + 写锁，开销可忽略；
    也便于测试 patch ``yuleosh.api.device_ui.DeviceRegistry``。
    """
    return DeviceRegistry(_device_db_path())


def _device_brief(dev: Device) -> dict:
    """设备列表/详情视图字段（UI 卡片所需最小集）。"""
    return {
        "id": dev.id,
        "name": dev.name,
        "platform": dev.platform,
        "state": dev.state.value,
        "current_job": dev.current_job,
        "last_seen": dev.last_seen,
        "firmware_version": dev.firmware_version,
    }


@require_auth
def handle_device_ui(method: str, path_tail: str, body: dict, query: dict,
                     handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/device-ui/... requests (module ⑥).

    ``**kwargs`` absorbs the ``current_user`` injected by require_auth
    (user_id/org_id/email/role) — role 用于审计记录，不做 acquire 门槛
    （设计决策 6：Developer 可刷板）。
    """
    current_user = kwargs.get("current_user") or {}
    parts = [p for p in (path_tail or "").split("/") if p]

    if not parts:
        return json_error(f"Unknown device-ui sub-path or method: {method} {path_tail}", 404)

    if parts[0] == "list" and method == "GET":
        return _device_list()
    if parts[0] == "stats" and method == "GET":
        return _device_stats()

    if len(parts) == 2:
        device_id, action = parts
        if action == "acquire" and method == "POST":
            return _device_acquire(device_id, body, current_user)
        if action == "release" and method == "POST":
            return _device_release(device_id, body)
        if action == "events" and method == "GET":
            return _device_events(device_id)

    return json_error(f"Unknown device-ui sub-path or method: {method} {path_tail}", 404)


def _device_list() -> tuple[dict, int]:
    """GET /api/v1/device-ui/list — 设备状态列表。"""
    registry = _get_registry()
    devices = registry.list_devices()
    return json_ok({
        "devices": [_device_brief(d) for d in devices],
        "count": len(devices),
        "note": None,
    })


def _device_stats() -> tuple[dict, int]:
    """GET /api/v1/device-ui/stats — 按状态聚合的利用率汇总。"""
    registry = _get_registry()
    devices = registry.list_devices()
    by_state = {s.value: 0 for s in DeviceState}
    for d in devices:
        state = getattr(d, "state", None)
        if isinstance(state, DeviceState):
            key = state.value
        elif state is None:
            key = "unknown"
        else:
            key = str(getattr(state, "value", state)) or "unknown"
        by_state[key] = by_state.get(key, 0) + 1
    return json_ok({
        "total": len(devices),
        "by_state": by_state,
        "note": None,
    })


def _device_acquire(device_id: str, body: dict, current_user: dict) -> tuple[dict, int]:
    """POST /api/v1/device-ui/{id}/acquire — 手动分配设备。

    任意登录用户可 acquire（设计决策 6）；操作者写入事件 detail 供审计。
    分配写 allocation + 设备置 BUSY + 记 BUSY 事件（与 allocator._assign 同语义）。
    """
    registry = _get_registry()
    dev = registry.get_device(device_id)
    if dev is None:
        return json_error(f"device not found: {device_id}", 404)

    body = body or {}
    job_id = body.get("job_id")
    if not job_id:
        return json_error("job_id is required", 400)

    try:
        ttl = int(body.get("ttl_seconds") or DEFAULT_TTL_SECONDS)
    except (TypeError, ValueError):
        return json_error("ttl_seconds must be an integer", 400)
    if ttl <= 0:
        return json_error("ttl_seconds must be a positive integer", 400)

    if not dev.is_available():
        return json_error(
            f"device {device_id} is not available "
            f"(state={dev.state.value}, current_job={dev.current_job})",
            409,
        )

    alloc = registry.create_allocation(device_id, job_id, ttl)
    updated = registry.update_device_state(device_id, DeviceState.BUSY, current_job=job_id)

    who = current_user.get("email") or str(current_user.get("user_id") or "unknown")
    role = current_user.get("role") or "member"
    registry.record_event(
        device_id, DeviceEventType.BUSY,
        f"acquired by job {job_id} (alloc {alloc.id}, user {who}/{role})",
    )

    return json_ok({
        "device": _device_brief(updated or dev),
        "allocation": alloc.to_dict(),
    })


def _device_release(device_id: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/device-ui/{id}/release — 释放设备。

    body.job_id 可选：提供时校验归属，防止误释放他人任务（allocator.release 语义）。
    """
    registry = _get_registry()
    dev = registry.get_device(device_id)
    if dev is None:
        return json_error(f"device not found: {device_id}", 404)

    alloc = registry.get_allocation_for_device(device_id)
    if alloc is None:
        return json_error(f"device {device_id} has no active allocation", 409)

    job_id = (body or {}).get("job_id") or None
    ok = registry.release_allocation(alloc.id, job_id=job_id)
    if not ok:
        return json_error(
            f"failed to release allocation {alloc.id} for device {device_id} "
            f"(held by job {alloc.job_id})",
            409,
        )

    registry.update_device_state(device_id, DeviceState.ONLINE, current_job=None)
    registry.record_event(
        device_id, DeviceEventType.RELEASED,
        f"released from job {alloc.job_id}",
    )
    return json_ok({
        "device": _device_brief(dev),
        "allocation_id": alloc.id,
        "job_id": alloc.job_id,
    })


def _device_events(device_id: str) -> tuple[dict, int]:
    """GET /api/v1/device-ui/{id}/events — 看门狗事件时间线（最近 50 条）。"""
    registry = _get_registry()
    dev = registry.get_device(device_id)
    if dev is None:
        return json_error(f"device not found: {device_id}", 404)

    events = registry.list_events(device_id, limit=EVENTS_LIMIT)
    return json_ok({
        "device": _device_brief(dev),
        "events": [e.to_dict() for e in events],
        "count": len(events),
    })
