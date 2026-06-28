#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Gscr_cpp.



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

# 默认规则定义文件路径（project root / misra-rules.yaml）
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------






_GSCR_CPP_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "gscr-cpp-rules.yaml"

class GscCppRuleSet(BaseRuleSet):
    """GSCR C++ 语言企标规则集。

    从 gscr-cpp-rules.yaml 加载 244 条企标 C++ 语言规则。
    部分规则映射到 MISRA C++:2023，可通过 clang-tidy 检测。
    """

    _name = "gscr-cpp"
    _display_name = "GSCR C++ (企标 C++ 语言规则 V1.1)"

    def __init__(self, rules_path: Optional[Path] = None):
        self._rules_path = rules_path or _GSCR_CPP_RULES_PATH
        self._defs = self._load_rule_definitions()
        self._misra_to_gscr: dict[str, list[str]] = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        """构建 MISRA C++ ID → GSCR CPP ID 的逆向映射。"""
        self._misra_to_gscr = {}
        if not self._defs or "rules" not in self._defs:
            return
        for gscr_id, rule_def in self._defs.get("rules", {}).items():
            mapped = rule_def.get("mapped_misra_ids", [])
            for misra_id in mapped:
                misra_lower = misra_id.lower().strip()
                if misra_lower not in self._misra_to_gscr:
                    self._misra_to_gscr[misra_lower] = []
                if gscr_id not in self._misra_to_gscr[misra_lower]:
                    self._misra_to_gscr[misra_lower].append(gscr_id)

    def map_misra_to_gscr(self, misra_rule_id: str) -> list[str]:
        """将 MISRA C++ 规则 ID 映射到企标 C++ 规则 ID。"""
        rid = misra_rule_id.lower().strip()
        for variant in [rid, rid.replace("misra-cpp2008", "misra-cpp2023")]:
            result = self._misra_to_gscr.get(variant, [])
            if result:
                return result
        return []

    def translate_violations(self, violations: list[dict]) -> list[dict]:
        """将 MISRA C++ 违规列表翻译为企标违规列表。"""
        result = []
        for v in violations:
            v = dict(v)
            misra_id = v.get("rule_id", "")
            gscr_ids = self.map_misra_to_gscr(misra_id)
            v["gscr_rule_ids"] = gscr_ids
            if gscr_ids:
                first_gscr = gscr_ids[0]
                gscr_def = self._defs.get("rules", {}).get(first_gscr, {})
                v["gscr_severity"] = gscr_def.get("severity", "S2")
                v["gscr_category"] = gscr_def.get("category", "")
                cn_desc = gscr_def.get("description_cn", "")
                if cn_desc:
                    v["gscr_message_cn"] = cn_desc
            else:
                v["gscr_severity"] = "S2"
                v["gscr_category"] = "MISRA C++ (未映射企标)"
            result.append(v)
        return result

    # ---- BaseRuleSet interface ----

    def supported_tools(self) -> list[str]:
        return ["clang-tidy", "cppcheck"]

    def get_tool_config(self, tool: str) -> dict:
        if tool == "clang-tidy":
            return {
                "checks": "clang-analyzer-*,cppcoreguidelines-*,*",
                "extra_args": ["-extra-arg=-std=c++17"],
            }
        if tool == "cppcheck":
            return {
                "addon": "misra",
                "enable": "all",
                "suppress": ["missingInclude"],
            }
        return {}

    def get_report_template_config(self) -> dict:
        return {
            "report_title": "GSCR C++ 企标合规报告 V1.1",
            "classification": ["S0", "S1", "S2"],
            "sections": [
                "Summary",
                "Violations by GSCR C++ Rule",
                "Severity Breakdown (S0/S1/S2)",
                "Manual Review Required Rules",
            ],
            "extra": {
                "standard": "GSCR",
                "version": "1.1",
                "language": "C++",
            },
        }

    def classify_rule(self, rule_id: str) -> str:
        if not rule_id:
            return "project_specific"
        rule_def = self._defs.get("rules", {}).get(rule_id, {})
        sev = str(rule_def.get("severity", "S2")).upper()
        mapping = {"S0": "critical", "S1": "required", "S2": "advisory"}
        return mapping.get(sev, "project_specific")

    def rule_definitions(self) -> dict:
        return dict(self._defs)

    def get_rule_count(self) -> dict:
        rules = self._defs.get("rules", {})
        s0 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S0")
        s1 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S1")
        s2 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S2")
        auto = sum(1 for r in rules.values() if r.get("auto_checkable"))
        manual = sum(1 for r in rules.values() if not r.get("auto_checkable"))
        return {
            "total": len(rules),
            "S0": s0,
            "S1": s1,
            "S2": s2,
            "auto_checkable": auto,
            "manual_review": manual,
        }

    def get_gscr_rule(self, gscr_id: str) -> dict:
        """获取单条企标 C++ 规则的完整定义。"""
        return self._defs.get("rules", {}).get(gscr_id, {})

    def list_rules_by_severity(self, severity: str) -> list[tuple[str, dict]]:
        """按严重等级列出 C++ 规则。"""
        result = []
        sev_upper = severity.upper()
        for rid, rdef in self._defs.get("rules", {}).items():
            if rdef.get("severity", "").upper() == sev_upper:
                result.append((rid, rdef))
        return result

    def list_rules_by_category(self, category: str) -> list[tuple[str, dict]]:
        """按分类列出 C++ 规则。"""
        result = []
        cat_lower = category.lower()
        for rid, rdef in self._defs.get("rules", {}).items():
            if cat_lower in rdef.get("category", "").lower():
                result.append((rid, rdef))
        return result

    def validate(self) -> list[str]:
        """验证 C++ 规则集的一致性。"""
        return BaseRuleSet.validate(self)

    def _load_rule_definitions(self) -> dict:
        path = self._rules_path
        if not path.exists():
            log.warning("GSCR C++ rules file not found: %s", path)
            return {"meta": {}, "rules": {}}
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return {"meta": {}, "rules": {}}
            return data
        except ImportError:
            log.warning("PyYAML not installed — cannot load GSCR C++ rules")
            return {"meta": {}, "rules": {}}
        except Exception as e:
            log.warning("Failed to load GSCR C++ rules from %s: %s", path, e)
            return {"meta": {}, "rules": {}}