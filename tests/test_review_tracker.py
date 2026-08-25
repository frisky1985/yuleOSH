"""Tests for review.tracker FindingTracker and modified ReviewFinding/ReviewSession (3A)."""

# @tests src/yuleosh/review/run.py

import json
import tempfile
from pathlib import Path

import pytest

from yuleosh.review.run import ReviewFinding, ReviewResult, ReviewSession
from yuleosh.review.tracker import FindingTracker


@pytest.fixture
def tmp_project(tmp_path):
    return tmp_path


@pytest.fixture
def tracker(tmp_project):
    return FindingTracker(tmp_project, "task-test")


def _make_session_with_findings(task_name="task-x", project_dir="/tmp") -> ReviewSession:
    session = ReviewSession(task_name, project_dir)
    result = ReviewResult(task_name, "code-style-reviewer")
    f1 = ReviewFinding("major", "architecture", "src/foo.c", 10, "function too long")
    f1.req_ids = ["SWR-001"]
    f2 = ReviewFinding("minor", "style", "src/foo.c", 20, "missing docstring")
    f2.req_ids = ["SWR-002"]
    result.findings = [f1, f2]
    result.status = "passed"
    session.add_review(result)
    return session


class TestReviewFindingFields:
    def test_finding_id_generated(self):
        f = ReviewFinding("major", "architecture", "src/a.c", 5, "some issue")
        assert hasattr(f, "finding_id")
        assert isinstance(f.finding_id, str)
        assert len(f.finding_id) == 8

    def test_finding_id_deterministic(self):
        f1 = ReviewFinding("major", "architecture", "src/a.c", 5, "some issue")
        f2 = ReviewFinding("major", "architecture", "src/a.c", 5, "some issue")
        assert f1.finding_id == f2.finding_id

    def test_req_ids_default_empty(self):
        f = ReviewFinding("minor", "style", "src/b.c", 1, "tab found")
        assert f.req_ids == []

    def test_status_default_open(self):
        f = ReviewFinding("minor", "style", "src/b.c", 1, "tab found")
        assert f.status == "open"

    def test_to_dict_includes_new_fields(self):
        f = ReviewFinding("critical", "security", "src/c.c", 99, "buffer overflow")
        f.req_ids = ["RS-001"]
        f.status = "fixed"
        d = f.to_dict()
        assert "finding_id" in d
        assert d["req_ids"] == ["RS-001"]
        assert d["status"] == "fixed"


class TestReviewSessionTraceability:
    def test_to_dict_includes_traceability(self, tmp_project):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        d = session.to_dict()
        assert "traceability" in d

    def test_traceability_maps_req_to_findings(self, tmp_project):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        d = session.to_dict()
        traceability = d["traceability"]
        assert "SWR-001" in traceability
        assert len(traceability["SWR-001"]) >= 1


class TestFindingTrackerRecord:
    def test_record_creates_jsonl(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        findings_file = tmp_project / ".osh" / "reviews" / "task-test" / "findings.jsonl"
        assert findings_file.exists()

    def test_recorded_findings_parseable(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        findings_file = tmp_project / ".osh" / "reviews" / "task-test" / "findings.jsonl"
        lines = findings_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            entry = json.loads(line)
            assert "finding_id" in entry

    def test_append_mode(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        tracker.record_findings(session)
        findings_file = tmp_project / ".osh" / "reviews" / "task-test" / "findings.jsonl"
        lines = [l for l in findings_file.read_text().strip().split("\n") if l]
        assert len(lines) >= 2


class TestFindingTrackerCloseFinding:
    def test_close_finding(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        fid = session.reviews[0].findings[0].finding_id
        result = tracker.close_finding(fid, "fixed in commit abc", "ci")
        assert result is True

    def test_close_nonexistent_returns_false(self, tracker):
        result = tracker.close_finding("deadbeef", "no op", "ci")
        assert result is False

    def test_closed_finding_excluded_from_open(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        fid = session.reviews[0].findings[0].finding_id
        tracker.close_finding(fid, "fixed", "ci")
        open_findings = tracker.get_open_findings()
        assert all(f["finding_id"] != fid for f in open_findings)


class TestFindingTrackerGetOpen:
    def test_get_open_returns_all_initially(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        open_findings = tracker.get_open_findings()
        assert len(open_findings) >= 2

    def test_filter_by_req_id(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        findings = tracker.get_open_findings(req_id="SWR-001")
        assert all("SWR-001" in f.get("req_ids", []) for f in findings)


class TestAutoCloseIfVerified:
    def test_auto_close_on_pass(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        closed = tracker.auto_close_if_verified("SWR-001", {"passed": True})
        assert closed >= 1

    def test_no_close_on_fail(self, tmp_project, tracker):
        session = _make_session_with_findings(project_dir=str(tmp_project))
        session.final_decision()
        tracker.record_findings(session)
        before = len(tracker.get_open_findings(req_id="SWR-001"))
        tracker.auto_close_if_verified("SWR-001", {"passed": False})
        after = len(tracker.get_open_findings(req_id="SWR-001"))
        assert after == before
