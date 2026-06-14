# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Adapter Module — Vector CANoe / dSPACE AutomationDesk 适配器。

Adapter Pattern 实现，将 Pipeline 产出的测试用例转化为各平台可执行格式。
与核心 Pipeline 完全解耦，可独立使用和扩展。

共享工具函数
--------------
- ``_XML_DECLARATION`` — 标准 XML 声明头
- ``_indent()`` — 格式化 XML ElementTree 缩进
- ``get_adapter()`` — 工厂函数，根据名称创建适配器实例
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List

# ──────────────────────────────────────────────────────────
# 共享常量
# ──────────────────────────────────────────────────────────

_XML_DECLARATION: str = '<?xml version="1.0" encoding="UTF-8"?>\n'

# ──────────────────────────────────────────────────────────
# 共享工具函数
# ──────────────────────────────────────────────────────────


def _indent(elem: ET.Element, level: int = 0) -> None:
    """Pretty-print an ElementTree — 就地添加空白缩进。"""
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
# TestCase 类型别名（所有适配器共享的输入模型）
# ──────────────────────────────────────────────────────────

TestCase = Dict[str, Any]
"""测试用例 dict 结构：:

    {
        "id": str,          # e.g. "TC_001"
        "title": str,       # e.g. "CAN Bus Communication"
        "group": str,       # e.g. "Smoke Tests"     (optional)
        "group_id": str,    # e.g. "TG_001"          (optional)
        "type": str,        # "PASS" | "FAIL" | "ERROR"
        "description": str, # 测试描述               (optional)
        "steps": list[dict],# 测试步骤               (optional)
        "signals": list[dict], # 关联信号             (optional)
        "capl": str,        # 自定义 CAPL 代码        (optional, CANoe only)
        "parameters": list[dict], # Simulink 参数     (optional, dSPACE only)
        "model": str,       # Simulink 模型引用        (optional, dSPACE only)
    }
"""

# ──────────────────────────────────────────────────────────
# 工厂函数
# ──────────────────────────────────────────────────────────


def get_adapter(name: str, **kwargs: Any):
    """工厂函数 — 根据名称创建适配器。

    Parameters
    ----------
    name : str
        适配器类型：``"canoe"`` (Vector CANoe) | ``"automationdesk"`` (dSPACE)。
    **kwargs
        传递给适配器构造函数的额外参数。

    Returns
    -------
    VectorCANoeAdapter | DSAPCEAutomationDeskAdapter

    Raises
    ------
    ValueError
        未知的适配器名称。
    """
    if name == "canoe":
        from .vector_adapter import VectorCANoeAdapter

        return VectorCANoeAdapter(**kwargs)
    elif name == "automationdesk":
        from .dspace_adapter import DSAPCEAutomationDeskAdapter

        return DSAPCEAutomationDeskAdapter(**kwargs)
    else:
        raise ValueError(
            f"Unknown adapter: {name!r}. "
            f"Supported: 'canoe', 'automationdesk'"
        )


# ──────────────────────────────────────────────────────────
# 导出
# ──────────────────────────────────────────────────────────

from .vector_adapter import VectorCANoeAdapter  # noqa: E402, F401
from .dspace_adapter import DSAPCEAutomationDeskAdapter  # noqa: E402, F401

__all__ = [
    "VectorCANoeAdapter",
    "DSAPCEAutomationDeskAdapter",
    "get_adapter",
    "_XML_DECLARATION",
    "_indent",
    "TestCase",
]
