#!/usr/bin/env python3
"""
Tests for yuleOSH OEM Template Adapter (oem_templates.py).

Tests cover:
  - Template field completeness for all OEM templates
  - Output format correctness (markdown, csv, json)
  - Layer filtering
  - Empty store graceful handling
  - Unknown template fallback
"""

import csv
import io
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

import pytest

from yuleosh.evidence.oem_templates import (
    OEM_TEMPLATES,
    export_traceability_matrix,
    get_template,
)


# ═══════════════════════════════════════════════════════════════════════
# Mock KGStore for test isolation
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MockNode:
    id: int
    entity_type: str
    entity_id: str
    label: str
    properties: dict
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MockEdge:
    id: int
    source_id: int
    target_id: int
    edge_type: str
    properties: dict
    layer: Optional[str] = None
    verified_at: Optional[str] = None
    build_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MockKGStore:
    """Minimal KG store mock for testing oem_templates.

    Pre-populated with sample requirements, code files, and test data
    when *auto_populate* is True (default).
    """

    def __init__(self, auto_populate: bool = True):
        self._nodes: dict[int, MockNode] = {}
        self._edges: list[MockEdge] = []
        self._next_id = 1
        if auto_populate:
            self._populate()

    def _nid(self) -> int:
        n = self._next_id
        self._next_id += 1
        return n

    def _add_node(self, entity_type: str, entity_id: str, label: str,
                  properties: Optional[dict] = None) -> int:
        nid = self._nid()
        self._nodes[nid] = MockNode(
            id=nid,
            entity_type=entity_type,
            entity_id=entity_id,
            label=label,
            properties=properties or {},
        )
        return nid

    def _add_edge(self, source_id: int, target_id: int, edge_type: str,
                  properties: Optional[dict] = None, layer: Optional[str] = None,
                  build_id: Optional[str] = None) -> int:
        eid = self._nid()
        self._edges.append(MockEdge(
            id=eid,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties or {},
            layer=layer,
            build_id=build_id,
        ))
        return eid

    def _populate(self):
        """Create a realistic test graph."""
        # Requirements
        req_brake = self._add_node(
            "requirement", "RS-BRAKE-001", "刹车灯控制",
            {"statement": "系统应在刹车踏板被踩下时点亮刹车灯",
             "asil": "ASIL_B", "source": "System Spec", "layer": "system"},
        )
        req_indicator = self._add_node(
            "requirement", "RS-INDICATOR-001", "转向灯控制",
            {"statement": "系统应在转向拨杆被操作时点亮相应转向灯",
             "asil": "ASIL_A", "source": "System Spec", "layer": "system"},
        )
        req_temp = self._add_node(
            "requirement", "RS-TEMP-001", "温度监控",
            {"statement": "系统应持续监控环境温度并报告异常",
             "asil": "QM", "source": "Safety Spec", "layer": "system"},
        )

        # Code files
        brake_file = self._add_node(
            "code_file", "src/brake_control.c", "Brake Control",
            {"language": "C"},
        )
        indicator_file = self._add_node(
            "code_file", "src/indicator_control.c", "Indicator Control",
            {"language": "C"},
        )
        temp_file = self._add_node(
            "code_file", "src/temp_monitor.c", "Temperature Monitor",
            {"language": "C"},
        )

        # Code functions
        brake_func = self._add_node(
            "code_function", "brake_control::activate_brake_light",
            "activate_brake_light",
            {"file_path": "src/brake_control.c"},
        )
        indicator_func = self._add_node(
            "code_function", "indicator_control::activate_indicator",
            "activate_indicator",
            {"file_path": "src/indicator_control.c"},
        )
        temp_func = self._add_node(
            "code_function", "temp_monitor::read_temperature",
            "read_temperature",
            {"file_path": "src/temp_monitor.c"},
        )

        # Test files
        brake_test = self._add_node(
            "test_file", "tests/test_brake_control.py", "Test Brake Control",
        )
        indicator_test = self._add_node(
            "test_file", "tests/test_indicator_control.py", "Test Indicator Control",
        )

        # Test functions
        brake_test_func = self._add_node(
            "test_function", "tests/test_brake_control.py::test_brake_light_activation",
            "test_brake_light_activation",
            {"file_path": "tests/test_brake_control.py"},
        )

        # ── Edges: Requirement → Code (implements) ─────
        self._add_edge(req_brake, brake_file, "implements",
                       properties={"layer": "system"}, build_id="build-042")
        self._add_edge(req_indicator, indicator_file, "implements",
                       properties={"layer": "system"}, build_id="build-042")
        self._add_edge(req_temp, temp_file, "implements",
                       properties={"layer": "system"}, build_id="build-042")

        # ── Edges: Requirement → Test (covers) ──────────
        self._add_edge(req_brake, brake_test, "covers",
                       layer="unit", build_id="build-042")
        self._add_edge(req_indicator, indicator_test, "covers",
                       layer="unit", build_id="build-042")

        # ── Edges: Test Function → Code Function (verifies) ──
        self._add_edge(brake_test_func, brake_func, "verifies")

        # ── Edges: code_file → code_function (contains) ──
        self._add_edge(brake_file, brake_func, "contains")
        self._add_edge(indicator_file, indicator_func, "contains")
        self._add_edge(temp_file, temp_func, "contains")

    # ── KGStore-like interface used by oem_templates ───────────────────

    def list_nodes(self, entity_type: Optional[str] = None):
        if entity_type:
            return [n for n in self._nodes.values() if n.entity_type == entity_type]
        return list(self._nodes.values())

    def get_node_by_id(self, node_id: int) -> Optional[MockNode]:
        return self._nodes.get(node_id)

    def get_node(self, entity_type: str, entity_id: str) -> Optional[MockNode]:
        for n in self._nodes.values():
            if n.entity_type == entity_type and n.entity_id == entity_id:
                return n
        return None

    def list_edges(self, edge_type: Optional[str] = None):
        if edge_type:
            return [e for e in self._edges if e.edge_type == edge_type]
        return list(self._edges)


class MockEmptyStore:
    """Empty store with no data — tests graceful empty output."""

    def list_nodes(self, entity_type=None):
        return []

    def get_node_by_id(self, node_id):
        return None

    def list_edges(self, edge_type=None):
        return []


# ═══════════════════════════════════════════════════════════════════════
# Shared Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def store():
    return MockKGStore(auto_populate=True)


@pytest.fixture
def empty_store():
    return MockEmptyStore()


# ═══════════════════════════════════════════════════════════════════════
# Tests: Template Field Completeness
# ═══════════════════════════════════════════════════════════════════════

REQUIRED_TEMPLATE_KEYS = {
    "display_name", "description", "column_map",
    "required_columns", "sort_key", "sort_reverse",
    "extra_columns", "header_style",
}


class TestTemplates:
    """Verify all templates have the required fields."""

    def _check_template(self, name: str, tpl: dict):
        missing = REQUIRED_TEMPLATE_KEYS - set(tpl.keys())
        assert not missing, f"Template '{name}' missing keys: {missing}"

        cm = tpl["column_map"]
        rc = tpl["required_columns"]

        # All required_columns must exist in column_map values
        for col in rc:
            assert col in cm.values(), (
                f"Template '{name}': required column '{col}' not in column_map values"
            )

        # sort_key must be a column in required_columns
        assert tpl["sort_key"] in rc, (
            f"Template '{name}': sort_key '{tpl['sort_key']}' not in required_columns"
        )

    def test_generic_template_fields(self):
        tpl = OEM_TEMPLATES["generic"]
        self._check_template("generic", tpl)

    def test_vw_template_fields(self):
        tpl = OEM_TEMPLATES["vw"]
        self._check_template("vw", tpl)

    def test_bmw_template_fields(self):
        tpl = OEM_TEMPLATES["bmw"]
        self._check_template("bmw", tpl)

    def test_mercedes_template_fields(self):
        tpl = OEM_TEMPLATES["mercedes"]
        self._check_template("mercedes", tpl)

    def test_oem_common_template_fields(self):
        tpl = OEM_TEMPLATES["oem_common"]
        self._check_template("oem_common", tpl)

    def test_all_templates_present(self):
        expected = {"generic", "vw", "bmw", "mercedes", "oem_common"}
        assert set(OEM_TEMPLATES.keys()) == expected

    def test_template_descriptions_nonempty(self):
        for name, tpl in OEM_TEMPLATES.items():
            assert tpl["description"].strip(), f"Template '{name}' has empty description"


# ═══════════════════════════════════════════════════════════════════════
# Tests: Export Formatting
# ═══════════════════════════════════════════════════════════════════════

class TestExportMarkdownFormat:
    """Verify Markdown output format."""

    def test_contains_table_header(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="markdown")
        # Should have table header with generic column names
        assert "# Generic ASPICE Traceability Matrix" in result
        assert "| Requirement ID" in result
        assert "| --- | --- |" in result

    def test_contains_data_rows(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="markdown")
        # Should contain requirement IDs that exist in the store
        assert "RS-BRAKE-001" in result
        assert "RS-INDICATOR-001" in result
        assert "RS-TEMP-001" in result

    def test_vw_columns_in_markdown(self, store):
        result = export_traceability_matrix(store, template="vw",
                                            output_format="markdown")
        # VW columns in header
        assert "VW-Anforderungs-ID" in result
        assert "ASIL" in result
        assert "Teststufe" in result

    def test_bmw_columns_in_markdown(self, store):
        result = export_traceability_matrix(store, template="bmw",
                                            output_format="markdown")
        assert "BMW-Anforderungs-ID" in result
        assert "ASIL / Safety Level" in result

    def test_mercedes_columns_in_markdown(self, store):
        result = export_traceability_matrix(store, template="mercedes",
                                            output_format="markdown")
        assert "MBN-Anforderungs-ID" in result
        assert "Sicherheitsintegritätsstufe (ASIL)" in result
        assert "Abdeckungsgrad (%)" in result


class TestExportCsvFormat:
    """Verify CSV output format."""

    def test_csv_header(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="csv")
        reader = csv.reader(io.StringIO(result))
        header = next(reader)
        assert "Requirement ID" in header
        assert "Test Case ID" in header
        assert "Trace Type" in header

    def test_csv_data_rows(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="csv")
        reader = csv.reader(io.StringIO(result))
        next(reader)  # skip header
        rows = list(reader)
        assert len(rows) == 3, f"Expected 3 data rows, got {len(rows)}"

    def test_csv_is_valid(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="csv")
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(result)
        assert dialect.delimiter == ","

    def test_csv_vw_format(self, store):
        result = export_traceability_matrix(store, template="vw",
                                            output_format="csv")
        reader = csv.reader(io.StringIO(result))
        header = next(reader)
        assert "VW-Anforderungs-ID" in header
        assert "ASIL" in header


class TestExportJsonFormat:
    """Verify JSON output format."""

    def test_json_structure(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json")
        data = json.loads(result)
        assert "export" in data
        assert "columns" in data
        assert "rows" in data
        assert "meta" in data

    def test_json_meta_counts(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json")
        data = json.loads(result)
        assert data["meta"]["column_count"] == len(data["columns"])
        assert data["meta"]["row_count"] == len(data["rows"])

    def test_json_data_content(self, store):
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json")
        data = json.loads(result)
        row_ids = [r.get("Requirement ID", "") for r in data["rows"]]
        assert "RS-BRAKE-001" in row_ids
        assert "RS-INDICATOR-001" in row_ids

    def test_json_vw_template(self, store):
        result = export_traceability_matrix(store, template="vw",
                                            output_format="json")
        data = json.loads(result)
        assert "VW-Anforderungs-ID" in data["columns"]
        # Data rows should have VW column names
        for row in data["rows"]:
            assert "VW-Anforderungs-ID" in row


# ═══════════════════════════════════════════════════════════════════════
# Tests: Filtering & Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestExportWithLayerFilter:
    """Verify layer filtering behavior."""

    def test_filter_unit_layers(self, store):
        """Unit layer should match unit test covers edges."""
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json",
                                            filter_layer="unit")
        data = json.loads(result)
        # Our mock has unit layer covers edges for brake and indicator
        assert data["meta"]["row_count"] >= 1

    def test_filter_system_layers(self, store):
        """System layer should match implements edges."""
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json",
                                            filter_layer="system")
        data = json.loads(result)
        # Our mock has system layer for all implements edges
        assert data["meta"]["row_count"] == 3

    def test_filter_no_match(self, store):
        """Filtering to a layer with no data should return no rows."""
        result = export_traceability_matrix(store, template="generic",
                                            output_format="json",
                                            filter_layer="hil")
        data = json.loads(result)
        assert data["meta"]["row_count"] == 0


class TestExportEmptyStore:
    """Verify graceful handling of empty KG store."""

    def test_empty_markdown(self, empty_store):
        result = export_traceability_matrix(empty_store, template="generic",
                                            output_format="markdown")
        assert "无追溯数据" in result or "Rows: 0" in result

    def test_empty_csv(self, empty_store):
        result = export_traceability_matrix(empty_store, template="generic",
                                            output_format="csv")
        reader = csv.reader(io.StringIO(result))
        header = next(reader)
        assert "Requirement ID" in header
        rows = list(reader)
        assert len(rows) == 0

    def test_empty_json(self, empty_store):
        result = export_traceability_matrix(empty_store, template="generic",
                                            output_format="json")
        data = json.loads(result)
        assert data["meta"]["row_count"] == 0
        assert data["rows"] == []


class TestExportUnknownTemplate:
    """Verify fallback to 'generic' for unknown template names."""

    def test_unknown_template_fallback(self, store):
        result = export_traceability_matrix(store, template="nonexistent",
                                            output_format="markdown")
        # Should fall back to generic
        assert "Generic ASPICE Traceability Matrix" in result

    def test_unknown_template_not_in_valid_set(self):
        tpl = get_template("made_up_name_123")
        assert tpl == OEM_TEMPLATES["generic"]


class TestExportInvalidFormat:
    """Verify error on unsupported output format."""

    def test_invalid_format_raises(self, store):
        with pytest.raises(ValueError, match="Unsupported output format"):
            export_traceability_matrix(store, template="generic",
                                       output_format="xml")


# ═══════════════════════════════════════════════════════════════════════
# Tests: get_template
# ═══════════════════════════════════════════════════════════════════════

class TestGetTemplate:
    """Verify template resolution logic."""

    def test_known_template(self):
        tpl = get_template("vw")
        assert tpl["display_name"].startswith("Volkswagen")

    def test_unknown_template(self):
        tpl = get_template("xyz_unknown")
        assert tpl == OEM_TEMPLATES["generic"]
