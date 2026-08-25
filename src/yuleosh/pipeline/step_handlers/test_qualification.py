#!/usr/bin/env python3

# @req SWR-001.2
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.6): 小明 — 合格性测试。

系统级端到端测试，验证 spec 中定义的 GIVEN/WHEN/THEN 场景。
包含三个子阶段：
1. 需求覆盖检查 (场景→测试用例)
2. 系统级测试执行 (E2E 场景)
3. 验收判定 (通过/失败/未覆盖)

This step is the final gate before release. It confirms that all
specified scenarios pass end-to-end on the target or in simulation.
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec

log = logging.getLogger("pipeline.step_handlers.test_qualification")

__all__ = ["step_test_qualification"]


def _record_step_verdict(session, verdict: str, artifact_paths: list) -> None:
    """Write step.verdict audit event non-fatally (Q1)."""
    try:
        import hashlib as _hl
        import os as _os
        from yuleosh.audit.model import AuditLog

        def _sha256(p: str) -> str:
            h = _hl.sha256()
            try:
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
            except OSError:
                return ""
            return h.hexdigest()

        artifact_hashes = {
            _os.path.basename(p): _sha256(p)
            for p in artifact_paths if p
        }
        audit_root = _os.environ.get("YULEOSH_AUDIT_ROOT")
        audit_log = AuditLog(data_root=audit_root)
        session_id = getattr(session, "name", "") or getattr(session, "session_id", "")
        audit_log.record(
            actor="system",
            action="step.verdict",
            target="step:test-qualification",
            tenant="",
            detail={
                "step": "test-qualification",
                "session_id": session_id,
                "verdict": verdict,
                "artifact_hashes": artifact_hashes,
            },
        )
    except Exception as _e:
        log.warning("_record_step_verdict failed (non-fatal): %s", _e)

# ── Scenario data model ─────────────────────────────────────────────────


class Scenario:
    """A GIVEN/WHEN/THEN scenario parsed from the spec."""

    def __init__(self, raw: str):
        self.raw = raw
        self.given: list[str] = []
        self.when: str = ""
        self.then: list[str] = []
        self._parse()

    def _parse(self):
        current_section = None
        for line in self.raw.split("\n"):
            stripped = line.strip()
            if stripped.upper().startswith("GIVEN"):
                current_section = "given"
                # rest of line after GIVEN
                rest = stripped[5:].strip().lstrip(":").strip()
                if rest:
                    self.given.append(rest)
            elif stripped.upper().startswith("WHEN"):
                current_section = "when"
                rest = stripped[4:].strip().lstrip(":").strip()
                self.when = rest
            elif stripped.upper().startswith("THEN"):
                current_section = "then"
                rest = stripped[4:].strip().lstrip(":").strip()
                if rest:
                    self.then.append(rest)
            elif current_section == "given" and stripped:
                self.given.append(stripped)
            elif current_section == "then" and stripped:
                self.then.append(stripped)
            elif current_section == "when" and not self.when and stripped:
                self.when = stripped

    @property
    def name(self) -> str:
        """Derive a readable name from the raw scenario."""
        # Take first line, sanitize
        first = self.raw.strip().split("\n")[0][:80]
        name = re.sub(r"[^a-zA-Z0-9_\- ]", "", first).strip()
        return name if name else "unnamed-scenario"

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "given": self.given,
            "when": self.when,
            "then": self.then,
        }


# ── Test discovery ────────────────────────────────────────────────────────


def _discover_scenarios(spec_path: str) -> list[Scenario]:
    """Parse the spec file to extract GIVEN/WHEN/THEN scenarios."""
    scenarios = []
    try:
        content = Path(spec_path).read_text()
    except OSError as e:
        log.warning(f"Cannot read spec file {spec_path}: {e}")
        return scenarios

    # Split on header lines (### or ##) that may introduce a scenario block.
    # A scenario block is recognized by containing GIVEN/WHEN/THEN keywords,
    # regardless of the heading level used by the spec author.
    blocks = re.split(r"\n(?=#{2,3}\s)", content)
    for block in blocks:
        if "GIVEN" in block.upper() and "WHEN" in block.upper():
            scenario = Scenario(block.strip())
            scenarios.append(scenario)

    # If no heading-delimited blocks matched, fall back to scanning the whole
    # text for contiguous GIVEN/WHEN/THEN runs (e.g. plain bullet scenarios).
    if not scenarios:
        for block in re.split(r"\n\s*\n", content):
            if "GIVEN" in block.upper() and "WHEN" in block.upper():
                scenario = Scenario(block.strip())
                scenarios.append(scenario)

    return scenarios


def _discover_test_files(project_dir: Path) -> list[Path]:
    """Discover system-level test files that match scenario names."""
    patterns = [
        "**/test_qualification*.py",
        "**/test_qualification*.c",
        "**/e2e_test*.py",
        "**/e2e_test*.c",
        "**/acceptance_test*.py",
        "**/acceptance_test*.c",
        "**/scenario_test*.py",
        "**/scenario_test*.c",
        "**/tests/system/*.py",
        "**/tests/system/*.c",
        "**/tests/e2e/*.py",
        "**/tests/e2e/*.c",
    ]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file():
                found.append(p)
    # Deduplicate
    seen = set()
    unique = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


# ── Coverage check ────────────────────────────────────────────────────────


def _check_scenario_coverage(
    scenarios: list[Scenario],
    test_files: list[Path],
) -> dict:
    """Check which scenarios have corresponding test implementations."""
    coverage = {
        "total_scenarios": len(scenarios),
        "covered": [],
        "uncovered": [],
        "coverage_pct": 0.0,
    }

    if not scenarios:
        return coverage

    # Build keyword index from test file contents
    test_index: dict[str, set[str]] = {}  # scenario_name -> set of test file paths

    for scenario in scenarios:
        keywords = set()
        # Extract significant words from scenario
        for word in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", scenario.raw):
            if word.upper() not in ("GIVEN", "WHEN", "THEN", "THE", "AND", "A", "AN"):
                keywords.add(word.lower())
        test_index[scenario.name] = keywords

    for scenario in scenarios:
        keywords = test_index.get(scenario.name, set())
        matched_files = []

        for tf in test_files:
            try:
                content = tf.read_text(errors="replace").lower()
            except OSError:
                continue

            # Count how many keywords appear in the test file
            match_count = sum(1 for kw in keywords if kw in content)
            threshold = max(2, len(keywords) // 3)
            if match_count >= threshold:
                matched_files.append(str(tf))

        if matched_files:
            coverage["covered"].append({
                "scenario": scenario.name,
                "raw": scenario.raw,
                "test_files": matched_files,
                "match_score": len(matched_files),
            })
        else:
            coverage["uncovered"].append({
                "scenario": scenario.name,
                "raw": scenario.raw,
            })

    coverage["covered_count"] = len(coverage["covered"])
    coverage["uncovered_count"] = len(coverage["uncovered"])
    coverage["coverage_pct"] = (
        (coverage["covered_count"] / coverage["total_scenarios"]) * 100
        if coverage["total_scenarios"] > 0 else 0.0
    )

    return coverage


# ── Test execution ────────────────────────────────────────────────────────


def _find_c_test_binary(test_file: Path, project_dir: Path):
    """Find the compiled binary for a C test source file.

    CMake build dirs (build/, cmake-build-*) place test executables under
    ``<build>/<rel_dir>/<stem>`` — e.g. ``tests/system/test_x.c`` →
    ``cmake-build-coverage/tests/system/test_x``.  Search all candidate
    build dirs and return the first executable found.

    2026-08-14 (headlamp dogfood #8b): CMake target 名可能与源文件 stem
    不同 (``add_executable(headlamp_qualification system/test_x.c)`` →
    二进制 ``build/tests/headlamp_qualification``) — 兜底扫描
    ``<build>/tests/`` 下的可执行文件, 匹配包含源 stem 或 test 关键字的。
    """
    stem = test_file.stem
    rel_dir = test_file.parent.relative_to(project_dir) if test_file.parent != project_dir else Path(".")
    # 2026-08-16 复发防护：旧实现固定优先 build/ → build/ 残留旧二进制时
    # 误选（8/13 window-anti-pinch 19/109 FAILED 根因）。改为收集所有候选
    # 后按 mtime 选最新，杜绝"删 build/ 治标、cmake 重建后又复发"。
    # glob 用 cmake-build*（匹配 cmake-build 与 cmake-build-coverage）——
    # cmake-build-* 漏掉无后缀的 cmake-build/（window-anti-pinch 实际目录）。
    build_dirs = sorted(project_dir.glob("build")) + sorted(project_dir.glob("cmake-build*"))
    candidates: list[Path] = []
    for build_dir in build_dirs:
        if not build_dir.is_dir():
            continue
        candidates.append(build_dir / rel_dir / stem)
        # 某些 CMake 配置把可执行文件放在 build/tests/ 下
        candidates.append(build_dir / "tests" / stem)
        candidates.append(build_dir / stem)
    # 兜底: build/tests/ 下可执行文件, 名称包含源 stem 或 "qualification"
    for build_dir in build_dirs:
        tests_dir = build_dir / "tests"
        if not tests_dir.is_dir():
            continue
        for cand in sorted(tests_dir.iterdir()):
            if not cand.is_file() or not os.access(cand, os.X_OK):
                continue
            if stem in cand.name or "qualification" in cand.name or "system" in cand.name:
                candidates.append(cand)
    # 去重 + 只保留存在且可执行的候选，按 mtime 选最新
    executable_candidates = [
        cand for cand in dict.fromkeys(candidates)
        if cand.is_file() and os.access(cand, os.X_OK)
    ]
    if not executable_candidates:
        return None
    return max(executable_candidates, key=lambda p: p.stat().st_mtime)


def _junit_report_path(project_dir: Path, test_file: Path) -> Path:
    """JUnit XML 输出路径 — 放 .yuleosh/reports/junit-<testfile>.xml。

    review_selftest._discover_junit_xml 会扫 .yuleosh/reports/ 与 session
    目录, 此路径确保带测试名的 JUnit 报告可被发现。
    """
    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"junit-{test_file.stem}.xml"


def _run_system_tests(
    test_files: list[Path],
    project_dir: Path,
    timeout_s: int = 120,
) -> dict:
    """Execute system-level test files and collect results."""
    results = {
        "executed": 0,
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": [],
    }

    for tf in test_files:
        if tf.suffix == ".py":
            try:
                log.info(f"  Running system test: {tf.name}")
                # 2026-08-20 r22 real-4: 加 --junit-xml — selftest-review 因
                # JUnit XML 无测试名无法做 SHALL→用例映射 (43 SHALL 全标
                # 'no evidence' → verify-loop failed)。pytest 的 junit 输出
                # 带 testcase name (test_scenario_qualified[场景名]), 供
                # review_selftest 解析与最终报告引用。
                junit_path = _junit_report_path(project_dir, tf)
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", str(tf), "-v", "--tb=short",
                     "--junit-xml", str(junit_path)],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
                succeeded = proc.returncode == 0
                results["executed"] += 1
                if succeeded:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "file": str(tf),
                        "exit_code": proc.returncode,
                        "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
                        "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
                    })

                results["details"].append({
                    "file": str(tf),
                    "succeeded": succeeded,
                    "returncode": proc.returncode,
                    "stdout_len": len(proc.stdout or ""),
                    "stderr_len": len(proc.stderr or ""),
                    "junit_xml": str(junit_path) if succeeded else "",
                })
            except subprocess.TimeoutExpired:
                results["executed"] += 1
                results["failed"] += 1
                results["errors"].append({
                    "file": str(tf),
                    "exit_code": -1,
                    "stdout_tail": "(timeout)",
                    "stderr_tail": f"Test exceeded {timeout_s}s timeout",
                })
                results["details"].append({
                    "file": str(tf),
                    "succeeded": False,
                    "returncode": -1,
                    "stdout_len": 0,
                    "stderr_len": 0,
                })
            except FileNotFoundError:
                log.warning(f"pytest not found — trying python unittest for {tf.name}")
                try:
                    proc = subprocess.run(
                        [sys.executable, str(tf)],
                        cwd=project_dir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                    )
                    succeeded = proc.returncode == 0
                    results["executed"] += 1
                    if succeeded:
                        results["passed"] += 1
                    else:
                        results["failed"] += 1
                        results["errors"].append({
                            "file": str(tf),
                            "exit_code": proc.returncode,
                            "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
                        })
                except Exception as e2:
                    log.error(f"Cannot run {tf.name}: {e2}")

        elif tf.suffix in (".c", ".cpp"):
            # C/C++ test files need to be compiled first — the pipeline's
            # ctest/build steps compile them (CMake add_executable). Look for
            # the built binary in common build dirs and execute it.
            # 2026-08-14 (headlamp dogfood #8): 之前只记录 "requires
            # compilation — skipped" → C 项目永远 INCOMPLETE。现在从
            # build 目录查找已编译产物并执行。
            binary = _find_c_test_binary(tf, project_dir)
            if binary is None:
                results["details"].append({
                    "file": str(tf),
                    "succeeded": False,
                    "message": "C/C++ test file found but no built binary "
                               "in build/ cmake-build-*/ — run cmake build first",
                })
                continue
            try:
                log.info(f"  Running system test binary: {binary}")
                proc = subprocess.run(
                    [str(binary)],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
                succeeded = proc.returncode == 0
                results["executed"] += 1
                if succeeded:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "file": str(tf),
                        "exit_code": proc.returncode,
                        "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
                        "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
                    })
                results["details"].append({
                    "file": str(tf),
                    "binary": str(binary),
                    "succeeded": succeeded,
                    "returncode": proc.returncode,
                })
            except subprocess.TimeoutExpired:
                results["executed"] += 1
                results["failed"] += 1
                results["errors"].append({
                    "file": str(tf),
                    "exit_code": -1,
                    "stdout_tail": "(timeout)",
                    "stderr_tail": f"Test exceeded {timeout_s}s timeout",
                })

    return results


def _build_qualification_report(
    spec_path: str,
    project_dir: Path,
    scenarios: list[Scenario],
    coverage: dict,
    test_results: dict,
) -> dict:
    """Build the full qualification test report."""
    # Determine overall verdict
    all_scenarios_covered = coverage["uncovered_count"] == 0
    all_tests_passed = test_results["failed"] == 0
    has_executed_tests = test_results["executed"] > 0

    if not scenarios:
        verdict = "not-applicable"
        verdict_reason = "No GIVEN/WHEN/THEN scenarios found in spec"
    elif not has_executed_tests:
        verdict = "incomplete"
        verdict_reason = "No system-level test files found to execute"
    elif all_scenarios_covered and all_tests_passed:
        verdict = "passed"
        verdict_reason = (
            f"All {coverage['total_scenarios']} scenarios covered "
            f"and {test_results['passed']}/{test_results['executed']} tests passed"
        )
    elif not all_scenarios_covered and all_tests_passed:
        verdict = "partial"
        verdict_reason = (
            f"{coverage['uncovered_count']} scenario(s) lack test implementation; "
            f"executed tests all passed"
        )
    else:
        verdict = "failed"
        verdict_reason = (
            f"{test_results['failed']}/{test_results['executed']} test(s) failed; "
            f"{coverage['uncovered_count']} scenario(s) uncovered"
        )

    return {
        "session": None,  # filled by caller
        "reviewer": "小明",
        "step": "test-qualification",
        "timestamp": datetime.now().isoformat(),
        "status": verdict,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "spec_path": spec_path,
        "project_dir": str(project_dir),
        "scenarios": [s.to_dict() for s in scenarios],
        "scenario_count": len(scenarios),
        "coverage": coverage,
        "test_results": test_results,
        "summary": (
            f"合格性测试: {verdict.upper()} — "
            f"场景={coverage['total_scenarios']}, "
            f"覆盖={coverage['covered_count']}/{coverage['total_scenarios']}, "
            f"通过={test_results['passed']}/{test_results['executed']}, "
            f"失败={test_results['failed']}/{test_results['executed']}"
        ),
    }


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_test_qualification(session: PipelineSession) -> str:
    """Step: 小明 — 合格性测试 (SWE.6).

    System-level end-to-end qualification testing:
    1. Parse GIVEN/WHEN/THEN scenarios from the spec
    2. Check test coverage against discovered test files
    3. Execute system-level tests
    4. Produce acceptance verdict (passed / failed / partial / incomplete)
    """
    try:
        print("  🏁 [小明] 合格性测试开始...")
        log.info("Running qualification testing (SWE.6)")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        spec_path = session.spec_path

        # ── Mock mode: skip real qualification ──────────────────────
        # In --mock runs the spec may not carry OpenSpec scenarios and
        # the test corpus is placeholder; a coverage computation would
        # crash with KeyError and block the demo. Record a SKIPPED
        # report and pass. Strict `is True` keeps MagicMock sessions honest.
        if getattr(session, "mock_mode", None) is True:
            report = {
                "step": "test-qualification",
                "agent": "小明",
                "session": session.name,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "status": "skipped",
                "reason": "mock mode — no real code/tests to qualify",
                "scenario_count": 0,
                "verdict": "skipped",
            }
            out_path = session.session_dir / "test-qualification.json"
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print("  ⏭️  [小明] 合格性测试跳过 — mock 模式")
            log.info("Qualification test skipped: mock mode")
            return str(out_path)

        # ── Phase 1: Scenario discovery ──
        log.info("Phase 1: Discovering GIVEN/WHEN/THEN scenarios from spec...")
        scenarios = _discover_scenarios(spec_path)
        log.info(f"  Found {len(scenarios)} scenario(s)")

        if not scenarios:
            print("  ⚠️  [小明] 未发现 GIVEN/WHEN/THEN 场景")
        else:
            for s in scenarios:
                print(f"  📋 场景: {s.name}")

        # ── Phase 2: Test coverage check ──
        log.info("Phase 2: Checking test coverage...")
        test_files = _discover_test_files(project_dir)
        coverage = _check_scenario_coverage(scenarios, test_files)

        coverage_pct = coverage.get("coverage_pct", 0)
        print(f"  📊 场景覆盖: {coverage['covered_count']}/{coverage['total_scenarios']} "
              f"({coverage_pct:.0f}%)")
        if coverage["uncovered"]:
            for u in coverage["uncovered"]:
                print(f"  ⚠️  未覆盖场景: {u['scenario']}")

        # ── Fail-fast (2026-08-12): 无系统级测试文件 → 立即判定 INCOMPLETE ──
        # 旧行为: 继续跑 _run_system_tests (0 executed) 到 Phase 4 才 INCOMPLETE,
        # 且 verdict 不被 _propagate_step_verdict 识别 → 假绿。现在提前判定,
        # verdict=incomplete 会被 orchestrator 按 gate 强度处置 (block → 中断)。
        if not test_files:
            print("  ⚠️  [小明] 未发现系统级测试文件 — 判定 INCOMPLETE (fail-fast)")
            log.warning("No system-level test files found — qualification INCOMPLETE")
            test_results = {
                "executed": 0, "passed": 0, "failed": 0,
                "error": "No system-level test files found to execute",
            }
            report = _build_qualification_report(
                spec_path, project_dir, scenarios, coverage, test_results,
            )
            report["session"] = session.name
            print(f"  🔄 [小明] 合格性测试判定: INCOMPLETE")
            print(f"    {report['verdict_reason']}")
            out_path = session.session_dir / "qualification-test.json"
            try:
                with open(out_path, "w") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
            except OSError as e:
                log.error(f"Cannot write qualification test report: {e}")
                raise PipelineStepError(f"Cannot write qualification test report: {e}")
            log.info("Qualification testing completed (fail-fast): incomplete")
            _record_step_verdict(session, "incomplete", [str(out_path)])
            return str(out_path)

        # ── Phase 3: Test execution ──
        log.info("Phase 3: Running system-level tests...")
        test_results = _run_system_tests(test_files, project_dir)

        print(f"  🧪 测试执行: {test_results['executed']} executed, "
              f"{test_results['passed']} passed, "
              f"{test_results['failed']} failed")

        # ── Phase 4: Acceptance verdict ──
        report = _build_qualification_report(
            spec_path, project_dir, scenarios, coverage, test_results,
        )
        report["session"] = session.name

        verdict = report["verdict"]
        verdict_icon = {
            "passed": "✅",
            "failed": "❌",
            "partial": "⚠️",
            "incomplete": "🔄",
            "not-applicable": "⏭️",
        }
        print(f"  {verdict_icon.get(verdict, '❓')} [小明] 合格性测试判定: {verdict.upper()}")
        print(f"    {report['verdict_reason']}")

        # ── Write output ──
        out_path = session.session_dir / "qualification-test.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write qualification test report: {e}")
            raise PipelineStepError(f"Cannot write qualification test report: {e}")

        log.info(f"Qualification testing completed: {verdict}")
        junit_paths = [
            d.get("junit_xml", "")
            for d in test_results.get("details", [])
            if d.get("junit_xml")
        ]
        _record_step_verdict(session, verdict, [str(out_path)] + junit_paths)
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Qualification test step failed: {e}")
        raise PipelineStepError(f"Qualification test step failed: {e}")
