# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
OSH Pipeline Prompts — Centralized LLM prompt templates for all 10 pipeline steps.

Each builder returns a (system_prompt, user_prompt) tuple.
The prompt system follows the "Agent Pipeline" naming convention:
  小明 (PM) → Hermes (Product/Review) → Claude (Arch/Dev)

Steps:
  0. Spec Check       (小明 — validation, no LLM)
  1. S.U.P.E.R分析    (小明 — LLM analysis)
  2. PRD生成          (Hermes — LLM generation)
  3. 内部评审          (小明 — artifact check + LLM analysis)
  4. 架构设计          (Claude — LLM architecture design)
  5. 开发实现          (Claude — LLM development planning)
  6. 测试规划          (Claude — LLM test planning)
  7. 自测验证          (Claude — test runner, no LLM)
  8. 代码审查          (Hermes — LLM review)
  9. 最终报告          (小明 — LLM summary)
"""

from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Prompt version management (T1.5: spec-delta 联动)
# ---------------------------------------------------------------------------
# Each prompt builder has a semantic version. When a prompt is modified,
# bump its version and record the change in docs/spec-delta.md.

PROMPT_VERSIONS: dict[str, str] = {
    "super-analysis":     "1.1.0",
    "prd":                "1.1.0",
    "internal-review":    "1.0.0",
    "architecture":       "1.0.0",
    "development":        "1.0.0",
    "test-planning":      "1.0.0",
    "code-review":        "1.0.0",
    "final-report":       "1.0.0",
}

# Spec injection limit (chars). 2026-08-16: raised from hard-coded 12000/8000/
# 6000/5000/4000 — specs grow past 20K chars (window-anti-pinch spec.md is
# 21K+), and the contract sections (§1.5 interface contract, §2.5 behavioral
# guardrail map, §3 acceptance scenarios) live at the END of the spec. Truncating
# the tail silently stripped those contracts from PRD/architecture/test-planning
# prompts → claude-review blockers (run-20260816-172910). Keep this large enough
# for real specs; if a spec exceeds it, prefer raising the limit over silent loss.
SPEC_INJECT_LIMIT = 30000


def _inject_spec(spec_content: str) -> str:
    """Inject spec content with an explicit truncation warning (方案 B, 2026-08-17).

    Silent truncation is a class of bugs (run-20260816-172910/174313): the
    tail contract sections (§1.5 interface / §2.5 guardrails / §3 acceptance)
    got silently stripped from prompts, causing claude-review/codegen failures.
    If a spec ever exceeds SPEC_INJECT_LIMIT, surface it loudly in the prompt
    instead of dropping the tail invisibly — reviewers can then flag it.
    """
    out = _inject_limited(spec_content, SPEC_INJECT_LIMIT, "spec")
    # 保持 SPEC_TRUNCATED 标记兼容 (测试/下游检测依赖该字样)
    if len(spec_content) > SPEC_INJECT_LIMIT:
        out = out.replace("TRUNCATED", "SPEC_TRUNCATED", 1)
    return out


def _inject_limited(content: str, limit: int, what: str) -> str:
    """Inject ``content`` capped at ``limit`` chars with an explicit marker.

    方案 B 推广 (2026-08-17): 评审/生成步骤的 artifact 输入（architecture、
    dev_plan、PRD 等）同样禁止静默截断。超过 limit 时注入头部 + 显式
    TRUNCATED 标记, LLM 看到后能自行判断"评审对象不完整"而不是把缺失
    当作设计缺陷（r19 实证: arch-review 误报"需补全 ADR-005+", 实际文档
    有, 只是被 [:8000] 砍掉）。
    """
    if len(content) <= limit:
        return content
    truncated = content[:limit]
    marker = (
        "\n\n<!-- ⚠️ TRUNCATED: content exceeds limit "
        f"({len(content)} > {limit} chars). "
        f"Tail sections of {what} may be missing. "
        "Raise the injection limit in the step handler and re-run. -->\n"
    )
    return truncated + marker


def get_prompt_versions() -> dict[str, str]:
    """Return a copy of the current prompt version map."""
    return dict(PROMPT_VERSIONS)


def get_prompt_version(step_key: str) -> str:
    """Return the version string for a given step key."""
    return PROMPT_VERSIONS.get(step_key, "0.0.0")


# ---------------------------------------------------------------------------
# Step 1: S.U.P.E.R Analysis — 小明
# ---------------------------------------------------------------------------

def build_super_analysis_prompt(
    spec_content: str,
    spec_name: str,
    requirements: list[dict],
    scenarios: list[str],
) -> tuple[str, str]:
    """Build a S.U.P.E.R. analysis prompt.

    S = Situation (project context)
    U = Understanding (key requirements and intent)
    P = Problem (core objectives)
    E = Execution (how to deliver)
    R = Resources (tools, frameworks, skills needed)
    P = Priority (P0/P1/P2 grouping)
    """
    total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

    system_prompt = (
        "You are a senior product analyst. Perform a S.U.P.E.R. analysis of the given "
        "OpenSpec specification document. Analyze:\n"
        "- **S** (Situation) — project context and stakeholder environment\n"
        "- **U** (Understanding) — key requirements and deep intent analysis\n"
        "- **P** (Problem) — core objectives the product solves\n"
        "- **E** (Execution) — approach to deliver, milestones, roadmap implications\n"
        "- **R** (Resources) — tools, frameworks, skills, and infrastructure needed\n"
        "- **P** (Priority) — P0 (critical)/P1 (important)/P2 (nice-to-have) grouping of requirements\n\n"
        "Output a well-structured Markdown report with clear section headers. "
        "Be specific and reference the actual requirement IDs and SHALL statements from the spec."
    )

    user_prompt = (
        f"# Specification: {spec_name}\n\n"
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n"
        f"## Parsed Metadata\n"
        f"- Requirements found: {len(requirements)}\n"
        f"- Total SHALL statements: {total_shall}\n"
        f"- Scenarios found: {len(scenarios)}\n\n"
        f"Write a complete S.U.P.E.R. analysis as Markdown. "
        f"Use the parsed metadata above as a starting point but enrich it "
        f"with genuine insights derived from the spec content."
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 2: PRD Generation — Hermes
# ---------------------------------------------------------------------------

def build_prd_prompt(
    spec_content: str,
    spec_name: str,
    requirements: list[dict],
    scenarios: list[str],
    super_analysis_content: str = "",
    existing_headers: str = "",
    project_asil: str = "",
) -> tuple[str, str]:
    """Build a Product Requirements Document (PRD) generation prompt."""
    total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

    system_prompt = (
        "You are a senior product manager (Hermes). Given an OpenSpec specification "
        "document and optionally a S.U.P.E.R analysis, generate a comprehensive "
        "Product Requirements Document (PRD) in Markdown.\n\n"
        "The PRD must cover:\n"
        "1. **Product Overview** — summary of the product scope and target users\n"
        "2. **Goals & Success Metrics** — measurable objectives for this release\n"
        "3. **User Stories** — structured as GIVEN/WHEN/THEN scenarios mapped to each requirement\n"
        "4. **Functional Requirements** — mapped from each spec SHALL/SHOULD statement, "
        "with implementation notes and priority (P0/P1/P2)\n"
        "5. **Non-Functional Requirements** — performance, security, compliance\n"
        "6. **Acceptance Criteria** — how we know each requirement is done\n"
        "7. **Out of Scope** — explicitly what this release does NOT cover\n\n"
        "CRITICAL — complete coverage:\n"
        "- The spec is organised into numbered requirement sections (e.g. `### SR-001`, "
        "`### SW-004`). You MUST create one Functional Requirements subsection for EVERY "
        "such section in the spec — none may be omitted, even if short.\n"
        "- In each subsection heading, keep the spec section ID in parentheses, e.g. "
        "`### 4.3 模块化架构 (SR-003)`. This ID is used for automated traceability.\n"
        "- Express every requirement as a table row with an ID (`FR-NNN`), a description, "
        "a priority (P0/P1/P2), and an implementation note.\n"
        "- If you are running low on output budget, prefer terse table rows for remaining "
        "sections over omitting them — every spec section must appear.\n\n"
        "CRITICAL — priority discipline (2026-08-16):\n"
        "- Every spec SHALL statement is a hard contractual requirement: it MUST map to a "
        "P0 or P1 requirement. NEVER mark a SHALL-derived requirement P2 (P2 = "
        "non-contractual nice-to-have). If you believe a SHALL is genuinely optional, "
        "keep it P1 and note the conflict in the implementation note — do not silently "
        "downgrade.\n"
        "- Acceptance Criteria MUST be concrete and testable: reference the spec "
        "Scenario (e.g. `Scenario: 防夹检测与反转`) and give measurable thresholds "
        "where the spec defines them (e.g. 50 ms pinch response, 100 mm reversal "
        "distance, 1 s cool-down, 300 ms Hall-loss). NEVER leave an AC as an empty "
        "stub or a bare restatement of the requirement.\n\n"
    )
    if project_asil:
        system_prompt += (
            "CRITICAL — ASIL discipline (2026-08-17, r21b):\n"
            f"- The project's ASIL level is defined by the platform config: **{project_asil}**.\n"
            "- Do NOT invent or self-declare an ASIL class in the PRD (e.g. do not write "
            "\"ASIL-B/C class\" when the project config/spec only says ASIL_B). If the spec "
            "does not state an ASIL level, describe safety-criticality in functional terms "
            "without assigning an ISO 26262 class.\n"
            "- If you cite an ASIL level, it MUST come from the project config above or the "
            "spec — never from general automotive assumptions.\n\n"
        )
    else:
        # 2026-08-18 r21e: 无 ASIL 时纪律段也必须注入 (r21e PRD 自造
        # 'ASIL_B (平台配置)' 的根因正是 project_asil='' 时整段不注入 → LLM 自由发挥)。
        system_prompt += (
            "CRITICAL — ASIL discipline (2026-08-17, r21b; 2026-08-18 r21e):\n"
            "- The project does NOT declare an ASIL level (no yuleosh.yaml asil "
            "field, no ASIL line in project-context.md / README.md, and the spec "
            "does not grade it).\n"
            "- Do NOT invent or self-declare an ASIL class anywhere in the PRD "
            "(e.g. do not write \"ASIL_B (平台配置)\" or \"ASIL-B/C class\").\n"
            "- Describe safety-criticality in functional terms without assigning "
            "an ISO 26262 class. If a class is genuinely needed downstream, mark "
            "it as \"ASIL level TBD by HARA\" — never invent one.\n\n"
        )
    system_prompt += (
        "Be thorough and reference specific requirement names and scenario details."
    )

    user_prompt = (
        f"# Specification: {spec_name}\n\n"
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n"
        f"## Parsed Metadata\n"
        f"- Requirements found: {len(requirements)}\n"
        f"- Total SHALL/SHOULD statements: {total_shall}\n"
        f"- Scenarios found: {len(scenarios)}\n\n"
    )
    if existing_headers:
        user_prompt += (
            "# 既有 API 契约 (必须对齐, 2026-08-16)\n"
            "以下是项目**现有代码**的头文件。PRD 中任何涉及函数接口的 FR/描述，"
            "**必须使用这些头文件里的真实函数名/类型/宏**，不得自造近义名。"
            "（例如现有 `hal_hall_get_count()` 不得写成 `hal_hall_get_pulse_count()`）"
            "头文件本身是既有实现与测试桩的契约；PRD 的接口描述必须与之一致，"
            "否则 codegen 会按 PRD 生成不兼容代码并破坏既有测试。\n\n"
            + existing_headers
            + "\n\n"
        )
    if super_analysis_content:
        user_prompt += (
            f"## S.U.P.E.R. Analysis (from prior step)\n"
            f"```markdown\n{super_analysis_content[:4000]}\n```\n\n"
        )
    user_prompt += (
        f"Write a comprehensive PRD based on the above specification. "
        f"Map each requirement to concrete user stories and acceptance criteria. "
        f"Assign priority (P0/P1/P2) to each requirement group."
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 4: Architecture Design — Claude
# ---------------------------------------------------------------------------

def build_architecture_prompt(
    spec_content: str,
    spec_name: str,
    session_name: str,
    directories: list[str],
    source_files: list[str],
    tech_stack: list[str],
    source_tree_str: str,
    key_file_snippets: list[str],
) -> tuple[str, str]:
    """Build an architecture design prompt."""
    tech_stack_str = ", ".join(sorted(tech_stack)) if tech_stack else "Python"

    system_prompt = (
        "You are a senior software architect. Analyze the project specification "
        "and source code structure provided. Produce a comprehensive architecture "
        "design document in Markdown covering:\n"
        "1. **Project Overview** — tech stack, module count, file count\n"
        "2. **Directory Structure** — show the tree and explain each module's role\n"
        "3. **Bounded Contexts** — domain boundaries derived from the spec\n"
        "4. **Architecture Decision Records (ADRs)** — at least 3 meaningful ADRs "
        "with context, decision, consequences format\n"
        "5. **Key Design Considerations** — constraints, trade-offs, patterns used\n"
        "Be specific and reference actual file paths and code elements."
    )

    user_prompt = (
        f"# Project: {session_name}\n\n"
        f"## Tech Stack\n{tech_stack_str}\n\n"
        f"## Source Tree ({len(directories)} dirs, {len(source_files)} files)\n"
        f"```\n{source_tree_str}\n```\n\n"
        f"## Specification ({spec_name})\n"
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n"
        f"## Key Source File Snippets\n"
        + "\n".join(key_file_snippets[:10])
        + "\n\nWrite a comprehensive architecture document."
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 5: Development Planning — Claude
# ---------------------------------------------------------------------------

def build_development_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str = "",
    prd_content: str = "",
    super_analysis_content: str = "",
    src_lines: int = 0,
    src_file_count: int = 0,
    test_lines: int = 0,
    test_file_count: int = 0,
    test_func_count: int = 0,
    coverage_summary: str = "",
    repo_facts: str = "",
    git_commits: int = 0,
    git_log: str = "",
) -> tuple[str, str]:
    """Build a development planning prompt."""
    test_ratio = f"{test_lines / src_lines:.1%}" if src_lines > 0 else "N/A"

    system_prompt = (
        "You are a senior software developer and tech lead. "
        "Given a project specification, S.U.P.E.R. analysis, PRD, and architecture document, "
        "produce a detailed development plan in Markdown covering:\n"
        "1. **Development Plan** — what to build, in what order, and why (priority-driven)\n"
        "2. **Task Breakdown** — atomic implementation tasks with estimated effort, "
        "file paths to modify, and acceptance criteria for each\n"
        "3. **Tech Debt Identification** — areas in the existing code that need refactoring, "
        "patterns that don't scale, missing tests, or quality concerns\n"
        "4. **Implementation Order** — recommended sequence of work with dependencies\n"
        "5. **Risk Assessment** — technical risks, unknowns, and mitigation strategies\n"
        "Be specific, reference actual file paths from the project, and provide actionable tasks."
    )

    context_parts = [
        f"# Specification: {spec_name}\n```markdown\n{_inject_spec(spec_content)}\n```"
    ]
    if architecture_content:
        context_parts.append(
            f"# Architecture Analysis\n```markdown\n{architecture_content[:4000]}\n```"
        )
    if prd_content:
        context_parts.append(
            f"# PRD\n```markdown\n{prd_content[:3000]}\n```"
        )
    if super_analysis_content:
        context_parts.append(
            f"# S.U.P.E.R. Analysis\n```markdown\n{super_analysis_content[:3000]}\n```"
        )
    context_parts.append(
        f"# Project Metrics\n"
        f"- Source lines: {src_lines} across {src_file_count} files\n"
        f"- Test lines: {test_lines} across {test_file_count} files\n"
        f"- Test functions: {test_func_count}\n"
        f"- Test-to-source ratio: {test_ratio}\n"
        f"- Coverage (latest report): {coverage_summary or 'no report'}\n"
        f"- Recent git commits: {git_commits}\n"
        f"```\n{git_log}\n```"
    )

    if repo_facts:
        context_parts.append(f"# Repository Facts\n```\n{repo_facts}\n```")

    user_prompt = "\n\n---\n\n".join(context_parts)
    user_prompt += "\n\n---\n\nNow produce the development plan, task breakdown, and tech debt identification as Markdown."
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 6: Test Planning — Claude
# ---------------------------------------------------------------------------

def build_test_planning_prompt(
    spec_content: str,
    requirements: list[dict],
    architecture_content: Optional[str] = None,
    development_plan_content: Optional[str] = None,
    repo_facts: str = "",
) -> tuple[str, str]:
    """Build a test-planning prompt that generates a comprehensive test plan.

    The prompt asks the LLM to produce a Markdown document containing:
    - Test strategy (unit / integration / E2E allocation)
    - Test case → requirement traceability table
    - Coverage targets

    Args:
        repo_facts: machine-collected repository fact snapshot (test files /
            framework / coverage / ASIL) injected so the plan is grounded in
            the real repo (2026-08-18 r21e: plan hallucinated Unity harness
            and non-existent test files).

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
        "- A Markdown table with columns: | Requirement ID | SHALL Description | "
        "Test Case ID | Test Case Description | Level (Unit/Integration/E2E) | Status |\n"
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
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n",
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

    if repo_facts:
        user_prompt_parts.append(
            f"## Repository Facts (machine-collected — 测试基建描述必须以此为准)\n"
            f"```\n{repo_facts}\n```\n\n"
        )

    user_prompt_parts.append(
        "---\n\n"
        f"Produce the complete Test Plan as Markdown. "
        f"Ensure the traceability matrix covers ALL {total_shall} SHALL statements, "
        f"each mapped to at least one test case."
    )

    user_prompt = "".join(user_prompt_parts)
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 8: Code Review — Hermes
# ---------------------------------------------------------------------------

def build_code_review_prompt(
    spec_content: str,
    spec_name: str,
    session_name: str,
    artifact_contents: dict[str, str],
    source_files: list[dict],
    timestamp: str = "",
) -> tuple[str, str]:
    """Build a code review prompt for Hermes.

    Args:
        spec_content: Full spec text.
        spec_name: Spec file name.
        session_name: Pipeline session name.
        artifact_contents: Dict of artifact_key → content for prior pipeline outputs.
        source_files: List of dicts with 'path', 'lines', 'content' keys.
        timestamp: ISO timestamp for the review.

    Returns (system_prompt, user_prompt) tuple.
    """
    system_prompt = (
        "You are an expert code reviewer (Hermes). Review the project's source code "
        "against the specification and all available pipeline artifacts. "
        "Produce a detailed review JSON with findings.\n\n"
        "Respond with ONLY valid JSON (no markdown, no explanation). "
        "The JSON must have this exact structure:\n"
        "{\n"
        '  "session": "<session-name>",\n'
        '  "reviewer": "Hermes",\n'
        '  "timestamp": "<ISO-timestamp>",\n'
        '  "status": "passed|failed|retry",\n'
        '  "findings": [\n'
        "    {\n"
        '      "severity": "critical|major|minor|info",\n'
        '      "category": "architecture|domain|style|security|coverage|spec-compliance",\n'
        '      "file": "<relative-file-path>",\n'
        '      "line": <integer-or-null>,\n'
        '      "message": "<detailed-description>"\n'
        "    }\n"
        "  ],\n"
        '  "finding_breakdown": {\n'
        '    "critical": <int>, "major": <int>, "minor": <int>, "info": <int>\n'
        "  },\n"
        '  "summary": "<overall-review-summary>"\n'
        "}"
    )

    artifact_sections = []
    for key, content in artifact_contents.items():
        artifact_sections.append(f"### {key}\n```\n{content[:3000]}\n```")

    source_sections = []
    for sf in source_files:
        source_sections.append(
            f"### {sf['path']} ({sf['lines']} lines)\n```python\n{sf['content']}\n```"
        )

    if len(source_sections) > 8:
        source_sections = source_sections[:8]
        source_sections.append("*(additional source files truncated)*")

    user_prompt = (
        f"# Specification: {spec_name}\n"
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n"
        f"# Pipeline Artifacts\n"
        + "\n".join(artifact_sections)
        + "\n\n# Source Code\n"
        + "\n".join(source_sections)
        + "\n\n---\n\n"
        f"Review session: {session_name}\n"
        f"Timestamp: {timestamp}\n\n"
        "Produce the JSON review. Check:\n"
        "- Does the code satisfy all spec SHALL/SHOULD statements?\n"
        "- Are there any architecture violations or layering issues?\n"
        "- Code style, security, and test coverage concerns?\n"
        "- Quality of the development plan and architecture design?"
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 9: Final Report — 小明
# ---------------------------------------------------------------------------

def build_final_report_prompt(
    session_name: str,
    session_status: str,
    spec_path: str,
    steps: list[dict],
    errors: list[str],
    artifact_paths: dict[str, str],
    artifact_summaries: dict[str, str],
) -> tuple[str, str]:
    """Build a final report prompt that asks the LLM to summarize the pipeline run.

    Args:
        session_name: Pipeline session name.
        session_status: "completed" or "failed".
        spec_path: Path to the specification file.
        steps: List of step dicts with name, agent, status, etc.
        errors: List of error messages.
        artifact_paths: Dict of artifact_key → file path.
        artifact_summaries: Dict of artifact_key → short content summary.

    Returns (system_prompt, user_prompt) tuple.
    """
    completed = sum(1 for s in steps if s.get("status") == "completed")
    failed = sum(1 for s in steps if s.get("status") == "failed")

    system_prompt = (
        "You are a project manager (小明) generating the final pipeline report. "
        "Given a summary of a completed ASPICE-compliant pipeline run, produce "
        "a concise, well-structured Markdown report covering:\n\n"
        "1. **Executive Summary** — 2-3 sentence overview of the pipeline outcome\n"
        "2. **Pipeline Result** — overall status, steps completed vs total\n"
        "3. **Key Findings** — most important insights from the pipeline run\n"
        "4. **Artifact Inventory** — each artifact with a 1-line description\n"
        "5. **Next Steps** — recommended follow-up actions\n\n"
        "Be concise but thorough. Highlight any risks or issues. "
        "Output clean Markdown only."
    )

    step_list = []
    status_icon = {"completed": "✅", "running": "🔄", "pending": "⏳", "failed": "❌"}
    for s in steps:
        icon = status_icon.get(s.get("status", ""), "❓")
        step_list.append(
            f"  {icon} Step {s.get('step', '?')} [{s.get('agent', '?')}] "
            f"{s.get('name', '?')}: {s.get('status', '?')}"
        )

    artifacts_list = []
    for key, path in artifact_paths.items():
        summary = artifact_summaries.get(key, "(no summary)")
        artifacts_list.append(f"  - **{key}**: `{path}` — {summary}")

    errors_list = []
    for e in errors:
        errors_list.append(f"  - ❌ {e}")

    user_prompt = (
        f"# Pipeline: {session_name}\n\n"
        f"**Status**: {session_status}\n"
        f"**Spec**: {spec_path}\n"
        f"**Steps**: {completed}/{len(steps)} completed, {failed} failed\n\n"
        f"## Steps\n" + "\n".join(step_list) + "\n\n"
        f"## Artifacts\n" + "\n".join(artifacts_list) + "\n"
    )
    if errors_list:
        user_prompt += f"\n## Errors\n" + "\n".join(errors_list) + "\n"
    user_prompt += (
        "\n\nGenerate the final pipeline report in Markdown. "
        "Include an executive summary, key findings, artifact inventory, and next steps."
    )
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Step 3: Internal Review — 小明
# ---------------------------------------------------------------------------

def build_internal_review_prompt(
    session_name: str,
    spec_content: str,
    spec_name: str,
    artifact_paths: dict[str, str],
    artifact_summaries: dict[str, str],
) -> tuple[str, str]:
    """Build an internal review prompt for 小明 to assess artifact quality.

    Args:
        session_name: Pipeline session name.
        spec_content: Full spec text.
        spec_name: Spec file name.
        artifact_paths: Dict of artifact_key → file path.
        artifact_summaries: Dict of artifact_key → short content summary.

    Returns (system_prompt, user_prompt) tuple.
    """
    system_prompt = (
        "You are a quality assurance lead (小明) performing an internal review of "
        "pipeline artifacts. Assess:\n"
        "1. **Completeness** — all required artifacts present?\n"
        "2. **Consistency** — do artifacts align with each other and the spec?\n"
        "3. **Quality** — is each artifact thorough and well-structured?\n"
        "4. **Traceability** — do requirements trace through all artifacts?\n\n"
        "Output a Markdown review report with findings and a PASS/FAIL/WARN verdict "
        "for each artifact. Be specific about issues found."
    )

    artifacts_list = []
    for key, path in artifact_paths.items():
        summary = artifact_summaries.get(key, "(no summary)")
        artifacts_list.append(f"  - **{key}** → `{path}`: {summary}")

    user_prompt = (
        f"# Internal Review: {session_name}\n\n"
        f"## Specification ({spec_name})\n"
        f"```markdown\n{_inject_spec(spec_content)}\n```\n\n"
        f"## Generated Artifacts\n" + "\n".join(artifacts_list) + "\n\n"
        f"Write an internal review report. For each artifact, give a verdict (PASS/FAIL/WARN) "
        f"and provide specific feedback. Include an overall assessment at the top."
    )
    return system_prompt, user_prompt
