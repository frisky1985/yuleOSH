#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
深度测试 — yuleOSH MISRA 3-Layer Fusion (ci.misra_fusion)

Covers:
  - FusionReport.merge: ALL_CONFIRM, MAJORITY, SINGLE, CONTRADICT, empty, single-layer
  - to_json / to_markdown output methods
  - parse_cppcheck_layer, parse_clang_tidy_layer, parse_ai_review_layer
  - Violation / FusedViolation / LayerResult dataclass behaviour
  - _clean_dict edge cases (NaN, sets, empty)
  - CLI main entry point
"""

import json
import math
from datetime import datetime
from pathlib import Path

import pytest
from unittest import mock

from yuleosh.ci.misra_fusion import (
    Violation,
    LayerResult,
    FusedViolation,
    FusionReport,
    parse_cppcheck_layer,
    parse_clang_tidy_layer,
    parse_ai_review_layer,
)


# ═════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_violations() -> tuple[list[Violation], list[Violation], list[Violation]]:
    """GIVEN three layers with two overlapping violations."""
    cppcheck_vs = [
        Violation(file="src/main.c", line=42, column=5, rule_id="misra-c2023-10.1",
                  severity="error", message="Bad cast", layer="cppcheck"),
        Violation(file="src/main.c", line=99, column=1, rule_id="misra-c2023-14.4",
                  severity="warning", message="Bad type", layer="cppcheck"),
    ]
    clang_tidy_vs = [
        Violation(file="src/main.c", line=42, column=5, rule_id="misra-c2023-10.1",
                  severity="error", message="Bad cast", layer="clang-tidy"),
        Violation(file="src/utils.c", line=10, column=3, rule_id="misra-c2023-17.7",
                  severity="warning", message="Unused return", layer="clang-tidy"),
    ]
    ai_review_vs = [
        Violation(file="src/main.c", line=42, column=5, rule_id="misra-c2023-10.1",
                  severity="error", message="Bad cast", layer="ai-review",
                  false_positive_chance=0.1),
        Violation(file="src/main.c", line=200, column=1, rule_id="misra-c2023-8.4",
                  severity="style", message="Missing prototype", layer="ai-review"),
    ]
    return cppcheck_vs, clang_tidy_vs, ai_review_vs


# ═════════════════════════════════════════════════════════════════════════════
#  Violation / LayerResult / FusedViolation dataclass tests
# ═════════════════════════════════════════════════════════════════════════════


class TestViolationDataclass:
    """GIVEN a Violation dataclass"""

    def test_default_values(self) -> None:
        """WHEN creating a Violation with only required fields THEN defaults are set."""
        v = Violation(file="f.c", line=1)
        assert v.file == "f.c"
        assert v.line == 1
        assert v.column == 0
        assert v.rule_id == ""
        assert v.severity == "style"
        assert v.message == ""
        assert v.layer == "unknown"
        assert v.category == ""
        assert v.false_positive_chance == 0.0

    def test_full_construction(self) -> None:
        """WHEN creating a Violation with all fields THEN values are stored."""
        v = Violation(file="a.c", line=10, column=3, rule_id="misra-c2023-10.1",
                      severity="error", message="Bad op", layer="cppcheck",
                      category="required", false_positive_chance=0.05)
        assert v.file == "a.c"
        assert v.line == 10
        assert v.false_positive_chance == 0.05
        assert v.category == "required"


class TestLayerResultDataclass:
    """GIVEN a LayerResult dataclass"""

    def test_default_construction(self) -> None:
        """WHEN creating a LayerResult with only tool THEN defaults are zero/empty."""
        lr = LayerResult(tool="cppcheck")
        assert lr.tool == "cppcheck"
        assert lr.violations == []
        assert lr.files_analyzed == 0
        assert lr.duration_seconds == 0.0
        assert lr.error == ""


class TestFusedViolationDataclass:
    """GIVEN a FusedViolation dataclass"""

    def test_default_construction(self) -> None:
        """WHEN creating a FusedViolation with required fields THEN defaults."""
        fv = FusedViolation(file="f.c", line=1, rule_id="R1", message="msg",
                            confidence="SINGLE", layers_found=["cppcheck"],
                            layers_cleared=["clang-tidy", "ai-review"])
        assert fv.confidence == "SINGLE"
        assert fv.layers_found == ["cppcheck"]
        assert fv.layers_cleared == ["clang-tidy", "ai-review"]
        assert fv.original_violations == []


# ═════════════════════════════════════════════════════════════════════════════
#  FusionReport.merge — core fusion logic
# ═════════════════════════════════════════════════════════════════════════════


class TestFusionReportMerge:
    """GIVEN FusionReport.merge() cross-validation logic"""

    def test_all_three_confirm(self, sample_violations) -> None:
        """WHEN all three layers flag the same violation THEN confidence is ALL_CONFIRM."""
        cpp, ct, ai = sample_violations
        # cpp[0] = (main.c:42, 10.1), ct[0] = (main.c:42, 10.1), ai[0] = (main.c:42, 10.1)
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=[cpp[0]]),
            LayerResult(tool="clang-tidy", violations=[ct[0]]),
            LayerResult(tool="ai-review", violations=[ai[0]]),
        )
        assert len(report.fused_violations) == 1
        assert report.fused_violations[0].confidence == "ALL_CONFIRM"
        assert report.fused_violations[0].layers_found == ["cppcheck", "clang-tidy", "ai-review"]
        assert report.summary["all_confirmed"] == 1
        assert report.summary["high_confidence_pct"] == 100.0

    def test_two_layers_agree(self, sample_violations) -> None:
        """WHEN two layers flag the same violation THEN confidence is MAJORITY."""
        cpp, ct, ai = sample_violations
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=[cpp[0]]),
            LayerResult(tool="clang-tidy", violations=[ct[0]]),
            LayerResult(tool="ai-review", violations=[]),
        )
        assert len(report.fused_violations) == 1
        assert report.fused_violations[0].confidence == "MAJORITY"
        assert report.summary["majority"] == 1

    def test_single_layer_only(self) -> None:
        """WHEN only one layer detects a violation THEN confidence is SINGLE."""
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=[]),
            LayerResult(tool="clang-tidy", violations=[]),
            LayerResult(tool="ai-review", violations=[
                Violation(file="f.c", line=1, column=0, rule_id="misra-c2023-10.1",
                          message="Solo", layer="ai-review"),
            ]),
        )
        assert len(report.fused_violations) == 1
        assert report.fused_violations[0].confidence == "SINGLE"
        assert report.summary["single_source"] == 1

    def test_no_violations(self) -> None:
        """WHEN no layer reports any violations THEN empty report with zero summary."""
        report = FusionReport.merge(
            LayerResult(tool="cppcheck"),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        assert report.fused_violations == []
        assert report.summary["total_fused_violations"] == 0
        assert report.summary["high_confidence_pct"] == 0.0

    def test_multiple_violations_complex(self, sample_violations) -> None:
        """WHEN merging multiple violations with different overlap patterns THEN each is classified correctly."""
        cpp, ct, ai = sample_violations
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=cpp),
            LayerResult(tool="clang-tidy", violations=ct),
            LayerResult(tool="ai-review", violations=ai),
        )
        # 4 unique (file, line, rule_id) keys:
        #   (main.c, 42, 10.1) → ALL_CONFIRM (3 layers)
        #   (main.c, 99, 14.4) → SINGLE (cppcheck only)
        #   (utils.c, 10, 17.7) → SINGLE (clang-tidy only)
        #   (main.c, 200, 8.4) → SINGLE (ai-review only)
        assert len(report.fused_violations) == 4
        confidences = {fv.confidence for fv in report.fused_violations}
        assert "ALL_CONFIRM" in confidences
        assert "SINGLE" in confidences
        assert report.summary["all_confirmed"] == 1
        assert report.summary["single_source"] == 3

    def test_false_positive_probability_averaged(self) -> None:
        """WHEN multiple violations share a key THEN FP probability is averaged."""
        cpp = [Violation(file="f.c", line=1, rule_id="R1", false_positive_chance=0.0, layer="cppcheck")]
        ct = [Violation(file="f.c", line=1, rule_id="R1", false_positive_chance=0.0, layer="clang-tidy")]
        ai = [Violation(file="f.c", line=1, rule_id="R1", false_positive_chance=0.8, layer="ai-review")]
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=cpp),
            LayerResult(tool="clang-tidy", violations=ct),
            LayerResult(tool="ai-review", violations=ai),
        )
        fv = report.fused_violations[0]
        # Only ai-review has fp > 0, so average = 0.8 / 1 = 0.8
        assert fv.false_positive_probability == pytest.approx(0.8)

    def test_summary_severity_breakdown(self) -> None:
        """WHEN merging violations with different severities THEN severity_breakdown is accurate."""
        cpp = [
            Violation(file="f.c", line=1, rule_id="R1", severity="error", layer="cppcheck"),
            Violation(file="f.c", line=2, rule_id="R2", severity="warning", layer="cppcheck"),
        ]
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=cpp),
            LayerResult(tool="clang-tidy", violations=[]),
            LayerResult(tool="ai-review", violations=[]),
        )
        assert report.summary["severity_breakdown"]["error"] == 1
        assert report.summary["severity_breakdown"]["warning"] == 1
        assert report.summary["severity_breakdown"]["style"] == 0


# ═════════════════════════════════════════════════════════════════════════════
#  FusionReport output methods
# ═════════════════════════════════════════════════════════════════════════════


class TestFusionReportOutput:
    """GIVEN FusionReport output methods"""

    def test_to_json_creates_file(self, tmp_path) -> None:
        """WHEN to_json is called THEN a JSON file is created at the given path."""
        report = FusionReport.merge(
            LayerResult(tool="cppcheck"),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        out = tmp_path / "report.json"
        result = report.to_json(str(out))
        assert result == str(out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert "fused_violations" in data
        assert "summary" in data
        assert "generated_at" in data

    def test_to_json_omits_original_violations(self, tmp_path) -> None:
        """WHEN to_json serialises THEN original_violations is removed from each fused entry."""
        cpp = [Violation(file="f.c", line=1, rule_id="R1", layer="cppcheck")]
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=cpp),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        out = tmp_path / "report.json"
        report.to_json(str(out))
        data = json.loads(out.read_text())
        for fv in data["fused_violations"]:
            assert "original_violations" not in fv

    def test_to_markdown_contains_key_sections(self) -> None:
        """WHEN to_markdown is called THEN it returns markdown with expected sections."""
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=[
                Violation(file="src/main.c", line=1, rule_id="R1", layer="cppcheck"),
            ]),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        md = report.to_markdown()
        assert "MISRA" in md
        assert "汇总" in md
        assert "融合结果明细" in md
        assert "分析" in md
        assert "建议" in md

    def test_to_markdown_truncates_over_50(self) -> None:
        """WHEN more than 50 fused violations exist THEN markdown shows truncation notice."""
        cpp_vs = [
            Violation(file=f"src/f{i}.c", line=1, rule_id=f"R{i}", layer="cppcheck")
            for i in range(60)
        ]
        report = FusionReport.merge(
            LayerResult(tool="cppcheck", violations=cpp_vs),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        md = report.to_markdown()
        assert "共 60 条" in md or "60" in md

    def test_generated_at_is_set_on_merge(self) -> None:
        """WHEN merging THEN generated_at is set to an ISO timestamp."""
        report = FusionReport.merge(
            LayerResult(tool="cppcheck"),
            LayerResult(tool="clang-tidy"),
            LayerResult(tool="ai-review"),
        )
        assert report.generated_at
        # Should be parseable as ISO datetime
        datetime.fromisoformat(report.generated_at)


# ═════════════════════════════════════════════════════════════════════════════
#  Parser tests
# ═════════════════════════════════════════════════════════════════════════════


class TestParseCppcheckLayer:
    """GIVEN parse_cppcheck_layer()"""

    def test_parse_typical_output(self) -> None:
        """WHEN given standard cppcheck MISRA output THEN violations are extracted."""
        text = (
            "/src/main.c:42:5: error: Bad cast [misra-c2023-10.1]\n"
            "/src/main.c:99:1: warning: Bad type [misra-c2023-14.4]\n"
        )
        result = parse_cppcheck_layer(text)
        assert result.tool == "cppcheck"
        assert len(result.violations) == 2
        assert result.files_analyzed == 1
        v0 = result.violations[0]
        assert v0.file == "/src/main.c"
        assert v0.line == 42
        assert v0.column == 5
        assert v0.severity == "error"
        assert v0.rule_id == "misra-c2023-10.1"
        assert v0.layer == "cppcheck"

    def test_parse_alt_rule_format(self) -> None:
        """WHEN cppcheck output uses 'MISRA rule: X.X' format THEN rule_id is still extracted."""
        text = "/src/main.c:10:0: style: MISRA rule: 8.4 [misra-rule]\n"
        result = parse_cppcheck_layer(text)
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "misra-c2023-8.4"

    def test_parse_empty_text(self) -> None:
        """WHEN given empty text THEN no violations."""
        result = parse_cppcheck_layer("")
        assert result.violations == []
        assert result.files_analyzed == 0

    def test_parse_multiple_files(self) -> None:
        """WHEN violations span multiple files THEN files_analyzed is correct."""
        text = (
            "/src/a.c:1:0: style: msg [misra-c2023-1.1]\n"
            "/src/b.c:2:0: style: msg [misra-c2023-1.2]\n"
            "/src/a.c:3:0: style: msg [misra-c2023-1.3]\n"
        )
        result = parse_cppcheck_layer(text)
        assert result.files_analyzed == 2


class TestParseClangTidyLayer:
    """GIVEN parse_clang_tidy_layer()"""

    def test_parse_typical_output(self) -> None:
        """WHEN given standard clang-tidy MISRA output THEN violations are extracted."""
        text = (
            "/src/main.c:42:5: warning: MISRA rule 10.1 [misra-c2023-10.1]\n"
            "/src/utils.c:10:3: error: MISRA rule 17.7 [misra-c2023-17.7]\n"
        )
        result = parse_clang_tidy_layer(text)
        assert result.tool == "clang-tidy"
        assert len(result.violations) == 2
        assert result.violations[0].rule_id == "misra-c2023-10.1"
        assert result.violations[0].severity == "warning"
        assert result.violations[1].rule_id == "misra-c2023-17.7"
        assert result.violations[1].severity == "error"

    def test_parse_note_severity(self) -> None:
        """WHEN clang-tidy uses 'note' severity THEN it is parsed."""
        text = "/src/main.c:5:1: note: Not really a MISRA violation [misra-other]\n"
        result = parse_clang_tidy_layer(text)
        assert len(result.violations) == 1
        assert result.violations[0].severity == "note"


class TestParseAiReviewLayer:
    """GIVEN parse_ai_review_layer()"""

    def test_parse_valid_json_dict(self) -> None:
        """WHEN given a valid dict THEN violations are extracted."""
        data = {
            "files_analyzed": 2,
            "duration_seconds": 1.5,
            "violations": [
                {"file": "src/main.c", "line": 42, "rule_id": "misra-c2023-10.1",
                 "severity": "required", "message": "Bad", "false_positive_chance": 0.1},
            ],
        }
        result = parse_ai_review_layer(data)
        assert result.tool == "ai-review"
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "misra-c2023-10.1"
        assert result.violations[0].false_positive_chance == 0.1
        assert result.files_analyzed == 2
        assert result.duration_seconds == 1.5

    def test_parse_valid_json_string(self) -> None:
        """WHEN given a valid JSON string THEN violations are extracted."""
        json_str = '{"violations": [{"file": "f.c", "line": 1, "rule_id": "R1"}]}'
        result = parse_ai_review_layer(json_str)
        assert len(result.violations) == 1
        assert result.violations[0].file == "f.c"

    def test_parse_invalid_json_string(self) -> None:
        """WHEN given invalid JSON THEN LayerResult has error."""
        result = parse_ai_review_layer("not json at all")
        assert result.tool == "ai-review"
        assert result.error == "Invalid JSON input"
        assert result.violations == []

    def test_parse_empty_violations(self) -> None:
        """WHEN JSON has no violations THEN empty result."""
        result = parse_ai_review_layer({"violations": []})
        assert result.violations == []


# ═════════════════════════════════════════════════════════════════════════════
#  _clean_dict edge cases
# ═════════════════════════════════════════════════════════════════════════════


class TestCleanDict:
    """GIVEN FusionReport._clean_dict static method"""

    def test_handles_sets(self) -> None:
        """WHEN a dict factory sees a set value THEN it is converted to a list."""
        result = FusionReport._clean_dict([("key", {1, 2, 3})])
        assert result["key"] == [1, 2, 3]

    def test_handles_nan(self) -> None:
        """WHEN a dict factory sees a NaN float THEN it is converted to None."""
        result = FusionReport._clean_dict([("key", float("nan"))])
        assert result["key"] is None

    def test_passes_regular_values(self) -> None:
        """WHEN values are regular types THEN they pass through."""
        result = FusionReport._clean_dict([
            ("s", "hello"),
            ("i", 42),
            ("f", 3.14),
            ("b", True),
            ("l", [1, 2]),
        ])
        assert result["s"] == "hello"
        assert result["i"] == 42
        assert result["f"] == 3.14
        assert result["b"] is True
        assert result["l"] == [1, 2]


# ═════════════════════════════════════════════════════════════════════════════
#  CLI main entry point
# ═════════════════════════════════════════════════════════════════════════════


class TestMain:
    """GIVEN the CLI main() entry point"""

    def test_main_with_all_files(self, tmp_path) -> None:
        """WHEN main runs with all three input files THEN report is generated."""
        # Write mock input files
        (tmp_path / "cppcheck.txt").write_text("/src/main.c:1:0: style: msg [misra-c2023-1.1]\n")
        (tmp_path / "clang.txt").write_text("/src/main.c:1:0: warning: msg [misra-c2023-1.1]\n")
        (tmp_path / "ai.json").write_text('{"violations": [{"file": "src/main.c", "line": 1, "rule_id": "misra-c2023-1.1"}]}')

        output = tmp_path / "out.json"
        with mock.patch("sys.argv", [
            "misra_fusion.py",
            "--cppcheck", str(tmp_path / "cppcheck.txt"),
            "--clang-tidy", str(tmp_path / "clang.txt"),
            "--ai-review", str(tmp_path / "ai.json"),
            "--output", str(output),
        ]):
            from yuleosh.ci.misra_fusion import main
            main()
        assert output.exists()
        data = json.loads(output.read_text())
        # cppcheck and clang-tidy both produce /src/main.c (with slash),
        # but AI review JSON has src/main.c (no slash) — different keys
        assert data["summary"]["total_fused_violations"] == 2
        assert data["summary"]["majority"] == 1
        assert data["summary"]["single_source"] == 1

    def test_main_with_minimal_args(self, tmp_path) -> None:
        """WHEN main runs with minimal arguments THEN empty report is created."""
        output = tmp_path / "out.json"
        with mock.patch("sys.argv", [
            "misra_fusion.py",
            "--output", str(output),
        ]):
            from yuleosh.ci.misra_fusion import main
            main()
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["summary"]["total_fused_violations"] == 0

    def test_main_with_markdown_flag(self, tmp_path) -> None:
        """WHEN main runs with --markdown THEN both JSON and MD are created."""
        output = tmp_path / "out.json"
        with mock.patch("sys.argv", [
            "misra_fusion.py",
            "--output", str(output),
            "--markdown",
        ]):
            from yuleosh.ci.misra_fusion import main
            main()
        md_path = Path(str(output).replace(".json", ".md"))
        assert output.exists()
        assert md_path.exists()
