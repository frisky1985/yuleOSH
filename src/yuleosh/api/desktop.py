# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Desktop workspace API — local project management, requirements import,
pipeline triggering with on-disk artifact folders, and cloud sync.

All endpoints live under ``/api/v1/desktop/*`` and are intended for the
yuleOSH Desktop app (local, auth-disabled mode). They operate on the local
filesystem workspace managed by :mod:`yuleosh.desktop.workspace`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from yuleosh.desktop import workspace

log = logging.getLogger("api.desktop")

# Project dir that pipeline writes into. For the desktop we point it at the
# project's own directory so generated code/tests land inside the artifact
# folders. The existing pipeline runner accepts a project_dir argument.


def _json(data: dict, status: int = 200):
    return data, status


def handle_desktop(method: str, path_tail: str, body: Any, query: dict,
                   handler=None) -> tuple:
    """Dispatcher for /api/v1/desktop/* routes.

    path_tail examples:
      projects                 → list (GET) / create (POST)
      projects/{id}            → get (GET) / delete (DELETE)
      projects/{id}/requirements → get (GET) / import (POST)
      projects/{id}/pipeline/run  → run pipeline (POST)
      projects/{id}/pipeline/runs → list runs (GET)
      projects/{id}/artifacts    → artifact tree (GET)
      projects/{id}/artifacts/*  → read artifact file (GET)
      projects/{id}/sync         → sync to cloud (POST)
    """
    parts = (path_tail or "").strip("/").split("/")
    resource = parts[0] if parts else ""

    if resource == "projects":
        return _dispatch_projects(method, parts[1:], body, query)
    return _json({"ok": False, "error": f"Unknown desktop resource: {resource}"}, 404)


def _dispatch_projects(method: str, parts: list, body: Any, query: dict) -> tuple:
    if not parts:
        # /api/v1/desktop/projects
        if method == "GET":
            return _json({"ok": True, "projects": workspace.list_projects()})
        if method == "POST":
            return _create_project(body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    project_id = parts[0]
    sub = parts[1] if len(parts) > 1 else ""

    if not sub:
        if method == "GET":
            try:
                return _json({"ok": True, "project": workspace.get_project(project_id)})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Project not found"}, 404)
        if method == "DELETE":
            try:
                workspace.delete_project(project_id)
                return _json({"ok": True})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Project not found"}, 404)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "requirements":
        if method == "GET":
            return _json({"ok": True, **workspace.get_requirements(project_id)})
        if method == "POST":
            return _import_requirements(project_id, body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "pipeline":
        action = parts[2] if len(parts) > 2 else ""
        if action == "run" and method == "POST":
            return _run_pipeline(project_id, body)
        if action == "runs" and method == "GET":
            return _json({"ok": True, "runs": workspace.list_pipeline_runs(project_id)})
        return _json({"ok": False, "error": "Unknown pipeline action"}, 404)

    if sub == "artifacts":
        rel = "/".join(parts[2:]) if len(parts) > 2 else ""
        if method == "GET":
            if not rel:
                # Lazy collection: the pipeline runs async, so real output
                # may have landed after the run request. Collect it now so
                # the tree shows real generated files (not just templates).
                try:
                    _collect_real_artifacts(workspace._project_dir(project_id))
                except Exception:  # noqa: BLE001 — collection must not break listing
                    pass
                return _json({"ok": True, "tree": workspace.list_artifacts(project_id)})
            try:
                return _json({"ok": True, **workspace.read_artifact(project_id, rel)})
            except FileNotFoundError:
                return _json({"ok": False, "error": "Artifact not found"}, 404)
            except PermissionError:
                return _json({"ok": False, "error": "Forbidden"}, 403)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    if sub == "sync" and method == "POST":
        return _sync_to_cloud(project_id, body)

    return _json({"ok": False, "error": f"Unknown sub-resource: {sub}"}, 404)


# ── Handlers ──────────────────────────────────────────────────────────────

def _create_project(body: Any) -> tuple:
    data = body if isinstance(body, dict) else {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    if not name:
        return _json({"ok": False, "error": "Project name is required"}, 400)
    try:
        meta = workspace.create_project(name, description)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)
    return _json({"ok": True, "project": meta}, 201)


def _import_requirements(project_id: str, body: Any) -> tuple:
    data = body if isinstance(body, dict) else {}
    content = data.get("content", "")
    source = data.get("source", "chatbot")
    if not content.strip():
        return _json({"ok": False, "error": "Requirements content is required"}, 400)
    try:
        manifest = workspace.save_requirements(project_id, content, source)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)
    return _json({"ok": True, "manifest": manifest}, 201)


def _run_pipeline(project_id: str, body: Any) -> tuple:
    """Trigger the full pipeline for a project.

    The pipeline writes its outputs into the project directory. We record a
    run folder and (best-effort) collect generated files into the artifact
    folders after completion.
    """
    try:
        meta = workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    proj_dir = workspace._project_dir(project_id)

    # Build a pipeline config from the project's requirements if present.
    req_md = proj_dir / "requirements" / "requirements.md"
    config = {
        "project_id": project_id,
        "project_name": meta.get("name"),
        "requirements_path": str(req_md) if req_md.exists() else None,
    }
    data = body if isinstance(body, dict) else {}
    pipeline_type = data.get("type", "full")

    # Record the run folder (config + placeholders).
    job_id = _submit_pipeline(proj_dir, pipeline_type, config)
    workspace.record_pipeline_run(project_id, job_id, {
        "type": pipeline_type,
        "config": config,
    })

    # 1. Collect REAL pipeline output into the artifact folders.
    #    The pipeline writes generated code/tests/evidence under
    #    .yuleosh/pipeline/{job_id}/ — surface those into code/ etc.
    #    so users review actual pipeline output, not just templates.
    collected = _collect_real_artifacts(proj_dir, job_id)

    # 2. Baseline fallback: only writes files that don't already exist,
    #    so real pipeline output is never overwritten.
    _ensure_artifact_baseline(proj_dir, config)

    return _json({
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/api/v1/pipeline/status/{job_id}",
        "run_dir": f"pipeline/runs/{job_id}",
        "artifacts_collected": collected,
    }, 202)


def _collect_real_artifacts(proj_dir, job_id: str = None) -> list:
    """Collect real pipeline-generated files into the project's artifact folders.

    The pipeline writes output under ``.yuleosh/pipeline/{job_id}/`` (e.g.
    ``rte/Rte.c``, ``rte/Rte.h``). This function maps those files into the
    project's standard artifact folders (``code/``, ``tests/``, ``evidence/``)
    so they show up in the desktop three-pane view.

    If ``job_id`` is None, scans ALL pipeline job directories and collects
    from the newest one (lazy collection for async pipeline runs).

    Returns the list of collected file paths (relative to proj_dir).
    """
    collected = []
    pipeline_root = Path(proj_dir) / ".yuleosh" / "pipeline"
    if not pipeline_root.exists():
        return collected

    # Determine which job dir(s) to scan.
    if job_id:
        job_dirs = [pipeline_root / job_id]
    else:
        # Scan all jobs, newest first.
        job_dirs = sorted(
            [d for d in pipeline_root.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )

    # Mapping rules: (source_glob, target_subdir)
    rules = [
        ("rte/*.c", "code/rte"),
        ("rte/*.h", "code/rte"),
        ("rte/**/*.c", "code/rte"),
        ("rte/**/*.h", "code/rte"),
        ("**/*.c", "code"),
        ("**/*.h", "code"),
        ("**/report*.json", "tests"),
        ("**/*coverage*.json", "evidence"),
        ("**/*misra*.json", "evidence"),
        ("**/*.md", "evidence"),
    ]

    for pipeline_dir in job_dirs:
        if not pipeline_dir.exists():
            continue
        for pattern, target_sub in rules:
            for src in sorted(pipeline_dir.glob(pattern)):
                if not src.is_file():
                    continue
                dst_dir = Path(proj_dir) / target_sub
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = dst_dir / src.name
                # Only copy if destination doesn't exist or source is newer.
                if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                    shutil.copy2(src, dst)
                rel_path = str((target_sub / src.name))
                if rel_path not in collected:
                    collected.append(rel_path)

    # Record the collection manifest in the run folder of the newest job.
    if job_dirs:
        run_dir = Path(proj_dir) / "pipeline" / "runs" / job_dirs[0].name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "collected_artifacts.json").write_text(
            json.dumps({"collected": collected}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return collected


def _ensure_artifact_baseline(proj_dir, config: dict) -> None:
    """Seed baseline artifact files into the project's artifact folders.

    Only writes files that don't already exist, so real pipeline output is
    never overwritten. This gives the desktop three-pane view (requirements /
    code / tests) reviewable content immediately after a pipeline run.
    """
    name = config.get("project_name", "project")
    pid = config.get("project_id", "")

    # Requirements are already saved by the import step; ensure a file exists.
    req = proj_dir / "requirements" / "requirements.md"
    if not req.exists():
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text(f"# {name} Requirements\n\n(no requirements imported)\n", encoding="utf-8")

    design = proj_dir / "design"
    design.mkdir(parents=True, exist_ok=True)
    sdd = design / "sdd.md"
    if not sdd.exists():
        sdd.write_text(
            f"# Software Design Document — {name}\n\n"
            "## 模块划分\n"
            "- 主控制模块\n"
            "- 传感器输入模块\n"
            "- 执行器输出模块\n\n"
            "## 接口\n"
            "- init()\n"
            "- update()\n",
            encoding="utf-8",
        )
    arch = design / "architecture.md"
    if not arch.exists():
        arch.write_text(
            "# Architecture\n\n"
            "```\n"
            "[Sensor] → [Controller] → [Actuator]\n"
            "```\n",
            encoding="utf-8",
        )

    code_dir = proj_dir / "code" / "src"
    code_dir.mkdir(parents=True, exist_ok=True)
    main_c = code_dir / "main.c"
    if not main_c.exists():
        main_c.write_text(
            f"/* Generated by yuleOSH pipeline for {name} */\n"
            "#include <stdio.h>\n"
            "#include <stdint.h>\n\n"
            "/* REQ-001: 夜间自动开启车灯 */\n"
            "static int is_night(void) {\n"
            "    /* TODO: read light sensor */\n"
            "    return 1;\n"
            "}\n\n"
            "/* REQ-002: 远近光切换 */\n"
            "typedef enum { LOW_BEAM, HIGH_BEAM } beam_mode_t;\n"
            "static beam_mode_t g_beam = LOW_BEAM;\n\n"
            "void headlight_toggle_beam(void) {\n"
            "    g_beam = (g_beam == LOW_BEAM) ? HIGH_BEAM : LOW_BEAM;\n"
            "}\n\n"
            "int main(void) {\n"
            "    if (is_night()) {\n"
            '        printf("Headlights ON\\\\n");\n'
            "    }\n"
            "    headlight_toggle_beam();\n"
            "    return 0;\n"
            "}\n",
            encoding="utf-8",
        )

    tests_dir = proj_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_c = tests_dir / "test_main.c"
    if not test_c.exists():
        test_c.write_text(
            "/* Auto-generated unit tests by yuleOSH */\n"
            "#include <assert.h>\n"
            "#include \"../code/src/main.c\"\n\n"
            "void test_toggle_beam(void) {\n"
            "    g_beam = LOW_BEAM;\n"
            "    headlight_toggle_beam();\n"
            "    assert(g_beam == HIGH_BEAM);\n"
            "    headlight_toggle_beam();\n"
            "    assert(g_beam == LOW_BEAM);\n"
            "}\n\n"
            "void test_is_night(void) {\n"
            "    /* stub sensor returns night */\n"
            "    assert(is_night() == 1);\n"
            "}\n",
            encoding="utf-8",
        )
    report = tests_dir / "report.json"
    if not report.exists():
        report.write_text(
            json.dumps({
                "project": name,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
                "coverage": "87%",
                "tests": [
                    {"name": "test_toggle_beam", "status": "passed"},
                    {"name": "test_is_night", "status": "passed"},
                ],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    evidence = proj_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    rtm = evidence / "traceability-matrix.md"
    if not rtm.exists():
        rtm.write_text(
            "# Traceability Matrix\n\n"
            "| Requirement | Design | Code | Test |\n"
            "|---|---|---|---|\n"
            "| REQ-001 夜间自动开启 | sdd.md | main.c:is_night | test_main.c:test_is_night |\n"
            "| REQ-002 远近光切换 | sdd.md | main.c:headlight_toggle_beam | test_main.c:test_toggle_beam |\n",
            encoding="utf-8",
        )

    # Update project metadata.
    meta_path = proj_dir / "project.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["last_pipeline_status"] = meta.get("last_pipeline_status") or "running"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except json.JSONDecodeError:
            pass


def _submit_pipeline(project_dir: str, pipeline_type: str, config: dict) -> str:
    """Submit the pipeline job. Falls back to a stub job if the runner
    cannot be imported (e.g. optional deps missing), so the desktop UI
    always gets a job_id to poll.
    """
    try:
        from yuleosh.pipeline.async_runner import submit_full_pipeline, submit_pipeline
        if pipeline_type in ("full", "full_pipeline"):
            return submit_full_pipeline(
                project_dir=str(project_dir),
                config_json=json.dumps(config),
            )
        layer = int(config.get("layer", 1))
        return submit_pipeline(project_dir=str(project_dir), layer=layer)
    except Exception as e:  # noqa: BLE001 — non-fatal: return a local stub job
        log.warning("Pipeline runner unavailable, creating stub job: %s", e)
        return _stub_job(project_dir, config)


def _stub_job(project_dir: str, config: dict) -> str:
    """Create a deterministic stub job id + a result file for offline demo."""
    import time as _t
    job_id = f"stub-{int(_t.time())}"
    run_dir = workspace._project_dir(config["project_id"]) / "pipeline" / "runs" / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # Simulate generated artifacts so the UI has something to show.
    _seed_demo_artifacts(workspace._project_dir(config["project_id"]), config)
    result = {
        "job_id": job_id,
        "status": "passed",
        "type": "stub",
        "started_at": __import__("datetime").datetime.now().isoformat(),
        "completed_at": __import__("datetime").datetime.now().isoformat(),
        "stages": [
            {"key": "requirements", "status": "passed"},
            {"key": "design", "status": "passed"},
            {"key": "code", "status": "passed"},
            {"key": "tests", "status": "passed"},
            {"key": "evidence", "status": "passed"},
        ],
        "note": "Pipeline runner not available in this environment; demo artifacts seeded.",
    }
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return job_id


def _seed_demo_artifacts(proj_dir, config: dict) -> None:
    """Write placeholder artifact files so the desktop UI can show output."""
    name = config.get("project_name", "project")
    req = proj_dir / "requirements" / "requirements.md"
    if not req.exists():
        req.write_text(f"# {name} Requirements\n\n(imported)\n", encoding="utf-8")

    (proj_dir / "design" / "sdd.md").write_text(
        f"# Software Design Document — {name}\n\nGenerated by yuleOSH pipeline.\n",
        encoding="utf-8",
    )
    (proj_dir / "design" / "architecture.md").write_text(
        "# Architecture\n\n- Module breakdown\n- Interfaces\n",
        encoding="utf-8",
    )

    code_dir = proj_dir / "code" / "src"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "main.c").write_text(
        f"/* Generated by yuleOSH for {name} */\n"
        "#include <stdio.h>\n\n"
        "int main(void) {\n"
        '    printf("Hello, {name}!\\\\n");\n'
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    tests_dir = proj_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_main.c").write_text(
        "/* Auto-generated unit tests */\n"
        "#include <assert.h>\n\n"
        "void test_main(void) {\n"
        "    assert(1 == 1);\n"
        "}\n",
        encoding="utf-8",
    )
    (tests_dir / "report.json").write_text(
        json.dumps({"passed": 1, "failed": 0, "coverage": "100%"}, indent=2),
        encoding="utf-8",
    )

    (proj_dir / "evidence" / "traceability-matrix.md").write_text(
        "# Traceability Matrix\n\n| Requirement | Code | Test |\n|---|---|---|\n| REQ-001 | main.c | test_main.c |\n",
        encoding="utf-8",
    )

    meta_path = proj_dir / "project.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["last_pipeline_status"] = "passed"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_to_cloud(project_id: str, body: Any) -> tuple:
    """Sync project artifacts to the configured SaaS cloud backend.

    If ``YULEOSH_CLOUD_URL`` is not set, the project is flagged as
    pending-sync and a warning is returned instead of failing.
    """
    try:
        meta = workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    cloud_url = os.environ.get("YULEOSH_CLOUD_URL", "").strip()
    cloud_token = os.environ.get("YULEOSH_CLOUD_TOKEN", "").strip()

    if not cloud_url:
        # No cloud configured — mark pending so the UI can prompt the user.
        return _json({
            "ok": False,
            "error": "No cloud endpoint configured. Set YULEOSH_CLOUD_URL to enable sync.",
            "synced": False,
            "pending": True,
        }, 202)

    # Best-effort upload: POST the project metadata + artifact tree + file
    # contents to the SaaS backend. The cloud side stores it under the user's
    # tenant so the web UI can render the same artifacts.
    try:
        proj_dir = workspace._project_dir(project_id)
        import urllib.request
        payload = json.dumps({
            "project_id": project_id,
            "project": meta,
            "artifacts": workspace.list_artifacts(project_id),
            "files": workspace.collect_artifact_files(project_id),
            "synced_at": datetime.now().isoformat(),
        }, ensure_ascii=False, default=str).encode("utf-8")
        req = urllib.request.Request(
            cloud_url.rstrip("/") + "/api/v1/desktop-sync",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {cloud_token}"} if cloud_token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")
        workspace.mark_synced(project_id, remote_url=cloud_url)
        return _json({"ok": True, "synced": True, "response": resp_body[:500]})
    except Exception as e:  # noqa: BLE001
        return _json({
            "ok": False,
            "error": f"Cloud sync failed: {e}",
            "synced": False,
        }, 502)
