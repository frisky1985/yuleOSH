"""Unit tests for yuleosh.knowledge_graph.queries_pg (v3.4.2b Wave 2a).

Covers all P0 query functions backed by a mocked KGStorePG (no real
PostgreSQL required — offline-safe):

  - trace_by_req_id / trace_by_file_path / trace_by_test_function
  - impact_analysis (with layer filter)
  - list_uncovered_requirements / list_orphan_code_files / list_snapshots
  - get_graph_stats
  - get_aspice_coverage (dict-row and tuple-row cursors)
  - get_confirmation_trace (dict-row and tuple-row cursors)
"""

import sys
import os
from unittest.mock import MagicMock

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.knowledge_graph.queries_pg import (
    trace_by_req_id,
    trace_by_file_path,
    trace_by_test_function,
    impact_analysis,
    list_uncovered_requirements,
    list_orphan_code_files,
    list_snapshots,
    get_graph_stats,
    get_aspice_coverage,
    get_confirmation_trace,
)
from yuleosh.knowledge_graph.models_pg import NodePG, EdgePG


# ── Helpers ────────────────────────────────────────────────────────────

def _node(entity_type, entity_id, **kw):
    return NodePG(entity_type=entity_type, entity_id=entity_id,
                  label=entity_id, **kw)


def _edge(source_id, target_id, edge_type="covers", properties=None, layer=None, id=None):
    return EdgePG(source_id=source_id, target_id=target_id,
                  edge_type=edge_type,
                  properties=properties or {},
                  layer=layer, id=id)


def _mock_store():
    store = MagicMock()
    return store


class FakeCursor:
    """Minimal psycopg2-like cursor with canned rows."""

    def __init__(self, rows=None, rowcount=0):
        self.rows = rows or []
        self.rowcount = rowcount
        self.executed = []
        self._i = 0

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if self._i < len(self.rows):
            r = self.rows[self._i]
            self._i += 1
            return r
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConn:
    def __init__(self, rows=None, rowcount=0):
        self.autocommit = False
        self.closed = False
        self._rows = rows
        self._rowcount = rowcount

    def cursor(self):
        return FakeCursor(rows=self._rows, rowcount=self._rowcount)

    def commit(self):
        pass


# ── trace_by_req_id ────────────────────────────────────────────────────

class TestTraceByReqId:
    def test_exact_hit(self):
        """GIVEN exact node WHEN trace THEN downstream traced with covers+contains."""
        store = _mock_store()
        req = _node("requirement", "RS-001-01", id="n1")
        store.get_node.return_value = req
        store.trace_downstream.return_value = (
            [req, _node("test_file", "t1.py", id="n2")],
            [_edge("n1", "n2")],
        )
        result = trace_by_req_id(store, "RS-001-01")
        store.get_node.assert_called_with("requirement", "RS-001-01")
        store.trace_downstream.assert_called_with(
            "n1", max_depth=3, edge_types={"covers", "contains"})
        assert result["source_node"]["entity_id"] == "RS-001-01"
        assert result["edges"][0]["confidence"] == 1.0
        assert "low_confidence_warning" not in result

    def test_fuzzy_list_match(self):
        """GIVEN exact miss WHEN list scan matches THEN node found."""
        store = _mock_store()
        store.get_node.return_value = None
        target = _node("requirement", "RS-002", id="n9")
        store.list_nodes.return_value = [
            _node("requirement", "RS-001", id="n1"),
            target,
        ]
        store.trace_downstream.return_value = ([target], [])
        result = trace_by_req_id(store, "RS-002")
        assert result["source_node"]["id"] == "n9"

    def test_last_resort_prefix_scan(self):
        """GIVEN no exact match WHEN prefix scan THEN matched by startswith."""
        store = _mock_store()
        store.get_node.return_value = None
        target = _node("requirement", "RS-100", id="n7")
        store.list_nodes.return_value = [
            _node("requirement", "RS-001", id="n1"),
            target,
        ]
        store.trace_downstream.return_value = ([target], [])
        result = trace_by_req_id(store, "RS-1")
        assert result["source_node"]["id"] == "n7"

    def test_not_found_returns_none(self):
        """GIVEN no node anywhere WHEN trace THEN None."""
        store = _mock_store()
        store.get_node.return_value = None
        store.list_nodes.return_value = []
        assert trace_by_req_id(store, "RS-X") is None

    def test_layer_filter(self):
        """GIVEN layer WHEN trace THEN edges filtered by layer."""
        store = _mock_store()
        req = _node("requirement", "RS-1", id="n1")
        store.get_node.return_value = req
        # NOTE: the layer filter reads e.properties["layer"] (not the dataclass
        # field), so tests must put layer inside properties.
        edge_ok = _edge("n1", "n2", properties={"confidence": 0.9, "layer": "unit"}, id="e-ok")
        edge_no_layer = _edge("n1", "n3", properties={}, id="e-none")
        edge_other = _edge("n1", "n4", properties={"layer": "hil"}, id="e-hil")
        store.trace_downstream.return_value = (
            [req, _node("test_file", "a.py", id="n2"),
             _node("test_file", "b.py", id="n3"),
             _node("test_file", "c.py", id="n4")],
            [edge_ok, edge_no_layer, edge_other],
        )
        result = trace_by_req_id(store, "RS-1", layer="unit")
        # only edges with matching layer or no layer survive
        edge_ids = {e["id"] for e in result["edges"]}
        assert edge_ok.id in edge_ids and edge_no_layer.id in edge_ids
        assert edge_other.id not in edge_ids
        # nodes pruned to reachable ids
        node_ids = {n["id"] for n in result["nodes"]}
        assert "n4" not in node_ids

    def test_low_confidence_warning(self):
        """GIVEN edge with confidence<0.8 WHEN trace THEN warning flag set."""
        store = _mock_store()
        req = _node("requirement", "RS-1", id="n1")
        store.get_node.return_value = req
        store.trace_downstream.return_value = (
            [req, _node("test_file", "a.py", id="n2")],
            [_edge("n1", "n2", properties={"confidence": 0.5})],
        )
        result = trace_by_req_id(store, "RS-1")
        assert result["low_confidence_warning"] is True
        assert result["edges"][0]["confidence"] == 0.5

    def test_functions_disabled(self):
        """GIVEN include_functions=False WHEN trace THEN only covers edges."""
        store = _mock_store()
        req = _node("requirement", "RS-1", id="n1")
        store.get_node.return_value = req
        store.trace_downstream.return_value = ([req], [])
        trace_by_req_id(store, "RS-1", include_functions=False)
        store.trace_downstream.assert_called_with(
            "n1", max_depth=3, edge_types={"covers"})


# ── trace_by_file_path ─────────────────────────────────────────────────

class TestTraceByFilePath:
    def test_code_file(self):
        """GIVEN code_file node WHEN trace THEN upstream traced."""
        store = _mock_store()
        fnode = _node("code_file", "src/a.c", id="f1")
        store.get_node.side_effect = [fnode]
        store.trace_upstream.return_value = ([fnode], [])
        result = trace_by_file_path(store, "src/a.c")
        store.get_node.assert_called_with("code_file", "src/a.c")
        assert result["source_node"]["entity_id"] == "src/a.c"

    def test_test_file_fallback(self):
        """GIVEN code_file miss THEN test_file fallback used."""
        store = _mock_store()
        fnode = _node("test_file", "tests/t_a.py", id="f2")
        store.get_node.side_effect = [None, fnode]
        store.trace_upstream.return_value = ([fnode], [])
        result = trace_by_file_path(store, "tests/t_a.py")
        assert result["source_node"]["id"] == "f2"

    def test_not_found(self):
        """GIVEN no file node THEN None."""
        store = _mock_store()
        store.get_node.return_value = None
        assert trace_by_file_path(store, "nope.c") is None

    def test_low_confidence(self):
        """GIVEN low-confidence edge THEN warning present."""
        store = _mock_store()
        fnode = _node("code_file", "src/a.c", id="f1")
        store.get_node.return_value = fnode
        store.trace_upstream.return_value = (
            [fnode, _node("requirement", "RS-1", id="n1")],
            [_edge("n1", "f1", properties={"confidence": 0.3})],
        )
        result = trace_by_file_path(store, "src/a.c")
        assert result["low_confidence_warning"] is True


# ── trace_by_test_function ─────────────────────────────────────────────

class TestTraceByTestFunction:
    def test_exact(self):
        """GIVEN exact test_function node WHEN trace THEN both directions."""
        store = _mock_store()
        func = _node("test_function", "tests/t_a.py::test_x", id="fn1")
        store.get_node.return_value = func
        store.trace_downstream.return_value = ([func], [])
        store.trace_upstream.return_value = ([func], [])
        result = trace_by_test_function(store, "tests/t_a.py::test_x")
        store.trace_downstream.assert_called_with("fn1", max_depth=2)
        store.trace_upstream.assert_called_with("fn1", max_depth=2)
        assert result["source_node"]["id"] == "fn1"

    def test_fuzzy_endswith(self):
        """GIVEN exact miss WHEN endswith match THEN node found."""
        store = _mock_store()
        func = _node("test_function", "tests/t_a.py::test_x", id="fn1")
        store.get_node.return_value = None
        store.list_nodes.return_value = [func]
        store.trace_downstream.return_value = ([func], [])
        store.trace_upstream.return_value = ([func], [])
        result = trace_by_test_function(store, "test_x")
        assert result["source_node"]["id"] == "fn1"

    def test_not_found(self):
        """GIVEN no test function THEN None."""
        store = _mock_store()
        store.get_node.return_value = None
        store.list_nodes.return_value = []
        assert trace_by_test_function(store, "missing") is None

    def test_combined_trace_and_warning(self):
        """GIVEN both directions WHEN trace THEN merged nodes/edges + warning."""
        store = _mock_store()
        func = _node("test_function", "t::f", id="fn1")
        req = _node("requirement", "RS-9", id="n1")
        store.get_node.return_value = func
        store.trace_downstream.return_value = (
            [func, _node("code_file", "a.c", id="c1")],
            [_edge("fn1", "c1", properties={"confidence": 0.7})],
        )
        store.trace_upstream.return_value = (
            [func, req],
            [_edge("n1", "fn1", properties={"confidence": 1.0})],
        )
        result = trace_by_test_function(store, "t::f")
        assert len(result["nodes"]) == 3
        assert result["low_confidence_warning"] is True


# ── impact_analysis ────────────────────────────────────────────────────

class TestImpactAnalysis:
    def test_no_layer(self):
        """GIVEN changed files WHEN impact THEN delegate to store."""
        store = _mock_store()
        store.impact_analysis.return_value = {
            "affected_reqs": [{"req_id": "RS-1"}],
            "affected_tests": [],
        }
        result = impact_analysis(store, ["src/a.c"])
        store.impact_analysis.assert_called_with(["src/a.c"])
        assert result["affected_reqs"][0]["req_id"] == "RS-1"

    def test_layer_filter_keeps_matching(self):
        """GIVEN layer WHEN impact THEN reqs without matching layer dropped."""
        store = _mock_store()
        store.impact_analysis.return_value = {
            "affected_reqs": [
                {"req_id": "RS-1"},
                {"req_id": "RS-2"},
            ],
            "affected_tests": [],
        }
        req1 = _node("requirement", "RS-1", id="n1")
        req2 = _node("requirement", "RS-2", id="n2")
        store.get_node.side_effect = [req1, req2]
        store.trace_downstream.side_effect = [
            ([], [_edge("n1", "t1", properties={"layer": "unit"})]),  # RS-1 unit
            ([], [_edge("n2", "t2", properties={"layer": "hil"})]),   # RS-2 hil
        ]
        result = impact_analysis(store, ["src/a.c"], layer="unit")
        req_ids = [r["req_id"] for r in result["affected_reqs"]]
        assert req_ids == ["RS-1"]

    def test_layer_filter_missing_node_skipped(self):
        """GIVEN layer WHEN req node missing THEN req skipped."""
        store = _mock_store()
        store.impact_analysis.return_value = {
            "affected_reqs": [{"req_id": "RS-X"}],
            "affected_tests": [],
        }
        store.get_node.return_value = None
        result = impact_analysis(store, ["f.c"], layer="unit")
        assert result["affected_reqs"] == []


# ── List / stats queries ───────────────────────────────────────────────

class TestListQueries:
    def test_uncovered_requirements(self):
        """GIVEN store uncovered reqs WHEN list THEN dicts returned."""
        store = _mock_store()
        store.get_uncovered_requirements.return_value = [
            _node("requirement", "RS-U1", id="u1")]
        result = list_uncovered_requirements(store)
        assert result[0]["entity_id"] == "RS-U1"

    def test_orphan_code_files(self):
        """GIVEN orphan files WHEN list THEN dicts returned."""
        store = _mock_store()
        store.get_orphan_code_files.return_value = [
            _node("code_file", "orphan.c", id="o1")]
        result = list_orphan_code_files(store)
        assert result[0]["id"] == "o1"

    def test_list_snapshots(self):
        """GIVEN snapshots WHEN list THEN dicts with limit passed."""
        store = _mock_store()
        from yuleosh.knowledge_graph.models_pg import SnapshotPG
        snap = SnapshotPG(build_id="b1", node_count=3, edge_count=2, id="s1")
        store.list_snapshots.return_value = [snap]
        result = list_snapshots(store, limit=5)
        store.list_snapshots.assert_called_with(limit=5)
        assert result[0]["build_id"] == "b1"

    def test_get_graph_stats(self):
        """GIVEN stats WHEN get_graph_stats THEN passthrough."""
        store = _mock_store()
        store.get_stats.return_value = {"total_nodes": 10}
        assert get_graph_stats(store)["total_nodes"] == 10


# ── get_aspice_coverage ────────────────────────────────────────────────

class TestAspiceCoverage:
    def test_dict_rows(self):
        """GIVEN dict-style cursor rows WHEN coverage THEN per-layer report."""
        store = _mock_store()
        store.conn = FakeConn(rows=[
            {"layer": "unit", "target_type": "test_file",
             "target_eid": "tests/t_u.py", "target_props": {}, "cnt": 3},
            {"layer": "unit", "target_type": "test_function",
             "target_eid": "t::f", "target_props": {"file_path": "tests/t_u.py"},
             "cnt": 1},
            {"layer": "hil", "target_type": "test_file",
             "target_eid": "hil/h1.py", "target_props": {}, "cnt": 2},
        ])
        report = get_aspice_coverage(store)
        assert report["unit"]["total_covers"] == 4
        assert report["unit"]["files"] == ["tests/t_u.py"]
        assert report["hil"]["total_covers"] == 2
        assert report["hil"]["files"] == ["hil/h1.py"]
        for ln in ("integration", "sil", "system"):
            assert report[ln]["total_covers"] == 0
            assert report[ln]["files"] == []

    def test_tuple_rows(self):
        """GIVEN tuple-style cursor rows WHEN coverage THEN parsed by index."""
        store = _mock_store()
        store.conn = FakeConn(rows=[
            ("unit", "test_function", "t::f", None, 5),
            ("unknown_layer_here", "test_file", "tf.py", {}, 1),
        ])
        report = get_aspice_coverage(store)
        assert report["unit"]["total_covers"] == 5
        # fpath derived from entity_id split
        assert report["unit"]["files"] == ["t"]
        # unknown layer key kept (has count > 0)
        assert "unknown_layer_here" in report

    def test_unknown_layer_zero_removed(self):
        """GIVEN _unknown layer with zero count THEN removed from report."""
        store = _mock_store()
        store.conn = FakeConn(rows=[
            {"layer": "_unknown", "target_type": "code_file",
             "target_eid": "x.c", "target_props": {}, "cnt": 0},
        ])
        report = get_aspice_coverage(store)
        assert "_unknown" not in report

    def test_empty(self):
        """GIVEN no rows THEN all layers zero."""
        store = _mock_store()
        store.conn = FakeConn(rows=[])
        report = get_aspice_coverage(store)
        assert report["unit"]["total_covers"] == 0
        assert report["hil"]["files"] == []


# ── get_confirmation_trace ─────────────────────────────────────────────

def _confirm_row_dict():
    return {
        "source_id": "s1", "target_id": "t1", "edge_type": "validates",
        "properties": {"k": "v"}, "build_id": "b1", "layer": "unit",
        "e_created": None, "e_updated": None,
        "s_type": "test_file", "s_eid": "tf.py", "s_label": "TF",
        "s_props": {}, "s_active": True, "s_created": None, "s_updated": None,
        "t_type": "requirement", "t_eid": "RS-1", "t_label": "Req",
        "t_props": {"testable": "true"}, "t_active": True,
        "t_created": None, "t_updated": None,
    }


class TestConfirmationTrace:
    def test_dict_rows(self):
        """GIVEN dict rows WHEN confirmation trace THEN full chain."""
        store = _mock_store()
        store.conn = FakeConn(rows=[_confirm_row_dict()])
        result = get_confirmation_trace(store)
        assert len(result) == 1
        assert result[0]["edge_type"] == "validates"
        assert result[0]["source"]["entity_id"] == "tf.py"
        assert result[0]["target"]["entity_id"] == "RS-1"
        assert result[0]["layer"] == "unit"
        assert result[0]["properties"] == {"k": "v"}

    def test_tuple_rows(self):
        """GIVEN tuple rows WHEN confirmation trace THEN parsed by index."""
        store = _mock_store()
        row = (
            "s1", "t1", "validates", {"k": "v"}, "b1", "hil",
            None, None,                    # e_created, e_updated
            "test_file", "tf.py", "TF", {}, True, None, None,  # source (8..14)
            "requirement", "RS-9", "Req", {}, True, None, None,  # target (15..21)
        )
        assert len(row) == 22
        store.conn = FakeConn(rows=[row])
        result = get_confirmation_trace(store)
        assert result[0]["layer"] == "hil"
        assert result[0]["source"]["entity_type"] == "test_file"
        assert result[0]["target"]["is_active"] is True

    def test_empty(self):
        """GIVEN no validates edges THEN empty list."""
        store = _mock_store()
        store.conn = FakeConn(rows=[])
        assert get_confirmation_trace(store) == []
