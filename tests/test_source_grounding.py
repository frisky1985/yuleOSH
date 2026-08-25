
# @tests src/yuleosh/pipeline/source_grounding.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for SourceGroundingChecker and repo_facts H2-1b extensions (H2-1d)."""

import pytest

from yuleosh.pipeline.source_grounding import SourceGroundingChecker, GroundingReport


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def two_files():
    """Two source files: hal.c (10 lines) and driver.py (5 lines)."""
    return [
        {"path": "src/hal.c", "lines": 10},
        {"path": "src/driver.py", "lines": 5},
    ]


@pytest.fixture()
def checker_files_only(two_files):
    return SourceGroundingChecker(source_files=two_files)


@pytest.fixture()
def checker_with_funcs(two_files):
    return SourceGroundingChecker(
        source_files=two_files,
        known_function_names={"hal_init", "hal_send", "driver_run"},
    )


@pytest.fixture()
def checker_with_reqs(two_files):
    return SourceGroundingChecker(
        source_files=two_files,
        known_req_ids={"REQ-UART-001", "REQ-UART-002", "SWR-CAN-01"},
    )


@pytest.fixture()
def full_checker(two_files):
    return SourceGroundingChecker(
        source_files=two_files,
        known_function_names={"hal_init", "hal_send"},
        known_req_ids={"REQ-UART-001"},
    )


# ── file:line grounding ────────────────────────────────────────────────────────

class TestFileLineGrounding:
    def test_valid_file_no_line(self, checker_files_only):
        report = checker_files_only.check("See src/hal.c for details.")
        assert report.clean
        assert report.checked_file_lines >= 1

    def test_valid_file_valid_line(self, checker_files_only):
        report = checker_files_only.check("Error at src/hal.c:5")
        assert report.clean

    def test_valid_file_boundary_line(self, checker_files_only):
        report = checker_files_only.check("Line src/hal.c:10 is valid.")
        assert report.clean

    def test_unknown_file_flagged(self, checker_files_only):
        report = checker_files_only.check("Bug in src/ghost.c:3")
        assert not report.clean
        v = report.violations[0]
        assert v.kind == "file_line"
        assert "ghost.c" in v.reference

    def test_line_out_of_range_flagged(self, checker_files_only):
        report = checker_files_only.check("See src/hal.c:99")
        assert not report.clean
        assert report.violations[0].kind == "file_line"
        assert "99" in report.violations[0].reason

    def test_line_zero_flagged(self, checker_files_only):
        report = checker_files_only.check("src/hal.c:0")
        assert not report.clean

    def test_python_file_valid(self, checker_files_only):
        report = checker_files_only.check("See src/driver.py:3")
        assert report.clean

    def test_multiple_violations_counted(self, checker_files_only):
        report = checker_files_only.check(
            "src/ghost.c:1 and src/hal.c:99 and src/fake.py:2"
        )
        assert len(report.violations) == 3

    def test_duplicate_reference_counted_once(self, checker_files_only):
        report = checker_files_only.check("src/ghost.c:1 src/ghost.c:1")
        assert len(report.violations) == 1

    def test_no_source_files_skips_check(self):
        checker = SourceGroundingChecker(source_files=[])
        report = checker.check("src/anything.c:99 mentioned here")
        assert report.clean
        assert report.checked_file_lines == 0

    def test_report_to_dict(self, checker_files_only):
        report = checker_files_only.check("src/ghost.c:1")
        d = report.to_dict()
        assert d["clean"] is False
        assert d["violation_count"] == 1
        assert d["violations"][0]["kind"] == "file_line"


# ── function name grounding ────────────────────────────────────────────────────

class TestFuncNameGrounding:
    def test_known_function_passes(self, checker_with_funcs):
        report = checker_with_funcs.check("Call hal_init() at startup.")
        assert report.clean
        assert report.checked_func_names >= 1

    def test_unknown_function_flagged(self, checker_with_funcs):
        report = checker_with_funcs.check("Call phantom_func() here.")
        assert not report.clean
        v = next(v for v in report.violations if v.kind == "func_name")
        assert "phantom_func" in v.reference

    def test_no_known_funcs_skips_check(self, two_files):
        checker = SourceGroundingChecker(source_files=two_files)
        report = checker.check("Call totally_fake_func() here.")
        func_violations = [v for v in report.violations if v.kind == "func_name"]
        assert func_violations == []
        assert report.checked_func_names == 0

    def test_short_names_ignored(self, checker_with_funcs):
        # regex requires ≥3 char names — "do()" / "go()" are skipped
        report = checker_with_funcs.check("do() go() if()")
        func_violations = [v for v in report.violations if v.kind == "func_name"]
        assert func_violations == []

    def test_duplicate_func_counted_once(self, checker_with_funcs):
        report = checker_with_funcs.check("phantom_func() phantom_func()")
        func_violations = [v for v in report.violations if v.kind == "func_name"]
        assert len(func_violations) == 1


# ── requirement ID grounding ───────────────────────────────────────────────────

class TestReqIdGrounding:
    def test_known_req_passes(self, checker_with_reqs):
        report = checker_with_reqs.check("Implements REQ-UART-001.")
        assert report.clean

    def test_unknown_req_flagged(self, checker_with_reqs):
        report = checker_with_reqs.check("See REQ-FAKE-999 for details.")
        req_violations = [v for v in report.violations if v.kind == "req_id"]
        assert req_violations
        assert "REQ-FAKE-999" in req_violations[0].reference.upper()

    def test_case_insensitive_match(self, checker_with_reqs):
        report = checker_with_reqs.check("req-uart-001 is satisfied.")
        assert report.clean

    def test_no_known_reqs_skips_check(self, two_files):
        checker = SourceGroundingChecker(source_files=two_files)
        report = checker.check("See REQ-GHOST-999.")
        req_violations = [v for v in report.violations if v.kind == "req_id"]
        assert req_violations == []
        assert report.checked_req_ids == 0

    def test_swr_prefix_matched(self, checker_with_reqs):
        report = checker_with_reqs.check("Satisfies SWR-CAN-01.")
        assert report.clean

    def test_unknown_swr_flagged(self, checker_with_reqs):
        report = checker_with_reqs.check("See SWR-CAN-99.")
        req_violations = [v for v in report.violations if v.kind == "req_id"]
        assert req_violations


# ── combined / clean report ────────────────────────────────────────────────────

class TestCombined:
    def test_all_valid_is_clean(self, full_checker):
        text = "hal_init() implemented in src/hal.c:1 per REQ-UART-001."
        report = full_checker.check(text)
        assert report.clean

    def test_mixed_valid_and_invalid(self, full_checker):
        text = (
            "hal_init() is fine but ghost_func() and src/ghost.c:1 "
            "and REQ-GHOST-000 are all hallucinated."
        )
        report = full_checker.check(text)
        assert not report.clean
        kinds = {v.kind for v in report.violations}
        assert "file_line" in kinds
        assert "func_name" in kinds
        assert "req_id" in kinds

    def test_empty_text_is_clean(self, full_checker):
        report = full_checker.check("")
        assert report.clean

    def test_report_violation_count_matches(self, full_checker):
        report = full_checker.check("src/ghost.c:1 ghost_func() REQ-FAKE-1")
        d = report.to_dict()
        assert d["violation_count"] == len(report.violations)


# ── repo_facts H2-1b: get_all_function_names / get_all_requirement_ids ─────────

class TestRepoFactsH2:
    def test_get_all_function_names_c(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_function_names

        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.c").write_text(
            "void hal_init(void) {}\nstatic int bar_helper(int x) { return x; }\n"
        )
        names = get_all_function_names(tmp_path)
        assert "hal_init" in names
        assert "bar_helper" in names

    def test_get_all_function_names_py(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_function_names

        src = tmp_path / "src"
        src.mkdir()
        (src / "util.py").write_text(
            "def compute_crc(data): pass\nasync def stream_read(fd): pass\n"
        )
        names = get_all_function_names(tmp_path)
        assert "compute_crc" in names
        assert "stream_read" in names

    def test_get_all_function_names_empty_dir(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_function_names

        names = get_all_function_names(tmp_path)
        assert names == set()

    def test_get_all_requirement_ids(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_requirement_ids

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "srs.md").write_text(
            "## REQ-UART-001: Baud rate\nSee also SWR-CAN-01.\n"
        )
        ids = get_all_requirement_ids(tmp_path)
        assert "REQ-UART-001" in ids
        assert "SWR-CAN-01" in ids

    def test_get_all_requirement_ids_empty(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_requirement_ids

        ids = get_all_requirement_ids(tmp_path)
        assert ids == set()

    def test_get_all_requirement_ids_case_normalized(self, tmp_path):
        from yuleosh.pipeline.repo_facts import get_all_requirement_ids

        (tmp_path / "README.md").write_text("Req-uart-001 must be met.\n")
        ids = get_all_requirement_ids(tmp_path)
        assert "REQ-UART-001" in ids
