# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""JSONL review 解析单测 (2026-08-20 r22 real-10, 截断容错根治).

背景: code-review 的 LLM 输出同一 finding 重复 30+ 次 → 超 max_tokens
截断 → 旧 JSON 格式"全有或全无" → 整份报废。JSONL 格式第一行 header,
每行一个 finding, 截断只丢最后一行。
"""

import json

from yuleosh.pipeline.stages.spec import _parse_jsonl_review

HEADER = (
    '{"session": "run-1", "reviewer": "Hermes", "timestamp": "2026-08-20T00:00:00", '
    '"status": "failed", "finding_breakdown": {"critical": 1, "major": 0, '
    '"minor": 0, "info": 0}, "summary": "two issues"}'
)
F1 = (
    '{"severity": "critical", "category": "spec-compliance", '
    '"file": "src/a.c", "line": 10, "snippet": "ctx->x = 1;", '
    '"message": "issue one"}'
)
F2 = (
    '{"severity": "minor", "category": "style", '
    '"file": "src/b.c", "line": 20, "snippet": "int y;", '
    '"message": "issue two"}'
)


class TestParseJsonlReview:
    def test_header_plus_findings(self):
        raw = f"{HEADER}\n{F1}\n{F2}\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert out["status"] == "failed"
        assert len(out["findings"]) == 2
        assert out["finding_breakdown"]["critical"] == 1
        assert out["finding_breakdown"]["minor"] == 1
        assert out["_jsonl_format"] is True

    def test_header_only_no_findings(self):
        raw = HEADER
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert out["findings"] == []
        # header 自报 critical:1 但无 findings 证据 → 信任证据, breakdown 重算
        assert out["finding_breakdown"]["critical"] == 0
        assert out["status"] == "passed"

    def test_truncated_last_line_survives(self):
        # 最后一行被截断 (输出超 max_tokens) — 只丢该行, 前面全部存活
        truncated_f2 = F2[:-10]  # 故意截断
        raw = f"{HEADER}\n{F1}\n{truncated_f2}\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert len(out["findings"]) == 1
        assert out["findings"][0]["file"] == "src/a.c"
        assert out["finding_breakdown"]["critical"] == 1
        assert out["finding_breakdown"]["minor"] == 0

    def test_duplicate_findings_all_survive(self):
        # 重复膨胀仍会产生多行 — 但解析层不丢失, 由 dedupe 层去重
        raw = f"{HEADER}\n{F1}\n{F1}\n{F1}\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert len(out["findings"]) == 3

    def test_noisy_lines_skipped(self):
        raw = f"some preamble text\n{HEADER}\n{F1}\nNOTE: done\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert len(out["findings"]) == 1

    def test_legacy_full_json_still_works(self):
        legacy = {
            "session": "run-1",
            "status": "failed",
            "findings": [
                {"severity": "major", "file": "src/a.c", "line": 5, "message": "m1"},
                {"severity": "info", "file": "src/b.c", "line": 9, "message": "m2"},
            ],
        }
        raw = json.dumps(legacy, indent=2)
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert out["status"] == "failed"
        assert len(out["findings"]) == 2

    def test_legacy_markdown_fence_json(self):
        # 旧格式可能包在 ```json 里 — 走 fence 剥离路径
        legacy = {
            "status": "passed",
            "findings": [{"severity": "info", "file": "src/a.c", "message": "m"}],
        }
        raw = f"```json\n{json.dumps(legacy, indent=2)}\n```"
        from yuleosh.pipeline.stages.spec import _try_parse_hermes_json
        out = _try_parse_hermes_json(raw, "run-1")
        assert out is not None
        assert out["status"] == "passed"

    def test_garbage_returns_none(self):
        assert _parse_jsonl_review("", "run-1") is None
        assert _parse_jsonl_review("not json at all", "run-1") is None
        assert _parse_jsonl_review("```\n{broken\n```", "run-1") is None

    def test_status_recomputed_from_findings(self):
        # header 说 passed 但 findings 有 major → 强制 failed (防假绿)
        header_passed = HEADER.replace('"status": "failed"', '"status": "passed"')
        raw = f"{header_passed}\n{F1}\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert out["status"] == "failed"

    def test_all_info_recomputed_passed(self):
        header_failed = HEADER.replace('"critical": 1', '"critical": 0')
        info_f = F2.replace('"minor"', '"info"')
        raw = f"{header_failed}\n{info_f}\n"
        out = _parse_jsonl_review(raw, "run-1")
        assert out is not None
        assert out["status"] == "passed"
