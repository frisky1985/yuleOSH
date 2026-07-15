"""Tests for review/run.py — OSH Review Engine."""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock, mock_open

from yuleosh.review.run import (
    ReviewFinding, ReviewResult, ReviewSession,
    review_architecture, review_domain_modeling, review_code_style,
    review_coverage, run_review, auto_review, REVIEWER_MAP,
)


class TestReviewFinding:
    def test_init(self):
        f = ReviewFinding("critical", "security", "main.c", 42, "null deref")
        assert f.severity == "critical"
        assert f.category == "security"
        assert f.file == "main.c"
        assert f.line == 42
        assert f.message == "null deref"

    def test_to_dict(self):
        f = ReviewFinding("minor", "style", "foo.py", 10, "lint")
        d = f.to_dict()
        assert d["severity"] == "minor"
        assert d["category"] == "style"
        assert d["file"] == "foo.py"
        assert d["line"] == 10
        assert d["message"] == "lint"


class TestReviewResult:
    def test_init(self):
        r = ReviewResult("task1", "alice")
        assert r.task_name == "task1"
        assert r.reviewer == "alice"
        assert r.status == "pending"
        assert r.findings == []
        assert r.retry_count == 0

    def test_add_finding(self):
        r = ReviewResult("t1", "bob")
        f = ReviewFinding("info", "style", "f.py", 1, "msg")
        r.add_finding(f)
        assert len(r.findings) == 1
        assert r.findings[0] is f

    def test_decide_empty(self):
        r = ReviewResult("t1", "bot")
        status = r.decide()
        assert status == "passed"
        assert r.summary.startswith("Clean")

    def test_decide_info_only(self):
        r = ReviewResult("t1", "bot")
        r.add_finding(ReviewFinding("info", "style", "a.py", 1, "info"))
        assert r.decide() == "passed"

    def test_decide_minor(self):
        r = ReviewResult("t1", "bot")
        r.add_finding(ReviewFinding("minor", "style", "a.py", 1, "minor"))
        assert r.decide() == "passed"

    def test_decide_major(self):
        r = ReviewResult("t1", "bot")
        r.add_finding(ReviewFinding("major", "arch", "a.py", 1, "major"))
        assert r.decide() == "passed"

    def test_decide_3_majors_still_pass(self):
        r = ReviewResult("t1", "bot")
        for _ in range(3):
            r.add_finding(ReviewFinding("major", "arch", "a.py", 1, "major"))
        assert r.decide() == "passed"

    def test_decide_4_majors_triggers_retry(self):
        r = ReviewResult("t1", "bot")
        for _ in range(4):
            r.add_finding(ReviewFinding("major", "arch", "a.py", 1, "major"))
        assert r.decide() == "retry"

    def test_decide_critical_triggers_retry(self):
        r = ReviewResult("t1", "bot")
        r.add_finding(ReviewFinding("critical", "security", "a.py", 1, "crit"))
        assert r.decide() == "retry"

    def test_decide_critical_after_5_retries_fails(self):
        r = ReviewResult("t1", "bot")
        r.retry_count = 5
        r.add_finding(ReviewFinding("critical", "security", "a.py", 1, "crit"))
        assert r.decide() == "failed"

    def test_to_dict(self):
        r = ReviewResult("t1", "bot")
        r.add_finding(ReviewFinding("critical", "security", "a.c", 10, "boom"))
        r.decide()
        d = r.to_dict()
        assert d["task"] == "t1"
        assert d["finding_count"] == 1
        assert d["finding_breakdown"]["critical"] == 1


class TestReviewSession:
    def test_init(self):
        s = ReviewSession("task-x", "/tmp/proj")
        assert s.task_name == "task-x"
        assert s.status == "running"
        assert s.decision is None

    def test_add_review(self):
        s = ReviewSession("t", "/tmp/p")
        r = ReviewResult("t", "bot")
        s.add_review(r)
        assert len(s.reviews) == 1

    def test_final_decision_no_reviews(self):
        s = ReviewSession("t", "/tmp/p")
        assert s.final_decision() == "failed"

    def test_final_decision_all_pass(self):
        s = ReviewSession("t", "/tmp/p")
        r1 = ReviewResult("t", "a")
        r1.decide()
        r2 = ReviewResult("t", "b")
        r2.decide()
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "passed"

    def test_final_decision_any_fail(self):
        s = ReviewSession("t", "/tmp/p")
        r1 = ReviewResult("t", "a")
        r1.decide()
        r2 = ReviewResult("t", "b")
        r2.add_finding(ReviewFinding("critical", "x", "f", 1, "bad"))
        r2.decide()
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "retry"

    def test_final_decision_retry_after_retries(self):
        s = ReviewSession("t", "/tmp/p")
        r = ReviewResult("t", "a")
        r.retry_count = 3  # still < 5, so becomes retry
        r.add_finding(ReviewFinding("critical", "x", "f", 1, "bad"))
        r.decide()
        s.add_review(r)
        assert s.final_decision() == "retry"

    def test_save(self):
        with tempfile.TemporaryDirectory() as td:
            s = ReviewSession("my-task", td)
            s.save()
            path = os.path.join(td, ".osh", "reviews", "my-task", "review-session.json")
            assert os.path.exists(path)
            data = json.load(open(path))
            assert data["task"] == "my-task"

    def test_to_dict(self):
        s = ReviewSession("t", "/tmp/p")
        s.add_review(ReviewResult("t", "bot"))
        d = s.to_dict()
        assert d["task"] == "t"
        assert len(d["reviews"]) == 1


class TestReviewArchitecture:
    def test_no_src_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = review_architecture("t", td, ["f.py"])
            assert result.status == "passed"

    def test_few_imports(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            pyf = os.path.join(src, "mod.py")
            with open(pyf, "w") as f:
                f.write("import os\nimport sys\n\ndef foo():\n    pass\n")
            result = review_architecture("t", td, ["src/mod.py"])
            assert result.status in ("passed", "retry")

    def test_many_imports_triggers_finding(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            pyf = os.path.join(src, "mod.py")
            lines = [f"import module_{i}\n" for i in range(40)]
            lines.append("def foo():\n    pass\n")
            with open(pyf, "w") as f:
                f.writelines(lines)
            result = review_architecture("t", td, ["src/mod.py"])
            assert len(result.findings) >= 1


class TestReviewDomainModeling:
    def test_no_src_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = review_domain_modeling("t", td, [])
            assert result.status == "passed"

    def test_mutable_default_arg_detected(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            pyf = os.path.join(src, "mod.py")
            with open(pyf, "w") as f:
                f.write("def foo(x=[]):\n    pass\n")
            result = review_domain_modeling("t", td, ["src/mod.py"])
            assert any("Mutable default arg" in f.message for f in result.findings)


class TestReviewCodeStyle:
    def test_no_src_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = review_code_style("t", td, [])
            assert result.status == "passed"

    def test_missing_docstring(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            pyf = os.path.join(src, "mod.py")
            with open(pyf, "w") as f:
                f.write("def bar():\n    pass\n")
            result = review_code_style("t", td, ["src/mod.py"])
            assert any("docstring" in f.message for f in result.findings)

    def test_tab_detected(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            pyf = os.path.join(src, "mod.py")
            with open(pyf, "w") as f:
                f.write("\tpass\n")
            result = review_code_style("t", td, ["src/mod.py"])
            assert any("Tab" in f.message for f in result.findings)


class TestReviewCoverage:
    def test_no_coverage_json(self):
        with tempfile.TemporaryDirectory() as td:
            result = review_coverage("t", td, [])
            assert any("No coverage data" in f.message for f in result.findings)

    def test_coverage_below_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            cov_path = os.path.join(td, "coverage.json")
            with open(cov_path, "w") as f:
                json.dump({"totals": {"percent_covered": 45.0}}, f)
            with patch("subprocess.run"):
                result = review_coverage("t", td, [])
            assert any("below 80%" in f.message for f in result.findings)

    def test_coverage_above_threshold(self):
        with tempfile.TemporaryDirectory() as td:
            cov_path = os.path.join(td, "coverage.json")
            with open(cov_path, "w") as f:
                json.dump({"totals": {"percent_covered": 85.0}}, f)
            with patch("subprocess.run"):
                result = review_coverage("t", td, [])
            assert any("meets threshold" in f.message for f in result.findings)


class TestREVIEWER_MAP:
    def test_keys_present(self):
        for k in ("feature", "bugfix", "refactor", "docs", "config", "embedded", "firmware"):
            assert k in REVIEWER_MAP

    def test_feature_has_correct_reviewers(self):
        reviewers = REVIEWER_MAP["feature"]
        names = [r.__name__ for r in reviewers]
        assert "review_architecture" in names
        assert "review_domain_modeling" in names
        assert "review_code_style" in names

    def test_docs_empty(self):
        assert REVIEWER_MAP["docs"] == []


class TestRunReview:
    def test_unknown_task_kind(self):
        with tempfile.TemporaryDirectory() as td:
            session = run_review("test-task", "unknown-kind", td, ["a.py"])
            assert session.decision == "passed"

    def test_docs_kind_auto_pass(self):
        with tempfile.TemporaryDirectory() as td:
            session = run_review("test-docs", "docs", td, ["docs/readme.md"])
            assert session.decision == "passed"

    def test_feature_kind_runs_reviewers(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            with open(os.path.join(src, "mod.py"), "w") as f:
                f.write("def foo():\n    pass\n")
            session = run_review("feature-test", "feature", td, ["src/mod.py"])
            assert session.decision is not None
            assert len(session.reviews) > 0
