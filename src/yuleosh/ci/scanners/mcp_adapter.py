# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""MCP 扫描器适配器（P3 可选，最小实现）。

适用：扫描器不在本机 / 客户 CI 工具链有 MCP 网关。

配置（.yuleosh/ci-config.yaml）::

    misra:
      scanner: mcp
      scanner_config:
        mcp_endpoint: "http://scanner-gateway:8000/mcp"   # MCP 端点（记录/校验用）
        mcp_tool: "run_misra_scan"                        # MCP 工具名（记录/校验用）
        cli_path: "mcp-invoke"                            # MCP 网关 CLI（实际执行）
        output_file: ""                                   # 已有输出文件（跳过 CLI）
        timeout: 300

执行语义：优先 output_file（客户网关已产出）；否则跑 cli_path 网关命令。
解析：先尝试 cppcheck 文本格式，再尝试 QAC/LDRA 行格式——MCP 网关返回的
具体工具输出由网关决定，这里尽量宽容。
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
    canonicalize_rule_id,
)
from yuleosh.ci.scanners.ldra_adapter import LdraScannerAdapter
from yuleosh.ci.scanners.qac_adapter import QacScannerAdapter

log = logging.getLogger("ci.scanners")

_DEFAULT_TIMEOUT = 300


class McpScannerAdapter(ScannerAdapter):
    """MCP 网关扫描器适配器（薄封装：CLI/output_file + 宽容解析）。"""

    name = "mcp"
    display_name = "MCP scanner gateway"

    def detect(self, project_dir: str, config: Any = None) -> bool:
        sc_cfg = getattr(config, "scanner_config", None) or {}
        if not isinstance(sc_cfg, dict):
            sc_cfg = {}
        output_file = sc_cfg.get("output_file", "")
        if output_file:
            return os.path.isfile(
                os.path.join(project_dir, output_file)
                if not os.path.isabs(output_file) else output_file
            )
        cli_path = sc_cfg.get("cli_path", "")
        if not cli_path:
            return False
        if os.path.isabs(cli_path):
            return os.path.isfile(cli_path)
        return shutil.which(cli_path) is not None

    def detect_hint(self, project_dir: str, config: Any = None) -> str:
        return ("configure misra.scanner_config.cli_path (MCP gateway CLI) or "
                "output_file (gateway-produced output)")

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
        output_file = sc_cfg.get("output_file", "")

        if output_file:
            of = os.path.join(project_dir, output_file) if not os.path.isabs(output_file) else output_file
            if not os.path.isfile(of):
                return ScannerResult(
                    tool=self.name, ok=False,
                    error=f"mcp output file not found: {of}",
                    hint="set misra.scanner_config.output_file to the gateway-produced output",
                )
            try:
                with open(of, "r", encoding="utf-8", errors="replace") as _fh:
                    raw = _fh.read()
            except OSError as e:
                return ScannerResult(tool=self.name, ok=False,
                                     error=f"mcp output read failed: {e}",
                                     hint="check output_file path and permissions")
            return ScannerResult(tool=self.name, raw_output=raw, ok=True)

        cli_path = sc_cfg.get("cli_path", "")
        if not cli_path:
            return ScannerResult(
                tool=self.name, ok=False,
                error="mcp scanner requires scanner_config.cli_path or output_file",
                hint="set misra.scanner_config.cli_path (MCP gateway CLI) or output_file",
            )
        mcp_tool = sc_cfg.get("mcp_tool", "run_misra_scan")
        cmd = [cli_path, mcp_tool]
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
                error=f"mcp CLI not found: {cli_path}",
                hint="set misra.scanner_config.cli_path to the MCP gateway CLI",
            )
        except subprocess.TimeoutExpired:
            return ScannerResult(
                tool=self.name, ok=False,
                error=f"mcp CLI timed out after {timeout}s",
                hint="increase misra.scanner_config.timeout or reduce file count",
            )
        except Exception as e:  # noqa: BLE001 — 子进程边界防御（外部工具异常兜底）
            return ScannerResult(
                tool=self.name, ok=False,
                error="mcp execution error: " + str(e),
                hint="check MCP gateway configuration",
            )

        output = result.stdout or result.stderr or ""
        return ScannerResult(tool=self.name, raw_output=output, command=cmd,
                             ok=True, elapsed=elapsed)

    def parse(self, raw: str) -> list[Violation]:
        """宽容解析：先 cppcheck 格式，再 QAC/LDRA 行格式。"""
        if not raw or not raw.strip():
            return []
        # 1) cppcheck 格式（bracketed/legacy）
        from yuleosh.ci.misra_report.core.parser import parse_cppcheck_output
        try:
            dicts = parse_cppcheck_output(raw)
        except Exception:  # noqa: BLE001 — 解析容错（外部工具输出不可控）
            dicts = []
        if dicts:
            return [Violation.from_dict({**d, "tool": self.name}) for d in dicts]
        # 2) QAC 行格式
        qac = QacScannerAdapter()
        qac_v = qac.parse(raw)
        if qac_v:
            for v in qac_v:
                v.tool = self.name
            return qac_v
        # 3) LDRA 行格式
        ldra = LdraScannerAdapter()
        ldra_v = ldra.parse(raw)
        for v in ldra_v:
            v.tool = self.name
        return ldra_v

    def normalize(
        self, violations: list[Violation], ruleset: Any = None
    ) -> list[Violation]:
        for v in violations:
            if v.rule_id:
                v.rule_id = canonicalize_rule_id(v.rule_id)
            if not v.tool:
                v.tool = self.name
        return violations
