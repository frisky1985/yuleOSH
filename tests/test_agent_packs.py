"""Tests for the bundled automotive agent/command role pack.

Covers:
  - provenance / completeness (218 agents + 192 commands, 8 roles)
  - per-role prompt size bounds and renderability
  - install into ``.yuleosh/agents/`` + role attribution by the loader
  - non-destructive reinstall / ``--force``
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from yuleosh.agent_packs import (
    ROLE_ORDER,
    available_packs,
    handle_agents_command,
    install_pack,
    pack_manifest,
    pack_roles,
)
from yuleosh.agent_registry import load_agent_constraints_by_role


class TestPackContents:
    def test_pack_available(self):
        assert "automotive" in available_packs()

    def test_all_eight_roles_present(self):
        roles = pack_roles("automotive")
        assert tuple(r for r in ROLE_ORDER if r in roles) == ROLE_ORDER
        for path in roles.values():
            assert path.is_file()

    def test_manifest_covers_every_upstream_entry(self):
        manifest = pack_manifest("automotive")
        assert len(manifest["agents"]) == 218
        assert len(manifest["commands"]) == 192
        assigned = sum(r["agents"] for r in manifest["roles"])
        commands = sum(r["commands"] for r in manifest["roles"])
        assert assigned == 218
        assert commands == 192

    def test_role_files_are_prompt_sized_and_well_formed(self):
        for role, path in pack_roles("automotive").items():
            text = path.read_text(encoding="utf-8")
            assert len(text) <= 16000, f"{role}: {len(text)} chars"
            assert text.startswith("<!-- source:")
            assert f"# 角色约束 —" in text
            # No wrapped lines: every list entry must stay on one line.
            for line in text.splitlines():
                assert line == "" or line.startswith(("- ", "#", "以下", "<!--")) \
                    or line.startswith(" "), f"{role}: bad line {line[:40]!r}"

    def test_mapped_domains_land_in_expected_roles(self):
        text = {
            role: path.read_text(encoding="utf-8")
            for role, path in pack_roles("automotive").items()
        }
        assert "fmea-analyst" in text["verifier"] or "fmea" in text["verifier"].lower()
        assert "orchestration" in text["pm"] or "v-model" in text["pm"].lower()
        assert "adas" in text["developer"].lower()
        assert "autosar" in text["architect"].lower()


class TestInstall:
    def test_install_writes_role_files_and_loader_attributes_them(self, tmp_path):
        result = install_pack(tmp_path)
        assert sorted(result["installed"]) == sorted(ROLE_ORDER)
        assert result["skipped"] == []

        by_role = load_agent_constraints_by_role(str(tmp_path))
        assert set(by_role) == set(ROLE_ORDER)
        assert "角色约束 — Developer" in by_role["developer"]
        assert "角色约束 — QA" in by_role["qa"]

    def test_reinstall_is_non_destructive(self, tmp_path):
        install_pack(tmp_path)
        dev = tmp_path / ".yuleosh" / "agents" / "developer.md"
        dev.write_text("project-specific rule", encoding="utf-8")

        result = install_pack(tmp_path)
        assert "developer" in result["skipped"]
        assert dev.read_text(encoding="utf-8") == "project-specific rule"

    def test_force_overwrites(self, tmp_path):
        install_pack(tmp_path)
        dev = tmp_path / ".yuleosh" / "agents" / "developer.md"
        dev.write_text("stale", encoding="utf-8")
        result = install_pack(tmp_path, force=True)
        assert "developer" in result["installed"]
        assert "角色约束" in dev.read_text(encoding="utf-8")

    def test_unknown_pack_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            install_pack(tmp_path, pack="does-not-exist")


class TestCli:
    def test_list(self, capsys):
        assert handle_agents_command(argparse.Namespace(agents_sub="list")) == 0
        out = capsys.readouterr().out
        assert "automotive" in out
        assert "218 agents" in out

    def test_install(self, tmp_path, capsys):
        args = argparse.Namespace(agents_sub="install-pack",
                                  project=str(tmp_path), pack="automotive",
                                  force=False)
        assert handle_agents_command(args) == 0
        assert (tmp_path / ".yuleosh" / "agents" / "qa.md").is_file()
        assert "installed 8 role file(s)" in capsys.readouterr().out
