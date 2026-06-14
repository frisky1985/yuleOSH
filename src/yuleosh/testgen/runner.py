#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
TestGen Runner — Execute generated test cases and produce coverage reports.

Supports dry-run mode (no actual compilation/execution), pluggable executors,
and SHALL-level traceability reporting.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from .generator import TestCase

log = logging.getLogger("testgen.runner")

# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class TestResult:
    """Result of executing a single test case."""
    test_id: str
    status: str  # "PASS", "FAIL", "SKIP", "ERROR"
    duration_ms: float = 0.0
    message: str = ""


@dataclass
class TestReport:
    """Aggregate report from running a batch of test cases."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    results: list[TestResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total * 100.0, 1)


@dataclass
class CoverageEntry:
    """A single SHALL → test-case mapping."""
    req_id: str
    shall_text: str
    covered_by: list[str]  # test case IDs
    uncovered: bool = False


@dataclass
class CoverageReport:
    """SHALL-level coverage report showing which requirements have tests."""
    total_shall: int = 0
    covered_shall: int = 0
    uncovered_shall: int = 0
    coverage_pct: float = 0.0
    entries: list[CoverageEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_shall": self.total_shall,
            "covered_shall": self.covered_shall,
            "uncovered_shall": self.uncovered_shall,
            "coverage_pct": self.coverage_pct,
            "entries": [asdict(e) for e in self.entries],
        }


# ── Runner ────────────────────────────────────────────────────────────────────


class TestRunner:
    """Execute generated test cases and produce coverage/execution reports.

    The runner supports two modes:
      1. **Dry-run** (default) — validates test case structure without execution.
      2. **Real execution** — writes test code to ``project_dir`` and runs it using
         the appropriate test framework.

    Usage:
        runner = TestRunner()
        report = runner.run_tests(cases, "path/to/project", dry_run=True)
        cov = runner.coverage_report()
    """

    def __init__(self):
        self._last_report: Optional[TestReport] = None
        self._last_coverage: Optional[CoverageReport] = None

    # ── Public API ────────────────────────────────────────────────────────

    def run_tests(
        self,
        test_cases: list[TestCase],
        project_dir: str,
        *,
        dry_run: bool = True,
        spec_path: Optional[str] = None,
        lang: str = "c",
    ) -> TestReport:
        """Run the given test cases and produce an execution report.

        Args:
            test_cases:  List of TestCase objects to execute.
            project_dir: Root directory of the project (for test harness location).
            dry_run:     If True, validate structure only (no actual execution).
            spec_path:   Path to the OpenSpec file (needed for coverage).
            lang:        Target language for generated test code ("c", "python", "go").

        Returns:
            A TestReport summarising pass/fail/skip counts and per-case results.
        """
        start = time.monotonic()

        if dry_run:
            report = self._dry_run(test_cases)
        else:
            report = self._execute(test_cases, project_dir, lang)

        report.duration_ms = round((time.monotonic() - start) * 1000, 1)
        self._last_report = report

        # Build coverage if spec_path is provided
        if spec_path:
            spec_dir = os.path.join(os.path.dirname(__file__), "..", "spec")
            sys.path.insert(0, os.path.normpath(spec_dir))
            try:
                from validate import parse_spec  # noqa: E402
                doc = parse_spec(spec_path)
                self._last_coverage = self._build_coverage(doc, test_cases)
            except Exception as e:
                log.warning("Coverage could not be computed: %s", e)

        return report

    def coverage_report(self) -> dict:
        """Return the last computed coverage report as a dict.

        Returns:
            dict with keys: total_shall, covered_shall, uncovered_shall,
            coverage_pct, entries.
        """
        if self._last_coverage is None:
            return CoverageReport().to_dict()
        return self._last_coverage.to_dict()

    def print_report(self, report: Optional[TestReport] = None) -> None:
        """Pretty-print a TestReport to stdout."""
        r = report or self._last_report
        if r is None:
            print("No report available.")
            return
        print(f"\n{'=' * 50}")
        print(f"🧪 TestGen Execution Report")
        print(f"{'=' * 50}")
        print(f"  Total:   {r.total}")
        print(f"  Passed:  {r.passed}")
        print(f"  Failed:  {r.failed}")
        print(f"  Skipped: {r.skipped}")
        print(f"  Errors:  {r.errors}")
        print(f"  Pass rate: {r.pass_rate}%")
        print(f"  Duration:  {r.duration_ms} ms")
        if r.failed > 0 or r.errors > 0:
            print(f"\n  ❌ Failures:")
            for res in r.results:
                if res.status in ("FAIL", "ERROR"):
                    print(f"    [{res.test_id}] {res.status}: {res.message}")
        print()

    # ── Internal: dry run ─────────────────────────────────────────────────

    @staticmethod
    def _dry_run(test_cases: list[TestCase]) -> TestReport:
        """Validate test case structure without executing.

        Checks:
          - All required fields are non-empty.
          - Priority is valid (P0/P1/P2).
          - Tags are known.
        """
        results: list[TestResult] = []
        valid_priorities = {"P0", "P1", "P2"}
        valid_tags = {"smoke", "regression", "unit", "integration", "boundary", "negative", "performance"}

        for tc in test_cases:
            issues: list[str] = []

            if not tc.given:
                issues.append("GIVEN empty")
            if not tc.when:
                issues.append("WHEN empty")
            if not tc.then:
                issues.append("THEN empty")
            if tc.priority not in valid_priorities:
                issues.append(f"invalid priority {tc.priority!r}")
            if not tc.shall_ref:
                issues.append("shall_ref empty")

            for tag in tc.tags:
                if tag not in valid_tags:
                    # Non-standard tags are informational, not failures
                    log.debug("Non-standard tag on %s: %s", tc.id, tag)

            if issues:
                results.append(TestResult(
                    test_id=tc.id,
                    status="FAIL",
                    message="; ".join(issues),
                ))
            else:
                results.append(TestResult(
                    test_id=tc.id,
                    status="PASS",
                ))

        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")

        return TestReport(
            total=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )

    # ── Internal: real execution ──────────────────────────────────────────

    @staticmethod
    def _execute(
        test_cases: list[TestCase],
        project_dir: str,
        lang: str,
    ) -> TestReport:
        """Execute test cases by writing generated test code and invoking the test runner.

        Supported frameworks by language:
          - python: pytest
          - c: ceedling / Unity
          - go: go test

        Args:
            test_cases:  Test cases to execute.
            project_dir: Project root for test harness location.
            lang:        Target language.

        Returns:
            TestReport summarising execution results.
        """
        from .formatter import format_pytest, format_gotest, format_ceedling

        fmt_map = {
            "python": (format_pytest, "test_gen.py", ["pytest", "-v"]),
            "go": (format_gotest, "gen_test.go", ["go", "test", "-v"]),
            "c": (format_ceedling, "test_gen.c", ["ceedling", "test:pattern=gen"]),
        }

        if lang not in fmt_map:
            raise ValueError(f"Unsupported language for execution: {lang!r}")

        fmt_fn, filename, cmd_template = fmt_map[lang]
        code = fmt_fn(test_cases)

        project_path = Path(project_dir).resolve()
        if lang == "python":
            # Write to tests/ directory
            test_dir = project_path / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            out_path = test_dir / filename
        elif lang == "go":
            test_dir = project_path
            out_path = test_dir / filename
        else:
            test_dir = project_path / "test" / "tests"
            test_dir.mkdir(parents=True, exist_ok=True)
            out_path = test_dir / filename

        out_path.write_text(code, encoding="utf-8")
        log.info("Wrote test code to %s", out_path)

        # Execute the test runner
        results: list[TestResult] = []
        if lang == "python":
            for tc in test_cases:
                try:
                    # Run pytest on the specific test file
                    t0 = time.monotonic()
                    r = subprocess.run(
                        ["pytest", str(out_path), "-v", "-k", tc.id, "--no-header", "-q"],
                        capture_output=True, text=True, timeout=60,
                    )
                    elapsed = (time.monotonic() - t0) * 1000
                    if r.returncode == 0:
                        status = "PASS"
                        msg = ""
                    elif r.returncode == 5:
                        status = "SKIP"
                        msg = "No test matched filter"
                    else:
                        status = "FAIL"
                        msg = r.stderr.strip()[-200:] if r.stderr else r.stdout.strip()[-200:]
                    results.append(TestResult(tc.id, status, round(elapsed, 1), msg))
                except subprocess.TimeoutExpired:
                    results.append(TestResult(tc.id, "ERROR", message="Timeout (60s)"))
                except Exception as e:
                    results.append(TestResult(tc.id, "ERROR", message=str(e)))
        else:
            # For C/Go — run the framework once and report aggregate
            log.warning("Real execution for lang=%s requires test harness setup; marking as SKIP", lang)
            for tc in test_cases:
                results.append(TestResult(tc.id, "SKIP", message="Test harness not configured"))

        passed = sum(1 for r in results if r.status == "PASS")
        failed = sum(1 for r in results if r.status == "FAIL")
        skipped = sum(1 for r in results if r.status == "SKIP")
        errors = sum(1 for r in results if r.status == "ERROR")

        return TestReport(
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            results=results,
        )

    # ── Coverage ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_coverage(
        doc: Any,
        test_cases: list[TestCase],
    ) -> CoverageReport:
        """Build a SHALL-level traceability matrix from spec doc and test cases.

        Maps each SHALL statement to the test cases that reference it via ``shall_ref``.
        """
        from validate import SpecRequirement  # noqa: E402

        entries: list[CoverageEntry] = []

        # Build a lookup: shall_ref -> list of test case IDs
        coverage_map: dict[str, list[str]] = {}
        for tc in test_cases:
            ref = tc.shall_ref.strip()
            if ref not in coverage_map:
                coverage_map[ref] = []
            coverage_map[ref].append(tc.id)

        for req in doc.requirements:
            for shall_text in req.shall:
                ref = req.req_id or req.name
                covered_by = coverage_map.get(ref, [])
                entry = CoverageEntry(
                    req_id=ref,
                    shall_text=shall_text,
                    covered_by=covered_by,
                    uncovered=len(covered_by) == 0,
                )
                entries.append(entry)

        total = len(entries)
        covered = sum(1 for e in entries if not e.uncovered)
        uncovered = total - covered
        pct = round((covered / total * 100.0), 1) if total else 100.0

        return CoverageReport(
            total_shall=total,
            covered_shall=covered,
            uncovered_shall=uncovered,
            coverage_pct=pct,
            entries=entries,
        )
