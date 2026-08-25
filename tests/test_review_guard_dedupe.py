
# @tests src/yuleosh/pipeline/review_guard.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""dedupe_review_findings 单测 (2026-08-20 r22 real-8).

背景: run-937fecd9a2bb code-review 的 LLM 输出同一 finding 重复 30+
次 → 输出超长截断 → JSON 解析失败 → 整个 code-review 报废。
"""

from yuleosh.pipeline.review_guard import dedupe_review_findings


def _finding(sev, file, line, msg):
    return {
        "severity": sev,
        "category": "spec-compliance",
        "file": file,
        "line": line,
        "snippet": f"ctx->cooldownUntilMs = timeMs + ctx->config.cooldownPeriodMs;",
        "message": msg,
    }


class TestDedupeReviewFindings:
    def test_no_duplicates_unchanged(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("critical", "src/a.c", 10, "issue A"),
                _finding("major", "src/b.c", 20, "issue B"),
            ],
        }
        out = dedupe_review_findings(review)
        assert len(out["findings"]) == 2
        assert "dedupe_stats" not in out
        assert out["status"] == "failed"

    def test_duplicates_removed(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("critical", "src/a.c", 10, "same issue"),
                _finding("critical", "src/a.c", 10, "same issue"),
                _finding("critical", "src/a.c", 10, "same issue"),
                _finding("major", "src/b.c", 20, "other issue"),
            ],
        }
        out = dedupe_review_findings(review)
        assert len(out["findings"]) == 2
        assert out["dedupe_stats"]["removed"] == 2
        assert out["dedupe_stats"]["kept"] == 2
        # 去重后仍有 critical+major → status 保持 failed (正确行为)
        assert out["status"] == "failed"
        assert "status_recalculated" not in out

    def test_duplicates_all_minor_recalc_passed(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("minor", "src/a.c", 10, "dup"),
                _finding("minor", "src/a.c", 10, "dup"),
                _finding("info", "src/b.c", 20, "note"),
            ],
        }
        out = dedupe_review_findings(review)
        assert len(out["findings"]) == 2
        # 去重后仅 minor/info → status 重算为 passed
        assert out["status"] == "passed"
        assert "status_recalculated" in out

    def test_duplicate_minor_keeps_failed_status(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("minor", "src/a.c", 10, "dup"),
                _finding("minor", "src/a.c", 10, "dup"),
                _finding("major", "src/b.c", 20, "real major"),
            ],
        }
        out = dedupe_review_findings(review)
        assert len(out["findings"]) == 2
        # 仍有 major → 不重算为 passed
        assert out["status"] == "failed"

    def test_same_message_different_line_kept(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("major", "src/a.c", 10, "same msg"),
                _finding("major", "src/a.c", 11, "same msg"),
            ],
        }
        out = dedupe_review_findings(review)
        assert len(out["findings"]) == 2

    def test_empty_findings_noop(self):
        review = {"status": "passed", "findings": []}
        out = dedupe_review_findings(review)
        assert out["findings"] == []
        assert "dedupe_stats" not in out

    def test_breakdown_recomputed(self):
        review = {
            "status": "failed",
            "findings": [
                _finding("critical", "src/a.c", 10, "dup"),
                _finding("critical", "src/a.c", 10, "dup"),
                _finding("info", "src/b.c", 20, "note"),
            ],
        }
        out = dedupe_review_findings(review)
        # 2 个重复 critical → 去重剩 1 critical + 1 info
        assert out["finding_breakdown"] == {"critical": 1, "major": 0, "minor": 0, "info": 1}
        # 仍有 critical → failed
        assert out["status"] == "failed"
