"""
Regression tests for the second-round deep-check upgrade (2026-08-07).

Round 1 (commits cfa7e8f, 3c55b98) upgraded check-item branches.  Round 2
closes the remaining shallow checks found during full re-audit:

- P1-1  _has_traced_requirements(): heading-only / empty-JSON matrix must NOT
        count as traceability.
- P1-2  document evidence: a stub document (heading only) must NOT count as
        "Evidence found".
- P1-3  _ci_results_exist() / _has_sil_results(): a .json whose name mentions
        "sil" or sits in .osh/ci but has no real outcome must NOT count.
- P1-4  review check: an empty / heading-only review record must NOT count.
- P1-5  impact check: an empty impact-analysis.md must NOT count.
- P2    _dir_has_files() / _count_unit_tests(): zero-byte files must NOT count.

Each test asserts BOTH directions: substantive content passes, stub fails.
"""

import json
from pathlib import Path

import pytest

from yuleosh.compliance.compliance_checker import ComplianceChecker

# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture
def checker(tmp_path):
    return ComplianceChecker(str(tmp_path))


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ------------------------------------------------------------------ #
# P1-1: traceability matrix must have mapping rows
# ------------------------------------------------------------------ #


class TestTraceabilitySubstantive:
    def test_heading_only_matrix_is_not_traceability(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "evidence" / "traceability-matrix.md", "# Traceability\n")
        assert checker._has_traced_requirements() is False

    def test_empty_json_matrix_is_not_traceability(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "evidence" / "traceability-matrix.json", "{}")
        assert checker._has_traced_requirements() is False

    def test_mapping_rows_count(self, checker, tmp_path):
        _write(
            tmp_path / ".osh" / "evidence" / "traceability-matrix.md",
            "# Traceability\n"
            "| REQ ID | Test |\n"
            "|--------|------|\n"
            "| REQ-001 | test_main.py |\n"
            "| REQ-002 | test_utils.py |\n",
        )
        assert checker._has_traced_requirements() is True

    def test_req_ids_in_matrix_count(self, checker, tmp_path):
        _write(
            tmp_path / ".osh" / "evidence" / "traceability-matrix.md",
            "REQ-001 -> test_main.py\nREQ-002 -> test_utils.py\n",
        )
        assert checker._has_traced_requirements() is True

    def test_populated_json_matrix_counts(self, checker, tmp_path):
        _write(
            tmp_path / ".osh" / "evidence" / "traceability-matrix.json",
            json.dumps({"REQ-001": ["test_main.py"], "REQ-002": ["test_utils.py"]}),
        )
        assert checker._has_traced_requirements() is True


# ------------------------------------------------------------------ #
# P1-2: document evidence must have substantive content
# ------------------------------------------------------------------ #


class TestDocumentEvidenceSubstantive:
    def test_heading_only_document_evidence_fails(self, tmp_path):
        _write(tmp_path / "docs" / "impact-analysis.md", "# Impact Analysis\n")
        checker = ComplianceChecker(str(tmp_path))
        # Direct probe of the evidence branch behaviour via a doc path:
        assert checker._file_has_content("docs", "impact-analysis.md", min_chars=100) is False

    def test_substantive_document_evidence_passes(self, tmp_path):
        _write(
            tmp_path / "docs" / "impact-analysis.md",
            "# Impact Analysis\n"
            "## Scope\n"
            "Changing the BLE stack affects the key manager and the mailbox\n"
            "client, plus the relay integration layer.\n"
            "## Effort & Risk\n"
            "Effort: 2 days. Risk: low — no protocol change required.\n"
        )
        checker = ComplianceChecker(str(tmp_path))
        assert checker._file_has_content("docs", "impact-analysis.md", min_chars=100) is True


# ------------------------------------------------------------------ #
# P1-3: CI / SIL results must carry a real outcome
# ------------------------------------------------------------------ #


class TestCiSilResultsSubstantive:
    def test_empty_ci_json_is_not_ci_result(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "ci" / "build-001.json", "{}")
        assert checker._ci_results_exist() is False

    def test_failed_ci_json_is_not_ci_result(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "ci" / "build-001.json", '{"status": "failed"}')
        assert checker._ci_results_exist() is False

    def test_passed_ci_json_counts(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "ci" / "build-001.json", '{"status": "passed"}')
        assert checker._ci_results_exist() is True

    def test_empty_sil_json_is_not_sil_result(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "ci" / "sil-test-001.json", "{}")
        assert checker._has_sil_results() is False

    def test_zero_byte_sil_marker_is_not_sil_result(self, checker, tmp_path):
        (tmp_path / ".osh" / "ci").mkdir(parents=True)
        (tmp_path / ".osh" / "ci" / "sil-result.txt").touch()
        assert checker._has_sil_results() is False

    def test_populated_sil_json_counts(self, checker, tmp_path):
        # f2169cd9 指标级校验: SIL 结果需 all_passed==true 且含真实产品模块
        # （hello.elf demo fixture 不算）。
        _write(
            tmp_path / ".osh" / "ci" / "sil-test-001.json",
            '{"all_passed": true, "results": [{"elf": "unlock_svc.elf", "passed": true}]}',
        )
        assert checker._has_sil_results() is True

    def test_sil_demo_fixture_does_not_count(self, checker, tmp_path):
        # hello.elf demo 不算 SIL 证据（f2169cd9 新逻辑）。
        _write(
            tmp_path / ".osh" / "ci" / "sil-test-001.json",
            '{"all_passed": true, "results": [{"elf": "hello.elf", "passed": true}]}',
        )
        assert checker._has_sil_results() is False


# ------------------------------------------------------------------ #
# P1-4: review records must have substance
# ------------------------------------------------------------------ #


class TestReviewSubstantive:
    def test_heading_only_review_fails(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "reviews" / "review-1.md", "# Review\n")
        assert any(
            checker._review_file_substantive(f)
            for f in (tmp_path / ".osh" / "reviews").iterdir()
        ) is False

    def test_empty_json_review_fails(self, checker, tmp_path):
        _write(tmp_path / ".osh" / "reviews" / "review-1.json", "{}")
        assert any(
            checker._review_file_substantive(f)
            for f in (tmp_path / ".osh" / "reviews").iterdir()
        ) is False

    def test_verdict_json_review_passes(self, checker, tmp_path):
        _write(
            tmp_path / ".osh" / "reviews" / "review-1.json",
            '{"result": "pass", "reviewer": "Alice", "comment": "All findings closed"}',
        )
        assert any(
            checker._review_file_substantive(f)
            for f in (tmp_path / ".osh" / "reviews").iterdir()
        ) is True

    def test_markdown_review_with_findings_passes(self, checker, tmp_path):
        _write(
            tmp_path / ".osh" / "reviews" / "review-1.md",
            "# Review\n"
            "Reviewer: Bob\n"
            "Finding 1: fix the bus timeout handling.\n"
            "Status: closed — fix verified in build 42.\n",
        )
        assert any(
            checker._review_file_substantive(f)
            for f in (tmp_path / ".osh" / "reviews").iterdir()
        ) is True


# ------------------------------------------------------------------ #
# P2: zero-byte files must not count
# ------------------------------------------------------------------ #


class TestZeroByteFiles:
    def test_dir_with_only_empty_file_has_no_files(self, checker, tmp_path):
        (tmp_path / "include").mkdir()
        (tmp_path / "include" / "api.h").touch()
        assert checker._dir_has_files("include") is False

    def test_dir_with_nonempty_file_counts(self, checker, tmp_path):
        _write(tmp_path / "include" / "api.h", "void api_init(void);\n")
        assert checker._dir_has_files("include") is True

    def test_empty_unit_test_not_counted(self, checker, tmp_path):
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_empty.py").touch()
        assert checker._count_unit_tests() == 0

    def test_real_unit_test_counted(self, checker, tmp_path):
        _write(tmp_path / "tests" / "test_real.py", "def test_x(): assert True\n")
        assert checker._count_unit_tests() == 1
