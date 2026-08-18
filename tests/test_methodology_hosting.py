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
    # OpenSpec 规范骨架
    assert (tmp_path / ".osh" / "specs" / "README.md").exists()
    assert (tmp_path / ".osh" / "specs" / "example" / "spec.md").exists()


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


# ── B 部分: standalone 引擎 ──

DIST_GATE = Path(__file__).resolve().parent.parent / "dist" / "methodology-gate.py"


def _run_standalone(project_dir: Path) -> subprocess.CompletedProcess:
    import os

    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, str(DIST_GATE), str(project_dir)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return proc


def test_standalone_exists_and_executable():
    """B2: dist/methodology-gate.py 存在、可执行、零第三方依赖。"""
    assert DIST_GATE.exists()
    content = DIST_GATE.read_text(encoding="utf-8")
    assert "#!/usr/bin/env python3" in content
    # 零第三方依赖：import 只允许标准库
    import ast

    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("yuleosh"), f"standalone imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("yuleosh"), f"standalone imports {node.module}"


def test_standalone_regenerated_from_source(tmp_path):
    """B1: 生成器再跑一次，产物应与提交版一致（单一实现无漂移）。"""
    import importlib.util

    builder_path = Path(__file__).resolve().parent.parent / "scripts" / "build-methodology-gate-standalone.py"
    spec = importlib.util.spec_from_file_location("build_gate_builder", builder_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    current = DIST_GATE.read_text(encoding="utf-8")
    rebuilt = mod._build()
    assert rebuilt == current, "dist/methodology-gate.py 过期 — 请重跑 scripts/build-methodology-gate-standalone.py"


def test_standalone_passes_mounted_project(tmp_path):
    """B2: standalone 在挂载+spec 项目 → exit 0。"""
    cmd_methodology_init(str(tmp_path))
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec v1.0.0\n\n## 9. 决策记录（Grilling/对齐沉淀）\n\n- **决策（X-1）**: 采用 A 方案。\n",
        encoding="utf-8",
    )
    proc = _run_standalone(tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_standalone_hard_fails_without_spec(tmp_path):
    """B2: standalone 在缺 spec 项目 → exit 1。"""
    cmd_methodology_init(str(tmp_path))
    proc = _run_standalone(tmp_path)
    assert proc.returncode == 1


def test_standalone_skips_non_methodology_project(tmp_path):
    """B2: standalone 在非方法论项目 → skip exit 0。"""
    (tmp_path / "readme.md").write_text("hello", encoding="utf-8")
    proc = _run_standalone(tmp_path)
    assert proc.returncode == 0
    assert "跳过" in proc.stdout


def test_standalone_json_matches_yuleosh_check(tmp_path):
    """B3: standalone --json 与 yuleosh methodology check --json 逐 stage 一致。"""
    import json
    import os

    cmd_methodology_init(str(tmp_path))
    (tmp_path / ".osh" / "specs" / "v1.0.0").mkdir(parents=True)
    (tmp_path / ".osh" / "specs" / "v1.0.0" / "spec.md").write_text(
        "# Spec v1.0.0\n\n## 9. 决策记录\n\n- **决策（X-1）**: 采用 A 方案。\n",
        encoding="utf-8",
    )
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "review.md").write_text(
        "# Review\n\n## Standards\n- ok\n\n## Spec\n- ok\n", encoding="utf-8"
    )

    # standalone
    p1 = subprocess.run(
        [sys.executable, str(DIST_GATE), str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert p1.returncode == 0
    d1 = json.loads(p1.stdout)

    # yuleosh check
    src = str(Path(__file__).resolve().parent.parent / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    p2 = subprocess.run(
        [sys.executable, "-m", "yuleosh._entry", "methodology", "check", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
        timeout=60,
    )
    assert p2.returncode == 0, p2.stderr
    d2 = json.loads(p2.stdout)

    assert d1["passed"] == d2["passed"]
    s1 = {(s["name"].replace("methodology-", ""), s["status"]) for s in d1["stages"]}
    s2 = {(s["name"].replace("methodology-", ""), s["status"]) for s in d2["stages"]}
    assert s1 == s2
