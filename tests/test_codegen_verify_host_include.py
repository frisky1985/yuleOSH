"""Tests for codegen verify_c host-project include scan (2026-08-12).

根因: 生成的 app 代码依赖宿主项目 HAL 头文件 (src/hal/include),
但验证命令只含 gen 目录的 -I → hal_motor.h file not found →
6 次真实 run codegen 全失败。修复: verify_c 支持 project_root,
扫描 <project_root>/src/**/include 加入 -I。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from yuleosh.codegen.compilers import verify_c

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") or shutil.which("cc")),
    reason="no C compiler available",
)


def test_verify_c_with_project_root_finds_host_hal(tmp_path):
    """生成的 app 代码 include 宿主 HAL 头 → project_root 提供时编译通过。"""
    # 宿主项目: src/hal/include/hal_motor.h
    proj = tmp_path / "proj"
    hal_inc = proj / "src" / "hal" / "include"
    hal_inc.mkdir(parents=True)
    (hal_inc / "hal_motor.h").write_text(
        "#ifndef HAL_MOTOR_H\n#define HAL_MOTOR_H\n"
        "typedef enum { HAL_MOTOR_DIRECTION_UP = 0, HAL_MOTOR_DIRECTION_DOWN } "
        "HalMotorDirection;\n"
        "void hal_motor_set_direction(HalMotorDirection d);\n"
        "#endif\n"
    )

    # 生成的 app 代码 (gen 目录不含 hal/): include 宿主 HAL
    gen = tmp_path / "gen"
    app_src = gen / "src" / "app" / "src"
    app_src.mkdir(parents=True)
    (app_src / "window_control.c").write_text(
        '#include "hal_motor.h"\n'
        "void run(void) { hal_motor_set_direction(HAL_MOTOR_DIRECTION_UP); }\n"
    )

    files = [app_src / "window_control.c"]

    # 旧行为 (无 project_root): 找不到 hal_motor.h → fail
    r_old = verify_c(files)
    assert r_old["ok"] is False

    # 新行为 (project_root): 扫描宿主 include → pass
    r_new = verify_c(files, project_root=proj)
    assert r_new["ok"] is True, r_new.get("errors")


def test_verify_c_project_root_reports_real_errors(tmp_path):
    """project_root 下错误应是真实代码错误 (不再是 include 缺失)。"""
    proj = tmp_path / "proj"
    hal_inc = proj / "src" / "hal" / "include"
    hal_inc.mkdir(parents=True)
    (hal_inc / "hal_motor.h").write_text(
        "#ifndef HAL_MOTOR_H\n#define HAL_MOTOR_H\n"
        "typedef enum { HAL_MOTOR_DIRECTION_UP = 0 } HalMotorDirection;\n"
        "void hal_motor_set_direction(HalMotorDirection d);\n"
        "#endif\n"
    )
    gen = tmp_path / "gen"
    app_src = gen / "src" / "app" / "src"
    app_src.mkdir(parents=True)
    (app_src / "bad.c").write_text(
        '#include "hal_motor.h"\n'
        "void run(void) { hal_motor_set_direction(HAL_MOTOR_DIR_STOP); }\n"
    )

    r = verify_c([app_src / "bad.c"], project_root=proj)
    assert r["ok"] is False
    # 错误是「未声明标识符」而非「文件找不到」
    assert "file not found" not in (r.get("errors") or "")
    assert "HAL_MOTOR_DIR_STOP" in (r.get("errors") or "")
