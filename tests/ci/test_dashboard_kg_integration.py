#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests: Dashboard → KG integration for SWE status.

Validates that write_swe_status() correctly uses KG data
for SWE.4, SWE.5, SWE.8, SWE.10 and falls back gracefully
when KG is unavailable.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.ci.dashboard_writer import (
    write_swe_status,
    _swe_status_from_kg,
    _check_kg_available,
    SWE_PHASES,
    DASHBOARD_DB_DIR,
    SWE_STATUS_FILE,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_project():
    """Create a temp project directory with .yuleosh/reports."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tdir = Path(tmpdir)
        (tdir / ".yuleosh" / "reports").mkdir(parents=True, exist_ok=True)
        yield tdir


def _ensure_kg_db(project_dir: str | Path) -> Path:
    """Create a dummy KG DB file so the existence check passes."""
    p = Path(project_dir) / ".yuleosh" / "knowledge_graph.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("placeholder")
    return p





# ═══════════════════════════════════════════════════════════════════════
# _swe_status_from_kg — graceful fallback
# ═══════════════════════════════════════════════════════════════════════


def test_swe_status_from_kg_empty_when_no_db(temp_project):
    """Returns empty dict when KG DB file does not exist."""
    # Ensure KG module is importable but no DB file
    assert _check_kg_available(), "KG should be importable"
    result = _swe_status_from_kg(str(temp_project))
    assert result == {}, "Expected empty dict when no KG DB"


def test_swe_status_from_kg_empty_when_kg_not_importable(temp_project):
    """Returns empty dict when KG module is not available."""
    with mock.patch(
        "yuleosh.ci.dashboard_writer._check_kg_available",
        return_value=False,
    ):
        result = _swe_status_from_kg(str(temp_project))
    assert result == {}, "Expected empty dict when KG not importable"


# ═══════════════════════════════════════════════════════════════════════
# _swe_status_from_kg — KG data queries
# ═══════════════════════════════════════════════════════════════════════


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe4_from_kg(mock_check, mock_get_store, mock_get_stats,
                       mock_list_snapshots, mock_get_confirms,
                       mock_get_aspice, temp_project):
    """SWE.4 completed when unit layer covers > 0."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 10, "total_edges": 5,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"covers": 3},
    }
    mock_get_aspice.return_value = {
        "unit": {"total_covers": 4, "files": ["test_unit_a.py"]},
        "integration": {"total_covers": 0, "files": []},
    }
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert result.get("SWE.4") == "completed", (
        f"Expected SWE.4=completed, got {result}"
    )


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe5_from_kg(mock_check, mock_get_store, mock_get_stats,
                       mock_list_snapshots, mock_get_confirms,
                       mock_get_aspice, temp_project):
    """SWE.5 completed when validates edges > 0."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 10, "total_edges": 5,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"covers": 2, "validates": 3},
    }
    mock_get_aspice.return_value = {"unit": {"total_covers": 2, "files": ["test_u.py"]}}
    mock_get_confirms.return_value = [
        {"edge_type": "validates", "source": {}, "target": {}, "layer": "integration"},
    ]
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert result.get("SWE.5") == "completed", (
        f"Expected SWE.5=completed, got {result}"
    )


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe5_not_started_when_no_confirms(
    mock_check, mock_get_store, mock_get_stats,
    mock_list_snapshots, mock_get_confirms, mock_get_aspice, temp_project,
):
    """SWE.5 absent when no validates edges."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 5, "total_edges": 3,
        "nodes_by_type": {"requirement": 3, "test_file": 2},
        "edges_by_type": {"covers": 3},
    }
    mock_get_aspice.return_value = {"unit": {"total_covers": 2, "files": []}}
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert "SWE.5" not in result, (
        f"Expected no SWE.5 when no confirms, got {result}"
    )


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe8_from_kg(mock_check, mock_get_store, mock_get_stats,
                       mock_list_snapshots, mock_get_confirms,
                       mock_get_aspice, temp_project):
    """SWE.8 validated when >= 3 snapshots, completed when < 3."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 10, "total_edges": 5,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"covers": 3},
    }
    mock_get_aspice.return_value = {"unit": {"total_covers": 2, "files": []}}
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = [
        {"build_id": "b1"}, {"build_id": "b2"}, {"build_id": "b3"},
    ]

    result = _swe_status_from_kg(str(temp_project))

    assert result.get("SWE.8") == "validated"

    # Test with 1 snapshot → completed (fresh mocks)
    @mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
    @mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
    @mock.patch("yuleosh.knowledge_graph.list_snapshots")
    @mock.patch("yuleosh.knowledge_graph.get_graph_stats")
    @mock.patch("yuleosh.knowledge_graph.get_store")
    @mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
    def _run_single_snapshot(
        c2, s2, gs2, ls2, gc2, ga2,
    ):
        store2 = mock.MagicMock()
        s2.return_value = store2
        gs2.return_value = {
            "total_nodes": 10, "total_edges": 5,
            "nodes_by_type": {"requirement": 5},
            "edges_by_type": {"covers": 3},
        }
        ga2.return_value = {"unit": {"total_covers": 2, "files": []}}
        gc2.return_value = []
        ls2.return_value = [{"build_id": "b1"}]
        return _swe_status_from_kg(str(temp_project))

    result2 = _run_single_snapshot()
    assert result2.get("SWE.8") == "completed"


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe10_from_kg(mock_check, mock_get_store, mock_get_stats,
                        mock_list_snapshots, mock_get_confirms,
                        mock_get_aspice, temp_project):
    """SWE.10 validated when covers >= reqs, completed when covers < reqs but > 0."""
    _ensure_kg_db(temp_project)

    # Case: covers >= reqs → validated
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 10, "total_edges": 8,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"covers": 6},
    }
    mock_get_aspice.return_value = {"unit": {"total_covers": 0, "files": []}}
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert result.get("SWE.10") == "validated", (
        f"Expected validated when covers(6) >= reqs(5), got {result}"
    )


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe10_partial(mock_check, mock_get_store, mock_get_stats,
                        mock_list_snapshots, mock_get_confirms,
                        mock_get_aspice, temp_project):
    """SWE.10 partial: covers < reqs but > 0 → completed."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 10, "total_edges": 5,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"covers": 2},
    }
    mock_get_aspice.return_value = {"unit": {"total_covers": 0, "files": []}}
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert result.get("SWE.10") == "completed"


@mock.patch("yuleosh.knowledge_graph.queries.get_aspice_coverage")
@mock.patch("yuleosh.knowledge_graph.get_confirmation_trace")
@mock.patch("yuleosh.knowledge_graph.list_snapshots")
@mock.patch("yuleosh.knowledge_graph.get_graph_stats")
@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe10_not_started_when_no_covers(
    mock_check, mock_get_store, mock_get_stats,
    mock_list_snapshots, mock_get_confirms, mock_get_aspice, temp_project,
):
    """SWE.10 absent when no covers edges."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    mock_get_stats.return_value = {
        "total_nodes": 5, "total_edges": 2,
        "nodes_by_type": {"requirement": 5},
        "edges_by_type": {"contains": 2},
    }
    mock_get_aspice.return_value = {}
    mock_get_confirms.return_value = []
    mock_list_snapshots.return_value = []

    result = _swe_status_from_kg(str(temp_project))

    assert "SWE.10" not in result, (
        f"Expected no SWE.10 when no covers, got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════
# write_swe_status — KG data takes priority
# ═══════════════════════════════════════════════════════════════════════


def test_write_swe_status_uses_kg_data_when_available(temp_project):
    """write_swe_status prioritizes KG data over file probes."""
    proj = str(temp_project)

    # Write a fake misra report (file probe) to establish SWE.4 baseline
    misra_file = temp_project / ".yuleosh" / "reports" / "misra-report.json"
    misra_file.write_text(json.dumps({"summary": {"total_violations": 42}}))

    # Create dummy KG DB so the check passes
    _ensure_kg_db(temp_project)

    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={"SWE.4": "completed", "SWE.5": "completed"},
    ):
        result = write_swe_status(proj, force=True)

    status = result.get("status", {})

    # SWE.4 from KG should override file probe
    assert status.get("SWE.4") == "completed", (
        f"Expected SWE.4=completed from KG, got {status}"
    )
    # SWE.5 from KG
    assert status.get("SWE.5") == "completed", (
        f"Expected SWE.5=completed from KG, got {status}"
    )

    # Evidence should include KG entries
    evidence = result.get("evidence_summary", {})
    swe4_ev = evidence.get("SWE.4", [])
    assert any("kg:" in e for e in swe4_ev), (
        f"Expected KG evidence in SWE.4, got {swe4_ev}"
    )


def test_write_swe_status_falls_back_to_file_probe(temp_project):
    """write_swe_status uses file probes when KG returns empty."""
    proj = str(temp_project)

    # Create a misra report so SWE.4 gets 'completed' from file probe
    misra_file = temp_project / ".yuleosh" / "reports" / "misra-report.json"
    misra_file.write_text(json.dumps({"summary": {"total_violations": 0}}))

    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={},  # KG returns nothing
    ):
        result = write_swe_status(proj, force=True)

    status = result.get("status", {})

    # SWE.4 should still be completed from file probe
    assert status.get("SWE.4") == "completed", (
        f"Expected SWE.4 from file probe, got {status}"
    )


def test_write_swe_status_output_format(temp_project):
    """write_swe_status output has all expected phases."""
    proj = str(temp_project)

    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={},
    ):
        result = write_swe_status(proj, force=True)

    status = result.get("status", {})
    for phase in SWE_PHASES:
        assert phase in status, f"Missing phase {phase} in status"

    # Output structure
    assert "timestamp" in result
    assert "evidence_summary" in result


def test_write_swe_status_idempotent(temp_project):
    """Repeated calls with same data do not duplicate records."""
    proj = str(temp_project)
    swe_path = temp_project / DASHBOARD_DB_DIR / SWE_STATUS_FILE

    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={},
    ):
        # First call
        r1 = write_swe_status(proj)

    # Read the file — should have exactly 1 record
    lines = swe_path.read_text().strip().split("\n")
    assert len(lines) == 1, f"Expected 1 record, got {len(lines)}"

    # Second call with no changes — should NOT write
    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={},
    ):
        r2 = write_swe_status(proj)

    # Read again
    lines2 = swe_path.read_text().strip().split("\n")
    assert len(lines2) == 1, (
        f"Expected still 1 record (idempotent), got {len(lines2)}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Coverage trend — structure check
# ═══════════════════════════════════════════════════════════════════════


def test_coverage_trend_output_structure(temp_project):
    """write_coverage_trend produces dashboard-parsable output."""
    from yuleosh.ci.dashboard_writer import write_coverage_trend

    # Create a minimal coverage report so the trend dir exists
    cov_dir = temp_project / ".yuleosh" / "reports"
    cov_dir.mkdir(parents=True, exist_ok=True)

    # Mock record_coverage at source since it's a local import
    with mock.patch(
        "yuleosh.ci.coverage_trend.record_coverage",
        return_value=None,
    ):
        result = write_coverage_trend(str(temp_project))

    assert isinstance(result, dict), (
        f"Expected dict, got {type(result)}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Edge: KG store exception handling
# ═══════════════════════════════════════════════════════════════════════


@mock.patch("yuleosh.knowledge_graph.get_store")
@mock.patch("yuleosh.ci.dashboard_writer._check_kg_available", return_value=True)
def test_swe_status_graceful_on_kg_exception(mock_check, mock_get_store, temp_project):
    """Graceful fallback when KG queries raise exceptions."""
    _ensure_kg_db(temp_project)
    store = mock.MagicMock()
    mock_get_store.return_value = store
    store.get_stats.side_effect = RuntimeError("DB corrupt")

    result = _swe_status_from_kg(str(temp_project))

    assert result == {}, (
        f"Expected empty dict on exception, got {result}"
    )


def test_write_swe_status_preserves_backward_compat(temp_project):
    """Backward compat: KG changes do not affect non-KG phases."""
    proj = str(temp_project)

    with mock.patch(
        "yuleosh.ci.dashboard_writer._swe_status_from_kg",
        return_value={"SWE.4": "completed"},
    ):
        result = write_swe_status(proj, force=True)

    status = result.get("status", {})
    # Non-KG phases like SWE.1, SWE.2 should still be present
    assert "SWE.1" in status
    assert "SWE.2" in status
    assert "SWE.3" in status
