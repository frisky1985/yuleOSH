#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Compliance CLI (A-M1 / A1-07).

``yuleosh compliance check --profile <name>`` 运行标准合规检查，支持通过
``--profile`` 选择任意 ``StandardProfile``（默认 ``aspice_v3.1``）。未知 profile
报错并列出可用清单（由 ``ProfileNotFoundError`` 携带）。

复用已 profile 驱动的 ``ComplianceChecker``（A1-05）：传入 ``StandardProfile``
对象即可零代码改动切换标准。
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import (
    load_profile,
    ProfileNotFoundError,
    ProfileError,
)

log = logging.getLogger("yuleosh.cli.commands.compliance")

_DEFAULT_PROFILE = "aspice_v3.1"


def cmd_compliance_check(args) -> int:
    """``yuleosh compliance check`` — 按 profile 运行合规检查。

    Returns:
        int: 0=成功；2=未知 profile；1=其它错误。
    """
    profile_name = getattr(args, "profile", _DEFAULT_PROFILE) or _DEFAULT_PROFILE
    project_dir = getattr(args, "project_dir", None) or os.environ.get(
        "OSH_HOME", os.getcwd()
    )
    output_format = getattr(args, "format", "markdown")
    save_path = getattr(args, "save", None)

    # 加载 profile（未知名称 → 列出可用清单并退出 2）
    try:
        profile = load_profile(profile_name)
    except ProfileNotFoundError as exc:
        print(f"❌ {exc}")
        return 2
    except ProfileError as exc:
        print(f"❌ profile 校验失败: {exc}")
        return 1
    except Exception as exc:  # yaml 解析等文件级错误
        print(f"❌ 加载 profile '{profile_name}' 失败: {exc}")
        return 1

    checker = ComplianceChecker(project_dir=project_dir, profile=profile)
    report = checker.run()

    if output_format == "json":
        out = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    else:
        out = checker.generate_report_markdown(report)

    print(out)

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        Path(save_path).write_text(out, encoding="utf-8")
        print(f"\n📄 Report saved: {save_path}")

    return 0


def build_parser(sub):
    """向主解析器注册 ``compliance`` 命令组 (A1-07)。"""
    p_compliance = sub.add_parser(
        "compliance",
        help="Run standard compliance check against a StandardProfile",
    )
    csub = p_compliance.add_subparsers(dest="compliance_sub")
    p_check = csub.add_parser(
        "check",
        help="Run compliance check (default profile: aspice_v3.1)",
    )
    p_check.add_argument(
        "--profile", "-p", default=_DEFAULT_PROFILE,
        help="Compliance profile name (without .yaml), e.g. aspice_v3.1",
    )
    p_check.add_argument(
        "--project-dir", default=None,
        help="Project root to check (default: OSH_HOME or CWD)",
    )
    p_check.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format (default: markdown)",
    )
    p_check.add_argument(
        "--save", "-o", default=None,
        help="Write the report to a file (path)",
    )
    return p_compliance
