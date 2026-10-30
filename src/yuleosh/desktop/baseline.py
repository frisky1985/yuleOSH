# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Configuration baselines (ASPICE SUP.8 minimal loop).

A baseline is an immutable snapshot of the project's configuration items::

    {project}/baselines/{name}.json

Each baseline records every artifact file with its SHA-256 digest, the author,
the optional pipeline run it belongs to, and a timestamp. Two baselines can be
diffed to produce a change list, which is archived as release evidence::

    {project}/.osh/evidence/baseline-diff-{from}--{to}.json
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.desktop import workspace

BASELINE_DIR = "baselines"
IMPACT_EVIDENCE_DIR = Path(".osh") / "evidence"

# 纳入基线的配置项分区。pipeline 下是运行历史，不算配置项，故排除。
CI_DIRS = ("requirements", "design", "code", "tests", "evidence", "change-requests")

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BaselineConflict(ValueError):
    """Raised when a baseline with the same name already exists."""


def _baseline_dir(project_id: str, create: bool = False) -> Path:
    d = workspace._project_dir(project_id) / BASELINE_DIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise ValueError(
            "baseline name must be 1-64 chars of letters, digits, '.', '_' or '-'"
        )
    return name


def _auto_name() -> str:
    return f"BSL-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _manifest(project_id: str) -> list[dict]:
    proj_dir = workspace._project_dir(project_id)
    files = []
    for sub in CI_DIRS:
        base = proj_dir / sub
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file():
                continue
            files.append({
                "path": str(f.relative_to(proj_dir)),
                "sha256": _sha256(f),
                "size": f.stat().st_size,
            })
    files.sort(key=lambda x: x["path"])
    return files


def create_baseline(project_id: str, body: dict[str, Any] | None = None) -> dict:
    """Snapshot the current configuration items into ``baselines/{name}.json``."""
    workspace._load_meta(project_id)
    body = body or {}

    name = _validate_name(body.get("name") or "") if body.get("name") else _auto_name()
    path = _baseline_dir(project_id) / f"{name}.json"
    if path.exists():
        raise BaselineConflict(f"Baseline already exists: {name}")

    files = _manifest(project_id)
    manifest_sha = hashlib.sha256(
        json.dumps(files, sort_keys=True).encode("utf-8")
    ).hexdigest()

    baseline = {
        "name": name,
        "label": (body.get("label") or "").strip(),
        "notes": (body.get("notes") or "").strip(),
        "author": (body.get("author") or "local").strip(),
        "pipeline_run": (body.get("pipeline_run") or "").strip() or None,
        "created_at": datetime.now().isoformat(),
        "file_count": len(files),
        "manifest_sha256": manifest_sha,
        "files": files,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return baseline


def load_baseline(project_id: str, name: str) -> dict:
    workspace._load_meta(project_id)
    name = _validate_name(name)
    path = _baseline_dir(project_id) / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Baseline not found: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_baselines(project_id: str) -> list[dict]:
    workspace._load_meta(project_id)
    d = _baseline_dir(project_id)
    if not d.exists():
        return []
    items = []
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # 列表不返回完整文件清单，避免响应过大。
        items.append({
            "name": data.get("name", p.stem),
            "label": data.get("label", ""),
            "author": data.get("author"),
            "pipeline_run": data.get("pipeline_run"),
            "created_at": data.get("created_at"),
            "file_count": data.get("file_count", 0),
            "manifest_sha256": data.get("manifest_sha256"),
        })
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def diff_baselines(project_id: str, from_name: str, to_name: str) -> dict:
    """Compare two baselines and archive the change list as evidence."""
    workspace._load_meta(project_id)
    before = load_baseline(project_id, from_name)
    after = load_baseline(project_id, to_name)

    old = {f["path"]: f["sha256"] for f in before["files"]}
    new = {f["path"]: f["sha256"] for f in after["files"]}

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = [
        {"path": p, "sha256_from": old[p], "sha256_to": new[p]}
        for p in sorted(set(old) & set(new))
        if old[p] != new[p]
    ]

    diff = {
        "from": before["name"],
        "to": after["name"],
        "generated_at": datetime.now().isoformat(),
        "added": added,
        "removed": removed,
        "modified": modified,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "total_changes": len(added) + len(removed) + len(modified),
        },
    }

    evidence = (
        workspace._project_dir(project_id)
        / IMPACT_EVIDENCE_DIR
        / f"baseline-diff-{before['name']}--{after['name']}.json"
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")
    diff["evidence_path"] = str(evidence.relative_to(workspace._project_dir(project_id)))
    return diff
