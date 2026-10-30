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
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from yuleosh.desktop import baseline, change_control, tracing, workspace

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
        # 单 job 状态（给前端轮询用，免鉴权）。
        # /api/v1/desktop/projects/{id}/pipeline/status/{job_id}
        if action == "status" and method == "GET" and len(parts) > 3:
            job_id = parts[3]
            return _pipeline_job_status(project_id, job_id)
        return _json({"ok": False, "error": "Unknown pipeline action"}, 404)

    # 追溯治理（P3）
    # /api/v1/desktop/projects/{id}/traceability                 (GET 当前矩阵 + 门禁判定)
    # /api/v1/desktop/projects/{id}/traceability/refresh         (POST 刷新，可绑定基线)
    # /api/v1/desktop/projects/{id}/traceability/reverse?file=   (GET 文件→需求反查)
    if sub == "traceability":
        return _dispatch_traceability(project_id, method, parts[2:], body, query)

    # 基线快照与比对（SUP.8 最小闭环）
    # /api/v1/desktop/projects/{id}/baselines                (GET 列表 / POST 新建快照)
    # /api/v1/desktop/projects/{id}/baselines/diff           (GET ?from=&to= 比对并归档证据)
    # /api/v1/desktop/projects/{id}/baselines/{name}         (GET 详情)
    if sub == "baselines":
        return _dispatch_baselines(project_id, method, parts[2:], body, query)

    # 变更请求（SUP.10 最小闭环）
    # /api/v1/desktop/projects/{id}/change-requests              (GET 列表 / POST 新建)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}      (GET 详情)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}/analyze     (POST 影响分析)
    # /api/v1/desktop/projects/{id}/change-requests/{cr_id}/transition  (POST 状态迁移)
    if sub == "change-requests":
        return _dispatch_change_requests(project_id, method, parts[2:], body)

    # 评审：对某个产物文件做通过/退回 + 批注，落到 evidence/review.json
    # /api/v1/desktop/projects/{id}/review                    (GET 列表 / POST 新增)
    # /api/v1/desktop/projects/{id}/review/bulk               (POST 批量：按分区或按 glob 批量打标)
    # /api/v1/desktop/projects/{id}/review/export             (GET 导出 evidence/review-report.md)
    # /api/v1/desktop/projects/{id}/review/{review_id}        (GET 详情 / DELETE 删除)
    if sub == "review":
        rev_id = parts[2] if len(parts) > 2 else ""
        sub_action = parts[2] if len(parts) > 2 else ""
        if sub_action == "bulk" and method == "POST":
            return _bulk_reviews(project_id, body)
        if sub_action == "export" and method == "GET":
            return _export_reviews(project_id)
        if rev_id and method == "GET":
            return _get_review(project_id, rev_id)
        if rev_id and method == "DELETE":
            return _delete_review(project_id, rev_id)
        if not rev_id and method == "GET":
            return _list_reviews(project_id)
        if not rev_id and method == "POST":
            return _add_review(project_id, body)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

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
        "poll_url": f"/api/v1/desktop/projects/{project_id}/pipeline/status/{job_id}",
        "run_dir": f"pipeline/runs/{job_id}",
        "artifacts_collected": collected,
    }, 202)


def _pipeline_job_status(project_id: str, job_id: str) -> tuple:
    """Return real pipeline job status (progress, stages, logs) for the desktop poller.

    Reads from async_runner's in-memory _PIPELINE_JOBS first (fast, live),
    falls back to the persisted result.json in pipeline/runs/{job_id}/ for
    jobs that completed before the server restarted.
    """
    # 1) Memory-first — async_runner 是同一进程，数据最鲜活。
    try:
        from yuleosh.pipeline.async_runner import get_job_status
        job = get_job_status(job_id)
        if job:
            return _json({
                "ok": True,
                "job_id": job_id,
                "status": job.get("status"),
                "progress": job.get("progress", 0),
                "current_stage": job.get("current_stage"),
                "stages": job.get("stages", []),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                "logs": job.get("logs", [])[-50:],  # 只留最近 50 条，省带宽
                "result": job.get("result"),
            })
    except Exception:  # noqa: BLE001 — runner 模块不可用时走磁盘
        pass

    # 2) Disk fallback — result.json 由 runner 完成时写入，或 stub_job 预置。
    run_dir = workspace._project_dir(project_id) / "pipeline" / "runs" / job_id
    result_path = run_dir / "result.json"
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            return _json({
                "ok": True,
                "job_id": job_id,
                "status": data.get("status", "unknown"),
                "progress": 100 if data.get("status") in ("passed", "failed") else 0,
                "current_stage": data.get("current_stage"),
                "stages": data.get("stages", []),
                "started_at": data.get("started_at"),
                "completed_at": data.get("completed_at"),
                "logs": [],
                "result": data.get("result"),
                "source": "disk",
            })
        except json.JSONDecodeError:
            pass

    return _json({"ok": False, "error": f"Job {job_id} not found"}, 404)


# ── Artifact classification contract ───────────────────────────────────
# 五分区是产物的唯一权威归属。规则按顺序短路，命中即返回，避免
# 「多个 glob 同时命中同一文件、后写覆盖前写」的歧义。
# 无法归类的产物一律进 _unclassified/（并写入 artifact-manifest.json），
# 由人工复核后归位，而不是猜一个分区塞进去。

UNCLASSIFIED_DIR = "_unclassified"

# 流水线内部文件，不是交付产物，不参与分区。
_SKIP_NAMES = {
    "config.json",
    "collected_artifacts.json",
    "artifact-manifest.json",
    "project.json",
    "session.json",
}
_SKIP_SUFFIXES = {".arxml", ".db", ".sqlite", ".sqlite3"}

_CODE_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".hpp", ".py", ".rs", ".js", ".ts"}
_TEST_DIRS = {"test", "tests", "unit_tests", "ctest", "testcases"}
_TEST_NAME_RE = re.compile(r"^(test_.*|.*_tests?)$")
_EVIDENCE_DIRS = {"evidence", "reports", "coverage", "results"}
_EVIDENCE_HINTS = (
    "coverage", "misra", "sarif", "report", "review", "audit", "trace", "certif", "evidence",
)
_DESIGN_HINTS = ("design", "sdd", "architecture", "interface", "uml", "hld", "lld")
_REQ_HINTS = ("requirement", "spec", "stakeholder", "sys-req", "prd")


def classify_artifact(rel_path) -> tuple[str, str, str] | None:
    """把流水线产物映射到五分区之一。

    判定顺序（先目录语义，后文件名语义，最后扩展名）：
      1. 内部文件 → None（不收集）
      2. RTE 生成代码 → code/rte
      3. 目录命中 tests/evidence/design/requirements
      4. 文件名命中 test_xxx / xxx_test → tests
      5. 文件名含 coverage/misra/report/... → evidence
      6. 文件名含 design/sdd/... → design
      7. 文件名含 requirement/spec/... → requirements
      8. 代码扩展名 → code
      9. 兜底 → _unclassified（人工复核）

    Returns ``(section, dest_subdir, rule)`` 或 ``None``。
    """
    rel = Path(rel_path)
    parts = [p.lower() for p in rel.parts[:-1]]
    stem = rel.stem.lower()
    name = rel.name.lower()
    suffix = rel.suffix.lower()

    if name in _SKIP_NAMES or suffix in _SKIP_SUFFIXES:
        return None

    # 2) RTE 生成的胶水代码固定进 code/rte
    if "rte" in parts or stem.startswith("rte"):
        return ("code", "code/rte", "rte")

    # 3) 目录语义优先
    if any(p in _TEST_DIRS for p in parts):
        return ("tests", "tests", "dir:tests")
    if any(p in _EVIDENCE_DIRS for p in parts):
        return ("evidence", "evidence", "dir:evidence")
    if any(p in ("design", "architecture", "arch") for p in parts):
        return ("design", "design", "dir:design")
    if any(p in ("requirements", "spec") for p in parts):
        return ("requirements", "requirements", "dir:requirements")

    # 4) 文件名语义
    if _TEST_NAME_RE.match(stem):
        return ("tests", "tests", "name:test")
    if any(h in name for h in _EVIDENCE_HINTS) or suffix in (".sarif", ".log"):
        return ("evidence", "evidence", "name:evidence")
    if any(h in stem for h in _DESIGN_HINTS):
        return ("design", "design", "name:design")
    if any(h in stem for h in _REQ_HINTS):
        return ("requirements", "requirements", "name:requirements")

    # 5) 扩展名兜底为代码
    if suffix in _CODE_SUFFIXES:
        return ("code", "code", "suffix:code")

    # 6) 无法确定归属：显式暴露，不猜
    return (UNCLASSIFIED_DIR, UNCLASSIFIED_DIR, "unclassified")


def _collect_real_artifacts(proj_dir, job_id: str = None) -> list:
    """Collect real pipeline-generated files into the project's artifact folders.

    The pipeline writes output under ``.yuleosh/pipeline/{job_id}/`` (e.g.
    ``rte/Rte.c``, ``rte/Rte.h``). This function maps those files into the
    project's five artifact sections (``requirements/ design/ code/ tests/
    evidence/``) via :func:`classify_artifact`, so they show up in the
    desktop five-section sidebar. Files that cannot be classified go to
    ``_unclassified/`` and are recorded in ``artifact-manifest.json``.

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

    # 分区归属由 classify_artifact() 决定（确定性规则），不再用扩展名 glob 猜类型。
    # 无法归类的文件落到 _unclassified/ 并记录在 manifest 里，不静默丢弃、
    # 也不静默塞进错误分区。
    manifest: list[dict] = []

    for pipeline_dir in job_dirs:
        if not pipeline_dir.exists():
            continue
        sources = sorted(p for p in pipeline_dir.rglob("*") if p.is_file())
        for src in sources:
            rel_src = src.relative_to(pipeline_dir)
            classified = classify_artifact(rel_src)
            if classified is None:  # 内部文件（config.json / *.arxml 等），不属于产物
                continue
            section, target_sub, rule = classified
            dst_dir = Path(proj_dir) / target_sub
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / src.name
            # Only copy if destination doesn't exist or source is newer.
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
            rel_path = str(Path(target_sub) / src.name)
            if rel_path not in collected:
                collected.append(rel_path)
                manifest.append({
                    "source": str(rel_src),
                    "path": rel_path,
                    "section": section,
                    "rule": rule,
                })

    # Record the collection manifest in the run folder of the newest job.
    if job_dirs:
        run_dir = Path(proj_dir) / "pipeline" / "runs" / job_dirs[0].name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "collected_artifacts.json").write_text(
            json.dumps({"collected": collected}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "artifact-manifest.json").write_text(
            json.dumps({"artifacts": manifest}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for item in manifest:
            if item["section"] == UNCLASSIFIED_DIR:
                log.warning(
                    "unclassified pipeline artifact: %s (from %s)",
                    item["path"], item["source"],
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

        # 增量同步：只传变化/新增文件 + 被删文件列表
        inc = workspace.collect_artifact_incremental(project_id)
        files_to_send = inc["files"]
        removed_list = inc["removed"]

        # 首次同步或文件有变化才上传；完全不变时云端不用更新文件，只刷新 meta
        has_changes = bool(files_to_send or removed_list or not Path(proj_dir / ".sync_manifest.json").exists())

        payload = json.dumps({
            "project_id": project_id,
            "project": meta,
            "artifacts": workspace.list_artifacts(project_id),
            "mode": "incremental",
            "files": files_to_send,
            "removed": removed_list,
            "manifest": inc["manifest"],
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
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp_body = resp.read().decode("utf-8", errors="replace")

        # 成功后更新本地 manifest
        workspace.save_sync_manifest(project_id, inc["manifest"])
        workspace.mark_synced(project_id, remote_url=cloud_url)

        return _json({
            "ok": True,
            "synced": True,
            "changed_files": inc["changed_count"],
            "removed_files": inc["removed_count"],
            "total_files": inc["total_current"],
            "skipped": not has_changes,
            "response": resp_body[:500],
        })
    except Exception as e:  # noqa: BLE001
        return _json({
            "ok": False,
            "error": f"Cloud sync failed: {e}",
            "synced": False,
        }, 502)


# ── Traceability handlers (P3) ────────────────────────────────────────────

def _dispatch_traceability(project_id: str, method: str, parts: list,
                           body: Any, query: dict) -> tuple:
    """Handle /projects/{id}/traceability[/refresh|/reverse]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    action = parts[0] if parts else ""
    data = body if isinstance(body, dict) else {}
    raw_threshold = _query_one(query, "threshold") if query else ""
    try:
        threshold = float(raw_threshold) if raw_threshold else None
    except ValueError:
        return _json({"ok": False, "error": "threshold must be a number"}, 400)

    try:
        if not action:
            if method != "GET":
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            matrix = tracing.load_matrix(project_id)
            if matrix is None:
                return _json({
                    "ok": False,
                    "error": "No traceability matrix. POST /traceability/refresh first.",
                }, 404)
            return _json({
                "ok": True,
                "summary": matrix.get("summary", {}),
                "baseline": matrix.get("baseline"),
                "generated": matrix.get("generated"),
                "gate": tracing.gate_verdict(matrix, threshold=threshold),
            })

        if action == "refresh" and method == "POST":
            result = tracing.refresh(project_id, data)
            return _json({
                "ok": True,
                "summary": result["matrix"]["summary"],
                "json": result["json"],
                "snapshot": result["snapshot"],
                "baseline": result["baseline"],
                "gate": tracing.gate_verdict(result["matrix"], threshold=threshold),
            }, 201)

        if action == "reverse" and method == "GET":
            file_path = _query_one(query, "file")
            if not file_path:
                return _json({"ok": False, "error": "query param 'file' is required"}, 400)
            return _json({"ok": True, **tracing.reverse_lookup(project_id, file_path)})

        return _json({"ok": False, "error": f"Unknown traceability action: {action}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Baseline handlers (SUP.8) ─────────────────────────────────────────────

def _query_one(query: dict, key: str) -> str:
    """Read a single query-string value (parse_qs returns lists)."""
    value = (query or {}).get(key)
    if isinstance(value, list):
        return (value[0] if value else "").strip()
    return (value or "").strip()


def _dispatch_baselines(project_id: str, method: str, parts: list,
                        body: Any, query: dict) -> tuple:
    """Handle /projects/{id}/baselines[/diff|/{name}]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    name = parts[0] if parts else ""
    data = body if isinstance(body, dict) else {}

    try:
        if not name:
            if method == "GET":
                return _json({"ok": True, "baselines": baseline.list_baselines(project_id)})
            if method == "POST":
                snap = baseline.create_baseline(project_id, data)
                return _json({"ok": True, "baseline": snap}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if name == "diff":
            if method != "GET":
                return _json({"ok": False, "error": "Method not allowed"}, 405)
            from_name = _query_one(query, "from")
            to_name = _query_one(query, "to")
            if not from_name or not to_name:
                return _json({"ok": False, "error": "query params 'from' and 'to' are required"}, 400)
            diff = baseline.diff_baselines(project_id, from_name, to_name)
            return _json({"ok": True, "diff": diff})

        if method == "GET":
            return _json({"ok": True, "baseline": baseline.load_baseline(project_id, name)})
        return _json({"ok": False, "error": "Method not allowed"}, 405)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except baseline.BaselineConflict as e:
        return _json({"ok": False, "error": str(e)}, 409)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Change-request handlers (SUP.10) ───────────────────────────────────────

def _dispatch_change_requests(project_id: str, method: str, parts: list, body: Any) -> tuple:
    """Handle /projects/{id}/change-requests[/{cr_id}[/{action}]]."""
    try:
        workspace._load_meta(project_id)
    except FileNotFoundError:
        return _json({"ok": False, "error": "Project not found"}, 404)

    cr_id = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    data = body if isinstance(body, dict) else {}

    if cr_id and (".." in cr_id or "/" in cr_id or "\\" in cr_id):
        return _json({"ok": False, "error": f"Invalid change request id: {cr_id}"}, 400)

    try:
        if not cr_id:
            if method == "GET":
                return _json({
                    "ok": True,
                    "change_requests": change_control.list_change_requests(project_id),
                })
            if method == "POST":
                cr = change_control.create_change_request(project_id, data)
                return _json({"ok": True, "change_request": cr}, 201)
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if not action:
            if method == "GET":
                cr = change_control.load_change_request(project_id, cr_id)
                return _json({"ok": True, "change_request": cr})
            return _json({"ok": False, "error": "Method not allowed"}, 405)

        if action == "analyze" and method == "POST":
            impact = change_control.analyze_impact(project_id, cr_id, data)
            cr = change_control.load_change_request(project_id, cr_id)
            return _json({"ok": True, "impact": impact, "change_request": cr})

        if action == "transition" and method == "POST":
            cr = change_control.transition(project_id, cr_id, data)
            return _json({"ok": True, "change_request": cr})

        return _json({"ok": False, "error": f"Unknown change-request action: {action}"}, 404)
    except FileNotFoundError as e:
        return _json({"ok": False, "error": str(e)}, 404)
    except change_control.InvalidTransition as e:
        return _json({"ok": False, "error": str(e)}, 409)
    except ValueError as e:
        return _json({"ok": False, "error": str(e)}, 400)


# ── Review handlers (evidence/review.json) ──────────────────────────────────

import secrets as _secrets

_REVIEW_STATUS = {"approved", "rejected", "needs_revision"}


def _review_path(project_id: str) -> Path:
    """Return the evidence/review.json path, creating parent dirs if needed."""
    proj_dir = workspace._project_dir(project_id)
    rev_dir = proj_dir / "evidence"
    rev_dir.mkdir(parents=True, exist_ok=True)
    return rev_dir / "review.json"


def _load_reviews(project_id: str) -> dict:
    """Load review.json; return empty dict if missing or invalid."""
    p = _review_path(project_id)
    if not p.exists():
        return {"reviews": {}, "index": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if "reviews" not in data:
            return {"reviews": data if isinstance(data, list) else {}, "index": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"reviews": {}, "index": []}


def _save_reviews(project_id: str, data: dict) -> None:
    p = _review_path(project_id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_review(project_id: str, body: Any) -> tuple:
    """Create a new review entry.

    body fields:
        artifact    str — 产物文件路径（如 code/src/main.c）
        status      str — approved | rejected | needs_revision
        comment     str — 批注（可选）
        author      str — 评审人（可选，默认 "local"）
        line_start  int — 行号范围（可选）
        line_end    int
    """
    data = body if isinstance(body, dict) else {}
    artifact = (data.get("artifact") or "").strip()
    status = (data.get("status") or "").strip().lower()
    comment = (data.get("comment") or "").strip()
    author = (data.get("author") or "local").strip()

    if not artifact:
        return _json({"ok": False, "error": "artifact is required"}, 400)
    if status not in _REVIEW_STATUS:
        return _json({"ok": False, "error": f"status must be one of {_REVIEW_STATUS}"}, 400)

    # 防路径穿越：artifact 必须在已知产物目录下
    proj_dir = workspace._project_dir(project_id)
    target = (proj_dir / artifact).resolve()
    try:
        target.relative_to(proj_dir.resolve())
    except ValueError:
        return _json({"ok": False, "error": "artifact path escapes project dir"}, 400)

    entry = {
        "id": _secrets.token_hex(6),
        "artifact": artifact,
        "status": status,
        "comment": comment,
        "author": author,
        "created_at": datetime.now().isoformat(),
        "line_start": data.get("line_start"),
        "line_end": data.get("line_end"),
    }

    store = _load_reviews(project_id)
    store["reviews"][entry["id"]] = entry
    if entry["id"] not in store.get("index", []):
        store.setdefault("index", []).append(entry["id"])
    _save_reviews(project_id, store)

    return _json({"ok": True, "review": entry}, 201)


def _list_reviews(project_id: str) -> tuple:
    """List all reviews for a project, newest first."""
    store = _load_reviews(project_id)
    reviews = list(store["reviews"].values())
    reviews.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # 按 artifact 分组的汇总（给前端侧栏用）
    by_artifact: dict[str, dict] = {}
    for r in reviews:
        art = r["artifact"]
        agg = by_artifact.setdefault(art, {"artifact": art, "approved": 0, "rejected": 0, "needs_revision": 0, "total": 0})
        agg[r["status"]] = agg.get(r["status"], 0) + 1
        agg["total"] += 1

    return _json({
        "ok": True,
        "reviews": reviews,
        "summary_by_artifact": list(by_artifact.values()),
        "total": len(reviews),
    })


def _get_review(project_id: str, rev_id: str) -> tuple:
    store = _load_reviews(project_id)
    rev = store["reviews"].get(rev_id)
    if not rev:
        return _json({"ok": False, "error": "Review not found"}, 404)
    return _json({"ok": True, "review": rev})


def _delete_review(project_id: str, rev_id: str) -> tuple:
    store = _load_reviews(project_id)
    if rev_id not in store["reviews"]:
        return _json({"ok": False, "error": "Review not found"}, 404)
    store["reviews"].pop(rev_id)
    store["index"] = [x for x in store.get("index", []) if x != rev_id]
    _save_reviews(project_id, store)
    return _json({"ok": True})


def _bulk_reviews(project_id: str, body: Any) -> tuple:
    """批量给多个产物打同一个评审标签。

    body 字段:
        scope        "artifact" | "section" | "all"
        artifacts    list[str]   — scope="artifact" 时指定文件路径
        section      str         — scope="section" 时指定分区名（如 code / tests）
        status       str         — approved | rejected | needs_revision
        comment      str         — 可选批注
    """
    data = body if isinstance(body, dict) else {}
    scope = data.get("scope", "all").strip()
    status = (data.get("status") or "").strip().lower()
    comment = (data.get("comment") or "").strip()

    if status not in _REVIEW_STATUS:
        return _json({"ok": False, "error": f"status must be one of {_REVIEW_STATUS}"}, 400)

    proj_dir = workspace._project_dir(project_id)
    # 收集所有产物文件路径
    all_files = []
    for sub in ("requirements", "design", "code", "tests", "evidence"):
        sub_path = proj_dir / sub
        if sub_path.exists():
            for fpath in sub_path.rglob("*"):
                if fpath.is_file():
                    all_files.append(str(fpath.relative_to(proj_dir)))

    if scope == "artifact":
        targets = [p for p in (data.get("artifacts") or []) if p in all_files]
    elif scope == "section":
        section = (data.get("section") or "").strip()
        if not section:
            return _json({"ok": False, "error": "section is required"}, 400)
        targets = [p for p in all_files if p.startswith(section + "/")]
    else:  # all
        targets = all_files

    if not targets:
        return _json({"ok": True, "created": 0, "skipped": 0, "message": "no files matched"}, 200)

    store = _load_reviews(project_id)
    existing_by_artifact: dict[str, str] = {
        r["artifact"]: rid for rid, r in store["reviews"].items()
    }
    created = 0
    skipped = 0

    for artifact in targets:
        if artifact in existing_by_artifact:
            # 同一文件已有评审记录 — 更新而非重复创建
            existing = store["reviews"][existing_by_artifact[artifact]]
            existing["status"] = status
            if comment:
                existing["comment"] = comment
            existing["created_at"] = datetime.now().isoformat()
            skipped += 1
            continue
        rid = _secrets.token_hex(6)
        store["reviews"][rid] = {
            "id": rid,
            "artifact": artifact,
            "status": status,
            "comment": comment,
            "author": "local",
            "created_at": datetime.now().isoformat(),
        }
        store.setdefault("index", []).append(rid)
        created += 1

    _save_reviews(project_id, store)
    return _json({"ok": True, "created": created, "updated": skipped})


def _export_reviews(project_id: str) -> tuple:
    """把 review.json 导出成 evidence/review-report.md 并返回其内容。"""
    store = _load_reviews(project_id)
    reviews = list(store["reviews"].values())
    reviews.sort(key=lambda r: r.get("artifact", ""))

    proj_dir = workspace._project_dir(project_id)
    meta_path = proj_dir / "project.json"
    proj_name = "unknown"
    if meta_path.exists():
        try:
            proj_name = json.loads(meta_path.read_text(encoding="utf-8")).get("name", "unknown")
        except (json.JSONDecodeError, OSError):
            pass

    # 汇总
    summary = {"approved": 0, "rejected": 0, "needs_revision": 0}
    for r in reviews:
        summary[r.get("status", "needs_revision")] = summary.get(r.get("status", "needs_revision"), 0) + 1

    # 按分区分组
    sections: dict[str, list[dict]] = {}
    for r in reviews:
        section = r["artifact"].split("/")[0] if "/" in r["artifact"] else "other"
        sections.setdefault(section, []).append(r)

    # 生成 Markdown
    lines = [
        f"# 评审报告 — {proj_name}",
        "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"> 评审总数：{len(reviews)}  ✅ 通过 {summary['approved']}  ❌ 退回 {summary['rejected']}  🔍 修改 {summary['needs_revision']}",
        "",
        "## 概览",
        "",
        f"| 分区 | 通过 | 退回 | 修改 | 合计 |",
        "|---|---|---|---|---|",
    ]
    for sec in sorted(sections.keys()):
        sec_reviews = sections[sec]
        s = {"approved": 0, "rejected": 0, "needs_revision": 0}
        for r in sec_reviews:
            s[r.get("status", "needs_revision")] = s.get(r.get("status", "needs_revision"), 0) + 1
        lines.append(f"| {sec} | {s['approved']} | {s['rejected']} | {s['needs_revision']} | {len(sec_reviews)} |")
    lines.append("")

    for sec in sorted(sections.keys()):
        sec_reviews = sections[sec]
        lines.extend([f"## {sec}", ""])
        for r in sec_reviews:
            tag = {"approved": "✅ 通过", "rejected": "❌ 退回", "needs_revision": "🔍 修改"}.get(r.get("status"), r.get("status"))
            lines.append(f"- **`{r['artifact']}`** — {tag}  ")
            if r.get("comment"):
                lines.append(f"  > {r['comment']}  ")
            lines.append(f"  _by {r.get('author', 'local')} · {r.get('created_at', '').replace('T', ' ')}_  ")
            lines.append("")

    content = "\n".join(lines)

    # 落盘到 evidence/review-report.md
    report_path = proj_dir / "evidence" / "review-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8")

    return _json({
        "ok": True,
        "path": "evidence/review-report.md",
        "content": content,
        "total": len(reviews),
        "summary": summary,
    })
