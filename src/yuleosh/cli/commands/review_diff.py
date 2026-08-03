# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — Review diff command group.

A5 (v3.8.0): extracted from cli/main.py (monolith split).  Behavior is
identical to the v3.7.0 inline implementation; cli/main.py re-exports
these functions for backward-compatible imports.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# OSH_HOME / sys.path bootstrap — mirrored from cli/main.py so command
# modules run standalone under pytest (SHALL-A5.5: no import of cli.main).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _osh_home() -> str:
    """Resolve OSH_HOME, honoring cli.main's live value (A5 compat).

    cli.main re-exports these commands; tests monkeypatch
    ``yuleosh.cli.main.OSH_HOME``.  A lazy lookup keeps the single source
    of truth in cli.main without a top-level circular import (SHALL-A5.5).
    """
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def cmd_review_diff(args):
    """Diff two review results."""
    import json as _json

    def _load_review(path_str: str) -> dict:
        p = Path(path_str)
        if p.exists():
            try:
                return _json.loads(p.read_text(encoding="utf-8"))
            except (_json.JSONDecodeError, OSError):
                pass
        # Try as session name under .yuleosh/sessions/
        sessions_dir = Path(_osh_home()) / ".yuleosh" / "sessions"
        if sessions_dir.exists():
            for sd in sorted(sessions_dir.iterdir()):
                if sd.is_dir() and (sd.name == path_str or path_str in sd.name):
                    for rf in sd.glob("*.json"):
                        try:
                            return _json.loads(rf.read_text(encoding="utf-8"))
                        except (_json.JSONDecodeError, OSError):
                            continue
        # Try .osh/reviews/latest/
        latest_dir = Path(_osh_home()) / ".osh" / "reviews" / "latest"
        if latest_dir.exists():
            for rf in latest_dir.glob("*.json"):
                if path_str in rf.name or rf.name == path_str:
                    try:
                        return _json.loads(rf.read_text(encoding="utf-8"))
                    except (_json.JSONDecodeError, OSError):
                        continue
        print(f"Error: review not found: {path_str}", file=sys.stderr)
        sys.exit(1)

    review_a = _load_review(args.review_a)
    review_b = _load_review(args.review_b or args.review_a)

    # Compare findings
    findings_a = set()
    for f in review_a.get("findings", []):
        if isinstance(f, dict):
            key = f.get("file", "") + ":" + str(f.get("line", "")) + ":" + f.get("message", "")[:60]
            findings_a.add(key)

    findings_b = set()
    for f in review_b.get("findings", []):
        if isinstance(f, dict):
            key = f.get("file", "") + ":" + str(f.get("line", "")) + ":" + f.get("message", "")[:60]
            findings_b.add(key)

    added = findings_b - findings_a
    removed = findings_a - findings_b
    common = findings_a & findings_b

    diff_result = {
        "review_a": {
            "type": review_a.get("review_type", "unknown"),
            "status": review_a.get("status", "unknown"),
            "generated_at": review_a.get("generated_at", ""),
        },
        "review_b": {
            "type": review_b.get("review_type", "unknown"),
            "status": review_b.get("status", "unknown"),
            "generated_at": review_b.get("generated_at", ""),
        },
        "findings_added": len(added),
        "findings_removed": len(removed),
        "findings_common": len(common),
        "added": sorted(list(added)),
        "removed": sorted(list(removed)),
    }

    if getattr(args, "json", False):
        print(_json.dumps(diff_result, indent=2, ensure_ascii=False))
        return

    print(f"\n  {'=' * 60}")
    print(f"   Review Diff")
    print(f"  {'=' * 60}")
    print(f"   Review A: {diff_result['review_a']['type']} ({diff_result['review_a']['status']}) @ {diff_result['review_a']['generated_at'][:19]}")
    print(f"   Review B: {diff_result['review_b']['type']} ({diff_result['review_b']['status']}) @ {diff_result['review_b']['generated_at'][:19]}")
    print(f"  {'─' * 60}")
    print(f"   Findings added:   {diff_result['findings_added']}")
    print(f"   Findings removed: {diff_result['findings_removed']}")
    print(f"   Findings common:  {diff_result['findings_common']}")

    if added:
        print(f"\n   🆕 新增发现:")
        for item in sorted(list(added))[:10]:
            print(f"       + {item}")
        if len(added) > 10:
            print(f"       ... 还有 {len(added) - 10} 项")

    if removed:
        print(f"\n   🗑️ 已解决发现:")
        for item in sorted(list(removed))[:10]:
            print(f"       - {item}")
        if len(removed) > 10:
            print(f"       ... 还有 {len(removed) - 10} 项")

    print()


def build_parser(rsub):
    """Register the review diff subcommand on the existing review parser (A5)."""
    p_review_diff = rsub.add_parser("diff", help="Diff two review results")
    p_review_diff.add_argument("review_a", help="First review result (file path or session name)")
    p_review_diff.add_argument("review_b", nargs="?", help="Second review result (file path or session name)")
    p_review_diff.add_argument("--json", action="store_true", help="Output diff as JSON")
    return p_review_diff
