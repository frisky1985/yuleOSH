# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Desktop workspace manager — local project directories with artifact folders.

Project layout (all paths relative to the workspace root):

    {workspace}/{project_id}/
      project.json              # metadata (id, name, description, created_at, ...)
      requirements/             # 需求产出物
        requirements.md
        requirements.json
      design/                   # 设计产出物 (SDD / DDD)
        sdd.md
        architecture.md
      code/                     # 代码产出物
        src/
      tests/                    # 测试用例产出物
        test_*.c
        report.json
      pipeline/                 # pipeline 运行历史
        runs/
          {job_id}/
            config.json
            result.json
            logs.txt
      evidence/                 # 合规证据包

The workspace root defaults to ``~/yuleosh-workspace`` and can be overridden
via the ``YULEOSH_DESKTOP_HOME`` environment variable.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ── Workspace root ────────────────────────────────────────────────────────

def workspace_root() -> Path:
    """Return the desktop workspace root directory (created if missing)."""
    root = Path(os.environ.get(
        "YULEOSH_DESKTOP_HOME",
        str(Path.home() / "yuleosh-workspace"),
    )).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── Artifact folder names (single source of truth) ────────────────────────

ARTIFACT_DIRS = ("requirements", "design", "code", "tests", "pipeline", "evidence")

# 无法自动归类的产物落在这里。不属于五分区，只在确实有文件时才出现在树上，
# 由 UI 以"待归类"告警样式呈现，供人工归位。
UNCLASSIFIED_DIR = "_unclassified"


# ── Project model ─────────────────────────────────────────────────────────

def _project_dir(project_id: str) -> Path:
    return workspace_root() / project_id


def _project_meta_path(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def _load_meta(project_id: str) -> dict:
    meta_path = _project_meta_path(project_id)
    if not meta_path.exists():
        raise FileNotFoundError(f"Project not found: {project_id}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _save_meta(project_id: str, meta: dict) -> None:
    meta["updated_at"] = datetime.now().isoformat()
    _project_meta_path(project_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_projects() -> list[dict]:
    """List all local projects sorted by updated_at descending."""
    root = workspace_root()
    projects = []
    for entry in root.iterdir():
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
    projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return projects


def create_project(name: str, description: str = "") -> dict:
    """Create a new project with the standard artifact folder skeleton."""
    name = name.strip()
    if not name:
        raise ValueError("Project name is required")

    project_id = uuid.uuid4().hex[:12]
    proj_dir = _project_dir(project_id)
    if proj_dir.exists():
        # Collision extremely unlikely with uuid4; retry once.
        project_id = uuid.uuid4().hex[:12]
        proj_dir = _project_dir(project_id)

    proj_dir.mkdir(parents=True, exist_ok=True)
    for sub in ARTIFACT_DIRS:
        (proj_dir / sub).mkdir(parents=True, exist_ok=True)
    (proj_dir / "pipeline" / "runs").mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    meta = {
        "id": project_id,
        "name": name,
        "description": description.strip(),
        "created_at": now,
        "updated_at": now,
        "pipeline_runs": 0,
        "last_pipeline_status": None,
        "cloud_synced": False,
        "last_synced_at": None,
    }
    _save_meta(project_id, meta)
    return meta


def get_project(project_id: str) -> dict:
    """Get project metadata plus artifact folder summary."""
    meta = _load_meta(project_id)
    proj_dir = _project_dir(project_id)
    folders = {}
    for sub in ARTIFACT_DIRS:
        sub_path = proj_dir / sub
        folders[sub] = {
            "path": sub,
            "exists": sub_path.exists(),
            "file_count": sum(1 for _ in sub_path.rglob("*") if _.is_file())
            if sub_path.exists() else 0,
        }
    meta["artifacts"] = folders
    return meta


def delete_project(project_id: str) -> None:
    """Delete a project and all its artifacts."""
    proj_dir = _project_dir(project_id)
    if not proj_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_id}")
    shutil.rmtree(proj_dir)


# ── Requirements ──────────────────────────────────────────────────────────

def save_requirements(project_id: str, content: str, source: str = "chatbot") -> dict:
    """Save imported requirements into the project's requirements/ folder.

    Args:
        project_id: target project.
        content: requirements text (Markdown supported).
        source: where the requirements came from ('cli' | 'chatbot' | 'file').
    """
    meta = _load_meta(project_id)
    req_dir = _project_dir(project_id) / "requirements"
    req_dir.mkdir(parents=True, exist_ok=True)

    # Write the human-readable requirements document.
    md_path = req_dir / "requirements.md"
    md_path.write_text(content, encoding="utf-8")

    # Write a machine-readable manifest.
    manifest = {
        "source": source,
        "imported_at": datetime.now().isoformat(),
        "char_count": len(content),
        "line_count": content.count("\n") + 1,
    }
    (req_dir / "requirements.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _save_meta(project_id, meta)
    return manifest


def get_requirements(project_id: str) -> dict:
    """Read the project's requirements content and manifest."""
    _load_meta(project_id)
    req_dir = _project_dir(project_id) / "requirements"
    md_path = req_dir / "requirements.md"
    json_path = req_dir / "requirements.json"
    content = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    manifest = {}
    if json_path.exists():
        try:
            manifest = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    return {"content": content, "manifest": manifest}


# ── Artifact tree browsing ────────────────────────────────────────────────

def _build_tree(base: Path, current: Path, max_depth: int = 6, depth: int = 0) -> dict:
    """Recursively build a file/folder tree under ``current`` (within base)."""
    rel = current.relative_to(base)
    name = current.name if str(rel) != "." else base.name
    node = {"name": name, "path": str(rel), "type": "dir", "children": []}
    if depth >= max_depth:
        return node
    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return node
    for entry in entries:
        if entry.name.startswith(".") and entry.name != ".yuleosh":
            continue
        if entry.is_dir():
            node["children"].append(_build_tree(base, entry, max_depth, depth + 1))
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            node["children"].append({
                "name": entry.name,
                "path": str(entry.relative_to(base)),
                "type": "file",
                "size": size,
            })
    return node


def list_artifacts(project_id: str) -> dict:
    """Return the artifact folder tree for a project."""
    _load_meta(project_id)
    proj_dir = _project_dir(project_id)
    tree = {"name": proj_dir.name, "path": ".", "type": "dir", "children": []}
    for sub in ARTIFACT_DIRS:
        sub_path = proj_dir / sub
        if sub_path.exists():
            tree["children"].append(_build_tree(proj_dir, sub_path))
    # 待归类目录不是正式分区，仅在有产物时附加到树末尾
    unclassified = proj_dir / UNCLASSIFIED_DIR
    if unclassified.exists() and any(p.is_file() for p in unclassified.rglob("*")):
        tree["children"].append(_build_tree(proj_dir, unclassified))
    return tree


def read_artifact(project_id: str, rel_path: str) -> dict:
    """Read an artifact file's content (text only; binary returns base64 info)."""
    _load_meta(project_id)
    proj_dir = _project_dir(project_id)
    # Path traversal protection.
    target = (proj_dir / rel_path).resolve()
    try:
        target.relative_to(proj_dir.resolve())
    except ValueError:
        raise PermissionError("Artifact path escapes project directory")

    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Artifact not found: {rel_path}")

    ext = target.suffix.lower()
    text_exts = {
        ".md", ".txt", ".json", ".yaml", ".yml", ".c", ".h", ".cpp", ".hpp",
        ".py", ".js", ".ts", ".tsx", ".html", ".css", ".log", ".xml", ".cfg",
        ".ini", ".toml", ".sh", ".make", ".mk",
    }
    if ext in text_exts or target.stat().st_size < 64 * 1024:
        try:
            content = target.read_text(encoding="utf-8")
            return {"path": rel_path, "content": content, "binary": False}
        except UnicodeDecodeError:
            pass
    return {
        "path": rel_path,
        "content": None,
        "binary": True,
        "size": target.stat().st_size,
        "message": "Binary file — open in external viewer",
    }


# ── Pipeline run record ───────────────────────────────────────────────────

def record_pipeline_run(project_id: str, job_id: str, config: Optional[dict] = None) -> Path:
    """Create a run record folder under pipeline/runs/{job_id}/ and return its path."""
    meta = _load_meta(project_id)
    run_dir = _project_dir(project_id) / "pipeline" / "runs" / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(config or {}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    meta["pipeline_runs"] = meta.get("pipeline_runs", 0) + 1
    _save_meta(project_id, meta)
    return run_dir


def save_pipeline_result(project_id: str, job_id: str, result: dict, logs: str = "") -> None:
    """Persist pipeline result + logs into the run folder."""
    _load_meta(project_id)
    run_dir = _project_dir(project_id) / "pipeline" / "runs" / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    if logs:
        (run_dir / "logs.txt").write_text(logs, encoding="utf-8")
    meta = _load_meta(project_id)
    meta["last_pipeline_status"] = result.get("status")
    _save_meta(project_id, meta)


def list_pipeline_runs(project_id: str) -> list[dict]:
    """List pipeline runs for a project (most recent first)."""
    _load_meta(project_id)
    runs_dir = _project_dir(project_id) / "pipeline" / "runs"
    runs = []
    if not runs_dir.exists():
        return runs
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        result_path = run_dir / "result.json"
        result = {}
        if result_path.exists():
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                result = {}
        runs.append({
            "job_id": run_dir.name,
            "status": result.get("status", "unknown"),
            "started_at": result.get("started_at"),
            "completed_at": result.get("completed_at"),
        })
    return runs


# ── Cloud sync (placeholder hooks) ────────────────────────────────────────
# The actual cloud upload requires a SaaS backend URL + credentials. We expose
# a sync_record update here; the API handler performs the upload (or flags it
# as pending when no cloud endpoint is configured).

def mark_synced(project_id: str, remote_url: Optional[str] = None) -> None:
    meta = _load_meta(project_id)
    meta["cloud_synced"] = True
    meta["last_synced_at"] = datetime.now().isoformat()
    if remote_url:
        meta["cloud_url"] = remote_url
    _save_meta(project_id, meta)


# ── Cloud sync payload collection ────────────────────────────────────────

_TEXT_EXTS = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".c", ".h", ".cpp", ".hpp",
    ".py", ".js", ".ts", ".tsx", ".html", ".css", ".log", ".xml", ".cfg",
    ".ini", ".toml", ".sh", ".make", ".mk",
}


def collect_artifact_files(project_id: str, max_size: int = 512 * 1024) -> list[dict]:
    """Return a flat list of all artifact files with their text content.

    Used by the cloud-sync upload so the SaaS backend can render the same
    artifacts in the web UI without requiring filesystem access.
    Binary files are included as metadata only (content omitted).
    """
    _load_meta(project_id)
    proj_dir = _project_dir(project_id)
    files: list[dict] = []
    for sub in ARTIFACT_DIRS:
        sub_path = proj_dir / sub
        if not sub_path.exists():
            continue
        for fpath in sorted(sub_path.rglob("*")):
            if not fpath.is_file():
                continue
            rel = str(fpath.relative_to(proj_dir))
            entry = {"path": rel, "size": fpath.stat().st_size}
            if fpath.suffix.lower() in _TEXT_EXTS and fpath.stat().st_size < max_size:
                try:
                    entry["content"] = fpath.read_text(encoding="utf-8")
                    entry["binary"] = False
                except UnicodeDecodeError:
                    entry["binary"] = True
            else:
                entry["binary"] = True
            files.append(entry)
    return files


def _file_hash(fpath: Path) -> str:
    """Return MD5 hex digest of a file (chunks for large files)."""
    import hashlib
    h = hashlib.md5()
    with open(fpath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def collect_artifact_incremental(project_id: str, max_size: int = 512 * 1024) -> dict:
    """Compute incremental sync payload: changed files + removed files.

    Compares current artifact files against the previous sync manifest
    (``.sync_manifest.json`` in the project dir). Returns a dict with::

        {
            "mode": "incremental",
            "files":     [...],   # changed + new files (same shape as collect_artifact_files)
            "removed":   [...],   # paths that were in the old manifest but are now absent
            "manifest":  {...},   # current {path: md5} manifest for next sync
            "changed_count": N,   # changed + new file count
            "removed_count": M,
        }

    On first sync (no prior manifest), behaves like collect_artifact_files
    with every file marked as changed.
    """
    _load_meta(project_id)
    proj_dir = _project_dir(project_id)
    manifest_path = proj_dir / ".sync_manifest.json"

    # 读取上一次的 manifest（如果存在）
    old_manifest: dict[str, str] = {}
    if manifest_path.exists():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old_manifest = {}

    # 扫当前所有产物文件
    current: dict[str, Path] = {}
    for sub in ARTIFACT_DIRS:
        sub_path = proj_dir / sub
        if not sub_path.exists():
            continue
        for fpath in sorted(sub_path.rglob("*")):
            if fpath.is_file():
                current[str(fpath.relative_to(proj_dir))] = fpath

    # 增量计算
    changed_files: list[dict] = []
    new_manifest: dict[str, str] = {}
    for rel, fpath in current.items():
        h = _file_hash(fpath)
        new_manifest[rel] = h
        if old_manifest.get(rel) != h:
            # 新文件或 hash 变化 — 打包内容
            size = fpath.stat().st_size
            entry = {"path": rel, "size": size}
            if fpath.suffix.lower() in _TEXT_EXTS and size < max_size:
                try:
                    entry["content"] = fpath.read_text(encoding="utf-8")
                    entry["binary"] = False
                except UnicodeDecodeError:
                    entry["binary"] = True
            else:
                entry["binary"] = True
            changed_files.append(entry)

    removed = sorted(set(old_manifest.keys()) - set(new_manifest.keys()))

    return {
        "mode": "incremental",
        "files": changed_files,
        "removed": removed,
        "manifest": new_manifest,
        "changed_count": len(changed_files),
        "removed_count": len(removed),
        "total_current": len(current),
    }


def save_sync_manifest(project_id: str, manifest: dict[str, str]) -> None:
    """Persist the sync manifest to the project dir for next incremental run."""
    proj_dir = _project_dir(project_id)
    manifest_path = proj_dir / ".sync_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
