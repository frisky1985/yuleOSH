#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
AI Preview Assessment — Code Analyzer (PREVIEW-REQ-004).

Performs static analysis on uploaded source code to determine:
  - Project structure and file types
  - Detected frameworks (FreeRTOS, Zephyr, AUTOSAR, etc.)
  - Code complexity metrics (per-file and aggregate)
  - Test infrastructure maturity
  - Compliance risk factors (MISRA, safety)
  - Pipeline config recommendation
  - Documentation quality
  - Language distribution
  - Estimated effort
  - Overall maturity rating
"""

from pathlib import Path
from typing import Union

from yuleosh.preview.score_engine import (
    _count_total_lines, _count_by_extension,
    _detect_languages, _assess_documentation,
    _estimate_effort, _compute_maturity,
    _extract_lines,
)
from yuleosh.preview.code_parser import (
    SUPPORTED_EXTENSIONS, _discover_files,
    _scan_frameworks, _measure_complexity,
    _measure_per_file_complexity, _measure_max_nesting,
    _detect_test_framework, _find_matching_files,
)
from yuleosh.preview.coverage_predictor import _predict_coverage
from yuleosh.preview.compliance_analyzer import _scan_risks
from yuleosh.preview.config_recommender import _recommend_template

# Re-export constants for backwards compatibility
LANGUAGE_MAP = {
    ".c": "C", ".h": "C Header", ".cpp": "C++", ".hpp": "C++ Header",
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript React", ".md": "Markdown", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
}


def analyze_directory(source_dir: Union[str, Path]) -> dict:
    """Analyze a source code directory and produce analysis data.

    Args:
        source_dir: Path to the extracted/cloned source code.

    Returns:
        dict with keys:
          - file_summary: total files, lines, by extension, by language
          - detected_frameworks: list of detected frameworks
          - complexity: avg function length, cyclomatic indicators, per-file
          - test_infrastructure: test framework, test file ratio
          - compliance_risks: list of risk findings
          - recommended_template: suggested template name
          - coverage_prediction: estimated coverage metrics
          - documentation_quality: README / docstring / spec quality
          - estimated_effort: person-hours estimate
          - maturity_rating: overall project maturity (0-100)
    """
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    # ── File discovery ──────────────────────────────────────────────
    all_files, source_files, header_files, test_files, config_files = _discover_files(source_dir)

    # ── Content scanning ────────────────────────────────────────────
    framework_hits = _scan_frameworks(source_dir)
    complexity = _measure_complexity(source_dir)
    risk_findings = _scan_risks(source_dir, complexity)

    # ── Test metrics ────────────────────────────────────────────────
    test_framework = _detect_test_framework(source_dir)
    test_density = len(test_files) / max(len(source_files), 1)

    # ── Language distribution ───────────────────────────────────────
    language_dist = _detect_languages(all_files, source_dir)

    # ── Documentation quality ───────────────────────────────────────
    doc_quality = _assess_documentation(source_dir)

    # ── Determine recommended template ──────────────────────────────
    recommended_template = _recommend_template(
        framework_hits, complexity, risk_findings
    )

    # ── Compute coverage prediction ─────────────────────────────────
    coverage = _predict_coverage(
        test_density=test_density,
        test_framework=test_framework,
        complexity_score=complexity.get("avg_lines_per_function", 0),
    )

    # ── Effort estimation ───────────────────────────────────────────
    effort = _estimate_effort(all_files, framework_hits, complexity)

    # ── Maturity rating ─────────────────────────────────────────────
    maturity = _compute_maturity(
        test_framework, test_density, len(test_files),
        complexity, doc_quality, framework_hits, coverage,
    )

    # ── Per-file complexity ─────────────────────────────────────────
    per_file_complexity = _measure_per_file_complexity(source_dir)

    result = {
        "file_summary": {
            "total_files": len(all_files),
            "source_files": len(source_files),
            "header_files": len(header_files),
            "test_files": len(test_files),
            "config_files": len(config_files),
            "total_lines": _count_total_lines(all_files),
            "by_extension": _count_by_extension(all_files),
            "by_language": language_dist,
        },
        "detected_frameworks": framework_hits,
        "complexity": complexity,
        "per_file_complexity": per_file_complexity,
        "test_infrastructure": {
            "detected_framework": test_framework,
            "test_density": round(test_density, 3),
            "test_file_count": len(test_files),
        },
        "compliance_risks": risk_findings,
        "recommended_template": recommended_template,
        "coverage_prediction": coverage,
        "documentation_quality": doc_quality,
        "estimated_effort": effort,
        "maturity_rating": maturity,
    }

    return result
