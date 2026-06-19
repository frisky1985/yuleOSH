#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Agent Traceability (G-47 / DEF-010).

Records bidirectional traceability between agent reviews and code versions:
- Commit SHA tracking per review session
- file:line location mapping for review findings
- build_id ↔ review_session cross-referencing

Reference: kpi.py (record 模式)

Usage:
    from yuleosh.ci.agent_traceability import (
        record_review,
        get_reviews_for_commit,
        get_commits_for_review,
        get_findings_for_file,
    )
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.agent_traceability")

TRACE_FILE = Path(".yuleosh") / "reports" / "agent-traceability.jsonl"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _ensure_trace_dir(project_dir: str) -> Path:
    """Ensure the trace file directory exists."""
    path = Path(project_dir) / TRACE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _get_git_commit(project_dir: str) -> str:
    """Get the full git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _generate_review_id(layer: int = 0) -> str:
    """Generate a unique review session ID.

    Format: RVW-YYYYMMDD-HHMMSS-<random suffix>
    """
    import random
    suffix = format(random.randint(0, 0xFFFF), "04x")
    return f"RVW-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{suffix}"


# ------------------------------------------------------------------
# Public API — record a review session
# ------------------------------------------------------------------


def record_review(
    project_dir: str,
    review_type: str = "",
    findings: Optional[list[dict]] = None,
    commit: str = "",
    build_id: str = "",
    agent_name: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record an agent review session with bidirectional traceability.

    Captures:
    - review_id (unique session identifier)
    - commit SHA (G-47 §19.1)
    - file:line findings (G-47 §19.2)
    - build_id association (G-47 §19.3)

    Parameters
    ----------
    project_dir : str
        Project root directory.
    review_type : str
        Type of review: "code-review", "arch-review", "misra-review",
        "bsp-review", "stack-review", "mmio-review", etc.
    findings : list[dict], optional
        List of finding dicts with at least "file" and optionally "line".
    commit : str
        Git commit SHA (auto-detected if empty).
    build_id : str
        Associated build_id for cross-referencing.
    agent_name : str
        Name of the reviewing agent (e.g. "小克", "小马", "Hermes").
    extra : dict, optional
        Additional metadata.

    Returns
    -------
    dict
        The recorded traceability entry.
    """
    if not commit:
        commit = _get_git_commit(project_dir)
    if not findings:
        findings = []

    review_id = _generate_review_id()

    # Normalize file:line format
    normalized_findings: list[dict] = []
    for f in findings:
        nf = {
            "file": f.get("file", ""),
            "line": f.get("line", 0),
            "severity": f.get("severity", "info"),
            "message": f.get("message", ""),
            "category": f.get("category", ""),
            "rule_id": f.get("rule_id", ""),
        }
        # Normalize to file:line format for traceability
        nf["location"] = f"{nf['file']}:{nf['line']}" if nf.get("line") else nf["file"]
        normalized_findings.append(nf)

    entry: dict[str, Any] = {
        "review_id": review_id,
        "timestamp": datetime.now().isoformat(),
        "commit": commit,
        "build_id": build_id,
        "review_type": review_type,
        "agent_name": agent_name,
        "finding_count": len(normalized_findings),
        "findings": normalized_findings,
    }

    if extra:
        entry.update(extra)

    # Append to traceability JSONL
    trace_path = _ensure_trace_dir(project_dir)
    with open(trace_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info(
        "Review recorded: %s (type=%s, findings=%d, commit=%s)",
        review_id,
        review_type,
        len(normalized_findings),
        commit[:12],
    )
    return entry


# ------------------------------------------------------------------
# Public API — query traceability
# ------------------------------------------------------------------


def get_reviews_for_commit(
    project_dir: str,
    commit: str,
    limit: int = 20,
) -> list[dict]:
    """Find all review sessions associated with a commit (G-47 §19.1).

    Enables: given a commit, what reviews were performed?

    Parameters
    ----------
    project_dir : str
        Project root directory.
    commit : str
        Git commit hash (supports prefix matching).
    limit : int
        Maximum results.

    Returns
    -------
    list[dict]
        Matching review entries.
    """
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return []

    entries: list[dict] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    entry_commit = entry.get("commit", "")
                    if entry_commit.startswith(commit):
                        entries.append(entry)
                        if len(entries) >= limit:
                            break
                except (json.JSONDecodeError, ValueError):
                    continue

    return entries


def get_commits_for_review(
    project_dir: str,
    review_id: str,
) -> list[dict]:
    """Find all entries for a specific review session (G-47 §19.1).

    Enables: given a review_id, what commits were involved?

    Parameters
    ----------
    project_dir : str
        Project root directory.
    review_id : str
        Review session ID.

    Returns
    -------
    list[dict]
        Matching entries.
    """
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return []

    entries: list[dict] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if entry.get("review_id") == review_id:
                        entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

    return entries


def get_findings_for_file(
    project_dir: str,
    file_path: str,
    limit: int = 50,
) -> list[dict]:
    """Find all review findings targeting a specific file (G-47 §19.2).

    Enables: given a file, what findings were reported by reviews?
    Supports both full path and file name matching.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    file_path : str
        File path to search for (supports substring matching).
    limit : int
        Maximum results.

    Returns
    -------
    list[dict]
        Matching findings with review context.
    """
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return []

    findings: list[dict] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    review_id = entry.get("review_id", "")
                    commit = entry.get("commit", "")
                    review_type = entry.get("review_type", "")
                    for finding in entry.get("findings", []):
                        fpath = finding.get("file", "")
                        if file_path in fpath:
                            findings.append({
                                "review_id": review_id,
                                "commit": commit,
                                "review_type": review_type,
                                "file": fpath,
                                "line": finding.get("line", 0),
                                "location": finding.get("location", f"{fpath}:{finding.get('line', 0)}"),
                                "severity": finding.get("severity", "info"),
                                "message": finding.get("message", ""),
                                "category": finding.get("category", ""),
                            })
                            if len(findings) >= limit:
                                return findings
                except (json.JSONDecodeError, ValueError):
                    continue

    return findings


def get_reviews_by_build(
    project_dir: str,
    build_id: str,
) -> list[dict]:
    """Find all review sessions associated with a build (G-47 §19.3).

    Enables: given a build_id, what reviews were performed?

    Parameters
    ----------
    project_dir : str
        Project root directory.
    build_id : str
        Build ID to match (supports prefix matching).

    Returns
    -------
    list[dict]
        Matching review entries.
    """
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return []

    entries: list[dict] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    entry_bid = entry.get("build_id", "")
                    if entry_bid.startswith(build_id):
                        entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

    return entries


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------


def show_traceability(
    project_dir: str,
    as_json: bool = False,
    limit: int = 10,
) -> str:
    """Display recent traceability entries as formatted table or JSON.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    as_json : bool
        Output as JSON.
    limit : int
        Number of recent entries.

    Returns
    -------
    str
        Formatted output.
    """
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return "*No traceability data found.*"

    entries: list[dict] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    entries.reverse()
    recent = entries[:limit]

    if not recent:
        return "*No traceability entries.*"

    if as_json:
        return json.dumps(recent, indent=2, ensure_ascii=False, default=str)

    rows = [
        "## Agent ↔ Code Traceability (G-47)",
        "",
        "| Review ID | Timestamp | Commit | Type | Agent | Findings | Build ID |",
        "|:----------|:----------|:-------|:-----|:-----:|:--------:|:---------|",
    ]

    for e in recent:
        rows.append(
            f"| {e.get('review_id', '?')} | "
            f"{e.get('timestamp', '?')[:19]} | "
            f"{e.get('commit', '?')[:12]} | "
            f"{e.get('review_type', '?')} | "
            f"{e.get('agent_name', '?')} | "
            f"{e.get('finding_count', 0)} | "
            f"{e.get('build_id', '?')} |"
        )

    rows.append("")
    return "\n".join(rows)


def validate_traceability_file(project_dir: str) -> dict:
    """Validate the traceability JSONL file integrity."""
    trace_path = Path(project_dir) / TRACE_FILE
    if not trace_path.exists():
        return {"valid": True, "entry_count": 0, "issues": ["No file yet"]}

    entries = 0
    issues: list[str] = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            entries += 1
            try:
                entry = json.loads(line)
                if "review_id" not in entry:
                    issues.append(f"Line {line_num}: missing review_id")
                if "commit" not in entry:
                    issues.append(f"Line {line_num}: missing commit")
            except json.JSONDecodeError as e:
                issues.append(f"Line {line_num}: invalid JSON: {e}")

    return {"valid": len(issues) == 0, "entry_count": entries, "issues": issues}


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _cli_main():
    """Simple CLI for agent traceability operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Traceability CLI (G-47)")
    parser.add_argument("action", nargs="?", default="show",
                        choices=["show", "record", "validate",
                                 "for-commit", "for-file", "for-build"])
    parser.add_argument("--project-dir", default=os.environ.get("OSH_HOME", os.getcwd()))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--commit", default="")
    parser.add_argument("--build-id", default="")
    parser.add_argument("--file", default="")
    parser.add_argument("--review-type", default="code-review")
    parser.add_argument("--agent", default="小克")

    args = parser.parse_args()

    if args.action == "show":
        print(show_traceability(args.project_dir, as_json=args.json, limit=args.limit))
    elif args.action == "record":
        entry = record_review(
            args.project_dir,
            review_type=args.review_type,
            commit=args.commit,
            build_id=args.build_id,
            agent_name=args.agent,
        )
        print(json.dumps(entry, indent=2, ensure_ascii=False, default=str))
    elif args.action == "validate":
        result = validate_traceability_file(args.project_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.action == "for-commit":
        if not args.commit:
            print("error: --commit is required")
            return
        entries = get_reviews_for_commit(args.project_dir, args.commit, limit=args.limit)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
        else:
            for e in entries:
                print(f"  {e.get('review_id')}: {e['review_type']} ({e['finding_count']} findings)")
    elif args.action == "for-file":
        if not args.file:
            print("error: --file is required")
            return
        findings = get_findings_for_file(args.project_dir, args.file, limit=args.limit)
        if args.json:
            print(json.dumps(findings, indent=2, ensure_ascii=False, default=str))
        else:
            for f in findings:
                print(f"  {f['location']}: {f['message']} ({f['severity']})")
    elif args.action == "for-build":
        if not args.build_id:
            print("error: --build-id is required")
            return
        entries = get_reviews_by_build(args.project_dir, args.build_id)
        if args.json:
            print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))
        else:
            for e in entries:
                print(f"  {e.get('review_id')}: {e['review_type']} @ {e['commit'][:12]}")


if __name__ == "__main__":
    _cli_main()
