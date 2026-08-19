#!/usr/bin/env python3
"""Pipeline step-level profiling baseline extractor.

Reads .osh/sessions/*/session.json (started_at/completed_at per step) and
aggregates per-step wall-clock timings: median / mean / p95 / max / n.

Usage:
    python3 scripts/profile_pipeline_steps.py [--dir <project_root>] [--top 30]

Outputs a markdown table to stdout (pipe to docs/planning/ for the baseline).
No code changes to the engine — pure observer over existing session data.
"""
import argparse
import glob
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=".", help="project root containing .osh/sessions/")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    base = os.path.join(args.dir, ".osh", "sessions")
    files = sorted(glob.glob(os.path.join(base, "*", "session.json")))
    if not files:
        print(f"No sessions found under {base}")
        return

    per_step = defaultdict(list)
    valid = 0
    for fp in files:
        try:
            with open(fp) as f:
                s = json.load(f)
        except Exception:
            continue
        steps = s.get("steps") or []
        if not steps:
            continue
        valid += 1
        sess_dir = os.path.basename(os.path.dirname(fp))
        for st in steps:
            t0 = parse_ts(st.get("started_at"))
            t1 = parse_ts(st.get("completed_at"))
            if t0 and t1:
                el = (t1 - t0).total_seconds()
                if el >= 0:
                    key = st.get("step_key") or st.get("name", "?")
                    per_step[key].append((el, sess_dir, st.get("status")))

    print(f"Sessions scanned: {len(files)}, valid (has steps): {valid}")
    rows = []
    for k, vals in per_step.items():
        times = [v[0] for v in vals]
        times_sorted = sorted(times)
        p95 = times_sorted[min(len(times_sorted) - 1, int(len(times_sorted) * 0.95))]
        rows.append((k, len(vals), statistics.median(times), statistics.mean(times), p95, max(times)))
    rows.sort(key=lambda r: -r[2])

    print(f"\n| step_key | n | median(s) | mean(s) | p95(s) | max(s) |")
    print(f"|---|---|---|---|---|---|")
    for k, n, med, mean, p95, mx in rows[: args.top]:
        print(f"| {k} | {n} | {med:.1f} | {mean:.1f} | {p95:.1f} | {mx:.1f} |")


if __name__ == "__main__":
    main()
