#!/usr/bin/env python3

# @req RS-001
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
LLM Fallback Strategy — 5-level progressive fallback for LLM output.

When a pipeline step calls an LLM, the output goes through a multi-level
fallback chain.  At each level, validation is performed.  If validation
fails, the system retries (up to a configured limit) before escalating
to the next fallback level.

Levels:
  0 — Raw pass-through (no validation — legacy behaviour)
  1 — Schema validation → reject if format violation, retry 2x
  2 — Content validation → reject if missing required fields, retry 2x
  3 — Semantic validation → reject if contradiction with context, retry 1x
  4 — Template fallback → use default template with LLM suggestions as comments
  5 — Abort step → mark failed, block pipeline

Usage::

    from yuleosh.llm.fallback import apply_fallback_chain, FallbackResult

    result = apply_fallback_chain(
        step_name="my-step",
        llm_output=raw_llm_text,
        schema={"required_fields": ["title", "summary"]},
        template="# Title\\n\\n{{summary}}",
        session_dir=Path("/path/to/session"),
    )
    if result.status == "abort":
        # Step failed — do not run dependent steps
        ...

Failures are logged to ``.yuleosh/reports/llm-validation-failures.jsonl``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from yuleosh.llm.validation import validate_llm_output

log = logging.getLogger("llm.fallback")


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class FallbackResult:
    """Result of applying the fallback chain to an LLM output.

    Attributes
    ----------
    status : str
        One of ``"ok"``, ``"fallback"``, ``"abort"``.
    output : str
        The final output (original, retried, or template).
    level : int
        The fallback level that produced the output (0-5).
    retries : int
        Number of retry attempts made.
    errors : list[str]
        Validation/error messages from the chain.
    confidence : float | None
        LLM self-reported confidence (0.0–1.0) parsed from the
        ``CONFIDENCE: <value>`` line appended to the output (H3-1c).
        None when the line is absent.
    """
    status: str = "ok"          # ok | fallback | abort
    output: str = ""
    level: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    confidence: Optional[float] = None


# ------------------------------------------------------------------
# Default templates for fallback
# ------------------------------------------------------------------

DEFAULT_TEMPLATES: dict[str, str] = {
    "spec": (
        "# {title}\n\n"
        "> This document was generated with template fallback "
        "(LLM output was invalid after retries).\n\n"
        "## Requirements\n\n"
        "- SHALL {description}\n"
        "- SHOULD be tested\n"
        "- MAY be extended\n"
    ),
    "review": (
        "# Review: {title}\n\n"
        "> This review was generated with template fallback "
        "(LLM output was invalid after retries).\n\n"
        "## Findings\n\n"
        "- (no findings — LLM failed)\n"
    ),
    "plan": (
        "# Plan: {title}\n\n"
        "> This plan was generated with template fallback "
        "(LLM output was invalid after retries).\n\n"
        "## Steps\n\n"
        "- Define requirements\n"
        "- Implement\n"
        "- Test\n"
    ),
    "default": (
        "# {title}\n\n"
        "> This document was generated with template fallback "
        "(LLM output was invalid after retries).\n\n"
        "## Content\n\n"
        "The LLM was unable to produce valid output for this step.\n"
        "Review the validation failures and re-run the pipeline.\n"
    ),
}


# ------------------------------------------------------------------
# Confidence extraction (H3-1c)
# ------------------------------------------------------------------

_CONFIDENCE_RE = re.compile(
    r"(?:^|\n)CONFIDENCE:\s*([01](?:\.\d+)?|\.\d+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_confidence(text: str) -> tuple[str, Optional[float]]:
    """Extract and strip the ``CONFIDENCE: <value>`` line from LLM output.

    Returns ``(cleaned_text, confidence)`` where ``confidence`` is a float
    in [0.0, 1.0] or None if not present.  Values outside [0, 1] are
    clamped silently.
    """
    m = _CONFIDENCE_RE.search(text)
    if not m:
        return text, None
    try:
        raw = float(m.group(1))
        confidence = max(0.0, min(1.0, raw))
    except ValueError:
        return text, None
    cleaned = _CONFIDENCE_RE.sub("", text).rstrip()
    return cleaned, confidence


# ------------------------------------------------------------------
# Retry callable (invokes the LLM with error feedback)
# ------------------------------------------------------------------


def _make_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    """Build a retry prompt with validation error feedback."""
    error_text = "\n".join(f"- {e}" for e in errors)
    return (
        f"{original_prompt}\n\n"
        f"---\n"
        f"### Correction Required\n\n"
        f"The previous response had the following validation errors:\n"
        f"{error_text}\n\n"
        f"Please fix these issues and respond again. "
        f"Pay attention to the required format and content structure.\n"
    )


# ------------------------------------------------------------------
# Fallback chain state
# ------------------------------------------------------------------


class _FallbackState:
    """Internal state for the fallback chain."""

    def __init__(
        self,
        step_name: str,
        session_dir: Optional[Path],
    ):
        self.step_name = step_name
        self.session_dir = session_dir
        self.current_level = 0
        self.retries = 0
        self.errors: list[str] = []
        self.output = ""
        self.llm_call: Optional[Callable] = None
        self.original_prompt = ""
        self.schema: dict = {}
        self.template: str = ""
        self.template_ctx: dict = {}
        self.start_time = time.time()

    def get_elapsed(self) -> float:
        return time.time() - self.start_time

    def log_failure(self, level: int, error: str) -> None:
        """Log a validation failure to .yuleosh/reports/llm-validation-failures.jsonl."""
        self.errors.append(error)
        log.warning("Fallback level %d: %s", level, error)

        # Write to failures file
        if self.session_dir:
            yuleosh_dir = self._find_yuleosh_dir()
            if yuleosh_dir:
                report_dir = yuleosh_dir / "reports"
                report_dir.mkdir(parents=True, exist_ok=True)
                failures_file = report_dir / "llm-validation-failures.jsonl"
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "step": self.step_name,
                    "level": level,
                    "error": error,
                    "retries": self.retries,
                    "elapsed_s": round(self.get_elapsed(), 3),
                }
                try:
                    with open(failures_file, "a") as f:
                        f.write(json.dumps(entry) + "\n")
                except OSError as e:
                    log.warning("Failed to write validation failure log: %s", e)

    def _find_yuleosh_dir(self) -> Optional[Path]:
        """Find the .yuleosh directory from session_dir."""
        if not self.session_dir:
            return None
        # Walk up from session_dir
        p = self.session_dir.resolve()
        while p.parent != p:
            candidate = p / ".yuleosh"
            if candidate.is_dir():
                return candidate
            p = p.parent
        return None


# ------------------------------------------------------------------
# Level implementators
# ------------------------------------------------------------------


def _level_0_raw(state: _FallbackState) -> FallbackResult:
    """Level 0: Raw pass-through (no validation)."""
    return FallbackResult(
        status="ok",
        output=state.output,
        level=0,
        retries=0,
        errors=[],
    )


def _level_1_schema(state: _FallbackState) -> FallbackResult:
    """Level 1: Schema validation → retry up to 2x."""
    if not state.schema:
        return _level_0_raw(state)

    state.current_level = 1
    for attempt in range(3):  # 1 original + 2 retries
        if attempt > 0:
            state.retries += 1
            log.info("Level 1 retry %d/2 for step '%s'", attempt, state.step_name)
            state.output = _retry_llm(state)

        if not state.output:
            state.log_failure(1, "LLM returned empty output")
            continue

        validation = validate_llm_output(state.output, state.schema)
        if validation["valid"]:
            return FallbackResult(
                status="ok",
                output=state.output,
                level=1,
                retries=state.retries,
                errors=[],
            )
        error_msg = "; ".join(validation["errors"])
        state.log_failure(1, f"Schema validation failed: {error_msg}")

    return FallbackResult(
        status="fallback",
        output=state.output,
        level=1,
        retries=state.retries,
        errors=state.errors[-3:],
    )


def _level_2_content(state: _FallbackState) -> FallbackResult:
    """Level 2: Content validation → retry up to 2x."""
    state.current_level = 2
    for attempt in range(3):  # 1 + 2 retries
        if attempt > 0:
            state.retries += 1
            log.info("Level 2 retry %d/2 for step '%s'", attempt, state.step_name)
            state.output = _retry_llm(state)

        if not state.output:
            state.log_failure(2, "LLM returned empty output")
            continue

        # Content validation: check for required fields and minimum content
        content_schema = dict(state.schema)
        content_schema.setdefault("type", "string")
        content_schema.setdefault("min_length", 50)
        validation = validate_llm_output(state.output, content_schema)
        if validation["valid"]:
            return FallbackResult(
                status="ok",
                output=state.output,
                level=2,
                retries=state.retries,
                errors=[],
            )
        error_msg = "; ".join(validation["errors"])
        state.log_failure(2, f"Content validation failed: {error_msg}")

    return FallbackResult(
        status="fallback",
        output=state.output,
        level=2,
        retries=state.retries,
        errors=state.errors[-3:],
    )


def _level_3_semantic(state: _FallbackState) -> FallbackResult:
    """Level 3: Semantic validation → retry up to 1x."""
    state.current_level = 3
    for attempt in range(2):  # 1 + 1 retry
        if attempt > 0:
            state.retries += 1
            log.info("Level 3 retry for step '%s'", state.step_name)
            state.output = _retry_llm(state)

        if not state.output:
            state.log_failure(3, "LLM returned empty output")
            continue

        # Contradiction detection: flag obvious contradictions
        contradictions = _detect_contradictions(state.output, state.schema)
        if not contradictions:
            return FallbackResult(
                status="ok",
                output=state.output,
                level=3,
                retries=state.retries,
                errors=[],
            )
        error_msg = "; ".join(contradictions)
        state.log_failure(3, f"Semantic validation failed: {error_msg}")

    return FallbackResult(
        status="fallback",
        output=state.output,
        level=3,
        retries=state.retries,
        errors=state.errors[-3:],
    )


def _level_4_template(state: _FallbackState) -> FallbackResult:
    """Level 4: Template fallback → use default template."""
    state.current_level = 4
    state.log_failure(4, "Falling back to default template")

    template = state.template or DEFAULT_TEMPLATES.get(
        state.step_name,
        DEFAULT_TEMPLATES["default"],
    )
    ctx = dict(state.template_ctx)
    ctx.setdefault("title", state.step_name.replace("_", " ").title())
    ctx.setdefault("description", "requirements to be defined")

    try:
        output = template.format(**ctx)
    except KeyError as e:
        log.warning("Template fallback: missing context key %s", e)
        output = DEFAULT_TEMPLATES["default"].format(
            title=ctx.get("title", state.step_name),
        )

    return FallbackResult(
        status="fallback",
        output=output,
        level=4,
        retries=state.retries,
        errors=state.errors,
    )


def _level_5_abort(state: _FallbackState) -> FallbackResult:
    """Level 5: Abort step → mark failed."""
    state.current_level = 5
    state.log_failure(
        5,
        "All fallback levels exhausted — aborting step",
    )

    return FallbackResult(
        status="abort",
        output="",
        level=5,
        retries=state.retries,
        errors=state.errors,
    )


# ------------------------------------------------------------------
# Retry helper
# ------------------------------------------------------------------


def _retry_llm(state: _FallbackState) -> str:
    """Call the LLM with error feedback from previous attempts."""
    if not state.llm_call:
        log.warning("No LLM callable configured for retry — returning empty")
        return ""

    try:
        retry_prompt = _make_retry_prompt(
            state.original_prompt, state.errors[-3:]
        )
        # The LLM callable is expected to accept a string prompt and
        # return a dict with a "content" key.
        result = state.llm_call(retry_prompt)
        if isinstance(result, dict):
            return result.get("content", "")
        return str(result)
    except Exception as e:
        log.error("LLM retry failed: %s", e)
        return ""


# ------------------------------------------------------------------
# Contradiction detection
# ------------------------------------------------------------------


def _detect_contradictions(output: str, schema: dict) -> list[str]:
    """Detect contradictions in LLM output.

    Simple checks:
    - "must not" vs "SHALL" (if schema has shalls_required)
    - Affirmative vs negative pairs on same subject
    """
    contradictions: list[str] = []
    text_lower = output.lower()

    # Check for "must not" / "shall not" alongside "SHALL" (if shalls are required)
    if schema.get("shalls_required", False):
        if "shall not" in text_lower and "shall" in text_lower:
            contradictions.append(
                "Output contains both 'SHALL' and 'shall not' — "
                "possible contradiction"
            )

    # Check for "must" vs "must not" pairs
    must_sentences = [
        s.strip() for s in output.split(".") if "must" in s.lower()
    ]
    for s in must_sentences:
        if "must not" in s.lower() and "must" in s.lower():
            # Only flag if the sentence is contradictory
            contradictions.append(
                f"Contradictory statement: '{s.strip()}'"
            )

    return contradictions


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def apply_fallback_chain(
    step_name: str,
    llm_output: str,
    *,
    schema: Optional[dict] = None,
    template: Optional[str] = None,
    template_ctx: Optional[dict] = None,
    session_dir: Optional[Path] = None,
    llm_call: Optional[Callable] = None,
    original_prompt: str = "",
    start_level: int = 0,
) -> FallbackResult:
    """Apply the 5-level fallback chain to an LLM output.

    Parameters
    ----------
    step_name : str
        Name of the pipeline step (for logging).
    llm_output : str
        The raw LLM output to validate.
    schema : dict, optional
        Schema for validation at levels 1-3.
    template : str, optional
        Custom template for level 4 fallback.  Defaults are provided
        for known step types (``"spec"``, ``"review"``, ``"plan"``).
    template_ctx : dict, optional
        Template context variables (e.g. ``{"title": "..."}``).
    session_dir : Path, optional
        Session directory (for failure logging).
    llm_call : Callable, optional
        Function to retry the LLM.  Called with the retry prompt
        (str) and expected to return a dict with a ``"content"`` key
        or a plain string.
    original_prompt : str
        The original prompt sent to the LLM (used for retry).
    start_level : int
        Starting fallback level (default 0 = full chain).

    Returns
    -------
    FallbackResult
        Result with status, output, level, retries, and errors.

    Raises
    ------
    RuntimeError
        If the fallback chain itself fails catastrophically.
    """
    state = _FallbackState(
        step_name=step_name,
        session_dir=session_dir,
    )
    # H3-1c: extract confidence from the raw output before validation.
    cleaned_output, confidence = _extract_confidence(llm_output)
    state.output = cleaned_output
    state.schema = schema or {}
    state.template = template or ""
    state.template_ctx = template_ctx or {}
    state.llm_call = llm_call
    state.original_prompt = original_prompt

    def _with_confidence(result: FallbackResult) -> FallbackResult:
        result.confidence = confidence
        return result

    # Run the chain starting from start_level
    # Level 0 is only used when NO schema is provided (raw passthrough)
    if not state.schema:
        if start_level <= 0:
            l0 = _level_0_raw(state)
            if l0.status == "ok" and l0.output:
                return _with_confidence(l0)

    # Level 1: Schema validation (always runs when schema is provided)
    if start_level <= 1 and state.schema:
        l1 = _level_1_schema(state)
        if l1.status == "ok":
            return _with_confidence(l1)

    # Level 2: Content validation
    if start_level <= 2:
        l2 = _level_2_content(state)
        if l2.status == "ok":
            return _with_confidence(l2)

    if start_level <= 3:
        l3 = _level_3_semantic(state)

    # Level 4: Template fallback — always returns usable output
    l4 = _level_4_template(state)
    if l4.output:
        return _with_confidence(l4)

    # Level 5: Abort (only if even template fallback returns nothing)
    l5 = _level_5_abort(state)
    return _with_confidence(l5)
