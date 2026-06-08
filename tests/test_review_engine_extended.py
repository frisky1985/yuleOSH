"""Extended tests for review engine — reviewer functions, session save/load, auto_review, main.

Covers: review_architecture, review_domain_modeling, review_code_style, review_coverage,
        ReviewSession.save, ReviewSession.final_decision edge cases, ReviewFinding.to_dict,
        ReviewResult.decide with majors/exact retry/fail, run_review, auto_review, main CLI.
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "review"))

from run import (
    ReviewFinding,
    ReviewResult,
    ReviewSession,
    review_architecture,
    review_domain_modeling,
    review_code_style,
    review_coverage,
    run_review,
    auto_review,
    main,
    REVIEWER_MAP,
)


# ===================================================================
# ReviewFinding edge cases
# ===================================================================

def test_finding_to_dict():
    """Test ReviewFinding.to_dict serialization."""
    f = ReviewFinding("critical", "security", "app.py", 10, "SQL injection risk")
    d = f.to_dict()
    assert d["severity"] == "critical"
    assert d["category"] == "security"
    assert d["file"] == "app.py"
    assert d["line"] == 10
    assert d["message"] == "SQL injection risk"


# ===================================================================
# ReviewResult decide edge cases
# ===================================================================

def test_result_decide_with_majors_only():
    """Test decide() with >3 majors triggers retry, <=3 majors triggers pass."""
    r = ReviewResult("test", "reviewer")
    for i in range(4):
        r.add_finding(ReviewFinding("major", "style", f"f{i}.py", i, f"Issue {i}"))
    assert r.decide() == "retry"
    assert r.retry_count == 0  # unchanged by decide

    r2 = ReviewResult("test", "reviewer")
    r2.add_finding(ReviewFinding("major", "style", "x.py", 1, "Minor style"))
    assert r2.decide() == "passed"


def test_result_decide_critical_block_then_retry_then_fail():
    """Test criticals cause retry up to 5 times, then fail."""
    r = ReviewResult("test", "reviewer")
    r.add_finding(ReviewFinding("critical", "security", "x.py", 1, "Critical"))

    # First 5 decide() calls with retry_count set externally
    for i in range(5):
        r.retry_count = i
        assert r.decide() == "retry", f"Retry {i+1}/5 should be retry"

    # After 5 retries, it should fail
    r.retry_count = 5
    assert r.decide() == "failed"
    assert r.status == "failed"
    assert "Failed after 5 retries" in r.summary


def test_result_to_dict():
    """Test ReviewResult.to_dict includes all keys."""
    r = ReviewResult("my-task", "arch-reviewer")
    r.add_finding(ReviewFinding("info", "style", "x.py", 1, "Minor"))
    r.decide()
    d = r.to_dict()
    assert d["task"] == "my-task"
    assert d["reviewer"] == "arch-reviewer"
    assert d["status"] in ("passed", "failed", "retry", "pending")
    assert d["finding_count"] >= 0
    assert "finding_breakdown" in d
    assert "summary" in d


# ===================================================================
# ReviewSession edge cases
# ===================================================================

def test_session_final_decision_empty():
    """Test no reviews -> fail."""
    with tempfile.TemporaryDirectory() as tmp:
        s = ReviewSession("empty-task", tmp)
        assert s.final_decision() == "failed"
        assert s.decision == "failed"


def test_session_final_decision_retry_wins():
    """Test any retry -> retry."""
    s = ReviewSession("retry-task", "/tmp")
    r1 = ReviewResult("test", "a")
    r1.status = "passed"
    r2 = ReviewResult("test", "b")
    r2.status = "retry"
    r3 = ReviewResult("test", "c")
    r3.status = "failed"
    s.add_review(r1)
    s.add_review(r2)
    s.add_review(r3)
    assert s.final_decision() == "retry"


def test_session_final_decision_failed_wins():
    """Test no retry, but failed -> failed."""
    s = ReviewSession("fail-task", "/tmp")
    r1 = ReviewResult("test", "a")
    r1.status = "passed"
    r2 = ReviewResult("test", "b")
    r2.status = "failed"
    s.add_review(r1)
    s.add_review(r2)
    assert s.final_decision() == "failed"


def test_session_final_decision_mixed_unknown():
    """Test unknown status mix -> retry."""
    s = ReviewSession("unknown-task", "/tmp")
    r1 = ReviewResult("test", "a")
    r1.status = "passed"
    r2 = ReviewResult("test", "b")
    r2.status = "running"
    s.add_review(r1)
    s.add_review(r2)
    assert s.final_decision() == "retry"


def test_session_save_and_to_dict():
    """Test ReviewSession.save() persists correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        s = ReviewSession("save-test", tmp)
        r = ReviewResult("save-test", "arch-reviewer")
        r.add_finding(ReviewFinding("info", "style", "x.py", 1, "test"))
        r.decide()
        s.add_review(r)
        s.final_decision()
        s.save()

        # Verify file exists
        session_path = Path(tmp) / ".osh" / "reviews" / "save-test" / "review-session.json"
        assert session_path.exists()

        with open(session_path) as f:
            data = json.load(f)

        assert data["task"] == "save-test"
        assert data["decision"] == "passed"
        assert len(data["reviews"]) == 1
        assert data["reviews"][0]["reviewer"] == "arch-reviewer"


# ===================================================================
# Reviewer functions
# ===================================================================

def test_review_architecture_no_src_dir():
    """Test architecture reviewer with no src/ directory."""
    with tempfile.TemporaryDirectory() as tmp:
        result = review_architecture("test-task", tmp, [])
        assert result.status == "passed"
        assert "No source directory" in result.summary


def test_review_architecture_with_src():
    """Test architecture reviewer scans src/ .py files."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("import os\nimport sys\n\n\ndef foo():\n    pass\n")
        result = review_architecture("test-task", tmp, [])
        assert result.status in ("passed", "retry", "failed")


def test_review_architecture_long_func():
    """Test architecture reviewer flags >20 line functions."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        # No trailing newline to avoid empty-last-line quirk
        long_func_code = "def long_func():\n" + "    pass\n" * 24 + "    pass"
        (src_dir / "bigfunc.py").write_text(long_func_code)
        result = review_architecture("test-task", tmp, [])
        assert len(result.findings) > 0


def test_review_architecture_many_imports():
    """Test architecture reviewer flags excessive imports (>30)."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        imports = "\n".join(f"import module_{i}" for i in range(35))
        (src_dir / "heavy.py").write_text(imports + "\n\nx = 1\n")
        result = review_architecture("test-task", tmp, [])
        assert any("imports" in f.message for f in result.findings)


def test_review_domain_modeling_no_src():
    """Test domain reviewer with no src/ directory."""
    with tempfile.TemporaryDirectory() as tmp:
        result = review_domain_modeling("test-task", tmp, [])
        assert result.status == "passed"
        assert "No source directory" in result.summary


def test_review_domain_modeling_mutable_default():
    """Test domain reviewer catches mutable default args."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        (src_dir / "bad.py").write_text("def foo(items=[]):\n    pass\n")
        result = review_domain_modeling("test-task", tmp, [])
        assert any("Mutable default" in f.message for f in result.findings)


def test_review_code_style_no_src():
    """Test code style reviewer with no src/ directory."""
    with tempfile.TemporaryDirectory() as tmp:
        result = review_code_style("test-task", tmp, [])
        assert result.status == "passed"
        assert "No source directory" in result.summary


def test_review_code_style_missing_docstring():
    """Test code style reviewer catches missing docstrings."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        (src_dir / "nodoc.py").write_text("def foo():\n    pass\n")
        result = review_code_style("test-task", tmp, [])
        assert any("missing docstring" in f.message for f in result.findings)


def test_review_code_style_tabs():
    """Test code style reviewer flags tab characters."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        (src_dir / "tabs.py").write_text("def foo():\n\tpass\n")
        result = review_code_style("test-task", tmp, [])
        assert any("Tab character" in f.message for f in result.findings)


def test_review_coverage_critical_below_80():
    """Test coverage reviewer below 80% threshold."""
    with tempfile.TemporaryDirectory() as tmp:
        cov_json = Path(tmp) / "coverage.json"
        cov_json.write_text(json.dumps({
            "totals": {"percent_covered": 45}
        }))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = review_coverage("test-task", tmp, [])
        assert any("below 80%" in f.message for f in result.findings)


def test_review_coverage_info_above_80():
    """Test coverage reviewer above 80% threshold."""
    with tempfile.TemporaryDirectory() as tmp:
        cov_json = Path(tmp) / "coverage.json"
        cov_json.write_text(json.dumps({
            "totals": {"percent_covered": 85}
        }))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = review_coverage("test-task", tmp, [])
        assert any("meets threshold" in f.message for f in result.findings)


def test_review_coverage_no_data():
    """Test coverage reviewer when coverage.json does not exist."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = review_coverage("test-task", tmp, [])
        assert any("No coverage data" in f.message for f in result.findings)


def test_review_coverage_exception():
    """Test coverage reviewer when subprocess fails."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("runner crashed")
            result = review_coverage("test-task", tmp, [])
        assert any("Coverage check failed" in f.message for f in result.findings)


# ===================================================================
# run_review orchestration
# ===================================================================

def test_run_review_docs_auto_pass():
    """Test docs kind (no reviewers) auto-passes."""
    with tempfile.TemporaryDirectory() as tmp:
        session = run_review("test-task", "docs", tmp, [])
        assert session.decision == "passed"
        assert session.status == "completed"
        # Verify saved
        session_path = Path(tmp) / ".osh" / "reviews" / "test-task" / "review-session.json"
        assert session_path.exists()


def test_run_review_unknown_kind():
    """Test unknown kind defaults to review_code_style."""
    with tempfile.TemporaryDirectory() as tmp:
        session = run_review("test-task", "nonexistent_kind", tmp, [])
        assert session.status == "completed"
        assert session.decision is not None


def test_run_review_feature_with_reviewers():
    """Test feature kind runs all configured reviewers."""
    with tempfile.TemporaryDirectory() as tmp:
        session = run_review("test-task", "feature", tmp, [])
        assert session.status == "completed"
        # Feature has 4 reviewers; all should succeed on empty project
        assert len(session.reviews) == 4


def test_run_review_with_changed_files():
    """Test run_review with changed files."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        (src_dir / "app.py").write_text(
            "import os\n\n\ndef foo(items=[]):\n    pass\n"
        )
        session = run_review("test-task", "feature", tmp, ["src/app.py"])
        assert session.status == "completed"


# ===================================================================
# auto_review
# ===================================================================

def test_auto_review_no_changed_files():
    """Test auto_review with no changed files."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 0
            result = auto_review(tmp)
            assert result is None


def test_auto_review_with_changed_files():
    """Test auto_review with changed files."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            # First call returns files
            mock_run.return_value.stdout = "src/app.py\n"
            mock_run.return_value.returncode = 0
            session = auto_review(tmp)
            assert session is not None
            assert session.status == "completed"


def test_auto_review_kind_detection_bugfix():
    """Test auto_review kind detection: bugfix files."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "src/bugfix.py\n"
            mock_run.return_value.returncode = 0
            session = auto_review(tmp)
            assert session is not None


def test_auto_review_kind_detection_docs():
    """Test auto_review kind detection: doc files."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "docs/README.md\n"
            mock_run.return_value.returncode = 0
            session = auto_review(tmp)
            assert session is not None


def test_auto_review_fallback_to_cached():
    """Test auto_review falls back to --cached when HEAD diff is empty."""
    with tempfile.TemporaryDirectory() as tmp:
        call_count = [0]

        def mock_subprocess(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.stdout = ""
            else:
                result.stdout = "src/x.py\n"
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_subprocess):
            session = auto_review(tmp)
            assert session is not None
            # auto_review calls subprocess.run for git diffs; review_coverage adds one more
            assert call_count[0] >= 2


# ===================================================================
# main CLI
# ===================================================================

def test_main_auto():
    """Test main() with 'auto' command."""
    test_args = ["run.py", "auto"]
    with patch.object(sys, "argv", test_args):
        with patch("run.auto_review") as mock_ar:
            mock_ar.return_value = MagicMock()
            main()


def test_main_task():
    """Test main() with 'task' command."""
    test_args = ["run.py", "task", "my-task", "feature"]
    with patch.object(sys, "argv", test_args):
        with patch("run.run_review") as mock_rr:
            mock_rr.return_value = MagicMock()
            with patch("subprocess.run") as mock_sp:
                mock_sp.return_value.stdout = "src/x.py\n"
                mock_sp.return_value.returncode = 0
                main()
                mock_rr.assert_called_once()
                args, _ = mock_rr.call_args
                assert args[0] == "my-task"  # task_name


def test_main_unknown():
    """Test main() with unknown command exits."""
    test_args = ["run.py", "unknown"]
    with patch.object(sys, "argv", test_args):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit:
            pass


def test_main_no_args():
    """Test main() with no args prints usage."""
    test_args = ["run.py"]
    with patch.object(sys, "argv", test_args):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit:
            pass


# ===================================================================
# REVIEWER_MAP usage
# ===================================================================

def test_reviewer_map_keys():
    """Test REVIEWER_MAP has expected keys."""
    assert "feature" in REVIEWER_MAP
    assert "bugfix" in REVIEWER_MAP
    assert "refactor" in REVIEWER_MAP
    assert "docs" in REVIEWER_MAP
    assert "config" in REVIEWER_MAP
    assert REVIEWER_MAP["docs"] == []
    assert len(REVIEWER_MAP["feature"]) == 4


def test_review_architecture_async_function():
    """Test architecture reviewer handles async def."""
    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp) / "src"
        src_dir.mkdir()
        (src_dir / "asyncmod.py").write_text(
            "async def fetch_data():\n    return 42\n\n\ndef sync_func():\n    pass\n"
        )
        result = review_architecture("test-task", tmp, [])
        assert result.status in ("passed", "retry", "failed")


def test_run_review_reviewer_error():
    """Test run_review handles reviewer exceptions gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict("run.REVIEWER_MAP", {"feature": [lambda n, d, f: (_ for _ in ()).throw(ValueError("reviewer crashed"))]}):
            session = run_review("test-task", "feature", tmp, [])
            assert session.status == "completed"
            assert len(session.reviews) == 1
            err_review = session.reviews[0]
            assert err_review.status == "failed"
            assert any("reviewer crashed" in f.message for f in err_review.findings)


def test_auto_review_with_refactor_kind():
    """Test auto_review detects refactor kind from file names."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "src/refactor_stuff.py\n"
            mock_run.return_value.returncode = 0
            session = auto_review(tmp)
            assert session is not None


def test_auto_review_with_osh_home():
    """Test auto_review uses OSH_HOME env var."""
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"OSH_HOME": tmp}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.stdout = "src/x.py\n"
                mock_run.return_value.returncode = 0
                session = auto_review()
                assert session is not None


def test_main_task_default_kind():
    """Test main() 'task' command with default kind."""
    test_args = ["run.py", "task", "my-task"]
    with patch.object(sys, "argv", test_args):
        with patch("run.run_review") as mock_rr:
            mock_rr.return_value = MagicMock()
            with patch("subprocess.run") as mock_sp:
                mock_sp.return_value.stdout = "src/x.py\n"
                mock_sp.return_value.returncode = 0
                main()
                mock_rr.assert_called_once()
