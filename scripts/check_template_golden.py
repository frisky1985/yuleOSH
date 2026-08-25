#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Check template golden samples — CI regression script.

Iterates all templates under src/yuleosh/templates/ and templates/,
runs compare_to_golden on each template that has a golden/ subdir,
prints a result table, and exits 1 if any critical failure is found.

Usage:
    python scripts/check_template_golden.py
    python scripts/check_template_golden.py --json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root without installing
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from yuleosh.templates.golden import load_golden, compare_to_golden


def _find_template_dirs() -> list[Path]:
    dirs: list[Path] = []
    for base in [
        _REPO_ROOT / "src" / "yuleosh" / "templates",
        _REPO_ROOT / "templates",
    ]:
        if not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if p.is_dir() and not p.name.startswith("_") and not p.name.startswith("."):
                dirs.append(p)
        # ECU subdir
        ecus = base / "ecus"
        if ecus.is_dir():
            for p in sorted(ecus.iterdir()):
                if p.is_dir():
                    dirs.append(p)
    return dirs


def main() -> int:
    to_json = "--json" in sys.argv
    template_dirs = _find_template_dirs()

    rows: list[dict] = []
    total_critical = 0

    for tdir in template_dirs:
        golden = load_golden(tdir)
        if golden is None:
            continue
        result = compare_to_golden(golden.golden_dir, golden)
        rows.append({
            "template": golden.template_name,
            "status": result["status"],
            "critical_failures": result["critical_failures"],
            "warn_count": result["warn_count"],
            "diffs": result["diffs"],
        })
        total_critical += result["critical_failures"]

    if to_json:
        print(json.dumps({"templates": rows, "total_critical_failures": total_critical}, indent=2))
    else:
        if not rows:
            print("No templates with golden/ samples found.")
            return 0
        w = max(len(r["template"]) for r in rows)
        print(f"\n{'Template':<{w}}  {'Status':<8}  {'Critical':<8}  {'Warns'}")
        print("-" * (w + 30))
        for r in rows:
            icon = {"pass": "✅", "warn": "⚠️ ", "fail": "❌"}.get(r["status"], "?")
            print(f"{r['template']:<{w}}  {icon} {r['status']:<6}  {r['critical_failures']:<8}  {r['warn_count']}")
        print(f"\nTotal templates checked: {len(rows)}  |  Critical failures: {total_critical}")

    return 1 if total_critical > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
