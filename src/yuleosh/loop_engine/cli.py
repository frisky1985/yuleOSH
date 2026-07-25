#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
yuleOSH Loop Engineering CLI — `yuleosh loop {status|run|config|dead-letter|audit|rollback}` (LE-007)。

提供统一的命令行接口来管理反馈回路：
  - `yuleosh loop status`       — 查看当前活跃的 loop 事件和状态
  - `yuleosh loop run <name>`   — 手动触发指定 loop
  - `yuleosh loop config`       — 查看/修改 loop 参数
  - `yuleosh loop dead-letter {list|retry|clear}` — 死信队列管理 (I4)
  - `yuleosh loop audit`        — 审计日志查询 (ACC-505)
  - `yuleosh loop rollback <journal_id>` — 回滚操作 (ACC-506)

Usage:
    yuleosh loop status
    yuleosh loop status --json
    yuleosh loop run loop1_defect_to_req --test test_foo --req RS-001
    yuleosh loop config
    yuleosh loop config --set dedup_window 600
    yuleosh loop dead-letter list
    yuleosh loop dead-letter retry
    yuleosh loop dead-letter clear
    yuleosh loop audit [--limit N] [--since DATETIME] [--handler HANDLER]
    yuleosh loop audit list [--limit N] [--handler HANDLER]
    yuleosh loop audit query <event_id>
    yuleosh loop rollback JRNL-20260717-001
"""

import argparse
import json
import logging
import os
import sys
import time

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
        old_value = None
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
        old_value = config.get(key)
        config[key] = parsed
        _save_config(config_path, config)
        print(f"\n  ✅ Config updated: {key} = {parsed!r}")
        print(f"     File: {config_path}\n")

        # ── B3 (ACC-605): 记录配置变更审计日志 ──
        try:
            details = {
                "key": key,
                "old_value": old_value,
                "new_value": parsed,
                "config_file": config_path,
            }
            loop_bus.audit_log.record_action(
                action="config_changed",
                actor="cli_user",
                handler_id="cli_user",
                result="success",
                details=details,
                duration_ms=0.0,
            )
            log.info("Audit: config_changed '%s' = %r (old: %r)", key, parsed, old_value)
        except Exception as e:
            log.warning("Audit record failed for config change: %s", e)

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
    """`yuleosh loop audit` — 审计日志查询 (ACC-505)。

    支持:
      - `yuleosh loop audit`             — 最近 50 条 (flat)
      - `yuleosh loop audit --limit 5`   — 最近 5 条
      - `yuleosh loop audit --since 2026-07-17T00:00:00 --handler Loop1DefectToReqHandler`
      - `yuleosh loop audit list`        — 同 flat
      - `yuleosh loop audit query <id>`  — 查询单条

    ACC-505 输出字段:
      timestamp, event_id, handler_id, action, result, duration_ms
    """
    sub = getattr(args, "audit_sub", None)

    if sub == "list" or sub is None:
        # 支持 flat `audit` 和 `audit list`
        limit = getattr(args, "limit", 50)
        event_type = getattr(args, "event_type", None)
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)
        handler_filter = getattr(args, "handler", None)

        entries = loop_bus.audit_log.list(
            limit=limit,
            event_type=event_type,
            since=since,
            until=until,
            handler=handler_filter,
        )

        if getattr(args, "json", False):
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
        if handler_filter:
            filters.append(f"handler={handler_filter}")

        if not entries:
            filter_str = " (" + ", ".join(filters) + ")" if filters else ""
            print(f"\n  📋 No audit records{filter_str}.\n")
            return

        header_info = f" (filter: {', '.join(filters)})" if filters else ""
        print(f"\n  📋 Audit Log (last {len(entries)} entries{header_info}):")
        # ACC-505 格式: timestamp, event_id, handler_id, action, result, duration_ms
        print(f"  {'=' * 100}")
        print(f"  {'Timestamp':<26s} {'Event ID':<12s} {'Handler ID':<32s} "
              f"{'Action':<20s} {'Result':<10s} {'Duration(ms)':<10s}")
        print(f"  {'─' * 100}")
        for entry in entries:
            ts = entry.get("timestamp", "?")
            eid = entry.get("event_id", "?")[:10]
            # 从 handler_results 中提取 handler_id
            hr = entry.get("handler_results", [])
            if hr:
                handler_id = hr[0].get("handler", "?")
            else:
                handler_id = entry.get("handler_id", "?")
            action = entry.get("action", "?")
            # 从 handler_results 提取 result
            if hr:
                result = hr[0].get("status", "?")
            else:
                result = entry.get("result", "?")
            duration_ms = entry.get("duration_ms", 0.0)
            duration_str = f"{duration_ms:.1f}" if isinstance(duration_ms, (int, float)) else str(duration_ms)

            print(f"  {ts:<26s} {eid:<12s} {handler_id:<32s} "
                  f"{action:<20s} {result:<10s} {duration_str:<10s}")
        print()

    elif sub == "query":
        event_id = args.event_id
        entry = loop_bus.audit_log.query(event_id)

        if getattr(args, "json", False):
            print(json.dumps(entry, indent=2, ensure_ascii=False, default=str)
                  if entry else "{}")
            return

        if not entry:
            print(f"\n  ❌ Audit entry not found: {event_id}\n")
            return

        print(f"\n  📋 Audit Entry: {event_id}")
        print(f"  {'=' * 50}")
        print(f"  Event Type:      {entry.get('event_type', '?')}")
        print(f"  Action:          {entry.get('action', '?')}")
        print(f"  Source:          {entry.get('source', '?')}")
        print(f"  Priority:        {entry.get('priority', '?')}")
        print(f"  Timestamp:       {entry.get('timestamp', '?')}")
        print(f"  Duration (ms):   {entry.get('duration_ms', 0.0)}")
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


def cmd_rollback(args):
    """`yuleosh loop rollback <journal_id>` — 回滚操作 (ACC-506)。

    查找持有该 journal_id 的 FeedbackHandler, 调用 rollback() 接口。
    回滚完成后追加审计日志 (ACC-606)。

    Args:
        journal_id: 要回滚的 journal 标识 (如 "JRNL-20260717-001")。
    """
    journal_id = args.journal_id
    engine = _build_engine()

    start_time = time.time()
    restored_entities: list[str] = []
    overall_success = True
    error_message = ""

    print(f"\n  🔄 Rollback: {journal_id}")
    print(f"  {'=' * 50}")

    # 遍历所有已注册 handler, 尝试回滚
    handlers = getattr(engine, '_handlers', {})
    if not handlers:
        engine = _build_engine()
        handlers = getattr(engine, '_handlers', {})

    if not handlers:
        print(f"  ⚠️  No registered handlers found.")
        overall_success = False
    else:
        for handler_name, handler in handlers.items():
            # 构造一个模拟事件, 携带 journal_id 用于回滚
            from yuleosh.loop_engine.event_bus import LoopEvent
            rollback_event = LoopEvent(
                event_type=LoopEventType.TEST_RESULT,  # 通用事件类型
                source="cli_rollback",
                data={
                    "journal_id": journal_id,
                    "reason": f"manual rollback of {journal_id}",
                },
                priority=0,  # 最高优先级
            )

            try:
                result = handler.rollback(rollback_event)
                if result.success:
                    restored_entities.append(handler_name)
                    print(f"    ✅ {handler_name}: rollback succeeded")
                    log.info("Rollback: %s succeeded for handler '%s'",
                             journal_id, handler_name)
                else:
                    overall_success = False
                    print(f"    ⏸️  {handler_name}: {result.action_taken}")
                    log.info("Rollback: %s skipped for '%s': %s",
                             journal_id, handler_name, result.action_taken)
            except Exception as e:
                overall_success = False
                error_message = str(e)
                print(f"    ❌ {handler_name}: rollback failed — {e}")
                log.warning("Rollback: %s failed for '%s': %s",
                            journal_id, handler_name, e)

    duration_ms = (time.time() - start_time) * 1000.0

    if overall_success and restored_entities:
        print(f"\n  ✅ Rollback complete: restored {len(restored_entities)} entity/entities")
    elif not restored_entities:
        print(f"\n  ⚠️  Rollback: no entities were restored")
    else:
        print(f"\n  ⚠️  Rollback completed with some failures")

    print(f"     Duration: {duration_ms:.1f} ms")

    # ── B4 (ACC-606): 记录回滚审计日志 ──
    try:
        details = {
            "journal_id": journal_id,
            "restored_entities": restored_entities,
            "error": error_message if not overall_success else "",
        }
        loop_bus.audit_log.record_action(
            action="rollback",
            actor="cli_user",
            handler_id="cli_user",
            result="success" if overall_success else "failure",
            details=details,
            duration_ms=duration_ms,
            journal_id=journal_id,
            restored_entities=restored_entities,
        )
        log.info("Audit: rollback '%s' recorded (%d entities restored)",
                 journal_id, len(restored_entities))
    except Exception as e:
        log.warning("Audit record failed for rollback: %s", e)

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

    # ── ACC-505: loop audit (支持 flat 模式 + list/query 子命令) ──
    p_audit = lsub.add_parser("audit", help="审计日志查询 (ACC-505)")
    asub = p_audit.add_subparsers(dest="audit_sub", help="Audit subcommand")

    p_audit_list = asub.add_parser("list", help="审计日志列表 (ACC-505)")
    p_audit_list.add_argument("--limit", "-l", type=int, default=50,
                              help="Max entries to show")
    p_audit_list.add_argument("--type", "-t", default=None,
                              dest="event_type",
                              help="Filter by event type (e.g. ci.failure)")
    p_audit_list.add_argument("--since", default=None,
                              help="ISO 8601 start time (e.g. 2026-07-17T00:00:00)")
    p_audit_list.add_argument("--until", default=None,
                              help="ISO 8601 end time (e.g. 2026-07-17T23:59:59)")
    p_audit_list.add_argument("--handler", default=None,
                              help="Filter by handler name (e.g. Loop1DefectToReqHandler)")
    p_audit_list.add_argument("--json", action="store_true", help="Output as JSON")

    p_audit_query = asub.add_parser("query", help="查询单条审计日志")
    p_audit_query.add_argument("event_id", help="Event ID to query")
    p_audit_query.add_argument("--json", action="store_true", help="Output as JSON")

    # Flat audit 模式 (无子命令) — 参数直接挂在 audit 上
    p_audit.add_argument("--limit", "-l", type=int, default=50,
                         help="Max entries to show")
    p_audit.add_argument("--type", "-t", default=None,
                         dest="event_type",
                         help="Filter by event type (e.g. ci.failure)")
    p_audit.add_argument("--since", default=None,
                         help="ISO 8601 start time (e.g. 2026-07-17T00:00:00)")
    p_audit.add_argument("--until", default=None,
                         help="ISO 8601 end time (e.g. 2026-07-17T23:59:59)")
    p_audit.add_argument("--handler", default=None,
                         help="Filter by handler name (e.g. Loop1DefectToReqHandler)")
    p_audit.add_argument("--json", action="store_true", help="Output as JSON")

    # ── ACC-506: loop rollback ──
    p_rollback = lsub.add_parser("rollback", help="回滚操作 (ACC-506)")
    p_rollback.add_argument("journal_id", help="Journal ID to roll back (e.g. JRNL-20260717-001)")


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
    elif args.loop_sub == "rollback":
        cmd_rollback(args)
    else:
        print("Usage: yuleosh loop {status|run|config|dead-letter|audit|rollback}")
        sys.exit(1)
