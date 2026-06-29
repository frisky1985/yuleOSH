#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Misra.



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
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "misra-rules.yaml"


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------






# ------------------------------------------------------------------
# MISRA C:2023 RuleSet
# ------------------------------------------------------------------


class MisraC2023RuleSet(BaseRuleSet):
    """MISRA C:2023 规则集。

    从 misra-rules.yaml 加载规则定义。
    """

    _name = "misra-c2023"
    _display_name = "MISRA C:2023"

    def __init__(self, rules_path: Optional[Path] = None):
        self._rules_path = rules_path or _DEFAULT_RULES_PATH
        self._defs = self._load_rule_definitions()
        self._init_classification_cache()

    def _init_classification_cache(self):
        """预计算规则 ID → 分类的缓存。"""
        self._classify_cache: dict[str, str] = {}
        for rid, defn in self._defs.items():
            if rid == "meta":
                continue
            sev = str(defn.get("severity", "")).lower()
            if sev in ("required", "advisory"):
                self._classify_cache[rid] = sev
            else:
                # 检查是否为 directive
                if self._is_directive(rid):
                    self._classify_cache[rid] = "directive"
                else:
                    self._classify_cache[rid] = "project_specific"

    @staticmethod
    def _is_directive(rule_id: str) -> bool:
        """判断规则 ID 是否为 directive。"""
        if not rule_id:
            return False
        rid_lower = rule_id.lower()
        if rid_lower.startswith("dir") or "dir-" in rid_lower:
            return True
        last_segment = rule_id.split("-")[-1] if "-" in rule_id else rule_id
        if last_segment.startswith("Dir") or last_segment.startswith("dir"):
            return True
        return False

    # ---- BaseRuleSet interface ----

    def supported_tools(self) -> list[str]:
        return ["cppcheck", "clang-tidy"]

    def get_tool_config(self, tool: str) -> dict:
        """返回工具的 MISRA 配置。

        cppcheck 使用 --addon=misra，clang-tidy 使用 misra-c2023-* 检查。
        """
        if tool == "cppcheck":
            return {
                "addon": "misra",
                "enable": "all",
                "suppress": ["missingInclude"],
                "rules_path": str(self._rules_path),
            }
        if tool == "clang-tidy":
            return {
                "checks": "misra-c2023-*",
            }
        return {}

    def get_report_template_config(self) -> dict:
        return {
            "report_title": "MISRA C:2023 Compliance Report",
            "classification": ["required", "advisory", "directive", "project_specific"],
            "sections": ["Summary", "Violations by Rule", "Deviation Overview", "3-Way Traceability"],
        }

    def classify_rule(self, rule_id: str) -> str:
        """将 MISRA 规则 ID 分类。

        优先使用缓存中的分类（从规则定义读取 severity）。
        若规则不在定义中，则按 ID 格式判断是否为 directive。
        """
        if not rule_id:
            return "project_specific"
        cached = self._classify_cache.get(rule_id)
        if cached:
            return cached
        if self._is_directive(rule_id):
            return "directive"
        return "project_specific"

    def rule_definitions(self) -> dict:
        return dict(self._defs)

    # ---- 内部方法 ----

    def _load_rule_definitions(self) -> dict:
        """从 YAML 文件加载规则定义。"""
        path = self._rules_path
        if not path.exists():
            log.warning("MISRA rules file not found: %s", path)
            return {}

        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data or "meta" not in data:
                log.warning("Invalid MISRA rules file format: %s", path)
                return {}
            return data
        except ImportError:
            log.warning("PyYAML not installed — cannot load rule definitions")
            return {}
        except Exception as e:
            log.warning("Failed to load MISRA rules from %s: %s", path, e)
            return {}