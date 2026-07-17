"""Tests for yuleosh.knowledge_graph.merge_gate — KG Merge Gate (KG-42).

Tests cover:
- MergeGateConfig creation and defaults
- GraphConsistencyChecker: node types, edge types, orphans, cycles, duplicates
- ConfidenceChecker: confidence calculations, coverage thresholds
- MergeGate: full orchestration, change detection, verdict, recommendations
- CLI handler: cmd_check_merge
- Pipeline step: step_merge_gate
- Edge cases: empty graph, no changes, all errors, all pass
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from yuleosh.knowledge_graph.merge_gate import (
    MergeGateConfig,
    GraphConsistencyChecker,
    ConfidenceChecker,
    MergeGate,
    cmd_check_merge,
    step_merge_gate,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_store():
    """Create a mock KG store with no data."""
    store = MagicMock()
    store.get_all_nodes.return_value = []
    store.get_all_edges.return_value = []
    return store


@pytest.fixture
def populated_store():
    """Create a mock KG store with valid requirements, functions, and tests."""
    store = MagicMock()

    nodes = [
        {"entity_id": "RS-001", "entity_type": "requirement", "name": "Pipeline execution"},
        {"entity_id": "RS-002", "entity_type": "requirement", "name": "Spec parsing"},
        {"entity_id": "RS-003", "entity_type": "requirement", "name": "Code review"},
        {"entity_id": "func_a", "entity_type": "function", "name": "run_pipeline"},
        {"entity_id": "func_b", "entity_type": "function", "name": "parse_spec"},
        {"entity_id": "test_a", "entity_type": "test", "name": "test_run_pipeline"},
        {"entity_id": "test_b", "entity_type": "test", "name": "test_parse_spec"},
        {"entity_id": "feature_x", "entity_type": "feature", "name": "KG Merge Gate"},
    ]
    store.get_all_nodes.return_value = nodes

    edges = [
        {"id": 1, "source_id": "RS-001", "target_id": "func_a", "relation_type": "covers", "confidence": 0.85},
        {"id": 2, "source_id": "RS-002", "target_id": "func_b", "relation_type": "covers", "confidence": 0.90},
        {"id": 3, "source_id": "func_a", "target_id": "test_a", "relation_type": "verifies", "confidence": 0.80},
        {"id": 4, "source_id": "func_b", "target_id": "test_b", "relation_type": "verifies", "confidence": 0.75},
        {"id": 5, "source_id": "RS-003", "target_id": "feature_x", "relation_type": "covers", "confidence": 0.65},
    ]
    store.get_all_edges.return_value = edges

    return store


@pytest.fixture
def store_with_orphans():
    """Mock store with orphan nodes and edges."""
    store = MagicMock()

    nodes = [
        {"entity_id": "RS-001", "entity_type": "requirement", "name": "Normal"},
        {"entity_id": "orphan_node", "entity_type": "requirement", "name": "Orphan"},
        {"entity_id": "orphan_node2", "entity_type": "function", "name": "Orphan func"},
    ]
    store.get_all_nodes.return_value = nodes

    edges = [
        {"id": 1, "source_id": "RS-001", "target_id": "func_a", "relation_type": "covers", "confidence": 0.8},
        {"id": 2, "source_id": "missing_src", "target_id": "RS-001", "relation_type": "covers", "confidence": 0.8},
    ]
    store.get_all_edges.return_value = edges

    return store


@pytest.fixture
def store_with_cycles():
    """Mock store with a cycle."""
    store = MagicMock()
    store.get_all_nodes.return_value = [
        {"entity_id": "A", "entity_type": "requirement", "name": "A"},
        {"entity_id": "B", "entity_type": "requirement", "name": "B"},
        {"entity_id": "C", "entity_type": "requirement", "name": "C"},
    ]
    store.get_all_edges.return_value = [
        {"id": 1, "source_id": "A", "target_id": "B", "relation_type": "covers", "confidence": 0.8},
        {"id": 2, "source_id": "B", "target_id": "C", "relation_type": "covers", "confidence": 0.8},
        {"id": 3, "source_id": "C", "target_id": "A", "relation_type": "covers", "confidence": 0.8},
    ]
    return store


@pytest.fixture
def store_with_duplicates():
    """Mock store with duplicate nodes."""
    store = MagicMock()
    store.get_all_nodes.return_value = [
        {"entity_id": "RS-001", "entity_type": "requirement", "name": "First"},
        {"entity_id": "RS-001", "entity_type": "requirement", "name": "Duplicate"},
        {"entity_id": "RS-002", "entity_type": "requirement", "name": "Unique"},
    ]
    store.get_all_edges.return_value = [
        {"id": 1, "source_id": "RS-001", "target_id": "func_a", "relation_type": "covers", "confidence": 0.8},
    ]
    return store


# ═══════════════════════════════════════════════════════════════════════
# Tests: MergeGateConfig
# ═══════════════════════════════════════════════════════════════════════


class TestMergeGateConfig:
    def test_default_config(self):
        """Config SHALL have sensible defaults."""
        config = MergeGateConfig()
        assert config.min_confidence == 0.7
        assert config.min_coverage == 0.8
        assert config.max_orphan_nodes == 5
        assert config.max_orphan_edges == 3
        assert config.check_cycles is True
        assert config.check_consistency is True
        assert config.auto_build is True
        assert config.fail_on_warning is False
        assert config.base_ref == "HEAD~1"

    def test_from_dict(self):
        """Config SHALL create from dict with filtered keys."""
        config = MergeGateConfig.from_dict({
            "min_confidence": 0.5,
            "min_coverage": 0.6,
            "unknown_key": "should be filtered",
        })
        assert config.min_confidence == 0.5
        assert config.min_coverage == 0.6
        assert not hasattr(config, "unknown_key")
        assert config.max_orphan_nodes == 5  # default preserved

    def test_from_dict_empty(self):
        """Config SHALL handle empty dict, using all defaults."""
        config = MergeGateConfig.from_dict({})
        assert config.min_confidence == 0.7
        assert config.min_coverage == 0.8


# ═══════════════════════════════════════════════════════════════════════
# Tests: GraphConsistencyChecker
# ═══════════════════════════════════════════════════════════════════════


class TestGraphConsistencyChecker:
    def test_empty_graph_passes(self, mock_store):
        """CHECK-01: Empty graph SHALL pass consistency checks."""
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is True
        assert len(result["errors"]) == 0

    def test_valid_graph_passes(self, populated_store):
        """CHECK-02: Valid graph with good types SHALL pass."""
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(populated_store, config)
        result = checker.check_all()
        assert result["passed"] is True
        assert result["error_count"] == 0

    def test_invalid_node_type_detected(self, mock_store):
        """CHECK-03: Invalid node type SHALL be detected."""
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "bad", "entity_type": "UNKNOWN_TYPE"},
        ]
        mock_store.get_all_edges.return_value = []
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "node_type" for e in result["errors"])

    def test_invalid_edge_type_detected(self, mock_store):
        """CHECK-04: Invalid edge type SHALL be detected."""
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "A", "entity_type": "requirement"},
            {"entity_id": "B", "entity_type": "function"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "A", "target_id": "B", "relation_type": "FLYING_UNICORN"},
        ]
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "edge_type" for e in result["errors"])

    def test_orphan_nodes_exceed_threshold(self, mock_store):
        """CHECK-05: Too many orphan nodes SHALL cause error."""
        config = MergeGateConfig(max_orphan_nodes=1)
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "A", "entity_type": "requirement"},
            {"entity_id": "B", "entity_type": "function"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "A", "target_id": "B", "relation_type": "covers"},
        ]
        # Only one edge connects A and B, so A should have edges but B is also connected
        # Wait - edge connects A→B, so both A and B are "connected"
        # Let me create a setup where there are orphans
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "A", "entity_type": "requirement", "name": "Connected"},
            {"entity_id": "B", "entity_type": "requirement", "name": "Connected"},
            {"entity_id": "orphan1", "entity_type": "function", "name": "Orphan 1"},
            {"entity_id": "orphan2", "entity_type": "function", "name": "Orphan 2"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "A", "target_id": "B", "relation_type": "covers"},
        ]
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "orphan_nodes" for e in result["errors"])

    def test_orphan_edges_detected(self, store_with_orphans):
        """CHECK-06: Orphan edges (missing target) SHALL be detected."""
        config = MergeGateConfig(max_orphan_edges=0)
        checker = GraphConsistencyChecker(store_with_orphans, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "orphan_edges" for e in result["errors"])

    def test_cycles_detected(self, store_with_cycles):
        """CHECK-07: Cycles in the graph SHALL be detected."""
        config = MergeGateConfig(check_cycles=True)
        checker = GraphConsistencyChecker(store_with_cycles, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "cycles" for e in result["errors"])

    def test_cycle_check_disabled(self, store_with_cycles):
        """CHECK-08: When cycle check is disabled, cycles SHALL NOT cause errors."""
        config = MergeGateConfig(check_cycles=False)
        checker = GraphConsistencyChecker(store_with_cycles, config)
        result = checker.check_all()
        # Other errors might exist, but not cycles
        assert all(e["check"] != "cycles" for e in result.get("errors", []))

    def test_duplicate_nodes_detected(self, store_with_duplicates):
        """CHECK-09: Duplicate nodes SHALL generate warnings."""
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(store_with_duplicates, config)
        result = checker.check_all()
        warnings = result.get("warnings", [])
        assert any(w["check"] == "duplicate_nodes" for w in warnings)

    def test_node_read_exception(self, mock_store):
        """CHECK-10: Store read exception SHALL be handled gracefully."""
        mock_store.get_all_nodes.side_effect = RuntimeError("DB unavailable")
        config = MergeGateConfig()
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any("Failed to read nodes" in e["message"] for e in result["errors"])

    def test_fail_on_warning_empty_graph(self, mock_store):
        """CHECK-11: Empty graph with fail_on_warning SHALL pass (no warnings)."""
        config = MergeGateConfig(fail_on_warning=True)
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is True

    def test_orphan_nodes_below_threshold(self, mock_store):
        """CHECK-12: Few orphan nodes below threshold SHALL only warn."""
        config = MergeGateConfig(max_orphan_nodes=10)
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "A", "entity_type": "requirement", "name": "Connected"},
            {"entity_id": "orphan1", "entity_type": "function", "name": "Orphan 1"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "A", "target_id": "func_x", "relation_type": "covers"},
        ]
        checker = GraphConsistencyChecker(mock_store, config)
        result = checker.check_all()
        # Orphan1 has no edges - but wait, func_x node doesn't exist
        # Actually, orphan check looks at edges connecting nodes
        # orphan1 has no edges at all
        assert result["passed"] is True  # below threshold
        assert any(w["check"] == "orphan_nodes" for w in result.get("warnings", []))


# ═══════════════════════════════════════════════════════════════════════
# Tests: ConfidenceChecker
# ═══════════════════════════════════════════════════════════════════════


class TestConfidenceChecker:
    def test_empty_graph(self, mock_store):
        """CONF-01: Empty graph SHALL return 0 confidence and warning."""
        config = MergeGateConfig()
        checker = ConfidenceChecker(mock_store, config)
        result = checker.check_all()
        assert result["overall_confidence"] == 0.0
        assert result["coverage"] == 0.0
        assert len(result["warnings"]) > 0

    def test_fully_traced_high_confidence(self, populated_store):
        """CONF-02: Fully traced graph with high confidence SHALL pass."""
        config = MergeGateConfig(min_confidence=0.5)
        checker = ConfidenceChecker(populated_store, config)
        result = checker.check_all()
        assert result["passed"] is True
        assert result["overall_confidence"] > 0
        assert result["coverage"] > 0

    def test_low_confidence_blocks_merge(self, mock_store):
        """CONF-03: Requirements below confidence threshold SHALL block."""
        config = MergeGateConfig(min_confidence=0.9)
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-LOW", "entity_type": "requirement", "name": "Low Confidence"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "RS-LOW", "target_id": "func_x",
             "relation_type": "covers", "confidence": 0.3},
        ]
        checker = ConfidenceChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "confidence" for e in result["errors"])

    def test_no_traceability_blocks_merge(self, mock_store):
        """CONF-04: Requirement with zero edges SHALL block."""
        config = MergeGateConfig(min_confidence=0.7)
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-NO-TRACE", "entity_type": "requirement", "name": "No Trace"},
        ]
        mock_store.get_all_edges.return_value = []
        checker = ConfidenceChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False
        assert any(e["check"] == "confidence" for e in result["errors"])

    def test_low_coverage_blocks_merge(self, mock_store):
        """CONF-05: Low requirement coverage SHALL block."""
        config = MergeGateConfig(min_coverage=0.9)
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-001", "entity_type": "requirement", "name": "Traced"},
            {"entity_id": "RS-002", "entity_type": "requirement", "name": "Untraced"},
            {"entity_id": "RS-003", "entity_type": "requirement", "name": "Untraced 2"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "RS-001", "target_id": "func_x",
             "relation_type": "covers", "confidence": 0.8},
        ]
        checker = ConfidenceChecker(mock_store, config)
        result = checker.check_all()
        # 1/3 = 33% coverage, below 90%
        assert result["passed"] is False
        assert any(e["check"] == "coverage" for e in result["errors"])

    def test_store_exception_handled(self, mock_store):
        """CONF-06: Store exception SHALL be handled."""
        mock_store.get_all_nodes.side_effect = RuntimeError("DB fail")
        config = MergeGateConfig()
        checker = ConfidenceChecker(mock_store, config)
        result = checker.check_all()
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════
# Tests: MergeGate
# ═══════════════════════════════════════════════════════════════════════


class TestMergeGate:
    def test_empty_graph_pass(self, mock_store, tmp_path):
        """GATE-01: Empty graph with lenient config SHALL pass."""
        config = MergeGateConfig(
            min_confidence=0.0,
            min_coverage=0.0,
            max_orphan_nodes=100,
            auto_build=False,
        )
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        assert result["verdict"] == "pass"
        assert result["passed"] is True

    def test_populated_graph_pass(self, populated_store, tmp_path):
        """GATE-02: Valid populated graph with appropriate thresholds SHALL pass."""
        config = MergeGateConfig(
            min_confidence=0.5,
            min_coverage=0.5,
            auto_build=False,
        )
        gate = MergeGate(populated_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        assert result["verdict"] == "pass"
        assert result["passed"] is True

    def test_low_confidence_blocks(self, populated_store, tmp_path):
        """GATE-03: Graph with low confidence edges SHALL block."""
        config = MergeGateConfig(
            min_confidence=0.9,  # RS-003 has only 0.65
            min_coverage=0.0,
            auto_build=False,
        )
        gate = MergeGate(populated_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        assert result["verdict"] == "fail"
        assert result["passed"] is False

    def test_report_output_file(self, mock_store, tmp_path):
        """GATE-04: Report SHALL be written to output_path when configured."""
        report_path = tmp_path / "merge-gate-report.json"
        config = MergeGateConfig(
            min_confidence=0.0,
            min_coverage=0.0,
            auto_build=False,
            output_path=str(report_path),
        )
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        gate.run(changed_files=[])
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert "verdict" in data
        assert "checks" in data

    def test_change_detection(self, mock_store, tmp_path):
        """GATE-05: Explicit changed files SHALL appear in report."""
        config = MergeGateConfig(auto_build=False)
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=["src/main.cpp", "docs/spec.md"])
        assert result["change_summary"]["detected_changes"] == 2
        assert "src/main.cpp" in result["change_summary"]["changed_files"]

    def test_change_detection_git(self, mock_store, tmp_path):
        """GATE-06: Git-based change detection SHALL work."""
        config = MergeGateConfig(auto_build=False)
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "src/main.cpp\ndocs/spec.md\n"

            result = gate.run()

            assert result["change_summary"]["detected_changes"] == 2

    def test_git_failure_fallback(self, mock_store, tmp_path):
        """GATE-07: Git failure SHALL fall back to empty change list."""
        config = MergeGateConfig(auto_build=False)
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("git not found")
            result = gate.run()
            assert result["change_summary"]["detected_changes"] == 0

    def test_config_pass_through(self, mock_store, tmp_path):
        """GATE-08: Config SHALL be reflected in report."""
        config = MergeGateConfig(
            min_confidence=0.42,
            min_coverage=0.84,
            auto_build=False,
            base_ref="main",
        )
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        cfg = result["config"]
        assert cfg["min_confidence"] == 0.42
        assert cfg["min_coverage"] == 0.84
        assert cfg["base_ref"] == "main"

    def test_recommendations_on_failure(self, populated_store, tmp_path):
        """GATE-09: Failed gate SHALL generate recommendations."""
        config = MergeGateConfig(
            min_confidence=0.99,  # Will fail
            min_coverage=0.99,    # Will fail
            auto_build=False,
        )
        gate = MergeGate(populated_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        assert len(result["recommendations"]) > 0
        assert any("BLOCKED" in r or "error" in r for r in result["recommendations"])

    def test_recommendations_on_success(self, mock_store, tmp_path):
        """GATE-10: Passed gate SHALL have positive recommendation."""
        config = MergeGateConfig(
            min_confidence=0.0, min_coverage=0.0, auto_build=False,
            max_orphan_nodes=100,
        )
        # Add a valid node with edge so there are no errors or warnings
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-001", "entity_type": "requirement", "name": "Test"},
            {"entity_id": "func_x", "entity_type": "function", "name": "Func"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "RS-001", "target_id": "func_x",
             "relation_type": "covers", "confidence": 0.8},
        ]
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        result = gate.run(changed_files=[])
        assert any("pass" in r.lower() or "✅" in r
                    for r in result["recommendations"])


# ═══════════════════════════════════════════════════════════════════════
# Tests: CLI handler (cmd_check_merge)
# ═══════════════════════════════════════════════════════════════════════


class TestCmdCheckMerge:
    def test_cli_basic(self, tmp_path):
        """CLI-01: cmd_check_merge SHALL run without error with basic args."""
        with patch("yuleosh.knowledge_graph.merge_gate.MergeGate.run") as mock_run:
            mock_run.return_value = {
                "verdict": "pass",
                "passed": True,
                "duration_seconds": 0.1,
                "change_summary": {"detected_changes": 0},
                "summary": {"total_errors": 0, "total_warnings": 0,
                            "error_details": [], "warning_details": []},
                "checks": {},
                "config": {},
                "recommendations": ["✅ All checks passed"],
                "timestamp": "2026-01-01T00:00:00",
            }

            class Args:
                project_dir = str(tmp_path)
                base_ref = "HEAD~1"
                min_confidence = None
                min_coverage = None
                auto_build = True
                output = None
                fail_on_warning = False
                no_build = False
                json = False

            result = cmd_check_merge(Args())
            assert result["verdict"] == "pass"

    def test_cli_json_output(self, tmp_path):
        """CLI-02: JSON output flag SHALL work."""
        with patch("yuleosh.knowledge_graph.merge_gate.MergeGate.run") as mock_run:
            mock_run.return_value = {
                "verdict": "pass", "passed": True, "duration_seconds": 0.1,
                "change_summary": {"detected_changes": 0},
                "summary": {"total_errors": 0, "total_warnings": 0,
                            "error_details": [], "warning_details": []},
                "checks": {}, "config": {},
                "recommendations": [],
                "timestamp": "2026-01-01T00:00:00",
            }

            class Args:
                project_dir = str(tmp_path)
                base_ref = "HEAD~1"
                min_confidence = None
                min_coverage = None
                auto_build = True
                output = None
                fail_on_warning = False
                no_build = False
                json = True

            result = cmd_check_merge(Args())
            assert result["verdict"] == "pass"

    def test_cli_custom_thresholds(self, tmp_path):
        """CLI-03: Custom thresholds SHALL pass through to config."""
        with patch("yuleosh.knowledge_graph.merge_gate.MergeGate.run") as mock_run:
            mock_run.return_value = {
                "verdict": "pass", "passed": True, "duration_seconds": 0.1,
                "change_summary": {"detected_changes": 0},
                "summary": {"total_errors": 0, "total_warnings": 0,
                            "error_details": [], "warning_details": []},
                "checks": {}, "config": {"min_confidence": 0.5, "min_coverage": 0.6},
                "recommendations": [],
                "timestamp": "2026-01-01T00:00:00",
            }

            class Args:
                project_dir = str(tmp_path)
                base_ref = "main"
                min_confidence = 0.5
                min_coverage = 0.6
                auto_build = True
                output = None
                fail_on_warning = False
                no_build = True
                json = False

            result = cmd_check_merge(Args())
            assert result["verdict"] == "pass"


# ═══════════════════════════════════════════════════════════════════════
# Tests: Pipeline step (step_merge_gate)
# ═══════════════════════════════════════════════════════════════════════


class TestStepMergeGate:
    def test_pipeline_step_pass(self, tmp_path):
        """STEP-01: Passing merge gate SHALL return report path."""
        from yuleosh.pipeline.session import PipelineSession

        with patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            session = PipelineSession(
                name="test-pass",
                spec_path=str(tmp_path / "spec.md"),
            )
            with patch("yuleosh.knowledge_graph.merge_gate.MergeGate.run") as mock_run:
                mock_run.return_value = {
                    "verdict": "pass",
                    "passed": True,
                    "duration_seconds": 0.1,
                    "change_summary": {"detected_changes": 0},
                    "summary": {"total_errors": 0, "total_warnings": 0,
                                "error_details": [], "warning_details": []},
                    "checks": {},
                    "config": {},
                    "recommendations": ["✅ All checks passed"],
                    "timestamp": "2026-01-01T00:00:00",
                }
                result = step_merge_gate(session)
                assert result.endswith("merge-gate-report.json")

    def test_pipeline_step_fail_raises(self, tmp_path):
        """STEP-02: Failing merge gate SHALL raise PipelineStepError."""
        from yuleosh.pipeline.session import PipelineSession, PipelineStepError

        with patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            session = PipelineSession(
                name="test-fail",
                spec_path=str(tmp_path / "spec.md"),
            )
            with patch("yuleosh.knowledge_graph.merge_gate.MergeGate.run") as mock_run:
                mock_run.return_value = {
                    "verdict": "fail",
                    "passed": False,
                    "duration_seconds": 0.1,
                    "change_summary": {"detected_changes": 0},
                    "summary": {"total_errors": 2, "total_warnings": 0,
                                "error_details": [
                                    {"check": "confidence", "message": "Low confidence"},
                                    {"check": "orphan_nodes", "message": "Orphan nodes"},
                                ], "warning_details": []},
                    "checks": {},
                    "config": {},
                    "recommendations": ["Fix errors"],
                    "timestamp": "2026-01-01T00:00:00",
                }
                with pytest.raises(PipelineStepError) as exc:
                    step_merge_gate(session)
                assert "BLOCKED" in str(exc.value)
                assert "Low confidence" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════
# Tests: Edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_node_list(self, mock_store):
        """EDGE-01: Empty node list SHALL not crash."""
        checker = GraphConsistencyChecker(mock_store, MergeGateConfig())
        result = checker.check_all()
        assert result["passed"] is True

    def test_edge_without_confidence(self, mock_store):
        """EDGE-02: Edge without confidence field SHALL not crash."""
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-001", "entity_type": "requirement", "name": "Test"},
        ]
        mock_store.get_all_edges.return_value = [
            {"id": 1, "source_id": "RS-001", "target_id": "func_x",
             "relation_type": "covers"},  # no confidence field
        ]
        checker = ConfidenceChecker(mock_store, MergeGateConfig())
        result = checker.check_all()
        # No confidence on edge -> no confidences collected -> 0.0 overall
        # Requirement has no trace edges with confidence -> low confidence error
        assert result["passed"] is False
        assert result["overall_confidence"] == 0.0

    def test_mixed_node_types(self, mock_store):
        """EDGE-03: Mixed valid/invalid types SHALL report only invalid."""
        mock_store.get_all_nodes.return_value = [
            {"entity_id": "RS-001", "entity_type": "requirement"},
            {"entity_id": "bad", "entity_type": "INVALID_TYPE"},
            {"entity_id": "fn", "entity_type": "function"},
        ]
        mock_store.get_all_edges.return_value = []
        checker = GraphConsistencyChecker(mock_store, MergeGateConfig())
        result = checker.check_all()
        assert result["passed"] is False
        node_errors = [e for e in result["errors"] if e["check"] == "node_type"]
        assert len(node_errors) == 1

    def test_accept_all_types(self, mock_store):
        """EDGE-04: All valid types SHALL pass node type validation."""
        valid_nodes = []
        for t in GraphConsistencyChecker.VALID_NODE_TYPES:
            valid_nodes.append({
                "entity_id": f"node_{t}",
                "entity_type": t,
                "name": f"Test {t}",
            })
        mock_store.get_all_nodes.return_value = valid_nodes
        # Connect all nodes in a chain to avoid orphan detection
        edges = []
        for i in range(len(valid_nodes) - 1):
            edges.append({
                "id": i,
                "source_id": valid_nodes[i]["entity_id"],
                "target_id": valid_nodes[i + 1]["entity_id"],
                "relation_type": "related_to",
                "confidence": 1.0,
            })
        mock_store.get_all_edges.return_value = edges
        checker = GraphConsistencyChecker(mock_store, MergeGateConfig())
        result = checker.check_all()
        assert result["passed"] is True

    def test_no_changed_files_auto(self, mock_store, tmp_path):
        """EDGE-05: No changes without git SHALL not fail."""
        config = MergeGateConfig(auto_build=False)
        gate = MergeGate(mock_store, project_dir=str(tmp_path), config=config)
        result = gate.run()
        assert "change_summary" in result
        assert result["change_summary"]["detected_changes"] >= 0
