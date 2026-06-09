"""Tests for review engine.

Covers: review, agent, blocking, archive, coverage, gate
Scenario-Ref: SDD → DDD → TDD 全流程
"""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "review"))

from run import ReviewFinding, ReviewResult, ReviewSession

def test_review_finding():
    """Test review finding creation."""
    f = ReviewFinding("critical", "architecture", "main.py", 42, "Bad design")
    assert f.severity == "critical"
    assert f.category == "architecture"
    assert f.file == "main.py"
    assert f.line == 42

def test_review_result():
    """Test review result lifecycle."""
    r = ReviewResult("test-task", "arch-reviewer")
    assert r.status == "pending"
    r.add_finding(ReviewFinding("info", "style", "x.py", 1, "Minor"))
    decision = r.decide()
    assert decision in ("passed", "failed", "retry")
    assert r.to_dict()["task"] == "test-task"

def test_review_critical_block():
    """Test critical findings block."""
    r = ReviewResult("test", "reviewer")
    r.add_finding(ReviewFinding("critical", "security", "x.py", 1, "Critical"))
    decision = r.decide()
    assert decision in ("retry", "failed")

def test_review_clean_pass():
    """Test clean review passes."""
    r = ReviewResult("test", "reviewer")
    decision = r.decide()
    assert decision == "passed"

def test_review_session():
    """Test review session aggregation."""
    s = ReviewSession("test-task", os.getcwd())
    r1 = ReviewResult("test", "a")
    r1.status = "passed"
    r2 = ReviewResult("test", "b")
    r2.status = "passed"
    s.add_review(r1)
    s.add_review(r2)
    decision = s.final_decision()
    assert decision == "passed"
