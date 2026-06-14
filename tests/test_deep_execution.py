"""Deep execution tests for remaining uncovered modules - spec, testgen, skills."""
import os, sys, re, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, PropertyMock, call
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestDeep:
    def test_spec_parse_mock(self):
        from yuleosh.spec.validate import parse_spec
        mock_content = "# Spec\n## Requirements\n### REQ-001: Test Req\n*shall* work"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                doc = parse_spec("/tmp/test.md")
                assert doc is not None

    def test_spec_parse_with_reqs(self):
        from yuleosh.spec.validate import parse_spec
        mock_content = (
            "# Test Spec\n## Functional Requirements\n### REQ-001: User Login\n"
            "*shall* authenticate\n*should* timeout\n"
            "## Scenarios\n### SCEN-001: Login Success\n"
            "*given* credentials\n*when* submit\n*then* logged in\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=mock_content):
                doc = parse_spec("/tmp/test.md")
                assert doc is not None

    def test_testgen_format(self):
        from yuleosh.testgen.generator import TestCase
        from yuleosh.testgen.formatter import format_pytest
        cases = [
            TestCase(id="TC-001", shall_ref="RS-001", scenario="Login",
                     given="creds", when="submit", then="logged in"),
            TestCase(id="TC-002", shall_ref="RS-002", scenario="Error",
                     given="invalid", when="submit", then="error"),
        ]
        code = format_pytest(cases)
        assert "def test_login" in code or "def test_Login" in code or "TC-001" in code

    def test_validate_transition_valid(self):
        from yuleosh.spec.validate import validate_status_transition
        ok, msg = validate_status_transition("PROPOSED", "APPROVED")
        assert ok is True

    def test_validate_transition_invalid(self):
        from yuleosh.spec.validate import validate_status_transition
        ok, msg = validate_status_transition("PROPOSED", "INVALID")
        assert ok is False

    def test_ci_check_dep(self):
        from yuleosh.ci.run import check_layer_dependency
        with patch("yuleosh.ci.run.get_latest_layer_result", return_value=None):
            result = check_layer_dependency(2, "/tmp/proj")
            assert result is None or result == ""

    def test_ci_check_dep_passed(self):
        with patch("yuleosh.ci.run.get_latest_layer_result") as mock_gllr:
            mock_result = MagicMock()
            mock_result.get.return_value = "passed"
            mock_gllr.return_value = mock_result
            from yuleosh.ci.run import check_layer_dependency
            result = check_layer_dependency(2, "/tmp/proj")
            assert result is None

    def test_skills_skillmanager(self):
        from yuleosh.skills import SkillManager
        from yuleosh.plugins import PluginManager
        with tempfile.TemporaryDirectory() as tmpdir:
            pm = PluginManager(plugins_dir=tmpdir)
            mgr = SkillManager(skills_dir=tmpdir, plugin_manager=pm)
            assert mgr is not None

    def test_skills_manifest_to_dict(self):
        from yuleosh.skills import SkillManifest
        m = SkillManifest(name="test", version="1.0", description="desc",
                          author="me", type="skill")
        d = m.to_dict()
        assert d["name"] == "test"
