#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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
})


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
