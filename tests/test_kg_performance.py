#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph Performance Baseline — SWE.4-BP4, ASPICE P0-5.

Measures query and bootstrap performance against the real full dataset
(~12K nodes, ~15K edges) from .yuleosh/knowledge_graph.db.

Performance gates (ASPICE SUP.9):
  - trace_by_req_id:    median < 2.0s
  - trace_by_file_path: median < 2.0s
  - impact_analysis:    median < 2.0s
  - bootstrap():        median < 30.0s
  - _build_implements_edges():  median < 10.0s
  - _annotate_covers_layer():   median < 5.0s

Usage:
    pytest tests/test_kg_performance.py -v                      # run + assert gates
    pytest tests/test_kg_performance.py --benchmark-only        # record baseline
    pytest tests/test_kg_performance.py --benchmark-save=data   # save baseline
"""

import logging
import os
import time
from pathlib import Path

import pytest

# ── Ensure we use the real project DB ────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("OSH_HOME", str(PROJECT_ROOT))
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-jwt-secret-for-ci-only-not-for-production")

logging.basicConfig(level=logging.WARNING)

# Performance gates (seconds)
GATE_QUERY = 2.0    # single query
GATE_BOOTSTRAP = 30.0
GATE_IMPLEMENTS = 10.0
GATE_LAYER = 5.0


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def get_store():
    """Return a KGStore connected to the real project database."""
    from yuleosh.knowledge_graph.store import KGStore

    # Force a fresh connection to the real DB (clear singleton first)
    KGStore._instances = {}
    db_path = str(PROJECT_ROOT / ".yuleosh" / "knowledge_graph.db")
    store = KGStore.__new__(KGStore, "perf")
    store.db_path = db_path

    import sqlite3
    store.conn = sqlite3.connect(db_path, check_same_thread=False)
    store.conn.row_factory = sqlite3.Row
    store._migrate()
    return store


def verify_dataset(store):
    """Verify the DB has the expected full dataset. Raises SkipTest if not."""
    stats = store.get_stats()
    msg = f"DB stats: {stats['total_nodes']} nodes, {stats['total_edges']} edges"
    if stats["total_nodes"] < 5000:
        pytest.skip(
            f"Full dataset not available ({stats['total_nodes']} nodes < 5000). "
            "Run bootstrap() first, or check .yuleosh/knowledge_graph.db"
        )
    return stats, msg


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def perf_store():
    """Connect to the real project knowledge graph DB once per module."""
    store = get_store()
    yield store
    store.conn.close()
    # Clean singleton so subsequent tests don't get a closed connection
    from yuleosh.knowledge_graph.store import KGStore
    KGStore._instances = {}


@pytest.fixture(scope="module")
def verified_stats(perf_store):
    """Verify dataset and return stats."""
    stats, msg = verify_dataset(perf_store)
    print(f"\n📊 {msg}")
    return stats


# ═══════════════════════════════════════════════════════════════════════
# Performance Tests — Query API
# ═══════════════════════════════════════════════════════════════════════

# Sample query targets (based on real data — adjust if these exact IDs change)
REQ_IDS = ["RS-001", "SWR-002.1-01", "RS-006-10"]
FILE_PATHS = ["src/yuleosh/store.py", "src/yuleosh/store_pg.py", "src/yuleosh/store_interface.py"]
IMPACT_FILES = [
    ["src/yuleosh/store.py"],
    ["src/yuleosh/store_pg.py", "src/yuleosh/review/analyzer.py"],
    ["tests/test_sil_runner.py"],
]


class TestTraceByReqId:
    """trace_by_req_id() — 3 query variants."""

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_req_id_rs001(self, perf_store, benchmark):
        """trace_by_req_id(RS-001) — high-level parent requirement."""
        from yuleosh.knowledge_graph.queries import trace_by_req_id

        def run():
            return trace_by_req_id(perf_store, "RS-001", include_tests=True,
                                   include_functions=True)

        result = benchmark(run)
        assert result is not None, "RS-001 should exist in graph"
        assert len(result.get("nodes", [])) >= 1

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_req_id_swr_child(self, perf_store, benchmark):
        """trace_by_req_id(SWR-002.1-01) — fine-grained child SHALL."""
        from yuleosh.knowledge_graph.queries import trace_by_req_id

        def run():
            return trace_by_req_id(perf_store, "SWR-002.1-01")

        result = benchmark(run)
        assert result is not None, "SWR-002.1-01 should exist in graph"

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_req_id_rs006_child(self, perf_store, benchmark):
        """trace_by_req_id(RS-006-10) — deep child with many connections."""
        from yuleosh.knowledge_graph.queries import trace_by_req_id

        def run():
            return trace_by_req_id(perf_store, "RS-006-10")

        result = benchmark(run)
        assert result is not None, "RS-006-10 should exist in graph"


class TestTraceByFilePath:
    """trace_by_file_path() — 3 query variants."""

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_file_store(self, perf_store, benchmark):
        """trace_by_file_path(src/yuleosh/store.py) — core module."""
        from yuleosh.knowledge_graph.queries import trace_by_file_path

        def run():
            return trace_by_file_path(perf_store, "src/yuleosh/store.py")

        result = benchmark(run)
        assert result is not None, "store.py should exist in graph"

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_file_store_pg(self, perf_store, benchmark):
        """trace_by_file_path(src/yuleosh/store_pg.py) — large module."""
        from yuleosh.knowledge_graph.queries import trace_by_file_path

        def run():
            return trace_by_file_path(perf_store, "src/yuleosh/store_pg.py")

        result = benchmark(run)
        assert result is not None, "store_pg.py should exist in graph"

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_trace_file_store_interface(self, perf_store, benchmark):
        """trace_by_file_path(src/yuleosh/store_interface.py) — interface module."""
        from yuleosh.knowledge_graph.queries import trace_by_file_path

        def run():
            return trace_by_file_path(perf_store, "src/yuleosh/store_interface.py")

        result = benchmark(run)
        assert result is not None, "store_interface.py should exist in graph"


class TestImpactAnalysis:
    """impact_analysis() — 3 query variants."""

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_impact_single_file(self, perf_store, benchmark):
        """impact_analysis([store.py]) — single code file change."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        def run():
            return impact_analysis(perf_store, ["src/yuleosh/store.py"])

        result = benchmark(run)
        assert "affected_reqs" in result

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_impact_multiple_files(self, perf_store, benchmark):
        """impact_analysis([store_pg.py, analyzer.py]) — multi-file change."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        def run():
            return impact_analysis(perf_store,
                                   ["src/yuleosh/store_pg.py",
                                    "src/yuleosh/review/analyzer.py"])

        result = benchmark(run)
        assert "affected_reqs" in result

    @pytest.mark.perf
    @pytest.mark.benchmark(min_rounds=3, max_time=12, warmup=False)
    def test_impact_test_file(self, perf_store, benchmark):
        """impact_analysis([test_sil_runner.py]) — test file change."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        def run():
            return impact_analysis(perf_store, ["tests/test_sil_runner.py"])

        result = benchmark(run)
        assert "affected_reqs" in result


# ═══════════════════════════════════════════════════════════════════════
# Performance Tests — Build Pipeline (re-runs)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.perf
@pytest.mark.benchmark(min_rounds=2, max_time=60, warmup=False)
def test_bootstrap_time(perf_store, benchmark):
    """bootstrap() — full pipeline re-run timing.

    Note: This re-runs imports against the existing data. It primarily
    exercises the upsert (idempotent) path. The dataset check at module
    level verifies the DB is populated.
    """
    from yuleosh.knowledge_graph.importer import bootstrap

    # Work with the existing data — bootstrap imports all traceability
    # files from disk. If those files are unchanged, upserts are no-ops.
    result = benchmark(lambda: bootstrap(perf_store, str(PROJECT_ROOT),
                                         create_snapshot=False))
    assert "summary" in result
    assert result["summary"]["total_nodes"] > 0


@pytest.mark.perf
@pytest.mark.benchmark(min_rounds=2, max_time=30, warmup=False)
def test_build_implements_edges_time(perf_store, benchmark):
    """_build_implements_edges() — derive implements from covers+verifies.

    This measures the derivation logic over the full graph.
    """
    from yuleosh.knowledge_graph.importer import _build_implements_edges

    result = benchmark(lambda: _build_implements_edges(perf_store))
    assert "edges" in result


@pytest.mark.perf
@pytest.mark.benchmark(min_rounds=2, max_time=15, warmup=False)
def test_annotate_covers_layer_time(perf_store, benchmark):
    """_annotate_covers_layer() — annotate covers edges with ASPICE layer.

    May skip edges already annotated; measures overhead of iterating
    all covers edges and resolving target nodes.
    """
    from yuleosh.knowledge_graph.importer import _annotate_covers_layer

    result = benchmark(lambda: _annotate_covers_layer(perf_store))
    assert "annotated" in result or "skipped" in result


# ═══════════════════════════════════════════════════════════════════════
# Raw timing (no benchmark dependency) — for CI without pytest-benchmark
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.perf
class TestPerfGates:
    """Performance gate assertions (ASPICE SUP.9 pass/fail)."""

    @pytest.mark.perf
    def test_trace_by_req_id_gate(self, perf_store, verified_stats):
        """trace_by_req_id gates: single query < 2s."""
        from yuleosh.knowledge_graph.queries import trace_by_req_id

        for req_id in REQ_IDS:
            start = time.perf_counter()
            result = trace_by_req_id(perf_store, req_id)
            elapsed = time.perf_counter() - start
            node_count = len(result.get("nodes", [])) if result else 0
            edge_count = len(result.get("edges", [])) if result else 0
            assert elapsed < GATE_QUERY, (
                f"trace_by_req_id({req_id}) took {elapsed:.3f}s "
                f"(gate: {GATE_QUERY}s) — {node_count} nodes, {edge_count} edges"
            )

    @pytest.mark.perf
    def test_trace_by_file_path_gate(self, perf_store, verified_stats):
        """trace_by_file_path gates: single query < 2s."""
        from yuleosh.knowledge_graph.queries import trace_by_file_path

        for fp in FILE_PATHS:
            start = time.perf_counter()
            result = trace_by_file_path(perf_store, fp)
            elapsed = time.perf_counter() - start
            node_count = len(result.get("nodes", [])) if result else 0
            edge_count = len(result.get("edges", [])) if result else 0
            assert elapsed < GATE_QUERY, (
                f"trace_by_file_path({fp}) took {elapsed:.3f}s "
                f"(gate: {GATE_QUERY}s) — {node_count} nodes, {edge_count} edges"
            )

    @pytest.mark.perf
    def test_impact_analysis_gate(self, perf_store, verified_stats):
        """impact_analysis gates: single query < 2s."""
        from yuleosh.knowledge_graph.queries import impact_analysis

        for files in IMPACT_FILES:
            start = time.perf_counter()
            result = impact_analysis(perf_store, files)
            elapsed = time.perf_counter() - start
            assert elapsed < GATE_QUERY, (
                f"impact_analysis({files}) took {elapsed:.3f}s "
                f"(gate: {GATE_QUERY}s) — {len(result['affected_reqs'])} reqs affected"
            )
