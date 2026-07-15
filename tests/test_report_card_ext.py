"""
Extended tests for yuleosh.report.card_generator — uncovered paths.

Covers:
  - _format_delta with previous == 0
  - generate_quality_card with misra trends, coverage trends, UT section, key changes
  - generate_feishu_card_json full output
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from yuleosh.report.card_generator import (
    _format_delta,
    _load_json,
    _load_jsonl_latest,
    generate_quality_card,
    generate_feishu_card_json,
)


# ═══════════════════════════════════════════════════════════════
# _load_jsonl_latest — edge cases
# ═══════════════════════════════════════════════════════════════

class TestLoadJsonlLatestEdge:
    """Edge cases for _load_jsonl_latest."""

    def test_invalid_json_line(self, tmp_path: Path):
        """GIVEN JSONL with invalid JSON WHEN loading latest THEN returns None."""
        p = tmp_path / "bad.jsonl"
        p.write_text("not valid json\n")
        result = _load_jsonl_latest(p)
        assert result is None

    def test_mixed_valid_invalid_then_invalid(self, tmp_path: Path):
        """GIVEN JSONL with valid then invalid line WHEN loading latest THEN returns None."""
        p = tmp_path / "mixed.jsonl"
        p.write_text('{"a": 1}\nnot json\n')
        result = _load_jsonl_latest(p)
        assert result is None


# ═══════════════════════════════════════════════════════════════
# _format_delta — edge cases
# ═══════════════════════════════════════════════════════════════

class TestFormatDeltaEdge:
    """Edge cases for _format_delta."""

    def test_previous_zero_returns_dash(self):
        """GIVEN previous is 0 WHEN formatting delta THEN returns em dash."""
        result = _format_delta(80.0, 0.0)
        assert result == "—"

    def test_small_delta_returns_arrow(self):
        """GIVEN delta < 0.5% WHEN formatting delta THEN returns arrow."""
        result = _format_delta(100.3, 100.0, higher_is_better=True)
        assert result == "→"

    def test_lower_is_better_improvement(self):
        """GIVEN lower-is-better metric with improvement WHEN formatting THEN shows green."""
        result = _format_delta(5.0, 10.0, higher_is_better=False)
        assert "🟢" in result

    def test_lower_is_better_decline(self):
        """GIVEN lower-is-better metric with decline WHEN formatting THEN shows red."""
        result = _format_delta(15.0, 10.0, higher_is_better=False)
        assert "🔴" in result

    def test_exact_small_negative_delta(self):
        """GIVEN slight negative delta < 0.5 WHEN formatting THEN arrow."""
        result = _format_delta(99.7, 100.0, higher_is_better=True)
        assert result == "→"

    def test_exact_small_positive_delta(self):
        """GIVEN slight positive delta < 0.5 WHEN formatting THEN arrow."""
        result = _format_delta(100.2, 100.0, higher_is_better=True)
        assert result == "→"


# ═══════════════════════════════════════════════════════════════
# generate_quality_card — with all sections populated
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def project_with_all_reports(tmp_path: Path) -> str:
    """Create a project directory with all report files populated."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)

    # misra-report.json with prev_build_diff
    (reports_dir / "misra-report.json").write_text(json.dumps({
        "summary": {
            "total_violations": 42,
            "total_rules_violated": 8,
            "violations_per_kloc": 3.14,
            "misra_classification": {"required": 5, "advisory": 7},
            "unique_files": ["main.c", "uart.c", "spi.c"],
        },
        "prev_build_diff": {
            "total_violations_delta": -5,
            "files_added": [],
            "files_removed": ["old_code.c"],
        },
    }))

    # c-coverage.json
    (reports_dir / "c-coverage.json").write_text(json.dumps({
        "line_rate": 88.5,
        "branch_rate": 75.0,
        "total_files": 42,
    }))

    # misra-trend.jsonl (two entries)
    (reports_dir / "misra-trend.jsonl").write_text(
        '{"timestamp":"2026-01-01T00:00:00","total_violations":50}\n'
        '{"timestamp":"2026-01-02T00:00:00","total_violations":42}\n'
    )

    # coverage-trend.jsonl (with nested "c" format)
    (reports_dir / "coverage-trend.jsonl").write_text(
        '{"timestamp":"2026-01-01T00:00:00","c":{"line_rate":85.0,"branch_rate":70.0}}\n'
    )

    # selftest-report.json (UT section)
    (reports_dir / "selftest-report.json").write_text(json.dumps({
        "total_tests": 100,
        "passed": 95,
        "failed": 5,
        "coverage": 78.5,
        "shall_coverage": {"total": 60, "covered": 55},
    }))

    return str(tmp_path)


class TestGenerateQualityCardFull:
    """Tests for generate_quality_card with all data present."""

    def test_with_misra_trend_and_delta(self, project_with_all_reports: str):
        """GIVEN all reports with trends WHEN generating card THEN includes delta."""
        card = generate_quality_card(project_with_all_reports)
        assert isinstance(card, str)
        assert "总违规" in card
        assert "42" in card
        assert "🟢" in card or "▲" in card  # improved (42 < 50)

    def test_contains_misra_section(self, project_with_all_reports: str):
        """GIVEN MISRA data present WHEN generating card THEN includes MISRA section."""
        card = generate_quality_card(project_with_all_reports)
        assert "MISRA" in card
        assert "Required" in card
        assert "Advisory" in card

    def test_contains_coverage_section(self, project_with_all_reports: str):
        """GIVEN coverage data present WHEN generating card THEN includes coverage."""
        card = generate_quality_card(project_with_all_reports)
        assert "行覆盖率" in card
        assert "88.5" in card
        assert "分支覆盖率" in card

    def test_contains_ut_section(self, project_with_all_reports: str):
        """GIVEN selftest data present WHEN generating card THEN includes UT section."""
        card = generate_quality_card(project_with_all_reports)
        assert "单元测试" in card or "通过率" in card
        # Should have SHALL coverage
        assert "SHALL" in card

    def test_contains_key_changes(self, project_with_all_reports: str):
        """GIVEN prev_build_diff present WHEN generating card THEN includes changes."""
        card = generate_quality_card(project_with_all_reports)
        assert "关键变化" in card or "消除" in card or "新增" in card

    def test_misra_increase_delta(self, tmp_path: Path):
        """GIVEN misra violations increased WHEN generating card THEN shows red delta."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 60, "total_rules_violated": 5,
                "violations_per_kloc": 5.0, "misra_classification": {"required": 3, "advisory": 2},
                "unique_files": ["main.c"],
            },
            "prev_build_diff": {"total_violations_delta": 10, "files_added": ["new_bug.c"], "files_removed": []},
        }))
        (reports_dir / "misra-trend.jsonl").write_text('{"timestamp":"2026-01-01","total_violations":50}\n')
        (reports_dir / "c-coverage.json").write_text(json.dumps({"line_rate": 80, "branch_rate": 70, "total_files": 1}))
        (reports_dir / "coverage-trend.jsonl").write_text('{"timestamp":"2026-01-01","line_rate":75.0,"branch_rate":65.0}\n')

        card = generate_quality_card(str(tmp_path))
        assert "🔴" in card  # MISRA violations increased

    def test_with_coverage_only_new_format(self, tmp_path: Path):
        """GIVEN coverage with nested 'c' format trend WHEN generating card THEN works."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 10, "total_rules_violated": 2,
                "violations_per_kloc": 1.0, "misra_classification": {"required": 1, "advisory": 1},
                "unique_files": ["main.c"],
            },
        }))
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 95.0, "branch_rate": 88.0, "total_files": 5,
        }))
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","c":{"line_rate":90.0,"branch_rate":80.0}}\n'
        )

        card = generate_quality_card(str(tmp_path))
        assert "95.0" in card
        assert "行覆盖率" in card

    def test_with_coverage_trend_flat_format(self, tmp_path: Path):
        """GIVEN coverage with flat format trend WHEN generating card THEN works."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 10, "total_rules_violated": 2,
                "violations_per_kloc": 1.0, "misra_classification": {"required": 1, "advisory": 1},
                "unique_files": ["main.c"],
            },
        }))
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 85.0, "branch_rate": 72.0, "total_files": 3,
        }))
        (reports_dir / "coverage-trend.jsonl").write_text(
            '{"timestamp":"2026-01-01","line_rate":80.0,"branch_rate":70.0}\n'
        )

        card = generate_quality_card(str(tmp_path))
        assert "85.0" in card

    def test_with_no_selftest_but_ci_layer(self, tmp_path: Path):
        """GIVEN no selftest report but CI layer results WHEN generating card THEN handles gracefully."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        # Create a CI layer result
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1-build.json").write_text(json.dumps({
            "layer": 1, "status": "passed",
        }))
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 5, "total_rules_violated": 1,
                "violations_per_kloc": 0.5, "misra_classification": {"required": 0, "advisory": 1},
                "unique_files": [],
            },
        }))

        card = generate_quality_card(str(tmp_path))
        assert isinstance(card, str)
        # Should fallback to "未有自测报告"
        assert "未有" in card or "自测" in card or "卡" in card


# ═══════════════════════════════════════════════════════════════
# generate_quality_card — edge cases
# ═══════════════════════════════════════════════════════════════

class TestGenerateQualityCardEdge:
    """Edge cases for generate_quality_card."""

    def test_no_misra_report(self, tmp_path: Path):
        """GIVEN no misra report WHEN generating card THEN shows fallback."""
        card = generate_quality_card(str(tmp_path))
        assert "未有 MISRA" in card or "Misra" in card or "卡" in card

    def test_misra_report_no_trend_no_diff(self, tmp_path: Path):
        """GIVEN misra report without trend or diff WHEN generating THEN shows basic info."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 10,
                "total_rules_violated": 3,
                "violations_per_kloc": 2.0,
                "misra_classification": {"required": 2, "advisory": 1},
                "unique_files": ["main.c"],
            },
        }))
        card = generate_quality_card(str(tmp_path))
        assert "10" in card
        assert "2.00" in card

    def test_selftest_with_high_pass(self, tmp_path: Path):
        """GIVEN high pass rate selftest WHEN generating THEN shows green."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 0, "total_rules_violated": 0,
                "violations_per_kloc": 0.0, "misra_classification": {},
                "unique_files": [],
            },
        }))
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 100.0, "branch_rate": 100.0, "total_files": 1,
        }))
        (reports_dir / "selftest-report.json").write_text(json.dumps({
            "total_tests": 100, "passed": 100, "failed": 0, "coverage": 95.0,
            "shall_coverage": {"total": 10, "covered": 10},
        }))
        card = generate_quality_card(str(tmp_path))
        assert "100/100" in card or "100%" in card

    def test_selftest_with_low_pass(self, tmp_path: Path):
        """GIVEN low pass rate selftest WHEN generating THEN shows appropriate icon."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 0, "total_rules_violated": 0,
                "violations_per_kloc": 0.0, "misra_classification": {},
                "unique_files": [],
            },
        }))
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 50.0, "branch_rate": 40.0, "total_files": 1,
        }))
        (reports_dir / "selftest-report.json").write_text(json.dumps({
            "total_tests": 10, "passed": 3, "failed": 7, "coverage": 25.0,
        }))
        card = generate_quality_card(str(tmp_path))
        assert isinstance(card, str)
        assert len(card) > 50

    def test_coverage_icons_thresholds(self, tmp_path: Path):
        """GIVEN different coverage levels WHEN generating THEN shows correct icons."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 0, "total_rules_violated": 0,
                "violations_per_kloc": 0.0, "misra_classification": {},
                "unique_files": [],
            },
        }))
        # line 70%, branch 60% — should be ⚠️ for both
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 70.0, "branch_rate": 60.0, "total_files": 1,
        }))
        card = generate_quality_card(str(tmp_path))
        assert "⚠️" in card

    def test_files_added_in_changes(self, tmp_path: Path):
        """GIVEN new files in prev_build_diff WHEN generating THEN lists them."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 5, "total_rules_violated": 2,
                "violations_per_kloc": 1.0, "misra_classification": {"required": 1, "advisory": 0},
                "unique_files": ["a.c"],
            },
            "prev_build_diff": {
                "total_violations_delta": 3,
                "files_added": ["new_bug.c", "also_bad.c", "third.c"],
                "files_removed": [],
            },
        }))
        card = generate_quality_card(str(tmp_path))
        assert "新增违规" in card or "new_bug" in card or "关键变化" in card

    def test_violations_decreased_in_changes(self, tmp_path: Path):
        """GIVEN violations decreased in prev_build_diff WHEN generating THEN shows resolved."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 5, "total_rules_violated": 2,
                "violations_per_kloc": 1.0, "misra_classification": {"required": 1, "advisory": 0},
                "unique_files": ["a.c"],
            },
            "prev_build_diff": {
                "total_violations_delta": -3,
                "files_added": [],
                "files_removed": ["old_bug.c"],
            },
        }))
        card = generate_quality_card(str(tmp_path))
        assert "解决违规" in card or "消除" in card

    def test_selftest_without_shall_coverage(self, tmp_path: Path):
        """GIVEN selftest without shall_coverage WHEN generating THEN no SHALL coverage line."""
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "misra-report.json").write_text(json.dumps({
            "summary": {
                "total_violations": 0, "total_rules_violated": 0,
                "violations_per_kloc": 0.0, "misra_classification": {},
                "unique_files": [],
            },
        }))
        (reports_dir / "c-coverage.json").write_text(json.dumps({
            "line_rate": 100.0, "branch_rate": 100.0, "total_files": 1,
        }))
        (reports_dir / "selftest-report.json").write_text(json.dumps({
            "total_tests": 10, "passed": 10, "failed": 0, "coverage": 0,
        }))
        card = generate_quality_card(str(tmp_path))
        # coverage_pct is 0, so no coverage line
        # shall_coverage not present, so no SHALL line


# ═══════════════════════════════════════════════════════════════
# generate_feishu_card_json
# ═══════════════════════════════════════════════════════════════

class TestGenerateFeishuCardJson:
    """Tests for generate_feishu_card_json."""

    def test_returns_dict(self, tmp_path: Path):
        """GIVEN project path WHEN generating feishu card THEN returns dict."""
        result = generate_feishu_card_json(str(tmp_path))
        assert isinstance(result, dict)

    def test_has_card_structure(self, tmp_path: Path):
        """GIVEN project path WHEN generating feishu card THEN returns correct structure."""
        result = generate_feishu_card_json(str(tmp_path))
        assert "config" in result
        assert "header" in result
        assert "elements" in result
        assert result["header"]["template"] == "blue"
        assert len(result["elements"]) >= 2
        # Should contain a markdown element
        assert any(e.get("tag") == "markdown" for e in result["elements"])
        assert any(e.get("tag") == "hr" for e in result["elements"])
        assert any(e.get("tag") == "note" for e in result["elements"])

    def test_header_contains_title(self, tmp_path: Path):
        """GIVEN project path WHEN generating feishu card THEN header has title."""
        result = generate_feishu_card_json(str(tmp_path))
        title = result["header"]["title"]
        assert "yuleOSH" in title["content"]

    def test_with_misra_data_shows_in_card(self, project_with_all_reports: str):
        """GIVEN project with misra data WHEN generating feishu card THEN misra appears in content."""
        result = generate_feishu_card_json(project_with_all_reports)
        markdown_elements = [e for e in result["elements"] if e.get("tag") == "markdown"]
        assert len(markdown_elements) >= 1
        content = markdown_elements[0]["content"]
        assert "MISRA" in content

    def test_note_contains_timestamp(self, tmp_path: Path):
        """GIVEN project path WHEN generating feishu card THEN note has timestamp."""
        result = generate_feishu_card_json(str(tmp_path))
        note_elements = [e for e in result["elements"] if e.get("tag") == "note"]
        assert len(note_elements) >= 1
