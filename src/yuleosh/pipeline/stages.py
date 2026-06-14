#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Stages — step handler functions, spec parsing, LLM call helper,
PIPELINE_STEPS definition, and utility decorators.

Import chain:  orchestrator -> stages -> session
               steps -> stages (for _call_llm, _parse_spec)
"""

import functools
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.llm.client import chat_completion
from yuleosh.pipeline.prompts import (
    build_super_analysis_prompt,
    build_prd_prompt,
    build_architecture_prompt,
    build_development_prompt,
    build_test_planning_prompt,
    build_code_review_prompt,
    build_final_report_prompt,
    build_internal_review_prompt,
)

log = logging.getLogger("pipeline.stages")

# Store for spec cache (lazy init)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from store import Store
    _store = Store()
except Exception as e:
    logging.getLogger("pipeline.stages").warning("Store init failed: %s", e)
    _store = None
finally:
    _p = os.path.join(os.path.dirname(__file__), "..")
    while _p in sys.path:
        sys.path.remove(_p)

_llm_client = chat_completion


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


# ------------------------------------------------------------------
# Spec cache — stores parsed results in SQLite keyed by path+mtime
# ------------------------------------------------------------------


def _get_spec_mtime(spec_path: str) -> float:
    """Return file mtime for cache invalidation."""
    try:
        return Path(spec_path).stat().st_mtime
    except OSError:
        return 0.0


def _call_llm(
    session: PipelineSession,
    system_prompt: str,
    user_prompt: str,
    **kwargs,
) -> dict:
    """Call LLM using the session's injected client or fall back to global chat_completion.

    This is the single point of dependency injection for LLM calls in pipeline steps.
    Tests can inject a mock via ``PipelineSession(llm_client=mock_fn)``.
    """
    client = session.llm_client if session.llm_client is not None else chat_completion
    return client(system_prompt, user_prompt, **kwargs)


# --- Step Handlers ---

@timed_step
def _parse_spec(spec_path: str) -> dict:
    """Parse spec file: returns requirements + scenarios, cached via SQLite.

    Cache is invalidated when the spec file's mtime changes.
    """
    mtime = _get_spec_mtime(spec_path)

    # Try cache hit
    if _store:
        try:
            cached = _store.get_cached_spec_parse(spec_path, mtime)
            if cached is not None:
                return cached
        except Exception as e:
            log.warning(f"Spec cache read failed (will re-parse): {e}")

    # Parse fresh
    requirements = _parse_requirements(spec_path)
    scenarios = _parse_scenarios(spec_path)
    result = {"requirements": requirements, "scenarios": scenarios}

    # Store in cache
    if _store:
        try:
            _store.cache_spec_parse(spec_path, mtime, result)
        except Exception as e:
            log.warning(f"Spec cache write failed (non-fatal): {e}")

    return result


def _parse_requirements(spec_path: str) -> list[dict]:
    """Read requirements from a spec file. Each requirement is a dict with name and shall_statements."""
    requirements = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found: {spec_path}")
            return requirements
        content = path.read_text()
        lines = content.split("\n")
        current_name = None
        current_shalls = []
        in_requirement = False
        for line in lines:
            stripped = line.strip()
            # Detect requirement header: ### Req-XXX:
            if stripped.startswith("### ") and "Req-" in stripped:
                if current_name:
                    requirements.append({
                        "name": current_name,
                        "shall_statements": current_shalls
                    })
                current_name = stripped.replace("### ", "")
                current_shalls = []
                in_requirement = True
            elif in_requirement and stripped.startswith("-") and ("SHALL" in stripped or "SHOULD" in stripped):
                current_shalls.append(stripped)
            elif in_requirement and stripped.startswith("### ") and "Req-" not in stripped:
                # End of requirement, next section (Scenario or other)
                in_requirement = False
        if current_name:
            requirements.append({
                "name": current_name,
                "shall_statements": current_shalls
            })
    except Exception as e:
        log.warning(f"Failed to parse requirements from {spec_path}: {e}")
    return requirements


def _parse_scenarios(spec_path: str) -> list[str]:
    """Read GIVEN/WHEN/THEN scenarios from a spec file."""
    scenarios = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found for scenarios: {spec_path}")
            return scenarios
        content = path.read_text()
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("### ") and ("GIVEN" in stripped or "WHEN" in stripped or "THEN" in stripped):
                scenarios.append(stripped.replace("### ", ""))
    except Exception as e:
        log.warning(f"Failed to parse scenarios from {spec_path}: {e}")
    return scenarios
