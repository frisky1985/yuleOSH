# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Usage statistics endpoints — overview counts and trends.

GET /api/v1/stats/overview — aggregated counts of everything
GET /api/v1/stats/trends — daily/weekly trends (if timestamps available)
"""

from datetime import datetime, timedelta
from collections import defaultdict

from . import json_ok, json_error
from yuleosh.store import Store


def handle_stats(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to stats sub-resources."""
    if method != "GET":
        return json_error("Use GET for stats", 405)

    if path_tail == "overview":
        return _overview()
    elif path_tail == "trends":
        return _trends(query)
    else:
        return json_error(f"Unknown stats resource: {path_tail}", 404)


def _overview():
    """GET /api/v1/stats/overview — aggregated counts of everything."""
    store = Store()
    stats = store.get_usage_stats()

    # Add computed fields
    success_rate = 0
    if stats["total_pipelines"] > 0:
        completed = stats["pipeline_statuses"].get("completed", 0)
        success_rate = round(completed / stats["total_pipelines"] * 100, 1)

    ci_pass_rate = 0
    if stats["total_ci_runs"] > 0:
        passed = 0
        try:
            conn = store.conn
            passed = conn.execute(
                "SELECT COUNT(*) as c FROM ci_runs WHERE status='passed'"
            ).fetchone()["c"]
        except Exception as e:
            import logging; logging.getLogger("api.stats").warning("Stats query error: %s", e)
            passed = 0
            pass
        ci_pass_rate = round(passed / stats["total_ci_runs"] * 100, 1)

    return json_ok({
        **stats,
        "pipeline_success_rate": success_rate,
        "ci_pass_rate": ci_pass_rate,
        "generated_at": datetime.now().isoformat(),
    })


def _trends(query: dict):
    """GET /api/v1/stats/trends — daily or weekly trends.

    Query params:
        period: "daily" or "weekly" (default: "daily")
        days: number of days to look back (default: 7)
    """
    period = query.get("period", ["daily"])[0]
    days = int(query.get("days", ["7"])[0])

    if period not in ("daily", "weekly"):
        return json_error("period must be 'daily' or 'weekly'", 400)

    store = Store()
    conn = store.conn

    now = datetime.now()
    start_date = now - timedelta(days=days)
    start_str = start_date.isoformat()

    # Gather pipeline runs by date
    pipe_rows = conn.execute(
        "SELECT created_at, status FROM pipelines WHERE created_at >= ? ORDER BY created_at",
        (start_str,)
    ).fetchall()

    # Gather CI runs by date
    ci_rows = conn.execute(
        "SELECT started_at, status FROM ci_runs WHERE started_at >= ? ORDER BY started_at",
        (start_str,)
    ).fetchall()

    # Gather reviews by date
    review_rows = conn.execute(
        "SELECT created_at FROM reviews WHERE created_at >= ? ORDER BY created_at",
        (start_str,)
    ).fetchall()

    def _bucket_key(iso_date: str, period: str) -> str:
        """Convert ISO datetime to bucket key."""
        try:
            dt = datetime.fromisoformat(iso_date)
            if period == "weekly":
                # ISO week
                iso_year, iso_week, _ = dt.isocalendar()
                return f"{iso_year}-W{iso_week:02d}"
            else:
                return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return "unknown"

    # Build buckets
    pipelines_by_bucket = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})
    ci_by_bucket = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0})
    reviews_by_bucket = defaultdict(int)

    for row in pipe_rows:
        key = _bucket_key(row["created_at"], period)
        pipelines_by_bucket[key]["total"] += 1
        if row["status"] in ("completed", "passed"):
            pipelines_by_bucket[key]["completed"] += 1
        elif row["status"] in ("failed", "error"):
            pipelines_by_bucket[key]["failed"] += 1

    for row in ci_rows:
        key = _bucket_key(row["started_at"], period)
        ci_by_bucket[key]["total"] += 1
        if row["status"] == "passed":
            ci_by_bucket[key]["passed"] += 1
        elif row["status"] == "failed":
            ci_by_bucket[key]["failed"] += 1

    for row in review_rows:
        key = _bucket_key(row["created_at"], period)
        reviews_by_bucket[key] += 1

    # Build sorted results
    all_buckets = sorted(set(
        list(pipelines_by_bucket.keys()) +
        list(ci_by_bucket.keys()) +
        list(reviews_by_bucket.keys())
    ))

    trend_data = []
    for bucket in all_buckets:
        trend_data.append({
            "period": bucket,
            "pipelines": pipelines_by_bucket[bucket],
            "ci_runs": ci_by_bucket[bucket],
            "reviews_total": reviews_by_bucket[bucket],
        })

    return json_ok({
        "period": period,
        "days_lookback": days,
        "buckets": trend_data,
        "total_points": len(trend_data),
        "generated_at": now.isoformat(),
    })
