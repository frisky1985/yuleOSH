#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Stages package.

Backward-compatible re-export: all names are re-exported here so that
    from yuleosh.pipeline.stages import _call_llm
continues to work after the split.

Internal modules:
  stages/utils.py  — timed_step decorator
  stages/llm.py    — _call_llm, _check_llm_key
  stages/spec.py   — _parse_spec, _parse_requirements, _parse_scenarios,
                     _try_parse_hermes_json, spec cache
"""

import logging

from yuleosh.pipeline.stages.utils import timed_step
from yuleosh.pipeline.stages.llm import _call_llm, _check_llm_key
from yuleosh.pipeline.stages.spec import (
    _get_spec_mtime,
    _parse_spec,
    _parse_requirements,
    _parse_scenarios,
    _try_parse_hermes_json,
)

log = logging.getLogger("pipeline.stages")

__all__ = [
    "timed_step",
    "_call_llm",
    "_get_spec_mtime",
    "_parse_spec",
    "_parse_requirements",
    "_parse_scenarios",
    "_check_llm_key",
    "_try_parse_hermes_json",
]
