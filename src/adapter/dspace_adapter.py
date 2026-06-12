"""
dSPACE AutomationDesk Adapter — 占位模块。

Wave 3 实现：将 Pipeline 产出的测试用例转化为 dSPACE AutomationDesk
可执行的格式（.m / .xml 自动化序列）。

当前版本仅为占位桩 (stub)，保持与 VectorCANoeAdapter 一致的接口签名。
"""

from __future__ import annotations

from typing import Any, Dict, List


class DSAPCEAdapter:
    """dSPACE AutomationDesk 适配器（占位，Wave 3 实现）。

    接口与 VectorCANoeAdapter 保持一致：
    - ``convert()`` — 转换测试用例为 dSPACE 兼容格式
    - ``generate_test_module()`` — 生成 AutomationDesk 测试模块
    - ``generate_capl()`` — 占位（dSPACE 使用 MATLAB/Simulink 脚本）
    - ``generate_dbc_map()`` — 生成信号映射配置
    """

    def convert(self, test_cases: List[Dict[str, Any]], output_dir: str) -> str:
        """转换测试用例 → dSPACE AutomationDesk 格式。

        .. warning::
           尚未实现。当前返回占位消息。
        """
        import warnings
        warnings.warn(
            "DSAPCEAdapter.convert() is a stub — Wave 3 implementation pending."
        )
        return f"[stub] DSAPCEAdapter.convert called, output_dir={output_dir}"

    def generate_test_module(self, test_cases: List[Dict[str, Any]]) -> str:
        """占位：生成 AutomationDesk 测试模块。"""
        return "<!-- DSAPCEAdapter stub: generate_test_module not yet implemented -->"

    def generate_capl(self, test_case: Dict[str, Any]) -> str:
        """占位：dSPACE 适配器不使用 CAPL。"""
        return "/* DSAPCEAdapter stub: dSPACE does not use CAPL */"

    def generate_dbc_map(self, signals: List[Dict[str, Any]]) -> str:
        """占位：生成 dSPACE 兼容的信号映射。"""
        return "<!-- DSAPCEAdapter stub: generate_dbc_map not yet implemented -->"
