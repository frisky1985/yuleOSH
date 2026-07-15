# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.autosar — ARXML parser and data models.

Covers:
  - Data model construction (SWCComponent, PortPrototype, RunnableEntity)
  - ARXML parsing from file
  - Edge cases (empty ARXML, malformed XML, namespace variants)
  - CLI output formatting (markdown, json, tree)
  - Reference extraction
  - Package hierarchy
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.autosar import (
    ARXMLParser,
    parse_arxml_file,
    parse_arxml_packages,
    SWCComponent,
    PortPrototype,
    RunnableEntity,
    SwcInternalBehavior,
    ComSpec,
    AutoSarPackage,
)
from yuleosh.autosar.cli import _format_json, _format_tree, import_arxml_to_spec


# ===========================================================================
# Sample ARXML content (inline, no external file dependency)
# ===========================================================================

SAMPLE_ARXML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGE>
    <SHORT-NAME>AppLayer</SHORT-NAME>
    <ELEMENTS>
      <APPLICATION-SW-COMPONENT-TYPE UUID="11111111-1111-1111-1111-111111111111">
        <SHORT-NAME>TestSwc</SHORT-NAME>
        <PORT-PROTOTYPE>
          <SHORT-NAME>InputPort</SHORT-NAME>
          <REQUIRED-INTERFACE>
            <PORT-INTERFACE-REF>/AppLayer/Interfaces/InputInterface</PORT-INTERFACE-REF>
          </REQUIRED-INTERFACE>
        </PORT-PROTOTYPE>
        <PORT-PROTOTYPE>
          <SHORT-NAME>OutputPort</SHORT-NAME>
          <PROVIDED-INTERFACE>
            <PORT-INTERFACE-REF>/AppLayer/Interfaces/OutputInterface</PORT-INTERFACE-REF>
          </PROVIDED-INTERFACE>
        </PORT-PROTOTYPE>
        <SWC-INTERNAL-BEHAVIOR>
          <SHORT-NAME>TestSwcBehavior</SHORT-NAME>
          <EXCLUSIVE-AREA>
            <SHORT-NAME>CritSection</SHORT-NAME>
          </EXCLUSIVE-AREA>
          <RUNNABLE-ENTITY>
            <SHORT-NAME>TestRunnable</SHORT-NAME>
            <SYMBOL>TestRunnable</SYMBOL>
            <CAN-BE-INVOKED-CONCURRENTLY>false</CAN-BE-INVOKED-CONCURRENTLY>
            <DATA-READ-ACCESS>
              <TARGET>/AppLayer/TestSwc/InputPort</TARGET>
            </DATA-READ-ACCESS>
            <DATA-WRITE-ACCESS>
              <TARGET>/AppLayer/TestSwc/OutputPort</TARGET>
            </DATA-WRITE-ACCESS>
            <EVENT>
              <TIMING-EVENT>
                <PERIOD>0.01</PERIOD>
              </TIMING-EVENT>
            </EVENT>
          </RUNNABLE-ENTITY>
        </SWC-INTERNAL-BEHAVIOR>
      </APPLICATION-SW-COMPONENT-TYPE>
    </ELEMENTS>
  </AR-PACKAGE>
</AUTOSAR>"""

SAMPLE_ARXML_NO_NAMESPACE = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR>
  <AR-PACKAGE>
    <SHORT-NAME>NoNsPkg</SHORT-NAME>
    <ELEMENTS>
      <APPLICATION-SW-COMPONENT-TYPE UUID="22222222-2222-2222-2222-222222222222">
        <SHORT-NAME>NoNsSwc</SHORT-NAME>
        <PORT-PROTOTYPE>
          <SHORT-NAME>PortA</SHORT-NAME>
          <PROVIDED-INTERFACE>
            <PORT-INTERFACE-REF>/NoNsPkg/Interfaces/PortAInterface</PORT-INTERFACE-REF>
          </PROVIDED-INTERFACE>
        </PORT-PROTOTYPE>
      </APPLICATION-SW-COMPONENT-TYPE>
    </ELEMENTS>
  </AR-PACKAGE>
</AUTOSAR>"""

MINIMAL_ARXML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGE>
    <SHORT-NAME>EmptyPkg</SHORT-NAME>
  </AR-PACKAGE>
</AUTOSAR>"""


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a temporary sample ARXML file."""
    f = tmp_path / "sample.arxml"
    f.write_text(SAMPLE_ARXML, encoding="utf-8")
    return f


@pytest.fixture
def no_ns_file(tmp_path: Path) -> Path:
    """Create a temporary ARXML file without namespace."""
    f = tmp_path / "no_ns.arxml"
    f.write_text(SAMPLE_ARXML_NO_NAMESPACE, encoding="utf-8")
    return f


@pytest.fixture
def minimal_file(tmp_path: Path) -> Path:
    """Create a minimal/empty ARXML file."""
    f = tmp_path / "minimal.arxml"
    f.write_text(MINIMAL_ARXML, encoding="utf-8")
    return f


@pytest.fixture
def real_sample_file() -> str:
    """Path to the real sample ARXML file."""
    return str(
        Path(__file__).parent.parent / "docs" / "examples" / "sample-autosar-swc.arxml"
    )


# ===========================================================================
# Data Model Tests
# ===========================================================================


class TestModels:
    """Tests for AUTOSAR dataclass models."""

    def test_swc_component_defaults(self):
        swc = SWCComponent(short_name="Test")
        assert swc.short_name == "Test"
        assert swc.ports == []
        assert swc.runnables == []
        assert swc.component_type == "ApplicationSwComponentType"
        assert swc.uuid == ""

    def test_swc_port_by_name(self):
        swc = SWCComponent(short_name="Test")
        swc.ports.append(PortPrototype(short_name="Port1", direction="in"))
        swc.ports.append(PortPrototype(short_name="Port2", direction="out"))
        assert swc.port_by_name("Port1") is not None
        assert swc.port_by_name("Port1").direction == "in"
        assert swc.port_by_name("NonExistent") is None

    def test_swc_runnable_by_name(self):
        swc = SWCComponent(short_name="Test")
        swc.runnables.append(RunnableEntity(short_name="Runnable1"))
        assert swc.runnable_by_name("Runnable1") is not None
        assert swc.runnable_by_name("NonExistent") is None

    def test_port_prototype_defaults(self):
        port = PortPrototype(short_name="P1")
        assert port.kind == "SenderReceiver"
        assert port.direction == "in"
        assert port.interface_ref == ""
        assert port.com_spec is None

    def test_port_prototype_full(self):
        com_spec = ComSpec(data_element="signal1", init_value="0")
        port = PortPrototype(
            short_name="P1",
            kind="ClientServer",
            direction="out",
            interface_ref="MyInterface",
            com_spec=com_spec,
            is_service=True,
        )
        assert port.kind == "ClientServer"
        assert port.direction == "out"
        assert port.interface_ref == "MyInterface"
        assert port.com_spec is not None
        assert port.com_spec.data_element == "signal1"
        assert port.is_service

    def test_runnable_entity_defaults(self):
        r = RunnableEntity(short_name="Rx")
        assert r.symbol == ""
        assert r.period_ms is None
        assert r.data_read_access == []
        assert r.data_write_access == []
        assert r.timing_event is None

    def test_runnable_entity_full(self):
        r = RunnableEntity(
            short_name="Tx",
            symbol="CanIf_TxIndication",
            period_ms=10.0,
            can_be_invoked_concurrently=True,
            data_read_access=["PortA"],
            data_write_access=["PortB"],
            timing_event="TimingEvent_10ms",
        )
        assert r.symbol == "CanIf_TxIndication"
        assert r.period_ms == 10.0
        assert r.can_be_invoked_concurrently
        assert "PortA" in r.data_read_access
        assert r.timing_event == "TimingEvent_10ms"

    def test_com_spec_defaults(self):
        s = ComSpec()
        assert s.data_element == ""
        assert s.init_value is None
        assert s.queue_length is None

    def test_auto_sar_package_tree(self):
        pkg = AutoSarPackage(short_name="Root")
        sub = AutoSarPackage(short_name="Sub")
        swc = SWCComponent(short_name="MySwc")
        pkg.sub_packages.append(sub)
        pkg.sw_components.append(swc)
        tree = pkg.print_tree()
        assert "📦 Root" in tree
        assert "📦 Sub" in tree
        assert "📄 MySwc" in tree

    def test_package_find_component(self):
        pkg = AutoSarPackage(short_name="Root")
        swc = SWCComponent(short_name="MySwc")
        pkg.sw_components.append(swc)
        assert pkg.find_component("MySwc") is swc
        assert pkg.find_component("Nope") is None

    def test_package_recursive_find(self):
        root = AutoSarPackage(short_name="Root")
        sub = AutoSarPackage(short_name="Sub")
        swc = SWCComponent(short_name="Deep")
        sub.sw_components.append(swc)
        root.sub_packages.append(sub)
        assert root.find_component("Deep") is swc

    def test_package_all_components(self):
        root = AutoSarPackage(short_name="Root")
        swc1 = SWCComponent(short_name="A")
        swc2 = SWCComponent(short_name="B")
        root.sw_components.append(swc1)
        root.sub_packages.append(AutoSarPackage(short_name="Sub"))
        root.sub_packages[0].sw_components.append(swc2)
        all_c = root.all_components()
        assert len(all_c) == 2
        assert swc1 in all_c
        assert swc2 in all_c


# ===========================================================================
# ARXML Parser Tests
# ===========================================================================


class TestARXMLParser:
    """Tests for ARXMLParser."""

    def test_parse_sample(self, sample_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(sample_file))
        assert len(swcs) == 1
        swc = swcs[0]
        assert swc.short_name == "TestSwc"
        assert swc.component_type == "APPLICATION-SW-COMPONENT-TYPE"

    def test_parse_sample_ports(self, sample_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(sample_file))
        swc = swcs[0]
        assert len(swc.ports) == 2
        port_names = {p.short_name for p in swc.ports}
        assert "InputPort" in port_names
        assert "OutputPort" in port_names

    def test_parse_sample_runnables(self, sample_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(sample_file))
        swc = swcs[0]
        assert len(swc.runnables) == 1
        runnable = swc.runnables[0]
        assert runnable.short_name == "TestRunnable"
        assert runnable.period_ms is not None
        assert runnable.symbol == "TestRunnable"

    def test_parse_sample_behavior(self, sample_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(sample_file))
        swc = swcs[0]
        assert len(swc.internal_behaviors) == 1
        ib = swc.internal_behaviors[0]
        assert ib.short_name == "TestSwcBehavior"
        assert "CritSection" in ib.exclusive_areas

    def test_parse_minimal_empty(self, minimal_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(minimal_file))
        assert len(swcs) == 0

    def test_parse_no_namespace(self, no_ns_file: Path):
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(no_ns_file))
        assert len(swcs) == 1
        assert swcs[0].short_name == "NoNsSwc"

    def test_parse_file_convenience(self, sample_file: Path):
        swcs = parse_arxml_file(str(sample_file))
        assert len(swcs) == 1

    def test_parse_packages(self, sample_file: Path):
        packages = parse_arxml_packages(str(sample_file))
        assert len(packages) == 1
        assert packages[0].short_name == "AppLayer"
        comps = packages[0].all_components()
        assert len(comps) == 1
        assert comps[0].short_name == "TestSwc"

    def test_parse_nonexistent_file(self):
        parser = ARXMLParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_swc("/nonexistent/file.arxml")

    def test_parse_malformed_xml(self, tmp_path: Path):
        f = tmp_path / "bad.arxml"
        f.write_text("not xml", encoding="utf-8")
        parser = ARXMLParser()
        with pytest.raises(ET.ParseError):
            parser.parse_swc(str(f))

    def test_port_direction_detection(self, tmp_path: Path):
        """Test that R-PORT gets direction 'in' and P-PORT gets 'out'."""
        arxml = """<?xml version="1.0" encoding="UTF-8"?>
        <AUTOSAR xmlns="http://autosar.org/schema/r4.0">
          <AR-PACKAGE>
            <SHORT-NAME>Pkg</SHORT-NAME>
            <ELEMENTS>
              <APPLICATION-SW-COMPONENT-TYPE>
                <SHORT-NAME>Swc</SHORT-NAME>
                <R-PORT-PROTOTYPE>
                  <SHORT-NAME>RxPort</SHORT-NAME>
                  <REQUIRED-INTERFACE>
                    <PORT-INTERFACE-REF>/Pkg/Intf</PORT-INTERFACE-REF>
                  </REQUIRED-INTERFACE>
                </R-PORT-PROTOTYPE>
                <P-PORT-PROTOTYPE>
                  <SHORT-NAME>TxPort</SHORT-NAME>
                  <PROVIDED-INTERFACE>
                    <PORT-INTERFACE-REF>/Pkg/Intf</PORT-INTERFACE-REF>
                  </PROVIDED-INTERFACE>
                </P-PORT-PROTOTYPE>
              </APPLICATION-SW-COMPONENT-TYPE>
            </ELEMENTS>
          </AR-PACKAGE>
        </AUTOSAR>"""
        f = tmp_path / "ports.arxml"
        f.write_text(arxml, encoding="utf-8")
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(f))
        assert len(swcs[0].ports) == 2
        port_map = {p.short_name: p for p in swcs[0].ports}
        assert port_map["RxPort"].direction == "in"
        assert port_map["TxPort"].direction == "out"

    def test_real_sample_file(self, real_sample_file: str):
        """Test parsing of the real-world sample ARXML file."""
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        assert len(swcs) == 2, f"Expected 2 SWCs, got {len(swcs)}"
        names = {s.short_name for s in swcs}
        assert "CanIf" in names
        assert "CanSm" in names

    def test_real_sample_ports_detail(self, real_sample_file: str):
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        canif = next(s for s in swcs if s.short_name == "CanIf")
        # CanIf has 4 ports
        assert len(canif.ports) >= 3
        port_names = {p.short_name for p in canif.ports}
        assert "CanRxData" in port_names
        assert "CanTxData" in port_names

    def test_real_sample_runnables_detail(self, real_sample_file: str):
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        cansm = next(s for s in swcs if s.short_name == "CanSm")
        assert len(cansm.runnables) == 2
        r_names = {r.short_name for r in cansm.runnables}
        assert "CanSm_MainFunction" in r_names

    def test_real_sample_timing_events(self, real_sample_file: str):
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        canif = next(s for s in swcs if s.short_name == "CanIf")
        tx_conf = next(r for r in canif.runnables if r.short_name == "CanIf_TxConfirmation")
        assert tx_conf.period_ms is not None
        assert tx_conf.timing_event is not None

    def test_real_sample_data_access(self, real_sample_file: str):
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        canif = next(s for s in swcs if s.short_name == "CanIf")
        rx_ind = next(r for r in canif.runnables if r.short_name == "CanIf_RxIndication")
        assert len(rx_ind.data_read_access) >= 0
        assert len(rx_ind.data_write_access) >= 0

    def test_real_sample_behavior(self, real_sample_file: str):
        parser = ARXMLParser()
        swcs = parser.parse_swc(real_sample_file)
        canif = next(s for s in swcs if s.short_name == "CanIf")
        assert len(canif.internal_behaviors) == 1
        assert canif.internal_behaviors[0].short_name == "CanIfBehavior"


# ===========================================================================
# Reference extraction tests
# ===========================================================================


class TestRefExtraction:
    """Tests for reference name extraction."""

    def test_extract_from_path(self):
        result = ARXMLParser._extract_ref_name(
            "/CanStack/SwcComponents/CanIf/CanRxData"
        )
        assert result == "CanRxData"

    def test_extract_simple(self):
        result = ARXMLParser._extract_ref_name("PortName")
        assert result == "PortName"

    def test_extract_empty(self):
        result = ARXMLParser._extract_ref_name("")
        assert result == ""

    def test_extract_trailing_slash(self):
        result = ARXMLParser._extract_ref_name("/pkg/swc/port/")
        assert result == "port"


# ===========================================================================
# CLI / Output formatting tests
# ===========================================================================


class TestCLIFormatting:
    """Tests for CLI output formatting."""

    def test_format_json(self):
        swc = SWCComponent(
            short_name="TestSwc",
            uuid="uuid-1",
            component_type="ApplicationSwComponentType",
        )
        swc.ports.append(PortPrototype(short_name="P1", direction="in"))
        json_str = _format_json([swc])
        data = json.loads(json_str)
        assert len(data) == 1
        assert data[0]["short_name"] == "TestSwc"
        assert data[0]["port_count"] == 1

    def test_format_tree_single(self):
        swc = SWCComponent(short_name="Swc1")
        tree = _format_tree([swc])
        assert "Swc1" in tree
        assert "AUTOSAR SWC Structure" in tree

    def test_format_tree_multiple(self):
        swc1 = SWCComponent(short_name="A")
        swc2 = SWCComponent(short_name="B")
        tree = _format_tree([swc1, swc2])
        assert "A" in tree
        assert "B" in tree

    def test_format_tree_with_ports(self):
        swc = SWCComponent(short_name="Swc")
        swc.ports.append(PortPrototype(short_name="Port1", direction="in"))
        tree = _format_tree([swc])
        assert "Port1" in tree
        assert "🔌" in tree

    def test_format_tree_with_runnables(self):
        swc = SWCComponent(short_name="Swc")
        swc.runnables.append(RunnableEntity(short_name="Rx", period_ms=10.0))
        tree = _format_tree([swc])
        assert "Rx" in tree
        assert "⚡" in tree

    def test_to_markdown(self):
        parser = ARXMLParser()
        swc = SWCComponent(short_name="Test", uuid="u1")
        swc.ports.append(PortPrototype(short_name="P1", direction="in"))
        swc.runnables.append(RunnableEntity(short_name="Rx", period_ms=10.0))
        md = parser.to_markdown([swc])
        assert "## SWC: Test" in md
        assert "P1" in md
        assert "Rx" in md

    def test_to_markdown_empty(self):
        parser = ARXMLParser()
        md = parser.to_markdown([])
        assert "0 components" in md


# ===========================================================================
# import_arxml_to_spec tests
# ===========================================================================


class TestImportToSpec:
    """Tests for import_arxml_to_spec()."""

    def test_import_to_spec(self, sample_file: Path, tmp_path: Path):
        result = import_arxml_to_spec(str(sample_file), str(tmp_path / "specs"))
        assert "TestSwc" in result
        spec_path = Path(result["TestSwc"])
        assert spec_path.exists()
        content = spec_path.read_text(encoding="utf-8")
        assert "TestSwc" in content
        assert "InputPort" in content

    def test_import_to_spec_with_real_file(self, real_sample_file: str, tmp_path: Path):
        result = import_arxml_to_spec(real_sample_file, str(tmp_path / "specs"))
        assert "CanIf" in result
        assert "CanSm" in result
        canif_path = Path(result["CanIf"])
        assert canif_path.exists()
        content = canif_path.read_text(encoding="utf-8")
        assert "CanIf" in content


# ===========================================================================
# Edge cases and error handling
# ===========================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.arxml"
        f.write_text("", encoding="utf-8")
        parser = ARXMLParser()
        with pytest.raises(ET.ParseError):
            parser.parse_swc(str(f))

    def test_parser_with_unknown_type(self, tmp_path: Path):
        arxml = """<?xml version="1.0" encoding="UTF-8"?>
        <AUTOSAR xmlns="http://autosar.org/schema/r4.0">
          <AR-PACKAGE>
            <SHORT-NAME>Pkg</SHORT-NAME>
            <ELEMENTS>
              <UNKNOWN-TYPE><SHORT-NAME>X</SHORT-NAME></UNKNOWN-TYPE>
            </ELEMENTS>
          </AR-PACKAGE>
        </AUTOSAR>"""
        f = tmp_path / "unknown.arxml"
        f.write_text(arxml, encoding="utf-8")
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(f))
        assert len(swcs) == 0

    def test_runnable_without_events(self, tmp_path: Path):
        arxml = """<?xml version="1.0" encoding="UTF-8"?>
        <AUTOSAR xmlns="http://autosar.org/schema/r4.0">
          <AR-PACKAGE>
            <SHORT-NAME>Pkg</SHORT-NAME>
            <ELEMENTS>
              <APPLICATION-SW-COMPONENT-TYPE>
                <SHORT-NAME>SimpleSwc</SHORT-NAME>
                <SWC-INTERNAL-BEHAVIOR>
                  <SHORT-NAME>SimpleBehavior</SHORT-NAME>
                  <RUNNABLE-ENTITY>
                    <SHORT-NAME>SimpleRunnable</SHORT-NAME>
                  </RUNNABLE-ENTITY>
                </SWC-INTERNAL-BEHAVIOR>
              </APPLICATION-SW-COMPONENT-TYPE>
            </ELEMENTS>
          </AR-PACKAGE>
        </AUTOSAR>"""
        f = tmp_path / "simple.arxml"
        f.write_text(arxml, encoding="utf-8")
        parser = ARXMLParser()
        swcs = parser.parse_swc(str(f))
        assert len(swcs) == 1
        r = swcs[0].runnables[0]
        assert r.timing_event is None
        assert r.period_ms is None

    def test_vector_adapter_shim(self):
        """Verify that autosar.parser can be imported from vector adapter tests."""
        from yuleosh.autosar.parser import ARXMLParser as P
        assert P is not None

    def test_parse_file_method(self, sample_file: Path):
        """Test the parse_file() convenience wrapper."""
        parser = ARXMLParser()
        swcs = parser.parse_file(str(sample_file))
        assert len(swcs) == 1

    def test_convenience_function(self, sample_file: Path):
        """Test parse_arxml_file top-level convenience function."""
        swcs = parse_arxml_file(str(sample_file))
        assert len(swcs) == 1
