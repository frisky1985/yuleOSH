# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for CI configuration module — ci.config.

GIVEN a yuleOSH project directory
WHEN ci-config.yaml exists / doesn't exist
THEN load_ci_config returns correct defaults or parsed values.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.ci.config import (
    CiConfig,
    CoverageConfig,
    HardwareTestConfig,
    load_ci_config,
    DEFAULT_CI_CONFIG_PATH,
    DEFAULT_COVERAGE_THRESHOLD_LINE,
    DEFAULT_COVERAGE_THRESHOLD_COND,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def tmp_project():
    """Create a temporary project directory with minimal structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal .yuleosh directory
        yuleosh_dir = Path(tmpdir) / ".yuleosh"
        yuleosh_dir.mkdir(parents=True, exist_ok=True)

        # Create targets directory (used by other modules)
        targets_dir = yuleosh_dir / "targets"
        targets_dir.mkdir(exist_ok=True)

        yield tmpdir


@pytest.fixture
def with_default_config(tmp_project):
    """Write a default ci-config.yaml to the temp project."""
    cfg = {
        "ci": {
            "layers": [1, 2, 25, 3],
            "layer_dependencies": {1: [], 2: [1], 25: [1, 2], 3: [1, 2, 25]},
        },
        "coverage": {
            "threshold_line": 85.0,
            "threshold_condition": 80.0,
            "strict": True,
            "module_thresholds": {"src/cross/": 85.0, "src/ci/": 75.0},
        },
        "hardware_test": {
            "enabled": True,
            "firmware": "build/firmware.elf",
            "boot_pattern": "Boot Complete",
            "flash_tool": "openocd",
            "serial_port": "/dev/ttyACM0",
            "baud": 115200,
            "test_timeout": 30,
            "boot_delay": 2.0,
            "test_scripts_dir": "tests/hil",
            "mock": True,
        },
    }
    cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)
    return tmp_project


# ------------------------------------------------------------------
# Tests: Default config (no file exists)
# ------------------------------------------------------------------


class TestLoadCIConfigDefaults:
    """GIVEN no ci-config.yaml WHEN loading THEN return defaults."""

    def test_default_layers(self, tmp_project):
        """WHEN no config THEN layers include L2.5."""
        cfg = load_ci_config(tmp_project)
        assert 25 in cfg.layers
        assert 1 in cfg.layers
        assert 2 in cfg.layers
        assert 3 in cfg.layers

    def test_default_coverage(self, tmp_project):
        """WHEN no config THEN coverage defaults apply."""
        cfg = load_ci_config(tmp_project)
        assert cfg.coverage.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE
        assert cfg.coverage.threshold_condition == DEFAULT_COVERAGE_THRESHOLD_COND
        assert cfg.coverage.strict is False
        assert cfg.coverage.module_thresholds == {}

    def test_default_hardware_test(self, tmp_project):
        """WHEN no config THEN HIL defaults apply."""
        cfg = load_ci_config(tmp_project)
        assert cfg.hardware_test.enabled is True
        assert cfg.hardware_test.boot_pattern == "Boot Complete"
        assert cfg.hardware_test.flash_tool == "auto"
        assert cfg.hardware_test.mock is False

    def test_default_layer_dependencies(self, tmp_project):
        """WHEN no config THEN L2.5 depends on L1 and L2."""
        cfg = load_ci_config(tmp_project)
        deps = cfg.layer_dependencies
        assert 25 in deps
        assert 1 in deps[25]
        assert 2 in deps[25]
        assert 3 in deps
        assert 25 in deps[3]

    def test_default_ci_config_dataclass(self):
        """GIVEN CiConfig() default THEN all fields have sensible values."""
        cfg = CiConfig()
        assert 25 in cfg.layers
        assert isinstance(cfg.coverage, CoverageConfig)
        assert isinstance(cfg.hardware_test, HardwareTestConfig)


# ------------------------------------------------------------------
# Tests: Parsed config
# ------------------------------------------------------------------


class TestLoadCIConfigParsed:
    """GIVEN ci-config.yaml exists WHEN loading THEN parse correctly."""

    def test_parsed_layers(self, with_default_config):
        """WHEN config specifies layers THEN those are used."""
        cfg = load_ci_config(with_default_config)
        assert cfg.layers == [1, 2, 25, 3]

    def test_parsed_coverage(self, with_default_config):
        """WHEN config specifies coverage THEN thresholds are applied."""
        cfg = load_ci_config(with_default_config)
        assert cfg.coverage.threshold_line == 85.0
        assert cfg.coverage.threshold_condition == 80.0
        assert cfg.coverage.strict is True
        assert "src/cross/" in cfg.coverage.module_thresholds
        assert cfg.coverage.module_thresholds["src/cross/"] == 85.0

    def test_parsed_hardware_test(self, with_default_config):
        """WHEN config specifies HIL THEN settings are applied."""
        cfg = load_ci_config(with_default_config)
        assert cfg.hardware_test.enabled is True
        assert cfg.hardware_test.firmware == "build/firmware.elf"
        assert cfg.hardware_test.boot_pattern == "Boot Complete"
        assert cfg.hardware_test.flash_tool == "openocd"
        assert cfg.hardware_test.serial_port == "/dev/ttyACM0"
        assert cfg.hardware_test.baud == 115200
        assert cfg.hardware_test.test_timeout == 30
        assert cfg.hardware_test.boot_delay == 2.0
        assert cfg.hardware_test.mock is True

    def test_parse_partial_config(self, tmp_project):
        """WHEN config has partial fields THEN missing use defaults."""
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        partial = {
            "coverage": {"threshold_line": 90.0},
            "hardware_test": {"mock": True},
        }
        with open(cfg_path, "w") as f:
            json.dump(partial, f)

        cfg = load_ci_config(tmp_project)
        assert cfg.coverage.threshold_line == 90.0
        assert cfg.coverage.threshold_condition == DEFAULT_COVERAGE_THRESHOLD_COND
        assert cfg.hardware_test.mock is True
        assert cfg.hardware_test.boot_pattern == "Boot Complete"

    def test_parse_empty_config(self, tmp_project):
        """WHEN config is empty dict THEN all use defaults."""
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        with open(cfg_path, "w") as f:
            json.dump({}, f)

        cfg = load_ci_config(tmp_project)
        assert cfg.coverage.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE
        assert cfg.hardware_test.mock is False
        assert 25 in cfg.layers

    def test_parse_invalid_yaml(self, tmp_project):
        """WHEN config has invalid YAML THEN fall back to defaults."""
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        with open(cfg_path, "w") as f:
            f.write("{invalid: [broken")

        cfg = load_ci_config(tmp_project)
        assert cfg.coverage.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE

    def test_layer_dependencies_parsed(self, with_default_config):
        """WHEN config specifies layer deps THEN parsed correctly."""
        cfg = load_ci_config(with_default_config)
        assert cfg.layer_dependencies[1] == []
        assert cfg.layer_dependencies[2] == [1]
        assert 1 in cfg.layer_dependencies[25]
        assert 2 in cfg.layer_dependencies[25]

    def test_empty_yaml_fields(self, tmp_project):
        """WHEN coverage block is empty dict THEN use defaults."""
        cfg_path = Path(tmp_project) / ".yuleosh" / "ci-config.yaml"
        with open(cfg_path, "w") as f:
            json.dump({"coverage": {}}, f)

        cfg = load_ci_config(tmp_project)
        assert cfg.coverage.threshold_line == DEFAULT_COVERAGE_THRESHOLD_LINE


# ------------------------------------------------------------------
# Tests: CoverageConfig model
# ------------------------------------------------------------------


class TestCoverageConfig:
    """GIVEN CoverageConfig instances WHEN used THEN properties work."""

    def test_default_thresholds(self):
        """WHEN default THEN thresholds match constants."""
        cc = CoverageConfig()
        assert cc.effective_line == DEFAULT_COVERAGE_THRESHOLD_LINE
        assert cc.effective_condition == DEFAULT_COVERAGE_THRESHOLD_COND

    def test_custom_thresholds(self):
        """WHEN custom thresholds THEN effective matches."""
        cc = CoverageConfig(threshold_line=92.0, threshold_condition=88.0)
        assert cc.effective_line == 92.0
        assert cc.effective_condition == 88.0

    def test_module_thresholds(self):
        """WHEN module thresholds set THEN accessible."""
        cc = CoverageConfig(module_thresholds={"src/core/": 95.0})
        assert cc.module_thresholds["src/core/"] == 95.0


# ------------------------------------------------------------------
# Tests: HardwareTestConfig model
# ------------------------------------------------------------------


class TestHardwareTestConfig:
    """GIVEN HardwareTestConfig instances WHEN used THEN properties work."""

    def test_default_hw(self):
        """WHEN default THEN mock is False."""
        hw = HardwareTestConfig()
        assert hw.mock is False
        assert hw.flash_tool == "auto"

    def test_mock_enabled(self):
        """WHEN mock=True THEN mock mode is on."""
        hw = HardwareTestConfig(mock=True)
        assert hw.mock is True
