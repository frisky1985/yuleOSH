#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step 4.5: 小克 — 代码实现审查。

在 Code Implementation 完成后、Self-Test 之前自动执行：
- 检查代码是否与架构设计一致
- 检查是否有明显的问题（未处理的错误、死代码等）
- 预判测试盲区
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _try_parse_hermes_json
log = logging.getLogger("pipeline.step_handlers.review_code")

__all__ = ["step_review_code"]


@timed_step
def step_review_code(session: PipelineSession) -> str:
    """Step: 小克 — 代码实现审查。

    Reads the spec, architecture design, and actual source files,
    then runs an LLM-powered review for consistency, issues, and
    test blind spots.
    """
    try:
        print("  🔍 [小克] 代码实现审查开始...")
        log.info("Running code implementation review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        spec_path = Path(session.spec_path)

        # --- Read spec ---
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Read artifacts ---
        artifact_contents = {}
        for key in ["architecture", "development"]:
            if key in session.artifacts:
                ap = Path(session.artifacts[key])
                if ap.exists():
                    artifact_contents[key] = ap.read_text()

        # --- Scan actual source files ---
        source_files_summary = []
        src_dir = project_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith((".py", ".c", ".h", ".go", ".rs", ".js", ".ts")):
                        fpath = Path(root) / f
                        rel = fpath.relative_to(project_dir)
                        try:
                            content = fpath.read_text() if fpath.stat().st_size < 15000 else ""
                            source_files_summary.append({
                                "path": str(rel),
                                "lines": len(content.splitlines()),
                                "content": content[:3000],
                            })
                        except Exception:
                            source_files_summary.append({
                                "path": str(rel),
                                "lines": 0,
                                "content": "(cannot read)",
                            })

        # --- Build and call LLM ---
        system_prompt, user_prompt = _build_code_review_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            architecture_content=artifact_contents.get("architecture", ""),
            dev_plan_content=artifact_contents.get("development", ""),
            source_files=source_files_summary,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during code review: {e}")
            raise PipelineStepError(
                f"Code implementation review LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        raw = result["content"].strip()
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens for code review (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "internal-code-review", "usage": usage})

        # Parse structured response with robust fallback
        review = _try_parse_hermes_json(raw, session.name)

        # Ensure required fields
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "小克")
        review.setdefault("step", "internal-code-review")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")
        review.setdefault("test_blind_spots", [])

        out_path = session.session_dir / "internal-code-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write code review: {e}")
            raise PipelineStepError(f"Cannot write code review: {e}")

        findings_count = len(review.get("findings", []))
        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(review['status'], '❓')} [小克] 代码实现审查完成 "
              f"({findings_count} findings, status={review['status']})")
        log.info(f"Code implementation review: {findings_count} findings, status={review['status']}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Code review step failed: {e}")
        raise PipelineStepError(f"Code review step failed: {e}")


# ---------------------------------------------------------------------------
# Internal: build code review prompt
# ---------------------------------------------------------------------------


def _build_code_review_prompt(
    spec_content: str,
    spec_name: str,
    architecture_content: str,
    dev_plan_content: str,
    source_files: list[dict],
) -> tuple[str, str]:
    """Build prompts for the LLM-powered code implementation review.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are a senior developer conducting a code implementation review.\n"
        "Review the actual source code against the specification and architecture design.\n"
        "Focus on:\n"
        "1. **Architecture consistency**: Does the code follow the architecture design?\n"
        "2. **Error handling**: Are there unhandled exceptions, missing try/except, silent failures?\n"
        "3. **Dead code / unused**: Unused imports, variables, functions, unreachable code.\n"
        "4. **Defensive programming**: Missing input validation, edge cases.\n"
        "5. **Test blind spots**: Which parts are likely untested or hard to test?\n\n"
        "Output a structured JSON with:\n"
        "- `status`: \"passed\", \"failed\", or \"retry\"\n"
        "- `findings`: array of {\"severity\": \"critical\"/\"major\"/\"minor\"/\"info\", "
        "\"category\": \"consistency\"/\"error-handling\"/\"dead-code\"/\"defensive\"/\"test-blindspot\", "
        "\"file\": \"...\", \"line\": N, \"message\": \"...\"}\n"
        "- `finding_breakdown`: {critical: N, major: N, minor: N, info: N}\n"
        "- `test_blind_spots`: [\"description of untested area\", ...]\n"
        "- `summary`: \"Short summary paragraph\"\n"
        "Wrap the JSON in ```json ... ```.\n"
        "If the response cannot be parsed as JSON, it will be treated as unstructured markdown."
    )

    # Format source file summaries
    src_lines = []
    for sf in source_files[:30]:
        src_lines.append(f"- {sf['path']}  ({sf['lines']} lines)")
    src_str = "\n".join(src_lines)

    # Include content of key files for deep analysis
    key_snippets = []
    for sf in source_files[:10]:
        if sf["content"] and sf["content"] != "(cannot read)":
            key_snippets.append(f"### {sf['path']}\n```\n{sf['content']}\n```")
    snippets_str = "\n\n".join(key_snippets)

    user_prompt = (
        f"## Spec: {spec_name}\n\n"
        f"### Specification\n"
        f"```\n{spec_content[:4000]}\n```\n\n"
        f"### Architecture Design\n"
        f"```\n{architecture_content[:4000]}\n```\n\n"
        f"### Development Plan\n"
        f"```\n{dev_plan_content[:3000]}\n```\n\n"
        f"### Source Files ({len(source_files)} total)\n"
        f"{src_str}\n\n"
        f"### Key File Contents\n"
        f"{snippets_str[:5000]}\n\n"
        f"Review the implementation. Identify:\n"
        f"- Code that deviates from architecture\n"
        f"- Unhandled errors, missing validation\n"
        f"- Dead code or unused artifacts\n"
        f"- Test blind spots\n"
        f"Output your review as structured JSON."
    )

    return system_prompt, user_prompt
