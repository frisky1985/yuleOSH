"""Phase 7 coverage — D1 域: demo_wow.py 的 create_demo_project / _write_demo_test。

目标（src/yuleosh/api/demo_wow.py L216-428）:
  - create_demo_project: 目录清理（已存在 rmtree / 不存在直建）、DEMO_SPECS
    命中与缺省回退（未知 example 落到 brake-light）、标准目录树与全部模板
    文件（spec / 测试 / C 源码 / 头文件 / ci-config.yaml）的真实落盘校验。
  - _write_demo_test: brake-light 与 wiper-control 两分支的测试文件内容。

红线遵守: 零网络 / 子进程依赖；时间依赖（datetime.now()）
用冻结时钟 mock；文件系统使用 pytest tmp_path 真实落盘。

注: 2026-08-11 src 已修复 _DEMO_SRC_TEMPLATE 的 ``{example.lower()}`` 非法方法
调用（见 src/yuleosh/api/demo_wow.py L246 根因注释）——本文件不再需要测试侧
模板补丁，并新增 test_create_project_src_include_uses_real_header_name 回归断言。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

from datetime import datetime
from pathlib import Path

import pytest

from yuleosh.api.demo_wow import _write_demo_test, create_demo_project

# ---------------------------------------------------------------------------
# 共享 fixture / 工具
# ---------------------------------------------------------------------------


class _FrozenDateTime(datetime):
    """datetime 替身: now() 返回固定值，spec 时间戳确定性。"""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 10, 12, 0, 0)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    """冻结模块内 datetime.now()，避免 spec 时间戳抖动。"""
    monkeypatch.setattr("yuleosh.api.demo_wow.datetime", _FrozenDateTime)


FROZEN_TS = "2026-08-10 12:00:00"


STD_SUBDIRS = [
    ".osh",
    ".osh/evidence",
    ".osh/ci",
    ".osh/reports",
    ".yuleosh",
    "docs",
    "src",
    "include",
    "tests",
    "specs",
]


def _assert_standard_tree(project: Path):
    for sub in STD_SUBDIRS:
        assert (project / sub).is_dir(), f"missing dir: {sub}"


# ---------------------------------------------------------------------------
# create_demo_project
# ---------------------------------------------------------------------------


def test_create_brake_light_project(tmp_path):
    """brake-light: DEMO_SPECS 命中 + project_dir 不存在（跳过 rmtree）。"""
    project = create_demo_project("brake-light", str(tmp_path))

    assert isinstance(project, Path)
    assert project == (tmp_path / "demo-brake-light").resolve()
    _assert_standard_tree(project)

    spec = (project / "docs" / "spec.md").read_text(encoding="utf-8")
    assert "Brake Light Control Unit — Demo Spec" in spec
    assert FROZEN_TS in spec

    test_src = (project / "tests" / "test_brake_light.py").read_text(encoding="utf-8")
    assert "class TestBrakeLightActivation" in test_src
    assert "REQ-BRK-001" in test_src
    assert "REQ-BRK-005" in test_src

    src = (project / "src" / "brake_light.c").read_text(encoding="utf-8")
    assert '"brake_light.h"' in src
    assert "void BrakeLight_init(void)" in src

    hdr = (project / "include" / "brake_light.h").read_text(encoding="utf-8")
    assert "DEMO_BRAKE_LIGHT_H" in hdr

    ci = (project / ".yuleosh" / "ci-config.yaml").read_text(encoding="utf-8")
    assert "layers: [1, 2, 3]" in ci
    assert "threshold_line: 85.0" in ci


def test_create_wiper_control_project(tmp_path):
    """wiper-control: _write_demo_test else 分支 + wiper 模板落盘。"""
    project = create_demo_project("wiper-control", str(tmp_path))

    assert project == (tmp_path / "demo-wiper-control").resolve()
    _assert_standard_tree(project)

    spec = (project / "docs" / "spec.md").read_text(encoding="utf-8")
    assert "Wiper Control Unit — Demo Spec" in spec
    assert FROZEN_TS in spec

    test_src = (project / "tests" / "test_wiper_control.py").read_text(encoding="utf-8")
    assert "class TestIntermittentMode" in test_src
    assert "REQ-WPR-001" in test_src
    assert "REQ-WPR-005" in test_src

    src = (project / "src" / "wiper_control.c").read_text(encoding="utf-8")
    assert '"wiper_control.h"' in src
    assert "void WiperControl_init(void)" in src

    hdr = (project / "include" / "wiper_control.h").read_text(encoding="utf-8")
    assert "DEMO_WIPER_CONTROL_H" in hdr


def test_create_project_unknown_example_falls_back(tmp_path):
    """未知 example: DEMO_SPECS.get 缺省回退 brake-light + demo-<name> 目录。"""
    project = create_demo_project("hover-car", str(tmp_path))

    assert project == (tmp_path / "demo-hover-car").resolve()
    _assert_standard_tree(project)

    # spec 回退到 brake-light 模板
    spec = (project / "docs" / "spec.md").read_text(encoding="utf-8")
    assert "Brake Light Control Unit — Demo Spec" in spec

    # _write_demo_test 走 else（wiper）分支
    test_src = (project / "tests" / "test_hover_car.py").read_text(encoding="utf-8")
    assert "class TestIntermittentMode" in test_src

    src = (project / "src" / "hover_car.c").read_text(encoding="utf-8")
    assert "void HoverCar_init(void)" in src


def test_create_project_recreates_existing_dir(tmp_path):
    """project_dir 已存在: 走 rmtree 清理分支后重建。"""
    work = tmp_path / "w"
    work.mkdir()
    stale = work / "demo-brake-light"
    stale.mkdir(parents=True)
    (stale / "stale.txt").write_text("stale", encoding="utf-8")
    (stale / ".osh").mkdir()

    project = create_demo_project("brake-light", str(work))

    assert not (project / "stale.txt").exists()
    assert (project / ".osh" / "evidence").is_dir()
    assert (project / "docs" / "spec.md").is_file()


# ---------------------------------------------------------------------------
# _write_demo_test
# ---------------------------------------------------------------------------


def test_write_demo_test_brake_light(tmp_path):
    """brake-light 分支: 5 个需求的 brake 测试类。"""
    p = tmp_path / "test_brake_light.py"
    _write_demo_test(p, "brake-light")

    content = p.read_text(encoding="utf-8")
    assert "class TestBrakeLightActivation" in content
    assert "Covers: REQ-BRK-001" in content
    assert "test_uart_report" in content
    assert "import time" in content


def test_write_demo_test_wiper(tmp_path):
    """wiper-control 分支: 5 个需求的 wiper 测试类。"""
    p = tmp_path / "test_wiper_control.py"
    _write_demo_test(p, "wiper-control")

    content = p.read_text(encoding="utf-8")
    assert "class TestIntermittentMode" in content
    assert "Covers: REQ-WPR-001" in content
    assert "test_power_cut_on_stall" in content


def test_create_project_src_include_uses_real_header_name(tmp_path):
    """回归 (2026-08-11): _DEMO_SRC_TEMPLATE 曾用 {example.lower()} 非法方法调用，
    str.format 抛 AttributeError，create_demo_project 必然崩溃。修复后生成的
    C 源码 #include 必须指向真实落盘的头文件名（example.replace('-','_') + .h）。"""
    project = create_demo_project("brake-light", str(tmp_path))

    src = (project / "src" / "brake_light.c").read_text(encoding="utf-8")
    hdr = project / "include" / "brake_light.h"

    assert hdr.is_file()
    assert '#include "brake_light.h"' in src
    assert "{example" not in src  # 模板占位符必须全部被格式化
    assert "{header_name" not in src

