"""
Tests for the KG-aware Compliance Checker upgrade.

Covers:
- KG store initialisation and graceful fallback
- KG-driven semantic checks for SWE.4/SWE.5 base practices
- KG stats in report markdown
- Backward compatibility: original file-based checks still work
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def aspice_yaml_path():
    """Path to the ASPICE v3.1 YAML definition."""
    path = Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "compliance" / "aspice_v3.1.yaml"
    if path.exists():
        return path
    pytest.skip("aspice_v3.1.yaml not found")


@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal project directory for compliance testing."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "requirements.md").write_text("# Requirements\n- REQ-001: The system SHALL do X\n")
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void) { return 0; }")
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "api.h").write_text("#ifndef API_H\n#define API_H\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_answer(): assert 1 + 1 == 2\n")
    (tmp_path / "tests" / "test_utils.py").write_text("def test_utils(): assert True\n")
    (tmp_path / ".osh" / "ci").mkdir(parents=True)
    (tmp_path / ".osh" / "ci" / "layer1-abc123.json").write_text('{"status": "passed"}')
    (tmp_path / ".osh" / "reviews").mkdir()
    (tmp_path / ".osh" / "reviews" / "review-1.md").write_text("# Review\n")
    (tmp_path / ".osh" / "evidence").mkdir()
    (tmp_path / ".osh" / "evidence" / "traceability-matrix.md").write_text("# Traceability\n")
    (tmp_path / ".clang-format").write_text("BasedOnStyle: LLVM\n")
    return tmp_path


# ===================================================================
# Helper: build a simple mock Edge for queries to consume
# ===================================================================


class _MockEdge:
    """Lightweight stand-in for knowledge_graph.models.Edge."""
    def __init__(self, layer=None, edge_type="covers"):
        self.layer = layer  # queries.py accesses edge.layer
        self.properties = {"layer": layer} if layer else {}
        self.edge_type = edge_type
        self.source_id = 1
        self.target_id = 2
        self.id = 1
        self.verified_at = None
        self.build_id = None
        self.created_at = "2026-07-15T00:00:00"
        self.updated_at = "2026-07-15T00:00:00"


class _MockNode:
    """Lightweight stand-in for knowledge_graph.models.Node."""
    def __init__(self, entity_id="test_file_a.py", entity_type="test_file", label="test", file_path=None):
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.label = label
        self.properties = {"file_path": file_path} if file_path else {}
        self.id = 1
        self.is_active = True
        self.created_at = "2026-07-15T00:00:00"
        self.updated_at = "2026-07-15T00:00:00"

    def to_dict(self):
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "label": self.label,
            "properties": self.properties,
            "id": self.id,
            "is_active": self.is_active,
        }


class _MockSnapshot:
    """Lightweight stand-in for knowledge_graph.models.Snapshot."""
    def __init__(self, build_id="build-1"):
        self.build_id = build_id
        self.built_at = "2026-07-15T00:00:00"
        self.node_count = 42
        self.edge_count = 10
        self.meta = {}
        self.id = 1

    def to_dict(self):
        return {
            "build_id": self.build_id,
            "built_at": self.built_at,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "meta": self.meta,
            "id": self.id,
        }


# ===================================================================
# Test 1: KG check with store available
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_check_with_store(mock_get_store, tmp_path, aspice_yaml_path):
    """Mock KG store available -> KG check path should succeed."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    # Build a mock store that returns proper data for real queries
    fake_store = mock.MagicMock()

    # get_graph_stats
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 42,
        "total_edges": 10,
        "nodes_by_type": {"requirement": 10, "code_file": 15, "test_file": 8, "test_function": 20},
        "edges_by_type": {"implements": 5, "covers": 8, "validates": 3, "verifies": 1},
    })

    # list_edges for get_aspice_coverage and get_confirmation_trace
    # list_edges — use side_effect to return different data per edge_type
    covers_edges = [_MockEdge(layer="unit"), _MockEdge(layer="unit"), _MockEdge(layer="unit")]
    validates_edges = [_MockEdge(layer="integration", edge_type="validates"),
                       _MockEdge(layer="system", edge_type="validates")]
    all_edges = covers_edges + validates_edges + [_MockEdge(layer="integration")]

    def _list_edges(edge_type=None):
        if edge_type == "covers":
            return covers_edges
        if edge_type == "validates":
            return validates_edges
        return all_edges

    fake_store.list_edges = mock.MagicMock(side_effect=_list_edges)
    fake_store.get_node_by_id = mock.MagicMock(return_value=_MockNode())

    fake_store.list_snapshots = mock.MagicMock(return_value=[_MockSnapshot(b) for b in ["build-a", "build-b", "build-c"]])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)

    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()
    assert store is not None
    mock_get_store.assert_called_once()

    # _check_with_kg — trace check (uses _get_kg_stats -> get_graph_stats -> implements_edges)
    result = checker._check_with_kg("bidirectional trace", store)
    assert result is True, "Should find implements_edges > 0"

    # _check_with_kg — trace check (same KG stats path, uses implements_edges)
    result = checker._check_with_kg("traceability check", store)
    assert result is True, "Should find implements_edges > 0"

    # Check with some unit covers in coverage data
    # We need list_edges to return edges with layer="unit" for covers
    fake_store.list_edges.return_value = [_MockEdge(layer="unit"), _MockEdge(layer="unit"), _MockEdge(layer="unit")]
    result = checker._check_with_kg("unit test verification", store)
    assert result is True, "Should find unit covers > 0"

    # Confirmation/validation check: needs validates edges
    fake_store.list_edges.return_value = [_MockEdge(layer="integration", edge_type="validates"),
                                          _MockEdge(layer="system", edge_type="validates")]
    result = checker._check_with_kg("confirmation trace", store)
    assert result is True, "Should find validates edges"

    # Snapshot check
    result = checker._check_with_kg("CI result check", store)
    assert result is True, "Should find snapshots > 0"


# ===================================================================
# Test 2: Graceful fallback when KG is unavailable
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store", return_value=None)
def test_kg_check_without_store(mock_get_store, sample_project, aspice_yaml_path):
    """KG unavailable -> should gracefully fallback to file checks."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    store = checker._get_kg_store()
    assert store is None, "Should return None when get_store fails"

    # _check_with_kg should return None (fallback signal)
    result = checker._check_with_kg("bidirectional trace", store)
    assert result is None, "Should return None to signal fallback"

    # Full run should still work and produce valid report
    report = checker.run()
    assert report["summary"]["total_bps"] > 0
    assert "kg_data" in report
    assert report["kg_data"] == {}, "kg_data should be empty when KG unavailable"


# ===================================================================
# Test 3: _check_with_kg exception handling (graceful degradation)
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_check_graceful_degradation(mock_get_store, tmp_path, aspice_yaml_path):
    """KG store methods raising exceptions -> should fallback gracefully."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    broken_store = mock.MagicMock()
    broken_store.get_stats.side_effect = RuntimeError("KG store broken")
    broken_store.list_edges.side_effect = RuntimeError("list_edges broken")
    broken_store.list_snapshots.side_effect = RuntimeError("snapshots broken")
    mock_get_store.return_value = broken_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()
    assert store is not None

    # _check_with_kg catches the exception from _get_kg_stats and returns None
    result = checker._check_with_kg("bidirectional trace", store)
    assert result is None, "Should fallback on exception"


# ===================================================================
# Test 4: SWE.4 BP2/3 uses get_aspice_coverage via KG
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_swe4_unit_trace(mock_get_store, sample_project, aspice_yaml_path):
    """SWE.4 BP2 checks should use KG traceability data."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 42,
        "total_edges": 10,
        "nodes_by_type": {"requirement": 10, "test_file": 8},
        "edges_by_type": {"implements": 3, "covers": 5, "validates": 2},
    })
    fake_store.list_edges = mock.MagicMock()
    fake_store.list_edges.return_value = [
        _MockEdge(layer="unit"), _MockEdge(layer="unit"), _MockEdge(layer="unit"),
    ]
    fake_store.list_snapshots = mock.MagicMock(return_value=[_MockSnapshot("b1")])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    report = checker.run()

    # SWE.4 BP2 — "Establish bidirectional traceability" 
    swe4 = report["swe_sections"].get("swe.4", {})
    bps = {bp["id"]: bp for bp in swe4.get("base_practices", [])}

    assert "SWE.4.BP2" in bps
    bp2_details = "\n".join(bps["SWE.4.BP2"]["details"])
    assert "[KG]" in bp2_details, "SWE.4.BP2 should use KG checks"


# ===================================================================
# Test 5: SWE.5 BP2/3 uses get_confirmation_trace via KG
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_swe5_confirm_trace(mock_get_store, sample_project, aspice_yaml_path):
    """SWE.5 BP checks should use KG confirmation trace data."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 30,
        "total_edges": 8,
        "nodes_by_type": {"requirement": 5, "test_file": 5},
        "edges_by_type": {"implements": 2, "covers": 4, "validates": 2},
    })
    fake_store.list_edges = mock.MagicMock()
    fake_store.list_edges.return_value = [
        _MockEdge(layer="integration", edge_type="validates"),
        _MockEdge(layer="system", edge_type="validates"),
    ]
    fake_store.list_snapshots = mock.MagicMock(return_value=[_MockSnapshot("b1")])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    report = checker.run()

    swe5 = report["swe_sections"].get("swe.5", {})
    bps = {bp["id"]: bp for bp in swe5.get("base_practices", [])}

    # Check for [KG] tags in SWE.5 BPs
    kg_bp_found = False
    for bp_id, bp in bps.items():
        details_text = "\n".join(bp["details"])
        if "[KG]" in details_text:
            kg_bp_found = True
            break
    assert kg_bp_found, "At least one SWE.5 BP should have [KG] tagged checks"


# ===================================================================
# Test 6: KG stats in report
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_stats_in_report(mock_get_store, sample_project, aspice_yaml_path):
    """Report should contain KG information block when KG is available."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 42,
        "total_edges": 16,
        "nodes_by_type": {"requirement": 10, "test_file": 8, "code_file": 15, "test_function": 20},
        "edges_by_type": {"implements": 5, "covers": 8, "validates": 3, "verifies": 1},
    })
    # For get_aspice_coverage: covers edges with layers
    # Use side_effect to return proper data per edge_type
    covers_edges = [
        _MockEdge(layer="unit"), _MockEdge(layer="unit"),
        _MockEdge(layer="unit"), _MockEdge(layer="unit"),
        _MockEdge(layer="integration"), _MockEdge(layer="integration"),
    ]
    validates_edges = [
        _MockEdge(layer="integration", edge_type="validates"),
        _MockEdge(layer="system", edge_type="validates"),
    ]
    def _list_edges(edge_type=None):
        if edge_type == "covers":
            return covers_edges
        if edge_type == "validates":
            return validates_edges
        return covers_edges + validates_edges

    fake_store.list_edges = mock.MagicMock(side_effect=_list_edges)

    # Mock the get_node_by_id for get_confirmation_trace to return proper nodes
    _nodes = {
        1: _MockNode(entity_id="test_file_a.py", entity_type="test_file"),
        2: _MockNode(entity_id="RS-001", entity_type="requirement"),
        3: _MockNode(entity_id="test_file_b.py", entity_type="test_file"),
    }
    fake_store.get_node_by_id = mock.MagicMock(side_effect=lambda nid: _nodes.get(nid))
    fake_store.list_snapshots = mock.MagicMock(return_value=[
        _MockSnapshot(f"build-{i}") for i in range(6)
    ])
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    report = checker.run()

    # Check kg_data in report dict
    assert "kg_data" in report
    kg_data = report["kg_data"]
    assert kg_data["implements_edges"] == 5
    assert kg_data["covers_edges"] == 8
    assert kg_data["validates_edges"] == 3
    assert kg_data["confirms_count"] == 2  # 2 validates edges with resolvable nodes
    assert kg_data["snapshots_count"] == 6

    # Check coverage stats
    assert "coverage" in kg_data
    assert kg_data["coverage"]["unit"]["total_covers"] == 4
    assert kg_data["coverage"]["integration"]["total_covers"] == 2

    # Generate markdown and check KG Data section exists
    markdown = checker.generate_report_markdown(report)
    assert "## KG Data (Real Traceability)" in markdown
    assert "Total Nodes" in markdown
    assert "Total Edges" in markdown
    assert "CI Snapshots" in markdown
    assert "Per-Layer Coverage" in markdown
    assert "unit" in markdown


# ===================================================================
# Test 7: Original file-based checks still work
# ===================================================================


def test_original_checks_still_work(sample_project, aspice_yaml_path):
    """Original file-based check logic should be unaffected by KG changes."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)

    # All original helper methods should work
    assert checker._file_exists("docs", "requirements.md")
    assert checker._dir_has_files("tests")
    assert checker._has_traced_requirements()
    assert checker._ci_results_exist()
    assert checker._evidence_dir_exists()
    assert checker._count_unit_tests() >= 2
    assert checker._has_content_matching("SHALL", "docs", "requirements.md")

    # Full run should produce valid report
    report = checker.run()
    assert report["summary"]["total_bps"] > 0

    # Markdown generation should work
    markdown = checker.generate_report_markdown(report)
    assert "# ASPICE" in markdown
    assert "Summary" in markdown


# ===================================================================
# Test 8: run_and_save backward compatible
# ===================================================================


def test_run_and_save_backward_compatible(sample_project, aspice_yaml_path):
    """run_and_save() should still work with same signature and produce valid output."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    output_path = checker.run_and_save()

    assert output_path is not None
    assert Path(output_path).exists()
    content = Path(output_path).read_text()
    assert "# ASPICE" in content


# ===================================================================
# Test 9: Constructor signature unchanged
# ===================================================================


def test_constructor_signature_unchanged(tmp_path, aspice_yaml_path):
    """ComplianceChecker constructor should accept same args as before."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    # Default template (no template_path arg)
    checker1 = ComplianceChecker(str(tmp_path))
    assert checker1.project_dir == tmp_path
    assert checker1.template is not None

    # Custom template
    checker2 = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    assert checker2.template_path == aspice_yaml_path
    assert checker2.template is not None


# ===================================================================
# Test 10: KG check with zero edges — should return False
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_check_zero_edges(mock_get_store, tmp_path, aspice_yaml_path):
    """KG with zero implements edges -> KG check should return False (not None)."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 0,
        "total_edges": 0,
        "nodes_by_type": {},
        "edges_by_type": {"implements": 0, "covers": 0, "validates": 0},
    })
    fake_store.list_edges = mock.MagicMock(return_value=[])
    fake_store.list_snapshots = mock.MagicMock(return_value=[])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    # Trace check with zero implements edges
    result = checker._check_with_kg("bidirectional trace", store)
    assert result is False, "Should return False when no implements edges exist"

    # Unit test check with zero covers edges
    result = checker._check_with_kg("unit test verification", store)
    assert result is False, "Should return False when no unit covers exist"

    # Snapshot check with zero snapshots
    result = checker._check_with_kg("CI result", store)
    assert result is False, "Should return False when no snapshots exist"


# ===================================================================
# Test 11: New KG mappings (R-03) — all return True with data
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.queries.impact_analysis")
@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_new_mappings_with_data(mock_get_store, mock_impact, tmp_path, aspice_yaml_path):
    """New KG mappings (R-03) should return True when data exists in KG."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    from yuleosh.knowledge_graph.models import Node

    fake_store = mock.MagicMock()

    # get_stats: code_file=10 (> 5 for architecture)
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 50,
        "total_edges": 20,
        "nodes_by_type": {
            "requirement": 15,
            "code_file": 10,
            "test_file": 8,
            "test_function": 25,
        },
        "edges_by_type": {
            "implements": 5,
            "covers": 12,
            "validates": 3,
        },
    })

    # list_edges: covers across unit, integration, sil
    covers_edges = [
        _MockEdge(layer="unit"), _MockEdge(layer="unit"), _MockEdge(layer="unit"),
        _MockEdge(layer="unit"), _MockEdge(layer="integration"),
        _MockEdge(layer="integration"), _MockEdge(layer="sil"),
    ]

    def _list_edges(edge_type=None):
        if edge_type == "covers":
            return covers_edges
        if edge_type == "validates":
            return [_MockEdge(layer="integration", edge_type="validates"),
                    _MockEdge(layer="sil", edge_type="validates")]
        return covers_edges

    fake_store.list_edges = mock.MagicMock(side_effect=_list_edges)

    # list_nodes("code_file"): include .h headers for interface check
    fake_store.list_nodes = mock.MagicMock(return_value=[
        Node(entity_id="main.c", entity_type="code_file", label="main.c", id=10),
        Node(entity_id="utils.c", entity_type="code_file", label="utils.c", id=11),
        Node(entity_id="api.h", entity_type="code_file", label="api.h", id=12),
        Node(entity_id="config.h", entity_type="code_file", label="config.h", id=13),
        Node(entity_id="driver.c", entity_type="code_file", label="driver.c", id=14),
        Node(entity_id="protocol.c", entity_type="code_file", label="protocol.c", id=15),
        Node(entity_id="timer.c", entity_type="code_file", label="timer.c", id=16),
        Node(entity_id="can.h", entity_type="code_file", label="can.h", id=17),
    ])

    # list_snapshots: 5 snapshots, some with review/misra meta
    snapshots = [_MockSnapshot(f"build-{i}") for i in range(5)]
    snapshots[0].meta = {"review_id": "R-001", "reviewer": "Alice"}
    snapshots[1].meta = {"misra": "MISRA_C_2023", "checks": 256}
    fake_store.list_snapshots = mock.MagicMock(return_value=snapshots)

    # get_node_by_id for coverage / confirmation queries
    fake_store.get_node_by_id = mock.MagicMock(return_value=_MockNode(
        entity_id="test_file_a.py", entity_type="test_file"))
    fake_store.get_node = mock.MagicMock(return_value=None)

    # Mock impact_analysis to return a non-empty result
    mock_impact.return_value = {
        "affected_reqs": [{"req_id": "RS-001", "label": "Speed req"}],
        "affected_tests": [{"file": "test_speed.py", "functions": ["test_speed"]}],
        "affected_functions": ["calc_speed"],
        "impact_summary": "1 requirements, 1 test functions, 1 code functions affected",
    }

    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    # 1. coverage check
    result = checker._check_with_kg("Statement coverage ≥ 80%", store)
    assert result is True, "coverage: should find total covers > 0"

    # 2. architecture check
    result = checker._check_with_kg("Architecture defines component boundaries", store)
    assert result is True, "architecture: code_file count > 5"

    # 3. review check
    result = checker._check_with_kg("Architecture review is conducted and documented", store)
    assert result is True, "review: should find review evidence in snapshot meta"

    # 4. standard / coding standard check
    result = checker._check_with_kg("Source code follows defined coding standards", store)
    assert result is True, "standard: should find misra config in snapshot meta"

    # 5. interface check
    result = checker._check_with_kg("All external interfaces are defined", store)
    assert result is True, "interface: should find .h header files in KG"

    # 6. qualification check
    result = checker._check_with_kg("Qualification test scope covers all requirements", store)
    assert result is True, "qualification: should find integration/sil covers"

    # 7. acceptance check (same logic as qualification)
    result = checker._check_with_kg("Acceptance criteria are defined", store)
    assert result is True, "acceptance: should find integration/sil covers"

    # 8. regression check
    result = checker._check_with_kg("Regression test strategy is defined", store)
    assert result is True, "regression: snapshot count > 3"

    # 9. impact check
    result = checker._check_with_kg("Changes to requirements trigger impact analysis", store)
    assert result is True, "impact: impact_analysis should return non-empty result"


# ===================================================================
# Test 12: New KG mappings (R-03) — return False when data missing
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.queries.impact_analysis")
@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_new_mappings_no_data(mock_get_store, mock_impact, tmp_path, aspice_yaml_path):
    """New KG mappings (R-03) should return False when KG has no relevant data."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    from yuleosh.knowledge_graph.models import Node

    fake_store = mock.MagicMock()

    # get_stats: code_file=2 (not > 5), all edges=0
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 5,
        "total_edges": 0,
        "nodes_by_type": {
            "requirement": 3,
            "code_file": 2,
        },
        "edges_by_type": {},
    })

    # list_edges: empty (no covers, no validates)
    fake_store.list_edges = mock.MagicMock(return_value=[])

    # list_nodes("code_file"): only .c files, no .h headers
    fake_store.list_nodes = mock.MagicMock()
    fake_store.list_nodes.side_effect = lambda entity_type: {
        "code_file": [
            Node(entity_id="main.c", entity_type="code_file", label="main.c", id=1),
            Node(entity_id="utils.c", entity_type="code_file", label="utils.c", id=2),
        ],
        "review": [],
    }.get(entity_type, [])

    # list_snapshots: only 2 (not > 3 for regression), no review/misra meta
    snapshots = [_MockSnapshot(f"build-{i}") for i in range(2)]
    fake_store.list_snapshots = mock.MagicMock(return_value=snapshots)

    # get_node_by_id for coverage queries
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)

    # Mock impact_analysis to return an empty result
    mock_impact.return_value = {
        "affected_reqs": [],
        "affected_tests": [],
        "affected_functions": [],
        "impact_summary": "0 requirements, 0 test functions, 0 code functions affected",
    }

    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    # 1. coverage check — no covers at all
    result = checker._check_with_kg("Statement coverage ≥ 80%", store)
    assert result is False, "coverage: should return False when no covers"

    # 2. architecture check — only 2 code_file nodes
    result = checker._check_with_kg("Architecture defines component boundaries", store)
    assert result is False, "architecture: code_file count ≤ 5"

    # 3. review check — no review evidence in snapshot meta
    result = checker._check_with_kg("Architecture review is conducted", store)
    assert result is False, "review: no review evidence in KG"

    # 4. standard check — no misra config in snapshots
    result = checker._check_with_kg("Source code follows coding standards", store)
    assert result is False, "standard: no misra config in snapshots"

    # 5. interface check — no .h header files
    result = checker._check_with_kg("All external interfaces are defined", store)
    assert result is False, "interface: no .h header files in KG"

    # 6. qualification check — no integration/sil covers
    result = checker._check_with_kg("Qualification test scope covers all requirements", store)
    assert result is False, "qualification: no integration/sil covers"

    # 7. acceptance check
    result = checker._check_with_kg("Acceptance criteria are defined for each requirement", store)
    assert result is False, "acceptance: no integration/sil covers"

    # 8. regression check — only 2 snapshots
    result = checker._check_with_kg("Regression test strategy is defined", store)
    assert result is False, "regression: snapshot count ≤ 3"

    # 9. impact check — empty result from impact_analysis
    result = checker._check_with_kg("Changes to requirements trigger impact analysis", store)
    assert result is False, "impact: impact_analysis returned empty result"


# ===================================================================
# Test 13: New KG mappings — graceful degradation on exception
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_new_mappings_graceful_degradation(mock_get_store, tmp_path, aspice_yaml_path):
    """New KG mappings (R-03) should return None on exception (fallback to file check)."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    broken_store = mock.MagicMock()
    broken_store.get_stats.side_effect = RuntimeError("KG store broken")
    broken_store.list_edges.side_effect = RuntimeError("list_edges broken")
    broken_store.list_snapshots.side_effect = RuntimeError("snapshots broken")
    broken_store.list_nodes.side_effect = RuntimeError("list_nodes broken")
    mock_get_store.return_value = broken_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()
    assert store is not None

    # Most new check paths should return None on exception.
    # Exception: architecture uses _get_kg_stats() which swallows errors
    # internally and returns empty dict → code_file=0 → False.
    # (Review comes before architecture in the if-chain, so "Architecture
    #  review is conducted" goes through the review path, not architecture.)
    expect_none = [
        "Statement coverage ≥ 80%",
        "Architecture review is conducted",
        "Source code follows coding standards",
        "All external interfaces are defined",
        "Qualification test scope covers all requirements",
        "Regression test strategy is defined",
        "Changes to requirements trigger impact analysis",
    ]
    for check_item in expect_none:
        result = checker._check_with_kg(check_item, store)
        assert result is None, f"'{check_item}' should fallback on exception (got {result})"

    # Architecture check: _get_kg_stats() handles errors → returns False not None
    result = checker._check_with_kg("Architecture defines component boundaries", store)
    assert result is False, "architecture: _get_kg_stats swallows error → no code files"

    # Existing checks: _get_kg_stats returns empty dict, trace sees graph={}
    # and returns None (fallback), not False
    result = checker._check_with_kg("bidirectional trace", store)
    assert result is None, "trace: _get_kg_stats empty dict -> graph missing -> None"


# ===================================================================
# Test 14: Review check falls back to review-type nodes when snapshots lack data
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_review_check_via_nodes(mock_get_store, tmp_path, aspice_yaml_path):
    """Review check returns True when KG has review-type nodes (not just snapshot meta)."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    from yuleosh.knowledge_graph.models import Node

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 10,
        "total_edges": 2,
        "nodes_by_type": {"requirement": 5, "code_file": 3, "review": 2},
        "edges_by_type": {"implements": 1, "covers": 1},
    })
    fake_store.list_edges = mock.MagicMock(return_value=[_MockEdge(layer="unit")])
    fake_store.list_snapshots = mock.MagicMock(return_value=[_MockSnapshot("b1")])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)

    # list_nodes("review"): return review nodes
    fake_store.list_nodes = mock.MagicMock(return_value=[
        Node(entity_id="R-001", entity_type="review", label="Design Review", id=20),
        Node(entity_id="R-002", entity_type="review", label="Code Review", id=21),
    ])

    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    # Review check should find review-type nodes
    result = checker._check_with_kg("Design review is conducted per component", store)
    assert result is True, "review: should find review-type nodes in KG"


# ===================================================================
# Test 15: Impact check handles empty code_files gracefully
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_impact_no_code_files(mock_get_store, tmp_path, aspice_yaml_path):
    """Impact check returns False when KG has no code_file nodes."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 3,
        "total_edges": 0,
        "nodes_by_type": {"requirement": 3},
        "edges_by_type": {},
    })
    fake_store.list_nodes = mock.MagicMock(return_value=[])  # no code files
    fake_store.list_edges = mock.MagicMock(return_value=[])
    fake_store.list_snapshots = mock.MagicMock(return_value=[])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    result = checker._check_with_kg("Impact analysis covers schedule and risks", store)
    assert result is False, "impact: should return False when no code files exist"


# ===================================================================
# Test 16: Standard check returns False when no snapshots have misra
# ===================================================================


@mock.patch("yuleosh.knowledge_graph.get_store")
def test_kg_standard_no_misra(mock_get_store, tmp_path, aspice_yaml_path):
    """Standard check returns False when snapshots exist but none have misra config."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    from yuleosh.knowledge_graph.models import Node

    fake_store = mock.MagicMock()
    fake_store.get_stats = mock.MagicMock(return_value={
        "total_nodes": 5,
        "total_edges": 0,
        "nodes_by_type": {"code_file": 3, "requirement": 2},
        "edges_by_type": {},
    })
    fake_store.list_edges = mock.MagicMock(return_value=[])
    # Snapshots exist but have no misra in meta
    snapshots = [_MockSnapshot(f"build-{i}") for i in range(3)]
    snapshots[0].meta = {"compiler": "gcc", "flags": "-O2"}
    snapshots[1].meta = {"coverage": {"line": 85}}
    snapshots[2].meta = {}  # no meta at all
    fake_store.list_snapshots = mock.MagicMock(return_value=snapshots)
    fake_store.list_nodes = mock.MagicMock(return_value=[
        Node(entity_id="main.c", entity_type="code_file", label="main.c", id=1),
    ])
    fake_store.get_node_by_id = mock.MagicMock(return_value=None)
    fake_store.get_node = mock.MagicMock(return_value=None)
    mock_get_store.return_value = fake_store

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    store = checker._get_kg_store()

    result = checker._check_with_kg("Source code follows defined coding standards", store)
    assert result is False, "standard: should return False when no misra in snapshots"
