#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Stages — utility decorators.

Extracted from stages.py (Phase 2.1 refactor, P0-4).
"""

import functools
import logging
import time

log = logging.getLogger("pipeline.stages.utils")


def timed_step(handler):
    """Decorate a step handler to measure and log execution time."""
    @functools.wraps(handler)
    def wrapper(session):
        t0 = time.perf_counter()
        try:
            result = handler(session)
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} FAILED after {elapsed:.3f}s")
            raise
    return wrapper
