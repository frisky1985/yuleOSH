"""AUD-ASPICE-001 反例注入：三类缺陷必须被确定性判红。

DoD 要求「反例注入」证明门禁不是只会报绿：

1. 漏 SHALL 映射 —— spec 的 SHALL 未在 PRD 中覆盖 → PRD 评审必须判 uncovered；
2. 接口契约不符 —— 声明了接口契约却抽不到/重复需求 ID → 契约门禁必须 passed=False；
3. 覆盖率不足 —— C 行覆盖率低于 c_fail_under → CI 覆盖率门禁必须返回 False。

每组都带一个正向对照（修好之后必须转绿），以证明失败来自注入的缺陷
本身，而不是被测函数恒假。
"""

# @tests src/yuleosh/pipeline/step_handlers/review_prd.py,
#        src/yuleosh/spec_contracts.py,
#        src/yuleosh/ci/stages/test.py

from __future__ import annotations

import json

import pytest

from yuleosh.ci.config import _clear_ci_config_cache
from yuleosh.ci.result import CIResult
from yuleosh.ci.stages.test import run_c_coverage_check
from yuleosh.pipeline.step_handlers.review_prd import (
    _check_shall_coverage,
    _extract_prd_requirements,
    _extract_shalls,
)
from yuleosh.spec_contracts import validate_contracts

# ── 1. 漏 SHALL 映射 ─────────────────────────────────────────────────────

SPEC_TWO_REQS = """\
## 1. 系统需求

### SR-001: LED 闪烁
- SHALL blink the status LED once per second.

### SR-002: 故障上报
- The system SHALL report fault codes over the UART interface.
"""

PRD_ONLY_SR001 = """\
## 4. 软件需求

### 4.1 (SR-001)
| FR-001 | LED 每 1 秒闪烁一次 | 高 |
"""

PRD_BOTH = """\
## 4. 软件需求

### 4.1 (SR-001)
| FR-001 | LED 每 1 秒闪烁一次 | 高 |

### 4.2 (SR-002)
| FR-002 | 通过 UART 上报故障码 | 高 |
"""


def _coverage(prd_content: str) -> list[dict]:
    shalls = _extract_shalls(SPEC_TWO_REQS)
    prd_reqs = _extract_prd_requirements(prd_content)
    return _check_shall_coverage(shalls, prd_reqs)


class TestMissingShallMappingIsRed:
    def test_injected_missing_requirement_is_uncovered(self):
        findings = _coverage(PRD_ONLY_SR001)
        uncovered = [f for f in findings
                     if not f["covered"] and not f["is_meta"]]
        assert len(uncovered) == 1, findings
        assert uncovered[0]["shall"]["section"] == "SR-002"
        assert uncovered[0]["confidence"] == "none"
        assert uncovered[0]["matched_prd"] == ""

    def test_control_all_shalls_covered(self):
        findings = _coverage(PRD_BOTH)
        uncovered = [f for f in findings
                     if not f["covered"] and not f["is_meta"]]
        assert uncovered == [], findings
        assert all(f["confidence"] == "high" for f in findings
                   if not f["is_meta"])


# ── 2. 接口契约不符 ─────────────────────────────────────────────────────

def _contracts(**overrides) -> dict:
    base = {
        "declares_interfaces": True,
        "interfaces": [{"header": f"hal_{i}.h"} for i in range(8)],
        "requirements": ["SWR-001", "SWR-002"],
        "guardrails": ["GR-001"],
        "params": [{"name": "P1"}],
        "nvm_layout": {},
    }
    base.update(overrides)
    return base


class TestInterfaceContractMismatchIsRed:
    def test_declared_but_zero_interfaces_is_red(self):
        result = validate_contracts(_contracts(interfaces=[]))
        assert result["passed"] is False
        assert any("declares interface contracts" in m
                   for m in result["missing"])

    def test_duplicate_requirement_ids_are_red(self):
        result = validate_contracts(
            _contracts(requirements=["SWR-001", "SWR-001", "SWR-002"])
        )
        assert result["passed"] is False
        assert any("duplicate requirement ids" in m
                   for m in result["missing"])
        assert result["details"]["requirements"]["duplicates"] == ["SWR-001"]

    def test_control_complete_contracts_pass(self):
        result = validate_contracts(_contracts())
        assert result["passed"] is True, result["missing"]


# ── 3. 覆盖率不足 ───────────────────────────────────────────────────────

def _write_coverage(project_dir, payload: dict) -> None:
    report_dir = project_dir / ".yuleosh" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "c-coverage.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class TestCoverageBelowThresholdIsRed:
    @pytest.fixture(autouse=True)
    def _fresh_config(self):
        _clear_ci_config_cache()
        yield
        _clear_ci_config_cache()

    def test_low_line_rate_blocks(self, tmp_path):
        _write_coverage(tmp_path, {"line_rate": 12.5, "branch_rate": 40.0})
        ci = CIResult(layer=2, commit_hash="deadbeef")
        assert run_c_coverage_check(str(tmp_path), ci) is False
        failed = [s for s in ci.stages if s.get("name") == "c-coverage-gate"]
        assert failed and failed[0]["status"] == "failed"
        assert "c_fail_under" in failed[0]["detail"]

    def test_control_high_line_rate_passes(self, tmp_path):
        _write_coverage(tmp_path, {"line_rate": 95.0, "branch_rate": 90.0})
        ci = CIResult(layer=2, commit_hash="deadbeef")
        assert run_c_coverage_check(str(tmp_path), ci) is True
        passed = [s for s in ci.stages if s.get("name") == "c-coverage-gate"]
        assert passed and passed[0]["status"] == "passed"

    def test_missing_report_is_skipped_not_false_green(self, tmp_path):
        ci = CIResult(layer=2, commit_hash="deadbeef")
        assert run_c_coverage_check(str(tmp_path), ci) is True
        stages = [s for s in ci.stages if s.get("name") == "c-coverage-gate"]
        assert stages and stages[0]["status"] == "skipped"
