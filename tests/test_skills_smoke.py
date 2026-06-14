"""Smoke tests for skills/__init__.py — SkillManifest, SkillManager, Workflow."""
import pytest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path

from yuleosh.skills import SkillManifest, SkillManager, Workflow, WorkflowStep
from yuleosh.plugins import PluginManifest, PluginManager


class TestWorkflowStep:
    """Smoke tests for WorkflowStep."""

    def test_create_minimal(self):
        step = WorkflowStep(id="step1", plugin="test-plugin")
        assert step.id == "step1"
        assert step.plugin == "test-plugin"
        assert step.inputs == {}
        assert step.depends_on == []
        assert step.condition is None

    def test_create_full(self):
        step = WorkflowStep(id="s1", plugin="p1", inputs={"key": "val"},
                            depends_on=["s0"], condition="always")
        assert step.depends_on == ["s0"]
        assert step.condition == "always"


class TestWorkflow:
    """Smoke tests for Workflow."""

    def test_create_minimal(self):
        wf = Workflow(version="1")
        assert wf.version == "1"
        assert wf.steps == []

    def test_from_dict(self):
        data = {
            "version": "2",
            "steps": [
                {"id": "build", "plugin": "builder", "inputs": {"cmd": "make"}},
                {"id": "test", "plugin": "tester", "depends_on": ["build"]},
            ],
            "outputs": {"result": "$steps.test.output"},
        }
        wf = Workflow.from_dict(data)
        assert wf.version == "2"
        assert len(wf.steps) == 2
        assert wf.steps[0].id == "build"
        assert wf.steps[1].depends_on == ["build"]

    def test_from_dict_empty_steps(self):
        wf = Workflow.from_dict({"version": "1"})
        assert wf.steps == []


class TestSkillManifest:
    """Smoke tests for SkillManifest."""

    def test_create_from_plugin_manifest(self):
        data = {
            "name": "test-skill", "version": "1.0.0", "type": "skill",
            "description": "A test skill", "author": "tester",
            "workflow": {"version": "1", "steps": []},
        }
        sm = SkillManifest.from_dict(data)
        assert sm.name == "test-skill"
        assert sm.type == "skill"
        assert sm.workflow is not None
        assert sm.workflow.version == "1"

    def test_without_workflow(self):
        data = {
            "name": "simple", "version": "1.0.0", "type": "skill",
            "description": "no workflow", "author": "tester",
        }
        sm = SkillManifest.from_dict(data)
        assert sm.workflow is None

    def test_has_plugin_manifest_attributes(self):
        data = {
            "name": "full", "version": "2.0.0", "type": "target",
            "description": "full manifest", "author": "author",
            "tags": ["tag1"], "timeout": 60,
        }
        sm = SkillManifest.from_dict(data)
        assert sm.tags == ["tag1"]
        assert sm.timeout == 60

    def test_from_file(self, tmp_path):
        data = {
            "name": "file-skill", "version": "1.0.0", "type": "skill",
            "description": "from file", "author": "tester",
            "workflow": {"version": "1", "steps": [{"id": "s1", "plugin": "p1"}]},
        }
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps(data))
        sm = SkillManifest.from_file(str(mf))
        assert sm.name == "file-skill"
        assert len(sm.workflow.steps) == 1


class TestSkillManager:
    """Smoke tests for SkillManager."""

    @pytest.fixture
    def pm(self, tmp_path):
        return PluginManager(str(tmp_path / "plugins"))

    @pytest.fixture
    def sm(self, tmp_path, pm):
        return SkillManager(str(tmp_path / "skills"), pm)

    def test_create(self, sm):
        assert sm.skills_dir.exists()
        assert sm.pm is not None

    def test_discover_skills_empty(self, sm):
        assert sm.discover_skills() == []

    def test_discover_skills(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "my-skill"
        skill_dir.mkdir()
        manifest = {
            "name": "my-skill", "version": "1.0.0", "type": "skill",
            "description": "test skill", "author": "test",
            "workflow": {"version": "1", "steps": [{"id": "step1", "plugin": "p1"}]},
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))
        skills = sm.discover_skills()
        assert len(skills) == 1
        assert skills[0].name == "my-skill"

    def test_discover_skills_filters_non_skill_type(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "not-a-skill"
        skill_dir.mkdir()
        manifest = {
            "name": "not-a-skill", "version": "1.0.0", "type": "target",
            "description": "not a skill", "author": "test",
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))
        skills = sm.discover_skills()
        assert len(skills) == 0

    def test_get_skill_not_found(self, sm):
        assert sm.get_skill("nonexistent") is None

    def test_get_skill_found(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "existing-skill"
        skill_dir.mkdir()
        manifest = {
            "name": "existing-skill", "version": "1.0.0", "type": "skill",
            "description": "existing", "author": "test",
            "workflow": {"version": "1", "steps": []},
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))
        skill = sm.get_skill("existing-skill")
        assert skill is not None
        assert skill.name == "existing-skill"

    def test_run_skill_not_found(self, sm):
        with pytest.raises(ValueError, match="不存在"):
            sm.run_skill("nonexistent", {})

    def test_run_skill_no_workflow(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "no-wf"
        skill_dir.mkdir()
        manifest = {
            "name": "no-wf", "version": "1.0.0", "type": "skill",
            "description": "no workflow", "author": "test",
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="没有定义 workflow"):
            sm.run_skill("no-wf", {})

    def test_run_skill_simple(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "simple-skill"
        skill_dir.mkdir()
        manifest = {
            "name": "simple-skill", "version": "1.0.0", "type": "skill",
            "description": "simple", "author": "test",
            "workflow": {
                "version": "1",
                "steps": [{"id": "step1", "plugin": "simple-plugin"}],
                "outputs": {"step1_result": "$steps.step1"},
            },
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))

        # Mock PluginSandbox at the sys.modules level (the import inside run_skill
        # does `from plugins.sandbox import PluginSandbox`)
        mock_sandbox_cls = MagicMock()
        mock_sandbox = MagicMock()
        mock_sandbox_cls.return_value = mock_sandbox
        mock_sandbox.execute.return_value = "done"

        fake_modules = {
            "plugins": MagicMock(),
            "plugins.sandbox": MagicMock(),
        }
        fake_modules["plugins.sandbox"].PluginSandbox = mock_sandbox_cls

        with patch.object(sm.pm, "load") as mock_load:
            mock_plugin = MagicMock()
            mock_plugin.directory = tmp_path / "plugins" / "simple-plugin"
            mock_plugin.manifest = MagicMock()
            mock_plugin.manifest.timeout = 30
            mock_load.return_value = mock_plugin

            with patch.dict("sys.modules", fake_modules):
                result = sm.run_skill("simple-skill", {"input_key": "input_val"})
                assert result == {"step1_result": "done"}

    def test_resolve_inputs_string_ref(self):
        resolved = SkillManager._resolve_inputs(
            {"arg1": "$steps.build.output"},
            {},
            {"build": {"output": "built"}},
        )
        assert resolved["arg1"] == "built"

    def test_resolve_inputs_root_ref(self):
        resolved = SkillManager._resolve_inputs(
            {"arg1": "$.name"},
            {"name": "test-value"},
            {},
        )
        assert resolved["arg1"] == "test-value"

    def test_resolve_inputs_literal(self):
        resolved = SkillManager._resolve_inputs(
            {"arg1": "literal-value"},
            {},
            {},
        )
        assert resolved["arg1"] == "literal-value"

    def test_resolve_outputs(self):
        outputs = SkillManager._resolve_outputs(
            {"result": "$steps.build.status"},
            {"build": {"status": "ok"}},
        )
        assert outputs["result"] == "ok"

    def test_resolve_outputs_literal(self):
        outputs = SkillManager._resolve_outputs(
            {"result": "static-value"},
            {},
        )
        assert outputs["result"] == "static-value"

    def test_run_with_deadlock(self, sm, tmp_path):
        skill_dir = sm.skills_dir / "deadlock-skill"
        skill_dir.mkdir()
        manifest = {
            "name": "deadlock-skill", "version": "1.0.0", "type": "skill",
            "description": "deadlock", "author": "test",
            "workflow": {"version": "1", "steps": [
                {"id": "a", "plugin": "pa", "depends_on": ["b"]},
                {"id": "b", "plugin": "pb", "depends_on": ["a"]},
            ]},
        }
        (skill_dir / "manifest.json").write_text(json.dumps(manifest))

        # Set up mock for PluginSandbox import
        mock_sandbox_cls = MagicMock()
        fake_modules = {
            "plugins": MagicMock(),
            "plugins.sandbox": MagicMock(),
        }
        fake_modules["plugins.sandbox"].PluginSandbox = mock_sandbox_cls

        with patch.object(sm.pm, "load") as mock_load:
            mock_plugin = MagicMock()
            mock_plugin.directory = tmp_path / "plugins" / "pa"
            mock_plugin.manifest = MagicMock()
            mock_plugin.manifest.timeout = 30
            mock_load.return_value = mock_plugin

            with patch.dict("sys.modules", fake_modules):
                with pytest.raises(RuntimeError, match="死锁"):
                    sm.run_skill("deadlock-skill", {})


class TestInitExports:
    def test_all_exported(self):
        import yuleosh.skills
        assert hasattr(yuleosh.skills, "SkillManifest")
        assert hasattr(yuleosh.skills, "SkillManager")
        assert hasattr(yuleosh.skills, "Workflow")
        assert hasattr(yuleosh.skills, "WorkflowStep")
