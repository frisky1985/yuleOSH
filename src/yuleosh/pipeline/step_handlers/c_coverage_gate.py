#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
C Coverage Gate — end-to-end C code coverage verification for yuleOSH pipelines.

Ensures the yuleASR project:
  1. Compiles with cmake -DENABLE_COVERAGE=ON
  2. Runs tests via ctest + gcovr
  3. Validates coverage against c_fail_under threshold using check_coverage_gate.py

Registered as pipeline step ``c-coverage-gate`` for L2 pipeline layer.

Usage::

    from yuleosh.pipeline.step_handlers.c_coverage_gate import coverage_gate_step

    result_path = coverage_gate_step(session)
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.c_coverage_gate")


def coverage_gate_step(session: PipelineSession) -> str:
    """Run C coverage pipeline verification end-to-end.

    Workflow:
      1. Check for coverage-enabled build or rebuild with ENABLE_COVERAGE=ON
      2. Run ctest for test execution
      3. Run gcovr to generate coverage JSON report
      4. Call check_coverage_gate.py to validate against thresholds
      5. Generate structured result report

    Parameters
    ----------
    session : PipelineSession
        Active pipeline session with project_dir context.

    Returns
    -------
    str
        Path to the coverage gate result JSON file.

    Raises
    ------
    PipelineStepError
        If coverage gate blocks the pipeline (line rate < c_fail_under).
    """
    project_dir = str(session.session_dir.parent.parent)
    log.info("C Coverage Gate: project_dir=%s", project_dir)

    results = {
        "session": session.name,
        "step": "c-coverage-gate",
        "timestamp": datetime.now().isoformat(),
        "project_dir": project_dir,
        "phases": {},
        "gate_passed": False,
        "c_fail_under": 70,
        "line_rate": 0.0,
        "branch_rate": 0.0,
        "errors": [],
        "warnings": [],
    }

    try:
        # Phase 1: Build with coverage enabled
        results["phases"]["build"] = _phase_build_coverage(project_dir, results)

        if not results["phases"]["build"]["success"]:
            results["errors"].append("Coverage build failed")
            _write_results(session, results)
            raise PipelineStepError("C coverage: build phase failed")

        # Phase 2: Run tests to generate .gcda files
        results["phases"]["test"] = _phase_run_tests(project_dir, results)

        if not results["phases"]["test"]["success"]:
            results["warnings"].append("Some tests failed — coverage data may be incomplete")

        # Phase 3: Generate coverage report via gcovr
        results["phases"]["gcovr"] = _phase_run_gcovr(project_dir, results)

        if not results["phases"]["gcovr"]["success"]:
            results["errors"].append("gcovr coverage report generation failed")
            _write_results(session, results)
            raise PipelineStepError("C coverage: gcovr phase failed")

        # Phase 4: Validate coverage gate via check_coverage_gate.py
        results["phases"]["gate"] = _phase_check_gate(project_dir, results)

        all_ok = all(
            results["phases"][p].get("success", False)
            for p in results["phases"]
        )

        results["gate_passed"] = all_ok

        if not all_ok:
            _write_results(session, results)
            errors = [e for p in results["phases"].values() if p.get("error") for e in [p["error"]]]
            raise PipelineStepError(f"C coverage gate: {', '.join(errors) if errors else 'gate failed'}")

        log.info("C Coverage Gate PASSED: line_rate=%.1f%%", results.get("line_rate", 0))
        return _write_results(session, results)

    except PipelineStepError:
        _write_results(session, results)
        raise
    except Exception as e:
        log.error("C Coverage Gate unexpected error: %s", e)
        results["errors"].append(str(e))
        _write_results(session, results)
        raise PipelineStepError(f"C coverage gate failed: {e}")


# ── Phase helpers ──


def _phase_build_coverage(project_dir: str, results: dict) -> dict:
    """Phase 1: Build with coverage enabled.

    Checks for an existing coverage build, or creates one with
    cmake -DENABLE_COVERAGE=ON.
    """
    build_dir = Path(project_dir) / "build"
    coverage_build_dir = Path(project_dir) / "cmake-build-coverage"

    # Check if coverage build already exists
    if coverage_build_dir.exists():
        gcda_files = list(coverage_build_dir.rglob("*.gcda")) + \
                     list(coverage_build_dir.rglob("*.gcno"))
        if gcda_files:
            log.info("Coverage build found: %s (%d gcda/gcno files)",
                     coverage_build_dir, len(gcda_files))
            results["c_fail_under"] = _get_fail_under(project_dir)
            return {
                "success": True,
                "build_dir": str(coverage_build_dir),
                "note": "Existing coverage build found",
                "gcno_count": len(gcda_files),
            }

    # Try to detect/use existing build
    if build_dir.exists():
        gcda_files = list(build_dir.rglob("*.gcda")) + list(build_dir.rglob("*.gcno"))
        if gcda_files:
            log.info("Using existing build dir with coverage data: %s", build_dir)
            results["c_fail_under"] = _get_fail_under(project_dir)
            return {
                "success": True,
                "build_dir": str(build_dir),
                "note": "Using existing build",
                "gcno_count": len(gcda_files),
            }

    # Attempt cmake build with ENABLE_COVERAGE=ON
    cd = str(coverage_build_dir)
    try:
        log.info("Building with ENABLE_COVERAGE=ON in %s...", cd)
        cmake_cmd = [
            "cmake", "-S", project_dir, "-B", cd,
            "-DENABLE_COVERAGE=ON",
            "-DCMAKE_BUILD_TYPE=Debug",
        ]
        subprocess.run(cmake_cmd, capture_output=True, text=True,
                       timeout=120, cwd=project_dir, check=False)

        # Build
        build_cmd = ["cmake", "--build", cd, "-j4"]
        build_result = subprocess.run(build_cmd, capture_output=True, text=True,
                                       timeout=300, cwd=project_dir, check=False)

        if build_result.returncode != 0:
            return {
                "success": False,
                "build_dir": cd,
                "error": f"Build failed (rc={build_result.returncode})",
                "stdout": build_result.stdout[-1000:],
                "stderr": build_result.stderr[-1000:],
            }

        results["c_fail_under"] = _get_fail_under(project_dir)
        return {
            "success": True,
            "build_dir": cd,
            "note": "Fresh coverage build",
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "build_dir": cd, "error": "Build timed out (300s)"}
    except FileNotFoundError as e:
        return {"success": False, "build_dir": cd, "error": f"CMake not found: {e}"}
    except Exception as e:
        return {"success": False, "build_dir": cd, "error": str(e)}


def _phase_run_tests(project_dir: str, results: dict) -> dict:
    """Phase 2: Run tests to generate .gcda files.

    Runs ctest in the coverage build directory.
    Falls back to running pytest/tests directly if no ctest.
    """
    build_dir = results.get("phases", {}).get("build", {}).get("build_dir", "")

    if not build_dir or not Path(build_dir).exists():
        return {"success": False, "error": "No build directory from phase 1"}

    # Try ctest first
    try:
        log.info("Running ctest in %s...", build_dir)
        ctest_result = subprocess.run(
            ["ctest", "--output-on-failure", "-j4"],
            capture_output=True, text=True,
            timeout=300, cwd=build_dir, check=False,
        )
        if ctest_result.returncode == 0:
            return {
                "success": True,
                "method": "ctest",
                "stdout": ctest_result.stdout[-1000:],
            }
        else:
            log.warning("ctest returned %d, coverage may be partial", ctest_result.returncode)

            # Even if some tests fail, gcda files may still exist
            gcda_files = list(Path(build_dir).rglob("*.gcda"))
            if gcda_files:
                return {
                    "success": True,
                    "method": "ctest_partial",
                    "warning": f"ctest returned {ctest_result.returncode} but {len(gcda_files)} .gcda files found",
                    "stdout": ctest_result.stdout[-1000:],
                }

            return {
                "success": False,
                "method": "ctest",
                "error": f"ctest failed (rc={ctest_result.returncode})",
                "stdout": ctest_result.stdout[-1000:],
                "stderr": ctest_result.stderr[-500:],
            }

    except FileNotFoundError:
        # No ctest found — fall back to pytest
        log.info("ctest not found, trying pytest...")
        try:
            pytest_result = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
                capture_output=True, text=True,
                timeout=120, cwd=project_dir,
            )
            return {
                "success": pytest_result.returncode == 0,
                "method": "pytest",
                "stdout": pytest_result.stdout[-1000:] if pytest_result.stdout else "",
            }
        except Exception as e:
            return {"success": False, "method": "fallback", "error": str(e)}

    except subprocess.TimeoutExpired:
        return {"success": False, "method": "ctest", "error": "ctest timed out (300s)"}

    except Exception as e:
        return {"success": False, "method": "ctest", "error": str(e)}


def _phase_run_gcovr(project_dir: str, results: dict) -> dict:
    """Phase 3: Generate coverage JSON report using gcovr.

    Searches for .gcda files in build directory and runs gcovr
    to produce a structured JSON report.
    """
    build_dir = results.get("phases", {}).get("build", {}).get("build_dir", "")
    reports_dir = Path(project_dir) / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "c-coverage.json"

    if not build_dir or not Path(build_dir).exists():
        # Fallback: try running the existing coverage script
        for script_name in ["tools/run_c_coverage.sh", "tools/rebuild_coverage.sh"]:
            script_path = Path(project_dir) / script_name
            if script_path.exists():
                try:
                    log.info("Running %s...", script_name)
                    result = subprocess.run(
                        ["bash", str(script_path)],
                        capture_output=True, text=True,
                        timeout=600, cwd=project_dir,
                    )
                    if result.returncode == 0 and json_path.exists():
                        return {"success": True, "method": script_name,
                                "json_path": str(json_path),
                                "stdout": result.stdout[-500:]}
                except Exception as e:
                    log.warning("Script %s failed: %s", script_name, e)

        return {"success": False, "error": "No build dir available for gcovr"}

    # Use yuleOSH's built-in coverage generator
    try:
        from yuleosh.ci.gcov_coverage import generate_c_coverage_report
        generated = generate_c_coverage_report(build_dir=build_dir)
        if generated and Path(generated).exists():
            return {"success": True, "method": "yuleosh_gcov_coverage",
                    "json_path": str(generated)}
    except (ImportError, Exception) as e:
        log.info("yuleosh gcov_coverage fallback: %s", e)

    # Direct gcovr invocation
    try:
        # Find source and object directories
        src_dirs = [str(build_dir)]
        for root, dirs, _ in os.walk(build_dir):
            if "CMakeFiles" in dirs or any(f.endswith(".dir") for f in dirs):
                src_dirs.append(root)

        gcovr_cmd = [
            "gcovr",
            "--root", project_dir,
            "--object-directory", build_dir,
            "--filter", "src/.*",
            "--exclude", "tests/.*",
            "--exclude", "third_party/.*",
            "--json", str(json_path),
            "--json-pretty",
            "--gcov-ignore-errors=source_not_found",
        ]

        log.info("Running gcovr...")
        gcovr_result = subprocess.run(
            gcovr_cmd, capture_output=True, text=True,
            timeout=120, cwd=project_dir, check=False,
        )

        if json_path.exists() and json_path.stat().st_size > 50:
            return {
                "success": True,
                "method": "gcovr",
                "json_path": str(json_path),
                "stdout": gcovr_result.stdout[-500:],
            }

        # Try without filter for broader coverage
        gcovr_cmd.remove("--filter")
        gcovr_cmd.remove("src/.*")
        gcovr_cmd.extend(["--filter", ".*"])

        gcovr_result2 = subprocess.run(
            gcovr_cmd, capture_output=True, text=True,
            timeout=120, cwd=project_dir, check=False,
        )

        if json_path.exists():
            return {
                "success": True,
                "method": "gcovr_broad",
                "json_path": str(json_path),
                "stdout": gcovr_result2.stdout[-500:],
            }

        return {"success": False, "error": "gcovr produced no output file",
                "stdout": (gcovr_result.stdout + gcovr_result2.stdout)[-1000:]}

    except FileNotFoundError:
        return {"success": False, "error": "gcovr not installed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "gcovr timed out (120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _phase_check_gate(project_dir: str, results: dict) -> dict:
    """Phase 4: Validate coverage against gate threshold.

    Calls check_coverage_gate.py from yuleASR tools or the yuleOSH
    check_coverage_gate logic directly.
    """
    # Try yuleASR's check_coverage_gate.py first
    for gate_path in [
        Path(project_dir) / "tools" / "check_coverage_gate.py",
        Path(project_dir) / "tools" / "check_coverage_gate.py",
    ]:
        if gate_path.exists():
            try:
                log.info("Running %s...", gate_path)
                result = subprocess.run(
                    [sys.executable, str(gate_path)],
                    capture_output=True, text=True,
                    timeout=60, cwd=project_dir, check=False,
                )
                passed = result.returncode == 0
                # Parse line and branch rates from output
                line_rate = 0.0
                branch_rate = 0.0
                for line in result.stdout.split("\n"):
                    if "Lines:" in line or "line" in line.lower() and "%" in line:
                        import re
                        m = re.search(r'([\d.]+)%', line)
                        if m:
                            line_rate = float(m.group(1))
                    if "Branches:" in line or "branch" in line.lower() and "%" in line:
                        m = re.search(r'([\d.]+)%', line)
                        if m:
                            branch_rate = float(m.group(1))
                results["line_rate"] = line_rate
                results["branch_rate"] = branch_rate
                return {
                    "success": passed,
                    "method": str(gate_path),
                    "line_rate": line_rate,
                    "branch_rate": branch_rate,
                    "stdout": result.stdout[-1000:],
                    "error": result.stderr[-500:] if not passed else None,
                }
            except Exception as e:
                log.warning("Coverage gate script failed: %s", e)
            break  # Only try the first found

    # Fallback: use yuleOSH's built-in C coverage gate check
    try:
        from yuleosh.ci.stages import run_c_coverage_check
        from yuleosh.ci.result import CIResult

        ci = CIResult()
        success = run_c_coverage_check(project_dir, ci)

        # Extract line rate from CI result
        stages = getattr(ci, "stages", [])
        line_rate = 0.0
        branch_rate = 0.0
        c_fail_under = 70
        for stage in stages:
            if stage.get("key") == "c-coverage-gate":
                detail = stage.get("detail", "")
                import re
                m = re.search(r'line_rate=([\d.]+)', detail)
                if m:
                    line_rate = float(m.group(1))
                    branch_m = re.search(r'branch_rate=([\d.]+)', detail)
                    if branch_m:
                        branch_rate = float(branch_m.group(1))

        results["line_rate"] = line_rate
        results["branch_rate"] = branch_rate
        return {
            "success": success,
            "method": "yuleosh_ci_c_coverage_check",
            "line_rate": line_rate,
            "branch_rate": branch_rate,
        }
    except ImportError as e:
        return {"success": False, "error": f"yuleOSH CI module not available: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_fail_under(project_dir: str) -> int:
    """Read c_fail_under from project configuration.

    Checks .yuleosh/ci-config.yaml and .yuleosh.yaml.
    """
    for config_path in [
        Path(project_dir) / ".yuleosh" / "ci-config.yaml",
        Path(project_dir) / ".yuleosh.yaml",
    ]:
        if config_path.exists():
            try:
                import yaml
                raw = yaml.safe_load(config_path.read_text())
                if not raw:
                    continue
                # Check coverage.c_fail_under
                coverage = raw.get("coverage", {})
                if isinstance(coverage, dict) and "c_fail_under" in coverage:
                    return int(coverage["c_fail_under"])
                # Check ci-config style
                ci = raw.get("ci", {})
                if isinstance(ci, dict):
                    cov = ci.get("coverage", {})
                    if isinstance(cov, dict) and "c_fail_under" in cov:
                        return int(cov["c_fail_under"])
            except Exception:
                continue
    return 70


def _write_results(session: PipelineSession, results: dict) -> str:
    """Write coverage gate results to session output file."""
    out_path = session.session_dir / "c-coverage-gate.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    return str(out_path)
