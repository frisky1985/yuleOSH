# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for cli/template.py — template init, from-template, main().

Target: 80%+ branch coverage.
Covers: cmd_template_init, _init_starter, _init_from_template, main().
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


# ======================================================================
# cmd_template_init
# ======================================================================

class TestCmdTemplateInit:
    """GIVEN cmd_template_init WHEN called THEN scaffolds project."""

    def test_starter_basic(self):
        """GIVEN project name WHEN init without template THEN starter created."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            result = cmd_template_init("my-project", parent_dir=tmp)
            assert result.exists()
            assert (result / "docs" / "spec.md").exists()
            assert (result / "src" / "__init__.py").exists()
            assert (result / "tests" / "__init__.py").exists()
            assert (result / "pyproject.toml").exists()
            assert (result / ".gitignore").exists()
            spec = (result / "docs" / "spec.md").read_text()
            assert "SHALL" in spec
            assert "my-project" in spec

    def test_relative_from_template(self):
        """GIVEN --from relative path WHEN template dir found THEN copied."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            # Create a template dir inside tmp
            tmpl = Path(tmp) / "mytemplate"
            tmpl.mkdir()
            (tmpl / "README.md").write_text("template readme")
            (tmpl / "src").mkdir()
            (tmpl / "src" / "main.c").write_text("int main(){}")
            # Create a subdir for template init inside tmp
            result = cmd_template_init("proj-from-rel", parent_dir=tmp, from_template="mytemplate")
            assert result.exists()
            assert (result / "README.md").exists()
            assert (result / "src" / "main.c").exists()

    def test_from_template_absolute_path(self):
        """GIVEN --from absolute path WHEN template dir found THEN copied."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            tmpl = Path(tmp) / "abs_template"
            tmpl.mkdir()
            (tmpl / "config.yaml").write_text("key: value")
            result = cmd_template_init("proj-abs", parent_dir=tmp, from_template=str(tmpl))
            assert result.exists()
            assert (result / "config.yaml").exists()

    def test_from_template_osh_home_fallback(self):
        """GIVEN --from not found locally WHEN OSH_HOME set THEN checks there."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            osh_home = Path(tmp) / ".osh"
            osh_home.mkdir()
            tmpl = osh_home / "remote_template"
            tmpl.mkdir()
            (tmpl / "remote.yaml").write_text("remote: true")
            with patch.dict(os.environ, {"OSH_HOME": str(osh_home)}):
                result = cmd_template_init(
                    "proj-osh", parent_dir=tmp, from_template="remote_template"
                )
                assert result.exists()
                assert (result / "remote.yaml").exists()

    def test_existing_directory(self):
        """GIVEN existing project dir WHEN init THEN sys.exit(1)."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            existing = Path(tmp) / "existing_proj"
            existing.mkdir()
            with pytest.raises(SystemExit) as exc:
                cmd_template_init("existing_proj", parent_dir=tmp)
            assert exc.value.code == 1

    def test_template_not_found(self):
        """GIVEN nonexistent --from template WHEN init THEN sys.exit(1)."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit) as exc:
                cmd_template_init("proj", parent_dir=tmp, from_template="/nonexistent/path")
            assert exc.value.code == 1

    def test_template_removes_stale_dirs(self):
        """GIVEN template with stale dirs WHEN init THEN they are removed."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            tmpl = Path(tmp) / "source_tmpl"
            tmpl.mkdir()
            (tmpl / ".git").mkdir()
            (tmpl / "__pycache__").mkdir()
            (tmpl / ".pytest_cache").mkdir()
            (tmpl / "build").mkdir()
            (tmpl / "keep.txt").write_text("keep")
            result = cmd_template_init("clean-proj", parent_dir=tmp, from_template=str(tmpl))
            assert (result / "keep.txt").exists()
            assert not (result / ".git").exists()
            assert not (result / "__pycache__").exists()
            assert not (result / ".pytest_cache").exists()
            assert not (result / "build").exists()

    def test_starter_creates_placeholder_test(self):
        """GIVEN starter init WHEN done THEN placeholder test file created."""
        from yuleosh.cli.template import cmd_template_init
        with tempfile.TemporaryDirectory() as tmp:
            result = cmd_template_init("test-proj", parent_dir=tmp)
            test_files = list((result / "tests").iterdir())
            test_content = (result / "tests" / "test_test-proj.py").read_text()
            assert "def test_placeholder" in test_content
            assert "assert True" in test_content


# ======================================================================
# main()
# ======================================================================

class TestMain:
    """GIVEN template.py main() WHEN run THEN dispatches correctly."""

    def test_main_init(self):
        """GIVEN sys.argv=['prog','init','name'] WHEN main THEN calls init."""
        from yuleosh.cli.template import main as tmpl_main
        with tempfile.TemporaryDirectory() as tmp:
            testargs = ["template.py", "init", "test-from-main"]
            with patch.object(sys, "argv", testargs):
                with patch.object(sys, "exit") as mock_exit:
                    with patch("yuleosh.cli.template.cmd_template_init") as mock_init:
                        mock_init.return_value = Path(tmp) / "test-from-main"
                        tmpl_main()
                        mock_init.assert_called_once()

    def test_main_init_with_from(self):
        """GIVEN sys.argv with --from flag WHEN main THEN parses it."""
        from yuleosh.cli.template import main as tmpl_main
        with tempfile.TemporaryDirectory() as tmp:
            testargs = ["template.py", "init", "myproj", "--from", "/some/template"]
            with patch.object(sys, "argv", testargs):
                with patch.object(sys, "exit") as mock_exit:
                    with patch("yuleosh.cli.template.cmd_template_init") as mock_init:
                        mock_init.return_value = Path(tmp) / "myproj"
                        tmpl_main()
                        # Should call with from_template="/some/template"
                        mock_init.assert_called_once_with("myproj", from_template="/some/template")

    def test_main_no_args(self):
        """GIVEN sys.argv=['prog'] WHEN main THEN exit(1)."""
        from yuleosh.cli.template import main as tmpl_main
        with patch.object(sys, "argv", ["template.py"]):
            with pytest.raises(SystemExit) as exc:
                tmpl_main()
            assert exc.value.code == 1

    def test_main_no_project_name(self):
        """GIVEN sys.argv=['prog','init'] WHEN main THEN exit(1)."""
        from yuleosh.cli.template import main as tmpl_main
        with patch.object(sys, "argv", ["template.py", "init"]):
            with pytest.raises(SystemExit) as exc:
                tmpl_main()
            assert exc.value.code == 1

    def test_main_unknown_command(self):
        """GIVEN sys.argv with unknown cmd WHEN main THEN exit(1)."""
        from yuleosh.cli.template import main as tmpl_main
        with patch.object(sys, "argv", ["template.py", "unknown_cmd"]):
            with pytest.raises(SystemExit) as exc:
                tmpl_main()
            assert exc.value.code == 1


# ======================================================================
# _init_starter internals
# ======================================================================

class TestInitStarter:
    """GIVEN _init_starter WHEN called THEN creates specific files."""

    def test_init_starter_gitignore(self):
        """GIVEN starter init WHEN .gitignore written THEN has expected entries."""
        from yuleosh.cli.template import _init_starter, GITIGNORE_CONTENT
        with tempfile.TemporaryDirectory() as tmp:
            result = _init_starter("proj", Path(tmp) / "proj")
            assert (result / ".gitignore").exists()
            content = (result / ".gitignore").read_text()
            assert "__pycache__" in content
            assert ".coverage" in content

    def test_init_starter_pyproject(self):
        """GIVEN starter init WHEN pyproject.toml written THEN has project name."""
        from yuleosh.cli.template import _init_starter
        with tempfile.TemporaryDirectory() as tmp:
            result = _init_starter("my-tool", Path(tmp) / "my-tool")
            pyproject = (result / "pyproject.toml").read_text()
            assert "my-tool" in pyproject
            assert "yuleOSH" in pyproject

    def test_init_starter_spec_content(self):
        """GIVEN starter init WHEN spec.md written THEN contains SHALL/SHOULD/MAY."""
        from yuleosh.cli.template import _init_starter
        with tempfile.TemporaryDirectory() as tmp:
            result = _init_starter("spec-check", Path(tmp) / "spec-check")
            spec = (result / "docs" / "spec.md").read_text()
            assert "SHALL" in spec
            assert "SHOULD" in spec
            assert "MAY" in spec
            assert "GIVEN" in spec
            assert "WHEN" in spec
            assert "THEN" in spec
            assert "Scenario" in spec
            assert "Reason" in spec


# ======================================================================
# _init_from_template internals
# ======================================================================

class TestInitFromTemplate:
    """GIVEN _init_from_template WHEN called THEN copies and cleans."""

    def test_copies_docs_src_tests(self):
        """GIVEN template with docs/src/tests WHEN init THEN files copied."""
        from yuleosh.cli.template import _init_from_template
        with tempfile.TemporaryDirectory() as tmp:
            tmpl = Path(tmp) / "t"
            tmpl.mkdir()
            (tmpl / "docs").mkdir()
            (tmpl / "docs" / "arch.md").write_text("# Architecture")
            (tmpl / "src").mkdir()
            (tmpl / "src" / "main.py").write_text("print('hello')")
            (tmpl / "tests").mkdir()
            (tmpl / "tests" / "test_main.py").write_text("def test(): pass")
            result = _init_from_template("proj", Path(tmp) / "proj", tmpl)
            assert (result / "docs" / "arch.md").exists()
            assert (result / "src" / "main.py").exists()
            assert (result / "tests" / "test_main.py").exists()

    def test_removes_git_and_cache(self):
        """GIVEN template with .git WHEN init THEN .git removed."""
        from yuleosh.cli.template import _init_from_template
        with tempfile.TemporaryDirectory() as tmp:
            tmpl = Path(tmp) / "t"
            tmpl.mkdir()
            (tmpl / ".git").mkdir()
            (tmpl / "src").mkdir()
            (tmpl / "src" / "code.c").write_text("// code")
            result = _init_from_template("proj", Path(tmp) / "proj", tmpl)
            assert not (result / ".git").exists()
            assert (result / "src" / "code.c").exists()
