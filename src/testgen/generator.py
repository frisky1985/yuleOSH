#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
TestGen Generator — AI-powered test case generation from OpenSpec.

Reads a spec file via the spec engine, constructs a structured LLM prompt,
parses the LLM response into TestCase objects, and supports coverage and
effectiveness estimation.
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("testgen.generator")

# ── Ensure spec module on path for standalone usage ──────────────────────────
_SPEC_SRC = Path(__file__).resolve().parent.parent / "spec"
if str(_SPEC_SRC) not in sys.path:
    sys.path.insert(0, str(_SPEC_SRC))

from validate import parse_spec  # noqa: E402


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class TestCase:
    """A single test case derived from an OpenSpec SHALL/SHOULD/MAY statement.

    Attributes:
        id:              Unique test case identifier (e.g. "TC-001").
        shall_ref:       The requirement id this test case maps to (e.g. "RS-001").
        scenario:        Short human-readable scenario name.
        given:           GIVEN precondition phrase.
        when:            WHEN trigger / action phrase.
        then:            THEN assertion / expected behaviour phrase.
        priority:        Priority level: P0 (critical), P1 (important), P2 (nice-to-have).
        tags:            Classification tags, e.g. ["smoke", "regression", "unit", "integration"].
    """
    id: str
    shall_ref: str
    scenario: str
    given: str
    when: str
    then: str
    priority: str = "P1"
    tags: list[str] = field(default_factory=lambda: ["unit"])

    def to_dict(self) -> dict:
        return asdict(self)


# ── Prompt Templates ─────────────────────────────────────────────────────────


_GENERATE_SYSTEM_PROMPT = """You are an expert embedded-systems test engineer.
Given an OpenSpec document, produce structured test cases in GIVEN/WHEN/THEN format.

Rules:
1. Generate at least one test case for every SHALL statement.
2. Include boundary/value-range test cases where applicable.
3. Include negative/error test cases for robustness.
4. Priority: P0 = safety/critical, P1 = normal functional, P2 = edge cases.
5. Tags: choose from smoke, regression, unit, integration, boundary, negative, performance.
6. Output ONLY a JSON array of objects with these keys:
   id (str), shall_ref (str), scenario (str), given (str), when (str), then (str),
   priority (str), tags (list[str]).
7. Do NOT wrap in markdown code fences — output raw JSON."""

_GENERATE_USER_TEMPLATE = """Generate test cases for the following OpenSpec document.

--- REQUIREMENTS ---
{requirements_json}

--- SCENARIOS ---
{scenarios_json}

Total SHALL statements: {shall_count}
Total existing scenarios: {scenario_count}

Generate comprehensive test cases covering all SHALL statements, with appropriate
positive, negative, and boundary test coverage. Return ONLY a JSON array."""

_EFFECTIVENESS_SYSTEM_PROMPT = """You are an embedded-systems QA analyst.
Evaluate a set of test cases against an OpenSpec document for coverage and effectiveness.

Respond with a JSON object containing:
- shall_coverage_pct (float): percentage of SHALL statements with at least one test
- boundary_coverage_pct (float): percentage of test cases covering boundary/edge values
- negative_tests (int): count of negative/error test cases
- estimation (str): "excellent", "good", "fair", or "poor"
- gaps (list[str]): description of uncovered scenarios

Output raw JSON only, no markdown fences."""


# ── Generator ─────────────────────────────────────────────────────────────────


class TestGenerator:
    """AI-powered test case generator from OpenSpec.

    Usage:
        gen = TestGenerator(llm_provider)
        cases = gen.generate_from_spec("path/to/spec.md")
        code = gen.generate_code_tests(cases, lang="c")
    """

    def __init__(self, llm_provider: Any):
        """Initialize with an LLM provider module.

        The provider must expose a ``chat_completion`` function with signature:
            chat_completion(system_prompt, user_prompt, *,
                            temperature=0.3, max_tokens=4096) -> dict
        returning at least ``{"content": str}``.
        """
        self.llm = llm_provider

    # ── Public API ────────────────────────────────────────────────────────

    def generate_from_spec(
        self,
        spec_path: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> list[TestCase]:
        """Read an OpenSpec file, invoke the LLM, and return parsed TestCase objects.

        Args:
            spec_path:  Path to an OpenSpec markdown file.
            temperature: LLM temperature (lower = more deterministic).
            max_tokens:  Maximum tokens in the LLM response.

        Returns:
            A list of TestCase instances derived from the spec.
        """
        # 1. Parse the spec
        doc = parse_spec(spec_path)
        log.info("Parsed spec: %d requirements, %d scenarios", len(doc.requirements), len(doc.scenarios))

        # 2. Build the prompt
        user_prompt = self._build_prompt(doc)

        # 3. Call the LLM
        response = self.llm.chat_completion(
            _GENERATE_SYSTEM_PROMPT,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = response.get("content", "")
        log.info("LLM responded (%d chars)", len(raw))

        # 4. Parse the response
        cases = self._parse_response(raw)

        # 5. Enrich metadata
        for i, case in enumerate(cases, start=1):
            if not case.id:
                case.id = f"TC-{i:03d}"

        log.info("Generated %d test cases", len(cases))
        return cases

    def generate_code_tests(
        self,
        test_cases: list[TestCase],
        lang: str = "c",
    ) -> str:
        """Convert a list of TestCase objects into executable test code.

        Args:
            test_cases: List of TestCase objects.
            lang:       Target language: "c", "python", or "go".

        Returns:
            A string containing the generated test code.
        """
        from .formatter import format_pytest, format_gotest, format_ceedling

        fmt_map = {
            "python": format_pytest,
            "c": format_ceedling,
            "go": format_gotest,
        }
        fmt = fmt_map.get(lang)
        if fmt is None:
            raise ValueError(f"Unsupported language: {lang!r}. Choose from: {list(fmt_map)}")

        return fmt(test_cases)

    def estimate_effectiveness(
        self,
        test_cases: list[TestCase],
        spec_path: Optional[str] = None,
        doc: Any = None,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> dict:
        """Evaluate test case coverage and effectiveness against the spec.

        One of ``spec_path`` or ``doc`` must be provided.

        Returns:
            dict with keys: shall_coverage_pct, boundary_coverage_pct,
            negative_tests, estimation, gaps.
        """
        if doc is None and spec_path is not None:
            doc = parse_spec(spec_path)
        elif doc is None:
            raise ValueError("Either spec_path or doc must be provided")

        shall_count = sum(len(r.shall) for r in doc.requirements)
        cases_json = json.dumps([c.to_dict() for c in test_cases], ensure_ascii=False)
        reqs_json = json.dumps(
            [r.to_dict() for r in doc.requirements],
            ensure_ascii=False,
        )

        user_prompt = (
            f"--- Test Cases ---\n{cases_json}\n\n"
            f"--- Requirements ---\n{reqs_json}\n\n"
        )

        response = self.llm.chat_completion(
            _EFFECTIVENESS_SYSTEM_PROMPT,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw = response.get("content", "")
        result = self._try_parse_json(raw)
        if result is None:
            result = {
                "shall_coverage_pct": 0.0,
                "boundary_coverage_pct": 0.0,
                "negative_tests": 0,
                "estimation": "poor",
                "gaps": ["Failed to parse LLM effectiveness response"],
            }
        result["shall_count"] = shall_count
        result["test_case_count"] = len(test_cases)
        return result

    def quick_coverage(
        self,
        test_cases: list[TestCase],
        spec_path: Optional[str] = None,
        doc: Any = None,
    ) -> dict:
        """Compute a simple deterministic coverage estimate (no LLM call).

        Counts how many unique SHALL references the test cases cover,
        and classifies tags for boundary/negative detection.
        """
        if doc is None and spec_path is not None:
            doc = parse_spec(spec_path)
        elif doc is None:
            raise ValueError("Either spec_path or doc must be provided")

        # Collect all SHALL ref IDs from requirements
        all_shall_refs: set[str] = set()
        for r in doc.requirements:
            for _ in r.shall:
                all_shall_refs.add(r.req_id or r.name)

        covered_refs: set[str] = set()
        boundary_count = 0
        negative_count = 0

        for tc in test_cases:
            ref = tc.shall_ref.strip()
            if ref in all_shall_refs:
                covered_refs.add(ref)
            if "boundary" in tc.tags:
                boundary_count += 1
            if "negative" in tc.tags:
                negative_count += 1

        total = len(all_shall_refs)
        covered = len(covered_refs)
        shall_cov = (covered / total * 100.0) if total else 100.0
        bc = (boundary_count / len(test_cases) * 100.0) if test_cases else 0.0

        return {
            "shall_coverage_pct": round(shall_cov, 1),
            "boundary_coverage_pct": round(bc, 1),
            "negative_tests": negative_count,
            "boundary_tests": boundary_count,
            "total_shall_refs": total,
            "covered_shall_refs": covered,
            "total_test_cases": len(test_cases),
        }

    # ── Internal helpers ──────────────────────────────────────────────────

    def _build_prompt(self, doc: Any) -> str:
        """Format a spec document into a user prompt for the LLM."""
        requirements_json = json.dumps(
            [r.to_dict() for r in doc.requirements],
            ensure_ascii=False,
            indent=2,
        )
        scenarios_json = json.dumps(
            [s.to_dict() for s in doc.scenarios],
            ensure_ascii=False,
            indent=2,
        )
        shall_count = sum(len(r.shall) for r in doc.requirements)

        return _GENERATE_USER_TEMPLATE.format(
            requirements_json=requirements_json,
            scenarios_json=scenarios_json,
            shall_count=shall_count,
            scenario_count=len(doc.scenarios),
        )

    def _parse_response(self, raw: str) -> list[TestCase]:
        """Parse the LLM JSON response into TestCase objects.

        Handles optional markdown code fences and trailing content.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Find the first and last ```
            start = cleaned.find("\n")
            end = cleaned.rfind("```")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end].strip()

        # Try to parse as JSON
        data = self._try_parse_json(cleaned)
        if data is None:
            # Maybe the response is surrounded by extra commentary — try extracting
            # the first JSON array or object
            data = self._extract_json_array(cleaned)

        if data is None:
            log.warning("Could not parse LLM response as JSON. Raw=%s", raw[:500])
            return []

        cases: list[TestCase] = []
        for item in data:
            try:
                tc = TestCase(
                    id=str(item.get("id", "")),
                    shall_ref=str(item.get("shall_ref", "")),
                    scenario=str(item.get("scenario", "")),
                    given=str(item.get("given", "")),
                    when=str(item.get("when", "")),
                    then=str(item.get("then", "")),
                    priority=str(item.get("priority", "P1")),
                    tags=list(item.get("tags", ["unit"])),
                )
                cases.append(tc)
            except (TypeError, ValueError, KeyError) as e:
                log.warning("Skipping malformed test case item: %s (%s)", item, e)

        return cases

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Any]:
        """Attempt to parse text as JSON, returning None on failure."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_array(text: str) -> Optional[list]:
        """Extract the first JSON array from arbitrary text."""
        # Find the first '[' and matching ']'
        start = text.find("[")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        """Extract the first JSON object from arbitrary text."""
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
        return None
