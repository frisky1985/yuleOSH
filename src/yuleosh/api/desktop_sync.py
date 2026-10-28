# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Cloud-side receiver for desktop project sync.

Desktop apps POST their project metadata + artifact files to
``/api/v1/desktop-sync``. The SaaS backend stores them under the user's
tenant so the web UI can render the same artifacts (requirements / code /
tests / evidence) that the desktop produced.

Storage layout (under ``OSH_HOME/cloud-sync/``)::

    cloud-sync/
      {project_id}/
        project.json        # project metadata
        artifacts.json      # artifact tree
        files/              # materialized artifact files
          requirements/requirements.md
          code/src/main.c
          ...

Endpoints
---------
- ``POST /api/v1/desktop-sync``            — receive a synced project
- ``GET  /api/v1/desktop-sync``            — list synced projects
- ``GET  /api/v1/desktop-sync/{id}``       — get project metadata + tree
- ``GET  /api/v1/desktop-sync/{id}/files/{path}`` — read an artifact file
- ``DELETE /api/v1/desktop-sync/{id}``     — remove a synced project
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("api.desktop_sync")


def _sync_root() -> Path:
    """Return the cloud-sync storage root (created if missing)."""
    osh_home = os.environ.get("OSH_HOME", str(Path.home() / ".yuleosh"))
    root = Path(osh_home) / "cloud-sync"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_dir(project_id: str) -> Path:
    # Prevent path traversal.
    safe = "".join(c for c in project_id if c.isalnum() or c in "-_")
    if safe != project_id:
        raise ValueError("Invalid project id")
    return _sync_root() / safe


def _json(data: dict, status: int = 200):
    return data, status


def handle_desktop_sync(method: str, path_tail: str, body: Any, query: dict,
                        handler=None) -> tuple:
    """Dispatcher for /api/v1/desktop-sync routes."""
    parts = (path_tail or "").strip("/").split("/")

    # POST /api/v1/desktop-sync  → receive a synced project
    if not parts or parts == [""]:
        if method == "POST":
            return _receive_sync(body)
        if method == "GET":
            return _list_synced()
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    project_id = parts[0]

    # /api/v1/desktop-sync/{id}
    if len(parts) == 1:
        if method == "GET":
            return _get_synced(project_id)
        if method == "DELETE":
            return _delete_synced(project_id)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    # /api/v1/desktop-sync/{id}/files/{path...}
    if len(parts) >= 2 and parts[1] == "files":
        rel = "/".join(parts[2:])
        if method == "GET":
            return _read_synced_file(project_id, rel)
        return _json({"ok": False, "error": "Method not allowed"}, 405)

    return _json({"ok": False, "error": f"Unknown sub-resource: {parts[1]}"}, 404)


# ── Handlers ──────────────────────────────────────────────────────────────

def _receive_sync(body: Any) -> tuple:
    """Receive a desktop project sync and persist it to cloud storage.

    Supports both full and incremental modes:

    - **Full mode** (default, backward-compatible): 接收整包 files，清空旧文件目录
      后重写。legacy 客户端或首次同步走这里。
    - **Incremental mode** (``mode: "incremental"``): ``files`` 只包含变化/新增
      文件，``removed`` 是本地已删除文件的路径列表。云端只更新变化的文件、
      删除 removed 列表，未提及的文件保留不动。适合频繁同步时节省带宽。
    """
    data = body if isinstance(body, dict) else {}
    project_id = data.get("project_id")
    if not project_id:
        return _json({"ok": False, "error": "project_id is required"}, 400)

    try:
        proj_dir = _project_dir(project_id)
    except ValueError:
        return _json({"ok": False, "error": "Invalid project id"}, 400)

    proj_dir.mkdir(parents=True, exist_ok=True)

    # Persist metadata.
    meta = data.get("project", {})
    meta["id"] = project_id
    meta["synced_at"] = data.get("synced_at", datetime.now().isoformat())
    meta["cloud_synced"] = True
    (proj_dir / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Persist artifact tree.
    tree = data.get("artifacts", {})
    (proj_dir / "artifacts.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Materialize files so the web UI can stream them directly.
    files_dir = proj_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    mode = data.get("mode", "full")
    file_count = 0

    if mode == "incremental":
        # 增量：只写变化的、只删 removed 的
        for f in data.get("files", []) or []:
            rel = f.get("path")
            if not rel or f.get("binary"):
                continue
            target = (files_dir / rel).resolve()
            try:
                target.relative_to(files_dir.resolve())
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.get("content", ""), encoding="utf-8")
            file_count += 1

        for rel in data.get("removed", []) or []:
            target = (files_dir / rel).resolve()
            try:
                target.relative_to(files_dir.resolve())
            except ValueError:
                continue
            if target.exists() and target.is_file():
                target.unlink()
                # 清理空父目录（到 files_dir 为止）
                parent = target.parent
                while parent != files_dir:
                    try:
                        parent.rmdir()
                    except OSError:
                        break
                    parent = parent.parent

        log.info("Desktop sync (incremental): project=%s updated=%d removed=%d",
                 project_id, file_count, len(data.get("removed", []) or []))
    else:
        # 全量：清掉旧 files_dir 后重写
        if files_dir.exists():
            shutil.rmtree(files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)
        for f in data.get("files", []) or []:
            rel = f.get("path")
            if not rel or f.get("binary"):
                continue
            target = (files_dir / rel).resolve()
            try:
                target.relative_to(files_dir.resolve())
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.get("content", ""), encoding="utf-8")
            file_count += 1

        log.info("Desktop sync (full): project=%s files=%d", project_id, file_count)

    # 保存 manifest（如果客户端传了），方便云端后续做一致性校验
    if data.get("manifest"):
        (proj_dir / ".cloud_manifest.json").write_text(
            json.dumps(data["manifest"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return _json({
        "ok": True,
        "project_id": project_id,
        "mode": mode,
        "files_stored": file_count,
        "removed_count": len(data.get("removed", []) or []),
        "url": f"/api/v1/desktop-sync/{project_id}",
    }, 201)


def _list_synced() -> tuple:
    """List all cloud-synced desktop projects."""
    root = _sync_root()
    projects = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        meta_path = entry / "project.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            projects.append(meta)
        except (json.JSONDecodeError, OSError):
            continue
    return _json({"ok": True, "projects": projects})


def _get_synced(project_id: str) -> tuple:
    """Get a synced project's metadata + artifact tree."""
    try:
        proj_dir = _project_dir(project_id)
    except ValueError:
        return _json({"ok": False, "error": "Invalid project id"}, 400)
    meta_path = proj_dir / "project.json"
    if not meta_path.exists():
        return _json({"ok": False, "error": "Synced project not found"}, 404)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    tree = {}
    tree_path = proj_dir / "artifacts.json"
    if tree_path.exists():
        try:
            tree = json.loads(tree_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            tree = {}
    return _json({"ok": True, "project": meta, "artifacts": tree})


def _read_synced_file(project_id: str, rel_path: str) -> tuple:
    """Read a materialized artifact file from a synced project."""
    try:
        proj_dir = _project_dir(project_id)
    except ValueError:
        return _json({"ok": False, "error": "Invalid project id"}, 400)
    files_dir = proj_dir / "files"
    if not files_dir.exists():
        return _json({"ok": False, "error": "No files for this project"}, 404)
    target = (files_dir / rel_path).resolve()
    try:
        target.relative_to(files_dir.resolve())
    except ValueError:
        return _json({"ok": False, "error": "Forbidden"}, 403)
    if not target.exists() or not target.is_file():
        return _json({"ok": False, "error": "File not found"}, 404)
    try:
        content = target.read_text(encoding="utf-8")
        return _json({"ok": True, "path": rel_path, "content": content, "binary": False})
    except UnicodeDecodeError:
        return _json({
            "ok": True, "path": rel_path, "content": None, "binary": True,
            "size": target.stat().st_size,
        })


def _delete_synced(project_id: str) -> tuple:
    """Remove a synced project from cloud storage."""
    try:
        proj_dir = _project_dir(project_id)
    except ValueError:
        return _json({"ok": False, "error": "Invalid project id"}, 400)
    if not proj_dir.exists():
        return _json({"ok": False, "error": "Synced project not found"}, 404)
    shutil.rmtree(proj_dir)
    return _json({"ok": True})
