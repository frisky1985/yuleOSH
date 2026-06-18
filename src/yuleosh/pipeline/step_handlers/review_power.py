#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step (SWE.5): 小克 — 低功耗/能效审查。

检查项:
- WFI/WFE 指令使用
- 时钟门控配置
- 外设备用/停止/待机模式配置
- 唤醒源配置
- 动态电压频率调节 (DVFS)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm

log = logging.getLogger("pipeline.step_handlers.review_power")

__all__ = ["step_review_power"]

PowerFinding = dict


# ── Discovery ─────────────────────────────────────────────────────────────


def _find_power_relevant_files(project_dir: Path) -> dict[str, list[Path]]:
    """Discover files with power-management-related content."""
    categories: dict[str, list[Path]] = {
        "c_source": [],
        "header": [],
        "config": [],
    }

    for p in project_dir.glob("**/*.c"):
        if p.is_file():
            try:
                content = p.read_text()
                if any(kw in content for kw in [
                    "WFI", "WFE", "sleep", "SLEEP", "STOP", "STANDBY",
                    "PWR_", "HAL_PWR", "RCC_", "HAL_RCC",
                    "DVFS", "PLL", "clock_gate", "CLOCK_GATE",
                    "__HAL_PWR", "__HAL_RCC_",
                    "LPUART", "LPTIM", "low_power", "lowpower",
                    "wakeup", "WAKEUP",
                ]):
                    categories["c_source"].append(p)
            except OSError:
                continue

    for p in project_dir.glob("**/*.h"):
        if p.is_file():
            try:
                content = p.read_text()
                if any(kw in content for kw in [
                    "PWR_", "SLEEP", "STOP", "STANDBY", "WFI", "WFE",
                    "low_power", "lowpower",
                    "WAKEUP", "wakeup",
                ]):
                    categories["header"].append(p)
            except OSError:
                continue

    for pat in ["**/*.cfg", "**/*.conf", "**/*.ioc", "**/*.ux"]:
        for p in project_dir.glob(pat):
            if p.is_file():
                categories["config"].append(p)

    for key in categories:
        seen = set()
        unique = []
        for p in categories[key]:
            rp = str(p.resolve())
            if rp not in seen:
                seen.add(rp)
                unique.append(p)
        categories[key] = unique

    return categories


# ── Static checks: WFI/WFE ────────────────────────────────────────────────


def _check_wfi_wfe_usage(contents: dict[str, str]) -> list[PowerFinding]:
    """Check for WFI/WFE instructions in idle/sleep paths."""
    findings = []

    wfi_count = 0
    wfe_count = 0
    wfi_files = []
    wfe_files = []

    for path, content in contents.items():
        if re.search(r'\bWFI\b', content):
            wfi_count += 1
            wfi_files.append(path)
        if re.search(r'\bWFE\b', content):
            wfe_count += 1
            wfe_files.append(path)

    total = wfi_count + wfe_count

    if total == 0:
        findings.append({
            "severity": "major",
            "category": "wfi_wfe",
            "file": "(multiple)",
            "message": "No WFI or WFE instructions found — processor will run "
                       "in busy-wait loop in idle, consuming maximum power",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "wfi_wfe",
            "file": "(multiple)",
            "message": f"WFI found in {len(wfi_files)} file(s), "
                       f"WFE found in {len(wfe_files)} file(s)",
        })

        for path in wfi_files:
            content = contents.get(path, "")
            if re.search(r'WFI', content):
                in_idle = bool(re.search(
                    r'while\s*\(1\)|for\s*\(;;\)|idle|os_idle|vTaskDelay|__WFE|__WFI',
                    content, re.IGNORECASE))
                if in_idle:
                    findings.append({
                        "severity": "info",
                        "category": "wfi_wfe",
                        "file": path,
                        "message": "WFI used in idle loop — good power-saving practice",
                    })
                else:
                    findings.append({
                        "severity": "info",
                        "category": "wfi_wfe",
                        "file": path,
                        "message": "WFI found — verify it is used in the main idle path, "
                                   "not just in initialization",
                    })

        for path in wfe_files:
            content = contents.get(path, "")
            if re.search(r'WFE', content):
                findings.append({
                    "severity": "info",
                    "category": "wfi_wfe",
                    "file": path,
                    "message": "WFE event wait used — verify SEV/SEVL handshake "
                               "between interrupt source and polling loop",
                })

        hal_pwr_wfi = sum(1 for path in wfi_files if "HAL_PWR" in contents.get(path, ""))
        if hal_pwr_wfi > 0:
            findings.append({
                "severity": "info",
                "category": "wfi_wfe",
                "file": "(multiple)",
                "message": f"Both HAL_PWR and WFI found in {hal_pwr_wfi} file(s) — "
                           f"likely using sleep-on-exit or sleep-now mode correctly",
            })

    return findings


def _check_sleep_on_exit(content: str, path: Path) -> list[PowerFinding]:
    """Check for SLEEPONEXIT configuration (SCB->SCR)."""
    findings = []

    has_sleep_on_exit = bool(re.search(
        r'SLEEPONEXIT|SCB_SCR_SLEEPONEXIT|SCB->SCR.*SLEEP|__HAL_PWR_SLEEPONEXIT',
        content, re.IGNORECASE))

    has_deep_sleep = bool(re.search(
        r'DEEPSLEEP|SCB_SCR_DEEPSLEEP|SCB->SCR.*DEEP|__HAL_PWR_DEEPSLEEP',
        content, re.IGNORECASE))

    if has_sleep_on_exit:
        findings.append({
            "severity": "info",
            "category": "sleep_mode",
            "file": str(path),
            "message": "Sleep-on-Exit configured — processor enters sleep after "
                       "each ISR return; suitable for event-driven systems",
        })

    if has_deep_sleep:
        findings.append({
            "severity": "info",
            "category": "sleep_mode",
            "file": str(path),
            "message": "Deep sleep mode configured — processor enters STOP mode "
                       "on WFI; verify wake-up sources are properly configured",
        })

    return findings


# ── Static checks: Clock gating ───────────────────────────────────────────


def _check_clock_gating(contents: dict[str, str]) -> list[PowerFinding]:
    """Check for clock gating configuration."""
    findings = []

    has_clock_disable = False

    ahb_gates = set()
    for path, content in contents.items():
        for m in re.finditer(r'__HAL_RCC_(\w+)_CLK_ENABLE', content):
            ahb_gates.add(m.group(1))

    if ahb_gates:
        findings.append({
            "severity": "info",
            "category": "clock_gating",
            "file": "(multiple)",
            "message": f"Clock gates enabled: {', '.join(sorted(ahb_gates)[:15])}"
                       f"{'...' if len(ahb_gates) > 15 else ''}",
        })

    for path, content in contents.items():
        if re.search(r'__HAL_RCC_\w+_CLK_DISABLE\b', content):
            has_clock_disable = True
            break

    if has_clock_disable:
        disabled_clocks = set()
        for path, content in contents.items():
            for m in re.finditer(r'__HAL_RCC_(\w+)_CLK_DISABLE', content):
                disabled_clocks.add(m.group(1))
        if disabled_clocks:
            findings.append({
                "severity": "info",
                "category": "clock_gating",
                "file": "(multiple)",
                "message": f"Clock gates disabled: {', '.join(sorted(disabled_clocks)[:10])}"
                           f"{'...' if len(disabled_clocks) > 10 else ''}",
            })
        else:
            findings.append({
                "severity": "info",
                "category": "clock_gating",
                "file": "(multiple)",
                "message": "Clock disable macros found but no specific peripheral "
                           "disable detected",
            })
    else:
        findings.append({
            "severity": "minor",
            "category": "clock_gating",
            "file": "(multiple)",
            "message": "No __HAL_RCC_*_CLK_DISABLE found — unused peripheral clocks "
                       "should be disabled to reduce dynamic power consumption",
        })

    return findings


# ── Static checks: Low-power modes ────────────────────────────────────────


def _check_low_power_modes(contents: dict[str, str]) -> list[PowerFinding]:
    """Check for sleep/stop/standby mode configuration and transitions."""
    findings = []

    sleep_mode = False
    stop_mode = False
    standby_mode = False
    shutdown_mode = False

    for path, content in contents.items():
        if re.search(r'HAL_PWR_EnterSLEEPMode', content):
            sleep_mode = True
        if re.search(r'HAL_PWR_EnterSTOPMode', content):
            stop_mode = True
        if re.search(r'HAL_PWR_EnterSTANDBYMode', content):
            standby_mode = True
        if re.search(r'HAL_PWR_EnterSHUTDOWNMode', content):
            shutdown_mode = True

    modes_used = []
    if sleep_mode:
        modes_used.append("SLEEP (lowest latency, ~mA range)")
    if stop_mode:
        modes_used.append("STOP (higher savings, ~µA range)")
    if standby_mode:
        modes_used.append("STANDBY (highest savings, ~nA range)")
    if shutdown_mode:
        modes_used.append("SHUTDOWN (max savings, VBAT only)")

    if not modes_used:
        findings.append({
            "severity": "major",
            "category": "low_power_mode",
            "file": "(multiple)",
            "message": "No low-power mode entry (SLEEP/STOP/STANDBY) found — "
                       "system always runs in RUN mode at full power",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "low_power_mode",
            "file": "(multiple)",
            "message": f"Low-power modes configured: {', '.join(modes_used)}",
        })

        if standby_mode:
            has_wakeup = any(
                re.search(r'WAKEUP|wakeup|RTC_Alarm|WKUP', content, re.IGNORECASE)
                for content in contents.values()
            )
            if not has_wakeup:
                findings.append({
                    "severity": "critical",
                    "category": "low_power_mode",
                    "file": "(multiple)",
                    "message": "STANDBY mode configured but no wake-up source detected "
                               "— system may never exit standby",
                })

    return findings


def _check_power_regulator(content: str, path: Path) -> list[PowerFinding]:
    """Check voltage regulator scaling configuration."""
    findings = []

    reg_scales = []
    for scale_name in [
        "PWR_REGULATOR_VOLTAGE_SCALE1",
        "PWR_REGULATOR_VOLTAGE_SCALE2",
        "PWR_REGULATOR_VOLTAGE_SCALE3",
        "PWR_REGULATOR_VOLTAGE_SCALE4",
        "PWR_REGULATOR_VOLTAGE_SCALE0",
    ]:
        if scale_name in content:
            reg_scales.append(scale_name)

    if reg_scales:
        findings.append({
            "severity": "info",
            "category": "regulator",
            "file": str(path),
            "message": f"Regulator voltage scaling: {', '.join(reg_scales)}",
        })
    else:
        has_basic_pwr = bool(re.search(
            r'HAL_PWR_ConfigPVD|__HAL_PWR_|PVD_LEVEL|PWR_CR1|PWR_CR2',
            content))
        if has_basic_pwr:
            findings.append({
                "severity": "info",
                "category": "regulator",
                "file": str(path),
                "message": "Basic PWR configuration found (PVD/PVMO)",
            })

    return findings


# ── Static checks: Wake-up sources ────────────────────────────────────────


def _check_wakeup_sources(contents: dict[str, str]) -> list[PowerFinding]:
    """Check wake-up source configuration."""
    findings = []

    wakeup_sources = set()
    for path, content in contents.items():
        if re.search(r'RTC_Alarm|HAL_RTCEx_SetWakeUpTimer|RTC_WAKEUP', content):
            wakeup_sources.add("RTC")
        if re.search(r'EXTI[._]|HAL_EXTI_|SYSCFG_EXTI', content):
            wakeup_sources.add("EXTI")
        if re.search(r'WAKEUP_PIN|WKUP[0-9]|PWR_WAKEUP_PIN', content):
            wakeup_sources.add("WAKEUP_PIN")
        if re.search(r'USB.*Wakeup|USB.*WU', content):
            wakeup_sources.add("USB")
        if re.search(r'UART.*Wakeup|LPUART.*WU|USART_WakeUp', content):
            wakeup_sources.add("UART/LPUART")
        if re.search(r'I2C.*WakeUp|I2C_WakeUp', content):
            wakeup_sources.add("I2C")
        if re.search(r'LPTIM|TIM.*Wakeup|HAL_TIMEx_', content):
            wakeup_sources.add("Timer/LPTIM")
        if re.search(r'COMP[._]|HAL_COMP_', content):
            wakeup_sources.add("Comparator")

    if wakeup_sources:
        findings.append({
            "severity": "info",
            "category": "wakeup_sources",
            "file": "(multiple)",
            "message": f"Wake-up sources: {', '.join(sorted(wakeup_sources))}",
        })
    else:
        findings.append({
            "severity": "info",
            "category": "wakeup_sources",
            "file": "(multiple)",
            "message": "No explicit wake-up source configuration found "
                       "— may use reset or default interrupt-based wakeup",
        })

    return findings


# ── Static checks: DVFS ───────────────────────────────────────────────────


def _check_dvfs(contents: dict[str, str]) -> list[PowerFinding]:
    """Check for dynamic voltage and frequency scaling configuration."""
    findings = []

    dvfs_detected = False
    for path, content in contents.items():
        if re.search(r'DVFS|Dynamic.*Voltage.*Scaling', content, re.IGNORECASE):
            dvfs_detected = True
            findings.append({
                "severity": "info",
                "category": "dvfs",
                "file": str(path),
                "message": "DVFS (Dynamic Voltage and Frequency Scaling) configured",
            })
            break

    freq_scaling = False
    for path, content in contents.items():
        if re.search(r'SystemCoreClock\s*(Update|Set|Change)', content):
            freq_scaling = True
        if re.search(r'HAL_RCC_ClockConfig\s*\(', content):
            freq_scaling = True

    if freq_scaling and not dvfs_detected:
        findings.append({
            "severity": "info",
            "category": "dvfs",
            "file": "(multiple)",
            "message": "Runtime clock frequency changes detected — "
                       "potential DVFS-like behavior without explicit DVFS naming",
        })

    msi_detected = False
    for path, content in contents.items():
        if re.search(r'MSI|MSI_RANGE|MSI_Clock|RCC_MSI', content):
            msi_detected = True
            findings.append({
                "severity": "info",
                "category": "dvfs",
                "file": str(path),
                "message": "MSI oscillator configured — enables automatic frequency "
                           "adjustment in low-power modes (STM32L/U series)",
            })
            break

    if not dvfs_detected and not freq_scaling and not msi_detected:
        findings.append({
            "severity": "info",
            "category": "dvfs",
            "file": "(multiple)",
            "message": "No DVFS / frequency scaling detected — system runs at "
                       "fixed frequency (common for simpler firmware)",
        })

    return findings


# ── Static checks: Peripheral power management ────────────────────────────


def _check_peripheral_power_management(contents: dict[str, str]) -> list[PowerFinding]:
    """Check for peripheral-specific power management patterns."""
    findings = []

    deinit_calls = 0
    init_calls = 0
    for path, content in contents.items():
        for m in re.finditer(r'HAL_(\w+)_Init\s*\(', content):
            init_calls += 1
        for m in re.finditer(r'HAL_(\w+)_DeInit\s*\(', content):
            deinit_calls += 1

    if init_calls > 0 and deinit_calls == 0:
        findings.append({
            "severity": "info",
            "category": "peripheral_power",
            "file": "(multiple)",
            "message": f"{init_calls} peripherals initialized, 0 deinitialized — "
                       f"peripherals run continuously even when idle",
        })

    lp_api_calls = set()
    for path, content in contents.items():
        for api in [
            "HAL_UARTEx_EnableStopMode",
            "HAL_UARTEx_DisableStopMode",
            "HAL_SPIEx_EnableStopMode",
            "HAL_I2CEx_EnableStopMode",
            "HAL_RTCEx_SetWakeUpTimer",
            "HAL_LPTIM_Init",
            "HAL_LPUART_Init",
        ]:
            if api in content:
                lp_api_calls.add(api)

    if lp_api_calls:
        findings.append({
            "severity": "info",
            "category": "peripheral_power",
            "file": "(multiple)",
            "message": f"Peripheral-specific low-power APIs: "
                       f"{', '.join(sorted(lp_api_calls))}",
        })

    pwr_macro_count = 0
    for path, content in contents.items():
        pwr_macro_count += len(list(re.finditer(r'__HAL_PWR_', content)))

    if pwr_macro_count > 0:
        findings.append({
            "severity": "info",
            "category": "peripheral_power",
            "file": "(multiple)",
            "message": f"{pwr_macro_count} low-power control macro(s) used",
        })

    return findings


# ── Main static review ────────────────────────────────────────────────────


def _static_power_review(project_dir: Path) -> list[PowerFinding]:
    """Run all static checks on power-management-related code."""
    all_findings: list[PowerFinding] = []
    files = _find_power_relevant_files(project_dir)

    total_files = sum(len(v) for v in files.values())
    if total_files == 0:
        all_findings.append({
            "severity": "major",
            "category": "discovery",
            "file": str(project_dir),
            "message": "No power-management-related files found — system likely "
                       "runs at full power without any low-power optimization",
        })
        return all_findings

    contents: dict[str, str] = {}
    for cat_key in files:
        for f in files[cat_key]:
            try:
                contents[str(f)] = f.read_text()
            except OSError:
                continue

    log.info("  Checking WFI/WFE usage...")
    all_findings.extend(_check_wfi_wfe_usage(contents))

    for path, content in contents.items():
        all_findings.extend(_check_sleep_on_exit(content, Path(path)))

    log.info("  Checking clock gating...")
    all_findings.extend(_check_clock_gating(contents))

    log.info("  Checking low-power modes...")
    all_findings.extend(_check_low_power_modes(contents))

    for path, content in contents.items():
        all_findings.extend(_check_power_regulator(content, Path(path)))

    log.info("  Checking wake-up sources...")
    all_findings.extend(_check_wakeup_sources(contents))

    log.info("  Checking DVFS...")
    all_findings.extend(_check_dvfs(contents))

    log.info("  Checking peripheral power management...")
    all_findings.extend(_check_peripheral_power_management(contents))

    return all_findings


# ── LLM-powered review ────────────────────────────────────────────────────


def _build_power_review_prompt(files: dict[str, list[Path]]) -> tuple[str, str]:
    """Build prompts for LLM-powered power management review."""
    contents: dict[str, str] = {}
    for category, cat_files in files.items():
        for f in cat_files:
            try:
                text = f.read_text()
                if any(kw in text for kw in [
                    "WFI", "WFE", "SLEEP", "STOP", "STANDBY",
                    "PWR_", "HAL_PWR", "DVFS", "wakeup", "WAKEUP",
                    "clock_gate", "RCC_", "PLL",
                ]):
                    contents[f"{category}:{f}"] = text
            except OSError:
                continue

    system_prompt = (
        "You are an embedded firmware low-power expert.\n"
        "Analyze the provided source files for:\n"
        "1. **WFI/WFE Usage**: Is the processor put into sleep mode during idle?\n"
        "2. **Clock Gating**: Are unused peripheral clocks disabled?\n"
        "3. **Low-Power Modes**: Are SLEEP/STOP/STANDBY modes correctly configured?\n"
        "4. **Wake-Up Sources**: Are all wake-up sources properly configured for exit from low-power modes?\n"
        "5. **DVFS**: Is dynamic voltage and frequency scaling implemented?\n"
        "6. **Peripheral Power**: Are peripherals deinitialized when not in use?\n\n"
        "Output a structured review with:\n"
        "- **PASS/FAIL/RETRY** status\n"
        "- **Findings** (severity: critical/major/minor/info, category, description)\n"
        "- **Summary** paragraph\n"
        "Use markdown format."
    )
    user_lines = ["## Power-Management Related Files\n"]
    for path_key, text in list(contents.items())[:10]:
        user_lines.append(f"### {path_key}\n```\n{text[:4000]}\n```\n")
    user_lines.append(
        "Review the power-management related code above. "
        "Check for any issues affecting energy efficiency, "
        "correct low-power mode entry/exit, and overall power optimization."
    )
    return system_prompt, "\n".join(user_lines)


# ── Step handler ──────────────────────────────────────────────────────────


@timed_step
def step_review_power(session: PipelineSession) -> str:
    """Step: 小克 — 低功耗/能效审查.

    Reviews firmware source code for power management concerns:
    WFI/WFE usage, clock gating, sleep/stop/standby modes,
    wake-up sources, DVFS, and peripheral power management.
    Combines static pattern checks with LLM-powered analysis.
    """
    try:
        print("  ⚡ [小克] 低功耗/能效审查开始...")
        log.info("Running power management review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Part A: Static checks ──
        log.info("Running static power checks...")
        static_findings = _static_power_review(project_dir)
        log.info(f"Static power review: {len(static_findings)} findings")

        # ── Part B: LLM-powered review ──
        log.info("Running LLM-powered power review...")
        llm_review = ""
        power_files = _find_power_relevant_files(project_dir)
        total_files = sum(len(v) for v in power_files.values())
        if total_files > 0:
            try:
                system_prompt, user_prompt = _build_power_review_prompt(power_files)
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=2048)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-power", "usage": usage})
                log.info(f"LLM power review: {usage.get('total_tokens', '?')} tokens")
            except Exception as e:
                log.warning(f"LLM power review failed (non-fatal): {e}")
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

        req_ids = ["SWE-MISRA-S1"]

        report = {
            "session": session.name,
            "reviewer": "小克",
            "step": "review-power",
            "spec_ref": "SWE.5",
            "req_ids": req_ids,
            "timestamp": datetime.now().isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "power_file_counts": {k: len(v) for k, v in power_files.items()},
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "power-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write power review: {e}")
            raise PipelineStepError(f"Cannot write power review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] 低功耗/能效审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"Power review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Power review step failed: {e}")
        raise PipelineStepError(f"Power review step failed: {e}")
