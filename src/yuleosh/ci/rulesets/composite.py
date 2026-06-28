#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Composite.



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

from yuleosh.ci.rulesets.base import BaseRuleSet

from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
from yuleosh.ci.rulesets.gscr_c import GscCRuleSet

# 默认规则定义文件路径（project root / misra-rules.yaml）
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------






# 复合规则集 — 同时加载 C 和 C++ 企标规则


class GscrCompositeRuleSet(BaseRuleSet):
    """GSCR 复合规则集 — 同时加载 C 和 C++ 企标规则。

    作为默认规则集，每次检查时自动运行全部 430 条企标规则。
    """

    _name = "gscr"
    _display_name = "GSCR 企标规则全集 (C + C++, V1.1)"

    def __init__(self):
        self._c_ruleset = GscCRuleSet()
        self._cpp_ruleset = GscCppRuleSet()
        self._defs = self._merge_definitions()

    def _merge_definitions(self) -> dict:
        c_defs = self._c_ruleset.rule_definitions()
        cpp_defs = self._cpp_ruleset.rule_definitions()

        c_count = len(c_defs.get("rules", {}))
        cpp_count = len(cpp_defs.get("rules", {}))

        merged = {
            "meta": {
                "standard": "GSCR",
                "version": "1.1",
                "description": "大研发企标规则汇总 — C + C++",
                "source": "企业标准",
                "total_rules": c_count + cpp_count,
                "languages": ["C", "C++"],
            },
            "rules": {},
        }
        merged["rules"].update(c_defs.get("rules", {}))
        merged["rules"].update(cpp_defs.get("rules", {}))
        return merged

    def supported_tools(self) -> list[str]:
        return ["cppcheck", "clang-tidy"]

    def get_tool_config(self, tool: str) -> dict:
        if tool == "cppcheck":
            return self._c_ruleset.get_tool_config(tool)
        if tool == "clang-tidy":
            return self._cpp_ruleset.get_tool_config(tool)
        return {}

    def get_report_template_config(self) -> dict:
        return {
            "report_title": "GSCR 企标合规报告 V1.1 (C + C++)",
            "classification": ["S0", "S1", "S2"],
            "sections": [
                "Summary",
                "C Rules Violations",
                "C++ Rules Violations",
                "Severity Breakdown",
                "Manual Review Required Rules",
            ],
            "extra": {
                "standard": "GSCR",
                "version": "1.1",
                "languages": ["C", "C++"],
            },
        }

    def classify_rule(self, rule_id: str) -> str:
        # 尝试 C 规则集
        result = self._c_ruleset.classify_rule(rule_id)
        if result != "project_specific":
            return result
        return self._cpp_ruleset.classify_rule(rule_id)

    def rule_definitions(self) -> dict:
        return dict(self._defs)

    def get_gscr_rule(self, gscr_id: str) -> dict:
        """获取单条企标规则的完整定义（从 C 或 C++ 子规则集查找）。"""
        rule = self._c_ruleset.get_gscr_rule(gscr_id)
        if rule:
            return rule
        return self._cpp_ruleset.get_gscr_rule(gscr_id)

    def map_misra_to_gscr(self, misra_rule_id: str) -> list[str]:
        c_result = self._c_ruleset.map_misra_to_gscr(misra_rule_id)
        if c_result:
            return c_result
        return self._cpp_ruleset.map_misra_to_gscr(misra_rule_id)

    def translate_violations(self, violations: list[dict]) -> list[dict]:
        """自动检测违规类型并翻译为企标规则。

        根据 violations 中 rule_id 的命名空间自动选择 C 或 C++ 规则集。
        
        - misra-c2023-*, misra-c2012-* → C 规则集
        - misra-cpp2023-*, misra-cpp2008-* → C++ 规则集
        - 其他 → 查两个规则集
        """
        import re
        c_violations = []
        cpp_violations = []
        other_violations = []
        for v in violations:
            rid = v.get("rule_id", "")
            if re.match(r'misra-cpp', rid, re.I):
                cpp_violations.append(v)
            elif re.match(r'misra-c20', rid, re.I):
                c_violations.append(v)
            else:
                other_violations.append(v)

        result = []
        if c_violations:
            result.extend(self._c_ruleset.translate_violations(c_violations))
        if cpp_violations:
            result.extend(self._cpp_ruleset.translate_violations(cpp_violations))
        # 其他规则 ID：同时查两个规则集，优先取有映射的
        for v in other_violations:
            v = dict(v)
            misra_id = v.get("rule_id", "")
            c_ids = self._c_ruleset.map_misra_to_gscr(misra_id)
            cpp_ids = self._cpp_ruleset.map_misra_to_gscr(misra_id)
            if c_ids:
                v["gscr_rule_ids"] = c_ids
                first_gscr = c_ids[0]
                gscr_def = self._c_ruleset.get_gscr_rule(first_gscr)
                v["gscr_severity"] = gscr_def.get("severity", "S2")
                v["gscr_category"] = gscr_def.get("category", "")
                cn_desc = gscr_def.get("description_cn", "")
                if cn_desc:
                    v["gscr_message_cn"] = cn_desc
            elif cpp_ids:
                v["gscr_rule_ids"] = cpp_ids
                first_gscr = cpp_ids[0]
                gscr_def = self._cpp_ruleset.get_gscr_rule(first_gscr)
                v["gscr_severity"] = gscr_def.get("severity", "S2")
                v["gscr_category"] = gscr_def.get("category", "")
                cn_desc = gscr_def.get("description_cn", "")
                if cn_desc:
                    v["gscr_message_cn"] = cn_desc
            else:
                v["gscr_rule_ids"] = []
                v["gscr_severity"] = "S2"
                v["gscr_category"] = "MISRA (未映射企标)"
            result.append(v)
        return result

    def validate(self) -> list[str]:
        """验证 C 和 C++ 两个子规则集的一致性。"""
        c_errors = self._c_ruleset.validate()
        cpp_errors = self._cpp_ruleset.validate()
        return c_errors + cpp_errors

    def get_rule_count(self) -> dict:
        c_stats = self._c_ruleset.get_rule_count()
        cpp_stats = self._cpp_ruleset.get_rule_count()
        return {
            "total": c_stats["total"] + cpp_stats["total"],
            "C": c_stats,
            "C++": cpp_stats,
        }


# ------------------------------------------------------------------
# ------------------------------------------------------------------

