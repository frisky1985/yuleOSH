#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Ruleset Plugin System — 插件式规则集管理。

为静态分析工具驱动提供规则集抽象层，支持多规则集注册/查找/实例化。

Usage:
    from yuleosh.ci.rulesets import RulesetRegistry, MisraC2023RuleSet

    # 注册（通常在模块导入时自动完成）
    RulesetRegistry.register(MisraC2023RuleSet, make_default=True)

    # 获取规则集实例
    ruleset = RulesetRegistry.create("misra-c2023")
    ruleset = RulesetRegistry.get_default()

    # 与 tool_drivers 集成
    driver = create_driver("cppcheck", project_dir="...", ruleset=ruleset)
"""

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


# ------------------------------------------------------------------
# Ruleset Registry (Singleton)
# ------------------------------------------------------------------


class RulesetRegistry:
    """规则集注册器（单例）。

    管理所有可用的规则集类，提供注册、创建、列表、默认规则集获取功能。
    """

    _instance: Optional["RulesetRegistry"] = None

    def __new__(cls) -> "RulesetRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry = {}   # type: dict[str, type[BaseRuleSet]]
            cls._instance._default = ""    # type: str
        return cls._instance

    # ---- 注册 API ----

    def register(self, ruleset_cls: type[BaseRuleSet], make_default: bool = False) -> None:
        """注册一个规则集类。

        Parameters
        ----------
        ruleset_cls : type[BaseRuleSet]
            继承 BaseRuleSet 的类。
        make_default : bool
            是否设为默认规则集。
        """
        name = getattr(ruleset_cls, "_name", "")
        if not name:
            raise ValueError(f"RuleSet class {ruleset_cls.__name__} must define _name")
        if not issubclass(ruleset_cls, BaseRuleSet):
            raise TypeError(f"{ruleset_cls.__name__} must inherit BaseRuleSet")

        self._registry[name] = ruleset_cls
        if make_default or not self._default:
            self._default = name
        log.info("Ruleset registered: %s -> %s (default=%s)", name, ruleset_cls.__name__, make_default)

    def create(self, name: str, **kwargs) -> BaseRuleSet:
        """创建已注册规则集的实例。

        Parameters
        ----------
        name : str
            规则集名称（如 "misra-c2023"）。
        **kwargs
            传递给规则集构造函数的参数。

        Returns
        -------
        BaseRuleSet
            规则集实例。

        Raises
        ------
        ValueError
            当 name 未注册时抛出。
        """
        cls_ = self._registry.get(name)
        if cls_ is None:
            supported = ", ".join(sorted(self._registry.keys()))
            raise ValueError(
                f"Unknown ruleset: '{name}'. Registered rulesets: {supported}"
            )
        return cls_(**kwargs)

    def list_rulesets(self) -> list[str]:
        """列出所有已注册的规则集名称。

        Returns
        -------
        list[str]
            规则集名称列表。
        """
        return sorted(self._registry.keys())

    def get_default(self) -> BaseRuleSet:
        """获取默认规则集实例。

        Returns
        -------
        BaseRuleSet
            默认规则集实例。

        Raises
        ------
        ValueError
            当没有注册任何规则集时抛出。
        """
        if not self._default:
            raise ValueError("No default ruleset registered. Call register() first.")
        cls_ = self._registry.get(self._default)
        if cls_ is None:
            raise ValueError(f"Default ruleset '{self._default}' not found in registry")
        return cls_()

    def get_default_name(self) -> str:
        """获取默认规则集名称。"""
        return self._default

    def get_info(self, name: str) -> dict:
        """获取规则集的元信息。

        Parameters
        ----------
        name : str
            规则集名称。

        Returns
        -------
        dict
            包含 name、display_name、supported_tools 的字典。
        """
        cls_ = self._registry.get(name)
        if cls_ is None:
            raise ValueError(f"Unknown ruleset: '{name}'")

        # 创建临时实例获取信息（轻量构造）
        try:
            inst = cls_()
            return {
                "name": inst.name,
                "display_name": inst.display_name,
                "supported_tools": inst.supported_tools(),
            }
        except Exception as e:
            # 即使构造失败，也返回类级信息
            return {
                "name": getattr(cls_, "_name", name),
                "display_name": getattr(cls_, "_display_name", name),
                "supported_tools": [],
                "_error": str(e),
            }


# ------------------------------------------------------------------
# ------------------------------------------------------------------
# General Standard Code Rules (GSCR) — 企标规则集
# ------------------------------------------------------------------

# 企标规则文件路径（相对于项目根目录）
_GSCR_C_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "gscr-c-rules.yaml"
_GSCR_CPP_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "gscr-cpp-rules.yaml"


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
# Auto-register built-in rulesets
# ------------------------------------------------------------------

_registry = RulesetRegistry()
_registry.register(MisraC2023RuleSet)                     # "misra-c2023" — 保留向后兼容
_registry.register(GscCRuleSet)                             # "gscr-c" — C 企标规则
_registry.register(GscCppRuleSet)                           # "gscr-cpp" — C++ 企标规则
_registry.register(GscrCompositeRuleSet, make_default=True) # "gscr" — 默认复合企标规则集
