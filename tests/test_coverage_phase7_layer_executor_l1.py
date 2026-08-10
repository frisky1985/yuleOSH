"""Phase 7 coverage boost — layer_executor.py L1 函数组（L59-165）。

Target functions (src/yuleosh/ci/layers/layer_executor.py):
  - _find_go_modules (L59-72)
  - _run_go_build    (L75-103)
  - _run_go_vet      (L106-134)
  - _run_go_test     (L137-165)

策略：
  - _find_go_modules 用 pytest tmp_path 真实构建 go.mod 目录树
    （根模块 / 嵌套多模块 / 空目录 / 被排除目录 .git vendor node_modules
    target build .hidden）；
  - _run_go_* 全部 mock ``layer_executor.subprocess.run``，按测试场景
    返回成功 / 非零退出码 / FileNotFoundError / TimeoutExpired，
    绝不触发真实 subprocess；
  - 无网络 / 时间依赖，无 multiprocessing。
"""

import subprocess
from unittest import mock

import pytest

from yuleosh.ci.layers import layer_executor as executor
from yuleosh.ci.result import CIResult

# (目标函数, stage 名, 超时错误信息模板)
GO_FUNCS = [
    pytest.param(executor._run_go_build, "go-build", "go build timed out (60s)", id="build"),
    pytest.param(executor._run_go_vet, "go-vet", "go vet timed out (60s)", id="vet"),
    pytest.param(executor._run_go_test, "go-test", "go test timed out (60s)", id="test"),
]


def _new_ci():
    return CIResult(1, "test-commit")


def _last_stage(ci):
    """取最后一个 stage，忽略 add_stage 自动附加的 timestamp。"""
    return {k: v for k, v in ci.stages[-1].items() if k != "timestamp"}


def _make_project(tmp_path):
    """建一个含根 go.mod 的单模块工程目录。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "go.mod").write_text("module example.com/proj\n", encoding="utf-8")
    return proj


# ═══════════════════════════════════════════════════════════════════════
# _find_go_modules (L59-72)
# ═══════════════════════════════════════════════════════════════════════


def test_find_go_modules_empty_dir(tmp_path):
    assert executor._find_go_modules(str(tmp_path)) == []


def test_find_go_modules_root_module_stops_descending(tmp_path):
    """根目录有 go.mod → 只返回根，不再下钻子目录。"""
    (tmp_path / "go.mod").write_text("module root\n", encoding="utf-8")
    (tmp_path / "sub" / "inner").mkdir(parents=True)
    (tmp_path / "sub" / "go.mod").write_text("module sub\n", encoding="utf-8")
    assert executor._find_go_modules(str(tmp_path)) == [str(tmp_path)]


def test_find_go_modules_nested_sorted_and_excluded_dirs(tmp_path):
    """根无 go.mod：返回所有含 go.mod 的子目录（排序），排除隐藏/黑名单目录。"""
    (tmp_path / "backend" / "dkcs").mkdir(parents=True)
    (tmp_path / "backend" / "cloud" / "hub").mkdir(parents=True)
    (tmp_path / "plain").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "vendor").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "target").mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / "backend" / "dkcs" / "go.mod").write_text("module a\n", encoding="utf-8")
    (tmp_path / "backend" / "cloud" / "hub" / "go.mod").write_text(
        "module b\n", encoding="utf-8"
    )
    # 以下 go.mod 都必须被跳过（目录被过滤，根本不会走进）
    (tmp_path / ".hidden" / "go.mod").write_text("module h\n", encoding="utf-8")
    (tmp_path / ".git" / "go.mod").write_text("module g\n", encoding="utf-8")
    (tmp_path / "vendor" / "go.mod").write_text("module v\n", encoding="utf-8")
    (tmp_path / "node_modules" / "go.mod").write_text("module n\n", encoding="utf-8")
    (tmp_path / "target" / "go.mod").write_text("module t\n", encoding="utf-8")
    (tmp_path / "build" / "go.mod").write_text("module bd\n", encoding="utf-8")

    assert executor._find_go_modules(str(tmp_path)) == [
        str(tmp_path / "backend" / "cloud" / "hub"),
        str(tmp_path / "backend" / "dkcs"),
    ]


# ═══════════════════════════════════════════════════════════════════════
# _run_go_build / _run_go_vet / _run_go_test (L75-165)
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(("func", "stage", "_timeout_msg"), GO_FUNCS)
def test_go_cmd_success(func, stage, _timeout_msg, tmp_path):
    proj = _make_project(tmp_path)
    ci = _new_ci()
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        mr.return_value = mock.MagicMock(returncode=0, stderr="")
        assert func(str(proj), ci, 60) is True
    mr.assert_called_once_with(
        ["go", stage.split("-")[1], "./..."],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(proj),
    )
    assert _last_stage(ci) == {"name": stage, "status": "passed", "detail": ""}


@pytest.mark.parametrize(("func", "stage", "_timeout_msg"), GO_FUNCS)
def test_go_cmd_failed_nonzero_exit(func, stage, _timeout_msg, tmp_path):
    proj = _make_project(tmp_path)
    ci = _new_ci()
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        mr.return_value = mock.MagicMock(returncode=1, stderr="boom error")
        assert func(str(proj), ci, 60) is False
    failed = [s for s in ci.stages if s["name"] == stage]
    assert failed[-1]["status"] == "failed"
    assert failed[-1]["detail"] == "[.] boom error"
    assert not any(s["status"] == "passed" for s in ci.stages)


@pytest.mark.parametrize(("func", "stage", "_timeout_msg"), GO_FUNCS)
def test_go_cmd_stderr_truncated_to_400(func, stage, _timeout_msg, tmp_path):
    """L90/121/152: result.stderr[:400] 截断。"""
    proj = _make_project(tmp_path)
    ci = _new_ci()
    long_err = "x" * 500
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        mr.return_value = mock.MagicMock(returncode=2, stderr=long_err)
        assert func(str(proj), ci, 60) is False
    failed = [s for s in ci.stages if s["name"] == stage]
    assert failed[-1]["detail"] == "[.] " + "x" * 400


@pytest.mark.parametrize(("func", "stage", "_timeout_msg"), GO_FUNCS)
def test_go_cmd_file_not_found(func, stage, _timeout_msg, tmp_path):
    proj = _make_project(tmp_path)
    ci = _new_ci()
    with mock.patch(
        "yuleosh.ci.layers.layer_executor.subprocess.run",
        side_effect=FileNotFoundError,
    ):
        assert func(str(proj), ci, 60) is False
    assert _last_stage(ci) == {
        "name": stage,
        "status": "error",
        "detail": "go not installed",
    }


@pytest.mark.parametrize(("func", "stage", "timeout_msg"), GO_FUNCS)
def test_go_cmd_timeout(func, stage, timeout_msg, tmp_path):
    proj = _make_project(tmp_path)
    ci = _new_ci()
    with mock.patch(
        "yuleosh.ci.layers.layer_executor.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["go"], timeout=60),
    ):
        assert func(str(proj), ci, 60) is False
    assert _last_stage(ci) == {
        "name": stage,
        "status": "error",
        "detail": timeout_msg,
    }


def test_go_build_no_modules_falls_back_to_project_dir(tmp_path):
    """无 go.mod：mods 回退为 [project_dir]（L78 的 or 分支）。"""
    proj = tmp_path / "empty"
    proj.mkdir()
    ci = _new_ci()
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        mr.return_value = mock.MagicMock(returncode=0, stderr="")
        assert executor._run_go_build(str(proj), ci, 60) is True
    assert mr.call_args.args[0] == ["go", "build", "./..."]
    assert mr.call_args.kwargs["cwd"] == str(proj)


def test_go_build_multi_module_mixed_results(tmp_path):
    """多模块 monorepo：第一个通过、第二个失败 → 整体 False。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "backend" / "dkcs").mkdir(parents=True)
    (proj / "backend" / "cloud" / "hub").mkdir(parents=True)
    (proj / "backend" / "dkcs" / "go.mod").write_text("module a\n", encoding="utf-8")
    (proj / "backend" / "cloud" / "hub" / "go.mod").write_text(
        "module b\n", encoding="utf-8"
    )
    ci = _new_ci()
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        # sorted 顺序: backend/cloud/hub 先于 backend/dkcs
        mr.side_effect = [
            mock.MagicMock(returncode=0, stderr=""),
            mock.MagicMock(returncode=1, stderr="vet err"),
        ]
        assert executor._run_go_build(str(proj), ci, 60) is False
    assert mr.call_count == 2
    failed = [s for s in ci.stages if s["name"] == "go-build" and s["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["detail"] == "[backend/dkcs] vet err"
    assert not any(s["status"] == "passed" for s in ci.stages)


def test_go_build_multi_module_all_pass(tmp_path):
    """多模块全部通过 → 末尾追加一次 passed stage。"""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a").mkdir()
    (proj / "b").mkdir()
    (proj / "a" / "go.mod").write_text("module a\n", encoding="utf-8")
    (proj / "b" / "go.mod").write_text("module b\n", encoding="utf-8")
    ci = _new_ci()
    with mock.patch("yuleosh.ci.layers.layer_executor.subprocess.run") as mr:
        mr.return_value = mock.MagicMock(returncode=0, stderr="")
        assert executor._run_go_build(str(proj), ci, 60) is True
    assert mr.call_count == 2
    assert _last_stage(ci) == {"name": "go-build", "status": "passed", "detail": ""}
    assert sum(1 for s in ci.stages if s["name"] == "go-build") == 1
