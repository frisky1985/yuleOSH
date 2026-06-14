#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
CI Result — CIResult data class + timed_stage decorator.

Shared by runner, layers, and stages.
Zero circular dependencies — imported by all other ci modules.
"""

import functools
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci.result")


def timed_stage(func):
    """Decorate a CI stage handler to measure and log execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            log.info(f"Stage {func.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.info(f"Stage {func.__name__} FAILED after {elapsed:.3f}s")
            raise
    return wrapper


class CIResult:
    """Captures CI result for a single layer."""

    def __init__(self, layer: int, commit_hash: str):
        self.layer = layer
        self.commit_hash = commit_hash
        self.started_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.status = "running"
        self.stages: list[dict] = []
        self.coverage: Optional[dict] = None
        self.errors: list[str] = []

    def add_stage(self, name: str, status: str, detail: str = ""):
        """Record a stage result."""
        self.stages.append({
            "name": name,
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        })

    def complete(self, status: str = "passed"):
        """Mark the CI layer as complete."""
        self.status = status
        self.completed_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "commit": self.commit_hash,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stages": self.stages,
            "coverage": self.coverage,
            "errors": self.errors,
        }
