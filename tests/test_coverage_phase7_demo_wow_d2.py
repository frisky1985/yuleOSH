"""Phase 7 coverage — D2 域: run_wow_demo / main（demo_wow.py L470-686）。

目标（零 src/ 改动）:
  - run_wow_demo: 完整 demo 流水线 —— 项目创建（真实落盘 tmp_path）、
    mock 流水线会话（run_demo_pipeline_steps 打桩）、证据收集
    （EvidenceCollector / pack_compliance_zip 打桩）、环境变量
    OSH_HOME / LLM_API_KEY 的保存-恢复与 pop 双分支、session
    failed 提前返回、brake-light / wiper-control 双模板分支、
    evidence ZIP 存在/缺失双分支、时间用固定时钟。
  - main: 未知 example 报错分支 + 有效 example 转发 run_wow_demo
    （含默认参数与 do_build 透传）。

红线遵守: 零 src/ 改动、零真实 subprocess / 网络 / 时间依赖（time.time
固定时钟、所有外部调用打桩）；文件系统仅用 pytest tmp_path 真实落盘。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

import os
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import pytest

from yuleosh.api.demo_wow import main, run_wow_demo

# ---------------------------------------------------------------------------
# 共享 fixture / 工具
# ---------------------------------------------------------------------------


class _FrozenDateTime(datetime):
    """datetime 替身: now() 返回固定值，spec 时间戳确定性。"""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 10, 12, 0, 0)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch):
    """冻结模块内 datetime.now()，避免 spec 时间戳抖动。"""
    monkeypatch.setattr("yuleosh.api.demo_wow.datetime", _FrozenDateTime)


BRAKE_REQ_IDS = [
    "REQ-BRK-001",
    "REQ-BRK-002",
    "REQ-BRK-003",
    "REQ-BRK-004",
    "REQ-BRK-005",
]
WIPER_REQ_IDS = [
    "REQ-WPR-001",
    "REQ-WPR-002",
    "REQ-WPR-003",
    "REQ-WPR-004",
    "REQ-WPR-005",
]


def _make_project_skeleton(tmp_path, example):
    """在 tmp_path 下预建 demo 项目骨架（docs/.osh 等），供 mock 返回。"""
    project = (tmp_path / f"demo-{example}").resolve()
    (project / "docs").mkdir(parents=True, exist_ok=True)
    (project / ".osh" / "evidence").mkdir(parents=True, exist_ok=True)
    return project


@contextmanager
def _demo_mocks(
    tmp_path, example="brake-light", session_status="ok", session_errors=(), zip_exists=True
):
    """run_wow_demo 外部依赖 mock 栈（无 subprocess / 网络 / 真实时钟）。

    - create_demo_project -> mock 返回真实落盘的骨架目录（create_demo_project
      本体属 D1 域且 src L246 有真实 bug: {example.lower()} 无法 format，见汇报）
    - run_demo_pipeline_steps -> 固定 session（ok / failed 两态）
    - EvidenceCollector -> MagicMock（requirements/scenarios 可赋值）
    - pack_compliance_zip -> 返回可控 ZIP 路径（存在 / 缺失）
    - time.time -> 固定时钟 [100.0, 123.4]，elapsed == 23.4
    """
    session = SimpleNamespace(
        status=session_status,
        errors=list(session_errors),
        steps=[{"step": "spec"}, {"step": "analysis"}],
    )
    project = _make_project_skeleton(tmp_path, example)
    zip_path = tmp_path / "evidence.zip"
    if zip_exists:
        zip_path.write_bytes(b"PK\x03\x04fake-zip")
    clock = iter([100.0, 123.4])

    with (
        mock.patch(
            "yuleosh.api.demo_wow.create_demo_project", return_value=project
        ) as m_create,
        mock.patch(
            "yuleosh.api.demo_quick.run_demo_pipeline_steps", return_value=session
        ) as m_run,
        mock.patch("yuleosh.evidence.generator.EvidenceCollector") as m_collector,
        mock.patch(
            "yuleosh.evidence.compliance.pack_compliance_zip",
            return_value=str(zip_path),
        ) as m_pack,
        mock.patch("time.time", side_effect=lambda: next(clock)),
    ):
        yield SimpleNamespace(
            session=session,
            project=project,
            zip_path=zip_path,
            create=m_create,
            run=m_run,
            collector_cls=m_collector,
            pack=m_pack,
        )


# ---------------------------------------------------------------------------
# run_wow_demo
# ---------------------------------------------------------------------------


def test_run_wow_demo_brake_light_completed(tmp_path, monkeypatch):
    """brake-light 全流程: 成功会话、brake 需求/场景分支、ZIP 存在、env 恢复。"""
    monkeypatch.setenv("LLM_API_KEY", "sk-real-key")
    monkeypatch.setenv("OSH_HOME", "/some/osh/home")

    with _demo_mocks(tmp_path, example="brake-light") as m:
        result = run_wow_demo("brake-light", str(tmp_path), do_build=False)

    project_dir = m.project
    spec_path = project_dir / "docs" / "spec.md"

    assert result["status"] == "completed"
    assert result["project_dir"] == str(project_dir)
    assert result["spec_path"] == str(spec_path)
    assert result["evidence_dir"] == str(project_dir / ".osh" / "evidence")
    assert result["evidence_zip"] == str(m.zip_path)
    assert result["zip_size_bytes"] == 12
    assert result["elapsed_seconds"] == 23.4
    assert len(result["artifacts"]) == 6

    # 项目创建: 以 example + work_dir 调用，返回骨架目录
    m.create.assert_called_once_with("brake-light", str(tmp_path))
    assert spec_path.is_file()  # L503 真实重写 spec.md

    # 流水线会话: 以 spec 路径 + 项目目录调用
    m.run.assert_called_once_with(str(spec_path), project_dir)

    # 证据收集: requirements / scenarios 赋值 + 收集与生成方法逐一调用
    collector = m.collector_cls.return_value
    m.collector_cls.assert_called_once_with(str(project_dir))
    assert [r["req_id"] for r in collector.requirements] == BRAKE_REQ_IDS
    assert collector.scenarios[0]["name"] == "Normal brake light activation"
    assert collector.scenarios[1]["then"] == ["Brake light stays in current state"]
    collector._collect_test_coverage.assert_called_once()
    collector.collect_reviews.assert_called_once()
    collector.collect_ci_results.assert_called_once()
    collector.collect_sil_reports.assert_called_once()
    for meth in (
        "generate_traceability_matrix",
        "generate_requirement_coverage",
        "generate_code_coverage_report",
        "generate_acceptance_matrix",
        "aggregate_review_logs",
    ):
        getattr(collector, meth).assert_called_once()
    m.pack.assert_called_once_with(collector)

    # LLM_API_KEY 恢复到调用前值；OSH_HOME 恢复到调用前值（修复 2026-08-11:
    # 证据步骤曾无条件重设 OSH_HOME 且不清理 → 泄漏为项目目录，现返回前恢复）
    assert os.environ["LLM_API_KEY"] == "sk-real-key"
    assert os.environ["OSH_HOME"] == "/some/osh/home"


def test_run_wow_demo_wiper_control_zip_missing(tmp_path, monkeypatch):
    """wiper-control 全流程: wiper 需求/场景分支、ZIP 缺失（size 0）、env pop。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OSH_HOME", raising=False)

    with _demo_mocks(tmp_path, example="wiper-control", zip_exists=False) as m:
        result = run_wow_demo("wiper-control", str(tmp_path), do_build=True)

    project_dir = m.project

    assert result["status"] == "completed"
    assert result["project_dir"] == str(project_dir)
    assert result["zip_size_bytes"] == 0
    assert result["elapsed_seconds"] == 23.4

    m.create.assert_called_once_with("wiper-control", str(tmp_path))
    collector = m.collector_cls.return_value
    assert [r["req_id"] for r in collector.requirements] == WIPER_REQ_IDS
    assert collector.scenarios[0]["name"] == "Intermittent wipe"
    assert collector.scenarios[2]["then"] == [
        "Stall detected within 200 ms",
        "Power cut to prevent damage",
    ]

    # LLM_API_KEY 走 pop 分支（调用后仍不存在）；OSH_HOME 走 pop 分支
    # （修复 2026-08-11: 证据步骤泄漏已修复，调用后恢复为不存在）
    assert "LLM_API_KEY" not in os.environ
    assert "OSH_HOME" not in os.environ


def test_run_wow_demo_failed_session(tmp_path, monkeypatch):
    """会话 failed: 提前返回错误 dict，不进入证据收集，env 走 pop 分支。"""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OSH_HOME", raising=False)

    with _demo_mocks(
        tmp_path, example="brake-light", session_status="failed", session_errors=["mock: spec missing"]
    ) as m:
        result = run_wow_demo("brake-light", str(tmp_path))

    project_dir = m.project

    assert result["status"] == "failed"
    assert result["project_dir"] == str(project_dir)
    assert result["errors"] == ["mock: spec missing"]
    assert result["elapsed_seconds"] == 23.4
    assert "evidence_zip" not in result
    assert "artifacts" not in result

    # 失败路径不触达证据收集
    m.collector_cls.assert_not_called()
    m.pack.assert_not_called()

    assert "LLM_API_KEY" not in os.environ
    assert "OSH_HOME" not in os.environ


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_unknown_example(capsys):
    """未知 example: 打印可用列表并返回 error dict。"""
    result = main("flying-car")

    assert result == {"status": "error", "message": "Unknown example: flying-car"}
    out = capsys.readouterr().out
    assert "Unknown example 'flying-car'" in out
    assert "brake-light, wiper-control" in out


def test_main_valid_example_forwards_to_run_wow_demo():
    """有效 example: 参数原样转发（含 do_build=True），返回其结果。"""
    with mock.patch(
        "yuleosh.api.demo_wow.run_wow_demo", return_value={"status": "completed"}
    ) as m_run:
        result = main("wiper-control", "/tmp/somewhere", do_build=True)

    m_run.assert_called_once_with("wiper-control", "/tmp/somewhere", do_build=True)
    assert result == {"status": "completed"}


def test_main_defaults_to_brake_light():
    """默认参数: example=brake-light、work_dir=.、do_build=False。"""
    with mock.patch("yuleosh.api.demo_wow.run_wow_demo", return_value={}) as m_run:
        result = main()

    m_run.assert_called_once_with("brake-light", ".", do_build=False)
    assert result == {}
