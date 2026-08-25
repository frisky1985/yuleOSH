
# @tests src/yuleosh/pipeline/context_guard.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Context Guard 单测（第九轮决策 9.3, 2026-08-19）— pipeline/context_guard.py。

覆盖:
  - estimate_context_level 三档水位（≤50 normal / 50-80 reference / >80 over_limit）
  - reference_inject 引用式注入（大段落替换 + 摘要 + 小段落不动）
  - truncate_with_reference_marker 显式省略标记（替代静默截断, 头尾保留）
"""

from pathlib import Path

import pytest

from yuleosh.pipeline.context_guard import (
    CONTEXT_NORMAL,
    CONTEXT_OVER_LIMIT,
    CONTEXT_REFERENCE,
    REFERENCE_MIN_BLOCK,
    REFERENCE_SUMMARY_LIMIT,
    estimate_context_level,
    reference_inject,
    truncate_with_reference_marker,
)


class TestEstimateContextLevel:
    """三档水位判定。"""

    def test_normal_within_50_percent(self):
        # EN 3.5 chars/token → 1000 chars ≈ 286 tokens; window 128_000 → 0.2%
        result = estimate_context_level("system", "user", context_window=128_000)
        assert result["mode"] == CONTEXT_NORMAL
        assert result["ratio"] <= 0.5

    def test_normal_boundary_50(self):
        # 构造恰好 ~50% 的输入: 50% * 128_000 tokens * 3.5 chars ≈ 224_000 chars
        big = "a" * 223_000
        result = estimate_context_level("", big, context_window=128_000)
        assert result["mode"] == CONTEXT_NORMAL
        assert result["ratio"] <= 0.5

    def test_reference_between_50_and_80(self):
        big = "a" * 300_000  # ≈ 85.7K tokens / 128K ≈ 67%
        result = estimate_context_level("", big, context_window=128_000)
        assert result["mode"] == CONTEXT_REFERENCE
        assert 0.5 < result["ratio"] <= 0.8
        assert "reference injection" in result["reason"]

    def test_over_limit_above_80(self):
        big = "a" * 400_000  # ≈ 114K tokens / 128K ≈ 89%
        result = estimate_context_level("", big, context_window=128_000)
        assert result["mode"] == CONTEXT_OVER_LIMIT
        assert result["ratio"] > 0.8
        assert "over_limit" in result["reason"]

    def test_env_window_override(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_CONTEXT_WINDOW", "1000")
        # 600 chars ≈ 171 tokens / 1000 = 17% → normal
        result = estimate_context_level("", "b" * 600)
        assert result["mode"] == CONTEXT_NORMAL
        assert result["context_window"] == 1000

    def test_small_window_triggers_reference(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_CONTEXT_WINDOW", "2000")
        # 6000 chars ≈ 1714 tokens / 2000 = 86% → over_limit
        result = estimate_context_level("", "c" * 6000)
        assert result["mode"] == CONTEXT_OVER_LIMIT


class TestReferenceInject:
    """引用式注入: 大段落替换为指针 + 摘要。"""

    def _prompt_with_artifact(self, key: str, body: str) -> str:
        return f"### {key}\n```\n{body}\n```"

    def test_small_block_untouched(self):
        text = self._prompt_with_artifact("prd", "x" * 100)
        new_text, changes = reference_inject(text, "/tmp/sess")
        assert new_text == text
        assert changes == []

    def test_large_block_replaced_with_pointer(self, tmp_path):
        body = "y" * (REFERENCE_MIN_BLOCK + 100)
        text = self._prompt_with_artifact("architecture", body)
        new_text, changes = reference_inject(text, tmp_path)
        assert len(changes) == 1
        assert changes[0]["key"] == "architecture"
        assert changes[0]["original_len"] >= len(body)  # 正则捕获含结尾换行
        assert "完整内容见" in new_text
        assert str(tmp_path) in new_text
        assert "结论字段摘要如下" in new_text
        # 摘要长度受 REFERENCE_SUMMARY_LIMIT 约束
        assert changes[0]["summary_len"] == REFERENCE_SUMMARY_LIMIT

    def test_multiple_blocks_only_large_replaced(self, tmp_path):
        small = self._prompt_with_artifact("prd", "s" * 100)
        large = self._prompt_with_artifact("development", "d" * (REFERENCE_MIN_BLOCK + 50))
        text = small + "\n" + large
        new_text, changes = reference_inject(text, tmp_path)
        assert len(changes) == 1
        assert changes[0]["key"] == "development"
        assert "### prd" in new_text  # 小段落保留原样


class TestTruncateWithReferenceMarker:
    """显式省略标记（替代静默截断）。"""

    def test_short_text_untouched(self):
        assert truncate_with_reference_marker("hello", 100, "/tmp/x") == "hello"

    def test_long_text_keeps_head_tail_with_marker(self):
        text = "A" * 1000
        result = truncate_with_reference_marker(text, 400, "/tmp/report.json")
        assert "omitted" in result
        assert "全文见 /tmp/report.json" in result
        # 头尾保留
        assert result.startswith("A" * 240)  # 0.6 * 400
        assert result.endswith("A" * 160)    # 0.4 * 400
        assert len(result) < 1000

    def test_marker_is_explicit_not_silent(self):
        text = "B" * 5000
        result = truncate_with_reference_marker(text, 1000, "/tmp/c.json")
        assert "…[omitted" in result
        assert "B" * 600 in result  # head 保留
        assert "B" * 400 in result  # tail 保留

    def test_boundary_no_marker_when_fits(self):
        text = "C" * 100
        assert truncate_with_reference_marker(text, 100, "/tmp/c.json") == text
