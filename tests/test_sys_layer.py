"""M1 / Phase A — SYS 系统层（SYS.1~SYS.5）落地测试.

覆盖:
- aspice_sys_v3.1 profile 经通用 loader 加载为 5 个过程域（零 dataclass 改动）
- 6 个 SYS handler 确定性生成 docs/system-*.md（无 LLM 依赖）
- step_review_sys 确定性门禁：缺章节即 RED
- ComplianceChecker 以 SYS profile 运行产出 SYS.1~SYS.5 证据区
- SYS.x → SWE.1 追溯 sidecar 读写（alm/traceability.load_sys_swe_trace）
"""

import json
import os

import pytest

from yuleosh.compliance.profile import load_profile
from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers import (
    step_sys_requirements,
    step_sys_architecture,
    step_sys_verification,
    step_sys_integration,
    step_sys_validation,
    step_review_sys,
)
from yuleosh.alm.traceability import load_sys_swe_trace


def _make_session(tmp_path, spec_text="# 车窗防夹\n\n## 概述\n\n防夹功能。\n\n## 需求\n\n系统应防夹。\n"):
    """构造隔离的 PipelineSession（OSH_HOME=tmp，无网络/LLM）。"""
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text(spec_text, encoding="utf-8")
    sess = PipelineSession("sys-test", str(spec))
    # 强制 project_dir 指向 tmp（handler 向 project_dir/docs 写 SYS 交付物）
    sess.project_dir = str(tmp_path)
    return sess


def _write_all_sys_docs(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for name in (
        "system-requirements.md",
        "system-architecture.md",
        "system-verification.md",
        "system-integration.md",
        "system-validation.md",
    ):
        (docs / name).write_text(
            f"# {name}\n\n## 可追溯性\n\n- 追溯至上游。\n", encoding="utf-8"
        )


# ── A1: profile 加载 ────────────────────────────────────────────────────
def test_sys_profile_loads_as_five_areas():
    p = load_profile("aspice_sys_v3.1")
    ids = [a.id for a in p.areas]
    assert ids == ["SYS.1", "SYS.2", "SYS.3", "SYS.4", "SYS.5"]
    # meta 与 SWE profile 同构
    assert p.standard == "ASPICE"
    assert p.version == "3.1"


def test_sys_profile_evidence_paths_align_with_handlers():
    p = load_profile("aspice_sys_v3.1")
    by_id = {a.id: a for a in p.areas}
    # 每个 SYS 区域的 BP evidence 路径与 handler 产物路径严格对齐
    expected = {
        "SYS.1": "docs/system-requirements.md",
        "SYS.2": "docs/system-architecture.md",
        "SYS.3": "docs/system-verification.md",
        "SYS.4": "docs/system-integration.md",
        "SYS.5": "docs/system-validation.md",
    }
    for sid, want in expected.items():
        ev_paths = {
            ev.path
            for bp in by_id[sid].base_practices
            for ev in bp.output_evidence
        }
        assert want in ev_paths, f"{sid} 缺证据路径 {want}"


# ── A2/A3: handler 确定性生成 ────────────────────────────────────────────
def test_sys_requirements_generates_doc_and_trace(tmp_path):
    sess = _make_session(tmp_path)
    out = step_sys_requirements(sess)
    req_doc = tmp_path / "docs" / "system-requirements.md"
    assert req_doc.exists()
    text = req_doc.read_text(encoding="utf-8")
    assert "## 系统需求" in text
    assert "## 可追溯性" in text
    assert "SYS-REQ-001" in text
    # 追溯 sidecar
    trace = load_sys_swe_trace(tmp_path)
    assert trace["sys_to_swe"].get("SYS-REQ-001") == "SWE.1"
    assert out == str(req_doc)


def test_sys_generators_produce_all_five_docs(tmp_path):
    sess = _make_session(tmp_path)
    for fn in (
        step_sys_requirements,
        step_sys_architecture,
        step_sys_verification,
        step_sys_integration,
        step_sys_validation,
    ):
        fn(sess)
    for rel in (
        "docs/system-requirements.md",
        "docs/system-architecture.md",
        "docs/system-verification.md",
        "docs/system-integration.md",
        "docs/system-validation.md",
    ):
        assert (tmp_path / rel).exists(), f"缺失 {rel}"


def test_sys_review_passes_when_docs_present(tmp_path):
    sess = _make_session(tmp_path)
    for fn in (
        step_sys_requirements,
        step_sys_architecture,
        step_sys_verification,
        step_sys_integration,
        step_sys_validation,
    ):
        fn(sess)
    rec = step_review_sys(sess)
    assert (tmp_path / ".osh" / "evidence" / "sys-review.json").exists()
    assert "sys-review" in rec


def test_sys_review_red_when_doc_missing(tmp_path):
    sess = _make_session(tmp_path)
    # 仅生成部分文档，缺 system-validation.md
    step_sys_requirements(sess)
    step_sys_architecture(sess)
    with pytest.raises(PipelineStepError):
        step_review_sys(sess)


def test_sys_review_red_when_section_missing(tmp_path):
    sess = _make_session(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    # 含文件但缺必需章节
    (docs / "system-requirements.md").write_text("# 系统需求\n\n(无追溯性章节)\n", encoding="utf-8")
    (docs / "system-architecture.md").write_text("# 架构\n\n## 可追溯性\n\nok\n", encoding="utf-8")
    with pytest.raises(PipelineStepError):
        step_review_sys(sess)


# ── A1 + checker: SYS profile 驱动合规检查产出 SYS 区 ───────────────────
def test_compliance_checker_uses_sys_profile(tmp_path):
    _write_all_sys_docs(tmp_path)
    profile = load_profile("aspice_sys_v3.1")
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=profile)
    report = checker.run()
    sections = report["swe_sections"]
    assert {"sys.1", "sys.2", "sys.3", "sys.4", "sys.5"} <= set(sections.keys())
    ids = {sections[k]["id"] for k in sections}
    assert ids == {"SYS.1", "SYS.2", "SYS.3", "SYS.4", "SYS.5"}


def test_compliance_checker_sys_areas_passed_with_docs(tmp_path):
    """M1 范围：SYS profile 驱动 checker 将 handler 产物识别为 SYS.1~5 证据。

    诚实边界：M1 仅交付「SYS profile + 确定性 handler + 证据路径对齐」。
    checker 的 check 启发式是 SWE 取向（识别 REQ-xxx/SHALL/functional area 等），
    不识别 SYS 交付物内容；SYS 内容判绿属 M3（信号治理 / checker 启发式扩展）。
    故此处断言「证据被识别」（details 含 ✅ Evidence found），而非全 ✅。
    """
    sess = _make_session(tmp_path)
    for fn in (
        step_sys_requirements,
        step_sys_architecture,
        step_sys_verification,
        step_sys_integration,
        step_sys_validation,
    ):
        fn(sess)
    profile = load_profile("aspice_sys_v3.1")
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=profile)
    report = checker.run()
    sections = report["swe_sections"]
    assert {"sys.1", "sys.2", "sys.3", "sys.4", "sys.5"} <= set(sections.keys())
    # 每个 SYS 区域至少一条 BP 的证据路径被识别（证据对齐生效，非假绿）
    for k in ("sys.1", "sys.2", "sys.3", "sys.4", "sys.5"):
        bp_details = [d for bp in sections[k]["base_practices"] for d in bp["details"]]
        assert any("✅ Evidence found" in d for d in bp_details), (k, sections[k])


def test_compliance_checker_sys_areas_missing_without_docs(tmp_path):
    # 无 SYS 文档 → SYS 区域至少一个 BP 失败（非假绿）
    profile = load_profile("aspice_sys_v3.1")
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=profile)
    report = checker.run()
    sys1 = report["swe_sections"]["sys.1"]
    assert any(bp["status"] != "✅" for bp in sys1["base_practices"]), sys1
