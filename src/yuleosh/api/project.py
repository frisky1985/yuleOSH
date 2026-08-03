# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Project CRUD endpoints."""

from datetime import datetime

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
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
    """GET /api/v1/project — list all projects.

    A4 (v3.8.0): goes through the Store interface (SHALL-A4.1) — no bare
    raw SQL calls in api/project.py anymore.
    """
    projects = store.list_projects()
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
        # A4: spec_path update via the Store interface (SHALL-A4.1).
        store.update_project_spec_path(name, spec_path)

    p = store.get_project(name)
    return json_ok(p)


def _project_stats(store) -> tuple[dict, int]:
    """GET /api/v1/project/stats — aggregate project statistics.

    A4 (v3.8.0): via Store.get_project_stats (SHALL-A4.1) — the v3.7.0
    bare-SQL counts moved into the Store implementation (SHALL-A4.4).
    """
    return json_ok(store.get_project_stats())
