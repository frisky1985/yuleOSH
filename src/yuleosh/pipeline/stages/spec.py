#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Pipeline Stages — Spec parsing and cache.

Extracted from stages.py (Phase 2.1 refactor, P0-4).

Provides:
  - _get_spec_mtime — file mtime for cache invalidation
  - _parse_spec     — cached spec parsing
  - _parse_requirements — extract Req-* sections from markdown spec
  - _parse_scenarios    — extract GIVEN/WHEN/THEN scenarios
  - _try_parse_hermes_json — robust LLM JSON response parsing
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from yuleosh.pipeline.stages.step_timing import timed_step

log = logging.getLogger("pipeline.stages.spec")


def _recover_truncated_review(raw: str, session_name: str) -> dict | None:
    """从被截断的 LLM review JSON 中恢复已完成内容 (2026-08-20 r22 real-8).

    LLM 重复膨胀输出超 max_tokens → 输出在 findings 数组中段截断 →
    标准 json.loads 失败。策略:
      1. 先尝试标准解析 (防御: 万一 JSON 实际完整)。
      2. 用 json.JSONDecoder.raw_decode 从 raw 中连续提取所有完整
         ``{...}`` 对象 — 每个 finding 对象通常是完整 JSON 值, 截断
         只发生在最后一个对象上。
      3. 若提取到 ≥1 个完整 finding 对象, 组装 review dict 返回;
         否则返回 None (调用方回退 retry)。
    """
    if not raw:
        return None
    # 1. 标准解析 (防御)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # 2. 提取完整对象: 逐段 raw_decode, 收集所有顶层 dict
    decoder = json.JSONDecoder()
    collected: list[dict] = []
    idx = 0
    n = len(raw)
    while idx < n:
        # 跳过非 JSON 起始字符
        while idx < n and raw[idx] not in "{[\"":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            collected.append(obj)
        idx = end

    if not collected:
        return None

    # 3. 找到主 review 对象 (含 findings 键的 dict; 优先最后一个)
    main: dict | None = None
    for cand in reversed(collected):
        if isinstance(cand, dict) and "findings" in cand:
            main = cand
            break
    if main is None:
        # 没有主对象 → 把收集到的都当 findings 容器
        main = {"findings": collected}

    findings = main.get("findings")
    if not isinstance(findings, list) or not findings:
        return None

    # 过滤: 只保留 dict 形式 finding (截断的字符串碎片丢弃)
    valid = [f for f in findings if isinstance(f, dict)]
    if not valid:
        return None

    main["findings"] = valid
    main.setdefault("session", session_name)
    main.setdefault("reviewer", "Hermes")
    main.setdefault("timestamp", datetime.now().isoformat())
    main.setdefault("status", "retry")
    main.setdefault("summary", "Recovered from truncated LLM output (重复膨胀截断).")
    # 注意: 去重由 review_guard.dedupe_review_findings 在调用方执行
    main["_recovered_truncated"] = True
    main["_raw_llm_output"] = raw
    return main

# Store for spec cache (lazy init)
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from store import Store  # noqa: E402
    _store = Store()
except Exception as e:
    logging.getLogger("pipeline.stages.spec").warning("Store init failed: %s", e)
    _store = None
finally:
    _p = os.path.join(os.path.dirname(__file__), "..", "..")
    while _p in sys.path:
        sys.path.remove(_p)


# ------------------------------------------------------------------
# Spec cache — stores parsed results in SQLite keyed by path+mtime
# ------------------------------------------------------------------


def _get_spec_mtime(spec_path: str) -> float:
    """Return file mtime for cache invalidation."""
    try:
        return Path(spec_path).stat().st_mtime
    except OSError:
        return 0.0


# --- Step Handlers ---


@timed_step
def _parse_spec(spec_path: str) -> dict:
    """Parse spec file: returns requirements + scenarios, cached via SQLite.

    Cache is invalidated when the spec file's mtime changes.
    """
    mtime = _get_spec_mtime(spec_path)

    # Try cache hit
    if _store:
        try:
            cached = _store.get_cached_spec_parse(spec_path, mtime)
            if cached is not None:
                return cached
        except Exception as e:
            log.warning(f"Spec cache read failed (will re-parse): {e}")

    # Parse fresh
    requirements = _parse_requirements(spec_path)
    scenarios = _parse_scenarios(spec_path)
    result = {"requirements": requirements, "scenarios": scenarios}

    # Store in cache
    if _store:
        try:
            _store.cache_spec_parse(spec_path, mtime, result)
        except Exception as e:
            log.warning(f"Spec cache write failed (non-fatal): {e}")

    return result


def _parse_requirements(spec_path: str) -> list[dict]:
    """Read requirements from a spec file. Each requirement is a dict with name and shall_statements.

    Supports requirement headers of the form:
      - `### Req-001:` (legacy)
      - `### SR-001: 硬件抽象` / `### SW-004: 防夹检测` (OpenSpec-style, 2026-08-16)
    SHALL/SHOULD bullet statements under each header are collected.
    """
    requirements = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found: {spec_path}")
            return requirements
        content = path.read_text()
        lines = content.split("\n")
        current_name = None
        current_shalls = []
        in_requirement = False
        # OpenSpec 风格: `### SR-001:` / `### SW-004:` / legacy `### Req-001`
        req_header_re = re.compile(
            r"^#{2,4}\s+([A-Za-z]{2,4}-\d+)\b",
        )
        for line in lines:
            stripped = line.strip()
            m = req_header_re.match(stripped)
            if m:
                if current_name:
                    requirements.append({
                        "name": current_name,
                        "shall_statements": current_shalls
                    })
                current_name = m.group(1)
                current_shalls = []
                in_requirement = True
            elif in_requirement and stripped.startswith("-") and ("SHALL" in stripped or "SHOULD" in stripped):
                current_shalls.append(stripped)
            elif in_requirement and stripped.startswith("### "):
                # End of requirement, next section (Scenario or other)
                in_requirement = False
        if current_name:
            requirements.append({
                "name": current_name,
                "shall_statements": current_shalls
            })
    except Exception as e:
        log.warning(f"Failed to parse requirements from {spec_path}: {e}")
    return requirements


def _parse_scenarios(spec_path: str) -> list[str]:
    """Read GIVEN/WHEN/THEN scenarios from a spec file.

    Recognizes both:
      - `### Scenario: 手动下降` (OpenSpec-style, body carries GIVEN/WHEN/THEN)
      - `### GIVEN ...` / `### WHEN ...` / `### THEN ...` (legacy heading style)
    """
    scenarios = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found for scenarios: {spec_path}")
            return scenarios
        content = path.read_text()
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("### "):
                # OpenSpec 风格: `### Scenario: 手动下降` — 记场景名
                if "Scenario" in stripped or "场景" in stripped:
                    scenarios.append(stripped.replace("### ", ""))
                elif ("GIVEN" in stripped or "WHEN" in stripped
                        or "THEN" in stripped):
                    # legacy 风格: 单行场景 (`### GIVEN ...`)
                    scenarios.append(stripped.replace("### ", ""))
    except Exception as e:
        log.warning(f"Failed to parse scenarios from {spec_path}: {e}")
    return scenarios


def _try_parse_hermes_json(raw: str, session_name: str) -> dict:
    """Parse Hermes review JSON from LLM output with robust fallback.

    Supports common format deviations:
      - Markdown ```json code fences
      - Leading/trailing explanatory text
      - Missing required fields (fills in defaults)
      - Pre/post whitespace
      - Multiple code blocks (uses the first valid JSON block)

    Returns a valid review dict in all cases (with status='retry' if
    parsing ultimately fails, including raw output for debugging).
    """
    json_str = raw.strip()
    raw_preview_500 = raw[:500]

    # Try bare JSON first
    if json_str.startswith("{") and json_str.endswith("}"):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass  # Fall through to fence stripping

    # Strip markdown fences: ```json ... ``` or ``` ... ```
    if "```" in json_str:
        # Collect all fenced blocks
        blocks = []
        in_fence = False
        current = []
        for line in json_str.split("\n"):
            if line.strip().startswith("```"):
                if in_fence:
                    # End of a fenced block
                    blocks.append("\n".join(current))
                    current = []
                    in_fence = False
                else:
                    in_fence = True
                    # Skip the opening fence (optionally with "json" after)
                    lang = line.strip().lstrip("```").strip().lower()
                    if lang and lang != "json":
                        # It's a non-JSON code block, skip content
                        in_fence = False
                    current = []
            elif in_fence:
                current.append(line)

        for block in blocks:
            block = block.strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # If we have leading text before a JSON block, try to find { ... }
    brace_start = json_str.find("{")
    if brace_start >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(json_str)):
            if json_str[i] == "{":
                depth += 1
            elif json_str[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[brace_start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue

    # Final fallback: return retry status with raw output embedded
    log.warning(f"Could not parse Hermes review JSON. Raw output (first 500 chars): {raw_preview_500}")
    # 截断恢复 (2026-08-20 r22 real-8): LLM 输出重复膨胀被 max_tokens
    # 截断 → JSON 不完整。尝试从截断文本中恢复"已完成"的 findings —
    # 用 incremental JSON 解码逐段累积, 或提取完整 finding 对象。
    recovered = _recover_truncated_review(raw, session_name)
    if recovered is not None:
        log.warning("Recovered %d finding(s) from truncated review JSON", len(recovered.get("findings", [])))
        return recovered
    return {
        "session": session_name,
        "reviewer": "Hermes",
        "timestamp": datetime.now().isoformat(),
        "status": "retry",
        "_raw_llm_output": raw,
        "findings": [{
            "severity": "major",
            "category": "reviewer-error",
            "file": "",
            "line": None,
            "message": (
                f"LLM review output was not valid JSON. "
                f"Raw output (first 500 chars): {raw_preview_500}"
            ),
        }],
        "finding_breakdown": {"critical": 0, "major": 1, "minor": 0, "info": 0},
        "summary": f"LLM review could not be parsed \u2014 check raw output.",
    }
