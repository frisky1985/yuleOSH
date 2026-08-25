#!/usr/bin/env python3

# @tests src/yuleosh/alm/traceability.py

"""Deep tests for alm/traceability.py RTM generation — KG-003."""

import pytest
from pathlib import Path

from yuleosh.alm.traceability import (
    generate_lrm,
    compute_trace_integrity,
    scan_req_annotations,
    scan_test_code_links,
)


class TestGenerateLrmAnnotations:
    def test_lrm_with_annotations(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.py").write_text("# @req RS-001\ndef main(): pass\n")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("# @tests src/main.py\ndef test_main(): pass\n")

        spec_file = tmp_path / "spec.md"
        spec_file.write_text("## RS-001\n- The system SHALL run main.\n")

        result = generate_lrm(str(tmp_path), spec_path=str(spec_file))
        assert result is not None
        reqs = result.get("requirements", [])
        assert len(reqs) >= 1

    def test_lrm_returns_dict(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Empty\n")

        result = generate_lrm(str(tmp_path), spec_path=str(spec_file))
        assert isinstance(result, dict)


class TestComputeTraceIntegrity:
    def test_integrity_hash_present(self, tmp_path):
        (tmp_path / ".yuleosh").mkdir()
        session_dir = tmp_path / ".yuleosh" / "sessions" / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "lrt.json").write_text('{"requirements": []}')

        record = compute_trace_integrity(str(tmp_path))
        assert "integrity_hash" in record
        assert "status" in record

    def test_integrity_hash_is_sha256(self, tmp_path):
        (tmp_path / ".yuleosh").mkdir()
        session_dir = tmp_path / ".yuleosh" / "sessions" / "s1"
        session_dir.mkdir(parents=True)
        (session_dir / "lrt.json").write_text('{"requirements": []}')

        record = compute_trace_integrity(str(tmp_path))
        assert len(record["integrity_hash"]) == 64


class TestScanAnnotationsIntegration:
    def test_req_and_tests_chain(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "mod.py").write_text("# @req RS-001\ndef func(): pass\n")

        result = scan_req_annotations(src_dir)
        assert "RS-001" in result
        assert len(result["RS-001"]) >= 1

    def test_tests_link_to_source(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_mod.py").write_text("# @tests src/mod.py\ndef test_func(): pass\n")

        result = scan_test_code_links(tmp_path)
        assert len(result) >= 1
        link = list(result.values())[0]
        assert link["source_file"] == "src/mod.py"
