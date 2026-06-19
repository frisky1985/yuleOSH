#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Build Metadata Persistence (G-48 / DEF-009).

Captures and persists build metadata for CL2 auditability:
- JSONL file with per-build records
- Field completeness validation
- Change audit trail
- Build-ID associability (linking artifacts to builds)
- Tool version pinning

参考: coverage_trend.py (JSONL 模式)

Usage:
    from yuleosh.ci.build_metadata import record_build, get_build_metadata
    record_build(project_dir, commit="abc123", status="passed")
    meta = get_build_metadata(project_dir)  # Latest build
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.build_metadata")

BUILD_META_FILE = Path(".yuleosh") / "reports" / "build-metadata.jsonl"

# Required fields for CL2 compliance (G-48 §20.2)
REQUIRED_FIELDS = [
    "build_id",
    "timestamp",
    "commit",
    "status",
    "layer",
    "tool_versions",
    "files_changed",
]

# Tool versions to capture
TOOLS_TO_VERSION = [
    "python",
    "cppcheck",
    "gcc",
    "cmake",
    "pytest",
    "git",
]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _ensure_meta_dir(project_dir: str) -> Path:
    """Ensure the metadata file directory exists."""
    path = Path(project_dir) / BUILD_META_FILE
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


def _get_git_files_changed(project_dir: str) -> int:
    """Count files changed in the most recent commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
        )
        if result.returncode == 0:
            return len([f for f in result.stdout.splitlines() if f.strip()])
        return 0
    except Exception:
        return 0


def _get_tool_versions(project_dir: str) -> dict[str, str]:
    """Capture versions of key tools used in the build pipeline.

    Returns dict mapping tool name → version string (or "not found").
    """
    versions: dict[str, str] = {}

    for tool in TOOLS_TO_VERSION:
        try:
            if tool == "python":
                result = subprocess.run(
                    [sys.executable, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                versions["python"] = result.stdout.strip() if result.returncode == 0 else sys.version
            elif tool == "git":
                result = subprocess.run(
                    ["git", "--version"],
                    capture_output=True, text=True, timeout=5,
                    cwd=project_dir,
                )
                versions["git"] = result.stdout.strip() if result.returncode == 0 else "not found"
            else:
                result = subprocess.run(
                    [tool, "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                out = result.stdout.strip() or result.stderr.strip()
                versions[tool] = out if out else "not found"
        except FileNotFoundError:
            versions[tool] = "not installed"
        except Exception as e:
            versions[tool] = f"error: {e}"

    return versions


def _generate_build_id(project_dir: str) -> str:
    """Generate a unique, sortable build ID.

    Format: YYYYMMDD-HHMMSS-<short-commit>
    """
    commit = _get_git_commit(project_dir)[:8]
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{commit}"


def _validate_fields(entry: dict) -> list[str]:
    """Validate that all required fields are present and non-empty.

    Returns a list of missing or empty field names.
    """
    missing: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in entry:
            missing.append(field)
        elif entry[field] is None:
            missing.append(field)
        elif isinstance(entry[field], str) and not entry[field].strip():
            missing.append(field)
        elif isinstance(entry[field], dict) and not entry[field]:
            missing.append(field)
        elif isinstance(entry[field], (int, float)) and entry[field] < 0:
            missing.append(f"invalid:{field}")
    return missing


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def record_build(
    project_dir: str,
    commit: str = "",
    status: str = "",
    layer: int = 0,
    extra_fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Record build metadata entry (G-48 §20.1).

    Appends a JSONL entry with build context: build_id, timestamp,
    commit hash, status, tool versions, and optional extra fields.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    commit : str
        Git commit hash. Auto-detected if empty.
    status : str
        Build status: "passed", "failed", "running", "warning".
    layer : int
        CI layer number (1, 2, 25, 3).
    extra_fields : dict, optional
        Additional metadata to include.

    Returns
    -------
    dict
        The recorded entry.
    """
    if not commit:
        commit = _get_git_commit(project_dir)

    build_id = _generate_build_id(project_dir)
    files_changed = _get_git_files_changed(project_dir)
    tool_versions = _get_tool_versions(project_dir)

    entry: dict[str, Any] = {
        "build_id": build_id,
        "timestamp": datetime.now().isoformat(),
        "commit": commit,
        "status": status,
        "layer": layer,
        "tool_versions": tool_versions,
        "files_changed": files_changed,
    }

    if extra_fields:
        entry.update(extra_fields)

    # Validate required fields (G-48 §20.2)
    missing = _validate_fields(entry)
    if missing:
        log.warning(
            "Build metadata missing required fields: %s (build_id=%s)",
            ", ".join(missing),
            build_id,
        )
        entry["_validation_warnings"] = missing

    # Append to JSONL file
    meta_path = _ensure_meta_dir(project_dir)
    with open(meta_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    log.info("Build metadata recorded: %s (layer=%d, status=%s)", build_id, layer, status)
    return entry


def get_build_metadata(
    project_dir: str,
    build_id: Optional[str] = None,
    limit: int = 1,
    layer: Optional[int] = None,
) -> list[dict]:
    """Retrieve build metadata entries (G-48 §20.3).

    Parameters
    ----------
    project_dir : str
        Project root directory.
    build_id : str, optional
        Specific build ID to retrieve (exact match).
    limit : int
        Maximum number of entries to return (default 1 = most recent).
    layer : int, optional
        Filter by CI layer number.

    Returns
    -------
    list[dict]
        Build metadata entries (most recent first).
    """
    meta_path = Path(project_dir) / BUILD_META_FILE
    if not meta_path.exists():
        return []

    entries: list[dict] = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    if build_id and entry.get("build_id") != build_id:
                        continue
                    if layer is not None and entry.get("layer") != layer:
                        continue
                    entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

    # Return most recent first
    entries.reverse()
    return entries[:limit]


def get_build_chain(
    project_dir: str,
    commit: str,
) -> list[dict]:
    """Get all build metadata entries for a specific commit (G-48 §20.4).

    This enables traceability: given a commit, find all associated builds.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    commit : str
        Git commit hash to match (supports prefix matching).

    Returns
    -------
    list[dict]
        Matching build entries sorted by timestamp (ascending).
    """
    meta_path = Path(project_dir) / BUILD_META_FILE
    if not meta_path.exists():
        return []

    entries: list[dict] = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    entry_commit = entry.get("commit", "")
                    if entry_commit.startswith(commit):
                        entries.append(entry)
                except (json.JSONDecodeError, ValueError):
                    continue

    return sorted(entries, key=lambda e: e.get("timestamp", ""))


def validate_metadata_integrity(project_dir: str) -> dict[str, Any]:
    """Validate build metadata file integrity (G-48 §20.5).

    Checks:
    - File exists and is valid JSONL
    - Required fields present in all entries
    - No duplicate build_ids
    - Timestamps are monotonically increasing

    Returns
    -------
    dict
        Validation result with status and details.
    """
    meta_path = Path(project_dir) / BUILD_META_FILE
    if not meta_path.exists():
        return {"valid": False, "error": "No build metadata file found"}

    entries: list[dict] = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entries.append((line_num, entry))
            except json.JSONDecodeError as e:
                return {
                    "valid": False,
                    "error": f"Invalid JSON on line {line_num}: {e}",
                }

    if not entries:
        return {"valid": True, "entry_count": 0, "warnings": ["No entries"]}

    issues: list[str] = []
    seen_build_ids: set[str] = set()
    prev_timestamp = ""

    for line_num, entry in entries:
        # Check required fields
        missing = _validate_fields(entry)
        if missing:
            issues.append(f"Line {line_num}: missing fields: {', '.join(missing)}")

        # Check duplicate build_ids
        bid = entry.get("build_id", "")
        if bid in seen_build_ids:
            issues.append(f"Line {line_num}: duplicate build_id: {bid}")
        seen_build_ids.add(bid)

        # Check timestamp monotonicity
        ts = entry.get("timestamp", "")
        if ts and prev_timestamp and ts < prev_timestamp:
            issues.append(
                f"Line {line_num}: timestamp not monotonic ({ts} < {prev_timestamp})"
            )
        if ts:
            prev_timestamp = ts

    result: dict[str, Any] = {
        "valid": len(issues) == 0,
        "entry_count": len(entries),
        "issues": issues,
    }
    return result


def show_build_metadata(project_dir: str, as_json: bool = False, limit: int = 10) -> str:
    """Display build metadata as formatted table or JSON.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    as_json : bool
        Output as JSON.
    limit : int
        Number of recent entries to show.

    Returns
    -------
    str
        Formatted output.
    """
    entries = get_build_metadata(project_dir, limit=limit)

    if not entries:
        return "*No build metadata found.*"

    if as_json:
        return json.dumps(entries, indent=2, ensure_ascii=False, default=str)

    rows = [
        "## Build Metadata",
        "",
        "| Build ID | Timestamp | Commit | Status | Layer | Files Changed |",
        "|:---------|:----------|:-------|:-----:|:-----:|:-------------:|",
    ]

    for e in entries:
        rows.append(
            f"| {e.get('build_id', '?')} | "
            f"{e.get('timestamp', '?')[:19]} | "
            f"{e.get('commit', '?')[:12]} | "
            f"{e.get('status', '?')} | "
            f"{e.get('layer', '?')} | "
            f"{e.get('files_changed', 0)} |"
        )

    rows.append("")
    return "\n".join(rows)


# ------------------------------------------------------------------
# CLI helpers
# ------------------------------------------------------------------


def _cli_main():
    """Simple CLI for build-metadata operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Build Metadata CLI (G-48)")
    parser.add_argument("action", nargs="?", default="show",
                        choices=["show", "record", "validate", "chain"])
    parser.add_argument("--project-dir", default=os.environ.get("OSH_HOME", os.getcwd()))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--commit", default="")
    parser.add_argument("--status", default="passed")
    parser.add_argument("--layer", type=int, default=0)
    parser.add_argument("--build-id", default="")

    args = parser.parse_args()

    if args.action == "show":
        print(show_build_metadata(args.project_dir, as_json=args.json, limit=args.limit))
    elif args.action == "record":
        entry = record_build(
            args.project_dir,
            commit=args.commit,
            status=args.status,
            layer=args.layer,
        )
        print(json.dumps(entry, indent=2, ensure_ascii=False, default=str))
    elif args.action == "validate":
        result = validate_metadata_integrity(args.project_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif args.action == "chain":
        if not args.commit:
            print("error: --commit is required for chain action")
            return
        entries = get_build_chain(args.project_dir, args.commit)
        print(json.dumps(entries, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    _cli_main()
