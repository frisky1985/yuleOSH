#!/usr/bin/env python3
"""
yuleOSH demo uart — 端到端UART通信示例

快速创建、编译、验证 STM32F4 ↔ ESP32 UART bridge 项目。
3分钟内跑通全流程。

Usage:
    yuleosh demo uart [--dir=<path>] [--build]

Options:
    --dir=<path>    目标目录（默认: ./demos/uart）
    --build         创建后自动编译验证（host模式）
    --skip-cmake    跳过CMake检查（仅复制模板）
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "demos" / "uart"
OSH_HOME = os.environ.get(
    "OSH_HOME",
    Path(__file__).resolve().parent.parent.parent.parent,
)

TEMPLATE_FILES = [
    "README.md",
    "CMakeLists.txt",
    "demo_host.c",
    "stm32/usart_driver.h",
    "stm32/usart_driver.c",
    "stm32/platform_stm32.c",
    "esp32/uart_bridge.h",
    "esp32/uart_bridge.c",
    "esp32/platform_esp32.c",
    "cmake/toolchain_stm32.cmake",
    "cmake/toolchain_esp32.cmake",
]


def _green(text): return f"\033[92m{text}\033[0m"
def _yellow(text): return f"\033[93m{text}\033[0m"
def _cyan(text): return f"\033[96m{text}\033[0m"
def _bold(text): return f"\033[1m{text}\033[0m"
def _red(text): return f"\033[91m{text}\033[0m"


def _check_tool(name):
    """Check if a tool is available on PATH."""
    found = shutil.which(name) is not None
    status = _green("✅") if found else _yellow("⚠️")
    print(f"  {status} {name}")
    return found


def _copy_template(target_dir: Path):
    """Copy template files to the target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in TEMPLATE_FILES:
        src = TEMPLATE_DIR / rel_path
        dst = target_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(str(src), str(dst))
        else:
            print(f"  {_yellow('⚠')}  Template file missing: {src}")

    # Create .gitkeep for empty dirs
    for sub in ["stm32", "esp32", "cmake"]:
        (target_dir / sub / ".gitkeep").touch(exist_ok=True)

    return target_dir


def _build_host(target_dir: Path) -> bool:
    """Run host-mode cmake + make in the target directory."""
    build_dir = target_dir / "build_host"
    build_dir.mkdir(exist_ok=True)

    print(f"\n  {_cyan('ℹ')}  Running cmake (host mode)...")
    cmake_result = subprocess.run(
        ["cmake", "-DTARGET=host", ".."],
        cwd=str(build_dir),
        capture_output=True, text=True,
    )
    if cmake_result.returncode != 0:
        print(f"  {_red('❌')}  CMake failed:\n{cmake_result.stderr}")
        return False

    print(f"  {_green('✅')}  CMake configured")

    print(f"  {_cyan('ℹ')}  Running make...")
    make_result = subprocess.run(
        ["make", "-j$(sysctl -n hw.logicalcpu 2>/dev/null || echo 4)"],
        cwd=str(build_dir),
        capture_output=True, text=True, shell=True,
    )
    if make_result.returncode != 0:
        print(f"  {_red('❌')}  Build failed:\n{make_result.stderr}")
        return False

    print(f"  {_green('✅')}  Build succeeded")

    # Run the demo
    demo_exe = build_dir / "uart_demo_host"
    if demo_exe.exists():
        print(f"\n  {_bold('━━━ Running UART Demo ━━━')}\n")
        result = subprocess.run([str(demo_exe)], cwd=str(build_dir))
        print(f"\n  {_green('✅')}  Demo exited with code {result.returncode}")
        return result.returncode == 0

    print(f"  {_yellow('⚠')}  Demo binary not found at {demo_exe}")
    return False


def cmd_demo_uart(target_dir: str = None, do_build: bool = False, skip_cmake: bool = False):
    """Create and optionally build the UART demo project."""
    # ── Banner ──────────────────────────────────────────────────────────────
    print()
    print("  " + "─" * 55)
    print("    🔱  y u l e O S H   D E M O   U A R T")
    print("    STM32F4 ↔ ESP32 UART Communication Demo")
    print("  " + "─" * 55)
    print()

    # ── Resolve target directory ────────────────────────────────────────────
    if target_dir:
        target = Path(target_dir).resolve()
    else:
        target = Path.cwd() / "demos" / "uart"

    print(f"  {_cyan('ℹ')}  Template source: {TEMPLATE_DIR}")
    print(f"  {_cyan('ℹ')}  Target:          {target}")
    print()

    # ── Step 1: Environment check ────────────────────────────────────────────
    print("  " + _bold("Step 1/4: Environment Check"))
    print()
    has_gcc = _check_tool("gcc")
    has_cmake = _check_tool("cmake")
    has_arm_gcc = _check_tool("arm-none-eabi-gcc")
    print()

    if skip_cmake:
        has_cmake = False  # skip cmake even if present

    if do_build and not has_gcc:
        print(f"  {_red('❌')}  gcc is required for --build")
        return 1

    # ── Step 2: Copy template ───────────────────────────────────────────────
    print("  " + _bold("Step 2/4: Creating Demo Project"))
    print()
    _copy_template(target)
    print(f"  {_green('✅')}  Demo project created at: {target}")
    print(f"  {_cyan('ℹ')}  Files: {len(TEMPLATE_FILES)} template files copied")
    print()

    # ── Step 3: Build (optional) ────────────────────────────────────────────
    if do_build and has_cmake:
        print("  " + _bold("Step 3/4: Compiling & Running Demo"))
        print()
        build_ok = _build_host(target)
        if not build_ok:
            print(f"\n  {_yellow('⚠')}  Build had issues — see above for details.")
        print()

    # ── Step 4: Summary ─────────────────────────────────────────────────────
    print("  " + _bold("Step 4/4: Summary"))
    print()
    print(f"  {_green('✅')}  UART Demo Ready!")
    print()
    print(f"  📁  Project:  {target}")
    print(f"  🔧  Build:    cd {target} && mkdir build_host && cd build_host &&")
    print(f"               cmake -DTARGET=host .. && make && ./uart_demo_host")
    print()
    if has_arm_gcc:
        print(f"  🔧  STM32:    cd {target} && mkdir build_stm32 && cd build_stm32 &&")
        print(f"               cmake -DTARGET=stm32f4 -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_stm32.cmake .. && make")
    else:
        print(f"  {_yellow('⚠')}  STM32:    Install arm-none-eabi-gcc for cross-compilation")
    print()

    print("  " + "─" * 55)
    print(f"    {_green('🎉 Demo complete!')} See {target / 'README.md'} for details.")
    print("  " + "─" * 55)
    print()

    return 0
