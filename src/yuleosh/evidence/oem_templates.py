"""
yuleOSH OEM Template Adapter — Export traceability matrices in OEM-compatible formats.

Provides OEM template definitions (VW, BMW, Mercedes, generic ASPICE) and the
``export_traceability_matrix()`` function that transforms yuleOSH's internal KG
trace data into audit-ready formats matching each OEM's expected layout.

OEM templates
─────────────
Each template defines:
  - column_map:           yuleOSH internal field → OEM column header
  - required_columns:     ordered list of columns (as OEM headers)
  - sort_key:             column by which rows are sorted
  - sort_reverse:         ascending (False) or descending (True)
  - extra_columns:        additional OEM-specific columns (ASIL, reviewer, etc.)
  - header_style:         formatting hint for markdown tables

Usage
─────
    from yuleosh.evidence.oem_templates import export_traceability_matrix

    md = export_traceability_matrix(store, template="vw", output_format="markdown")
    csv = export_traceability_matrix(store, template="bmw", output_format="csv")
    json = export_traceability_matrix(store, template="mercedes", output_format="json")
"""

import csv
import io
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

log = logging.getLogger("yuleosh.evidence.oem_templates")

# ═══════════════════════════════════════════════════════════════════════
# Internal data model
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class _TraceRow:
    """One row in the traceability matrix, before OEM column mapping."""

    req_id: str = ""
    req_title: str = ""
    req_statement: str = ""
    req_source: str = ""           # e.g. spec doc name
    req_asil: str = ""             # ASIL level (QM, ASIL_A..D)
    req_layer: str = ""            # system / SW (ASPICE layer)
    test_id: str = ""
    test_name: str = ""
    test_file: str = ""
    test_function: str = ""
    test_type: str = ""            # unit / integration / sil / hil / system
    test_verdict: str = ""
    test_evidence: str = ""        # path or URL to test evidence
    code_file: str = ""
    code_function: str = ""
    coverage_pct: str = ""
    trace_type: str = "implements"  # implements / covers / verifies / validates
    reviewer: str = ""
    reviewed_at: str = ""
    build_id: str = ""
    layer: str = ""
    properties: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# OEM Template Definitions
# ═══════════════════════════════════════════════════════════════════════

OEM_TEMPLATES = {
    "generic": {
        "display_name": "Generic ASPICE Traceability Matrix",
        "description": "通用 ASPICE 追溯矩阵 — 包含完整的需求→代码→测试追溯链，适用于一般审计场景",
        "column_map": {
            "req_id": "Requirement ID",
            "req_title": "Requirement Title",
            "req_statement": "Requirement Statement",
            "test_id": "Test Case ID",
            "test_name": "Test Case Name",
            "test_file": "Test File",
            "test_type": "Test Level",
            "test_verdict": "Test Verdict",
            "test_evidence": "Test Evidence",
            "code_file": "Implementation File",
            "code_function": "Implementation Function",
            "layer": "Layer",
            "trace_type": "Trace Type",
            "build_id": "Build ID",
        },
        "required_columns": [
            "Requirement ID",
            "Requirement Title",
            "Requirement Statement",
            "Test Case ID",
            "Test Case Name",
            "Test Level",
            "Test Verdict",
            "Test Evidence",
            "Implementation File",
            "Implementation Function",
            "Layer",
            "Trace Type",
            "Build ID",
        ],
        "sort_key": "Requirement ID",
        "sort_reverse": False,
        "extra_columns": {},
        "header_style": "default",
    },
    "vw": {
        "display_name": "Volkswagen Traceability Matrix",
        "description": "Volkswagen 标准追溯矩阵 — 符合 VW 80000 / VDA ASPICE 审计要求，含 ASIL 等级、需求来源等信息",
        "column_map": {
            "req_id": "VW-Anforderungs-ID",
            "req_title": "Bezeichnung",
            "req_statement": "Anforderungstext",
            "req_source": "Quelle",
            "req_asil": "ASIL",
            "req_layer": "Ebene",
            "test_id": "Testfall-ID",
            "test_name": "Testfallbezeichnung",
            "test_file": "Testdatei",
            "test_type": "Teststufe",
            "test_verdict": "Testergebnis",
            "test_evidence": "Testnachweis",
            "code_file": "Implementierungsdatei",
            "code_function": "Funktion",
            "reviewer": "Prüfer",
            "reviewed_at": "Geprüft am",
            "layer": "ASPICE-Schicht",
            "trace_type": "Verbindungstyp",
            "build_id": "Build-ID",
        },
        "required_columns": [
            "VW-Anforderungs-ID",
            "Bezeichnung",
            "Anforderungstext",
            "Quelle",
            "ASIL",
            "Ebene",
            "Testfall-ID",
            "Testfallbezeichnung",
            "Teststufe",
            "Testergebnis",
            "Testnachweis",
            "Implementierungsdatei",
            "Funktion",
            "Prüfer",
            "Geprüft am",
            "ASPICE-Schicht",
            "Verbindungstyp",
            "Build-ID",
        ],
        "sort_key": "VW-Anforderungs-ID",
        "sort_reverse": False,
        "extra_columns": {
            "req_asil": "QM",
            "req_source": "SW Spec",
            "req_layer": "System",
            "reviewer": "",
            "reviewed_at": "",
        },
        "header_style": "vw",
    },
    "bmw": {
        "display_name": "BMW Traceability Matrix",
        "description": "BMW 标准追溯矩阵 — 符合 BMW Group ASPICE / Sicherheitsstandard 格式，含安全等级、评审记录",
        "column_map": {
            "req_id": "BMW-Anforderungs-ID",
            "req_title": "Titel",
            "req_statement": "Beschreibung",
            "req_asil": "ASIL / Safety Level",
            "req_source": "Quelle / Dokument",
            "test_id": "Test-Fall-ID",
            "test_name": "Test-Name",
            "test_file": "Test-Datei",
            "test_function": "Test-Funktion",
            "test_type": "Test-Level",
            "test_verdict": "Testergebnis",
            "test_evidence": "Nachweis-Dokument",
            "code_file": "SW-Komponente",
            "code_function": "SW-Funktion",
            "reviewer": "Reviewer",
            "reviewed_at": "Review-Datum",
            "layer": "SW-Schicht",
            "trace_type": "Mapping-Typ",
        },
        "required_columns": [
            "BMW-Anforderungs-ID",
            "Titel",
            "Beschreibung",
            "ASIL / Safety Level",
            "Quelle / Dokument",
            "Test-Fall-ID",
            "Test-Name",
            "Test-Level",
            "Testergebnis",
            "Nachweis-Dokument",
            "SW-Komponente",
            "SW-Funktion",
            "Reviewer",
            "Review-Datum",
            "SW-Schicht",
            "Mapping-Typ",
        ],
        "sort_key": "BMW-Anforderungs-ID",
        "sort_reverse": False,
        "extra_columns": {
            "req_asil": "QM",
            "req_source": "SW Spec",
            "reviewer": "",
            "reviewed_at": "",
        },
        "header_style": "bmw",
    },
    "mercedes": {
        "display_name": "Mercedes-Benz Traceability Matrix",
        "description": "Mercedes-Benz 标准追溯矩阵 — 符合 Mercedes-Benz ASPICE / MB.ASIL 审计格式，含安全完整性等级、需求类别",
        "column_map": {
            "req_id": "MBN-Anforderungs-ID",
            "req_title": "Titel / Kurzbeschreibung",
            "req_statement": "Anforderungsbeschreibung",
            "req_asil": "Sicherheitsintegritätsstufe (ASIL)",
            "req_source": "Quelle (ASPICE PA / System)",
            "test_id": "Prüfspezifikations-ID",
            "test_name": "Prüfbezeichnung",
            "test_file": "Prüfdatei",
            "test_type": "Prüfstufe",
            "test_verdict": "Prüfergebnis",
            "test_evidence": "Prüfnachweis",
            "code_file": "Implementierung (Datei)",
            "code_function": "Implementierung (Funktion)",
            "reviewer": "Verantwortlicher Prüfer",
            "reviewed_at": "Prüfdatum",
            "coverage_pct": "Abdeckungsgrad (%)",
            "build_id": "Build-Nummer",
            "layer": "ASPICE-Ebene",
            "trace_type": "Verbindungsart",
        },
        "required_columns": [
            "MBN-Anforderungs-ID",
            "Titel / Kurzbeschreibung",
            "Anforderungsbeschreibung",
            "Sicherheitsintegritätsstufe (ASIL)",
            "Quelle (ASPICE PA / System)",
            "Prüfspezifikations-ID",
            "Prüfbezeichnung",
            "Prüfstufe",
            "Prüfergebnis",
            "Prüfnachweis",
            "Implementierung (Datei)",
            "Implementierung (Funktion)",
            "Verantwortlicher Prüfer",
            "Prüfdatum",
            "Abdeckungsgrad (%)",
            "Build-Nummer",
            "ASPICE-Ebene",
            "Verbindungsart",
        ],
        "sort_key": "MBN-Anforderungs-ID",
        "sort_reverse": False,
        "extra_columns": {
            "req_asil": "QM",
            "req_source": "SW Spec",
            "reviewer": "",
            "reviewed_at": "",
            "coverage_pct": "",
        },
        "header_style": "mercedes",
    },
    "oem_common": {
        "display_name": "OEM Common Minimum Traceability Matrix",
        "description": "OEM 通用最小追溯集 — 跨 OEM 审计可接受的最小公共列集，适合对比多种模板",
        "column_map": {
            "req_id": "Requirement ID",
            "req_title": "Requirement Title",
            "test_id": "Test Case ID",
            "test_name": "Test Name",
            "test_type": "Test Level",
            "test_verdict": "Verdict",
            "test_evidence": "Evidence Link",
            "code_file": "Implementation",
            "trace_type": "Relation",
        },
        "required_columns": [
            "Requirement ID",
            "Requirement Title",
            "Test Case ID",
            "Test Name",
            "Test Level",
            "Verdict",
            "Evidence Link",
            "Implementation",
            "Relation",
        ],
        "sort_key": "Requirement ID",
        "sort_reverse": False,
        "extra_columns": {},
        "header_style": "default",
    },
}


def get_template(template_name: str) -> dict:
    """Look up an OEM template by name. Falls back to 'generic' on unknown names."""
    if template_name in OEM_TEMPLATES:
        return OEM_TEMPLATES[template_name]
    log.warning("Unknown OEM template '%s', falling back to 'generic'", template_name)
    return OEM_TEMPLATES["generic"]


# ═══════════════════════════════════════════════════════════════════════
# KG Data Pull
# ═══════════════════════════════════════════════════════════════════════


def _build_trace_rows(
    store,
    filter_layer: Optional[str] = None,
    include_test_evidence: bool = True,
) -> list[_TraceRow]:
    """Build internal trace rows from the KG store.

    Traverses the complete Requirement → Code → Test trace chain:
      - requirement  ──implements──→  code_file/code_function
      - requirement  ──covers──→  test_file/test_function
      - test_function  ──verifies──→  code_function

    Returns a list of ``_TraceRow`` dataclass instances.
    """
    rows: list[_TraceRow] = []

    # ── Collect all edges from the graph ─────────────────────────────────
    try:
        req_nodes = store.list_nodes("requirement")
    except Exception:
        req_nodes = []

    if not req_nodes:
        log.info("No requirement nodes in KG — returning empty trace matrix")
        return []

    # Build lookup maps for efficiency
    node_cache: dict[int, dict] = {}

    def _get_node_info(nid: int) -> dict:
        if nid in node_cache:
            return node_cache[nid]
        try:
            node = store.get_node_by_id(nid)
            if node:
                info = {
                    "entity_type": node.entity_type,
                    "entity_id": node.entity_id,
                    "label": node.label,
                    "properties": node.properties,
                }
                node_cache[nid] = info
                return info
        except Exception:
            pass
        node_cache[nid] = {}
        return {}

    # Collect implements edges
    try:
        implements_edges = store.list_edges("implements")
    except Exception:
        implements_edges = []

    # Collect covers edges
    try:
        covers_edges = store.list_edges("covers")
    except Exception:
        covers_edges = []

    # Collect verifies edges
    try:
        verifies_edges = store.list_edges("verifies")
    except Exception:
        verifies_edges = []

    # Build requirement → code mappings
    req_to_code: dict[str, list[_TraceRow]] = {}
    for edge in implements_edges:
        source_info = _get_node_info(edge.source_id)
        target_info = _get_node_info(edge.target_id)
        if source_info.get("entity_type") != "requirement":
            # Some stores have requirement as target
            if target_info.get("entity_type") == "requirement":
                source_info, target_info = target_info, source_info
            elif source_info.get("entity_type") != "requirement":
                continue

        req_id = source_info.get("entity_id", "")
        code_file = ""
        code_func = ""
        if target_info.get("entity_type") == "code_file":
            code_file = target_info.get("entity_id", "")
        elif target_info.get("entity_type") == "code_function":
            code_func = target_info.get("entity_id", "")
            code_file = target_info.get("properties", {}).get("file_path", "")

        row = _TraceRow(
            req_id=req_id,
            req_title=source_info.get("label", ""),
            code_file=code_file,
            code_function=code_func,
            trace_type="implements",
            layer=edge.layer or edge.properties.get("layer", ""),
            build_id=edge.build_id or "",
            properties=edge.properties,
        )

        # Populate req properties
        req_props = source_info.get("properties", {})
        if isinstance(req_props, dict):
            row.req_statement = req_props.get("statement", req_props.get("shall", "")) or ""
            row.req_asil = req_props.get("asil", req_props.get("safety_level", "")) or ""
            row.req_source = req_props.get("source", req_props.get("document", "")) or ""
            row.req_layer = req_props.get("layer", "") or ""

        if filter_layer and row.layer != filter_layer:
            continue
        req_to_code.setdefault(req_id, []).append(row)
        rows.append(row)

    # Build requirement → test mappings from covers edges
    for edge in covers_edges:
        source_info = _get_node_info(edge.source_id)
        target_info = _get_node_info(edge.target_id)
        if source_info.get("entity_type") != "requirement":
            if target_info.get("entity_type") == "requirement":
                source_info, target_info = target_info, source_info
            elif source_info.get("entity_type") != "requirement":
                continue

        req_id = source_info.get("entity_id", "")
        test_type = ""
        test_file = ""
        test_name = ""
        test_func = ""
        test_id_val = ""

        if target_info.get("entity_type") == "test_file":
            test_file = target_info.get("entity_id", "")
            test_name = target_info.get("label", "")
            test_id_val = test_file
        elif target_info.get("entity_type") == "test_function":
            test_func = target_info.get("entity_id", "")
            test_name = target_info.get("label", "")
            test_file = target_info.get("properties", {}).get("file_path", "")
            test_id_val = test_name
        else:
            continue

        edge_layer = edge.layer or edge.properties.get("layer", "")

        if filter_layer and edge_layer != filter_layer:
            continue

        # Check if we already have an implements row for this req_id
        existing_rows = req_to_code.get(req_id, [])
        if existing_rows:
            for erow in existing_rows:
                erow.test_id = test_id_val
                erow.test_name = test_name
                erow.test_file = test_file
                erow.test_function = test_func
                erow.test_type = edge_layer
                erow.test_evidence = str(test_file) if include_test_evidence else ""
                # Merge trace_type
                if erow.trace_type != "implements":
                    erow.trace_type = "implements+covers"
                else:
                    erow.trace_type = "implements"
        else:
            row = _TraceRow(
                req_id=req_id,
                req_title=source_info.get("label", ""),
                test_id=test_id_val,
                test_name=test_name,
                test_file=test_file,
                test_function=test_func,
                test_type=edge_layer,
                trace_type="covers",
                layer=edge_layer,
                test_evidence=str(test_file) if include_test_evidence else "",
                build_id=edge.build_id or "",
                properties=edge.properties,
            )
            req_props = source_info.get("properties", {})
            if isinstance(req_props, dict):
                row.req_statement = req_props.get("statement", req_props.get("shall", "")) or ""
                row.req_asil = req_props.get("asil", req_props.get("safety_level", "")) or ""
                row.req_source = req_props.get("source", req_props.get("document", "")) or ""
            rows.append(row)
            req_to_code.setdefault(req_id, []).append(row)

    # Augment with verifies edges (test_function → code_function)
    verifies_map: dict[int, list[dict]] = {}
    for edge in verifies_edges:
        source_info = _get_node_info(edge.source_id)
        target_info = _get_node_info(edge.target_id)
        if source_info.get("entity_type") == "test_function":
            test_func_id = source_info.get("entity_id", "")
            code_func_name = target_info.get("entity_id", "") if target_info.get("entity_type") == "code_function" else ""
            for row in rows:
                if row.test_function == test_func_id:
                    if code_func_name:
                        row.code_function = code_func_name
                    break

    return rows


# ═══════════════════════════════════════════════════════════════════════
# Formatting Helpers
# ═══════════════════════════════════════════════════════════════════════


def _map_and_sort_rows(rows: list[_TraceRow], template: dict) -> list[dict]:
    """Map internal row fields to OEM column names, then sort."""
    col_map = template["column_map"]
    sort_key = template["sort_key"]
    sort_rev = template["sort_reverse"]

    # Build reverse mapping: OEM header → internal field
    header_to_field = {v: k for k, v in col_map.items()}

    # Transform rows
    mapped: list[dict] = []
    for row in rows:
        row_dict = asdict(row)
        mapped_row = {}
        for oem_col, internal_field in header_to_field.items():
            val = row_dict.get(internal_field, "")
            mapped_row[oem_col] = val if val is not None else ""
        # Fill extra columns with defaults
        for extra_field, default_val in template.get("extra_columns", {}).items():
            internal_name = extra_field
            oem_name = col_map.get(internal_name, internal_name)
            if oem_name not in mapped_row or not mapped_row.get(oem_name):
                mapped_row[oem_name] = default_val
        mapped.append(mapped_row)

    # Sort
    if sort_key in col_map.values():
        mapped.sort(key=lambda r: str(r.get(sort_key, "")), reverse=sort_rev)

    return mapped


def _format_markdown(mapped_rows: list[dict], template: dict) -> str:
    """Format mapped rows as a markdown table."""
    columns = template["required_columns"]
    out = io.StringIO()
    out.write(f"# {template['display_name']}\n\n")
    out.write(f"> Generated: {datetime.now().isoformat()}\n")
    out.write(f"> Template: {template['display_name']}\n")
    out.write(f"> Rows: {len(mapped_rows)}\n\n")

    if not mapped_rows:
        out.write("*（无追溯数据）*\n\n")
        return out.getvalue()

    # Table header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    out.write(header + "\n")
    out.write(separator + "\n")

    for row in mapped_rows:
        cells = []
        for col in columns:
            val = row.get(col, "")
            # Escape pipe characters in cell values
            cell = str(val).replace("|", "\\|")
            # Truncate long values for readability
            if len(cell) > 80:
                cell = cell[:77] + "..."
            cells.append(cell)
        out.write("| " + " | ".join(cells) + " |\n")

    out.write("\n")
    out.write("---\n")
    out.write(f"*Export: {datetime.now().isoformat()} | yuleOSH OEM Template Adapter*\n")
    return out.getvalue()


def _format_csv(mapped_rows: list[dict], template: dict) -> str:
    """Format mapped rows as CSV."""
    columns = template["required_columns"]
    out = io.StringIO()
    writer = csv.writer(out)
    # Header
    writer.writerow(columns)
    # Data
    for row in mapped_rows:
        writer.writerow([row.get(col, "") for col in columns])
    return out.getvalue()


def _format_json(mapped_rows: list[dict], template: dict) -> str:
    """Format mapped rows as JSON."""
    columns = template["required_columns"]
    output = {
        "export": {
            "template": template["display_name"],
            "generated_at": datetime.now().isoformat(),
        },
        "columns": columns,
        "rows": [],
    }

    for row in mapped_rows:
        entry = {}
        for col in columns:
            entry[col] = row.get(col, "")
        output["rows"].append(entry)

    output["meta"] = {
        "row_count": len(mapped_rows),
        "column_count": len(columns),
    }

    return json.dumps(output, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════
# Main Export Function
# ═══════════════════════════════════════════════════════════════════════


def export_traceability_matrix(
    store,
    template: str = "generic",
    output_format: str = "markdown",
    filter_layer: Optional[str] = None,
    include_test_evidence: bool = True,
) -> str:
    """Export traceability matrix in OEM-compatible format.

    Pulls the full Requirement → Code → Test trace chain from the KG store,
    maps columns to the selected OEM template, sorts, and formats the output.

    Args:
        store: ``KGStore`` (or ``KGStorePG``) instance with populated data.
        template: OEM template name.
                  One of ``"generic"``, ``"vw"``, ``"bmw"``, ``"mercedes"``,
                  ``"oem_common"``. Unknown names fall back to ``"generic"``.
        output_format: Output serialization format.
                       ``"markdown"`` | ``"csv"`` | ``"json"``.
                       Default: ``"markdown"``.
        filter_layer: Optional layer filter (e.g. ``"unit"``, ``"integration"``,
                      ``"sil"``, ``"hil"``). ``None`` means all layers.
        include_test_evidence: When ``True``, include test evidence file paths
                               in the output. Default: ``True``.

    Returns:
        Formatted traceability matrix as a string.

    Raises:
        ValueError: If ``output_format`` is not one of the supported values.

    Examples:
        >>> from yuleosh.knowledge_graph import get_store
        >>> store = get_store()
        >>> md_matrix = export_traceability_matrix(store, template="vw")
        >>> csv_matrix = export_traceability_matrix(store, template="bmw",
        ...                                          output_format="csv")
    """
    # Validate arguments
    supported_formats = {"markdown", "csv", "json"}
    if output_format not in supported_formats:
        raise ValueError(
            f"Unsupported output format '{output_format}'. "
            f"Supported: {', '.join(sorted(supported_formats))}"
        )

    tpl = get_template(template)

    # Build internal trace rows
    rows = _build_trace_rows(store, filter_layer=filter_layer,
                             include_test_evidence=include_test_evidence)

    # Map to OEM columns and sort
    mapped_rows = _map_and_sort_rows(rows, tpl)

    # Format output
    formatters = {
        "markdown": _format_markdown,
        "csv": _format_csv,
        "json": _format_json,
    }

    return formatters[output_format](mapped_rows, tpl)
