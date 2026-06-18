#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 5.5: 小克 — Development Plan 审查。

在 Development Plan 生成后、Code Implementation 之前自动执行，审查：
- 计划是否覆盖了架构中的所有模块
- 任务分解粒度是否合理（每个任务是否可独立完成和测试）
- 是否有明确的交付标准和验收条件
- 时间/资源估算是否合理
- 依赖关系是否被正确处理

Exports:
  step_review_devplan — LLM-powered Development Plan quality review
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_devplan")

__all__ = ["step_review_devplan"]


# ------------------------------------------------------------------
# Static checks for Development Plan completeness
# ------------------------------------------------------------------


def _extract_tasks(devplan_content: str) -> list[dict]:
    """Extract task entries from the Development Plan.

    Attempts to find structured task descriptions by common markup
    patterns (numbered lists, markdown headings, bullet points with
    task identifiers).

    Returns a list of dicts with:
      - id: task identifier or title
      - description: the task description text
      - est_time: estimated time if present, else ""
    """
    tasks: list[dict] = []
    lines = devplan_content.split("\n")

    # Pattern 1: "### Task X.Y: ..." or "## Task X.Y: ..."
    task_heading_re = re.compile(
        r'^#{2,3}\s+(?:Task|任务|Step)\s*(\S+)\s*[:：](.+)$',
        re.IGNORECASE,
    )
    # Pattern 2: "- [ ] Task X.Y: ..." (checkbox list)
    checkbox_re = re.compile(
        r'^\s*[-*]\s*\[\s*[xX ]?\s*\]\s*(?:Task|任务|Step)?\s*(\S*)\s*[:：]?(.+?)(?:\s*\((\d+[dhms])\))?\s*$',
        re.IGNORECASE,
    )
    # Pattern 3: "X. Task: ..." (numbered list)
    numbered_re = re.compile(
        r'^\s*\d+[.、]\s*(?:Task|任务|Step)?\s*(\S*)\s*[:：]?(.+)$',
        re.IGNORECASE,
    )

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue

        m = task_heading_re.match(stripped)
        if m:
            tasks.append({"id": m.group(1), "description": m.group(2).strip(), "est_time": ""})
            continue

        m = checkbox_re.match(stripped)
        if m:
            tasks.append({
                "id": m.group(1) or f"task-{len(tasks)+1}",
                "description": m.group(2).strip(),
                "est_time": m.group(3) or "",
            })
            continue

        m = numbered_re.match(stripped)
        if m:
            tasks.append({
                "id": m.group(1) or f"task-{len(tasks)+1}",
                "description": m.group(2).strip(),
                "est_time": "",
            })

    return tasks


def _check_acceptance_criteria(devplan_content: str) -> dict:
    """Check for presence of acceptance criteria / delivery standards.

    Returns a dict with:
      - has_criteria: bool
      - indicators: list of matched keywords
      - score: int (0-100)
    """
    indicators = [
        "验收标准", "acceptance criteria", "AC:", "交付标准",
        "definition of done", "DoD", "完成定义",
        "gating", "gate", "checklist", "检查清单",
        "测试用例", "test case", "验证", "verify",
        "PASS", "FAIL", "expected result",
    ]

    found = []
    for ind in indicators:
        if ind.lower() in devplan_content.lower():
            found.append(ind)

    score = min(100, len(found) * 12)
    if "acceptance criteria" in devplan_content.lower() or "验收标准" in devplan_content:
        score = max(score, 60)

    return {
        "has_criteria": bool(found),
        "indicators": found,
        "score": score,
    }


def _check_dependency_modeling(devplan_content: str) -> dict:
    """Check whether task dependencies are modeled.

    Returns a dict with dependency analysis results.
    """
    dep_keywords = [
        "依赖", "dependency", "depends on", "blocked by",
        "前置条件", "prerequisite", "requires",
        "顺序", "sequence", "order", "后",
        "并行", "parallel", "concurrent",
    ]

    found = []
    for kw in dep_keywords:
        if kw.lower() in devplan_content.lower():
            found.append(kw)

    return {
        "has_dependencies": bool(found),
        "matched_keywords": found,
        "score": min(100, len(found) * 15),
    }


def _check_time_estimates(tasks: list[dict], devplan_content: str) -> dict:
    """Check whether tasks have time or effort estimates.

    Returns a dict with estimation assessment.
    """
    est_keywords = [
        "小时", "hour", "天", "day", "周", "week",
        "story point", "SP", "人天", "人月",
        "estimated", "estimate", "预计",
    ]

    found = []
    for kw in est_keywords:
        if kw.lower() in devplan_content.lower():
            found.append(kw)

    tasks_with_estimates = sum(1 for t in tasks if t["est_time"])
    total_tasks = len(tasks)

    return {
        "total_tasks": total_tasks,
        "tasks_with_estimates": tasks_with_estimates,
        "estimate_keywords_found": found,
        "score": min(100, int(tasks_with_estimates / max(total_tasks, 1) * 50) + len(found) * 10),
    }


def _check_module_coverage(
    devplan_content: str,
    architecture_content: str,
) -> list[dict]:
    """Cross-reference architecture modules against Development Plan tasks.

    Extracts module names from the architecture and checks each one
    against the devplan content.  Returns a list of coverage findings.
    """
    findings: list[dict] = []

    # Extract module/component names from architecture
    module_re = re.compile(
        r'^#{2,3}\s+(?:模块|Module|Component|子系统)\s*[:：]?\s*(.+)$',
        re.IGNORECASE | re.MULTILINE,
    )
    arch_sections = module_re.findall(architecture_content)
    if not arch_sections:
        # Fallback: extract any heading as a potential module
        arch_sections = re.findall(r'^##\s+(.+)$', architecture_content, re.MULTILINE)

    for section in arch_sections:
        section_name = section.strip()
        key_terms = [w for w in re.split(r'[\s,;:()/\\-]+', section_name) if len(w) > 3]
        if not key_terms:
            continue
        covered = sum(1 for kw in key_terms if kw.lower() in devplan_content.lower())
        ratio = covered / len(key_terms) if key_terms else 0
        findings.append({
            "module": section_name,
            "covered": ratio >= 0.4,
            "match_ratio": round(ratio, 2),
            "matched_terms": [kw for kw in key_terms if kw.lower() in devplan_content.lower()],
        })

    return findings


def _assess_granularity(tasks: list[dict]) -> dict:
    """Assess whether task granularity is appropriate.

    Rules of thumb:
      - Very few tasks (< 3) → too coarse, consider splitting
      - Very many tasks (> 20 for a typical module) → too fine
      - Each task should be independently completable and testable
      - Check for generic task descriptions that are too vague

    Returns a dict with granularity assessment.
    """
    total = len(tasks)
    vague_keywords = ["研究", "调查", "research", "investigate", "待定", "TBD", "todo", "待确认"]
    vague_tasks = 0
    for t in tasks:
        desc = t.get("description", "").lower()
        if any(kw.lower() in desc for kw in vague_keywords):
            vague_tasks += 1

    assessment = "ok"
    issues = []

    if total < 3:
        assessment = "too_coarse"
        issues.append(f"Only {total} tasks identified — consider splitting into smaller, independently testable units")
    elif total > 20:
        assessment = "too_fine"
        issues.append(f"{total} tasks may be overly granular — consider grouping related items")

    if vague_tasks > max(1, total // 4):
        issues.append(f"{vague_tasks}/{total} tasks contain vague or undefined descriptions")

    return {
        "total_tasks": total,
        "vague_tasks": vague_tasks,
        "assessment": assessment,
        "issues": issues,
    }


# ------------------------------------------------------------------
# LLM-powered development plan review prompt builder
# ------------------------------------------------------------------


def _build_devplan_review_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str,
    devplan_content: str,
) -> tuple[str, str]:
    """Build system + user prompts for the LLM-powered devplan review.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are an experienced technical project manager conducting a development plan review.\n"
        "Evaluate the Development Plan against the specification and architecture design.\n"
        "Focus on:\n"
        "1. **Coverage**: Does the plan cover every module/component in the architecture?\n"
        "2. **Task granularity**: Is each task independently completable and testable?\n"
        "3. **Acceptance criteria**: Does each task have clear definition of done?\n"
        "4. **Dependency management**: Are task dependencies correctly identified?\n"
        "5. **Effort estimation**: Are time/resource estimates reasonable?\n"
        "6. **Risk identification**: Are there any risks or gaps in the plan?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (each with: severity=critical/major/minor/info, "
        "category=coverage/granularity/criteria/dependency/estimation/risk, "
        "description, and recommendation)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification Content\n"
        f"```\n{spec_content[:6000]}\n```\n\n"
        f"### Architecture Design\n"
        f"```\n{architecture_content[:6000]}\n```\n\n"
        f"### Development Plan\n"
        f"```\n{devplan_content[:8000]}\n```\n\n"
        f"Review this Development Plan for completeness, granularity, "
        f"acceptance criteria, dependency modeling, and estimation quality."
    )

    return system_prompt, user_prompt


# ------------------------------------------------------------------
# Main step handler
# ------------------------------------------------------------------


@timed_step
def step_review_devplan(session: PipelineSession) -> str:
    """Step 5.5: 小克 — Development Plan 审查。

    Reviews the Development Plan for:
    - Full coverage of architecture modules
    - Appropriate task granularity
    - Presence of acceptance criteria / definition of done
    - Dependency modeling
    - Effort estimation quality

    The step is non-blocking: findings are advisory and do not halt
    the pipeline.  Critical gaps are recorded for downstream awareness.
    """
    try:
        print("  🔍 [小克] Development Plan 审查开始...")
        log.info("Running Development Plan review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Read spec ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else ""

        if not spec_content:
            log.warning("Spec file not found or empty: %s", session.spec_path)
            raise PipelineStepError(f"Spec file not found: {session.spec_path}")

        # --- Read architecture artifact ---
        architecture_content = ""
        if "architecture" in session.artifacts:
            ap = Path(session.artifacts["architecture"])
            if ap.exists():
                architecture_content = ap.read_text()

        # --- Read development plan artifact ---
        devplan_content = ""
        if "development-plan" in session.artifacts:
            dp = Path(session.artifacts["development-plan"])
            if dp.exists():
                devplan_content = dp.read_text()
        # Also check for "development" key (backward-compatible naming)
        if not devplan_content and "development" in session.artifacts:
            dp = Path(session.artifacts["development"])
            if dp.exists():
                devplan_content = dp.read_text()

        if not devplan_content:
            log.warning("Development plan artifact not found; skipping review")
            raise PipelineStepError(
                "Development plan artifact not found in session artifacts. "
                "Ensure a development-plan (or development) step ran before this review."
            )

        # --- Static checks ---
        tasks = _extract_tasks(devplan_content)
        acceptance = _check_acceptance_criteria(devplan_content)
        dependencies = _check_dependency_modeling(devplan_content)
        estimates = _check_time_estimates(tasks, devplan_content)
        granularity = _assess_granularity(tasks)

        module_coverage = []
        if architecture_content:
            module_coverage = _check_module_coverage(devplan_content, architecture_content)

        covered_modules = sum(1 for m in module_coverage if m["covered"])
        total_modules = len(module_coverage)

        log.info(
            "Devplan static checks: %d tasks, %d/%d modules covered, "
            "acceptance=%d, dependencies=%d, estimates=%d, granularity=%s",
            len(tasks),
            covered_modules, total_modules,
            acceptance["score"],
            dependencies["score"],
            estimates["score"],
            granularity["assessment"],
        )

        # --- LLM-powered review ---
        log.info("Running LLM-powered development plan review...")

        llm_review = ""
        try:
            system_prompt, user_prompt = _build_devplan_review_prompt(
                spec_content=spec_content,
                spec_name=spec_path.name,
                architecture_content=architecture_content,
                devplan_content=devplan_content,
            )
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
            llm_review = result["content"]
            usage = result.get("usage", {})
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "devplan-review", "usage": usage})
            log.info("LLM devplan review: %s tokens", usage.get("total_tokens", "?"))
        except Exception as e:
            log.warning("LLM devplan review failed (non-fatal): %s", e)
            llm_review = "(LLM-powered review unavailable)"

        # --- Assemble findings ---
        findings: list[dict] = []

        # Module coverage findings
        for mc in module_coverage:
            if not mc["covered"]:
                findings.append({
                    "severity": "major",
                    "category": "coverage",
                    "description": f"Architecture module '{mc['module']}' "
                                   f"is not covered in the Development Plan",
                    "recommendation": f"Add tasks for module '{mc['module']}' "
                                      f"with implementation and testing steps",
                })

        # Granularity findings
        for issue in granularity["issues"]:
            findings.append({
                "severity": "minor" if granularity["assessment"] != "too_coarse" else "major",
                "category": "granularity",
                "description": issue,
                "recommendation": "Review task decomposition and split or group tasks as needed",
            })

        # Acceptance criteria findings
        if acceptance["score"] < 40:
            findings.append({
                "severity": "major",
                "category": "criteria",
                "description": "Acceptance criteria or definition of done "
                               "not clearly stated for tasks",
                "recommendation": "Add explicit acceptance criteria (验收标准) "
                                  "or definition of done to each task",
            })

        # Dependency findings
        if dependencies["score"] < 40:
            findings.append({
                "severity": "minor",
                "category": "dependency",
                "description": "Task dependencies are not clearly modeled",
                "recommendation": "Identify and document dependencies between tasks "
                                  "(e.g., blocked by, requires, parallel)",
            })

        # Estimation findings
        if estimates["score"] < 40 and estimates["total_tasks"] > 2:
            findings.append({
                "severity": "minor",
                "category": "estimation",
                "description": f"Only {estimates['tasks_with_estimates']}/"
                               f"{estimates['total_tasks']} tasks have time estimates",
                "recommendation": "Add time or effort estimates to each task "
                                  "(hours, story points, or person-days)",
            })

        # --- Build report ---
        overall_status = "passed"
        if any(f["severity"] == "critical" for f in findings):
            overall_status = "failed"
        elif len([f for f in findings if f["severity"] == "major"]) > 2:
            overall_status = "retry"

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "development-plan-review",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "findings": findings,
            "finding_count": len(findings),
            "finding_breakdown": {
                "critical": sum(1 for f in findings if f["severity"] == "critical"),
                "major": sum(1 for f in findings if f["severity"] == "major"),
                "minor": sum(1 for f in findings if f["severity"] == "minor"),
                "info": sum(1 for f in findings if f["severity"] == "info"),
            },
            "static_checks": {
                "tasks_found": len(tasks),
                "tasks_sample": tasks[:10],
                "module_coverage": {
                    "total_modules": total_modules,
                    "covered": covered_modules,
                    "coverage_pct": round(covered_modules / max(total_modules, 1) * 100, 1),
                    "details": module_coverage,
                },
                "acceptance_criteria": acceptance,
                "dependency_modeling": dependencies,
                "effort_estimation": estimates,
                "task_granularity": granularity,
            },
            "llm_review": llm_review,
            "summary": (
                f"Static: {covered_modules}/{total_modules} modules covered, "
                f"{len(tasks)} tasks, acceptance_score={acceptance['score']}, "
                f"granularity={granularity['assessment']} | "
                f"LLM: {'analyzed' if llm_review and not llm_review.startswith('(') else 'skipped'}"
            ),
        }

        # --- Write output ---
        out_path = session.session_dir / "devplan-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write devplan review: {e}")
            raise PipelineStepError(f"Cannot write devplan review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] Development Plan 审查完成 "
              f"({len(findings)} findings, status={overall_status})")
        print(f"       Tasks: {len(tasks)} | Modules: {covered_modules}/{total_modules} | "
              f"Acceptance: {acceptance['score']}/100")
        log.info("Devplan review completed: %s", overall_status)
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Development Plan review step failed: {e}")
        raise PipelineStepError(f"Development Plan review step failed: {e}")
