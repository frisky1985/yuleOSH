#!/usr/bin/env python3
"""Collect a normalized ASPICE v3.1 compliance golden baseline.

Part of A1-01 (TASK_STATUS T-010). Freezes the current ComplianceChecker
output as a regression safety net for the upcoming profile-driven refactor
(A1-05): after the refactor the checker must still emit byte-identical
normalized output for the same fixture.

Usage:
    python scripts/collect_compliance_golden.py --project <dir> --out <json>

Normalization — non-deterministic fields removed / relativized:
  - generated_at : dropped (timestamp)
  - project_dir  : replaced with <GOLDEN_PROJECT_DIR> (absolute path)
  - kg_data      : kept as-is (deterministic {} for fixtures without a KG store)
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


def normalize_report(report: dict) -> dict:
    """Strip non-deterministic fields for byte-stable golden comparison."""
    r = copy.deepcopy(report)
    r.pop("generated_at", None)
    if "project_dir" in r:
        r["project_dir"] = "<GOLDEN_PROJECT_DIR>"
    return r


def stable_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)


def collect(project_dir: str, out_path: Path) -> Path:
    """Run ComplianceChecker on ``project_dir``, normalize, write golden JSON."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    report = ComplianceChecker(project_dir).run()
    norm = normalize_report(report)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stable_json(norm), encoding="utf-8")
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Collect ASPICE v3.1 compliance golden baseline"
    )
    ap.add_argument("--project", required=True, help="Project directory to scan")
    ap.add_argument("--out", required=True, help="Output golden JSON path")
    args = ap.parse_args(argv)
    out = collect(args.project, Path(args.out))
    print(f"golden written: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
