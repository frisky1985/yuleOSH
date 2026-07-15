# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for yuleosh.report.exporter — uncovered functions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def tmp_project(tmp_path: Path) -> str:
    """Create a project with .osh/ci and .yuleosh/reports directories."""
    (tmp_path / ".osh" / "ci").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "reports").mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture
def seeded_ci_results(tmp_project: str) -> str:
    """Create sample CI result files for layers 1, 2, 25, 3."""
    project_dir = tmp_project
    for layer, status in [(1, "passed"), (2, "passed"), (25, "passed"), (3, "failed")]:
        ci_dir = Path(project_dir) / ".osh" / "ci"
        data = {
            "layer": layer,
            "status": status,
            "commit": "abc123",
            "started_at": "2026-01-01T00:00:00",
            "completed_at": "2026-01-01T00:01:00",
            "stages": [
                {"name": "build", "status": "passed"},
                {"name": "test", "status": "passed" if layer != 3 else "failed",
                 "detail": ""},
            ],
            "coverage": {"line_coverage": 85.0, "condition_coverage": 72.0,
                         "line_pass": True, "condition_pass": True},
            "errors": [],
        }
        f = ci_dir / f"layer{layer}-build.json"
        f.write_text(json.dumps(data), encoding="utf-8")
    return project_dir


@pytest.fixture
def seeded_misra_report(tmp_project: str) -> str:
    """Create a sample misra-report.json."""
    reports_dir = Path(tmp_project) / ".yuleosh" / "reports"
    data = {
        "summary": {
            "total_violations": 5,
            "total_rules_violated": 3,
            "violations_per_kloc": 2.5,
            "misra_classification": {"required": 2, "advisory": 3},
            "unique_files": ["main.c", "uart.c"],
        }
    }
    (reports_dir / "misra-report.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_project


@pytest.fixture
def seeded_coverage_report(tmp_project: str) -> str:
    """Create a sample c-coverage.json."""
    reports_dir = Path(tmp_project) / ".yuleosh" / "reports"
    data = {"line_rate": 85.0, "branch_rate": 72.0, "total_files": 10,
            "line_pass": True, "branch_pass": True}
    (reports_dir / "c-coverage.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_project


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════


class TestExporterExtended:
    """Extended tests for report exporter."""

    def test_load_misra_report_found(self, seeded_misra_report: str):
        from yuleosh.report.exporter import _load_misra_report
        report = _load_misra_report(seeded_misra_report)
        assert report is not None
        assert report["summary"]["total_violations"] == 5

    def test_load_misra_report_not_found(self, tmp_project: str):
        from yuleosh.report.exporter import _load_misra_report
        assert _load_misra_report(tmp_project) is None

    def test_load_coverage_report_found(self, seeded_coverage_report: str):
        from yuleosh.report.exporter import _load_coverage_report
        report = _load_coverage_report(seeded_coverage_report)
        assert report is not None
        assert report["line_rate"] == 85.0

    def test_load_coverage_report_not_found(self, tmp_project: str):
        from yuleosh.report.exporter import _load_coverage_report
        assert _load_coverage_report(tmp_project) is None

    def test_collect_all_layers(self, seeded_ci_results: str):
        from yuleosh.report.exporter import _collect_all_layers
        layers = _collect_all_layers(seeded_ci_results)
        assert len(layers) == 4
        assert layers[0]["layer"] == 1
        assert layers[1]["layer"] == 2
        assert layers[2]["layer"] == 25
        assert layers[3]["layer"] == 3

    def test_collect_all_layers_empty(self, tmp_project: str):
        from yuleosh.report.exporter import _collect_all_layers
        layers = _collect_all_layers(tmp_project)
        assert layers == []

    def test_generate_json_report_incremental(self, seeded_ci_results: str):
        from yuleosh.report.exporter import generate_json_report
        layers = __import__("yuleosh.report.exporter", fromlist=["_collect_all_layers"]).\
            _collect_all_layers(seeded_ci_results)
        report = generate_json_report(seeded_ci_results, layers, is_final=False)
        assert report["report_type"] == "incremental"
        assert len(report["layers"]) == 4

    def test_generate_json_report_final(self, seeded_ci_results: str):
        from yuleosh.report.exporter import generate_json_report
        layers = []
        for fn in [__import__("yuleosh.report.exporter", fromlist=["_collect_all_layers"])
                   ._collect_all_layers]:
            layers = fn(seeded_ci_results)
        report = generate_json_report(
            seeded_ci_results, layers,
            misra={"summary": {"total_violations": 5, "misra_classification": {},
                               "total_rules_violated": 0, "violations_per_kloc": 0,
                               "unique_files": []}},
            coverage={"line_rate": 85.0, "branch_rate": 72.0},
            is_final=True,
        )
        assert report["report_type"] == "final"
        assert "misra" in report
        assert "c_coverage" in report

    def test_generate_layer_report(self, seeded_ci_results: str):
        from yuleosh.report.exporter import generate_layer_report
        saved = generate_layer_report(seeded_ci_results, 1)
        assert saved is not None
        assert Path(saved).exists()

    def test_generate_markdown_report(self, seeded_ci_results: str):
        from yuleosh.report.exporter import generate_markdown_report, _collect_all_layers
        layers = _collect_all_layers(seeded_ci_results)
        md = generate_markdown_report("project-x", layers, is_final=False)
        assert "project-x" in md
        assert "Layer" in md or "layer" in md

    def test_generate_markdown_report_final(self, seeded_ci_results: str,
                                             seeded_misra_report: str):
        from yuleosh.report.exporter import generate_markdown_report, _collect_all_layers
        from yuleosh.report.exporter import _load_misra_report, _load_coverage_report
        layers = _collect_all_layers(seeded_ci_results)
        misra = _load_misra_report(seeded_misra_report)
        cov = _load_coverage_report(seeded_ci_results)
        md = generate_markdown_report("project-x", layers, misra=misra, coverage=cov,
                                       is_final=True)
        assert "project-x" in md

    def test_generate_final_report(self, seeded_ci_results: str,
                                    seeded_misra_report: str,
                                    seeded_coverage_report: str):
        from yuleosh.report.exporter import generate_final_report
        report_dir = generate_final_report(seeded_ci_results)
        assert report_dir is not None
        assert Path(report_dir).exists()
        # Check that reports were generated
        json_path = Path(report_dir) / "ci-final-report.json"
        assert json_path.exists()
        content = json_path.read_text(encoding="utf-8")
        assert "report_type" in content



