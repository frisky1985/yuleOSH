#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Layers — package (Phase 2.5 refactor split from layers.py).

Split into:
  - layer_config.py  — 配置、依赖、语言检测
  - layer_executor.py — 各层执行函数
  - layer_validator.py — 验证与结果处理

Backward-compatible re-exports.
"""

import logging
log = logging.getLogger("ci.layers")

from yuleosh.ci.config import layer_dependencies

from yuleosh.ci.layers.layer_config import (
    get_latest_layer_result,
    check_layer_dependency,
    _detect_project_language,
    _LayerTimeout,
    _SKIP_DIRS,
)

from yuleosh.ci.layers.layer_config import (
    get_latest_layer_result,
    check_layer_dependency,
    _detect_project_language,
    _LayerTimeout,
    _SKIP_DIRS,
)

from yuleosh.ci.layers.layer_executor import (
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
)

from yuleosh.ci.layers.layer_validator import (
    validate_layer_result,
    format_layer_summary,
)

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
]
