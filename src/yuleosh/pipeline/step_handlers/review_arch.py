#!/usr/bin/env python3

# @req RS-003
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm
from yuleosh.review.run import review_architecture as _run_arch_review
from yuleosh.pipeline.prompts import _inject_spec, _inject_limited, SPEC_INJECT_LIMIT

log = logging.getLogger("pipeline.step_handlers.review_arch")

from yuleosh.pipeline.step_handlers.audit_utils import record_step_verdict

__all__ = ["step_review_arch"]

#: 架构漂移的确定性检查（不依赖 LLM 判断）。
_AUTOSAR_MARKERS = ("Rte_", "SchM", "BSW", "SWC", "arxml")


def _mentions_hal(text: str) -> bool:
    """是否提到 HAL / 硬件抽象层（``\\bhal\\b`` 避免命中 "shall"）。"""
    low = text.lower()
    return bool(re.search(r"\bhal\b", low)) or "硬件抽象" in text or "抽象层" in text


def _deterministic_drift_findings(spec_content: str,
                                  arch_content: str) -> list[dict]:
    """确定性架构漂移检查（AUD-ASPICE-001 NC-05）。

    只做两条保守规则，避免误报：
    1. spec 要求 HAL 抽象 → 架构必须体现 HAL/硬件抽象层；
    2. 架构引入 AUTOSAR 组件但 spec 未要求 → 过度设计/范围漂移。
    """
    if not spec_content or not arch_content:
        return []
    findings: list[dict] = []
    spec_low = spec_content.lower()
    if _mentions_hal(spec_content) and not _mentions_hal(arch_content):
        findings.append({
            "severity": "major",
            "category": "Architecture/Drift",
            "message": "spec 要求硬件抽象层 (HAL)，但架构文档未提及 HAL/硬件抽象",
            "source": "deterministic",
            "rule": "ARCH-DRIFT-HAL",
        })
    markers = [m for m in _AUTOSAR_MARKERS if m.lower() in arch_content.lower()]
    if markers and "autosar" not in spec_low:
        findings.append({
            "severity": "major",
            "category": "Architecture/Scope",
            "message": (
                "架构引入 AUTOSAR 组件 (" + ", ".join(markers)
                + ")，但 spec 未要求 AUTOSAR —— 存在过度设计/范围漂移"),
            "source": "deterministic",
            "rule": "ARCH-DRIFT-AUTOSAR",
        })
    return findings


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
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=6144)
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

        # AUD-ASPICE-001 NC-05: 静态检查看不到源码时，评审员不能据此判 passed。
        # 架构阶段本就没有源码是正常的，所以这里只把「没有任何可审证据」
        # 视为证据缺口；同时补一组确定性漂移检查，避免 LLM 评审在
        # 「架构过度设计 / 偏离 spec」时给 0 findings。
        evidence_gaps: list[str] = []
        if not architecture_content.strip():
            evidence_gaps.append("architecture artifact missing or empty")
        if not spec_content.strip() or "(spec file not found)" in spec_content:
            evidence_gaps.append("spec artifact missing or unreadable")

        drift_findings = _deterministic_drift_findings(spec_content, architecture_content)
        findings_json.extend(drift_findings)

        # AUD-ASPICE-001 NC-02: SSOT 拓扑闭环校验（悬空引用/孤儿需求/缺设计单元）
        try:
            from yuleosh.spec.ssot import build_model, validate_topology

            _model = build_model(spec_content, architecture_content)
            topology_findings = [i.as_finding()
                                 for i in validate_topology(_model)]
        except Exception as e:  # pragma: no cover - 防御
            log.debug("SSOT topology check skipped: %s", e)
            topology_findings = []
        findings_json.extend(topology_findings)

        finding_breakdown = {
            "critical": sum(1 for f in findings_json if f.get("severity") == "critical"),
            "major": sum(1 for f in findings_json if f.get("severity") == "major"),
            "minor": sum(1 for f in findings_json if f.get("severity") == "minor"),
            "info": sum(1 for f in findings_json if f.get("severity") == "info"),
        }

        overall_status = "passed"
        if evidence_gaps:
            # 无证据 ≠ 通过。gate 侧会把 passed=false 判为 failed。
            overall_status = "failed"
        elif any(f.get("severity") == "critical" for f in findings_json):
            overall_status = "failed"
        elif drift_findings or topology_findings or finding_breakdown["major"] > 3:
            # 确定性漂移/拓扑问题必须回灌架构重做（NC-01 返工路由）
            overall_status = "retry"

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "architecture-review",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "passed": overall_status == "passed",
            "evidence_gaps": evidence_gaps,
            "static_findings": findings_json,
            "finding_count": len(findings_json),
            "finding_breakdown": finding_breakdown,
            "static_summary": static_summary,
            "llm_review": llm_review,
            "summary": (
                f"Static: {static_summary} | "
                f"LLM: {'analyzed' if llm_review and not llm_review.startswith('(') else 'skipped'}"
                + (f" | evidence_gaps: {len(evidence_gaps)}" if evidence_gaps else "")
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
        record_step_verdict(session, "arch-review", overall_status, [str(out_path)])
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
        f"```\n{_inject_spec(spec_content)}\n```\n\n"
        f"### Architecture Design\n"
        f"```\n{_inject_limited(architecture_content, SPEC_INJECT_LIMIT, 'architecture')}\n```\n\n"
        f"Review the architecture against the specification above.\n"
        f"Identify any gaps, risks, or inconsistencies."
    )

    return system_prompt, user_prompt
