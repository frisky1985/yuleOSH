#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5, 第八轮专项): 小克 — 看门狗审查 (embedded-realtime 组)。

检查嵌入式看门狗风险域（通用 code-review 易漏）:
- 超时配置（窗口/溢出时间与任务周期匹配）
- 喂狗路径（所有主循环/任务路径是否覆盖；喂狗位置是否正确）
- 安全状态（超时后进入的安全状态/恢复路径）
- 错误恢复（故障记录、重试策略、防反复复位）

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

log = logging.getLogger("pipeline.step_handlers.review_watchdog")

__all__ = ["step_review_watchdog"]

WatchdogFinding = dict  # type alias for readability

# ── Static checks for watchdog safety ──────────────────────────────────

# 看门狗初始化 / 配置 API
_WDT_INIT_PATTERNS = [
    r"\b(?:wdt_init|watchdog_init|iwdg_init|wwdg_init|IWDG_Init|WWDG_Init|HAL_IWDG_Init|HAL_WWDG_Init|WDT_Init)\s*\(",
    r"\b(?:IWDG|WWDG|WDT|watchdog)\w*\s*=\s*(?:enable|disable|on|off)\b",
]
# 喂狗 / kick API
_FEED_PATTERNS = [
    r"\b(?:wdt_feed|watchdog_feed|wdt_kick|iwdg_refresh|wwdg_refresh|HAL_IWDG_Refresh|HAL_WWDG_Refresh|WDT_Feed|Watchdog_Kick|__HAL_IWDG_RELOAD_COUNTER)\s*\(",
    r"\b(?:feed|kick|refresh|reload)\w*\s*\(\s*(?:wdt|watchdog|iwdg|wwdg|IWDG|WWDG|WDT)\w*\s*\)",
]
# 超时 / 窗口配置
_TIMEOUT_PATTERNS = [
    r"\b(?:timeout|Timeout|TIMEOUT|window|prescaler|PRESCALER|reload|RLR)\w*\s*[=:]\s*\d+",
]
# 安全状态 / 恢复
_SAFESTATE_PATTERNS = [
    r"\b(?:safe_state|safeState|fault_handler|error_handler|reset_handler|recover|recovery|NVIC_SystemReset)\b",
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


def _scan_watchdog_safety(project_dir: Path) -> list[WatchdogFinding]:
    """静态扫描看门狗风险域，返回 findings。"""
    findings: list[WatchdogFinding] = []
    sources = _find_c_sources(project_dir)
    if not sources:
        return findings

    has_wdt = False
    has_feed = False
    has_timeout = False
    has_safestate = False
    wdt_files: list[str] = []

    for p in sources:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(project_dir))
        is_wdt_file = bool(re.search(r"wdt|watchdog|iwdg|wwdg", rel, re.IGNORECASE))

        for pat in _WDT_INIT_PATTERNS:
            if re.search(pat, content):
                has_wdt = True
                if is_wdt_file and rel not in wdt_files:
                    wdt_files.append(rel)
                break
        for pat in _FEED_PATTERNS:
            if re.search(pat, content):
                has_feed = True
                break
        if is_wdt_file:
            for pat in _TIMEOUT_PATTERNS:
                if re.search(pat, content):
                    has_timeout = True
                    break
            for pat in _SAFESTATE_PATTERNS:
                if re.search(pat, content):
                    has_safestate = True
                    break

    if not has_wdt and not wdt_files:
        return findings  # 无看门狗相关代码 → 空 findings（上层自动 skip）

    if has_wdt and not has_feed:
        findings.append({
            "severity": "critical",
            "category": "feed_path",
            "file": ", ".join(wdt_files[:3]) or "src/",
            "message": (
                "看门狗已初始化但未检测到喂狗调用 — 系统将周期性复位，"
                "或喂狗路径未覆盖所有运行路径"
            ),
        })

    if has_wdt and not has_timeout:
        findings.append({
            "severity": "major",
            "category": "timeout_config",
            "file": ", ".join(wdt_files[:3]) or "src/",
            "message": (
                "看门狗配置未发现显式超时/窗口参数 — 默认值可能与任务周期"
                "不匹配（过短误复位 / 过长失去保护）"
            ),
        })

    if has_wdt and not has_safestate:
        findings.append({
            "severity": "major",
            "category": "safe_state",
            "file": ", ".join(wdt_files[:3]) or "src/",
            "message": (
                "看门狗超时后未发现安全状态/错误恢复路径（safe_state/"
                "fault_handler/recovery）— 复位后可能直接回到故障状态反复复位"
            ),
        })

    return findings


# ── LLM prompt ─────────────────────────────────────────────────────────


def _build_watchdog_review_prompt(project_dir: Path,
                                  findings: list[WatchdogFinding]) -> tuple[str, str]:
    """Build the watchdog safety review prompt."""
    lines = [
        "你是嵌入式看门狗（WDT）安全专家。审查以下项目的看门狗设计风险：",
        "1. 超时/窗口配置是否与任务周期、最坏执行时间匹配",
        "2. 喂狗路径是否覆盖所有正常运行路径（避免误喂狗掩盖故障）",
        "3. 超时后的安全状态与错误恢复（防反复复位）",
        "4. 看门狗自身失效（被意外禁用/配置丢失）的兜底",
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
            "你是一个严谨的嵌入式看门狗安全评审 agent。只依据证据下结论，" + "不确定的项标注'需人工确认'，不编造缺陷。",
        ),
        "\n".join(lines),
    )


# ── Step handler ─────────────────────────────────────────────────────────


@timed_step
def step_review_watchdog(session: PipelineSession) -> str:
    """Step: 小克 — 看门狗审查 (embedded-realtime 组)。

    静态模式检查 + LLM 深度审查，报告写入 watchdog-review.json。
    任一 critical → failed；major > 3 → retry；否则 passed。
    无看门狗相关文件 → 自动 skip（不报错）。
    """
    try:
        print("  🐕 [小克] 看门狗审查开始...")
        log.info("Running watchdog safety review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real review ──────────────────────────
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [小克] 看门狗审查跳过 — mock 模式")
            return write_mock_skip(
                session, "review-watchdog",
                "mock mode — no real code to review",
            )

        # ── 审查锚定: 本次 run 无代码部署 → honest skip ──
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        _deploy_skip = maybe_skip_code_review(session, "review-watchdog", reviewer="小克")
        if _deploy_skip:
            print("  ⏭️  [小克] 看门狗审查跳过 — 本次 run 无代码部署")
            return _deploy_skip

        # ── Part A: Static checks ──
        static_findings = _scan_watchdog_safety(project_dir)
        if not static_findings and not _find_c_sources(project_dir):
            skip = write_mock_skip(
                session, "review-watchdog",
                "no C/C++ source files — watchdog review not applicable",
            )
            print("  ⏭️  [小克] 看门狗审查跳过 — 无 C/C++ 源码")
            return skip

        # ── Part B: LLM-powered review ──
        llm_review = ""
        if static_findings:
            try:
                system_prompt, user_prompt = _build_watchdog_review_prompt(
                    project_dir, static_findings
                )
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-watchdog", "usage": usage})
            except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
                log.warning(f"LLM watchdog review failed (non-fatal): {e}")
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
            "step": "review-watchdog",
            "spec_ref": "SWE.5",
            "req_ids": ["SWE-MISRA-S1"],
            "timestamp": datetime.now(UTC).isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项看门狗安全问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "watchdog-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write watchdog review: {e}")
            raise PipelineStepError(f"Cannot write watchdog review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 看门狗审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Watchdog review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Watchdog review step failed: {e}")
        raise PipelineStepError(f"Watchdog review step failed: {e}")
