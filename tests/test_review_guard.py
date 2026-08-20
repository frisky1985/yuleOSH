# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Review hallucination guard 单测 (2026-08-20 r22 real-4 复盘).

背景: run-69f7d4ae221f 两个 LLM 审查步骤出现系统性幻觉 —
  - internal-code-review 报 hal_hall.c:54 语法错误 (文件仅 53 行, 构建通过)
  - code-review 报 window_modes.c:124 无 (void) 抑制 (实际 137 行有) 等
本模块 (review_guard.py) 提供:
  - numbered_source            — 源码注入带真实行号前缀
  - validate_review_findings   — file:line 存在性自动验证, 幻觉降级 info
"""

import pytest

from yuleosh.pipeline.review_guard import (
    numbered_source,
    validate_review_findings,
)

SRC_HALL = "\n".join(f"line{i}" for i in range(1, 54))  # 53 行真实文件
SRC_MODES = "\n".join(f"code{i}" for i in range(1, 200))  # 199 行真实文件

SOURCE_FILES = [
    {"path": "src/hal/src/hal_hall.c", "lines": 53, "content": SRC_HALL},
    {"path": "src/app/src/window_modes.c", "lines": 199, "content": SRC_MODES},
]


class TestNumberedSource:
    def test_short_content_passthrough(self):
        assert numbered_source("a\nb") == "1| a\n2| b"

    def test_blank_content(self):
        assert numbered_source("") == ""

    def test_line_numbers_are_real(self):
        out = numbered_source(SRC_HALL)
        lines = out.splitlines()
        assert lines[0].startswith(" 1| ")
        assert lines[-1].startswith("53| ")
        assert len(lines) == 53


class TestValidateReviewFindings:
    def test_valid_finding_unchanged(self):
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/app/src/window_modes.c",
                    "line": 137,
                    "message": "real issue",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        assert review["findings"][0]["severity"] == "critical"
        assert "hallucinated" not in review["findings"][0]
        assert "hallucination_stats" not in review

    def test_line_out_of_range_flagged_and_downgraded(self):
        # 复现 run-69f7d4ae221f: hal_hall.c 仅 53 行, LLM 报 line 54
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/hal/src/hal_hall.c",
                    "line": 54,
                    "message": "Syntax error: incomplete comment block",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        f = review["findings"][0]
        assert f["hallucinated"] is True
        assert f["severity"] == "info"
        assert f["severity_original"] == "critical"
        assert "line 54 超出" in f["hallucination_reason"]
        # 全幻觉 critical → status 重算 passed
        assert review["status"] == "passed"
        assert review["hallucination_stats"]["hallucinated_findings"] == 1
        assert review["finding_breakdown"] == {
            "critical": 0, "major": 0, "minor": 0, "info": 1,
        }

    def test_file_not_in_injected_set_flagged(self):
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "major",
                    "file": "src/never_injected.c",
                    "line": 3,
                    "message": "issue in unseen file",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        f = review["findings"][0]
        assert f["hallucinated"] is True
        assert f["severity"] == "info"
        assert "不在本次注入的源码集合中" in f["hallucination_reason"]

    def test_non_integer_line_flagged(self):
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/app/src/window_modes.c",
                    "line": "abc",
                    "message": "bad line",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        assert review["findings"][0]["hallucinated"] is True

    def test_mixed_real_and_hallucinated_keeps_failed(self):
        # 1 条真实 critical + 1 条幻觉 → 仍 failed (真实问题不能掩盖)
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/app/src/window_modes.c",
                    "line": 137,
                    "message": "real issue",
                },
                {
                    "severity": "critical",
                    "file": "src/hal/src/hal_hall.c",
                    "line": 54,
                    "message": "hallucinated syntax error",
                },
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        assert review["status"] == "failed"
        assert review["findings"][0].get("hallucinated") is not True
        assert review["findings"][1]["hallucinated"] is True
        assert review["hallucination_stats"]["hallucinated_findings"] == 1

    def test_line_zero_flagged(self):
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "minor",
                    "file": "src/app/src/window_modes.c",
                    "line": 0,
                    "message": "line zero",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        assert review["findings"][0]["hallucinated"] is True

    def test_no_findings_noop(self):
        review = {"status": "passed", "findings": []}
        validate_review_findings(review, SOURCE_FILES)
        assert review == {"status": "passed", "findings": []}

    def test_snippet_mismatch_flagged(self):
        # 复现 run-a97bd1d51fdf 内容错位: line 87 是 IDLE cooldown,
        # 但 LLM 报 G-18 violation (FAULT 检查), snippet 与真实行不匹配
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/app/src/window_modes.c",
                    "line": 3,
                    "snippet": "if (ctx->state == WINDOW_CONTROL_CLOSING)",
                    "message": "G-18 violation",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        f = review["findings"][0]
        assert f["hallucinated"] is True
        assert f["severity"] == "info"
        assert "snippet 与" in f["hallucination_reason"]

    def test_snippet_match_kept(self):
        # snippet 与真实行内容匹配 → 非幻觉
        review = {
            "status": "failed",
            "findings": [
                {
                    "severity": "critical",
                    "file": "src/app/src/window_modes.c",
                    "line": 3,
                    "snippet": "code3",
                    "message": "real issue on line 3",
                }
            ],
        }
        validate_review_findings(review, SOURCE_FILES)
        f = review["findings"][0]
        assert f.get("hallucinated") is not True
        assert f["severity"] == "critical"
