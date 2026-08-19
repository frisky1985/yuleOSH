#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5, 第八轮专项): 小克 — 时序审查 (embedded-realtime 组)。

检查嵌入式实时时序风险域（通用 code-review 易漏）:
- 任务周期配置（周期与超时/窗口匹配）
- WCET（最坏执行时间）估计与预算
- 中断延迟（临界区/关中断时长对实时性的影响）
- 调度预算（任务优先级/时间片/deadline 满足性）

结构遵循现有 9 个嵌入式专项 handler 模式:
  mock skip → deploy skip → 静态检查 → LLM 审查 → JSON 报告。
无相关文件时自动 skip（不报错）。
"""

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import _call_llm, timed_step

log = logging.getLogger("pipeline.step_handlers.review_timing")

__all__ = ["step_review_timing"]

TimingFinding = dict  # type alias for readability

# ── Static checks for timing safety ────────────────────────────────────

# 任务周期 / 延时 API（RTOS 周期任务）
_PERIOD_PATTERNS = [
    r"\b(?:vTaskDelay|osDelay|xTaskCreate|osThreadNew|task_period|period_ms|TASK_PERIOD|task_interval)\s*\(",
    r"\b(?:PERIOD|period_ms|periodUs|TICK|tick_ms|CYCLE)\w*\s*[=:]\s*\d+",
]
# 阻塞 / 长循环（WCET 风险）
_BLOCK_PATTERNS = [
    r"\b(?:while\s*\(\s*1\s*\)|for\s*\(\s*;\s*;\s*\))",
    r"\b(?:delay_ms|delay_us|HAL_Delay|osDelay|vTaskDelay|busy_wait|spin_lock)\s*\(",
]
# 中断延迟（临界区关中断）
_LATENCY_PATTERNS = [
    r"\b(?:__disable_irq|portENTER_CRITICAL|taskENTER_CRITICAL|cli\s*\()",
]
# 调度 / 优先级
_SCHED_PATTERNS = [
    r"\b(?:osPriority|configMAX_PRIORITIES|priority|PRIORITY|setPriority|vTaskPrioritySet)\b",
    r"\b(?:deadline|Deadline|DEADLINE|wcet|WCET|budget|Budget|budget_ms)\b",
]


def _find_c_sources(project_dir: Path) -> list[Path]:
    """Discover C/C++ sources under src/ (skip build/artifacts dirs)."""
    src_dir = project_dir / "src"
    if not src_dir.exists():
        return []
    found: list[Path] = []
    skip_dirs = {"build", "cmake-build", "cmake-build-debug", "cmake-build-release",
                 "cmake-build-coverage", "artifacts", ".yuleosh", ".osh", "node_modules"}
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for f in sorted(files):
            if f.endswith((".c", ".h", ".cpp", ".hpp")):
                found.append(Path(root) / f)
    return found


def _scan_timing_safety(project_dir: Path) -> list[TimingFinding]:
    """静态扫描时序风险域，返回 findings。"""
    findings: list[TimingFinding] = []
    sources = _find_c_sources(project_dir)
    if not sources:
        return findings

    has_period = False
    has_block = False
    has_latency = False
    # has_sched unused (ruff F841) — kept for readability
    has_budget = False
    timing_files: list[str] = []

    for p in sources:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(project_dir))
        is_timing_file = bool(re.search(r"task|timer|time|sched|rtos|freertos",
                                        rel, re.IGNORECASE))

        for pat in _PERIOD_PATTERNS:
            if re.search(pat, content):
                has_period = True
                if is_timing_file and rel not in timing_files:
                    timing_files.append(rel)
                break
        for pat in _BLOCK_PATTERNS:
            if re.search(pat, content):
                has_block = True
                break
        for pat in _LATENCY_PATTERNS:
            if re.search(pat, content):
                has_latency = True
                break
        for pat in _SCHED_PATTERNS[1:]:
            if re.search(pat, content):
                has_budget = True
                break

    if not has_period and not timing_files:
        return findings  # 无时序相关代码 → 空 findings（上层自动 skip）

    if has_block and not has_period:
        findings.append({
            "severity": "major",
            "category": "wcet",
            "file": ", ".join(timing_files[:3]) or "src/",
            "message": (
                "检测到阻塞循环/忙等但未发现任务周期配置 — 无法验证最坏"
                "执行时间（WCET）是否满足调度预算"
            ),
        })

    if has_latency:
        findings.append({
            "severity": "minor",
            "category": "interrupt_latency",
            "file": ", ".join(timing_files[:3]) or "src/",
            "message": (
                "检测到关中断/临界区原语 — 需人工确认临界区长度不违反"
                "中断延迟预算（实时性契约）"
            ),
        })

    if has_period and not has_budget:
        findings.append({
            "severity": "minor",
            "category": "scheduling",
            "file": ", ".join(timing_files[:3]) or "src/",
            "message": (
                "检测到周期任务但未发现 WCET/deadline/预算标注 — 建议补充"
                "调度预算文档以支撑时序分析"
            ),
        })

    return findings


# ── LLM prompt ─────────────────────────────────────────────────────────


def _build_timing_review_prompt(project_dir: Path,
                                findings: list[TimingFinding]) -> tuple[str, str]:
    """Build the timing safety review prompt."""
    lines = [
        "你是嵌入式实时系统时序专家。审查以下项目的时序风险：",
        "1. 任务周期配置与超时/窗口/采样率匹配",
        "2. WCET（最坏执行时间）估计与调度预算",
        "3. 中断延迟（临界区/关中断时长对实时性的影响）",
        "4. 调度预算（优先级/时间片/deadline 满足性）",
        "",
        "静态扫描发现:",
    ]
    if findings:
        for f in findings[:20]:
            lines.append(
                f"- [{f['severity']}] ({f['category']}) {f['file']}: {f['message']}"
            )
    else:
        lines.append("- (无静态发现)")
    lines.append("")
    lines.append("项目路径: " + str(project_dir))
    lines.append(
        "请输出: ①每个风险点的严重级别与具体位置 ②修复建议 ③确认无问题的领域。"
    )
    return (
        (
            "你是一个严谨的嵌入式实时时序评审 agent。只依据证据下结论，" + "不确定的项标注'需人工确认'，不编造缺陷。",
        ),
        "\n".join(lines),
    )


# ── Step handler ─────────────────────────────────────────────────────────


@timed_step
def step_review_timing(session: PipelineSession) -> str:
    """Step: 小克 — 时序审查 (embedded-realtime 组)。

    静态模式检查 + LLM 深度审查，报告写入 timing-review.json。
    任一 critical → failed；major > 3 → retry；否则 passed。
    无时序相关文件 → 自动 skip（不报错）。
    """
    try:
        print("  ⏱️  [小克] 时序审查开始...")
        log.info("Running timing safety review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real review ──────────────────────────
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [小克] 时序审查跳过 — mock 模式")
            return write_mock_skip(
                session, "review-timing",
                "mock mode — no real code to review",
            )

        # ── 审查锚定: 本次 run 无代码部署 → honest skip ──
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        _deploy_skip = maybe_skip_code_review(session, "review-timing", reviewer="小克")
        if _deploy_skip:
            print("  ⏭️  [小克] 时序审查跳过 — 本次 run 无代码部署")
            return _deploy_skip

        # ── Part A: Static checks ──
        static_findings = _scan_timing_safety(project_dir)
        if not static_findings and not _find_c_sources(project_dir):
            skip = write_mock_skip(
                session, "review-timing",
                "no C/C++ source files — timing review not applicable",
            )
            print("  ⏭️  [小克] 时序审查跳过 — 无 C/C++ 源码")
            return skip

        # ── Part B: LLM-powered review ──
        llm_review = ""
        if static_findings:
            try:
                system_prompt, user_prompt = _build_timing_review_prompt(
                    project_dir, static_findings
                )
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-timing", "usage": usage})
            except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
                log.warning(f"LLM timing review failed (non-fatal): {e}")
                llm_review = "(LLM-powered review unavailable)"

        # ── Build output report ──
        finding_breakdown = {
            "critical": sum(1 for f in static_findings if f["severity"] == "critical"),
            "major": sum(1 for f in static_findings if f["severity"] == "major"),
            "minor": sum(1 for f in static_findings if f["severity"] == "minor"),
            "info": sum(1 for f in static_findings if f["severity"] == "info"),
        }

        overall_status = "passed"
        if any(f["severity"] == "critical" for f in static_findings):
            overall_status = "failed"
        elif finding_breakdown["major"] > 3:
            overall_status = "retry"

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-timing",
            "spec_ref": "SWE.5",
            "req_ids": ["SWE-MISRA-S1"],
            "timestamp": datetime.now(UTC).isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项时序问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "timing-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write timing review: {e}")
            raise PipelineStepError(f"Cannot write timing review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 时序审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Timing review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Timing review step failed: {e}")
        raise PipelineStepError(f"Timing review step failed: {e}")
