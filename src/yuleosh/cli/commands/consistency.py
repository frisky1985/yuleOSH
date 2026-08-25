# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CLI — Consistency verification command group.

T-004: Cross-run consistency verification for production readiness.

Commands:
  - `yuleosh consistency check <session> --baseline <name>`: Compare session against baseline
  - `yuleosh baseline save <session> --name <name>`: Save session as baseline
  - `yuleosh baseline list`: List all saved baselines
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.cli.consistency")

# OSH_HOME / sys.path bootstrap
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = Path(_SCRIPT_DIR).resolve().parent.parent.parent.parent / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def _osh_home() -> str:
    """Resolve OSH_HOME."""
    try:
        import yuleosh.cli.main as _m
        return _m.OSH_HOME
    except Exception:
        return os.environ.get("OSH_HOME", os.getcwd())


def _baselines_dir() -> Path:
    """Return the baselines directory, creating it if needed."""
    d = Path(_osh_home()) / ".yuleosh" / "baselines"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_session_summary(session_dir: Path) -> dict:
    """Load session summary from gate-summary.json and other artifacts."""
    summary = {
        "session_dir": str(session_dir),
        "gate_summary": {},
        "integrity_hash": None,
        "artifact_hashes": {},
        "test_cases": [],
    }

    # Load gate-summary.json
    gate_summary_path = session_dir / "gate-summary.json"
    if gate_summary_path.exists():
        try:
            data = json.loads(gate_summary_path.read_text(encoding="utf-8"))
            summary["gate_summary"] = data
            # Extract artifact hashes from gates
            for gate in data.get("gates", []):
                for step_key, hash_val in gate.get("artifact_hashes", {}).items():
                    summary["artifact_hashes"][step_key] = hash_val
        except Exception as e:
            log.warning("Failed to load gate-summary.json: %s", e)

    # Load test-cases.json if present
    test_cases_path = session_dir / "test-cases.json"
    if test_cases_path.exists():
        try:
            data = json.loads(test_cases_path.read_text(encoding="utf-8"))
            summary["test_cases"] = data.get("test_cases", [])
        except Exception as e:
            log.warning("Failed to load test-cases.json: %s", e)

    return summary


def _compute_session_fingerprint(session_dir: Path) -> dict:
    """Compute a fingerprint for a session that can be compared across runs."""
    import hashlib

    summary = _load_session_summary(session_dir)

    # Compute fingerprint from all artifact hashes
    fingerprint_data = {
        "artifact_hashes": dict(sorted(summary["artifact_hashes"].items())),
        "test_case_ids": sorted([tc.get("test_id", "") for tc in summary["test_cases"]]),
    }

    canonical = json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "fingerprint": fingerprint,
        "artifact_count": len(summary["artifact_hashes"]),
        "test_case_count": len(summary["test_cases"]),
        "artifact_hashes": summary["artifact_hashes"],
        "test_case_ids": fingerprint_data["test_case_ids"],
    }


def cmd_baseline_save(args):
    """Save a session as a named baseline."""
    project_dir = _osh_home()
    sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"

    session_name = args.session
    session_dir = sessions_dir / session_name

    if not session_dir.exists():
        print(f"Error: Session '{session_name}' not found at {session_dir}")
        return 1

    baseline_name = args.name
    baseline_path = _baselines_dir() / f"{baseline_name}.json"

    # Compute fingerprint
    fingerprint = _compute_session_fingerprint(session_dir)

    # Save baseline
    baseline_data = {
        "name": baseline_name,
        "session": session_name,
        "created_at": datetime.now().isoformat(),
        "fingerprint": fingerprint["fingerprint"],
        "artifact_count": fingerprint["artifact_count"],
        "test_case_count": fingerprint["test_case_count"],
        "artifact_hashes": fingerprint["artifact_hashes"],
        "test_case_ids": fingerprint["test_case_ids"],
    }

    baseline_path.write_text(
        json.dumps(baseline_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n  Baseline saved: {baseline_name}")
    print(f"  Session: {session_name}")
    print(f"  Fingerprint: {fingerprint['fingerprint'][:16]}...")
    print(f"  Artifacts: {fingerprint['artifact_count']}")
    print(f"  Test cases: {fingerprint['test_case_count']}")
    print(f"  Path: {baseline_path}")
    return 0


def cmd_baseline_list(args):
    """List all saved baselines."""
    baselines_dir = _baselines_dir()

    if not baselines_dir.exists():
        print("No baselines found.")
        return 0

    baselines = sorted(baselines_dir.glob("*.json"))
    if not baselines:
        print("No baselines found.")
        return 0

    print(f"\n  Saved baselines ({len(baselines)}):")
    print(f"  {'─' * 60}")
    for b in baselines:
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
            print(f"  {data['name']:<20} session={data['session']:<15} created={data['created_at'][:10]}")
        except Exception:
            print(f"  {b.stem:<20} (invalid)")
    return 0


def cmd_consistency_check(args):
    """Check consistency between a session and a baseline."""
    project_dir = _osh_home()
    sessions_dir = Path(project_dir) / ".yuleosh" / "sessions"

    session_name = args.session
    session_dir = sessions_dir / session_name

    if not session_dir.exists():
        print(f"Error: Session '{session_name}' not found at {session_dir}")
        return 1

    baseline_name = args.baseline
    baseline_path = _baselines_dir() / f"{baseline_name}.json"

    if not baseline_path.exists():
        print(f"Error: Baseline '{baseline_name}' not found at {baseline_path}")
        return 0

    # Load baseline
    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))

    # Compute session fingerprint
    session_fingerprint = _compute_session_fingerprint(session_dir)

    # Compare
    report = {
        "session": session_name,
        "baseline": baseline_name,
        "checked_at": datetime.now().isoformat(),
        "checks": [],
    }

    all_match = True

    # Check 1: Fingerprint match
    fp_match = session_fingerprint["fingerprint"] == baseline_data["fingerprint"]
    report["checks"].append({
        "name": "Overall fingerprint",
        "expected": baseline_data["fingerprint"][:16] + "...",
        "actual": session_fingerprint["fingerprint"][:16] + "...",
        "match": fp_match,
    })
    if not fp_match:
        all_match = False

    # Check 2: Artifact count
    artifact_count_match = session_fingerprint["artifact_count"] == baseline_data["artifact_count"]
    report["checks"].append({
        "name": "Artifact count",
        "expected": baseline_data["artifact_count"],
        "actual": session_fingerprint["artifact_count"],
        "match": artifact_count_match,
    })
    if not artifact_count_match:
        all_match = False

    # Check 3: Test case count
    test_count_match = session_fingerprint["test_case_count"] == baseline_data["test_case_count"]
    report["checks"].append({
        "name": "Test case count",
        "expected": baseline_data["test_case_count"],
        "actual": session_fingerprint["test_case_count"],
        "match": test_count_match,
    })
    if not test_count_match:
        all_match = False

    # Check 4: Individual artifact hashes
    baseline_hashes = baseline_data.get("artifact_hashes", {})
    session_hashes = session_fingerprint["artifact_hashes"]
    artifacts_match = 0
    artifacts_total = len(baseline_hashes)

    for step_key, expected_hash in baseline_hashes.items():
        actual_hash = session_hashes.get(step_key, "")
        if expected_hash == actual_hash:
            artifacts_match += 1

    report["checks"].append({
        "name": "Artifact hashes",
        "expected": f"{artifacts_total} artifacts",
        "actual": f"{artifacts_match}/{artifacts_total} match",
        "match": artifacts_match == artifacts_total,
    })
    if artifacts_match != artifacts_total:
        all_match = False

    # Check 5: Test case IDs
    baseline_test_ids = set(baseline_data.get("test_case_ids", []))
    session_test_ids = set(session_fingerprint["test_case_ids"])
    test_ids_match = baseline_test_ids == session_test_ids

    report["checks"].append({
        "name": "Test case IDs",
        "expected": f"{len(baseline_test_ids)} test cases",
        "actual": f"{len(baseline_test_ids & session_test_ids)}/{len(baseline_test_ids)} match",
        "match": test_ids_match,
    })
    if not test_ids_match:
        all_match = False

    report["overall"] = "CONSISTENT" if all_match else "INCONSISTENT"

    # Print report
    print(f"\n  Consistency Report")
    print(f"  {'─' * 60}")
    print(f"  Session:  {session_name}")
    print(f"  Baseline: {baseline_name}")
    print(f"  Checked:  {report['checked_at'][:19]}")
    print()

    for check in report["checks"]:
        status = "MATCH" if check["match"] else "MISMATCH"
        symbol = "+" if check["match"] else "!"
        print(f"  [{symbol}] {check['name']:<25} {status}")
        print(f"      Expected: {check['expected']}")
        print(f"      Actual:   {check['actual']}")
        print()

    print(f"  {'─' * 60}")
    print(f"  Overall: {report['overall']}")

    # Save report
    report_path = session_dir / "consistency_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  Report saved: {report_path}")

    return 0 if all_match else 1


def register_commands(subparsers):
    """Register consistency commands with the argument parser."""
    # consistency check
    parser_check = subparsers.add_parser(
        "check",
        help="Check consistency between a session and a baseline",
    )
    parser_check.add_argument("session", help="Session name to check")
    parser_check.add_argument("--baseline", "-b", required=True, help="Baseline name")
    parser_check.set_defaults(func=cmd_consistency_check)

    # baseline save
    parser_save = subparsers.add_parser(
        "save",
        help="Save a session as a named baseline",
    )
    parser_save.add_argument("session", help="Session name to save")
    parser_save.add_argument("--name", "-n", required=True, help="Baseline name")
    parser_save.set_defaults(func=cmd_baseline_save)

    # baseline list
    parser_list = subparsers.add_parser(
        "list",
        help="List all saved baselines",
    )
    parser_list.set_defaults(func=cmd_baseline_list)


def build_parser(subparsers):
    """Build the consistency/baseline command group for main CLI integration."""
    # consistency command group
    p_consistency = subparsers.add_parser(
        "consistency",
        help="Cross-run consistency verification (T-004)",
    )
    csub = p_consistency.add_subparsers(dest="consistency_sub")
    register_commands(csub)

    # baseline command group (alias for convenience)
    p_baseline = subparsers.add_parser(
        "baseline",
        help="Baseline management (alias for consistency save/list)",
    )
    bsub = p_baseline.add_subparsers(dest="baseline_sub")

    # baseline save
    parser_save = bsub.add_parser("save", help="Save a session as a named baseline")
    parser_save.add_argument("session", help="Session name to save")
    parser_save.add_argument("--name", "-n", required=True, help="Baseline name")
    parser_save.set_defaults(func=cmd_baseline_save)

    # baseline list
    parser_list = bsub.add_parser("list", help="List all saved baselines")
    parser_list.set_defaults(func=cmd_baseline_list)


def main():
    """Entry point for standalone execution."""
    parser = argparse.ArgumentParser(description="Consistency verification commands")
    subparsers = parser.add_subparsers(dest="command")
    register_commands(subparsers)

    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
