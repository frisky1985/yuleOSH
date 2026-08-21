# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Project venv manager — 项目级 Python 虚拟环境（EI-M1B）。

每个项目独立 venv（``<OSH_HOME>/.osh/venvs/<project>/``），隔离依赖，
避免多项目共享系统 Python 环境互相污染（本地开发核心痛点）。

职责:
- ``resolve_venv_dir``: 计算项目 venv 路径（不创建）
- ``ensure_venv``: 不存在则创建（幂等），返回 venv 路径
- ``install_dependencies``: 按 requirements.txt / pyproject.toml 安装依赖
- ``ensure_project_venv``: 一键 ensure + install（EI-M1B.1/.2）

设计要点:
- venv 用当前解释器创建（``sys.executable -m venv``），保证 worker 与
  平台同 Python 版本（EI-M1B.1 要求 python3.12）。
- 依赖清单变化触发重装（EI-M1B.4）: 通过 requirements hash 文件判断。
- 无清单时跳过安装（EI-M1B.2），不报错。
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("engine.project_venv")

# 项目 venv 根目录（相对 OSH_HOME）
VENVS_REL = Path(".osh") / "venvs"


def _osh_home(project_dir: str | Path) -> Path:
    """项目根目录（OSH_HOME env 优先，回退 project_dir）。"""
    return Path(os.environ.get("OSH_HOME", str(project_dir))).resolve()


def resolve_venv_dir(project_dir: str | Path) -> Path:
    """计算项目 venv 目录（不创建）。

    ``<OSH_HOME>/.osh/venvs/<project_name>/``，project_name 取项目目录 basename
    （EI-M1B.1 路径规则）。
    """
    project_dir = Path(project_dir).resolve()
    return _osh_home(project_dir) / VENVS_REL / project_dir.name


def _requirements_paths(project_dir: Path) -> list[Path]:
    """候选依赖清单：requirements.txt 优先，其次 pyproject.toml。"""
    candidates = [
        project_dir / "requirements.txt",
        project_dir / "pyproject.toml",
        project_dir / "setup.py",
    ]
    return [p for p in candidates if p.exists()]


def _deps_signature(project_dir: Path) -> str:
    """依赖清单内容 hash（EI-M1B.4: 变化触发重装）。"""
    h = hashlib.sha256()
    for p in _requirements_paths(project_dir):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _sig_file(venv_dir: Path) -> Path:
    return venv_dir / ".osh-deps-sig"


def ensure_venv(project_dir: str | Path, python: str | None = None) -> Path:
    """确保项目 venv 存在（幂等），返回 venv 目录。

    EI-M1B.1: 首次调用创建 venv（python3.12）；已存在则复用（EI-M1B.4）。
    """
    venv_dir = resolve_venv_dir(project_dir)
    if venv_dir.exists() and (venv_dir / "bin" / "python").exists():
        return venv_dir

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    interpreter = python or sys.executable
    log.info("Creating project venv at %s (python=%s)", venv_dir, interpreter)
    proc = subprocess.run(
        [interpreter, "-m", "venv", str(venv_dir)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to create venv at {venv_dir}: {proc.stderr[-500:]}"
        )
    return venv_dir


def install_dependencies(project_dir: str | Path, venv_dir: str | Path,
                         timeout_s: int = 600) -> bool:
    """按依赖清单安装到项目 venv（EI-M1B.2/.4）。

    返回 True 表示执行了安装；无清单/无变化返回 False（跳过）。
    """
    project_dir = Path(project_dir).resolve()
    venv_dir = Path(venv_dir)
    reqs = _requirements_paths(project_dir)
    if not reqs:
        return False  # 无清单：跳过（EI-M1B.2）

    # 依赖未变化则不重装（EI-M1B.4 复用）
    sig = _deps_signature(project_dir)
    if _sig_file(venv_dir).exists() and _sig_file(venv_dir).read_text() == sig:
        return False

    pip = venv_dir / "bin" / "pip"
    if not pip.exists():
        raise RuntimeError(f"venv pip not found at {pip}")

    for req in reqs:
        if req.name == "requirements.txt":
            cmd = [str(pip), "install", "-r", str(req)]
        else:
            # pyproject.toml / setup.py: 安装项目自身（可编辑）
            cmd = [str(pip), "install", "-e", str(project_dir)]
        log.info("Installing deps via %s", " ".join(cmd))
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Dependency install failed ({req.name}): {proc.stderr[-500:]}"
            )

    _sig_file(venv_dir).write_text(sig)
    return True


def ensure_project_venv(project_dir: str | Path,
                        install: bool = True) -> Path:
    """一键 ensure + install（EI-M1B 主入口）。

    返回 venv 目录（python 解释器位于 ``<venv>/bin/python``）。
    """
    project_dir = Path(project_dir).resolve()
    venv_dir = ensure_venv(project_dir)
    if install:
        install_dependencies(project_dir, venv_dir)
    return venv_dir
