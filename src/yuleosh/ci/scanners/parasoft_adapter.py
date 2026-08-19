# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Parasoft C/C++test 扫描器适配器（商业工具，支持 C:2023）。

配置（.yuleosh/ci-config.yaml）::

    misra:
      scanner: parasoft
      scanner_config:
        cli_path: "cpptestcli"        # CLI 可执行名或绝对路径
        profile: "MISRA_C_2023"       # 工具内 profile
        report_file: ""               # 已有 XML 报告路径（跳过 CLI 执行）
        timeout: 300

输出解析支持 Parasoft C/C++test XML 报告（report.xml 风格）::

    <report version="2023.2">
      <file path="src/brake_control.c">
        <violation rule="MISRA.C.2012.10.1" line="42" severity="Error">
          message text
        </violation>
      </file>
    </report>

rule 属性支持 ``MISRA.C.2012.X.Y`` / ``MISRA-C-2012-Rule-X-Y`` /
``MISRA_C_2023_Rule_X_Y`` 等变体；normalize 统一映射 misra-rules.yaml。
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from typing import Any

from yuleosh.ci.scanners.base import (
    ScannerAdapter,
    ScannerResult,
    Violation,
    canonicalize_rule_id,
)

log = logging.getLogger("ci.scanners")

_DEFAULT_TIMEOUT = 300

# Parasoft severity → 统一 severity（对齐 cppcheck 档位）
_SEVERITY_MAP = {
    "error": "error",
    "warning": "warning",
    "info": "style",
    "information": "style",
    "critical": "error",
    "fatal": "error",
    "required": "required",
    "advisory": "advisory",
    "mandatory": "error",
    "style": "style",
}


class ParasoftScannerAdapter(ScannerAdapter):
    """Parasoft C/C++test 适配器（CLI/XML 解析，DTP REST API 后补）。"""

    name = "parasoft"
    display_name = "Parasoft C/C++test"

    def detect(self, project_dir: str, config: Any = None) -> bool:
        """cli_path 可执行或 report_file 已存在即可用。"""
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
        return ("install Parasoft C/C++test or set misra.scanner_config.report_file "
                "to an existing XML report")

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

        # 模式 A：已有报告文件（客户 CI 生成后喂给 yuleOSH）
        if report_file:
            rp = os.path.join(project_dir, report_file) if not os.path.isabs(report_file) else report_file
            if not os.path.isfile(rp):
                return ScannerResult(
                    tool=self.name, ok=False,
                    error=f"parasoft report file not found: {rp}",
                    hint="set misra.scanner_config.report_file to an existing XML report",
                )
            try:
                with open(rp, "r", encoding="utf-8", errors="replace") as _fh:
                    raw = _fh.read()
            except OSError as e:
                return ScannerResult(tool=self.name, ok=False,
                                     error=f"parasoft report read failed: {e}",
                                     hint="check report_file path and permissions")
            return ScannerResult(tool=self.name, raw_output=raw, ok=True)

        # 模式 B：CLI 执行
        cli_path = sc_cfg.get("cli_path", "cpptestcli")
        profile = sc_cfg.get("profile", "MISRA_C_2023")
        cmd = [cli_path]
        if profile:
            cmd += ["-config", f"builtin://{profile}"]
        if target_files:
            cmd += [os.path.join(project_dir, f) if not os.path.isabs(f) else f
                    for f in target_files]
        cmd += ["-report", "xml"]

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
                error=f"parasoft CLI not found: {cli_path}",
                hint="install Parasoft C/C++test or set misra.scanner_config.cli_path",
            )
        except subprocess.TimeoutExpired:
            return ScannerResult(
                tool=self.name, ok=False,
                error=f"parasoft CLI timed out after {timeout}s",
                hint="increase misra.scanner_config.timeout or reduce file count",
            )
        except Exception as e:  # noqa: BLE001 — 子进程边界防御（外部工具异常兜底）
            return ScannerResult(
                tool=self.name, ok=False,
                error="parasoft execution error: " + str(e),
                hint="check Parasoft installation and configuration",
            )

        output = result.stdout or result.stderr or ""
        return ScannerResult(tool=self.name, raw_output=output, command=cmd,
                             ok=True, elapsed=elapsed)

    def parse(self, raw: str) -> list[Violation]:
        """解析 Parasoft XML 报告 → 统一违规列表。"""
        violations: list[Violation] = []
        if not raw or not raw.strip():
            return violations
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.warning("parasoft XML parse failed: %s", exc)
            return violations

        for file_el in root.iter("file"):
            path = (file_el.get("path") or "").strip()
            for v_el in file_el.iter("violation"):
                rule = (v_el.get("rule") or "").strip()
                line = v_el.get("line") or v_el.get("linenum") or "0"
                sev_raw = (v_el.get("severity") or "style").strip().lower()
                severity = _SEVERITY_MAP.get(sev_raw, sev_raw)
                message = (v_el.text or "").strip() or (v_el.get("message") or "").strip()
                # category 属性（Required/Advisory）留作 rule_year 佐证
                rule_year = "2023"
                rule_lower = rule.lower()
                if "2012" in rule_lower:
                    rule_year = "2012"
                try:
                    line_num = int(line)
                except (TypeError, ValueError):
                    line_num = 0
                violations.append(Violation(
                    rule_id=rule,
                    severity=severity,
                    file=path,
                    line=line_num,
                    message=message,
                    tool=self.name,
                    rule_year=rule_year,
                ))
        return violations

    def normalize(
        self, violations: list[Violation], ruleset: Any = None
    ) -> list[Violation]:
        """Parasoft rule 属性（MISRA.C.2012.X.Y）→ misra-rules.yaml 规范 ID。"""
        for v in violations:
            if v.rule_id:
                # Parasoft 用点分隔年份：MISRA.C.2012.10.1 → misra-c2012-10.1
                # （extract_rule_number 取 10.1，canonicalize 决定年份身份）
                v.rule_id = canonicalize_rule_id(v.rule_id)
            if not v.tool:
                v.tool = self.name
        return violations
