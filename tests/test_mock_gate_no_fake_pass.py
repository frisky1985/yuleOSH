"""假绿修复测试：mock 模式门禁不再伪装通过。

对应 sprint-contract-fake-green-hardening T9：
- c_coverage_gate / merge_gate 在 mock 模式产出报告必须 passed=False + skipped=True，
  下游不得把 mock 产物当"门禁通过"证据。
"""

# @tests src/yuleosh/ci/honesty_gate.py
import json
import pathlib
from unittest.mock import MagicMock

from yuleosh.knowledge_graph.merge_gate import step_merge_gate
from yuleosh.pipeline.step_handlers.c_coverage_gate import coverage_gate_step


class TestMockGateNoFakePass:
    def test_merge_gate_mock_report_not_passed(self, tmp_path):
        """T9: merge_gate mock 报告 passed=False + verdict=skipped。"""
        session_dir = pathlib.Path(tmp_path) / "session"
        session_dir.mkdir(parents=True)
        session = MagicMock()
        session.mock_mode = True
        session.name = "test-mock"
        session.session_dir = str(session_dir)
        out = step_merge_gate(session)
        report = json.loads(pathlib.Path(out).read_text())
        assert report["passed"] is False
        assert report["verdict"] == "skipped"
        assert report["skipped"] is True

    def test_c_coverage_gate_mock_report_not_passed(self, tmp_path):
        """T9: c_coverage_gate mock 报告 gate_passed=False。"""
        proj = pathlib.Path(tmp_path) / "proj"
        session_dir = proj / ".yuleosh" / "session"
        session_dir.mkdir(parents=True)
        session = MagicMock()
        session.mock_mode = True
        session.name = "test-mock"
        session.session_dir = session_dir
        out = coverage_gate_step(session)
        report = json.loads(pathlib.Path(out).read_text())
        assert report["gate_passed"] is False
        assert report["skipped"] is True

    def test_merge_gate_mock_report_still_written(self, tmp_path):
        """回归: mock 报告仍写入（pipeline 靠返回路径继续）。"""
        session_dir = pathlib.Path(tmp_path) / "session"
        session_dir.mkdir(parents=True)
        session = MagicMock()
        session.mock_mode = True
        session.name = "test-mock"
        session.session_dir = str(session_dir)
        out = step_merge_gate(session)
        assert out.endswith("merge-gate-report.json")
        assert pathlib.Path(out).is_file()
