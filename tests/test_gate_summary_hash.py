
# @tests src/yuleosh/pipeline/gates.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for gate-summary artifact hashes (Q3-d).

Verifies that write_gate_summary() embeds per-step artifact_hashes in each
gate entry when the corresponding step output files exist in session_dir.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from yuleosh.pipeline.gates import write_gate_summary, GATES


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture()
def fake_session(tmp_path):
    return SimpleNamespace(
        name="test-sess",
        session_dir=tmp_path,
        steps=[],
    )


class TestGateSummaryArtifactHashes:

    def test_no_artifact_files_produces_no_hashes(self, fake_session, tmp_path):
        """When no step artifact files exist, gate entries have no artifact_hashes."""
        out = write_gate_summary(fake_session)
        summary = json.loads(Path(out).read_text())
        for gate in summary["gates"]:
            assert "artifact_hashes" not in gate

    def test_existing_artifact_file_hash_in_gate_entry(self, fake_session, tmp_path):
        """A present step artifact file appears in the gate's artifact_hashes."""
        # Find a gate and one of its step keys
        gate_def = GATES[0]
        step_key = gate_def["step_keys"][0]

        artifact = tmp_path / f"{step_key}.json"
        artifact.write_text('{"status":"passed"}', encoding="utf-8")
        expected = _sha256(artifact)

        out = write_gate_summary(fake_session)
        summary = json.loads(Path(out).read_text())

        # Find the matching gate
        target_gate = next(g for g in summary["gates"] if g["gate"] == gate_def["gate"])
        assert "artifact_hashes" in target_gate
        assert target_gate["artifact_hashes"][step_key] == expected

    def test_only_present_files_included_in_hashes(self, fake_session, tmp_path):
        """Only step keys with existing files appear in artifact_hashes."""
        gate_def = GATES[0]
        step_key = gate_def["step_keys"][0]

        artifact = tmp_path / f"{step_key}.json"
        artifact.write_text('{"step":"present"}', encoding="utf-8")

        out = write_gate_summary(fake_session)
        summary = json.loads(Path(out).read_text())

        target_gate = next(g for g in summary["gates"] if g["gate"] == gate_def["gate"])
        hashes = target_gate.get("artifact_hashes", {})
        # Only the present step should be in hashes
        assert step_key in hashes
        for other_key in gate_def["step_keys"][1:]:
            assert other_key not in hashes

    def test_hash_changes_when_file_content_changes(self, fake_session, tmp_path):
        """If a step artifact is modified, the hash in gate-summary changes."""
        gate_def = GATES[0]
        step_key = gate_def["step_keys"][0]
        artifact = tmp_path / f"{step_key}.json"

        artifact.write_text('{"status":"passed"}', encoding="utf-8")
        out1 = write_gate_summary(fake_session)
        s1 = json.loads(Path(out1).read_text())
        gate1 = next(g for g in s1["gates"] if g["gate"] == gate_def["gate"])
        hash1 = gate1["artifact_hashes"][step_key]

        artifact.write_text('{"status":"failed","reason":"regression"}', encoding="utf-8")
        out2 = write_gate_summary(fake_session)
        s2 = json.loads(Path(out2).read_text())
        gate2 = next(g for g in s2["gates"] if g["gate"] == gate_def["gate"])
        hash2 = gate2["artifact_hashes"][step_key]

        assert hash1 != hash2

    def test_multiple_gates_with_artifacts(self, fake_session, tmp_path):
        """Multiple gates each include their own artifact_hashes independently."""
        # Write artifacts for first step of first two gates
        created = {}
        for gate_def in GATES[:2]:
            step_key = gate_def["step_keys"][0]
            artifact = tmp_path / f"{step_key}.json"
            artifact.write_text(f'{{"gate":"{gate_def["gate"]}"}}', encoding="utf-8")
            created[gate_def["gate"]] = (step_key, _sha256(artifact))

        out = write_gate_summary(fake_session)
        summary = json.loads(Path(out).read_text())

        for gate_def in GATES[:2]:
            gate_entry = next(g for g in summary["gates"] if g["gate"] == gate_def["gate"])
            step_key, expected_hash = created[gate_def["gate"]]
            assert gate_entry["artifact_hashes"][step_key] == expected_hash

    def test_gate_summary_schema_unchanged(self, fake_session, tmp_path):
        """Existing gate-summary fields are preserved after adding artifact_hashes."""
        out = write_gate_summary(fake_session)
        summary = json.loads(Path(out).read_text())

        assert summary["schema"] == "gate-summary-v1"
        assert "session" in summary
        assert "timestamp" in summary
        assert "worst_gate_status" in summary
        assert "gates" in summary
        for gate in summary["gates"]:
            assert "gate" in gate
            assert "name" in gate
            assert "status" in gate
            assert "step_keys" in gate

    def test_no_session_dir_raises_without_output_path(self):
        """Missing session_dir raises ValueError when output_path not provided."""
        session = SimpleNamespace(name="no-dir", steps=[])
        with pytest.raises(ValueError, match="session has no session_dir"):
            write_gate_summary(session)
