#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

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
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "tests/",
                        "-q",
                        "-m",
                        "integration",
                        "--timeout=120",
                    ],
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
        if result_returncode is not None and result_returncode != 0:
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

        out_path = session.session_dir / "integration-test.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error("Cannot write integration test report: %s", e)
            raise PipelineStepError(f"Cannot write integration test report: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "unknown": "⚠️"}
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

    elif runner.startswith("go"):
        # go test output: "ok  package  0.123s"  or  "FAIL  package  0.456s"
        import re
        ok_lines = re.findall(r"^ok\s+\S+", output, re.MULTILINE)
        fail_lines = re.findall(r"^FAIL\s+\S+", output, re.MULTILINE)
        passed = len(ok_lines)
        failed = len(fail_lines)

    return passed, failed
