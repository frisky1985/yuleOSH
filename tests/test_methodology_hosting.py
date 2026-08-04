#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for L3 方法论宿主平台化 — yuleosh methodology init/check CLI.

验证:
- init 在任意项目生成 .yuleosh/agents/ 四件套 + CONTEXT.md + ci-config 片段
- init 幂等（二次运行不覆盖已有文件，除非 --force）
- 模板渲染 {{PROJECT_NAME}} 占位符
- check 复用 methodology_gate：挂载后项目全绿 exit 0
- check 在缺 spec 项目 hard fail exit 1
- check 在非方法论项目跳过 exit 0
- check --json 输出结构化
"""

import subprocess
import sys
from pathlib import Path

import pytest

from yuleosh.cli.commands.methodology import (
    _render,
    _template_dir,
    cmd_methodology_check,
    cmd_methodology_init,
)
from yuleosh.ci.stages.methodology_gate import run_methodology_gate


class FakeCI:
    def __init__(self):
        self.stages = []

    def add_stage(self, name, status, msg=""):
        self.stages.append((name, status, msg))


# ── 模板层 ──


def test_template_dir_resolves():
    d = Path(_template_dir())
    assert d.is_dir()
    assert (d / "template.yaml").exists()
    assert (d / ".yuleosh" / "agents" / "METHODOLOGY.md").exists()
    assert (d / ".yuleosh" / "agents" / "RULES.md").exists()
    assert (d / ".yuleosh" / "agents" / "HOOKS.md").exists()
    assert (d / ".yuleosh" / "agents" / "AGENTS.md").exists()
    assert (d / "CONTEXT.md").exists()
    assert (d / "ci-config.methodology.yaml").exists()


def test_template_yaml_discoverable():
    """methodology 模板必须能被模板发现机制列出（template list）。"""
    from yuleosh.templates import list_templates

    names = [t["name"] for t in list_templates()]
    assert "methodology" in names


def test_render_placeholders():
    out = _render("hello {{PROJECT_NAME}} desc={{PROJECT_DESC}}", "my-proj", "desc")
    assert out == "hello my-proj desc=desc"


# ── init ──


def test_init_creates_skeleton(tmp_path):
    cmd_methodology_init(str(tmp_path))
    assert (tmp_path / ".yuleosh" / "agents" / "METHODOLOGY.md").exists()
    assert (tmp_path / ".yuleosh" / "agents" / "RULES.md").exists()
    assert (tmp_path / ".yuleosh" / "agents" / "HOOKS.md").exists()
    assert (tmp_path / ".yuleosh" / "agents" / "AGENTS.md").exists()
    assert (tmp_path / "CONTEXT.md").exists()
    assert (tmp_path / ".yuleosh" / "ci-config.yaml").exists()


def test_init_renders_project_name(tmp_path):
    cmd_methodology_init(str(tmp_path))
    ctx = (tmp_path / "CONTEXT.md").read_text(encoding="utf-8")
    assert tmp_path.name in ctx


def test_init_idempotent_no_overwrite(tmp_path):
    cmd_methodology_init(str(tmp_path))
    (tmp_path / "CONTEXT.md").write_text("# 自定义 CONTEXT — 用户已编辑\n", encoding="utf-8")
    cmd_methodology_init(str(tmp_path))
    # 二次 init 不覆盖用户已编辑内容
    assert (tmp_path / "CONTEXT.md").read_text(encoding="utf-8").startswith("# 自定义")


def test_init_force_overwrites(tmp_path):
    cmd_methodology_init(str(tmp_path))
    (tmp_path / "CONTEXT.md").write_text("# 旧内容\n", encoding="utf-8")
    cmd_methodology_init(str(tmp_path), force=True)
    assert tmp_path.name in (tmp_path / "CONTEXT.md").read_text(encoding="utf-8")


def test_init_missing_dir_exits(tmp_path, capsys):
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as e:
        cmd_methodology_init(str(missing))
    assert e.value.code == 1


# ── check ──


def test_check_passes_on_mounted_project(tmp_path):
    """挂载后 + 有 spec 决策记录 → 门禁 PASS exit 0。"""
    cmd_methodology_init(str(tmp_path))
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec v1.0.0\n\n## 9. 决策记录（Grilling/对齐沉淀）\n\n- **决策（X-1）**: 采用 A 方案。\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as e:
        cmd_methodology_check(str(tmp_path))
    assert e.value.code == 0


def test_check_hard_fail_without_spec(tmp_path):
    """挂载了但无 spec → §1 hard fail exit 1。"""
    cmd_methodology_init(str(tmp_path))
    with pytest.raises(SystemExit) as e:
        cmd_methodology_check(str(tmp_path))
    assert e.value.code == 1


def test_check_skips_non_methodology_project(tmp_path):
    """无 spec/CONTEXT/.yuleosh 的普通项目 → 跳过 exit 0。"""
    (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cmd_methodology_check(str(tmp_path))
    assert e.value.code == 0


def test_check_json_output(tmp_path):
    """check --json 输出结构化 JSON（用 subprocess 验证真实 CLI 行为）。"""
    cmd_methodology_init(str(tmp_path))
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec\n\n## 9. 决策记录\n\n- 决策（X-1）: A。\n", encoding="utf-8"
    )
    import os

    env = dict(os.environ)
    src = str(Path(__file__).resolve().parent.parent / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "yuleosh._entry", "methodology", "check", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0, proc.stderr
    import json

    payload = json.loads(proc.stdout)
    assert payload["passed"] is True
    assert any(s["status"] == "passed" for s in payload["stages"])


# ── 与 L2 gate 集成 ──


def test_mounted_project_recognized_as_methodology_project(tmp_path):
    """init 生成的骨架必须被 _is_methodology_project 识别为方法论项目。"""
    from yuleosh.ci.stages.methodology_gate import _is_methodology_project

    cmd_methodology_init(str(tmp_path))
    assert _is_methodology_project(str(tmp_path)) is True


def test_cli_entry_registered():
    """yuleosh --help 必须列出 methodology 子命令。"""
    from yuleosh.cli.main import _build_parser

    parser = _build_parser()
    # 直接检查子命令集合
    subparsers = None
    for action in parser._actions:
        if action.dest == "command":
            subparsers = action.choices
    assert subparsers is not None
    assert "methodology" in subparsers
