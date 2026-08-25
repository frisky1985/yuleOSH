
# @tests src/yuleosh/pipeline/orchestrator.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""C++ 泛化 (A1 dogfood, 2026-08-21): 项目语言检测.

修复前: CMakeLists.txt 存在即返回 'c' → C++ 项目 codegen 生成 C 代码假绿.
修复后: 统计项目自有源码 (排除 third_party/build) 判断 c/cpp/python.
"""

from pathlib import Path

from yuleosh.pipeline.step_handlers.execution import _detect_project_language


def _make_project(tmp_path, cmake=True, c_files=(), cpp_files=(), py=False,
                  third_party_c=()):
    root = Path(tmp_path)
    if cmake:
        (root / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.16)\n")
    if py:
        (root / "pyproject.toml").write_text("[project]\n")
    src = root / "src"
    src.mkdir(exist_ok=True)
    for name in c_files:
        (src / name).write_text("int f(void){return 0;}\n")
    for name in cpp_files:
        (src / name).write_text("namespace m { int f(){return 0;} }\n")
    if third_party_c:
        tp = root / "third_party" / "freertos"
        tp.mkdir(parents=True, exist_ok=True)
        for name in third_party_c:
            (tp / name).write_text("int g(void){return 0;}\n")
    return root


class TestDetectProjectLanguage:
    def test_cmake_pure_cpp(self, tmp_path):
        """GIVEN CMake + 纯 .cpp WHEN detect THEN 'cpp'."""
        root = _make_project(tmp_path, cpp_files=("a.cpp", "b.cpp"))
        assert _detect_project_language(root) == "cpp"

    def test_cmake_pure_c(self, tmp_path):
        """GIVEN CMake + 纯 .c WHEN detect THEN 'c' (原行为不回归)."""
        root = _make_project(tmp_path, c_files=("a.c", "b.c"))
        assert _detect_project_language(root) == "c"

    def test_cmake_mixed_cpp_dominant(self, tmp_path):
        """GIVEN CMake + 混合源且 .cpp 为主 WHEN detect THEN 'cpp'."""
        root = _make_project(tmp_path, c_files=("a.c",), cpp_files=("a.cpp", "b.cpp"))
        assert _detect_project_language(root) == "cpp"

    def test_cmake_third_party_c_not_dominant(self, tmp_path):
        """GIVEN C++ 项目 + third_party 大量 .c WHEN detect THEN 'cpp'.

        A1 dogfood 实测回归: FreeRTOS (third_party) 18 个 .c 曾淹没
        项目真实语言导致误判 'c'。
        """
        root = _make_project(
            tmp_path,
            cpp_files=("motor.cpp", "hal.cpp"),
            third_party_c=(f"t{i}.c" for i in range(18)),
        )
        assert _detect_project_language(root) == "cpp"

    def test_python_project(self, tmp_path):
        """GIVEN pyproject.toml WHEN detect THEN 'python'."""
        root = _make_project(tmp_path, cmake=False, py=True)
        assert _detect_project_language(root) == "python"

    def test_unknown_project(self, tmp_path):
        """GIVEN 无特征项目 WHEN detect THEN None."""
        root = _make_project(tmp_path, cmake=False)
        assert _detect_project_language(root) is None
