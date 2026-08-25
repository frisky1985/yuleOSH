#!/usr/bin/env python3

# @tests src/yuleosh/codegen/engine.py
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for codegen seed 增量开发 (方案 C, 2026-08-12).

覆盖:
- collect_seed_sources 收集项目现有 src (.c/.h) 作为基线
- build_codegen_prompt 注入 seed + 增量指令 (只输出修改文件)
- engine seed 同步: 复制 seed 到输出目录, LLM 只增量修改
- verify 验证整个输出目录 (seed 副本 + 修改) — 跨文件引用可捕获
- best-state 回滚: 越修越坏的轮次回滚到错误数最少的版本
- verify_python 只编译 .py (混合目录不误报)
"""

import os
import shutil
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.codegen import (
    CodegenEngine,
    GeneratedFile,
    build_codegen_prompt,
    verify_python,
)
from yuleosh.codegen.prompts import collect_seed_sources
from yuleosh.pipeline.session import PipelineSession

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") or shutil.which("cc")),
    reason="no C compiler available",
)


def _make_project(tmp_path) -> Path:
    """Build a mini host project with an existing HAL + app seed."""
    proj = tmp_path / "proj"
    hal_inc = proj / "src" / "hal" / "include"
    hal_src = proj / "src" / "hal" / "src"
    app_inc = proj / "src" / "app" / "include"
    app_src = proj / "src" / "app" / "src"
    for d in (hal_inc, hal_src, app_inc, app_src):
        d.mkdir(parents=True)
    (hal_inc / "hal_motor.h").write_text(
        "#ifndef HAL_MOTOR_H\n#define HAL_MOTOR_H\n"
        "typedef enum { HAL_MOTOR_DIRECTION_UP = 0, HAL_MOTOR_DIRECTION_DOWN } "
        "HalMotorDirection;\n"
        "void hal_motor_set_direction(HalMotorDirection d);\n"
        "#endif\n",
        encoding="utf-8",
    )
    (hal_src / "hal_motor.c").write_text(
        '#include "hal_motor.h"\n'
        "void hal_motor_set_direction(HalMotorDirection d) { (void)d; }\n",
        encoding="utf-8",
    )
    (app_inc / "window_control.h").write_text(
        "#ifndef WINDOW_CONTROL_H\n#define WINDOW_CONTROL_H\n"
        "typedef enum { WINDOW_CONTROL_IDLE = 0, WINDOW_CONTROL_MOVING } "
        "WindowControlState;\n"
        "void window_control_init(void);\n"
        "void window_control_step(void);\n"
        "#endif\n",
        encoding="utf-8",
    )
    (app_src / "window_control.c").write_text(
        '#include "window_control.h"\n'
        "#include \"hal_motor.h\"\n"
        "static WindowControlState s_state = WINDOW_CONTROL_IDLE;\n"
        "void window_control_init(void) { s_state = WINDOW_CONTROL_IDLE; }\n"
        "void window_control_step(void) {\n"
        "    if (s_state == WINDOW_CONTROL_MOVING) {\n"
        "        hal_motor_set_direction(HAL_MOTOR_DIRECTION_UP);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    return proj


def _session(tmp_path, name="seed-test"):
    spec = tmp_path / "spec.md"
    spec.write_text("SHALL: implement window control\n")
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(name=name, spec_path=str(spec),
                               development_mode="generate-code")


class TestCollectSeedSources:
    def test_collects_c_and_h_files(self, tmp_path):
        proj = _make_project(tmp_path)
        seed = collect_seed_sources(proj)
        assert "src/hal/include/hal_motor.h" in seed
        assert "src/hal/src/hal_motor.c" in seed
        assert "src/app/src/window_control.c" in seed

    def test_excludes_build_dirs(self, tmp_path):
        proj = _make_project(tmp_path)
        (proj / "src" / "build").mkdir(parents=True)
        (proj / "src" / "build" / "junk.h").write_text("int junk;\n")
        seed = collect_seed_sources(proj)
        assert "junk.h" not in seed

    def test_empty_when_no_src(self, tmp_path):
        assert collect_seed_sources(tmp_path) == ""


class TestPromptSeedInjection:
    def test_seed_block_and_incremental_instructions(self):
        _, user_p = build_codegen_prompt(
            "SPEC", "s.md", seed_sources="### src/a.c\n```c\nint a;\n```"
        )
        assert "项目现有代码基线 (seed)" in user_p
        assert "只输出你新增或修改的文件" in user_p
        assert "src/a.c" in user_p

    def test_no_seed_no_incremental_block(self):
        _, user_p = build_codegen_prompt("SPEC", "s.md")
        assert "项目现有代码基线" not in user_p

    def test_system_prompt_has_incremental_rule(self):
        sys_p, _ = build_codegen_prompt("SPEC", "s.md", seed_sources="seed")
        assert "Incrementally modify" in sys_p

    def test_context_content_injected(self):
        """CONTEXT.md 领域术语/语言约束注入 codegen prompt。

        Regression: 2026-08-14 headlamp dogfood — CONTEXT.md 未注入 → LLM
        不知道项目是 C 嵌入式 → 生成 Python 假绿。
        """
        _, user_p = build_codegen_prompt(
            "SPEC", "s.md",
            context_content="本项目是 C99 嵌入式固件。禁止生成 Python。",
        )
        assert "C99" in user_p
        assert "禁止生成 Python" in user_p

    def test_context_content_absent_by_default(self):
        _, user_p = build_codegen_prompt("SPEC", "s.md")
        assert "# Project Context" not in user_p


class TestEngineSeedSync:
    def test_seed_copied_to_output_dir(self, tmp_path):
        proj = _make_project(tmp_path)
        session = _session(tmp_path)
        engine = CodegenEngine(llm_client=lambda s, u, **k: {
            "content": "### FILE: src/app/src/window_control.c\n```c\n"
                       "// modified\n#include \"window_control.h\"\n"
                       "void window_control_init(void) {}\n"
                       "void window_control_step(void) {}\n```\n"},
            max_retries=0, seed_dir=proj, output_dir=tmp_path / "out")
        result = engine.generate(session, "sys", "user")
        out = Path(result.output_dir)
        # seed 基线文件被复制
        assert (out / "src" / "hal" / "include" / "hal_motor.h").exists()
        assert (out / "src" / "hal" / "src" / "hal_motor.c").exists()
        # 未修改文件保留 seed 内容
        assert "WINDOW_CONTROL_IDLE" in (out / "src" / "app" / "include" /
                                         "window_control.h").read_text()

    def test_verify_whole_tree_catches_cross_file_ref(self, tmp_path):
        """生成 app 代码 include seed HAL → 验证整个目录才编译通过。"""
        proj = _make_project(tmp_path)
        session = _session(tmp_path)

        def llm(system, user, **kw):
            # 只输出修改的 window_control.c — 依赖 seed 的 hal_motor.h
            return {"content": (
                "### FILE: src/app/src/window_control.c\n```c\n"
                "#include \"window_control.h\"\n"
                "#include \"hal_motor.h\"\n"
                "void window_control_init(void) {}\n"
                "void window_control_step(void) {\n"
                "    hal_motor_set_direction(HAL_MOTOR_DIRECTION_DOWN);\n"
                "}\n```\n")}

        engine = CodegenEngine(llm_client=llm, max_retries=0,
                               seed_dir=proj, output_dir=tmp_path / "out")
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified", result.last_errors

    def test_no_seed_keeps_legacy_behavior(self, tmp_path):
        """无 seed_dir: 输出目录只有 LLM 生成的文件, 行为不变。"""
        session = _session(tmp_path)

        def llm(system, user, **kw):
            return {"content": "### FILE: src/x.py\n```python\ndef f():\n    return 1\n```\n"}

        engine = CodegenEngine(llm_client=llm, max_retries=0,
                               output_dir=tmp_path / "out")
        result = engine.generate(session, "sys", "user")
        assert result.status == "verified"
        assert len(list(Path(result.output_dir).rglob("*.py"))) == 1


class TestBestStateRollback:
    def test_worse_round_rolls_back_to_best(self, tmp_path):
        """Round1 错误 1 个 → best; Round2 错误更多 → 回滚到 Round1 版本。"""
        proj = _make_project(tmp_path)
        session = _session(tmp_path)
        calls = {"n": 0}

        def llm(system, user, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                # round 1: 单文件, 一个错误 (引用不存在枚举)
                body = (
                    '#include "window_control.h"\n'
                    '#include "hal_motor.h"\n'
                    "void window_control_init(void) {}\n"
                    "void window_control_step(void) {\n"
                    "    hal_motor_set_direction(HAL_MOTOR_DIR_STOP);\n"  # 错误
                    "}\n"
                )
            else:
                # round 2: 越修越坏 — 括号不匹配 + 未声明
                body = (
                    '#include "window_control.h"\n'
                    '#include "hal_motor.h"\n'
                    "void window_control_init(void) {}\n"
                    "void window_control_step(void) {\n"
                    "    if (1 {  // 语法错误\n"
                    "        hal_motor_set_direction(UNKNOWN_X);\n"
                    "    }\n"
                )
            return {"content": (
                "### FILE: src/app/src/window_control.c\n```c\n"
                f"{body}\n```\n")}

        engine = CodegenEngine(llm_client=llm, max_retries=3,
                               seed_dir=proj, output_dir=tmp_path / "out")
        result = engine.generate(session, "sys", "user")
        assert result.status == "failed"
        # 最终磁盘上是最佳版本 (round 1): 有 HAL_MOTOR_DIR_STOP 而非坏括号
        final = (Path(result.output_dir) / "src" / "app" / "src" /
                 "window_control.c").read_text()
        assert "HAL_MOTOR_DIR_STOP" in final
        assert "if (1 {" not in final

    def test_repair_context_lists_disk_files(self, tmp_path):
        """repair context 提示磁盘已有文件 → 只输出修改文件。"""
        proj = _make_project(tmp_path)
        session = _session(tmp_path)
        prompts = []

        def llm(system, user, **kw):
            prompts.append(user)
            return {"content": (
                "### FILE: src/app/src/window_control.c\n```c\n"
                '#include "window_control.h"\n'
                "void window_control_init(void) {}\n"
                "void window_control_step(void) {}\n```\n")}

        engine = CodegenEngine(llm_client=llm, max_retries=3,
                               seed_dir=proj, output_dir=tmp_path / "out")
        engine.generate(session, "sys", "user")
        assert len(prompts) == 1  # round 1 verified, no repair
        # 直接调用 _format_repair_context 验证 disk hint
        ctx = CodegenEngine._format_repair_context(
            "error: boom",
            [GeneratedFile("src/app/src/window_control.c", "x", "c")],
            best_state={"src/hal/include/hal_motor.h": "/* h */",
                        "src/app/src/window_control.c": "/* c */"},
        )
        assert "当前磁盘上已有这些文件" in ctx
        assert "只重新输出你修改的文件" in ctx


class TestVerifyPythonMixedDir:
    def test_py_compile_ignores_non_py(self, tmp_path):
        """混合目录: .h 不应被 py_compile 编译。"""
        (tmp_path / "a.py").write_text("def f():\n    return 1\n")
        (tmp_path / "b.h").write_text("#ifndef B_H\n#define B_H\n#endif\n")
        result = verify_python([tmp_path / "a.py", tmp_path / "b.h"])
        assert result["ok"] is True
        assert "a.py" in result["command"]
        assert "b.h" not in result["command"]

    def test_py_compile_no_py_files_ok(self, tmp_path):
        (tmp_path / "b.h").write_text("#ifndef B_H\n#endif\n")
        result = verify_python([tmp_path / "b.h"])
        assert result["ok"] is True
