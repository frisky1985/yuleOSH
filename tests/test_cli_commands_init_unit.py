"""Unit tests for yuleosh.cli.commands.init — cmd_template_init (v3.4.2 Wave 1).

Covers:
  - Existing target directory → SystemExit
  - Missing templates dir → SystemExit
  - Empty templates dir → SystemExit
  - Auto-pick first template when template_name is None
  - Unknown template name → SystemExit
  - Successful copy with template.json variable substitution
  - Successful copy without template.json (no metadata)
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from yuleosh.cli.commands import init as init_mod


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Fixture: point module-level OSH_HOME at a temp dir."""
    osh_home = tmp_path / "osh_home"
    monkeypatch.setattr(init_mod, "OSH_HOME", str(osh_home))
    return tmp_path, osh_home


def _make_template(osh_home: Path, name: str, with_meta: bool = True,
                   description: str = "Demo template") -> Path:
    """Create a project template dir with a sample file."""
    tpl = osh_home / "templates" / "project" / name
    tpl.mkdir(parents=True)
    src = tpl / "src"
    src.mkdir()
    (src / "main.c").write_text("// {{PROJECT_NAME}} {{PROJECT_DESC}}\n")
    if with_meta:
        (tpl / "template.json").write_text(json.dumps({"description": description}))
    return tpl


class TestCmdTemplateInit:
    def test_target_exists_exits(self, env, capsys):
        """GIVEN existing project dir WHEN init THEN SystemExit + error msg."""
        tmp_path, osh_home = env
        (tmp_path / "proj").mkdir()
        with pytest.raises(SystemExit) as exc:
            init_mod.cmd_template_init("proj", parent_dir=str(tmp_path))
        assert exc.value.code == 1
        assert "already exists" in capsys.readouterr().out

    def test_no_templates_dir_exits(self, env, capsys):
        """GIVEN missing templates dir WHEN init THEN SystemExit."""
        tmp_path, osh_home = env
        with pytest.raises(SystemExit) as exc:
            init_mod.cmd_template_init("proj", parent_dir=str(tmp_path))
        assert exc.value.code == 1
        assert "No templates available" in capsys.readouterr().out

    def test_empty_templates_dir_exits(self, env, capsys):
        """GIVEN empty templates dir WHEN init THEN SystemExit."""
        tmp_path, osh_home = env
        (osh_home / "templates" / "project").mkdir(parents=True)
        with pytest.raises(SystemExit) as exc:
            init_mod.cmd_template_init("proj", parent_dir=str(tmp_path))
        assert exc.value.code == 1
        assert "No templates found" in capsys.readouterr().out

    def test_unknown_template_exits(self, env, capsys):
        """GIVEN requested template missing WHEN init THEN SystemExit."""
        tmp_path, osh_home = env
        _make_template(osh_home, "basic")
        with pytest.raises(SystemExit) as exc:
            init_mod.cmd_template_init("proj", parent_dir=str(tmp_path),
                                       template_name="ghost")
        assert exc.value.code == 1
        assert "not found" in capsys.readouterr().out

    def test_auto_pick_first_template(self, env, capsys):
        """GIVEN no template_name WHEN init THEN first dir used + message."""
        tmp_path, osh_home = env
        _make_template(osh_home, "first_tpl", with_meta=False)
        _make_template(osh_home, "second_tpl", with_meta=False)
        init_mod.cmd_template_init("proj", parent_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert "Using template: first_tpl" in out
        assert "Created project proj from template first_tpl" in out
        assert (tmp_path / "proj" / "src" / "main.c").exists()

    def test_copy_with_variable_substitution(self, env, capsys):
        """GIVEN template with template.json WHEN init THEN vars replaced."""
        tmp_path, osh_home = env
        _make_template(osh_home, "basic", description="Brake ECU")
        init_mod.cmd_template_init("proj", parent_dir=str(tmp_path),
                                   template_name="basic")
        content = (tmp_path / "proj" / "src" / "main.c").read_text()
        assert "{{PROJECT_NAME}}" not in content
        assert "proj" in content
        assert "Brake ECU" in content
        assert "Created project proj from template basic" in capsys.readouterr().out

    def test_copy_without_metadata(self, env, capsys):
        """GIVEN template without template.json WHEN init THEN files copied raw."""
        tmp_path, osh_home = env
        _make_template(osh_home, "plain", with_meta=False)
        init_mod.cmd_template_init("proj", parent_dir=str(tmp_path),
                                   template_name="plain")
        content = (tmp_path / "proj" / "src" / "main.c").read_text()
        # placeholder remains (no metadata to substitute)
        assert "{{PROJECT_NAME}}" in content
        assert "Created project proj from template plain" in capsys.readouterr().out
