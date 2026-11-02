# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for _auto_generate_cmakelists — 覆盖率门禁的 CMake 自动生成把守.

2026-11-02: 该函数新增时 ``target_link_libraries(... projectlib m)`` 与
``add_library(project_lib ...)`` target 名不一致 (少下划线) — CMake
configure 阶段必报 "target projectlib was never created", 覆盖率门禁
在 codegen 产物上 100% 坏掉。本文件锁死:

* 生成内容中链接的 target 名与 add_library 定义的 target 名一致;
* 无 ``projectlib`` (坏名) 残留;
* 项目名不硬编码 dogfood 项目 (headlight_controller);
* 已有 CMakeLists.txt 不覆盖; 无 src/ 不生成;
* 本机有 cmake 时真跑 configure 做 L2 独立验证。
"""

import re
import shutil
from pathlib import Path

import pytest

from yuleosh.pipeline.step_handlers.c_coverage_gate import (
    _auto_generate_cmakelists,
)


def _make_project(tmp_path: Path) -> Path:
    """src/ + tests/test_foo.c + 自带 Unity 的最小 C 工程."""
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "app.c").write_text("int app_main(void) { return 0; }\n", encoding="utf-8")
    unity = tmp_path / "tests" / "unity" / "src"
    unity.mkdir(parents=True, exist_ok=True)
    (unity / "unity.h").write_text("#pragma once\n", encoding="utf-8")
    (unity / "unity.c").write_text("int unity_dummy;\n", encoding="utf-8")
    tests = tmp_path / "tests"
    (tests / "test_app.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    return tmp_path


def test_generated_cmake_links_defined_target(tmp_path, monkeypatch):
    """GIVEN 无 CMakeLists 的工程 WHEN 自动生成 THEN target 名一致、无坏名残留."""
    # 隔离开发机 Unity fallback 路径 — 只允许工程自带 Unity 生效。
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    proj = _make_project(tmp_path / "proj")
    assert _auto_generate_cmakelists(proj) is True

    content = (proj / "CMakeLists.txt").read_text(encoding="utf-8")

    # add_library 定义 project_lib
    assert "add_library(project_lib STATIC" in content
    # 每个测试 target 链接的必须是 project_lib (带下划线)
    for m in re.finditer(r"target_link_libraries\((\S+) (\S+) m\)", content):
        assert m.group(2) == "project_lib", (
            f"target {m.group(1)} 链接了未定义的 target: {m.group(2)}"
        )
    # 坏名 (无下划线) 不得出现
    assert "projectlib" not in content
    # dogfood 项目名不得硬编码
    assert "headlight_controller" not in content
    assert "project(yuleosh_coverage C)" in content
    # 测试 target 与 add_test 齐全
    assert 'add_executable(test_app "' in content
    assert "add_test(NAME test_app COMMAND test_app)" in content


def test_existing_cmakelists_not_overwritten(tmp_path):
    """GIVEN 已有 CMakeLists.txt WHEN 调用 THEN 返回 True 且内容不变."""
    proj = tmp_path / "proj"
    src = proj / "src"
    src.mkdir(parents=True)
    (src / "app.c").write_text("int x;\n", encoding="utf-8")
    original = "cmake_minimum_required(VERSION 3.16)\nproject(mine C)\n"
    (proj / "CMakeLists.txt").write_text(original, encoding="utf-8")

    assert _auto_generate_cmakelists(proj) is True
    assert (proj / "CMakeLists.txt").read_text(encoding="utf-8") == original


def test_no_src_dir_returns_false(tmp_path):
    """GIVEN 无 src/ 目录 WHEN 调用 THEN 返回 False 且不写文件."""
    proj = tmp_path / "proj"
    proj.mkdir()

    assert _auto_generate_cmakelists(proj) is False
    assert not (proj / "CMakeLists.txt").exists()


@pytest.mark.skipif(
    shutil.which("cmake") is None or shutil.which("gcc") is None,
    reason="cmake/gcc not available",
)
def test_generated_cmake_actually_configures(tmp_path, monkeypatch):
    """L2 独立验证: 生成内容真过 cmake configure **+ build** (不靠读字符串猜).

    注意: CMake 对 target_link_libraries 里的非 target 名按 ``-l<name>``
    透传给链接器 — configure 不报错, 坏名只在 **build/链接** 阶段爆炸
    (ld: library not found for -lprojectlib)。只测 configure 会漏放,
    所以必须 build。
    """
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    proj = _make_project(tmp_path / "proj")
    assert _auto_generate_cmakelists(proj) is True

    import subprocess

    build = proj / "cmake-build-coverage"
    cr = subprocess.run(
        ["cmake", "-S", str(proj), "-B", str(build), "-DENABLE_COVERAGE=ON"],
        capture_output=True, text=True, timeout=120,
    )
    assert cr.returncode == 0, f"cmake configure failed:\n{cr.stdout}\n{cr.stderr}"

    br = subprocess.run(
        ["cmake", "--build", str(build)],
        capture_output=True, text=True, timeout=180,
    )
    assert br.returncode == 0, (
        f"cmake build failed (未定义 target 名只会在链接阶段爆炸):\n"
        f"{br.stdout}\n{br.stderr}"
    )
