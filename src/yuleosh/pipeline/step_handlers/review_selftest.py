#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 5.5: 小克 — 自测结果审查。

在 Self-Test 完成后自动执行：
- 分析测试结果（通过/失败/跳过）
- 检查测试是否覆盖了 spec 中的 SHALL
- 标注未覆盖的 SHALL
- 输出测试gap报告
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec, _try_parse_hermes_json

log = logging.getLogger("pipeline.step_handlers.review_selftest")

__all__ = ["step_review_selftest"]


@timed_step
def step_review_selftest(session: PipelineSession) -> str:
    """Step: 小克 — 自测结果审查。

    Reads the self-test report, spec SHALL statements, and test plan,
    then produces a gap analysis report.
    """
    try:
        print("  🔍 [小克] 自测结果审查开始...")
        log.info("Running self-test review")

        spec_path = Path(session.spec_path)

        # --- Read self-test report ---
        self_test_content = ""
        if "self-test" in session.artifacts:
            ap = Path(session.artifacts["self-test"])
            if ap.exists():
                self_test_content = ap.read_text()

        if not self_test_content:
            log.warning("No self-test artifact found")
            # Still continue with spec analysis even without test results
            self_test_content = "(No self-test report available)"

        # --- Read spec ---
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Parse spec SHALL statements ---
        shall_statements = _extract_shall_statements(spec_content)
        log.info(f"Found {len(shall_statements)} SHALL statements in spec")

        # --- Read test plan (if available) ---
        test_plan_content = ""
        if "test-planning" in session.artifacts:
            ap = Path(session.artifacts["test-planning"])
            if ap.exists():
                test_plan_content = ap.read_text()

        # --- Run LLM-based gap analysis ---
        system_prompt, user_prompt = _build_selftest_review_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            self_test_content=self_test_content,
            shall_statements=shall_statements,
            test_plan_content=test_plan_content,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during self-test review: {e}")
            raise PipelineStepError(
                f"Self-test review LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        raw = result["content"].strip()
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens for self-test review (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "self-test-review", "usage": usage})

        # Parse structured response
        review = _try_parse_hermes_json(raw, session.name)

        # Ensure required fields
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "小克")
        review.setdefault("step", "self-test-review")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")
        review.setdefault("shall_total", len(shall_statements))
        review.setdefault("shall_covered", 0)
        review.setdefault("shall_uncovered", [])
        review.setdefault("shall_unknown", len(shall_statements))
        review.setdefault("test_gap_areas", [])

        out_path = session.session_dir / "selftest-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write self-test review: {e}")
            raise PipelineStepError(f"Cannot write self-test review: {e}")

        findings_count = len(review.get("findings", []))
        uncovered_count = len(review.get("shall_uncovered", []))
        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(review['status'], '❓')} [小克] 自测审查完成 "
              f"({findings_count} findings, "
              f"{review.get('shall_covered', 0)}/{review.get('shall_total', 0)} SHALLs covered, "
              f"{uncovered_count} uncovered)")
        log.info(f"Self-test review: {findings_count} findings, "
                 f"{review.get('shall_covered', 0)}/{review.get('shall_total', 0)} SHALLs covered")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Self-test review step failed: {e}")
        raise PipelineStepError(f"Self-test review step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: extract SHALL statements from spec markdown
# ---------------------------------------------------------------------------


def _extract_shall_statements(spec_content: str) -> list[dict]:
    """Extract SHALL/MAY/SHOULD statements from spec content with context.

    Returns a list of dicts: {statement, section, line_number}.
    """
    shalls: list[dict] = []
    lines = spec_content.split("\n")
    current_section = "preamble"

    for i, line in enumerate(lines):
        # Track headings as section context
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
        if heading_match:
            current_section = heading_match.group(2).strip()
            continue

        # Match SHALL / SHOULD / MAY keywords (case-insensitive)
        matches = re.finditer(
            r"([^.!?]*?\b(SHALL|SHOULD|MAY)\b[^.!?]*[.!?])",
            line,
            re.IGNORECASE,
        )
        for m in matches:
            statement = m.group(1).strip()
            if statement:
                shalls.append({
                    "statement": statement,
                    "section": current_section,
                    "line": i + 1,
                })

    return shalls


# ---------------------------------------------------------------------------
# Internal: build self-test review prompt
# ---------------------------------------------------------------------------


def _build_selftest_review_prompt(
    spec_content: str,
    spec_name: str,
    self_test_content: str,
    shall_statements: list[dict],
    test_plan_content: str,
) -> tuple[str, str]:
    """Build prompts for the LLM-powered self-test results review.

    Returns (system_prompt, user_prompt).
    """
    # Format SHALL list for the prompt
    shall_lines = []
    for s in shall_statements:
        shall_lines.append(f"- [{s['section']}] L{s['line']}: {s['statement']}")
    shall_str = "\n".join(shall_lines[:40])
    if len(shall_statements) > 40:
        shall_str += f"\n- ... and {len(shall_statements) - 40} more"

    system_prompt = (
        "You are a test reviewer analyzing self-test results against requirements.\n"
        "Your task is to:\n"
        "1. **Analyze test results**: Summarize pass/fail/skip from the test output.\n"
        "2. **SHALL coverage mapping**: For each SHALL/SHOULD/MAY statement in the spec, "
        "determine if it is covered by the test results.\n"
        "3. **Identify gaps**: List SHALL statements that have no corresponding test coverage.\n"
        "4. **Suggest improvements**: Recommend additional tests for uncovered areas.\n\n"
        "Output a structured JSON with:\n"
        "- `status`: \"passed\" if all critical SHALLs covered and tests pass, "
        "\"failed\" if critical gaps exist, \"retry\" for minor gaps\n"
        "- `findings`: array of finding objects (severity, category, message)\n"
        "- `finding_breakdown`: {critical: N, major: N, minor: N, info: N}\n"
        "- `shall_total`: total number of SHALL/SHOULD/MAY statements\n"
        "- `shall_covered`: number covered by tests\n"
        "- `shall_uncovered`: list of uncovered SHALL statement texts\n"
        "- `test_gap_areas`: [\"description of untested area\", ...]\n"
        "- `summary`: \"Short summary paragraph\"\n"
        "Wrap the JSON in ```json ... ```."
    )

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification (excerpt)\n"
        f"```\n{spec_content[:5000]}\n```\n\n"
        f"### SHALL/SHOULD/MAY Statements ({len(shall_statements)} total)\n"
        f"{shall_str}\n\n"
        f"### Self-Test Report\n"
        f"```\n{self_test_content[:5000]}\n```\n\n"
        f"### Test Plan (if available)\n"
        f"```\n{test_plan_content[:3000]}\n```\n\n"
        f"Analyze the test coverage. For each SHALL statement, determine if:\n"
        f"- ✅ Covered by tests\n"
        f"- ❌ Not covered (gap)\n"
        f"- ❓ Unknown / ambiguous\n\n"
        f"Output your analysis as structured JSON."
    )

    return system_prompt, user_prompt
