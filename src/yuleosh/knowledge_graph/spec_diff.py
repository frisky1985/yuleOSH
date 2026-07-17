#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Spec Diff — spec file change detection (P1).

Analyzes *.spec.md files to detect SHALL statement changes (add/modify/delete)
between two versions of a spec file. Supports both git-based diff (by commit
or branch) and file comparison (old/new paths).

Spec change detection is a key input to the incremental build engine:
  - Added SHALL statements → create new Requirement nodes
  - Modified SHALL statements → update existing Requirement nodes + mark pending
  - Deleted SHALL statements → soft-delete Requirement nodes

Usage:
    from yuleosh.knowledge_graph.spec_diff import analyze_spec_changes
    changes = analyze_spec_changes(old_text, new_text)
    # → {"added": [...], "modified": [...], "deleted": [...]}
"""

import difflib
import logging
import re
from typing import Optional

log = logging.getLogger("yuleosh.knowledge_graph.spec_diff")

# SHALL ID pattern: matches things like RS-001-01, SWR-002.1-01, SYS-REQ-5.3-01
_SHALL_ID_RE = re.compile(r"([A-Z]+(?:-[A-Z]+)?-\d+(?:\.\d+)*(?:-\d+)?)")
_SHALL_LINE_RE = re.compile(r"^\s*\*\s+\[(.+?)\]\s+(.+?)(?:\.\s*|\s*//.*)?$", re.MULTILINE)
# Alternative pattern for numbered lists or plain bullet + SHALL ID
_SHALL_REF_RE = re.compile(r"(?:SHALL|SHOULD|MUST|MAY)\s+ID[:\s]+([A-Z]+-\d+(?:\.\d+)*(?:-\d+)?)", re.IGNORECASE)
# Spec section header pattern
_SECTION_RE = re.compile(r"^#{2,4}\s+(.+)$", re.MULTILINE)


def extract_shall_statements(md_text: str) -> list[dict]:
    """Extract SHALL statements from spec markdown text.

    Returns a list of dicts with keys:
      - shall_id: the SHALL ID (e.g., "RS-001-01")
      - statement: the full statement text
      - section: the section heading under which this ID appears
      - line_number: approximate line number in the original text

    Supports multiple spec formats:
      1. `* [RS-001-01] The SHALL ...`  (standard yuleOSH bullet format)
      2. `- RS-001-01: The SHALL ...`    (dash format)
      3. Inline SHALL ID references
    """
    results = []
    if not md_text or not md_text.strip():
        return results

    lines = md_text.split("\n")
    current_section = ""

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track current section heading
        section_match = _SECTION_RE.match(line)
        if section_match:
            current_section = section_match.group(1).strip()

        # Pattern 1: * [RS-001-01] Statement text
        m1 = _SHALL_LINE_RE.match(stripped)
        if m1:
            shall_id = m1.group(1).strip()
            statement = m1.group(2).strip()
            results.append({
                "shall_id": shall_id,
                "statement": statement,
                "section": current_section,
                "line_number": i,
            })
            continue

        # Pattern 2: - RS-001-01: Statement text
        m2 = re.match(r"^-\s+([A-Z]+-\d+(?:\.\d+)*(?:-\d+)?)\s*[:\-]\s*(.+)$", stripped)
        if m2:
            shall_id = m2.group(1).strip()
            statement = m2.group(2).strip()
            results.append({
                "shall_id": shall_id,
                "statement": statement,
                "section": current_section,
                "line_number": i,
            })
            continue

        # Pattern 3: Inline SHALL ID anywhere in text
        for match in _SHALL_ID_RE.finditer(stripped):
            in_id = match.group(1)
            in_ref_match = _SHALL_REF_RE.search(stripped)
            if in_ref_match and in_ref_match.group(1) == in_id:
                # This is a SHALL ID reference, not a definition
                # Only capture if it looks like a definition (has statement after it)
                pass
            else:
                # Try to capture as a potential definition
                # Check if followed by enough text to be a statement
                remaining = stripped[match.end():].strip()
                if remaining.startswith(":") or remaining.startswith("-"):
                    statement = remaining.lstrip(":- ").strip()
                    if statement:
                        results.append({
                            "shall_id": in_id,
                            "statement": statement,
                            "section": current_section,
                            "line_number": i,
                        })

    log.debug("Extracted %d SHALL statements from spec text", len(results))
    return results


def extract_shall_ids(md_text: str) -> list[str]:
    """Quick extraction: return just the ordered list of SHALL IDs from text."""
    statements = extract_shall_statements(md_text)
    return [s["shall_id"] for s in statements]


def _normalize_statement(text: str) -> str:
    """Normalize a statement for diff comparison.

    Strips trailing punctuation, normalizes whitespace,
    and lowercases for equality detection.
    """
    text = text.strip().rstrip(".")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def analyze_spec_changes(old_text: str, new_text: str) -> dict:
    """Analyze spec changes between old and new versions.

    Detects added, modified, and deleted SHALL statements.

    Args:
        old_text: The old version of the spec markdown text
        new_text: The new version of the spec markdown text

    Returns:
        dict with keys:
          - added: list of {"shall_id", "statement", "section", "line_number"}
          - modified: list of {"shall_id", "old_statement", "new_statement", "section"}
          - deleted: list of {"shall_id", "statement", "section", "line_number"}
          - unchanged: list of {"shall_id", "statement"} (for tracking)
          - summary: human-readable summary string
    """
    old_statements = extract_shall_statements(old_text) if old_text else []
    new_statements = extract_shall_statements(new_text) if new_text else []

    old_by_id: dict[str, dict] = {s["shall_id"]: s for s in old_statements}
    new_by_id: dict[str, dict] = {s["shall_id"]: s for s in new_statements}

    old_ids = set(old_by_id.keys())
    new_ids = set(new_by_id.keys())

    added_ids = new_ids - old_ids
    deleted_ids = old_ids - new_ids
    common_ids = old_ids & new_ids

    added = [new_by_id[sid] for sid in sorted(added_ids)]
    deleted = [old_by_id[sid] for sid in sorted(deleted_ids)]

    modified = []
    unchanged = []
    for sid in sorted(common_ids):
        old_s = _normalize_statement(old_by_id[sid].get("statement", ""))
        new_s = _normalize_statement(new_by_id[sid].get("statement", ""))
        if old_s != new_s:
            modified.append({
                "shall_id": sid,
                "old_statement": old_by_id[sid].get("statement", ""),
                "new_statement": new_by_id[sid].get("statement", ""),
                "section": new_by_id[sid].get("section", ""),
            })
        else:
            unchanged.append({
                "shall_id": sid,
                "statement": old_by_id[sid].get("statement", ""),
            })

    total_old = len(old_ids)
    summary_parts = []
    if added:
        summary_parts.append(f"{len(added)} added")
    if modified:
        summary_parts.append(f"{len(modified)} modified")
    if deleted:
        summary_parts.append(f"{len(deleted)} deleted")
    if unchanged:
        summary_parts.append(f"{len(unchanged)} unchanged")
    summary = f"Spec changes: {', '.join(summary_parts)} (from {total_old} total SHALLs)" if summary_parts else "No spec changes detected"

    log.info(
        "Spec diff: %d added, %d modified, %d deleted, %d unchanged (from %d total)",
        len(added), len(modified), len(deleted), len(unchanged), total_old,
    )
    return {
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "unchanged": unchanged,
        "summary": summary,
    }


def analyze_spec_file_changes(old_path: str, new_path: str) -> dict:
    """Analyze spec changes by comparing two spec files on disk.

    Args:
        old_path: Path to the old spec file
        new_path: Path to the new spec file

    Returns:
        Same format as analyze_spec_changes()
    """
    import os

    old_text = ""
    new_text = ""
    if os.path.isfile(old_path):
        with open(old_path, "r", encoding="utf-8", errors="replace") as f:
            old_text = f.read()
    if os.path.isfile(new_path):
        with open(new_path, "r", encoding="utf-8", errors="replace") as f:
            new_text = f.read()

    return analyze_spec_changes(old_text, new_text)


def detect_spec_files_in_changes(changed_files: list[str]) -> list[str]:
    """Filter a list of changed files to only include *.spec.md files.

    Args:
        changed_files: List of file paths (relative or absolute)

    Returns:
        Filtered list of *.spec.md file paths
    """
    return [f for f in changed_files if f.endswith(".spec.md") or "/spec/" in f.replace("\\", "/")]


def apply_spec_changes_to_store(store, changes: dict) -> dict:
    """Apply detected spec changes to the knowledge graph store.

    Creates/updates/deletes Requirement nodes based on spec changes.

    Args:
        store: KGStore or KGStorePG instance
        changes: Result from analyze_spec_changes()

    Returns:
        Summary dict with counts of created/updated/deleted nodes
    """
    from yuleosh.knowledge_graph.models import Node

    created = 0
    updated = 0
    deleted = 0

    for statement in changes.get("added", []):
        node = Node(
            entity_type="requirement",
            entity_id=statement["shall_id"],
            label=statement["shall_id"],
            properties={
                "statement": statement.get("statement", ""),
                "section": statement.get("section", ""),
                "source": "spec_diff",
                "change_type": "added",
                "testable": True,
            },
        )
        store.upsert_node(node)
        created += 1

    for stmt in changes.get("modified", []):
        existing = store.get_node("requirement", stmt["shall_id"])
        if existing:
            props = dict(existing.properties)
            props["statement"] = stmt.get("new_statement", "")
            props["old_statement"] = stmt.get("old_statement", "")
            props["section"] = stmt.get("section", "")
            props["has_pending_changes"] = True
            props["change_type"] = "modified"
            node = Node(
                entity_type="requirement",
                entity_id=stmt["shall_id"],
                label=stmt["shall_id"],
                properties=props,
                is_active=existing.is_active,
            )
            store.upsert_node(node)
            updated += 1

    for stmt in changes.get("deleted", []):
        existing = store.get_node("requirement", stmt["shall_id"])
        if existing and existing.is_active:
            props = dict(existing.properties)
            props["change_type"] = "deleted"
            node = Node(
                entity_type="requirement",
                entity_id=stmt["shall_id"],
                label=stmt["shall_id"],
                properties=props,
                is_active=False,
            )
            store.upsert_node(node)
            deleted += 1

    log.info(
        "Applied spec changes: %d created, %d updated, %d deleted",
        created, updated, deleted,
    )
    return {"created": created, "updated": updated, "deleted": deleted}


def get_spec_changes_from_git(git_base: str, spec_file: str) -> dict:
    """Get spec changes by git diff of a spec file.

    Args:
        git_base: Git base reference (e.g., "HEAD~1", "main")
        spec_file: Path to the spec file

    Returns:
        Same format as analyze_spec_changes()
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "show", f"{git_base}:{spec_file}"],
            capture_output=True, text=True, check=False, timeout=30,
        )
        old_text = result.stdout if result.returncode == 0 else ""

        with open(spec_file, "r", encoding="utf-8", errors="replace") as f:
            new_text = f.read()

        return analyze_spec_changes(old_text, new_text)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("Failed to get spec changes from git: %s", e)
        return {"added": [], "modified": [], "deleted": [], "unchanged": [], "summary": "Error reading git spec"}
