#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Loop Engineering CLI — `yuleosh loop {status|run|config|dead-letter|audit}` (LE-007)。

提供统一的命令行接口来管理反馈回路：
  - `yuleosh loop status`       — 查看当前活跃的 loop 事件和状态
  - `yuleosh loop run <name>`   — 手动触发指定 loop
  - `yuleosh loop config`       — 查看/修改 loop 参数
  - `yuleosh loop dead-letter {list|retry|clear}` — 死信队列管理 (I4)
  - `yuleosh loop audit {list|query}`              — 审计日志查询 (I4)

Usage:
    yuleosh loop status
    yuleosh loop status --json
    yuleosh loop run loop1_defect_to_req --test test_foo --req RS-001
    yuleosh loop config
    yuleosh loop config --set dedup_window 600
    yuleosh loop dead-letter list
    yuleosh loop dead-letter retry
    yuleosh loop dead-letter clear
    yuleosh loop audit list
    yuleosh loop audit query <event_id>
"""

import argparse
import json
import logging
import os
import sys

from yuleosh.loop_engine import LoopEngine
from yuleosh.loop_engine.event_bus import loop_bus, LoopEventType

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
        from yuleosh.loop_engine.feedback_handlers import Loop1DefectToReqHandler
        loop1 = Loop1DefectToReqHandler(kg_store=kg_store)
        engine.register_handler(loop1)
    except Exception as e:
        log.warning("Loop1 handler init skipped: %s", e)

    # Loop 2 — 现场缺陷→FMEA
    try:
        from yuleosh.loop_engine.feedback_handlers import Loop2FieldToFMEAHandler
        from yuleosh.knowledge_management.store import KBStore
        kg_store_km = KBStore()
        loop2 = Loop2FieldToFMEAHandler(kg_store=kg_store_km)
        engine.register_handler(loop2)
    except Exception as e:
        log.warning("Loop2 handler init skipped: %s", e)

    # Loop 3 — KPI→RCA→改进
    try:
        from yuleosh.loop_engine.rca_engine import RCAEngine
        from yuleosh.loop_engine.feedback_handlers import Loop3KPIToImproveHandler
        rca_engine = RCAEngine(kg_store=kg_store_km if 'kg_store_km' in dir() else None)
        loop3 = Loop3KPIToImproveHandler(rca_engine=rca_engine)
        engine.register_handler(loop3)
    except Exception as e:
        log.warning("Loop3 handler init skipped: %s", e)

    # Loop 4 — KG 置信度自进化
    try:
        from yuleosh.loop_engine.feedback_handlers import Loop4KGSelfEvolveHandler
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
    """`yuleosh loop status` — 查看当前活跃的 loop 事件和状态。

    I4 增强:
        - 显示来源验证状态
        - 显示速率限制统计
        - 显示死信队列统计
        - 显示审计统计
    """
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

    # I4: 来源验证状态
    sv = eb_stats.get("source_validator", {})
    if sv:
        print(f"  🛡️  Source Validation: {'✅ ON' if sv.get('enabled') else '⏸️ OFF'} "
              f"| Secret: {'configured' if sv.get('has_secret') else 'none'} "
              f"| Whitelist: {len(sv.get('whitelist', []))} sources")
    print()

    # I4: 速率限制 & 死信队列 & 审计
    rl = eb_stats.get("rate_limiter", {})
    dl = eb_stats.get("dead_letter", {})
    al = eb_stats.get("audit", {})

    print(f"  ⚡ Rate Limiting: {'✅ ON' if rl.get('enabled') else '⏸️ OFF'} "
          f"| Default: {rl.get('default_rate', 'N/A')} e/s")
    print(f"  💀 Dead Letter Queue: {dl.get('count', 0)} events "
          f"| Max retries: {dl.get('max_retries', 'N/A')}")
    print(f"  📋 Audit Log: {al.get('total_records', 0)} records "
          f"| Max: {al.get('max_entries', 'N/A')}")
    print()

    # 速率限制桶详情
    buckets = rl.get("buckets", {})
    if buckets:
        print(f"  🪣  Token Buckets ({len(buckets)}):")
        print(f"  {'─' * 50}")
        for btype, binfo in sorted(buckets.items()):
            tokens = binfo.get("tokens", 0)
            rate = binfo.get("rate", 0)
            dropped = binfo.get("dropped", 0)
            status_icon = "🟢" if tokens > 1 else "🟡" if tokens > 0 else "🔴"
            print(f"  {status_icon} {btype:<25s} {tokens:>7.1f} tokens  "
                  f"rate={rate:.1f}/s  dropped={dropped}")
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
            sig = "🔏" if ev.get("signature") else "  "
            print(f"     {ev['event_type']:30s} "
                  f"prio={ev['priority']} "
                  f"id={ev['event_id'][:8]} "
                  f"{sig}")
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

    # 默认参数 (含 I4 新增)
    defaults = {
        "dedup_window_seconds": 300,
        "max_retries": 3,
        "max_history": 2000,
        "loop1_enabled": True,
        "loop2_enabled": False,
        "loop3_enabled": False,
        "loop4_enabled": False,
        "log_level": "INFO",
        # I4 生产加固参数
        "source_validation_enabled": True,
        "rate_limit_enabled": True,
        "rate_limit_default": 50.0,
        "dead_letter_max_retries": 3,
        "dead_letter_backoff": 2.0,
        "audit_max_entries": 5000,
    }

    merged = {**defaults, **config}

    print(f"  {'Parameter':<30s} {'Value':<20s} {'Source':<10s}")
    print(f"  {'─' * 60}")
    for key, default_val in defaults.items():
        current = merged.get(key, default_val)
        source = "file" if key in config else "default"
        print(f"  {key:<30s} {str(current):<20s} {source:<10s}")

    print()


def cmd_dead_letter(args):
    """`yuleosh loop dead-letter` — 死信队列管理 (I4)。"""
    sub = args.dl_sub

    if sub == "list":
        limit = getattr(args, "limit", 50)
        entries = loop_bus.dead_letter.list(limit=limit)

        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
            return

        if not entries:
            print("\n  ✅ Dead letter queue is empty.\n")
            return

        print(f"\n  💀 Dead Letter Queue ({len(entries)} entries):")
        print(f"  {'=' * 65}")
        print(f"  {'Event ID':<12s} {'Type':<22s} {'Source':<15s} {'Retry':<6s} {'Reason'}")
        print(f"  {'─' * 65}")
        for entry in entries:
            eid = entry.get("event_id", "?")[:10]
            etype = entry.get("event_type", "?")
            src = entry.get("source", "?")
            retry = f"{entry.get('retry_count', 0)}/{entry.get('max_retries', 3)}"
            reason = entry.get("failure_reason", "")[:30]
            print(f"  {eid:<12s} {etype:<22s} {src:<15s} {retry:<6s} {reason}")
        print()

    elif sub == "retry":
        count = loop_bus.dead_letter.count()
        if count == 0:
            print("\n  ✅ Dead letter queue is empty, nothing to retry.\n")
            return

        print(f"\n  🔄 Retrying {count} dead letter events...")

        def retry_callback(entry):
            """重试回调 — 重新发布事件到总线。"""
            event_type = LoopEventType(entry["event_type"])
            loop_bus.emit(
                event_type,
                source=entry.get("source", "dlq_retry"),
                data=entry.get("data", {}),
                priority=entry.get("priority", 5),
            )

        success, failed = loop_bus.dead_letter.retry_all(retry_callback)
        remaining = loop_bus.dead_letter.count()

        print(f"  ✅ Retry complete: {success} succeeded, "
              f"{failed} failed, {remaining} remaining\n")

    elif sub == "clear":
        count = loop_bus.dead_letter.count()
        cleared = loop_bus.dead_letter.clear()
        print(f"\n  🗑️  Cleared {cleared} entries from dead letter queue.\n")


def cmd_audit(args):
    """`yuleosh loop audit` — 审计日志查询 (I4)。"""
    sub = args.audit_sub

    if sub == "list":
        limit = getattr(args, "limit", 50)
        event_type = getattr(args, "event_type", None)
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)

        entries = loop_bus.audit_log.list(
            limit=limit,
            event_type=event_type,
            since=since,
            until=until,
        )

        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
            return

        # 显示过滤条件摘要
        filters = []
        if event_type:
            filters.append(f"type={event_type}")
        if since:
            filters.append(f"since={since}")
        if until:
            filters.append(f"until={until}")

        if not entries:
            filter_str = " (" + ", ".join(filters) + ")" if filters else ""
            print(f"\n  📋 No audit records{filter_str}.\n")
            return

        header_info = f" (filter: {', '.join(filters)})" if filters else ""
        print(f"\n  📋 Audit Log (last {len(entries)} entries{header_info}):")
        print(f"  {'=' * 80}")
        print(f"  {'Event ID':<12s} {'Type':<22s} {'Source':<14s} {'Prio':<5s} "
              f"{'Retry':<6s} {'Rollback':<18s}")
        print(f"  {'─' * 80}")
        for entry in entries:
            eid = entry.get("event_id", "?")[:10]
            etype = entry.get("event_type", "?")
            src = entry.get("source", "?")
            prio = str(entry.get("priority", "?"))
            retry = str(entry.get("retry_count", 0))
            rb = entry.get("rollback_status", "")[:16]
            print(f"  {eid:<12s} {etype:<22s} {src:<14s} {prio:<5s} "
                  f"{retry:<6s} {rb:<18s}")
        print()

    elif sub == "query":
        event_id = args.event_id
        entry = loop_bus.audit_log.query(event_id)

        if args.json:
            print(json.dumps(entry, indent=2, ensure_ascii=False, default=str)
                  if entry else "{}")
            return

        if not entry:
            print(f"\n  ❌ Audit entry not found: {event_id}\n")
            return

        print(f"\n  📋 Audit Entry: {event_id}")
        print(f"  {'=' * 50}")
        print(f"  Event Type:      {entry.get('event_type', '?')}")
        print(f"  Source:          {entry.get('source', '?')}")
        print(f"  Priority:        {entry.get('priority', '?')}")
        print(f"  Timestamp:       {entry.get('timestamp', '?')}")
        print(f"  Retry Count:     {entry.get('retry_count', 0)}")
        print(f"  Rollback Status: {entry.get('rollback_status', '?')}")
        print(f"  Fingerprint:     {entry.get('source_fingerprint', '?')}")
        print(f"  Signature:       {entry.get('signature', '?')[:20]}...")

        hr = entry.get("handler_results", [])
        if hr:
            print(f"  Handler Results:")
            for r in hr:
                status = r.get("status", "?")
                icon = "✅" if status == "success" else "❌"
                hname = r.get("handler", "?")
                print(f"    {icon} {hname}: {status}")
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

    # ── I4: loop dead-letter ──
    p_dl = lsub.add_parser("dead-letter", help="死信队列管理 (I4)")
    dlsub = p_dl.add_subparsers(dest="dl_sub", help="Dead letter subcommand")

    p_dl_list = dlsub.add_parser("list", help="查看死信队列")
    p_dl_list.add_argument("--limit", "-l", type=int, default=50,
                           help="Max entries to show")
    p_dl_list.add_argument("--json", action="store_true", help="Output as JSON")

    dlsub.add_parser("retry", help="重试死信事件")
    dlsub.add_parser("clear", help="清空死信队列")

    # ── I4: loop audit ──
    p_audit = lsub.add_parser("audit", help="审计日志查询 (I4)")
    asub = p_audit.add_subparsers(dest="audit_sub", help="Audit subcommand")

    p_audit_list = asub.add_parser("list", help="审计日志列表")
    p_audit_list.add_argument("--limit", "-l", type=int, default=50,
                              help="Max entries to show")
    p_audit_list.add_argument("--type", "-t", default=None,
                              dest="event_type",
                              help="Filter by event type (e.g. ci.failure)")
    p_audit_list.add_argument("--since", default=None,
                              help="ISO 8601 start time (e.g. 2026-07-17T00:00:00)")
    p_audit_list.add_argument("--until", default=None,
                              help="ISO 8601 end time (e.g. 2026-07-17T23:59:59)")
    p_audit_list.add_argument("--json", action="store_true", help="Output as JSON")

    p_audit_query = asub.add_parser("query", help="查询单条审计日志")
    p_audit_query.add_argument("event_id", help="Event ID to query")
    p_audit_query.add_argument("--json", action="store_true", help="Output as JSON")


def handle_loop_command(args):
    """Dispatch loop subcommands."""
    if args.loop_sub == "status":
        cmd_status(args)
    elif args.loop_sub == "run":
        cmd_run(args)
    elif args.loop_sub == "config":
        cmd_config(args)
    elif args.loop_sub == "dead-letter":
        cmd_dead_letter(args)
    elif args.loop_sub == "audit":
        cmd_audit(args)
    else:
        print("Usage: yuleosh loop {status|run|config|dead-letter|audit}")
        sys.exit(1)
