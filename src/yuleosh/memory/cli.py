# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Memory CLI — fact store + session search.

Usage:
    yuleosh memory remember "fact" [--entity X] [--category Y] [--tags a,b] [--trust N]
    yuleosh memory recall <query> [--entity X] [--category Y] [--limit N]
    yuleosh memory forget <id>
    yuleosh memory list [--category Y] [--entity X] [--limit N]
    yuleosh memory stats
    yuleosh memory log "session note" [--key K] [--kind note|decision|review]
    yuleosh session search <query> [--limit N]
"""

import argparse

from .store import MemoryStore


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
