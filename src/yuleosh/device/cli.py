#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""`yuleosh device` CLI —— 设备管理层命令入口。

Commands::

    yuleosh device list                # 设备状态总览
    yuleosh device add                 # 注册设备
    yuleosh device remove <id>         # 移除设备
    yuleosh device check <id>          # 单设备健康检查
    yuleosh device events [--limit N]  # 事件日志
    yuleosh device acquire             # 手动锁（调试用）
    yuleosh device release             # 手动释放
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from yuleosh.device import DeviceManager, DeviceState


def _manager(args) -> DeviceManager:
    db_path = getattr(args, "device_db", None)
    return DeviceManager(db_path=db_path)


def _print_table(rows: list[list[str]]) -> None:
    if not rows:
        return
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*rows[0]))
    print("  ".join("-" * w for w in widths))
    for r in rows[1:]:
        print(fmt.format(*r))


def cmd_device_list(args) -> None:
    mgr = _manager(args)
    devices = mgr.list_devices()
    if not devices:
        print("(no devices registered — use `yuleosh device add`)")
        return
    rows = [["NAME", "PLATFORM", "FLASHER", "STATE", "JOB", "LAST-SEEN"]]
    for d in devices:
        rows.append([
            d.name, d.platform, d.flasher, d.state.value,
            d.current_job or "-", d.last_seen or "-",
        ])
    _print_table(rows)


def cmd_device_add(args) -> None:
    mgr = _manager(args)
    dev = mgr.add_device(
        name=args.name,
        platform=args.platform,
        flasher=args.flasher,
        flasher_config={"interface": args.interface, "target": args.target}
        if args.interface else {},
        port=args.port,
        serial=args.serial,
    )
    if args.online:
        mgr.registry.update_device_state(dev.id, DeviceState.ONLINE,
                                         last_seen=datetime.now().isoformat(
                                             timespec="seconds"))
    dev_after = mgr.get_device(dev.id)
    print(f"registered device {dev.name} (id={dev.id}, "
          f"state={dev_after.state.value if dev_after else dev.state.value})")


def cmd_device_remove(args) -> None:
    mgr = _manager(args)
    dev = mgr.get_device(args.device_id)
    if dev is None:
        dev = mgr.registry.get_device_by_name(args.device_id)
    if dev is None:
        print(f"device {args.device_id} not found")
        sys.exit(1)
    ok = mgr.remove_device(dev.id)
    if not ok:
        print(f"cannot remove device {args.device_id} "
              "(has active allocation)")
        sys.exit(1)
    print(f"removed device {args.device_id}")


def cmd_device_check(args) -> None:
    mgr = _manager(args)
    dev = mgr.get_device(args.device_id)
    if dev is None:
        dev = mgr.registry.get_device_by_name(args.device_id)
    if dev is None:
        print(f"device {args.device_id} not found")
        sys.exit(1)
    print(f"device: {dev.name} (id={dev.id})")
    print(f"  platform   : {dev.platform}")
    print(f"  flasher    : {dev.flasher}")
    print(f"  state      : {dev.state.value}")
    print(f"  port       : {dev.port or '-'}")
    print(f"  serial     : {dev.serial or '-'}")
    print(f"  current_job: {dev.current_job or '-'}")
    print(f"  last_seen  : {dev.last_seen or '-'}")


def cmd_device_events(args) -> None:
    mgr = _manager(args)
    events = mgr.list_events(limit=args.limit)
    if not events:
        print("(no device events)")
        return
    rows = [["TIME", "DEVICE", "EVENT", "DETAIL"]]
    for e in events:
        rows.append([e.created_at, e.device_id, e.event_type.value, e.detail])
    _print_table(rows)


def cmd_device_acquire(args) -> None:
    mgr = _manager(args)
    dev = mgr.allocator.acquire(
        platform=args.platform,
        job_id=args.job,
        timeout=float(args.timeout),
        ttl_seconds=args.ttl,
    )
    if dev is None:
        print(f"no device available (platform={args.platform}, "
              f"timeout={args.timeout}s)")
        sys.exit(1)
    print(f"acquired {dev.name} (id={dev.id}) for job {args.job}")


def cmd_device_release(args) -> None:
    mgr = _manager(args)
    try:
        ok = mgr.allocator.release(args.device_id, job_id=args.job)
    except Exception as e:
        print(f"release failed: {e}")
        sys.exit(1)
    if not ok:
        print(f"device {args.device_id} was not busy")
        sys.exit(1)
    print(f"released {args.device_id}")


def build_device_parser(sub) -> None:
    p_dev = sub.add_parser("device", help="Device management (HIL device pool)")
    dsub = p_dev.add_subparsers(dest="device_sub")

    p_list = dsub.add_parser("list", help="List registered devices")
    p_list.add_argument("--db", dest="device_db", default=None,
                        help="Device DB path (default ~/.yuleosh/device.db)")

    p_add = dsub.add_parser("add", help="Register a device")
    p_add.add_argument("--name", required=True, help="Display name")
    p_add.add_argument("--platform", required=True,
                       choices=["s32k", "stm32", "esp32", "generic"],
                       help="Target platform")
    p_add.add_argument("--flasher", default="openocd",
                       choices=["openocd", "jlink", "esptool"],
                       help="Flasher tool (default openocd)")
    p_add.add_argument("--interface", default=None,
                       help="OpenOCD interface (e.g. stlink, jlink)")
    p_add.add_argument("--target", default=None,
                       help="OpenOCD target (e.g. s32k344, stm32f4x)")
    p_add.add_argument("--port", default=None, help="Serial port path")
    p_add.add_argument("--serial", default=None, help="USB serial number")
    p_add.add_argument("--online", action="store_true",
                       help="Mark device ONLINE immediately (skip watchdog)")
    p_add.add_argument("--db", dest="device_db", default=None,
                       help="Device DB path")

    p_rm = dsub.add_parser("remove", help="Remove a device")
    p_rm.add_argument("device_id", help="Device id or name")
    p_rm.add_argument("--db", dest="device_db", default=None,
                      help="Device DB path")

    p_chk = dsub.add_parser("check", help="Show device details / health")
    p_chk.add_argument("device_id", help="Device id or name")
    p_chk.add_argument("--db", dest="device_db", default=None,
                       help="Device DB path")

    p_ev = dsub.add_parser("events", help="Show device event log")
    p_ev.add_argument("--limit", type=int, default=50,
                      help="Max events (default 50)")
    p_ev.add_argument("--db", dest="device_db", default=None,
                      help="Device DB path")

    p_acq = dsub.add_parser("acquire", help="Manually acquire a device (debug)")
    p_acq.add_argument("--platform", default=None, help="Platform filter")
    p_acq.add_argument("--job", default="cli-debug", help="Job id")
    p_acq.add_argument("--timeout", type=float, default=30.0,
                       help="Wait timeout seconds (default 30)")
    p_acq.add_argument("--ttl", type=int, default=1800,
                       help="Allocation TTL seconds (default 1800)")
    p_acq.add_argument("--db", dest="device_db", default=None,
                       help="Device DB path")

    p_rel = dsub.add_parser("release", help="Manually release a device (debug)")
    p_rel.add_argument("device_id", help="Device id or name")
    p_rel.add_argument("--job", default=None, help="Job id (ownership check)")
    p_rel.add_argument("--db", dest="device_db", default=None,
                       help="Device DB path")


def handle_device_command(args) -> None:
    if args.device_sub == "list":
        cmd_device_list(args)
    elif args.device_sub == "add":
        cmd_device_add(args)
    elif args.device_sub == "remove":
        cmd_device_remove(args)
    elif args.device_sub == "check":
        cmd_device_check(args)
    elif args.device_sub == "events":
        cmd_device_events(args)
    elif args.device_sub == "acquire":
        cmd_device_acquire(args)
    elif args.device_sub == "release":
        cmd_device_release(args)
    else:
        print("usage: yuleosh device <list|add|remove|check|events|acquire|release>")
        sys.exit(1)
