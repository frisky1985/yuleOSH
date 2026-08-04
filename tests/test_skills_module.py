#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for src/yuleosh/skills — model, registry, prompt splicing, CLI.

Covers: registration / lookup / listing / unregister, JSON persistence,
built-in skills, ``render_skills`` prompt splicing, and the
``yuleosh skills list|show`` CLI handlers.
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.skills import (
    BUILTIN_SKILL_NAMES,
    Skill,
    SkillRegistry,
    builtin_skills,
    get_registry,
    render_skills,
    reset_registry,
    resolve_skill_names,
    set_registry,
)
from yuleosh.skills.cli import handle_skills_command


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Each test starts from a fresh singleton."""
    reset_registry()
    yield
    reset_registry()


def _make_skill(name: str = "demo-skill", tags=None):
    return Skill(
        name=name,
        title=f"Title {name}",
        description=f"Desc {name}",
        content="# Demo\n\nSome **content** for %s." % name,
        tags=tags or ["demo"],
    )


# ==================================================================
# Model
# ==================================================================


class TestSkillModel:
    def test_skill_defaults(self):
        s = Skill(name="x", title="T", description="D", content="C")
        assert s.tags == []
        assert s.version == "1.0.0"
        assert s.created_at  # non-empty ISO timestamp

    def test_skill_to_dict_from_dict_roundtrip(self):
        s = _make_skill(tags=["a", "b"])
        d = s.to_dict()
        s2 = Skill.from_dict(d)
        assert s2.name == s.name
        assert s2.content == s.content
        assert s2.tags == ["a", "b"]
        assert s2.version == s.version

    def test_skill_from_dict_skips_unknown_keys(self):
        s = Skill.from_dict({"name": "n", "title": "t", "description": "d",
                             "content": "c", "future_key": 42})
        assert s.name == "n"
        assert not hasattr(s, "future_key")

    def test_skill_render_includes_header_and_content(self):
        s = _make_skill()
        rendered = s.render()
        assert "### Skill: demo-skill" in rendered
        assert "- **Title**: Title demo-skill" in rendered
        assert "# Demo" in rendered
        assert "Some **content**" in rendered


# ==================================================================
# Registry
# ==================================================================


class TestSkillRegistry:
    def test_register_get(self):
        reg = SkillRegistry()
        s = _make_skill()
        assert reg.register(s) is True
        assert reg.get("demo-skill") is s

    def test_register_duplicate_rejected_without_overwrite(self):
        reg = SkillRegistry()
        assert reg.register(_make_skill()) is True
        assert reg.register(_make_skill()) is False
        assert reg.register(_make_skill(), overwrite=True) is True

    def test_register_many_counts_added(self):
        reg = SkillRegistry()
        added = reg.register_many([_make_skill("a"), _make_skill("b"),
                                   _make_skill("a")])
        assert added == 2

    def test_unregister(self):
        reg = SkillRegistry()
        reg.register(_make_skill())
        assert reg.unregister("demo-skill") is True
        assert reg.get("demo-skill") is None
        assert reg.unregister("demo-skill") is False

    def test_list_sorted_and_tag_filter(self):
        reg = SkillRegistry()
        reg.register(_make_skill("b", tags=["c"]))
        reg.register(_make_skill("a", tags=["c"]))
        reg.register(_make_skill("z", tags=["other"]))
        names = [s.name for s in reg.list()]
        assert names == ["a", "b", "z"]
        assert [s.name for s in reg.list(tag="c")] == ["a", "b"]

    def test_contains_and_len(self):
        reg = SkillRegistry()
        assert "x" not in reg
        reg.register(_make_skill("x"))
        assert "x" in reg
        assert len(reg) == 1

    def test_json_persistence_roundtrip(self, tmp_path):
        reg = SkillRegistry(persist_path=tmp_path / "skills.json")
        reg.register(_make_skill("persisted"))
        path = reg.save()
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["skills"][0]["name"] == "persisted"

        reg2 = SkillRegistry(persist_path=tmp_path / "skills.json")
        assert reg2.load() == 1
        assert reg2.get("persisted") is not None

    def test_load_missing_file_returns_zero(self, tmp_path):
        reg = SkillRegistry(persist_path=tmp_path / "nope.json")
        assert reg.load() == 0

    def test_load_merges_without_overwriting_existing(self, tmp_path):
        path = tmp_path / "skills.json"
        path.write_text(json.dumps({"version": "1", "skills": [
            {"name": "keep", "title": "t", "description": "d", "content": "c"}]}))
        reg = SkillRegistry(persist_path=path)
        reg.register(_make_skill("keep"))
        loaded = reg.load()
        assert loaded == 0  # 'keep' already present
        assert reg.get("keep").content != "c"  # existing entry untouched

    def test_save_requires_path(self):
        reg = SkillRegistry()  # no persist_path
        reg.register(_make_skill())
        with pytest.raises(ValueError):
            reg.save()


class TestSingletonRegistry:
    def test_get_registry_is_singleton(self):
        assert get_registry() is get_registry()

    def test_get_registry_auto_registers_builtins(self):
        reg = get_registry()
        assert set(BUILTIN_SKILL_NAMES) <= set(reg.names())
        assert len(reg) >= 3

    def test_set_registry_replaces_singleton(self):
        custom = SkillRegistry()
        custom.register(_make_skill("custom"))
        set_registry(custom)
        assert get_registry() is custom
        assert "custom" in get_registry()


class TestBuiltinSkills:
    @pytest.mark.parametrize("name", BUILTIN_SKILL_NAMES)
    def test_builtin_skill_present_with_content(self, name):
        by_name = {s.name: s for s in builtin_skills()}
        skill = by_name[name]
        assert skill.name == name
        assert len(skill.content) > 100
        assert skill.description

    def test_builtin_skills_fresh_instances(self):
        a, b = builtin_skills(), builtin_skills()
        assert a[0] is not b[0]


# ==================================================================
# Prompt splicing
# ==================================================================


class TestRenderSkills:
    def test_render_skills_empty_names(self):
        assert render_skills([]) == ""

    def test_render_skills_unknown_names_skipped(self):
        reg = SkillRegistry()
        reg.register(_make_skill("known"))
        with mock.patch("yuleosh.skills.prompt.log.warning") as warn:
            out = render_skills(["known", "missing"], registry=reg)
        warn.assert_called_once()
        assert "known" in out and "missing" not in out

    def test_render_skills_includes_all_requested(self):
        reg = SkillRegistry()
        reg.register_many([_make_skill("a", tags=["t"]), _make_skill("b", tags=["t"])])
        out = render_skills(["a", "b"], registry=reg)
        assert out.startswith("## 📚 技能参考")
        assert "Skill: a" in out and "Skill: b" in out
        assert "Desc a" in out and "Desc b" in out

    def test_render_skills_truncates_long_content(self):
        reg = SkillRegistry()
        reg.register(Skill(name="long", title="t", description="d",
                           content="x" * 10000))
        out = render_skills(["long"], registry=reg, max_chars_per_skill=500)
        assert len(out) < 2000
        assert "(truncated)" in out

    def test_resolve_skill_names_accepts_string_and_list(self):
        reg = SkillRegistry()
        reg.register_many([_make_skill("a"), _make_skill("b")])
        assert resolve_skill_names("a, b, nope", registry=reg) == ["a", "b"]
        assert resolve_skill_names(["a"], registry=reg) == ["a"]
        assert resolve_skill_names(None, registry=reg) == []

    def test_render_skills_uses_default_registry(self):
        out = render_skills(["autosar-coding"])
        assert "AUTOSAR C 编码规范要点" in out


# ==================================================================
# CLI handlers
# ==================================================================


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestSkillsCli:
    def test_list_command(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="list", json=False))
        out = capsys.readouterr().out
        assert rc == 0
        assert "autosar-coding" in out
        assert "misra-fix" in out
        assert "Total:" in out

    def test_list_json(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="list", json=True))
        out = capsys.readouterr().out
        assert rc == 0
        data = json.loads(out)
        names = {s["name"] for s in data}
        # 内置技能必须在列；v3.10.0 起含持久化导入的 mattpocock 技能
        assert set(BUILTIN_SKILL_NAMES) <= names
        assert len(names) >= len(BUILTIN_SKILL_NAMES)

    def test_show_existing_skill(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="show", name="misra-fix"))
        out = capsys.readouterr().out
        assert rc == 0
        assert "MISRA 违规修复模式" in out

    def test_show_unknown_skill(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="show", name="does-not-exist"))
        out = capsys.readouterr().out
        assert rc == 1
        assert "not found" in out

    def test_show_without_name(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="show", name=None))
        assert rc == 2

    def test_unknown_subcommand(self, capsys):
        rc = handle_skills_command(_Args(skills_sub="frobnicate"))
        assert rc == 2
