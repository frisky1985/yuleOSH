#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Loop Engineering CLI — `yuleosh loop {status|run|config}` (LE-007)。

提供统一的命令行接口来管理反馈回路：
  - `yuleosh loop status`       — 查看当前活跃的 loop 事件和状态
  - `yuleosh loop run <name>`   — 手动触发指定 loop
  - `yuleosh loop config`       — 查看/修改 loop 参数

Usage:
    yuleosh loop status
    yuleosh loop status --json
    yuleosh loop run loop1_defect_to_req --test test_foo --req RS-001
    yuleosh loop config
    yuleosh loop config --set dedup_window 600
"""

import argparse
import json
import logging
import os
import sys

from yuleosh.loop_engine import LoopEngine
from yuleosh.loop_engine.event_bus import loop_bus, LoopEventType
from yuleosh.loop_engine.feedback_handlers import (
    get_registered_handlers,
    Loop1DefectToReqHandler,
    Loop2FieldToFMEAHandler,
    Loop3KPIToImproveHandler,
    Loop4KGSelfEvolveHandler,
)

log = logging.getLogger("yuleosh.loop_engine.cli")


# ═══════════════════════════════════════════════════════════════════════
# 共享引擎
# ═══════════════════════════════════════════════════════════════════════

def _build_engine() -> LoopEngine:
    """构建并初始化 LoopEngine。"""
    engine = LoopEngine(event_bus=loop_bus)

    # 自动注册所有已发现的 FeedbackHandler
    # Loop 1 — 缺陷→需求回溯
    try:
        kg_store = _get_kg_store()
        loop1 = Loop1DefectToReqHandler(kg_store=kg_store)
        engine.register_handler(loop1)
    except Exception as e:
        log.warning("Loop1 handler init skipped: %s", e)

    # Loop 2 — 现场缺陷→FMEA
    try:
        from yuleosh.loop_engine.rca_engine import RCAEngine
        from yuleosh.knowledge_management.store import KBStore
        kg_store_km = KBStore()
        loop2 = Loop2FieldToFMEAHandler(kg_store=kg_store_km)
        engine.register_handler(loop2)
    except Exception as e:
        log.warning("Loop2 handler init skipped: %s", e)

    # Loop 3 — KPI→RCA→改进
    try:
        rca_engine = RCAEngine(kg_store=kg_store_km if 'kg_store_km' in dir() else None)
        loop3 = Loop3KPIToImproveHandler(rca_engine=rca_engine)
        engine.register_handler(loop3)
    except Exception as e:
        log.warning("Loop3 handler init skipped: %s", e)

    # Loop 4 — KG 置信度自进化
    try:
        loop4 = Loop4KGSelfEvolveHandler(
            knowledge_store=kg_store_km if 'kg_store_km' in dir() else None
        )
        engine.register_handler(loop4)
    except Exception as e:
        log.warning("Loop4 handler init skipped: %s", e)

    engine.start()
    return engine


def _get_kg_store():
    """获取 KG 存储后端 (如果可用)。"""
    try:
        from yuleosh.knowledge_graph import get_store
        return get_store()
    except ImportError:
        return None


# ═══════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════

def cmd_status(args):
    """`yuleosh loop status` — 查看当前活跃的 loop 事件和状态。"""
    engine = _build_engine()
    status = engine.status

    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
        return

    # 格式化输出
    print()
    print("  🔄 yuleOSH Loop Engineering Status")
    print(f"  {'=' * 50}")
    print(f"  Engine: {'● RUNNING' if status['running'] else '○ STOPPED'}")
    print()

    # EventBus 统计
    eb_stats = status.get("event_bus_stats", {})
    print(f"  📊 EventBus: {eb_stats.get('total_emitted', 0)} emitted, "
          f"{eb_stats.get('total_handled', 0)} handled, "
          f"{eb_stats.get('total_failed', 0)} failed, "
          f"{eb_stats.get('total_deduped', 0)} deduped, "
          f"{eb_stats.get('total_retried', 0)} retried")
    print()

    # Handlers
    handlers = status.get("handlers", {})
    if handlers:
        print(f"  🧩 Registered Handlers ({len(handlers)}):")
        print(f"  {'─' * 50}")
        for name, info in handlers.items():
            events_str = ", ".join(info.get("subscribed_events", []))
            ready = "✅" if info.get("can_handle") else "⏸️"
            print(f"  {ready} {name}")
            print(f"     Events: {events_str}")
        print()
    else:
        print("  ⚠️  No handlers registered")
        print()

    # 最近事件
    recent = loop_bus.history(limit=5)
    if recent:
        print(f"  📋 Recent Events (last {len(recent)}):")
        print(f"  {'─' * 50}")
        for ev in recent:
            print(f"     {ev['event_type']:30s} "
                  f"prio={ev['priority']} "
                  f"id={ev['event_id'][:8]}")
        print()


def cmd_run(args):
    """`yuleosh loop run <name>` — 手动触发指定 loop。"""
    loop_name = args.loop_name
    engine = _build_engine()

    # 构建事件数据
    data = {}
    if args.test:
        data["test_name"] = args.test
        data["test_fqn"] = args.test
    if args.req:
        data["req_id"] = args.req
    if args.error:
        data["error"] = args.error
    if args.source:
        data["source"] = args.source

    # 构建模拟事件
    if loop_name == "loop1_defect_to_req" or loop_name == "Loop1DefectToReqHandler":
        event_type = LoopEventType.CI_FAILURE
        if not data.get("test_name"):
            data["test_name"] = "manual_trigger"
    elif loop_name == "loop2_field_to_fmea":
        event_type = LoopEventType.FIELD_DEFECT
    elif loop_name == "loop3_kpi_to_improve":
        event_type = LoopEventType.KPI_BREACH
    elif loop_name == "loop4_kg_self_evolve":
        event_type = LoopEventType.KG_LOW_CONFIDENCE
    else:
        # 尝试从已注册 handler 获取事件类型
        from yuleosh.loop_engine.feedback_handlers.base import get_registered_handlers
        handlers = get_registered_handlers()
        if loop_name in handlers:
            handler_cls = handlers[loop_name]
            handler_instance = handler_cls(kg_store=_get_kg_store())
            event_type = handler_instance.subscribed_events()[0]
        else:
            print(f"  ❌ Unknown loop: {loop_name}")
            print(f"     Available: {list(handlers.keys())}")
            sys.exit(1)

    # 使用 engine.run_loop_once
    try:
        result = engine.run_loop_once(loop_name, **data)
    except ValueError as e:
        # 通过名称查找
        handlers = {h.name: h for _, h in engine._handlers.items()}
        if loop_name in handlers:
            from yuleosh.loop_engine.event_bus import LoopEvent
            event = LoopEvent(
                event_type=event_type,
                source="cli",
                data=data,
            )
            result = handlers[loop_name].handle(event)
        else:
            print(f"  ❌ {e}")
            sys.exit(1)

    # 输出结果
    print()
    print(f"  🔄 Loop Run: {loop_name}")
    print(f"  {'=' * 50}")
    print(f"  Event type: {event_type.value}")
    print(f"  Result: {'✅ SUCCESS' if result.success else '❌ FAILURE'}")
    print(f"  Action: {result.action_taken}")
    if result.evidence_ref:
        print(f"  Evidence: {result.evidence_ref}")
    print(f"  Rollback possible: {result.rollback_possible}")
    if result.details:
        print(f"  Details: {json.dumps(result.details, indent=2, default=str)}")
    print()


def cmd_config(args):
    """`yuleosh loop config` — 查看/修改 loop 参数。"""
    config_path = os.path.join(
        os.environ.get("OSH_HOME", "."),
        ".yuleosh", "loop_config.json"
    )

    # — 修改参数 —
    if args.set:
        key, value = args.set.split("=", 1) if "=" in args.set else (args.set, "")
        # 解析值类型
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        elif value.isdigit():
            parsed = int(value)
        else:
            try:
                parsed = float(value)
            except ValueError:
                parsed = value

        config = _load_config(config_path)
        config[key] = parsed
        _save_config(config_path, config)
        print(f"\n  ✅ Config updated: {key} = {parsed!r}")
        print(f"     File: {config_path}\n")
        return

    # — 查看参数 —
    config = _load_config(config_path)

    print()
    print("  ⚙️  Loop Configuration")
    print(f"  {'=' * 50}")
    print(f"  Config file: {config_path}")
    print()

    # 默认参数
    defaults = {
        "dedup_window_seconds": 300,
        "max_retries": 3,
        "max_history": 2000,
        "loop1_enabled": True,
        "loop2_enabled": False,
        "loop3_enabled": False,
        "loop4_enabled": False,
        "log_level": "INFO",
    }

    merged = {**defaults, **config}

    print(f"  {'Parameter':<30s} {'Value':<20s} {'Source':<10s}")
    print(f"  {'─' * 60}")
    for key, default_val in defaults.items():
        current = merged.get(key, default_val)
        source = "file" if key in config else "default"
        print(f"  {key:<30s} {str(current):<20s} {source:<10s}")

    print()


def _load_config(config_path: str) -> dict:
    """加载 loop 配置文件。"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_config(config_path: str, config: dict):
    """保存 loop 配置文件。"""
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# Argument Parser
# ═══════════════════════════════════════════════════════════════════════

def build_loop_subparser(subparsers):
    """构建 `yuleosh loop` 子命令解析器。

    在 main.py 的 _build_parser() 中调用。
    """
    p_loop = subparsers.add_parser("loop", help="Loop Engineering management")
    lsub = p_loop.add_subparsers(dest="loop_sub", help="Loop subcommand")

    # loop status
    p_status = lsub.add_parser("status", help="查看当前活跃的 loop 事件和状态")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")

    # loop run
    p_run = lsub.add_parser("run", help="手动触发指定 loop")
    p_run.add_argument("loop_name", help="Loop handler name (e.g. loop1_defect_to_req)")
    p_run.add_argument("--test", "-t", default=None, help="Test function name")
    p_run.add_argument("--req", "-r", default=None, help="Requirement ID")
    p_run.add_argument("--error", "-e", default=None, help="Error message")
    p_run.add_argument("--source", "-s", default="cli", help="Event source")

    # loop config
    p_config = lsub.add_parser("config", help="查看/修改 loop 参数")
    p_config.add_argument("--set", "-s", default=None,
                          help="设置参数 (key=value, e.g. dedup_window=600)")


def handle_loop_command(args):
    """Dispatch loop subcommands."""
    if args.loop_sub == "status":
        cmd_status(args)
    elif args.loop_sub == "run":
        cmd_run(args)
    elif args.loop_sub == "config":
        cmd_config(args)
    else:
        print("Usage: yuleosh loop {status|run|config}")
        sys.exit(1)
