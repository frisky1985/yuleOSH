# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Post-merge hook — auto-create KB entries for MISRA analysis results.

Behaviour:
1. Detect yuleOSH project scope.
2. Check for a persisted MISRA snapshot in .yuleosh/ci/last-misra-snapshot.json.
3. Create KB articles for any violations not already saved to the KB.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from yuleosh.kb.store import KbStore

log = logging.getLogger("yuleosh.hooks.post_merge")

SNAPSHOT_RELPATH = ".yuleosh/ci/last-misra-snapshot.json"


def _is_yuleosh_project(cwd: str | Path) -> bool:
    root = Path(cwd).resolve()
    for ancestor in [root] + list(root.parents):
        if (ancestor / ".yuleosh").is_dir():
            return True
        if (ancestor / "yuleosh.yaml").is_file():
            return True
    return False


def _classify_misra_category(rule_id: Optional[str]) -> str:
    if rule_id is None:
        return "advisory"
    try:
        num = float(rule_id)
    except ValueError:
        return "advisory"
    if num < 15.0:
        return "required"
    return "advisory"


def _load_snapshot(project_root: Path) -> list[dict]:
    snap_path = project_root / SNAPSHOT_RELPATH
    if snap_path.exists():
        try:
            return json.loads(snap_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _get_existing_kb_signatures(store: KbStore) -> set:
    """Return set of 'rule_id:file:line' tuples already in KB."""
    articles = store.list_articles(limit=5000)
    sigs: set[str] = set()
    for a in articles:
        ref = a.source_ref or ""
        tags = a.tags or ""
        parts = a.title.split(":", 1)
        rule_id = parts[0].replace("MISRA-", "") if parts else ""
        # source_ref is "file:line"
        sigs.add(f"{rule_id}:{ref}")
    return sigs


def run_post_merge(cwd: Optional[str] = None) -> int:
    """Run the post-merge hook. Returns 0 on success, 1 on error."""
    if cwd is None:
        cwd = os.getcwd()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    if not _is_yuleosh_project(cwd):
        return 0

    project_root = Path(cwd).resolve()
    violations = _load_snapshot(project_root)
    if not violations:
        return 0

    print(f"\n📋 Post-merge: processing {len(violations)} MISRA violation(s) for KB ingestion...")

    try:
        store = KbStore()
        existing = _get_existing_kb_signatures(store)
        created = 0

        for v in violations:
            rule_id = v.get("rule_id") or "unknown"
            ref = f"{v.get('file', '')}:{v.get('line', 0)}"
            sig = f"{rule_id}:{ref}"

            if sig in existing:
                continue  # already in KB

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
                    f"\n---\n*Auto-created by post-merge hook*"
                ),
                "source": "misra_analysis",
                "source_ref": ref,
                "tags": tags,
            })
            created += 1

        if created:
            print(f"📚 Created {created} new KB article(s) from MISRA snapshot.")
        else:
            print("✅ All violations already in KB. No new articles created.")

    except Exception as exc:
        log.error("Post-merge hook failed: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run_post_merge())
