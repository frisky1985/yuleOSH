"""Unit tests for yuleosh.ci.result — pure Python, no external deps."""

import pytest
from yuleosh.ci.result import CIResult


class TestCIResult:
    def test_create_default(self):
        r = CIResult(layer=1, commit_hash="abc123")
        assert r.layer == 1
        assert r.commit_hash == "abc123"
        assert r.status == "running"
        assert r.stages == []

    def test_add_stage(self):
        r = CIResult(layer=2, commit_hash="def456")
        r.add_stage(name="lint", status="passed")
        assert len(r.stages) == 1
        assert r.stages[0]["name"] == "lint"

    def test_complete(self):
        r = CIResult(layer=1, commit_hash="abc")
        r.complete(status="passed")
        assert r.status == "passed"
        assert r.completed_at is not None

    def test_to_dict(self):
        r = CIResult(layer=1, commit_hash="abc")
        d = r.to_dict()
        assert d["layer"] == 1
        assert d["status"] == "running"
