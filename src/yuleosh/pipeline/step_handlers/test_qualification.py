#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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

    # Split on ### lines that contain GIVEN/WHEN/THEN
    blocks = re.split(r"\n(?=###\s)", content)
    for block in blocks:
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
                proc = subprocess.run(
                    [sys.executable, "-m", "pytest", str(tf), "-v", "--tb=short"],
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
            # C/C++ test files need to be compiled first — note for user
            results["details"].append({
                "file": str(tf),
                "succeeded": False,
                "message": "C/C++ test file requires compilation before execution — skipped",
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
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Qualification test step failed: {e}")
        raise PipelineStepError(f"Qualification test step failed: {e}")
