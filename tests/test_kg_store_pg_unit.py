"""Unit tests for yuleosh.knowledge_graph.store_pg (v3.4.2b Wave 2a).

All tests run OFFLINE: a fake ``psycopg2`` module is injected into
sys.modules and a fake connection/cursor replays canned rows.  No
PostgreSQL server required.

Covers:
  - singleton factory (__new__ / reset / DSN resolution errors)
  - connection lifecycle (conn property, _close_conn, close)
  - schema & migration (_ensure_schema / _migrate)
  - node CRUD (upsert/get/get_by_id/list/soft_delete)
  - edge CRUD (upsert/get/list/delete)
  - RECURSIVE CTE traversal (trace_downstream / trace_upstream)
  - snapshot CRUD (create/get/list)
  - stats / uncovered / orphan / top fan-out / top fan-in
  - snapshot_diff
  - impact_analysis
  - row helpers (_row_to_node / _row_to_edge)
"""

# @tests src/yuleosh/knowledge_graph/store.py

import sys
import os
from datetime import datetime

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.knowledge_graph.store_pg import KGStorePG
from yuleosh.knowledge_graph.models_pg import NodePG, EdgePG, SnapshotPG


# ── Fake psycopg2 layer ────────────────────────────────────────────────

class FakeCursor:
    """Replays canned result sets — one per execute() call, like psycopg2."""

    def __init__(self, result_sets=None, rowcount=0):
        self.result_sets = list(result_sets or [])
        self._rs_i = 0
        self._current = []
        self._row_i = 0
        self.rowcount = rowcount
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if self._rs_i < len(self.result_sets):
            self._current = self.result_sets[self._rs_i]
        else:
            self._current = []
        self._row_i = 0
        self._rs_i += 1

    def fetchone(self):
        if self._row_i < len(self._current):
            r = self._current[self._row_i]
            self._row_i += 1
            return r
        return None

    def fetchall(self):
        self._row_i = len(self._current)
        return self._current

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    """Connection whose cursor() returns a fresh cursor per row-group."""

    def __init__(self, row_groups=None, rowcount=0):
        # row_groups: list of per-cursor lists of per-execute result sets
        self.row_groups = list(row_groups or [])
        self._group_i = 0
        self.rowcount = rowcount
        self.autocommit = False
        self.closed = False
        self.commits = 0
        self.cursors = []

    def cursor(self):
        result_sets = []
        if self._group_i < len(self.row_groups):
            result_sets = self.row_groups[self._group_i]
            self._group_i += 1
        cur = FakeCursor(result_sets=result_sets, rowcount=self.rowcount)
        self.cursors.append(cur)
        return cur

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakePsycopg2:
    def __init__(self):
        self.connects = []  # (dsn, FakeConn)

    def connect(self, dsn):
        conn = FakeConn()
        self.connects.append((dsn, conn))
        return conn


# ── Row builders ───────────────────────────────────────────────────────

def _node_row(nid, etype, eid, label="L", props=None, active=True,
              created=None, updated=None):
    return (nid, etype, eid, label, props or {}, active, created, updated)


def _snap_row(sid, build_id, built_at=None, node_count=1, edge_count=1, meta=None):
    return (sid, build_id, built_at, node_count, edge_count, meta or {})


@pytest.fixture(autouse=True)
def _pg_env(monkeypatch):
    """Install fake psycopg2 + reset singleton state per test."""
    fake = FakePsycopg2()
    monkeypatch.setitem(sys.modules, "psycopg2", fake)
    KGStorePG.reset()
    yield fake
    KGStorePG.reset()


@pytest.fixture
def store(_pg_env):
    return KGStorePG(dsn="postgresql://u:p@localhost:5432/db")


# ── Factory / singleton ────────────────────────────────────────────────

class TestFactory:
    def test_requires_dsn(self, monkeypatch):
        """GIVEN no dsn and no env WHEN new THEN ValueError."""
        monkeypatch.delenv("YULEOSH_DB_URL", raising=False)
        with pytest.raises(ValueError, match="connection string"):
            KGStorePG()

    def test_env_dsn_used(self, monkeypatch):
        """GIVEN YULEOSH_DB_URL env WHEN new THEN env dsn resolved."""
        monkeypatch.setenv("YULEOSH_DB_URL", "postgresql://env:env@h:5432/e")
        inst = KGStorePG()
        assert inst.dsn == "postgresql://env:env@h:5432/e"

    def test_singleton_same_dsn(self, _pg_env):
        """GIVEN same dsn WHEN two instantiations THEN same object."""
        a = KGStorePG(dsn="dsn-a")
        b = KGStorePG(dsn="dsn-a")
        assert a is b

    def test_different_dsn_different_instance(self, _pg_env):
        """GIVEN different dsn WHEN instantiated THEN separate instances."""
        a = KGStorePG(dsn="dsn-a")
        b = KGStorePG(dsn="dsn-b")
        assert a is not b

    def test_reset_clears_instances(self, _pg_env):
        """GIVEN instances WHEN reset THEN new instantiation is fresh."""
        a = KGStorePG(dsn="dsn-a")
        KGStorePG.reset()
        b = KGStorePG(dsn="dsn-a")
        assert a is not b

    def test_setup(self, store):
        """GIVEN store WHEN setup THEN schema+migrate run and self returned."""
        result = store.setup()
        assert result is store
        sqls = " ".join(" ".join(c.executed) for c in store.conn.cursors)
        assert "CREATE TABLE IF NOT EXISTS kg_meta" in sqls
        assert "kg_schema_version" in sqls


# ── Connection lifecycle ───────────────────────────────────────────────

class TestConnection:
    def test_conn_creates_and_autocommit(self, store, _pg_env):
        """GIVEN store WHEN conn accessed THEN psycopg2.connect called + autocommit."""
        conn = store.conn
        assert _pg_env.connects[0][0] == "postgresql://u:p@localhost:5432/db"
        assert conn.autocommit is True
        assert store.conn is conn  # cached

    def test_conn_reopens_when_closed(self, store):
        """GIVEN closed conn WHEN accessed THEN reconnected."""
        first = store.conn
        first.closed = True
        second = store.conn
        assert second is not first

    def test_close(self, store):
        """GIVEN open conn WHEN close THEN closed."""
        conn = store.conn
        store.close()
        assert conn.closed is True

    def test_close_skips_when_none(self, store):
        """GIVEN no conn WHEN close THEN no error."""
        store.close()  # no conn yet
        assert True


# ── Node CRUD ──────────────────────────────────────────────────────────

class TestNodeCRUD:
    def test_upsert_node_returns_uuid(self, store):
        """GIVEN node WHEN upsert THEN UUID string returned."""
        store.conn.row_groups = [[[("n-uuid-1",)]]]
        node = NodePG(entity_type="requirement", entity_id="RS-1", label="Req")
        assert store.upsert_node(node) == "n-uuid-1"

    def test_get_node_found(self, store):
        """GIVEN matching row WHEN get_node THEN NodePG returned."""
        store.conn.row_groups = [[[_node_row("n1", "requirement", "RS-1", props={"a": 1})]]]
        node = store.get_node("requirement", "RS-1")
        assert isinstance(node, NodePG)
        assert node.id == "n1"
        assert node.entity_id == "RS-1"
        assert node.properties == {"a": 1}

    def test_get_node_missing(self, store):
        """GIVEN no row WHEN get_node THEN None."""
        store.conn.row_groups = [[[]]]
        assert store.get_node("requirement", "RS-X") is None

    def test_get_node_by_id(self, store):
        """GIVEN id lookup THEN NodePG returned."""
        store.conn.row_groups = [[[_node_row("n9", "code_file", "a.c")]]]
        node = store.get_node_by_id("n9")
        assert node.entity_id == "a.c"

    def test_list_nodes_filtered(self, store):
        """GIVEN entity_type WHEN list_nodes THEN WHERE clause + rows parsed."""
        store.conn.row_groups = [[[
            _node_row("n1", "test_file", "t1.py"),
            _node_row("n2", "test_file", "t2.py"),
        ]]]
        nodes = store.list_nodes("test_file")
        assert [n.entity_id for n in nodes] == ["t1.py", "t2.py"]

    def test_list_nodes_all(self, store):
        """GIVEN no filter WHEN list_nodes THEN all active nodes."""
        store.conn.row_groups = [[[_node_row("n1", "requirement", "R1")]]]
        nodes = store.list_nodes()
        assert len(nodes) == 1

    def test_soft_delete_hit(self, store):
        """GIVEN affected row WHEN soft_delete THEN True + commit."""
        store.conn.rowcount = 1
        assert store.soft_delete_node("requirement", "RS-1") is True
        assert store.conn.commits == 1

    def test_soft_delete_miss(self, store):
        """GIVEN no affected rows WHEN soft_delete THEN False."""
        store.conn.rowcount = 0
        assert store.soft_delete_node("requirement", "RS-1") is False


# ── Edge CRUD ──────────────────────────────────────────────────────────

class TestEdgeCRUD:
    def test_upsert_edge(self, store):
        """GIVEN edge WHEN upsert THEN UUID returned."""
        store.conn.row_groups = [[[("e-uuid-1",)]]]
        edge = EdgePG(source_id="s1", target_id="t1", edge_type="covers")
        assert store.upsert_edge(edge) == "e-uuid-1"

    def test_get_edge_found(self, store):
        """GIVEN matching row WHEN get_edge THEN EdgePG."""
        store.conn.row_groups = [[[(
            "e1", "s1", "t1", "covers", {"c": 1.0}, None, "b1",
            None, None,
        )]]]
        edge = store.get_edge("s1", "t1", "covers")
        assert edge.id == "e1"
        assert edge.edge_type == "covers"
        assert edge.build_id == "b1"

    def test_get_edge_missing(self, store):
        """GIVEN no row WHEN get_edge THEN None."""
        store.conn.row_groups = [[[]]]
        assert store.get_edge("s1", "t1", "covers") is None

    def test_list_edges_filtered(self, store):
        """GIVEN edge_type WHEN list_edges THEN filtered rows."""
        store.conn.row_groups = [[[(
            "e1", "s1", "t1", "covers", {}, None, None, None, None)]]]
        edges = store.list_edges("covers")
        assert len(edges) == 1 and edges[0].edge_type == "covers"

    def test_list_edges_all(self, store):
        """GIVEN no filter WHEN list_edges THEN all rows."""
        store.conn.row_groups = [[[
            ("e1", "s1", "t1", "covers", {}, None, None, None, None),
            ("e2", "s2", "t2", "defines", {}, None, None, None, None),
        ]]]
        assert len(store.list_edges()) == 2

    def test_delete_edge_hit(self, store):
        """GIVEN affected WHEN delete_edge THEN True."""
        store.conn.rowcount = 1
        assert store.delete_edge("s1", "t1", "covers") is True

    def test_delete_edge_miss(self, store):
        """GIVEN none affected WHEN delete_edge THEN False."""
        store.conn.rowcount = 0
        assert store.delete_edge("s1", "t1", "covers") is False


# ── Traversal ──────────────────────────────────────────────────────────

def _base_trace_row(nid, etype, eid, props=None):
    return (nid, etype, eid, "L", props or {}, True, None, None,
            None, None, None, None, None, None, None, 0)


def _edge_trace_row(nid, etype, eid, edge_id, src, tgt, etype_name,
                    props=None, verified=None, build=None):
    return (nid, etype, eid, "L", props or {}, True, None, None,
            edge_id, src, tgt, etype_name, props or {}, verified, build, 1)


class TestTraversal:
    def test_trace_downstream_base_and_edges(self, store):
        """GIVEN base + edge rows WHEN downstream THEN nodes+edges built."""
        store.conn.row_groups = [[[
            _base_trace_row("n1", "requirement", "RS-1"),
            _edge_trace_row("n2", "test_file", "t.py", "e1", "n1", "n2",
                            "covers", {"confidence": 0.9}),
        ]]]
        nodes, edges = store.trace_downstream("n1", max_depth=3,
                                              edge_types={"covers"})
        assert sorted(n.id for n in nodes) == ["n1", "n2"]
        assert len(edges) == 1
        assert edges[0].id == "e1"
        assert edges[0].edge_type == "covers"
        assert edges[0].source_id == "n1" and edges[0].target_id == "n2"
        sql = store.conn.cursors[0].executed[0]
        assert "WITH RECURSIVE" in sql
        assert "edge_type IN" in sql  # type filter built

    def test_trace_downstream_no_type_filter(self, store):
        """GIVEN no edge_types WHEN downstream THEN no IN clause."""
        store.conn.row_groups = [[[_base_trace_row("n1", "requirement", "RS-1")]]]
        nodes, edges = store.trace_downstream("n1")
        assert [n.id for n in nodes] == ["n1"]
        assert edges == []
        sql = store.conn.cursors[0].executed[0]
        assert "edge_type IN" not in sql

    def test_trace_upstream(self, store):
        """GIVEN base + edge rows WHEN upstream THEN nodes+edges built."""
        store.conn.row_groups = [[[
            _base_trace_row("n2", "test_file", "t.py"),
            _edge_trace_row("n1", "requirement", "RS-1", "e9", "n1", "n2",
                            "covers"),
        ]]]
        nodes, edges = store.trace_upstream("n2")
        assert sorted(n.id for n in nodes) == ["n1", "n2"]
        assert edges[0].source_id == "n1"

    def test_trace_upstream_with_filter(self, store):
        """GIVEN edge_types WHEN upstream THEN IN clause present."""
        store.conn.row_groups = [[[_base_trace_row("n1", "code_file", "a.c")]]]
        store.trace_upstream("n1", max_depth=2, edge_types={"covers", "defines"})
        sql = store.conn.cursors[0].executed[0]
        assert "edge_type IN (%s,%s)" in sql

    def test_trace_props_non_dict(self, store):
        """GIVEN JSON-string props WHEN trace THEN string preserved as-is."""
        store.conn.row_groups = [[[
            _base_trace_row("n1", "requirement", "RS-1", props='{"x":1}'),
        ]]]
        nodes, _ = store.trace_downstream("n1")
        assert nodes[0].properties == '{"x":1}'


# ── Snapshots ──────────────────────────────────────────────────────────

class TestSnapshots:
    def test_create_snapshot(self, store):
        """GIVEN counts + insert rows WHEN create_snapshot THEN SnapshotPG."""
        t = datetime(2026, 1, 1, 0, 0, 0)
        store.conn.row_groups = [
            [[(5,)], [(3,)]],                          # COUNT queries (same cursor)
            [[("snap-uuid", t)]],                      # INSERT RETURNING
        ]
        snap = store.create_snapshot("build-1", meta={"src": "ci"})
        assert snap.id == "snap-uuid"
        assert snap.build_id == "build-1"
        assert snap.node_count == 5
        assert snap.edge_count == 3
        assert snap.meta == {"src": "ci"}

    def test_get_snapshot_found(self, store):
        """GIVEN snapshot row WHEN get_snapshot THEN SnapshotPG."""
        t = datetime(2026, 1, 1, 0, 0, 0)
        store.conn.row_groups = [[[_snap_row("s1", "b1",
                                            built_at=t,
                                            node_count=4, edge_count=2)]]]
        snap = store.get_snapshot("b1")
        assert snap.build_id == "b1"
        assert snap.node_count == 4

    def test_get_snapshot_missing(self, store):
        """GIVEN no row WHEN get_snapshot THEN None."""
        store.conn.row_groups = [[[]]]
        assert store.get_snapshot("b-x") is None

    def test_list_snapshots(self, store):
        """GIVEN rows WHEN list_snapshots THEN ordered SnapshotPG list."""
        t = datetime(2026, 1, 1, 0, 0, 0)
        store.conn.row_groups = [[[
            _snap_row("s2", "b2", built_at=t, node_count=9, edge_count=8),
            _snap_row("s1", "b1", built_at=t, node_count=1, edge_count=0),
        ]]]
        snaps = store.list_snapshots(limit=10)
        assert [s.build_id for s in snaps] == ["b2", "b1"]
        assert snaps[0].edge_count == 8


# ── Stats / special queries ────────────────────────────────────────────

class TestStats:
    def test_get_stats(self, store):
        """GIVEN grouped rows WHEN get_stats THEN counts dict."""
        store.conn.row_groups = [[
            [("requirement", 3), ("test_file", 2)],
            [("covers", 5), ("defines", 1)],
        ]]
        stats = store.get_stats()
        assert stats["total_nodes"] == 5
        assert stats["total_edges"] == 6
        assert stats["nodes_by_type"] == {"requirement": 3, "test_file": 2}
        assert stats["edges_by_type"] == {"covers": 5, "defines": 1}

    def test_get_uncovered_requirements(self, store):
        """GIVEN node rows WHEN uncovered THEN NodePG list."""
        store.conn.row_groups = [[[
            _node_row("u1", "requirement", "RS-U1"),
            _node_row("u2", "requirement", "RS-U2"),
        ]]]
        reqs = store.get_uncovered_requirements()
        assert [r.entity_id for r in reqs] == ["RS-U1", "RS-U2"]

    def test_get_orphan_code_files(self, store):
        """GIVEN node rows WHEN orphans THEN NodePG list."""
        store.conn.row_groups = [[[_node_row("o1", "code_file", "orphan.c")]]]
        orphans = store.get_orphan_code_files()
        assert orphans[0].entity_id == "orphan.c"


class RealDictLike(dict):
    """Row supporting both string keys and integer indexing."""

    def __init__(self, seq, **kw):
        super().__init__(kw)
        self._seq = list(seq)
        for i, v in enumerate(seq):
            dict.__setitem__(self, i, v)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._seq[key]
        return dict.__getitem__(self, key)


class TestTopFan:
    def test_top_fan_out(self, store):
        """GIVEN rows with edge_count WHEN fan_out THEN (NodePG, count) list."""
        row = _node_row("n1", "requirement", "RS-1")
        store.conn.row_groups = [[[RealDictLike(row + (7,), edge_count=7)]]]
        results = store.get_top_fan_out(limit=5)
        assert results[0][0].entity_id == "RS-1"
        assert results[0][1] == 7

    def test_top_fan_in(self, store):
        """GIVEN rows with trailing edge_count WHEN fan_in THEN parsed."""
        row = _node_row("n1", "test_file", "t.py")
        store.conn.row_groups = [[[RealDictLike(row + (3,))]]]
        results = store.get_top_fan_in(limit=5)
        assert results[0][0].entity_id == "t.py"
        assert results[0][1] == 3


# ── snapshot_diff ──────────────────────────────────────────────────────

class TestSnapshotDiff:
    def test_diff(self, store):
        """GIVEN added/removed rows + snapshots WHEN diff THEN summary dict."""
        t = datetime(2026, 1, 1, 0, 0, 0)
        store.conn.row_groups = [
            [[("code_file", "new.c", "New")],   # added (same cursor)
             [("code_file", "old.c", "Old")]],  # removed
            [[_snap_row("sA", "A", built_at=t, node_count=10)]],
            [[_snap_row("sB", "B", built_at=t, node_count=12)]],
        ]
        diff = store.snapshot_diff("A", "B")
        assert diff["build_a"] == "A"
        assert diff["added_nodes"] == [{"entity_type": "code_file",
                                        "entity_id": "new.c", "label": "New"}]
        assert diff["removed_nodes"][0]["entity_id"] == "old.c"
        assert diff["node_count_a"] == 10
        assert diff["node_count_b"] == 12
        assert "added" in diff["summary"]

    def test_diff_missing_snapshots(self, store):
        """GIVEN no snapshot rows WHEN diff THEN counts None."""
        store.conn.row_groups = [[[], []], [[]], [[]]]
        diff = store.snapshot_diff("A", "B")
        assert diff["node_count_a"] is None
        assert diff["node_count_b"] is None


# ── impact_analysis ────────────────────────────────────────────────────

class TestImpactAnalysis:
    def test_empty_files(self, store):
        """GIVEN no files WHEN impact THEN no-files summary."""
        result = store.impact_analysis([])
        assert result["affected_reqs"] == []
        assert result["impact_summary"] == "No files changed"

    def test_full_flow(self, store):
        """GIVEN direct+indirect reqs and tests WHEN impact THEN full result."""
        store.conn.row_groups = [[
            [("RS-1", "Req One", "direct")],                 # direct (exec 1)
            [("RS-2", "Req Two", "indirect")],               # indirect (exec 2)
            [("tests/t_a.py::f1", "f1", "RS-1", "covers"),  # tests (exec 3)
             ("tests/t_a.py::f2", "f2", "RS-1", "covers")],
        ]]
        result = store.impact_analysis(["src/a.c", "tests/t_a.py"])
        req_ids = [r["req_id"] for r in result["affected_reqs"]]
        assert req_ids == ["RS-1", "RS-2"]
        assert result["affected_tests"] == [
            {"file": "tests/t_a.py::f1", "functions": ["f1"]},
            {"file": "tests/t_a.py::f2", "functions": ["f2"]},
        ]
        assert "2 requirements" in result["impact_summary"]

    def test_no_reqs_no_tests_query(self, store):
        """GIVEN no direct reqs WHEN impact THEN tests query skipped."""
        store.conn.row_groups = [[[], []]]
        result = store.impact_analysis(["src/a.c"])
        assert result["affected_reqs"] == []
        assert result["affected_tests"] == []
        assert "0 test functions" in result["impact_summary"]

    def test_indirect_dup_dropped(self, store):
        """GIVEN duplicate indirect req WHEN impact THEN deduped."""
        store.conn.row_groups = [[
            [("RS-1", "R", "direct")],
            [("RS-1", "R", "indirect")],
        ]]
        result = store.impact_analysis(["src/a.c"])
        assert len(result["affected_reqs"]) == 1


# ── Row helpers ────────────────────────────────────────────────────────

class TestRowHelpers:
    def test_row_to_node(self, store):
        """GIVEN node row WHEN _row_to_node THEN NodePG fields mapped."""
        created = datetime(2026, 1, 1, 12, 0, 0)
        node = store._row_to_node(
            _node_row("n1", "requirement", "RS-1", props={"k": "v"},
                      created=created, updated=created))
        assert node.id == "n1"
        assert node.created_at == "2026-01-01T12:00:00"
        assert node.updated_at == "2026-01-01T12:00:00"

    def test_row_to_node_none_timestamps(self, store):
        """GIVEN row with no timestamps WHEN _row_to_node THEN None kept."""
        node = store._row_to_node(_node_row("n1", "code_file", "a.c"))
        assert node.created_at is None

    def test_row_to_edge(self, store):
        """GIVEN edge row WHEN _row_to_edge THEN EdgePG fields mapped."""
        edge = store._row_to_edge((
            "e1", "s1", "t1", "covers", {"c": 0.5}, None, "b1", None, None))
        assert edge.id == "e1"
        assert edge.properties == {"c": 0.5}
        assert edge.build_id == "b1"

    def test_row_to_edge_with_timestamps(self, store):
        """GIVEN edge row with verified_at WHEN _row_to_edge THEN isoformat."""
        t = datetime(2026, 2, 2, 8, 30, 0)
        edge = store._row_to_edge(("e1", "s1", "t1", "covers", {}, t, "b1",
                                   t, t))
        assert edge.verified_at == "2026-02-02T08:30:00"
