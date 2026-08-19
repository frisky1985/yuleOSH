# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Memory CLI — fact store + session search + 反思蒸馏闭环.

Usage:
    yuleosh memory remember "fact" [--entity X] [--category Y] [--tags a,b] [--trust N]
    yuleosh memory recall <query> [--entity X] [--category Y] [--limit N]
    yuleosh memory forget <id>
    yuleosh memory list [--category Y] [--entity X] [--limit N]
    yuleosh memory stats
    yuleosh memory log "session note" [--key K] [--kind note|decision|review]
    yuleosh memory distill [--days N] [--project DIR] [--mock] [--dry-run]
    yuleosh memory reflect [--days N] [--project DIR] [--mock] [--max-age-days N] [--dry-run]
    yuleosh memory feedback --step <step_key> --status passed|failed|retry
    yuleosh session search <query> [--limit N]
"""

import argparse
import logging

from .store import MemoryStore

log = logging.getLogger("yuleosh.memory.cli")


def build_memory_subparser(subparsers) -> argparse.ArgumentParser:
    """Add the 'memory' subcommand parser."""
    mem = subparsers.add_parser("memory", help="Cross-session memory (fact store)")
    msub = mem.add_subparsers(dest="memory_sub", required=True)

    # memory remember
    p = msub.add_parser("remember", help="Remember a fact")
    p.add_argument("content", help="Fact content")
    p.add_argument("--entity", default="", help="Entity the fact is about")
    p.add_argument("--category", default="general",
                   help="Category (project/architecture/decision/…; default: general)")
    p.add_argument("--tags", default="", help="Comma-separated tags")
    p.add_argument("--trust", type=float, default=None,
                   help="Initial trust 0.0–1.0 (default: 0.5)")

    # memory recall
    p = msub.add_parser("recall", help="Recall facts matching a query")
    p.add_argument("query", help="Search text")
    p.add_argument("--entity", default=None, help="Filter by entity")
    p.add_argument("--category", default=None, help="Filter by category")
    p.add_argument("--limit", type=int, default=20, help="Max results")

    # memory forget
    p = msub.add_parser("forget", help="Delete a fact by id")
    p.add_argument("id", type=int, help="Fact id")

    # memory list
    p = msub.add_parser("list", help="List facts")
    p.add_argument("--category", default=None, help="Filter by category")
    p.add_argument("--entity", default=None, help="Filter by entity")
    p.add_argument("--limit", type=int, default=50, help="Max results")
    p.add_argument("--offset", type=int, default=0, help="Offset")

    # memory stats
    msub.add_parser("stats", help="Show memory statistics")

    # memory log
    p = msub.add_parser("log", help="Record a session/decision note (searchable)")
    p.add_argument("content", help="Note content")
    p.add_argument("--key", default="", help="Session key")
    p.add_argument("--kind", default="note",
                   choices=["note", "decision", "review"],
                   help="Note kind (default: note)")

    # memory context — preview of the context injected into LLM calls
    p = msub.add_parser(
        "context",
        help="Preview project-memory context injected into LLM calls",
    )
    p.add_argument("query", help="Search text")
    p.add_argument("--max-facts", type=int, default=5,
                   help="Max facts (default: 5)")
    p.add_argument("--max-sessions", type=int, default=3,
                   help="Max sessions (default: 3)")
    p.add_argument("--max-chars", type=int, default=2000,
                   help="Max context chars (default: 2000)")

    # memory distill — P1 反思蒸馏闭环：sessions → facts 落库
    p = msub.add_parser(
        "distill",
        help="蒸馏最近 N 天会话为结构化记忆（事实/经验/教训/纠正）",
    )
    p.add_argument("--days", type=int, default=1,
                   help="回看天数（default: 1）")
    p.add_argument("--project", default=".",
                   help="项目目录（读 sessions/ 与 .osh/sessions/，default: cwd）")
    p.add_argument("--mock", action="store_true",
                   help="确定性启发式抽取（无需 API key，演示/测试）")
    p.add_argument("--dry-run", action="store_true",
                   help="只报告不落库")

    # memory reflect — P2 反思器：冲突解决 + 过时归档
    p = msub.add_parser(
        "reflect",
        help="反思蒸馏候选 vs 现有记忆：冲突解决 + 过时归档",
    )
    p.add_argument("--days", type=int, default=1,
                   help="无候选文件时回看天数（default: 1）")
    p.add_argument("--project", default=".",
                   help="项目目录（default: cwd）")
    p.add_argument("--mock", action="store_true",
                   help="确定性启发式抽取（无候选文件时）")
    p.add_argument("--max-age-days", type=int, default=30,
                   help="过时归档阈值天数（default: 30）")
    p.add_argument("--dry-run", action="store_true",
                   help="只报告动作不执行")

    # memory feedback — P3 反馈环：步骤结果回采
    p = msub.add_parser(
        "feedback",
        help="步骤结果回采：调整该 step 注入过的事实 trust",
    )
    p.add_argument("--step", required=True, help="Pipeline step key")
    p.add_argument("--status", required=True,
                   choices=["passed", "failed", "retry"],
                   help="步骤结果")

    return mem


def handle_memory_command(args) -> int:
    """Dispatch the memory subcommand."""
    store = MemoryStore()

    if args.memory_sub == "remember":
        fact = store.remember(
            content=args.content,
            entity=args.entity,
            category=args.category,
            tags=args.tags,
            trust=args.trust,
        )
        print(f"✅ Remembered [#{fact['id']}] ({fact['category']}"
              f"{' / ' + fact['entity'] if fact['entity'] else ''})"
              f" trust={fact['trust']:.2f}")
        print(f"   {fact['content']}")

        # 方案 B (2026-08-07): memory 沉淀 → 自动入"待生效"知识索引。
        try:
            from yuleosh.knowledge.indexer import KnowledgeIndexer

            entry = KnowledgeIndexer().record(
                kind="memory_remember",
                content=fact["content"],
                source=f"fact:{fact['id']}",
                meta={"entity": fact.get("entity", ""), "category": fact.get("category", "")},
            )
            if entry:
                print(f"   📥 已自动入待生效知识索引 (hash={entry['hash']})")
                print("      → yuleosh knowledge approve <hash> 确认注入")
        except Exception as e:  # noqa: BLE001 — 沉淀 hook 永不阻塞 remember
            log.warning("Knowledge indexer hook failed (non-fatal): %s", e)

    elif args.memory_sub == "recall":
        facts = store.recall(args.query, entity=args.entity,
                             category=args.category, limit=args.limit)
        if not facts:
            print(f"🧠 No facts match '{args.query}'.")
            return 0
        print(f"🧠 Recalled {len(facts)} fact(s) for '{args.query}':")
        print("=" * 72)
        for f in facts:
            tags = f" [{f['tags']}]" if f["tags"] else ""
            ent = f" ({f['entity']})" if f["entity"] else ""
            print(f"\n  [#{f['id']}] {f['content']}{ent}{tags}")
            print(f"      category={f['category']} trust={f['trust']:.2f} "
                  f"recalls={f['recall_count']} updated={f['updated_at']}")
        print("=" * 72)

    elif args.memory_sub == "forget":
        if store.forget(args.id):
            print(f"🗑️  Forgotten fact #{args.id}.")
        else:
            print(f"⚠️  No fact with id {args.id}.")

    elif args.memory_sub == "list":
        facts = store.list_facts(category=args.category, entity=args.entity,
                                 limit=args.limit, offset=args.offset)
        if not facts:
            print("🧠 No facts stored yet. Use `yuleosh memory remember \"…\"`.")
            return 0
        print(f"🧠 Memory facts ({len(facts)} shown):")
        print("=" * 72)
        for f in facts:
            tags = f" [{f['tags']}]" if f["tags"] else ""
            ent = f" ({f['entity']})" if f["entity"] else ""
            print(f"\n  [#{f['id']}] {f['content']}{ent}{tags}")
            print(f"      category={f['category']} trust={f['trust']:.2f} "
                  f"recalls={f['recall_count']} updated={f['updated_at']}")
        print("=" * 72)

    elif args.memory_sub == "stats":
        st = store.stats()
        print("🧠 Memory statistics:")
        print(f"  Facts:     {st['facts']}")
        print(f"  Sessions:  {st['sessions']}")
        if st["by_category"]:
            print("  By category:")
            for cat, n in st["by_category"].items():
                print(f"    - {cat}: {n}")

    elif args.memory_sub == "log":
        entry = store.log_session(args.content, session_key=args.key,
                                  kind=args.kind)
        print(f"✅ Logged session note [#{entry['id']}] "
              f"kind={entry['kind']} at {entry['created_at']}")

    elif args.memory_sub == "context":
        from yuleosh.memory.llm_context import MemoryContextAssembler
        context = MemoryContextAssembler(
            max_facts=args.max_facts,
            max_sessions=args.max_sessions,
            max_chars=args.max_chars,
        ).assemble(args.query)
        if not context:
            print(f"🧠 No project memory context for '{args.query}'.")
            return 0
        print("🧠 Project memory context (injected into LLM system prompt):")
        print("=" * 72)
        print(context)
        print("=" * 72)
        print(f"(chars={len(context)}, max_chars={args.max_chars})")

    elif args.memory_sub == "distill":
        from yuleosh.memory.distill import Distiller, mock_distill_llm

        d = Distiller(
            llm_fn=mock_distill_llm if args.mock else None,
            project_dir=args.project,
        )
        summary = d.distill(days=args.days, dry_run=args.dry_run)
        mode = " [dry-run]" if args.dry_run else ""
        print(f"🧠 Distill{mode}: days={summary['days']} "
              f"chunks={summary['chunks']} "
              f"candidates={summary['candidates']} "
              f"inserted={summary['inserted']} "
              f"deduped={summary['deduped']}")
        if summary.get("note"):
            print(f"   ({summary['note']})")
        if summary["facts"]:
            print(f"   facts: {summary['facts']}")

    elif args.memory_sub == "reflect":
        from yuleosh.memory.distill import (
            Distiller,
            load_last_candidates,
            mock_distill_llm,
        )
        from yuleosh.memory.reflect import Reflector

        candidates = load_last_candidates(args.project)
        if not candidates:
            d = Distiller(
                llm_fn=mock_distill_llm if args.mock else None,
                project_dir=args.project,
            )
            candidates = d.extract_candidates(
                d.collect_session_texts(days=args.days), days=args.days)
        r = Reflector(project_dir=args.project)
        summary = r.reflect(candidates, max_age_days=args.max_age_days,
                            dry_run=args.dry_run)
        mode = " [dry-run]" if args.dry_run else ""
        print(f"🧠 Reflect{mode}: conflicts={summary['conflicts']} "
              f"obsolete={summary['obsolete']} actions={summary['actions']}")
        print(f"   applied: archived={summary['archived']} "
              f"inserted={summary['inserted']} "
              f"downgraded={summary['downgraded']}")

    elif args.memory_sub == "feedback":
        from yuleosh.memory.feedback import apply_step_result

        n = apply_step_result(args.step, args.status)
        print(f"🧠 Feedback: step={args.step} status={args.status} "
              f"settled={n} usage row(s)")

    return 0


def build_session_subparser(subparsers) -> argparse.ArgumentParser:
    """Add the 'session' subcommand parser."""
    sess = subparsers.add_parser("session", help="Session log search")
    ssub = sess.add_subparsers(dest="session_sub", required=True)

    p = ssub.add_parser("search", help="Full-text search over session logs")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", type=int, default=20, help="Max results")

    return sess


def handle_session_command(args) -> int:
    """Dispatch the session subcommand."""
    store = MemoryStore()

    if args.session_sub == "search":
        results = store.search_sessions(args.query, limit=args.limit)
        if not results:
            print(f"🔎 No session logs match '{args.query}'.")
            return 0
        print(f"🔎 {len(results)} session log(s) matching '{args.query}':")
        print("=" * 72)
        for r in results:
            print(f"\n  [#{r['id']}] ({r['kind']}) {r['session_key'] or 'default'}"
                  f" — {r['created_at']}")
            print(f"      {r['snippet']}")
        print("=" * 72)

    return 0
