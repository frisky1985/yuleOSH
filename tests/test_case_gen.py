
# @tests src/yuleosh/pipeline/step_handlers/test_case_gen.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for the deterministic test case generator (Q6-d).

Verifies:
- GIVEN/WHEN/THEN scenarios are parsed from spec text
- Each test case has test_id = {req_id}::{scenario_id}
- req_ids extracted from blocks
- Multiple scenarios → multiple test cases
- Empty spec → status=empty, test_cases=[]
- step_test_case_gen writes test-cases.json to session_dir
- session.artifacts["test-cases"] set correctly
- No-spec-path session → skipped output
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.pipeline.step_handlers.test_case_gen import (
    run_test_case_gen,
    step_test_case_gen,
    _scenario_id,
    _extract_req_ids,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def spec_file(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# System Spec\n\n"
        "## RS-001: Initialization\n\n"
        "GIVEN the system is powered on\n"
        "WHEN the main() function is called\n"
        "THEN the system shall initialize within 100ms\n\n"
        "## RS-002: Communication\n\n"
        "GIVEN a UART connection is established\n"
        "WHEN a valid frame is received\n"
        "THEN the system shall acknowledge within 10ms\n",
        encoding="utf-8",
    )
    return spec


@pytest.fixture()
def fake_session(tmp_path, spec_file):
    artifacts = {}
    return SimpleNamespace(
        name="sess-test",
        session_dir=tmp_path,
        spec_path=str(spec_file),
        artifacts=artifacts,
    )


# ── Tests: run_test_case_gen ─────────────────────────────────────────────────

class TestRunTestCaseGen:

    def test_basic_scenario_parsed(self, spec_file):
        result = run_test_case_gen(str(spec_file))
        assert result["test_count"] >= 1
        assert result["status"] == "ok"

    def test_two_scenarios_produce_two_cases(self, spec_file):
        result = run_test_case_gen(str(spec_file))
        assert result["test_count"] == 2

    def test_test_id_format(self, spec_file):
        """test_id must be {req_id}::{scenario_id}."""
        result = run_test_case_gen(str(spec_file))
        for tc in result["test_cases"]:
            assert "::" in tc["test_id"], f"test_id missing '::': {tc['test_id']}"
            req_part, sc_part = tc["test_id"].split("::", 1)
            assert req_part.startswith("R") or req_part.startswith("S") or req_part == "REQ-UNKNOWN"
            assert sc_part.startswith("SC-")

    def test_req_id_extracted_from_block(self, spec_file):
        """req_ids extracted from requirement header in block."""
        result = run_test_case_gen(str(spec_file))
        req_ids_found = [tc["req_id"] for tc in result["test_cases"]]
        assert any("RS-001" in r or "RS-002" in r for r in req_ids_found)

    def test_preconditions_contains_given(self, spec_file):
        """preconditions list populated from GIVEN lines."""
        result = run_test_case_gen(str(spec_file))
        tc = result["test_cases"][0]
        assert len(tc["preconditions"]) > 0
        assert any("power" in p.lower() or "system" in p.lower()
                   for p in tc["preconditions"])

    def test_steps_contains_when(self, spec_file):
        """steps list populated from WHEN line."""
        result = run_test_case_gen(str(spec_file))
        tc = result["test_cases"][0]
        assert len(tc["steps"]) > 0

    def test_expected_contains_then(self, spec_file):
        """expected list populated from THEN line."""
        result = run_test_case_gen(str(spec_file))
        tc = result["test_cases"][0]
        assert len(tc["expected"]) > 0

    def test_status_generated(self, spec_file):
        """Each test case has status='generated'."""
        result = run_test_case_gen(str(spec_file))
        for tc in result["test_cases"]:
            assert tc["status"] == "generated"

    def test_empty_spec_returns_empty(self, tmp_path):
        """Empty spec file → status=empty, test_cases=[]."""
        spec = tmp_path / "empty.md"
        spec.write_text("# No scenarios here\n", encoding="utf-8")
        result = run_test_case_gen(str(spec))
        assert result["status"] == "empty"
        assert result["test_cases"] == []
        assert result["test_count"] == 0

    def test_missing_spec_file_does_not_raise(self, tmp_path):
        """Missing spec file → returns empty result, no exception."""
        result = run_test_case_gen(str(tmp_path / "nonexistent.md"))
        assert result["test_count"] == 0

    def test_result_has_required_keys(self, spec_file):
        """Result dict has all required keys."""
        result = run_test_case_gen(str(spec_file))
        for key in ("session", "spec_path", "generated_at", "test_count", "status", "test_cases"):
            assert key in result

    def test_deterministic_on_same_spec(self, spec_file):
        """Two calls on the same spec produce identical test_id sets."""
        r1 = run_test_case_gen(str(spec_file))
        r2 = run_test_case_gen(str(spec_file))
        ids1 = {tc["test_id"] for tc in r1["test_cases"]}
        ids2 = {tc["test_id"] for tc in r2["test_cases"]}
        assert ids1 == ids2


# ── Tests: step_test_case_gen ─────────────────────────────────────────────────

class TestStepTestCaseGen:

    def test_writes_test_cases_json(self, fake_session, tmp_path):
        """step writes test-cases.json to session_dir."""
        out = step_test_case_gen(fake_session)
        assert Path(out).name == "test-cases.json"
        assert Path(out).exists()

    def test_output_is_valid_json(self, fake_session):
        out = step_test_case_gen(fake_session)
        data = json.loads(Path(out).read_text())
        assert "test_cases" in data

    def test_sets_artifacts_key(self, fake_session):
        """session.artifacts['test-cases'] is set to the output path."""
        step_test_case_gen(fake_session)
        assert "test-cases" in fake_session.artifacts
        assert fake_session.artifacts["test-cases"].endswith("test-cases.json")

    def test_no_spec_path_produces_skipped(self, tmp_path):
        """Session with no spec_path → skipped output, no exception."""
        session = SimpleNamespace(
            name="sess-nopec",
            session_dir=tmp_path,
            spec_path="",
            artifacts={},
        )
        out = step_test_case_gen(session)
        data = json.loads(Path(out).read_text())
        assert data["status"] == "skipped"
        assert data["test_cases"] == []


# ── Tests: helpers ────────────────────────────────────────────────────────────

class TestHelpers:

    def test_extract_req_ids_finds_rs_ids(self):
        text = "RS-001 and RS-002 are related to this scenario."
        ids = _extract_req_ids(text)
        assert "RS-001" in ids
        assert "RS-002" in ids

    def test_extract_req_ids_deduplicates(self):
        text = "RS-001 appears RS-001 twice"
        ids = _extract_req_ids(text)
        assert ids.count("RS-001") == 1

    def test_extract_req_ids_empty_text(self):
        assert _extract_req_ids("") == []

    def test_scenario_id_stable(self):
        """Same index+when produces same scenario_id."""
        s1 = _scenario_id(0, "the system receives a frame")
        s2 = _scenario_id(0, "the system receives a frame")
        assert s1 == s2

    def test_scenario_id_starts_with_sc(self):
        s = _scenario_id(0, "initialize")
        assert s.startswith("SC-")
