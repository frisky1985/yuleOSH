#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step CI.1: 小马 — MISRA CI 结果审查。

MISRA 检查完成后自动分析结果：
- 解析 .yuleosh/reports/misra-report.json
- 计算违规趋势（与上次运行对比）
- 给出修复建议优先级
- 标记需要偏差申请的违规

Exports:
  step_review_misra_ci — MISRA CI result analysis and trend review
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_misra_ci")

__all__ = ["step_review_misra_ci"]

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_DEFAULT_REPORT_DIR = ".yuleosh/reports"
_DEFAULT_TREND_FILE = ".yuleosh/reports/misra-trend.jsonl"

# Severity-to-priority mapping for MISRA rules
_PRIORITY_MAP: dict[str, int] = {
    "required": 1,
    "advisory": 2,
    "unknown": 3,
}


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _read_misra_report(project_dir: Path) -> Optional[dict]:
    """Read the latest MISRA report from the standard location.

    Returns the parsed JSON dict, or None if the report does not exist
    or cannot be read.
    """
    report_path = project_dir / _DEFAULT_REPORT_DIR / "misra-report.json"
    if not report_path.exists():
        log.warning("MISRA report not found: %s", report_path)
        return None
    try:
        return json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read MISRA report: %s", e)
        return None


def _read_misra_trend(project_dir: Path, max_entries: int = 20) -> list[dict]:
    """Read trend entries from the MISRA trend file.

    Returns a list of entries, most recent first, limited to max_entries.
    """
    trend_path = project_dir / _DEFAULT_TREND_FILE
    if not trend_path.exists():
        return []

    entries: list[dict] = []
    try:
        with open(trend_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
    except OSError as e:
        log.warning("Failed to read MISRA trend: %s", e)
        return []

    # Most recent first
    entries.reverse()
    return entries[:max_entries]


def _compute_trend(current: dict, previous: Optional[dict]) -> dict:
    """Compare current MISRA results with the previous run.

    Returns a dict with keys:
      - direction: "up" | "down" | "same" | "first_run"
      - delta: int (change in total violations)
      - required_delta: int
      - advisory_delta: int
    """
    if previous is None:
        return {
            "direction": "first_run",
            "delta": 0,
            "required_delta": 0,
            "advisory_delta": 0,
        }

    curr_total = current.get("summary", {}).get("total_violations", 0)
    prev_total = previous.get("summary", {}).get("total_violations", 0)

    curr_required = sum(
        1 for v in current.get("violations_raw", [])
        if v.get("severity") in ("error", "warning")
    )
    prev_required = sum(
        1 for v in previous.get("violations_raw", [])
        if v.get("severity") in ("error", "warning")
    )

    diff = curr_total - prev_total
    req_diff = curr_required - prev_required

    if diff > 0:
        direction = "up"
    elif diff < 0:
        direction = "down"
    else:
        direction = "same"

    return {
        "direction": direction,
        "delta": diff,
        "required_delta": req_diff,
        "previous_total": prev_total,
        "current_total": curr_total,
    }


def _classify_violations(report: dict) -> list[dict]:
    """Classify violations by severity and priority.

    Returns a list of dicts with:
      - rule_id: str
      - severity: str ("required" | "advisory" | "unknown")
      - priority: int (1=highest, 3=lowest)
      - count: int
      - needs_deviation: bool (true if severity is "required" and count > 0)
    """
    groups = report.get("groups", {})
    classified: list[dict] = []

    for rule_id, group in groups.items():
        sev = group.get("severity_category", "unknown").lower()
        count = group.get("count", 0)
        priority = _PRIORITY_MAP.get(sev, 3)

        classified.append({
            "rule_id": rule_id,
            "severity": sev,
            "priority": priority,
            "count": count,
            "title": group.get("title", ""),
            "files": group.get("files", []),
            "needs_deviation": sev == "required" and count > 0,
        })

    # Sort by priority (1 first), then by count descending
    classified.sort(key=lambda x: (x["priority"], -x["count"]))
    return classified


def _generate_fix_recommendations(
    classified: list[dict],
    trend: dict,
    total_violations: int,
) -> list[str]:
    """Generate human-readable fix recommendations.

    Returns a list of recommendation strings.
    """
    recommendations: list[str] = []

    # Priority 1 (required, must fix) violations
    p1 = [c for c in classified if c["priority"] == 1 and c["count"] > 0]
    if p1:
        total_p1 = sum(c["count"] for c in p1)
        rule_list = ", ".join(c["rule_id"] for c in p1[:5])
        recommendations.append(
            f"PRIORITY 1 — Fix {total_p1} Required violation(s) across "
            f"{len(p1)} rule(s): {rule_list}"
        )
        if len(p1) > 5:
            recommendations[-1] += f" and {len(p1) - 5} more"

    # Priority 2 (advisory) violations
    p2 = [c for c in classified if c["priority"] == 2 and c["count"] > 0]
    if p2:
        total_p2 = sum(c["count"] for c in p2)
        recommendations.append(
            f"PRIORITY 2 — Address {total_p2} Advisory violation(s) "
            f"when convenient to improve code quality"
        )

    # Trend-based recommendations
    if trend["direction"] == "up":
        recommendations.append(
            f"⚠️ Violations increased by {trend['delta']} — review "
            f"recent changes for new MISRA violations"
        )
    elif trend["direction"] == "down":
        recommendations.append(
            f"✅ Violations decreased by {abs(trend['delta'])} — "
            f"good progress on MISRA compliance"
        )

    # Deviation recommendations
    needs_deviation = [c for c in classified if c["needs_deviation"]]
    if needs_deviation:
        dev_rules = ", ".join(c["rule_id"] for c in needs_deviation[:3])
        recommendations.append(
            f"Deviation required — {len(needs_deviation)} Required rule(s) "
            f"with active violations need formal deviation approval: {dev_rules}"
        )

    if not p1 and not p2:
        recommendations.append(
            "No actionable MISRA violations found. Continue maintaining compliance."
        )

    return recommendations


def _check_for_regression_violations(
    current_report: dict,
    trend_entries: list[dict],
) -> list[dict]:
    """Identify violations that appear to be new regressions.

    Compares current violation rules with previous run (if available).

    Returns a list of regression findings.
    """
    regression_findings: list[dict] = []

    if len(trend_entries) < 2:
        return regression_findings

    prev_entries = trend_entries[-2:]  # current + one previous
    if len(prev_entries) < 2:
        return regression_findings

    curr_total = current_report.get("summary", {}).get("total_violations", 0)

    for entry in reversed(prev_entries):
        prev_total = entry.get("total_violations", 0)
        if curr_total > prev_total:
            regression_findings.append({
                "type": "regression",
                "previous_violations": prev_total,
                "current_violations": curr_total,
                "delta": curr_total - prev_total,
                "possible_cause": "New violations introduced since last MISRA check",
            })
            break
        elif curr_total < prev_total:
            regression_findings.append({
                "type": "improvement",
                "previous_violations": prev_total,
                "current_violations": curr_total,
                "delta": curr_total - prev_total,
                "possible_cause": "Violations resolved since last MISRA check",
            })
            break

    return regression_findings


# ------------------------------------------------------------------
# Main step handler
# ------------------------------------------------------------------


@timed_step
def step_review_misra_ci(session: PipelineSession) -> str:
    """Step CI.1: 小马 — MISRA CI result review.

    Analyzes the MISRA check output after CI Layer 1 completes:
    - Reads the structured MISRA report from .yuleosh/reports/
    - Compares with previous runs via trend data
    - Classifies violations by severity and priority
    - Generates fix recommendations
    - Marks violations that need formal deviation requests

    Reports are written to {session_dir}/misra-review.json.
    """
    try:
        print("  🔮 [小马] Analyzing MISRA CI results...")
        log.info("Analyzing MISRA CI results")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- 1. Read current MISRA report ---
        report = _read_misra_report(project_dir)
        if report is None:
            log.warning("No MISRA report found — MISRA check may not have run")
            review = {
                "session": session.name,
                "reviewer": "小马",
                "timestamp": datetime.now().isoformat(),
                "status": "skipped",
                "summary": {
                    "message": "MISRA report not found — CI MISRA check may not have been executed.",
                    "total_violations": 0,
                    "trend_available": False,
                },
                "recommendations": ["Run CI Layer 1 MISRA check first to generate report data."],
            }
            out_path = session.session_dir / "misra-review.json"
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
            print("  ⏭️  [小马] No MISRA report found — skipped")
            return str(out_path)

        summary = report.get("summary", {})
        total_violations = summary.get("total_violations", 0)
        groups = report.get("groups", {})

        # --- 2. Read trend data ---
        trend_entries = _read_misra_trend(project_dir, max_entries=20)
        previous_trend = trend_entries[1] if len(trend_entries) >= 2 else None

        # --- 3. Compute trend ---
        # Build a "previous report" from trend data for comparison
        previous_report: Optional[dict] = None
        if previous_trend:
            previous_report = {
                "summary": {
                    "total_violations": previous_trend.get("total_violations", 0),
                },
            }

        trend = _compute_trend(report, previous_report)
        log.info("MISRA trend: %s (delta=%d)", trend["direction"], trend["delta"])

        # --- 4. Classify violations ---
        classified = _classify_violations(report)

        # --- 5. Check for regressions ---
        regression_findings = _check_for_regression_violations(report, trend_entries)

        # --- 6. Generate recommendations ---
        recommendations = _generate_fix_recommendations(
            classified, trend, total_violations,
        )

        # --- 7. Determine overall status ---
        if total_violations == 0:
            status = "passed"
        elif any(c["severity"] == "required" and c["count"] > 0 for c in classified):
            status = "failed"
        elif trend["direction"] == "up":
            status = "warning"
        else:
            status = "passed"

        # --- Compile review ---
        review = {
            "session": session.name,
            "reviewer": "小马",
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "report_source": str(project_dir / _DEFAULT_REPORT_DIR / "misra-report.json"),
            "summary": {
                "total_violations": total_violations,
                "rules_violated": summary.get("total_rules_violated", 0),
                "files_affected": len(summary.get("unique_files", [])),
                "severity_counts": summary.get("severity_counts", {}),
            },
            "trend_analysis": {
                "available": len(trend_entries) > 0,
                "direction": trend["direction"],
                "delta": trend["delta"],
                "required_delta": trend.get("required_delta", 0),
                "previous_total": trend.get("previous_total", 0),
                "current_total": trend.get("current_total", total_violations),
                "runs_recorded": len(trend_entries),
            },
            "violations_by_priority": {
                "p1_required": [
                    c for c in classified if c["priority"] == 1
                ],
                "p2_advisory": [
                    c for c in classified if c["priority"] == 2
                ],
                "p3_info": [
                    c for c in classified if c["priority"] == 3
                ],
            },
            "regression_analysis": regression_findings,
            "needs_deviation": [
                c for c in classified if c["needs_deviation"]
            ],
            "recommendations": recommendations,
        }

        # --- Write output ---
        out_path = session.session_dir / "misra-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write MISRA review: {e}")
            raise PipelineStepError(f"Cannot write MISRA review: {e}")

        # --- Print summary ---
        p1_count = sum(c["count"] for c in classified if c["priority"] == 1)
        p2_count = sum(c["count"] for c in classified if c["priority"] == 2)
        print(f"  ✅ [小马] MISRA CI review completed:")
        print(f"       Total violations: {total_violations}")
        print(f"       P1 (required):    {p1_count}")
        print(f"       P2 (advisory):    {p2_count}")
        print(f"       Trend:            {trend['direction']} ({trend['delta']:+d})")
        print(f"       Status:           {status}")
        if any(c["needs_deviation"] for c in classified):
            dev_rules = [c["rule_id"] for c in classified if c["needs_deviation"]]
            print(f"       ⚠️  Deviation needed: {len(dev_rules)} rule(s)")
            for r in dev_rules[:3]:
                print(f"          - {r}")
        log.info("MISRA review: violations=%d, p1=%d, trend=%s, status=%s",
                 total_violations, p1_count, trend["direction"], status)

        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"MISRA CI review step failed: {e}")
        raise PipelineStepError(f"MISRA CI review step failed: {e}")
