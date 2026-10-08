"""T5 / SYS-REQ-005: 追溯矩阵默认落盘且指标达标。

需求追溯: STAKE-04 → SYS-REQ-005

验收标准:
  1. 流水线默认产出 .osh/evidence/traceability-matrix.{json,md}（结构化、含真实映射行）；
  2. 落盘后合规引擎 _has_traced_requirements() / _traceability_metrics_met() 为 True；
  3. 反假绿: 覆盖率不足时产物照写但判定仍为 False（绝不伪造映射）。

设计红线: 本测试刻意包含「低覆盖必须判红」用例 —— 若有人把覆盖率写死为
100% 或伪造测试引用，该用例会立即失败。
"""

import json
from pathlib import Path

from yuleosh.alm.traceability import write_authoritative_traceability


# ── helpers ─────────────────────────────────────────────────────────────

def _make_project(root: Path, *, n_reqs: int = 3, n_tested: int = 2) -> Path:
    """构造 fixture 工程。

    需求 ID 必须用 spec 自定义 ID（**REQ-001**:）——traceability 的 pytest
    扫描仅在 req_id 不以 ``SHALL-`` 开头时触发（_find_tests_for_requirement），
    否则永远匹配不到测试，覆盖率恒为 0。
    """
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    lines = ["# Demo Spec", "", "## Requirements", ""]
    for i in range(1, n_reqs + 1):
        lines.append(f"- **REQ-{i:03d}**: The system SHALL perform function {i}.")
    (docs / "spec.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if n_tested > 0:
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        body = []
        for i in range(1, n_tested + 1):
            body.append(f"# covers REQ-{i:03d}\ndef test_fn{i}():\n    assert True\n\n")
        (tests / "test_demo.py").write_text("\n".join(body), encoding="utf-8")
    return root


class _FakeSession:
    def __init__(self, project_dir):
        self.project_dir = str(project_dir)


# ── 1. 落盘产物 ─────────────────────────────────────────────────────────

def test_emission_writes_both_artifacts(tmp_path):
    proj = _make_project(tmp_path, n_reqs=3, n_tested=2)
    result = write_authoritative_traceability(str(proj))

    md = Path(result["md"])
    js = Path(result["json"])
    assert md.is_file(), "traceability-matrix.md 未落盘"
    assert js.is_file(), "traceability-matrix.json 未落盘"
    assert md.parent.name == "evidence" and md.parent.parent.name == ".osh"

    data = json.loads(js.read_text(encoding="utf-8"))
    # checker 依赖的键名（compliance_checker.py:517-518）
    assert data["summary"]["total_requirements"] == 3
    assert data["summary"]["with_test_coverage"] == 2
    assert len(data["requirements"]) == 3
    # 真实映射行，而非空壳
    assert sum(1 for r in data["requirements"] if r["test_files"]) == 2

    md_text = md.read_text(encoding="utf-8")
    assert "| Requirement |" in md_text
    assert "Status: ✅ Covered" in md_text
    assert "Status: ❌ Not Covered" in md_text


# ── 2. 合规引擎判定（验收核心）────────────────────────────────────────

def test_checker_gates_pass_after_emission(tmp_path):
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    proj = _make_project(tmp_path, n_reqs=3, n_tested=2)
    checker = ComplianceChecker(str(proj))

    # 落盘前：应为 False（证明测试确实在验证"落盘带来的改善"，而非恒真）
    assert checker._has_traced_requirements() is False
    assert checker._traceability_metrics_met() is False

    write_authoritative_traceability(str(proj))

    assert checker._has_traced_requirements() is True
    assert checker._traceability_metrics_met() is True  # 2/3 = 66.7% ≥ 60%


# ── 3. 反假绿 ───────────────────────────────────────────────────────────

def test_no_false_green_when_tests_missing(tmp_path):
    """一条测试都没写时，覆盖率必须如实为 0，判红。"""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    proj = _make_project(tmp_path, n_reqs=3, n_tested=0)
    result = write_authoritative_traceability(str(proj))

    assert result["summary"]["total_requirements"] == 3
    assert result["summary"]["with_test_coverage"] == 0
    assert result["summary"]["coverage_pct"] == 0.0

    checker = ComplianceChecker(str(proj))
    assert checker._has_traced_requirements() is True    # 有矩阵（含 SHALL-ID）
    assert checker._traceability_metrics_met() is False  # 但 0% 覆盖 → 判红


def test_no_false_green_when_coverage_below_threshold(tmp_path):
    """覆盖 1/3 = 33% < 60% → 判红（边界下方）。"""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    proj = _make_project(tmp_path, n_reqs=3, n_tested=1)
    write_authoritative_traceability(str(proj))
    checker = ComplianceChecker(str(proj))
    assert checker._traceability_metrics_met() is False


def test_empty_project_emits_honest_empty_matrix(tmp_path):
    """无 spec 时产物照写但如实为空，绝不凭空造需求。"""
    result = write_authoritative_traceability(str(tmp_path))
    assert result["summary"]["total_requirements"] == 0
    assert "no requirements parsed" in Path(result["md"]).read_text(encoding="utf-8")


# ── 4. 流水线钩子 ───────────────────────────────────────────────────────

def test_hook_writes_by_default(tmp_path, monkeypatch):
    from yuleosh.pipeline import orchestrator

    monkeypatch.delenv("OSH_EMIT_TRACEABILITY", raising=False)
    proj = _make_project(tmp_path, n_reqs=2, n_tested=2)

    result = orchestrator._emit_traceability_artifacts(_FakeSession(proj))

    assert result is not None
    assert Path(result["json"]).is_file()
    assert (proj / ".osh" / "evidence" / "traceability-matrix.md").is_file()


def test_hook_disabled_by_env(tmp_path, monkeypatch):
    from yuleosh.pipeline import orchestrator

    monkeypatch.setenv("OSH_EMIT_TRACEABILITY", "0")
    proj = _make_project(tmp_path, n_reqs=2, n_tested=2)

    assert orchestrator._emit_traceability_artifacts(_FakeSession(proj)) is None
    assert not (proj / ".osh" / "evidence" / "traceability-matrix.json").exists()


def test_hook_never_raises(tmp_path, monkeypatch):
    """证据产物失败绝不影响 run 结论。"""
    from yuleosh.alm import traceability as tr
    from yuleosh.pipeline import orchestrator

    monkeypatch.delenv("OSH_EMIT_TRACEABILITY", raising=False)

    def _boom(*_a, **_kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(tr, "write_authoritative_traceability", _boom)
    assert orchestrator._emit_traceability_artifacts(_FakeSession(tmp_path)) is None


def test_hook_no_project_dir_is_noop(monkeypatch):
    from yuleosh.pipeline import orchestrator

    monkeypatch.delenv("OSH_EMIT_TRACEABILITY", raising=False)

    class _NoProj:
        project_dir = None

    assert orchestrator._emit_traceability_artifacts(_NoProj()) is None


# ── 5. SYS 层追溯并入（M1.5 链路A 一致性）────────────────────────────

def test_sys_trace_propagated_into_matrix(tmp_path):
    proj = _make_project(tmp_path, n_reqs=1, n_tested=1)
    ev = proj / ".osh" / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "sys-to-swe-trace.json").write_text(
        json.dumps({"sys_to_swe": {"SYS-REQ-001": "REQ-001"}}), encoding="utf-8")

    result = write_authoritative_traceability(str(proj))
    data = json.loads(Path(result["json"]).read_text(encoding="utf-8"))
    assert data["sys_trace"]["sys_to_swe"] == {"SYS-REQ-001": "REQ-001"}
    assert "SYS-REQ-001 → REQ-001" in Path(result["md"]).read_text(encoding="utf-8")
