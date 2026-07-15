"""Tests for ci/agent_traceability.py — Agent Traceability (G-47)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from yuleosh.ci.agent_traceability import (
    record_review, get_reviews_for_commit, get_commits_for_review,
    get_findings_for_file, get_reviews_by_build,
    show_traceability, validate_traceability_file,
    _generate_review_id, _ensure_trace_dir, TRACE_FILE,
)


class TestGenerateReviewId:
    def test_format(self):
        rid = _generate_review_id()
        assert rid.startswith("RVW-")
        parts = rid.split("-")
        assert len(parts) >= 4

    def test_unique(self):
        ids = {_generate_review_id() for _ in range(10)}
        assert len(ids) == 10


class TestEnsureTraceDir:
    def test_creates_dir(self):
        with tempfile.TemporaryDirectory() as td:
            path = _ensure_trace_dir(td)
            assert path.parent.exists()
            assert path.name == "agent-traceability.jsonl"


class TestRecordReview:
    def test_record_minimal(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_review(td)
            assert "review_id" in entry
            assert entry["finding_count"] == 0

    def test_record_with_findings(self):
        with tempfile.TemporaryDirectory() as td:
            findings = [
                {"file": "src/main.c", "line": 42, "severity": "major", "message": "null deref"},
                {"file": "src/utils.c", "line": 10, "severity": "info", "message": "style"},
            ]
            entry = record_review(td, review_type="code-review",
                                    findings=findings,
                                    agent_name="小克")
            assert entry["finding_count"] == 2
            assert entry["review_type"] == "code-review"
            assert entry["agent_name"] == "小克"
            assert entry["findings"][0]["location"] == "src/main.c:42"

    def test_record_with_build_id(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_review(td, build_id="build-001")
            assert entry["build_id"] == "build-001"

    def test_record_with_extra(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_review(td, extra={"custom_field": "value"})
            assert entry["custom_field"] == "value"


class TestGetReviewsForCommit:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = get_reviews_for_commit(td, "abc123")
            assert result == []

    def test_matches_commit(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, commit="abc123def456")
            record_review(td, commit="xyz789")
            result = get_reviews_for_commit(td, "abc123")
            assert len(result) == 1

    def test_prefix_matching(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, commit="abcdef123456")
            result = get_reviews_for_commit(td, "abc")
            assert len(result) == 1

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, commit="abc123")
            result = get_reviews_for_commit(td, "xyz")
            assert result == []


class TestGetCommitsForReview:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = get_commits_for_review(td, "RVW-123")
            assert result == []

    def test_matches_review_id(self):
        with tempfile.TemporaryDirectory() as td:
            entry = record_review(td, commit="abc123")
            rid = entry["review_id"]
            result = get_commits_for_review(td, rid)
            assert len(result) == 1
            assert result[0]["commit"] == "abc123"


class TestGetFindingsForFile:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = get_findings_for_file(td, "main.c")
            assert result == []

    def test_matches_file(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, findings=[
                {"file": "src/main.c", "line": 10, "severity": "critical", "message": "bug"},
            ])
            result = get_findings_for_file(td, "main.c")
            assert len(result) >= 1

    def test_substring_matching(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, findings=[
                {"file": "src/utils/helper.c", "line": 5, "severity": "minor", "message": "lint"},
            ])
            result = get_findings_for_file(td, "helper.c")
            assert len(result) >= 1

    def test_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, findings=[{"file": "a.c", "line": 1}])
            result = get_findings_for_file(td, "b.c")
            assert result == []


class TestGetReviewsByBuild:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = get_reviews_by_build(td, "build-001")
            assert result == []

    def test_matches_build(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, build_id="build-001")
            record_review(td, build_id="build-002")
            result = get_reviews_by_build(td, "build-001")
            assert len(result) == 1

    def test_prefix_matching(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, build_id="build-001-extra")
            result = get_reviews_by_build(td, "build-001")
            assert len(result) == 1


class TestShowTraceability:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = show_traceability(td)
            assert "No traceability" in result

    def test_with_entries_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, review_type="arch-review", agent_name="小马",
                          findings=[{"file": "a.c", "line": 1}])
            result = show_traceability(td)
            assert "Traceability" in result
            assert "arch-review" in result

    def test_as_json(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td, review_type="code-review")
            result = show_traceability(td, as_json=True)
            data = json.loads(result)
            assert isinstance(data, list)
            assert len(data) >= 1


class TestValidateTraceabilityFile:
    def test_no_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = validate_traceability_file(td)
            assert result["valid"] is True
            assert result["entry_count"] == 0

    def test_valid_file(self):
        with tempfile.TemporaryDirectory() as td:
            record_review(td)
            result = validate_traceability_file(td)
            assert result["valid"] is True
            assert result["entry_count"] == 1

    def test_invalid_entry(self):
        with tempfile.TemporaryDirectory() as td:
            trace_dir = Path(td) / ".yuleosh" / "reports"
            trace_dir.mkdir(parents=True, exist_ok=True)
            (trace_dir / "agent-traceability.jsonl").write_text("not-json\n")
            result = validate_traceability_file(td)
            assert result["valid"] is False
            assert len(result["issues"]) >= 1
