"""Tests for kb.codegen_failures CodegenFailureStore (2B)."""

# @tests src/yuleosh/kb/codegen_failures.py

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.kb.codegen_failures import CodegenFailureCase, CodegenFailureStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_failures.db")
    return CodegenFailureStore(db_path=db_path)


def _make_result(status="failed", error_text="undefined reference to `HAL_Init'", rounds=3):
    result = MagicMock()
    result.status = status
    # Field names must mirror the real CodegenResult (codegen/engine.py):
    # last_errors (str), brainstorm (dict), rounds (int).
    result.last_errors = error_text
    result.rounds = rounds
    result.brainstorm = {"strategy": "brainstorm"}
    return result


class TestCodegenFailureCaseFields:
    def test_dataclass_fields(self):
        case = CodegenFailureCase(
            id=1,
            project_id="proj-a",
            session_id="sess-001",
            error_signature="abc123",
            error_text="compile error",
            language="c",
            round_count=3,
            strategy_used="brainstorm",
            resolution="",
            created_at="2026-01-01T00:00:00",
        )
        assert case.project_id == "proj-a"
        assert case.error_signature == "abc123"
        assert case.round_count == 3


class TestRecordFailure:
    def test_records_failed_result(self, store):
        result = _make_result(status="failed", error_text="undefined reference to HAL_Init")
        store.record_failure("proj-a", "sess-001", result, "c")
        cases = store.find_similar("undefined reference", "c", limit=10)
        assert len(cases) >= 1
        assert "HAL_Init" in cases[0].error_text or "undefined" in cases[0].error_text

    def test_skips_successful_result(self, store):
        result = _make_result(status="success")
        store.record_failure("proj-a", "sess-002", result, "c")
        cases = store.find_similar("", "c", limit=10)
        assert len(cases) == 0

    def test_deduplicates_same_error(self, store):
        error = "undefined reference to `main'"
        result1 = _make_result(error_text=error)
        result2 = _make_result(error_text=error)
        store.record_failure("proj-a", "sess-001", result1, "c")
        store.record_failure("proj-a", "sess-002", result2, "c")
        cases = store.find_similar(error, "c", limit=10)
        assert len(cases) == 1

    def test_allows_different_projects_same_error(self, store):
        error = "implicit declaration of function"
        result = _make_result(error_text=error)
        store.record_failure("proj-a", "sess-001", result, "c")
        store.record_failure("proj-b", "sess-002", result, "c")
        cases = store.find_similar(error, "c", limit=10)
        assert len(cases) == 2


class TestRecordResolution:
    def test_updates_resolution(self, store):
        result = _make_result(error_text="stack overflow in ISR")
        store.record_failure("proj-a", "sess-001", result, "c")
        store.record_resolution("sess-001", "reduced stack usage by moving buffers to static")
        cases = store.find_similar("stack overflow", "c", limit=10)
        assert cases[0].resolution != ""

    def test_no_error_on_unknown_session(self, store):
        store.record_resolution("nonexistent-sess", "some fix")  # should not raise


class TestFindSimilar:
    def test_empty_store_returns_empty(self, store):
        cases = store.find_similar("any error", "c", limit=5)
        assert cases == []

    def test_language_filter(self, store):
        result_c = _make_result(error_text="malloc not allowed")
        result_py = _make_result(error_text="malloc not allowed")
        store.record_failure("proj-a", "sess-c", result_c, "c")
        store.record_failure("proj-b", "sess-py", result_py, "python")
        cases = store.find_similar("malloc", "c", limit=10)
        assert all(c.language == "c" for c in cases)

    def test_limit_respected(self, store):
        for i in range(5):
            r = _make_result(error_text=f"error variant {i} linker fail")
            store.record_failure(f"proj-{i}", f"sess-{i}", r, "c")
        cases = store.find_similar("linker fail", "c", limit=3)
        assert len(cases) <= 3


class TestFormatForPrompt:
    def test_returns_string(self, store):
        result = _make_result(error_text="watchdog not kicking in ISR context")
        store.record_failure("proj-a", "sess-001", result, "c")
        cases = store.find_similar("watchdog", "c", limit=5)
        text = store.format_for_prompt(cases)
        assert isinstance(text, str)
        assert len(text) > 0

    def test_empty_cases_returns_empty_or_placeholder(self, store):
        text = store.format_for_prompt([])
        assert isinstance(text, str)

    def test_respects_max_chars(self, store):
        cases = []
        for i in range(10):
            cases.append(CodegenFailureCase(
                id=i, project_id="p", session_id=f"s{i}",
                error_signature=f"sig{i}",
                error_text="x" * 500,
                language="c", round_count=1,
                strategy_used="", resolution="",
                created_at="2026-01-01T00:00:00",
            ))
        text = store.format_for_prompt(cases, max_chars=500)
        assert len(text) <= 600  # some tolerance for headers
