"""SYS-REQ-002 验证: V 左半 (SYS→SWE.1) 连续性可被强制执行。

背景 (M1.5 前): _check_sys_requirements_aligned 只写对齐报告 + 记 WARNING,
V 两侧脱节时 SWE.1 照样 completed —— 链接「被记录」但无法「被强制」。

验收 (docs/planning/left-branch-fix-requirements.md SYS-REQ-002):
  - OSH_SYS_ALIGN_STRICT 开启 → 未对齐(含左半缺失) 时 SWE.1 步骤失败
  - 默认关闭 → 行为与改动前完全一致 (向后兼容)
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.pipeline.session import PipelineStepError
from yuleosh.pipeline.step_handlers import spec as spec_mod


# ── 测试替身 ──────────────────────────────────────────────────────────────
class _FakeSession:
    def __init__(self, root: Path, spec: Path, sdir: Path):
        self.project_dir = str(root)
        self.spec_path = str(spec)
        self.session_dir = Path(sdir)
        self._artifacts: dict = {}

    def set_artifact(self, k: str, v: str) -> None:
        self._artifacts[k] = v


class _OkRun:
    returncode = 0
    stdout = json.dumps({
        "error_count": 0,
        "issues": [],
        "coverage": {"score": 92.0},
    })
    stderr = ""


def _contracts_ok():
    return {
        "validation": {"passed": True, "missing": [], "details": {}},
        "contracts": {"files": []},
    }


def _run_spec_check(sess):
    """以替身依赖跑一遍 step_spec_check, 返回其返回值 (可能抛 PipelineStepError)。"""
    with mock.patch.object(spec_mod.subprocess, "run", return_value=_OkRun()), \
         mock.patch.object(spec_mod, "contracts_check", return_value=_contracts_ok()):
        return spec_mod.step_spec_check(sess)


def _mk(tmp_path: Path, sys_doc: str | None, spec_text: str):
    spec = tmp_path / "spec.md"
    spec.write_text(spec_text, encoding="utf-8")
    if sys_doc is not None:
        d = tmp_path / "docs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "system-requirements.md").write_text(sys_doc, encoding="utf-8")
    sdir = tmp_path / ".osh" / "sessions" / "s1"
    sdir.mkdir(parents=True, exist_ok=True)
    return _FakeSession(tmp_path, spec, sdir), sdir


# ── 对齐报告 status 语义 ──────────────────────────────────────────────────
def test_align_report_status_absent_when_no_sys_doc(tmp_path):
    sess, _ = _mk(tmp_path, sys_doc=None, spec_text="# Spec\n")
    rep = spec_mod._check_sys_requirements_aligned(sess)
    assert rep is not None and rep["status"] == "absent"
    assert rep["total_sys_reqs"] == 0


def test_align_report_status_none_parsed(tmp_path):
    sess, _ = _mk(tmp_path, sys_doc="# System\nno requirement ids\n", spec_text="# Spec\n")
    rep = spec_mod._check_sys_requirements_aligned(sess)
    assert rep["status"] == "none-parsed"


def test_align_report_returns_partial(tmp_path):
    sess, _ = _mk(
        tmp_path,
        sys_doc="# SYS\nSYS-REQ-001 alpha\nSYS-REQ-002 beta\n",
        spec_text="# Spec\nmentions SYS-REQ-001 only\n",
    )
    rep = spec_mod._check_sys_requirements_aligned(sess)
    assert rep["status"] == "partial"
    assert rep["missing_in_spec"] == ["SYS-REQ-002"]


def test_align_report_returns_aligned(tmp_path):
    sess, _ = _mk(
        tmp_path,
        sys_doc="# SYS\nSYS-REQ-001 alpha\n",
        spec_text="# Spec\nrefers SYS-REQ-001\n",
    )
    rep = spec_mod._check_sys_requirements_aligned(sess)
    assert rep["status"] == "aligned"
    assert rep["missing_in_spec"] == []


# ── strict 开关 ───────────────────────────────────────────────────────────
def test_strict_helper_default_off(monkeypatch):
    monkeypatch.delenv("OSH_SYS_ALIGN_STRICT", raising=False)
    assert spec_mod._sys_align_strict_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "YES", "on"])
def test_strict_helper_truthy_values(monkeypatch, val):
    monkeypatch.setenv("OSH_SYS_ALIGN_STRICT", val)
    assert spec_mod._sys_align_strict_enabled() is True


def test_strict_helper_empty_value_disabled(monkeypatch):
    monkeypatch.setenv("OSH_SYS_ALIGN_STRICT", "")
    assert spec_mod._sys_align_strict_enabled() is False


# ── strict 端到端: 未对齐必须阻断 ─────────────────────────────────────────
def test_strict_blocks_when_left_branch_absent(tmp_path, monkeypatch):
    """左半完全缺失 + strict → SWE.1 必须失败 (而非全绿放行)。"""
    monkeypatch.setenv("OSH_SYS_ALIGN_STRICT", "1")
    sess, _ = _mk(tmp_path, sys_doc=None, spec_text="# Spec\n")
    with pytest.raises(PipelineStepError) as ei:
        _run_spec_check(sess)
    assert "V 左半链路断裂" in str(ei.value)
    assert "absent" in str(ei.value)


def test_strict_blocks_when_partial(tmp_path, monkeypatch):
    """部分未引用 + strict → SWE.1 失败。"""
    monkeypatch.setenv("OSH_SYS_ALIGN_STRICT", "1")
    sess, _ = _mk(
        tmp_path,
        sys_doc="# SYS\nSYS-REQ-001 alpha\nSYS-REQ-002 beta\n",
        spec_text="# Spec\nonly SYS-REQ-001\n",
    )
    with pytest.raises(PipelineStepError) as ei:
        _run_spec_check(sess)
    assert "V 左半链路断裂" in str(ei.value)
    assert "SYS-REQ-002" in str(ei.value)


def test_strict_passes_when_aligned(tmp_path, monkeypatch):
    """完全对齐 + strict → 正常完成, 返回产物路径。"""
    monkeypatch.setenv("OSH_SYS_ALIGN_STRICT", "1")
    sess, sdir = _mk(
        tmp_path,
        sys_doc="# SYS\nSYS-REQ-001 alpha\n",
        spec_text="# Spec\nrefers SYS-REQ-001\n",
    )
    out = _run_spec_check(sess)
    assert out == str(sdir / "spec-check.json")
    assert sess._artifacts.get("sys_spec_alignment") is not None


# ── 向后兼容: 默认必须放行 ────────────────────────────────────────────────
def test_default_passes_despite_partial(tmp_path, monkeypatch):
    """默认 (strict 关闭) + 部分未引用 → 不阻断, 仍写对齐报告 (与改动前一致)。"""
    monkeypatch.delenv("OSH_SYS_ALIGN_STRICT", raising=False)
    sess, sdir = _mk(
        tmp_path,
        sys_doc="# SYS\nSYS-REQ-001 alpha\nSYS-REQ-002 beta\n",
        spec_text="# Spec\nno refs\n",
    )
    out = _run_spec_check(sess)  # 不得抛异常
    assert out == str(sdir / "spec-check.json")
    align = json.loads((sdir / "sys-spec-alignment.json").read_text(encoding="utf-8"))
    assert align["status"] == "partial"


def test_default_passes_when_left_branch_absent(tmp_path, monkeypatch):
    """默认 + 左半缺失 → 不阻断, 且不产生额外对齐产物 (磁盘行为不变)。"""
    monkeypatch.delenv("OSH_SYS_ALIGN_STRICT", raising=False)
    sess, sdir = _mk(tmp_path, sys_doc=None, spec_text="# Spec\n")
    out = _run_spec_check(sess)  # 不得抛异常
    assert out == str(sdir / "spec-check.json")
    assert not (sdir / "sys-spec-alignment.json").exists()
