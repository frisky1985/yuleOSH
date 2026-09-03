#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step SWE.5: 小克 — 接口/集成测试。

在 Self-Test 完成后按以下维度执行接口测试：
1. 模块间接口（API 调用链）
2. 数据流接口（输入→输出 完整性）
3. 外部依赖接口（LLM client, 存储系统等）
4. Spec 定义的 GIVEN/WHEN/THEN 场景级测试
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _parse_scenarios, _parse_spec
from yuleosh.pipeline.guardrail import TestResult

log = logging.getLogger("pipeline.step_handlers.test_integration")

__all__ = ["step_integration_test"]


@timed_step
def step_integration_test(session: PipelineSession) -> str:
    """Step: 小克 — 接口/集成测试。

    Runs integration tests across modules:
      - Prefers pytest with -m integration marker
      - Falls back to Go -tags=integration
      - Reports passed/failed counts and scenario coverage
    """
    try:
        print("  📋 [小克] 接口集成测试开始...")
        log.info("Running integration test step")

        # 2026-08-13 (e2e 修复): 用 session 解析的 project_dir, 不用环境变量 —
        # 与 codegen/test_c_unit 分支同源: 嵌套/测试调用时环境变量可能已变,
        # 退化到错误目录 → 门禁假失败。
        project_dir = Path(getattr(session, "project_dir", None)
                           or os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real review ──────────────────────────
        # In --mock runs the LLM emits placeholder code; scanning the real
        # project tree would produce false findings and block the demo.
        # Strict `is True` keeps MagicMock sessions honest.
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [小克] 接口集成测试跳过 — mock 模式")
            return write_mock_skip(
                session, "integration-test",
                "mock mode — no real code to review",
            )


        # 1. Read spec for scenario-level test cases
        spec_scenarios = _parse_scenarios(session.spec_path)
        spec_data = _parse_spec(session.spec_path)
        log.info(
            "Found %d GIVEN/WHEN/THEN scenarios in spec",
            len(spec_scenarios),
        )

        # 2. Run integration tests (skip unit tests, run e2e/integration)
        test_output = ""
        result_returncode = None
        test_runner = "none"

        # Try pytest with integration marker
        test_dir = project_dir / "tests"
        if (test_dir / "conftest.py").exists() or test_dir.exists():
            try:
                pytest_cmd = [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/",
                    "-q",
                    "-m",
                    "integration",
                    # 2026-09-03: 子项目(如 templates/gpio-led-chaser)本身没有
                    # pytest 配置, pytest 会沿 rootdir 向上发现仓库根的 pytest.ini,
                    # 继承其 addopts (--cov=src/yuleosh --cov-fail-under=5)。对纯
                    # C/CMake 子项目, pytest 收集不到 Python 测试 → 覆盖率 0% →
                    # --cov-fail-under 触发 rc=1, 把本应 skipped 的步骤误判 failed。
                    # 这里显式清空 addopts, 让覆盖率交给专门的 coverage 步骤处理,
                    # 本步骤只关心集成测试本身的通过/失败。
                    "-o",
                    "addopts=",
                ]
                # --timeout requires pytest-timeout; probe for it first so we
                # don't crash with "unrecognized arguments" on bare installs.
                probe = subprocess.run(
                    [sys.executable, "-m", "pytest", "--help"],
                    capture_output=True, text=True, timeout=30,
                )
                if "--timeout=" in (probe.stdout or "") or "--timeout=" in (probe.stderr or ""):
                    pytest_cmd.append("--timeout=120")
                result = subprocess.run(
                    pytest_cmd,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd=project_dir,
                )
                test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                result_returncode = result.returncode
                test_runner = "pytest-integration"
                log.info(
                    "pytest integration tests: returncode=%d, stdout_len=%d",
                    result.returncode,
                    len(result.stdout or ""),
                )
            except FileNotFoundError:
                log.info("pytest not found, trying Go integration tests")
            except subprocess.TimeoutExpired:
                test_output = "TIMEOUT: pytest integration tests exceeded 180s"
                test_runner = "pytest-integration-timeout"
                log.warning("pytest integration tests timed out")

        # Fallback: try C/CMake integration tests via ctest -L integration
        # (2026-08-15). C projects declare integration tests as ctest
        # entries with LABELS "integration"; `ctest -L integration` runs
        # exactly those. This only engages when pytest found nothing
        # (rc==5 / not found) so Python projects keep pytest semantics.
        if (test_runner in ("none", "pytest-integration")
                and result_returncode in (None, 5)):
            # 只保留含 CTestTestfile.cmake 的 build 目录参与; 没有 CTestTestfile
            # 的残留目录(如 coverage 步生成的 cmake-build-coverage)不参与。
            cmake_build_dirs = [
                d for d in (
                    list(project_dir.glob("build")) +
                    list(project_dir.glob("cmake-build*"))
                )
                if (d / "CTestTestfile.cmake").exists()
            ]
            # 2026-09-04 (gpio dogfood): C/CMake 子项目若还没有可跑 ctest 的
            # build 目录 (例如 c-unit-test 走了 gcc 编译兜底, 或只残留无
            # CTestTestfile 的 coverage 目录), integration-test 永远 skipped。
            # 这里在 CMakeLists.txt 存在时自动 cmake -S -B 配置一个干净的
            # build 目录, 使本步骤对纯 C/CMake 子项目也能真正执行
            # ctest -L integration (而非 skipped)。
            if not cmake_build_dirs and (project_dir / "CMakeLists.txt").exists():
                _cfg_dir = project_dir / "build"
                try:
                    cfg = subprocess.run(
                        ["cmake", "-S", str(project_dir), "-B", str(_cfg_dir)],
                        capture_output=True, text=True, timeout=180,
                    )
                    if cfg.returncode == 0 and (_cfg_dir / "CTestTestfile.cmake").exists():
                        cmake_build_dirs = [_cfg_dir]
                        log.info("Configured build dir %s for integration-test", _cfg_dir)
                    else:
                        log.warning(
                            "cmake configure failed for integration-test: %s",
                            (cfg.stderr or cfg.stdout)[-500:],
                        )
                except FileNotFoundError:
                    log.info("cmake not found — cannot configure build for integration-test")
                except subprocess.TimeoutExpired:
                    log.warning("cmake configure timed out for integration-test")
            for build_dir in cmake_build_dirs:
                ctest_cfg = build_dir / "CTestTestfile.cmake"
                if not ctest_cfg.exists():
                    continue
                try:
                    log.info("Rebuilding %s before ctest -L integration", build_dir)
                    build_result = subprocess.run(
                        ["cmake", "--build", str(build_dir), "-j4"],
                        capture_output=True, text=True,
                        timeout=180, cwd=build_dir,
                    )
                    if build_result.returncode != 0:
                        test_output = (build_result.stderr or build_result.stdout)[-1000:]
                        result_returncode = build_result.returncode
                        test_runner = "ctest-integration-build-failed"
                        passed, failed = 0, 0
                        break
                    result = subprocess.run(
                        ["ctest", "-L", "integration", "--output-on-failure"],
                        capture_output=True, text=True,
                        timeout=180, cwd=build_dir,
                    )
                    test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    result_returncode = result.returncode
                    test_runner = "ctest-integration"
                    passed, failed = _parse_test_counts(test_output, "ctest-integration")
                    log.info(
                        "ctest -L integration: returncode=%d, passed=%d, failed=%d",
                        result.returncode, passed, failed,
                    )
                    break
                except FileNotFoundError:
                    log.info("ctest not found")
                except subprocess.TimeoutExpired:
                    test_output = "TIMEOUT: ctest -L integration exceeded 180s"
                    test_runner = "ctest-integration-timeout"
                    log.warning("ctest -L integration timed out")
                    break

        # Fallback: try Go integration tests
        if test_runner == "none":
            go_mod = project_dir / "go.mod"
            if go_mod.exists():
                try:
                    result = subprocess.run(
                        ["go", "test", "-tags=integration", "./..."],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=project_dir,
                    )
                    test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    result_returncode = result.returncode
                    test_runner = "go-integration"
                    log.info(
                        "Go integration tests: returncode=%d",
                        result.returncode,
                    )
                except FileNotFoundError:
                    log.info("Go not installed; skipping Go integration tests")
                except subprocess.TimeoutExpired:
                    test_output = "TIMEOUT: Go integration tests exceeded 300s"
                    test_runner = "go-integration-timeout"
                    log.warning("Go integration tests timed out")

        # If no framework found, produce a lightweight surrogate
        if test_runner == "none":
            test_output = (
                "Integration test framework not available. "
                "No pytest -m integration or go test -tags=integration found."
            )
            log.warning("No integration test framework found")

        # 3. Parse test results for pass/fail counts
        passed, failed = _parse_test_counts(test_output, test_runner)

        # 4. Determine status
        # pytest exits 5 when NO tests matched (-m integration). For a
        # C/CMake project whose tests live in ctest (not pytest), this is
        # expected, not a failure — treat as skipped. Only a real test
        # failure (tests ran and failed) should block the pipeline.
        # ctest -L integration exits 8 when no test matches the label —
        # same semantics: C project without integration tests = skipped.
        if result_returncode == 5 and test_runner == "pytest-integration":
            status = "skipped"
        elif result_returncode == 8 and test_runner == "ctest-integration":
            status = "skipped"
        elif result_returncode is not None and result_returncode != 0:
            status = "failed"
        elif failed > 0:
            status = "failed"
        elif test_runner == "none":
            status = "unknown"
        else:
            status = "passed"

        # 5. Generate integration test report
        report = {
            "step": "integration-test",
            "agent": "小克",
            "session": session.name,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "spec_scenarios_total": len(spec_scenarios),
            "spec_scenarios": spec_scenarios,
            "test_runner": test_runner,
            "returncode": result_returncode,
            "output": test_output[:3000],
            "passed": passed,
            "failed": failed,
            "status": status,
        }

        # ── 门禁联动回滚 (2026-08-13, 方案 A) ─────────────────────
        # 只对真实失败 (status=failed) 联动; skipped/unknown 不动。
        if status == "failed":
            try:
                from yuleosh.pipeline.guardrail import (
                    IntegrationTestRunner,
                    maybe_rollback_on_gate_failure,
                )
                gate_result = TestResult(
                    runner=test_runner,
                    status=status,
                    passed=passed,
                    failed=failed,
                    returncode=result_returncode,
                    output=test_output[:3000],
                )
                linkage = maybe_rollback_on_gate_failure(
                    session, "integration-test", gate_result,
                    runner=IntegrationTestRunner(),
                )
                if linkage.get("action") == "rolled_back":
                    report["guardrail_linkage"] = {
                        "action": "rolled_back",
                        "detail": (
                            "deploy regression confirmed — src/ rolled back "
                            "to baseline, gate re-run passed"
                        ),
                        "rerun_failed": linkage["rerun"].failed,
                    }
                    print("  🔄 [小克] 集成测试失败 → 行为护栏联动回滚: "
                          "部署回归已确认, src/ 回滚至基线, 门禁复跑通过")
                elif linkage.get("action") == "gate_failed_independent":
                    report["guardrail_linkage"] = {
                        "action": "gate_failed_independent",
                        "detail": (
                            "baseline also fails after rollback — failure is "
                            "independent of deployment; src/ restored to "
                            "deployed state"
                        ),
                        "rerun_failed": linkage["rerun"].failed,
                    }
                    print("  ⚠️ [小克] 集成测试失败 → 联动回滚验证: 基线也失败, "
                          "非部署问题 — src/ 已恢复部署版, 需人工介入")
                elif linkage.get("action") == "rollback_undo_failed":
                    report["guardrail_linkage"] = {
                        "action": "rollback_undo_failed",
                        "detail": "undo rollback failed — src/ left at baseline!",
                    }
            except Exception as e:  # pragma: no cover - defensive
                log.warning("Guardrail linkage failed (non-fatal): %s", e)

        out_path = session.session_dir / "integration-test.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error("Cannot write integration test report: %s", e)
            raise PipelineStepError(f"Cannot write integration test report: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "unknown": "⚠️", "skipped": "⏭️"}
        print(
            f"  {status_icon.get(status, '❓')} [小克] 接口集成测试完成 "
            f"(runner={test_runner}, {passed} passed, {failed} failed, "
            f"{len(spec_scenarios)} scenarios)"
        )
        log.info(
            "Integration test: runner=%s, passed=%d, failed=%d, scenarios=%d",
            test_runner,
            passed,
            failed,
            len(spec_scenarios),
        )

        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error("Integration test step failed: %s", e)
        raise PipelineStepError(f"Integration test step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: parse pass/fail counts from test output
# ---------------------------------------------------------------------------

def _parse_test_counts(output: str, runner: str) -> tuple[int, int]:
    """Parse passed/failed test counts from runner output.

    Returns (passed, failed) — both default to 0 on parse failure.
    """
    passed = 0
    failed = 0

    if not output:
        return passed, failed

    if runner.startswith("pytest"):
        # pytest summary lines: "3 passed, 1 failed, 2 skipped in 5.23s"
        import re
        m = re.search(r"(\d+)\s+passed", output)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", output)
        if m:
            failed = int(m.group(1))

    elif runner.startswith("ctest"):
        # ctest summary: "100% tests passed, 0 tests failed out of 1"
        import re
        m = re.search(r"(\d+)%\s+tests passed,\s*(\d+)\s+tests failed", output)
        if m:
            failed = int(m.group(2))
            total_m = re.search(r"out of\s+(\d+)", output)
            if total_m:
                passed = int(total_m.group(1)) - failed

    elif runner.startswith("go"):
        # go test output: "ok  package  0.123s"  or  "FAIL  package  0.456s"
        import re
        ok_lines = re.findall(r"^ok\s+\S+", output, re.MULTILINE)
        fail_lines = re.findall(r"^FAIL\s+\S+", output, re.MULTILINE)
        passed = len(ok_lines)
        failed = len(fail_lines)

    return passed, failed
