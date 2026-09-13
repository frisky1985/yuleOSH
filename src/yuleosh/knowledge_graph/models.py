#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Knowledge Graph data models — lightweight dataclasses.

These are used for return values from queries and for input to the store.
Internal storage uses dicts (sqlite3.Row-compatible).
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Entity types (node labels) ──────────────────────────────────────────

ENTITY_TYPES = frozenset({
    "requirement",
    "code_module",
    "code_file",
    "code_function",
    "test_file",
    "test_function",
    "spec_doc",
    # B1-10 C AST 专属实体
    "CFunction",
    "CGlobalVar",
    "CMacro",
    "ISR",
})

# ── Edge types ──────────────────────────────────────────────────────────

EDGE_TYPES = frozenset({
    "defines",
    "implements",
    "covers",
    "verifies",
    "validates",
    "depends_on",
    "contains",
    "affects",
    # B1-10 C 调用图边
    "calls",
    "potential_calls",
})

# ── B1-10 置信度初值（决策点 D4，S3 评审定稿）────────────────────────────
# 三级流转阈值，对齐 B3：
#   clean      = 0.9  （AST 无损解析，函数/全局/ISR）
#   error      = 0.5  （文件含语法错误节点）
#   macro_heavy= 0.35  （函数式宏 / flag 宏，真实语义需 B-M2 LLM 推断补齐）
C_CONFIDENCE_CLEAN = 0.9
C_CONFIDENCE_ERROR = 0.5
C_CONFIDENCE_MACRO_HEAVY = 0.35


def c_entity_confidence(entity_kind: str, has_error: bool = False,
                        macro_heavy: bool = False) -> float:
    """B1-10 置信度初值规则（三级流转阈值，对齐 B3）。

    - 宏重度（函数式/flag 宏）→ 0.35（无论文件是否有错，宏本身可解析）
    - 含语法错误 → 0.5
    - 干净函数/全局/ISR → 0.9

    Args:
        entity_kind: ``CFunction`` / ``CGlobalVar`` / ``CMacro`` / ``ISR``
        has_error:   该文件解析是否含 ERROR/MISSING 节点
        macro_heavy: 仅对 ``CMacro`` 有意义——函数式/flag 宏为真
    """
    if entity_kind == "CMacro":
        if macro_heavy:
            return C_CONFIDENCE_MACRO_HEAVY
        return C_CONFIDENCE_ERROR if has_error else C_CONFIDENCE_CLEAN
    if has_error:
        return C_CONFIDENCE_ERROR
    return C_CONFIDENCE_CLEAN


@dataclass
class Node:
    """A node in the knowledge graph."""
    entity_type: str
    entity_id: str
    label: str
    properties: dict = field(default_factory=dict)
    is_active: bool = True
    id: Optional[int] = None          # rowid, set by store
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    confidence: Optional[float] = None  # B1-10 置信度初值（None=未设）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "label": self.label,
            "properties": self.properties,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "confidence": self.confidence,
        }


@dataclass
class Edge:
    """An edge (relationship) in the knowledge graph.

    The ``layer`` field distinguishes test levels for ASPICE:
      - "unit"        — SWE.4 Unit Test
      - "integration" — SWE.5 Integration Test
      - "system"      — SYS.5 System Test
      - "hil"         — Hardware-in-the-Loop
      - "sil"         — Software-in-the-Loop
    """
    source_id: int
    target_id: int
    edge_type: str
    properties: dict = field(default_factory=dict)
    verified_at: Optional[str] = None
    build_id: Optional[str] = None
    layer: Optional[str] = None  # "unit" / "integration" / "system" / "hil" / "sil"
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "properties": self.properties,
            "verified_at": self.verified_at,
            "build_id": self.build_id,
            "layer": self.layer,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Snapshot:
    """A graph snapshot from a CI build."""
    build_id: str
    node_count: int
    edge_count: int
    meta: dict = field(default_factory=dict)
    id: Optional[int] = None
    built_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "build_id": self.build_id,
            "built_at": self.built_at,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "meta": self.meta,
        }


@dataclass
class TraceResult:
    """Result of a trace query, with subgraph nodes and edges."""
    source_node: Optional[Node] = None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_node": self.source_node.to_dict() if self.source_node else None,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }
