"""Tests for pipeline/step_handlers/review_misra_ci.py."""
import os
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from yuleosh.pipeline.step_handlers.review_misra_ci import (
    _read_misra_report, _read_misra_trend, _compute_trend,
    _classify_violations, _generate_fix_recommendations,
    _check_for_regression_violations, step_review_misra_ci,
    _check_report_staleness,
    _PRIORITY_MAP, _DEFAULT_REPORT_DIR,
)


class TestPriorityMap:
    def test_mapping(self):
        assert _PRIORITY_MAP["required"] == 1
        assert _PRIORITY_MAP["advisory"] == 2
        assert _PRIORITY_MAP["unknown"] == 3


class TestReadMisraReport:
    def test_no_report(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_misra_report(Path(td))
            assert result is None

    def test_valid_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / ".yuleosh" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            data = {"summary": {"total_violations": 10}, "groups": {}}
            (report_dir / "misra-report.json").write_text(json.dumps(data))
            result = _read_misra_report(Path(td))
            assert result["summary"]["total_violations"] == 10

    def test_corrupt_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_dir = Path(td) / ".yuleosh" / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "misra-report.json").write_text("not-json")
            result = _read_misra_report(Path(td))
            assert result is None


class TestReadMisraTrend:
    def test_no_trend_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = _read_misra_trend(Path(td))
            assert result == []

    def test_with_entries(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "misra-trend.jsonl").write_text(
                json.dumps({"total_violations": 10}) + "\n"
                + json.dumps({"total_violations": 5}) + "\n"
            )
            result = _read_misra_trend(Path(td))
            assert len(result) == 2
            assert result[0]["total_violations"] == 5  # most recent first

    def test_max_entries(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps({"total_violations": i}) + "\n" for i in range(30)]
            (trend_dir / "misra-trend.jsonl").write_text("".join(lines))
            result = _read_misra_trend(Path(td), max_entries=5)
            assert len(result) == 5

    def test_bad_json_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            trend_dir = Path(td) / ".yuleosh" / "reports"
            trend_dir.mkdir(parents=True, exist_ok=True)
            (trend_dir / "misra-trend.jsonl").write_text("bad\n" + json.dumps({"ok": 1}) + "\n")
            result = _read_misra_trend(Path(td))
            assert len(result) == 1


class TestComputeTrend:
    def test_first_run(self):
        trend = _compute_trend({"summary": {"total_violations": 5}}, None)
        assert trend["direction"] == "first_run"

    def test_no_change(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 5}, "violations_raw": []},
            {"summary": {"total_violations": 5}, "violations_raw": []}
        )
        assert trend["direction"] == "same"

    def test_increase(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 10}, "violations_raw": [{"severity": "error"}]},
            {"summary": {"total_violations": 5}, "violations_raw": [{"severity": "error"}]}
        )
        assert trend["direction"] == "up"
        assert trend["delta"] == 5

    def test_decrease(self):
        trend = _compute_trend(
            {"summary": {"total_violations": 3}, "violations_raw": []},
            {"summary": {"total_violations": 10}, "violations_raw": [{"severity": "warning"}]}
        )
        assert trend["direction"] == "down"
        assert trend["delta"] == -7


class TestClassifyViolations:
    def test_empty_groups(self):
        classified = _classify_violations({"groups": {}})
        assert classified == []

    def test_required_violation(self):
        report = {"groups": {
            "R1.1": {
                "severity_category": "Required",
                "count": 3,
                "title": "Test rule",
                "files": ["main.c"],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["priority"] == 1
        assert classified[0]["needs_deviation"] is True

    def test_advisory_violation(self):
        report = {"groups": {
            "A1.1": {
                "severity_category": "Advisory",
                "count": 2,
                "title": "Advisory rule",
                "files": [],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["priority"] == 2

    def test_sort_by_priority(self):
        report = {"groups": {
            "R1": {"severity_category": "Required", "count": 1, "title": "R", "files": []},
            "A1": {"severity_category": "Advisory", "count": 5, "title": "A", "files": []},
        }}
        classified = _classify_violations(report)
        assert classified[0]["rule_id"] == "R1"

    def test_mandatory_severity(self):
        """Unknown/"mandatory" category falls back to priority 3, no deviation
        (v3.4.0: only ``required`` severity needs deviation — docstring spec)."""
        report = {"groups": {
            "M1.1": {
                "severity_category": "Mandatory",
                "count": 2,
                "title": "Mandatory rule",
                "files": ["main.c"],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["severity"] == "mandatory"
        assert classified[0]["needs_deviation"] is False

    def test_unknown_severity_category(self):
        """Unknown severity category should be treated as priority 3."""
        report = {"groups": {
            "X1": {
                "severity_category": "unknown",
                "count": 1,
                "title": "Unknown",
                "files": [],
            }
        }}
        classified = _classify_violations(report)
        assert len(classified) == 1
        assert classified[0]["priority"] == 3

    def test_no_violations_raw_key_in_compute_trend(self):
        """_compute_trend should handle missing violations_raw key gracefully."""
        trend = _compute_trend(
            {"summary": {"total_violations": 5}},
            {"summary": {"total_violations": 3}},
        )
        assert trend["direction"] == "up"
        assert trend["delta"] == 2
        assert trend["required_delta"] == 0

    def test_compute_trend_same_with_empty_violations(self):
        """_compute_trend with empty violations_raw on both sides."""
        trend = _compute_trend(
            {"summary": {"total_violations": 5}, "violations_raw": []},
            {"summary": {"total_violations": 5}, "violations_raw": []},
        )
        assert trend["direction"] == "same"
        assert trend["delta"] == 0
        assert trend["required_delta"] == 0


class TestGenerateFixRecommendations:
    def test_no_p1_p2(self):
        recs = _generate_fix_recommendations([], {"direction": "same"}, 0)
        assert any("No actionable" in r for r in recs)

    def test_with_p1_violations(self):
        classified = [{"priority": 1, "count": 5, "rule_id": "R1.1",
                        "needs_deviation": True}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 5)
        assert any("PRIORITY 1" in r for r in recs)

    def test_with_p2_violations(self):
        classified = [{"priority": 2, "count": 3, "rule_id": "A1.1",
                        "needs_deviation": False}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 3)
        assert any("PRIORITY 2" in r for r in recs)

    def test_increasing_trend_detected(self):
        recs = _generate_fix_recommendations([], {"direction": "up", "delta": 5}, 5)
        assert any("increased" in r for r in recs)

    def test_decreasing_trend_detected(self):
        recs = _generate_fix_recommendations([], {"direction": "down", "delta": -3}, 2)
        assert any("decreased" in r for r in recs)

    def test_deviation_needed(self):
        classified = [{"priority": 1, "count": 2, "rule_id": "R2.1",
                        "needs_deviation": True}]
        recs = _generate_fix_recommendations(classified, {"direction": "same"}, 2)
        assert any("Deviation" in r for r in recs)


class TestCheckForRegressionViolations:
    def test_few_entries(self):
        result = _check_for_regression_violations({"summary": {"total_violations": 5}}, [])
        assert result == []

    def test_one_entry(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 5}},
            [{"total_violations": 3}]
        )
        assert result == []

    def test_regression_found(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 10}},
            [{"total_violations": 10}, {"total_violations": 5}]
        )
        assert len(result) >= 1
        assert result[0]["type"] == "regression"
        assert result[0]["delta"] == 5

    def test_improvement_found(self):
        result = _check_for_regression_violations(
            {"summary": {"total_violations": 3}},
            [{"total_violations": 3}, {"total_violations": 10}]
        )
        assert len(result) >= 1
        assert result[0]["type"] == "improvement"


class TestStepReviewMisraCi:
    def test_no_report_skips(self):
        session = MagicMock()
        session.name = "test"
        session.session_dir = Path("/tmp")
        with patch("yuleosh.pipeline.step_handlers.review_misra_ci.Path") as mock_path:
            mock_path.return_value = Path("/nonexistent")
            result = step_review_misra_ci(session)
            assert result is not None

    def test_skip_no_misra_data(self):
        session = MagicMock()
        session.name = "test"
        session.session_dir = Path("/tmp")
        with patch.dict("os.environ", {}, clear=True):
            result = step_review_misra_ci(session)
            assert result is not None


class TestStepReviewMisraCiWithReport:
    """Integration test: step_review_misra_ci with a real report file."""

    def test_with_valid_report(self):
        with tempfile.TemporaryDirectory() as td:
            # Setup minimal project structure
            report_dir = Path(td) / _DEFAULT_REPORT_DIR
            report_dir.mkdir(parents=True, exist_ok=True)

            # Write a valid MISRA report
            report_data = {
                "summary": {
                    "total_violations": 42,
                    "total_rules_violated": 10,
                    "unique_files": ["main.c", "foo.c"],
                    "severity_counts": {"Required": 12, "Advisory": 30},
                },
                "groups": {
                    "R1.1": {
                        "severity_category": "Required",
                        "count": 8,
                        "title": "Test rule",
                        "files": ["main.c"],
                    },
                    "A1.1": {
                        "severity_category": "Advisory",
                        "count": 30,
                        "title": "Advisory rule",
                        "files": ["foo.c"],
                    },
                },
                "violations_raw": [
                    {"severity": "error", "rule": "R1.1"},
                    {"severity": "warning", "rule": "A1.1"},
                ],
            }
            (report_dir / "misra-report.json").write_text(json.dumps(report_data))

            session = MagicMock()
            session.name = "test-session"
            session_dir = Path(td) / ".yuleosh" / "sessions" / "test-session"
            session_dir.mkdir(parents=True, exist_ok=True)
            session.session_dir = session_dir

            with patch.dict("os.environ", {"OSH_HOME": td}, clear=True):
                result = step_review_misra_ci(session)
                assert result is not None
                # Verify the output file was written
                out_path = session_dir / "misra-review.json"
                assert out_path.exists()
                review = json.loads(out_path.read_text())
                assert review["status"] == "failed"  # Has required violations
                assert review["summary"]["total_violations"] == 42
                assert len(review["violations_by_priority"]["p1_required"]) == 1
                assert len(review["violations_by_priority"]["p2_advisory"]) == 1


class TestCheckReportStaleness:
    """2026-08-17 (window-anti-pinch r20p): misra-review 读陈旧报告假绿根因。

    pipeline 的 misra-review 步骤读 .yuleosh/reports/misra-report.json（CI 生成）。
    若代码已更新（r20n 回绕修复 2b431b9）但报告未重新生成 → 报告 0 违规 = 假绿放行。
    回归测试：陈旧报告必须降级为 warning，绝不 passed。
    """

    def _write_report(self, tmp_path: Path, total_violations: int = 0) -> Path:
        report_dir = tmp_path / _DEFAULT_REPORT_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "summary": {"total_violations": total_violations},
            "groups": {},
        }
        report = report_dir / "misra-report.json"
        report.write_text(json.dumps(data))
        return report

    def _run_step(self, tmp_path: Path) -> dict:
        session = MagicMock()
        session.name = "test-session"
        session_dir = tmp_path / ".yuleosh" / "sessions" / "test-session"
        session_dir.mkdir(parents=True, exist_ok=True)
        session.session_dir = session_dir
        with patch.dict("os.environ", {"OSH_HOME": str(tmp_path)}, clear=True):
            step_review_misra_ci(session)
        return json.loads((session_dir / "misra-review.json").read_text())

    def test_stale_when_report_older_than_src(self, tmp_path):
        """报告 0 违规 + src/ 代码更新（比报告新）→ status=warning + stale 标记。"""
        report = self._write_report(tmp_path)
        old = time.time() - 3600
        os.utime(report, (old, old))
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.c").write_text("int main(void){return 0;}")  # mtime=now

        review = self._run_step(tmp_path)
        assert review["status"] == "warning", review["status"]
        assert review.get("stale_report"), "陈旧报告必须带 stale_report 证据"

    def test_fresh_report_stays_passed(self, tmp_path):
        """报告 0 违规且 src/ 比报告旧 → status=passed（正常路径不受影响）。"""
        report = self._write_report(tmp_path)  # mtime=now
        src = tmp_path / "src"
        src.mkdir()
        f = src / "main.c"
        f.write_text("int main(void){return 0;}")
        os.utime(f, (time.time() - 7200, time.time() - 7200))

        review = self._run_step(tmp_path)
        assert review["status"] == "passed", review["status"]
        assert "stale_report" not in review

    def test_stale_report_with_required_violations_stays_failed(self, tmp_path):
        """陈旧报告 + required 违规 → 仍 failed（不因陈旧掩盖真实违规）。"""
        report = self._write_report(tmp_path, total_violations=5)
        old = time.time() - 3600
        os.utime(report, (old, old))
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.c").write_text("int main(void){return 0;}")

        # 直接改 groups 造 required 违规
        data = {
            "summary": {"total_violations": 5},
            "groups": {
                "R1.1": {
                    "severity_category": "Required",
                    "count": 5,
                    "title": "Test rule",
                    "files": ["main.c"],
                }
            },
        }
        (tmp_path / _DEFAULT_REPORT_DIR / "misra-report.json").write_text(json.dumps(data))
        os.utime(tmp_path / _DEFAULT_REPORT_DIR / "misra-report.json", (old, old))

        review = self._run_step(tmp_path)
        assert review["status"] == "failed", review["status"]

    def test_no_src_no_git_cannot_judge(self, tmp_path):
        """无 src/ 且非 git 仓库 → 无法判断新鲜度 → 不误报（None）。"""
        report = self._write_report(tmp_path)
        assert _check_report_staleness(tmp_path, report) is None

    def test_doc_only_commit_does_not_make_report_stale(self, tmp_path):
        """最新提交只含文档（TASK_STATUS.md）→ 不误判 stale。

        Regression: r22 实测 misra-review 因 TASK_STATUS.md 提交（12:41）
        早于报告（11:20）误判 stale warning，pipeline YELLOW。旧实现用
        git 最新提交时间（含文档提交）当代码变更；新实现只比较
        src/tests 的 .c/.h mtime。
        """
        report = self._write_report(tmp_path)  # mtime=now
        # 文档提交（晚于报告）——旧实现会因此判 stale
        import subprocess
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"],
                       check=True, capture_output=True)
        (tmp_path / "TASK_STATUS.md").write_text("# status\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "docs"],
                       check=True, capture_output=True)
        # src/ 无 C 文件变更 → 不 stale
        assert _check_report_staleness(tmp_path, report) is None
