"""Tests for evidence/oem_templates.py — OEM traceability matrix export."""

import json
import tempfile
from pathlib import Path

import pytest

from yuleosh.evidence.oem_templates import (
    OEM_TEMPLATES,
    get_template,
    export_traceability_matrix,
    _TraceRow,
    _map_and_sort_rows,
    _format_markdown,
    _format_csv,
    _format_json,
    _build_trace_rows,
)


# ═══════════════════════════════════════════════════════════════════════
# Test Helpers — Mock Store
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_empty_store():
    """A store with no requirements — returns empty graphs."""

    class MockStore:
        def list_nodes(self, entity_type):
            return []

        def list_edges(self, edge_type):
            return []

    return MockStore()


@pytest.fixture
def mock_basic_store():
    """A store with 1 requirement, 1 code_file, 1 test function, 1 covers edge."""

    nid_counter = iter(range(1000))

    class MockNode:
        def __init__(self, entity_type, entity_id, label="", properties=None):
            self.id = next(nid_counter)
            self.entity_type = entity_type
            self.entity_id = entity_id
            self.label = label
            self.properties = properties or {}

    class MockEdge:
        def __init__(self, source_id, target_id, layer="", build_id="", edge_type="implements", properties=None):
            self.source_id = source_id
            self.target_id = target_id
            self.layer = layer
            self.build_id = build_id
            self.edge_type = edge_type
            self.properties = properties or {}

    nodes = {}
    edges_by_type = {"implements": [], "covers": [], "verifies": []}

    req_node = MockNode("requirement", "REQ-001", "System shall do X",
                         {"statement": "The system shall do X", "asil": "ASIL_B"})
    nodes[req_node.id] = req_node
    req_id = req_node.id

    code_node = MockNode("code_file", "src/main.c", "main.c",
                          {"file_path": "src/main.c"})
    nodes[code_node.id] = code_node
    code_id = code_node.id

    test_node = MockNode("test_function", "test_main", "test_main",
                          {"file_path": "tests/test_main.c"})
    nodes[test_node.id] = test_node
    test_id = test_node.id

    edges_by_type["implements"].append(
        MockEdge(req_id, code_id, layer="sw", build_id="b-1")
    )
    edges_by_type["covers"].append(
        MockEdge(req_id, test_id, layer="unit", build_id="b-1")
    )

    class MockStore:
        def __init__(self):
            self._nodes = nodes
            self._edges = edges_by_type

        def list_nodes(self, entity_type):
            if entity_type == "requirement":
                return [n for n in self._nodes.values() if n.entity_type == "requirement"]
            return []

        def list_edges(self, edge_type):
            return self._edges.get(edge_type, [])

        def get_node_by_id(self, nid):
            return self._nodes.get(nid)

    return MockStore()


@pytest.fixture
def mock_store_only_req():
    """A store with only requirements — no edges."""

    class MockNode:
        def __init__(self, entity_type, entity_id, label="", properties=None):
            self.id = 1
            self.entity_type = entity_type
            self.entity_id = entity_id
            self.label = label
            self.properties = properties or {}

    req = MockNode("requirement", "REQ-001", "System req",
                    {"statement": "shall do X"})

    class MockStore:
        def list_nodes(self, entity_type):
            if entity_type == "requirement":
                return [req]
            return []

        def list_edges(self, edge_type):
            return []

        def get_node_by_id(self, nid):
            if nid == 1:
                return req
            return None

    return MockStore()


# ═══════════════════════════════════════════════════════════════════════
# Template definition tests
# ═══════════════════════════════════════════════════════════════════════


class TestOemTemplates:
    def test_all_templates_have_required_keys(self):
        for name, tpl in OEM_TEMPLATES.items():
            assert "display_name" in tpl, f"{name} missing display_name"
            assert "description" in tpl, f"{name} missing description"
            assert "column_map" in tpl, f"{name} missing column_map"
            assert "required_columns" in tpl, f"{name} missing required_columns"
            assert "sort_key" in tpl, f"{name} missing sort_key"
            assert "sort_reverse" in tpl, f"{name} missing sort_reverse"

    def test_known_templates_present(self):
        names = {"generic", "vw", "bmw", "mercedes", "oem_common"}
        assert names == set(OEM_TEMPLATES.keys())

    def test_required_columns_match_column_map(self):
        for name, tpl in OEM_TEMPLATES.items():
            mapped_headers = set(tpl["column_map"].values())
            for col in tpl["required_columns"]:
                assert col in mapped_headers, (
                    f"{name}: required column '{col}' not in column_map values"
                )

    def test_generic_template_has_basic_columns(self):
        tpl = OEM_TEMPLATES["generic"]
        assert "Requirement ID" in tpl["required_columns"]
        assert "Test Case ID" in tpl["required_columns"]
        assert "Implementation File" in tpl["required_columns"]

    def test_vw_template_has_german_headers(self):
        tpl = OEM_TEMPLATES["vw"]
        assert "VW-Anforderungs-ID" in tpl["required_columns"]
        assert "Prüfer" in tpl["required_columns"]
        assert "ASIL" in tpl["required_columns"]

    def test_mercedes_has_abdeckungsgrad(self):
        tpl = OEM_TEMPLATES["mercedes"]
        assert "Abdeckungsgrad (%)" in tpl["required_columns"]

    def test_all_required_columns_unique(self):
        for name, tpl in OEM_TEMPLATES.items():
            cols = tpl["required_columns"]
            assert len(cols) == len(set(cols)), f"{name}: duplicate required columns"


# ═══════════════════════════════════════════════════════════════════════
# get_template tests
# ═══════════════════════════════════════════════════════════════════════


class TestGetTemplate:
    def test_known_name(self):
        tpl = get_template("vw")
        assert tpl["display_name"].startswith("Volkswagen")

    def test_unknown_falls_back_to_generic(self):
        tpl = get_template("nonexistent")
        assert tpl["display_name"] == "Generic ASPICE Traceability Matrix"
        assert tpl["sort_key"] == "Requirement ID"

    def test_generic_by_name(self):
        tpl = get_template("generic")
        assert "Generic" in tpl["display_name"]

    def test_bmw(self):
        tpl = get_template("bmw")
        assert "BMW" in tpl["display_name"]

    def test_mercedes(self):
        tpl = get_template("mercedes")
        assert "Mercedes-Benz" in tpl["display_name"]


# ═══════════════════════════════════════════════════════════════════════
# _TraceRow dataclass tests
# ═══════════════════════════════════════════════════════════════════════


class TestTraceRow:
    def test_default_values(self):
        row = _TraceRow()
        assert row.req_id == ""
        assert row.req_title == ""
        assert row.test_id == ""
        assert row.trace_type == "implements"
        assert row.properties == {}

    def test_custom_values(self):
        row = _TraceRow(req_id="REQ-1", test_name="Test-1", trace_type="covers",
                        test_evidence="/path/to/report")
        assert row.req_id == "REQ-1"
        assert row.test_name == "Test-1"
        assert row.trace_type == "covers"
        assert row.test_evidence == "/path/to/report"

    def test_asil_and_layer(self):
        row = _TraceRow(req_id="R1", req_asil="ASIL_D", layer="sw")
        assert row.req_asil == "ASIL_D"
        assert row.layer == "sw"


# ═══════════════════════════════════════════════════════════════════════
# _build_trace_rows tests
# ═══════════════════════════════════════════════════════════════════════


class TestBuildTraceRows:
    def test_empty_store_returns_empty(self, mock_empty_store):
        rows = _build_trace_rows(mock_empty_store)
        assert rows == []

    def test_req_with_code_and_test(self, mock_basic_store):
        rows = _build_trace_rows(mock_basic_store)
        assert len(rows) > 0
        # Should have at least 1 row with REQ-001, code_file + test info merged
        reqs = [r for r in rows if r.req_id == "REQ-001"]
        assert len(reqs) >= 1
        assert reqs[0].req_title == "System shall do X"
        assert reqs[0].code_file == "src/main.c"

    def test_filter_layer(self, mock_basic_store):
        rows = _build_trace_rows(mock_basic_store, filter_layer="nonexistent")
        assert rows == []

    def test_no_test_evidence_false(self, mock_basic_store):
        rows = _build_trace_rows(mock_basic_store, include_test_evidence=False)
        # test_evidence should be empty
        for r in rows:
            if r.test_id:
                assert r.test_evidence == ""

    def test_store_with_no_edges(self, mock_store_only_req):
        rows = _build_trace_rows(mock_store_only_req)
        # Store has req but no edges, so rows should be empty
        # because the code requires implements or covers edges
        assert rows == []

    def test_req_as_target_in_implements(self):
        """Some stores have requirement as target in implements edge."""

        class MockNode:
            def __init__(self, eid, etype, label="", props=None):
                self.id = hash(eid)
                self.entity_id = eid
                self.entity_type = etype
                self.label = label
                self.properties = props or {}

        class MockEdge:
            def __init__(self, src, tgt, layer="", build_id="", props=None):
                self.source_id = src.id
                self.target_id = tgt.id
                self.layer = layer
                self.build_id = build_id
                self.properties = props or {}

        code_node = MockNode("src/code.c", "code_file", "code",
                              {"file_path": "src/code.c"})
        req_node = MockNode("REQ-001", "requirement", "The req",
                            {"statement": "req text"})
        edge = MockEdge(code_node, req_node, layer="sw")

        nodes = {code_node.id: code_node, req_node.id: req_node}

        class MockStore:
            def list_nodes(self, entity_type):
                if entity_type == "requirement":
                    return [req_node]
                return []

            def list_edges(self, edge_type):
                if edge_type == "implements":
                    return [edge]
                return []

            def get_node_by_id(self, nid):
                return nodes.get(nid)

        store = MockStore()
        rows = _build_trace_rows(store)
        assert len(rows) > 0
        assert rows[0].req_id == "REQ-001"
        assert rows[0].code_file == "src/code.c"


# ═══════════════════════════════════════════════════════════════════════
# _map_and_sort_rows tests
# ═══════════════════════════════════════════════════════════════════════


class TestMapAndSortRows:
    def test_maps_internal_to_oem_columns(self):
        rows = [
            _TraceRow(req_id="R1", req_title="Title", test_id="T1"),
        ]
        tpl = OEM_TEMPLATES["generic"]
        mapped = _map_and_sort_rows(rows, tpl)
        assert len(mapped) == 1
        assert mapped[0]["Requirement ID"] == "R1"
        assert mapped[0]["Test Case ID"] == "T1"

    def test_sort_by_req_id(self):
        rows = [
            _TraceRow(req_id="R2"),
            _TraceRow(req_id="R1"),
            _TraceRow(req_id="R3"),
        ]
        tpl = OEM_TEMPLATES["generic"]
        mapped = _map_and_sort_rows(rows, tpl)
        ids = [m["Requirement ID"] for m in mapped]
        assert ids == ["R1", "R2", "R3"]

    def test_reverse_sort(self):
        rows = [
            _TraceRow(req_id="R1"),
            _TraceRow(req_id="R3"),
            _TraceRow(req_id="R2"),
        ]
        tpl = dict(OEM_TEMPLATES["generic"])
        tpl["sort_reverse"] = True
        mapped = _map_and_sort_rows(rows, tpl)
        ids = [m["Requirement ID"] for m in mapped]
        assert ids == ["R3", "R2", "R1"]

    def test_extra_columns_filled(self):
        rows = [_TraceRow(req_id="R1")]
        tpl = OEM_TEMPLATES["vw"]  # has extra_columns
        mapped = _map_and_sort_rows(rows, tpl)
        assert "ASIL" in mapped[0]
        assert mapped[0]["ASIL"] == "QM"  # default from extra_columns

    def test_empty_rows(self):
        mapped = _map_and_sort_rows([], OEM_TEMPLATES["generic"])
        assert mapped == []


# ═══════════════════════════════════════════════════════════════════════
# _format_markdown tests
# ═══════════════════════════════════════════════════════════════════════


class TestFormatMarkdown:
    def test_empty_rows(self):
        result = _format_markdown([], OEM_TEMPLATES["generic"])
        assert "无追溯数据" in result

    def test_header_present(self):
        rows = [{"Requirement ID": "R1", "Requirement Title": "T1", "Requirement Statement": "S1",
                 "Test Case ID": "", "Test Case Name": "", "Test Level": "", "Test Verdict": "",
                 "Test Evidence": "", "Implementation File": "", "Implementation Function": "",
                 "Layer": "", "Trace Type": "", "Build ID": ""}]
        result = _format_markdown(rows, OEM_TEMPLATES["generic"])
        assert "| Requirement ID |" in result
        assert "| R1 |" in result

    def test_pipe_escaped(self):
        rows = [{"Requirement ID": "R|1", "Requirement Title": "", "Requirement Statement": "",
                 "Test Case ID": "", "Test Case Name": "", "Test Level": "", "Test Verdict": "",
                 "Test Evidence": "", "Implementation File": "", "Implementation Function": "",
                 "Layer": "", "Trace Type": "", "Build ID": ""}]
        result = _format_markdown(rows, OEM_TEMPLATES["generic"])
        assert "R\\|1" in result

    def test_long_value_truncated(self):
        long_val = "A" * 100
        rows = [{"Requirement ID": long_val, "Requirement Title": "", "Requirement Statement": "",
                 "Test Case ID": "", "Test Case Name": "", "Test Level": "", "Test Verdict": "",
                 "Test Evidence": "", "Implementation File": "", "Implementation Function": "",
                 "Layer": "", "Trace Type": "", "Build ID": ""}]
        result = _format_markdown(rows, OEM_TEMPLATES["generic"])
        assert "..." in result

    def test_template_name_in_output(self):
        result = _format_markdown([], OEM_TEMPLATES["vw"])
        assert "Volkswagen Traceability Matrix" in result


# ═══════════════════════════════════════════════════════════════════════
# _format_csv tests
# ═══════════════════════════════════════════════════════════════════════


class TestFormatCsv:
    def test_header(self):
        rows = [{"Requirement ID": "R1", "Requirement Title": "T1"}]
        result = _format_csv(rows, OEM_TEMPLATES["generic"])
        assert "Requirement ID" in result
        assert "Requirement Title" in result

    def test_data_row(self):
        rows = [{"Requirement ID": "R1", "Requirement Title": "T1", "Requirement Statement": "S1",
                 "Test Case ID": "TC1", "Test Case Name": "", "Test Level": "", "Test Verdict": "",
                 "Test Evidence": "", "Implementation File": "", "Implementation Function": "",
                 "Layer": "", "Trace Type": "", "Build ID": ""}]
        result = _format_csv(rows, OEM_TEMPLATES["generic"])
        assert "R1" in result
        assert "T1" in result

    def test_empty(self):
        result = _format_csv([], OEM_TEMPLATES["generic"])
        assert "Requirement ID" in result  # still has header


# ═══════════════════════════════════════════════════════════════════════
# _format_json tests
# ═══════════════════════════════════════════════════════════════════════


class TestFormatJson:
    def test_structure(self):
        rows = [{"Requirement ID": "R1", "Requirement Title": "T1"}]
        result = _format_json(rows, OEM_TEMPLATES["generic"])
        data = json.loads(result)
        assert "export" in data
        assert "rows" in data
        assert "meta" in data
        assert data["meta"]["row_count"] == 1
        assert data["rows"][0]["Requirement ID"] == "R1"

    def test_empty_rows(self):
        result = _format_json([], OEM_TEMPLATES["generic"])
        data = json.loads(result)
        assert data["rows"] == []
        assert data["meta"]["row_count"] == 0


# ═══════════════════════════════════════════════════════════════════════
# export_traceability_matrix — integration tests
# ═══════════════════════════════════════════════════════════════════════


class TestExportTraceabilityMatrix:
    def test_empty_store_markdown(self, mock_empty_store):
        result = export_traceability_matrix(mock_empty_store, template="generic",
                                             output_format="markdown")
        assert "Generic ASPICE Traceability Matrix" in result
        assert "无追溯数据" in result or "rows: 0" in result.lower() or "0" in result

    def test_empty_store_csv(self, mock_empty_store):
        result = export_traceability_matrix(mock_empty_store, template="generic",
                                             output_format="csv")
        assert "Requirement ID" in result

    def test_empty_store_json(self, mock_empty_store):
        result = export_traceability_matrix(mock_empty_store, template="generic",
                                             output_format="json")
        data = json.loads(result)
        assert data["export"]["template"] == "Generic ASPICE Traceability Matrix"

    def test_basic_store_markdown(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, template="generic")
        assert "Generic" in result
        assert "REQ-001" in result

    def test_vw_template_markdown(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, template="vw",
                                             output_format="markdown")
        assert "Volkswagen" in result

    def test_bmw_template_csv(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, template="bmw",
                                             output_format="csv")
        assert "BMW" in result or "SW-Komponente" in result or "Titel" in result

    def test_mercedes_template_json(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, template="mercedes",
                                             output_format="json")
        data = json.loads(result)
        assert "Mercedes-Benz" in data["export"]["template"]

    def test_unknown_template_falls_back(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, template="unknown",
                                             output_format="markdown")
        assert "Generic" in result

    def test_filter_layer(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, filter_layer="nonexistent",
                                             output_format="markdown")
        assert "0" in result.split("Rows:")[1].split("\n")[0] if "Rows:" in result else True

    def test_invalid_format_raises(self, mock_empty_store):
        with pytest.raises(ValueError) as excinfo:
            export_traceability_matrix(mock_empty_store, output_format="xml")
        assert "Unsupported output format" in str(excinfo.value)

    def test_include_test_evidence_false(self, mock_basic_store):
        result = export_traceability_matrix(mock_basic_store, include_test_evidence=False,
                                             output_format="markdown")
        assert "REQ-001" in result
