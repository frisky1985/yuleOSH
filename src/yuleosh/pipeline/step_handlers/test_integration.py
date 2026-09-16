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
import shutil
import subprocess
import sys
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _parse_scenarios, _parse_spec
from yuleosh.pipeline.guardrail import TestResult

log = logging.getLogger("pipeline.step_handlers.test_integration")


def _is_project_root(d) -> bool:
    """Heuristic: does ``d`` look like a project root we can run integration
    tests from? Checks for common markers used by the runner branches below
    (pytest/tests, CMake, Go, JS, Python)."""
    d = Path(d)
    return any((d / m).exists() for m in (
        "tests", "CMakeLists.txt", "go.mod", "package.json", "pyproject.toml",
    ))


def _cmake_cache_source_dir(build_dir) -> "str | None":
    """Extract the project source dir recorded in a build dir's CMakeCache.

    Returns the absolute source path CMake configured this build from, or
    None if no cache / not parseable. Used to detect a *stale* build dir
    whose cache still points at a different source tree — e.g. the demo
    runner copies ``templates/gpio-led-chaser`` to a temp dir, carrying
    along a ``CMakeCache.txt`` that records the template's original absolute
    path. Reusing such a cache makes ``ctest`` look for executables at the
    WRONG location and fail with rc=8.
    """
    cache = Path(build_dir) / "CMakeCache.txt"
    if not cache.exists():
        return None
    try:
        text = cache.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for line in text.splitlines():
        # e.g.  gpio_led_chaser_SOURCE_DIR:STATIC=/abs/path
        if "_SOURCE_DIR:" in line and "=" in line and "BINARY_DIR" not in line:
            return line.split("=", 1)[1].strip()
    return None


def _remove_stale_build_dirs(project_dir) -> "list[str]":
    """Remove build dirs whose CMakeCache points at a different source tree.

    A project copied/relocated (template -> temp demo dir) can carry a stale
    ``build/`` whose CMakeCache still records the ORIGINAL source path. Reusing
    that cache makes ctest resolve executables at the wrong location. We drop
    such dirs so the step's auto-configure fallback issues a fresh
    ``cmake -S . -B build``. Returns the list of removed dir paths.
    """
    project_dir = Path(project_dir).resolve()
    removed = []
    for cand in list(project_dir.glob("build")) + list(project_dir.glob("cmake-build*")):
        if not cand.is_dir():
            continue
        csd = _cmake_cache_source_dir(cand)
        if csd and Path(csd).resolve() != project_dir:
            log.warning(
                "Stale CMake cache in %s (SOURCE_DIR=%s != project %s) — "
                "removing for fresh configure", cand, csd, project_dir,
            )
            shutil.rmtree(cand, ignore_errors=True)
            removed.append(str(cand))
    return removed


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

        # 2026-09-16: 优先用 session.spec_path 解析项目目录, 与
        # c_coverage_gate._resolve_coverage_project_dir 保持一致。完整链路下
        # session.project_dir 常为 None, 若只退化到 OSH_HOME 会落在父目录
        # (如 /tmp/yuleosh_local_demo), 而子项目 (gpio-led-chaser) 在其子目录,
        # 导致 tests/ / CMakeLists.txt 都找不到 → C 模板 ctest 兜底完全不触发
        # (status=unknown)。spec_path (<project>/docs/spec.md -> <project>) 是
        # authoritative, 稳健不受 OSH_HOME / session_dir 位置影响。
        # 2026-09-16: 项目目录解析优先级
        #   1) session.project_dir (仅当它真的是项目根: 含 tests/CMakeLists/go.mod
        #      等标记) — 保留历史语义与单测契约 ("project_dir 即项目根")。
        #   2) session.spec_path (<project>/docs/spec.md -> <project>) — 与
        #      c_coverage_gate 一致, 是 authoritative。完整链路下 session.project_dir
        #      默认 = OSH_HOME (orchestrator 传入), 在子项目布局里落在父目录而非
        #      具体项目根 → 被 _is_project_root 判否 → 回退到这里, 正确定位到子项目,
        #      使 C 模板 ctest 兜底真正触发 (不再 status=unknown)。
        #   3) OSH_HOME — 最后兜底。
        # 用 isinstance(str/Path) 守卫, 避免 MagicMock 的 getattr 返回子 Mock 被误判
        # 为有效路径。
        proj_dir = getattr(session, "project_dir", None)
        spec_path = getattr(session, "spec_path", None)
        if isinstance(proj_dir, (str, Path)) and str(proj_dir).strip() \
                and _is_project_root(proj_dir):
            project_dir = Path(proj_dir).resolve()
        elif isinstance(spec_path, (str, Path)) and str(spec_path).strip():
            # spec_path 形如 <project>/docs/spec.md -> 取两级父得到 <project>
            project_dir = Path(spec_path).resolve().parent.parent
        else:
            project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

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
        # True when a CMake configure failed because the required toolchain is
        # absent in this environment (e.g. ESP-IDF / IDF_PATH for esp-idf-blinky).
        # Used to surface an honest non-green (skipped) integration gate instead
        # of the 0-test "vacuum pass" (configure fails silently → test_runner
        # stays "none" → status "unknown" → gate collapses to "passed").
        cmake_configure_failed = False

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
            # 2026-09-16: 先清除 cache 失配的陈旧 build 目录。项目被拷贝/搬迁
            # (如 demo runner 把 templates/gpio-led-chaser 拷到临时目录) 会把原
            # 模板路径的 CMakeCache 一并带过来; 复用此类 cache 会让 ctest 到错误
            # 位置找可执行文件 (rc=8 假失败)。清除后若无可用的 build 目录, 下方
            # 自动配置逻辑会走全新 cmake -S -B build。
            _remove_stale_build_dirs(project_dir)
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
                        cmake_configure_failed = True
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
        # 注 (2026-09-16):
        #   - ctest 在「无测试匹配 label」时返回 0 (打印 "No tests were found!!!"),
        #     并非 8。为诚实避免「0 测试真空通过」(vacuum pass), 这种情况判 skipped。
        #   - ctest 返回 8 表示「有测试失败」, 必须判 failed; 此前
        #     `rc==8 and ctest-integration -> skipped` 的分支会掩盖真实门禁失败, 已删除。
        if result_returncode == 5 and test_runner == "pytest-integration":
            status = "skipped"
        elif (result_returncode == 0
              and "No tests were found" in (test_output or "")):
            # ctest -L integration matched nothing — honest non-green (skipped),
            # not a false pass.
            status = "skipped"
        elif result_returncode is not None and result_returncode != 0:
            status = "failed"
        elif failed > 0:
            status = "failed"
        elif test_runner == "none":
            if cmake_configure_failed:
                # CMake configure failed (toolchain / IDF absent in this env):
                # integration tests could not be built or run, so this is an
                # honest non-green (skipped) gate — NOT a false pass. The
                # project requires a toolchain not present here (e.g. ESP-IDF
                # for esp-idf-blinky); the spec declares this limitation.
                status = "skipped"
            else:
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

        # Surface the toolchain-absent reason in the artifact for traceability.
        if cmake_configure_failed:
            report["reason"] = (
                "cmake configure failed — project requires a toolchain "
                "(e.g. ESP-IDF / IDF_PATH) not present in this environment; "
                "integration tests could not be built or run"
            )

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
