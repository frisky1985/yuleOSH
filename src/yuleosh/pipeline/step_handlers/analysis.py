#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Analysis step handlers — S.U.P.E.R analysis, PRD generation, internal review.

Exports:
  step_super_analysis — AI-powered S.U.P.E.R startup analysis
  step_hermes_prd     — AI-powered product requirements document generation
  step_internal_review — AI-powered internal review of artifacts
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec
from yuleosh.pipeline.prompts import (
    build_super_analysis_prompt,
    build_prd_prompt,
    build_internal_review_prompt,
)

log = logging.getLogger("pipeline.step_handlers.analysis")

__all__ = ["step_super_analysis", "step_hermes_prd", "step_internal_review"]


# ------------------------------------------------------------------
# PRD section coverage guard (2026-08-13)
# ------------------------------------------------------------------

# Spec section IDs that the PRD must cover: `### SR-001`, `### SW-004`
_SPEC_SECTION_ID_RE = re.compile(r"^#{2,4}\s+([A-Z]{2}-\d+)\b", re.IGNORECASE)
# PRD section heading carrying a spec ID: `### 4.1 硬件抽象层 (SR-001)`
_PRD_COVERED_SECTION_RE = re.compile(r"\(?([A-Z]{2}-\d+)\)?", re.IGNORECASE)


def _check_prd_section_coverage(spec_content: str, prd_content: str) -> list[str]:
    """Return spec section IDs (SR-XXX/SW-XXX) missing from the PRD.

    A section is *covered* when the PRD carries the same section ID anywhere
    (heading or body). Spec sections are gathered from `### SR-XXX:` headings;
    scenario headings (`### Scenario:`) are not requirement sections.
    """
    if not spec_content or not prd_content:
        return []
    spec_sections: list[str] = []
    for line in spec_content.splitlines():
        m = _SPEC_SECTION_ID_RE.match(line.strip())
        if m:
            sid = m.group(1).upper()
            if sid not in spec_sections:
                spec_sections.append(sid)
    if not spec_sections:
        return []

    prd_upper = prd_content.upper()
    missing = [sid for sid in spec_sections if sid not in prd_upper]
    return missing


def _prd_retry_prompt(original_user_prompt: str, missing_sections: list[str]) -> str:
    """Build a retry prompt feeding the missing section list back to the LLM."""
    return (
        original_user_prompt
        + "\n\n"
        + "## ⚠️ Coverage feedback from automated review\n"
        + "Your previous PRD did NOT cover the following spec section(s): "
        + ", ".join(missing_sections)
        + ".\n"
        + "Please regenerate the COMPLETE PRD ensuring every spec section appears. "
        + "Do not truncate the output — emit the full document.\n"
    )


def _prd_truncation_retry_prompt(original_user_prompt: str,
                                 truncations: list[str]) -> str:
    """Build a retry prompt feeding truncation signals back to the LLM."""
    return (
        original_user_prompt
        + "\n\n"
        + "## ✂️ 输出截断警告 (2026-08-16)\n"
        + "你上一版 PRD 被检测到输出截断/不完整，信号如下：\n"
        + "\n".join(f"- {t}" for t in truncations)
        + "\n\n"
        + "请重新输出**完整**的 PRD。若内容过长，优先保留全部 FR 表格行与 "
        + "Acceptance Criteria（可压缩 prose/overview 部分），但不得省略任何 "
        + "spec section、不得让 AC 章节残缺。不要以省略号/未完表格结尾。\n"
    )


def _detect_prd_truncation(prd_content: str, scenario_count: int) -> list[str]:
    """Detect PRD truncation/incompleteness signals (2026-08-16).

    PRD 生成无截断检测曾导致 AC-003 空 stub + 防夹/霍尔丢失验收场景整体缺失
    (claude-review blocker 1)。三重启发式:

    1. 尾部未闭合: 最后一个非空行以 `|` 结尾 (表格行被切断)
    2. AC 数 < 场景数: PRD 的 AC-NNN 数应 >= spec 场景数
       (spec 每个验收场景都应有对应 AC)
    3. 缺收尾章节: PRD 未包含 Out of Scope (prompt 强制要求第 7 节)

    返回截断信号列表; 无信号返回 []。
    """
    signals: list[str] = []
    if not prd_content or not prd_content.strip():
        return ["PRD 输出为空"]

    lines = [ln.rstrip() for ln in prd_content.splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        if last.rstrip().endswith("|"):
            signals.append(
                "文档以未闭合的表格行结尾（最后一行以 `|` 结束）— 输出被截断"
            )
        # 尾部 3 行内出现明显截断特征 (孤立 `|` / 半个标题)
        tail = "\n".join(lines[-3:])
        if re.search(r"\|[ \t]*$", tail, re.M):
            signals.append("末尾存在未闭合表格结构 — 输出不完整")

    ac_count = len(re.findall(r"\bAC-\d+\b", prd_content))
    if scenario_count > 0 and ac_count < scenario_count:
        signals.append(
            f"Acceptance Criteria 数量 ({ac_count}) 少于 spec 验收场景数 "
            f"({scenario_count}) — AC 章节可能被截断/缺失"
        )

    if "Out of Scope" not in prd_content and "out of scope" not in prd_content.lower():
        signals.append("缺少 'Out of Scope' 章节（prompt 要求第 7 节）— 文档可能未完成")

    return signals


@timed_step
def step_super_analysis(session: PipelineSession) -> str:
    """Step 1: 小明 — S.U.P.E.R analysis powered by real LLM."""
    try:
        print("  📊 [小明] Running AI-powered S.U.P.E.R analysis...")
        log.info("Running AI-powered S.U.P.E.R analysis")

        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

        system_prompt, user_prompt = build_super_analysis_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            requirements=requirements,
            scenarios=scenarios,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt)
        except Exception as e:
            log.error(f"LLM call failed during S.U.P.E.R analysis: {e}")
            raise PipelineStepError(
                f"S.U.P.E.R analysis LLM call failed: {e}\n"
                f"Spec: {session.spec_path}\n"
                f"This error is not silently degraded \u2014 the pipeline stops here."
            )

        analysis = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "super-analysis", "usage": usage})

        # Prepend a metadata header
        full_output = (
            f"# S.U.P.E.R Analysis: {Path(session.spec_path).stem}\n\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}  |  Scenarios: {len(scenarios)}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} (prompt {usage.get('prompt_tokens', '?')} + completion {usage.get('completion_tokens', '?')})\n\n"
            f"{analysis}"
        )

        out_path = session.session_dir / "startup-analysis.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write analysis file: {e}")
            raise PipelineStepError(f"Cannot write analysis file: {e}")
        print(f"  ✅ [小明] AI S.U.P.E.R analysis generated at {out_path}")
        log.info(f"AI S.U.P.E.R analysis saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"S.U.P.E.R analysis failed: {e}")
        raise PipelineStepError(f"S.U.P.E.R analysis failed: {e}")


@timed_step
def step_hermes_prd(session: PipelineSession) -> str:
    """Step 2: Hermes — AI-powered PRD generation from spec.

    Reads the spec file, parses requirements and scenarios,
    then uses the LLM to produce a real Product Requirements Document.

    Quality guard (2026-08-13): after each LLM generation the PRD is checked
    for spec-section coverage (SR-XXX / SW-XXX alignment). Missing sections
    trigger a bounded retry (max 2) with the missing list fed back to the LLM.
    If the retries are exhausted, the PRD is still written (best effort) and
    the missing sections are recorded in a sidecar report — the step does NOT
    fabricate template content or silently pass.
    """
    try:
        print("  🔮 [Hermes] Running AI-powered PRD generation...")
        log.info("Running AI-powered PRD generation")

        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

        # Read S.U.P.E.R analysis from artifacts if available
        super_content = ""
        super_key = "super-analysis"
        if super_key in session.artifacts:
            super_path = Path(session.artifacts[super_key])
            if super_path.exists():
                super_content = super_path.read_text()

        # 既有 API 契约 (2026-08-16): PRD 的接口描述必须对齐现有头文件,
        # 否则 codegen 会按 PRD 生成不兼容接口 (评审 blocker 2: FR-004 接口名漂移)。
        existing_headers = ""
        try:
            from yuleosh.codegen.prompts import collect_existing_headers
            existing_headers = collect_existing_headers(
                Path(session.project_dir), max_files=12,
            )
        except Exception as e:  # pragma: no cover - defensive
            log.warning("collect_existing_headers failed (non-fatal): %s", e)

        system_prompt, user_prompt = build_prd_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            requirements=requirements,
            scenarios=scenarios,
            super_analysis_content=super_content,
            existing_headers=existing_headers,
        )

        max_retries = 2
        result: dict | None = None
        missing_sections: list[str] = []
        truncations: list[str] = []
        for attempt in range(max_retries + 1):
            try:
                result = _call_llm(session, system_prompt, user_prompt)
            except Exception as e:
                log.error(f"LLM call failed during PRD generation: {e}")
                raise PipelineStepError(
                    f"PRD generation LLM call failed: {e}\n"
                    f"Spec: {session.spec_path}"
                )

            analysis = result["content"]
            # ── Section coverage check (best effort, only after first pass) ──
            missing_sections = _check_prd_section_coverage(spec_content, analysis)
            # ── Truncation check (2026-08-16): AC 截断/尾部未闭合 → 重试 ──
            truncations = _detect_prd_truncation(analysis, len(scenarios))
            if not missing_sections and not truncations:
                break
            if attempt < max_retries:
                log.warning(
                    "PRD incomplete: %d missing section(s) + %d truncation "
                    "signal(s) — retry %d/%d",
                    len(missing_sections), len(truncations),
                    attempt + 1, max_retries,
                )
                user_prompt = _prd_retry_prompt(user_prompt, missing_sections)
                if truncations:
                    user_prompt = _prd_truncation_retry_prompt(
                        user_prompt, truncations,
                    )

        assert result is not None, "PRD LLM call did not return a result"
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "prd", "usage": usage})

        full_output = (
            f"# PRD: {session.name}\n\n"
            f"> Generated from spec: {session.spec_path}\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}  |  Scenarios: {len(scenarios)}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} (prompt {usage.get('prompt_tokens', '?')} + completion {usage.get('completion_tokens', '?')})\n\n"
            f"{analysis}"
        )

        out_path = session.session_dir / "prd.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write PRD: {e}")
            raise PipelineStepError(f"Cannot write PRD: {e}")

        # ── Sidecar coverage report (never silently pass) ──
        if missing_sections or truncations:
            cov_report = {
                "session": session.name,
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "partial",
                "missing_spec_sections": missing_sections,
                "truncation_signals": truncations,
                "message": (
                    f"PRD written but incomplete: {len(missing_sections)} "
                    f"missing section(s) + {len(truncations)} truncation "
                    "signal(s). Review and extend the PRD before release."
                ),
            }
            try:
                cov_path = session.session_dir / "prd-coverage-gap.json"
                cov_path.write_text(json.dumps(cov_report, indent=2, ensure_ascii=False))
                log.warning("PRD coverage gap report written to %s", cov_path)
            except OSError as e:
                log.warning("Cannot write PRD coverage gap report: %s", e)

        print(f"  ✅ [Hermes] AI-powered PRD generated at {out_path}"
              + (f" (⚠️ missing {len(missing_sections)} section(s): {', '.join(missing_sections)})" if missing_sections else "")
              + (f" (⚠️ {len(truncations)} truncation signal(s))" if truncations else ""))
        log.info(f"AI-powered PRD saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"PRD step failed: {e}")
        raise PipelineStepError(f"PRD step failed: {e}")


@timed_step
def step_internal_review(session: PipelineSession) -> str:
    """Step 3: 小明 — AI-powered internal review.

    Checks artifact existence (hard requirement) then uses LLM to assess
    quality, consistency, and traceability of generated artifacts.
    """
    try:
        print("  🔍 [小明] Running AI-powered internal review...")
        log.info("Running internal review")

        artifacts = session.artifacts

        # Check required artifacts exist (hard requirement)
        required = ["spec-check", "super-analysis", "prd"]
        missing = [r for r in required if r not in artifacts]
        if missing:
            log.error(f"Internal review failed \u2014 missing artifacts: {', '.join(missing)}")
            raise PipelineStepError(
                f"Internal review failed \u2014 missing artifacts: {', '.join(missing)}"
            )

        # Read artifact summaries for LLM analysis
        artifact_summaries: dict[str, str] = {}
        for key, path in artifacts.items():
            try:
                p = Path(path)
                if p.exists():
                    content = p.read_text()[:300]
                    first_line = content.split("\n", 1)[0].strip("# ").strip()
                    artifact_summaries[key] = first_line or "(empty)"
                else:
                    artifact_summaries[key] = "MISSING"
            except Exception:
                artifact_summaries[key] = "(read error)"

        # Read spec for context
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        system_prompt, user_prompt = build_internal_review_prompt(
            session_name=session.name,
            spec_content=spec_content,
            spec_name=spec_path.name,
            artifact_paths=session.artifacts,
            artifact_summaries=artifact_summaries,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
            analysis = result["content"]
            usage = result.get("usage", {})
            log.info(
                "LLM returned %d tokens for internal review (prompt=%s, completion=%s)",
                usage.get("total_tokens", "?"),
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
            )
            session.token_usage_total += usage.get("total_tokens", 0)
            session.token_usage_steps.append({"step": "internal-review", "usage": usage})

            full_output = (
                f"# Internal Review: {session.name}\n\n"
                f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
                f"> Tokens: {usage.get('total_tokens', '?')} "
                f"(prompt {usage.get('prompt_tokens', '?')} + "
                f"completion {usage.get('completion_tokens', '?')})\n\n"
                f"{analysis}"
            )
        except (RuntimeError, PipelineStepError) as llm_err:
            # Fallback to basic report if LLM fails
            log.warning(f"LLM call for internal review failed, using basic template: {llm_err}")
            lines = [
                f"# Internal Review: {session.name}",
                f"",
                f"> ⚠\ufe0f AI-powered analysis unavailable \u2014 LLM call failed",
                f"",
                f"## Artifact Status",
                f"",
            ]
            for key, path in session.artifacts.items():
                p = Path(path)
                if p.exists():
                    lines.append(f"\u2705 **{key}**: `{path}`")
                else:
                    lines.append(f"\u274c **{key}**: MISSING at `{path}`")
            full_output = "\n".join(lines)

        out_path = session.session_dir / "review-result.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write review result: {e}")
            raise PipelineStepError(f"Cannot write review result: {e}")
        print(f"  ✅ [小明] AI internal review generated at {out_path}")
        log.info("Internal review passed")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Internal review failed: {e}")
        raise PipelineStepError(f"Internal review failed: {e}")
