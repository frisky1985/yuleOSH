#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Stages — utility decorators.

Extracted from stages.py (Phase 2.1 refactor, P0-4).
"""

import functools
import logging
import time

log = logging.getLogger("pipeline.stages.utils")


def timed_step(handler):
    """Decorate a step handler to measure and log execution time.

    Accepts *args/**kwargs so it works both on plain functions
    ``step_xxx(session)`` and on bound methods like
    ``BaseHandler.__call__(self, session)`` — a fixed ``wrapper(session)``
    signature dropped ``self`` and broke callable handler instances
    (QemuTestHandler, v3.12.0 regression).
    """
    @functools.wraps(handler)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            result = handler(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} FAILED after {elapsed:.3f}s")
            raise
    return wrapper
