#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Gscr_c.



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
# ------------------------------------------------------------------
# General Standard Code Rules (GSCR) — 企标规则集
# ------------------------------------------------------------------

# 企标规则文件路径（相对于项目根目录）
_GSCR_C_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "gscr-c-rules.yaml"
_GSCR_CPP_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "gscr-cpp-rules.yaml"


class GscCRuleSet(BaseRuleSet):
    """GSCR C 语言企标规则集。

    从 gscr-c-rules.yaml 加载 186 条企标 C 语言规则。
    每条规则映射到对应的 MISRA 规则 ID，cppcheck 输出后自动转换。
    """

    _name = "gscr-c"
    _display_name = "GSCR C (企标 C 语言规则 V1.1)"

    # ── 运行时错误关键词 → GSCR 规则映射表 ──────────────────────
    # MISRA C:2023 Dir-4.1 "Run-time failures shall be minimized" 未细分编号子规则。
    # 本表通过关键词匹配 cppcheck 违规消息文本，实现运行时错误的细分路由。
    # 参考: Polyspace Bug Finder 文档中 Dir-4.1 的 Rationale 分类
    #   (arithmetic errors, pointer arithmetic, array bound errors,
    #    function parameters, pointer dereferencing, dynamic memory)
    _RUNTIME_ERROR_MAP: list[tuple[str, str, str]] = [
        # (keyword, gscr_id, misra_2023_category)
        # ── 注意事项: 关键词按特异性从高到低排列 ──
        # "subnormal" 必须在 "float" 之前，否则 "subnormal float" 会误匹配 "float"
        # "non-terminating call" 必须在 "non-terminating loop" 之前，否则误匹配
        # "division by zero" 必须在 "divide by zero" 之前
        # "out of bounds" 必须在 "array index" 之前（数组越界消息常用 "out of bounds"）
        ("non-terminating call",  "GSCR-C-27.17", "function parameter: non-terminating call (Dir-4.1)"),
        ("non-terminating loop",  "GSCR-C-27.18", "function parameter: non-terminating loop (Dir-4.1)"),
        ("correctness condition", "GSCR-C-27.19", "function parameter: correctness condition (Dir-4.1)"),
        ("subnormal",             "GSCR-C-27.13", "arithmetic error: subnormal float (Dir-4.1)"),
        ("division by zero",      "GSCR-C-27.9",  "arithmetic error: division by zero (Dir-4.1)"),
        ("divide by zero",        "GSCR-C-27.9",  "arithmetic error: division by zero (Dir-4.1)"),
        ("absolute address",      "GSCR-C-27.14", "pointer arithmetic: absolute address (Dir-4.1)"),
        ("out of bounds",         "GSCR-C-27.16", "array bound error: out-of-bounds index (Dir-4.1)"),
        ("array index",           "GSCR-C-27.16", "array bound error: out-of-bounds index (Dir-4.1)"),
        ("infinite loop",         "GSCR-C-27.18", "function parameter: non-terminating loop (Dir-4.1)"),
        ("unreachable",           "GSCR-C-27.8",  "unreachable code (Dir-4.1 / also Rule 2.1)"),
        ("null pointer",          "GSCR-C-27.15", "pointer dereferencing: null/invalid (Dir-4.1)"),
        ("dereference",           "GSCR-C-27.15", "pointer dereferencing: null/invalid (Dir-4.1)"),
        ("standard library",      "GSCR-C-27.20", "standard library: invalid use (Dir-4.1)"),
        ("recursive",             "GSCR-C-27.17", "function parameter: non-terminating call (Dir-4.1)"),
        ("overflow",              "GSCR-C-27.12", "arithmetic error: overflow (Dir-4.1)"),
        ("float",                 "GSCR-C-27.10", "arithmetic error: floating-point operation (Dir-4.1)"),
        ("shift",                 "GSCR-C-27.11", "arithmetic error: invalid shift (Dir-4.1)"),
    ]

    def __init__(self, rules_path: Optional[Path] = None):
        self._rules_path = rules_path or _GSCR_C_RULES_PATH
        self._defs = self._load_rule_definitions()
        self._misra_to_gscr: dict[str, list[str]] = {}
        self._build_reverse_mapping()

    def _build_reverse_mapping(self):
        """构建 MISRA ID → GSCR ID 的逆向映射。

        cppcheck 输出 MISRA 违规，需映射回企标规则 ID 做报告。
        """
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
        """将 MISRA 规则 ID 映射到企标规则 ID 列表。

        支持 MISRA 2012 和 2023 格式，以及 Dir-/MRule- 前缀格式。

        Parameters
        ----------
        misra_rule_id : str
            cppcheck 输出的 MISRA 规则 ID，如 "misra-c2012-17.7"。

        Returns
        -------
        list[str]
            对应的企标规则 ID 列表（可能为空表示无企标映射）。
            对于 Dir-4.1（运行时错误），返回最具体的 GSCR 匹配；
            如需完整列表请使用 _misra_to_gscr 直接查询。
        """
        rid = misra_rule_id.lower().strip()

        # 生成所有可能的格式变体
        variants = [rid]

        # 年份归一化: c2012 → c2023
        rid_2023 = rid.replace("misra-c2012", "misra-c2023")
        if rid_2023 != rid:
            variants.append(rid_2023)

        # 尝试直接查找
        for variant in variants:
            if variant in self._misra_to_gscr:
                return list(self._misra_to_gscr[variant])

        # 容错：处理小数点不匹配（如 misra-c2012-7.2 vs misra-c2023-7.2 但在 YAML 中是 3.x）
        # 这种情况只能通过消息文本匹配，回退到空
        return []

    @classmethod
    def _match_runtime_error_rule(cls, message: str) -> str:
        """根据 cppcheck message 文本匹配最具体的运行时错误 GSCR 规则。

        使用 _RUNTIME_ERROR_MAP 类常量进行关键词匹配。
        关键词列表按特异性从高到低排列（更长的关键词在前）。

        Parameters
        ----------
        message : str
            cppcheck 输出的消息文本。

        Returns
        -------
        str
            最匹配的 GSCR-C-27.x 规则 ID，若完全不匹配则返回 "GSCR-C-4.1"（通用运行时）。
        """
        msg_lower = message.lower()

        # 关键词按特异性从高到低匹配（_RUNTIME_ERROR_MAP 按此顺序定义）
        for keyword, gscr_id, _ in cls._RUNTIME_ERROR_MAP:
            if keyword in msg_lower:
                return gscr_id
        return "GSCR-C-4.1"

    @classmethod
    def _match_runtime_error_category(cls, message: str) -> str:
        """根据消息文本返回对应的 MISRA C:2023 Dir-4.1 错误类别。

        Parameters
        ----------
        message : str
            cppcheck 输出的消息文本。

        Returns
        -------
        str
            Dir-4.1 错误类别描述，如 "arithmetic error: division by zero (Dir-4.1)"。
            若无法匹配则返回空字符串。
        """
        msg_lower = message.lower()
        for keyword, _, category in cls._RUNTIME_ERROR_MAP:
            if keyword in msg_lower:
                return category
        return ""

    def _get_runtime_error_category(self, gscr_id: str) -> str:
        """从 YAML 定义中获取运行时错误规则的 MISRA C:2023 Dir-4.1 类别。"""
        rule_def = self._defs.get("rules", {}).get(gscr_id, {})
        return rule_def.get("misra_2023_category", "")

    def translate_violations(self, violations: list[dict]) -> list[dict]:
        """将 MISRA 违规列表翻译为企标违规列表。

        Parameters
        ----------
        violations : list[dict]
            cppcheck 解析后的违规列表，应包含 "rule_id" 键。

        Returns
        -------
        list[dict]
            增强后的违规列表，增加 gscr_rule_ids 和 gscr_severity 字段。
        """
        result = []
        for v in violations:
            v = dict(v)
            misra_id = v.get("rule_id", "")
            gscr_ids = self.map_misra_to_gscr(misra_id)

            # P0-2: 运行时错误细分 — Dir-4.1 根据 message 匹配具体子规则
            if gscr_ids and len(gscr_ids) > 1 and any(
                "dir-4.1" in mid.lower() for mid in (misra_id,)
            ):
                message = v.get("message", "")
                matched_id = self._match_runtime_error_rule(message)
                # 如果 matched_id 在 gscr_ids 中，使用它；否则保留 GSCR-C-4.1
                if matched_id in gscr_ids:
                    gscr_ids = [matched_id]
                else:
                    # 保底：取 GSCR-C-4.1（如果有）
                    gscr_ids = [gid for gid in gscr_ids if gid == "GSCR-C-4.1"] or [gscr_ids[0]]

            v["gscr_rule_ids"] = gscr_ids
            if gscr_ids:
                # 取第一条映射的企标规则的严重等级
                first_gscr = gscr_ids[0]
                gscr_def = self._defs.get("rules", {}).get(first_gscr, {})
                v["gscr_severity"] = gscr_def.get("severity", "S2")
                v["gscr_category"] = gscr_def.get("category", "")
                # 用企标规则中文名替换消息
                cn_desc = gscr_def.get("description_cn", "")
                if cn_desc:
                    v["gscr_message_cn"] = cn_desc
                # MISRA C:2023 运行时错误类别标注（从 YAML misra_2023_category 字段读取）
                v["misra_2023_category"] = gscr_def.get("misra_2023_category", "")
            else:
                v["gscr_severity"] = "S2"
                v["gscr_category"] = "MISRA (未映射企标)"
            result.append(v)
        return result

    def get_gscr_rule(self, gscr_id: str) -> dict:
        """获取单条企标规则的完整定义。"""
        return self._defs.get("rules", {}).get(gscr_id, {})

    def list_rules_by_severity(self, severity: str) -> list[tuple[str, dict]]:
        """按严重等级列出规则。"""
        result = []
        sev_upper = severity.upper()
        for rid, rdef in self._defs.get("rules", {}).items():
            if rdef.get("severity", "").upper() == sev_upper:
                result.append((rid, rdef))
        return result

    def list_rules_by_category(self, category: str) -> list[tuple[str, dict]]:
        """按分类列出规则。"""
        result = []
        cat_lower = category.lower()
        for rid, rdef in self._defs.get("rules", {}).items():
            if cat_lower in rdef.get("category", "").lower():
                result.append((rid, rdef))
        return result

    # ---- BaseRuleSet interface ----

    def supported_tools(self) -> list[str]:
        return ["cppcheck"]

    def get_tool_config(self, tool: str) -> dict:
        if tool == "cppcheck":
            return {
                "addon": "misra",
                "enable": "all",
                "suppress": ["missingInclude"],
                "rules_path": str(self._rules_path),
            }
        if tool == "clang-tidy":
            # GSCR C++ 部分规则可通过 clang-tidy 检测
            return {
                "checks": "*",
                "extra_args": ["-extra-arg=-std=c11"],
            }
        return {}

    def get_report_template_config(self) -> dict:
        return {
            "report_title": "GSCR C 企标合规报告 V1.1",
            "classification": ["S0", "S1", "S2"],
            "sections": [
                "Summary",
                "Violations by GSCR Rule",
                "Violations by Category",
                "Severity Breakdown (S0/S1/S2)",
                "MISRA-to-GSCR Mapping",
                "Manual Review Required Rules",
            ],
            "extra": {
                "standard": "GSCR",
                "version": "1.1",
                "language": "C",
            },
        }

    def classify_rule(self, rule_id: str) -> str:
        """将企标规则 ID 分类。

        S0 → critical (必须修复)
        S1 → required (必须修复或评审偏离)
        S2 → advisory (建议修复)
        """
        if not rule_id:
            return "project_specific"
        rule_def = self._defs.get("rules", {}).get(rule_id, {})
        sev = str(rule_def.get("severity", "S2")).upper()
        mapping = {"S0": "critical", "S1": "required", "S2": "advisory"}
        return mapping.get(sev, "project_specific")

    def rule_definitions(self) -> dict:
        return dict(self._defs)

    def get_rule_count(self) -> dict:
        """获取规则统计。"""
        rules = self._defs.get("rules", {})
        s0 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S0")
        s1 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S1")
        s2 = sum(1 for r in rules.values() if r.get("severity", "").upper() == "S2")
        auto = sum(1 for r in rules.values() if r.get("auto_checkable"))
        manual = sum(1 for r in rules.values() if not r.get("auto_checkable"))
        categories = set()
        for r in rules.values():
            cat = r.get("category", "")
            if cat:
                categories.add(cat)
        return {
            "total": len(rules),
            "S0": s0,
            "S1": s1,
            "S2": s2,
            "auto_checkable": auto,
            "manual_review": manual,
            "categories": sorted(categories),
        }

    def validate(self) -> list[str]:
        """验证 C 规则集的一致性。"""
        errors = BaseRuleSet.validate(self)
        # C 规则集额外检查: ID 前缀一致性
        rules = self._defs.get("rules", {})
        for rid in rules:
            if rid.startswith("GSCR-") and not rid.startswith("GSCR-C-"):
                errors.append(f"{rid}: C rule ID missing 'C-' prefix")
        return errors

    def _load_rule_definitions(self) -> dict:
        """从 YAML 文件加载企标规则定义。"""
        path = self._rules_path
        if not path.exists():
            log.warning("GSCR C rules file not found: %s", path)
            return {"meta": {}, "rules": {}}

        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                log.warning("Empty GSCR C rules file: %s", path)
                return {"meta": {}, "rules": {}}
            return data
        except ImportError:
            log.warning("PyYAML not installed — cannot load GSCR rules")
            return {"meta": {}, "rules": {}}
        except Exception as e:
            log.warning("Failed to load GSCR C rules from %s: %s", path, e)
            return {"meta": {}, "rules": {}}