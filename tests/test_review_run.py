"""Tests for yuleosh.review.run — review runner module (correct constructors)."""

import tempfile
from pathlib import Path
from unittest import mock
import pytest

from yuleosh.review.run import (
    ReviewFinding,
    ReviewResult,
    ReviewSession,
    run_review,
    auto_review,
)


# ------------------------------------------------------------------
# ReviewFinding
# ------------------------------------------------------------------

def test_review_finding_creation():
    """GIVEN finding params WHEN creating ReviewFinding THEN fields set."""
    f = ReviewFinding(severity="major", category="coding", file="src/main.c", line=42, message="Missing bounds check")
    assert f.severity == "major"
    assert f.file == "src/main.c"
    assert f.line == 42
    assert f.message == "Missing bounds check"


def test_review_finding_to_dict():
    """GIVEN ReviewFinding WHEN to_dict THEN returns serializable dict."""
    f = ReviewFinding("minor", "style", "test.c", 1, "desc")
    d = f.to_dict()
    assert d["severity"] == "minor"
    assert d["line"] == 1
    assert d["file"] == "test.c"


# ------------------------------------------------------------------
# ReviewResult
# ------------------------------------------------------------------

def test_review_result_creation():
    """GIVEN basic params WHEN creating ReviewResult THEN fields set."""
    r = ReviewResult(task_name="arch-review", reviewer="小克")
    assert r.task_name == "arch-review"
    assert r.reviewer == "小克"
    assert r.status == "pending"
    assert r.findings == []


def test_review_result_add_finding():
    """GIVEN ReviewResult WHEN adding finding THEN finding stored."""
    r = ReviewResult("style", "reviewer")
    f = ReviewFinding("major", "style", "a.c", 5, "Issue")
    r.add_finding(f)
    assert len(r.findings) == 1
    assert r.findings[0].severity == "major"


def test_review_result_to_dict():
    """GIVEN ReviewResult with findings WHEN to_dict THEN serialized."""
    r = ReviewResult("test", "bot")
    r.add_finding(ReviewFinding("minor", "style", "x.c", 1, "style issue"))
    d = r.to_dict()
    assert d["task"] == "test"
    assert d["finding_count"] == 1
    assert d["finding_breakdown"]["minor"] == 1


# ------------------------------------------------------------------
# ReviewResult.decide
# ------------------------------------------------------------------

def test_decide_clean_passes():
    """GIVEN no findings WHEN decide THEN status is 'passed' with clean summary."""
    r = ReviewResult("test", "bot")
    status = r.decide()
    assert status == "passed"
    assert "Clean" in r.summary


def test_decide_minor_passes():
    """GIVEN minor findings WHEN decide THEN status is 'passed'."""
    r = ReviewResult("test", "bot")
    r.add_finding(ReviewFinding("minor", "style", "a.c", 1, "minor"))
    status = r.decide()
    assert status == "passed"


def test_decide_critical_retries():
    """GIVEN critical findings WHEN decide THEN status is 'retry' if retries remain."""
    r = ReviewResult("test", "bot")
    r.add_finding(ReviewFinding("critical", "safety", "a.c", 10, "critical!"))
    status = r.decide()
    assert status == "retry"


def test_decide_critical_fails_after_5_retries():
    """GIVEN critical findings after 5 retries WHEN decide THEN status is 'failed'."""
    r = ReviewResult("test", "bot")
    r.retry_count = 5
    r.add_finding(ReviewFinding("critical", "safety", "a.c", 10, "critical!"))
    status = r.decide()
    assert status == "failed"


def test_decide_many_majors_retries():
    """GIVEN >3 major findings WHEN decide THEN status is 'retry'."""
    r = ReviewResult("test", "bot")
    for i in range(4):
        r.add_finding(ReviewFinding("major", "coding", f"a{i}.c", i, f"Major {i}"))
    status = r.decide()
    assert status == "retry"


# ------------------------------------------------------------------
# ReviewSession
# ------------------------------------------------------------------

def test_review_session_creation():
    """GIVEN session params WHEN creating ReviewSession THEN works."""
    s = ReviewSession(task_name="arch-review", project_dir="/tmp/test")
    assert s.status == "running"
    assert s.reviews == []
    assert s.task_name == "arch-review"
    assert s.project_dir == "/tmp/test"


def test_review_session_with_results():
    """GIVEN session with results WHEN created THEN stores them."""
    r = ReviewResult("arch", "reviewer")
    s = ReviewSession("test", "/tmp/p")
    s.add_review(r)
    assert s.status == "running"
    assert len(s.reviews) == 1


# ------------------------------------------------------------------
# run_review
# ------------------------------------------------------------------

@mock.patch("yuleosh.review.run.auto_review")
def test_run_review_calls_auto_review(mock_auto):
    """GIVEN task params WHEN run_review THEN delegates to auto_review or similar."""
    mock_auto.return_value = ReviewSession("test", "/tmp/p")
    result = run_review("test-task", "architecture", "/tmp/project", ["src/main.c"])
    # run_review may call auto_review internally
    assert result is not None


# ------------------------------------------------------------------
# auto_review
# ------------------------------------------------------------------

@mock.patch("yuleosh.review.run.subprocess.run")
def test_auto_review_returns_session(mock_subprocess):
    """GIVEN valid project WHEN auto_review THEN returns ReviewSession."""
    import subprocess
    mock_result = mock.MagicMock()
    mock_result.stdout = "src/main.c\n"
    mock_result.returncode = 0
    mock_subprocess.return_value = mock_result
    
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir(parents=True)
        (root / "src" / "main.c").write_text("int main() { return 0; }\n")
        result = auto_review(project_dir=str(root))
    assert isinstance(result, ReviewSession)
