#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for evidence/check.py — Multi-layer evidence check.

Covers:
- All 7 check layers
- Valid evidence pack → valid: True
- Missing manifest → valid: False
- Coverage warnings → valid: False with warnings
- Cross-reference resolution
- Timestamp ordering
- SHA-256 integrity verification
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.evidence.check import (
    run_full_evidence_check,
    check_files_present,
    check_fields_complete,
    check_values_reasonable,
    check_timestamps_ordered,
    check_cross_refs_resolved,
    check_sha256_integrity,
    check_signature_valid,
    format_check_result,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def valid_evidence_dir():
    """Create a valid evidence pack with complete structure."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Create required structure
        for sub in ["pipeline", "requirements", "design", "code/review-records",
                    "code/coverage", "test", "release", "artifacts"]:
            (root / sub).mkdir(parents=True)

        # Create files
        files_data = []
        for rel_path, content, required in [
            ("pipeline/pipeline-run.json", {"status": "passed", "steps": [{"name": "build", "timestamp": "2026-01-01T00:00:00Z", "started_at": "2026-01-01T00:00:00Z"}]}, True),
            ("pipeline/pipeline-config.yaml", "pipeline:\n  stages: [build, test]", False),
            ("requirements/traceability.json", {"entries": [{"id": "REQ-001", "refs": ["REQ-001"]}]}, True),
            ("requirements/spec.md", "# Spec", True),
            ("design/sdd-report.json", {"architecture": "layered"}, False),
            ("test/test-results.json", {"passed": 10, "failed": 0}, True),
            ("code/coverage/coverage-summary.json", {"line_coverage": 0.65}, False),
            ("release/release-notes.md", "# v1.0", False),
            ("summary.md", "# Evidence Summary", False),
        ]:
            fp = root / rel_path
            fp.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, dict):
                fp.write_text(json.dumps(content))
            else:
                fp.write_text(content)

            entry = {
                "path": rel_path,
                "size_bytes": fp.stat().st_size,
                "sha256": hashlib.sha256(fp.read_bytes()).hexdigest(),
                "content_type": "json" if rel_path.endswith(".json") else "md" if rel_path.endswith(".md") else "yaml",
                "description": f"File: {rel_path}",
                "required": required,
                "cross_refs": [],
            }
            files_data.append(entry)

        # Build manifest
        manifest = {
            "schema_version": "1.0.0",
            "build_id": "test-001",
            "generated_at": "2026-07-05T14:00:00Z",
            "generated_by": "pytest",
            "evidence_pack_version": "1.0.0",
            "files": files_data,
            "file_count": len(files_data),
            "total_size_bytes": sum(f["size_bytes"] for f in files_data),
            "sha256": "aabbccdd" * 8,
            "cross_refs_valid": True,
            "unresolved_refs": [],
            "coverage_warnings": [],
        }

        (root / "audit-manifest.json").write_text(json.dumps(manifest, indent=2))

        yield str(root)


@pytest.fixture
def invalid_evidence_dir():
    """Create a minimal evidence pack that fails checks."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "test.json").write_text("{}")
        yield str(root)


# ═══════════════════════════════════════════════════════════════════════
# Test: run_full_evidence_check
# ═══════════════════════════════════════════════════════════════════════


class TestFullCheck:
    """Integration test — full multi-layer check."""

    def test_valid_pack_returns_true(self, valid_evidence_dir):
        result = run_full_evidence_check(valid_evidence_dir)
        assert result.valid is True, f"Expected valid: True, got: {result.summary}"
        assert len(result.checks) >= 6

    def test_valid_pack_all_checks_pass(self, valid_evidence_dir):
        result = run_full_evidence_check(valid_evidence_dir)
        for c in result.checks:
            assert c.passed, f"Check '{c.name}' failed: {c.details}"
        assert len(result.errors) == 0

    def test_invalid_pack_returns_false(self, invalid_evidence_dir):
        result = run_full_evidence_check(invalid_evidence_dir)
        assert result.valid is False
        # Should have at least some failing checks
        failing = [c for c in result.checks if not c.passed]
        assert len(failing) > 0

    def test_format_contains_valid(self, valid_evidence_dir):
        result = run_full_evidence_check(valid_evidence_dir)
        output = format_check_result(result)
        assert "valid: True" in output
        assert "✅" in output

    def test_format_shows_invalid(self, invalid_evidence_dir):
        result = run_full_evidence_check(invalid_evidence_dir)
        output = format_check_result(result)
        assert "valid: False" in output

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_full_evidence_check(tmp)
            assert result.valid is False
            # files_present should fail
            files_check = next(
                c for c in result.checks if c.name == "files_present"
            )
            assert not files_check.passed


# ═══════════════════════════════════════════════════════════════════════
# Test: Individual check functions
# ═══════════════════════════════════════════════════════════════════════


class TestCheckFilesPresent:
    def test_passes_with_manifest(self, valid_evidence_dir):
        result = check_files_present(valid_evidence_dir)
        assert result.passed

    def test_fails_without_manifest(self, invalid_evidence_dir):
        result = check_files_present(invalid_evidence_dir)
        assert not result.passed
        assert "not found" in result.details


class TestCheckFieldsComplete:
    def test_passes_with_valid_json(self, valid_evidence_dir):
        result = check_fields_complete(valid_evidence_dir)
        assert result.passed

    def test_fails_with_empty_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "audit-manifest.json").write_text("{}")
            (Path(tmp) / "empty.json").write_text("{}")
            result = check_fields_complete(str(tmp))
            assert not result.passed

    def test_fails_with_bad_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.json").write_text("{invalid")
            result = check_fields_complete(str(tmp))
            assert not result.passed


class TestCheckValuesReasonable:
    def test_passes_with_normal_values(self, valid_evidence_dir):
        result = check_values_reasonable(valid_evidence_dir)
        assert result.passed

    def test_warns_on_low_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "coverage.json").write_text(
                json.dumps({"line_coverage": 0.012})
            )
            result = check_values_reasonable(str(tmp))
            assert not result.passed  # Warning = not passed
            # 0.012 is > 0.01 but < 0.05, so should trigger "below 5%"
            assert "below 5%" in result.details.lower() or "critically low" in result.details

    def test_passes_on_zero_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audit-manifest.json").write_text(json.dumps({"files": []}))
            (root / "data.json").write_text(json.dumps({"count": 42, "rate": 0.5}))
            result = check_values_reasonable(str(tmp))
            assert result.passed


class TestCheckTimestampsOrdered:
    def test_passes_ordered(self, valid_evidence_dir):
        result = check_timestamps_ordered(valid_evidence_dir)
        assert result.passed

    def test_skips_no_pipeline_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "audit-manifest.json").write_text(json.dumps({"files": []}))
            result = check_timestamps_ordered(str(tmp))
            assert result.passed


class TestCheckCrossRefsResolved:
    def test_passes_with_valid_refs(self, valid_evidence_dir):
        result = check_cross_refs_resolved(valid_evidence_dir)
        assert result.passed

    def test_skips_no_traceability(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "audit-manifest.json").write_text(json.dumps({"files": []}))
            result = check_cross_refs_resolved(str(tmp))
            assert result.passed


class TestCheckSHA256Integrity:
    def test_passes_with_valid_manifest(self, valid_evidence_dir):
        result = check_sha256_integrity(valid_evidence_dir)
        assert result.passed

    def test_fails_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_sha256_integrity(str(tmp))
            assert not result.passed

    def test_fails_on_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create file and manifest with wrong hash
            (root / "test.txt").write_text("hello")
            manifest = {
                "files": [{
                    "path": "test.txt",
                    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                    "size_bytes": 5,
                    "content_type": "text",
                    "description": "test",
                    "required": False,
                    "cross_refs": [],
                }]
            }
            (root / "audit-manifest.json").write_text(json.dumps(manifest))
            result = check_sha256_integrity(str(tmp))
            assert not result.passed
            assert "hash mismatch" in result.details


class TestCheckSignatureValid:
    def test_passes_no_signature(self, valid_evidence_dir):
        result = check_signature_valid(valid_evidence_dir)
        assert result.passed
        assert "No signature" in result.details
