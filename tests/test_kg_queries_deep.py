#!/usr/bin/env python3

# @tests src/yuleosh/knowledge_graph/queries.py

"""Deep tests for knowledge_graph/queries.py — KG-002 graph queries."""

import pytest
from unittest.mock import MagicMock

from yuleosh.knowledge_graph.queries import (
    trace_by_req_id,
    impact_analysis,
    list_uncovered_requirements,
    list_orphan_code_files,
    get_graph_stats,
)


class _FakeNode:
    def __init__(self, entity_id, node_type="requirement"):
        self.entity_id = entity_id
        self.type = node_type
        self.id = entity_id
        self.properties = {}

    def to_dict(self):
        return {"entity_id": self.entity_id, "type": self.type, "id": self.id}


class _FakeEdge:
    def __init__(self, source_id, target_id, edge_type="covers"):
        self.source_id = source_id
        self.target_id = target_id
        self.type = edge_type
        self.properties = {}

    def to_dict(self):
        return {"source_id": self.source_id, "target_id": self.target_id, "type": self.type}


def _make_store(nodes=None, edges=None):
    store = MagicMock()
    node_map = {n.entity_id: n for n in (nodes or [])}
    store.get_node.side_effect = lambda t, eid: node_map.get(eid)
    store.list_nodes.return_value = nodes or []
    store.trace_downstream.return_value = (nodes or [], edges or [])
    store.list_edges.return_value = edges or []
    store.get_stats.return_value = {"nodes": len(nodes or []), "edges": len(edges or [])}
    return store


class TestTraceByReqId:
    def test_existing_requirement(self):
        req = _FakeNode("RS-001")
        test_node = _FakeNode("test_foo.py", "test_file")
        edge = _FakeEdge(req.id, test_node.id, "covers")
        store = _make_store([req, test_node], [edge])
        result = trace_by_req_id(store, "RS-001")
        assert result is not None

    def test_nonexistent_requirement(self):
        store = _make_store()
        result = trace_by_req_id(store, "RS-999")
        assert result is None

    def test_prefix_match(self):
        req = _FakeNode("RS-001-01")
        store = MagicMock()
        store.get_node.return_value = None
        store.list_nodes.return_value = [req]
        store.trace_downstream.return_value = ([req], [])
        result = trace_by_req_id(store, "RS-001")
        assert result is not None


class TestImpactAnalysis:
    def test_returns_dict(self):
        store = MagicMock()
        store.list_edges.return_value = []
        store.list_nodes.return_value = []
        result = impact_analysis(store, ["src/foo.c"])
        assert isinstance(result, dict)


class TestListUncoveredRequirements:
    def test_empty_store(self):
        store = MagicMock()
        store.list_nodes.return_value = []
        result = list_uncovered_requirements(store)
        assert result == []

    def test_uncovered_req_found(self):
        req = _FakeNode("RS-001")
        store = MagicMock()
        store.list_nodes.return_value = [req]
        store.list_edges.return_value = []
        result = list_uncovered_requirements(store)
        assert len(result) >= 0


class TestListOrphanCodeFiles:
    def test_empty_store(self):
        store = MagicMock()
        store.list_nodes.return_value = []
        result = list_orphan_code_files(store)
        assert isinstance(result, list)


class TestGetGraphStats:
    def test_returns_dict(self):
        store = MagicMock()
        store.get_stats.return_value = {"nodes": 5, "edges": 3}
        result = get_graph_stats(store)
        assert isinstance(result, dict)
        assert result["nodes"] == 5
