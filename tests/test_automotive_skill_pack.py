#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Bundled automotive skill pack — data integrity + pipeline integration."""

from __future__ import annotations

import json

import pytest

from yuleosh.skills import packs
from yuleosh.skills.model import Skill
from yuleosh.skills.registry import SkillRegistry, get_registry, reset_registry
from yuleosh.skills.selector import select_skill_names


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_registry()
    yield
    reset_registry()


class TestPackData:
    def test_pack_is_bundled_and_complete(self):
        assert packs.AUTOMOTIVE_PACK.is_file()
        payload = json.loads(packs.AUTOMOTIVE_PACK.read_text(encoding="utf-8"))
        assert payload["license"] == "MIT"
        assert payload["source"].endswith("automotive-claude-code-agents")
        assert payload["count"] >= 4000
        assert len(payload["skills"]) == payload["count"]

    def test_skills_are_unique_and_tagged(self):
        skills = packs.load_automotive_skills()
        assert len(skills) >= 4000
        names = [s.name for s in skills]
        assert len(names) == len(set(names))
        assert all("automotive" in s.tags for s in skills)
        assert all(s.content.strip() for s in skills)
        curated = [s for s in skills if "curated" in s.tags]
        assert len(curated) >= 50

    def test_pack_can_be_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("YULEOSH_SKILL_PACKS", "0")
        assert packs.load_automotive_skills() == []


class TestRegistryIntegration:
    def test_install_registers_without_index_hook(self):
        registry = SkillRegistry()
        added = packs.install_automotive_pack(registry)
        assert added >= 4000
        assert "automotive-safety-fmea-001" in registry
        assert packs.install_automotive_pack(registry) == 0  # idempotent

    def test_default_registry_exposes_pack(self):
        registry = get_registry()
        assert "automotive-automotive-workflow-v-model-development" in registry
        assert len(registry) > len(packs.load_automotive_skills())


class TestSelector:
    def test_profiles_are_step_specific(self):
        req = select_skill_names("sys-requirements", "requirement analysis", limit=1)
        test = select_skill_names("test-codegen", "unit test coverage", limit=1)
        assert req and test
        assert req != test
        assert "workflow" in req[0] or "requirement" in req[0]
        assert "test" in test[0]

    def test_deterministic_and_capped(self):
        first = select_skill_names("development", "LED driver", limit=3)
        second = select_skill_names("development", "LED driver", limit=3)
        assert first == second
        assert len(first) == 3
        assert len(select_skill_names("development", limit=1)) == 1

    def test_duplicate_templates_are_skipped(self):
        names = select_skill_names("development", limit=3)
        skills = [get_registry().get(n) for n in names]
        assert len({s.content for s in skills}) == 3

    def test_unknown_step_is_empty(self):
        assert select_skill_names("no-such-step") == []


class TestPromptInjection:
    def test_auto_skills_reach_the_prompt(self):
        from yuleosh.pipeline.knowledge_injection import (
            SKILLS_HEADER,
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        cfg = PipelineKnowledgeConfig(
            inject_memory=False, inject_rag=False, inject_skills=True)
        out = _assemble_skills("sys-requirements", cfg, "LED blink 1s")
        assert out.startswith(SKILLS_HEADER)
        assert "automotive-" in out
        assert len(out) < 4000

    def test_explicit_names_win_over_auto(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        cfg = PipelineKnowledgeConfig(skills=["autosar-coding"])
        out = _assemble_skills("sys-requirements", cfg, "LED")
        assert "autosar-coding" in out or "AUTOSAR" in out

    def test_auto_skills_can_be_disabled(self):
        from yuleosh.pipeline.knowledge_injection import (
            PipelineKnowledgeConfig,
            _assemble_skills,
        )

        cfg = PipelineKnowledgeConfig(auto_skills=False)
        assert _assemble_skills("sys-requirements", cfg, "LED") == ""


class TestCodegenInjection:
    def _engine(self, tmp_path, captured):
        from yuleosh.codegen.engine import CodegenEngine

        def fake_llm(system_prompt, prompt, **kwargs):
            captured["system"] = system_prompt
            return {"content": "ok"}

        return CodegenEngine(output_dir=tmp_path, llm_client=fake_llm)

    def test_codegen_prompt_gets_step_skills(self, tmp_path):
        from types import SimpleNamespace

        captured = {}
        engine = self._engine(tmp_path, captured)
        session = SimpleNamespace(mock_mode=False, project_dir=str(tmp_path))
        assert engine._call_llm(session, "SYS", "write LED driver") == "ok"
        assert "## Pipeline Skills" in captured["system"]
        assert "automotive-" in captured["system"]
        assert captured["system"].rstrip().endswith("SYS")

    def test_mock_mode_skips_skill_injection(self, tmp_path):
        from types import SimpleNamespace

        captured = {}
        engine = self._engine(tmp_path, captured)
        session = SimpleNamespace(mock_mode=True, project_dir=str(tmp_path))
        engine._call_llm(session, "SYS", "write LED driver")
        assert "## Pipeline Skills" not in captured["system"]
