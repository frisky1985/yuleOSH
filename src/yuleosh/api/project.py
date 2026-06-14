# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Project CRUD endpoints."""

from datetime import datetime

from . import json_ok, json_error


def handle_project(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to project sub-resources."""
    from yuleosh.store import Store  # pylint: disable=import-error
    store = Store()

    if path_tail == "stats" and method == "GET":
        return _project_stats(store)

    if method == "GET":
        # GET /api/v1/project — list all
        if path_tail == "" or path_tail == "list":
            return _list_projects(store)
        # GET /api/v1/project/{name} — get specific
        return _get_project(store, path_tail)

    if method == "POST":
        # POST /api/v1/project — create
        return _create_project(store, body)

    return json_error(f"Method {method} not supported for projects", 405)


def _list_projects(store) -> tuple[dict, int]:
    """GET /api/v1/project — list all projects."""
    conn = store.conn
    cur = conn.execute("SELECT * FROM projects ORDER BY created_at DESC")
    projects = [dict(r) for r in cur.fetchall()]
    return json_ok({"projects": projects, "count": len(projects)})


def _get_project(store, name: str) -> tuple[dict, int]:
    """GET /api/v1/project/{name} — get a specific project."""
    if not name:
        return json_error("Project name is required")
    p = store.get_project(name)
    if not p:
        return json_error(f"Project not found: {name}", 404)
    return json_ok(p)


def _create_project(store, body: dict) -> tuple[dict, int]:
    """POST /api/v1/project — create a new project."""
    name = body.get("name", "")
    description = body.get("description", "")
    spec_path = body.get("spec_path", "")

    if not name:
        return json_error("'name' is required")

    store.init_project(name, description)

    if spec_path:
        conn = store.conn
        conn.execute("UPDATE projects SET spec_path=? WHERE name=?", (spec_path, name))
        conn.commit()

    p = store.get_project(name)
    return json_ok(p)


def _project_stats(store) -> tuple[dict, int]:
    """GET /api/v1/project/stats — aggregate project statistics."""
    # Count across all store tables
    conn = store.conn
    pipe_count = conn.execute("SELECT COUNT(*) as c FROM pipelines").fetchone()["c"]
    ci_count = conn.execute("SELECT COUNT(*) as c FROM ci_runs").fetchone()["c"]
    review_count = conn.execute("SELECT COUNT(*) as c FROM reviews").fetchone()["c"]
    ev_count = conn.execute("SELECT COUNT(*) as c FROM evidence").fetchone()["c"]
    proj_count = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]

    # Count pipeline statuses
    pipe_statuses = conn.execute(
        "SELECT status, COUNT(*) as c FROM pipelines GROUP BY status"
    ).fetchall()
    statuses = {r["status"]: r["c"] for r in pipe_statuses}

    return json_ok({
        "projects": proj_count,
        "pipelines": pipe_count,
        "pipeline_statuses": statuses,
        "ci_runs": ci_count,
        "reviews": review_count,
        "evidence_files": ev_count,
    })
