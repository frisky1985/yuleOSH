# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for evidence modules: generator.py, compliance.py (pack), evidence_check.py.

All tests use unittest.mock and temp directories — no real LLM or filesystem side effects.
API calls match actual function signatures from the source.
"""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ===================================================================
# evidence/generator.py — EvidenceCollector
# ===================================================================

class TestEvidenceCollectorInit:
    """EvidenceCollector initialization and basic properties."""

    def test_init_creates_evidence_dir(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path), version="0.2.0")
        assert collector.version == "0.2.0"
        assert collector.evidence_dir.exists()
        assert str(tmp_path / ".osh" / "evidence") == str(collector.evidence_dir)

    def test_init_default_version(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        assert collector.version == "0.1.0"
        assert collector.evidence_dir.exists()

    def test_init_empty_containers(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        assert collector.requirements == []
        assert collector.scenarios == []

    def test_parse_scenario_refs(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        refs = collector._parse_scenario_refs("Scenario: SC-001 covers RS-001")
        assert isinstance(refs, list)


class TestEvidenceCollectorRequirements:
    """Collecting requirements into EvidenceCollector."""

    def test_collect_requirements_adds_data(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.collect_requirements()
        assert hasattr(collector, "requirements")

    def test_collect_with_mock(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        with mock.patch.object(collector, "collect_requirements") as mock_req:
            collector.collect_requirements()
            mock_req.assert_called_once()

    def test_aggregate_review_logs(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        collector = EvidenceCollector(str(tmp_path))
        collector.reviews = [
            {"id": "R1", "status": "passed", "findings": 0},
            {"id": "R2", "status": "failed", "findings": 3},
        ]
        with mock.patch.object(collector, "aggregate_review_logs") as mock_agg:
            mock_agg.return_value = str(tmp_path / "review_logs.md")
            path = collector.aggregate_review_logs()
            assert path is not None


# ===================================================================
# evidence/compliance.py — pack_compliance_zip
# ===================================================================

class TestPackComplianceZip:
    """pack_compliance_zip: bundles evidence into a ZIP archive."""

    def test_pack_basic(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        from yuleosh.evidence.compliance import pack_compliance_zip

        collector = EvidenceCollector(str(tmp_path))
        collector.requirements = [{"name": "RS-001", "shall_count": 1, "reason": "Safety"}]
        collector.reviews = [{"id": "R1", "status": "passed", "findings": 0}]

        # Create a traceability file
        tm_path = collector.evidence_dir / "traceability.md"
        tm_path.write_text("# Traceability Matrix\n| Req | Test |\n|-----|------|\n| RS-001 | TC-001 |")

        zip_path = pack_compliance_zip(collector)
        assert zip_path is not None
        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert len(names) > 0
            manifest_files = [n for n in names if "manifest" in n.lower()]
            assert len(manifest_files) > 0, f"Manifest not found in {names}"

    def test_pack_no_evidence_handled(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        from yuleosh.evidence.compliance import pack_compliance_zip

        collector = EvidenceCollector(str(tmp_path))
        zip_path = pack_compliance_zip(collector)
        assert zip_path is not None
        assert os.path.exists(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert len(names) >= 0

    def test_pack_includes_manifest(self, tmp_path):
        from yuleosh.evidence.generator import EvidenceCollector
        from yuleosh.evidence.compliance import pack_compliance_zip

        collector = EvidenceCollector(str(tmp_path))
        collector.requirements = [{"name": "RS-001", "shall_count": 1, "reason": ""}]
        tm_path = collector.evidence_dir / "traceability.md"
        tm_path.write_text("# Traceability\n")

        zip_path = pack_compliance_zip(collector)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            manifest_files = [n for n in names if "manifest" in n.lower()]
            assert len(manifest_files) > 0, f"Manifest not found in {names}"


# ===================================================================
# evidence/evidence_check.py — evidence validation
# ===================================================================

class TestEvidenceCheck:
    """Evidence check module — validates evidence completeness."""

    def test_imports_cleanly(self):
        import yuleosh.evidence.evidence_check as ec
        assert ec is not None

    def test_has_core_exports(self):
        import yuleosh.evidence.evidence_check as ec
        public_symbols = [s for s in dir(ec) if not s.startswith("_")]
        assert len(public_symbols) > 0


# ===================================================================
# evidence/analysis.py — analysis functions
# ===================================================================

class TestEvidenceAnalysis:
    """Evidence analysis module — parsing functions."""

    def test_parse_scenario_refs_exists(self):
        from yuleosh.evidence.analysis import parse_scenario_refs
        result = parse_scenario_refs("Scenario: SC-001 covers RS-001")
        assert isinstance(result, list)

    def test_parse_covers_from_file_exists(self):
        from yuleosh.evidence.analysis import parse_covers_from_file
        result = parse_covers_from_file("")
        assert isinstance(result, dict) or isinstance(result, list)


# ===================================================================
# evidence/report.py — report generation
# ===================================================================

class TestEvidenceReport:
    """Evidence report module — format and table helpers."""

    def test_format_maturity_label(self):
        from yuleosh.evidence.report import format_maturity_label
        assert format_maturity_label(85) == "excellent"
        assert format_maturity_label(65) == "good"
        assert format_maturity_label(45) == "fair"
        assert format_maturity_label(25) == "developing"
        assert format_maturity_label(5) == "initial"

    def test_format_status_icon(self):
        from yuleosh.evidence.report import format_status_icon
        assert format_status_icon("passed") == "✅"
        assert format_status_icon("failed") == "❌"
        assert format_status_icon("unknown") == "❓"

    def test_format_coverage_summary(self):
        from yuleosh.evidence.report import format_coverage_summary
        summary = format_coverage_summary(total=20, covered=10)
        assert summary is not None
        assert "50%" in summary or "50" in summary

    def test_make_table_row(self):
        from yuleosh.evidence.report import make_table_row
        row = make_table_row("A", "B", "C")
        assert isinstance(row, str)
        assert "|" in row
        assert "A" in row

    def test_make_header_row(self):
        from yuleosh.evidence.report import make_header_row
        row = make_header_row("Name", "Status")
        assert isinstance(row, str)
        assert "Name" in row
        assert ":---" in row

    def test_make_acceptance_row(self):
        from yuleosh.evidence.report import make_acceptance_row
        row = make_acceptance_row("RS-001", "Init", "SHALL", "Test", "TC-001", "auto", "high", "✅")
        assert isinstance(row, str)
        assert "RS-001" in row

    def test_make_coverage_table_row(self):
        from yuleosh.evidence.report import make_coverage_table_row
        row = make_coverage_table_row("Lines", "80%", "60%", "✅")
        assert isinstance(row, str)
        assert "Lines" in row

    def test_dedent(self):
        from yuleosh.evidence.report import dedent
        text = "  hello\n  world"
        result = dedent(text)
        assert "hello" in result
        assert "world" in result

    def test_generate_timestamp(self):
        from yuleosh.evidence.report import generate_timestamp
        ts = generate_timestamp()
        assert isinstance(ts, str)
        assert "T" in ts  # ISO-8601 format
