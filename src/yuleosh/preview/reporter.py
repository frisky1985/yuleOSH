#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
AI Preview Assessment — Report Generator (PREVIEW-REQ-004).

Transforms raw analysis data from analyzer.py into the structured
assessment report format defined in the spec:
  - Coverage prediction
  - Compliance risk
  - Recommended pipeline config
"""

import time
from typing import Any


def build_assessment_report(analysis: dict) -> dict:
    """Build a complete assessment report from raw analysis data.

    Args:
        analysis: Output from analyzer.analyze_directory()

    Returns:
        dict with sections: coverage_prediction, compliance_risks,
                            recommended_pipeline
    """
    report = {
        "generated_at": time.time(),
        "project_summary": _build_project_summary(analysis),
        "coverage_prediction": _build_coverage_prediction(analysis),
        "compliance_risks": _build_compliance_risks(analysis),
        "recommended_pipeline": _build_recommended_pipeline(analysis),
    }
    return report


def _build_project_summary(analysis: dict) -> dict:
    """Build project summary section."""
    fs = analysis.get("file_summary", {})
    frameworks = [f["name"] for f in analysis.get("detected_frameworks", [])]

    return {
        "total_files": fs.get("total_files", 0),
        "total_lines": fs.get("total_lines", 0),
        "source_files": fs.get("source_files", 0),
        "test_files": fs.get("test_files", 0),
        "by_extension": fs.get("by_extension", {}),
        "detected_frameworks": frameworks,
        "test_framework": analysis.get("test_infrastructure", {}).get("detected_framework", "none"),
        "test_density": analysis.get("test_infrastructure", {}).get("test_density", 0),
    }


def _build_coverage_prediction(analysis: dict) -> dict:
    """Build coverage prediction section (PREVIEW-REQ-004.1)."""
    cp = analysis.get("coverage_prediction", {})

    return {
        "current_coverage_estimate": cp.get("current_coverage_estimate", 0),
        "projected_coverage_after_yuleosh": cp.get("projected_coverage_after_yuleosh", 0),
        "confidence": cp.get("confidence", "low"),
        "bottleneck_files": cp.get("bottleneck_files", []),
    }


def _build_compliance_risks(analysis: dict) -> list[dict]:
    """Build compliance risks section (PREVIEW-REQ-004.2)."""
    return analysis.get("compliance_risks", [])


def _build_recommended_pipeline(analysis: dict) -> dict:
    """Build recommended pipeline section (PREVIEW-REQ-004.3)."""
    return analysis.get("recommended_template", {
        "recommended_template": "generic-embedded-c",
        "steps": [],
        "ci_layers": {},
        "review_gates": [],
        "yaml_snippet": "",
    })
