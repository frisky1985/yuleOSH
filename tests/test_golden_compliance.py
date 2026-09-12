"""A1-01 golden baseline regression + stability tests (TASK_STATUS T-010).

These tests freeze the current ComplianceChecker output as a golden baseline.
After the A1-05 profile-driven refactor, the checker must still produce
byte-identical normalized output for the same fixture ("--profile aspice_v3.1
输出与重构前逐字节一致" 的前置安全网).

Acceptance (per SPRINT-A1-B1-2026Q4.md A1-01):
  - 重复采集两次逐字节一致 (test_golden_stable)
  - 当前输出与已提交 golden 一致 (test_golden_matches_committed)
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "compliance_sample"
GOLDEN_DIR = ROOT / "tests" / "golden" / "compliance_aspice_v3_1"
GOLDEN = GOLDEN_DIR / "compliance_sample.json"


def _load_collector():
    path = ROOT / "scripts" / "collect_compliance_golden.py"
    spec = importlib.util.spec_from_file_location("collect_compliance_golden", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_golden_stable(tmp_path):
    """Two independent collections must be byte-identical after normalization."""
    mod = _load_collector()
    p1 = tmp_path / "run1.json"
    p2 = tmp_path / "run2.json"
    mod.collect(str(FIXTURE), p1)
    mod.collect(str(FIXTURE), p2)
    assert p1.read_text() == p2.read_text(), "golden collection is non-deterministic"


def test_golden_matches_committed():
    """Current output must match the committed golden baseline."""
    mod = _load_collector()
    fresh = GOLDEN_DIR / ".fresh.json"
    mod.collect(str(FIXTURE), fresh)
    try:
        current = fresh.read_text(encoding="utf-8")
        assert GOLDEN.exists(), (
            f"golden missing: {GOLDEN} — run: "
            f"python scripts/collect_compliance_golden.py "
            f"--project tests/fixtures/compliance_sample "
            f"--out tests/golden/compliance_aspice_v3_1/compliance_sample.json"
        )
        committed = GOLDEN.read_text(encoding="utf-8")
        assert current == committed, "compliance output drifted from golden baseline"
    finally:
        fresh.unlink(missing_ok=True)
