"""
OSH Pipeline Prompts — Prompt templates for pipeline LLM steps.

Each prompt is a function returning (system_prompt, user_prompt) tuple
given the current session context.
"""

from pathlib import Path
from typing import Optional


def build_test_planning_prompt(
    spec_content: str,
    requirements: list[dict],
    architecture_content: Optional[str] = None,
    development_plan_content: Optional[str] = None,
) -> tuple[str, str]:
    """Build a test-planning prompt that generates a comprehensive test plan.

    The prompt asks the LLM to produce a Markdown document containing:
    - Test strategy (unit / integration / E2E allocation)
    - Test case → requirement traceability table
    - Coverage targets

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)
    req_summary_lines = []
    for r in requirements:
        name = r.get("name", "?")
        shalls = r.get("shall_statements", [])
        for s in shalls:
            req_summary_lines.append(f"  - `{name}` → {s}")
        if not shalls:
            req_summary_lines.append(f"  - `{name}` → (no SHALL statements)")

    system_prompt = (
        "You are a senior test architect and quality engineer. "
        "Given a system specification, architecture analysis, and development plan, "
        "produce a rigorous Test Plan document in Markdown.\n\n"
        "The test plan MUST include:\n\n"
        "## 1. Test Strategy\n"
        "- Define the allocation of testing effort across unit, integration, and E2E levels\n"
        "- Explain the rationale for each level (what is tested there and why)\n"
        "- Describe any test infrastructure requirements (mocks, fixtures, harnesses)\n\n"
        "## 2. Test Case → Requirement Traceability Matrix\n"
        "- A Markdown table with columns: | Requirement ID | SHALL Description | Test Case ID | Test Case Description | Level (Unit/Integration/E2E) | Status |\n"
        "- Every SHALL statement from the specification MUST be mapped to at least one test case\n"
        "- Test cases SHOULD be named TC-RS-XXX-N or TC-SWR-XXX-N following the requirement ID\n\n"
        "## 3. Coverage Targets\n"
        "- Line coverage target\n"
        "- Branch coverage target\n"
        "- Requirement coverage (must be ≥ 100% — every SHALL tested)\n"
        "- Any additional quality gates (e.g., mutation score, static analysis)\n\n"
        "## 4. Test Environment\n"
        "- Required test runners, frameworks, and tools\n"
        "- Test data requirements\n"
        "- CI integration notes\n\n"
        "Be thorough and specific. Every SHALL must have a corresponding test case.\n"
        "Output clean Markdown — no extra commentary outside the document structure."
    )

    user_prompt_parts = [
        f"# Specification: Project Specification\n\n"
        f"```markdown\n{spec_content[:8000]}\n```\n\n",
        f"## Requirements Summary ({len(requirements)} requirements, {total_shall} SHALL statements)\n",
        "\n".join(req_summary_lines) + "\n\n",
    ]

    if architecture_content:
        user_prompt_parts.append(
            f"## Architecture Analysis\n```markdown\n{architecture_content[:4000]}\n```\n\n"
        )

    if development_plan_content:
        user_prompt_parts.append(
            f"## Development Plan\n```markdown\n{development_plan_content[:4000]}\n```\n\n"
        )

    user_prompt_parts.append(
        "---\n\n"
        f"Produce the complete Test Plan as Markdown. "
        f"Ensure the traceability matrix covers ALL {total_shall} SHALL statements, "
        f"each mapped to at least one test case."
    )

    user_prompt = "".join(user_prompt_parts)
    return system_prompt, user_prompt
