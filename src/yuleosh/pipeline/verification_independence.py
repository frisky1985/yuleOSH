#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""验证独立性台账（AUD-ASPICE-001 NC-03）。

ASPICE / SDD §1.2 要求「验证独立性」：验证结论必须来自与被验证对象不同的
通道，且独立性等级可审计。本模块把每个验证步骤的独立性如实分级并写入
``session.json``：

======  ==========================================================
等级    含义
======  ==========================================================
isolated  独立通道：确定性解析器 / 编译器与测试运行器子进程 / 外部 CLI
degraded  同模型新上下文（LLM 自评审）——不满足"物理隔离"
none      未执行验证（skipped / failed / mock）
======  ==========================================================

分级是**记录事实**，不是放宽门禁：``none`` 的 P0 步骤由 NC-12 的
P0 阻断规则处理。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("pipeline.verification_independence")

LEVEL_ISOLATED = "isolated"
LEVEL_DEGRADED = "degraded"
LEVEL_NONE = "none"

#: step_key → (channel, description)。
#: channel ∈ {deterministic, toolchain, external-agent, llm-same-model}
CHANNEL_MAP: dict[str, tuple[str, str]] = {
    # 确定性解析 / 纯计算
    "test-case-gen": ("deterministic", "spec-only deterministic parser"),
    "verify-loop": ("deterministic", "test runner loop (no LLM)"),
    "traceability": ("deterministic", "artifact traceability scan"),
    # 编译 / 执行器子进程
    "c-unit-test": ("toolchain", "compiler + ctest subprocess"),
    "test-c-unit": ("toolchain", "compiler + ctest subprocess"),
    "integration-test": ("toolchain", "integration runner subprocess"),
    "qemu-run": ("toolchain", "qemu subprocess"),
    "c-coverage-gate": ("toolchain", "ctest + gcovr subprocess"),
    "static-analysis": ("toolchain", "cppcheck / misra analyser"),
    "misra-review": ("toolchain", "cppcheck / misra analyser"),
    # 外部 CLI（独立进程 / 独立模型）
    "claude-review": ("external-agent", "claude CLI (separate process)"),
    "codex-verify": ("external-agent", "codex CLI (separate process)"),
    # 同模型新上下文的自评审 —— 只能算 degraded
    "prd-review": ("llm-same-model", "same model, new context"),
    "internal-review": ("llm-same-model", "same model, new context"),
    "arch-review": ("llm-same-model", "same model, new context"),
    "development-review": ("llm-same-model", "same model, new context"),
    "test-planning": ("llm-same-model", "same model, new context"),
    "internal-code-review": ("llm-same-model", "same model, new context"),
}

_ISOLATED_CHANNELS = {"deterministic", "toolchain", "external-agent"}

_FUNC_DEF_RE = re.compile(r"\b[A-Za-z_]\w*\s*\([^;{}()]*\)\s*\{")
_SKIP_DIRS = {"artifacts", "build", "cmake-build-coverage", "third_party",
              ".git", ".osh", "tests", "node_modules"}


def channel_for(step_key: str) -> tuple[str, str] | None:
    """返回步骤的验证通道；非验证步骤返回 None。"""
    return CHANNEL_MAP.get(step_key)


def _read_artifact(path) -> dict:
    try:
        if not path:
            return {}
        p = Path(path)
        if not p.is_file() or p.suffix.lower() != ".json":
            return {}
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _artifact_skipped(artifact: dict) -> str:
    """若产物显式声明 skipped，返回其理由；否则空串。"""
    if artifact.get("skipped") is True:
        return str(artifact.get("reason") or "artifact marked skipped")
    if str(artifact.get("status", "")).strip().lower() == "skipped":
        return str(artifact.get("reason") or "artifact status=skipped")
    return ""


def classify(step_key: str, step_status: str = "completed",
             artifact: dict | None = None, reason: str = "") -> dict | None:
    """给一个验证步骤分级。非验证步骤返回 None。

    Parameters
    ----------
    step_status: ``completed`` / ``failed`` / ``skipped`` / ``cached``
    artifact: 步骤产物 JSON（用于识别 handler 内部显式 skip）
    """
    entry = channel_for(step_key)
    if entry is None:
        return None
    channel, description = entry

    detail = {
        "channel": channel,
        "channel_description": description,
        "step_status": step_status,
    }

    if step_status in ("failed", "skipped", "blocked"):
        return {**detail, "level": LEVEL_NONE,
                "reason": reason or f"step {step_status}"}

    skipped_reason = _artifact_skipped(artifact or {})
    if skipped_reason:
        return {**detail, "level": LEVEL_NONE, "reason": skipped_reason}

    level = LEVEL_ISOLATED if channel in _ISOLATED_CHANNELS else LEVEL_DEGRADED
    payload = {**detail, "level": level, "reason": reason}
    if level == LEVEL_DEGRADED:
        payload["reason"] = (
            "same model in a new context — independent review channel absent"
        )
    return payload


def record(session, step_key: str, step_status: str = "completed",
           artifact_path=None, reason: str = "") -> dict | None:
    """分级并写入 ``session.verification_independence``。"""
    artifact = _read_artifact(artifact_path)
    verdict = classify(step_key, step_status, artifact, reason)
    if verdict is None:
        return None
    ledger = getattr(session, "verification_independence", None)
    if not isinstance(ledger, dict):
        ledger = {}
        try:
            session.verification_independence = ledger
        except Exception:  # pragma: no cover - 只读 session 兜底
            return verdict
    ledger[step_key] = verdict
    return verdict


def summarize(session) -> dict:
    """汇总独立性台账：{counts, degraded, missing(p0 未执行)}。"""
    ledger = getattr(session, "verification_independence", {}) or {}
    counts = {LEVEL_ISOLATED: 0, LEVEL_DEGRADED: 0, LEVEL_NONE: 0}
    for verdict in ledger.values():
        level = verdict.get("level", LEVEL_NONE)
        counts[level] = counts.get(level, 0) + 1
    return {
        "counts": counts,
        "degraded": sorted(k for k, v in ledger.items()
                           if v.get("level") == LEVEL_DEGRADED),
        "not_verified": sorted(k for k, v in ledger.items()
                               if v.get("level") == LEVEL_NONE),
    }


def source_body_leak(artifact_path, project_dir) -> list[str]:
    """检测测试产物中是否混入了工程源码的函数体（SDD §4.2 通道 B 隔离）。

    返回命中的源文件相对路径列表；空列表表示产物只含 spec 派生信息。
    判定用「函数体原文子串」而不是函数名：函数名出现在测试里是正常的
    （被测 API），函数体原文出现才说明测试上下文接触了实现。
    """
    try:
        text = Path(artifact_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if not text.strip():
        return []

    root = Path(project_dir)
    normalised_text = _normalise(text)
    hits: list[str] = []
    for src in root.rglob("*"):
        if src.suffix not in (".c", ".cpp", ".cc"):
            continue
        try:
            rel = src.relative_to(root)
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        try:
            body = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for snippet in _function_bodies(body):
            if _normalise(snippet) in normalised_text:
                hits.append(str(rel))
                break
    return sorted(set(hits))


def _normalise(text: str) -> str:
    """归一化：去掉全部空白与反斜杠后再比对。

    产出的测试文件常是 JSON/字符串字面量，源码里的换行 ``\\n`` / 引号 ``\\"``
    会被二次转义 —— 空白与转义符的差异不改变"函数体是否被搬运"这一事实，
    因此统一剥离后再做子串匹配。
    """
    return re.sub(r"[\s\\]+", "", re.sub(r"\\[ntr]", "", text))


def _function_bodies(source: str, min_len: int = 80) -> list[str]:
    """提取 C 函数体的原文片段（长度 ≥ min_len 才用于泄漏比对）。"""
    bodies: list[str] = []
    for match in _FUNC_DEF_RE.finditer(source):
        start = match.end() - 1  # 指向 '{'
        depth = 0
        for idx in range(start, len(source)):
            ch = source[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = source[start:idx + 1].strip()
                    if len(snippet) >= min_len:
                        bodies.append(snippet)
                    break
    return bodies
