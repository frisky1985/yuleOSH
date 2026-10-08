"""M1.5 孤岛消除专项测试 — 验证 SYS 层四重孤岛被打通 (A/B/C 链路)。

A: SYS 追溯映射并入主 LRT 矩阵 (generate_lrt 返回 sys_trace)
B: SWE.1 spec-check 消费 SYS 上游需求 (_check_sys_requirements_aligned 不阻断)
C: dashboard 暴露 sys_status (SYS.1~5) + gates (含 G0)

前端 (D) 渲染需本机起服务截图复核, 此处仅覆盖后端数据层。
"""

import json
from pathlib import Path

import pytest

from yuleosh.alm.traceability import generate_lrt
from yuleosh.pipeline.step_handlers.spec import _check_sys_requirements_aligned


def _write_sys_trace(root: Path, mapping: dict) -> None:
    ev = root / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    ev.joinpath("sys-to-swe-trace.json").write_text(
        json.dumps({"sys_to_swe": mapping, "note": "test"}, ensure_ascii=False),
        encoding="utf-8",
    )


# ── 链路A: SYS 映射并入主 LRT 矩阵 ───────────────────────────────────────
def test_generate_lrt_includes_sys_trace(tmp_path):
    # sys_trace 来自 load_sys_swe_trace, 与 lrm (SWE 层扫描) 无关, 空项目即可验证
    _write_sys_trace(tmp_path, {"SYS-REQ-001": "SWE.1", "SYS-REQ-002": "SWE.1"})
    result = generate_lrt(str(tmp_path))
    sys_trace = result.get("sys_trace", {})
    assert sys_trace.get("sys_to_swe", {}).get("SYS-REQ-001") == "SWE.1"
    assert sys_trace["sys_to_swe"]["SYS-REQ-002"] == "SWE.1"


def test_generate_lrt_sys_trace_empty_when_no_file(tmp_path):
    result = generate_lrt(str(tmp_path))
    assert result.get("sys_trace", {}).get("sys_to_swe", {}) == {}


# ── 链路B: SWE.1 消费 SYS 上游需求 (不阻断主流程) ────────────────────────
class _FakeSession:
    def __init__(self, root: Path, spec: Path, sdir: Path):
        self.project_dir = str(root)
        self.spec_path = str(spec)
        self.session_dir = Path(sdir)
        self._artifacts: dict = {}

    def set_artifact(self, k: str, v: str) -> None:
        self._artifacts[k] = v


def test_check_sys_requirements_aligned_partial(tmp_path):
    sys_doc = tmp_path / "docs" / "system-requirements.md"
    sys_doc.parent.mkdir(parents=True, exist_ok=True)
    sys_doc.write_text(
        "# SYS\n- SYS-REQ-001 system requirement A\n- SYS-REQ-002 system requirement B\n",
        encoding="utf-8",
    )
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\nNo SYS refs here.\n", encoding="utf-8")
    sdir = tmp_path / ".osh" / "sessions" / "s1"
    sdir.mkdir(parents=True, exist_ok=True)
    sess = _FakeSession(tmp_path, spec, sdir)
    _check_sys_requirements_aligned(sess)  # 必须不 raise
    align = sdir / "sys-spec-alignment.json"
    assert align.exists()
    data = json.loads(align.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert "SYS-REQ-001" in data["missing_in_spec"]


def test_check_sys_requirements_aligned_aligned(tmp_path):
    sys_doc = tmp_path / "docs" / "system-requirements.md"
    sys_doc.parent.mkdir(parents=True, exist_ok=True)
    sys_doc.write_text("# SYS\n- SYS-REQ-001 system requirement A\n", encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\nSYS-REQ-001 is covered.\n", encoding="utf-8")
    sdir = tmp_path / ".osh" / "sessions" / "s1"
    sdir.mkdir(parents=True, exist_ok=True)
    sess = _FakeSession(tmp_path, spec, sdir)
    _check_sys_requirements_aligned(sess)
    data = json.loads((sdir / "sys-spec-alignment.json").read_text(encoding="utf-8"))
    assert data["status"] == "aligned"
    assert data["missing_in_spec"] == []


def test_check_sys_requirements_aligned_no_sys_doc(tmp_path):
    # 系统层未运行 (无 system-requirements.md) 时应为静默 no-op, 不 raise
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n", encoding="utf-8")
    sdir = tmp_path / ".osh" / "sessions" / "s1"
    sdir.mkdir(parents=True, exist_ok=True)
    sess = _FakeSession(tmp_path, spec, sdir)
    _check_sys_requirements_aligned(sess)
    assert not (sdir / "sys-spec-alignment.json").exists()


# ── 链路C: dashboard 暴露 sys_status + gates (含 G0) ──────────────────────
dashboard = pytest.importorskip("yuleosh.api.dashboard")


def test_dashboard_sys_status_and_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    ev = tmp_path / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    ev.joinpath("sys-review.json").write_text(
        json.dumps({"verdict": "passed"}), encoding="utf-8"
    )
    sess = tmp_path / ".osh" / "sessions" / "run1"
    sess.mkdir(parents=True, exist_ok=True)
    sess.joinpath("gate-summary.json").write_text(
        json.dumps({"gates": [{"gate": "G0", "name": "SYS 系统层 Gate", "status": "passed"}]}),
        encoding="utf-8",
    )
    sys_status = dashboard._build_sys_status()
    assert sys_status["SYS.1"]["status"] == "completed"
    assert sys_status["SYS.5"]["status"] == "completed"
    gates = dashboard._load_gates_summary()
    assert any(g["gate"] == "G0" for g in gates)
