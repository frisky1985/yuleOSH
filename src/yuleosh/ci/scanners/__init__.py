# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH CI — 外部扫描器适配层（ScannerAdapter，2026-08-19）。

统一消费任何 MISRA 扫描器输出（cppcheck 默认 / Parasoft / QAC / LDRA / MCP）。

使用：
    from yuleosh.ci.scanners import ScannerRegistry
    scanner = ScannerRegistry().get("cppcheck")
    result = scanner.run(project_dir=..., config=misra_cfg, target_files=c_files)
    violations = scanner.normalize(scanner.parse(result.raw_output))
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Self

from yuleosh.ci.scanners.base import (
    ScannerAdapter,
    ScannerResult,
    Violation,
    canonicalize_rule_id,
    extract_rule_number,
    violations_to_dicts,
)

log = logging.getLogger("ci.scanners")


class ScannerRegistry:
    """扫描器注册表（单例，模式与 RulesetRegistry 一致）。

    管理所有可用扫描器适配器类，提供注册、创建、获取、列表。
    未配置的工具 detect() 返回 False 且不抛错（验收标准 #2）。
    """

    _instance: ClassVar[ScannerRegistry | None] = None

    def __new__(cls) -> Self:
        inst = cls._instance
        if inst is None:
            inst = super().__new__(cls)
            cls._instance = inst
        return inst

    def __init__(self) -> None:
        # 单例：__init__ 每次实例化都会调用，用 hasattr 守卫只初始化一次
        if not hasattr(self, "_registry"):
            self._registry: dict[str, type[ScannerAdapter]] = {}
            self._default: str = ""
            self._register_builtins()

    def _register_builtins(self) -> None:
        """注册内置适配器（P1+P2+P3）。"""
        from yuleosh.ci.scanners.cppcheck_adapter import CppcheckScannerAdapter
        from yuleosh.ci.scanners.ldra_adapter import LdraScannerAdapter
        from yuleosh.ci.scanners.mcp_adapter import McpScannerAdapter
        from yuleosh.ci.scanners.parasoft_adapter import ParasoftScannerAdapter
        from yuleosh.ci.scanners.qac_adapter import QacScannerAdapter

        self.register(CppcheckScannerAdapter, make_default=True)
        self.register(ParasoftScannerAdapter)
        self.register(QacScannerAdapter)
        self.register(LdraScannerAdapter)
        self.register(McpScannerAdapter)

    # ---- 注册 API ----

    def register(self, adapter_cls: type[ScannerAdapter], make_default: bool = False) -> None:
        """注册一个扫描器适配器类。"""
        name = getattr(adapter_cls, "name", "")
        if not name:
            raise ValueError(f"ScannerAdapter class {adapter_cls.__name__} must define name")
        if not issubclass(adapter_cls, ScannerAdapter):
            raise TypeError(f"{adapter_cls.__name__} must inherit ScannerAdapter")

        self._registry[name] = adapter_cls
        if make_default or not self._default:
            self._default = name
        log.info("Scanner registered: %s -> %s (default=%s)",
                 name, adapter_cls.__name__, make_default)

    def create(self, name: str, **kwargs: Any) -> ScannerAdapter:
        """创建已注册适配器的实例。"""
        cls_ = self._registry.get(name)
        if cls_ is None:
            supported = ", ".join(sorted(self._registry.keys()))
            raise ValueError(
                f"Unknown scanner: '{name}'. Registered scanners: {supported}"
            )
        return cls_(**kwargs)

    def get(self, name: str | None = None) -> ScannerAdapter:
        """获取适配器实例。name 缺省 = 默认（cppcheck）。"""
        resolved: str = name or self._default
        return self.create(resolved)

    def names(self) -> list[str]:
        """所有已注册扫描器名（排序）。"""
        return sorted(self._registry.keys())

    def available(self) -> list[str]:
        """同 names()（对外命名统一）。"""
        return self.names()

    def is_registered(self, name: str) -> bool:
        return name in self._registry

    def reset(self) -> None:
        """清空注册表并重建内置（测试用）。"""
        self._registry.clear()
        self._default = ""
        self._register_builtins()


__all__ = [
    "ScannerAdapter",
    "ScannerRegistry",
    "ScannerResult",
    "Violation",
    "canonicalize_rule_id",
    "extract_rule_number",
    "violations_to_dicts",
]
