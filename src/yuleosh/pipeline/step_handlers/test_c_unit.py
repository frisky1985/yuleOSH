#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step SWE.4+: 小克 — C 单元测试 (Unity/Ceedling).

在 SWE.4 自测之后、接口测试之前执行。
对项目中的 C 代码运行 Unity 测试框架 / Ceedling 或 GCC 编译测试。

ASPICE 对齐: SWE.4 单元验证 — 要求在实现语言层面执行单元测试。
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step
from yuleosh.pipeline.guardrail import TestResult

log = logging.getLogger("pipeline.step_handlers.test_c_unit")

__all__ = ["step_c_unit_test"]


@timed_step
def run_c_test_suite(project_dir: str | Path,
                     timeout_build: int = 300,
                     timeout_ctest: int = 300,
                     force_rebuild: bool = False) -> dict:
    """Run the project's C unit test suite and return a result dict.

    2026-08-13 (行为护栏): 从 step_c_unit_test 提取的可复用核心 —
    codegen-deploy 用它在部署前后各跑一次, 对比测试结果检测行为回归。
    返回 dict: runner / returncode / passed / failed / output / status /
    c_files / c_test_files / c_header_files。

    force_rebuild (2026-08-13): 行为护栏场景传 True — 删除 build 里的
    .o/.a 强制全量重编。原因: 部署后立即测试时 cmake 增量构建可能因
    mtime 同秒/APFS 纳秒精度跳过重编 → ctest 跑旧二进制 → 假通过。
    正常 c-unit-test 步骤保持增量 (False), 不受影响。
    """
    project_dir = Path(project_dir)

    # 2026-08-14 (headlamp dogfood #3): rglob 全目录扫描会把
    # artifacts/generated-code/ 旧产物 (含 unity.h 测试) 当项目源码 →
    # gcc-compile-check 假失败。排除非源码目录: 生成产物/构建目录/元数据。
    _EXCLUDED_DIRS = {
        ".git", ".osh", ".yuleosh", ".pytest_cache", "__pycache__",
        "artifacts", "build", "cmake-build", "cmake-build-debug",
        "cmake-build-release", "cmake-build-coverage", "node_modules",
        "third_party", "third-party", "vendor", "external",
    }

    def _iter_sources(pattern: str) -> list:
        out = []
        for p in project_dir.rglob(pattern):
            try:
                rel = p.relative_to(project_dir)
            except ValueError:
                continue
            if any(part in _EXCLUDED_DIRS for part in rel.parts):
                continue
            out.append(p)
        return out

    # 1. Check for C source files
    c_files = _iter_sources("*.c")
    c_header_files = _iter_sources("*.h")
    log.info("Found %d .c files and %d .h files", len(c_files), len(c_header_files))

    if not c_files:
        return {
            "runner": "none", "returncode": None, "passed": 0, "failed": 0,
            "output": "", "status": "skipped", "reason": "No C source files found",
            "c_files": 0, "c_test_files": 0, "c_header_files": 0,
        }

    # 2. Find C test files
    c_test_files = (
        _iter_sources("*test*.c") +
        _iter_sources("*Test*.c") +
        _iter_sources("*_test.c") +
        _iter_sources("*_tst.c")
    )
    c_test_files = list(set(c_test_files))  # deduplicate
    log.info("Found %d C test files", len(c_test_files))

    # 3. Try runners in priority order
    test_output = ""
    result_returncode = None
    test_runner = "none"
    passed = 0
    failed = 0

    # 3a0. Try ctest first — CMake projects define real buildable tests.
    cmake_build_dirs = (
        list(project_dir.glob("build")) +
        list(project_dir.glob("cmake-build*"))
    )
    for build_dir in cmake_build_dirs:
        ctest_cfg = build_dir / "CTestTestfile.cmake"
        if not ctest_cfg.exists():
            continue
        try:
            if force_rebuild:
                # 强制重建 (2026-08-13): 行为护栏部署后立即跑本函数时,
                # cmake 增量构建会因 DependInfo.cmake/.d 缓存 + mtime 同秒
                # 跳过重编 → ctest 跑旧二进制 → 假通过 (实测 60% flaky)。
                # 删除整个 build 目录并重新 configure — 护栏正确性 > 速度。
                _btmp = build_dir.with_name(build_dir.name + ".osh-bak")
                try:
                    if _btmp.exists():
                        shutil.rmtree(_btmp)
                    build_dir.rename(_btmp)
                    subprocess.run(
                        ["cmake", "-S", str(project_dir), "-B", str(build_dir)],
                        capture_output=True, text=True, timeout=timeout_build,
                    )
                    shutil.rmtree(_btmp, ignore_errors=True)
                except OSError as e:
                    log.warning("force rebuild: cmake reconfigure failed: %s", e)
            log.info("Rebuilding %s before ctest%s", build_dir,
                     " (forced)" if force_rebuild else "")
            build_result = subprocess.run(
                ["cmake", "--build", str(build_dir), "-j4"],
                capture_output=True, text=True,
                timeout=timeout_build, cwd=build_dir,
            )
            if build_result.returncode != 0:
                log.warning(
                    "Build failed in %s (rc=%d): %s",
                    build_dir, build_result.returncode,
                    (build_result.stderr or build_result.stdout)[-500:],
                )
                test_output = (build_result.stderr or build_result.stdout)[-1000:]
                result_returncode = build_result.returncode
                test_runner = "ctest-build-failed"
                passed, failed = 0, 0
                break

            log.info("Attempting ctest in %s", build_dir)
            # -LE integration: unit step runs unit tests only; integration
            # tests (LABELS "integration") belong to the integration-test
            # step (2026-08-15, three-layer test separation).
            result = subprocess.run(
                ["ctest", "--output-on-failure", "-j4", "-LE", "integration"],
                capture_output=True, text=True,
                timeout=timeout_ctest, cwd=build_dir,
            )
            test_output = (result.stdout or "") + "\n" + (result.stderr or "")
            result_returncode = result.returncode
            test_runner = "ctest"
            passed, failed = _parse_ctest_counts(result.stdout or "")
            log.info(
                "ctest: returncode=%d, passed=%d, failed=%d",
                result.returncode, passed, failed,
            )
            break
        except FileNotFoundError:
            log.info("ctest not found")
        except subprocess.TimeoutExpired:
            test_output = "TIMEOUT: ctest exceeded %ds" % timeout_ctest
            test_runner = "ctest-timeout"
            log.warning("ctest timed out")
            break

    # 3a. Try Unity test runner (tests/unity/)
    unity_dir = project_dir / "tests" / "unity"
    if unity_dir.exists() and (unity_dir / "Makefile").exists():
        try:
            log.info("Attempting Unity test runner at %s", unity_dir)
            result = subprocess.run(
                ["make", "-C", str(unity_dir)],
                capture_output=True, text=True, timeout=120,
            )
            test_output = (result.stdout or "") + "\n" + (result.stderr or "")
            result_returncode = result.returncode
            test_runner = "unity"
            passed, failed = _parse_unity_counts(test_output)
            log.info(
                "Unity tests: returncode=%d, passed=%d, failed=%d",
                result.returncode, passed, failed,
            )
        except FileNotFoundError:
            log.info("make not found, cannot run Unity tests")
        except subprocess.TimeoutExpired:
            test_output = "TIMEOUT: Unity tests exceeded 120s"
            test_runner = "unity-timeout"
            log.warning("Unity tests timed out")

    # 3b. Try Ceedling
    if test_runner == "none" and (project_dir / "project.yml").exists():
        try:
            log.info("Attempting Ceedling test runner")
            result = subprocess.run(
                ["ceedling", "test:all"],
                capture_output=True, text=True, timeout=180,
                cwd=project_dir,
            )
            test_output = (result.stdout or "") + "\n" + (result.stderr or "")
            result_returncode = result.returncode
            test_runner = "ceedling"
            passed, failed = _parse_ceedling_counts(test_output)
            log.info(
                "Ceedling tests: returncode=%d, passed=%d, failed=%d",
                result.returncode, passed, failed,
            )
        except FileNotFoundError:
            log.info("ceedling not found")
        except subprocess.TimeoutExpired:
            test_output = "TIMEOUT: Ceedling tests exceeded 180s"
            test_runner = "ceedling-timeout"
            log.warning("Ceedling tests timed out")

    # 3c. Fallback: gcc compile test of discovered test files
    if test_runner == "none" and c_test_files:
        try:
            log.info("Attempting GCC compile test of %d test file(s)", len(c_test_files))
            src_files = [str(f) for f in c_test_files]
            unity_src = unity_dir / "src" / "unity.c"
            if unity_src.exists():
                src_files.append(str(unity_src))
                inc_flags = ["-I", str(unity_dir / "src")]
                link_flags = ["-lunity"]
            else:
                # 2026-08-14 (headlamp dogfood #5): 项目不用 Unity 框架时
                # 不能加 -lunity — 纯 main/自研 runner 测试会链接失败
                # (ld: library 'unity' not found)。无 Unity → 只编译链接
                # 测试文件本身。
                inc_flags = []
                link_flags = []

            for inc_dir in sorted(_collect_include_dirs(project_dir)):
                if f"-I{inc_dir}" not in inc_flags:
                    inc_flags.append(f"-I{inc_dir}")

            tmp_runner = os.path.join(
                tempfile.gettempdir(),
                f"c_test_runner_{os.getpid()}_{id(project_dir)}"
            )
            result = subprocess.run(
                ["gcc", "-o", tmp_runner]
                + src_files
                + inc_flags
                + link_flags
                + ["-lm", "-Wall", "-Wextra"],
                capture_output=True, text=True, timeout=60,
            )
            test_output = (result.stdout or "") + "\n" + (result.stderr or "")
            result_returncode = result.returncode
            test_runner = "gcc-compile-check"
            passed = 0
            failed = 0 if result.returncode == 0 else len(c_test_files)
            log.info("GCC compile check: returncode=%d", result.returncode)
            try:
                if os.path.exists(tmp_runner):
                    os.unlink(tmp_runner)
            except OSError:
                pass
        except FileNotFoundError:
            log.info("gcc not found, cannot compile test")
        except subprocess.TimeoutExpired:
            test_output = "TIMEOUT: GCC compile check exceeded 60s"
            test_runner = "gcc-compile-timeout"
            log.warning("GCC compile check timed out")

    # 4. Determine status
    if test_runner == "none":
        status = "unknown"
    elif result_returncode is not None and result_returncode != 0:
        status = "failed"
    elif failed > 0:
        status = "failed"
    else:
        status = "passed"

    return {
        "runner": test_runner,
        "returncode": result_returncode,
        "output": test_output[:3000],
        "passed": passed,
        "failed": failed,
        "status": status,
        "c_files": len(c_files),
        "c_test_files": len(c_test_files),
        "c_header_files": len(c_header_files),
    }



def step_c_unit_test(session: PipelineSession) -> str:
    """Step: 小克 — C 单元测试 (Unity/Ceedling).

    Discovers and runs C-level unit tests:
      1. Unity test framework under tests/unity/
      2. Ceedling (project.yml detected)
      3. Fallback: gcc compile check of *test*.c files

    If no C source files are found, the step is skipped (not failed).

    2026-08-13: runner 逻辑提取到 :func:`run_c_test_suite` — codegen-deploy
    的行为护栏复用同一套测试执行, 保证部署前后对比口径一致。
    """
    try:
        print("  📋 [小克] C 单元测试开始...")
        log.info("Running C unit test step")

        # 2026-08-13 (e2e 修复): 用 session 解析的 project_dir, 不用环境变量 —
        # 与 codegen 分支同源 (2026-08-12): 嵌套/测试调用时环境变量可能已变,
        # 退化到错误目录 → 找不到 build → fallback gcc-compile-check →
        # 门禁假失败 (e2e 真实项目抓到)。
        project_dir = Path(getattr(session, "project_dir", None)
                           or os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real test run ──────────────────────────
        if getattr(session, "mock_mode", None) is True:
            report = {
                "step": "c-unit-test",
                "agent": "小克",
                "session": session.name,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "status": "skipped",
                "reason": "mock mode — LLM outputs are placeholders, no real code to test",
                "c_files": 0,
                "c_test_files": 0,
                "test_runner": "none",
            }
            out_path = session.session_dir / "c-unit-test.json"
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("  ⏭️  [小克] 跳过 C 单元测试 — mock 模式")
            log.info("C unit test skipped: mock mode")
            return str(out_path)

        result = run_c_test_suite(project_dir)
        c_files = result["c_files"]
        c_test_files = result["c_test_files"]
        test_runner = result["runner"]
        result_returncode = result["returncode"]
        test_output = result["output"]
        passed = result["passed"]
        failed = result["failed"]
        status = result["status"]

        if test_runner == "none":
            report = {
                "step": "c-unit-test",
                "agent": "小克",
                "session": session.name,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "status": "skipped",
                "reason": "No C source files found" if c_files == 0
                         else "No test runner available (ctest/unity/ceedling/gcc)",
                "c_files": c_files,
                "c_test_files": c_test_files,
                "test_runner": "none",
            }
            out_path = session.session_dir / "c-unit-test.json"
            try:
                with open(out_path, "w") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
            except OSError as e:
                log.error("Cannot write C unit test report: %s", e)
                raise PipelineStepError(f"Cannot write C unit test report: {e}")
            print("  ⏭️  [小克] 跳过 C 单元测试 — 无测试框架")
            log.info("C unit test skipped: no test runner")
            return str(out_path)

        # Generate report
        # 注: run_c_test_suite 返回的 c_test_files 已是 int (内部 len),
        # 不能再用 len() 包装 (e2e 真实项目抓到的 TypeError, 2026-08-13)
        report = {
            "step": "c-unit-test",
            "agent": "小克",
            "session": session.name,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "c_files": c_files,
            "c_header_files": result["c_header_files"],
            "c_test_files": result["c_test_files"],
            "test_runner": test_runner,
            "returncode": result_returncode,
            "output": test_output[:3000],
            "passed": passed,
            "failed": failed,
            "status": status,
        }

        # ── 门禁联动回滚 (2026-08-13, 方案 A) ─────────────────────
        # 门禁失败 + 部署生效 + 备份在 → 回滚 src → 重跑本门禁隔离验证:
        #   基线通过 = 部署回归 (保持回滚, deploy 报告更新);
        #   基线也失败 = 非部署问题 (undo 恢复部署, 标 RED 人工介入)。
        # 覆盖 c-unit-test/integration-test/self-test/qemu-run;
        # coverage/misra 不联动 (反模式)。
        if status == "failed":
            try:
                from yuleosh.pipeline.guardrail import (
                    CCTestRunner,
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
                    session, "c-unit-test", gate_result, runner=CCTestRunner()
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
                    print("  🔄 [小克] C 单元测试失败 → 行为护栏联动回滚: "
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
                    print("  ⚠️ [小克] C 单元测试失败 → 联动回滚验证: 基线也失败, "
                          "非部署问题 — src/ 已恢复部署版, 需人工介入")
                elif linkage.get("action") == "rollback_undo_failed":
                    report["guardrail_linkage"] = {
                        "action": "rollback_undo_failed",
                        "detail": "undo rollback failed — src/ left at baseline!",
                    }
            except Exception as e:  # pragma: no cover - defensive
                log.warning("Guardrail linkage failed (non-fatal): %s", e)

        out_path = session.session_dir / "c-unit-test.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error("Cannot write C unit test report: %s", e)
            raise PipelineStepError(f"Cannot write C unit test report: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "unknown": "⚠️"}
        print(
            f"  {status_icon.get(status, '❓')} [小克] C 单元测试完成 "
            f"(runner={test_runner}, {passed} passed, {failed} failed, "
            f"{c_files} C files)"
        )
        log.info(
            "C unit test: runner=%s, passed=%d, failed=%d, C files=%d",
            test_runner, passed, failed, c_files,
        )

        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error("C unit test step failed: %s", e)
        raise PipelineStepError(f"C unit test step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: parse Unity test output
# ---------------------------------------------------------------------------

def _parse_unity_counts(output: str) -> tuple[int, int]:
    """Parse Unity test runner output for pass/fail counts.

    Unity output lines like::
        OK (1 test, 1 assertion, 0 failed, 0 ignored)
    or::
        FAIL (1 test, 1 assertion, 1 failed, 0 ignored)
    """
    passed = 0
    failed = 0

    if not output:
        return passed, failed

    # Match per-test lines
    ok_matches = re.findall(r"^OK\s+\(", output, re.MULTILINE)
    fail_matches = re.findall(r"^FAIL\s+\(", output, re.MULTILINE)

    passed = len(ok_matches)
    failed = len(fail_matches)

    # Also try summary line: "X Tests X Failures X Ignored"
    m = re.search(r"(\d+)\s*Tests?\s+(\d+)\s*Failures?", output)
    if m:
        total_tests = int(m.group(1))
        total_failures = int(m.group(2))
        if passed == 0 and failed == 0:
            # No per-test matches found; use summary
            passed = total_tests - total_failures
            failed = total_failures

    return passed, failed


def _parse_ceedling_counts(output: str) -> tuple[int, int]:
    """Parse Ceedling test output for pass/fail counts.

    Ceedling summary lines like::
        --------------------
        TEST OUTPUT SUMMARY
        --------------------
        Passed: 4
        Failed: 1
    """
    passed = 0
    failed = 0

    if not output:
        return passed, failed

    # Ceedling summary
    m = re.search(r"Passed:\s*(\d+)", output)
    if m:
        passed = int(m.group(1))
    m = re.search(r"Failed:\s*(\d+)", output)
    if m:
        failed = int(m.group(1))

    # Fallback: grep for FAIL in Ceedling output
    if passed == 0 and failed == 0:
        fail_count = len(re.findall(r"^\s*FAILED\s*$", output, re.MULTILINE))
        ok_count = len(re.findall(r"^\s*PASSED\s*$", output, re.MULTILINE))
        passed = ok_count
        failed = fail_count

    return passed, failed


def _collect_include_dirs(project_dir: Path) -> list[str]:
    """Collect project include directories (any dir containing a .h file).

    Mirrors verify_c's fix: multi-directory C projects fail a bare gcc
    compile check without -I flags. Walking the tree and adding every
    directory that holds headers makes the compile check robust for
    src/app/include, src/hal/include, tests/, etc.
    """
    include_dirs: list[str] = []
    build_markers = ("build", "cmake-build", "_build", ".git", "node_modules")
    try:
        for root, dirs, files in os.walk(project_dir):
            # Skip build artifacts and VCS dirs
            dirs[:] = [
                d for d in dirs
                if not any(m in d for m in build_markers)
            ]
            if any(f.endswith(".h") for f in files):
                include_dirs.append(str(Path(root)))
    except OSError:
        pass
    return include_dirs


def _parse_ctest_counts(output: str) -> tuple[int, int]:
    """Parse ctest summary output for pass/fail counts.

    ctest prints a final summary like::

        100% tests passed, 0 tests failed out of 1
    """
    passed = 0
    failed = 0
    if not output:
        return passed, failed
    m = re.search(r"(\d+)%\s+tests passed,\s*(\d+)\s+tests failed", output)
    if m:
        failed = int(m.group(2))
        total_m = re.search(r"out of\s+(\d+)", output)
        if total_m:
            passed = int(total_m.group(1)) - failed
    return passed, failed
