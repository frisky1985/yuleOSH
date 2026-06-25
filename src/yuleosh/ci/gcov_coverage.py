"""C/C++ code coverage via gcov/lcov.

在 SWE.4（单元测试）后运行，为 C 代码生成覆盖率报告。

用法:
    python -m yuleosh.ci.gcov_coverage [--build-dir <path>] [--src-dir <path>]
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.gcov_coverage")


def run_gcov_coverage(build_dir: str = ".", src_dir: str = "src") -> dict:
    """Run gcov + lcov to generate C coverage report.

    Steps:
    1. Change to build_dir and run ``lcov --capture --directory . --output-file coverage.info``.
    2. Filter out system/external headers.
    3. Generate HTML report via ``genhtml``.

    Returns a dict with:
        - success: bool
        - lcov_file: path to the generated .info file
        - html_dir: path to the generated HTML report directory
        - error: error message if failed
    """
    result: dict = {
        "success": False,
        "lcov_file": "",
        "html_dir": "",
        "error": "",
    }

    build_path = Path(build_dir).resolve()
    if not build_path.is_dir():
        result["error"] = f"Build directory not found: {build_dir}"
        log.error(result["error"])
        return result

    lcov_file = str(build_path / "coverage.info")
    html_dir = str(build_path / "coverage-report-html")
    coverage_abs = build_path / "coverage.info"

    # Step 1: lcov capture
    try:
        log.info("Running lcov capture in %s ...", build_dir)
        subprocess.run(
            ["lcov", "--capture", "--directory", ".",
             "--output-file", lcov_file],
            capture_output=True, text=True, timeout=120,
            cwd=build_dir,
        )
    except FileNotFoundError:
        result["error"] = "lcov not installed"
        log.error(result["error"])
        return result
    except subprocess.TimeoutExpired:
        result["error"] = "lcov timed out"
        log.error(result["error"])
        return result
    except Exception as e:
        result["error"] = f"lcov execution error: {e}"
        log.error(result["error"])
        return result

    if not Path(lcov_file).exists():
        result["error"] = "lcov produced no output file"
        log.error(result["error"])
        return result

    # Step 2: Filter out system/external headers
    src_abs = str(Path(src_dir).resolve())
    filtered_file = str(build_path / "coverage-filtered.info")
    try:
        subprocess.run(
            ["lcov", "--remove", lcov_file,
             "/usr/*", "/opt/*", "*/test/*", "*/tests/*",
             "*/build/*",
             "--output-file", filtered_file],
            capture_output=True, text=True, timeout=60,
            cwd=build_dir,
        )
    except Exception as e:
        log.warning("lcov filter step failed: %s — using raw output", e)
        filtered_file = lcov_file

    # Step 3: Generate HTML report
    try:
        subprocess.run(
            ["genhtml", filtered_file, "--output-directory", html_dir,
             "--title", "C/C++ Coverage Report",
             "--legend", "--frames"],
            capture_output=True, text=True, timeout=120,
            cwd=build_dir,
        )
    except FileNotFoundError:
        log.warning("genhtml not installed — skipping HTML report generation")
        html_dir = ""
    except subprocess.TimeoutExpired:
        log.warning("genhtml timed out — HTML report may be incomplete")
    except Exception as e:
        log.warning("genhtml error: %s", e)

    result["success"] = True
    result["lcov_file"] = filtered_file
    result["html_dir"] = html_dir

    # Log summary line count
    try:
        line_result = subprocess.run(
            ["lcov", "--summary", filtered_file],
            capture_output=True, text=True, timeout=30,
            cwd=build_dir,
        )
        log.info("lcov summary:\n%s", line_result.stdout or line_result.stderr)
    except Exception:
        pass

    return result


def parse_lcov_output(lcov_file: str) -> dict:
    """Parse lcov .info file into structured report.

    Returns a dict with:
        - files: list of per-file coverage dicts
        - totals: aggregate line/hit/function/branch counts
        - line_rate: overall line coverage ratio (0.0-1.0)
        - branch_rate: overall branch coverage ratio (0.0-1.0)
    """
    result: dict = {
        "files": [],
        "totals": {
            "lines": {"found": 0, "hit": 0},
            "functions": {"found": 0, "hit": 0},
            "branches": {"found": 0, "hit": 0},
        },
        "line_rate": 0.0,
        "branch_rate": 0.0,
    }

    if not os.path.isfile(lcov_file):
        log.warning("lcov file not found: %s", lcov_file)
        return result

    current_file: Optional[dict] = None

    with open(lcov_file) as f:
        for line in f:
            line = line.strip()

            # SF:<source_file>
            m_sf = re.match(r"^SF:(.+)$", line)
            if m_sf:
                if current_file:
                    result["files"].append(current_file)
                current_file = {
                    "file": m_sf.group(1),
                    "lines": {"found": 0, "hit": 0},
                    "functions": {"found": 0, "hit": 0},
                    "branches": {"found": 0, "hit": 0},
                }
                continue

            if current_file is None:
                continue

            # DA:<line>,<count>
            m_da = re.match(r"^DA:(\d+),(\d+)$", line)
            if m_da:
                count = int(m_da.group(2))
                current_file["lines"]["found"] += 1
                if count > 0:
                    current_file["lines"]["hit"] += 1
                continue

            # FNF:<count>
            m_fnf = re.match(r"^FNF:(\d+)$", line)
            if m_fnf:
                current_file["functions"]["found"] = int(m_fnf.group(1))
                continue

            # FNH:<count>
            m_fnh = re.match(r"^FNH:(\d+)$", line)
            if m_fnh:
                current_file["functions"]["hit"] = int(m_fnh.group(1))
                continue

            # BRF:<count>
            m_brf = re.match(r"^BRF:(\d+)$", line)
            if m_brf:
                current_file["branches"]["found"] = int(m_brf.group(1))
                continue

            # BRH:<count>
            m_brh = re.match(r"^BRH:(\d+)$", line)
            if m_brh:
                current_file["branches"]["hit"] = int(m_brh.group(1))
                continue

            # end_of_record
            if line == "end_of_record" and current_file:
                # Calculate per-file rate
                f_found = current_file["lines"]["found"]
                f_lines = f_found
                f_hit = current_file["lines"]["hit"]
                current_file["line_rate"] = (f_hit / f_found) if f_found > 0 else 0.0

                b_found = current_file["branches"]["found"]
                b_hit = current_file["branches"]["hit"]
                current_file["branch_rate"] = (b_hit / b_found) if b_found > 0 else 0.0

                # Accumulate totals
                result["totals"]["lines"]["found"] += current_file["lines"]["found"]
                result["totals"]["lines"]["hit"] += current_file["lines"]["hit"]
                result["totals"]["functions"]["found"] += current_file["functions"]["found"]
                result["totals"]["functions"]["hit"] += current_file["functions"]["hit"]
                result["totals"]["branches"]["found"] += current_file["branches"]["found"]
                result["totals"]["branches"]["hit"] += current_file["branches"]["hit"]

                result["files"].append(current_file)
                current_file = None
                continue

    # Compute overall rates
    total_lines = result["totals"]["lines"]
    total_branches = result["totals"]["branches"]
    result["line_rate"] = (
        total_lines["hit"] / total_lines["found"]
        if total_lines["found"] > 0 else 0.0
    )
    result["branch_rate"] = (
        total_branches["hit"] / total_branches["found"]
        if total_branches["found"] > 0 else 0.0
    )

    return result


def generate_c_coverage_report(build_dir: str = ".") -> str:
    """Generate C coverage report and return JSON path.

    Runs lcov capture + parse, saves structured JSON to
    ``.yuleosh/reports/c-coverage.json``, and returns the JSON file path.

    Returns an empty string if coverage generation fails.
    """
    project_dir = Path(build_dir).resolve()
    # Guard: walk up only within workspace bounds, never reach filesystem root
    root_candidate = project_dir
    while not (root_candidate / ".yuleosh").exists() and root_candidate.parent != root_candidate:
        root_candidate = root_candidate.parent
    # If .yuleosh not found anywhere up to root, fallback to the original build_dir
    if not (root_candidate / ".yuleosh").exists():
        project_dir = Path(build_dir).resolve()
    else:
        project_dir = root_candidate

    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    result = run_gcov_coverage(build_dir=build_dir)

    if not result["success"]:
        log.error("C coverage generation failed: %s", result.get("error", "unknown"))
        return ""

    lcov_path = result["lcov_file"]
    if not lcov_path or not os.path.isfile(lcov_path):
        log.error("lcov file not produced")
        return ""

    parsed = parse_lcov_output(lcov_path)

    output = {
        "success": True,
        "lcov_file": lcov_path,
        "html_dir": result.get("html_dir", ""),
        "totals": parsed["totals"],
        "line_rate": round(parsed["line_rate"] * 100, 2),
        "branch_rate": round(parsed["branch_rate"] * 100, 2),
        "total_files": len(parsed["files"]),
        "files": [
            {
                "file": f["file"],
                "line_rate": round(f.get("line_rate", 0) * 100, 2),
                "branch_rate": round(f.get("branch_rate", 0) * 100, 2),
                "lines": f["lines"],
                "functions": f["functions"],
            }
            for f in parsed["files"]
        ],
    }

    json_path = report_dir / "c-coverage.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)

    log.info("C coverage report saved to %s", json_path)
    return str(json_path)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="C/C++ code coverage via gcov/lcov"
    )
    parser.add_argument(
        "--build-dir", default=".",
        help="Build directory containing .gcda/.gcno files",
    )
    parser.add_argument(
        "--src-dir", default="src",
        help="Source directory (for filtering)",
    )
    args = parser.parse_args()

    path = generate_c_coverage_report(build_dir=args.build_dir)
    if path:
        print(f"C coverage report: {path}")
        sys.exit(0)
    else:
        print("C coverage generation failed", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
