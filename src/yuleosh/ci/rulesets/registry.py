#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT


"""

CI Rulesets — Registry.



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

from yuleosh.ci.rulesets.composite import GscrCompositeRuleSet
from yuleosh.ci.rulesets.gscr_cpp import GscCppRuleSet
from yuleosh.ci.rulesets.gscr_c import GscCRuleSet
from yuleosh.ci.rulesets.misra import MisraC2023RuleSet

# 默认规则定义文件路径（project root / misra-rules.yaml）
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "misra-rules.yaml"


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------






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
            }# Auto-register built-in rulesets
_registry = RulesetRegistry()
_registry.register(MisraC2023RuleSet)
_registry.register(GscCRuleSet)
_registry.register(GscCppRuleSet)
_registry.register(GscrCompositeRuleSet, make_default=True)