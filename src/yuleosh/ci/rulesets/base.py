#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Base.



Part of the rulesets/ package split from rulesets.py (Phase 2.2).

"""



#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


import abc
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.rulesets")

# 默认规则定义文件路径（project root / misra-rules.yaml）
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------




class BaseRuleSet(abc.ABC):
    """规则集抽象基类。

    子类必须定义：
      - _name（注册用标识符）
      - _display_name（人类可读名称）
    子类必须实现所有抽象方法。
    """

    # 类级常量 — 供 RulesetRegistry 在无需实例化时读取
    _name: str = ""
    _display_name: str = ""

    @property
    def name(self) -> str:
        """规则集标识符（如 "misra-c2023"）。"""
        return self._name

    @property
    def display_name(self) -> str:
        """显示名（如 "MISRA C:2023"）。"""
        return self._display_name

    @abc.abstractmethod
    def supported_tools(self) -> list[str]:
        """返回本规则集支持的工具名称列表。

        Returns
        -------
        list[str]
            如 ["cppcheck", "clang-tidy"]。
        """
        ...

    @abc.abstractmethod
    def get_tool_config(self, tool: str) -> dict:
        """返回指定工具的配置参数。

        Parameters
        ----------
        tool : str
            工具名称（如 "cppcheck"）。

        Returns
        -------
        dict
            工具的配置字典（如 addon 路径、supressions 等）。
        """
        ...

    @abc.abstractmethod
    def get_report_template_config(self) -> dict:
        """返回报告模板配置。

        Returns
        -------
        dict
            包含 report_title、classification、sections 等字段。
        """
        ...

    @abc.abstractmethod
    def classify_rule(self, rule_id: str) -> str:
        """将规则 ID 分类。

        Parameters
        ----------
        rule_id : str
            规则 ID（如 "misra-c2023-17.7"）。

        Returns
        -------
        str
            分类： "required" | "advisory" | "directive" | "project_specific"。
        """
        ...

    @abc.abstractmethod
    def rule_definitions(self) -> dict:
        """返回规则定义映射。

        Returns
        -------
        dict
            规则 ID → 规则定义字典。
        """
        ...

    def validate(self) -> list[str]:
        """验证规则集定义的一致性和完整性。

        返回所有验证错误的列表（空列表表示完全通过）。
        子类可覆盖此方法实现自定义验证逻辑。
        """
        errors: list[str] = []
        rules = self.rule_definitions().get("rules", {})
        if not rules:
            errors.append("No rules defined in ruleset")
            return errors

        for rid, rdef in rules.items():
            # 检查必要字段
            required_fields = ["title", "severity", "category", "description_en", "check_method", "auto_checkable"]
            for field in required_fields:
                if field not in rdef:
                    errors.append(f"{rid}: missing required field '{field}'")

            # 检查 severity 是否合法
            sev = rdef.get("severity", "").upper()
            if sev not in ("S0", "S1", "S2"):
                errors.append(f"{rid}: invalid severity '{rdef.get("severity", "")}'")

            # 检查 mapped_misra_ids 格式
            misra_ids = rdef.get("mapped_misra_ids", [])
            if misra_ids:
                for mid in misra_ids:
                    if not self._valid_misra_id_format(mid):
                        errors.append(f"{rid}: invalid mapped_misra_id format '{mid}'")
            else:
                # 无 MISRA 映射的规则应提供 references 或 deviation_note
                if not rdef.get("references") and not rdef.get("deviation_note"):
                    errors.append(f"{rid}: no MISRA mapping and missing references/deviation_note")

            # 检查 auto_checkable 类型
            auto_checkable = rdef.get("auto_checkable")
            if not isinstance(auto_checkable, bool):
                errors.append(f"{rid}: 'auto_checkable' should be a boolean, got {type(auto_checkable).__name__}")

        return errors

    @staticmethod
    def _valid_misra_id_format(misra_id: str) -> bool:
        """验证 MISRA ID 格式。

        支持的格式 (调用方已 lower()):
        - misra-c2012/2023-X.Y              标准规则
        - misra-c2012/2023-Dir-X.Y          Directive
        - misra-c2012/2023-mrule-X.Y        Mandatory Rule
        - misra-c2012/2023-cwe-XXX          CWE 映射
        - misra-c2012/2023-X.Y.Z            C 三部分版本（C++ 标准）
        - misra-cpp2008/2023-X.Y.Z          C++ 规则（三部分版本）
        """
        import re
        rid = misra_id.lower()
        patterns = [
            # MISRA C 标准规则: misra-c2012-17.7, misra-c2023-dir-4.1, misra-c2023-mrule-21.2
            r'^misra-c20(?:12|23)-(?:(?:dir|mrule)-)?\d+\.\d+$',
            # MISRA C CWE 映射: misra-c2012-cwe-416
            r'^misra-c20(?:12|23)-cwe-\d+$',
            # MISRA C 三部分版本: misra-c2012-0.1.2, misra-c2012-dir-0.3.1
            r'^misra-c20(?:12|23)-(?:(?:dir|mrule)-)?\d+\.\d+\.\d+$',
            # MISRA C++: misra-cpp2008-0.1.2, misra-cpp2023-0.1.2
            r'^misra-cpp20(?:08|23)-\d+\.\d+\.\d+$',
        ]
        return any(re.match(p, rid) for p in patterns)