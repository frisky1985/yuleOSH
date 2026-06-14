"""Smoke tests for review/ module — run, c_review, resource_predictor."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json
import tempfile
from pathlib import Path

from yuleosh.review.run import (
    ReviewFinding, ReviewResult, ReviewSession,
    review_architecture, review_domain_modeling, review_code_style,
    review_coverage, run_review, auto_review, REVIEWER_MAP,
)
from yuleosh.review.resource_predictor import (
    predict_resources, predict_all_in_project,
    _detect_platform, _count_global_ram, _count_rom_estimate,
    _assess_stack_risk, _estimate_isr_latency,
)


class TestReviewFinding:
    """Smoke tests for ReviewFinding."""

    def test_create(self):
        rf = ReviewFinding("critical", "architecture", "main.c", 42, "Missing volatile")
        assert rf.severity == "critical"
        assert rf.category == "architecture"
        assert rf.file == "main.c"
        assert rf.line == 42

    def test_to_dict(self):
        rf = ReviewFinding("major", "style", "file.py", 10, "Too long")
        d = rf.to_dict()
        assert d["severity"] == "major"
        assert d["line"] == 10


class TestReviewResult:
    """Smoke tests for ReviewResult."""

    def test_create(self):
        rr = ReviewResult("task-1", "arch-reviewer")
        assert rr.task_name == "task-1"
        assert rr.status == "pending"
        assert rr.findings == []

    def test_add_finding(self):
        rr = ReviewResult("task-1", "reviewer")
        rr.add_finding(ReviewFinding("critical", "arch", "f.c", 1, "msg"))
        assert len(rr.findings) == 1

    def test_decide_clean(self):
        rr = ReviewResult("task-1", "reviewer")
        assert rr.decide() == "passed"
        assert rr.summary == "Clean — no issues found"

    def test_decide_with_majors_passes(self):
        rr = ReviewResult("task-1", "reviewer")
        rr.add_finding(ReviewFinding("major", "style", "f.c", 1, "style issue"))
        assert rr.decide() == "passed"

    def test_decide_more_than_3_majors_retry(self):
        rr = ReviewResult("task-1", "reviewer")
        for i in range(4):
            rr.add_finding(ReviewFinding("major", "style", "f.c", i, f"issue {i}"))
        assert rr.decide() == "retry"

    def test_decide_critical_fails_after_retries(self):
        rr = ReviewResult("task-1", "reviewer")
        rr.retry_count = 5
        rr.add_finding(ReviewFinding("critical", "arch", "f.c", 1, "CRITICAL"))
        assert rr.decide() == "failed"
        assert "Failed after 5 retries" in rr.summary

    def test_to_dict(self):
        rr = ReviewResult("task-1", "r1")
        rr.add_finding(ReviewFinding("info", "style", "f.py", 1, "info"))
        rr.decide()
        d = rr.to_dict()
        assert d["finding_breakdown"]["info"] == 1


class TestReviewSession:
    """Smoke tests for ReviewSession."""

    def test_create(self):
        rs = ReviewSession("task-1", "/tmp/project")
        assert rs.task_name == "task-1"
        assert rs.status == "running"

    def test_add_review(self):
        rs = ReviewSession("task-1", "/tmp/project")
        rr = ReviewResult("task-1", "r1")
        rs.add_review(rr)
        assert len(rs.reviews) == 1

    def test_final_decision_all_pass(self):
        rs = ReviewSession("task-1", "/tmp/project")
        r1 = ReviewResult("task-1", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task-1", "r2")
        r2.status = "passed"
        rs.add_review(r1)
        rs.add_review(r2)
        assert rs.final_decision() == "passed"

    def test_final_decision_any_failed(self):
        rs = ReviewSession("task-1", "/tmp/project")
        r1 = ReviewResult("task-1", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task-1", "r2")
        r2.status = "failed"
        rs.add_review(r1)
        rs.add_review(r2)
        assert rs.final_decision() == "failed"

    def test_final_decision_no_reviews(self):
        rs = ReviewSession("task-1", "/tmp/project")
        assert rs.final_decision() == "failed"

    def test_save(self, tmp_path):
        rs = ReviewSession("test-task", str(tmp_path))
        r1 = ReviewResult("test-task", "r1")
        r1.status = "passed"
        rs.add_review(r1)
        rs.final_decision()
        rs.save()
        saved_file = tmp_path / ".osh" / "reviews" / "test-task" / "review-session.json"
        assert saved_file.exists()
        data = json.loads(saved_file.read_text())
        assert data["decision"] == "passed"

    def test_to_dict(self):
        rs = ReviewSession("task-1", "/tmp")
        r1 = ReviewResult("task-1", "r1")
        r1.status = "passed"
        rs.add_review(r1)
        rs.final_decision()
        d = rs.to_dict()
        assert d["decision"] == "passed"
        assert len(d["reviews"]) == 1


class TestReviewers:
    """Smoke tests for reviewer functions."""

    def test_review_architecture_no_src(self, tmp_path):
        result = review_architecture("task", str(tmp_path), [])
        assert result.status == "passed"
        assert "No source directory" in result.summary

    def test_review_architecture_with_src(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text(
            "def hello():\n    x = 1\n    return x\n"
        )
        result = review_architecture("task", str(tmp_path), [])
        assert result.status in ("passed", "retry", "failed")
        assert isinstance(result.summary, str)

    def test_review_domain_modeling_no_src(self, tmp_path):
        result = review_domain_modeling("task", str(tmp_path), [])
        assert result.status == "passed"

    def test_review_domain_modeling_with_mutable_default(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text(
            "class Config:\n    def __init__(self, items=[]):\n        pass\n"
        )
        result = review_domain_modeling("task", str(tmp_path), [])
        assert result.status in ("passed", "retry", "failed")

    def test_review_code_style_no_src(self, tmp_path):
        result = review_code_style("task", str(tmp_path), [])
        assert result.status == "passed"

    def test_review_code_style_with_missing_docstring(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "nodoc.py").write_text(
            "def run():\n    pass\n"
        )
        result = review_code_style("task", str(tmp_path), [])
        assert result.status in ("passed", "retry", "failed")

    def test_review_coverage_subprocess_fails(self, tmp_path):
        result = review_coverage("task", str(tmp_path), [])
        assert result.status in ("passed", "failed", "retry")

    def test_review_coverage_subprocess_success(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            (tmp_path / "coverage.json").write_text(
                json.dumps({"totals": {"percent_covered": 85.0}})
            )
            result = review_coverage("task", str(tmp_path), [])
            assert result is not None

    def test_reviewer_map_contains_keys(self):
        assert "feature" in REVIEWER_MAP
        assert "bugfix" in REVIEWER_MAP
        assert "docs" in REVIEWER_MAP
        assert "embedded" in REVIEWER_MAP


class TestRunReview:
    """Smoke tests for run_review orchestrator."""

    def test_run_review_no_reviewers_for_kind(self, tmp_path):
        session = run_review("doc-task", "docs", str(tmp_path), [])
        assert session.decision == "passed"

    def test_run_review_feature(self, tmp_path):
        # Feature kind has reviewers
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            session = run_review("feature-task", "feature", str(tmp_path), [])
            assert session.status == "completed"
            assert session.decision in ("passed", "failed", "retry")


class TestResourcePredictor:
    """Smoke tests for resource_predictor.py."""

    def test_predict_resources_file_not_found(self):
        result = predict_resources("/nonexistent/file.c")
        assert "N/A" in result["ram_estimate"]

    def test_predict_resources_simple(self, tmp_path):
        c_file = tmp_path / "test.c"
        c_file.write_text("int x = 5;")
        result = predict_resources(str(c_file))
        assert "ram_estimate" in result
        assert "rom_estimate" in result
        assert "stack_risk" in result
        assert "isr_latency" in result
        assert "suggestions" in result

    def test_predict_resources_with_code(self, tmp_path):
        c_file = tmp_path / "firmware.c"
        c_file.write_text("""
#include <stdint.h>
static uint8_t buffer[256];
void main(void) {
    volatile int i;
    for (i = 0; i < 1000; i++);
}
""")
        result = predict_resources(str(c_file))
        assert isinstance(result["ram_estimate"], str)
        assert isinstance(result["stack_risk"], str)

    def test_detect_platform(self):
        assert _detect_platform("#include <STM32F4xx.h>") == "cortex_m4"
        assert _detect_platform("#include <esp_wifi.h>") == "esp32"
        assert _detect_platform("") == "cortex_m4"  # default

    def test_count_global_ram(self):
        ram = _count_global_ram("static uint32_t my_var;\nint counter;")
        assert ram > 0

    def test_count_rom_estimate(self):
        rom = _count_rom_estimate("void func() { int a = 1; }")
        assert rom > 0

    def test_assess_stack_risk_low(self):
        risk = _assess_stack_risk("void f() { int x; }")
        assert risk == "低"

    def test_assess_stack_risk_high(self):
        risk = _assess_stack_risk("void f() { uint8_t buf[1024]; }")
        assert risk in ("高", "中")

    def test_estimate_isr_latency_default(self):
        latency = _estimate_isr_latency("", "cortex_m4")
        assert "μs" in latency

    def test_estimate_isr_latency_with_critical_section(self):
        latency = _estimate_isr_latency("__disable_irq()\n/* critical */\na+=1;\n__enable_irq()", "cortex_m4")
        assert "μs" in latency

    def test_predict_all_in_project(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "file.c").write_text("int main() { return 0; }")
        results = predict_all_in_project(str(tmp_path))
        assert len(results) > 0

    def test_predict_all_in_project_empty(self, tmp_path):
        results = predict_all_in_project(str(tmp_path / "empty"))
        assert results == []


class TestCAReview:
    """Smoke tests for c_review.py (embedded C static analyzer)."""

    def test_review_no_c_files(self, tmp_path):
        from yuleosh.review.c_review import review_embedded_c
        result = review_embedded_c("task", str(tmp_path), ["readme.md"])
        assert result.status == "passed"

    def test_review_with_volatile_missing(self, tmp_path):
        from yuleosh.review.c_review import review_embedded_c
        src = tmp_path / "src"
        src.mkdir()
        c_file = src / "main.c"
        c_file.write_text("""void callback(void) { }
uint32_t shared_var;
""")
        result = review_embedded_c("task", str(tmp_path), [str(c_file.relative_to(tmp_path))])
        assert result is not None
        assert isinstance(result.summary, str)


class TestInitExports:
    def test_review_run_exports(self):
        assert hasattr(run_review, "__name__") if callable(run_review) else True

    def test_resource_predictor_exports(self):
        assert callable(predict_resources)
        assert callable(predict_all_in_project)
