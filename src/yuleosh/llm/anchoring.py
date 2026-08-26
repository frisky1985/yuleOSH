#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
llm/anchoring.py — KG 锚定校验 + 选择性自一致性投票（双层幻觉防护）。

Layer 1: 检查 LLM 输出是否引用了 KG 中已知实体（快路径，零 LLM 调用）。
Layer 2: 仅对无锚点输出触发 3 变体投票（慢路径，~0.6-0.9x 额外调用）。

Usage::

    from yuleosh.llm.anchoring import check_anchoring, consistency_vote

    result = check_anchoring(llm_output, task_type="code_generation")
    if not result.anchored:
        vote = await consistency_vote(prompt, task_type)
        if vote.consensus:
            llm_output = vote.merged_output
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("llm.anchoring")


# ═══════════════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class AnchorResult:
    """Layer 1 锚定校验结果。"""

    anchored: bool
    method: str  # "kg-entity" | "none"
    entity_ids: list[str] = field(default_factory=list)
    task_type: str = ""


@dataclass
class VoteResult:
    """Layer 2 投票共识结果。"""

    consensus: bool
    merged_output: str = ""
    agreement: float = 0.0  # Jaccard or ROUGE-L score
    variant_outputs: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# Layer 1: KG Anchoring Check
# ═══════════════════════════════════════════════════════════════════════

# 可锚定的 task_type 集合
ANCHORABLE_TASKS = frozenset({
    "code_generation",
    "safety_code_generation",
    "spec_review",
    "architecture_design",
    "test_generation",
    "misra_review",
    "review_blocking",
    "review_selfcheck",
})

# 需求 ID 正则
_REQ_ID_RE = re.compile(
    r"\b(RS-\d+|SWR-\d+(?:\.\d+)?|KG-\d+|NFR-\d+|FSR-\d+|CR-\d+)\b"
)

# 函数/类型/模块标识符正则（C/Python 风格）
_IDENTIFIER_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]{2,})\b"
)

# 文件路径正则
_FILE_PATH_RE = re.compile(
    r"(?:src|lib|include)/[a-zA-Z0-9_/\.\-]+\.(?:py|c|h|cpp|hpp)"
)


def _extract_identifiers(text: str) -> set[str]:
    """从文本中提取标识符（函数名、类型名等）。"""
    return set(_IDENTIFIER_RE.findall(text))


def _extract_req_ids(text: str) -> set[str]:
    """从文本中提取需求 ID。"""
    return set(_REQ_ID_RE.findall(text))


def _extract_file_paths(text: str) -> set[str]:
    """从文本中提取文件路径。"""
    return set(_FILE_PATH_RE.findall(text))


def check_anchoring(
    output: str,
    task_type: str,
    store: Any | None = None,
) -> AnchorResult:
    """Layer 1: 检查 LLM 输出是否引用了 KG 中已知实体。

    策略（按 task_type 分）：
    - code_generation / safety_code_generation: 扫描标识符，与 KG 中
      node_type="function"|"type"|"module" 的 entity_id 做交集
    - spec_review / architecture_design: 扫描需求 ID，与 KG 中
      node_type="requirement" 的 entity_id 做交集
    - test_generation: 扫描文件路径，与 KG 中 node_type="file" 做交集

    Args:
        output: LLM 生成的文本。
        task_type: 任务类型。
        store: KGStore 实例（默认从环境变量解析）。

    Returns:
        AnchorResult 包含 anchored 状态和匹配到的 entity_ids。
    """
    if not output or not output.strip():
        return AnchorResult(anchored=False, method="none", task_type=task_type)

    if task_type not in ANCHORABLE_TASKS:
        return AnchorResult(anchored=True, method="none", task_type=task_type)

    # Lazy import to avoid circular dependency
    if store is None:
        try:
            from yuleosh.knowledge_graph.store import KGStore
            store = KGStore()
        except Exception:
            log.debug("KGStore unavailable, skipping anchoring")
            return AnchorResult(anchored=True, method="none", task_type=task_type)

    matched_ids: list[str] = []

    if task_type in ("code_generation", "safety_code_generation"):
        # 提取标识符，与 KG 中的 function/type/module 节点做交集
        identifiers = _extract_identifiers(output)
        for entity_type in ("function", "type", "module", "file"):
            try:
                kg_nodes = store.list_nodes(entity_type)
                kg_ids = {n.entity_id for n in kg_nodes}
                matched = identifiers & kg_ids
                matched_ids.extend(matched)
            except Exception:
                pass

    elif task_type in ("spec_review", "architecture_design", "misra_review",
                       "review_blocking", "review_selfcheck"):
        # 提取需求 ID，与 KG 中的 requirement 节点做交集
        req_ids = _extract_req_ids(output)
        try:
            kg_nodes = store.list_nodes("requirement")
            kg_ids = {n.entity_id for n in kg_nodes}
            matched = req_ids & kg_ids
            matched_ids.extend(matched)
        except Exception:
            pass

    elif task_type == "test_generation":
        # 提取文件路径，与 KG 中的 file 节点做交集
        file_paths = _extract_file_paths(output)
        try:
            kg_nodes = store.list_nodes("file")
            kg_ids = {n.entity_id for n in kg_nodes}
            matched = file_paths & kg_ids
            matched_ids.extend(matched)
        except Exception:
            pass

    # 去重
    matched_ids = list(dict.fromkeys(matched_ids))

    if matched_ids:
        return AnchorResult(
            anchored=True,
            method="kg-entity",
            entity_ids=matched_ids,
            task_type=task_type,
        )
    else:
        return AnchorResult(
            anchored=False,
            method="none",
            entity_ids=[],
            task_type=task_type,
        )


# ═══════════════════════════════════════════════════════════════════════
# Layer 2: Self-Consistency Voting
# ═══════════════════════════════════════════════════════════════════════


def _jaccard(set_a: set, set_b: set) -> float:
    """计算两个集合的 Jaccard 相似度。"""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def _extract_signatures(code: str) -> set[str]:
    """从代码中提取函数签名。"""
    # C/Python 风格函数定义
    patterns = [
        r"(?:void|int|float|double|char|bool|static|inline|async|def)\s+(\w+\s*\([^)]*\))",
        r"def\s+(\w+\s*\([^)]*\))",
        r"(\w+\s*\([^)]*\))\s*(?:->|:)\s*",
    ]
    sigs = set()
    for pat in patterns:
        for m in re.finditer(pat, code):
            sigs.add(m.group(1).strip())
    return sigs


def _extract_shall_statements(text: str) -> set[str]:
    """从文本中提取 SHALL 语句。"""
    statements = set()
    pattern = r"\bSHALL\b\s+\w[^.!?\n]*"
    for m in re.finditer(pattern, text, re.IGNORECASE):
        stmt = m.group().strip()
        if stmt:
            statements.add(stmt.lower())
    return statements


def _compute_agreement(
    outputs: list[str],
    task_type: str,
) -> float:
    """计算多个输出的平均一致性分数。"""
    if len(outputs) < 2:
        return 1.0

    if task_type in ("code_generation", "safety_code_generation"):
        # 提取函数签名集合，计算两两 Jaccard
        sig_sets = [_extract_signatures(o) for o in outputs]
    elif task_type in ("spec_review", "architecture_design"):
        # 提取 SHALL 语句集合
        sig_sets = [_extract_shall_statements(o) for o in outputs]
    else:
        # 其他：用词集合的 Jaccard
        sig_sets = [set(o.lower().split()) for o in outputs]

    # 计算所有两两配对的平均 Jaccard
    total = 0.0
    count = 0
    for i in range(len(sig_sets)):
        for j in range(i + 1, len(sig_sets)):
            total += _jaccard(sig_sets[i], sig_sets[j])
            count += 1

    return total / count if count > 0 else 0.0


async def consistency_vote(
    prompt: str,
    task_type: str,
    config: Any | None = None,
    n_variants: int = 3,
    consensus_threshold: float = 0.7,
) -> VoteResult:
    """Layer 2: 对同一 prompt 用 n 组变体参数调用 LLM，检查输出一致性。

    变体策略：
    - variant 1: temperature=0.0, seed=42 (确定性)
    - variant 2: temperature=0.3, seed=123 (微扰)
    - variant 3: temperature=0.0, seed=456 (不同 seed)

    Args:
        prompt: 原始 prompt。
        task_type: 任务类型。
        config: LLMConfig 实例。
        n_variants: 变体数量（默认 3）。
        consensus_threshold: 一致性阈值（默认 0.7）。

    Returns:
        VoteResult 包含共识状态、合并输出和一致性分数。
    """
    from yuleosh.llm.client import LLMClient
    from yuleosh.llm.providers.base import LLMConfig

    if config is None:
        config = LLMConfig()

    # 构建变体配置
    variants = []
    variant_configs = [
        {"temperature": 0.0, "seed": 42},
        {"temperature": 0.3, "seed": 123},
        {"temperature": 0.0, "seed": 456},
    ]

    for i, vc in enumerate(variant_configs[:n_variants]):
        vconfig = LLMConfig(
            model=config.model,
            provider=config.provider,
            max_tokens=config.max_tokens,
            temperature=vc["temperature"],
            seed=vc["seed"],
            rag_enabled=False,  # 投票时关闭 RAG 避免干扰
            memory_enabled=False,
            anchoring_enabled=False,  # 投票内部调用不再触发锚定
            task_type=task_type,
        )
        variants.append((i, vconfig))

    # 并行调用所有变体
    tasks = []
    for i, vconfig in variants:
        task = LLMClient.call(
            prompt=prompt,
            task_type=task_type,
            config=vconfig,
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 收集有效输出
    outputs = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("Voting variant failed: %s", r)
            continue
        if hasattr(r, "content") and r.content:
            outputs.append(r.content)

    if not outputs:
        return VoteResult(consensus=False, agreement=0.0)

    # 计算一致性
    agreement = _compute_agreement(outputs, task_type)
    consensus = agreement >= consensus_threshold

    # 合并输出：选最长的（通常最完整）
    merged = max(outputs, key=len) if outputs else ""

    return VoteResult(
        consensus=consensus,
        merged_output=merged,
        agreement=agreement,
        variant_outputs=outputs,
    )


# ═══════════════════════════════════════════════════════════════════════
# KG Write-back
# ═══════════════════════════════════════════════════════════════════════


def write_consensus_to_kg(
    entity_id: str,
    output: str,
    source: str = "voting-consensus",
    store: Any | None = None,
) -> None:
    """将投票共识结果写入 KG，下次同类查询可直接命中 Layer 1。

    Args:
        entity_id: 实体 ID（如 "RS-001" 或函数名）。
        output: 共识输出文本。
        source: 来源标记（默认 "voting-consensus"）。
        store: KGStore 实例。
    """
    if store is None:
        try:
            from yuleosh.knowledge_graph.store import KGStore
            store = KGStore()
        except Exception:
            log.debug("KGStore unavailable, skipping write-back")
            return

    try:
        # 检查是否已存在
        existing = store.get_node("consensus", entity_id)
        if existing:
            log.debug("Consensus already exists for %s", entity_id)
            return

        # 创建共识节点
        from yuleosh.knowledge_graph.models import Node
        node = Node(
            entity_type="consensus",
            entity_id=entity_id,
            label=f"Voting consensus: {entity_id}",
            properties={
                "source": source,
                "output_hash": hash(output),
                "output_preview": output[:200],
            },
        )
        store.add_node(node)
        log.info("Wrote voting consensus to KG: %s", entity_id)
    except Exception as e:
        log.warning("Failed to write consensus to KG: %s", e)
