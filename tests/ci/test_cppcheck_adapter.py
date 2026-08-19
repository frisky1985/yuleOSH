# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""CppcheckScannerAdapter 单测（2026-08-19 P1 收编 review_misra cppcheck 逻辑）。

验收标准 #1：cppcheck 默认路径不回归 —— 命令构建 / 解析 / 错误语义与
review_misra.py 原实现一致。
"""

import subprocess

from yuleosh.ci.config import MisraConfig
from yuleosh.ci.scanners.cppcheck_adapter import CppcheckScannerAdapter

CPPCHECK_OUTPUT = """\
src/brake.c:42:5: error: The expression 'x' is assigned a value that is never used. [misra-c2012-2.2]
src/brake.c:57:9: warning: A function should have a single point of exit. [misra-c2012-15.5]
src/brake.h:12:1: style: A macro shall not be defined with the same name as a keyword. [misra-c2012-2.5]
"""


def _make_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "brake.c").write_text("int x;\n")
    return tmp_path


class TestCppcheckRun:
    def test_builds_command_and_parses(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)
        calls = {}

        def fake_run(cmd, **kwargs):
            calls["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stderr=CPPCHECK_OUTPUT, stdout="")

        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.subprocess.run", fake_run
        )

        adapter = CppcheckScannerAdapter()
        cfg = MisraConfig(suppress_rules=["10.1"], rule_overrides=[])
        result = adapter.run(str(project), config=cfg, target_files=["src/brake.c"])

        assert result.ok
        assert result.raw_output == CPPCHECK_OUTPUT
        cmd = calls["cmd"]
        assert cmd[0] == "cppcheck"
        assert "--addon=misra" in cmd
        assert "--language=c" in cmd
        assert "--std=c11" in cmd
        assert "--enable=all" in cmd
        assert "--suppress=misra-c2023-10.1" in cmd
        assert "--suppress=misra-c2012-10.1" in cmd
        assert "src/brake.c" in cmd

        violations = adapter.normalize(adapter.parse(result.raw_output))
        assert len(violations) == 3
        assert all(v.tool == "cppcheck" for v in violations)
        # 诚实归一化：2.2 modified → 保留 c2012 身份
        assert violations[0].rule_id == "misra-c2012-2.2"
        assert violations[0].file == "src/brake.c"
        assert violations[0].line == 42
        assert violations[1].rule_id == "misra-c2023-15.5"
        assert violations[2].rule_id == "misra-c2023-2.5"
        # dict roundtrip 保留 tool 字段
        d = violations[0].to_dict()
        assert d["tool"] == "cppcheck"

    def test_suppress_rule_overrides_disabled(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)
        calls = {}

        def fake_run(cmd, **kwargs):
            calls["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stderr="", stdout="")

        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.subprocess.run", fake_run
        )
        from yuleosh.ci.config import MisraRuleOverride

        cfg = MisraConfig(
            rule_overrides=[MisraRuleOverride(rule_id="misra-c2023-8.13", enabled=False)]
        )
        CppcheckScannerAdapter().run(str(project), config=cfg, target_files=["src/brake.c"])
        assert "--suppress=misra-c2023-8.13" in calls["cmd"]

    def test_file_not_found_returns_error(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)

        def boom(*args, **kwargs):
            raise FileNotFoundError("cppcheck")

        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.subprocess.run", boom
        )
        result = CppcheckScannerAdapter().run(str(project), config=None, target_files=[])
        assert not result.ok
        assert "cppcheck not installed" in result.error
        assert "install cppcheck" in result.hint

    def test_timeout_returns_error(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired("cppcheck", 180)

        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.subprocess.run", boom
        )
        result = CppcheckScannerAdapter().run(str(project), config=None, target_files=[])
        assert not result.ok
        assert "timed out" in result.error

    def test_rule_texts_path_creates_addon_json(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)
        (project / "misra-rule-texts.txt").write_text("dummy")
        calls = {}

        def fake_run(cmd, **kwargs):
            calls["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stderr="", stdout="")

        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.subprocess.run", fake_run
        )
        cfg = MisraConfig(rule_texts_path="misra-rule-texts.txt")
        result = CppcheckScannerAdapter().run(str(project), config=cfg, target_files=["src/brake.c"])
        assert result.ok
        assert ".yuleosh" in calls["cmd"][1]  # addon arg = JSON config path
        assert (project / ".yuleosh" / "misra-addon-config.json").exists()

    def test_detect_uses_which(self, tmp_path, monkeypatch):
        project = _make_project(tmp_path)
        adapter = CppcheckScannerAdapter()
        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.shutil.which",
            lambda name: "/usr/bin/cppcheck" if name == "cppcheck" else None,
        )
        assert adapter.detect(str(project)) is True
        monkeypatch.setattr(
            "yuleosh.ci.scanners.cppcheck_adapter.shutil.which", lambda name: None
        )
        assert adapter.detect(str(project)) is False


class TestCppcheckParse:
    def test_parse_empty(self):
        assert CppcheckScannerAdapter().parse("") == []

    def test_parse_malformed_lines_ignored(self):
        adapter = CppcheckScannerAdapter()
        vs = adapter.parse("not a cppcheck line\njust text\n")
        assert vs == []
