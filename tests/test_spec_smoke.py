"""Smoke tests for yuleosh.spec.validate — spec parser and validator."""
import os, sys, re
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestSpecValidate:
    def test_import(self):
        from yuleosh.spec.validate import (
            parse_spec, validate_spec, diff_specs
        )
        assert callable(parse_spec)

    def test_import_classes(self):
        from yuleosh.spec.validate import (
            SpecDocument, SpecRequirement, SpecScenario
        )
        assert SpecRequirement is not None
        assert SpecScenario is not None

    def test_spec_requirement_create(self):
        from yuleosh.spec.validate import SpecRequirement
        r = SpecRequirement(name="Test Req", shall=["must work"],
                            should=[], may=[], reason="testing")
        assert r.name == "Test Req"

    def test_spec_scenario_create(self):
        from yuleosh.spec.validate import SpecScenario
        s = SpecScenario(name="Test Scenario", given=["system ready"],
                         when=["trigger"], then=["response"])
        assert s.name == "Test Scenario"

    def test_spec_document_create(self):
        from yuleosh.spec.validate import SpecDocument
        doc = SpecDocument(path="/tmp/test.md")
        assert doc.path == "/tmp/test.md"

    def test_parse_spec_not_found(self):
        from yuleosh.spec.validate import parse_spec
        with patch("pathlib.Path.exists", return_value=False):
            import pytest
            with pytest.raises(FileNotFoundError):
                parse_spec("/nonexistent.md")

    def test_valid_status_transitions(self):
        from yuleosh.spec.validate import VALID_STATUS_TRANSITIONS
        assert isinstance(VALID_STATUS_TRANSITIONS, dict)
        assert "PROPOSED" in VALID_STATUS_TRANSITIONS

    def test_id_pattern(self):
        from yuleosh.spec.validate import ID_PATTERN
        assert isinstance(ID_PATTERN, re.Pattern)
        assert ID_PATTERN.match("RS-001") is not None
        assert ID_PATTERN.match("SWR-42") is not None

    def test_allowed_statuses(self):
        from yuleosh.spec.validate import ALLOWED_STATUSES
        assert isinstance(ALLOWED_STATUSES, tuple)
