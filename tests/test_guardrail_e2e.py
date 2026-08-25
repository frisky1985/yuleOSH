"""行为护栏体系端到端测试 (2026-08-13, 从 wiper-control e2e 验证沉淀).

在自建的 mini C 项目上跑完整链路, 覆盖:
  E2E-1: codegen 部署行为回归 → 护栏自动回滚 + 报告一致
  E2E-2: 门禁联动回滚 — 部署良好代码 → 注入回归 → c-unit-test 失败 →
         回滚 → 复跑通过 → 保持回滚 + deploy 报告更新
  E2E-3: 门禁联动 undo — 回滚后基线也失败 → 恢复部署 (gate_failed_independent)
  E2E-4: 编译失败也是回归 (e2e 抓到的判定盲区)

与 test_guardrail_system.py 的区别: 这里用真实 CTestRunner 跑完整
「部署 → 门禁 → 回滚 → 复跑」链路, 不是 FakeRunner 模拟。
"""

# @tests src/yuleosh/pipeline/guardrail.py

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.deploy_state import has_deployed_code, load_deploy_report
from yuleosh.pipeline.guardrail import (
    CCTestRunner,
    TestResult,
    maybe_rollback_on_gate_failure,
)
from yuleosh.pipeline.session import PipelineSession
from yuleosh.pipeline.step_handlers.execution import step_codegen_deploy

pytestmark = pytest.mark.skipif(
    not (shutil.which("gcc") and shutil.which("cmake") and shutil.which("ctest")),
    reason="need gcc + cmake + ctest",
)


GOOD_CTRL_C = """\
#include "wiper_control.h"
#include "hal_pwm.h"

void wiper_control_init(void) {
    /* 正常实现: 初始化后使能 PWM */
    HAL_PWM_Init();
    HAL_PWM_Enable(0);
}
"""

# 行为回归: 初始化后不 Enable PWM (编译通过, 测试断言 Enable 会失败)
REGRESS_CTRL_C = """\
#include "wiper_control.h"
#include "hal_pwm.h"

void wiper_control_init(void) {
    /* BUG: 忘记 HAL_PWM_Enable — 行为回归 */
    HAL_PWM_Init();
}
"""

# 编译失败: 调用未声明函数 (比测试失败更严重)
COMPILE_FAIL_C = """\
#include "wiper_control.h"
#include "hal_pwm.h"

void wiper_control_init(void) {
    undefined_function_xyz();
}
"""


def _make_project(tmp_path) -> Path:
    """Mini wiper-control 风格 C 项目: 2 个模块 + 2 个测试。"""
    proj = tmp_path
    (proj / "src" / "app" / "include").mkdir(parents=True)
    (proj / "src" / "app" / "src").mkdir(parents=True)
    (proj / "src" / "hal" / "include").mkdir(parents=True)
    (proj / "src" / "hal" / "src").mkdir(parents=True)
    (proj / "tests").mkdir(parents=True)

    (proj / "src" / "app" / "include" / "wiper_control.h").write_text(
        "#ifndef WIPER_CONTROL_H\n#define WIPER_CONTROL_H\n"
        "void wiper_control_init(void);\n#endif\n",
        encoding="utf-8",
    )
    (proj / "src" / "app" / "src" / "wiper_control.c").write_text(
        GOOD_CTRL_C, encoding="utf-8",
    )
    (proj / "src" / "hal" / "include" / "hal_pwm.h").write_text(
        "#ifndef HAL_PWM_H\n#define HAL_PWM_H\n"
        "void HAL_PWM_Init(void);\n"
        "void HAL_PWM_Enable(int ch);\n"
        "void HAL_PWM_Disable(int ch);\n"
        "int HAL_PWM_IsEnabled(int ch);\n#endif\n",
        encoding="utf-8",
    )
    (proj / "src" / "hal" / "src" / "hal_pwm.c").write_text(
        "static int g_enabled = 0;\n"
        "void HAL_PWM_Init(void) { g_enabled = 0; }\n"
        "void HAL_PWM_Enable(int ch) { (void)ch; g_enabled = 1; }\n"
        "void HAL_PWM_Disable(int ch) { (void)ch; g_enabled = 0; }\n"
        "int HAL_PWM_IsEnabled(int ch) { (void)ch; return g_enabled; }\n",
        encoding="utf-8",
    )
    (proj / "tests" / "test_wiper_control.c").write_text(
        '#include "wiper_control.h"\n'
        '#include "hal_pwm.h"\n'
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int fails = 0;\n"
        "    wiper_control_init();\n"
        "    if (!HAL_PWM_IsEnabled(0)) { printf(\"FAIL: PWM not enabled\\n\"); fails++; }\n"
        "    printf(\"%d failures\\n\", fails);\n"
        "    return fails;\n"
        "}\n",
        encoding="utf-8",
    )
    (proj / "tests" / "test_hal.c").write_text(
        '#include "hal_pwm.h"\n'
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int fails = 0;\n"
        "    HAL_PWM_Init();\n"
        "    HAL_PWM_Enable(1);\n"
        "    if (!HAL_PWM_IsEnabled(1)) { printf(\"FAIL: hal enable\\n\"); fails++; }\n"
        "    HAL_PWM_Disable(1);\n"
        "    if (HAL_PWM_IsEnabled(1)) { printf(\"FAIL: hal disable\\n\"); fails++; }\n"
        "    printf(\"%d failures\\n\", fails);\n"
        "    return fails;\n"
        "}\n",
        encoding="utf-8",
    )
    (proj / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(wiper_test C)\n"
        "enable_testing()\n"
        "include_directories(\n"
        "    ${CMAKE_SOURCE_DIR}/src/app/include\n"
        "    ${CMAKE_SOURCE_DIR}/src/hal/include\n"
        ")\n"
        "add_library(wiper_app STATIC src/app/src/wiper_control.c)\n"
        "add_library(wiper_hal STATIC src/hal/src/hal_pwm.c)\n"
        "add_executable(test_wiper_control tests/test_wiper_control.c)\n"
        "target_link_libraries(test_wiper_control wiper_app wiper_hal)\n"
        "add_test(NAME wiper_control_tests COMMAND test_wiper_control)\n"
        "add_executable(test_hal tests/test_hal.c)\n"
        "target_link_libraries(test_hal wiper_hal)\n"
        "add_test(NAME hal_tests COMMAND test_hal)\n",
        encoding="utf-8",
    )
    return proj


def _session(tmp_path, name: str) -> PipelineSession:
    spec = tmp_path / "spec.md"
    spec.write_text("SHALL: wiper control works\n")
    with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
        return PipelineSession(name=name, spec_path=str(spec))


def _gen_tree(proj: Path, name: str, wiper_c: str) -> Path:
    """构造 codegen 产物树: 完整 src 结构 + 指定的 wiper_control.c 版本。"""
    gen = proj / "artifacts" / "generated-code" / name
    if gen.exists():
        shutil.rmtree(gen)
    shutil.copytree(proj / "src", gen / "src")
    (gen / "src" / "app" / "src" / "wiper_control.c").write_text(
        wiper_c, encoding="utf-8",
    )
    (gen / "codegen-report.md").write_text(
        "# Code Generation Report\n\n> Status: ✅ verified\n", encoding="utf-8",
    )
    return gen


def _reset_src(proj: Path):
    """把 src 恢复为部署前基线 (重新写入 good 版)。"""
    (proj / "src" / "app" / "src" / "wiper_control.c").write_text(
        GOOD_CTRL_C, encoding="utf-8",
    )


def _cleanup(proj: Path):
    for d in [proj / ".yuleosh", proj / "artifacts", proj / "build", proj / ".osh"]:
        shutil.rmtree(d, ignore_errors=True)
    # 预 configure: 护栏的 run_c_test_suite 才能走 ctest 而非 gcc-compile-check
    # (gcc fallback 会把两个含 main() 的 test 文件一起编 → duplicate main →
    # 基线就红 → 护栏无法判定回归)
    subprocess.run(
        ["cmake", "-S", str(proj), "-B", str(proj / "build")],
        capture_output=True, text=True, timeout=120, check=True,
    )


class TestGuardrailE2E:
    def test_e2e1_behavior_regression_rolls_back(self, tmp_path):
        proj = _make_project(tmp_path)
        _cleanup(proj)
        session = _session(tmp_path, "e2e-regress")
        _gen_tree(proj, session.name, REGRESS_CTRL_C)  # 行为回归
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())

        assert report["status"] == "deployed_behavior_regression"
        assert report["deployed"] == []
        guard = report["behavior_guardrail"]
        assert guard["verdict"] == "regression_rolled_back"
        assert guard["baseline"]["status"] == "passed"
        assert guard["after"]["failed"] > 0
        assert has_deployed_code(proj) is False
        # src 恢复基线 (good 版)
        src_text = (proj / "src" / "app" / "src" / "wiper_control.c").read_text()
        assert "HAL_PWM_Enable(0)" in src_text
        assert "BUG" not in src_text
        # 备份落盘可查
        assert report.get("guardrail_backup")

    def test_e2e2_gate_linkage_rolls_back(self, tmp_path):
        proj = _make_project(tmp_path)
        _cleanup(proj)
        session = _session(tmp_path, "e2e-gate")
        _gen_tree(proj, session.name, GOOD_CTRL_C)
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"

        # 注入回归 → 门禁失败 → 联动回滚 → 复跑通过
        (proj / "src" / "app" / "src" / "wiper_control.c").write_text(
            REGRESS_CTRL_C, encoding="utf-8",
        )
        gate_result = TestResult(runner="ctest", status="failed", failed=1)
        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=CCTestRunner(),
        )
        assert linkage.get("action") == "rolled_back"
        assert linkage["rerun"].status == "passed"
        # src 回滚到基线
        src_text = (proj / "src" / "app" / "src" / "wiper_control.c").read_text()
        assert "HAL_PWM_Enable(0)" in src_text
        # deploy 报告更新
        report = load_deploy_report(proj)
        assert report is not None
        assert report["status"] == "deployed_behavior_regression"
        assert report["deployed"] == []

    def test_e2e3_gate_linkage_undo(self, tmp_path):
        """回滚后基线仍失败 → 非部署问题 → undo 恢复部署。"""
        proj = _make_project(tmp_path)
        _cleanup(proj)
        session = _session(tmp_path, "e2e-gate-undo")
        _gen_tree(proj, session.name, GOOD_CTRL_C)
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())
        assert report["status"] == "deployed"

        # 注入回归 + 复跑也失败 (模拟非部署问题: 环境坏了)
        (proj / "src" / "app" / "src" / "wiper_control.c").write_text(
            REGRESS_CTRL_C, encoding="utf-8",
        )
        gate_result = TestResult(runner="ctest", status="failed", failed=1)

        class AlwaysFail:
            name = "fake-fail"

            def run(self, project_dir, force_rebuild=False):
                return TestResult(runner="ctest", status="failed", failed=2)

        linkage = maybe_rollback_on_gate_failure(
            session, "c-unit-test", gate_result, runner=AlwaysFail(),
        )
        assert linkage.get("action") == "gate_failed_independent"
        # src 恢复部署版 (good 版 — 部署时就是 good)
        src_text = (proj / "src" / "app" / "src" / "wiper_control.c").read_text()
        assert "HAL_PWM_Enable(0)" in src_text
        # deploy 报告不动
        report = load_deploy_report(proj)
        assert report is not None
        assert report["status"] == "deployed"

    def test_e2e4_compile_failure_is_regression(self, tmp_path):
        """编译失败 (ctest-build-failed) 也是回归 — 必须回滚。"""
        proj = _make_project(tmp_path)
        _cleanup(proj)
        session = _session(tmp_path, "e2e-compilefail")
        _gen_tree(proj, session.name, COMPILE_FAIL_C)
        out = step_codegen_deploy(session)
        report = json.loads(Path(out).read_text())

        assert report["status"] == "deployed_behavior_regression"
        guard = report["behavior_guardrail"]
        assert guard["verdict"] == "regression_rolled_back"
        assert guard["after"]["runner"] == "ctest-build-failed"
        # src 恢复基线
        src_text = (proj / "src" / "app" / "src" / "wiper_control.c").read_text()
        assert "HAL_PWM_Enable(0)" in src_text
        assert "undefined_function_xyz" not in src_text
