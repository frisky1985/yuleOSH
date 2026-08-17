#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for step_claude_arch source tree discovery (r21b 复盘根因 #7).

2026-08-17 (window-anti-pinch r21b): 架构文档误判"文件: 0 个（源码树
未填充）"—— step_claude_arch 的扩展名白名单不含 .c/.h, C 项目源文件
全部漏扫 → 架构步骤基于空源码树立论。本测试钉死 C/C++ 文件被计入。
"""

import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers.execution import step_claude_arch


def _session(tmp_path, name="arch-test"):
    spec = tmp_path / "spec.md"
    spec.write_text("SHALL: test\n")
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(name=name, spec_path=str(spec))


def _make_c_project(tmp_path) -> None:
    """C 项目: src/app/src/*.c + src/hal/include/*.h (r21b window-anti-pinch 形态)."""
    for rel in ("src/app/src", "src/hal/include"):
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/app/src/window_control.c").write_text(
        "int window_control_process(void){return 0;}\n")
    (tmp_path / "src/app/src/window_position.c").write_text(
        "int window_position_get(void){return 0;}\n")
    (tmp_path / "src/hal/include/hal_motor.h").write_text(
        "#ifndef HAL_MOTOR_H\n#define HAL_MOTOR_H\nvoid hal_motor_init(void);\n#endif\n")


def test_arch_discovers_c_sources(tmp_path, monkeypatch):
    """C 项目源码树必须被架构步骤发现 (r21b 曾漏扫 .c/.h → 文件: 0 个)."""
    _make_c_project(tmp_path)

    captured = {}

    def fake_llm(system, user, **kw):
        captured["user"] = user
        captured["system"] = system
        return {"content": "# Architecture\n\nok\n"}

    session = _session(tmp_path)
    session.llm_client = fake_llm
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        out = step_claude_arch(session)

    assert out and Path(out).exists()
    # prompt 中源码树统计必须含 C 文件
    user = captured["user"]
    assert "3 files" in user, f"prompt 应统计 3 个 C 源文件, got: {user[:400]}"
    assert "window_control.c" in user
    assert "hal_motor.h" in user
    # tech stack 应含 C
    assert "C" in user


def test_arch_python_still_works(tmp_path, monkeypatch):
    """Python 项目不受影响 (回归保护)."""
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/main.py").write_text("def main():\n    pass\n")

    captured = {}

    def fake_llm(system, user, **kw):
        captured["user"] = user
        return {"content": "# Architecture\n\nok\n"}

    session = _session(tmp_path)
    session.llm_client = fake_llm
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        out = step_claude_arch(session)

    assert out and Path(out).exists()
    assert "1 files" in captured["user"]
    assert "main.py" in captured["user"]
