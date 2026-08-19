#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Change Proposal review step handler — spec-cp-review.

Reviews pending (proposed) Change Proposals against the current spec
before implementation proceeds. A proposal that is not clearly aligned
with the spec / requirements / contracts BLOCKS the pipeline (the spec
is not settled — implementing on top of an undecided change would bake
in assumptions).

Reports are written to {session_dir}/spec-cp-review.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step
from yuleosh.pipeline.stages.llm import _call_llm
from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
from yuleosh.spec.changes import list_changes, load_proposal

log = logging.getLogger("pipeline.step_handlers.spec_cp_review")

__all__ = ["step_spec_cp_review", "build_cp_review_prompt"]


def _project_dir(session: PipelineSession) -> Path:
    """Resolve project root (session.project_dir preferred)."""
    pd = getattr(session, "project_dir", None)
    if pd:
        return Path(pd)
    return Path(os.environ.get("OSH_HOME", ".")).resolve()


def build_cp_review_prompt(cp, spec_path: str) -> tuple[str, str]:
    """Build system/user prompts for CP review.

    The reviewer must challenge the proposal's assumptions (grill-me
    spirit, RULES §13): is the Why justified? Does What Changes align
    with the spec? Are Impact / Rollback Plan credible? Verdict must be
    one of approve / reject / needs-work with concrete rationale.
    """
    system_prompt = (
        "You are an independent change-reviewer for an automotive-grade "
        "specification (ASPICE context). Your job is to challenge the "
        "proposal's assumptions — do NOT be sycophantic, do NOT rubber-stamp.\n"
        "For each change proposal, answer:\n"
        "1. Why — is the motivation real and supported by the spec?\n"
        "2. What Changes — does it align with the existing spec / contracts?\n"
        "3. Impact — are affected capabilities identified? Any missing?\n"
        "4. Rollback Plan — is it credible?\n"
        "5. Verdict — one of: approve / reject / needs-work, with rationale.\n"
        "Output STRICT JSON:\n"
        '{"change_id": "...", "verdict": "approve|reject|needs-work", '
        '"rationale": "...", "blockers": ["..."]}'
    )
    user_prompt = (
        f"# Change Proposal: {cp.change_id}\n"
        f"Title: {cp.title}\nStatus: {cp.status}\n"
        f"Affects: {', '.join(cp.affects)}\n\n"
        f"## Proposal body\n{cp.proposal_path.read_text(encoding='utf-8')}\n\n"
        f"## Tasks\n{cp.tasks_path.read_text(encoding='utf-8') if cp.tasks_path.exists() else '(none)'}\n\n"
        f"## Current spec path\n{spec_path}\n"
        f"Review the proposal and return the JSON verdict."
    )
    return system_prompt, user_prompt


@timed_step
def step_spec_cp_review(session: PipelineSession) -> str:
    """Step: 小明 — review pending Change Proposals (OpenSpec evolution)."""
    try:
        print("  📋 [小明] Reviewing pending change proposals...")
        project_dir = _project_dir(session)
        pending = [cp for cp in list_changes(project_dir) if cp.status == "proposed"]

        if not pending:
            log.info("No pending change proposals — skipping")
            return write_mock_skip(
                session,
                "spec-cp-review",
                "No pending change proposals in .osh/changes/",
                report_extra={"reviewer": "小明", "pending_count": 0},
            )

        if is_mock(session):
            return write_mock_skip(
                session,
                "spec-cp-review",
                "Mock mode — change proposal review skipped",
                report_extra={"reviewer": "小明", "pending_count": len(pending)},
            )

        reviews = []
        blocked = []
        spec_target = Path(session.spec_path)
        for cp in pending:
            system_prompt, user_prompt = build_cp_review_prompt(cp, str(spec_target))
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
            content = result.get("content", "")
            # D3 (2026-08-19): 回填 token usage — spec_cp_review 是全 pipeline
            # 唯一漏记 _call_llm usage 的 handler (其余 handler 均已记录,
            # llm_gateway 路径也已记录)。统一后 session.json 的
            # token_usage_steps 覆盖所有 LLM 步骤, prompt 优化有数据依据。
            _usage = result.get("usage") or {}
            session.token_usage_total += _usage.get("total_tokens", 0)
            session.token_usage_steps.append({
                "step": "spec-cp-review",
                "usage": _usage,
            })
            try:
                parsed = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                log.error("CP review LLM output not JSON: %.200s", content)
                raise PipelineStepError(
                    f"CP review LLM output is not valid JSON for {cp.change_id}"
                )
            verdict = parsed.get("verdict", "needs-work")
            reviews.append({
                "change_id": cp.change_id,
                "title": cp.title,
                "verdict": verdict,
                "rationale": parsed.get("rationale", ""),
                "blockers": parsed.get("blockers", []),
            })
            if verdict != "approve":
                blocked.append(cp.change_id)
            log.info("CP %s review verdict: %s", cp.change_id, verdict)

        report = {
            "session": session.name,
            "reviewer": "小明",
            "timestamp": datetime.now().isoformat(),
            "status": "blocked" if blocked else "passed",
            "pending_count": len(pending),
            "reviews": reviews,
            "blocking_change_ids": blocked,
        }
        out_path = session.session_dir / "spec-cp-review.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        if blocked:
            raise PipelineStepError(
                "Change proposal review FAILED — spec not settled for: "
                + ", ".join(blocked)
                + " (resolve the proposals before implementing)"
            )
        print(f"  ✅ [小明] {len(reviews)} change proposal(s) reviewed, all approved")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error("CP review step failed: %s", e)
        raise PipelineStepError(f"Change proposal review failed: {e}")
