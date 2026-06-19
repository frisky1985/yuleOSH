#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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
import subprocess
import sys
import tempfile
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.test_c_unit")

__all__ = ["step_c_unit_test"]


@timed_step
def step_c_unit_test(session: PipelineSession) -> str:
    """Step: 小克 — C 单元测试 (Unity/Ceedling).

    Discovers and runs C-level unit tests:
      1. Unity test framework under tests/unity/
      2. Ceedling (project.yml detected)
      3. Fallback: gcc compile check of *test*.c files

    If no C source files are found, the step is skipped (not failed).
    """
    try:
        print("  📋 [小克] C 单元测试开始...")
        log.info("Running C unit test step")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # 1. Check for C source files
        c_files = list(project_dir.rglob("*.c"))
        c_header_files = list(project_dir.rglob("*.h"))
        log.info("Found %d .c files and %d .h files", len(c_files), len(c_header_files))

        if not c_files:
            # No C files — skip gracefully
            report = {
                "step": "c-unit-test",
                "agent": "小克",
                "session": session.name,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "status": "skipped",
                "reason": "No C source files found",
                "c_files": 0,
                "c_test_files": 0,
                "test_runner": "none",
            }
            out_path = session.session_dir / "c-unit-test.json"
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("  ⏭️  [小克] 跳过 C 单元测试 — 项目无 C 源码")
            log.info("C unit test skipped: no C source files")
            return str(out_path)

        # 2. Find C test files
        c_test_files = (
            list(project_dir.rglob("*test*.c")) +
            list(project_dir.rglob("*Test*.c")) +
            list(project_dir.rglob("*_test.c")) +
            list(project_dir.rglob("*_tst.c"))
        )
        c_test_files = list(set(c_test_files))  # deduplicate
        log.info("Found %d C test files", len(c_test_files))

        # Try runners in priority order
        test_output = ""
        result_returncode = None
        test_runner = "none"
        passed = 0
        failed = 0

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
                # Include unity submodule if available
                unity_src = unity_dir / "src" / "unity.c"
                if unity_src.exists():
                    src_files.append(str(unity_src))
                    inc_flags = ["-I", str(unity_dir / "src")]
                else:
                    inc_flags = []

                # Use a unique temp path per run (fix: $$ literal vs PID expansion)
                tmp_runner = os.path.join(
                    tempfile.gettempdir(),
                    f"c_test_runner_{os.getpid()}_{id(session)}"
                )
                result = subprocess.run(
                    ["gcc", "-o", tmp_runner]
                    + src_files
                    + inc_flags
                    + ["-lunity", "-lm", "-Wall", "-Wextra"],
                    capture_output=True, text=True, timeout=60,
                )
                test_output = (result.stdout or "") + "\n" + (result.stderr or "")
                result_returncode = result.returncode
                test_runner = "gcc-compile-check"
                passed = 0
                failed = 0 if result.returncode == 0 else len(c_test_files)
                log.info(
                    "GCC compile check: returncode=%d", result.returncode,
                )
                # Clean up the temp binary
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

        # 5. Generate report
        report = {
            "step": "c-unit-test",
            "agent": "小克",
            "session": session.name,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "c_files": len(c_files),
            "c_header_files": len(c_header_files),
            "c_test_files": len(c_test_files),
            "test_runner": test_runner,
            "returncode": result_returncode,
            "output": test_output[:3000],
            "passed": passed,
            "failed": failed,
            "status": status,
        }

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
            f"{len(c_files)} C files)"
        )
        log.info(
            "C unit test: runner=%s, passed=%d, failed=%d, C files=%d",
            test_runner, passed, failed, len(c_files),
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
