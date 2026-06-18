
"""
yuleOSH CI Configuration — load and validate `.yuleosh/ci-config.yaml`.

Provides a typed dataclass for CI config with sensible defaults.
Supports per-project overrides for coverage thresholds, layer enabling,
and HIL test configuration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import json

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
DEFAULT_MISRA_ADDON = "misra"  # misra-c-2023 | misra-c-2012


# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass
class MisraRuleOverride:
    """Per-rule override for MISRA C:2023 analysis.

    Allows selectively enabling/disabling individual rules,
    overriding severity levels, and overriding auto-checkability.
    """

    rule_id: str = ""
    enabled: bool = True
    severity_override: str = ""  # Optional: advisory | required | warning
    auto_checkable_override: bool | None = None


@dataclass
class MisraDeviation:
    """Deviation record for a specific MISRA rule on a file pattern.

    Documents a deliberate waiver, requiring approval and expiry.
    When active, matching violations are marked "acknowledged"
    in the traceability matrix.
    """

    rule_id: str = ""
    file_pattern: str = ""  # glob pattern, e.g. "src/legacy/*.c"
    reason: str = ""
    approved_by: str = ""
    expires: str = ""  # ISO date, e.g. "2026-09-30"
    status: str = "pending"  # pending | approved | rejected


@dataclass
class MisraProfile:
    """A named MISRA profile with rule overrides and deviations.

    Profiles allow quick switching between different compliance modes:
    - "safety": Strictest, all rules enabled (default)
    - "performance": Relaxed rules for performance-critical code
    - "testing": Relaxed rules for test / non-production code
    """
    name: str = ""
    rule_overrides: list[MisraRuleOverride] = field(default_factory=list)
    deviations: list[MisraDeviation] = field(default_factory=list)
    severity_map: dict = field(default_factory=dict)


@dataclass
class AlmConfig:
    """ALM (Application Lifecycle Management) integration configuration.

    Attributes
    ----------
    enabled : bool
        Whether ALM integration is active.
    backend : str
        ALM system type: ``"jira"`` | ``"polarion"`` | ``"codebeamer"``.
    url : str
        Base URL of the ALM instance.
    project_key : str
        Project key or space name in the ALM system.
    api_token : str
        API token or password for authentication.
        Reading from environment variables (e.g. ``ALM_API_TOKEN``) is
        strongly recommended over hard-coding.
    """

    enabled: bool = False
    backend: str = ""  # "jira" | "polarion" | "codebeamer"
    url: str = ""
    project_key: str = ""
    api_token: str = ""  # 从环境变量读取更安全


@dataclass
class MisraConfig:
    """MISRA C:2023 static analysis configuration (A-03)."""

    enabled: bool = True
    addon: str = DEFAULT_MISRA_ADDON  # 'misra' or 'misra-c-2023' or 'misra-c-2012'
    fail_on_violation: bool = True
    fail_on_advisory: bool = False
    fail_threshold: int = 10
    violations_per_kloc: float = 2.0
    cppcheck_std: str = "c11"
    suppress_rules: list = field(default_factory=list)
    rule_texts_path: str = ""
    rule_overrides: list[MisraRuleOverride] = field(default_factory=list)
    deviations: list[MisraDeviation] = field(default_factory=list)
    _deviation_raw: list[dict] = field(default_factory=list)  # preserve raw YAML order for writing
    alm: AlmConfig = field(default_factory=AlmConfig)
    active_profile: str = "safety"  # "safety" | "performance" | "testing"
    profiles: dict[str, MisraProfile] = field(default_factory=dict)


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
    misra: MisraConfig = field(default_factory=MisraConfig)


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

    # MISRA block
    misra_block = raw.get("misra", {})
    if isinstance(misra_block, dict):
        cfg.misra.enabled = bool(misra_block.get("enabled", True))
        cfg.misra.addon = str(misra_block.get("addon", DEFAULT_MISRA_ADDON))
        cfg.misra.fail_on_violation = bool(misra_block.get("fail_on_violation", True))
        cfg.misra.fail_on_advisory = bool(misra_block.get("fail_on_advisory", False))
        cfg.misra.fail_threshold = int(misra_block.get("fail_threshold", 10))
        cfg.misra.violations_per_kloc = float(misra_block.get("violations_per_kloc", 2.0))
        cfg.misra.cppcheck_std = str(misra_block.get("cppcheck_std", "c11"))
        suppress = misra_block.get("suppress_rules", [])
        if isinstance(suppress, list):
            cfg.misra.suppress_rules = [str(s) for s in suppress]
        cfg.misra.rule_texts_path = str(misra_block.get("rule_texts_path", ""))
        cfg.misra.active_profile = str(misra_block.get("active_profile", "safety"))

        # Parse profiles block
        profiles_block = misra_block.get("profiles", {})
        if isinstance(profiles_block, dict):
            parsed_profiles: dict[str, MisraProfile] = {}
            for prof_name, prof_cfg in profiles_block.items():
                if not isinstance(prof_cfg, dict):
                    continue
                ovr_list: list[MisraRuleOverride] = []
                for ovr in prof_cfg.get("rule_overrides", []):
                    if isinstance(ovr, dict):
                        ovr_list.append(MisraRuleOverride(
                            rule_id=str(ovr.get("rule", "")),
                            enabled=bool(ovr.get("enabled", True)),
                            severity_override=str(ovr.get("severity", "")),
                        ))
                dev_list: list[MisraDeviation] = []
                for d in prof_cfg.get("deviations", []):
                    if isinstance(d, dict):
                        dev_list.append(MisraDeviation(
                            rule_id=str(d.get("rule", "")),
                            file_pattern=str(d.get("file", "")),
                            reason=str(d.get("reason", "")),
                            approved_by=str(d.get("approved_by", "")),
                            expires=str(d.get("expires", "")),
                            status=str(d.get("status", "pending")),
                        ))
                parsed_profiles[prof_name] = MisraProfile(
                    name=str(prof_cfg.get("name", "")),
                    rule_overrides=ovr_list,
                    deviations=dev_list,
                    severity_map=prof_cfg.get("severity_map", {}),
                )
            cfg.misra.profiles = parsed_profiles

        # Parse rule_overrides
        rules_block = misra_block.get("rules", {})
        if isinstance(rules_block, dict):
            overrides: list[MisraRuleOverride] = []
            for rule_id, rule_cfg in rules_block.items():
                if isinstance(rule_cfg, dict):
                    overrides.append(MisraRuleOverride(
                        rule_id=str(rule_id),
                        enabled=bool(rule_cfg.get("enabled", True)),
                        severity_override=str(rule_cfg.get("severity", "")),
                        auto_checkable_override=(
                            bool(rule_cfg["auto_checkable"])
                            if "auto_checkable" in rule_cfg
                            else None
                        ),
                    ))
            cfg.misra.rule_overrides = overrides

        # Parse deviations
        deviations_block = misra_block.get("deviations", [])
        if isinstance(deviations_block, list):
            dev_list: list[MisraDeviation] = []
            dev_raw_list: list[dict] = []
            for d in deviations_block:
                if isinstance(d, dict):
                    dev_list.append(MisraDeviation(
                        rule_id=str(d.get("rule", "")),
                        file_pattern=str(d.get("file", "")),
                        reason=str(d.get("reason", "")),
                        approved_by=str(d.get("approved_by", "")),
                        expires=str(d.get("expires", "")),
                        status=str(d.get("status", "pending")),
                    ))
                    dev_raw_list.append(d)
            cfg.misra.deviations = dev_list
            cfg.misra._deviation_raw = dev_raw_list

        # ALM block (nested under misra)
        alm_block = misra_block.get("alm", {})
        if isinstance(alm_block, dict):
            cfg.misra.alm.enabled = bool(alm_block.get("enabled", False))
            cfg.misra.alm.backend = str(alm_block.get("backend", ""))
            cfg.misra.alm.url = str(alm_block.get("url", ""))
            cfg.misra.alm.project_key = str(alm_block.get("project_key", ""))
            # API token may come from config or from env var for safety
            cfg.misra.alm.api_token = str(alm_block.get("api_token", ""))
            env_token = os.environ.get("ALM_API_TOKEN", "")
            if env_token:
                cfg.misra.alm.api_token = env_token

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


# CI config cache (module-level, shared across all imports)
_ci_config_cache: dict[str, "CiConfig"] = {}


def _get_ci_config(project_dir: str = "") -> "CiConfig":
    """Load and cache CI configuration from ``.yuleosh/ci-config.yaml``."""
    if project_dir not in _ci_config_cache:
        from yuleosh.ci.config import CiConfig, load_ci_config  # type: ignore[import-untyped]
        _ci_config_cache[project_dir] = load_ci_config(project_dir)
    return _ci_config_cache.get(project_dir)  # type: ignore[return-value]


def _clear_ci_config_cache() -> None:
    """Clear the CI config cache (used in tests)."""
    _ci_config_cache.clear()


# ------------------------------------------------------------------
# Strict mode helpers
# ------------------------------------------------------------------


def is_strict() -> bool:
    """Check if CI is running in strict mode (CI_STRICT=1).

    In strict mode, missing tools cause pipeline failure instead of
    silent skip.  Any stage with FileNotFoundError blocks the pipeline.
    """
    return os.environ.get("CI_STRICT", "0") == "1"


def is_misra_fail_fast() -> bool:
    """Check if MISRA_FAIL_FAST is active.

    When enabled, MISRA/CppCheck or clang-tidy failures (non-zero exit)
    block the pipeline immediately instead of producing warnings.
    """
    return os.environ.get("MISRA_FAIL_FAST", "0") == "1"


# ------------------------------------------------------------------
# Layer dependency configuration (A-03)
# ------------------------------------------------------------------

# Layer dependency chain: each layer lists its upstream dependencies.
# L1 has no dependencies.  L2 depends on L1.  L2.5 depends on L1 and L2.
# L3 depends on L1, L2, and L2.5.
# Order: L1 → L2 → L2.5 → L3.
layer_dependencies: dict[int, list[int]] = {
    1: [],
    2: [1],
    25: [1, 2],
    3: [1, 2, 25],
}


# ------------------------------------------------------------------
# Deviation YAML helpers
# ------------------------------------------------------------------


def _deviations_to_yaml_dicts(deviations: list[MisraDeviation]) -> list[dict]:
    """Convert MisraDeviation list to YAML-serializable dict list.

    Preserves the field order expected by ci-config.yaml:
    rule, file, reason, approved_by, expires, status.
    """
    result: list[dict] = []
    for d in deviations:
        result.append({
            "rule": d.rule_id,
            "file": d.file_pattern,
            "reason": d.reason,
            "approved_by": d.approved_by,
            "expires": d.expires,
            "status": d.status,
        })
    return result


def update_deviation_status(
    project_dir: str,
    rule_id: str,
    file_pattern: str,
    new_status: str,
) -> bool:
    """Update the status of a deviation record in ci-config.yaml.

    This performs an in-memory update via PyYAML and writes the file back,
    preserving all other fields.  Returns True on success, False if the
    deviation is not found or YAML write fails.
    """
    import yaml

    path = Path(project_dir) / DEFAULT_CI_CONFIG_PATH
    if not path.exists():
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return False

    # Navigate to deviations list
    misra_block = raw.get("misra", {})
    if not isinstance(misra_block, dict):
        return False

    deviations = misra_block.get("deviations", [])
    if not isinstance(deviations, list):
        return False

    found = False
    for d in deviations:
        if isinstance(d, dict) and d.get("rule") == rule_id and d.get("file") == file_pattern:
            d["status"] = new_status
            found = True
            break

    if not found:
        return False

    # Write back
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except (yaml.YAMLError, OSError):
        return False


