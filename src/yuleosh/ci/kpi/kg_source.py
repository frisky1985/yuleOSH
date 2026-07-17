#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI KPI — KG (Knowledge Graph) data source.

Provides functions to extract KG metrics and normalize them into KPI
dimensions: kg_coverage, kg_health, kg_confidence.

Integrated into the KPI pipeline via:
    from yuleosh.ci.kpi.kg_source import get_kg_metrics_summary
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.kpi.kg_source")


def _get_kg_store(project_dir: str):
    """Lazy-initialize a KGStore instance for the given project."""
    try:
        from yuleosh.knowledge_graph.store import KGStore
        db_path = Path(project_dir) / ".yuleosh" / "knowledge_graph.db"
        return KGStore(db_path=str(db_path))
    except ImportError:
        log.warning("knowledge_graph.store not available — KG KPI skipped")
        return None
    except Exception as e:
        log.warning("KGStore init failed: %s", e)
        return None


def get_kg_coverage_metrics(project_dir: str) -> dict[str, Any]:
    """Extract KG coverage metrics.

    Returns
    -------
    dict with keys:
        - coverage_pct: float — requirement coverage % (0-100)
        - covered: int — number of covered requirements
        - uncovered: int — number of uncovered requirements
        - total_requirements: int
        - non_testable: int
    """
    store = _get_kg_store(project_dir)
    if store is None:
        return {}

    try:
        from yuleosh.knowledge_graph.reporter import generate_metrics
        metrics = generate_metrics(store)
        cov = metrics.get("coverage", {})
        coverage_pct = cov.get("coverage_percentage", 0.0)
        return {
            "coverage_pct": float(coverage_pct),
            "covered": cov.get("covered_requirements", 0),
            "uncovered": cov.get("uncovered_requirements", 0),
            "total_requirements": cov.get("total_requirements", 0),
            "non_testable": cov.get("non_testable_requirements", 0),
        }
    except Exception as e:
        log.warning("Failed to generate KG coverage metrics: %s", e)
        return {}


def get_kg_health_metrics(project_dir: str) -> dict[str, Any]:
    """Extract KG graph health metrics.

    Returns
    -------
    dict with keys:
        - total_nodes: int
        - total_edges: int
        - orphan_code_files: int
        - orphan_test_files: int
        - low_confidence_edges: int
        - edge_density: float — edges / nodes ratio
    """
    store = _get_kg_store(project_dir)
    if store is None:
        return {}

    try:
        stats = store.get_stats()
        total_nodes = stats.get("total_nodes", 0)
        total_edges = stats.get("total_edges", 0)
        orphan_code = len(store.get_orphan_code_files())

        # Count orphan test files (test_file nodes with no edges)
        orphan_test = 0
        for tn in store.list_nodes("test_file", active_only=True):
            outgoing = store.get_outgoing_edges(tn.id)
            incoming = store.get_incoming_edges(tn.id)
            if not outgoing and not incoming:
                orphan_test += 1

        # Count low-confidence edges
        low_conf = 0
        for e in store.list_edges():
            conf = e.properties.get("confidence", 1.0)
            if isinstance(conf, (int, float)) and conf < 0.8:
                low_conf += 1

        density = round(total_edges / max(total_nodes, 1), 2)

        return {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "orphan_code_files": orphan_code,
            "orphan_test_files": orphan_test,
            "low_confidence_edges": low_conf,
            "edge_density": density,
        }
    except Exception as e:
        log.warning("Failed to generate KG health metrics: %s", e)
        return {}


def get_kg_confidence_metrics(project_dir: str) -> dict[str, Any]:
    """Extract KG confidence metrics.

    Returns
    -------
    dict with keys:
        - avg_confidence: float — average confidence across all edges (0-1)
        - explicit_pct: float — % edges with confidence >= 0.95
        - derived_pct: float — % edges with confidence 0.8-0.95
        - heuristic_pct: float — % edges with confidence < 0.8
        - confidences: list[float] — all confidence values
    """
    store = _get_kg_store(project_dir)
    if store is None:
        return {}

    try:
        confidences = []
        for e in store.list_edges():
            conf = e.properties.get("confidence", 1.0)
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))

        if not confidences:
            return {
                "avg_confidence": 0.0,
                "explicit_pct": 0.0,
                "derived_pct": 0.0,
                "heuristic_pct": 0.0,
                "edge_count": 0,
            }

        avg_conf = sum(confidences) / len(confidences)
        total = len(confidences)
        explicit = sum(1 for c in confidences if c >= 0.95)
        derived = sum(1 for c in confidences if 0.8 <= c < 0.95)
        heuristic = sum(1 for c in confidences if c < 0.8)

        return {
            "avg_confidence": round(avg_conf, 4),
            "explicit_pct": round(explicit / total * 100, 1) if total > 0 else 0.0,
            "derived_pct": round(derived / total * 100, 1) if total > 0 else 0.0,
            "heuristic_pct": round(heuristic / total * 100, 1) if total > 0 else 0.0,
            "edge_count": total,
        }
    except Exception as e:
        log.warning("Failed to generate KG confidence metrics: %s", e)
        return {}


def get_kg_metrics_summary(project_dir: str, as_json: bool = False) -> str:
    """Get merged KG KPI metrics summary.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    as_json : bool
        Return JSON string instead of formatted text.

    Returns
    -------
    str
        Formatted summary or JSON.
    """
    coverage = get_kg_coverage_metrics(project_dir)
    health = get_kg_health_metrics(project_dir)
    confidence = get_kg_confidence_metrics(project_dir)

    result = {
        "timestamp": datetime.now().isoformat(),
        "project_dir": project_dir,
        "kg_coverage": coverage,
        "kg_health": health,
        "kg_confidence": confidence,
    }

    if as_json:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    cov_pct = coverage.get("coverage_pct", "N/A")
    total_nodes = health.get("total_nodes", "N/A")
    total_edges = health.get("total_edges", "N/A")
    avg_conf = confidence.get("avg_confidence", "N/A")

    lines = [
        "## KG 度量摘要",
        "",
        f"| 维度 | 指标 | 数值 |",
        f"|------|------|-----:|",
        f"| 覆盖 | 覆盖率 | {cov_pct}% |",
        f"| 覆盖 | 已覆盖/未覆盖 | {coverage.get('covered', '?')}/{coverage.get('uncovered', '?')} |",
        f"| 健康 | 节点/边 | {total_nodes}/{total_edges} |",
        f"| 健康 | 边密度 | {health.get('edge_density', 'N/A')} |",
        f"| 健康 | 孤立代码文件 | {health.get('orphan_code_files', 'N/A')} |",
        f"| 健康 | 低置信度边 | {health.get('low_confidence_edges', 'N/A')} |",
        f"| 置信 | 平均置信度 | {avg_conf} |",
        f"| 置信 | 显式/推导/启发式 | {confidence.get('explicit_pct', '?')}%/{confidence.get('derived_pct', '?')}%/{confidence.get('heuristic_pct', '?')}% |",
    ]
    return "\n".join(lines)
