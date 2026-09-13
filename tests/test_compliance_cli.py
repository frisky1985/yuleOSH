#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for ``yuleosh compliance check --profile`` CLI (A1-07)."""

import json

from yuleosh.cli.commands.compliance import cmd_compliance_check, _DEFAULT_PROFILE


def _args(profile=_DEFAULT_PROFILE, project_dir=None, fmt="markdown", save=None):
    class _A:
        pass
    a = _A()
    a.profile = profile
    a.project_dir = project_dir
    a.format = fmt
    a.save = save
    return a


def test_compliance_check_default_profile(capsys, tmp_path):
    """默认 aspice_v3.1 profile 跑通并返回 0，输出含标准名。"""
    rc = cmd_compliance_check(_args(project_dir=str(tmp_path)))
    assert rc == 0
    out = capsys.readouterr().out
    assert "ASPICE" in out
    assert "Compliance Check Report" in out


def test_compliance_check_json_format(capsys, tmp_path):
    """--format json 输出可解析且含 summary。"""
    rc = cmd_compliance_check(_args(project_dir=str(tmp_path), fmt="json"))
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "summary" in data
    assert data["standard"] == "ASPICE"


def test_compliance_check_unknown_profile(capsys, tmp_path):
    """未知 profile 返回 2 并列出可用清单。"""
    rc = cmd_compliance_check(_args(profile="no_such_profile_xyz", project_dir=str(tmp_path)))
    assert rc == 2
    out = capsys.readouterr().out
    assert "no_such_profile_xyz" in out
    # 可用清单提示（aspice_v3.1 必在其中）
    assert _DEFAULT_PROFILE in out


def test_compliance_check_save(capsys, tmp_path):
    """--save 写出报告文件。"""
    report = tmp_path / "report.md"
    rc = cmd_compliance_check(_args(project_dir=str(tmp_path), save=str(report)))
    assert rc == 0
    assert report.exists()
    assert "ASPICE" in report.read_text(encoding="utf-8")
