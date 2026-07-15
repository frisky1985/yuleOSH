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

# 默认规则定义文件路径
# 优先级：
# 1. 包内路径（pip install 后 site-packages 下的 misra-rules.yaml）
# 2. 项目根目录回退（开发模式）
_THIS_DIR = Path(__file__).resolve().parent
_SITE_PACKAGES_PATH = _THIS_DIR / "misra-rules.yaml"
_PROJECT_ROOT_PATH = _THIS_DIR.parent.parent.parent.parent.parent / "misra-rules.yaml"
_DEFAULT_RULES_PATH = _SITE_PACKAGES_PATH if _SITE_PACKAGES_PATH.exists() else _PROJECT_ROOT_PATH


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
        """预计算规则 ID → 分类的缓存。

        同时构建 C:2012 → C:2023 的反向兼容查找表。
        """
        self._classify_cache: dict[str, str] = {}
        self._backward_compat: dict[str, str] = {}  # C:2012 ID → C:2023 key
        for rid, defn in self._defs.items():
            if rid == "meta":
                continue

            # 检查是否为 directive（优先级高于 severity）
            if self._is_directive(rid):
                self._classify_cache[rid] = "directive"
            else:
                sev = str(defn.get("severity", "")).lower()
                if sev in ("required", "advisory"):
                    self._classify_cache[rid] = sev
                else:
                    self._classify_cache[rid] = "project_specific"

            # Build backward compat: map C:2012-style IDs to this canonical key
            c2012_ref = defn.get("c2012_ref", "")
            if c2012_ref:
                # Map "Rule X.Y" → "misra-c2023-X.Y"
                self._backward_compat[c2012_ref.lower()] = rid
                # Also map just the numeric part
                import re
                num_match = re.search(r'(\d+\.\d+)', c2012_ref)
                if num_match:
                    self._backward_compat[num_match.group(1)] = rid
                    self._backward_compat[f"rule {num_match.group(1)}"] = rid

            # Also map short numeric ID → canonical key
            import re
            m = re.match(r'^misra-c\d{4}-(.+)$', rid)
            if m:
                short = m.group(1).lower()
                self._backward_compat[short] = rid
                num_m = re.match(r'^(\d+\.\d+)$', short)
                if num_m:
                    self._backward_compat[num_m.group(1)] = rid
                dir_m = re.match(r'^dir[- ]?(\d+\.\d+)$', short, re.IGNORECASE)
                if dir_m:
                    self._backward_compat[dir_m.group(1)] = rid
                    self._backward_compat[f"dir {dir_m.group(1)}".lower()] = rid

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

    def _resolve_rule_id(self, rule_id: str) -> str:
        """将 C:2012 或短格式规则 ID 解析为 C:2023 规范形式。"""
        if not rule_id:
            return ""
        key = rule_id.lower().strip()
        canonical = self._backward_compat.get(key)
        if canonical:
            return canonical

        # 尝试去掉 "MISRA" / "Rule" 前缀
        import re
        stripped = re.sub(r'^(?:misra|c\d{4}|rule)\s*', '', key, flags=re.IGNORECASE).strip()
        if stripped and stripped != key:
            canonical = self._backward_compat.get(stripped)
            if canonical:
                return canonical

        # 尝试纯数字部分
        num_match = re.search(r'(\d+\.\d+)', rule_id)
        if num_match:
            canonical = self._backward_compat.get(num_match.group(1))
            if canonical:
                return canonical

        return rule_id

    def classify_rule(self, rule_id: str) -> str:
        """将 MISRA 规则 ID 分类。

        支持 C:2012 和 C:2023 两种格式的规则 ID。
        优先使用缓存中的分类（从规则定义读取 severity）。
        若规则不在定义中，则按 ID 格式判断是否为 directive。
        """
        if not rule_id:
            return "project_specific"

        # 解析为 C:2023 规范形式
        resolved = self._resolve_rule_id(rule_id)

        # 查缓存
        cached = self._classify_cache.get(resolved)
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