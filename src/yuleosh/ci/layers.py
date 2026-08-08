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

log = logging.getLogger("ci.layers")

from yuleosh.ci.config import layer_dependencies
from yuleosh.ci.layers import (
    _SKIP_DIRS,
    _detect_project_language,
    _LayerTimeout,
    # executor
    _run_go_build,
    _run_go_layer1,
    _run_go_test,
    _run_go_vet,
    _run_layer1_impl,
    _run_python_layer1,
    # QG-007 profile-aware helpers (moved into the package, 2026-08-08)
    check_coverage_gate_with_profile,
    check_layer_dependency,
    format_layer_summary,
    # config
    get_latest_layer_result,
    get_profile_label,
    run_layer1,
    run_layer2,
    run_layer3,
    run_layer_25,
    # validator
    validate_layer_result,
)

# NOTE (2026-08-08): The profile-aware helpers were previously defined
# below.  Because ``import yuleosh.ci.layers`` resolves to the PACKAGE
# (ci/layers/__init__.py), definitions in this module were unreachable.
# They now live in the package and are re-exported above.

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
