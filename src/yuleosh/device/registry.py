#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""设备注册表 —— SQLite 持久化的设备/分配/事件存储。

设备是平台级资源（跨项目共享的板卡池），独立于项目级 store：
  - 默认 DB: ~/.yuleosh/device.db
  - 可用环境变量 YULEOSH_DEVICE_DB 覆盖（测试/多租户用）

Thread-safe：连接 per-call + 写锁，对齐 yuleOSH store 模式。
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    Allocation,
    AllocationStatus,
    Device,
    DeviceEvent,
    DeviceEventType,
    DeviceState,
)

log = logging.getLogger("yuleosh.device.registry")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    platform TEXT NOT NULL,
    flasher TEXT NOT NULL DEFAULT 'openocd',
    flasher_config TEXT NOT NULL DEFAULT '{}',
    port TEXT,
    serial TEXT,
    state TEXT NOT NULL DEFAULT 'unknown',
    current_job TEXT,
    firmware_version TEXT,
    last_seen TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS allocations (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    released_at TEXT,
    ttl_seconds INTEGER NOT NULL DEFAULT 1800,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS device_events (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _default_db_path() -> Path:
    env = os.environ.get("YULEOSH_DEVICE_DB")
    if env:
        return Path(env)
    return Path.home() / ".yuleosh" / "device.db"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DeviceRegistry:
    """设备注册表。

    管理 Device / Allocation / DeviceEvent 三类实体的持久化。
    不包含分配策略（allocator 负责）与健康探测（watchdog 负责）。
    """

    def __init__(self, db_path: Optional[str | Path] = None):
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_schema()

    # ── 存储基础 ──────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._write_lock:
            conn = self._conn()
            try:
                cur = conn.execute(sql, params)
                conn.commit()
                return cur
            finally:
                conn.close()

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._conn()
        try:
            cur = conn.execute(sql, params)
            return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    # ── Device CRUD ───────────────────────────────────────────

    def add_device(
        self,
        name: str,
        platform: str,
        flasher: str = "openocd",
        flasher_config: dict | None = None,
        port: str | None = None,
        serial: str | None = None,
        device_id: str | None = None,
    ) -> Device:
        import json as _json

        dev = Device(
            id=device_id or self._new_id(),
            name=name,
            platform=platform,
            flasher=flasher,
            flasher_config=flasher_config or {},
            port=port,
            serial=serial,
        )
        self._execute(
            """
            INSERT INTO devices
                (id, name, platform, flasher, flasher_config, port, serial,
                 state, current_job, firmware_version, last_seen,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                dev.id, dev.name, dev.platform, dev.flasher,
                _json.dumps(dev.flasher_config), dev.port, dev.serial,
                dev.state.value, dev.current_job, dev.firmware_version,
                dev.last_seen, dev.created_at, dev.updated_at,
            ),
        )
        self.record_event(dev.id, DeviceEventType.REGISTERED,
                          f"registered platform={platform}")
        return dev

    def get_device(self, device_id: str) -> Optional[Device]:
        rows = self._query("SELECT * FROM devices WHERE id = ?", (device_id,))
        if not rows:
            return None
        return self._row_to_device(rows[0])

    def get_device_by_name(self, name: str) -> Optional[Device]:
        rows = self._query("SELECT * FROM devices WHERE name = ?", (name,))
        if not rows:
            return None
        return self._row_to_device(rows[0])

    def list_devices(self) -> list[Device]:
        rows = self._query("SELECT * FROM devices ORDER BY name")
        return [self._row_to_device(r) for r in rows]

    def remove_device(self, device_id: str) -> bool:
        dev = self.get_device(device_id)
        if dev is None:
            return False
        # 有活跃分配时禁止移除
        active = self._query(
            "SELECT id FROM allocations WHERE device_id = ? AND status = 'active'",
            (device_id,),
        )
        if active:
            log.warning("refusing to remove busy device %s", device_id)
            return False
        self._execute("DELETE FROM devices WHERE id = ?", (device_id,))
        self.record_event(device_id, DeviceEventType.REMOVED,
                          f"removed device {dev.name}")
        return True

    def update_device_state(
        self,
        device_id: str,
        state: DeviceState,
        current_job: str | None = None,
        firmware_version: str | None = None,
        last_seen: str | None = None,
    ) -> Optional[Device]:
        """更新设备状态。

        current_job 语义：显式传入（含 None 清空）；省略时保留原值。
        因调用方总是显式传，直接写入。
        """
        dev = self.get_device(device_id)
        if dev is None:
            return None
        now = _now_iso()
        self._execute(
            """
            UPDATE devices
               SET state = ?, current_job = ?, firmware_version = ?,
                   last_seen = COALESCE(?, last_seen), updated_at = ?
             WHERE id = ?
            """,
            (
                state.value,
                current_job,
                firmware_version if firmware_version is not None
                else dev.firmware_version,
                last_seen,
                now,
                device_id,
            ),
        )
        return self.get_device(device_id)

    # ── Allocation ────────────────────────────────────────────

    def create_allocation(
        self, device_id: str, job_id: str, ttl_seconds: int = 1800
    ) -> Allocation:
        alloc = Allocation(
            id=self._new_id(),
            device_id=device_id,
            job_id=job_id,
            ttl_seconds=ttl_seconds,
        )
        self._execute(
            """
            INSERT INTO allocations
                (id, device_id, job_id, acquired_at, released_at,
                 ttl_seconds, status)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                alloc.id, alloc.device_id, alloc.job_id, alloc.acquired_at,
                alloc.released_at, alloc.ttl_seconds, alloc.status.value,
            ),
        )
        return alloc

    def get_allocation(self, alloc_id: str) -> Optional[Allocation]:
        rows = self._query("SELECT * FROM allocations WHERE id = ?", (alloc_id,))
        if not rows:
            return None
        return self._row_to_allocation(rows[0])

    def get_active_allocations(self) -> list[Allocation]:
        rows = self._query(
            "SELECT * FROM allocations WHERE status = 'active' ORDER BY acquired_at"
        )
        return [self._row_to_allocation(r) for r in rows]

    def get_allocation_for_device(self, device_id: str) -> Optional[Allocation]:
        rows = self._query(
            "SELECT * FROM allocations WHERE device_id = ? AND status = 'active'",
            (device_id,),
        )
        if not rows:
            return None
        return self._row_to_allocation(rows[0])

    def release_allocation(
        self, alloc_id: str, job_id: str | None = None
    ) -> bool:
        """释放分配（可校验 job_id 防误释放）。"""
        alloc = self.get_allocation(alloc_id)
        if alloc is None or alloc.status != AllocationStatus.ACTIVE:
            return False
        if job_id is not None and alloc.job_id != job_id:
            log.warning("allocation %s belongs to job %s, not %s",
                        alloc_id, alloc.job_id, job_id)
            return False
        self._execute(
            "UPDATE allocations SET status = 'released', released_at = ? WHERE id = ?",
            (_now_iso(), alloc_id),
        )
        return True

    def expire_allocation(self, alloc_id: str) -> bool:
        self._execute(
            "UPDATE allocations SET status = 'expired', released_at = ? WHERE id = ?",
            (_now_iso(), alloc_id),
        )
        return True

    # ── DeviceEvent ───────────────────────────────────────────

    def record_event(
        self,
        device_id: str,
        event_type: DeviceEventType,
        detail: str = "",
    ) -> DeviceEvent:
        ev = DeviceEvent(
            id=self._new_id(),
            device_id=device_id,
            event_type=event_type,
            detail=detail,
        )
        self._execute(
            """
            INSERT INTO device_events (id, device_id, event_type, detail, created_at)
            VALUES (?,?,?,?,?)
            """,
            (ev.id, ev.device_id, ev.event_type.value, ev.detail, ev.created_at),
        )
        return ev

    def list_events(self, device_id: str | None = None, limit: int = 100) -> list[DeviceEvent]:
        if device_id:
            rows = self._query(
                "SELECT * FROM device_events WHERE device_id = ? ORDER BY created_at DESC LIMIT ?",
                (device_id, limit),
            )
        else:
            rows = self._query(
                "SELECT * FROM device_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [
            DeviceEvent(
                id=r["id"], device_id=r["device_id"],
                event_type=DeviceEventType(r["event_type"]),
                detail=r["detail"], created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _row_to_device(row: sqlite3.Row) -> Device:
        import json as _json

        cfg = {}
        try:
            cfg = _json.loads(row["flasher_config"] or "{}")
        except ValueError:
            cfg = {}
        return Device(
            id=row["id"], name=row["name"], platform=row["platform"],
            flasher=row["flasher"], flasher_config=cfg,
            port=row["port"], serial=row["serial"],
            state=DeviceState(row["state"]),
            current_job=row["current_job"],
            firmware_version=row["firmware_version"],
            last_seen=row["last_seen"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_allocation(row: sqlite3.Row) -> Allocation:
        return Allocation(
            id=row["id"], device_id=row["device_id"], job_id=row["job_id"],
            acquired_at=row["acquired_at"], released_at=row["released_at"],
            ttl_seconds=row["ttl_seconds"],
            status=AllocationStatus(row["status"]),
        )
