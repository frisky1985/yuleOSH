"""Focused execution tests for spec/validate and core modules."""
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestSpecParseExecution:
    def test_spec_parse_basic(self):
        from yuleosh.spec.validate import parse_spec
        content = "# Test\n## Requirements\n### REQ-001: Login\n*shall* work"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                doc = parse_spec("/tmp/test.md")
                assert doc is not None
                assert doc.path == "/tmp/test.md"

    def test_spec_parse_full(self):
        from yuleosh.spec.validate import parse_spec
        content = (
            "# Full Spec\n"
            "## Functional Requirements\n"
            "### REQ-001: User Login\n"
            "*shall* authenticate user with valid credentials\n"
            "*should* lock after 5 attempts\n"
            "*may* support biometric\n"
            "**reason** Security requirement\n"
            "## Scenarios\n"
            "### SCEN-001: Successful Login\n"
            "*given* user has valid credentials\n"
            "*when* user submits login form\n"
            "*then* user is redirected to dashboard\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                doc = parse_spec("/tmp/test.md")
                req = doc.requirements[0]
                assert req.name == "User Login"
                assert "authenticate" in " ".join(req.shall)

    def test_spec_validate_empty(self):
        from yuleosh.spec.validate import validate_spec, SpecDocument
        doc = SpecDocument(path="/tmp/test.md")
        issues = validate_spec(doc)
        assert isinstance(issues, list)

    def test_spec_parse_multi_req(self):
        from yuleosh.spec.validate import parse_spec
        content = (
            "# Multi Req\n"
            "## Requirements\n"
            "### REQ-001: First\n*shall* work\n"
            "### REQ-002: Second\n*shall* also work\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                doc = parse_spec("/tmp/test.md")
                assert len(doc.requirements) >= 2

    def test_spec_parse_empty_line_handling(self):
        from yuleosh.spec.validate import parse_spec
        content = "# Empty Handling\n\n## Requirements\n\n### REQ-001: Demo\n\n*shall* work\n\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                doc = parse_spec("/tmp/test.md")
                assert len(doc.requirements) >= 1


class TestSkillsExecute:
    def test_skill_manifest_full(self):
        from yuleosh.skills import SkillManifest
        m = SkillManifest(
            name="test-skill", version="1.0.0", description="A test skill",
            author="tester", type="workflow",
            dependencies={"core": ">=1.0"},
            tags=["test", "demo"],
            icon="test-icon",
        )
        d = m.to_dict()
        assert d["name"] == "test-skill"
        assert d["type"] == "workflow"

    def test_workflow_no_steps(self):
        from yuleosh.skills import Workflow
        wf = Workflow(version="1.0", steps=[])
        assert wf.version == "1.0"
        assert wf.steps == []
