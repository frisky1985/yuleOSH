"""Unit tests for yuleosh.ci.config — pure Python, no external deps."""

# @tests src/yuleosh/ci/run.py

import pytest
from yuleosh.ci.config import (
    CoverageConfig,
    HardwareTestConfig,
    MisraConfig,
    MisraRuleOverride,
    MisraDeviation,
    MisraProfile,
    CiConfig,
    AlmConfig,
    DEFAULT_COVERAGE_THRESHOLD_LINE,
    DEFAULT_COVERAGE_THRESHOLD_COND,
    DEFAULT_STRICT,
    DEFAULT_MISRA_ADDON,
)


class TestDefaults:
    def test_default_thresholds(self):
        assert DEFAULT_COVERAGE_THRESHOLD_LINE == 50.0
        assert DEFAULT_COVERAGE_THRESHOLD_COND == 50.0
        assert DEFAULT_STRICT is True
        assert DEFAULT_MISRA_ADDON == "misra"


class TestMisraRuleOverride:
    def test_defaults(self):
        mro = MisraRuleOverride()
        assert mro.rule_id == ""
        assert mro.enabled is True

    def test_with_rule_id(self):
        mro = MisraRuleOverride(rule_id="R1")
        assert mro.rule_id == "R1"


class TestMisraDeviation:
    def test_defaults(self):
        md = MisraDeviation()
        assert md.status == "pending"
        assert md.risk_level == "mid"

    def test_with_rule(self):
        md = MisraDeviation(rule_id="R1", file_pattern="*.c", reason="legacy")
        assert md.rule_id == "R1"
        assert md.reason == "legacy"


class TestMisraProfile:
    def test_defaults(self):
        mp = MisraProfile()
        assert mp.name == ""

    def test_named(self):
        mp = MisraProfile(name="strict")
        assert mp.name == "strict"
        assert "mandatory" in mp.rules


class TestAlmConfig:
    def test_defaults(self):
        cfg = AlmConfig()
        assert cfg.enabled is False
        assert cfg.backend == ""


class TestCoverageConfig:
    def test_defaults(self):
        cfg = CoverageConfig()
        assert cfg.threshold_line == 50.0
        assert cfg.threshold_condition == 50.0
        assert cfg.strict is True

    def test_effective_properties(self):
        cfg = CoverageConfig(threshold_line=80.0, threshold_condition=70.0)
        assert cfg.effective_line == 80.0
        assert cfg.effective_condition == 70.0

    def test_c_fail_under_default(self):
        cfg = CoverageConfig()
        assert cfg.c_fail_under == 70

    def test_c_fail_under_branch_default_none(self):
        """branch gate 默认关闭（None）— 向后兼容。"""
        cfg = CoverageConfig()
        assert cfg.c_fail_under_branch is None

    def test_c_fail_under_branch_settable(self):
        cfg = CoverageConfig(c_fail_under_branch=45.0)
        assert cfg.c_fail_under_branch == 45.0


class TestHardwareTestConfig:
    def test_defaults(self):
        cfg = HardwareTestConfig()
        assert cfg.enabled is True
        assert cfg.firmware == "build/firmware.elf"
        assert cfg.mock is False


class TestMisraConfig:
    def test_defaults(self):
        cfg = MisraConfig()
        assert cfg.addon == "misra"
        assert cfg.fail_on_required is True
        assert cfg.active_profile == "safety"

    def test_custom(self):
        cfg = MisraConfig(addon="misra-c-2023", fail_on_required=False)
        assert cfg.addon == "misra-c-2023"
        assert cfg.fail_on_required is False


class TestCiConfig:
    def test_defaults(self):
        cfg = CiConfig()
        assert isinstance(cfg.coverage, CoverageConfig)
        assert isinstance(cfg.misra, MisraConfig)
        assert isinstance(cfg.hardware_test, HardwareTestConfig)

    def test_layers_default(self):
        cfg = CiConfig()
        assert 1 in cfg.layers
        assert 3 in cfg.layers
