#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for KPI KG integration (Phase 2.5 — KG 度量接入 KPI 管线)."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.ci.kpi.kg_source import (
    get_kg_coverage_metrics,
    get_kg_health_metrics,
    get_kg_confidence_metrics,
    get_kg_metrics_summary,
)


@pytest.fixture
def temp_project():
    """Create a temporary project directory with an empty .yuleosh dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / ".yuleosh").mkdir(parents=True, exist_ok=True)
        yield tmpdir


@pytest.fixture
def kg_store(tmp_path):
    """Create a KGStore instance with sample data."""
    from yuleosh.knowledge_graph.store import KGStore
    from yuleosh.knowledge_graph.models import Node, Edge

    db_path = str(tmp_path / ".yuleosh" / "knowledge_graph.db")
    store = KGStore(db_path=db_path)

    reqs = [
        Node("requirement", "REQ-001", label="System shall boot", properties={"testable": True}),
        Node("requirement", "REQ-002", label="System shall blink LED", properties={"testable": True}),
        Node("requirement", "REQ-003", label="System shall log", properties={"testable": True}),
        Node("requirement", "REQ-004", label="Management req", properties={"testable": False}),
    ]
    for r in reqs:
        store.upsert_node(r)

    tests = [
        Node("test_file", "tests/test_boot.py", label="Boot test"),
        Node("test_file", "tests/test_led.py", label="LED test"),
    ]
    for t in tests:
        store.upsert_node(t)

    store.upsert_node(Node("code_file", "src/extra.c", label="Extra file"))

    edges = [
        Edge(store.get_node("requirement", "REQ-001").id,
             store.get_node("test_file", "tests/test_boot.py").id,
             "covers", properties={"confidence": 0.98, "layer": "unit"}),
        Edge(store.get_node("requirement", "REQ-002").id,
             store.get_node("test_file", "tests/test_led.py").id,
             "covers", properties={"confidence": 0.85, "layer": "unit"}),
    ]
    for e in edges:
        store.upsert_edge(e)

    store.create_snapshot("build-001", meta={"node_count": 7, "edge_count": 2})
    return store


@pytest.fixture
def project_with_kg(kg_store, tmp_path):
    """Project directory with seeded KG data."""
    _ = kg_store
    yield str(tmp_path)


# ══════════════════════════════════════════════════════════════════════
# get_kg_coverage_metrics
# ══════════════════════════════════════════════════════════════════════

def test_kg_coverage_no_kg_empty_db(temp_project):
    """Should return zero-values when no KG data (empty KGStore)."""
    result = get_kg_coverage_metrics(temp_project)
    assert result.get("coverage_pct") == 0.0
    assert result.get("covered") == 0
    assert result.get("uncovered") == 0


def test_kg_coverage_with_data(project_with_kg):
    """Should return coverage metrics from seeded KG."""
    result = get_kg_coverage_metrics(project_with_kg)
    assert result["coverage_pct"] == pytest.approx(66.67, rel=0.1)
    assert result["covered"] == 2
    assert result["uncovered"] == 1
    assert result["total_requirements"] == 4
    assert result["non_testable"] == 1


def test_kg_coverage_all_covered(kg_store, tmp_path):
    """Should return 100% when all requirements are covered."""
    from yuleosh.knowledge_graph.models import Edge
    node_c = kg_store.get_node("requirement", "REQ-003")
    test_c = kg_store.get_node("test_file", "tests/test_boot.py")
    kg_store.upsert_edge(Edge(node_c.id, test_c.id, "covers", properties={"confidence": 0.9}))
    result = get_kg_coverage_metrics(str(tmp_path))
    assert result["coverage_pct"] == pytest.approx(100.0, rel=0.1)
    assert result["covered"] == 3
    assert result["uncovered"] == 0


# ══════════════════════════════════════════════════════════════════════
# get_kg_health_metrics
# ══════════════════════════════════════════════════════════════════════

def test_kg_health_no_kg(temp_project):
    """Should return zero-value health metrics."""
    result = get_kg_health_metrics(temp_project)
    assert result.get("total_nodes") == 0
    assert result.get("total_edges") == 0


def test_kg_health_with_data(project_with_kg):
    """Should return health metrics from seeded KG."""
    result = get_kg_health_metrics(project_with_kg)
    assert result["total_nodes"] == 7
    assert result["total_edges"] == 2
    assert result["orphan_code_files"] == 1
    assert result["low_confidence_edges"] == 0


def test_kg_health_low_confidence(kg_store, tmp_path):
    """Should detect low-confidence edges."""
    from yuleosh.knowledge_graph.models import Edge
    node_a = kg_store.get_node("requirement", "REQ-003")
    node_b = kg_store.get_node("test_file", "tests/test_boot.py")
    kg_store.upsert_edge(Edge(node_a.id, node_b.id, "covers",
                              properties={"confidence": 0.5}))
    result = get_kg_health_metrics(str(tmp_path))
    assert result["low_confidence_edges"] >= 1


# ══════════════════════════════════════════════════════════════════════
# get_kg_confidence_metrics
# ══════════════════════════════════════════════════════════════════════

def test_kg_confidence_no_kg(temp_project):
    """Should return zero-value confidence metrics."""
    result = get_kg_confidence_metrics(temp_project)
    assert result.get("edge_count") == 0
    assert result.get("avg_confidence") == 0.0


def test_kg_confidence_with_data(project_with_kg):
    """Should return confidence metrics from seeded KG."""
    result = get_kg_confidence_metrics(project_with_kg)
    assert result["edge_count"] == 2
    assert result["avg_confidence"] == pytest.approx(0.915, rel=0.1)
    assert result["explicit_pct"] == pytest.approx(50.0, rel=0.1)
    assert result["derived_pct"] == pytest.approx(50.0, rel=0.1)
    assert result["heuristic_pct"] == pytest.approx(0.0, rel=0.1)


# ══════════════════════════════════════════════════════════════════════
# get_kg_metrics_summary
# ══════════════════════════════════════════════════════════════════════

def test_kg_summary_json(project_with_kg):
    """Should return JSON when as_json=True."""
    result = get_kg_metrics_summary(project_with_kg, as_json=True)
    parsed = json.loads(result)
    assert "kg_coverage" in parsed
    assert "kg_health" in parsed
    assert "kg_confidence" in parsed
    assert parsed["project_dir"] == project_with_kg


def test_kg_summary_text(project_with_kg):
    """Should return formatted text when as_json=False."""
    result = get_kg_metrics_summary(project_with_kg, as_json=False)
    assert "KG 度量摘要" in result
    assert "覆盖率" in result


# ══════════════════════════════════════════════════════════════════════
# kpi_status integration
# ══════════════════════════════════════════════════════════════════════

def test_kpi_status_includes_kg(mocker, project_with_kg):
    """kpi_status() should include KG entries in output."""
    mocker.patch("yuleosh.ci.kpi.report._load_latest_misra_entry", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._load_latest_coverage_entry", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._get_misra_trend_avg", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._get_coverage_trend_avg", return_value={})
    mocker.patch("yuleosh.ci.kpi.report.get_process_stability_summary", return_value="{}")
    mocker.patch("yuleosh.ci.kpi.report.get_defect_escape_summary",
                 return_value=json.dumps({}))

    from yuleosh.ci.kpi.report import kpi_status
    result = kpi_status(project_with_kg, as_json=True)
    parsed = json.loads(result)
    entry_metrics = [e["metric"] for e in parsed.get("entries", [])]
    assert "kg_coverage_pct" in entry_metrics


def test_kpi_status_text_renders_kg(mocker, project_with_kg):
    """Dashboard text output should render KG entries."""
    mocker.patch("yuleosh.ci.kpi.report._load_latest_misra_entry", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._load_latest_coverage_entry", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._get_misra_trend_avg", return_value={})
    mocker.patch("yuleosh.ci.kpi.report._get_coverage_trend_avg", return_value={})
    mocker.patch("yuleosh.ci.kpi.report.get_process_stability_summary", return_value="{}")
    mocker.patch("yuleosh.ci.kpi.report.get_defect_escape_summary",
                 return_value=json.dumps({}))
    from yuleosh.ci.kpi.report import kpi_status
    result = kpi_status(project_with_kg, as_json=False)
    assert "KG 需求覆盖率" in result
    assert "KG 边密度" in result
