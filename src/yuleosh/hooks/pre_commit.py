# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Pre-commit hook — run MISRA cppcheck on staged .c/.h files.

Behaviour:
1. Detect whether CWD is inside a yuleOSH project (looks for .yuleosh/ or yuleosh.yaml).
2. Gather staged .c/.h files via `git diff --cached --name-only --diff-filter=ACM`.
3. Run cppcheck with MISRA addon on those files.
4. Compare violations against the previous commit's snapshot.
5. Warn about NEW violations (but do NOT block the commit).
6. Automatically persist a snapshot to .yuleosh/ci/last-misra-snapshot.json.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from yuleosh.kb.store import KbStore

log = logging.getLogger("yuleosh.hooks.pre_commit")

# ── helpers ─────────────────────────────────────────────────────────────

SNAPSHOT_RELPATH = ".yuleosh/ci/last-misra-snapshot.json"


def _is_yuleosh_project(cwd: str | Path) -> bool:
    """Check whether *cwd* (or any parent) is a yuleOSH project."""
    root = Path(cwd).resolve()
    for ancestor in [root] + list(root.parents):
        if (ancestor / ".yuleosh").is_dir():
            return True
        if (ancestor / "yuleosh.yaml").is_file():
            return True
    return False


def _get_staged_source_files() -> list[str]:
    """Return list of staged .c/.h files."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        log.warning("Failed to list staged files: %s", exc)
        return []

    files = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line.endswith((".c", ".h", ".cc", ".cpp", ".hpp")):
            files.append(line)
    return files


def _parse_cppcheck_violations(text: str) -> list[dict]:
    """Parse cppcheck text output into structured violation dicts.

    Supports both bracketed and legacy cppcheck formats.
    """
    import re

    violations: list[dict] = []
    # Bracketed: [file:line:col] (severity) message [rule]
    # Legacy:   file:line:col: severity: message
    pattern = re.compile(
        r"(?:"
        r"  \[(?P<file>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?\]\s*\((?P<severity>[^)]+)\)\s+"
        r"|"
        r"  (?P<file2>[^:\n]+):(?P<line2>\d+):(?P<col2>\d+):\s*(?P<severity2>[^:]+):\s+"
        r")"
        r"(?P<message>.+)$",
        re.MULTILINE | re.VERBOSE,
    )

    for match in pattern.finditer(text):
        raw_file = match.group("file") or match.group("file2") or ""
        line = int(match.group("line") or match.group("line2") or 0)
        col_str = match.group("col") or match.group("col2")
        column = int(col_str) if col_str else 0
        severity = (match.group("severity") or match.group("severity2") or "style").lower()
        message = match.group("message").strip()

        # Try extracting MISRA rule ID from message
        rule_id = _extract_rule_id(message)

        violations.append({
            "rule_id": rule_id,
            "file": raw_file,
            "line": line,
            "column": column,
            "severity": severity,
            "message": message,
        })

    return violations


def _extract_rule_id(message: str) -> Optional[str]:
    """Extract MISRA rule ID (e.g. '10.1', '12.3') from a cppcheck message."""
    import re
    # MISRA C2012-10.1, MISRA C-10.1, MISRA C10.1, MISRA 10.1
    m = re.search(r"MISRA[- ]?(?:C(?:\d{4})?)?[-.]?(\d+\.\d+)", message, re.IGNORECASE)
    if m:
        return m.group(1)
    # Rule-10.1, Rule 10.1
    m = re.search(r"Rule[- :]+(\d+(?:\.\d+)?)", message, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _run_cppcheck(files: list[str]) -> str:
    """Run cppcheck with MISRA addon on *files* and return raw stdout+stderr."""
    cmd = [
        "cppcheck",
        "--enable=all",
        "--suppress=missingIncludeSystem",
        "--addon=misra",
        "--language=c",
        "-q",
    ] + files

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=120,
        )
    except FileNotFoundError:
        log.warning("cppcheck not found — skipping MISRA analysis")
        return ""
    except subprocess.TimeoutExpired:
        log.warning("cppcheck timed out — skipping MISRA analysis")
        return ""

    # cppcheck outputs violations to stderr
    return result.stderr + "\n" + result.stdout


def _load_last_snapshot(project_root: Path) -> list[dict]:
    """Load previously persisted violation snapshot, or return empty list."""
    snap_path = project_root / SNAPSHOT_RELPATH
    if snap_path.exists():
        try:
            return json.loads(snap_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_snapshot(project_root: Path, violations: list[dict]):
    """Persist current violation snapshot to disk."""
    snap_path = project_root / SNAPSHOT_RELPATH
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(violations, indent=2, ensure_ascii=False))


def _classify_misra_category(rule_id: Optional[str]) -> str:
    """Guess MISRA category (required/advisory) by rule number ranges."""
    if rule_id is None:
        return "advisory"
    try:
        num = float(rule_id)
    except ValueError:
        return "advisory"
    # Rules under 15 are typically "required" in MISRA C:2012
    if num < 15.0:
        return "required"
    return "advisory"


def _create_kb_entries(store: KbStore, violations: list[dict]):
    """Create KB articles for each violation that doesn't already exist."""
    for v in violations:
        rule_id = v.get("rule_id") or "unknown"
        title = f"MISRA-{rule_id}: {v.get('message', '')[:80]}"
        tag = _classify_misra_category(rule_id)
        tags = f"misra,{tag}"
        if rule_id != "unknown":
            tags += f",rule-{rule_id.replace('.', '-')}"

        store.create_article({
            "title": title,
            "content": (
                f"## MISRA Violation: Rule {rule_id}\n\n"
                f"**File:** `{v.get('file', '')}`\n"
                f"**Line:** {v.get('line', 0)}\n"
                f"**Severity:** {v.get('severity', '')}\n"
                f"**Message:** {v.get('message', '')}\n"
            ),
            "source": "misra_analysis",
            "source_ref": f"{v.get('file', '')}:{v.get('line', 0)}",
            "tags": tags,
        })


def _find_new_violations(current: list[dict], last: list[dict]) -> list[dict]:
    """Return violations in *current* that are NOT in *last*.

    Comparison key: (rule_id, file, line).
    """
    last_set: set[tuple] = {
        (v.get("rule_id", ""), v.get("file", ""), v.get("line", 0))
        for v in last
    }
    return [
        v for v in current
        if (v.get("rule_id", ""), v.get("file", ""), v.get("line", 0)) not in last_set
    ]


# ── main entry ──────────────────────────────────────────────────────────

def run_pre_commit(cwd: Optional[str] = None) -> int:
    """Run the pre-commit hook. Returns 0 (always non-blocking)."""
    if cwd is None:
        cwd = os.getcwd()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # 1. Detect yuleOSH project
    if not _is_yuleosh_project(cwd):
        # Not a yuleOSH project — skip silently
        return 0

    project_root = Path(cwd).resolve()

    # 2. Get staged source files
    staged = _get_staged_source_files()
    if not staged:
        return 0

    abs_staged = []
    for f in staged:
        p = project_root / f
        if p.exists():
            abs_staged.append(str(p))

    if not abs_staged:
        return 0

    # 3. Run cppcheck
    raw_output = _run_cppcheck(abs_staged)
    if not raw_output:
        return 0

    current = _parse_cppcheck_violations(raw_output)
    if not current:
        return 0

    print(f"\n🔍 MISRA analysis: {len(current)} violation(s) found in staged files.")
    for v in current:
        rid = v.get("rule_id") or "?"
        print(f"  - [{rid}] {v.get('file', '?')}:{v.get('line', 0)}  {v.get('message', '')[:100]}")

    # 4. Compare with last snapshot
    last = _load_last_snapshot(project_root)
    new_violations = _find_new_violations(current, last)

    if new_violations:
        print(f"\n⚠️  {len(new_violations)} NEW violation(s) detected (not present in last commit):")
        for v in new_violations:
            rid = v.get("rule_id") or "?"
            print(f"  ⚡ [{rid}] {v.get('file', '?')}:{v.get('line', 0)}  {v.get('message', '')[:100]}")
        print("\nℹ️  Pre-commit hook does NOT block commits. Please review new violations.")
    else:
        print("✅ No new violations compared to last snapshot.")

    # 5. Persist snapshot
    _save_snapshot(project_root, current)

    # 6. Create KB entries (best-effort)
    try:
        store = KbStore()
        # Only create for new violations to avoid spam
        _create_kb_entries(store, new_violations)
        if new_violations:
            print(f"📚 Created {len(new_violations)} KB article(s) for new violations.")
    except Exception as exc:
        log.warning("Failed to create KB entries: %s", exc)

    # Always return 0 — do NOT block the commit
    return 0


if __name__ == "__main__":
    sys.exit(run_pre_commit())
