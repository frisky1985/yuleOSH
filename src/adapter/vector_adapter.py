"""
Vector CANoe Adapter — 将 yuleOSH Pipeline 产出的测试用例
转化为 Vector CANoe 兼容的 XML Test Feature 格式。

输出格式：
  - CANoe Test Feature XML (*.can / *.xml)
  - CANoe Simulation Setup XML（基础配置）
  - CAPL 脚本（可选简化版，嵌入 XML 或独立文件）

依赖：xml.etree.ElementTree（Python 标准库，无额外依赖）
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────────────────
# XML 声明 & 辅助
# ──────────────────────────────────────────────────────────

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'

_CANOE_NS = "http://vector.com/canoe/testfeature"
_NSMAP = {"": _CANOE_NS}

# Register namespace so ET won't produce ns0: prefixes
ET.register_namespace("", _CANOE_NS)


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Pretty-print an ElementTree — adds whitespace indentation in-place."""
    indent_str = "  "
    i = "\n" + level * indent_str
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + indent_str
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


# ──────────────────────────────────────────────────────────
# Test Case 输入模型（TypedDict 风格）
# ──────────────────────────────────────────────────────────

TestCase = Dict[str, Any]
"""测试用例 dict 结构：:

    {
        "id": str,          # e.g. "TC_001"
        "title": str,       # e.g. "CAN Bus Communication"
        "group": str,       # e.g. "Smoke Tests"   (optional)
        "group_id": str,    # e.g. "TG_001"         (optional)
        "type": str,        # "PASS" | "FAIL" | "ERROR"
        "description": str, # 测试描述 (optional)
        "steps": list[dict],# 测试步骤 (optional)
        "signals": list[dict], # 关联信号 (optional)
        "capl": str,        # 自定义 CAPL 代码 (optional)
    }
"""


# ──────────────────────────────────────────────────────────
# VectorCANoeAdapter
# ──────────────────────────────────────────────────────────

class VectorCANoeAdapter:
    """Adapter: yuleOSH test cases → CANoe XML Test Feature.

    Typical usage::

        adapter = VectorCANoeAdapter()
        output = adapter.convert(test_cases, output_dir="/tmp/canoe_out")

    This generates one ``.can`` XML file per test group, plus a
    ``simulation_setup.xml`` and optional ``*.can`` files for standalone
    CAPL scripts.
    """

    def __init__(self, namespace: str = _CANOE_NS):
        self._namespace = namespace

    # ── Public API ────────────────────────────────────────

    def convert(self, test_cases: List[TestCase], output_dir: str) -> str:
        """将测试用例列表转换为 CANoe XML Test Feature 文件。

        Parameters
        ----------
        test_cases : list[dict]
            测试用例列表，每个元素符合 TestCase 结构。
        output_dir : str
            输出目录路径（会自动创建）。

        Returns
        -------
        str
            生成的 CANoe XML 文件路径列表（以换行符分隔）。
        """
        os.makedirs(output_dir, exist_ok=True)

        generated: List[str] = []

        # 1) 生成 Test Module XML
        xml_content = self.generate_test_module(test_cases)
        module_path = os.path.join(output_dir, "test_module.can")
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        generated.append(module_path)

        # 2) 生成 Simulation Setup XML
        signals = self._collect_signals(test_cases)
        sim_xml = self._generate_simulation_setup(signals)
        sim_path = os.path.join(output_dir, "simulation_setup.xml")
        with open(sim_path, "w", encoding="utf-8") as f:
            f.write(sim_xml)
        generated.append(sim_path)

        # 3) 提取独立的 CAPL 文件（如果测试用例包含自定义 CAPL）
        for tc in test_cases:
            capl_code = self.generate_capl(tc)
            if capl_code.strip():
                capl_path = os.path.join(
                    output_dir, f"{self._safe_filename(tc.get('id', 'unknown'))}.can"
                )
                with open(capl_path, "w", encoding="utf-8") as f:
                    f.write(capl_code)
                generated.append(capl_path)

        return "\n".join(generated)

    def generate_test_module(self, test_cases: List[TestCase]) -> str:
        """生成 CANoe Test Module XML（含 TestFeatureSet 结构）。

        输出是符合 CANoe XML Test Feature 格式的完整 XML 文档。
        """
        root = ET.Element(f"{{{self._namespace}}}testmodule")

        # 将测试用例按 group 分组
        groups: Dict[str, List[TestCase]] = {}
        for tc in test_cases:
            gid = tc.get("group_id", "TG_DEFAULT")
            groups.setdefault(gid, []).append(tc)

        for gid, members in groups.items():
            group_title = members[0].get("group", f"Group {gid}")
            tg = ET.SubElement(
                root, f"{{{self._namespace}}}testgroup",
                attrib={"ident": gid, "title": group_title},
            )

            for tc in members:
                tc_el = ET.SubElement(
                    tg, f"{{{self._namespace}}}testcase",
                    attrib={
                        "ident": tc.get("id", "TC_000"),
                        "title": tc.get("title", "Untitled"),
                    },
                )

                # --- type attribute (PASS / FAIL / ERROR) ---
                result_type = tc.get("type", "PASS")
                tc_el.set("type", result_type)

                # --- description ---
                desc = tc.get("description", "")
                if desc:
                    desc_el = ET.SubElement(
                        tc_el, f"{{{self._namespace}}}description"
                    )
                    desc_el.text = desc

                # --- CAPL block ---
                capl_code = self.generate_capl(tc)
                if capl_code.strip():
                    capl_el = ET.SubElement(
                        tc_el, f"{{{self._namespace}}}capl"
                    )
                    capl_el.text = capl_code

                # --- steps (optional, for documentation) ---
                steps = tc.get("steps", [])
                if steps:
                    steps_el = ET.SubElement(
                        tc_el, f"{{{self._namespace}}}steps"
                    )
                    for i, step in enumerate(steps, 1):
                        step_el = ET.SubElement(
                            steps_el, f"{{{self._namespace}}}step",
                            attrib={"index": str(i)},
                        )
                        action = step.get("action", "")
                        expected = step.get("expected", "")
                        step_el.text = f"{action} → {expected}"

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    def generate_capl(self, test_case: TestCase) -> str:
        """为单个测试用例生成 CAPL 脚本。

        如果测试用例已提供 ``capl`` 字段则直接返回；
        否则根据测试用例类型自动生成简化 CAPL 框架代码。
        """
        custom_capl = test_case.get("capl")
        if custom_capl and custom_capl.strip():
            return custom_capl

        tc_id = test_case.get("id", "TC_000")
        tc_type = test_case.get("type", "PASS")
        signals = test_case.get("signals", [])

        lines: List[str] = []
        lines.append(f"/* Auto-generated CAPL for {tc_id} */")
        lines.append("")

        # TestCase function — CANoe Test Feature entry point
        lines.append(f"void {tc_id}()")
        lines.append("{")

        # Basic signal checks if signals are provided
        if signals:
            lines.append("  // --- Signal checks ---")
            for sig in signals:
                sig_name = sig.get("name", "UnknownSignal")
                expected_val = sig.get("expected_value", "1")
                lines.append(f"  if (${{{sig_name}}} != {expected_val})")
                lines.append("  {")
                lines.append(
                    f'    TestStep("Check", "{sig_name} value mismatch");'
                )
                lines.append("    testStepFail();")
                lines.append("    return;")
                lines.append("  }")
                lines.append("  else")
                lines.append("  {")
                lines.append(
                    f'    TestStep("Check", "{sig_name} = {expected_val} — OK");'
                )
                lines.append("  }")
                lines.append("")

        # Result
        if tc_type == "PASS":
            lines.append("  TestStep(\"Result\", \"Test PASSED\");")
            lines.append("  testStepPass();")
        elif tc_type == "FAIL":
            lines.append("  TestStep(\"Result\", \"Test FAILED (expected)\");")
            lines.append("  testStepFail();")
        elif tc_type == "ERROR":
            lines.append("  TestStep(\"Result\", \"Test ERROR (expected)\");")
            lines.append("  testStepFail();")
        else:
            lines.append("  TestStep(\"Result\", \"Test completed\");")

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def generate_dbc_map(self, signals: List[Dict[str, Any]]) -> str:
        """生成 CAN DBC 信号映射的 XML 配置。

        Parameters
        ----------
        signals : list[dict]
            信号定义列表，每个元素包含 ``name``, ``message``, ``start_bit``,
            ``length``, ``factor``, ``offset``, ``min``, ``max``, ``unit``。

        Returns
        -------
        str
            DBC 信号映射 XML 字符串。
        """
        root = ET.Element(f"{{{self._namespace}}}dbc_map")

        for sig in signals:
            sig_el = ET.SubElement(
                root, f"{{{self._namespace}}}signal",
                attrib={
                    "name": sig.get("name", ""),
                    "message": sig.get("message", ""),
                },
            )

            # Optional metadata
            for attr in ("start_bit", "length", "factor", "offset",
                         "min", "max", "unit"):
                val = sig.get(attr)
                if val is not None:
                    attr_el = ET.SubElement(
                        sig_el, f"{{{self._namespace}}}{attr}"
                    )
                    attr_el.text = str(val)

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    # ── Internal helpers ──────────────────────────────────

    def _collect_signals(self, test_cases: List[TestCase]) -> List[Dict[str, Any]]:
        """从测试用例列表中收集所有唯一的信号定义。"""
        seen: set = set()
        signals: List[Dict[str, Any]] = []
        for tc in test_cases:
            for sig in tc.get("signals", []):
                sig_name = sig.get("name")
                if sig_name and sig_name not in seen:
                    seen.add(sig_name)
                    signals.append(sig)
        return signals

    def _generate_simulation_setup(
        self, signals: List[Dict[str, Any]]
    ) -> str:
        """生成基础的 CANoe Simulation Setup XML 配置。"""
        root = ET.Element(
            f"{{{self._namespace}}}simulation_setup",
            attrib={"version": "1.0"},
        )

        # Bus configuration
        bus_config = ET.SubElement(
            root, f"{{{self._namespace}}}bus_configuration"
        )
        ET.SubElement(
            bus_config, f"{{{self._namespace}}}can",
            attrib={
                "channel": "1",
                "baudrate": "500000",
                "mode": "CAN20",
            },
        )

        # Database references (if signals reference DBC files)
        db_refs: set = set()
        for sig in signals:
            db = sig.get("dbc", "")
            if db:
                db_refs.add(db)

        if db_refs:
            databases = ET.SubElement(
                root, f"{{{self._namespace}}}databases"
            )
            for db in sorted(db_refs):
                ET.SubElement(
                    databases, f"{{{self._namespace}}}database",
                    attrib={"path": db},
                )

        # Test nodes
        test_nodes = ET.SubElement(
            root, f"{{{self._namespace}}}test_nodes"
        )
        ET.SubElement(
            test_nodes, f"{{{self._namespace}}}test_node",
            attrib={
                "name": "TestModuleExecutor",
                "type": "test_module",
            },
        )

        _indent(root)
        return _XML_DECLARATION + ET.tostring(root, encoding="unicode")

    @staticmethod
    def _safe_filename(name: str) -> str:
        """将标识符转为安全的文件名（仅保留字母、数字、下划线）。"""
        return re.sub(r"[^a-zA-Z0-9_]", "_", name)
