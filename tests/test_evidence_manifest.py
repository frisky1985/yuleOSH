#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for evidence/manifest.py — AuditManifest generation.

Covers:
- File scanning and SHA-256 computation
- AuditManifest dataclass construction
- Save/load round-trip
- Cross-reference validation
- Coverage reasonableness checks
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest

from yuleosh.evidence.manifest import (
    AuditManifest,
    ManifestFileEntry,
    generate_audit_manifest,
    save_manifest,
    load_manifest,
    manifest_to_dict,
)


class TestManifestFileEntry:
    """ManifestFileEntry construction and serialization."""

    def test_create_entry(self):
        entry = ManifestFileEntry(
            path="test/file.json",
            size_bytes=1234,
            sha256="abc123" * 8,
            content_type="json",
            description="Test file",
            required=True,
            cross_refs=["other_file.json"],
        )
        assert entry.path == "test/file.json"
        assert entry.size_bytes == 1234
        assert entry.required is True
        assert "other_file.json" in entry.cross_refs

    def test_entry_defaults(self):
        entry = ManifestFileEntry(
            path="test.txt",
            size_bytes=0,
            sha256="0000",
            content_type="text",
            description="Empty file",
        )
        assert entry.required is False
        assert entry.cross_refs == []


class TestAuditManifest:
    """AuditManifest construction and serialization."""

    def test_create_manifest(self):
        files = [
            ManifestFileEntry(
                path="pipeline-run.json",
                size_bytes=500,
                sha256="a" * 64,
                content_type="json",
                description="Pipeline run",
                required=True,
            ),
            ManifestFileEntry(
                path="summary.md",
                size_bytes=200,
                sha256="b" * 64,
                content_type="md",
                description="Summary",
            ),
        ]
        m = AuditManifest(
            schema_version="1.0.0",
            build_id="abc123-20260705",
            generated_at="2026-07-05T14:00:00Z",
            generated_by="test",
            evidence_pack_version="1.0.0",
            files=files,
            file_count=2,
            total_size_bytes=700,
            sha256="c" * 64,
        )
        assert m.schema_version == "1.0.0"
        assert m.file_count == 2
        assert m.total_size_bytes == 700

    def test_manifest_to_dict_roundtrip(self):
        entry = ManifestFileEntry(
            path="test.json",
            size_bytes=100,
            sha256="d" * 64,
            content_type="json",
            description="Roundtrip test",
            required=False,
        )
        m = AuditManifest(
            schema_version="1.0.0",
            build_id="r1",
            generated_at="now",
            generated_by="test",
            evidence_pack_version="1.0.0",
            files=[entry],
            file_count=1,
            total_size_bytes=100,
            sha256="e" * 64,
        )
        d = manifest_to_dict(m)
        assert d["schema_version"] == "1.0.0"
        assert len(d["files"]) == 1
        assert d["files"][0]["path"] == "test.json"
        assert d["file_count"] == 1

    def test_signature_field(self):
        m = AuditManifest(
            schema_version="1.0.0",
            build_id="sig-test",
            generated_at="now",
            generated_by="test",
            evidence_pack_version="1.0.0",
            files=[],
            file_count=0,
            total_size_bytes=0,
            sha256="f" * 64,
            signature="base64sig",
        )
        assert m.signature == "base64sig"
        d = manifest_to_dict(m)
        assert d["signature"] == "base64sig"


class TestGenerateAuditManifest:
    """generate_audit_manifest() integration tests."""

    @pytest.fixture
    def evidence_dir(self):
        """Create a temporary evidence directory with test files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create standard directory structure
            for sub in ["pipeline", "requirements", "design", "code/review-records",
                        "code/coverage", "test", "release", "artifacts"]:
                (root / sub).mkdir(parents=True)

            # Create files
            (root / "pipeline" / "pipeline-run.json").write_text(
                json.dumps({"status": "passed", "steps": []})
            )
            (root / "requirements" / "traceability.json").write_text(
                json.dumps({"entries": [{"id": "REQ-001", "name": "Test"}]})
            )
            (root / "requirements" / "spec.md").write_text("# Test Spec")
            (root / "test" / "test-results.json").write_text(
                json.dumps({"passed": 10, "failed": 0})
            )
            (root / "code" / "coverage" / "coverage-summary.json").write_text(
                json.dumps({"line_coverage": 0.75, "branch_coverage": 0.60})
            )
            (root / "release" / "release-notes.md").write_text("# Release v1.0")
            (root / "summary.md").write_text("# Evidence Summary")
            yield str(root)

    def test_generates_manifest(self, evidence_dir):
        manifest = generate_audit_manifest(evidence_dir, build_id="test-build-001")
        assert manifest.build_id == "test-build-001"
        assert manifest.schema_version == "1.0.0"
        assert manifest.generated_by == "yuleosh-ev-cli"
        assert manifest.file_count >= 6  # at least 6 files
        assert manifest.sha256 != ""

    def test_includes_all_files(self, evidence_dir):
        manifest = generate_audit_manifest(evidence_dir, "b1")
        paths = {f.path for f in manifest.files}
        assert "pipeline/pipeline-run.json" in paths
        assert "requirements/traceability.json" in paths
        assert "code/coverage/coverage-summary.json" in paths
        assert "summary.md" in paths

    def test_file_hashes_are_valid(self, evidence_dir):
        manifest = generate_audit_manifest(evidence_dir, "b2")
        for entry in manifest.files:
            assert len(entry.sha256) == 64, f"Invalid SHA-256 for {entry.path}"
            # Verify hash matches file content
            fp = Path(evidence_dir) / entry.path
            expected = hashlib.sha256(fp.read_bytes()).hexdigest()
            assert entry.sha256 == expected, f"Hash mismatch for {entry.path}"

    def test_no_files_error(self):
        # Passing a file path (not a directory) should raise NotADirectoryError
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "dummy.txt")
            Path(file_path).write_text("hi")
            with pytest.raises(NotADirectoryError):
                generate_audit_manifest(file_path, "err-test")

    def test_save_and_load_roundtrip(self, evidence_dir):
        manifest = generate_audit_manifest(evidence_dir, "roundtrip")
        manifest_path = os.path.join(evidence_dir, "audit-manifest.json")
        save_manifest(manifest, manifest_path)

        # Verify file exists and is valid JSON
        assert os.path.exists(manifest_path)
        with open(manifest_path) as f:
            data = json.load(f)
        assert data["build_id"] == "roundtrip"
        assert data["file_count"] == manifest.file_count

        # Load back
        loaded = load_manifest(manifest_path)
        assert loaded.build_id == "roundtrip"
        assert loaded.file_count == manifest.file_count
        assert loaded.files[0].path == manifest.files[0].path

    def test_required_files_marked(self, evidence_dir):
        manifest = generate_audit_manifest(evidence_dir, "req-test")
        required = [f for f in manifest.files if f.required]
        assert len(required) > 0
        # pipeline-run.json should be required
        pipeline_entry = next(
            (f for f in manifest.files if "pipeline-run.json" in f.path), None
        )
        if pipeline_entry:
            assert pipeline_entry.required is True

    def test_coverage_warnings(self, evidence_dir):
        # Write a coverage file with critically low value
        cov_path = Path(evidence_dir) / "code" / "coverage" / "coverage-summary.json"
        cov_path.write_text(json.dumps({"line_coverage": 0.014, "branch_coverage": 0.005}))
        manifest = generate_audit_manifest(evidence_dir, "cov-warn")
        assert len(manifest.coverage_warnings) > 0
        has_warning = any("coverage" in w.lower() for w in manifest.coverage_warnings)
        assert has_warning
