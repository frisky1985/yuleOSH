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

# YAML文档Schema验证（CL2-E05：文档-代码同步 YAML Schema 验证）
# 定义需要验证的文档类型及其预期的Schema字段
DOC_YAML_SCHEMAS = {
    "architecture": {
        "required_fields": ["module_name", "version", "last_updated", "code_path"],
        "patterns": ["docs/architecture/**/*.yaml", "docs/architecture/**/*.yml"],
    },
    "interface": {
        "required_fields": ["interface_name", "parameters", "return_type", "changelog"],
        "patterns": ["docs/interfaces/**/*.yaml", "docs/interfaces/**/*.yml"],
    },
    "requirement": {
        "required_fields": ["requirement_id", "description", "status", "code_module"],
        "patterns": ["docs/requirements/**/*.yaml", "docs/requirements/**/*.yml"],
    },
}


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


# ------------------------------------------------------------------
# CL2-E05: YAML Schema validation for document files
# ------------------------------------------------------------------


def validate_doc_yaml_schema(project_dir: str) -> list[dict]:
    """Validate YAML document files against expected schemas (CL2-E05).

    Scans the project for YAML documents matching known patterns
    (architecture, interface, requirement) and validates that each
    contains the required fields defined in DOC_YAML_SCHEMAS.

    Returns a list of findings (error/warning/info) per document.
    """
    findings: list[dict] = []
    project_path = Path(project_dir)
    import yaml

    for doc_type, schema in DOC_YAML_SCHEMAS.items():
        required = schema["required_fields"]
        patterns = schema["patterns"]
        matching_files: list[Path] = []
        for pat in patterns:
            matching_files.extend(project_path.glob(pat))

        if not matching_files:
            findings.append({
                "rule": f"schema-{doc_type}",
                "severity": "info",
                "message": f"No {doc_type} YAML documents found matching {patterns}",
            })
            continue

        for f in matching_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh)
            except (OSError, yaml.YAMLError) as e:
                findings.append({
                    "rule": f"schema-{doc_type}",
                    "severity": "error",
                    "file": str(f),
                    "message": f"Cannot parse YAML file: {e}",
                })
                continue

            if not isinstance(doc, dict):
                findings.append({
                    "rule": f"schema-{doc_type}",
                    "severity": "error",
                    "file": str(f),
                    "message": f"Expected a YAML mapping (dict), got {type(doc).__name__}",
                })
                continue

            missing = [rf for rf in required if rf not in doc]
            if missing:
                findings.append({
                    "rule": f"schema-{doc_type}",
                    "severity": "error",
                    "file": str(f),
                    "message": f"Missing required field(s): {', '.join(missing)}",
                })
            else:
                findings.append({
                    "rule": f"schema-{doc_type}",
                    "severity": "info",
                    "file": str(f),
                    "message": f"All required fields present: {', '.join(required)}",
                })

    return findings


# ------------------------------------------------------------------
# CL2-E06: Document state gate with critical/warning differentiation
# ------------------------------------------------------------------


def run_sync_check_gate(
    project_dir: str,
    base_ref: str = "HEAD",
) -> dict:
    """Enhanced sync gate combining doc-tracking (E06) and schema validation (E05).

    Returns a consolidated result dict with:
        - status: "passed" | "failed" | "warning"
        - tracking_results: results from run_sync_check()
        - schema_results: results from validate_doc_yaml_schema()
        - summary: text summary
    """
    result: dict = {
        "status": "passed",
        "tracking_results": {},
        "schema_results": [],
        "summary": "",
        "generated_at": datetime.now().isoformat(),
    }

    # Part A: run_sync_check (E06)
    tracking = run_sync_check(project_dir, base_ref=base_ref)
    result["tracking_results"] = tracking

    # Part B: validate_doc_yaml_schema (E05)
    schema_findings = validate_doc_yaml_schema(project_dir)
    result["schema_results"] = schema_findings

    # Determine overall status
    tracking_status = tracking.get("status", "passed")
    schema_errors = [
        sf for sf in schema_findings if sf.get("severity") == "error"
    ]

    if tracking_status == "failed" or schema_errors:
        result["status"] = "failed"
    elif tracking_status == "warning" or any(
        sf.get("severity") in ("error", "warning") for sf in schema_findings
    ):
        result["status"] = "warning"
    else:
        result["status"] = "passed"

    total_findings = len(schema_findings) + len(tracking.get("rule_results", []))
    error_count = len(schema_errors) + sum(
        1 for r in tracking.get("rule_results", []) if r.get("severity") == "error"
    )
    warning_count = sum(
        1 for r in tracking.get("rule_results", []) if r.get("severity") == "warning"
    )

    result["summary"] = (
        f"Sync gate: {result['status']} | {total_findings} total, "
        f"{error_count} error(s), {warning_count} warning(s)"
    )

    return result


def print_sync_result(result: dict) -> None:
    """Print a human-readable summary of the sync check result.

    Supports both plain run_sync_check() output and the enhanced
    run_sync_check_gate() output with schema validation results.
    """
    # Deeper access: if this is run_sync_check_gate output, extract sub-results
    tracking = result.get("tracking_results", result)
    schema_results = result.get("schema_results", [])

    status = result.get("status", tracking.get("status", "unknown"))
    if status == "passed":
        status_icon = "✅"
    elif status == "warning":
        status_icon = "⚠️"
    else:
        status_icon = "❌"

    print(f"\n  📝 Doc Sync Gate Check")
    print(f"  {'=' * 50}")
    print(f"  Status: {status_icon} {status.upper()}")
    print(f"  Generated: {result.get('generated_at', tracking.get('generated_at', ''))[:19]}")
    print()

    # Part 1: Code→Doc tracking (E06)
    changed = tracking.get("changed_files", [])
    print(f"  🎯 [E06] Code-Doc Tracking")
    print(f"  {'─' * 50}")
    print(f"  Changed files ({len(changed)}):")
    for cf in changed:
        print(f"    • {cf}")
    print()

    rules = tracking.get("rule_results", [])
    if rules:
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
    else:
        print(f"  ✅ All code→doc tracking rules satisfied")
    print()

    # Part 2: YAML Schema validation (E05)
    print(f"  📐 [E05] YAML Schema Validation")
    print(f"  {'─' * 50}")
    if schema_results:
        schema_errors = [s for s in schema_results if s.get("severity") == "error"]
        schema_warnings = [s for s in schema_results if s.get("severity") == "warning"]
        schema_infos = [s for s in schema_results if s.get("severity") == "info"]

        for e in schema_errors:
            print(f"  ❌ [ERROR] {e.get('rule', '?')}: {e.get('message', '')}")
            if e.get("file"):
                print(f"       File: {e['file']}")
            print()

        for w in schema_warnings:
            print(f"  ⚠️  [WARNING] {w.get('rule', '?')}: {w.get('message', '')}")
            if w.get("file"):
                print(f"       File: {w['file']}")
            print()

        print(f"  {len(schema_errors)} schema error(s), {len(schema_warnings)} warning(s), "
              f"{len(schema_infos)} info(s)")
    else:
        print(f"  ✅ No schema validation issues")
    print()

    evidence_path = result.get("_evidence_path", "")
    if evidence_path:
        print(f"  Evidence saved: {evidence_path}")
    print()


def main():
    """CLI entry point for ``yuleosh audit sync-check``."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Doc sync gate — verify docs are updated with code changes "
                    "(CL2-E05: YAML Schema validation + E06: doc tracking gate)",
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
    parser.add_argument(
        "--enhanced", action="store_true",
        help="Run enhanced gate including YAML Schema validation (CL2-E05)",
    )
    args = parser.parse_args()

    project_dir = args.project_dir

    if args.enhanced:
        result = run_sync_check_gate(project_dir, base_ref=args.base_ref)
    else:
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
