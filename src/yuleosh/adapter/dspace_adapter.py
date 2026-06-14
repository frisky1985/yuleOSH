# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
dSPACE AutomationDesk Adapter — 将 yuleOSH Pipeline 产出的测试用例
转化为 dSPACE AutomationDesk 兼容的 XML 格式。

输出格式：
  - AutomationDesk XML (*.autoxml / *.xml)
    - <AutoDesk> 根元素
    - <TestSet> 测试集合（对应测试用例组）
    - <TestStep> 单个测试步骤（对应测试用例）
    - <ParameterSet> Simulink 参数映射
    - <Measurement>/<Evaluation> 测量与评估
    - <ModelRef> Simulink 模型引用（MiL/SiL）

依赖：xml.etree.ElementTree（Python 标准库，无额外依赖）
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

# 导入共享工具函数
from . import _XML_DECLARATION, _indent, TestCase

# ──────────────────────────────────────────────────────────
# dSPACE AutomationDesk 命名空间
# ──────────────────────────────────────────────────────────

_AUTODESK_NS = "http://www.dspace.com/automationdesk"
_AUTODESK_DEFAULT_NS = ""  # 默认无前缀，使用默认命名空间

ET.register_namespace("", _AUTODESK_NS)

# ──────────────────────────────────────────────────────────
# 条件/测量 操作常量
# ──────────────────────────────────────────────────────────

CONDITION_TYPES = {"LessThan", "GreaterThan", "EqualTo", "InRange", "OutOfRange"}
CRITERION_TYPES = {"PassFail", "PassFailError", "Comparison", "Timeout"}


# ──────────────────────────────────────────────────────────
# DSAPCEAutomationDeskAdapter
# ──────────────────────────────────────────────────────────

class DSAPCEAutomationDeskAdapter:
    """Adapter: yuleOSH test cases → dSPACE AutomationDesk XML format.

    dSPACE AutomationDesk 使用 XML 描述自动化测试序列，
    包含 TestSet, TestStep, Parameter 等元素。
    支持导入 Simulink 模型进行 MiL/SiL 测试。

    Typical usage::

        adapter = DSAPCEAutomationDeskAdapter()
        output = adapter.convert(test_cases, output_dir="/tmp/adk_out")

    This generates one ``.autoxml`` file per test case group, plus
    a master ``project.autoxml`` and a ``simulink_params.xml``
    for Simulink parameter mapping.
    """

    def __init__(self, namespace: str = _AUTODESK_NS):
        self._namespace = namespace

    # ── Public API ────────────────────────────────────────

    def convert(self, test_cases: List[TestCase], output_dir: str) -> str:
        """将测试用例列表转换为 AutomationDesk XML 文件。

        Parameters
        ----------
        test_cases : list[dict]
            测试用例列表，每个元素符合 TestCase 结构。
        output_dir : str
            输出目录路径（会自动创建）。

        Returns
        -------
        str
            生成的 XML 文件路径列表（以换行符分隔）。
        """
        os.makedirs(output_dir, exist_ok=True)

        generated: List[str] = []

        # 1) 生成主项目文件
        master_xml = self._generate_master_project(test_cases)
        master_path = os.path.join(output_dir, "project.autoxml")
        with open(master_path, "w", encoding="utf-8") as f:
            f.write(master_xml)
        generated.append(master_path)

        # 2) 按 group 生成独立的 TestSet 文件
        groups: Dict[str, List[TestCase]] = {}
        for tc in test_cases:
            gid = tc.get("group_id", "TG_DEFAULT")
            groups.setdefault(gid, []).append(tc)

        for gid, members in groups.items():
            group_title = members[0].get("group", f"Group {gid}")
            ts_xml = self.generate_test_set(members, name=group_title)
            ts_name = self._safe_filename(gid)
            ts_path = os.path.join(output_dir, f"testset_{ts_name}.autoxml")
            with open(ts_path, "w", encoding="utf-8") as f:
                f.write(ts_xml)
            generated.append(ts_path)

        # 3) 生成 Simulink 参数映射（如果测试用例包含参数）
        params = self._collect_parameters(test_cases)
        if params:
            param_xml = self._generate_parameter_config(params)
            param_path = os.path.join(output_dir, "simulink_params.xml")
            with open(param_path, "w", encoding="utf-8") as f:
                f.write(param_xml)
            generated.append(param_path)

        # 4) 生成 Simulink 模型引用（如果测试用例指定了模型）
        models = self._collect_models(test_cases)
        for model_name in models:
            model_xml = self.generate_model_ref(model_name)
            model_path = os.path.join(
                output_dir, f"model_{self._safe_filename(model_name)}.xml"
            )
            with open(model_path, "w", encoding="utf-8") as f:
                f.write(model_xml)
            generated.append(model_path)

        return "\n".join(generated)

    def generate_test_set(
        self,
        test_cases: List[TestCase],
        name: str = "yuleOSH_Generated",
    ) -> str:
        """生成 AutomationDesk TestSet XML。

        一个 TestSet 包含 Setup（模型配置 + 参数集）和多个 TestStep。

        Parameters
        ----------
        test_cases : list[dict]
            测试用例列表。
        name : str
            TestSet 名称属性。

        Returns
        -------
        str
            格式化的 AutomationDesk XML 字符串。
        """
        root = ET.Element(
            f"{{{self._namespace}}}AutoDesk",
            attrib={"version": "2.0"},
        )

        test_set = ET.SubElement(
            root,
            f"{{{self._namespace}}}TestSet",
            attrib={"name": name},
        )

        # ── Setup ──────────────────────────────────────
        setup = ET.SubElement(
            test_set, f"{{{self._namespace}}}Setup"
        )

        # 收集模型引用
        models = self._collect_models(test_cases)
        if models:
            for model_name in models:
                ET.SubElement(
                    setup,
                    f"{{{self._namespace}}}Executable",
                    attrib={
                        "name": model_name,
                        "type": "SimulinkModel",
                    },
                )
        else:
            # 默认 Simulink 模型引用
            ET.SubElement(
                setup,
                f"{{{self._namespace}}}Executable",
                attrib={
                    "name": "model.sdf",
                    "type": "SimulinkModel",
                },
            )

        # ── ParameterSet ──────────────────────────────
        params = self._collect_parameters(test_cases)
        if params:
            param_set = ET.SubElement(
                setup,
                f"{{{self._namespace}}}ParameterSet",
                attrib={"name": "TestParams"},
            )
            for param in params:
                ET.SubElement(
                    param_set,
                    f"{{{self._namespace}}}Parameter",
                    attrib={
                        "name": param.get("name", ""),
                        "value": str(param.get("value", "")),
                    },
                )

        # ── TestSteps ─────────────────────────────────
        for tc in test_cases:
            step_xml = self.generate_test_step(tc)
            # 将生成的 TestStep 元素添加到 TestSet
            test_set.append(step_xml)

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    def generate_test_step(self, test_case: TestCase) -> ET.Element:
        """生成单个 AutomationDesk TestStep XML 元素。

        Parameters
        ----------
        test_case : dict
            单个测试用例。

        Returns
        -------
        xml.etree.ElementTree.Element
            <TestStep> 元素。
        """
        tc_id = test_case.get("id", "TC_000")
        tc_title = test_case.get("title", "Untitled")
        tc_type = test_case.get("type", "PASS")

        step_el = ET.Element(
            f"{{{self._namespace}}}TestStep",
            attrib={
                "name": f"{tc_id}_{self._safe_filename(tc_title)}",
            },
        )

        # ── Description ──────────────────────────────
        desc = test_case.get("description", "")
        if desc:
            desc_el = ET.SubElement(
                step_el, f"{{{self._namespace}}}Description"
            )
            desc_el.text = desc

        # ── Measurement ──────────────────────────────
        signals = test_case.get("signals", [])
        steps_list = test_case.get("steps", [])

        if signals or steps_list:
            measurement = ET.SubElement(
                step_el, f"{{{self._namespace}}}Measurement"
            )

            for sig in signals:
                sig_name = sig.get("name", "UnknownSignal")
                sig_el = ET.SubElement(
                    measurement,
                    f"{{{self._namespace}}}Signal",
                    attrib={"name": sig_name},
                )

                # 为信号创建条件
                expected_val = sig.get("expected_value")
                if expected_val is not None:
                    condition_type = sig.get("condition", "EqualTo")
                    ET.SubElement(
                        measurement,
                        f"{{{self._namespace}}}Condition",
                        attrib={
                            "type": condition_type,
                            "value": str(expected_val),
                        },
                    )

            # steps 中的每个 step 也作为测量点
            for step in steps_list:
                action = step.get("action", "")
                expected = step.get("expected", "")
                step_point = ET.SubElement(
                    measurement,
                    f"{{{self._namespace}}}StepPoint",
                    attrib={"name": self._safe_filename(action)},
                )
                if expected:
                    step_point.set("expected", expected)

        # ── Evaluation ───────────────────────────────
        evaluation = ET.SubElement(
            step_el, f"{{{self._namespace}}}Evaluation"
        )

        if tc_type == "PASS":
            # 从信号中获取预期值进行 PassFail 评估
            if signals:
                for sig in signals:
                    expected_val = sig.get("expected_value", "")
                    tolerance = sig.get("tolerance", "0")
                    criterion = ET.SubElement(
                        evaluation,
                        f"{{{self._namespace}}}Criterion",
                        attrib={"type": "PassFail"},
                    )
                    ET.SubElement(
                        criterion,
                        f"{{{self._namespace}}}Expected",
                        attrib={
                            "value": str(expected_val),
                            "tolerance": str(tolerance),
                        },
                    )
            else:
                # 无信号时的通用 Pass
                criterion = ET.SubElement(
                    evaluation,
                    f"{{{self._namespace}}}Criterion",
                    attrib={"type": "PassFail"},
                )
                ET.SubElement(
                    criterion,
                    f"{{{self._namespace}}}Expected",
                    attrib={"value": "PASS", "tolerance": "0"},
                )

        elif tc_type == "FAIL":
            criterion = ET.SubElement(
                evaluation,
                f"{{{self._namespace}}}Criterion",
                attrib={"type": "PassFail"},
            )
            ET.SubElement(
                criterion,
                f"{{{self._namespace}}}Expected",
                attrib={"value": "FAIL", "tolerance": "0"},
            )

        elif tc_type == "ERROR":
            criterion = ET.SubElement(
                evaluation,
                f"{{{self._namespace}}}Criterion",
                attrib={"type": "PassFailError"},
            )
            ET.SubElement(
                criterion,
                f"{{{self._namespace}}}Expected",
                attrib={
                    "value": "ERROR",
                    "tolerance": "0",
                    "description": "Expected test error",
                },
            )

        # ── ParameterSet per TestStep (optional) ────
        tc_params = test_case.get("parameters", [])
        if tc_params:
            ps = ET.SubElement(
                step_el,
                f"{{{self._namespace}}}ParameterSet",
                attrib={"name": f"{tc_id}_Params"},
            )
            for p in tc_params:
                ET.SubElement(
                    ps,
                    f"{{{self._namespace}}}Parameter",
                    attrib={
                        "name": str(p.get("name", "")),
                        "value": str(p.get("value", "")),
                    },
                )

        return step_el

    def generate_parameter_set(self, test_case: TestCase) -> str:
        """生成 dSPACE ParameterSet XML（Simulink 参数映射）。

        Parameters
        ----------
        test_case : dict
            包含 ``parameters`` 字段的测试用例。

        Returns
        -------
        str
            ParameterSet XML 字符串。
        """
        params = test_case.get("parameters", [])
        tc_id = test_case.get("id", "TC_000")

        root = ET.Element(
            f"{{{self._namespace}}}AutoDesk",
            attrib={"version": "2.0"},
        )

        param_set = ET.SubElement(
            root,
            f"{{{self._namespace}}}ParameterSet",
            attrib={"name": f"{tc_id}_ParameterSet"},
        )

        for p in params:
            ET.SubElement(
                param_set,
                f"{{{self._namespace}}}Parameter",
                attrib={
                    "name": str(p.get("name", "")),
                    "value": str(p.get("value", "")),
                },
            )

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    def generate_model_ref(self, model_name: str) -> str:
        """生成 Simulink Model 引用配置 XML。

        dSPACE AutomationDesk 使用 ``.sdf`` (Simulink Data File)
        或 ``.slx`` 作为模型文件引用。

        Parameters
        ----------
        model_name : str
            Simulink 模型文件名（如 ``"model.sdf"`` 或 ``"simulink_model.slx"``）。

        Returns
        -------
        str
            模型引用配置 XML 字符串。
        """
        root = ET.Element(
            f"{{{self._namespace}}}AutoDesk",
            attrib={"version": "2.0"},
        )

        # 自动补全扩展名
        if not any(model_name.endswith(ext) for ext in (".sdf", ".slx", ".mdl")):
            model_name += ".sdf"

        model_config = ET.SubElement(
            root,
            f"{{{self._namespace}}}ModelConfiguration",
            attrib={"name": model_name},
        )

        ET.SubElement(
            model_config,
            f"{{{self._namespace}}}ModelFile",
            attrib={"path": model_name},
        )

        # 默认 MiL (Model-in-the-Loop) 配置
        mil_config = ET.SubElement(
            model_config,
            f"{{{self._namespace}}}MiLConfiguration",
        )
        ET.SubElement(
            mil_config,
            f"{{{self._namespace}}}Mode",
        ).text = "Normal"

        ET.SubElement(
            mil_config,
            f"{{{self._namespace}}}SimulationTime",
        ).text = "10.0"

        ET.SubElement(
            mil_config,
            f"{{{self._namespace}}}SolverType",
        ).text = "FixedStep"

        ET.SubElement(
            mil_config,
            f"{{{self._namespace}}}SolverName",
        ).text = "Auto"

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    # ── Internal helpers ──────────────────────────────────

    def _generate_master_project(
        self, test_cases: List[TestCase]
    ) -> str:
        """生成 AutomationDesk 主项目文件 / 索引。

        包含所有 TestSet 引用和全局配置。
        """
        root = ET.Element(
            f"{{{self._namespace}}}AutoDesk",
            attrib={"version": "2.0"},
        )

        project = ET.SubElement(
            root,
            f"{{{self._namespace}}}Project",
            attrib={
                "name": "yuleOSH_TestProject",
                "description": "Auto-generated by yuleOSH Pipeline",
            },
        )

        # 全局设置
        settings = ET.SubElement(
            project,
            f"{{{self._namespace}}}Settings",
        )

        ET.SubElement(
            settings,
            f"{{{self._namespace}}}DefaultTimeout",
        ).text = "60"

        ET.SubElement(
            settings,
            f"{{{self._namespace}}}MeasurementRate",
        ).text = "100"

        ET.SubElement(
            settings,
            f"{{{self._namespace}}}LogLevel",
        ).text = "Info"

        # 引用的 TestSet 列表
        test_sets = ET.SubElement(
            project,
            f"{{{self._namespace}}}TestSets",
        )

        groups: Dict[str, List[TestCase]] = {}
        for tc in test_cases:
            gid = tc.get("group_id", "TG_DEFAULT")
            groups.setdefault(gid, []).append(tc)

        for gid in groups:
            ET.SubElement(
                test_sets,
                f"{{{self._namespace}}}TestSetRef",
                attrib={
                    "name": groups[gid][0].get("group", f"Group {gid}"),
                    "file": f"testset_{self._safe_filename(gid)}.autoxml",
                },
            )

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    def _generate_parameter_config(
        self, parameters: List[Dict[str, Any]]
    ) -> str:
        """生成 Simulink 参数全局配置文件。"""
        root = ET.Element(
            f"{{{self._namespace}}}AutoDesk",
            attrib={"version": "2.0"},
        )

        config = ET.SubElement(
            root,
            f"{{{self._namespace}}}ParameterConfiguration",
            attrib={"name": "GlobalSimulinkParams"},
        )

        for p in parameters:
            ET.SubElement(
                config,
                f"{{{self._namespace}}}Parameter",
                attrib={
                    "name": str(p.get("name", "")),
                    "value": str(p.get("value", "")),
                },
            )

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    @staticmethod
    def _collect_parameters(test_cases: List[TestCase]) -> List[Dict[str, Any]]:
        """从所有测试用例中收集唯一的 Simulink 参数。"""
        seen: set = set()
        params: List[Dict[str, Any]] = []
        for tc in test_cases:
            for p in tc.get("parameters", []):
                p_name = p.get("name")
                if p_name and p_name not in seen:
                    seen.add(p_name)
                    params.append(p)
        return params

    @staticmethod
    def _collect_models(test_cases: List[TestCase]) -> set:
        """从所有测试用例中收集唯一的模型名称。"""
        models: set = set()
        for tc in test_cases:
            model = tc.get("model")
            if model:
                models.add(model)
        return models

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将标识符转为安全的文件名（仅保留字母、数字、下划线）。"""
        return re.sub(r"[^a-zA-Z0-9_]", "_", name)
