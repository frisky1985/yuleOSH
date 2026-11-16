#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""运行历史聚合（AUD-ASPICE-001 NC-13 / CL3 量化管理）。

CL3 要求过程可量化：连续运行成功率、门禁失败分布、缺陷密度趋势。本模块
从 session 目录读取 ``session.json``（以及同目录的 ``gate-summary.json``），
输出最近 N 次运行的统计。

用法::

    python -m yuleosh.ci.kpi.history --window 10 --out .osh/metrics/history.json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ci.kpi.history")

_GREEN_OUTCOMES = frozenset({"green"})


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _session_runs(sessions_root: Path) -> list[dict]:
    """读取每个 run 目录的 session.json（按 started_at 升序）。"""
    runs: list[dict] = []
    if not sessions_root.is_dir():
        return runs
    for run_dir in sessions_root.iterdir():
        session_file = run_dir / "session.json"
        if not session_file.is_file():
            continue
        data = _load_json(session_file)
        if not data:
            continue
        verdict = data.get("gate_verdict") or {}
        runs.append({
            "run_id": data.get("name") or run_dir.name,
            "status": data.get("status") or "unknown",
            "started_at": data.get("started_at") or "",
            "finished_at": data.get("finished_at") or "",
            "outcome": (verdict.get("outcome") or "").strip().lower(),
            "blocking_gates": verdict.get("blocking_gates") or [],
            "errors": len(data.get("errors") or []),
            "session_dir": str(run_dir),
        })
    runs.sort(key=lambda r: (r["started_at"], r["run_id"]))
    return runs


def summarize(sessions_root, window: int = 10) -> dict:
    """聚合最近 ``window`` 次运行。

    Returns
    -------
    dict
        ``{runs, green, success_rate_pct, outcomes, gate_failures, window}``
    """
    runs = _session_runs(Path(sessions_root))
    recent = runs[-window:] if window > 0 else runs
    total = len(recent)
    green = sum(1 for r in recent if r["outcome"] in _GREEN_OUTCOMES)
    outcomes: dict[str, int] = {}
    gate_failures: dict[str, int] = {}
    for run in recent:
        key = run["outcome"] or "unknown"
        outcomes[key] = outcomes.get(key, 0) + 1
        for blocker in run["blocking_gates"]:
            gate = str(blocker.get("gate") or "unknown")
            status = str(blocker.get("status") or "unknown")
            label = f"{gate}:{status}"
            gate_failures[label] = gate_failures.get(label, 0) + 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_runs_seen": len(runs),
        "window": window,
        "runs": total,
        "green": green,
        "success_rate_pct": round(green / total * 100, 1) if total else 0.0,
        "outcomes": outcomes,
        "gate_failures": dict(sorted(gate_failures.items(),
                                     key=lambda kv: -kv[1])),
        "recent": [
            {k: v for k, v in run.items() if k != "session_dir"}
            for run in recent
        ],
    }


def write_report(sessions_root, out_path, window: int = 10) -> dict:
    report = summarize(sessions_root, window=window)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    return report


def _main(argv=None) -> int:
    from yuleosh.pipeline.session import resolve_sessions_root

    parser = argparse.ArgumentParser(description="yuleOSH run-history KPIs")
    parser.add_argument("--sessions-root", default=None)
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--out", default=".osh/metrics/history.json")
    args = parser.parse_args(argv)

    root = Path(args.sessions_root) if args.sessions_root else resolve_sessions_root()
    report = write_report(root, args.out, window=args.window)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
