"""Unit tests for yuleosh.pipeline.config_validator (v3.4.2 Wave 1).

Covers:
  - validate_pipeline_config(): JSON config parsing (modules list / enabled
    dict / invalid JSON), ARXML parsing, project-dir .yuleosh scanning,
    required-module checks, dependency checks, valid/invalid verdicts
  - _validate_arxml_syntax(): empty/prolog/root/closing/balance checks
  - _extract_arxml_modules(): ECUC + MODULE-REF patterns, dedupe
  - cli_validate(): file-not-found / read-error / valid / invalid exits
"""

# @tests src/yuleosh/pipeline/orchestrator.py

import json
import os
import sys
from pathlib import Path

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.pipeline.config_validator import (
    BSW_MODULE_DEPENDENCIES,
    REQUIRED_MODULES,
    validate_pipeline_config,
    _validate_arxml_syntax,
    _extract_arxml_modules,
    cli_validate,
)


MINIMAL_ARXML = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR>
  <ECUC-MODULE-CONFIGURATION>
    <SHORT-NAME>Can</SHORT-NAME>
  </ECUC-MODULE-CONFIGURATION>
  <ECUC-MODULE-CONFIGURATION>
    <SHORT-NAME>Mcu</SHORT-NAME>
  </ECUC-MODULE-CONFIGURATION>
</AUTOSAR>
"""

COMPLETE_JSON = json.dumps({
    "modules": [
        {"name": "Mcu", "enabled": True},
        {"name": "Port"},
        {"name": "Dio"},
        {"name": "Os"},
        {"module": "Can"},
        {"name": "CanIf"},
    ],
})


class TestValidatePipelineConfig:
    def test_empty_config_missing_required(self):
        """GIVEN no inputs WHEN validate THEN missing required modules."""
        r = validate_pipeline_config()
        assert r["valid"] is False
        assert any("Missing required module" in i for i in r["issues"])
        assert len(r["issues"]) == len(REQUIRED_MODULES)

    def test_complete_json_valid(self):
        """GIVEN full stack JSON WHEN validate THEN valid."""
        cfg = json.dumps({
            "modules": [
                {"name": m} for m in
                ["Mcu", "Port", "Dio", "Os", "Can", "CanIf", "Eth", "EthIf"]
            ],
        })
        r = validate_pipeline_config(config_json=cfg)
        assert r["valid"] is True
        assert r["issues"] == []
        assert set(REQUIRED_MODULES) <= set(r["modules_found"])

    def test_json_enabled_dict_form(self):
        """GIVEN {module: {enabled: true}} form WHEN validate THEN modules found."""
        cfg = json.dumps({"Can": {"enabled": True}, "Mcu": {"enabled": True},
                          "Port": {"enabled": True}, "Dio": {"enabled": True},
                          "Os": {"enabled": True}, "CanIf": {"enabled": True}})
        r = validate_pipeline_config(config_json=cfg)
        assert "Can" in r["modules_found"]
        assert r["valid"] is True

    def test_json_enabled_modules_list(self):
        """GIVEN enabled_modules list WHEN validate THEN added to found."""
        cfg = json.dumps({"modules": [{"name": "Mcu"}], "enabled_modules": ["Os"]})
        r = validate_pipeline_config(config_json=cfg)
        assert "Mcu" in r["modules_found"]
        assert "Os" in r["modules_found"]

    def test_json_parse_error(self):
        """GIVEN malformed JSON WHEN validate THEN parse issue reported."""
        r = validate_pipeline_config(config_json="{not json")
        assert r["valid"] is False
        assert any("JSON parse error" in i for i in r["issues"])

    def test_arxml_modules_extracted(self):
        """GIVEN ARXML with Can/Mcu WHEN validate THEN modules found + deps ok."""
        r = validate_pipeline_config(arxml_content=MINIMAL_ARXML)
        assert {"Can", "Mcu"} <= set(r["modules_found"])
        # missing Port/Dio/Os remain
        assert r["valid"] is False

    def test_dependency_missing(self):
        """GIVEN CanIf without Can WHEN validate THEN dependency issue."""
        cfg = json.dumps({
            "modules": [{"name": m} for m in ["Mcu", "Port", "Dio", "Os", "CanIf"]],
        })
        r = validate_pipeline_config(config_json=cfg)
        assert any("CanIf" in i and "Can" in i for i in r["issues"])

    def test_project_dir_scan_json_and_arxml(self, tmp_path):
        """GIVEN project dir with .yuleosh configs WHEN validate THEN modules found."""
        ydir = tmp_path / ".yuleosh"
        ydir.mkdir()
        (ydir / "cfg.json").write_text(json.dumps({
            "modules": ["Mcu", "Port", "Dio", "Os", "Can", "CanIf"],
        }))
        (ydir / "mcu.arxml").write_text(
            "<AUTOSAR><ECUC-MODULE-CONFIGURATION><SHORT-NAME>Eth"
            "</SHORT-NAME></ECUC-MODULE-CONFIGURATION></AUTOSAR>")
        r = validate_pipeline_config(project_dir=str(tmp_path))
        assert "Can" in r["modules_found"]
        assert "Eth" in r["modules_found"]
        assert r["project_dir"] == str(tmp_path)
        assert r["valid"] is True

    def test_project_dir_scan_bad_json_ignored(self, tmp_path):
        """GIVEN corrupt .yuleosh json WHEN validate THEN skipped w/o crash."""
        ydir = tmp_path / ".yuleosh"
        ydir.mkdir()
        (ydir / "bad.json").write_text("{corrupt")
        (ydir / "good.json").write_text(json.dumps({"modules": ["Mcu", "Port", "Dio", "Os"]}))
        r = validate_pipeline_config(project_dir=str(tmp_path))
        assert set(REQUIRED_MODULES) <= set(r["modules_found"])

    def test_project_dir_no_yuleosh(self, tmp_path):
        """GIVEN project dir without .yuleosh WHEN validate THEN required missing."""
        r = validate_pipeline_config(project_dir=str(tmp_path))
        assert r["valid"] is False
        assert len(r["issues"]) == len(REQUIRED_MODULES)


class TestValidateArxmlSyntax:
    def test_empty_content(self):
        """GIVEN empty ARXML WHEN validate THEN empty issue."""
        issues = _validate_arxml_syntax("")
        assert any("empty" in i for i in issues)

    def test_missing_prolog(self):
        """GIVEN no prolog WHEN validate THEN prolog issue."""
        issues = _validate_arxml_syntax("<AUTOSAR></AUTOSAR>")
        assert any("prolog" in i for i in issues)

    def test_missing_root(self):
        """GIVEN no AUTOSAR root WHEN validate THEN root issue."""
        issues = _validate_arxml_syntax('<?xml version="1.0"?><FOO/>')
        assert any("root" in i for i in issues)

    def test_missing_closing(self):
        """GIVEN no closing tag WHEN validate THEN closing issue."""
        issues = _validate_arxml_syntax('<?xml version="1.0"?><AUTOSAR>')
        assert any("closing" in i for i in issues)

    def test_unbalanced_module_tags(self):
        """GIVEN unbalanced ECUC tags WHEN validate THEN balance issue."""
        content = ('<?xml version="1.0"?><AUTOSAR>'
                   "<ECUC-MODULE-CONFIGURATION><SHORT-NAME>Can</SHORT-NAME>"
                   "</AUTOSAR>")
        issues = _validate_arxml_syntax(content)
        assert any("Unbalanced" in i for i in issues)

    def test_valid_arxml_no_issues(self):
        """GIVEN well-formed ARXML WHEN validate THEN no issues."""
        issues = _validate_arxml_syntax(MINIMAL_ARXML)
        assert issues == []


class TestExtractArxmlModules:
    def test_ecuc_configuration_pattern(self):
        """GIVEN ECUC blocks WHEN extract THEN module names captured."""
        modules = _extract_arxml_modules(MINIMAL_ARXML)
        assert set(modules) == {"Can", "Mcu"}

    def test_module_ref_pattern(self):
        """GIVEN MODULE-REF entries WHEN extract THEN basename captured."""
        content = ("<MODULE-REF>/AUTOSAR/EcucDefs/Can</MODULE-REF>"
                   "<MODULE-REF>Mcu</MODULE-REF>")
        modules = _extract_arxml_modules(content)
        assert "Can" in modules
        assert "Mcu" in modules

    def test_dedupes(self):
        """GIVEN repeated modules WHEN extract THEN unique list."""
        modules = _extract_arxml_modules(MINIMAL_ARXML + MINIMAL_ARXML)
        assert len(modules) == 2

    def test_empty_content(self):
        """GIVEN empty ARXML WHEN extract THEN []."""
        assert _extract_arxml_modules("") == []


class TestCliValidate:
    def test_json_file_not_found(self, tmp_path, capsys):
        """GIVEN missing --json file WHEN cli_validate THEN exit 1."""
        rc = cli_validate(["--json", str(tmp_path / "nope.json")])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_json_read_error(self, tmp_path, capsys):
        """GIVEN unreadable --json file WHEN cli_validate THEN exit 1."""
        d = tmp_path / "sub"
        d.mkdir()
        rc = cli_validate(["--json", str(d)])
        assert rc == 1
        assert "Error reading JSON" in capsys.readouterr().err

    def test_arxml_file_not_found(self, tmp_path, capsys):
        """GIVEN missing --arxml file WHEN cli_validate THEN exit 1."""
        rc = cli_validate(["--arxml", str(tmp_path / "nope.arxml")])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_valid_config_returns_0(self, tmp_path, capsys):
        """GIVEN valid JSON config WHEN cli_validate THEN exit 0 + report."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(COMPLETE_JSON)
        rc = cli_validate(["--json", str(cfg)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "VALID" in out

    def test_invalid_config_returns_1(self, tmp_path, capsys):
        """GIVEN invalid JSON config WHEN cli_validate THEN exit 1 + issues."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"modules": [{"name": "CanIf"}]}))
        rc = cli_validate(["--json", str(cfg)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "INVALID" in out
        assert "Issues:" in out

    def test_arxml_valid_path(self, tmp_path, capsys):
        """GIVEN ARXML path + json path WHEN cli_validate THEN exit 0."""
        arxml = tmp_path / "cfg.arxml"
        arxml.write_text(MINIMAL_ARXML)
        cfg = tmp_path / "cfg.json"
        cfg.write_text(COMPLETE_JSON)
        rc = cli_validate(["--arxml", str(arxml), "--json", str(cfg)])
        assert rc == 0
        assert "VALID" in capsys.readouterr().out

    def test_default_project_dir(self, tmp_path, capsys):
        """GIVEN no --project-dir WHEN cli_validate THEN defaults to cwd."""
        cfg = tmp_path / "cfg.json"
        cfg.write_text(COMPLETE_JSON)
        rc = cli_validate(["--json", str(cfg)])
        assert rc == 0


def test_dependency_table_sanity():
    """GIVEN dependency table THEN well-known chains present."""
    assert BSW_MODULE_DEPENDENCIES["CanIf"]["required"] == ["Can"]
    assert BSW_MODULE_DEPENDENCIES["Dcm"]["required"] == ["CanTp", "LinTp", "FrIf"]
    assert BSW_MODULE_DEPENDENCIES["Mcu"]["required"] == []
