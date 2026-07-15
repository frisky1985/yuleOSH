# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for autosar/cli.py — format helpers, command handler, spec import."""

import json
import sys
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch, PropertyMock

import pytest

from yuleosh.autosar.cli import (
    register_cli,
    _format_json,
    _format_tree,
    _handle_arxml_command,
    import_arxml_to_spec,
)
from yuleosh.autosar.models import SWCComponent, PortPrototype, RunnableEntity


# ══════════════════════════════════════════════════════════════════════════
# Fixtures: sample SWC components
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_swcs():
    ports = [
        PortPrototype(
            short_name="PortA",
            kind="SenderReceiverInterface",
            direction="out",
            interface_ref="/pkg/PortA",
        ),
        PortPrototype(
            short_name="PortB",
            kind="ClientServerInterface",
            direction="in",
            interface_ref="/pkg/PortB",
        ),
    ]
    runnables = [
        RunnableEntity(
            short_name="Runnable1",
            symbol="Runnable1_func",
            period_ms=10,
            timing_event="Periodic",
            data_read_access=["PortA"],
            data_write_access=["PortB"],
        ),
        RunnableEntity(
            short_name="Runnable2",
            symbol="Runnable2_func",
            period_ms=None,
            timing_event=None,
            data_read_access=[],
            data_write_access=[],
        ),
    ]
    swc1 = SWCComponent(
        short_name="MySWC",
        uuid="1234-5678",
        component_type="ApplicationSwComponentType",
        arxml_file="/path/to/file.arxml",
        ports=ports,
        runnables=runnables,
    )
    swc2 = SWCComponent(
        short_name="EmptySWC",
        uuid="8765-4321",
        component_type="CompositionSwComponentType",
        arxml_file="/path/to/file.arxml",
        ports=[],
        runnables=[],
    )
    return [swc1, swc2]


# ══════════════════════════════════════════════════════════════════════════
# _format_json
# ══════════════════════════════════════════════════════════════════════════

class TestFormatJson:
    def test_swc_with_ports_and_runnables(self, sample_swcs):
        result = _format_json(sample_swcs)
        data = json.loads(result)
        assert len(data) == 2

        # Check first SWC
        swc1 = data[0]
        assert swc1["short_name"] == "MySWC"
        assert swc1["uuid"] == "1234-5678"
        assert swc1["component_type"] == "ApplicationSwComponentType"
        assert len(swc1["ports"]) == 2
        assert swc1["ports"][0]["short_name"] == "PortA"
        assert swc1["ports"][0]["direction"] == "out"
        assert len(swc1["runnables"]) == 2
        assert swc1["runnables"][0]["symbol"] == "Runnable1_func"
        assert swc1["runnables"][0]["period_ms"] == 10
        assert swc1["port_count"] == 2
        assert swc1["runnable_count"] == 2

        # Check second SWC (empty)
        swc2 = data[1]
        assert swc2["short_name"] == "EmptySWC"
        assert swc2["ports"] == []
        assert swc2["runnables"] == []
        assert swc2["port_count"] == 0
        assert swc2["runnable_count"] == 0

    def test_empty_list(self):
        result = _format_json([])
        assert json.loads(result) == []


# ══════════════════════════════════════════════════════════════════════════
# _format_tree
# ══════════════════════════════════════════════════════════════════════════

class TestFormatTree:
    def test_multiple_swcs(self, sample_swcs):
        result = _format_tree(sample_swcs)
        assert "AUTOSAR SWC Structure" in result
        assert "MySWC" in result
        assert "ApplicationSwComponentType" in result
        assert "EmptySWC" in result
        assert "CompositionSwComponentType" in result
        # Ports
        assert "PortA" in result
        assert "[out]" in result
        # Runnables
        assert "Runnable1" in result
        assert "(10ms)" in result
        assert "Runnable2" in result  # no period → no "(Nms)"

    def test_single_swc(self):
        swc = SWCComponent(
            short_name="Single",
            uuid="",
            component_type="ApplicationSwComponentType",
            arxml_file="",
            ports=[],
            runnables=[],
        )
        result = _format_tree([swc])
        assert "└──" in result  # last item uses └──
        assert "Single" in result

    def test_empty_list(self):
        result = _format_tree([])
        assert "AUTOSAR SWC Structure" in result


# ══════════════════════════════════════════════════════════════════════════
# _handle_arxml_command
# ══════════════════════════════════════════════════════════════════════════

class TestHandleArxmlCommand:
    def test_file_not_found(self, capsys):
        """When file doesn't exist, print error and exit(1)."""
        args = MagicMock()
        args.file = "/nonexistent/file.arxml"
        args.verbose = False
        args.swc = ""
        args.format = "markdown"
        args.output = ""

        with pytest.raises(SystemExit) as exc:
            _handle_arxml_command(args)
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Error: file not found" in captured.err

    def test_parse_error(self, tmp_path: Path, capsys):
        """When ARXMLParser raises, print error and exit(1)."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<invalid-xml")

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = False
        args.swc = ""
        args.format = "markdown"
        args.output = ""

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.side_effect = ValueError("Parse error: invalid format")
            MockParser.return_value = mock_parser

            with pytest.raises(SystemExit) as exc:
                _handle_arxml_command(args)
            assert exc.value.code == 1
            captured = capsys.readouterr()
            assert "Error parsing ARXML" in captured.err

    def test_swc_not_found_filter(self, tmp_path: Path, capsys):
        """Filter for non-existent SWC name."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<dummy>")

        swc1 = SWCComponent(short_name="RealSWC", uuid="u1", component_type="App",
                            arxml_file="", ports=[], runnables=[])

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = False
        args.swc = "NonExistent"
        args.format = "markdown"
        args.output = ""

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = [swc1]
            MockParser.return_value = mock_parser

            with pytest.raises(SystemExit) as exc:
                _handle_arxml_command(args)
            assert exc.value.code == 1
            captured = capsys.readouterr()
            assert "NonExistent" in captured.err

    def test_swc_filter_success(self, tmp_path: Path):
        """Filter by SWC short_name works."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<dummy>")

        swcs = [
            SWCComponent(short_name="TargetSWC", uuid="u1", component_type="App",
                         arxml_file="", ports=[], runnables=[]),
            SWCComponent(short_name="OtherSWC", uuid="u2", component_type="App",
                         arxml_file="", ports=[], runnables=[]),
        ]

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = False
        args.swc = "TargetSWC"
        args.format = "markdown"
        args.output = ""

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = swcs
            mock_parser.to_markdown.return_value = "# TargetSWC spec"
            MockParser.return_value = mock_parser

            _handle_arxml_command(args)
            # Should have only passed the filtered SWC to to_markdown
            filtered_swcs = mock_parser.to_markdown.call_args[0][0]
            assert len(filtered_swcs) == 1
            assert filtered_swcs[0].short_name == "TargetSWC"

    def test_json_output_to_stdout(self, tmp_path: Path, capsys):
        """Json format writes to stdout."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<dummy>")

        swc = SWCComponent(short_name="MySWC", uuid="u1", component_type="App",
                           arxml_file="", ports=[], runnables=[])

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = False
        args.swc = ""
        args.format = "json"
        args.output = ""

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = [swc]
            MockParser.return_value = mock_parser

            _handle_arxml_command(args)
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data[0]["short_name"] == "MySWC"

    def test_tree_output_to_file(self, tmp_path: Path):
        """Tree format writes to a file."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<dummy>")

        swc = SWCComponent(short_name="MySWC", uuid="u1", component_type="App",
                           arxml_file="", ports=[], runnables=[])

        output_file = tmp_path / "output.txt"

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = False
        args.swc = ""
        args.format = "tree"
        args.output = str(output_file)

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = [swc]
            MockParser.return_value = mock_parser

            _handle_arxml_command(args)
            assert output_file.exists()
            content = output_file.read_text()
            assert "MySWC" in content

    def test_verbose_mode(self, tmp_path: Path):
        """Verbose flag sets logging level."""
        arxml_file = tmp_path / "test.arxml"
        arxml_file.write_text("<dummy>")

        swc = SWCComponent(short_name="MySWC", uuid="u1", component_type="App",
                           arxml_file="", ports=[], runnables=[])

        args = MagicMock()
        args.file = str(arxml_file)
        args.verbose = True
        args.swc = ""
        args.format = "markdown"
        args.output = ""

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = [swc]
            mock_parser.to_markdown.return_value = "# spec"
            MockParser.return_value = mock_parser

            with patch("yuleosh.autosar.cli.logging.getLogger") as mock_logger:
                logger = MagicMock()
                mock_logger.return_value = logger
                _handle_arxml_command(args)
                logger.setLevel.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# register_cli
# ══════════════════════════════════════════════════════════════════════════

class TestRegisterCli:
    def test_registers_subcommand(self):
        subparsers = MagicMock()
        register_cli(subparsers)
        subparsers.add_parser.assert_called_once_with(
            "arxml",
            help=ANY,
            description=ANY,
        )


# ══════════════════════════════════════════════════════════════════════════
# import_arxml_to_spec
# ══════════════════════════════════════════════════════════════════════════

class TestImportArxmlToSpec:
    def test_creates_spec_files(self, tmp_path: Path):
        arxml_file = tmp_path / "input.arxml"
        arxml_file.write_text("<dummy>")
        output_dir = tmp_path / "specs"

        swcs = [
            SWCComponent(short_name="MySWC", uuid="u1", component_type="App",
                         arxml_file="", ports=[], runnables=[]),
            SWCComponent(short_name="OtherSWC", uuid="u2", component_type="App",
                         arxml_file="", ports=[], runnables=[]),
        ]

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = swcs

            def to_markdown_side(swc_list):
                return f"# {swc_list[0].short_name} spec"
            mock_parser.to_markdown.side_effect = to_markdown_side
            MockParser.return_value = mock_parser

            result = import_arxml_to_spec(str(arxml_file), str(output_dir))

            assert len(result) == 2
            assert "MySWC" in result
            assert "OtherSWC" in result
            assert (output_dir / "myswc-spec.md").exists()
            assert (output_dir / "otherswc-spec.md").exists()

    def test_creates_output_dir(self, tmp_path: Path):
        """Output directory should be created automatically."""
        arxml_file = tmp_path / "input.arxml"
        arxml_file.write_text("<dummy>")
        output_dir = tmp_path / "new" / "specs"

        swc = SWCComponent(short_name="TestSWC", uuid="u1", component_type="App",
                           arxml_file="", ports=[], runnables=[])

        with patch("yuleosh.autosar.cli.ARXMLParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_swc.return_value = [swc]
            mock_parser.to_markdown.return_value = "# Test spec"
            MockParser.return_value = mock_parser

            result = import_arxml_to_spec(str(arxml_file), str(output_dir))
            assert output_dir.exists()
            assert len(result) == 1
