# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""ScannerAdapter — registry / Violation / canonicalize / config 单测（2026-08-19 P1）。

验收标准 #2：ScannerRegistry 可注册/获取适配器；未配置的工具 detect 返回 False
且 skip 不报错。
"""

import pytest

from yuleosh.ci.scanners import (
    ScannerRegistry,
    Violation,
    canonicalize_rule_id,
    extract_rule_number,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """单例注册表测试隔离：每测试前后重建内置。"""
    ScannerRegistry().reset()
    yield
    ScannerRegistry().reset()


# ===================================================================
# Violation 模型
# ===================================================================


class TestViolation:
    def test_to_dict_roundtrip_lossless(self):
        v = Violation(
            rule_id="misra-c2023-10.1", severity="warning", file="src/a.c",
            line=42, message="m", tool="cppcheck", column=5, rule_year="2012",
        )
        d = v.to_dict()
        assert d["tool"] == "cppcheck"
        assert d["rule_year"] == "2012"
        assert Violation.from_dict(d).to_dict() == d

    def test_from_dict_preserves_extra_keys(self):
        d = {
            "rule_id": "x", "file": "f.c", "line": 1, "severity": "error",
            "message": "m", "tool": "t", "custom_key": "keep",
        }
        v = Violation.from_dict(d)
        assert v.extra["custom_key"] == "keep"
        assert v.to_dict()["custom_key"] == "keep"

    def test_to_dict_omits_empty_optional_fields(self):
        """空值可选字段省略，下游 v.get() 兜底语义不变（零回归）。"""
        v = Violation(rule_id="r", file="f", line=1, severity="error",
                      message="m", tool="t")
        d = v.to_dict()
        assert "severity_category" not in d
        assert "code_category" not in d
        assert "file_rel" not in d
        assert d["column"] == 0


# ===================================================================
# 规则 ID 映射
# ===================================================================


class TestExtractRuleNumber:
    @pytest.mark.parametrize("raw,expected", [
        ("MISRA.C.2012.10.1", "10.1"),
        ("MISRA_C_2023_Rule_10_1", "10.1"),
        ("MISRA-C-2012-Rule-15-7", "15.7"),
        ("MISRA.C.2023.17.7", "17.7"),
        ("Rule 10.1", "10.1"),
        ("Dir 4.1", "4.1"),
        ("10.1", "10.1"),
        ("2.5", "2.5"),
        ("", ""),
        ("no-rule-here", ""),
    ])
    def test_extract(self, raw, expected):
        assert extract_rule_number(raw) == expected


class TestCanonicalizeRuleId:
    @pytest.mark.parametrize("raw,expected", [
        # 规范键：10.1 modified → 保留 c2012 身份（诚实规则）
        ("misra-c2012-10.1", "misra-c2012-10.1"),
        # 规范键：17.7 unchanged → re-label c2023
        ("misra-c2012-17.7", "misra-c2023-17.7"),
        # 文本形式
        ("Rule 10.1", "misra-c2023-10.1"),
        ("Dir 4.1", "misra-c2023-dir-4.1"),
        ("10.1", "misra-c2023-10.1"),
        # 商业工具格式（C:2012 工具 → 诚实映射）
        ("MISRA.C.2012.10.1", "misra-c2012-10.1"),
        ("MISRA-C-2012-Rule-15-7", "misra-c2023-15.7"),
        # 商业工具格式（C:2023 工具 → c2023 映射）
        ("MISRA_C_2023_Rule_10_1", "misra-c2023-10.1"),
        ("MISRA.C.2023.17.7", "misra-c2023-17.7"),
        ("2.5", "misra-c2023-2.5"),
        ("", ""),
    ])
    def test_mapping(self, raw, expected):
        assert canonicalize_rule_id(raw) == expected


# ===================================================================
# ScannerRegistry
# ===================================================================


class TestScannerRegistry:
    def test_default_is_cppcheck(self):
        reg = ScannerRegistry()
        assert reg.get().name == "cppcheck"
        assert reg.get("cppcheck").name == "cppcheck"

    def test_builtins_registered(self):
        names = ScannerRegistry().available()
        assert "cppcheck" in names
        assert "parasoft" in names
        assert "qac" in names
        assert "ldra" in names
        assert "mcp" in names

    def test_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown scanner"):
            ScannerRegistry().get("nonexistent-scanner")

    def test_register_custom_adapter(self):
        from yuleosh.ci.scanners.base import ScannerAdapter, ScannerResult

        class FakeScanner(ScannerAdapter):
            name = "fake"
            display_name = "Fake Scanner"

            def run(self, project_dir, config=None, target_files=None, **kwargs):
                return ScannerResult(tool=self.name, raw_output="")

            def parse(self, raw):
                return []

        reg = ScannerRegistry()
        reg.register(FakeScanner)
        assert reg.get("fake").name == "fake"
        assert reg.is_registered("fake")
        assert "fake" in reg.names()

    def test_register_requires_name(self):
        from yuleosh.ci.scanners.base import ScannerAdapter

        class NoName(ScannerAdapter):
            display_name = "x"

            def run(self, project_dir, config=None, target_files=None, **kwargs):
                raise NotImplementedError

            def parse(self, raw):
                return []

        with pytest.raises(ValueError, match="must define name"):
            ScannerRegistry().register(NoName)

    def test_unconfigured_tool_detect_false_no_error(self):
        """验收 #2：未配置的商业工具 detect 返回 False 且不抛错。"""
        reg = ScannerRegistry()
        for name in ("qac", "parasoft", "ldra", "mcp"):
            adapter = reg.get(name)
            assert adapter.detect("/tmp/does-not-exist") is False

    def test_reset_restores_builtins(self):
        reg = ScannerRegistry()
        reg.reset()
        assert "cppcheck" in reg.available()
        assert len(reg.names()) == 5


# ===================================================================
# misra.scanner 配置解析
# ===================================================================


class TestScannerConfig:
    def test_config_parses_scanner_and_scanner_config(self, tmp_path):
        from yuleosh.ci.config import load_ci_config
        (tmp_path / ".yuleosh").mkdir()
        (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
            "misra:\n"
            "  scanner: qac\n"
            "  scanner_config:\n"
            "    cli_path: qacli\n"
            "    profile: MISRA_C_2023\n"
        )
        cfg = load_ci_config(str(tmp_path))
        assert cfg.misra.scanner == "qac"
        assert cfg.misra.scanner_config["cli_path"] == "qacli"
        assert cfg.misra.scanner_config["profile"] == "MISRA_C_2023"

    def test_default_scanner_is_cppcheck(self):
        from yuleosh.ci.config import MisraConfig
        assert MisraConfig().scanner == "cppcheck"
        assert MisraConfig().scanner_config == {}

    def test_yaml_validator_accepts_scanner_keys(self, tmp_path):
        from yuleosh.ci.yaml_validator import validate_ci_config
        (tmp_path / ".yuleosh").mkdir()
        cfg_path = tmp_path / ".yuleosh" / "ci-config.yaml"
        cfg_path.write_text(
            "misra:\n"
            "  scanner: parasoft\n"
            "  scanner_config:\n"
            "    cli_path: cpptestcli\n"
        )
        result = validate_ci_config(str(cfg_path))
        assert result.get("valid") is True, result.get("errors")
