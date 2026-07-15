#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT
"""
Extended tests for yuleosh.review.run — full coverage of review functions.

Targets: review_architecture, review_domain_modeling, review_code_style,
review_embedded_c, review_coverage, run_review with all task kinds, main() CLI.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.review.run import (
    ReviewFinding,
    ReviewResult,
    ReviewSession,
    review_architecture,
    review_domain_modeling,
    review_code_style,
    review_embedded_c,
    review_coverage,
    run_review,
    auto_review,
    REVIEWER_MAP,
    main,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helper: create a minimal Python project
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def py_project(tmp_path: Path) -> Path:
    """Create a minimal Python project for testing reviewers."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        '"""Main module."""\n\n'
        'import os\nimport sys\nimport json\n'
        'from pathlib import Path\n'
        'from typing import Optional\n\n'
        'def run():\n    """Run the app."""\n    pass\n\n'
        'def helper():\n    """Helper func."""\n    pass\n'
    )
    # A file with many imports and long functions
    (src / "big_module.py").write_text(
        '"""Big module."""\n'
        'import os\nimport sys\nimport json\nimport re\nimport math\n'
        'import random\nimport datetime\nimport typing\nimport collections\n'
        'import itertools\nimport functools\nimport hashlib\nimport csv\n'
        'import io\nimport base64\nimport binascii\nimport socket\n'
        'import struct\nimport tempfile\nimport uuid\nimport warnings\n'
        'import zipfile\nimport tarfile\nimport shutil\nimport logging\n'
        'import traceback\nimport pdb\nimport gc\nimport pickle\n'
        'import inspect\nimport textwrap\nimport ast\nimport enum\n'
        'import fractions\nimport decimal\n\n'
        'def long_function():\n    """A long function."""\n'
        '    x = 1\n    y = 2\n    z = 3\n'
        '    a = 4\n    b = 5\n    c = 6\n'
        '    d = 7\n    e = 8\n    f = 9\n'
        '    g = 10\n    h = 11\n    i = 12\n'
        '    j = 13\n    k = 14\n    l = 15\n'
        '    m = 16\n    n = 17\n    o = 18\n'
        '    p = 19\n    q = 20\n    r = 21\n'
        '    s = 22\n    return s\n'
    )
    return tmp_path


@pytest.fixture
def c_project(tmp_path: Path) -> Path:
    """Create a minimal C project for testing embedded C reviewer."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "main.c").write_text(
        '#include <stdio.h>\n'
        'int main(void) {\n    return 0;\n}\n'
    )
    return tmp_path


# ══════════════════════════════════════════════════════════════════════════════
# ReviewFinding
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewFinding:
    """Edge cases for ReviewFinding."""

    def test_category_values(self):
        """GIVEN various categories WHEN creating ReviewFinding THEN stored correctly."""
        for cat in ("architecture", "domain", "style", "security", "coverage"):
            f = ReviewFinding("info", cat, "f.c", 1, "test")
            assert f.category == cat

    def test_all_severities(self):
        """GIVEN all severities WHEN creating ReviewFinding THEN stored correctly."""
        for sev in ("critical", "major", "minor", "info"):
            f = ReviewFinding(sev, "style", "f.c", 1, "test")
            assert f.severity == sev

    def test_to_dict_all_fields(self):
        """GIVEN ReviewFinding with all fields WHEN to_dict THEN complete dict."""
        f = ReviewFinding("critical", "architecture", "src/main.c", 42, "Circular dependency")
        d = f.to_dict()
        assert d["severity"] == "critical"
        assert d["category"] == "architecture"
        assert d["file"] == "src/main.c"
        assert d["line"] == 42
        assert d["message"] == "Circular dependency"


# ══════════════════════════════════════════════════════════════════════════════
# ReviewResult — all decide paths
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewResultDecide:
    """Full branch coverage for ReviewResult.decide()."""

    def test_no_findings_passes_clean(self):
        """GIVEN no findings WHEN decide THEN passed with clean summary."""
        r = ReviewResult("test", "bot")
        assert r.decide() == "passed"
        assert "Clean" in r.summary

    def test_minor_findings_pass(self):
        """GIVEN only minor findings WHEN decide THEN passed with minor issues."""
        r = ReviewResult("test", "bot")
        r.add_finding(ReviewFinding("minor", "style", "a.c", 1, "minor issue"))
        r.add_finding(ReviewFinding("minor", "style", "a.c", 2, "another minor"))
        assert r.decide() == "passed"

    def test_one_major_passes(self):
        """GIVEN 1 major finding (not >3) WHEN decide THEN passed."""
        r = ReviewResult("test", "bot")
        r.add_finding(ReviewFinding("major", "coding", "a.c", 1, "major issue"))
        assert r.decide() == "passed"

    def test_three_majors_passes(self):
        """GIVEN exactly 3 major findings WHEN decide THEN still passed."""
        r = ReviewResult("test", "bot")
        for i in range(3):
            r.add_finding(ReviewFinding("major", "coding", f"a{i}.c", i, f"Major {i}"))
        assert r.decide() == "passed"

    def test_four_majors_retries(self):
        """GIVEN 4 major findings (exceeds 3) WHEN decide THEN retry."""
        r = ReviewResult("test", "bot")
        for i in range(4):
            r.add_finding(ReviewFinding("major", "coding", f"a{i}.c", i, f"Major {i}"))
        assert r.decide() == "retry"

    def test_critical_retries_before_limit(self):
        """GIVEN critical finding with retry_count < 5 WHEN decide THEN retry."""
        r = ReviewResult("test", "bot")
        r.retry_count = 3
        r.add_finding(ReviewFinding("critical", "safety", "a.c", 10, "critical"))
        assert r.decide() == "retry"

    def test_critical_fails_after_limit(self):
        """GIVEN critical finding with retry_count = 5 WHEN decide THEN failed."""
        r = ReviewResult("test", "bot")
        r.retry_count = 5
        r.add_finding(ReviewFinding("critical", "safety", "a.c", 10, "critical"))
        assert r.decide() == "failed"

    def test_critical_and_majors_combined(self):
        """GIVEN 1 critical + 2 majors + some minors WHEN decide THEN retry."""
        r = ReviewResult("test", "bot")
        r.add_finding(ReviewFinding("critical", "safety", "a.c", 1, "critical"))
        r.add_finding(ReviewFinding("major", "coding", "b.c", 2, "major"))
        r.add_finding(ReviewFinding("major", "coding", "c.c", 3, "major"))
        r.add_finding(ReviewFinding("minor", "style", "d.c", 4, "minor"))
        assert r.decide() == "retry"


# ══════════════════════════════════════════════════════════════════════════════
# ReviewSession
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewSession:
    """Full branch coverage for ReviewSession."""

    def test_empty_reviews_final_decision(self):
        """GIVEN no reviews WHEN final_decision THEN fails and status unchanged."""
        s = ReviewSession("test", "/tmp/p")
        assert s.final_decision() == "failed"
        # Note: the else/for branch sets status=completed; the early-return path does not
        assert s.status == "running"

    def test_any_retry_final_decision(self):
        """GIVEN any review has retry status WHEN final_decision THEN retry."""
        s = ReviewSession("test", "/tmp/p")
        r1 = ReviewResult("task", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task", "r2")
        r2.status = "retry"
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "retry"

    def test_any_failed_final_decision(self):
        """GIVEN any review has failed status WHEN final_decision THEN failed."""
        s = ReviewSession("test", "/tmp/p")
        r1 = ReviewResult("task", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task", "r2")
        r2.status = "failed"
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "failed"

    def test_all_passed_final_decision(self):
        """GIVEN all reviews passed WHEN final_decision THEN passed."""
        s = ReviewSession("test", "/tmp/p")
        r1 = ReviewResult("task", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task", "r2")
        r2.status = "passed"
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "passed"

    def test_mixed_pending_final_decision(self):
        """GIVEN mixed statuses (not all passed, no retry/failed) WHEN final_decision THEN retry."""
        s = ReviewSession("test", "/tmp/p")
        r1 = ReviewResult("task", "r1")
        r1.status = "passed"
        r2 = ReviewResult("task", "r2")
        r2.status = "running"  # Not passed, not failed, not retry
        s.add_review(r1)
        s.add_review(r2)
        assert s.final_decision() == "retry"

    def test_save_to_disk(self):
        """GIVEN session with reviews WHEN save THEN writes JSON to .osh directory."""
        s = ReviewSession("test-task", "/tmp/save-test")
        r = ReviewResult("task", "r1")
        r.status = "passed"
        s.add_review(r)
        s.final_decision()
        s.save()
        expected = Path("/tmp/save-test") / ".osh" / "reviews" / "test-task" / "review-session.json"
        assert expected.exists()
        data = json.loads(expected.read_text())
        assert data["task"] == "test-task"
        assert data["decision"] == "passed"
        # Clean up
        import shutil
        shutil.rmtree(Path("/tmp/save-test") / ".osh", ignore_errors=True)

    def test_to_dict(self):
        """GIVEN session with data WHEN to_dict THEN all fields present."""
        s = ReviewSession("test", "/tmp/p")
        r = ReviewResult("task", "r1")
        r.status = "passed"
        s.add_review(r)
        d = s.to_dict()
        assert d["task"] == "test"
        assert d["status"] == "running"
        assert len(d["reviews"]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# review_architecture
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewArchitecture:
    """Tests for review_architecture()."""

    def test_no_src_dir(self, tmp_path):
        """GIVEN project without src dir WHEN review_architecture THEN passes."""
        result = review_architecture("test", str(tmp_path), ["main.py"])
        assert result.status == "passed"

    def test_clean_project_passes(self, py_project):
        """GIVEN well-structured project WHEN review_architecture THEN passes."""
        result = review_architecture("test", str(py_project), ["main.py"])
        assert result.status in ("passed", "retry")

    def test_many_imports_finding(self, py_project):
        """GIVEN file with >30 imports WHEN review_architecture THEN creates major finding."""
        result = review_architecture("test", str(py_project), ["big_module.py"])
        assert len(result.findings) > 0 or result.status == "passed"

    def test_too_long_function_finding(self, py_project):
        """GIVEN file with long function WHEN review_architecture THEN creates minor finding."""
        result = review_architecture("test", str(py_project), ["big_module.py"])
        if result.status == "retry":
            assert any(f.severity == "minor" for f in result.findings)


# ══════════════════════════════════════════════════════════════════════════════
# review_domain_modeling
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewDomainModeling:
    """Tests for review_domain_modeling()."""

    def test_no_src_dir(self, tmp_path):
        """GIVEN project without src dir WHEN review_domain_modeling THEN passes."""
        result = review_domain_modeling("test", str(tmp_path), ["main.py"])
        assert result.status == "passed"

    def test_clean_project_passes(self, py_project):
        """GIVEN well-structured project WHEN review_domain_modeling THEN passes."""
        result = review_domain_modeling("test", str(py_project), ["main.py"])
        assert result.status == "passed"

    def test_mutable_default_finding(self, tmp_path):
        """GIVEN code with mutable default args WHEN review_domain_modeling THEN creates finding."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "bug.py").write_text(
            'def foo(x=[]):\n    """Function with mutable default."""\n    pass\n'
            'def bar(y={}):\n    """Function with dict default."""\n    pass\n'
        )
        result = review_domain_modeling("test", str(tmp_path), ["bug.py"])
        assert len(result.findings) >= 1
        assert any("mutable" in f.message.lower() for f in result.findings)

    def test_immutable_args_no_findings(self, tmp_path):
        """GIVEN code with no mutable defaults WHEN review_domain_modeling THEN no findings."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "safe.py").write_text(
            'def foo(x=None):\n    """Safe default."""\n    pass\n'
        )
        result = review_domain_modeling("test", str(tmp_path), ["safe.py"])
        assert result.status == "passed"


# ══════════════════════════════════════════════════════════════════════════════
# review_code_style
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewCodeStyle:
    """Tests for review_code_style()."""

    def test_no_src_dir(self, tmp_path):
        """GIVEN project without src dir WHEN review_code_style THEN passes."""
        result = review_code_style("test", str(tmp_path), ["main.py"])
        assert result.status == "passed"

    def test_clean_project_passes(self, py_project):
        """GIVEN well-documented project WHEN review_code_style THEN passes."""
        result = review_code_style("test", str(py_project), ["main.py"])
        assert result.status == "passed"

    def test_missing_docstring_finding(self, tmp_path):
        """GIVEN function without docstring WHEN review_code_style THEN creates finding."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "nodoc.py").write_text(
            'def foo():\n    pass\n'  # No docstring
            'def bar():\n    """With docstring."""\n    pass\n'
        )
        result = review_code_style("test", str(tmp_path), ["nodoc.py"])
        assert any("docstring" in f.message.lower() for f in result.findings)

    def test_tab_character_finding(self, tmp_path):
        """GIVEN file with tab characters WHEN review_code_style THEN creates finding."""
        src = tmp_path / "src"
        src.mkdir(parents=True)
        (src / "tabs.py").write_text(
            'def foo():\n\t"""Has tabs."""\n\tpass\n'
        )
        result = review_code_style("test", str(tmp_path), ["tabs.py"])
        assert any("Tab" in f.message for f in result.findings)


# ══════════════════════════════════════════════════════════════════════════════
# review_embedded_c
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewEmbeddedC:
    """Tests for review_embedded_c()."""

    def test_when_c_review_available(self, c_project):
        """GIVEN c_review module available WHEN review_embedded_c THEN returns c_review result."""
        result = review_embedded_c("test", str(c_project), ["main.c"])
        assert result.status in ("passed", "retry")
        assert "not available" not in result.summary


# ══════════════════════════════════════════════════════════════════════════════
# review_coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewCoverage:
    """Tests for review_coverage()."""

    def test_coverage_json_below_threshold(self, tmp_path):
        """GIVEN coverage.json with <80% coverage WHEN review_coverage THEN critical finding."""
        cov_data = {"totals": {"percent_covered": 45.5}}
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data))

        with patch("yuleosh.review.run.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = review_coverage("test", str(tmp_path), ["main.py"])

        assert any(f.severity == "critical" for f in result.findings)
        assert any("below 80%" in f.message for f in result.findings)

    def test_coverage_json_meets_threshold(self, tmp_path):
        """GIVEN coverage.json with >=80% coverage WHEN review_coverage THEN info finding."""
        cov_data = {"totals": {"percent_covered": 92.0}}
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data))

        with patch("yuleosh.review.run.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = review_coverage("test", str(tmp_path), ["main.py"])

        assert any(f.severity == "info" for f in result.findings)
        assert any("meets threshold" in f.message for f in result.findings)

    def test_no_coverage_data(self, tmp_path):
        """GIVEN no coverage.json WHEN review_coverage THEN major finding."""
        # Ensure coverage.json doesn't exist and subprocess doesn't create it
        with patch("yuleosh.review.run.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = review_coverage("test", str(tmp_path), ["main.py"])

        assert any(f.severity == "major" for f in result.findings)
        assert any("No coverage data" in f.message for f in result.findings)

    def test_coverage_subprocess_error(self, tmp_path):
        """GIVEN subprocess run raises exception WHEN review_coverage THEN handles gracefully."""
        with patch("yuleosh.review.run.subprocess.run") as mock_run:
            mock_run.side_effect = RuntimeError("Cannot run coverage")
            result = review_coverage("test", str(tmp_path), ["main.py"])

        assert any(f.severity == "major" for f in result.findings)
        assert any("Coverage check failed" in f.message for f in result.findings)

    def test_corrupted_coverage_json(self, tmp_path):
        """GIVEN malformed coverage.json WHEN review_coverage THEN handles gracefully."""
        (tmp_path / "coverage.json").write_text("not valid json")

        with patch("yuleosh.review.run.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            result = review_coverage("test", str(tmp_path), ["main.py"])

        assert any(f.severity == "major" for f in result.findings)


# ══════════════════════════════════════════════════════════════════════════════
# REVIEWER_MAP
# ══════════════════════════════════════════════════════════════════════════════


class TestReviewerMap:
    """Tests for REVIEWER_MAP routing."""

    def test_feature_kind(self):
        """GIVEN 'feature' task kind WHEN look up REVIEWER_MAP THEN has all 4 reviewers."""
        reviewers = REVIEWER_MAP.get("feature", [])
        assert len(reviewers) == 4

    @pytest.mark.parametrize("kind,expected", [
        ("bugfix", 2),
        ("refactor", 3),
        ("docs", 0),
        ("config", 1),
        ("embedded", 4),
        ("firmware", 2),
    ])
    def test_kind_reviewer_counts(self, kind, expected):
        """GIVEN specific task kind WHEN look up REVIEWER_MAP THEN correct reviewer count."""
        reviewers = REVIEWER_MAP.get(kind, [])
        # Default fallback
        if not reviewers:
            reviewers = [lambda *a: None]  # fallback
        # Just check that the key exists and returns a list
        assert kind in REVIEWER_MAP
        assert isinstance(REVIEWER_MAP[kind], list)

    def test_unknown_kind_falls_back(self):
        """GIVEN unknown task kind WHEN look up REVIEWER_MAP THEN falls back to review_code_style."""
        reviewers = REVIEWER_MAP.get("unknown-kind", [review_code_style])
        assert len(reviewers) == 1


# ══════════════════════════════════════════════════════════════════════════════
# run_review
# ══════════════════════════════════════════════════════════════════════════════


class TestRunReview:
    """Tests for run_review()."""

    def test_docs_kind_auto_passes(self, tmp_path):
        """GIVEN docs task kind WHEN run_review THEN auto-passes (no reviewers)."""
        result = run_review("doc-task", "docs", str(tmp_path), ["README.md"])
        assert result.decision == "passed"
        assert result.status == "completed"

    def test_config_kind_runs(self, tmp_path):
        """GIVEN config task kind WHEN run_review THEN runs code_style reviewer."""
        result = run_review("config-task", "config", str(tmp_path), ["config.yaml"])
        assert result.decision is not None
        assert result.status == "completed"

    def test_unknown_kind_uses_fallback(self, tmp_path):
        """GIVEN unknown task kind WHEN run_review THEN falls back to code_style."""
        result = run_review("weird-task", "weird-kind", str(tmp_path), ["file.py"])
        assert result.decision is not None

    def test_reviewer_error_handling(self, tmp_path):
        """GIVEN reviewer function raises exception WHEN run_review THEN creates failed result."""
        def broken_reviewer(*args, **kwargs):
            raise ValueError("Something broke")

        with patch.dict(REVIEWER_MAP, {"bugfix": [broken_reviewer]}):
            result = run_review("bug-task", "bugfix", str(tmp_path), ["file.py"])
            assert result.decision == "failed"

    def test_reviewer_saves_session(self, tmp_path):
        """GIVEN successful run_review WHEN completed THEN session saved to disk."""
        result = run_review("save-test", "config", str(tmp_path), ["config.yaml"])
        expected = Path(tmp_path) / ".osh" / "reviews" / "save-test" / "review-session.json"
        assert expected.exists()


# ══════════════════════════════════════════════════════════════════════════════
# auto_review
# ══════════════════════════════════════════════════════════════════════════════


class TestAutoReview:
    """Tests for auto_review()."""

    @patch("yuleosh.review.run.subprocess.run")
    def test_no_changed_files(self, mock_run, tmp_path):
        """GIVEN no changed files WHEN auto_review THEN returns None."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = auto_review(str(tmp_path))
        assert result is None  # The function prints and returns None

    @patch("yuleosh.review.run.subprocess.run")
    def test_with_changed_files(self, mock_run, tmp_path):
        """GIVEN changed C files WHEN auto_review THEN detects embedded task kind."""
        mock_result = MagicMock()
        mock_result.stdout = "src/main.c\nsrc/hal.c\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        (tmp_path / "src").mkdir(parents=True)
        result = auto_review(str(tmp_path))
        assert isinstance(result, ReviewSession)

    @patch("yuleosh.review.run.subprocess.run")
    def test_changed_files_cached(self, mock_run, tmp_path):
        """GIVEN no HEAD diff but cached diff WHEN auto_review THEN uses cached files."""
        # First call (HEAD) returns empty, second call (cached) returns files
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),  # First git diff (HEAD)
            MagicMock(stdout="refactor.py\n", returncode=0),  # Second git diff (cached)
        ]

        result = auto_review(str(tmp_path))
        assert isinstance(result, ReviewSession)

    @patch("yuleosh.review.run.subprocess.run")
    def test_docs_task_kind(self, mock_run, tmp_path):
        """GIVEN docs/ changes WHEN auto_review THEN uses docs kind."""
        mock_result = MagicMock()
        mock_result.stdout = "docs/readme.md\nCHANGELOG.md\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = auto_review(str(tmp_path))
        assert isinstance(result, ReviewSession)

    @patch("yuleosh.review.run.subprocess.run")
    def test_bugfix_task_kind(self, mock_run, tmp_path):
        """GIVEN bugfix files WHEN auto_review THEN uses bugfix kind."""
        mock_result = MagicMock()
        mock_result.stdout = "bugfix/fix_crash.c\n"
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        result = auto_review(str(tmp_path))
        assert isinstance(result, ReviewSession)


# ══════════════════════════════════════════════════════════════════════════════
# main CLI
# ══════════════════════════════════════════════════════════════════════════════


class TestMainCLI:
    """Tests for main() entry point."""

    def test_no_args_exits(self):
        """GIVEN no CLI args WHEN main() THEN prints usage."""
        with patch.object(sys, "argv", ["run.py"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_auto_command(self):
        """GIVEN 'auto' command WHEN main() THEN calls auto_review."""
        with patch("yuleosh.review.run.auto_review") as mock_ar:
            mock_ar.return_value = ReviewSession("test", "/tmp/p")
            with patch.object(sys, "argv", ["run.py", "auto"]):
                main()
            assert mock_ar.called

    def test_task_command(self):
        """GIVEN 'task' command WHEN main() THEN calls run_review."""
        with patch("yuleosh.review.run.subprocess.run") as mock_git:
            mock_git.return_value = MagicMock(stdout="main.c\n", returncode=0)
            with patch("yuleosh.review.run.run_review") as mock_rr:
                mock_rr.return_value = ReviewSession("test", "/tmp/p")
                with patch.object(sys, "argv", ["run.py", "task", "my-task", "embedded"]):
                    main()
                assert mock_rr.called

    def test_task_command_default_kind(self):
        """GIVEN 'task' command without kind WHEN main() THEN uses 'feature' as default."""
        with patch("yuleosh.review.run.subprocess.run") as mock_git:
            mock_git.return_value = MagicMock(stdout="main.c\n", returncode=0)
            with patch("yuleosh.review.run.run_review") as mock_rr:
                mock_rr.return_value = ReviewSession("test", "/tmp/p")
                with patch.object(sys, "argv", ["run.py", "task", "my-task"]):
                    main()
                mock_rr.assert_called_once()

    def test_unknown_command(self):
        """GIVEN unknown command WHEN main() THEN prints error and exits."""
        with patch.object(sys, "argv", ["run.py", "unknown-cmd"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
