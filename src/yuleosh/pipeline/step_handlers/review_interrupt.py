#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5, 第八轮专项): 小克 — 中断系统审查 (embedded-realtime 组)。

检查嵌入式中断系统风险域（通用 code-review 易漏）:
- 优先级反转 / 优先级分组配置
- 中断嵌套深度与可重入性
- 共享数据竞争（ISR 与主循环/任务共享变量无保护）
- 临界区使用（enter/exit critical 配对、中断屏蔽时长）

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

log = logging.getLogger("pipeline.step_handlers.review_interrupt")

__all__ = ["step_review_interrupt"]

InterruptFinding = dict  # type alias for readability

# ── Static checks for interrupt safety ─────────────────────────────────

# 中断服务函数特征（Cortex-M 命名 / 通用 IRQHandler / ISR 前缀）
_ISR_PATTERNS = [
    r"\b(\w*(?:IRQHandler|_ISR|_isr|Isr|ISR)\w*)\s*\(",
    r"\b(?:HAL_|LL_)?\w+_IRQHandler\s*\(",
]
# 临界区 / 中断屏蔽原语
_CRITICAL_PATTERNS = [
    r"\b(?:enter_critical|__disable_irq|disable_irq|cli|__interrupt_disable|portENTER_CRITICAL|taskENTER_CRITICAL|__asm\s*\(\s*\"cpsid)\b",
    r"\b(?:exit_critical|__enable_irq|enable_irq|sti|__interrupt_enable|portEXIT_CRITICAL|taskEXIT_CRITICAL|__asm\s*\(\s*\"cpsie)\b",
]
# 优先级配置 API
_PRIORITY_PATTERNS = [
    r"\b(?:NVIC_SetPriority|HAL_NVIC_SetPriority|configMAX_SYSCALL_INTERRUPT_PRIORITY|configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY)\b",
    r"\b(?:configMAX_PRIORITIES|osPriority|__NVIC_SetPriority)\b",
]


def _find_c_sources(project_dir: Path) -> list[Path]:
    """Discover C/C++ sources under src/ (skip artifacts/.yuleosh/build)."""
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


def _scan_interrupt_safety(project_dir: Path) -> list[InterruptFinding]:
    """静态扫描中断风险域，返回 findings。"""
    findings: list[InterruptFinding] = []
    sources = _find_c_sources(project_dir)
    if not sources:
        return findings

    has_isr = False
    has_critical = False
    has_priority = False
    shared_volatiles: list[str] = []

    for p in sources:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(project_dir))

        # 1. ISR 存在性
        for pat in _ISR_PATTERNS:
            for m in re.finditer(pat, content):
                has_isr = True
                findings.append({
                    "severity": "info",
                    "category": "isr",
                    "file": rel,
                    "line": content[:m.start()].count("\n") + 1,
                    "message": f"检测到中断服务函数 {m.group(1)} — 需人工确认嵌套/可重入",
                })
                break
            if has_isr:
                break

        # 2. 临界区配对（enter 与 exit 数量）
        enter_count = 0
        exit_count = 0
        for pat in _CRITICAL_PATTERNS[:1]:
            enter_count += len(re.findall(pat, content))
        for pat in _CRITICAL_PATTERNS[1:]:
            exit_count += len(re.findall(pat, content))
        if enter_count or exit_count:
            has_critical = True
            if enter_count != exit_count:
                findings.append({
                    "severity": "major",
                    "category": "critical_section",
                    "file": rel,
                    "message": (
                        f"临界区原语不配对: enter×{enter_count} vs exit×{exit_count} "
                        f"— 中断屏蔽可能泄漏，导致实时性/死锁风险"
                    ),
                })

        # 3. 共享数据竞争: volatile 全局 + ISR 写 + 主循环读（启发式）
        volatile_vars = re.findall(
            r"\bvolatile\s+(?:[A-Za-z_]\w*\s+)+([A-Za-z_]\w*)\s*[;=]",
            content,
        )
        for v in volatile_vars:
            if v not in shared_volatiles:
                shared_volatiles.append(v)

        # 4. 优先级配置存在性
        for pat in _PRIORITY_PATTERNS:
            if re.search(pat, content):
                has_priority = True
                break

    if not has_isr and not has_critical and not has_priority:
        return findings  # 无中断相关代码 → 空 findings（上层自动 skip）

    if has_isr and not has_critical and not has_priority:
        findings.append({
            "severity": "major",
            "category": "shared_data",
            "file": "src/",
            "message": (
                "存在中断服务函数但未检测到临界区/中断屏蔽原语 — "
                "ISR 与主循环共享数据若无保护将产生数据竞争"
            ),
        })

    if shared_volatiles and len(shared_volatiles) > 8:
        findings.append({
            "severity": "minor",
            "category": "shared_data",
            "file": "src/",
            "message": (
                f"检测到 {len(shared_volatiles)} 个 volatile 共享变量 "
                f"({', '.join(shared_volatiles[:5])}...) — 建议逐项确认 ISR 访问受保护"
            ),
        })

    return findings


# ── LLM prompt ─────────────────────────────────────────────────────────


def _build_interrupt_review_prompt(project_dir: Path,
                                   findings: list[InterruptFinding]) -> tuple[str, str]:
    """Build the interrupt-safety review prompt."""
    lines = [
        "你是嵌入式系统中断安全专家。审查以下项目中与中断相关的风险：",
        "1. 优先级反转 / 优先级分组配置不当",
        "2. 中断嵌套过深或 ISR 非可重入",
        "3. ISR 与主循环/任务共享数据竞争（缺少 volatile/临界区/原子操作）",
        "4. 临界区过长或中断屏蔽泄漏",
        "",
        "基于静态扫描结果 + 项目源码给出风险清单。",
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
            "你是一个严谨的嵌入式中断安全评审 agent。只依据证据下结论，" + "不确定的项标注'需人工确认'，不编造缺陷。",
        ),
        "\n".join(lines),
    )


# ── Step handler ─────────────────────────────────────────────────────────


@timed_step
def step_review_interrupt(session: PipelineSession) -> str:
    """Step: 小克 — 中断系统审查 (embedded-realtime 组)。

    静态模式检查 + LLM 深度审查，报告写入 interrupt-review.json。
    任一 critical → failed；major > 3 → retry；否则 passed。
    无中断相关文件 → 自动 skip（不报错）。
    """
    try:
        print("  ⚡ [小克] 中断系统审查开始...")
        log.info("Running interrupt safety review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real review ──────────────────────────
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [小克] 中断审查跳过 — mock 模式")
            return write_mock_skip(
                session, "review-interrupt",
                "mock mode — no real code to review",
            )

        # ── 审查锚定: 本次 run 无代码部署 → honest skip ──
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        _deploy_skip = maybe_skip_code_review(session, "review-interrupt", reviewer="小克")
        if _deploy_skip:
            print("  ⏭️  [小克] 中断审查跳过 — 本次 run 无代码部署")
            return _deploy_skip

        # ── Part A: Static checks ──
        static_findings = _scan_interrupt_safety(project_dir)
        if not _find_c_sources(project_dir):
            # 无 C 源码项目 — 专项无审查对象，honest skip
            skip = write_mock_skip(
                session, "review-interrupt",
                "no C/C++ source files — interrupt review not applicable",
            )
            print("  ⏭️  [小克] 中断审查跳过 — 无 C/C++ 源码")
            return skip

        # ── Part B: LLM-powered review ──
        llm_review = ""
        if static_findings:
            try:
                system_prompt, user_prompt = _build_interrupt_review_prompt(
                    project_dir, static_findings
                )
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-interrupt", "usage": usage})
            except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
                log.warning(f"LLM interrupt review failed (non-fatal): {e}")
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
            "step": "review-interrupt",
            "spec_ref": "SWE.5",
            "req_ids": ["SWE-MISRA-S1"],
            "timestamp": datetime.now(UTC).isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项中断安全问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "interrupt-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write interrupt review: {e}")
            raise PipelineStepError(f"Cannot write interrupt review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 中断系统审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Interrupt review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Interrupt review step failed: {e}")
        raise PipelineStepError(f"Interrupt review step failed: {e}")
