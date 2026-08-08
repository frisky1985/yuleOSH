# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
CI Layers — package (Phase 2.5 refactor split from layers.py).

Split into:
  - layer_config.py  — 配置、依赖、语言检测
  - layer_executor.py — 各层执行函数
  - layer_validator.py — 验证与结果处理

Backward-compatible re-exports.
"""

import logging

from yuleosh.ci.config import layer_dependencies
from yuleosh.ci.layers.layer_config import (
    _SKIP_DIRS,
    _detect_project_language,
    _LayerTimeout,
    check_layer_dependency,
    get_latest_layer_result,
)
from yuleosh.ci.layers.layer_executor import (
    _run_go_build,
    _run_go_layer1,
    _run_go_test,
    _run_go_vet,
    _run_layer1_impl,
    _run_python_layer1,
    run_layer1,
    run_layer2,
    run_layer3,
    run_layer_25,
)
from yuleosh.ci.layers.layer_validator import (
    format_layer_summary,
    validate_layer_result,
)

log = logging.getLogger("ci.layers")

# QG-007 profile-aware helpers.  These used to live in the legacy
# ``ci/layers.py`` module, which became unreachable after the Phase 2.5
# package split (``import yuleosh.ci.layers`` resolves to this package,
# shadowing the module).  Moved here so they are importable again
# (2026-08-08, coverage Phase 2).


def check_coverage_gate_with_profile(
    project_dir: str,
    coverage_data: dict | None = None,
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
        except Exception as e:  # noqa: BLE001 - non-fatal config degradation
            logging.getLogger("ci.layers").warning(
                "Could not apply profile '%s': %s", profile, e
            )

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
    except Exception:  # noqa: BLE001 - fallback label on any error
        return "ci"


__all__ = [
    "_SKIP_DIRS",
    "_LayerTimeout",
    "_detect_project_language",
    "_run_go_build",
    "_run_go_layer1",
    "_run_go_test",
    "_run_go_vet",
    "_run_layer1_impl",
    "_run_python_layer1",
    "check_coverage_gate_with_profile",
    "check_layer_dependency",
    "format_layer_summary",
    "get_latest_layer_result",
    "get_profile_label",
    "layer_dependencies",
    "run_layer1",
    "run_layer2",
    "run_layer3",
    "run_layer_25",
    "validate_layer_result",
]
