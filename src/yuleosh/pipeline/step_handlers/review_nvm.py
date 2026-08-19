#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step (SWE.5, 第八轮专项): 小克 — NVM 存储审查 (embedded-runtime 组)。

检查嵌入式非易失存储风险域（通用 code-review 易漏）:
- 掉电安全（写入中断/电源跌落时的数据完整性）
- 数据一致性（校验和/CRC/版本号/双缓冲）
- 磨损均衡（flash 擦写次数/寿命）
- 双缓冲 / 页映射（spec SW-006 NVM 布局契约对齐）

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

log = logging.getLogger("pipeline.step_handlers.review_nvm")

__all__ = ["step_review_nvm"]

NvmFinding = dict  # type alias for readability

# ── Static checks for NVM safety ───────────────────────────────────────

# NVM 写 / flash 操作 API
_NVM_WRITE_PATTERNS = [
    r"\b(?:nvm_write|flash_write|flash_program|eeprom_write|storage_write|NVM_Write|Flash_Write|HAL_FLASH_Program)\s*\(",
    r"\b(?:nvm_erase|flash_erase|HAL_FLASHEx_Erase)\s*\(",
]
# 完整性保护原语
_INTEGRITY_PATTERNS = [
    r"\b(?:crc|CRC|checksum|checksum_|_checksum|magic|version|seq|sequence)\b",
]
# 双缓冲 / 备份 / 回滚
_DOUBLE_BUFFER_PATTERNS = [
    r"\b(?:double|dual|backup|backup_|active|shadow|bank|ping|pong|rollback|_prev|_old)\b",
]
# 磨损均衡
_WEAR_LEVEL_PATTERNS = [
    r"\b(?:wear|wear_level|erase_count|erase_cnt|cycle_count|WearLevel|round_robin)\b",
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


def _scan_nvm_safety(project_dir: Path) -> list[NvmFinding]:
    """静态扫描 NVM 风险域，返回 findings。"""
    findings: list[NvmFinding] = []
    sources = _find_c_sources(project_dir)
    if not sources:
        return findings

    has_nvm_write = False
    has_integrity = False
    has_double_buffer = False
    has_wear_level = False
    nvm_files: list[str] = []

    for p in sources:
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(p.relative_to(project_dir))
        is_nvm_file = bool(re.search(r"nvm|flash|eeprom|storage", rel, re.IGNORECASE))

        for pat in _NVM_WRITE_PATTERNS:
            if re.search(pat, content):
                has_nvm_write = True
                if is_nvm_file and rel not in nvm_files:
                    nvm_files.append(rel)
                break

        if is_nvm_file:
            for pat in _INTEGRITY_PATTERNS:
                if re.search(pat, content):
                    has_integrity = True
                    break
            for pat in _DOUBLE_BUFFER_PATTERNS:
                if re.search(pat, content):
                    has_double_buffer = True
                    break
            for pat in _WEAR_LEVEL_PATTERNS:
                if re.search(pat, content):
                    has_wear_level = True
                    break

    if not has_nvm_write and not nvm_files:
        return findings  # 无 NVM 相关代码 → 空 findings（上层自动 skip）

    if has_nvm_write and not has_integrity:
        findings.append({
            "severity": "major",
            "category": "data_integrity",
            "file": ", ".join(nvm_files[:3]) or "src/",
            "message": (
                "检测到 NVM 写入操作但未发现完整性保护（CRC/校验和/magic/版本号）"
                " — 掉电中断写入将产生不可检测的损坏数据"
            ),
        })

    if has_nvm_write and not has_double_buffer:
        findings.append({
            "severity": "major",
            "category": "power_loss_safety",
            "file": ", ".join(nvm_files[:3]) or "src/",
            "message": (
                "NVM 写入未发现双缓冲/备份/回滚机制 — 写入中途掉电会损坏"
                "唯一副本，违反 spec SW-006 NVM 布局契约的掉电安全要求"
            ),
        })

    if has_nvm_write and not has_wear_level:
        findings.append({
            "severity": "minor",
            "category": "wear_leveling",
            "file": ", ".join(nvm_files[:3]) or "src/",
            "message": (
                "NVM 频繁写入路径未发现磨损均衡/擦写计数 — flash 寿命在"
                "高频参数保存场景下可能不足"
            ),
        })

    return findings


# ── LLM prompt ─────────────────────────────────────────────────────────


def _build_nvm_review_prompt(project_dir: Path,
                             findings: list[NvmFinding]) -> tuple[str, str]:
    """Build the NVM safety review prompt (aligned to spec SW-006)."""
    lines = [
        "你是嵌入式非易失存储专家。审查以下项目的 NVM 设计风险：",
        "1. 掉电安全：写入中断/电源跌落时数据完整性",
        "2. 数据一致性：校验和/CRC/版本号/事务语义",
        "3. 磨损均衡：flash 擦写次数与寿命",
        "4. 双缓冲/页映射：与 spec SW-006 NVM 布局契约的对齐",
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
        "请输出: ①每个风险点的严重级别与具体位置 ②修复建议 "
        "③确认无问题的领域（尤其对照 spec 中 SW-006 NVM 布局契约）。"
    )
    return (
        (
            "你是一个严谨的嵌入式 NVM 安全评审 agent。只依据证据下结论，" + "不确定的项标注'需人工确认'，不编造缺陷。",
        ),
        "\n".join(lines),
    )


# ── Step handler ─────────────────────────────────────────────────────────


@timed_step
def step_review_nvm(session: PipelineSession) -> str:
    """Step: 小克 — NVM 存储审查 (embedded-runtime 组)。

    静态模式检查 + LLM 深度审查，报告写入 nvm-review.json。
    任一 critical → failed；major > 3 → retry；否则 passed。
    无 NVM 相关文件 → 自动 skip（不报错）。
    """
    try:
        print("  💾 [小克] NVM 存储审查开始...")
        log.info("Running NVM safety review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # ── Mock mode: skip real review ──────────────────────────
        from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip
        if is_mock(session):
            print("  ⏭️  [小克] NVM 审查跳过 — mock 模式")
            return write_mock_skip(
                session, "review-nvm",
                "mock mode — no real code to review",
            )

        # ── 审查锚定: 本次 run 无代码部署 → honest skip ──
        from yuleosh.pipeline.deploy_state import maybe_skip_code_review
        _deploy_skip = maybe_skip_code_review(session, "review-nvm", reviewer="小克")
        if _deploy_skip:
            print("  ⏭️  [小克] NVM 审查跳过 — 本次 run 无代码部署")
            return _deploy_skip

        # ── Part A: Static checks ──
        static_findings = _scan_nvm_safety(project_dir)
        if not static_findings and not _find_c_sources(project_dir):
            skip = write_mock_skip(
                session, "review-nvm",
                "no C/C++ source files — NVM review not applicable",
            )
            print("  ⏭️  [小克] NVM 审查跳过 — 无 C/C++ 源码")
            return skip

        # ── Part B: LLM-powered review ──
        llm_review = ""
        if static_findings:
            try:
                system_prompt, user_prompt = _build_nvm_review_prompt(
                    project_dir, static_findings
                )
                llm_result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
                llm_review = llm_result["content"]
                usage = llm_result.get("usage", {})
                session.token_usage_total += usage.get("total_tokens", 0)
                session.token_usage_steps.append({"step": "review-nvm", "usage": usage})
            except Exception as e:  # pragma: no cover - defensive  # noqa: BLE001
                log.warning(f"LLM NVM review failed (non-fatal): {e}")
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
            "step": "review-nvm",
            "spec_ref": "SWE.5",
            "req_ids": ["SWE-MISRA-S1", "SW-006"],
            "timestamp": datetime.now(UTC).isoformat(),
            "status": overall_status,
            "static_findings": static_findings,
            "finding_count": len(static_findings),
            "finding_breakdown": finding_breakdown,
            "llm_review": llm_review,
            "summary": (
                f"发现 {len(static_findings)} 项 NVM 安全问题 "
                f"(critical={finding_breakdown['critical']}, "
                f"major={finding_breakdown['major']}, "
                f"minor={finding_breakdown['minor']}, "
                f"info={finding_breakdown['info']})"
            ),
        }

        out_path = session.session_dir / "nvm-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error(f"Cannot write NVM review: {e}")
            raise PipelineStepError(f"Cannot write NVM review: {e}")

        status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄"}
        print(f"  {status_icon.get(overall_status, '❓')} [小克] NVM 存储审查完成 "
              f"({len(static_findings)} findings, status={overall_status})")
        log.info(f"NVM review completed: {overall_status}")
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"NVM review step failed: {e}")
        raise PipelineStepError(f"NVM review step failed: {e}")
