#!/usr/bin/env python3

# @tests src/yuleosh/ci/config.py

"""Deep tests for ci/config.py — SWR-004.1 CI configurable."""

import pytest
from pathlib import Path

from yuleosh.ci.config import (
    CiConfig,
    MisraConfig,
    CoverageConfig,
    MisraProfile,
    MisraRuleOverride,
    MisraDeviation,
    AlmConfig,
    HardwareTestConfig,
    DEFAULT_COVERAGE_THRESHOLD_LINE,
    DEFAULT_COVERAGE_THRESHOLD_COND,
    DEFAULT_LAYERS,
    DEFAULT_LAYER_DEPENDENCIES,
    DEFAULT_CI_CONFIG_PATH,
    load_ci_config,
)


class TestCiConfigDefaults:
    def test_default_layers(self):
        config = CiConfig()
        assert config.layers == DEFAULT_LAYERS

    def test_default_coverage_threshold(self):
        cov = CoverageConfig()
        assert cov.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE
        assert cov.threshold_condition == DEFAULT_COVERAGE_THRESHOLD_COND

    def test_default_misra_enabled(self):
        misra = MisraConfig()
        assert misra.enabled is True
        assert misra.scanner == "cppcheck"

    def test_layer_dependencies(self):
        assert 1 in DEFAULT_LAYER_DEPENDENCIES
        assert DEFAULT_LAYER_DEPENDENCIES[1] == []
        assert 1 in DEFAULT_LAYER_DEPENDENCIES[2]

    def test_default_config_path(self):
        assert DEFAULT_CI_CONFIG_PATH == ".yuleosh/ci-config.yaml"


class TestMisraConfig:
    def test_default_addon(self):
        misra = MisraConfig()
        assert misra.addon == "misra"

    def test_default_exclude_paths(self):
        misra = MisraConfig()
        assert "tests/**" in misra.exclude_paths

    def test_fail_on_required_default(self):
        misra = MisraConfig()
        assert misra.fail_on_required is True

    def test_active_profile_default(self):
        misra = MisraConfig()
        assert misra.active_profile == "safety"


class TestMisraProfile:
    def test_default_profile_rules(self):
        profile = MisraProfile()
        assert "mandatory" in profile.rules
        assert "required" in profile.rules

    def test_profile_block_on(self):
        profile = MisraProfile()
        assert "mandatory" in profile.block_on

    def test_profile_with_overrides(self):
        override = MisraRuleOverride(rule_id="Rule 11.1", enabled=False)
        profile = MisraProfile(name="custom", rule_overrides=[override])
        assert profile.rule_overrides[0].rule_id == "Rule 11.1"
        assert profile.rule_overrides[0].enabled is False


class TestMisraDeviation:
    def test_deviation_defaults(self):
        dev = MisraDeviation()
        assert dev.status == "pending"
        assert dev.risk_level == "mid"

    def test_deviation_with_values(self):
        dev = MisraDeviation(
            rule_id="Rule 8.12",
            file_pattern="src/legacy/*.c",
            reason="Implicit enum",
            approved_by="lead",
            status="approved",
        )
        assert dev.rule_id == "Rule 8.12"
        assert dev.status == "approved"


class TestAlmConfig:
    def test_alm_defaults_disabled(self):
        alm = AlmConfig()
        assert alm.enabled is False
        assert alm.backend == ""

    def test_alm_with_jira(self):
        alm = AlmConfig(enabled=True, backend="jira", url="https://jira.example.com")
        assert alm.backend == "jira"


class TestCoverageConfig:
    def test_module_thresholds_empty(self):
        cov = CoverageConfig()
        assert cov.module_thresholds == {}

    def test_strict_default(self):
        cov = CoverageConfig()
        assert cov.strict is True


class TestLoadCiConfig:
    def test_load_missing_file_returns_defaults(self, tmp_path):
        config = load_ci_config(project_dir=str(tmp_path))
        assert isinstance(config, CiConfig)

    def test_load_valid_yaml(self, tmp_path):
        yaml_file = tmp_path / "ci-config.yaml"
        yaml_file.write_text("ci:\n  layers: [1, 2]\ncoverage:\n  threshold_line: 80.0\n")
        config = load_ci_config(project_dir=str(tmp_path), config_path="ci-config.yaml")
        assert config.layers == [1, 2]
        assert config.coverage.threshold_line == 80.0
