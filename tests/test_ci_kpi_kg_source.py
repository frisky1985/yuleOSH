"""Tests for ci/kpi/kg_source.py — KG KPI data source."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from yuleosh.ci.kpi.kg_source import (
    _get_kg_store,
    get_kg_coverage_metrics,
    get_kg_health_metrics,
    get_kg_confidence_metrics,
    get_kg_metrics_summary,
)

# NOTE: KGStore is imported lazily inside _get_kg_store() via:
#   from yuleosh.knowledge_graph.store import KGStore
# generate_metrics is imported lazily inside get_kg_coverage_metrics() via:
#   from yuleosh.knowledge_graph.reporter import generate_metrics
# So patches must target the actual import sources, not the local module names.


# ------------------------------------------------------------------
# _get_kg_store
# ------------------------------------------------------------------

@patch("yuleosh.knowledge_graph.store.KGStore")
def test_get_kg_store_success(mock_kg_store_cls, tmp_path):
    """GIVEN a project dir WHEN KGStore is available THEN returns store."""
    mock_store = MagicMock()
    mock_kg_store_cls.return_value = mock_store
    store = _get_kg_store(str(tmp_path))
    assert store is mock_store
    expected_db = str(tmp_path / ".yuleosh" / "knowledge_graph.db")
    mock_kg_store_cls.assert_called_once_with(db_path=expected_db)


@patch("yuleosh.knowledge_graph.store.KGStore", side_effect=ImportError("no kg"))
def test_get_kg_store_import_error(mock_kg_store_cls, tmp_path):
    """GIVEN import failing WHEN getting store THEN returns None."""
    store = _get_kg_store(str(tmp_path))
    assert store is None


@patch("yuleosh.knowledge_graph.store.KGStore")
def test_get_kg_store_init_exception(mock_kg_store_cls, tmp_path):
    """GIVEN KGStore init raises WHEN getting store THEN returns None."""
    mock_kg_store_cls.side_effect = Exception("bad init")
    store = _get_kg_store(str(tmp_path))
    assert store is None


# ------------------------------------------------------------------
# get_kg_coverage_metrics
# ------------------------------------------------------------------

@patch("yuleosh.ci.kpi.kg_source._get_kg_store", return_value=None)
def test_kg_coverage_metrics_store_none(mock_get_store, tmp_path):
    """GIVEN KGStore unavailable WHEN getting coverage THEN returns empty dict."""
    result = get_kg_coverage_metrics(str(tmp_path))
    assert result == {}


@patch("yuleosh.knowledge_graph.reporter.generate_metrics")
@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_coverage_metrics_success(mock_get_store, mock_gen_metrics, tmp_path):
    """GIVEN KG metrics available WHEN getting coverage THEN returns parsed dict."""
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_gen_metrics.return_value = {
        "coverage": {
            "coverage_percentage": 72.5,
            "covered_requirements": 29,
            "uncovered_requirements": 11,
            "total_requirements": 40,
            "non_testable_requirements": 3,
        }
    }
    result = get_kg_coverage_metrics(str(tmp_path))
    assert result["coverage_pct"] == 72.5
    assert result["covered"] == 29
    assert result["uncovered"] == 11
    assert result["total_requirements"] == 40
    assert result["non_testable"] == 3


@patch("yuleosh.knowledge_graph.reporter.generate_metrics")
@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_coverage_metrics_exception(mock_get_store, mock_gen_metrics, tmp_path):
    """GIVEN generate_metrics fails WHEN getting coverage THEN returns empty dict."""
    mock_store = MagicMock()
    mock_get_store.return_value = mock_store
    mock_gen_metrics.side_effect = Exception("metric failure")
    result = get_kg_coverage_metrics(str(tmp_path))
    assert result == {}


# ------------------------------------------------------------------
# get_kg_health_metrics
# ------------------------------------------------------------------

@patch("yuleosh.ci.kpi.kg_source._get_kg_store", return_value=None)
def test_kg_health_metrics_store_none(mock_get_store, tmp_path):
    """GIVEN KGStore unavailable WHEN getting health THEN returns empty dict."""
    result = get_kg_health_metrics(str(tmp_path))
    assert result == {}


def _make_mock_store(total_nodes=100, total_edges=250, orphan_code=5,
                     orphan_test=3, low_conf=8):
    """Build a MagicMock KGStore with canned data."""
    store = MagicMock()
    store.get_stats.return_value = {
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }

    # Mock get_orphan_code_files
    store.get_orphan_code_files.return_value = [f"file{i}.c" for i in range(orphan_code)]

    # Mock list_nodes for test_file
    test_nodes = []
    for i in range(orphan_test):
        tn = MagicMock()
        tn.id = f"test_{i}"
        test_nodes.append(tn)
    # Add one non-orphan test node
    non_orphan = MagicMock()
    non_orphan.id = "test_ok"
    test_nodes.append(non_orphan)
    store.list_nodes.return_value = test_nodes

    # Mock get_outgoing_edges / get_incoming_edges
    def get_outgoing(node_id):
        if node_id == "test_ok":
            return [MagicMock()]
        return []
    def get_incoming(node_id):
        if node_id == "test_ok":
            return [MagicMock()]
        return []
    store.get_outgoing_edges = MagicMock(side_effect=get_outgoing)
    store.get_incoming_edges = MagicMock(side_effect=get_incoming)

    # Mock list_edges
    edges = []
    for i in range(low_conf):
        e = MagicMock()
        e.properties = {"confidence": 0.3 + (i * 0.05)}
        edges.append(e)
    for i in range(total_edges - low_conf):
        e = MagicMock()
        e.properties = {"confidence": 0.9}
        edges.append(e)
    store.list_edges.return_value = edges

    return store


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_health_metrics_success(mock_get_store, tmp_path):
    """GIVEN health metrics available WHEN getting health THEN returns parsed dict."""
    store = _make_mock_store(total_nodes=100, total_edges=250, orphan_code=3,
                             orphan_test=5, low_conf=8)
    mock_get_store.return_value = store
    result = get_kg_health_metrics(str(tmp_path))
    assert result["total_nodes"] == 100
    assert result["total_edges"] == 250
    assert result["orphan_code_files"] == 3
    assert result["orphan_test_files"] == 5
    assert result["low_confidence_edges"] == 8
    assert result["edge_density"] == 2.5  # 250/100


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_health_metrics_exception(mock_get_store, tmp_path):
    """GIVEN health metrics fail WHEN getting health THEN returns empty dict."""
    mock_store = MagicMock()
    mock_store.get_stats.side_effect = Exception("stats failed")
    mock_get_store.return_value = mock_store
    result = get_kg_health_metrics(str(tmp_path))
    assert result == {}


# ------------------------------------------------------------------
# get_kg_confidence_metrics
# ------------------------------------------------------------------

@patch("yuleosh.ci.kpi.kg_source._get_kg_store", return_value=None)
def test_kg_confidence_metrics_store_none(mock_get_store, tmp_path):
    """GIVEN KGStore unavailable WHEN getting confidence THEN returns empty dict."""
    result = get_kg_confidence_metrics(str(tmp_path))
    assert result == {}


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_confidence_metrics_success(mock_get_store, tmp_path):
    """GIVEN confidence metrics available WHEN getting confidence THEN returns parsed dict."""
    store = _make_mock_store(total_nodes=10, total_edges=20, low_conf=5)
    mock_get_store.return_value = store
    result = get_kg_confidence_metrics(str(tmp_path))
    assert "avg_confidence" in result
    assert "explicit_pct" in result
    assert "derived_pct" in result
    assert "heuristic_pct" in result
    assert result["edge_count"] == 20


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_confidence_metrics_no_edges(mock_get_store, tmp_path):
    """GIVEN no edges WHEN getting confidence THEN returns zero metrics."""
    store = MagicMock()
    store.list_edges.return_value = []
    mock_get_store.return_value = store
    result = get_kg_confidence_metrics(str(tmp_path))
    assert result["avg_confidence"] == 0.0
    assert result["edge_count"] == 0


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_confidence_metrics_conf_not_numeric(mock_get_store, tmp_path):
    """GIVEN edges with non-numeric confidence WHEN getting confidence THEN skips them."""
    store = MagicMock()
    e1 = MagicMock()
    e1.properties = {"confidence": 0.95}
    e2 = MagicMock()
    e2.properties = {"confidence": "high"}  # string, not numeric
    e3 = MagicMock()
    e3.properties = {"confidence": None}  # None
    store.list_edges.return_value = [e1, e2, e3]
    mock_get_store.return_value = store
    result = get_kg_confidence_metrics(str(tmp_path))
    assert result["edge_count"] == 1
    assert result["avg_confidence"] == 0.95


@patch("yuleosh.ci.kpi.kg_source._get_kg_store")
def test_kg_confidence_metrics_exception(mock_get_store, tmp_path):
    """GIVEN confidence metrics fail WHEN getting confidence THEN returns empty dict."""
    mock_store = MagicMock()
    mock_store.list_edges.side_effect = Exception("edge failure")
    mock_get_store.return_value = mock_store
    result = get_kg_confidence_metrics(str(tmp_path))
    assert result == {}


# ------------------------------------------------------------------
# get_kg_metrics_summary
# ------------------------------------------------------------------

@patch("yuleosh.ci.kpi.kg_source.get_kg_confidence_metrics")
@patch("yuleosh.ci.kpi.kg_source.get_kg_health_metrics")
@patch("yuleosh.ci.kpi.kg_source.get_kg_coverage_metrics")
def test_metrics_summary_as_json(mock_cov, mock_health, mock_conf, tmp_path):
    """GIVEN metrics available WHEN summary as_json THEN returns JSON string."""
    mock_cov.return_value = {"coverage_pct": 80.0, "covered": 20, "uncovered": 5,
                             "total_requirements": 25, "non_testable": 1}
    mock_health.return_value = {"total_nodes": 100, "total_edges": 200,
                                "orphan_code_files": 3, "orphan_test_files": 2,
                                "low_confidence_edges": 5, "edge_density": 2.0}
    mock_conf.return_value = {"avg_confidence": 0.85, "explicit_pct": 60.0,
                              "derived_pct": 30.0, "heuristic_pct": 10.0,
                              "edge_count": 200}
    result = get_kg_metrics_summary(str(tmp_path), as_json=True)
    parsed = json.loads(result)
    assert "kg_coverage" in parsed
    assert "kg_health" in parsed
    assert "kg_confidence" in parsed
    assert parsed["kg_coverage"]["coverage_pct"] == 80.0


@patch("yuleosh.ci.kpi.kg_source.get_kg_confidence_metrics")
@patch("yuleosh.ci.kpi.kg_source.get_kg_health_metrics")
@patch("yuleosh.ci.kpi.kg_source.get_kg_coverage_metrics")
def test_metrics_summary_text(mock_cov, mock_health, mock_conf, tmp_path):
    """GIVEN metrics available WHEN summary as text THEN returns formatted Markdown."""
    mock_cov.return_value = {"coverage_pct": 80.0, "covered": 20, "uncovered": 5,
                             "total_requirements": 25, "non_testable": 1}
    mock_health.return_value = {"total_nodes": 100, "total_edges": 200,
                                "orphan_code_files": 3, "orphan_test_files": 2,
                                "low_confidence_edges": 5, "edge_density": 2.0}
    mock_conf.return_value = {"avg_confidence": 0.85, "explicit_pct": 60.0,
                              "derived_pct": 30.0, "heuristic_pct": 10.0,
                              "edge_count": 200}
    result = get_kg_metrics_summary(str(tmp_path), as_json=False)
    assert "KG 度量摘要" in result
    assert "覆盖" in result
    assert "健康" in result
    assert "置信" in result
