#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Review / final-report step handlers.

Exports:
  step_hermes_review  — AI-powered code review
  step_final_report   — AI-powered final report generation
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _try_parse_hermes_json
from yuleosh.pipeline.prompts import (
    build_code_review_prompt,
    build_final_report_prompt,
)

log = logging.getLogger("pipeline.step_handlers.review")

__all__ = ["step_hermes_review", "step_final_report"]


@timed_step
def step_hermes_review(session: PipelineSession) -> str:
    """Step 8: Hermes — AI-powered code review.

    Reads spec + all artifacts (architecture, test report, development plan, etc.),
    sends to LLM, and produces a real code review with findings.
    """
    try:
        print("  🔮 [Hermes] Running AI-powered code review...")
        log.info("Running AI-powered code review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Read spec ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Collect all available artifacts ---
        artifact_contents = {}
        for key in ["architecture", "development", "self-test", "prd", "super-analysis", "review-result"]:
            if key in session.artifacts:
                ap = Path(session.artifacts[key])
                if ap.exists():
                    artifact_contents[key] = ap.read_text()

        # --- Scan actual source files ---
        source_files = []
        src_dir = project_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith(".py"):
                        fpath = Path(root) / f
                        rel = fpath.relative_to(project_dir)
                        content = fpath.read_text() if fpath.exists() and fpath.stat().st_size < 20000 else ""
                        source_files.append({"path": str(rel), "lines": len(content.splitlines()), "content": content[:3000]})

        # --- Build LLM prompt ---
        system_prompt, user_prompt = build_code_review_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            session_name=session.name,
            artifact_contents=artifact_contents,
            source_files=source_files,
            timestamp=datetime.now().isoformat(),
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during code review: {e}")
            raise PipelineStepError(
                f"Code review LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        raw = result["content"].strip()
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "code-review", "usage": usage})

        # Parse with robust fallback (handles markdown fences, leading text, etc.)
        review = _try_parse_hermes_json(raw, session.name)

        # Ensure required fields
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "Hermes")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")

        out_path = session.session_dir / "code-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write code review: {e}")
            raise PipelineStepError(f"Cannot write code review: {e}")
        print(f"  ✅ [Hermes] AI code review completed ({len(review['findings'])} findings, status={review['status']})")
        log.info(f"AI code review: {len(review['findings'])} findings, status={review['status']}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Code review step failed: {e}")
        raise PipelineStepError(f"Code review step failed: {e}")


@timed_step
def step_final_report(session: PipelineSession) -> str:
    """Step 9: 小明 — AI-powered final report generation.

    Uses LLM to summarize the entire pipeline run with executive summary,
    key findings, artifact inventory, and next steps.
    Falls back to template if LLM is unavailable.
    """
    try:
        print("  📋 [小明] Generating AI-powered final report...")
        log.info("Generating final report")

        out_path = session.session_dir / "final-report.md"

        # Read artifact summaries (first 100 chars of each artifact)
        artifact_summaries: dict[str, str] = {}
        for key, path in session.artifacts.items():
            try:
                content = Path(path).read_text()[:200]
                first_line = content.split("\n", 1)[0].strip("# ").strip()
                artifact_summaries[key] = first_line or "(binary/empty)"
            except Exception:
                artifact_summaries[key] = "(cannot read)"

        system_prompt, user_prompt = build_final_report_prompt(
            session_name=session.name,
            session_status=session.status,
            spec_path=session.spec_path,
            steps=session.steps,
            errors=session.errors,
            artifact_paths=session.artifacts,
            artifact_summaries=artifact_summaries,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
            llm_report = result["content"]
            usage = result.get("usage", {})
            log.info(
                "LLM returned %d tokens for final report (prompt=%s, completion=%s)",
                usage.get("total_tokens", "?"),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
            )
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "final-report", "usage": usage})

            full_output = (
                f"# Final Report: {session.name}\n\n"
                f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
                f"> Tokens: {usage.get('total_tokens', '?')} "
                f"(prompt {usage.get('prompt_tokens', '?')} + "
                f"completion {usage.get('completion_tokens', '?')})\n\n"
                f"{llm_report}"
            )
            try:
                out_path.write_text(full_output)
            except OSError as e:
                log.error(f"Cannot write final report: {e}")
                raise PipelineStepError(f"Cannot write final report: {e}")
        except (RuntimeError, PipelineStepError) as llm_err:
            # Fallback to template-based report if LLM fails
            log.warning(f"LLM call for final report failed, using template fallback: {llm_err}")
            lines = [
                f"# Final Report: {session.name}",
                f"",
                f"**Status**: {session.status}",
                f"**Spec**: {session.spec_path}",
                f"**Created**: {session.created_at}",
                f"**Completed**: {session.updated_at}",
                f"",
                f"> ⚠\ufe0f AI-powered summary unavailable \u2014 LLM call failed",
                f"",
                f"## Pipeline Steps",
                f"",
            ]
            for step in session.steps:
                status_icon = {"completed": "\u2705", "running": "\U0001f504", "pending": "\u23f3", "failed": "\u274c"}
                icon = status_icon.get(step["status"], "\u2753")
                lines.append(
                    f"{icon} **Step {step['step']}** [{step['agent']}] "
                    f"{step['name']}: {step['status']}"
                )
            if session.errors:
                lines.extend(["", "## Errors", ""])
                for e in session.errors:
                    lines.append(f"- \u274c {e}")
            lines.extend(["", "## Artifacts", ""])
            for key, path in session.artifacts.items():
                lines.append(f"- **{key}**: {path}")
            try:
                out_path.write_text("\n".join(lines))
            except OSError as e:
                log.error(f"Cannot write final report: {e}")
                raise PipelineStepError(f"Cannot write final report: {e}")

        print(f"  ✅ Final report at {out_path}")
        log.info(f"Final report generated at {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Final report step failed: {e}")
        raise PipelineStepError(f"Final report step failed: {e}")
