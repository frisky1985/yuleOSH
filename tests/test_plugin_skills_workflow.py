#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for yuleosh.skills.plugin_skills — SkillManager workflow execution.

Complements tests/test_plugins.py by covering the workflow-run paths:
dependency ordering, input/output resolution ($steps / $. refs), deadlock
detection, and error handling for missing skills/workflows/plugins.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.skills.plugin_skills import (
    SkillManager,
    SkillManifest,
    Workflow,
    WorkflowStep,
)


def _write_manifest(skills_dir: Path, name: str, workflow: dict) -> Path:
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.0.0",
        "type": "skill",
        "description": "test skill",
        "author": "tester",
        "workflow": workflow,
    }
    p = d / "manifest.json"
    p.write_text(json.dumps(manifest))
    return p


class TestSkillManagerWorkflow:
    def _make_skill_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir(exist_ok=True)
        return skills_dir

    def test_get_skill_missing_returns_none(self, tmp_path):
        sm = SkillManager(self._make_skill_dir(tmp_path), mock.MagicMock())
        assert sm.get_skill("nope") is None

    def test_discover_filters_non_skill_types(self, tmp_path):
        skills_dir = self._make_skill_dir(tmp_path)
        # valid skill
        _write_manifest(skills_dir, "good", {"version": "1", "steps": []})
        # non-skill type manifest
        bad_dir = skills_dir / "tool-one"
        bad_dir.mkdir(exist_ok=True)
        (bad_dir / "manifest.json").write_text(json.dumps({
            "name": "tool-one", "version": "1.0.0", "type": "tool",
            "description": "d", "author": "a"}))
        # malformed json
        junk = skills_dir / "junk"
        junk.mkdir(exist_ok=True)
        (junk / "manifest.json").write_text("{not json")
        # dir without manifest
        (skills_dir / "empty").mkdir(exist_ok=True)

        sm = SkillManager(skills_dir, mock.MagicMock())
        names = [s.name for s in sm.discover_skills()]
        assert names == ["good"]

    def test_run_skill_missing_skill_raises(self, tmp_path):
        sm = SkillManager(self._make_skill_dir(tmp_path), mock.MagicMock())
        with pytest.raises(ValueError, match="不存在"):
            sm.run_skill("ghost", {})

    def test_run_skill_without_workflow_raises(self, tmp_path):
        skills_dir = self._make_skill_dir(tmp_path)
        d = skills_dir / "noflow"
        d.mkdir(exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({
            "name": "noflow", "version": "1.0.0", "type": "skill",
            "description": "d", "author": "a"}))
        sm = SkillManager(skills_dir, mock.MagicMock())
        with pytest.raises(ValueError, match="workflow"):
            sm.run_skill("noflow", {})

    def test_run_skill_dependency_order(self, tmp_path):
        """Steps with depends_on run after their dependency."""
        import sys
        import types

        skills_dir = self._make_skill_dir(tmp_path)
        _write_manifest(skills_dir, "wf", {
            "version": "1",
            "steps": [
                {"id": "b", "plugin": "p-b", "depends_on": ["a"]},
                {"id": "a", "plugin": "p-a"},
            ],
            "outputs": {"combined": "$steps.b"},
        })
        pm = mock.MagicMock()
        order = []

        class FakeSandbox:
            def __init__(self, *a, **k):
                pass

            def execute(self, plugin, inputs):
                order.append(plugin._name)
                return {"value": f"out-{len(order)}"}

        def load_side(name):
            p = mock.MagicMock()
            p._name = name
            return p

        pm.load.side_effect = load_side
        sm = SkillManager(skills_dir, pm)
        # The legacy run_skill imports `plugins.sandbox` at call time.
        fake_mod = types.ModuleType("plugins.sandbox")
        fake_mod.PluginSandbox = FakeSandbox
        with mock.patch.dict(sys.modules, {"plugins.sandbox": fake_mod}):
            out = sm.run_skill("wf", {})
        assert order == ["p-a", "p-b"]
        assert out["combined"]["value"] == "out-2"

    def test_run_skill_deadlock_raises(self, tmp_path):
        """Circular dependency → deadlock error."""
        skills_dir = self._make_skill_dir(tmp_path)
        _write_manifest(skills_dir, "cycle", {
            "version": "1",
            "steps": [
                {"id": "x", "plugin": "p-x", "depends_on": ["y"]},
                {"id": "y", "plugin": "p-y", "depends_on": ["x"]},
            ],
        })
        pm = mock.MagicMock()
        pm.load.return_value = mock.MagicMock(directory=tmp_path,
                                              manifest=mock.MagicMock())
        sm = SkillManager(skills_dir, pm)
        with pytest.raises(RuntimeError, match="死锁"):
            sm.run_skill("cycle", {})

    def test_run_skill_missing_plugin_raises(self, tmp_path):
        skills_dir = self._make_skill_dir(tmp_path)
        _write_manifest(skills_dir, "noplugin", {
            "version": "1",
            "steps": [{"id": "s1", "plugin": "not-installed"}],
        })
        pm = mock.MagicMock()
        pm.load.return_value = None
        sm = SkillManager(skills_dir, pm)
        with pytest.raises(RuntimeError, match="未安装"):
            sm.run_skill("noplugin", {})

    def test_resolve_inputs_and_outputs(self):
        sm = SkillManager(Path("/tmp"), mock.MagicMock())
        step_inputs = {
            "direct": 42,
            "root_ref": "$.port",
            "step_ref": "$steps.one",
            "step_ref_nested": "$steps.one.value",
        }
        resolved = sm._resolve_inputs(step_inputs, {"port": "COM1"},
                                      {"one": {"value": 7}})
        assert resolved["direct"] == 42
        assert resolved["root_ref"] == "COM1"
        assert resolved["step_ref"] == {"value": 7}
        assert resolved["step_ref_nested"] == 7

        outputs = sm._resolve_outputs(
            {"a": "$steps.one", "b": "$steps.one.value", "c": "literal"},
            {"one": {"value": 9}},
        )
        assert outputs == {"a": {"value": 9}, "b": 9, "c": "literal"}

    def test_workflow_from_dict_and_steps(self):
        wf = Workflow.from_dict({
            "version": "2",
            "steps": [{"id": "s1", "plugin": "p1", "inputs": {"a": 1},
                       "depends_on": ["s0"], "condition": "x"}],
            "outputs": {"r": "$steps.s1"},
        })
        assert wf.version == "2"
        assert wf.steps[0].id == "s1"
        assert wf.steps[0].depends_on == ["s0"]
        assert wf.steps[0].condition == "x"
        step = WorkflowStep(id="a", plugin="b")
        assert step.inputs == {}
