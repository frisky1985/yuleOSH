# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Review endpoints — auto-review, task review, list reviews."""

import json
import os
import sys
import subprocess
from pathlib import Path

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
def handle_review(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to review sub-resources."""
    if path_tail == "auto" and method == "POST":
        return _run_auto_review(body)
    elif path_tail == "task" and method == "POST":
        return _run_task_review(body)
    elif path_tail == "list" and method == "GET":
        return _list_reviews()
    elif path_tail == "" and method == "GET":
        return _list_reviews()
    return json_error(f"Unknown review resource: {path_tail}", 404)


def _run_auto_review(body: dict) -> tuple[dict, int]:
    """POST /api/v1/review/auto — auto-review changed files."""
    project_dir = os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent)

    try:
        # Use subprocess to run the review engine
        result = subprocess.run(
            [sys.executable, "src/review/run.py", "auto"],
            capture_output=True, text=True, timeout=120,
            cwd=project_dir,
        )
        return json_ok({
            "status": "completed",
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        })
    except subprocess.TimeoutExpired:
        return json_error("Auto-review timed out", 504)
    except Exception as e:
        return json_error(f"Review error: {e}", 500)


def _run_task_review(body: dict) -> tuple[dict, int]:
    """POST /api/v1/review/task — review a specific task."""
    task_name = body.get("task", "")
    task_kind = body.get("kind", "feature")

    if not task_name:
        return json_error("'task' name is required")

    project_dir = os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent)

    try:
        result = subprocess.run(
            [sys.executable, "src/review/run.py", "task", task_name, task_kind],
            capture_output=True, text=True, timeout=120,
            cwd=project_dir,
        )
        return json_ok({
            "task": task_name,
            "kind": task_kind,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        })
    except subprocess.TimeoutExpired:
        return json_error("Task review timed out", 504)
    except Exception as e:
        return json_error(f"Task review error: {e}", 500)


def _list_reviews() -> tuple[dict, int]:
    """GET /api/v1/review/list — list all review sessions."""
    from . import OSH_HOME

    rev_dir = Path(OSH_HOME) / ".osh" / "reviews"
    sessions = []
    if rev_dir.exists():
        for d in sorted(rev_dir.iterdir(), reverse=True):
            if d.is_dir():
                sess_file = d / "review-session.json"
                if sess_file.exists():
                    data = json.loads(sess_file.read_text())
                    sessions.append(data)

    return json_ok({"sessions": sessions, "count": len(sessions)})
