# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

    # kb lessons
    lessons_p = kb_sub.add_parser("lessons", help="List lessons learned")
    lessons_p.add_argument("--project", default="", help="Filter by project")
    lessons_p.add_argument("--severity", default="", choices=["", "low", "medium", "high", "critical"],
                          help="Filter by severity")
    lessons_p.add_argument("--limit", type=int, default=20, help="Max results")

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
            limit=args.limit,
        )
        total = store.count_lessons(
            project_id=args.project or None,
            severity=args.severity or None,
        )
        if not lessons:
            print("No lessons found.")
            return 0
        print(f"\n📝 Lessons Learned ({total} total)")
        print(f"{'='*70}")
        for l in lessons:
            sev_icon = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(l.severity, "⚪")
            proj = f" [{l.project_id}]" if l.project_id else ""
            print(f"\n  {sev_icon} [{l.id}] {l.title}{proj}")
            print(f"      Severity: {l.severity}")
            print(f"      Problem:  {l.problem[:120].replace(chr(10), ' ')}")
            print(f"      Solution: {l.solution[:120].replace(chr(10), ' ')}")
        print(f"\n{'='*70}\n")

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
    """Collect all .c/.h files under *src_dir* (absolute or relative)."""
    base = Path(src_dir)
    if not base.is_absolute() and project_root:
        base = Path(project_root) / src_dir
    if not base.exists():
        return []
    return [str(p) for p in base.rglob("*.[ch]") if p.is_file()]


def _run_cppcheck_for_ingest(files: list[str]) -> str:
    """Run cppcheck with MISRA addon and return raw output."""
    cmd = ["cppcheck", "--enable=all", "--suppress=missingIncludeSystem", "--addon=misra", "--language=c", "-q"] + files
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
