"""O4 — yuleOSH orchestrator.status_pipeline (L483-512) 与 main (L622-650) 全分支测试。

覆盖目标（src/yuleosh/pipeline/orchestrator.py，零 src/ 改动）:
  - status_pipeline:
      * name 给定 + 会话目录存在 → 打印该会话
      * name 给定 + 会话目录不存在 → "No pipeline sessions found."
      * name 为空 → 枚举 OSH_HOME/.osh/sessions 下所有子目录
      * sessions 为空 → "No pipeline sessions found." 并返回
      * session.json 存在 → 解析并按状态打印图标 ✅/🔄/❌/📋/❓
      * session.json 缺失 → 静默跳过
      * 非目录条目（普通文件）被 is_dir() 过滤
      * steps_done / steps_total 统计（status == "completed" 计数）
  - main（CLI 入口）:
      * 无参数 → usage + sys.exit(1)
      * status 无 / 有 name → status_pipeline(None / name)
      * --profile <name> <spec> → run_pipeline(profile=...) + exit 0/1
      * 普通 spec → run_pipeline(cmd) + exit 0/1
      * KeyboardInterrupt → sys.exit(130)
      * 未处理异常 → sys.exit(1)

红线遵守: 零 src/ 改动、零网络 / 子进程 / 时间依赖 —— status_pipeline 用
真实临时目录 + 手写 session.json 驱动；main 的 sys.argv 与下游调用全部
mock.patch 注入。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

import json
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from yuleosh.pipeline import orchestrator as orch

# ---------------------------------------------------------------------------
# 工具：构造 OSH_HOME/.osh/sessions 目录结构
# ---------------------------------------------------------------------------


@pytest.fixture
def osh_home(tmp_path, monkeypatch):
    """隔离 OSH_HOME 并预建 sessions 根目录。"""
    sessions = tmp_path / ".osh" / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return sessions


def _write_session(sessions, name, status, steps=None):
    """写入一个 session.json，steps 为 status 列表，缺省时按会话状态推一个。"""
    sdir = sessions / name
    sdir.mkdir(parents=True, exist_ok=True)
    if steps is None:
        steps = [status]
    data = {
        # Phase 9: 目录名 = run_id，显示名走 session.json['name']
        "name": name,
        "status": status,
        "steps": [{"status": s, "name": f"step-{i}"} for i, s in enumerate(steps)],
    }
    (sdir / "session.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    return sdir


# ---------------------------------------------------------------------------
# status_pipeline: name 给定分支（L492-495）
# ---------------------------------------------------------------------------


def test_status_named_session_exists(osh_home, capsys):
    """name 给定且目录存在 → 只打印该会话（L494-495）。"""
    _write_session(osh_home, "run-a", "completed", ["completed", "pending"])
    # 再放一个无关会话，确认不会被打印
    _write_session(osh_home, "run-b", "failed", ["failed"])

    orch.status_pipeline("run-a")

    out = capsys.readouterr().out
    assert "✅ run-a: [1/2] completed" in out
    assert "run-b" not in out


def test_status_named_session_missing(osh_home, capsys):
    """name 给定但目录不存在 → sessions 为空 → 提示无会话（L494 False + L499）。"""
    orch.status_pipeline("ghost")

    out = capsys.readouterr().out
    assert "No pipeline sessions found." in out


def test_status_named_falsy_name_lists_all(osh_home, capsys):
    """name 为 falsy（空串）→ 走 else 分支枚举目录（L496-497）。"""
    _write_session(osh_home, "run-x", "created", ["created"])
    orch.status_pipeline("")
    assert "📋 run-x: [0/1] created" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# status_pipeline: name 为空分支（L496-497）
# ---------------------------------------------------------------------------


def test_status_no_sessions_found(osh_home, capsys):
    """sessions 根目录存在但为空 → 提示无会话（L499-501）。"""
    orch.status_pipeline()
    assert "No pipeline sessions found." in capsys.readouterr().out


def test_status_sorts_session_dirs(osh_home, capsys):
    """无 name → 目录名排序后逐个打印（L497 + L503）。"""
    _write_session(osh_home, "b-session", "running", ["running"])
    _write_session(osh_home, "a-session", "completed", ["completed"])
    orch.status_pipeline()

    out = capsys.readouterr().out
    assert out.index("a-session") < out.index("b-session")


def test_status_skips_non_dir_entries(osh_home, capsys):
    """根目录里的普通文件被 is_dir() 过滤（L497）。"""
    (osh_home / "not-a-dir.txt").write_text("junk", encoding="utf-8")
    _write_session(osh_home, "run-z", "failed", ["failed"])
    orch.status_pipeline()
    out = capsys.readouterr().out
    assert "not-a-dir" not in out
    assert "❌ run-z" in out


def test_status_skips_missing_session_json(osh_home, capsys):
    """目录存在但无 session.json → 静默跳过（L505 False 分支）。"""
    (osh_home / "empty-dir").mkdir()
    _write_session(osh_home, "run-y", "completed", ["completed"])
    orch.status_pipeline()
    out = capsys.readouterr().out
    assert "empty-dir" not in out
    assert "run-y" in out


# ---------------------------------------------------------------------------
# status_pipeline: 状态图标映射 + 步骤统计（L508-512）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "icon"),
    [
        ("completed", "✅"),
        ("running", "🔄"),
        ("failed", "❌"),
        ("created", "📋"),
        ("weird", "❓"),
    ],
)
def test_status_icon_mapping(osh_home, capsys, status, icon):
    """五种状态 → 图标映射（L508-509 含 get 默认值 ❓）。"""
    _write_session(osh_home, f"s-{status}", status, [status, "pending"])
    orch.status_pipeline(f"s-{status}")
    out = capsys.readouterr().out
    # 仅 completed 计入 steps_done（L510）
    done = 1 if status == "completed" else 0
    assert f"{icon} s-{status}: [{done}/2] {status}" in out


def test_status_step_counts_all_completed(osh_home, capsys):
    """所有步骤 completed → 计数 [3/3]（L510-511）。"""
    _write_session(
        osh_home, "full", "completed", ["completed", "completed", "completed"]
    )
    orch.status_pipeline("full")
    assert "✅ full: [3/3] completed" in capsys.readouterr().out


def test_status_step_counts_none_completed(osh_home, capsys):
    """无步骤 completed → 计数 [0/2]（L510 sum 为 0）。"""
    _write_session(osh_home, "zero", "running", ["running", "pending"])
    orch.status_pipeline("zero")
    assert "🔄 zero: [0/2] running" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main: 参数解析 / 分支派发（L622-650）
# ---------------------------------------------------------------------------


def _run_main(argv, **patches):
    """以给定 argv 运行 main，status_pipeline / run_pipeline 默认打桩。"""
    defaults = {
        "yuleosh.pipeline.orchestrator.status_pipeline": mock.Mock(),
        "yuleosh.pipeline.orchestrator.run_pipeline": mock.Mock(
            return_value=SimpleNamespace(status="completed")
        ),
    }
    defaults.update(patches)
    with mock.patch.object(sys, "argv", argv), ExitStackCompat(defaults):
        orch.main()


class ExitStackCompat:
    """最小多 patch 上下文管理器（避免额外依赖）。"""

    def __init__(self, patches):
        self._patches = [
            mock.patch(target, value) for target, value in patches.items()
        ]

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False


def test_main_no_args_prints_usage(capsys):
    """无参数 → usage 打印到 stderr + sys.exit(1)（L623-628）。"""
    with pytest.raises(SystemExit) as ei:
        _run_main(["run.py"])
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "Usage:" in err
    assert "status [name]" in err


def test_main_status_without_name():
    """status 无 name → status_pipeline(None)（L633-634）。"""
    with mock.patch.object(sys, "argv", ["run.py", "status"]), mock.patch(
        "yuleosh.pipeline.orchestrator.status_pipeline"
    ) as sp:
        orch.main()
    sp.assert_called_once_with(None)


def test_main_status_with_name():
    """status 带 name → status_pipeline(name)（L634 True 分支）。"""
    with mock.patch.object(sys, "argv", ["run.py", "status", "run-1"]), mock.patch(
        "yuleosh.pipeline.orchestrator.status_pipeline"
    ) as sp:
        orch.main()
    sp.assert_called_once_with("run-1")


def test_main_profile_run_completed():
    """--profile <name> <spec> 且 completed → sys.exit(0)（L635-639）。"""
    rp = mock.Mock(return_value=SimpleNamespace(status="completed"))
    with mock.patch.object(sys, "argv", ["run.py", "--profile", "ci", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ) as rp_mock, pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 0
    rp_mock.assert_called_once_with("spec.md", profile="ci")


def test_main_profile_run_failed():
    """--profile 分支且 status != completed → sys.exit(1)（L639 后半）。"""
    rp = mock.Mock(return_value=SimpleNamespace(status="failed"))
    with mock.patch.object(sys, "argv", ["run.py", "--profile", "ci", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ), pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 1


def test_main_plain_run_completed():
    """普通 <spec> 且 completed → sys.exit(0)（L641-642）。"""
    rp = mock.Mock(return_value=SimpleNamespace(status="completed"))
    with mock.patch.object(sys, "argv", ["run.py", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ) as rp_mock, pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 0
    rp_mock.assert_called_once_with("spec.md")


def test_main_plain_run_failed():
    """普通分支且 status != completed → sys.exit(1)。"""
    rp = mock.Mock(return_value=SimpleNamespace(status="created"))
    with mock.patch.object(sys, "argv", ["run.py", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ), pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 1


def test_main_keyboard_interrupt(capsys):
    """run_pipeline 抛 KeyboardInterrupt → warning + sys.exit(130)（L643-646）。"""
    rp = mock.Mock(side_effect=KeyboardInterrupt)
    with mock.patch.object(sys, "argv", ["run.py", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ), pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 130
    assert "interrupted" in capsys.readouterr().err


def test_main_unhandled_exception(capsys):
    """run_pipeline 抛普通异常 → log critical + sys.exit(1)（L647-650）。"""
    rp = mock.Mock(side_effect=RuntimeError("boom"))
    with mock.patch.object(sys, "argv", ["run.py", "spec.md"]), mock.patch(
        "yuleosh.pipeline.orchestrator.run_pipeline", rp
    ), pytest.raises(SystemExit) as ei:
        orch.main()
    assert ei.value.code == 1
    assert "Unhandled exception: boom" in capsys.readouterr().err
