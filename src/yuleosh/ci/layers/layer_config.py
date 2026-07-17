#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Layers — Config helpers (extracted from layers.py).

Includes:
  - get_latest_layer_result — 读取最近一次 CI 结果
  - check_layer_dependency — 层依赖检查
  - _detect_project_language — 项目语言自动检测
  - _LayerTimeout — 超时异常
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from yuleosh.ci.config import _get_ci_config, layer_dependencies

log = logging.getLogger("ci.layers.config")

# Directories to always skip during filesystem walks (large dep dirs)
_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".egg-info", ".mypy_cache",
             "node_modules", "venv", ".venv", "vendor", ".vendor",
             "third_party", ".cache", ".go", "target", ".build"}


class _LayerTimeout(Exception):
    """Raised when a CI layer exceeds its configured timeout."""
    pass


def get_latest_layer_result(layer: int, project_dir: str) -> Optional[dict]:
    """Read the most recent CI result for the given layer from .osh/ci/.

    Returns the parsed JSON dict if found, or None if no result exists.
    """
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        return None

    prefix = f"layer{layer}-"
    result_files = sorted(
        [f for f in ci_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not result_files:
        return None
    try:
        return json.loads(result_files[0].read_text())
    except (json.JSONDecodeError, OSError):
        return None


def check_layer_dependency(target_layer: int, project_dir: str) -> Optional[str]:
    """Check if all dependencies for *target_layer* are satisfied.

    Reads the dependency chain from ``ci-config.yaml`` first, falling back
    to the hardcoded global ``layer_dependencies`` dict when the config
    file is absent or broken.

    Returns None if all deps passed, or a string describing the first
    blocking dependency failure.
    """
    try:
        cfg = _get_ci_config(project_dir)
        deps = cfg.layer_dependencies.get(target_layer, [])
    except Exception as e:
        logging.getLogger("ci.layers.config").info(
            "Layer dependency check config fallback: %s", e
        )
        deps = layer_dependencies.get(target_layer, [])

    for dep in deps:
        result = get_latest_layer_result(dep, project_dir)
        if result is None:
            return (
                f"Layer {dep} has no recorded result — "
                f"run layer {dep} first before layer {target_layer}"
            )
        if result.get("status") != "passed":
            return (
                f"Layer {dep} status is '{result.get('status', 'unknown')}' — "
                f"layer {target_layer} blocked (dependency chain: "
                f"{' → '.join(str(l) for l in deps)})"
            )
    return None


def _detect_project_language(project_dir: str) -> str:
    """Detect the project language type by examining marker files.

    Checks in order:
    1. ``go.mod`` → Go project
    2. ``pyproject.toml`` or ``setup.py`` → Python project
    3. ``CMakeLists.txt`` or ``Makefile`` → C project
    4. Falls back to scanning ``src/`` for C/C++ source files
    5. If none matched, return "c" (backward compatible default)

    Returns
    -------
    str
        One of ``"go"``, ``"python"``, or ``"c"``.
    """
    project_path = Path(project_dir)

    # 1. Go project
    if (project_path / "go.mod").exists():
        return "go"

    # 2. Python project
    if (project_path / "pyproject.toml").exists():
        return "python"
    if (project_path / "setup.py").exists():
        return "python"
    if (project_path / "setup.cfg").exists():
        return "python"

    # 3. C project (build system markers)
    if (project_path / "CMakeLists.txt").exists():
        return "c"
    if (project_path / "Makefile").exists():
        return "c"

    # 4. Check src/ for C/C++ source files (limited depth)
    src_dir = project_path / "src"
    if src_dir.is_dir():
        for root, dirs, files in os.walk(src_dir):
            rel = os.path.relpath(root, str(src_dir))
            if rel.count(os.sep) > 4:
                dirs.clear()
                continue
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                if f.endswith((".c", ".cpp", ".h", ".hpp")):
                    return "c"

    # 5. Check for .py files in project root (Python project without pyproject.toml)
    py_files = list(project_path.glob("*.py"))
    if py_files:
        return "python"

    # 6. Default: treat as C project (backward compatible)
    return "c"
