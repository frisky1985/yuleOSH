#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 2.5: 小克 — 架构设计审查。

在 Architecture Design 完成后自动执行，审查：
- 架构是否符合 spec 中的功能需求
- 模块划分是否合理
- 接口定义是否清晰

This wraps the existing `review_architecture()` from yuleosh.review.run
into a Pipeline-compatible step handler.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm
from yuleosh.review.run import review_architecture as _run_arch_review

log = logging.getLogger("pipeline.step_handlers.review_arch")

__all__ = ["step_review_arch"]


@timed_step
def step_review_arch(session: PipelineSession) -> str:
    """Step: 小克 — 架构设计审查。

    Integrates the existing static `review_architecture()` checker with an
    LLM-powered review that validates the architecture design against the
    spec and prior artifacts (spec, PRD).
    """
    try:
        print("  🔍 [小克] 架构设计审查开始...")
        log.info("Running architecture review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Part A: Static checks from existing reviewer ---
        log.info("Running static architecture checks...")

        # Collect changed files via git
        changed_files: list[str] = []
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, timeout=10,
                cwd=str(project_dir),
            )
            changed_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        except Exception as e:
            log.warning(f"Git diff failed (non-fatal): {e}")

        # Run the existing architecture reviewer
        review_result = _run_arch_review(
            task_name=session.name,
            project_dir=str(project_dir),
            changed_files=changed_files,
        )
        log.info(f"Static arch review: {len(review_result.findings)} findings, status={review_result.status}")

        # --- Part B: LLM-powered architecture review against spec ---
        log.info("Running LLM-powered architecture review...")

        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        architecture_content = ""
        if "architecture" in session.artifacts:
            ap = Path(session.artifacts["architecture"])
            if ap.exists():
                architecture_content = ap.read_text()

        if architecture_content:
            try:
                system_prompt, user_prompt = _build_arch_review_prompt(
                    spec_content=spec_content,
                    spec_name=spec_path.name,
                    architecture_content=architecture_content,
                )
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "arch-review", "usage": usage})
                log.info(f"LLM arch review: {usage.get('total_tokens', '?')} tokens")
            except Exception as e:
                log.warning(f"LLM arch review failed (non-fatal): {e}")
                llm_review = "(LLM-powered review unavailable)"
        else:
            llm_review = "(No architecture artifact to review)"

        # --- Build output report ---
        findings_json = [f.to_dict() for f in review_result.findings]
        static_summary = review_result.summary

        finding_breakdown = {
            "critical": sum(1 for f in review_result.findings if f.severity == "critical"),
            "major": sum(1 for f in review_result.findings if f.severity == "major"),
            "minor": sum(1 for f in review_result.findings if f.severity == "minor"),
            "info": sum(1 for f in review_result.findings if f.severity == "info"),
        }

        overall_status = "passed"
        if any(f.severity in ("critical",) for f in review_result.findings):
            overall_status = "failed"
        elif len([f for f in review_result.findings if f.severity == "major"]) > 3:
            overall_status = "retry"

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "architecture-review",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": findings_json,
            "finding_count": len(findings_json),
            "finding_breakdown": finding_breakdown,
            "static_summary": static_summary,
            "llm_review": llm_review,
            "summary": (
                f"Static: {static_summary} | "
                f"LLM: {'analyzed' if llm_review and not llm_review.startswith('(') else 'skipped'}"
            ),
        }

        out_path = session.session_dir / "arch-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write arch review: {e}")
            raise PipelineStepError(f"Cannot write arch review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 架构审查完成 "
              f"({len(findings_json)} findings, status={overall_status})")
        log.info(f"Architecture review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Architecture review step failed: {e}")
        raise PipelineStepError(f"Architecture review step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: build architecture review prompt inline
# ---------------------------------------------------------------------------


def _build_arch_review_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str,
) -> tuple[str, str]:
    """Build prompts for the LLM-powered architecture review.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are a senior software architect conducting a design review.\n"
        "Check the architecture design against the requirement specification.\n"
        "Focus on:\n"
        "1. Does the architecture satisfy all functional requirements in the spec?\n"
        "2. Are non-functional requirements (performance, safety, security) addressed?\n"
        "3. Is the module decomposition reasonable (cohesion, coupling)?\n"
        "4. Are interfaces clearly defined and consistent?\n"
        "5. Are there any architectural risks or missing concerns?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (each with severity: critical/major/minor/info, category, and description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification Content\n"
        f"```\n{spec_content[:8000]}\n```\n\n"
        f"### Architecture Design\n"
        f"```\n{architecture_content[:8000]}\n```\n\n"
        f"Review the architecture against the specification above.\n"
        f"Identify any gaps, risks, or inconsistencies."
    )

    return system_prompt, user_prompt
