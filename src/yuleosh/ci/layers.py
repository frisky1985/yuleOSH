#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CI Layers — backward-compatible re-export module.

This module has been split into ``ci/layers/`` package (Phase 2.5 refactor).
All public symbols are re-exported here for backward compatibility.

See ``ci/layers/`` package for implementation details:
  - layer_config.py  — 配置、依赖、语言检测
  - layer_executor.py — 各层执行函数
  - layer_validator.py — 验证与结果处理

QG-007 (CI Profile): Additional helpers for profile-aware gate checks.
"""

import logging
from typing import Optional

log = logging.getLogger("ci.layers")

from yuleosh.ci.config import layer_dependencies, validate_misra_profiles

from yuleosh.ci.layers import (
    # config
    get_latest_layer_result,
    check_layer_dependency,
    _detect_project_language,
    _LayerTimeout,
    _SKIP_DIRS,
    # executor
    _run_go_build,
    _run_go_vet,
    _run_go_test,
    _run_go_layer1,
    _run_python_layer1,
    _run_layer1_impl,
    run_layer1,
    run_layer2,
    run_layer_25,
    run_layer3,
    # validator
    validate_layer_result,
    format_layer_summary,
)


# ------------------------------------------------------------------
# Profile-aware gate helpers (QG-007)
# ------------------------------------------------------------------


def check_coverage_gate_with_profile(
    project_dir: str,
    coverage_data: Optional[dict] = None,
    override_strict: bool = False,
    profile: str = "",
) -> tuple[bool, list[str]]:
    """Check coverage gate using profile-aware thresholds.

    Applies the specified CI environment profile to the config before
    checking the coverage gate.  This ensures the correct thresholds
    are used for development vs CI vs production runs.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    coverage_data : dict, optional
        Coverage report data.
    override_strict : bool
        If True, bypass strict mode blocking.
    profile : str
        CI environment profile: development, ci, or production.
        Empty string means "ci" (default).

    Returns
    -------
    tuple[bool, list[str]]
        (passed, messages)
    """
    # Apply profile to config before checking gate
    if profile:
        try:
            from yuleosh.ci.config import _get_ci_config, load_ci_profile_into_config
            cfg = _get_ci_config(project_dir)
            load_ci_profile_into_config(cfg, profile)
        except Exception as e:
            log.warning("Could not apply profile '%s': %s", profile, e)

    # Delegate to the standard coverage gate check (now profile-aware)
    from yuleosh.ci.runner import check_coverage_gate as _check_gate
    return _check_gate(
        project_dir, coverage_data, override_strict=override_strict,
    )


def get_profile_label(project_dir: str) -> str:
    """Get the active CI profile label for display.

    Returns one of: development, ci, production
    Falls back to "ci" on any error.
    """
    try:
        from yuleosh.ci.config import _get_ci_config
        cfg = _get_ci_config(project_dir)
        return getattr(cfg, "ci_profile", "ci")
    except Exception:
        return "ci"


__all__ = [
    "get_latest_layer_result",
    "check_layer_dependency",
    "_detect_project_language",
    "_LayerTimeout",
    "_SKIP_DIRS",
    "_run_go_build",
    "_run_go_vet",
    "_run_go_test",
    "_run_go_layer1",
    "_run_python_layer1",
    "_run_layer1_impl",
    "run_layer1",
    "run_layer2",
    "run_layer_25",
    "run_layer3",
    "validate_layer_result",
    "format_layer_summary",
    "layer_dependencies",
    "check_coverage_gate_with_profile",
    "get_profile_label",
]
