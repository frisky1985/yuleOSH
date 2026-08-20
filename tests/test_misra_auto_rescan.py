"""Tests for MISRA review auto-rescan (self-healing stale report).

2026-08-20 (window-anti-pinch r22p7): pipeline 的 development/codegen-deploy
步骤必然在 misra-review 之前改代码 → 任何先前生成的 MISRA 报告必然 stale。
修复：misra-review 检测到 stale 时自动重扫 (mode=full)，重扫成功且报告新鲜
则继续正常判定（自愈），重扫失败则保持 warning（fail-safe）。
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.step_handlers.review_misra_ci import (
    _check_report_staleness,
    _latest_src_change_time,
    step_review_misra_ci,
)


def _write_report(project_dir: Path, total: int = 0, generated_at: str = "") -> Path:
    report_path = project_dir / ".yuleosh/reports/misra-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "generated_at": generated_at or "2026-08-20T00:00:00",
        "total_violations": total,
        "summary": {"total_violations": total},
        "groups": {},
        "violations_raw": [],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False))
    return report_path


def _touch_src(project_dir: Path, name: str = "main.c") -> Path:
    src = project_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    f = src / name
    f.write_text("int main(void) { return 0; }\n")
    return f


def _make_session(project_dir: Path):
    session = mock.MagicMock()
    session.name = "test-run"
    session.session_dir = project_dir / ".osh/sessions/test-run"
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


class TestStalenessDetection:
    def test_fresh_report_no_staleness(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            src = _touch_src(proj)
            report = _write_report(proj)
            # 报告比代码新
            os.utime(report, (src.stat().st_mtime + 10, src.stat().st_mtime + 10))
            assert _check_report_staleness(proj, report) is None

    def test_stale_report_detected(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            src = _touch_src(proj)
            report = _write_report(proj)
            # 报告比代码旧
            os.utime(report, (src.stat().st_mtime - 10, src.stat().st_mtime - 10))
            staleness = _check_report_staleness(proj, report)
            assert staleness is not None
            assert "早于最新代码变更" in staleness

    def test_no_src_no_staleness(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            report = _write_report(proj)
            assert _latest_src_change_time(proj) is None
            assert _check_report_staleness(proj, report) is None


class TestAutoRescanSelfHealing:
    """核心：stale → 自动重扫 → 报告新鲜 → passed（不再 YELLOW）。"""

    @pytest.fixture
    def project(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            # 生成一个"旧"报告（generated_at 过去 + mtime 强制提前，保证 stale 触发）
            _write_report(proj, total=0, generated_at="2026-08-19T10:00:00")
            # 代码变更晚于报告
            src = _touch_src(proj)
            report_path = proj / ".yuleosh/reports/misra-report.json"
            # 报告 mtime 早于 src 10s → _check_report_staleness 必然命中
            os.utime(report_path, (src.stat().st_mtime - 10, src.stat().st_mtime - 10))
            yield proj

    def _make_fresh_report_side_effect(self, project_dir):
        """模拟 run_misra_check 成功重扫：写一个新报告（比代码新）。"""

        def _effect(*args, **kwargs):
            _write_report(project_dir, total=0, generated_at="2026-08-20T23:00:00")
            return True

        return _effect

    def test_stale_auto_rescan_passes(self, project, monkeypatch):
        """stale 报告 → 自动重扫成功 → 报告新鲜 → verdict passed。"""
        # handler 内部 `from yuleosh.ci.stages.review_misra import run_misra_check`
        # 每次执行重新取源模块 → patch 源模块即可生效
        import yuleosh.ci.stages.review_misra as ci_mod

        monkeypatch.setattr(
            ci_mod,
            "run_misra_check",
            self._make_fresh_report_side_effect(project),
        )
        # session + 环境
        session = _make_session(project)
        monkeypatch.setenv("OSH_HOME", str(project))

        out = step_review_misra_ci(session)
        with open(out) as f:
            review = json.load(f)
        assert review["status"] == "passed", json.dumps(review, ensure_ascii=False)
        assert "stale_report" not in review
        # 自愈后仍输出 auto-rescan 痕迹（recommendations 不含"需重跑 CI"）
        assert not any("重新生成 MISRA 报告" in r for r in review["recommendations"])

    def test_stale_rescan_failure_keeps_warning(self, project, monkeypatch):
        """重扫失败 → 保持 warning（fail-safe）。"""
        import yuleosh.ci.stages.review_misra as ci_mod

        def _fail(*args, **kwargs):
            return False

        monkeypatch.setattr(ci_mod, "run_misra_check", _fail)
        session = _make_session(project)
        monkeypatch.setenv("OSH_HOME", str(project))

        out = step_review_misra_ci(session)
        with open(out) as f:
            review = json.load(f)
        assert review["status"] == "warning"
        assert "stale_report" in review

    def test_stale_rescan_exception_keeps_warning(self, project, monkeypatch):
        """重扫抛异常 → 保持 warning（fail-safe）。"""
        import yuleosh.ci.stages.review_misra as ci_mod

        def _boom(*args, **kwargs):
            raise RuntimeError("cppcheck not found")

        monkeypatch.setattr(ci_mod, "run_misra_check", _boom)
        session = _make_session(project)
        monkeypatch.setenv("OSH_HOME", str(project))

        out = step_review_misra_ci(session)
        with open(out) as f:
            review = json.load(f)
        assert review["status"] == "warning"
        assert "stale_report" in review

    def test_rescan_writes_actual_report(self, project, monkeypatch):
        """真实重扫（不 mock run_misra_check 本体，但隔离 subprocess）— 验证
        run_misra_check 能在 project 上跑完并产出报告。若无 cppcheck 则 skip。"""
        import shutil

        if shutil.which("cppcheck") is None:
            pytest.skip("cppcheck not installed")
        import yuleosh.pipeline.step_handlers.review_misra_ci as mod

        session = _make_session(project)
        monkeypatch.setenv("OSH_HOME", str(project))
        # 用真实 run_misra_check
        from yuleosh.ci.stages.review_misra import run_misra_check
        from yuleosh.ci.result import CIResult

        ci = CIResult(1, "HEAD")
        ok = run_misra_check(str(project), ci, mode="full")
        assert ok is True or ok is False  # 不因扫描结果阻断而失败
        report_path = project / ".yuleosh/reports/misra-report.json"
        assert report_path.exists()
        assert _check_report_staleness(project, report_path) is None
