# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Knowledge index CLI — ``yuleosh knowledge`` 子命令（方案 B, 2026-08-07）。

Usage:
    yuleosh knowledge pending             — 列出待生效沉淀（人工确认候选）
    yuleosh knowledge approve [hash|idx]  — 确认某条生效（或 --all）
    yuleosh knowledge reject [hash|idx]   — 否决某条（或 --all）
    yuleosh knowledge audit [--limit N]   — 查看 approve/reject 审计
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from yuleosh.knowledge.indexer import KnowledgeIndexer


def build_knowledge_subparser(subparsers) -> argparse.ArgumentParser:
    """Add the 'knowledge' subcommand parser."""
    p = subparsers.add_parser(
        "knowledge",
        help="沉淀知识索引 — 待生效/生效/审计（方案B）",
    )
    ksub = p.add_subparsers(dest="knowledge_sub", required=True)

    ksub.add_parser("pending", help="列出待生效沉淀（人工确认候选）")

    p_approve = ksub.add_parser("approve", help="人工确认沉淀生效（pending → active）")
    p_approve.add_argument("item", nargs="?", default=None,
                           help="条目 hash 或序号（缺省需 --all）")
    p_approve.add_argument("--all", action="store_true",
                           help="批准全部待生效条目")

    p_reject = ksub.add_parser("reject", help="否决待生效沉淀（不入 active）")
    p_reject.add_argument("item", nargs="?", default=None,
                          help="条目 hash 或序号（缺省需 --all）")
    p_reject.add_argument("--all", action="store_true",
                          help="否决全部待生效条目")

    p_audit = ksub.add_parser("audit", help="查看 approve/reject 审计日志")
    p_audit.add_argument("--limit", type=int, default=50, help="最大条数")
    return p


def handle_knowledge_command(args) -> int:
    """Dispatch the knowledge subcommand (returns exit code)."""
    indexer = KnowledgeIndexer(project_dir=getattr(args, "osh_home", None) or None)
    sub = getattr(args, "knowledge_sub", None)

    if sub == "pending":
        return _cmd_pending(indexer)
    if sub == "approve":
        return _cmd_approve(indexer, getattr(args, "item", None),
                            bool(getattr(args, "all", False)))
    if sub == "reject":
        return _cmd_reject(indexer, getattr(args, "item", None),
                           bool(getattr(args, "all", False)))
    if sub == "audit":
        return _cmd_audit(indexer, getattr(args, "limit", 50))
    print("Usage: yuleosh knowledge pending|approve|reject|audit", file=sys.stderr)
    return 2


def _cmd_pending(indexer: KnowledgeIndexer) -> int:
    items = indexer.list_pending()
    if not items:
        print("📭 没有待生效沉淀（knowledge-pending.json 为空）。")
        return 0
    print(f"\n📥 待生效沉淀（{len(items)} 条，人工确认后进入注入生效索引）")
    print("=" * 72)
    for i, item in enumerate(items):
        kind = item.get("kind", "?")
        content = str(item.get("content", "")).replace("\n", " ")[:120]
        print(f"\n  [{i}] ({kind}) {content}")
        print(f"      hash={item.get('hash')}  created={item.get('created_at')}")
    print(f"\n  yuleosh knowledge approve <hash> | --all   # 确认生效")
    print(f"  yuleosh knowledge reject  <hash> | --all   # 否决")
    print()
    return 0


def _cmd_approve(indexer: KnowledgeIndexer, item: Optional[str], all_: bool) -> int:
    if not all_ and not item:
        print("❌ 请指定条目（hash/序号）或 --all", file=sys.stderr)
        return 2
    count = indexer.approve(item_id=item, all_=all_)
    if count:
        print(f"✅ 已确认 {count} 条沉淀生效（进入 knowledge-active.json）。")
        return 0
    print("⚠️  没有匹配的待生效条目。")
    return 1


def _cmd_reject(indexer: KnowledgeIndexer, item: Optional[str], all_: bool) -> int:
    if not all_ and not item:
        print("❌ 请指定条目（hash/序号）或 --all", file=sys.stderr)
        return 2
    count = indexer.reject(item_id=item, all_=all_)
    if count:
        print(f"🗑️  已否决 {count} 条沉淀（未进入生效索引）。")
        return 0
    print("⚠️  没有匹配的待生效条目。")
    return 1


def _cmd_audit(indexer: KnowledgeIndexer, limit: int) -> int:
    entries = indexer.audit_log(limit=limit)
    if not entries:
        print("📋 审计日志为空（尚无 approve/reject 操作）。")
        return 0
    print(f"\n📋 知识索引审计（最近 {len(entries)} 条）")
    print("=" * 72)
    for e in entries:
        print(f"  [{e.get('ts')}] {e.get('action'):>7}  "
              f"({e.get('kind')}) {str(e.get('content',''))[:80]}")
    print()
    return 0
