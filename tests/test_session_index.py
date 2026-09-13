"""session_index.discover_project_sessions 单元测试。

验证：
* 递归发现 OSH_HOME 下所有 .osh/sessions/*/session.json（含子目录）
* UI 触发跑（落在 project_dir 子目录）也能被扫到
* 同一项目多份会话按 updated_at 取最新（latest-wins）
* active 标志 = 任一会话处于非终态（created/running/queued…，completed/failed 之外）；
  编排器运行中只把 session.status 保持 "created"，故 created 必须判为活跃
* project_dir 正确反推（优先 session 自带，否则按路径）
"""

import json
import tempfile
from pathlib import Path

from yuleosh.pipeline.session_index import discover_project_sessions


def _write_session(project_dir: Path, run_id: str, status: str,
                   updated_at: str, spec_path: str = None, project_dir_field=None):
    sess_dir = project_dir / ".osh" / "sessions" / run_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": run_id,
        "name": f"run-{run_id}",
        "status": status,
        "current_step": 3,
        "updated_at": updated_at,
        "steps": [],
    }
    if spec_path is not None:
        data["spec_path"] = spec_path
    if project_dir_field is not None:
        data["project_dir"] = project_dir_field
    (sess_dir / "session.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def test_recursive_discovery_finds_subdir_and_top_level():
    root = Path(tempfile.mkdtemp())
    # 后台(CLI) 跑：落在 OSH_HOME 顶层
    cli_proj = root / "cli-top"
    _write_session(cli_proj, "cli001", "completed", "2026-09-13T10:00:00")
    # UI 触发跑：落在 OSH_HOME 子目录 templates/mcu-firmware
    ui_proj = root / "templates" / "mcu-firmware"
    spec = ui_proj / "docs" / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("# spec")
    _write_session(ui_proj, "ui001", "completed", "2026-09-13T11:00:00",
                   spec_path=str(spec))

    idx = discover_project_sessions(root)
    flat_ids = {s["run_id"] for s in idx["sessions"]}
    assert flat_ids == {"cli001", "ui001"}, flat_ids
    proj_dirs = {p["project_dir"] for p in idx["projects"]}
    assert str(cli_proj.resolve()) in proj_dirs
    assert str(ui_proj.resolve()) in proj_dirs


def test_latest_wins_and_active_flag():
    root = Path(tempfile.mkdtemp())
    proj = root / "proj"
    # 旧会话：completed
    _write_session(proj, "old", "completed", "2026-09-13T09:00:00")
    # 新会话：running（最新）
    _write_session(proj, "new", "running", "2026-09-13T12:00:00")

    idx = discover_project_sessions(root)
    assert idx["project_count"] == 1
    p = idx["projects"][0]
    assert p["latest_run_id"] == "new", p
    assert p["latest_status"] == "running"
    assert p["active"] is True
    assert p["runs_count"] == 2
    assert "running" in p["statuses"]


def test_project_dir_derived_from_path_when_missing():
    root = Path(tempfile.mkdtemp())
    proj = root / "deep" / "nested" / "myproj"
    _write_session(proj, "x1", "completed", "2026-09-13T08:00:00")  # 无 project_dir 字段
    idx = discover_project_sessions(root)
    p = idx["projects"][0]
    assert p["project_dir"] == str(proj.resolve()), p["project_dir"]
    assert p["project_name"] == "myproj"


def test_project_dir_field_overrides_path():
    root = Path(tempfile.mkdtemp())
    proj = root / "actual"
    # session 物理上在 wrong 目录，但自带正确的 project_dir 字段
    wrong = root / "wrong"
    _write_session(wrong, "x2", "completed", "2026-09-13T08:00:00",
                   project_dir_field=str(proj.resolve()))
    idx = discover_project_sessions(root)
    p = idx["projects"][0]
    assert p["project_dir"] == str(proj.resolve())


def test_created_status_counts_as_active():
    """编排器运行中 session.status 恒为 'created'（收尾才翻 completed/failed）。

    回归：active 判定必须覆盖 created，否则运行中项目在 dashboard 上不会
    亮起「后台运行中」。
    """
    root = Path(tempfile.mkdtemp())
    proj = root / "proj"
    # 一份正在跑的会话（编排器中途的实际状态）
    _write_session(proj, "mid", "created", "2026-09-13T12:00:00",
                   spec_path=str(proj / "docs" / "spec.md"))
    (proj / "docs").mkdir(parents=True, exist_ok=True)
    (proj / "docs" / "spec.md").write_text("# s")
    idx = discover_project_sessions(root)
    p = idx["projects"][0]
    assert p["latest_status"] == "created"
    assert p["active"] is True, "created 状态必须判为活跃"
    assert "created" in p["statuses"]


def test_completed_and_failed_are_not_active():
    root = Path(tempfile.mkdtemp())
    proj = root / "proj"
    _write_session(proj, "c", "completed", "2026-09-13T12:00:00")
    _write_session(proj, "f", "failed", "2026-09-13T11:00:00")
    idx = discover_project_sessions(root)
    p = idx["projects"][0]
    assert p["active"] is False, "completed/failed 必须判为非活跃"


def test_dedup_by_run_id():
    root = Path(tempfile.mkdtemp())
    proj = root / "p"
    # 同一 run_id 出现在两个位置（理论上不应发生，但需去重）
    _write_session(proj, "dup", "completed", "2026-09-13T08:00:00")
    other = root / "other" / "p"
    _write_session(other, "dup", "completed", "2026-09-13T08:00:00")
    idx = discover_project_sessions(root)
    flat_ids = [s["run_id"] for s in idx["sessions"]]
    assert flat_ids.count("dup") == 1, flat_ids
