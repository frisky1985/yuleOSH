"""codegen cflags 测试 — 2026-08-18 r21f 复盘修复。

根因: verify_c 裸 gcc -fsyntax-only -Wall 漏掉 -Wextra 独有警告
(unused parameter) → 生成代码通过语法预检却在项目真实 -Werror 构建
失败 (window_modes.c), 4 轮 repair 全盲。修复: verify_c/compile_verify
支持 cflags 参数 + discover_project_cflags 从 CMakeLists 自动发现。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from yuleosh.codegen.compilers import (
    compile_verify,
    discover_project_cflags,
    verify_c,
)

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") or shutil.which("cc")),
    reason="no C compiler available",
)

# 含未用参数的文件 — 裸 -Wall 不报, -Wextra 报, -Werror 变错误
UNUSED_PARAM_SRC = (
    "#include <stdint.h>\n"
    "int check_pinch(uint32_t positionPulses, uint32_t timeMs, "
    "uint32_t lastCheckTimeMs)\n"
    "{\n"
    "    (void)timeMs;\n"
    "    return positionPulses > 100 ? 1 : 0;\n"
    "}\n"
)

CLEAN_SRC = (
    "int add(int a, int b)\n"
    "{\n"
    "    return a + b;\n"
    "}\n"
)


@pytest.fixture
def unused_param_file(tmp_path: Path) -> Path:
    f = tmp_path / "window_modes.c"
    f.write_text(UNUSED_PARAM_SRC)
    return f


@pytest.fixture
def clean_file(tmp_path: Path) -> Path:
    f = tmp_path / "clean.c"
    f.write_text(CLEAN_SRC)
    return f


class TestVerifyCCFlags:
    def test_default_legacy_wall_misses_unused_param(self, unused_param_file):
        """r21f 根因: 默认 (-Wall) 放行未用参数 — 旧行为保留。"""
        r = verify_c([unused_param_file])
        assert r["ok"] is True, r.get("output")
        assert "-Wextra" not in r["command"]

    def test_wextra_werror_catches_unused_param(self, unused_param_file):
        """项目真实 flags (-Wall -Wextra -Werror) 下未用参数是错误。"""
        r = verify_c([unused_param_file],
                     cflags=["-Wall", "-Wextra", "-Werror"])
        assert r["ok"] is False
        assert "unused parameter" in r["output"]
        assert "-Werror" in r["command"]

    def test_clean_code_passes_with_strict_flags(self, clean_file):
        r = verify_c([clean_file],
                     cflags=["-Wall", "-Wextra", "-Werror"])
        assert r["ok"] is True, r.get("output")

    def test_compile_verify_passes_cflags(self, unused_param_file):
        r = compile_verify([unused_param_file], language="c",
                           cflags=["-Wall", "-Wextra", "-Werror"])
        assert r["ok"] is False
        assert "unused parameter" in r["output"]

    def test_compile_verify_default_still_passes(self, unused_param_file):
        r = compile_verify([unused_param_file], language="c")
        assert r["ok"] is True, r.get("output")


class TestDiscoverProjectCflags:
    def _write_cmake(self, root: Path, content: str):
        root.mkdir(parents=True, exist_ok=True)
        (root / "CMakeLists.txt").write_text(content)

    def test_parses_cmake_c_flags(self, tmp_path):
        """window-anti-pinch 同款: CMAKE_C_FLAGS 声明 -Wall -Wextra -Werror。"""
        self._write_cmake(tmp_path, (
            "cmake_minimum_required(VERSION 3.20)\n"
            'set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -Wall -Wextra -Werror")\n'
            "add_executable(window_app src/main.c)\n"
        ))
        flags = discover_project_cflags(tmp_path)
        assert "-Wall" in flags
        assert "-Wextra" in flags
        assert "-Werror" in flags

    def test_skips_arm_cross_flags(self, tmp_path):
        """只提取 -W*, 不提取 ARM 交叉编译 flags (-mcpu/-mthumb/...)。"""
        self._write_cmake(tmp_path, (
            "set(CMAKE_C_FLAGS \"${CMAKE_C_FLAGS} -Wall -Wextra -Werror\")\n"
            "set(CMAKE_C_FLAGS_ARM \"-mcpu=cortex-m33 -mthumb -O2 "
            "-ffreestanding -nostdlib -Wall -Wextra\")\n"
            "add_compile_options(--coverage -O0 -g)\n"
        ))
        flags = discover_project_cflags(tmp_path)
        assert flags == ["-Wall", "-Wextra", "-Werror"]
        assert all(not f.startswith(("-mcpu", "-mthumb", "-ffree",
                                     "-nostdlib", "--coverage")) for f in flags)

    def test_add_compile_options_scanned(self, tmp_path):
        self._write_cmake(tmp_path, (
            "add_compile_options(-Wno-unused-parameter -Werror)\n"
        ))
        flags = discover_project_cflags(tmp_path)
        assert "-Wno-unused-parameter" in flags
        assert "-Werror" in flags

    def test_missing_cmakelists_returns_empty(self, tmp_path):
        assert discover_project_cflags(tmp_path) == []

    def test_no_warning_flags_returns_empty(self, tmp_path):
        self._write_cmake(tmp_path, (
            "cmake_minimum_required(VERSION 3.20)\n"
            "add_executable(app main.c)\n"
        ))
        assert discover_project_cflags(tmp_path) == []
