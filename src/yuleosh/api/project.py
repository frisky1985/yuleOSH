# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Project CRUD endpoints."""

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from . import json_ok, json_error
from .middleware import require_auth

logger = logging.getLogger(__name__)


@require_auth
def handle_project(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to project sub-resources."""
    from yuleosh.store import Store  # pylint: disable=import-error
    store = Store()
    user = kwargs.get("current_user")

    if path_tail == "stats" and method == "GET":
        return _project_stats(store)

    if method == "GET":
        # GET /api/v1/project — list all
        if path_tail == "" or path_tail == "list":
            return _list_projects(store)
        # GET /api/v1/project/{name} — get specific
        return _get_project(store, path_tail)

    if method == "POST":
        if path_tail == "seed-demo":
            return _seed_demo_project(store, body, user)
        # POST /api/v1/project — create (dual-write legacy + org table)
        return _create_project(store, body, user)

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


def _create_project(store, body: dict, user: dict | None = None) -> tuple[dict, int]:
    """POST /api/v1/project — create a new project.

    Dual-write so the project is visible where it needs to be:
      * legacy ``projects`` table (by name) — the spec/pipeline chain
        resolves projects by name;
      * org-scoped ``org_projects`` table (by org_id) — the Dashboard
        lists projects under the caller's organization, so the freshly
        created project actually shows up there.
    """
    name = (body.get("name") or "").strip()
    description = body.get("description", "")
    spec_path = body.get("spec_path", "")
    if not name:
        return json_error("'name' is required")

    slug = (body.get("slug") or "").strip() or re.sub(
        r"[^a-z0-9-]", "", name.lower().replace(" ", "-")
    )

    # 1) legacy table (spec/pipeline chain resolves projects by name)
    store.init_project(name, description)
    if spec_path:
        # A4: spec_path update via the Store interface (SHALL-A4.1).
        store.update_project_spec_path(name, spec_path)

    # 2) org-scoped table (Dashboard lists per-org projects)
    org_id = (user or {}).get("org_id")
    if org_id:
        try:
            if not store.get_org_project(org_id, slug):
                store.create_org_project(org_id, name, slug, description)
        except Exception as e:  # defensive: org write must not break create
            logger.warning("create_org_project(org=%s) failed: %s", org_id, e)

    # Return the org-scoped project so its id matches what the Dashboard
    # actually lists — the frontend selects the freshly created project by
    # this id, so a legacy-table id here would select the wrong row.
    proj = store.get_org_project(org_id, slug) or store.get_project(name) or {}
    return json_ok(proj)


# Sample spec written for the demo project so its pipeline can be run at once.
_DEMO_SPEC_YAML = """\
# yuleOSH demo spec — {name}
project: {name}
domain: automotive
module: uart_driver
requirements:
  - id: REQ-UART-001
    title: UART 波特率可配置
    coverage: 100%
  - id: REQ-UART-002
    title: 发送 FIFO 溢出保护
    coverage: 100%
  - id: REQ-UART-003
    title: 接收中断丢帧防护
    coverage: 100%
tests:
  unit: 1020
  coverage_target: 85
pipeline:
  stages:
    - spec_validation
    - plan_lint
    - clang_tidy
    - unit_tests
    - coverage
    - sil
    - cross_compile
    - hil
    - evidence
"""


def _write_demo_spec(name: str, slug: str) -> str | None:
    """Write a minimal sample spec YAML for the demo project; return its path."""
    try:
        root = os.environ.get("OSH_HOME") or os.getcwd()
        spec_dir = Path(root) / ".yuleosh" / "seed" / slug
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / "spec.yaml"
        if not spec_file.exists():
            spec_file.write_text(_DEMO_SPEC_YAML.format(name=name), encoding="utf-8")
        return str(spec_file)
    except Exception as e:  # noqa: BLE001
        logger.warning("seed spec write failed: %s", e)
        return None


def _seed_demo_project(store, body: dict, user: dict | None = None) -> tuple[dict, int]:
    """POST /api/v1/project/seed-demo — inject a ready-to-run demo project.

    Creates a demo org_project (so it shows up in the Dashboard project list)
    plus the legacy ``projects`` row, and seeds a sample spec file so the
    pipeline can be run immediately. Idempotent: re-running returns the
    existing project when the slug already exists for the org.
    """
    org_id = (user or {}).get("org_id")
    if not org_id:
        return json_error("seed-demo requires an authenticated org context", 400)

    name = (body.get("name") or "UART 驱动演示项目").strip()
    slug = (body.get("slug") or "uart-demo").strip() or re.sub(
        r"[^a-z0-9-]", "", name.lower().replace(" ", "-")
    )
    description = body.get("description") or (
        "yuleOSH pipeline demo 示例项目（UART 驱动），可立即运行合规流水线。"
    )

    # Idempotent on the project row: if the org project already exists,
    # still ensure the sample spec file is present (and its path recorded)
    # so the pipeline can run immediately.
    existing = store.get_org_project(org_id, slug)
    if existing:
        spec_path = _write_demo_spec(name, slug)
        if spec_path:
            try:
                store.update_project_spec_path(name, spec_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("seed update_project_spec_path(existing) failed: %s", e)
        return json_ok(existing)

    # 1) legacy table (spec/pipeline chain resolves projects by name)
    store.init_project(name, description)
    # 2) org-scoped table (Dashboard lists per-org projects)
    try:
        store.create_org_project(org_id, name, slug, description)
    except Exception as e:  # noqa: BLE001
        logger.warning("seed create_org_project(org=%s) failed: %s", org_id, e)

    # 3) sample spec file so the pipeline can be run immediately
    spec_path = _write_demo_spec(name, slug)
    if spec_path:
        try:
            store.update_project_spec_path(name, spec_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("seed update_project_spec_path failed: %s", e)

    proj = store.get_org_project(org_id, slug) or store.get_project(name) or {}
    return json_ok(proj)


def _project_stats(store) -> tuple[dict, int]:
    """GET /api/v1/project/stats — aggregate project statistics.

    A4 (v3.8.0): via Store.get_project_stats (SHALL-A4.1) — the v3.7.0
    bare-SQL counts moved into the Store implementation (SHALL-A4.4).
    """
    return json_ok(store.get_project_stats())
