"""Smoke tests for yuleosh.adapter — dSPACE and Vector CANoe adapters.

Tests basic import, class instantiation, and method invocation.
No external dependencies — all I/O mocked.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ======================================================================
# Test data
# ======================================================================

SAMPLE_TEST_CASES = [
    {
        "id": "TC_001",
        "title": "CAN Bus Communication",
        "group": "Smoke Tests",
        "type": "PASS",
        "description": "Verify CAN bus communication",
        "steps": [
            {"name": "Send CAN message", "expected": "ACK received"},
        ],
        "signals": [
            {"name": "CAN_Message_1", "id": 0x100, "type": "CAN", "cycle_ms": 100},
        ],
        "parameters": [
            {"name": "Gain", "value": 2.5, "unit": "V/V"},
        ],
    },
]


# ======================================================================
# yuleosh.adapter.__init__ — _indent, _XML_DECLARATION, get_adapter
# ======================================================================

class TestAdapterInit:
    def test_xml_declaration(self):
        from yuleosh.adapter import _XML_DECLARATION
        assert _XML_DECLARATION == '<?xml version="1.0" encoding="UTF-8"?>\n'

    def test_indent(self):
        from yuleosh.adapter import _indent
        import xml.etree.ElementTree as ET
        root = ET.Element("root")
        child = ET.SubElement(root, "child")
        _indent(root)
        # Should not crash
        assert root.tag == "root"

    def test_get_adapter_canoe(self):
        from yuleosh.adapter import get_adapter
        adapter = get_adapter("canoe")
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        assert isinstance(adapter, VectorCANoeAdapter)

    def test_get_adapter_automationdesk(self):
        from yuleosh.adapter import get_adapter
        adapter = get_adapter("automationdesk")
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        assert isinstance(adapter, DSAPCEAutomationDeskAdapter)

    def test_get_adapter_invalid(self):
        from yuleosh.adapter import get_adapter
        import pytest
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("unknown_adapter")


# ======================================================================
# yuleosh.adapter.dspace_adapter — DSAPCEAutomationDeskAdapter
# ======================================================================

class TestDSpaceAdapter:
    def test_import(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        assert DSAPCEAutomationDeskAdapter is not None

    def test_instantiate_default(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter()
        assert adapter is not None

    def test_instantiate_custom_namespace(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter(namespace="http://custom.ns")
        assert adapter is not None

    def test_generate_test_set(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter()
        result = adapter.generate_test_set(SAMPLE_TEST_CASES)
        assert isinstance(result, str)
        assert "TestSet" in result or "AutoDesk" in result
        assert len(result) > 0

    def test_generate_test_step(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter()
        element = adapter.generate_test_step(SAMPLE_TEST_CASES[0])
        assert element is not None

    def test_convert(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = adapter.convert(SAMPLE_TEST_CASES, tmpdir)
            assert isinstance(result, str)
            # Should result in at least one file path
            assert len(result.strip()) > 0

    def test_safe_filename(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        result = DSAPCEAutomationDeskAdapter._safe_filename("Hello World!")
        assert result == "Hello_World_"

    def test_generate_parameter_set(self):
        from yuleosh.adapter.dspace_adapter import DSAPCEAutomationDeskAdapter
        adapter = DSAPCEAutomationDeskAdapter()
        result = adapter.generate_parameter_set(SAMPLE_TEST_CASES[0])
        assert isinstance(result, str)


# ======================================================================
# yuleosh.adapter.vector_adapter — VectorCANoeAdapter
# ======================================================================

class TestVectorCanoeAdapter:
    def test_import(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        assert VectorCANoeAdapter is not None

    def test_instantiate_default(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter()
        assert adapter is not None

    def test_instantiate_custom_prefix(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter(prefix="custom")
        assert adapter is not None

    def test_generate_test_module(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter()
        xml_str = adapter.generate_test_module(SAMPLE_TEST_CASES)
        assert isinstance(xml_str, str)
        assert xml_str.startswith('<?xml')

    def test_convert(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = adapter.convert(SAMPLE_TEST_CASES, tmpdir)
            assert isinstance(result, str)
            assert len(result.strip()) > 0

    def test_generate_capl(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter()
        capl_code = adapter.generate_capl(SAMPLE_TEST_CASES[0])
        assert isinstance(capl_code, str)

    def test_generate_dbc_map(self):
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        adapter = VectorCANoeAdapter()
        signals = [{"name": "Speed", "id": 0x123, "type": "CAN", "cycle_ms": 100}]
        result = adapter.generate_dbc_map(signals)
        assert isinstance(result, str)
