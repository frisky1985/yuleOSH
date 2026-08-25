#!/usr/bin/env python3
"""Regression tests for PRD pipeline fixes (2026-08-16).

Covers:
  C1: _parse_requirements / _parse_scenarios OpenSpec-style (SR-/SW-/Scenario:)
  C3: _detect_prd_truncation heuristics + retry prompt
  C2: build_prd_prompt existing_headers injection + priority discipline
"""

# @tests src/yuleosh/pipeline/step_handlers/review_prd.py

import sys
from pathlib import Path

import pytest

from yuleosh.pipeline.prompts import build_prd_prompt  # noqa: E402
from yuleosh.pipeline.stages.spec import (  # noqa: E402
    _parse_requirements,
    _parse_scenarios,
)
from yuleosh.pipeline.step_handlers.analysis import (  # noqa: E402
    _detect_prd_truncation,
    _prd_truncation_retry_prompt,
)

# ── C1: OpenSpec-style spec parsing ─────────────────────────────────


class TestParseRequirementsOpenSpec:
    def test_sr_sw_headers_parsed(self, tmp_path):
        spec = tmp_path / "spec.md"
        spec.write_text(
            "### SR-001: 硬件抽象\n"
            "- The system SHALL provide a HAL abstraction layer\n"
            "- The system SHALL support PWM output\n"
            "\n"
            "### SW-004: 防夹检测\n"
            "- The system SHALL detect pinch\n"
            "\n"
            "### Scenario: 手动下降\n"
            "- GIVEN the system is in IDLE\n"
        )
        reqs = _parse_requirements(str(spec))
        assert [r["name"] for r in reqs] == ["SR-001", "SW-004"]
        assert len(reqs[0]["shall_statements"]) == 2
        assert len(reqs[1]["shall_statements"]) == 1

    def test_legacy_req_headers_still_work(self, tmp_path):
        spec = tmp_path / "spec.md"
        spec.write_text(
            "### Req-001\n"
            "- The system SHALL work.\n"
        )
        reqs = _parse_requirements(str(spec))
        assert len(reqs) == 1
        assert reqs[0]["name"] == "Req-001"
        assert len(reqs[0]["shall_statements"]) == 1

    def test_scenario_headers_parsed(self, tmp_path):
        spec = tmp_path / "spec.md"
        spec.write_text(
            "### Scenario: 防夹检测与反转\n"
            "- GIVEN window closing in pinch zone\n"
            "- WHEN obstruction blocks\n"
            "- THEN system SHALL detect pinch\n"
        )
        scens = _parse_scenarios(str(spec))
        assert len(scens) == 1
        assert "防夹检测与反转" in scens[0]

    def test_real_window_anti_pinch_spec(self):
        """Regression: real spec must parse to 11 reqs / 51 SHALL / 4 scenarios.

        SHALL 数从 45 → 51 (2026-08-16 spec v1.1.0 契约化新增约束语句:
        防夹判定语义/反转模式/坐标系/配置单位/AC 阈值, 部分以 **...SHALL...**
        粗体行表述也被计入 SHALL 语句)。
        """
        spec = Path(
            "/Users/stefan/workspace/window-anti-pinch/window-anti-pinch/spec.md"
        )
        if not spec.exists():
            pytest.skip("window-anti-pinch spec not present")
        reqs = _parse_requirements(str(spec))
        scens = _parse_scenarios(str(spec))
        total_shall = sum(len(r["shall_statements"]) for r in reqs)
        # 快照断言脆弱: spec 每次契约化 (v1.1.x) 都涨 SHALL 数
        # (51 → 72, 2026-08-16 v1.1.5 NVM 契约)。只验证下限 + 结构。
        assert len(reqs) >= 11, f"got {len(reqs)}"
        assert total_shall >= 51, f"got {total_shall}"
        assert len(scens) == 4, f"got {len(scens)}"


# ── C3: truncation detection ────────────────────────────────────────


class TestDetectPrdTruncation:
    def test_complete_prd_no_signals(self):
        prd = (
            "# PRD\n"
            "## 6 Acceptance Criteria\n"
            "AC-001 a\nAC-002 b\nAC-003 c\nAC-004 d\n"
            "## 7 Out of Scope\n"
            "- nothing\n"
        )
        assert _detect_prd_truncation(prd, 4) == []

    def test_empty_output(self):
        assert _detect_prd_truncation("", 4) == ["PRD 输出为空"]
        assert _detect_prd_truncation("   \n  ", 4) == ["PRD 输出为空"]

    def test_unclosed_table_tail(self):
        prd = "# PRD\n| FR-001 | desc | P0 |\n| FR-002 | desc | P1"
        signals = _detect_prd_truncation(prd, 4)
        assert any("未闭合表格" in s for s in signals)

    def test_complete_table_rows_not_false_positive(self):
        # 2026-08-17 回归 (r19 实证): traceability 矩阵的正常表格行以 `|`
        # 结尾, 旧实现 re.search(r"\|[ \t]*$", tail) 把完整 PRD 误报截断。
        prd = (
            "# PRD\n"
            "| SW-008 | FR-067 ~ FR-073 | — | AC-006-1 ~ AC-006-5 | G-01, G-02 |\n"
            "| SW-007 | FR-062 ~ FR-066 | US-004, US-007 | AC-004-1 ~ AC-004-5 | G-10, G-13 |\n\n"
            "---\n\n"
            "*本文档由 Hermes (PM) 基于 spec.md v1.1.7 生成*"
        )
        signals = _detect_prd_truncation(prd, 4)
        assert not any("表格" in s for s in signals), f"误报: {signals}"

    def test_complete_table_rows_ending_no_epilogue(self):
        # 表格行直接结尾 (无结束语) 也不该报"未闭合表格"
        prd = "# PRD\n| FR-001 | desc | P0 |\n| FR-002 | desc | P1 |"
        signals = _detect_prd_truncation(prd, 4)
        assert not any("表格" in s for s in signals), f"误报: {signals}"

    def test_ac_count_below_scenarios(self):
        prd = "# PRD\nAC-001 a\n## 7 Out of Scope\n- nothing\n"
        signals = _detect_prd_truncation(prd, 4)
        assert any("Acceptance Criteria 数量 (1) 少于" in s for s in signals)

    def test_missing_out_of_scope(self):
        prd = "# PRD\nAC-001 a\nAC-002 b\nAC-003 c\nAC-004 d\n"
        signals = _detect_prd_truncation(prd, 4)
        assert any("Out of Scope" in s for s in signals)

    def test_retry_prompt_mentions_truncation(self):
        p = _prd_truncation_retry_prompt("BASE", ["sig-a", "sig-b"])
        assert "BASE" in p
        assert "截断" in p
        assert "sig-a" in p
        assert "sig-b" in p


# ── C2: PRD prompt API contract injection ───────────────────────────


class TestBuildPrdPromptExistingHeaders:
    def test_existing_headers_injected(self):
        sys_p, user_p = build_prd_prompt(
            spec_content="### SR-001\n- SHALL x",
            spec_name="spec.md",
            requirements=[{"name": "SR-001", "shall_statements": ["- SHALL x"]}],
            scenarios=["Scenario: X"],
            existing_headers="### src/hal/include/hal_hall.h\n```c\nint hal_hall_get_count(void);\n```",
        )
        assert "既有 API 契约" in user_p
        assert "hal_hall_get_count" in user_p
        assert "hal_hall_get_pulse_count" in user_p  # anti-example present

    def test_no_headers_no_injection(self):
        sys_p, user_p = build_prd_prompt(
            spec_content="### SR-001\n- SHALL x",
            spec_name="spec.md",
            requirements=[{"name": "SR-001", "shall_statements": ["- SHALL x"]}],
            scenarios=[],
        )
        assert "既有 API 契约" not in user_p

    def test_priority_discipline_in_system_prompt(self):
        sys_p, user_p = build_prd_prompt(
            spec_content="### SR-001\n- SHALL x",
            spec_name="spec.md",
            requirements=[{"name": "SR-001", "shall_statements": ["- SHALL x"]}],
            scenarios=[],
        )
        assert "NEVER mark a SHALL-derived requirement P2" in sys_p
        assert "Acceptance Criteria MUST be concrete" in sys_p
