#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Projects stats API — per-project aggregate counters for the dashboard
live-feed cards.

Background:
  ActiveProjectsCard (frontend) wants three numbers per project:
    * missing_requirements   — how many reqs lack test/evidence
    * pending_tests         — failed + skipped cases the user must attend
    * evidence_count        — historical ASPICE docs on disk (init baseline)
  These are derived from already-existing per-resource endpoints, so this
  module does NOT re-implement the scanning logic — it delegates to
  ``requirements._gaps`` and ``tests._tests_cases`` and adds a tiny scan
  for ``evidence_count`` (counting ASPICE document files across all
  session dirs belonging to the project).

Mounted at:
    GET /api/v1/projects-stats/stats?project=<name>

Response shape (always 200 on success, 400/403/404 on bad project):
    {
      "project": "<name>",
      "missing_requirements": int,
      "pending_tests": int,
      "evidence_count": int,
      "note": str | null
    }
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.projects_stats")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

# 复用 artifacts 模块的 ASPICE 文档白名单（保持「证据」口径一致）。
# 同一份白名单在两处使用避免口径漂移。
from .artifacts import (_ASPICE_DOCUMENT_EXTS as _EVIDENCE_EXTS,
                        _ASPICE_EVIDENCE_BASENAMES as _EVIDENCE_BASENAMES)  # noqa: E402


# ── Project name resolution (与 requirements._resolve_project_dir 一致) ──

def _resolve_project_dir(project: str) -> tuple[Optional[Path], Optional[tuple]]:
    """Resolve ``OSH_HOME/projects/<project>`` with a path-traversal guard.

    Mirrors ``yuleosh.api.requirements._resolve_project_dir`` to keep the
    auth/safety rules consistent across endpoints. Returns
    ``(project_dir, None)`` on success or ``(None, error_tuple)`` on
    failure.
    """
    if not project:
        return None, json_error("缺少 project 参数", 400)
    if "/" in project or "\\" in project or project in (".", "..") \
            or project.startswith("."):
        return None, json_error("非法 project 名称", 403)
    base = Path(OSH_HOME).resolve() / "projects"
    try:
        proj_dir = (base / project).resolve()
        proj_dir.relative_to(base)
    except (ValueError, OSError):
        return None, json_error("project 路径越界", 403)
    return proj_dir, None


def _scan_evidence_count(project_name: str) -> int:
    """Count ASPICE document files in every session belonging to the project.

    Sessions live at ``<OSH_HOME>/.osh/sessions/<run_id>/`` and each carries
    a ``session.json`` with a ``project`` field. We filter by that field
    rather than by walking ``projects/<name>/`` (orchestrator sessions
    never nest under ``projects/``).

    Returns 0 when the sessions root is absent or no session matches the
    project — graceful (the card simply shows zero).
    """
    sessions_root = Path(OSH_HOME) / ".osh" / "sessions"
    if not sessions_root.is_dir():
        return 0
    total = 0
    try:
        for session_dir in sessions_root.iterdir():
            if not session_dir.is_dir():
                continue
            # Quick project filter via session.json metadata.
            try:
                meta = json.loads(
                    (session_dir / "session.json").read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(meta, dict):
                continue
            # session.json may store project under several keys.
            sess_project = meta.get("project") or meta.get("project_id") \
                or meta.get("project_name")
            if sess_project != project_name:
                continue
            for f in session_dir.rglob("*"):
                if not f.is_file():
                    continue
                ext = f.suffix.lower().lstrip(".")
                if ext not in _EVIDENCE_EXTS:
                    continue
                # .md 额外要求 basename 命中白名单（与 artifacts.py
                # 同口径 —— 避免「test-results-2026-09-04.md」这类
                # 临时报告被算成正式证据）
                if ext == "md" and f.stem.lower() not in _EVIDENCE_BASENAMES:
                    continue
                total += 1
    except OSError as _e:  # noqa: BLE001
        log.debug("evidence scan failed for %s: %s", project_name, _e)
    return total


# ── Handlers ────────────────────────────────────────────────────────────

@require_auth
def handle_projects_stats(method: str, path_tail: str, body: dict, query: dict,
                          handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Route ``GET /api/v1/projects-stats/stats`` requests.

    ``**kwargs`` absorbs the ``current_user`` injected by ``require_auth``.

    Supported routes:
        GET /api/v1/projects-stats/stats — per-project aggregate counters

    Query params:
        - ``project``  single-segment project name (required, path-traversal
          guarded; bare name + ``resolve``越界校验见红线).
    """
    if method != "GET" or path_tail != "stats":
        return json_error(
            f"Unknown projects-stats sub-path or method: {method} {path_tail}",
            404)

    project = query.get("project")
    if isinstance(project, list):
        project = project[0] if project else ""
    project = (project or "").strip()
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err
    assert proj_dir is not None  # err is None on success

    # ── missing_requirements ─────────────────────────────────────────
    # 复用 requirements._gaps —— 返回里 gaps 数组每个元素就是「缺 test
    # 或 evidence 的需求」。空响应（spec 缺失）按 0 计。
    from .requirements import _gaps as _requirements_gaps
    gaps_payload, gaps_status = _requirements_gaps({"project": project})
    if gaps_status != 200:
        return gaps_payload, gaps_status
    gaps_body = gaps_payload.get("data") or {}
    gaps_list = gaps_body.get("gaps", []) or []
    missing_requirements = len(gaps_list)

    # ── pending_tests ────────────────────────────────────────────────
    # 复用 tests._tests_cases 的 summary —— failed + skipped 即「用户需
    # 要关注的用例」; passed 不算 pending。无 session 时 summary 全 0。
    from .tests import _tests_cases as _tests_cases_inner
    tests_payload, tests_status = _tests_cases_inner({"project": project})
    if tests_status != 200:
        return tests_payload, tests_status
    test_summary = (tests_payload.get("data") or {}).get("summary", {}) or {}
    pending_tests = int(test_summary.get("failed", 0)) \
        + int(test_summary.get("skipped", 0))

    # ── evidence_count ───────────────────────────────────────────────
    evidence_count = _scan_evidence_count(project)

    return json_ok({
        "project": project,
        "missing_requirements": missing_requirements,
        "pending_tests": pending_tests,
        "evidence_count": evidence_count,
        "note": gaps_body.get("note"),
    })


__all__ = ["handle_projects_stats"]