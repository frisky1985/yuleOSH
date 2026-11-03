"""Tests for shared recursive-CTE traversal (P2-6)."""

import sqlite3

import pytest

from yuleosh.knowledge_graph._graph_traversal import build_trace_sql
from yuleosh.knowledge_graph.models import Edge, Node
from yuleosh.knowledge_graph.store import KGStore


@pytest.fixture
def store():
    s = KGStore.__new__(KGStore, "test")
    s.db_path = ":memory:"
    s.conn = sqlite3.connect(":memory:")
    s.conn.row_factory = sqlite3.Row
    s._migrate()
    yield s
    s.conn.close()
    KGStore._instances = {}


def _chain(store, n_nodes=4, edge_type="covers"):
    ids = []
    for i in range(n_nodes):
        ids.append(store.upsert_node(
            Node(entity_type="code_file", entity_id=f"f{i}", label=f"f{i}")))
    for a, b in zip(ids, ids[1:]):
        store.upsert_edge(Edge(source_id=a, target_id=b, edge_type=edge_type))
    return ids


class TestSqlBuilder:
    def test_sqlite_template(self):
        sql, params = build_trace_sql("sqlite", "downstream")
        assert "WITH RECURSIVE" in sql
        assert "GROUP BY node_id, edge_id" in sql
        assert "?" in sql
        assert params == []

    def test_pg_template_unchanged(self):
        sql, params = build_trace_sql("pg", "upstream")
        assert "NULL::uuid" in sql
        assert "%s" in sql
        assert "ORDER BY depth, entity_type" in sql
        assert params == []

    def test_edge_type_filter_sorted(self):
        sql, params = build_trace_sql(
            "sqlite", "upstream", {"verifies", "covers"})
        assert "IN (?,?)" in sql
        assert params == ["covers", "verifies"]

    def test_unknown_dialect(self):
        with pytest.raises(ValueError):
            build_trace_sql("mysql", "downstream")


class TestSQLiteTraversal:
    def test_downstream_depth_limit(self, store):
        ids = _chain(store)
        nodes, edges = store.trace_downstream(ids[0], max_depth=2)
        assert {n.entity_id for n in nodes} == {"f0", "f1", "f2"}
        assert len(edges) == 2

    def test_downstream_one_hop(self, store):
        ids = _chain(store)
        nodes, edges = store.trace_downstream(ids[0], max_depth=1)
        assert {n.entity_id for n in nodes} == {"f0", "f1"}
        assert len(edges) == 1

    def test_edge_type_filter(self, store):
        ids = _chain(store, n_nodes=2, edge_type="covers")
        store.upsert_edge(Edge(
            source_id=ids[0], target_id=ids[1], edge_type="depends_on"))
        nodes, edges = store.trace_downstream(
            ids[0], max_depth=5, edge_types={"covers"})
        assert {n.entity_id for n in nodes} == {"f0", "f1"}
        assert {e.edge_type for e in edges} == {"covers"}

    def test_cycle_terminates(self, store):
        a = store.upsert_node(Node(entity_type="code_file", entity_id="a", label="a"))
        b = store.upsert_node(Node(entity_type="code_file", entity_id="b", label="b"))
        store.upsert_edge(Edge(source_id=a, target_id=b, edge_type="calls"))
        store.upsert_edge(Edge(source_id=b, target_id=a, edge_type="calls"))
        nodes, edges = store.trace_downstream(a, max_depth=5)
        assert {n.entity_id for n in nodes} == {"a", "b"}
        assert len(edges) == 2  # 每条边只返回一次（按 edge_id 去重）

    def test_upstream_mirror(self, store):
        ids = _chain(store)
        nodes, edges = store.trace_upstream(ids[-1], max_depth=2)
        assert {n.entity_id for n in nodes} == {"f3", "f2", "f1"}
        assert len(edges) == 2

    def test_unknown_start_returns_empty(self, store):
        nodes, edges = store.trace_downstream(99999, max_depth=3)
        assert nodes == []
        assert edges == []
