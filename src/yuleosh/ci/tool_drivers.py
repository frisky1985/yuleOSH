#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tool Drivers — 静态分析工具驱动接口

定义 BaseToolDriver 抽象基类，封装各静态分析工具的 parse / run / report 接口。
现有 CppcheckDriver 封装 misra_report.py 逻辑，ClangTidyDriver 为预留 stub。

Usage:
    from yuleosh.ci.tool_drivers import create_driver

    driver = create_driver("cppcheck", project_dir="/path")
    violations = driver.parse(raw_output)
    report = driver.generate_report(violations)

    driver = create_driver("clang-tidy", project_dir="/path")
    # stub, ready for future implementation
"""

import abc
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ci.tool_drivers")


# ------------------------------------------------------------------
# Abstract Base Class
# ------------------------------------------------------------------


class BaseToolDriver(abc.ABC):
    """静态分析工具驱动的抽象基类。

    所有具体驱动必须实现：
      - parse(raw_output: str) -> list[dict]   : 解析工具原始输出
      - run(target: str) -> str                 : 执行工具分析（可选）
      - generate_report(violations: list[dict]) -> dict : 生成结构化报告
      - name -> str                             : 工具名称

    Parameters
    ----------
    project_dir : str
        项目根目录。
    config : dict, optional
        工具配置参数（如规则集路径、额外参数等）。
    """

    def __init__(self, project_dir: str, config: Optional[dict] = None):
        self._project_dir = Path(project_dir).resolve()
        self._config = config or {}

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """工具名称标识符。"""
        ...

    @abc.abstractmethod
    def parse(self, raw_output: str) -> list[dict]:
        """解析工具的原始输出，返回违规列表。

        Returns
        -------
        list[dict]
            每条违规包含：file, line, col, severity, message, rule_id。
        """
        ...

    @abc.abstractmethod
    def run(self, target: str) -> str:
        """执行工具分析并返回原始输出。

        Parameters
        ----------
        target : str
            分析目标（文件路径 / 目录 / 编译数据库等）。

        Returns
        -------
        str
            工具原始输出文本。
        """
        ...

    @abc.abstractmethod
    def generate_report(self, violations: list[dict]) -> dict:
        """从违规列表生成结构化报告。

        Returns
        -------
        dict
            结构化的报告字典。
        """
        ...

    @property
    def config(self) -> dict:
        """获取当前驱动配置。"""
        return dict(self._config)

    def get_report_dir(self) -> Path:
        """获取标准报告输出目录。"""
        return self._project_dir / ".yuleosh" / "reports"


# ------------------------------------------------------------------
# CppcheckDriver
# ------------------------------------------------------------------


class CppcheckDriver(BaseToolDriver):
    """Cppcheck MISRA 分析驱动。

    封装 misra_report.py 中的解析、汇总、报告生成逻辑。
    支持 cppcheck --addon=misra 输出格式。

    可选接受 ruleset 参数，用于获取工具配置和规则定义。
    """

    def __init__(self, project_dir: str, config: Optional[dict] = None):
        super().__init__(project_dir, config)
        self._ruleset = None
        ruleset_config = self._config.get("ruleset")
        if ruleset_config is not None:
            self._ruleset = ruleset_config

    @property
    def name(self) -> str:
        return "cppcheck"

    @property
    def ruleset(self):
        """获取当前关联的规则集实例。"""
        return self._ruleset

    def set_ruleset(self, ruleset) -> None:
        """设置规则集实例。"""
        self._ruleset = ruleset

    def _get_effective_config(self) -> dict:
        """获取有效配置（合并规则集配置和驱动配置）。"""
        cfg = dict(self._config)
        if self._ruleset is not None:
            tool_cfg = self._ruleset.get_tool_config("cppcheck")
            # 合并，config 中的值优先
            for k, v in tool_cfg.items():
                cfg.setdefault(k, v)
        return cfg

    def parse(self, raw_output: str) -> list[dict]:
        """解析 cppcheck --addon=misra 输出。

        内部调用 misra_report.parse_cppcheck_output()，返回标准化的违规记录。
        """
        from yuleosh.ci.misra_report import parse_cppcheck_output
        return parse_cppcheck_output(raw_output)

    def run(self, target: str) -> str:
        """执行 cppcheck 分析。

        如果设置了 ruleset，则使用 ruleset.get_tool_config() 给出的配置。

        Parameters
        ----------
        target : str
            源文件或目录路径。

        Returns
        -------
        str
            cppcheck 原始输出。
        """
        import subprocess
        target_path = Path(target)

        if not target_path.exists():
            raise FileNotFoundError(f"Analysis target not found: {target}")

        eff_cfg = self._get_effective_config()
        addon = eff_cfg.get("addon", "misra")
        enable = eff_cfg.get("enable", "all")
        suppress_opts = []
        for s in eff_cfg.get("suppress", []):
            suppress_opts.append(f"--suppress={s}")

        extra_args = self._config.get("extra_args", [])
        args = ["cppcheck", f"--addon={addon}", f"--enable={enable}"] + suppress_opts + extra_args

        if target_path.is_file():
            args.append(str(target_path))
        else:
            # Recursive for directories
            args.append("--recursive")
            args.append(str(target_path))

        log.info("Running cppcheck: %s", " ".join(args))

        run_timeout = self._config.get("run_timeout", 300)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=run_timeout,
            )
            # cppcheck outputs diagnostics to stderr
            return result.stdout + result.stderr
        except FileNotFoundError:
            log.error("cppcheck not found on PATH")
            return "(error: cppcheck not found)"
        except subprocess.TimeoutExpired:
            log.error("cppcheck timed out after %ss", run_timeout)
            return "(error: cppcheck timed out)"

    def generate_report(self, violations: list[dict]) -> dict:
        """从违规列表生成结构化 MISRA 报告。

        内部调用 misra_report 的 group / enrich / summary / JSON 生成。
        如果设置了 ruleset，则使用 ruleset.rule_definitions() 获取规则定义。

        Returns
        -------
        dict
            完整 MISRA 报告字典。
        """
        from yuleosh.ci.misra_report import (
            load_rule_definitions,
            group_by_rule,
            enrich_with_definitions,
            compute_summary_stats,
            generate_json_report,
        )

        # Load rule definitions — 优先使用 ruleset
        if self._ruleset is not None:
            rule_defs = self._ruleset.rule_definitions()
        else:
            rules_path = self._config.get("rules_path")
            if rules_path:
                rule_defs = load_rule_definitions(Path(rules_path))
            else:
                rule_defs = load_rule_definitions()

        # Group, enrich, summarize
        groups = group_by_rule(violations)
        groups = enrich_with_definitions(groups, rule_defs)
        summary = compute_summary_stats(violations, groups, rule_defs)

        # Generate and parse back to dict
        report_dir = self._config.get("output_dir", self.get_report_dir())
        report_json_str = generate_json_report(
            violations, groups, summary, rule_defs,
            output_dir=report_dir,
        )
        return json.loads(report_json_str)

    def get_rule_definitions(self) -> dict:
        """加载 MISRA 规则定义。

        若关联了 ruleset，则使用 ruleset.rule_definitions()。
        """
        if self._ruleset is not None:
            return self._ruleset.rule_definitions()
        from yuleosh.ci.misra_report import load_rule_definitions
        return load_rule_definitions()

    def get_ruleset_info(self) -> Optional[dict]:
        """获取关联规则集的元信息。"""
        if self._ruleset is None:
            return None
        return {
            "name": self._ruleset.name,
            "display_name": self._ruleset.display_name,
            "supported_tools": self._ruleset.supported_tools(),
        }


# ------------------------------------------------------------------
# ClangTidyDriver (Stub)
# ------------------------------------------------------------------


class ClangTidyDriver(BaseToolDriver):
    """Clang-Tidy 分析驱动（Stub，预留接口）。

    当前为骨架实现，所有方法返回空值/标识 stub 状态。
    待后续实现 clang-tidy 输出解析逻辑。
    """

    @property
    def name(self) -> str:
        return "clang-tidy"

    def parse(self, raw_output: str) -> list[dict]:
        """解析 clang-tidy 输出（Stub）。

        TODO: 实现 clang-tidy 输出格式解析。
        期望格式（LLVM 15+）:
          /path/file.c:42:5: warning: ... [clang-analyzer-...]
          /path/file.c:95:9: error: ... [readability-...]

        Returns
        -------
        list[dict]
            空列表（Stub 状态）。
        """
        log.warning("ClangTidyDriver.parse() — stub, no parsing implemented")
        return []

    def run(self, target: str) -> str:
        """执行 clang-tidy 分析（Stub）。

        Parameters
        ----------
        target : str
            源文件路径。

        Returns
        -------
        str
            "(stub) clang-tidy not yet implemented"。
        """
        log.warning("ClangTidyDriver.run() — stub, no execution implemented")
        return "(stub) clang-tidy not yet implemented"

    def generate_report(self, violations: list[dict]) -> dict:
        """生成 clang-tidy 结构化报告（Stub）。

        Returns
        -------
        dict
            带 stub 标识的空报告。
        """
        report = {
            "tool": "clang-tidy",
            "status": "stub",
            "generated_at": datetime.now().isoformat(),
            "total_violations": len(violations),
            "violations": violations,
            "message": "ClangTidyDriver — stub, report generation not yet implemented",
        }
        return report


# ------------------------------------------------------------------
# 驱动工厂
# ------------------------------------------------------------------

_DRIVER_REGISTRY: dict[str, type[BaseToolDriver]] = {
    "cppcheck": CppcheckDriver,
    "clang-tidy": ClangTidyDriver,
}


def create_driver(tool: str, project_dir: str, config: Optional[dict] = None, ruleset=None) -> BaseToolDriver:
    """创建指定工具的分析驱动实例。

    工厂方法——根据 tool 参数选择对应的驱动实现。

    Parameters
    ----------
    tool : str
        工具名称: "cppcheck" | "clang-tidy"。
    project_dir : str
        项目根目录。
    config : dict, optional
        工具配置参数。
    ruleset : BaseRuleSet, optional
        可选的规则集实例。如果提供，驱动将使用规则集的配置和规则定义。

    Returns
    -------
    BaseToolDriver
        驱动实例。

    Raises
    ------
    ValueError
        当 tool 不在注册的驱动列表中时抛出。
    """
    driver_cls = _DRIVER_REGISTRY.get(tool)
    if driver_cls is None:
        supported = ", ".join(sorted(_DRIVER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown tool: '{tool}'. Supported tools: {supported}"
        )
    merged_config = dict(config or {})
    if ruleset is not None:
        merged_config["ruleset"] = ruleset
    return driver_cls(project_dir=project_dir, config=merged_config)


def register_driver(tool: str, driver_cls: type[BaseToolDriver]) -> None:
    """注册新的工具驱动。

    用于扩展支持新工具（如 clang-tidy 实现后注册）。

    Parameters
    ----------
    tool : str
        工具名称标识符。
    driver_cls : type[BaseToolDriver]
        驱动类，必须继承 BaseToolDriver。
    """
    if not issubclass(driver_cls, BaseToolDriver):
        raise TypeError(f"{driver_cls.__name__} must inherit BaseToolDriver")
    _DRIVER_REGISTRY[tool] = driver_cls
    log.info("Tool driver registered: %s -> %s", tool, driver_cls.__name__)


def list_drivers() -> list[str]:
    """列出所有已注册的工具驱动名称。

    Returns
    -------
    list[str]
        注册的工具名称列表。
    """
    return sorted(_DRIVER_REGISTRY.keys())
