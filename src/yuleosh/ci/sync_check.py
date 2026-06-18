#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
文档同步门禁检查 (Doc Sync Gate) — E05

当代码修改时，检查对应文档是否已同步更新。
规则定义在 ``docs/.sync-gate.yaml`` 中。

用法:
    python -m yuleosh.ci.sync_check [--project-dir <path>]
    yuleosh audit sync-check
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.sync_check")

DEFAULT_GATE_FILE = "docs/.sync-gate.yaml"


def load_sync_gate_config(project_dir: str) -> list[dict]:
    """Load the sync-gate YAML config from ``docs/.sync-gate.yaml``.

    Returns a list of tracking rule dicts, each with:
        - code_path: str  (relative path pattern to watch)
        - docs: list[str] (relative paths of docs to check)
        - reason: str     (rationale for the rule)
    """
    gate_path = Path(project_dir) / DEFAULT_GATE_FILE
    if not gate_path.exists():
        log.warning("Sync gate config not found: %s", gate_path)
        return []

    import yaml
    try:
        raw = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("Failed to parse sync gate config: %s", e)
        return []

    return raw.get("tracking", [])


def get_changed_files(project_dir: str, base_ref: str = "HEAD") -> list[str]:
    """Get list of changed files compared to a Git ref.

    First tries ``git diff --name-only`` against *base_ref*.
    Falls back to listing modified files if git fails.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
            if files:
                return files
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.debug("git diff fallback: %s", e)

    # Fallback: also check git status
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
            cwd=project_dir,
        )
        if result.returncode == 0:
            files = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if line:
                    # porcelain format: XY filename
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        files.append(parts[1])
            return files
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return []


def check_mtime_freshness(doc_path: str, project_dir: str) -> bool:
    """Check if a doc file has been modified recently (within 30 days)."""
    full_path = Path(project_dir) / doc_path
    if not full_path.exists():
        return False

    mtime = full_path.stat().st_mtime
    age_days = (datetime.now().timestamp() - mtime) / 86400
    return age_days <= 30


def run_sync_check(project_dir: str, base_ref: str = "HEAD") -> dict:
    """Run the full document sync gate check.

    Returns a dict with:
        - status: "passed" | "failed" | "warning"
        - rule_results: list of per-rule check results
        - changed_files: list of changed files detected
        - summary: text summary
    """
    result: dict = {
        "status": "passed",
        "rule_results": [],
        "changed_files": [],
        "summary": "",
        "generated_at": datetime.now().isoformat(),
    }

    # 1. Load gate rules
    rules = load_sync_gate_config(project_dir)
    if not rules:
        result["status"] = "warning"
        result["summary"] = "No sync gate rules defined (docs/.sync-gate.yaml not found or empty)"
        return result

    # 2. Detect changed files
    changed = get_changed_files(project_dir, base_ref)
    result["changed_files"] = changed

    if not changed:
        result["status"] = "passed"
        result["summary"] = "No changed files detected in working tree"
        return result

    # 3. Compare changed files against tracking rules
    failures = []
    warnings = []

    for rule in rules:
        code_path = rule.get("code_path", "")
        docs = rule.get("docs", [])
        reason = rule.get("reason", "")

        # Check if this code_path matches any changed file
        # Support glob patterns: check if changed file starts with or contains the prefix
        matched = [
            cf for cf in changed
            if cf == code_path or cf.startswith(code_path.rstrip("*"))
        ]

        if not matched:
            continue

        # This rule's code path changed — check docs
        for doc_path in docs:
            full_doc = Path(project_dir) / doc_path
            if not full_doc.exists():
                failures.append({
                    "rule": f"{code_path} → {doc_path}",
                    "reason": reason,
                    "issue": f"Document does not exist: {doc_path}",
                    "matched_files": matched,
                })
            elif not check_mtime_freshness(doc_path, project_dir):
                warnings.append({
                    "rule": f"{code_path} → {doc_path}",
                    "reason": reason,
                    "issue": f"Document not recently updated (>30 days): {doc_path}",
                    "matched_files": matched,
                })

    # 4. Compile result
    rule_results = []
    for f in failures:
        rule_results.append({
            "rule_id": f["rule"],
            "severity": "error",
            "reason": f["reason"],
            "message": f["issue"],
            "matched_files": f["matched_files"],
        })

    for w in warnings:
        rule_results.append({
            "rule_id": w["rule"],
            "severity": "warning",
            "reason": w["reason"],
            "message": w["issue"],
            "matched_files": w["matched_files"],
        })

    result["rule_results"] = rule_results

    if failures:
        result["status"] = "failed"
        result["summary"] = (
            f"Sync gate FAILED: {len(failures)} error(s), {len(warnings)} warning(s)"
        )
    elif warnings:
        result["status"] = "warning"
        result["summary"] = (
            f"Sync gate PASSED with {len(warnings)} warning(s)"
        )
    else:
        result["status"] = "passed"
        result["summary"] = "All sync gate rules satisfied"

    return result


def save_sync_evidence(project_dir: str, result: dict) -> str:
    """Save sync check result to ``.yuleosh/reports/docsync-evidence.json``.

    Returns the output file path.
    """
    report_dir = Path(project_dir) / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    evidence_path = report_dir / "docsync-evidence.json"
    with open(evidence_path, "w") as f:
        json.dump(result, f, indent=2)

    log.info("Sync check evidence saved to %s", evidence_path)
    return str(evidence_path)


def print_sync_result(result: dict) -> None:
    """Print a human-readable summary of the sync check result."""
    status = result.get("status", "unknown")
    if status == "passed":
        status_icon = "✅"
    elif status == "warning":
        status_icon = "⚠️"
    else:
        status_icon = "❌"

    print(f"\n  📝 Doc Sync Gate Check")
    print(f"  {'=' * 50}")
    print(f"  Status: {status_icon} {status.upper()}")
    print(f"  Generated: {result.get('generated_at', '')[:19]}")
    print()

    changed = result.get("changed_files", [])
    print(f"  Changed files ({len(changed)}):")
    for cf in changed:
        print(f"    • {cf}")
    print()

    rules = result.get("rule_results", [])
    if not rules:
        print(f"  ✅ All sync gate rules satisfied — no documentation gaps")
        return

    errors = [r for r in rules if r.get("severity") == "error"]
    warnings = [r for r in rules if r.get("severity") == "warning"]

    for e in errors:
        print(f"  ❌ [ERROR] {e['rule_id']}")
        print(f"       Reason: {e.get('reason', 'N/A')}")
        print(f"       Issue:  {e.get('message', 'N/A')}")
        for mf in e.get("matched_files", []):
            print(f"       ← {mf}")
        print()

    for w in warnings:
        print(f"  ⚠️  [WARNING] {w['rule_id']}")
        print(f"       Reason: {w.get('reason', 'N/A')}")
        print(f"       Issue:  {w.get('message', 'N/A')}")
        print()

    print(f"  {'─' * 50}")
    print(f"  {len(errors)} error(s), {len(warnings)} warning(s)")
    print()

    evidence_path = result.get("_evidence_path", "")
    if evidence_path:
        print(f"  Evidence saved: {evidence_path}")
    print()


def main():
    """CLI entry point for ``yuleosh audit sync-check``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Doc sync gate — verify docs are updated with code changes",
    )
    parser.add_argument(
        "--project-dir", default=os.environ.get("OSH_HOME", os.getcwd()),
        help="Project root directory",
    )
    parser.add_argument(
        "--base-ref", default="HEAD",
        help="Git base reference for diff (default: HEAD)",
    )
    parser.add_argument(
        "--save", action="store_true", default=True,
        help="Save evidence to .yuleosh/reports/docsync-evidence.json",
    )
    args = parser.parse_args()

    project_dir = args.project_dir
    result = run_sync_check(project_dir, base_ref=args.base_ref)

    if args.save:
        path = save_sync_evidence(project_dir, result)
        result["_evidence_path"] = path

    print_sync_result(result)

    if result.get("status") == "failed":
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
