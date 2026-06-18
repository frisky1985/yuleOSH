#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step CI.2: 小马 — 测试覆盖结果审查。

CI 测试运行完成后自动分析：
- 覆盖率是否达标（fail_under=70%）
- 未覆盖的代码模块是否有风险
- 测试失败是否是新增的回归

Exports:
  step_review_test_coverage — Test coverage and CI result analysis
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_test_coverage")

__all__ = ["step_review_test_coverage"]

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_DEFAULT_COVERAGE_THRESHOLD_LINE = 70.0
_DEFAULT_COVERAGE_THRESHOLD_COND = 50.0

_CI_RESULT_DIR = ".osh/ci"
_COVERAGE_DATA_DIR = ".yuleosh/reports"


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _find_latest_ci_result(
    project_dir: Path,
    layer: int = 1,
) -> Optional[dict]:
    """Find and parse the most recent CI layer result JSON.

    Returns the parsed dict, or None if no result exists.
    """
    ci_dir = project_dir / _CI_RESULT_DIR
    if not ci_dir.exists():
        return None

    prefix = f"layer{layer}-"
    candidates = sorted(
        [f for f in ci_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read CI result %s: %s", candidates[0], e)
        return None


def _load_coverage_data(project_dir: Path) -> Optional[dict]:
    """Load coverage JSON data from the standard output location.

    Supports both pytest-cov JSON and the yuleOSH coverage export format.
    """
    # Try yuleOSH coverage export format
    cov_paths = [
        project_dir / _COVERAGE_DATA_DIR / "coverage.json",
        project_dir / "coverage.json",
        project_dir / ".coverage",
        project_dir / "coverage" / "coverage.json",
    ]

    for cov_path in cov_paths:
        if cov_path.exists():
            try:
                # .coverage is SQLite (coverage.py raw), skip here
                if cov_path.suffix == ".coverage":
                    continue
                return json.loads(cov_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

    return None


def _read_coverage_xml(project_dir: Path) -> Optional[dict]:
    """Fallback: read coverage.xml if coverage.json is not available."""
    xml_path = project_dir / _COVERAGE_DATA_DIR / "coverage.xml"
    if not xml_path.exists():
        xml_path = project_dir / "coverage.xml"
    if not xml_path.exists():
        return None

    # Minimal XML parser — extract line-rate from <coverage> and <class> elements
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        line_rate = float(root.get("line-rate", "0"))
        branch_rate = float(root.get("branch-rate", "0"))

        # Per-package breakdown
        packages: list[dict] = []
        for pkg in root.findall(".//package"):
            pkg_name = pkg.get("name", "unknown")
            pkg_line_rate = float(pkg.get("line-rate", "0"))
            packages.append({
                "name": pkg_name,
                "line_rate": pkg_line_rate,
            })

        return {
            "line_rate_percent": round(line_rate * 100, 1),
            "branch_rate_percent": round(branch_rate * 100, 1),
            "packages": packages,
        }
    except (ET.ParseError, ValueError, OSError) as e:
        log.warning("Failed to parse coverage XML: %s", e)
        return None


def _assess_module_risk(
    ci_result: Optional[dict],
    coverage_data: Optional[dict],
) -> list[dict]:
    """Assess risk of uncovered or poorly-tested modules.

    Returns a list of risk findings with module name, coverage pct,
    and risk level.
    """
    risks: list[dict] = []

    if not coverage_data:
        return risks

    # Check per-package coverage from XML
    packages = coverage_data.get("packages", [])
    for pkg in packages:
        name = pkg.get("name", "")
        line_rate = pkg.get("line_rate", 0.0)

        if isinstance(line_rate, float) and line_rate < 0.5:
            risks.append({
                "module": name,
                "coverage_pct": round(line_rate * 100, 1) if line_rate <= 1 else line_rate,
                "risk_level": "high",
                "rationale": f"Line coverage below 50% — high risk for undetected defects",
            })
        elif isinstance(line_rate, float) and line_rate < 0.7:
            risks.append({
                "module": name,
                "coverage_pct": round(line_rate * 100, 1) if line_rate <= 1 else line_rate,
                "risk_level": "medium",
                "rationale": f"Line coverage between 50-70% — moderate risk, consider adding tests",
            })

    # Also look at source modules from coverage JSON if available
    if isinstance(coverage_data, dict) and "files" in coverage_data:
        for file_path, file_data in coverage_data["files"].items():
            if isinstance(file_data, dict):
                executed = file_data.get("executed_lines", [])
                missing = file_data.get("missing_lines", [])
                total = len(executed) + len(missing)
                if total > 0:
                    coverage_pct = len(executed) / total * 100
                    if coverage_pct < 30:
                        risks.append({
                            "module": file_path,
                            "coverage_pct": round(coverage_pct, 1),
                            "risk_level": "critical",
                            "rationale": f"Less than 30% line coverage — critical risk",
                        })

    return risks


def _check_test_regression(
    ci_result: Optional[dict],
    previous_ci_result: Optional[dict],
) -> list[dict]:
    """Check if test failures are new regressions vs previous run.

    Returns a list of regression findings.
    """
    findings: list[dict] = []

    if ci_result is None:
        return findings

    current_stages = ci_result.get("stages", [])
    current_unit_stage = next(
        (s for s in current_stages if s.get("name") in ("unit-tests", "coverage")),
        None,
    )

    current_failed = current_unit_stage.get("status") == "failed" if current_unit_stage else False
    current_detail = current_unit_stage.get("detail", "") if current_unit_stage else ""

    if not current_failed:
        # No failures — no regression to report
        return findings

    if previous_ci_result is None:
        findings.append({
            "type": "regression",
            "stage": "unit-tests",
            "detail": "Test failure detected but no previous run for comparison",
            "is_regression": False,
        })
        return findings

    prev_stages = previous_ci_result.get("stages", [])
    prev_unit_stage = next(
        (s for s in prev_stages if s.get("name") in ("unit-tests", "coverage")),
        None,
    )
    prev_failed = prev_unit_stage.get("status") == "failed" if prev_unit_stage else False
    prev_detail = prev_unit_stage.get("detail", "") if prev_unit_stage else ""

    is_regression = not prev_failed
    is_pre_existing = prev_failed and (prev_detail == current_detail)

    if is_regression:
        findings.append({
            "type": "regression",
            "stage": "unit-tests",
            "detail": current_detail,
            "is_regression": True,
            "rationale": "Tests were passing in the previous run but fail now — new regression",
        })
    elif is_pre_existing:
        findings.append({
            "type": "regression",
            "stage": "unit-tests",
            "detail": current_detail,
            "is_regression": False,
            "rationale": "Same failure as previous run — pre-existing issue",
        })
    else:
        findings.append({
            "type": "regression",
            "stage": "unit-tests",
            "detail": current_detail,
            "is_regression": False,
            "rationale": "Different failure than previous run — investigate separately",
        })

    return findings


def _read_coverage_thresholds(project_dir: Path) -> dict:
    """Read coverage thresholds from CI config if available.

    Returns dict with `line` and `condition` thresholds.
    """
    try:
        from yuleosh.ci.config import _get_ci_config
        cfg = _get_ci_config(str(project_dir))
        if cfg and cfg.coverage:
            return {
                "line": cfg.coverage.threshold_line,
                "condition": cfg.coverage.threshold_condition,
            }
    except Exception:
        pass

    return {
        "line": _DEFAULT_COVERAGE_THRESHOLD_LINE,
        "condition": _DEFAULT_COVERAGE_THRESHOLD_COND,
    }


# ------------------------------------------------------------------
# Main step handler
# ------------------------------------------------------------------


@timed_step
def step_review_test_coverage(session: PipelineSession) -> str:
    """Step CI.2: 小马 — Test coverage result review.

    Analyzes CI Layer 1 test coverage results:
    - Checks if line/condition coverage meets thresholds (70%/50%)
    - Identifies uncovered modules and assess risk
    - Detects test regressions vs previous CI runs
    - Gives actionable recommendations for coverage gaps

    Reports are written to {session_dir}/coverage-review.json.
    """
    try:
        print("  🔮 [小马] Analyzing test coverage results...")
        log.info("Analyzing test coverage results")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- 1. Load coverage data ---
        ci_result = _find_latest_ci_result(project_dir, layer=1)
        prev_ci_result = _find_latest_ci_result(project_dir, layer=1)

        # Check if there's a previous run for regression detection by scanning more results
        ci_dir = project_dir / _CI_RESULT_DIR
        prev_ci_result = None
        if ci_dir.exists():
            prefix = "layer1-"
            candidates = sorted(
                [f for f in ci_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".json"],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            if len(candidates) >= 2:
                try:
                    prev_ci_result = json.loads(candidates[1].read_text())
                except (json.JSONDecodeError, OSError):
                    pass

        # --- 2. Load raw coverage data (JSON/XML) ---
        coverage_data = _load_coverage_data(project_dir)
        if coverage_data is None:
            coverage_data = _read_coverage_xml(project_dir)
            if coverage_data is None:
                log.info("No coverage data files found — may use CI result counters")

        # --- 3. Extract coverage metrics ---
        thresholds = _read_coverage_thresholds(project_dir)
        line_threshold = thresholds["line"]
        cond_threshold = thresholds["condition"]

        # Try CIResult coverage first
        line_coverage: Optional[float] = None
        cond_coverage: Optional[float] = None

        if ci_result and ci_result.get("coverage"):
            line_coverage = ci_result["coverage"].get("line_coverage")
            cond_coverage = ci_result["coverage"].get("condition_coverage")
        elif coverage_data:
            line_coverage = coverage_data.get("line_rate_percent")
            cond_coverage = coverage_data.get("branch_rate_percent")

        # --- 4. Assess module risk ---
        module_risks = _assess_module_risk(ci_result, coverage_data)

        # --- 5. Check for test regressions ---
        regression_findings = _check_test_regression(ci_result, prev_ci_result)

        # --- 6. Determine pass/fail ---
        coverage_met = True
        if line_coverage is not None:
            if line_coverage < line_threshold:
                coverage_met = False

        all_tests_passed = True
        test_failures: list[str] = []
        if ci_result:
            for stage in ci_result.get("stages", []):
                if stage.get("status") == "failed":
                    all_tests_passed = False
                    test_failures.append(stage.get("name", stage.get("detail", "unknown")))

        has_critical_risk = any(r["risk_level"] == "critical" for r in module_risks)
        has_high_risk = any(r["risk_level"] == "high" for r in module_risks)

        # --- Determine overall status ---
        if not coverage_met or not all_tests_passed:
            status = "failed"
        elif has_critical_risk:
            status = "warning"
        else:
            status = "passed"

        # --- 7. Build recommendations ---
        recommendations: list[str] = []

        if not coverage_met and line_coverage is not None:
            recommendations.append(
                f"Coverage below threshold: {line_coverage:.1f}% line coverage "
                f"(threshold: {line_threshold}%).  Add tests for uncovered modules."
            )
            if cond_coverage is not None and cond_coverage < cond_threshold:
                recommendations.append(
                    f"Branch coverage {cond_coverage:.1f}% below threshold "
                    f"{cond_threshold}%.  Add condition/decision coverage."
                )

        if test_failures:
            rec = f"Test failures detected: {', '.join(test_failures)}."
            if regression_findings:
                regression_types = [f["type"] for f in regression_findings if f.get("is_regression")]
                if regression_types:
                    rec += " These appear to be NEW regressions."
            recommendations.append(rec)

        if has_critical_risk:
            for r in module_risks:
                if r["risk_level"] == "critical":
                    recommendations.append(
                        f"CRITICAL: Module '{r['module']}' has only "
                        f"{r['coverage_pct']}% coverage — high defect risk."
                    )

        if not recommendations:
            if line_coverage is not None:
                recommendations.append(
                    f"Coverage {line_coverage:.1f}% meets threshold "
                    f"({line_threshold}%).  All tests passed."
                )
            else:
                recommendations.append(
                    "Coverage data not available for detailed analysis."
                )

        # --- Compile report ---
        coverage_detail: dict = {
            "line_coverage_pct": line_coverage,
            "condition_coverage_pct": cond_coverage,
            "line_threshold_pct": line_threshold,
            "condition_threshold_pct": cond_threshold,
            "coverage_met": coverage_met,
        }

        if coverage_data and "packages" in coverage_data:
            coverage_detail["per_package"] = coverage_data["packages"]

        review = {
            "session": session.name,
            "reviewer": "小马",
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "summary": {
                "all_tests_passed": all_tests_passed,
                "coverage_met": coverage_met,
                "coverage": coverage_detail,
                "test_failures": test_failures,
                "module_risks": {
                    "total": len(module_risks),
                    "critical": sum(1 for r in module_risks if r["risk_level"] == "critical"),
                    "high": sum(1 for r in module_risks if r["risk_level"] == "high"),
                    "medium": sum(1 for r in module_risks if r["risk_level"] == "medium"),
                },
                "regressions": len(regression_findings),
            },
            "module_risk_assessment": module_risks,
            "regression_analysis": regression_findings,
            "recommendations": recommendations,
        }

        # --- Write output ---
        out_path = session.session_dir / "coverage-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write coverage review: {e}")
            raise PipelineStepError(f"Cannot write coverage review: {e}")

        # --- Print summary ---
        cov_str = f"{line_coverage:.1f}%" if line_coverage is not None else "N/A"
        cond_str = f"{cond_coverage:.1f}%" if cond_coverage is not None else "N/A"
        print(f"  ✅ [小马] Test coverage review completed:")
        print(f"       Tests passed:     {all_tests_passed}")
        print(f"       Line coverage:    {cov_str} (threshold: {line_threshold}%)")
        if cond_coverage is not None:
            print(f"       Branch coverage:  {cond_str} (threshold: {cond_threshold}%)")
        print(f"       Module risks:     {len(module_risks)} ({review['summary']['module_risks']['critical']} critical, {review['summary']['module_risks']['high']} high)")
        print(f"       Regressions:      {len(regression_findings)}")
        print(f"       Status:           {status}")
        log.info("Coverage review: line=%s, cond=%s, tests=%s, risks=%d, status=%s",
                 cov_str, cond_str, all_tests_passed, len(module_risks), status)

        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Test coverage review step failed: {e}")
        raise PipelineStepError(f"Test coverage review step failed: {e}")
