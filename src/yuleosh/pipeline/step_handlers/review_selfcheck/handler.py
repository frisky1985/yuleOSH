#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
pipeline/step_handlers/review_selfcheck/handler.py — LLM 输出自查 (H2-2).

背景: `review_selfcheck` 在 TASK_ROUTES 注册 (model=deepseek-v4, risk=L3)
但无实现。LLM 前序步骤输出 (code-review / architecture / development / PRD
等) 在进入后续 gate 前缺乏自动自查，幻觉 finding 直接影响 verdict。

修法 (H2-2):
  - step_review_selfcheck 读取当前最近一份 LLM 输出（优先 session artifact
    顺序：code-review > architecture > development > prd > 任意最新）
  - 用 repo_facts 注入真实仓库事实作为 grounding 锚点
  - 构造自查 prompt：逐条验证声明的 source grounding，标记
    confidence: high / medium / low / unsupported
  - 解析 LLM 自查结论 → 写入 session.selfcheck_result
  - low / unsupported 项降为 warning（不阻断 pipeline）

H2-2c 自查 prompt 关键约束:
  "逐条验证以下声明是否有 source grounding，
   标记 confidence: high/medium/low/unsupported"
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step

log = logging.getLogger("pipeline.step_handlers.review_selfcheck")

# ── Artifact priority for which output to self-check ─────────────────────────
_ARTIFACT_PRIORITY = [
    "code-review",
    "internal-code-review",
    "architecture",
    "development",
    "test-planning",
    "prd",
    "super-analysis",
]

# ── Self-check output schema ──────────────────────────────────────────────────
_SELFCHECK_SCHEMA = """\
Return a JSON object with this structure:
{
  "verdict": "passed" | "warning" | "failed",
  "summary": "<one sentence>",
  "items": [
    {
      "claim": "<exact quoted claim from the text>",
      "confidence": "high" | "medium" | "low" | "unsupported",
      "reason": "<why — cite source file/line/function if grounded, or explain gap>"
    }
  ]
}
Rules:
- verdict "passed"  → all items confidence high or medium
- verdict "warning" → at least one item low, none unsupported
- verdict "failed"  → at least one item unsupported
- Do NOT invent file names, line numbers, or requirement IDs not present in
  the Repository Facts section.
- If a claim cannot be verified from the provided context, mark it
  confidence "unsupported", not "low".
"""

# ── Prompt builder (H2-2c) ────────────────────────────────────────────────────

def _build_selfcheck_prompt(
    llm_output: str,
    repo_facts_text: str,
    artifact_key: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the self-check LLM call."""
    system_prompt = (
        "你是 yuleOSH 自查 agent（小克）。\n"
        "你的唯一任务是逐条验证另一个 LLM 步骤的输出声明是否有"
        "可溯源的 source grounding。\n"
        "禁止：编造行号、文件名、函数名、需求 ID。\n"
        "禁止：把「未提供上下文」解读为「不存在」。\n"
        "若某声明既无法从 Repository Facts 验证也无法从输出本身溯源，"
        "标记 unsupported — 不要给予宽松评级。\n\n"
        + _SELFCHECK_SCHEMA
    )

    user_prompt = (
        f"## 被审查步骤: {artifact_key}\n\n"
        f"### Repository Facts (machine-collected grounding baseline)\n\n"
        f"{repo_facts_text or '(no repo facts available)'}\n\n"
        f"### LLM 输出 (待自查)\n\n"
        f"{llm_output[:8000]}"  # cap to avoid blowing context
        + ("\n…[truncated]" if len(llm_output) > 8000 else "")
        + "\n\n---\n"
        "请逐条抽取上方输出中的具体声明（file:line 引用、函数名引用、"
        "需求 ID 引用、架构断言、测试覆盖率声明等），验证每条的 grounding，"
        "并返回符合 schema 的 JSON。"
    )
    return system_prompt, user_prompt


# ── Result parser ─────────────────────────────────────────────────────────────

def _parse_selfcheck_result(raw: str) -> dict[str, Any]:
    """Extract JSON from the LLM self-check response."""
    # Try direct parse
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        pass
    # Extract first JSON object block
    m = re.search(r"\{[\s\S]+\}", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    # Fallback: return a minimal error result
    return {
        "verdict": "warning",
        "summary": "selfcheck output could not be parsed as JSON",
        "items": [],
        "_parse_error": raw[:500],
    }


def _downgrade_unsupported(result: dict[str, Any]) -> None:
    """H2-2d: annotate low/unsupported items; escalate verdict if needed."""
    items = result.get("items") or []
    low_count = sum(1 for i in items if i.get("confidence") == "low")
    unsupported_count = sum(1 for i in items if i.get("confidence") == "unsupported")

    if unsupported_count > 0:
        result["verdict"] = "failed"
        result["gate_action"] = (
            f"{unsupported_count} unsupported claim(s) — gate triage required"
        )
    elif low_count > 0:
        if result.get("verdict") not in ("failed",):
            result["verdict"] = "warning"
        result["gate_action"] = (
            f"{low_count} low-confidence claim(s) — downgraded to warning"
        )
    else:
        result.setdefault("verdict", "passed")
        result["gate_action"] = "all claims grounded"


# ── Main step handler ─────────────────────────────────────────────────────────

@timed_step
def step_review_selfcheck(session: PipelineSession) -> str:
    """Self-check pass on the most recent LLM step output (H2-2).

    Reads the highest-priority available artifact, runs a grounding-focused
    self-check via LLM, stores the parsed result on the session, and returns
    the artifact path.  Low/unsupported findings are annotated as warnings
    but never block the pipeline (non-fatal by design).
    """
    try:
        print("  🔎 [小克] 自查 — LLM 输出 source grounding 验证...")

        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [自查] 跳过 — mock 模式")
            return write_mock_skip(
                session, "review-selfcheck",
                "mock mode — selfcheck skipped",
            )

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── 1. Pick the artifact to self-check ────────────────────────────
        artifact_key = ""
        llm_output = ""
        for key in _ARTIFACT_PRIORITY:
            if key in (session.artifacts or {}):
                ap = Path(session.artifacts[key])
                if ap.exists():
                    artifact_key = key
                    llm_output = ap.read_text(encoding="utf-8", errors="replace")
                    break

        if not llm_output:
            log.info("review_selfcheck: no eligible artifact found — skipping")
            result = {
                "verdict": "passed",
                "summary": "no prior LLM artifact to self-check",
                "items": [],
                "skipped": True,
            }
            session.selfcheck_result = result
            return _write_result(session, project_dir, result, artifact_key or "none")

        log.info("review_selfcheck: checking artifact '%s'", artifact_key)

        # ── 2. Collect repo facts for grounding baseline ──────────────────
        from yuleosh.pipeline.repo_facts import collect_repo_facts, format_repo_facts
        try:
            facts = collect_repo_facts(project_dir)
            repo_facts_text = format_repo_facts(facts)
        except Exception as e:
            log.warning("repo_facts collection failed (non-fatal): %s", e)
            repo_facts_text = "(repo facts unavailable)"

        # ── 3. Build + call LLM ───────────────────────────────────────────
        from yuleosh.pipeline.stages import _call_llm

        system_prompt, user_prompt = _build_selfcheck_prompt(
            llm_output, repo_facts_text, artifact_key
        )
        session.pipeline_knowledge_step_key = "review_selfcheck"

        raw = _call_llm(session, system_prompt, user_prompt)
        content = raw if isinstance(raw, str) else raw.get("content", "")

        # ── 4. Parse + annotate ───────────────────────────────────────────
        result = _parse_selfcheck_result(content)
        _downgrade_unsupported(result)
        result["checked_artifact"] = artifact_key
        result["timestamp"] = datetime.now(UTC).isoformat()

        session.selfcheck_result = result

        # ── 5. Log summary ────────────────────────────────────────────────
        verdict = result.get("verdict", "unknown")
        n_items = len(result.get("items") or [])
        gate_action = result.get("gate_action", "")
        print(
            f"  {'✅' if verdict == 'passed' else '⚠️' if verdict == 'warning' else '❌'}"
            f" [自查] verdict={verdict}  items={n_items}  {gate_action}"
        )
        if verdict in ("warning", "failed"):
            log.warning(
                "review_selfcheck: verdict=%s — %s", verdict, gate_action
            )

        return _write_result(session, project_dir, result, artifact_key)

    except PipelineStepError:
        raise
    except Exception as e:
        raise PipelineStepError(f"review_selfcheck failed: {e}") from e


def _write_result(
    session: PipelineSession,
    project_dir: Path,
    result: dict[str, Any],
    artifact_key: str,
) -> str:
    """Write the selfcheck result JSON and register the artifact."""
    out_dir = project_dir / ".yuleosh" / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "selfcheck-result.json"
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    session.artifacts["review-selfcheck"] = str(out_path)
    log.info(
        "review_selfcheck result written to %s (checked: %s)", out_path, artifact_key
    )
    return str(out_path)
