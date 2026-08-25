"""Unit tests for yuleosh.cli.commands.template — template listing (v3.4.2 Wave 1).

Covers:
  - ensure_osh_home(): creates OSH_HOME directory
  - cmd_template_list(): missing dir, empty dir, populated dir with descriptions
  - cmd_ecu_template_list(): missing dir, populated dir
"""

# @tests src/yuleosh/cli/main.py

import json
import os
import sys
from pathlib import Path

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.cli.commands import template as tpl_mod


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point module-level OSH_HOME at a temp dir and return helpers."""
    osh_home = tmp_path / "osh_home"
    monkeypatch.setattr(tpl_mod, "OSH_HOME", str(osh_home))
    return tmp_path, osh_home


def _add_project_template(osh_home: Path, name: str, desc: str = "") -> None:
    d = osh_home / "templates" / "project" / name
    d.mkdir(parents=True)
    if desc:
        (d / "template.json").write_text(json.dumps({"description": desc}))


class TestEnsureOshHome:
    def test_creates_directory(self, env):
        """GIVEN missing OSH_HOME WHEN ensure_osh_home THEN dir created."""
        tmp_path, osh_home = env
        assert not osh_home.exists()
        tpl_mod.ensure_osh_home()
        assert osh_home.is_dir()

    def test_idempotent(self, env):
        """GIVEN existing OSH_HOME WHEN ensure_osh_home THEN no error."""
        tmp_path, osh_home = env
        osh_home.mkdir()
        tpl_mod.ensure_osh_home()
        assert osh_home.is_dir()


class TestCmdTemplateList:
    def test_missing_dir_prints_notice(self, env, capsys):
        """GIVEN no templates dir WHEN list THEN notice printed."""
        tmp_path, osh_home = env
        tpl_mod.cmd_template_list()
        assert "No templates found." in capsys.readouterr().out

    def test_empty_dir_prints_header(self, env, capsys):
        """GIVEN empty templates dir WHEN list THEN header only."""
        tmp_path, osh_home = env
        (osh_home / "templates" / "project").mkdir(parents=True)
        tpl_mod.cmd_template_list()
        out = capsys.readouterr().out
        assert "Available templates:" in out
        assert "No templates found." not in out

    def test_lists_templates_with_description(self, env, capsys):
        """GIVEN templates with metadata WHEN list THEN name + description."""
        tmp_path, osh_home = env
        _add_project_template(osh_home, "brake_ecu", "Brake ECU demo")
        _add_project_template(osh_home, "body_ecu", "Body control")
        tpl_mod.cmd_template_list()
        out = capsys.readouterr().out
        assert "brake_ecu" in out and "Brake ECU demo" in out
        assert "body_ecu" in out and "Body control" in out

    def test_lists_template_without_description(self, env, capsys):
        """GIVEN template without metadata WHEN list THEN name + empty desc."""
        tmp_path, osh_home = env
        _add_project_template(osh_home, "plain_tpl")
        tpl_mod.cmd_template_list()
        assert "plain_tpl" in capsys.readouterr().out

    def test_sorted_order(self, env, capsys):
        """GIVEN unsorted template dirs WHEN list THEN sorted output."""
        tmp_path, osh_home = env
        _add_project_template(osh_home, "zebra")
        _add_project_template(osh_home, "alpha")
        tpl_mod.cmd_template_list()
        out = capsys.readouterr().out
        assert out.index("alpha") < out.index("zebra")


class TestCmdEcuTemplateList:
    def test_missing_dir_prints_notice(self, env, capsys):
        """GIVEN no ECU templates dir WHEN list THEN notice."""
        tmp_path, osh_home = env
        tpl_mod.cmd_ecu_template_list()
        assert "No ECU templates found." in capsys.readouterr().out

    def test_lists_ecu_templates(self, env, capsys):
        """GIVEN ECU templates WHEN list THEN names listed."""
        tmp_path, osh_home = env
        d = osh_home / "templates" / "ecu" / "tc397"
        d.mkdir(parents=True)
        tpl_mod.cmd_ecu_template_list()
        out = capsys.readouterr().out
        assert "Available ECU templates:" in out
        assert "tc397" in out
