# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Cppcheck 扫描器适配器（默认，MISRA C:2012）。

从 review_misra.py 收编 cppcheck 调用逻辑（2026-08-19 ScannerAdapter P1）：
suppress 参数 / include 路径 / AUTOSAR 宏定义 / rule_texts_path addon JSON /
.cppcheck_suppressions / 相对路径传递 / 180s 超时与错误语义，全部保持原样，
默认路径零回归。

解析复用 ``misra_report.core.parser.parse_cppcheck_output``（含 C:2012 诚实
归一化：modified/removed 规则保留 misra-c2012-* 身份）。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Any

from yuleosh.ci.scanners.base import (
    ScannerAdapter,
    ScannerResult,
    Violation,
    violations_to_dicts,
)

log = logging.getLogger("ci.scanners")

# AUTOSAR 平台宏定义 — 抑制常见假阳性（与 review_misra.py 原逻辑一致）
_AUTOSAR_DEFINES = [
    "-DSTD_ON", "-DSTD_OFF", "-DSTD_HIGH", "-DSTD_LOW",
    "-DSTD_ACTIVE", "-DSTD_IDLE",
    "-DNULL_PTR", "-DTRUE", "-DFALSE",
    "-DE_OK", "-DE_NOT_OK",
    "-DNULL",
]

# cppcheck 默认超时（秒）；scanner_config.timeout 可覆盖
_DEFAULT_TIMEOUT = 180

# C++ 泛化 (2026-08-21 A1 dogfood): 项目含 .cpp 时 cppcheck 用 C++ 语言模式
_CPP_EXTENSIONS = (".cpp", ".cc", ".cxx", ".c++")


def _detect_cppcheck_language(project_dir: str) -> str:
    """按项目源码决定 cppcheck 语言: 含 C++ 源 → 'c++', 否则 'c'.

    cppcheck --language=c 解析 .cpp 会报 syntaxError (namespace/class),
    导致 C++ 项目扫描全量误报 (A1 dogfood 实测, 2026-08-21)。
    """
    try:
        for dirpath, _dirnames, filenames in os.walk(project_dir):
            if "third_party" in dirpath or "build" in dirpath:
                continue
            for fn in filenames:
                if fn.endswith(_CPP_EXTENSIONS):
                    return "c++"
    except OSError:
        pass
    return "c"


class CppcheckScannerAdapter(ScannerAdapter):
    """cppcheck --addon=misra 适配器（默认扫描器，C:2012 工具链）。"""

    name = "cppcheck"
    display_name = "cppcheck (MISRA C:2012 addon)"

    def detect(self, project_dir: str, config: Any = None) -> bool:
        """cppcheck 可执行文件存在即可用。"""
        if shutil.which("cppcheck"):
            return True
        # cppcheck-wheel / 自定义路径兜底
        sc_cfg = getattr(config, "scanner_config", None) or {}
        cli_path = sc_cfg.get("cli_path", "") if isinstance(sc_cfg, dict) else ""
        return bool(cli_path and os.path.isfile(os.path.join(project_dir, cli_path)))

    def detect_hint(self, project_dir: str, config: Any = None) -> str:
        return "install cppcheck (e.g. 'apt install cppcheck' or 'brew install cppcheck')"

    def run(
        self,
        project_dir: str,
        config: Any = None,
        target_files: list[str] | None = None,
        **kwargs: Any,
    ) -> ScannerResult:
        """构建并执行 cppcheck 命令（逻辑与 review_misra.py 原实现一致）。"""
        sc_cfg = getattr(config, "scanner_config", None) or {}
        if not isinstance(sc_cfg, dict):
            sc_cfg = {}
        timeout = int(sc_cfg.get("timeout", _DEFAULT_TIMEOUT) or _DEFAULT_TIMEOUT)

        misra_cfg = config
        addon = getattr(misra_cfg, "addon", None) or "misra"
        cppcheck_std = getattr(misra_cfg, "cppcheck_std", None) or "c11"
        enable = getattr(misra_cfg, "enable", None) or "all"
        suppress_rules = getattr(misra_cfg, "suppress_rules", None) or []
        rule_overrides = getattr(misra_cfg, "rule_overrides", None) or []
        rule_texts_path = getattr(misra_cfg, "rule_texts_path", None) or ""
        include_paths_cfg = getattr(misra_cfg, "include_paths", None) or []

        # ── Build suppression arguments from config + rule_overrides ──
        suppress_args = []
        for rule_id in suppress_rules:
            suppress_args.append("--suppress=misra-c2023-" + rule_id)
            suppress_args.append("--suppress=misra-c2012-" + rule_id)
        for override in rule_overrides:
            if not override.enabled and override.rule_id:
                suppress_args.append("--suppress=" + override.rule_id)

        # ── Auto-detect include paths and add -I flags ──
        from yuleosh.ci.stages.review_collect import _detect_include_paths
        include_paths = _detect_include_paths(project_dir)
        for inc in include_paths_cfg:
            inc_resolved = os.path.join(project_dir, inc) if not os.path.isabs(inc) else inc
            if os.path.isdir(inc_resolved) and inc_resolved not in include_paths:
                include_paths.append(inc_resolved)
        include_args = []
        for inc in include_paths:
            # 项目相对 -I：cppcheck 输出相对路径，匹配 suppressions-list 条目
            if os.path.isabs(inc):
                try:
                    rel_inc = os.path.relpath(inc, project_dir)
                    if not rel_inc.startswith(".."):
                        inc = rel_inc
                except ValueError:
                    pass
            include_args.extend(["-I", inc])
        if include_args:
            log.info("Adding include paths: %s", " ".join(
                [inc for i, inc in enumerate(include_args) if i % 2 == 1]
            ))

        # compile_commands.json 提示
        compile_db = os.path.join(project_dir, "compile_commands.json")
        if os.path.isfile(compile_db):
            log.info("Found compile_commands.json — consider using --project=compile_commands.json")

        # ── Construct cppcheck command ──
        cppcheck_suppressions = os.path.join(project_dir, ".cppcheck_suppressions")
        suppressions_list_args = []
        if os.path.isfile(cppcheck_suppressions):
            suppressions_list_args = ["--suppressions-list=" + cppcheck_suppressions]

        define_args = list(_AUTOSAR_DEFINES)

        # cppcheck-config.h for AUTOSAR platform defines
        cppcheck_config_h = os.path.join(project_dir, "cppcheck-config.h")
        if os.path.isfile(cppcheck_config_h):
            define_args.append("--include=" + cppcheck_config_h)
            define_args.append("--max-configs=1")
            if getattr(misra_cfg, "enabled", True):
                suppress_args.append("--suppress=misra-config")

        # addon arg: JSON config when rule_texts_path is set
        addon_arg = addon
        if rule_texts_path:
            rt_resolved = os.path.join(project_dir, rule_texts_path) if not os.path.isabs(rule_texts_path) else rule_texts_path
            if os.path.isfile(rt_resolved):
                addon_json = os.path.join(project_dir, ".yuleosh", "misra-addon-config.json")
                if not os.path.isfile(addon_json):
                    import json as _json
                    addon_cfg = {
                        "script": addon,
                        "python": "python3",
                        "args": ["--rule-texts=" + rt_resolved],
                    }
                    os.makedirs(os.path.dirname(addon_json), exist_ok=True)
                    with open(addon_json, "w") as _f:
                        _json.dump(addon_cfg, _f, indent=2)
                    log.info("Created addon JSON config: %s", addon_json)
                addon_arg = addon_json
            else:
                log.warning("rule_texts_path configured but file not found: %s", rt_resolved)

        cmd = [
            "cppcheck",
            "--addon=" + addon_arg,
            "--language=" + _detect_cppcheck_language(project_dir),
            "--std=" + cppcheck_std,
            "--enable=" + enable,
            "--suppress=missingIncludeSystem",
            "--suppress=missingInclude",
            "--suppress=normalCheckLevelMaxBranches",
            "-q",
        ] + suppressions_list_args + define_args + include_args + suppress_args

        # 相对路径传递（输出路径匹配 suppressions-list 项目相对条目）
        rel_c_files = []
        for f in (target_files or []):
            if os.path.isabs(f):
                try:
                    rel = os.path.relpath(f, project_dir)
                    if not rel.startswith(".."):
                        rel_c_files.append(rel)
                        continue
                except ValueError:
                    pass
            rel_c_files.append(f)
        cmd += rel_c_files

        try:
            start = time.perf_counter()
            # check=False：cppcheck 对发现违规返回非零，输出解析以 stderr 文本
            # 为准（与 review_misra.py 原语义一致）。
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=project_dir,
                check=False,
            )
            elapsed = time.perf_counter() - start
        except FileNotFoundError:
            return ScannerResult(
                tool=self.name,
                ok=False,
                error="cppcheck not installed",
                hint="install cppcheck (e.g. 'apt install cppcheck' or 'brew install cppcheck')",
            )
        except subprocess.TimeoutExpired:
            return ScannerResult(
                tool=self.name,
                ok=False,
                error=f"cppcheck timed out after {timeout}s",
                hint="increase timeout or reduce file count. Try 'cppcheck --project=compile_commands.json' for faster analysis",
            )
        except Exception as e:  # noqa: BLE001 — 子进程边界防御
            return ScannerResult(
                tool=self.name,
                ok=False,
                error="cppcheck execution error: " + str(e),
                hint="check cppcheck installation and project configuration",
            )

        # cppcheck 写 MISRA warnings 到 stderr
        output = result.stderr or result.stdout or ""
        return ScannerResult(
            tool=self.name,
            raw_output=output,
            command=cmd,
            ok=True,
            elapsed=elapsed,
        )

    def parse(self, raw: str) -> list[Violation]:
        """解析 cppcheck 文本输出（复用 parse_cppcheck_output，含诚实归一化）。"""
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        try:
            dicts = parse_cppcheck_output(raw)
        except Exception as exc:  # noqa: BLE001 — 解析容错（外部工具输出不可控）
            log.warning("cppcheck parse failed: %s", exc)
            return []
        return [Violation.from_dict({**d, "tool": self.name}) for d in dicts]

    def normalize(
        self, violations: list[Violation], ruleset: Any = None
    ) -> list[Violation]:
        """cppcheck 解析已含规范 ID（parse_cppcheck_output 内归一化），
        仅补工具标记；再走一次 canonicalize 幂等无害。"""
        return super().normalize(violations, ruleset)


# 便捷函数：适配器 Violation → dict 列表（下游消费）
def cppcheck_violations_to_dicts(violations: list[Violation]) -> list[dict]:
    return violations_to_dicts(violations)
