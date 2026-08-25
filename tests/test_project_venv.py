"""Tests for engine/project_venv.py — project venv isolation (EI-M1B)."""

# @tests src/yuleosh/project_detection.py

import os
import subprocess
import sys
from pathlib import Path

import pytest

from yuleosh.engine.project_venv import (
    ensure_venv,
    ensure_project_venv,
    install_dependencies,
    resolve_venv_dir,
)


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """临时项目目录（含 requirements.txt 或空）。

    OSH_HOME 隔离（2026-08-25）: resolve_venv_dir 以 OSH_HOME 优先（见
    engine/project_venv._osh_home）。全量随机序下 OSH_HOME 会被其他测试
    改写，导致 venv 路径指向共享目录、签名/安装断言互相干扰（实证:
    test_install_dependencies_* 全量失败、单独通过）。这里固定 OSH_HOME
    到本测试的 tmp_path，保证 venv 路径确定且互不共享。
    """
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    p = tmp_path / "my-project"
    p.mkdir()
    return p


def test_resolve_venv_dir(tmp_path):
    """GIVEN 项目目录 WHEN resolve THEN .osh/venvs/<name>。"""
    p = tmp_path / "proj-a"
    p.mkdir()
    venv = resolve_venv_dir(p)
    assert venv.name == "proj-a"
    assert venv.parent.name == "venvs"
    assert venv.parent.parent.name == ".osh"


def test_ensure_venv_creates(project_dir):
    """GIVEN 无 venv WHEN ensure THEN 创建且幂等。"""
    venv = ensure_venv(project_dir)
    assert (venv / "bin" / "python").exists()
    # 第二次调用复用（不报错）
    venv2 = ensure_venv(project_dir)
    assert venv == venv2


def test_ensure_venv_matches_system_python(project_dir):
    """GIVEN ensure THEN venv python 与当前解释器同版本。"""
    venv = ensure_venv(project_dir)
    out = subprocess.run(
        [str(venv / "bin" / "python"), "--version"],
        capture_output=True, text=True, check=True,
    )
    sys_ver = sys.version.split()[0]
    assert sys_ver in out.stdout


def test_install_dependencies_no_manifest(project_dir):
    """GIVEN 无依赖清单 WHEN install THEN 返回 False（跳过不报错）。"""
    assert install_dependencies(project_dir, project_dir / ".venv") is False


def test_install_dependencies_manifest(project_dir):
    """GIVEN requirements.txt WHEN install THEN 安装并签名。"""
    (project_dir / "requirements.txt").write_text("six==1.16.0\n")
    venv = ensure_venv(project_dir)
    installed = install_dependencies(project_dir, venv)
    assert installed is True
    # 依赖已可用
    out = subprocess.run(
        [str(venv / "bin" / "python"), "-c", "import six; print(six.__version__)"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "1.16.0"


def test_install_dependencies_unchanged_skips(project_dir):
    """GIVEN 依赖未变 WHEN install THEN 返回 False（复用不重装）。"""
    (project_dir / "requirements.txt").write_text("six==1.16.0\n")
    venv = ensure_venv(project_dir)
    assert install_dependencies(project_dir, venv) is True
    assert install_dependencies(project_dir, venv) is False  # 签名未变


def test_install_dependencies_changed_reinstalls(project_dir):
    """GIVEN 依赖变化 WHEN install THEN 重装（签名变化）。"""
    (project_dir / "requirements.txt").write_text("six==1.16.0\n")
    venv = ensure_venv(project_dir)
    assert install_dependencies(project_dir, venv) is True
    (project_dir / "requirements.txt").write_text("six==1.16.0\nrequests==2.31.0\n")
    assert install_dependencies(project_dir, venv) is True  # 签名变化触发


def test_ensure_project_venv_one_shot(project_dir):
    """GIVEN 完整项目 WHEN ensure_project_venv THEN venv 就绪。"""
    (project_dir / "requirements.txt").write_text("six==1.16.0\n")
    venv = ensure_project_venv(project_dir)
    assert (venv / "bin" / "python").exists()
    out = subprocess.run(
        [str(venv / "bin" / "python"), "-c", "import six"],
        capture_output=True, text=True, check=True,
    )
    assert out.returncode == 0
