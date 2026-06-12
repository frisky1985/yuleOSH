# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH CI Configuration — load and validate `.yuleosh/ci-config.yaml`.

Provides a typed dataclass for CI config with sensible defaults.
Supports per-project overrides for coverage thresholds, layer enabling,
and HIL test configuration.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.config")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

DEFAULT_CI_CONFIG_PATH = ".yuleosh/ci-config.yaml"

DEFAULT_LAYERS = [1, 2, 25, 3]
DEFAULT_LAYER_DEPENDENCIES: dict[int, list[int]] = {
    1: [],
    2: [1],
    25: [1, 2],
    3: [1, 2, 25],
}

DEFAULT_COVERAGE_THRESHOLD_LINE = 85.0
DEFAULT_COVERAGE_THRESHOLD_COND = 80.0
DEFAULT_STRICT = False


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass
class CoverageConfig:
    """Coverage gate configuration (SWR-003.2)."""

    threshold_line: float = DEFAULT_COVERAGE_THRESHOLD_LINE
    threshold_condition: float = DEFAULT_COVERAGE_THRESHOLD_COND
    strict: bool = DEFAULT_STRICT
    module_thresholds: dict[str, float] = field(default_factory=dict)

    @property
    def effective_line(self) -> float:
        return self.threshold_line

    @property
    def effective_condition(self) -> float:
        return self.threshold_condition


@dataclass
class HardwareTestConfig:
    """L2.5 HIL test configuration."""

    enabled: bool = True
    firmware: str = "build/firmware.elf"
    boot_pattern: str = "Boot Complete"
    flash_tool: str = "auto"
    serial_port: str = ""
    baud: int = 115200
    test_timeout: int = 30
    boot_delay: float = 2.0
    test_scripts_dir: str = "tests/hil"
    mock: bool = False


@dataclass
class CiConfig:
    """Complete CI configuration for a yuleOSH project."""

    layers: list[int] = field(default_factory=lambda: list(DEFAULT_LAYERS))
    layer_dependencies: dict[int, list[int]] = field(
        default_factory=lambda: dict(DEFAULT_LAYER_DEPENDENCIES)
    )
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    hardware_test: HardwareTestConfig = field(default_factory=HardwareTestConfig)


# ------------------------------------------------------------------
# Loader
# ------------------------------------------------------------------


def load_ci_config(
    project_dir: Optional[str] = None,
    config_path: Optional[str] = None,
) -> CiConfig:
    """Load CI configuration from ``.yuleosh/ci-config.yaml``.

    If the file does not exist, returns a default :class:`CiConfig`.
    Missing fields use defaults.

    Parameters
    ----------
    project_dir : str, optional
        Project root directory. Defaults to ``OSH_HOME`` or current directory.
    config_path : str, optional
        Explicit path to config file (relative to project_dir).

    Returns
    -------
    CiConfig
        Parsed configuration with defaults for any missing fields.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    path = config_path or DEFAULT_CI_CONFIG_PATH
    full_path = os.path.join(project_dir, path)

    if not os.path.exists(full_path):
        log.info("CI config not found at %s — using defaults", full_path)
        return CiConfig()

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        # No yaml installed — try reading as JSON
        try:
            with open(full_path) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, Exception):
            log.warning("Cannot parse %s — using defaults", full_path)
            return CiConfig()
    else:
        try:
            with open(full_path) as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError:
            log.warning("Invalid YAML in %s — using defaults", full_path)
            return CiConfig()

    return _parse_ci_config(raw)


def _parse_ci_config(raw: dict | None) -> CiConfig:
    """Parse raw dict into a CiConfig dataclass."""
    if not raw:
        return CiConfig()

    cfg = CiConfig()

    # CI block
    ci_block = raw.get("ci", {})
    if isinstance(ci_block, dict):
        if "layers" in ci_block and isinstance(ci_block["layers"], list):
            cfg.layers = [int(l) for l in ci_block["layers"]]
        if "layer_dependencies" in ci_block and isinstance(
            ci_block["layer_dependencies"], dict
        ):
            deps: dict[int, list[int]] = {}
            for k, v in ci_block["layer_dependencies"].items():
                deps[int(k)] = [int(x) for x in v]
            cfg.layer_dependencies = deps

    # Coverage block
    cov_block = raw.get("coverage", {})
    if isinstance(cov_block, dict):
        cfg.coverage.threshold_line = float(
            cov_block.get("threshold_line", DEFAULT_COVERAGE_THRESHOLD_LINE)
        )
        cfg.coverage.threshold_condition = float(
            cov_block.get("threshold_condition", DEFAULT_COVERAGE_THRESHOLD_COND)
        )
        cfg.coverage.strict = bool(cov_block.get("strict", DEFAULT_STRICT))
        module_thresholds = cov_block.get("module_thresholds", {})
        if isinstance(module_thresholds, dict):
            cfg.coverage.module_thresholds = {
                k: float(v) for k, v in module_thresholds.items()
            }

    # Hardware test block
    hw_block = raw.get("hardware_test", {})
    if isinstance(hw_block, dict):
        cfg.hardware_test.enabled = bool(hw_block.get("enabled", True))
        cfg.hardware_test.firmware = str(
            hw_block.get("firmware", cfg.hardware_test.firmware)
        )
        cfg.hardware_test.boot_pattern = str(
            hw_block.get("boot_pattern", cfg.hardware_test.boot_pattern)
        )
        cfg.hardware_test.flash_tool = str(
            hw_block.get("flash_tool", cfg.hardware_test.flash_tool)
        )
        cfg.hardware_test.serial_port = str(
            hw_block.get("serial_port", cfg.hardware_test.serial_port)
        )
        cfg.hardware_test.baud = int(hw_block.get("baud", cfg.hardware_test.baud))
        cfg.hardware_test.test_timeout = int(
            hw_block.get("test_timeout", cfg.hardware_test.test_timeout)
        )
        cfg.hardware_test.boot_delay = float(
            hw_block.get("boot_delay", cfg.hardware_test.boot_delay)
        )
        cfg.hardware_test.test_scripts_dir = str(
            hw_block.get("test_scripts_dir", cfg.hardware_test.test_scripts_dir)
        )
        cfg.hardware_test.mock = bool(hw_block.get("mock", False))

    return cfg
