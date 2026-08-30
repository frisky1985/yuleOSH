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
# Catalog of ready-to-run demo projects injected by `seed-demo`. Each entry is
# a self-contained spec (requirements + pipeline stages) so the demo can run a
# compliance pipeline immediately after being loaded.
_PIPELINE_STAGES = [
    "spec_validation", "plan_lint", "clang_tidy", "unit_tests",
    "coverage", "sil", "cross_compile", "hil", "evidence",
]

DEMO_CATALOG = {
    "uart-demo": {
        "name": "UART 驱动演示项目",
        "description": "yuleOSH pipeline demo 示例项目（UART 驱动），可立即运行合规流水线。",
        "domain": "automotive", "module": "uart_driver",
        "requirements": [
            ("REQ-UART-001", "UART 波特率可配置", "100%"),
            ("REQ-UART-002", "发送 FIFO 溢出保护", "100%"),
            ("REQ-UART-003", "接收中断丢帧防护", "100%"),
        ],
    },
    "gpio-demo": {
        "name": "GPIO 流水灯演示",
        "description": "yuleOSH pipeline demo 示例项目（GPIO 流水灯），可立即运行合规流水线。",
        "domain": "automotive", "module": "gpio_led",
        "requirements": [
            ("REQ-GPIO-001", "LED 引脚输出可控", "100%"),
            ("REQ-GPIO-002", "流水灯时序正确", "100%"),
            ("REQ-GPIO-003", "低功耗休眠模式", "100%"),
        ],
    },
    "can-demo": {
        "name": "CAN 通信演示",
        "description": "yuleOSH pipeline demo 示例项目（CAN 总线通信），可立即运行合规流水线。",
        "domain": "automotive", "module": "can_bus",
        "requirements": [
            ("REQ-CAN-001", "报文收发可靠", "100%"),
            ("REQ-CAN-002", "总线错误恢复", "100%"),
            ("REQ-CAN-003", "波特率自适应", "100%"),
        ],
    },
}


def _build_demo_spec_yaml(demo: dict) -> str:
    """Render a demo project's spec YAML from its catalog entry."""
    reqs = "\n".join(
        f"  - id: {rid}\n    title: {title}\n    coverage: {cov}"
        for rid, title, cov in demo["requirements"]
    )
    stages = "\n".join(f"    - {s}" for s in _PIPELINE_STAGES)
    return f"""\
# yuleOSH demo spec — {demo['name']}
project: {demo['name']}
domain: {demo['domain']}
module: {demo['module']}
requirements:
{reqs}
tests:
  unit: 1020
  coverage_target: 85
pipeline:
  stages:
{stages}
"""


def _write_demo_spec(name: str, slug: str) -> str | None:
    """Write a minimal sample spec YAML for the demo project; return its path."""
    try:
        root = os.environ.get("OSH_HOME") or os.getcwd()
        spec_dir = Path(root) / ".yuleosh" / "seed" / slug
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / "spec.yaml"
        if not spec_file.exists():
            demo = DEMO_CATALOG.get(slug, DEMO_CATALOG["uart-demo"])
            spec_file.write_text(_build_demo_spec_yaml(demo), encoding="utf-8")
        return str(spec_file)
    except Exception as e:  # noqa: BLE001
        logger.warning("seed spec write failed: %s", e)
        return None


# One-time data upgrade: the two E2E test shells created earlier (Demo Pipe X/Y)
# are promoted in place into proper runnable demo projects (GPIO / CAN) so they
# join the seed catalog instead of lingering as empty shells in the Dashboard.
_LEGACY_TEST_MIGRATIONS = [
    ("demo-pipe-x", "gpio-demo", "GPIO 流水灯演示",
     "yuleOSH pipeline demo 示例项目（GPIO 流水灯），可立即运行合规流水线。"),
    ("demo-pipe-y", "can-demo", "CAN 通信演示",
     "yuleOSH pipeline demo 示例项目（CAN 总线通信），可立即运行合规流水线。"),
]


def _migrate_existing_test_projects(store, org_id: int) -> None:
    """Promote the earlier E2E test shells (slug demo-pipe-x / demo-pipe-y)
    into real demo projects (gpio-demo / can-demo) in place. Idempotent: once
    renamed, the old slugs no longer exist and this becomes a no-op.
    """
    for old_slug, new_slug, new_name, new_desc in _LEGACY_TEST_MIGRATIONS:
        old = store.get_org_project(org_id, old_slug)
        if not old:
            continue
        store.update_org_project(org_id, old_slug, name=new_name,
                                 new_slug=new_slug, description=new_desc)
        store.rename_project(old["name"], new_name, new_desc)
        spec_path = _write_demo_spec(new_name, new_slug)
        if spec_path:
            try:
                store.update_project_spec_path(new_name, spec_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("migrate update_project_spec_path failed: %s", e)


def _seed_demo_project(store, body: dict, user: dict | None = None) -> tuple[dict, int]:
    """POST /api/v1/project/seed-demo — inject the ready-to-run demo catalog.

    Seeds every project in DEMO_CATALOG (UART / GPIO / CAN demos) so they all
    appear in the Dashboard and can run a compliance pipeline immediately.
    Idempotent: re-running just ensures each demo's spec file is present.
    """
    org_id = (user or {}).get("org_id")
    if not org_id:
        return json_error("seed-demo requires an authenticated org context", 400)

    # 1) one-time upgrade of the earlier E2E test shells into real demos
    _migrate_existing_test_projects(store, org_id)

    primary_slug = (body.get("slug") or "uart-demo").strip() or "uart-demo"
    seeded, primary = [], None
    for slug, demo in DEMO_CATALOG.items():
        name = demo["name"]
        description = demo["description"]

        # Idempotent: only create the org row if it isn't there yet; always
        # (re)ensure the sample spec file so the pipeline can run immediately.
        if not store.get_org_project(org_id, slug):
            store.init_project(name, description)
            try:
                store.create_org_project(org_id, name, slug, description)
            except Exception as e:  # noqa: BLE001
                logger.warning("seed create_org_project(org=%s) failed: %s", org_id, e)

        spec_path = _write_demo_spec(name, slug)
        if spec_path:
            try:
                store.update_project_spec_path(name, spec_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("seed update_project_spec_path failed: %s", e)

        proj = store.get_org_project(org_id, slug) or store.get_project(name) or {}
        seeded.append(proj)
        if slug == primary_slug:
            primary = proj

    return json_ok(primary or (seeded[0] if seeded else {}))


def _project_stats(store) -> tuple[dict, int]:
    """GET /api/v1/project/stats — aggregate project statistics.

    A4 (v3.8.0): via Store.get_project_stats (SHALL-A4.1) — the v3.7.0
    bare-SQL counts moved into the Store implementation (SHALL-A4.4).
    """
    return json_ok(store.get_project_stats())
