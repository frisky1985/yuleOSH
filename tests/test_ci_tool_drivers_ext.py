"""
Extended tests for yuleosh.ci.tool_drivers — push coverage ≥ 60%.
"""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestBaseToolDriver:
    """Cover BaseToolDriver abstract class."""

    def test_config_property(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        driver = CppcheckDriver(project_dir="/tmp", config={"key": "val"})
        assert driver.config == {"key": "val"}
        # Config should be a copy
        cfg = driver.config
        cfg["new"] = "x"
        assert "new" not in driver.config

    def test_config_defaults_to_empty_dict(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        driver = CppcheckDriver(project_dir="/tmp")
        assert driver.config == {}

    def test_get_report_dir(self, tmp_path):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        driver = CppcheckDriver(project_dir=str(tmp_path))
        report_dir = driver.get_report_dir()
        assert str(tmp_path) in str(report_dir)
        assert ".yuleosh" in str(report_dir)
        assert "reports" in str(report_dir)

    def test_project_dir_resolved(self, tmp_path):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        # Use a path that exists so resolve() works
        path = tmp_path / "sub"
        path.mkdir()
        driver = CppcheckDriver(project_dir=str(path))
        assert str(path.resolve()) in str(driver._project_dir)


class TestCppcheckDriver:
    """Cover CppcheckDriver implementation."""

    def test_name(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        assert d.name == "cppcheck"

    def test_ruleset_none_by_default(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        assert d.ruleset is None

    def test_set_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        mock_ruleset = mock.Mock()
        mock_ruleset.name = "test-ruleset"
        d.set_ruleset(mock_ruleset)
        assert d.ruleset is not None

    def test_ruleset_init_via_config(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_ruleset = mock.Mock()
        mock_ruleset.name = "test-ruleset"
        d = CppcheckDriver(project_dir="/tmp", config={"ruleset": mock_ruleset})
        assert d.ruleset is not None

    def test_get_effective_config_no_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp", config={"addon": "misra-c2012"})
        cfg = d._get_effective_config()
        assert cfg["addon"] == "misra-c2012"

    def test_get_effective_config_with_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_ruleset = mock.Mock()
        mock_ruleset.get_tool_config.return_value = {"addon": "misra", "enable": "all"}
        d = CppcheckDriver(project_dir="/tmp", config={"ruleset": mock_ruleset, "enable": "style"})
        cfg = d._get_effective_config()
        # config takes priority
        assert cfg["enable"] == "style"
        # From ruleset
        assert cfg["addon"] == "misra"

    @mock.patch("subprocess.run")
    def test_run_file_target(self, mock_run):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        import tempfile as tf
        tmp = Path(tf.mkdtemp())
        src_file = tmp / "main.c"
        src_file.write_text("int main() { return 0; }")

        d = CppcheckDriver(project_dir=str(tmp))
        d.run(str(src_file))
        args = mock_run.call_args[0][0]
        assert "cppcheck" in args
        assert any("--addon" in a for a in args)
        assert "--recursive" not in args  # Not for files

    @mock.patch("subprocess.run")
    def test_run_directory_target(self, mock_run):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""

        import tempfile as tf
        tmp = Path(tf.mkdtemp())
        d = CppcheckDriver(project_dir=str(tmp))
        d.run(str(tmp))
        args = mock_run.call_args[0][0]
        assert "--recursive" in args

    def test_run_target_not_found(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        with pytest.raises(FileNotFoundError):
            d.run("/nonexistent/target.c")

    @mock.patch("subprocess.run")
    def test_run_cppcheck_not_found(self, mock_run):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_run.side_effect = FileNotFoundError("cppcheck not found")
        import tempfile as tf
        tmp = Path(tf.mkdtemp())
        src_file = tmp / "main.c"
        src_file.write_text("int main() { return 0; }")
        d = CppcheckDriver(project_dir=str(tmp))
        result = d.run(str(src_file))
        assert "error" in result

    @mock.patch("subprocess.run")
    def test_run_timeout(self, mock_run):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        from subprocess import TimeoutExpired
        mock_run.side_effect = TimeoutExpired("cppcheck", 300)
        import tempfile as tf
        tmp = Path(tf.mkdtemp())
        src_file = tmp / "main.c"
        src_file.write_text("int main() { return 0; }")
        d = CppcheckDriver(project_dir=str(tmp))
        result = d.run(str(src_file))
        assert "timed out" in result

    def test_parse(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        raw = '{"file":"main.c","line":1,"col":1,"severity":"error","message":"test","rule_id":"misra-c2023-17.7"}\n'
        result = d.parse(raw)
        assert isinstance(result, list)

    @mock.patch("yuleosh.ci.misra_report.load_rule_definitions")
    @mock.patch("yuleosh.ci.misra_report.group_by_rule")
    @mock.patch("yuleosh.ci.misra_report.enrich_with_definitions")
    @mock.patch("yuleosh.ci.misra_report.compute_summary_stats")
    @mock.patch("yuleosh.ci.misra_report.generate_json_report")
    def test_generate_report_no_ruleset(self, mock_gen, mock_summary,
                                         mock_enrich, mock_group, mock_load):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        d.generate_report([{"rule_id": "test"}])
        mock_load.assert_called_once()

    @mock.patch("yuleosh.ci.misra_report.generate_json_report")
    def test_generate_report_with_ruleset(self, mock_gen):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_ruleset = mock.Mock()
        mock_ruleset.rule_definitions.return_value = {"rules": {}}
        d = CppcheckDriver(project_dir="/tmp", config={"ruleset": mock_ruleset})
        d.generate_report([{"rule_id": "test"}])
        mock_ruleset.rule_definitions.assert_called_once()

    def test_get_rule_definitions_no_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        with mock.patch("yuleosh.ci.misra_report.load_rule_definitions") as m:
            m.return_value = {"rules": {}}
            result = d.get_rule_definitions()
            assert result == {"rules": {}}

    def test_get_rule_definitions_with_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_ruleset = mock.Mock()
        mock_ruleset.rule_definitions.return_value = {"rules": {"R1": {}}}
        d = CppcheckDriver(project_dir="/tmp", config={"ruleset": mock_ruleset})
        result = d.get_rule_definitions()
        assert result == {"rules": {"R1": {}}}

    def test_get_ruleset_info_no_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        d = CppcheckDriver(project_dir="/tmp")
        assert d.get_ruleset_info() is None

    def test_get_ruleset_info_with_ruleset(self):
        from yuleosh.ci.tool_drivers import CppcheckDriver
        mock_ruleset = mock.Mock()
        mock_ruleset.name = "test-rs"
        mock_ruleset.display_name = "Test Ruleset"
        mock_ruleset.supported_tools.return_value = ["cppcheck"]
        d = CppcheckDriver(project_dir="/tmp", config={"ruleset": mock_ruleset})
        info = d.get_ruleset_info()
        assert info["name"] == "test-rs"
        assert info["display_name"] == "Test Ruleset"


class TestClangTidyDriver:
    """Cover ClangTidyDriver stub."""

    def test_name(self):
        from yuleosh.ci.tool_drivers import ClangTidyDriver
        d = ClangTidyDriver(project_dir="/tmp")
        assert d.name == "clang-tidy"

    def test_parse_returns_empty(self):
        from yuleosh.ci.tool_drivers import ClangTidyDriver
        d = ClangTidyDriver(project_dir="/tmp")
        assert d.parse("any output") == []

    def test_run_returns_stub(self):
        from yuleosh.ci.tool_drivers import ClangTidyDriver
        d = ClangTidyDriver(project_dir="/tmp")
        result = d.run("/dev/null")
        assert "stub" in result

    def test_generate_report_structure(self):
        from yuleosh.ci.tool_drivers import ClangTidyDriver
        d = ClangTidyDriver(project_dir="/tmp")
        report = d.generate_report([{"id": "test"}])
        assert report["tool"] == "clang-tidy"
        assert report["status"] == "stub"
        assert report["total_violations"] == 1


class TestDriverFactory:
    """Cover create_driver, register_driver, list_drivers."""

    def test_create_cppcheck(self):
        from yuleosh.ci.tool_drivers import create_driver, CppcheckDriver
        d = create_driver("cppcheck", project_dir="/tmp")
        assert isinstance(d, CppcheckDriver)

    def test_create_clang_tidy(self):
        from yuleosh.ci.tool_drivers import create_driver, ClangTidyDriver
        d = create_driver("clang-tidy", project_dir="/tmp")
        assert isinstance(d, ClangTidyDriver)

    def test_create_unknown_raises(self):
        from yuleosh.ci.tool_drivers import create_driver
        with pytest.raises(ValueError, match="Unknown tool"):
            create_driver("unknown-tool", project_dir="/tmp")

    def test_create_with_ruleset(self):
        from yuleosh.ci.tool_drivers import create_driver
        mock_ruleset = mock.Mock()
        d = create_driver("cppcheck", project_dir="/tmp", ruleset=mock_ruleset)
        assert d._config.get("ruleset") is mock_ruleset

    def test_register_driver(self):
        from yuleosh.ci.tool_drivers import register_driver, list_drivers
        # Create a valid driver class
        from yuleosh.ci.tool_drivers import BaseToolDriver
        class FakeDriver(BaseToolDriver):
            @property
            def name(self): return "fake"
            def parse(self, raw): return []
            def run(self, target): return ""
            def generate_report(self, v): return {}
        register_driver("fake", FakeDriver)
        assert "fake" in list_drivers()

    def test_register_invalid_type(self):
        from yuleosh.ci.tool_drivers import register_driver
        with pytest.raises(TypeError):
            register_driver("bad", dict)

    def test_list_drivers(self):
        from yuleosh.ci.tool_drivers import list_drivers
        drivers = list_drivers()
        assert "cppcheck" in drivers
        assert "clang-tidy" in drivers
