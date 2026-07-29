#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for preview/reporter.py — build_assessment_report()
"""

from yuleosh.preview.reporter import (
    build_assessment_report,
    _build_project_summary,
    _build_coverage_prediction,
    _build_compliance_risks,
    _build_recommended_pipeline,
)


class TestAssessmentReport:
    """Coverage-boosting tests for preview/reporter."""

    def test_build_assessment_report_minimal(self):
        """Minimal analysis produces a complete report with all sections."""
        analysis = {
            "file_summary": {
                "total_files": 10,
                "total_lines": 500,
                "source_files": 8,
                "test_files": 2,
                "by_extension": {".c": 5, ".h": 3, ".py": 2},
                "by_language": {
                    "primary_language": "C",
                    "distribution": {"C": 60, "Python": 40},
                },
            },
            "detected_frameworks": [{"name": "Unity"}],
            "test_infrastructure": {
                "detected_framework": "Unity",
                "test_density": 0.3,
            },
            "coverage_prediction": {
                "current_coverage_estimate": 25.0,
                "projected_coverage_after_yuleosh": 80.0,
                "confidence": "medium",
                "bottleneck_files": ["src/main.c"],
            },
            "compliance_risks": [{"risk_level": "medium", "description": "No assertions"}],
            "estimated_effort": {"estimated_person_hours": 40},
            "maturity_rating": {"rating": "bronze", "score": 35},
            "documentation_quality": {
                "doc_score": 40,
                "has_readme": True,
                "comment_to_code_ratio": 0.05,
            },
            "recommended_template": {
                "recommended_template": "generic-embedded-c",
                "steps": ["spec-check", "architecture"],
                "ci_layers": {"1": {}},
                "review_gates": ["misra"],
                "yaml_snippet": "",
            },
        }
        report = build_assessment_report(analysis)
        assert "generated_at" in report
        assert "project_summary" in report
        assert "coverage_prediction" in report
        assert "compliance_risks" in report
        assert "recommended_pipeline" in report

        summary = report["project_summary"]
        assert summary["total_files"] == 10
        assert summary["primary_language"] == "C"
        assert summary["maturity_rating"] == "bronze"

        cp = report["coverage_prediction"]
        assert cp["current_coverage_estimate"] == 25.0
        assert cp["confidence"] == "medium"

    def test_build_assessment_report_empty(self):
        """Empty analysis produces safe defaults."""
        report = build_assessment_report({})
        summary = report["project_summary"]
        assert summary["total_files"] == 0
        assert summary["primary_language"] == "Unknown"

    def test_build_project_summary_extra_fields(self):
        """_build_project_summary handles missing fields gracefully."""
        result = _build_project_summary({})
        assert result["total_files"] == 0
        assert result["total_lines"] == 0
        assert result["test_density"] == 0

    def test_build_coverage_prediction_empty(self):
        """_build_coverage_prediction returns defaults for empty input."""
        result = _build_coverage_prediction({})
        assert result["current_coverage_estimate"] == 0
        assert result["confidence"] == "low"

    def test_build_compliance_risks_empty(self):
        """_build_compliance_risks returns empty list."""
        assert _build_compliance_risks({}) == []

    def test_build_recommended_pipeline_empty(self):
        """_build_recommended_pipeline returns default template."""
        result = _build_recommended_pipeline({})
        assert result["recommended_template"] == "generic-embedded-c"
