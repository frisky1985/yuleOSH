# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Skill Store — Skill 是更高层次的 Plugin 组合。

Skill 将多个 Plugin 编排为一个完整工作流，通过 manifest 中的 workflow 字段定义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from yuleosh.plugins import PluginManifest, PluginManager


# ---------------------------------------------------------------------------
# Workflow 数据模型
# ---------------------------------------------------------------------------

@dataclass
class WorkflowStep:
    """工作流步骤定义。"""
    id: str
    plugin: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    condition: Optional[str] = None


@dataclass
class Workflow:
    """Skill 工作流定义。"""
    version: str
    steps: list[WorkflowStep] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        steps = []
        for s in data.get("steps", []):
            steps.append(WorkflowStep(
                id=s.get("id", ""),
                plugin=s.get("plugin", ""),
                inputs=s.get("inputs", {}),
                depends_on=s.get("depends_on", []),
                condition=s.get("condition"),
            ))
        return cls(
            version=data.get("version", "1"),
            steps=steps,
            outputs=data.get("outputs", {}),
        )


# ---------------------------------------------------------------------------
# Skill Manifest（扩展 PluginManifest）
# ---------------------------------------------------------------------------

@dataclass
class SkillManifest(PluginManifest):
    """Skill Manifest — 在 Plugin Manifest 上增加 workflow 字段。"""
    workflow: Optional[Workflow] = None

    @classmethod
    def from_dict(cls, data: dict) -> "SkillManifest":
        base = PluginManifest.from_dict(data)
        workflow_data = data.get("workflow")
        workflow = Workflow.from_dict(workflow_data) if workflow_data else None
        return cls(
            **{f.name: getattr(base, f.name) for f in PluginManifest.__dataclass_fields__.values()},
            workflow=workflow,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "SkillManifest":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# SkillManager
# ---------------------------------------------------------------------------

class SkillManager:
    """Skill 管理器 — 加载和编排 Skill 工作流。"""

    def __init__(self, skills_dir: str | Path, plugin_manager: PluginManager):
        self.skills_dir = Path(skills_dir).resolve()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.pm = plugin_manager

    def discover_skills(self) -> list[SkillManifest]:
        """发现所有已安装的 Skill。"""
        skills: list[SkillManifest] = []
        if not self.skills_dir.is_dir():
            return skills
        for entry in sorted(self.skills_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = SkillManifest.from_file(manifest_path)
                if manifest.type == "skill":
                    skills.append(manifest)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return skills

    def get_skill(self, name: str) -> Optional[SkillManifest]:
        """获取指定 Skill 的 Manifest。"""
        manifest_path = self.skills_dir / name / "manifest.json"
        if not manifest_path.is_file():
            return None
        try:
            return SkillManifest.from_file(manifest_path)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def run_skill(self, name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """运行 Skill 工作流。"""
        manifest = self.get_skill(name)
        if manifest is None:
            raise ValueError(f"Skill '{name}' 不存在")
        if manifest.workflow is None:
            raise ValueError(f"Skill '{name}' 没有定义 workflow")

        workflow = manifest.workflow
        results: dict[str, Any] = {}
        completed: set[str] = set()

        # 拓扑排序执行
        max_iterations = len(workflow.steps) * 10
        while len(completed) < len(workflow.steps) and max_iterations > 0:
            max_iterations -= 1
            ran_any = False
            for step in workflow.steps:
                if step.id in completed:
                    continue
                # 检查依赖是否完成
                deps_met = all(dep in completed for dep in step.depends_on)
                if not deps_met:
                    continue
                # 执行步骤
                plugin = self.pm.load(step.plugin)
                if plugin is None:
                    raise RuntimeError(f"步骤 {step.id}: 依赖插件 '{step.plugin}' 未安装")

                step_inputs = self._resolve_inputs(step.inputs, inputs, results)
                from plugins.sandbox import PluginSandbox
                sandbox = PluginSandbox(plugin.directory, plugin.manifest)
                step_result = sandbox.execute(plugin, step_inputs)

                results[step.id] = step_result
                completed.add(step.id)
                ran_any = True

            if not ran_any:
                # 死锁检查
                uncompleted = [s.id for s in workflow.steps if s.id not in completed]
                raise RuntimeError(f"工作流死锁：步骤 {uncompleted} 的依赖无法满足")

        output = self._resolve_outputs(workflow.outputs, results)
        return output

    @staticmethod
    def _resolve_inputs(
        step_inputs: dict,
        root_inputs: dict,
        step_results: dict[str, Any],
    ) -> dict[str, Any]:
        """解析输入参数（支持 JSONPath 风格引用）。"""
        resolved: dict[str, Any] = {}
        for key, value in step_inputs.items():
            if isinstance(value, str) and value.startswith("$steps."):
                parts = value.split(".")
                step_id = parts[1]
                output_key = ".".join(parts[2:]) if len(parts) > 2 else None
                result = step_results.get(step_id)
                if output_key and isinstance(result, dict):
                    resolved[key] = result.get(output_key)
                else:
                    resolved[key] = result
            elif isinstance(value, str) and value.startswith("$."):
                # 根输入引用
                path = value[2:].strip(".")
                resolved[key] = root_inputs.get(path, value)
            else:
                resolved[key] = value
        return resolved

    @staticmethod
    def _resolve_outputs(workflow_outputs: dict, step_results: dict[str, Any]) -> dict[str, Any]:
        """解析工作流输出。"""
        outputs: dict[str, Any] = {}
        for key, value in workflow_outputs.items():
            if isinstance(value, str) and value.startswith("$steps."):
                parts = value.split(".")
                step_id = parts[1]
                output_key = ".".join(parts[2:]) if len(parts) > 2 else None
                result = step_results.get(step_id)
                if output_key and isinstance(result, dict):
                    outputs[key] = result.get(output_key)
                else:
                    outputs[key] = result
            else:
                outputs[key] = value
        return outputs


__all__ = [
    "SkillManifest",
    "SkillManager",
    "Workflow",
    "WorkflowStep",
]
