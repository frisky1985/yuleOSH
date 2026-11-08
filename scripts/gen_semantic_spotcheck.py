#!/usr/bin/env python3

# @req RS-005
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Generate the semantic spot-check sheet for traceability links.

Usage:
    python3 scripts/gen_semantic_spotcheck.py [--project .] [--count 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yuleosh.evidence.spotcheck import (  # noqa: E402
    DEFAULT_COUNT,
    load_requirements,
    render_checklist,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=str(ROOT))
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument(
        "--out",
        default="docs/evidence/pending-reviews/semantic-spotcheck.md",
    )
    args = parser.parse_args()

    project = Path(args.project).resolve()
    matrix = project / ".osh" / "evidence" / "traceability-matrix.json"
    if not matrix.exists():
        print(f"matrix not found: {matrix}", file=sys.stderr)
        return 1

    rows = load_requirements(matrix)
    content = render_checklist(rows, project, args.count)

    out = project / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"semantic spot-check written: {out} ({min(args.count, len(rows))} samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
