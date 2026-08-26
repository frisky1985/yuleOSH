#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for llm/anchoring.py — KG 锚定校验 + 选择性自一致性投票。"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

from yuleosh.llm.anchoring import (
    AnchorResult,
    VoteResult,
    check_anchoring,
    consistency_vote,
    write_consensus_to_kg,
    _extract_identifiers,
    _extract_req_ids,
    _extract_file_paths,
    _jaccard,
    _compute_agreement,
    ANCHORABLE_TASKS,
)


# ═══════════════════════════════════════════════════════════════════════
# Helper: Fake KG Store
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FakeNode:
    entity_type: str
    entity_id: str
    label: str = ""
    properties: dict = None


class FakeKGStore:
    """Minimal KG store mock for testing."""

    def __init__(self, nodes=None):
        self._nodes = nodes or []

    def list_nodes(self, entity_type=None):
        if entity_type:
            return [n for n in self._nodes if n.entity_type == entity_type]
        return self._nodes

    def get_node(self, entity_type, entity_id):
        for n in self._nodes:
            if n.entity_type == entity_type and n.entity_id == entity_id:
                return n
        return None

    def add_node(self, node):
        self._nodes.append(node)


# ═══════════════════════════════════════════════════════════════════════
# Tests: Data classes
# ═══════════════════════════════════════════════════════════════════════


class TestAnchorResult:
    def test_anchor_result_fields(self):
        r = AnchorResult(anchored=True, method="kg-entity", entity_ids=["RS-001"])
        assert r.anchored is True
        assert r.method == "kg-entity"
        assert r.entity_ids == ["RS-001"]
        assert r.task_type == ""

    def test_anchor_result_defaults(self):
        r = AnchorResult(anchored=False, method="none")
        assert r.entity_ids == []
        assert r.task_type == ""


class TestVoteResult:
    def test_vote_result_fields(self):
        r = VoteResult(consensus=True, merged_output="code", agreement=0.85)
        assert r.consensus is True
        assert r.merged_output == "code"
        assert r.agreement == 0.85
        assert r.variant_outputs == []

    def test_vote_result_defaults(self):
        r = VoteResult(consensus=False)
        assert r.merged_output == ""
        assert r.agreement == 0.0


# ═══════════════════════════════════════════════════════════════════════
# Tests: Extraction helpers
# ═══════════════════════════════════════════════════════════════════════


class TestExtractionHelpers:
    def test_extract_identifiers(self):
        code = "void hw_init(void) { int counter = 0; }"
        ids = _extract_identifiers(code)
        assert "hw_init" in ids
        assert "void" in ids
        assert "counter" in ids

    def test_extract_req_ids(self):
        text = "The system SHALL comply with RS-001 and SWR-002.1 per KG-003."
        ids = _extract_req_ids(text)
        assert "RS-001" in ids
        assert "SWR-002.1" in ids
        assert "KG-003" in ids

    def test_extract_file_paths(self):
        text = "See src/main.c and lib/driver/hal.h for details."
        paths = _extract_file_paths(text)
        assert "src/main.c" in paths
        assert "lib/driver/hal.h" in paths

    def test_jaccard_identical(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_jaccard_disjoint(self):
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_partial(self):
        assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1/3)

    def test_jaccard_empty(self):
        assert _jaccard(set(), set()) == 1.0


# ═══════════════════════════════════════════════════════════════════════
# Tests: Layer 1 — KG Anchoring
# ═══════════════════════════════════════════════════════════════════════


class TestCheckAnchoring:
    def test_anchored_code_output(self):
        """输出含已知函数名 → anchored=True."""
        store = FakeKGStore([
            FakeNode("function", "hw_init"),
            FakeNode("function", "uart_send"),
        ])
        output = "void hw_init(void) { /* init hardware */ }"
        result = check_anchoring(output, "code_generation", store=store)
        assert result.anchored is True
        assert result.method == "kg-entity"
        assert "hw_init" in result.entity_ids

    def test_unanchored_code_output(self):
        """输出全为虚构 API → anchored=False."""
        store = FakeKGStore([
            FakeNode("function", "hw_init"),
        ])
        output = "void fictional_api_xyz(void) { /* unknown */ }"
        result = check_anchoring(output, "code_generation", store=store)
        assert result.anchored is False
        assert result.method == "none"

    def test_anchored_spec_ids(self):
        """输出引用 RS-001 且 KG 有该节点 → anchored."""
        store = FakeKGStore([
            FakeNode("requirement", "RS-001"),
            FakeNode("requirement", "RS-002"),
        ])
        output = "The system SHALL comply with RS-001 for safety."
        result = check_anchoring(output, "spec_review", store=store)
        assert result.anchored is True
        assert "RS-001" in result.entity_ids

    def test_unanchored_spec_ids(self):
        """输出引用 RS-999 且 KG 无该节点 → unanchored."""
        store = FakeKGStore([
            FakeNode("requirement", "RS-001"),
        ])
        output = "The system SHALL comply with RS-999 for unknown."
        result = check_anchoring(output, "spec_review", store=store)
        assert result.anchored is False

    def test_empty_output_unanchored(self):
        """空输出 → unanchored."""
        store = FakeKGStore([FakeNode("function", "hw_init")])
        result = check_anchoring("", "code_generation", store=store)
        assert result.anchored is False

    def test_non_anchorable_task(self):
        """task_type 不在 ANCHORABLE_TASKS → 跳过检查，anchored=True."""
        store = FakeKGStore([])
        result = check_anchoring("anything", "simple_summary", store=store)
        assert result.anchored is True
        assert result.method == "none"

    def test_anchoring_with_file_paths(self):
        """test_generation 用文件路径锚定."""
        store = FakeKGStore([
            FakeNode("file", "src/main.c"),
        ])
        output = "Generate tests for src/main.c"
        result = check_anchoring(output, "test_generation", store=store)
        assert result.anchored is True
        assert "src/main.c" in result.entity_ids

    def test_anchoring_store_unavailable(self):
        """KGStore 不可用时 → anchored=True (fail-open)."""
        with patch("yuleosh.knowledge_graph.store.KGStore", side_effect=ImportError):
            result = check_anchoring("some output", "code_generation", store=None)
            # Should not crash, returns anchored=True (fail-open)
            assert result.anchored is True


# ═══════════════════════════════════════════════════════════════════════
# Tests: Layer 2 — Consistency Voting
# ═══════════════════════════════════════════════════════════════════════


class TestConsistencyVoting:
    @pytest.mark.asyncio
    async def test_voting_consensus_code(self):
        """3 变体生成相似函数签名 → consensus=True."""
        mock_responses = [
            MagicMock(content="void hw_init(void) { init(); }"),
            MagicMock(content="void hw_init(void) { init(); setup(); }"),
            MagicMock(content="void hw_init(void) { init(); }"),
        ]
        with patch("yuleosh.llm.client.LLMClient") as mock_client:
            mock_client.call = AsyncMock(side_effect=mock_responses)
            result = await consistency_vote(
                "generate hw_init", "code_generation", n_variants=3
            )
            assert result.consensus is True
            assert result.agreement > 0.5
            assert len(result.variant_outputs) == 3

    @pytest.mark.asyncio
    async def test_voting_divergent_code(self):
        """3 变体生成完全不同代码 → consensus=False."""
        mock_responses = [
            MagicMock(content="void alpha(void) {}"),
            MagicMock(content="int beta(int x) { return x; }"),
            MagicMock(content="char* gamma() { return NULL; }"),
        ]
        with patch("yuleosh.llm.client.LLMClient") as mock_client:
            mock_client.call = AsyncMock(side_effect=mock_responses)
            result = await consistency_vote(
                "generate function", "code_generation", n_variants=3
            )
            assert result.consensus is False
            assert result.agreement < 0.5

    @pytest.mark.asyncio
    async def test_voting_consensus_spec(self):
        """3 变体生成相似 SHALL 语句 → consensus."""
        mock_responses = [
            MagicMock(content="The system SHALL initialize hardware. The system SHALL verify power."),
            MagicMock(content="The system SHALL initialize hardware. The system SHALL verify power."),
            MagicMock(content="The system SHALL initialize hardware. The system SHALL verify power on boot."),
        ]
        with patch("yuleosh.llm.client.LLMClient") as mock_client:
            mock_client.call = AsyncMock(side_effect=mock_responses)
            result = await consistency_vote(
                "write spec", "spec_review", n_variants=3, consensus_threshold=0.5
            )
            assert result.consensus is True

    @pytest.mark.asyncio
    async def test_voting_with_failures(self):
        """部分变体失败时仍计算共识."""
        mock_responses = [
            MagicMock(content="void hw_init(void) {}"),
            RuntimeError("timeout"),
            MagicMock(content="void hw_init(void) { init(); }"),
        ]
        with patch("yuleosh.llm.client.LLMClient") as mock_client:
            mock_client.call = AsyncMock(side_effect=mock_responses)
            result = await consistency_vote(
                "generate", "code_generation", n_variants=3
            )
            # 2 valid outputs with similar signatures
            assert len(result.variant_outputs) == 2


# ═══════════════════════════════════════════════════════════════════════
# Tests: KG Write-back
# ═══════════════════════════════════════════════════════════════════════


class TestWriteConsensus:
    def test_write_consensus_to_kg(self):
        """投票共识写入 KG 后可被查询."""
        store = FakeKGStore()
        write_consensus_to_kg("vote-test-123", "consensus output", store=store)
        node = store.get_node("consensus", "vote-test-123")
        assert node is not None
        assert node.properties["source"] == "voting-consensus"

    def test_write_consensus_idempotent(self):
        """重复写入同一 entity_id 不报错."""
        store = FakeKGStore()
        write_consensus_to_kg("vote-test-456", "output1", store=store)
        write_consensus_to_kg("vote-test-456", "output2", store=store)
        # Should still have only one node
        nodes = store.list_nodes("consensus")
        assert len(nodes) == 1


# ═══════════════════════════════════════════════════════════════════════
# Tests: Integration
# ═══════════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_anchorable_tasks_constant(self):
        """ANCHORABLE_TASKS 包含预期任务类型."""
        assert "code_generation" in ANCHORABLE_TASKS
        assert "spec_review" in ANCHORABLE_TASKS
        assert "architecture_design" in ANCHORABLE_TASKS
        assert "simple_summary" not in ANCHORABLE_TASKS

    def test_compute_agreement_identical(self):
        """相同输出 → agreement=1.0."""
        outputs = ["void hw_init(void) {}"] * 3
        score = _compute_agreement(outputs, "code_generation")
        assert score == 1.0

    def test_compute_agreement_divergent(self):
        """完全不同输出 → agreement 低."""
        outputs = [
            "void alpha(void) {}",
            "int beta(int x) { return x; }",
            "char* gamma() { return NULL; }",
        ]
        score = _compute_agreement(outputs, "code_generation")
        assert score < 0.5
