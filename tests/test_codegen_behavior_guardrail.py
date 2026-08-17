#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for codegen-deploy 行为护栏 (2026-08-13).

覆盖:
- 部署后测试回归 → 自动回滚 src/ 至部署前基线
- 无回归 → 部署保留
- run_c_test_suite 可复用 (ctest runner 检测)
- OSH_BEHAVIOR_GUARD=0 关闭护栏
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers.execution import step_codegen_deploy
from yuleosh.pipeline.step_handlers.test_c_unit import run_c_test_suite

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") and shutil.which("cmake") and shutil.which("ctest")),
    reason="need gcc + cmake + ctest",
)


def _make_cmake_project(tmp_path) -> Path:
    """Minimal CMake C project at tmp_path root: app.c with 2 functions.

    项目直接建在 tmp_path (session.project_dir = OSH_HOME = tmp_path),
    保证 codegen-deploy 的 gen_dir 定位 (project_dir/artifacts/...) 匹配。
    """
    proj = tmp_path
    (proj / "src").mkdir(parents=True)
    (proj / "tests").mkdir(parents=True)
    (proj / "src" / "app.c").write_text(
        "int add(int a, int b) { return a + b; }\n"
        "int sub(int a, int b) { return a - b; }\n",
        encoding="utf-8",
    )
    (proj / "tests" / "test_app.c").write_text(
        '#include "app.h"\n'
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int fails = 0;\n"
        "    if (add(2, 3) != 5) { printf(\"FAIL add\\n\"); fails++; }\n"
        "    if (sub(5, 3) != 2) { printf(\"FAIL sub\\n\"); fails++; }\n"
        "    printf(\"%d failures\\n\", fails);\n"
        "    return fails;\n"
        "}\n",
        encoding="utf-8",
    )
    (proj / "src" / "app.h").write_text(
        "#ifndef APP_H\n#define APP_H\nint add(int a, int b);\n"
        "int sub(int a, int b);\n#endif\n",
        encoding="utf-8",
    )
    (proj / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(test C)\n"
        "enable_testing()\n"
        "add_library(app STATIC src/app.c)\n"
        "target_include_directories(app PUBLIC src)\n"
        "add_executable(test_app tests/test_app.c)\n"
        "target_link_libraries(test_app app)\n"
        "add_test(NAME app_tests COMMAND test_app)\n",
        encoding="utf-8",
    )
    return proj


def _configure(proj: Path):
    build = proj / "build"
    build.mkdir(exist_ok=True)
    subprocess.run(["cmake", "-S", str(proj), "-B", str(build)],
                   capture_output=True, text=True, timeout=120, check=True)


def _session(tmp_path, name="deploy-test"):
    spec = tmp_path / "spec.md"
    spec.write_text("SHALL: keep behavior\n")
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(name=name, spec_path=str(spec))


def _gen_tree(proj: Path, name: str, app_c: str) -> Path:
    """Build a codegen artifact tree under proj/artifacts/generated-code/name.

    结构: <gen>/src/app.c (deploy 用 rel = relative_to(gen_dir) → src/app.c)。
    """
    gen = proj / "artifacts" / "generated-code" / name
    src_gen = gen / "src"
    src_gen.mkdir(parents=True)
    (src_gen / "app.c").write_text(app_c, encoding="utf-8")
    (src_gen / "app.h").write_text(
        "#ifndef APP_H\n#define APP_H\nint add(int a, int b);\n"
        "int sub(int a, int b);\n#endif\n",
        encoding="utf-8",
    )
    (gen / "codegen-report.md").write_text(
        f"# Code Generation Report\n\n> Status: ✅ verified\n", encoding="utf-8",
    )
    return gen


class TestRunCTestSuite:
    def test_runs_ctest_and_reports_counts(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        result = run_c_test_suite(proj)
        assert result["runner"] == "ctest"
        assert result["status"] == "passed"
        assert result["failed"] == 0
        assert result["passed"] == 1  # 1 test registered

    def test_stale_cmakelists_triggers_reconfigure(self, tmp_path, monkeypatch):
        """CMakeLists.txt 比 CMakeCache.txt 新 → 自动重新 configure。

        2026-08-17 (window-anti-pinch r20p): cmake-build-coverage 混入 ARM
        objcopy/linker 产物正是 CMakeLists 变更后未 reconfigure 导致 —
        增量构建沿用旧配置, ctest 跑旧/损坏产物假失败。正常 c-unit-test
        步骤也必须检测该场景, 不能只依赖 force_rebuild 手动删目录。
        """
        proj = _make_cmake_project(tmp_path)
        _configure(proj)

        # 模拟 CMakeLists 变更: 更新其 mtime 到未来
        cmake_lists = proj / "CMakeLists.txt"
        future = 2_000_000_000  # 远大于当前 epoch
        os.utime(cmake_lists, (future, future))

        # 记录 configure 调用 (cmake -S ... -B ...)
        real_run = subprocess.run
        configure_calls = []

        def spy(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and len(cmd) >= 3 \
                    and cmd[0] == "cmake" and cmd[1] == "-S":
                configure_calls.append(cmd)
            return real_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", spy)

        result = run_c_test_suite(proj)

        assert result["runner"] == "ctest"
        assert result["status"] == "passed"
        assert result["failed"] == 0
        # CMakeLists 过期 → 步骤内自动重新 configure (不删目录, 保留增量)
        assert len(configure_calls) == 1
        assert configure_calls[0][1] == "-S"


class TestBehaviorGuardrail:
    def test_no_regression_keeps_deployment(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-ok")
        # 生成的 app.c 行为正确 (add/sub 都实现)
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a - b; }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        guard = report["behavior_guardrail"]
        assert guard["enabled"] is True
        assert guard["verdict"] == "passed"
        assert guard["rolled_back"] is False
        # 部署的代码保留
        assert "a + b" in (proj / "src" / "app.c").read_text()

    def test_regression_rolls_back(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-regress")
        # 生成的 app.c 行为回归: sub 实现错误 (返回 a+b)
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a + b; }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed_behavior_regression"
        guard = report["behavior_guardrail"]
        assert guard["verdict"] == "regression_rolled_back"
        assert guard["rolled_back"] is True
        assert guard["baseline"]["failed"] == 0
        assert guard["after"]["failed"] > 0
        # 回滚: src/app.c 恢复为部署前基线 (sub 正确)
        assert "a - b" in (proj / "src" / "app.c").read_text()

    def test_compile_failure_rolls_back(self, tmp_path):
        """编译失败 (ctest-build-failed) 也是回归 — 基线通过后部署代码编译失败
        必须回滚 (e2e 抓到的判定盲区, 2026-08-13)。"""
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-compilefail")
        # 生成的 app.c 编译失败 (调用未声明函数) — 比测试失败更严重
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return undefined_fn(a); }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed_behavior_regression"
        guard = report["behavior_guardrail"]
        assert guard["verdict"] == "regression_rolled_back"
        assert guard["rolled_back"] is True
        assert guard["after"]["runner"] == "ctest-build-failed"
        # 回滚: src/app.c 恢复基线
        assert "a - b" in (proj / "src" / "app.c").read_text()

    def test_guard_disabled_env(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-noguard")
        _gen_tree(proj, session.name,
                  "int add(int a, int b) { return a + b; }\n"
                  "int sub(int a, int b) { return a + b; }\n")  # 回归但护栏关
        with mock.patch.dict(os.environ, {"OSH_BEHAVIOR_GUARD": "0"}):
            out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        assert report["behavior_guardrail"]["enabled"] is False
        assert report["behavior_guardrail"]["verdict"] == "not_verified"
        # 未回滚 — 回归代码保留 (护栏关闭是显式选择)
        assert "a + b" in (proj / "src" / "app.c").read_text()

    def test_new_file_added_no_regression(self, tmp_path):
        proj = _make_cmake_project(tmp_path)
        _configure(proj)
        session = _session(tmp_path, "deploy-newfile")
        # 生成代码新增 mul (原 src 无此函数) — 不影响既有测试
        gen = _gen_tree(proj, session.name,
                        "int add(int a, int b) { return a + b; }\n"
                        "int sub(int a, int b) { return a - b; }\n"
                        "int mul(int a, int b) { return a * b; }\n")
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"
        assert report["behavior_guardrail"]["verdict"] == "passed"
        assert "mul" in (proj / "src" / "app.c").read_text()
