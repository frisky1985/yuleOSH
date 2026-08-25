#!/usr/bin/env python3

# @req SWR-001.2
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Step: test_case_gen — 独立 test case generator (Q6).

从 spec 的 SHALL 陈述和 GIVEN/WHEN/THEN 场景确定性生成结构化测试用例骨架。
输出 test-cases.json，格式与 RTM 直接 join：
  {req_id}::{scenario_id} 作为 test_id。

设计目标:
- 纯确定性：不调用 LLM，基于 spec 解析生成骨架
- 输出格式与 JUnit testcase name 约定对齐
- alm/traceability.py scan_test_reports 可直接识别 test-cases.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.test_case_gen")

__all__ = ["run_test_case_gen", "step_test_case_gen"]


# ── Spec parsing ──────────────────────────────────────────────────────────────

_SHALL_RE = re.compile(
    r'\b(?:RS|SWR|SRS|REQ|TS)-\d+(?:\.\d+)*\b',
    re.IGNORECASE,
)

_GIVEN_RE = re.compile(r'(?i)^#+\s*|GIVEN\s*[:\-]?\s*(.+)', re.MULTILINE)


class _ScenarioParser:
    """Parse GIVEN/WHEN/THEN blocks from a spec text."""

    _BLOCK_SEP = re.compile(r'\n(?=#{2,4}\s)')
    _GIVEN = re.compile(r'(?i)GIVEN\s*[:\-]?\s*(.*)')
    _WHEN = re.compile(r'(?i)WHEN\s*[:\-]?\s*(.*)')
    _THEN = re.compile(r'(?i)THEN\s*[:\-]?\s*(.*)')

    def parse(self, text: str) -> list[dict[str, Any]]:
        scenarios = []
        blocks = self._BLOCK_SEP.split(text)
        if len(blocks) <= 1:
            # flat text — split on blank lines
            blocks = re.split(r'\n\s*\n', text)

        for block in blocks:
            if not re.search(r'(?i)GIVEN', block):
                continue
            if not re.search(r'(?i)WHEN', block):
                continue
            scenario = self._parse_block(block.strip())
            if scenario:
                scenarios.append(scenario)
        return scenarios

    def _parse_block(self, block: str) -> dict[str, Any] | None:
        given, when, then = [], "", []
        current = None
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            gm = self._GIVEN.match(s)
            wm = self._WHEN.match(s)
            tm = self._THEN.match(s)
            if gm:
                current = "given"
                rest = gm.group(1).strip()
                if rest:
                    given.append(rest)
            elif wm:
                current = "when"
                rest = wm.group(1).strip()
                if rest:
                    when = rest
            elif tm:
                current = "then"
                rest = tm.group(1).strip()
                if rest:
                    then.append(rest)
            elif current == "given" and s:
                given.append(s)
            elif current == "when" and not when and s:
                when = s
            elif current == "then" and s:
                then.append(s)

        if not given or not when:
            return None
        return {"given": given, "when": when, "then": then, "raw_block": block}


def _extract_req_ids(text: str) -> list[str]:
    """Extract requirement IDs referenced in a block."""
    return list(dict.fromkeys(m.upper() for m in _SHALL_RE.findall(text)))


def _scenario_id(index: int, when_text: str) -> str:
    """Generate a stable short scenario ID."""
    slug = re.sub(r'[^a-z0-9]+', '-', when_text.lower().strip())[:40].strip('-')
    return f"SC-{index + 1:03d}-{slug}" if slug else f"SC-{index + 1:03d}"


def _derive_title(when: str, given: list[str]) -> str:
    """Derive a readable test case title."""
    when_clean = re.sub(r'\s+', ' ', when).strip()
    return f"When {when_clean}" if when_clean else "Unnamed scenario"


def _build_test_case(
    index: int,
    scenario: dict[str, Any],
    req_ids: list[str],
    spec_path: str,
) -> dict[str, Any]:
    given = scenario["given"]
    when = scenario["when"]
    then = scenario["then"]

    scenario_id = _scenario_id(index, when)
    # Primary req_id: first extracted or "REQ-UNKNOWN"
    req_id = req_ids[0] if req_ids else "REQ-UNKNOWN"
    test_id = f"{req_id}::{scenario_id}"

    return {
        "test_id": test_id,
        "req_id": req_id,
        "req_ids": req_ids,
        "scenario_id": scenario_id,
        "title": _derive_title(when, given),
        "preconditions": given,
        "steps": [when] if isinstance(when, str) else when,
        "expected": then,
        "status": "generated",
        "spec_source": spec_path,
    }


# ── Main runner ───────────────────────────────────────────────────────────────

def run_test_case_gen(
    spec_path: str,
    session_name: str = "",
) -> dict[str, Any]:
    """Parse spec and generate structured test case skeletons.

    Returns a dict with:
      - test_cases: list of test case dicts
      - test_count: int
      - spec_path: str
      - generated_at: ISO timestamp
      - status: "ok" | "empty"
    """
    spec_text = ""
    try:
        spec_text = Path(spec_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.warning("Cannot read spec %s: %s", spec_path, e)

    parser = _ScenarioParser()
    scenarios = parser.parse(spec_text)

    test_cases = []
    for i, scenario in enumerate(scenarios):
        req_ids = _extract_req_ids(scenario.get("raw_block", ""))
        if not req_ids:
            # Fall back to scanning the surrounding spec text for IDs near this block
            req_ids = _extract_req_ids(spec_text)[:3]
        tc = _build_test_case(i, scenario, req_ids, spec_path)
        test_cases.append(tc)

    return {
        "session": session_name,
        "spec_path": spec_path,
        "generated_at": datetime.now().isoformat(),
        "test_count": len(test_cases),
        "status": "ok" if test_cases else "empty",
        "test_cases": test_cases,
    }


# ── Pipeline step ─────────────────────────────────────────────────────────────

def step_test_case_gen(session: PipelineSession) -> str:
    """Step: deterministic test case generator from spec scenarios (Q6).

    Parses GIVEN/WHEN/THEN blocks from the spec and outputs a structured
    test-cases.json. No LLM call — pure deterministic parsing.

    Output: session.session_dir/test-cases.json
    Artifact key: session.artifacts["test-cases"]
    """
    try:
        print("  🧩 [test-case-gen] 生成结构化测试用例骨架...")

        spec_path = getattr(session, "spec_path", "")
        if not spec_path:
            log.warning("test_case_gen: no spec_path on session — skipping")
            out = _write_skip(session, "no spec_path")
            return str(out)

        result = run_test_case_gen(spec_path, session_name=session.name)
        test_count = result["test_count"]

        out_path = Path(session.session_dir) / "test-cases.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        session.artifacts["test-cases"] = str(out_path)

        icon = "✅" if test_count > 0 else "⚠️"
        print(f"  {icon} [test-case-gen] 生成 {test_count} 条测试用例 → {out_path.name}")
        log.info("test_case_gen: %d test cases written to %s", test_count, out_path)
        return str(out_path)

    except PipelineStepError:
        raise
    except Exception as e:
        log.error("test_case_gen step failed: %s", e)
        raise PipelineStepError(f"test_case_gen step failed: {e}") from e


def _write_skip(session: PipelineSession, reason: str) -> Path:
    out_path = Path(session.session_dir) / "test-cases.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "session": session.name,
            "status": "skipped",
            "reason": reason,
            "test_count": 0,
            "test_cases": [],
            "generated_at": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    session.artifacts["test-cases"] = str(out_path)
    return out_path
