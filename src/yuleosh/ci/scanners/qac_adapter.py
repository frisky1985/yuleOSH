# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Helix QAC 扫描器适配器（商业工具，支持 C:2023）。

配置（.yuleosh/ci-config.yaml）::

    misra:
      scanner: qac
      scanner_config:
        cli_path: "qacli"             # QAC CLI 可执行名或绝对路径
        profile: "MISRA_C_2023"       # 工具内 profile
        report_file: ""               # 已有文本报告路径（跳过 CLI 执行）
        timeout: 300

输出解析支持 QAC 文本报告（console/导出风格）::

    src/speed_control.c:33: (Required) Rule 10.1: Operands shall not be of inappropriate essential type
    src/speed_control.c:47: (Advisory) Rule 2.5: A macro shall not be defined with the same name as a keyword
    src/speed_control.h:12: (Required) Dir 4.1: Run-time failures shall be minimized

severity 括号值 Required/Advisory/Mandatory/Style 映射统一档位。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Any

from yuleosh.ci.scanners.base import (
    ScannerAdapter,
    ScannerResult,
    Violation,
    canonicalize_rule_id,
)

log = logging.getLogger("ci.scanners")

_DEFAULT_TIMEOUT = 300

# QAC 括号 severity → 统一 severity（对齐 cppcheck 档位）
_SEVERITY_MAP = {
    "mandatory": "error",
    "required": "required",
    "advisory": "advisory",
    "style": "style",
    "error": "error",
    "warning": "warning",
    "info": "style",
    "information": "style",
}

# 行格式：file:line: (Severity) Rule X.Y: message
_PATTERN_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):\s*\((?P<severity>[^)]+)\)\s*"
    r"(?P<rule>(?:Rule|Dir)\s+[\d.]+|[A-Za-z0-9_.\-]+)\s*:\s*(?P<message>.*)$"
)


class QacScannerAdapter(ScannerAdapter):
    """Helix QAC 适配器（CLI/文本解析）。"""

    name = "qac"
    display_name = "Helix QAC"

    def detect(self, project_dir: str, config: Any = None) -> bool:
        sc_cfg = getattr(config, "scanner_config", None) or {}
        if not isinstance(sc_cfg, dict):
            sc_cfg = {}
        report_file = sc_cfg.get("report_file", "")
        if report_file:
            return os.path.isfile(
                os.path.join(project_dir, report_file)
                if not os.path.isabs(report_file) else report_file
            )
        cli_path = sc_cfg.get("cli_path", "")
        if not cli_path:
            return False
        if os.path.isabs(cli_path):
            return os.path.isfile(cli_path)
        return shutil.which(cli_path) is not None

    def detect_hint(self, project_dir: str, config: Any = None) -> str:
        return ("install Helix QAC or set misra.scanner_config.report_file "
                "to an existing QAC text report")

    def run(
        self,
        project_dir: str,
        config: Any = None,
        target_files: list[str] | None = None,
        **kwargs: Any,
    ) -> ScannerResult:
        sc_cfg = getattr(config, "scanner_config", None) or {}
        if not isinstance(sc_cfg, dict):
            sc_cfg = {}
        timeout = int(sc_cfg.get("timeout", _DEFAULT_TIMEOUT) or _DEFAULT_TIMEOUT)
        report_file = sc_cfg.get("report_file", "")

        if report_file:
            rp = os.path.join(project_dir, report_file) if not os.path.isabs(report_file) else report_file
            if not os.path.isfile(rp):
                return ScannerResult(
                    tool=self.name, ok=False,
                    error=f"qac report file not found: {rp}",
                    hint="set misra.scanner_config.report_file to an existing QAC text report",
                )
            try:
                with open(rp, "r", encoding="utf-8", errors="replace") as _fh:
                    raw = _fh.read()
            except OSError as e:
                return ScannerResult(tool=self.name, ok=False,
                                     error=f"qac report read failed: {e}",
                                     hint="check report_file path and permissions")
            return ScannerResult(tool=self.name, raw_output=raw, ok=True)

        cli_path = sc_cfg.get("cli_path", "qacli")
        profile = sc_cfg.get("profile", "MISRA_C_2023")
        cmd = [cli_path, "analyze"]
        if profile:
            cmd += ["--profile", profile]
        if target_files:
            cmd += [os.path.join(project_dir, f) if not os.path.isabs(f) else f
                    for f in target_files]

        try:
            start = time.perf_counter()
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, cwd=project_dir,
                check=False,
            )
            elapsed = time.perf_counter() - start
        except FileNotFoundError:
            return ScannerResult(
                tool=self.name, ok=False,
                error=f"qac CLI not found: {cli_path}",
                hint="install Helix QAC or set misra.scanner_config.cli_path",
            )
        except subprocess.TimeoutExpired:
            return ScannerResult(
                tool=self.name, ok=False,
                error=f"qac CLI timed out after {timeout}s",
                hint="increase misra.scanner_config.timeout or reduce file count",
            )
        except Exception as e:  # noqa: BLE001 — 子进程边界防御（外部工具异常兜底）
            return ScannerResult(
                tool=self.name, ok=False,
                error="qac execution error: " + str(e),
                hint="check Helix QAC installation and configuration",
            )

        output = result.stdout or result.stderr or ""
        return ScannerResult(tool=self.name, raw_output=output, command=cmd,
                             ok=True, elapsed=elapsed)

    def parse(self, raw: str) -> list[Violation]:
        """解析 QAC 文本报告 → 统一违规列表。"""
        violations: list[Violation] = []
        if not raw:
            return violations
        for line in raw.splitlines():
            m = _PATTERN_LINE.match(line.strip())
            if not m:
                continue
            sev_raw = m.group("severity").strip().lower()
            severity = _SEVERITY_MAP.get(sev_raw, sev_raw)
            rule = m.group("rule").strip()
            try:
                line_num = int(m.group("line"))
            except (TypeError, ValueError):
                line_num = 0
            violations.append(Violation(
                rule_id=rule,
                severity=severity,
                file=m.group("file").strip(),
                line=line_num,
                message=m.group("message").strip(),
                tool=self.name,
                rule_year="2023",
            ))
        return violations

    def normalize(
        self, violations: list[Violation], ruleset: Any = None
    ) -> list[Violation]:
        for v in violations:
            if v.rule_id:
                v.rule_id = canonicalize_rule_id(v.rule_id)
            if not v.tool:
                v.tool = self.name
        return violations
