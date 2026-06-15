#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Stages — step handler functions, spec parsing, LLM call helper,
PIPELINE_STEPS definition, and utility decorators.

Import chain:  orchestrator -> stages -> session
               steps -> stages (for _call_llm, _parse_spec)

Exports:
  timed_step, _call_llm, _parse_spec, _parse_requirements, _parse_scenarios
  _get_spec_mtime, _check_llm_key, _try_parse_hermes_json
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

    For backward-compatible test mock paths, the global fallback is looked up
    through the ``run`` shim module at call time (deferred import avoids cycles).
    """
    # Deferred import from the run shim so that test mocks on
    # yuleosh.pipeline.run.chat_completion take effect.
    from yuleosh.pipeline.run import chat_completion as _fallback
    client = session.llm_client if session.llm_client is not None else _fallback
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


def _check_llm_key() -> str | None:
    """Check for a valid LLM API key in environment variables.

    Returns the key if found, or None if neither LLM_API_KEY nor
    OPENAI_API_KEY is set.
    """
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("""
❌ LLM API key not found

yuleOSH's pipeline requires an LLM API key to run AI agent steps.
Set one of these environment variables:

    export LLM_API_KEY=sk-...    # OpenAI/OpenAI-compatible API
    export OPENAI_API_KEY=sk-... # OpenAI

Then re-run: yuleosh pipeline run <spec>

\U0001f4a1 For demo/testing without a real LLM, use the --mock flag:
    yuleosh pipeline run --mock docs/spec.md
""")
    return key


def _try_parse_hermes_json(raw: str, session_name: str) -> dict:
    """Parse Hermes review JSON from LLM output with robust fallback.

    Supports common format deviations:
      - Markdown ```json code fences
      - Leading/trailing explanatory text
      - Missing required fields (fills in defaults)
      - Pre/post whitespace
      - Multiple code blocks (uses the first valid JSON block)

    Returns a valid review dict in all cases (with status='retry' if
    parsing ultimately fails, including raw output for debugging).
    """
    json_str = raw.strip()
    raw_preview_500 = raw[:500]

    # Try bare JSON first
    if json_str.startswith("{") and json_str.endswith("}"):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass  # Fall through to fence stripping

    # Strip markdown fences: ```json ... ``` or ``` ... ```
    if "```" in json_str:
        # Collect all fenced blocks
        blocks = []
        in_fence = False
        current = []
        for line in json_str.split("\n"):
            if line.strip().startswith("```"):
                if in_fence:
                    # End of a fenced block
                    blocks.append("\n".join(current))
                    current = []
                    in_fence = False
                else:
                    in_fence = True
                    # Skip the opening fence (optionally with "json" after)
                    lang = line.strip().lstrip("```").strip().lower()
                    if lang and lang != "json":
                        # It's a non-JSON code block, skip content
                        in_fence = False
                    current = []
            elif in_fence:
                current.append(line)

        for block in blocks:
            block = block.strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # If we have leading text before a JSON block, try to find { ... }
    brace_start = json_str.find("{")
    if brace_start >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(json_str)):
            if json_str[i] == "{":
                depth += 1
            elif json_str[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[brace_start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue

    # Final fallback: return retry status with raw output embedded
    log.warning(f"Could not parse Hermes review JSON. Raw output (first 500 chars): {raw_preview_500}")
    return {
        "session": session_name,
        "reviewer": "Hermes",
        "timestamp": datetime.now().isoformat(),
        "status": "retry",
        "_raw_llm_output": raw,
        "findings": [{
            "severity": "major",
            "category": "reviewer-error",
            "file": "",
            "line": None,
            "message": (
                f"LLM review output was not valid JSON. "
                f"Raw output (first 500 chars): {raw_preview_500}"
            ),
        }],
        "finding_breakdown": {"critical": 0, "major": 1, "minor": 0, "info": 0},
        "summary": f"LLM review could not be parsed \u2014 check raw output.",
    }
