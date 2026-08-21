# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Knowledge Base CLI — integrated into yuleosh kb subcommand.

Usage:
    yuleosh kb list                    — List knowledge base articles
    yuleosh kb create --title "..."    — Create a KB article
    yuleosh kb search <query>          — Search articles
    yuleosh kb lessons                 — List lessons
    yuleosh kb fmea                    — List FMEA entries
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .store import KbStore


def build_lesson_subparser(subparsers):
    """Add the 'lesson' subcommand group (yuleosh lesson create / kb lesson create)."""
    lesson_p = subparsers.add_parser("lesson", help="Lessons learned commands (create from improvement ticket)")
    lesson_sub = lesson_p.add_subparsers(dest="lesson_sub", required=True)

    create_p = lesson_sub.add_parser("create", help="Create a Lesson from an improvement ticket (工单一键沉淀知识)")
    create_p.add_argument("--ticket", required=True,
                          help="Improvement ticket ID (e.g. IMP-2026-08-04-misra_vi)")
    create_p.add_argument("--req", default="", help="Requirement ID (e.g. REQ-xxx, optional)")
    create_p.add_argument("--title", default="",
                          help="Lesson title (default: ticket metric)")
    create_p.add_argument("--severity", default="",
                          choices=["", "low", "medium", "high", "critical"],
                          help="Severity (default: from ticket)")
    return lesson_p


def build_kb_subparser(subparsers):
    """Add the 'kb' subcommand parser."""
    kb_parser = subparsers.add_parser("kb", help="Knowledge base commands")
    kb_sub = kb_parser.add_subparsers(dest="kb_sub", required=True)

    # kb list
    list_p = kb_sub.add_parser("list", help="List knowledge base articles")
    list_p.add_argument("--limit", type=int, default=20, help="Max results")
    list_p.add_argument("--offset", type=int, default=0, help="Offset")

    # kb create
    create_p = kb_sub.add_parser("create", help="Create a KB article")
    create_p.add_argument("--title", required=True, help="Article title")
    create_p.add_argument("--content", default="", help="Article content (Markdown)")
    create_p.add_argument("--source", default="", help="Source (misra_analysis/manual/import)")
    create_p.add_argument("--source-ref", default="", help="Source reference")
    create_p.add_argument("--tags", default="", help="Comma-separated tags")

    # kb search
    search_p = kb_sub.add_parser("search", help="Search knowledge base")
    search_p.add_argument("query", help="Search query")
    search_p.add_argument("--limit", type=int, default=20, help="Max results")
    cleanup_p = kb_sub.add_parser("cleanup", help="Deduplicate articles by content hash (EI-M3A)")

    # kb lessons
    lessons_p = kb_sub.add_parser("lessons", help="List lessons learned")
    lessons_p.add_argument("--project", default="", help="Filter by project")
    lessons_p.add_argument("--severity", default="", choices=["", "low", "medium", "high", "critical"],
                          help="Filter by severity")
    lessons_p.add_argument("--ticket", default="", help="Filter by ticket ID (e.g. IMP-xxx)")
    lessons_p.add_argument("--limit", type=int, default=20, help="Max results")

    # kb lesson create — 从改进工单一键沉淀 Lesson（工单→知识闭环）
    build_lesson_subparser(kb_sub)

    # kb fmea
    fmea_p = kb_sub.add_parser("fmea", help="List FMEA entries")
    fmea_p.add_argument("--sort", default="rpn", choices=["rpn", "severity", "occurence", "detection", "created_at"],
                       help="Sort field")
    fmea_p.add_argument("--asc", action="store_true", help="Sort ascending")
    fmea_p.add_argument("--limit", type=int, default=20, help="Max results")

    # kb ingest-misra
    ingest_p = kb_sub.add_parser("ingest-misra", help="Run MISRA analysis and ingest violations into KB")
    ingest_p.add_argument("--files", nargs="*", default=None,
                          help="Source files to analyze (default: all .c/.h in src/)")
    ingest_p.add_argument("--input", default=None,
                          help="Read cppcheck output from file instead of running cppcheck")
    ingest_p.add_argument("--src-dir", default="src",
                          help="Source directory (default: src)")
    ingest_p.add_argument("--dry-run", action="store_true",
                          help="Print violations without writing to KB")

    return kb_parser


def handle_kb_command(args) -> int:
    """Dispatch the kb subcommand."""
    store = KbStore()

    if args.kb_sub == "list":
        articles = store.list_articles(limit=args.limit, offset=args.offset)
        total = store.count_articles()
        if not articles:
            print("No articles found.")
            return 0
        print(f"\n📚 Knowledge Base Articles ({total} total)")
        print(f"{'='*70}")
        for a in articles:
            tags = f" [{a.tags}]" if a.tags else ""
            src = f" ({a.source})" if a.source else ""
            print(f"\n  [{a.id}] {a.title}{tags}{src}")
            print(f"      {a.content[:120].replace(chr(10), ' ')}{'...' if len(a.content) > 120 else ''}")
            created = a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "?"
            print(f"      Created: {created}")
        print(f"\n{'='*70}")
        print(f"{total} article(s)\n")

    elif args.kb_sub == "create":
        article = store.create_article({
            "title": args.title,
            "content": args.content,
            "source": args.source,
            "source_ref": getattr(args, "source_ref", ""),
            "tags": args.tags,
        })
        print(f"✅ Article created: [{article.id}] {article.title}")

    elif args.kb_sub == "cleanup":
        # EI-M3A.3: 存量重复清理（content hash 去重 + 回填空 hash）
        result = store.cleanup_duplicate_articles()
        print(f"🧹 KB duplicate cleanup: before={result['articles_before']} "
              f"backfilled={result['backfilled']} removed={result['removed']} "
              f"kept={result['kept']}")

    elif args.kb_sub == "search":
        articles = store.list_articles(search=args.query, limit=args.limit)
        total = store.count_articles(search=args.query)
        if not articles:
            print(f"No results for '{args.query}'.")
            return 0
        print(f"\n🔍 Search results for '{args.query}' ({total} found)")
        print(f"{'='*70}")
        for a in articles:
            print(f"\n  [{a.id}] {a.title}  ({a.source})")
            preview = a.content[:150].replace("\n", " ")
            print(f"      {preview}{'...' if len(a.content) > 150 else ''}")
        print(f"\n{'='*70}\n")

    elif args.kb_sub == "lessons":
        lessons = store.list_lessons(
            project_id=args.project or None,
            severity=args.severity or None,
            ticket_id=getattr(args, "ticket", "") or None,
            limit=args.limit,
        )
        total = store.count_lessons(
            project_id=args.project or None,
            severity=args.severity or None,
            ticket_id=getattr(args, "ticket", "") or None,
        )
        if not lessons:
            print("No lessons found.")
            return 0
        print(f"\n📝 Lessons Learned ({total} total)")
        print(f"{'='*70}")
        for l in lessons:
            sev_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(l.severity, "⚪")
            proj = f" [{l.project_id}]" if l.project_id else ""
            ticket_link = f" [ticket: {l.ticket_id}]" if l.ticket_id else ""
            req_link = f" [req: {l.requirement_id}]" if l.requirement_id else ""
            print(f"\n  {sev_icon} [{l.id}] {l.title}{proj}{ticket_link}{req_link}")
            print(f"      Severity: {l.severity}")
            print(f"      Problem:  {l.problem[:120].replace(chr(10), ' ')}")
            print(f"      Solution: {l.solution[:120].replace(chr(10), ' ')}")
        print(f"\n{'='*70}\n")

    elif args.kb_sub == "lesson":
        return handle_lesson_command(args)

    elif args.kb_sub == "fmea":
        entries = store.list_fmea(
            sort_by=args.sort,
            sort_desc=not args.asc,
            limit=args.limit,
        )
        total = store.count_fmea()
        if not entries:
            print("No FMEA entries found.")
            return 0
        print(f"\n⚠️  FMEA Entries ({total} total, sorted by {args.sort})")
        print(f"{'='*70}")
        for e in entries:
            print(f"\n  [{e.id}] {e.item}")
            print(f"      Failure: {e.failure_mode[:80]}")
            print(f"      Effect:  {e.effect[:80]}")
            print(f"      S:{e.severity} O:{e.occurence} D:{e.detection}  RPN: {e.rpn}")
        print(f"\n{'='*70}\n")

    elif args.kb_sub == "ingest-misra":
        return _handle_ingest_misra(args, store)

    return 0


# ── Lesson create — 工单一键沉淀知识 ──────────────────────────────────

def _resolve_ticket_path(ticket_id: str) -> Path:
    """定位 improvement_tickets/{ticket_id}.yaml。

    搜索顺序：OSH_HOME 环境变量 → 当前工作目录 → 仓库根（本文件上溯 4 层）。
    """
    candidates = []
    osh_home = os.environ.get("OSH_HOME")
    if osh_home:
        candidates.append(Path(osh_home) / "improvement_tickets" / f"{ticket_id}.yaml")
    candidates.append(Path.cwd() / "improvement_tickets" / f"{ticket_id}.yaml")
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates.append(repo_root / "improvement_tickets" / f"{ticket_id}.yaml")
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _load_ticket(ticket_id: str) -> dict:
    """从 improvement_tickets/{ticket_id}.yaml 读取工单，返回 improvement_ticket 字段 dict。

    Raises:
        FileNotFoundError: 工单文件不存在。
        ValueError: YAML 解析失败或缺少 improvement_ticket 节点。
    """
    import yaml
    path = _resolve_ticket_path(ticket_id)
    if not path.exists():
        raise FileNotFoundError(
            f"工单不存在: {path}（预期位置 improvement_tickets/{ticket_id}.yaml）"
        )
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"工单 YAML 解析失败: {path}: {exc}") from exc
    ticket = data.get("improvement_ticket") if isinstance(data, dict) else None
    if not isinstance(ticket, dict):
        raise ValueError(f"工单缺少 improvement_ticket 节点: {path}")
    return ticket


def handle_lesson_command(args) -> int:
    """Dispatch the top-level 'lesson' subcommand (or kb lesson)."""
    if getattr(args, "lesson_sub", None) == "create":
        return _handle_lesson_create(args)
    print("Usage: yuleosh lesson create --ticket IMP-xxx [--req REQ-xxx] [--title ...] [--severity ...]")
    return 1


def _handle_lesson_create(args) -> int:
    """Create a Lesson from an improvement ticket (工单一键沉淀知识)."""
    store = KbStore()
    ticket_id = args.ticket
    try:
        ticket = _load_ticket(ticket_id)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    # 工单字段 → Lesson 字段映射
    title = args.title or ticket.get("metric") or ticket_id
    severity = args.severity or ticket.get("severity", "medium")
    requirement_id = args.req or ticket.get("requirement_id", "")

    lesson = store.create_lesson({
        "title": title,
        "problem": ticket.get("problem_description", ""),
        "solution": ticket.get("recommended_actions", ""),
        "root_cause": ticket.get("root_cause", ""),
        "severity": severity,
        "ticket_id": ticket_id,
        "requirement_id": requirement_id,
    })

    print(f"✅ Lesson created: [{lesson.id}] {lesson.title}")
    print(f"   🎫 关联工单: {ticket_id}")
    if requirement_id:
        print(f"   📎 关联需求: {requirement_id}")
    if str(ticket.get("status", "")).lower() == "closed":
        print("   ♻️  已从 closed 工单沉淀（工单已闭环，知识已归档）")

    # 方案 B (2026-08-07): lesson 沉淀 → 自动入"待生效"知识索引。
    try:
        from yuleosh.knowledge.indexer import KnowledgeIndexer

        entry = KnowledgeIndexer().record(
            kind="lesson_create",
            content=f"[Lesson {lesson.id}] {title}: {lesson.solution or lesson.problem}",
            source=f"ticket:{ticket_id}",
            meta={"ticket_id": ticket_id, "requirement_id": requirement_id},
        )
        if entry:
            print(f"   📥 已自动入待生效知识索引 (hash={entry['hash']})")
            print("      → yuleosh knowledge approve <hash> 确认注入")
    except Exception as e:  # noqa: BLE001 — 沉淀 hook 永不阻塞 lesson 创建
        import logging as _logging

        _logging.getLogger("yuleosh.kb.cli").warning(
            "Knowledge indexer hook failed (non-fatal): %s", e
        )
    return 0


# ── Ingest MISRA ─────────────────────────────────────────────────────────


CPPCHECK_TO_MISRA_MAP: dict[str, str] = {
    # cppcheck diagnostic ID → MISRA C:2023 rule ID
    "staticness":           "misra-c2023-8.7",    # Functions should have static linkage
    "unusedFunction":       "misra-c2023-2.7",    # Source code shall not contain uncalled functions
    "unusedStructMember":   "misra-c2023-2.3",    # Unused type declarations
    "unusedVariable":       "misra-c2023-2.4",    # Unused tag declarations/symbols
    "unusedLabel":         "misra-c2023-2.6",    # Unreferenced labels
    "variableScope":       "misra-c2023-8.8",    # Static storage class specifier
    "constParameter":      "misra-c2023-8.13",   # const-qualified pointer parameters
    "constVariable":       "misra-c2023-8.13",   # const-qualification
    "shadowVariable":      "misra-c2023-5.10",   # Identifier hiding / shadow
    "shadowFunction":      "misra-c2023-5.1",    # Identifier distinctness
    "redundantAssignment": "misra-c2023-2.2",    # Dead code / unreachable
    "nullPointer":         "misra-c2023-18.6",   # Array indexing bounds
    "arrayIndexOutOfBounds": "misra-c2023-18.6", # Bounds checking
    "bufferAccessOutOfBounds": "misra-c2023-18.6",
    "noConstructor":       "misra-c2023-9.1",    # Uninitialized variables
    "uninitvar":           "misra-c2023-9.1",    # Uninitialized variable
    "uninitStructMember":  "misra-c2023-9.1",
    "knownConditionTrueFalse": "misra-c2023-14.3",  # Controlling expression invariant
    "shiftTooManyBits":    "misra-c2023-10.1",   # Inappropriate operand type
    "integerOverflow":     "misra-c2023-10.3",   # Complex integer narrowing
    "signConversion":      "misra-c2023-10.4",   # Signed/unsigned mismatch
    "unsignedLessThanZero": "misra-c2023-10.4",
    "pointerArith":        "misra-c2023-18.4",   # Pointer arithmetic
    "nullDefaultRef":      "misra-c2023-15.1",   # Control flow
    "redundantCondition":  "misra-c2023-14.3",   # Invariant condition
    "funcArgOrder":        "misra-c2023-17.1",   # Function parameter count
    "returnValue":         "misra-c2023-17.7",   # Return value must be used
    "missingReturn":       "misra-c2023-17.7",
    "leakFreeReturn":      "misra-c2023-22.1",   # Dynamic memory
    "memleak":             "misra-c2023-22.1",
    "duplicateBreak":      "misra-c2023-15.4",   # Single exit point
    "multiCondition":      "misra-c2023-13.2",   # Side effect in expression
    "suspiciousSemicolon": "misra-c2023-15.6",   # if-else termination
    "switchCaseFallthrough": "misra-c2023-16.4",  # break in switch
    "variableHidingEnum":  "misra-c2023-5.6",    # typedef uniqueness
    "noAssignmentOperator":"misra-c2023-13.3",   # Discarded side-effect expression
    "readWriteOnly":       "misra-c2023-2.2",    # Dead code
    "functionConst":       "misra-c2023-8.13",   # const parameters
    "mismatchAllocation":  "misra-c2023-22.1",   # Dynamic memory
    "badBitmaskCheck":     "misra-c2023-12.1",   # Operator precedence
}


def _parse_cppcheck_output(text: str) -> list[dict]:
    """
    Parse cppcheck plain-text output into violation dicts.
    
    Supports:
      - file:line:col: severity: message [diagnostic_id]
      - file:line: severity: message [diagnostic_id]
      - [file:line] (severity) message
    
    Non-violation lines (Active checkers, checkers report, summary) are filtered.
    Lines with known cppcheck diagnostic IDs are mapped to MISRA rules.
    """
    import re
    violations: list[dict] = []
    
    # Skip non-violation lines early
    skip_patterns = [
        r"Active checkers:",
        r"checkersReport",
        r"^$",
        r"Checking ",
        r"^\(information\)",
        r"nofile:",
        r"Defines:",
        r"Include paths:",
        r"^cppcheck:",
        r"^# ",
    ]
    skip_re = re.compile("(" + "|".join(skip_patterns) + ")", re.IGNORECASE)
    
    # Two main formats:
    # 1) [file:line:col] (severity) message   (bracketed)
    # 2) file:line[:col]: severity: message   (colon-separated, col optional)
    pattern_colon = re.compile(
        r"^(?P<file>[^:\n]+):(?P<line>\d+)"
        r"(?::(?P<col>\d+))?:"                     # optional column
        r"\s*(?P<severity>[^:]+):\s+"
        r"(?P<msg>.+)$",
        re.MULTILINE,
    )
    pattern_bracket = re.compile(
        r"^\[(?P<file>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?\]"
        r"\s*\((?P<severity>[^)]+)\)\s+"
        r"(?P<msg>.+)$",
        re.MULTILINE,
    )
    
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if skip_re.search(line):
            continue
        
        m = pattern_colon.match(line) or pattern_bracket.match(line)
        if not m:
            continue
        
        file_path = m.group("file")
        line_num = int(m.group("line"))
        col_num = int(m.group("col")) if m.group("col") else 0
        severity = m.group("severity").strip().lower()
        message = m.group("msg").strip()
        
        rule_id = _extract_rule_id(message)
        if not rule_id:
            # Still check if there's a cppcheck diagnostic ID in brackets
            diag_m = re.search(r"\[(\w+)\]$", message)
            if diag_m:
                diag_id = diag_m.group(1)
                rule_id = CPPCHECK_TO_MISRA_MAP.get(diag_id)
        
        if not rule_id:
            continue  # skip lines that can't be mapped
        
        violations.append({
            "rule_id": rule_id,
            "file": file_path,
            "line": line_num,
            "col": col_num,
            "severity": severity,
            "message": message,
        })
    
    return violations


def _extract_rule_id(message: str) -> str | None:
    """Extract MISRA rule ID from a cppcheck MISRA addon message.
    
    Handles formats:
      - [misra-c2012-17.7] → misra-c2023-17.7
      - [misra-c2023-17.7] → misra-c2023-17.7
      - (17.7) or (dir-4.2) → misra-c2023-17.7 / misra-c2023-dir-4.2
      - MISRA C2012-17.7 / MISRA-17.7 / Rule 17.7 → misra-c2023-17.7
    """
    import re
    
    # 1) [misra-c2012-17.7] or [misra-c2023-17.7] bracket style
    m = re.search(r"\[misra-c20(?:12|23)-(.+?)\]", message, re.IGNORECASE)
    if m:
        raw = m.group(1)
        if raw.startswith("dir-"):
            return f"misra-c2023-{raw}"
        return f"misra-c2023-{raw}"
    
    # 2) (17.7) paren style
    m = re.search(r"\((\d+\.\d+)\)", message)
    if m:
        return f"misra-c2023-{m.group(1)}"
    
    # 3) (dir-4.2) paren style
    m = re.search(r"\(dir-(\d+\.\d+)\)", message, re.IGNORECASE)
    if m:
        return f"misra-c2023-dir-{m.group(1)}"
    
    # 4) MISRA C2012-17.7 / MISRA-17.7 / Rule 17.7 text style
    m = re.search(r"MISRA[- ]?(?:C(?:\d{4})?)?[-.]?(\d+\.\d+)", message, re.IGNORECASE)
    if m:
        return f"misra-c2023-{m.group(1)}"
    
    # 5) MISRA dir-4.x text style
    m = re.search(r"MISRA[- ]?dir[-.]?(\d+\.\d+)", message, re.IGNORECASE)
    if m:
        return f"misra-c2023-dir-{m.group(1)}"
    
    # 6) Rule 17.7 / Rule: 17.7
    m = re.search(r"Rule[- :]+(\d+(?:\.\d+)?)", message, re.IGNORECASE)
    if m:
        num = m.group(1)
        if "." in num:
            return f"misra-c2023-{num}"
        return f"misra-c2023-{num}.0"  # Fallback for integer rules
    
    return None


def _classify_misra_category(rule_id: str | None) -> str:
    if rule_id is None:
        return "advisory"
    # Try to extract the numeric part (e.g., "misra-c2023-17.7" → "17.7")
    import re
    m = re.search(r"(\d+\.\d+)", rule_id)
    if not m:
        return "advisory"
    try:
        num = float(m.group(1))
    except ValueError:
        return "advisory"
    return "required" if num < 15.0 else "advisory"


def _collect_source_files(src_dir: str, project_root: str | None = None) -> list[str]:
    """Collect all .c/.h/.cpp files under *src_dir* (absolute or relative).

    C++ 泛化 (2026-08-21 A1 dogfood): 原 `*.[ch]` glob 不匹配 .cpp。
    """
    base = Path(src_dir)
    if not base.is_absolute() and project_root:
        base = Path(project_root) / src_dir
    if not base.exists():
        return []
    files = [str(p) for p in base.rglob("*.c") if p.is_file()]
    files += [str(p) for p in base.rglob("*.h") if p.is_file()]
    files += [str(p) for p in base.rglob("*.cpp") if p.is_file()]
    files += [str(p) for p in base.rglob("*.hpp") if p.is_file()]
    return files


def _run_cppcheck_for_ingest(files: list[str]) -> str:
    """Run cppcheck with MISRA addon and return raw output."""
    # C++ 泛化 (2026-08-21): 含 .cpp 文件时用 C++ 语言模式, 避免 syntaxError 误报
    has_cpp = any(f.endswith((".cpp", ".cc", ".cxx", ".c++")) for f in files)
    lang = "c++" if has_cpp else "c"
    cmd = ["cppcheck", "--enable=all", "--suppress=missingIncludeSystem", "--addon=misra", f"--language={lang}", "-q"] + files
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        return result.stderr + "\n" + result.stdout
    except FileNotFoundError:
        print("⚠️  cppcheck not found. Install it or use --input to provide a report file.", file=sys.stderr)
        return ""
    except subprocess.TimeoutExpired:
        print("⚠️  cppcheck timed out.", file=sys.stderr)
        return ""


def _handle_ingest_misra(args, store: KbStore) -> int:
    """Handle the 'kb ingest-misra' subcommand."""
    # Determine source directory
    project_root = os.environ.get("OSH_HOME", os.getcwd())

    # 1. Get violation data
    if args.input:
        # Read from file
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"❌ Input file not found: {args.input}", file=sys.stderr)
            return 1
        raw_output = input_path.read_text()
        print(f"📄 Read MISRA report from {args.input}")
    else:
        # Run cppcheck
        if args.files:
            files = args.files
        else:
            src_dir = args.src_dir
            files = _collect_source_files(src_dir, project_root)

        if not files:
            print(f"❌ No source files found in '{args.src_dir}'.", file=sys.stderr)
            return 1

        print(f"🔍 Running cppcheck MISRA analysis on {len(files)} file(s)...")
        raw_output = _run_cppcheck_for_ingest(files)
        if not raw_output:
            return 1

    # 2. Parse violations
    violations = _parse_cppcheck_output(raw_output)

    if not violations:
        print("✅ No MISRA violations found.")
        return 0

    print(f"\n📊 Found {len(violations)} MISRA violation(s):")
    for v in violations:
        rid = v.get("rule_id") or "?"
        print(f"  [{rid}] {v['file']}:{v['line']}  {v['message'][:100]}")

    # 3. Write to KB (or dry-run)
    if args.dry_run:
        print("\n🏁 Dry-run mode. Skipping KB write.")
        return 0

    created = 0
    for v in violations:
        rule_id = v.get("rule_id") or "unknown"
        tag = _classify_misra_category(rule_id)
        tags = f"misra,{tag}"
        if rule_id != "unknown":
            tags += f",rule-{rule_id.replace('.', '-')}"

        store.create_article({
            "title": f"MISRA-{rule_id}: {v.get('message', '')[:80]}",
            "content": (
                f"## MISRA Violation: Rule {rule_id}\n\n"
                f"**File:** `{v.get('file', '')}`\n"
                f"**Line:** {v.get('line', 0)}\n"
                f"**Severity:** {v.get('severity', '')}\n"
                f"**Message:** {v.get('message', '')}\n"
                f"\n---\n*Ingested by `yuleosh kb ingest-misra`*"
            ),
            "source": "misra_analysis",
            "source_ref": f"{v.get('file', '')}:{v.get('line', 0)}",
            "tags": tags,
        })
        created += 1

    print(f"\n📚 Ingested {created} violation(s) into Knowledge Base.")
    print(f"🏷️  Tags applied: misra, required/advisory, rule-*")
    return 0


# ── Direct CLI entry point (for testing) ────────────────────────────────

def main():
    """Direct CLI entry for testing: python -m yuleosh.kb.cli <args>."""
    parser = argparse.ArgumentParser(description="Knowledge Base CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    build_kb_subparser(sub)
    args = parser.parse_args()
    sys.exit(handle_kb_command(args))


if __name__ == "__main__":
    main()
