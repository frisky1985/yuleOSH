#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — RTOS 配置审查。

检查 RTOS（FreeRTOS / RT-Thread / Zephyr）配置：
- 任务优先级 (configMAX_PRIORITIES)
- 任务堆栈大小 (configMINIMAL_STACK_SIZE)
- 中断优先级分组
- 看门狗 / 钩子函数配置
- 互斥量 / 信号量使用
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_rtos")

__all__ = ["step_review_rtos"]

RtosFinding = dict


# ── Static checks ─────────────────────────────────────────────────────────


def _find_rtos_config_files(project_dir: Path) -> list[Path]:
    """Discover RTOS configuration files in the project tree."""
    patterns = [
        "**/FreeRTOSConfig.h",
        "**/FreeRTOSConfig*.h",
        "**/rtconfig.h",
        "**/rtconfig*.h",
        "**/kconfig*",
        "**/Kconfig*",
        "**/*os_cfg*.h",
    ]
    found: list[Path] = []
    for pat in patterns:
        for p in project_dir.glob(pat):
            if p.is_file():
                found.append(p)
    seen = set()
    unique = []
    for p in found:
        rp = str(p.resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(p)

    # Also search for common defines in header files
    if not unique:
        for p in project_dir.rglob("*.h"):
            try:
                content = p.read_text(errors="replace")
                if any(kw in content for kw in ("configMAX_PRIORITIES", "FreeRTOSConfig",
                                                 "RTOS_CONFIG", "RT_USING_")):
                    rp = str(p.resolve())
                    if rp not in seen:
                        seen.add(rp)
                        unique.append(p)
            except (OSError, UnicodeDecodeError):
                continue

    return unique


def _parse_config_macro(name: str, content: str, default=None) -> str | None:
    """Extract a #define value from RTOS config headers."""
    # Single-line #define
    m = re.search(
        rf"#\s*define\s+{re.escape(name)}\s+(.+?)(?:\s*//|\s*/\*|(?:\r?\n|$))",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    # Undef pattern
    if re.search(rf"#\s*undef\s+{re.escape(name)}", content):
        return "undef"
    return default


def _check_max_priorities(content: str, path: Path) -> list[RtosFinding]:
    """Check configMAX_PRIORITIES."""
    findings = []
    val_str = _parse_config_macro("configMAX_PRIORITIES", content)
    if val_str is None:
        findings.append({
            "severity": "major",
            "category": "priorities",
            "file": str(path),
            "message": "configMAX_PRIORITIES not defined — using FreeRTOS default (may be 32)",
        })
        return findings

    try:
        val = int(val_str, 0)
        if val > 32:
            findings.append({
                "severity": "minor",
                "category": "priorities",
                "file": str(path),
                "message": f"configMAX_PRIORITIES={val} is > 32 — increases scheduler RAM usage; "
                           f"consider reducing if fewer task levels are needed",
            })
        elif val < 4:
            findings.append({
                "severity": "major",
                "category": "priorities",
                "file": str(path),
                "message": f"configMAX_PRIORITIES={val} is very low — may cause priority inversion "
                           f"or limit system responsiveness",
            })
        else:
            findings.append({
                "severity": "info",
                "category": "priorities",
                "file": str(path),
                "message": f"configMAX_PRIORITIES={val}",
            })
    except ValueError:
        findings.append({
            "severity": "info",
            "category": "priorities",
            "file": str(path),
            "message": f"configMAX_PRIORITIES={val_str} — cannot parse numeric value",
        })
    return findings


def _check_minimal_stack(content: str, path: Path) -> list[RtosFinding]:
    """Check configMINIMAL_STACK_SIZE."""
    findings = []
    val_str = _parse_config_macro("configMINIMAL_STACK_SIZE", content)
    if val_str is None:
        findings.append({
            "severity": "minor",
            "category": "stack",
            "file": str(path),
            "message": "configMINIMAL_STACK_SIZE not defined — using FreeRTOS default (may be architecture-dependent)",
        })
        return findings

    try:
        val = int(val_str, 0)
        if val < 60:
            findings.append({
                "severity": "major",
                "category": "stack",
                "file": str(path),
                "message": f"configMINIMAL_STACK_SIZE={val} < 60 words — idle task stack likely too small",
            })
        elif val < 120:
            findings.append({
                "severity": "minor",
                "category": "stack",
                "file": str(path),
                "message": f"configMINIMAL_STACK_SIZE={val} — verify this is sufficient for idle + timer tasks",
            })
        else:
            findings.append({
                "severity": "info",
                "category": "stack",
                "file": str(path),
                "message": f"configMINIMAL_STACK_SIZE={val} words",
            })
    except ValueError:
        findings.append({
            "severity": "info",
            "category": "stack",
            "file": str(path),
            "message": f"configMINIMAL_STACK_SIZE={val_str} — cannot parse numeric value",
        })
    return findings


def _check_interrupt_priority(content: str, path: Path) -> list[RtosFinding]:
    """Check interrupt priority grouping and max syscall priority."""
    findings = []
    # configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY (STM32Cube) or equivalent
    for macro_name in ("configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY",
                       "configMAX_SYSCALL_INTERRUPT_PRIORITY",
                       "configMAX_API_CALL_INTERRUPT_PRIORITY",
                       "configKERNEL_INTERRUPT_PRIORITY"):
        val_str = _parse_config_macro(macro_name, content)
        if val_str is not None:
            try:
                val = int(val_str, 0)
                findings.append({
                    "severity": "info",
                    "category": "interrupt_priority",
                    "file": str(path),
                    "message": f"{macro_name}={val}",
                })
                # For Cortex-M, priority 0 is highest; values > 0 mask lower
                if val == 0:
                    findings.append({
                        "severity": "minor",
                        "category": "interrupt_priority",
                        "file": str(path),
                        "message": f"{macro_name}=0 — all interrupts disabled from kernel API calls; "
                                   f"verify low-priority ISRs can still use FreeRTOS API",
                    })
            except ValueError:
                findings.append({
                    "severity": "info",
                    "category": "interrupt_priority",
                    "file": str(path),
                    "message": f"{macro_name}={val_str}",
                })
            break

    # configLIBRARY_LOWEST_INTERRUPT_PRIORITY or configPRIO_BITS
    for bits_macro in ("configPRIO_BITS", "configLIBRARY_LOWEST_INTERRUPT_PRIORITY"):
        bits_str = _parse_config_macro(bits_macro, content)
        if bits_str is not None:
            findings.append({
                "severity": "info",
                "category": "interrupt_priority",
                "file": str(path),
                "message": f"{bits_macro}={bits_str}",
            })

    # configMAX_SYSCALL_INTERRUPT_PRIORITY (deprecated alias)
    if _parse_config_macro("configMAX_SYSCALL_INTERRUPT_PRIORITY", content) is not None:
        findings.append({
            "severity": "info",
            "category": "interrupt_priority",
            "file": str(path),
            "message": "configMAX_SYSCALL_INTERRUPT_PRIORITY defined (deprecated in newer FreeRTOS versions)",
        })

    # Check for configUSE_PORT_OPTIMISED_TASK_SELECTION
    port_opt = _parse_config_macro("configUSE_PORT_OPTIMISED_TASK_SELECTION", content)
    if port_opt and port_opt not in ("0",):
        findings.append({
            "severity": "info",
            "category": "scheduler",
            "file": str(path),
            "message": "configUSE_PORT_OPTIMISED_TASK_SELECTION enabled — uses hardware instructions if available",
        })

    return findings


def _check_hooks_and_watchdog(content: str, path: Path) -> list[RtosFinding]:
    """Check idle hook, tick hook, and application hook configuration."""
    findings = []

    # Idle hook
    idle_hook = _parse_config_macro("configUSE_IDLE_HOOK", content)
    if idle_hook and idle_hook not in ("0",):
        findings.append({
            "severity": "info",
            "category": "hooks",
            "file": str(path),
            "message": "configUSE_IDLE_HOOK enabled — CPU sleep / watchdog feed expected in idle hook",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "hooks",
            "file": str(path),
            "message": "configUSE_IDLE_HOOK disabled — consider enabling for low-power idle or watchdog feed",
        })

    # Tick hook
    tick_hook = _parse_config_macro("configUSE_TICK_HOOK", content)
    if tick_hook and tick_hook not in ("0",):
        findings.append({
            "severity": "info",
            "category": "hooks",
            "file": str(path),
            "message": "configUSE_TICK_HOOK enabled — tick processing overhead present",
        })

    # Tickless idle (low power)
    tickless = _parse_config_macro("configUSE_TICKLESS_IDLE", content)
    if tickless and tickless not in ("0",):
        findings.append({
            "severity": "info",
            "category": "power",
            "file": str(path),
            "message": f"configUSE_TICKLESS_IDLE={tickless} — low-power idle mode enabled",
        })

    # Check for configTICK_RATE_HZ
    tick_rate = _parse_config_macro("configTICK_RATE_HZ", content)
    if tick_rate:
        try:
            hz = int(tick_rate, 0)
            if hz > 1000:
                findings.append({
                    "severity": "minor",
                    "category": "timing",
                    "file": str(path),
                    "message": f"configTICK_RATE_HZ={hz} Hz — high tick rate increases context switch overhead "
                               f"and power consumption",
                })
            elif hz < 100:
                findings.append({
                    "severity": "minor",
                    "category": "timing",
                    "file": str(path),
                    "message": f"configTICK_RATE_HZ={hz} Hz — low tick rate reduces timer granularity",
                })
        except ValueError:
            pass

    return findings


def _check_config_assert(content: str, path: Path) -> list[RtosFinding]:
    """Check configASSERT definition (critical for debug builds).

    FreeRTOS 10+ recommends defining configASSERT(x) to catch API misuse
    and internal consistency errors during development.
    """
    findings = []

    # configASSERT is defined via #define, not a standard config macro
    # Look for it as a macro or function definition
    assert_found = False

    # Explicit #define configASSERT
    if re.search(r'#\s*define\s+configASSERT', content):
        assert_found = True
        # Check if it's a no-op (empty body) or actual assertion
        assert_body = re.search(
            r'#\s*define\s+configASSERT\s*\((.*?)\)(.*?)(?:(?:\r?\n)|$)',
            content, re.DOTALL)
        if assert_body:
            body = assert_body.group(2).strip()
            if not body or body == '' or body.startswith('(') and body.endswith(')'):
                findings.append({
                    "severity": "minor",
                    "category": "config_assert",
                    "file": str(path),
                    "message": (
                        "configASSERT defined as no-op (empty) — "
                        "assertions will not fire; recommend using "
                        "configASSERT(x) with vAssertCalled() for debug builds"
                    ),
                })
            elif 'vAssertCalled' in body or 'assert' in body.lower():
                findings.append({
                    "severity": "info",
                    "category": "config_assert",
                    "file": str(path),
                    "message": (
                        "configASSERT defined with assertion handler "
                        "(vAssertCalled/assert) — proper debug support"
                    ),
                })
            else:
                findings.append({
                    "severity": "info",
                    "category": "config_assert",
                    "file": str(path),
                    "message": f"configASSERT defined: {body[:80]}...",
                })

    if not assert_found:
        # Check for configUSE_RECORDER or similar debug features
        findings.append({
            "severity": "minor",
            "category": "config_assert",
            "file": str(path),
            "message": (
                "configASSERT not defined — recommend defining configASSERT(x) "
                "for FreeRTOS 10+ to catch API misuse and internal errors "
                "during development; use '#define configASSERT(x) vAssertCalled()' "
                "pattern"
            ),
        })

    return findings


def _check_stack_overflow_hook(content: str, path: Path) -> list[RtosFinding]:
    """Check configCHECK_FOR_STACK_OVERFLOW setting.

    Method 1 (value=1): Check stack pointer on context switch
    Method 2 (value=2): Fill canary pattern at task creation, verify on switch
    """
    findings = []

    val_str = _parse_config_macro("configCHECK_FOR_STACK_OVERFLOW", content)

    if val_str is None:
        findings.append({
            "severity": "minor",
            "category": "stack_overflow",
            "file": str(path),
            "message": (
                "configCHECK_FOR_STACK_OVERFLOW not defined — "
                "task stack overflow detection is disabled; "
                "recommend setting to 1 (method 1: stack pointer check) "
                "or 2 (method 2: canary fill + check) for production safety"
            ),
        })
        return findings

    try:
        val = int(val_str, 0)
        if val == 0:
            findings.append({
                "severity": "minor",
                "category": "stack_overflow",
                "file": str(path),
                "message": (
                    "configCHECK_FOR_STACK_OVERFLOW=0 — stack overflow "
                    "detection disabled; enable for safer production operation"
                ),
            })
        elif val == 1:
            # Also need vApplicationStackOverflowHook defined somewhere
            findings.append({
                "severity": "info",
                "category": "stack_overflow",
                "file": str(path),
                "message": (
                    "configCHECK_FOR_STACK_OVERFLOW=1 (method 1) — "
                    "stack pointer checked on context switch; "
                    "ensure vApplicationStackOverflowHook() is implemented"
                ),
            })
        elif val == 2:
            findings.append({
                "severity": "info",
                "category": "stack_overflow",
                "file": str(path),
                "message": (
                    "configCHECK_FOR_STACK_OVERFLOW=2 (method 2) — "
                    "canary pattern fill + verification on switch; "
                    "more reliable than method 1, small performance cost"
                ),
            })
        else:
            findings.append({
                "severity": "info",
                "category": "stack_overflow",
                "file": str(path),
                "message": f"configCHECK_FOR_STACK_OVERFLOW={val_str}",
            })
    except ValueError:
        findings.append({
            "severity": "info",
            "category": "stack_overflow",
            "file": str(path),
            "message": f"configCHECK_FOR_STACK_OVERFLOW={val_str}",
        })

    return findings


def _check_run_time_stats(content: str, path: Path) -> list[RtosFinding]:
    """Check configGENERATE_RUN_TIME_STATS and related timing stats."""
    findings = []

    val_str = _parse_config_macro("configGENERATE_RUN_TIME_STATS", content)

    if val_str is None or val_str == "0":
        findings.append({
            "severity": "info",
            "category": "run_time_stats",
            "file": str(path),
            "message": (
                "configGENERATE_RUN_TIME_STATS not defined or disabled — "
                "task run-time profiling unavailable; enable for performance "
                "debugging and CPU utilization analysis"
            ),
        })
        return findings

    # Check for the required timer setup macros
    use_trace = _parse_config_macro("configUSE_TRACE_FACILITY", content)
    use_stats = _parse_config_macro("configUSE_STATS_FORMATTING_FUNCTIONS", content)

    details = []
    if use_trace and use_trace != "0":
        details.append("configUSE_TRACE_FACILITY enabled")
    if use_stats and use_stats != "0":
        details.append("configUSE_STATS_FORMATTING_FUNCTIONS enabled")

    findings.append({
        "severity": "info",
        "category": "run_time_stats",
        "file": str(path),
        "message": (
            f"configGENERATE_RUN_TIME_STATS={val_str} — "
            f"task CPU utilization stats enabled; "
            f"{' '.join(details) if details else 'verify portGET_RUN_TIME_COUNTER_VALUE() is defined'}"
        ),
    })

    return findings


def _check_mutex_and_semaphore(content: str, path: Path) -> list[RtosFinding]:
    """Check mutual exclusion and synchronization configuration."""
    findings = []

    # configUSE_MUTEXES
    use_mutex = _parse_config_macro("configUSE_MUTEXES", content)
    if use_mutex and use_mutex not in ("0",):
        findings.append({
            "severity": "info",
            "category": "synchronization",
            "file": str(path),
            "message": "configUSE_MUTEXES enabled — priority inheritance available",
        })

    # configUSE_RECURSIVE_MUTEXES
    use_recursive = _parse_config_macro("configUSE_RECURSIVE_MUTEXES", content)
    if use_recursive and use_recursive not in ("0",):
        findings.append({
            "severity": "info",
            "category": "synchronization",
            "file": str(path),
            "message": "configUSE_RECURSIVE_MUTEXES enabled",
        })

    # configUSE_COUNTING_SEMAPHORES
    use_counting = _parse_config_macro("configUSE_COUNTING_SEMAPHORES", content)
    if use_counting and use_counting not in ("0",):
        findings.append({
            "severity": "info",
            "category": "synchronization",
            "file": str(path),
            "message": "configUSE_COUNTING_SEMAPHORES enabled",
        })

    # configUSE_QUEUE_SETS
    use_queueset = _parse_config_macro("configUSE_QUEUE_SETS", content)
    if use_queueset and use_queueset not in ("0",):
        findings.append({
            "severity": "info",
            "category": "synchronization",
            "file": str(path),
            "message": "configUSE_QUEUE_SETS enabled",
        })

    # Check that at least one sync mechanism is enabled
    sync_enabled = any(
        _parse_config_macro(m, content) not in (None, "0")
        for m in ("configUSE_MUTEXES", "configUSE_SEMAPHORES",
                   "configUSE_COUNTING_SEMAPHORES", "configUSE_QUEUE_SETS")
    )
    if not sync_enabled:
        findings.append({
            "severity": "info",
            "category": "synchronization",
            "file": str(path),
            "message": "No mutex or semaphore features explicitly enabled — "
                       "verify synchronization strategy for multi-task project",
        })

    return findings


def _static_rtos_review(project_dir: Path) -> list[RtosFinding]:
    """Run all static checks on discovered RTOS config files."""
    all_findings: list[RtosFinding] = []
    config_files = _find_rtos_config_files(project_dir)

    if not config_files:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No RTOS configuration file (FreeRTOSConfig.h / rtconfig.h) found in project tree",
        })
        return all_findings

    for f in config_files:
        log.info(f"  Checking RTOS config: {f}")
        try:
            content = f.read_text()
        except OSError as e:
            all_findings.append({
                "severity": "major",
                "category": "io",
                "file": str(f),
                "message": f"Cannot read RTOS config: {e}",
            })
            continue

        all_findings.extend(_check_max_priorities(content, f))
        all_findings.extend(_check_minimal_stack(content, f))
        all_findings.extend(_check_interrupt_priority(content, f))
        all_findings.extend(_check_hooks_and_watchdog(content, f))
        all_findings.extend(_check_mutex_and_semaphore(content, f))
        all_findings.extend(_check_config_assert(content, f))
        all_findings.extend(_check_stack_overflow_hook(content, f))
        all_findings.extend(_check_run_time_stats(content, f))

    return all_findings


def _build_rtos_review_prompt(
    rtos_contents: dict[str, str],
) -> tuple[str, str]:
    """Build prompts for LLM-powered RTOS config review."""
    system_prompt = (
        "You are an embedded firmware expert reviewing RTOS configuration.\n"
        "Analyze the provided RTOS configuration files for:\n"
        "1. Task priority levels — are configMAX_PRIORITIES appropriate?\n"
        "2. Stack sizes — are configMINIMAL_STACK_SIZE and per-task stacks adequate?\n"
        "3. Interrupt handling — is the priority grouping correct for the target MCU?\n"
        "4. Timer / tick settings — is the tick rate and timer resolution suitable?\n"
        "5. Memory allocation — heap scheme, dynamic vs static allocation\n"
        "6. Safety features — stack overflow detection, run-time stats, assertions\n"
        "7. Any RTOS features that could cause issues (queue sets, recursive mutexes, etc.)\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## RTOS Configuration Files\n"]
    for path, content in rtos_contents.items():
        user_lines.append(f"### {path}\n```c\n{content[:6000]}\n```\n")
    user_lines.append(
        "Review the RTOS configuration above. "
        "Identify any settings that could cause issues "
        "for a production embedded firmware target."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_rtos(session: PipelineSession) -> str:
    """Step: 小克 — RTOS 配置审查。

    Discovers and reviews RTOS configuration files in the project tree.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  ⚙️  [小克] RTOS 配置审查开始...")
        log.info("Running RTOS config review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static RTOS config checks...")
        static_findings = _static_rtos_review(project_dir)
        log.info(f"Static RTOS review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered RTOS review...")
        llm_review = ""
        config_files = _find_rtos_config_files(project_dir)
        if config_files:
            rtos_contents = {}
            for p in config_files:
                try:
                    rtos_contents[str(p)] = p.read_text()
                except OSError:
                    pass
            if rtos_contents:
                try:
                    system_prompt, user_prompt = _build_rtos_review_prompt(rtos_contents)
                    llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                    llm_review = llm_result["content"]
                    usage = llm_result.get("usage", {})
                    session.token_usage_total += usage.get("total_tokens", 0)
                    session.token_usage_steps.append({"step": "review-rtos", "usage": usage})
                    log.info(f"LLM RTOS review: {usage.get('total_tokens', '?')} tokens")
                except Exception as e:
                    log.warning(f"LLM RTOS review failed (non-fatal): {e}")
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
            "step": "review-rtos",
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "config_files_found": [str(p) for p in config_files],
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "rtos-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write RTOS review: {e}")
            raise PipelineStepError(f"Cannot write RTOS review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] RTOS 配置审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"RTOS review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"RTOS review step failed: {e}")
        raise PipelineStepError(f"RTOS review step failed: {e}")
