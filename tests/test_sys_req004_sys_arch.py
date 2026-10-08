"""T4 / SYS-REQ-004: SYS 交付物内容实质化（以 SYS.2 系统架构为样板）。

需求追溯: STAKE-03b → SYS-REQ-004

缺陷: SYS.2 产物原为泛化散文（约 595B），无系统元素边界、无接口定义、
无需求覆盖矩阵 —— 架构内容不可验证；且合规引擎 ``_has_arch_document``
的候选路径根本不含 ``docs/system-architecture.md``，写再实也恒判
"no substantive architecture doc found"。

验收: SYS.2 不再报 "no substantive architecture doc found"。

反假绿红线（本文件刻意把守）:
  1. 接口无上游来源时必须如实标注未定义 —— 不得臆造类型/取值范围；
     因此 SYS.2.BP2 在无接口信息时**必须保持非 ✅**。
  2. 仅 SYS 区认可系统架构文档；SWE 区不得借道系统架构文档蒙混过关。
"""

import os
from pathlib import Path

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.step_handlers import (
    step_sys_requirements,
    step_sys_architecture,
)


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("# 车窗防夹\n\n## GPIO 控制\n\n系统应驱动 LED。\n\n"
                    "## 传感器通信\n\n系统应读取传感器。\n", encoding="utf-8")
    sess = type("S", (), {})()  # 轻量替身，仅 handler 用到的属性
    sess.project_dir = str(tmp_path)
    sess.spec_path = str(spec)
    sess.session_dir = str(tmp_path / ".osh" / "sessions" / "t4")
    return sess


def _gen_arch(tmp_path):
    sess = _make_session(tmp_path)
    step_sys_requirements(sess)
    step_sys_architecture(sess)
    return Path(tmp_path) / "docs" / "system-architecture.md"


# ── 1. 内容实质化 ───────────────────────────────────────────────────────

def test_arch_derives_elements_from_real_requirements(tmp_path):
    doc = _gen_arch(tmp_path)
    text = doc.read_text(encoding="utf-8")

    req_doc = (tmp_path / "docs" / "system-requirements.md").read_text(encoding="utf-8")
    req_ids = sorted({line.split()[0] for line in req_req_lines(req_doc)})

    # 每条真实 SYS-REQ 都对应一个系统元素 + 一行覆盖矩阵
    for rid in req_ids:
        assert rid in text, f"{rid} 未出现在架构文档"
    assert "## 系统元素与边界" in text
    assert "## 需求覆盖矩阵" in text
    assert text.count("| SE-") >= len(req_ids)
    # 内容量级显著大于原 595B 泛化散文
    assert len(text) > 700


def req_req_lines(req_doc_text):
    return [ln for ln in req_doc_text.splitlines() if "SYS-REQ-" in ln]


def test_arch_declares_interfaces_undefined_instead_of_fabricating(tmp_path):
    """无上游接口信息 → 必须如实标注未定义，绝不臆造类型/取值范围。"""
    text = _gen_arch(tmp_path).read_text(encoding="utf-8")
    assert "接口状态: **未定义**" in text
    assert "待补充" in text
    # 不得出现伪造的取值/类型断言
    assert "uint32" not in text


def test_arch_honest_when_no_requirements_source(tmp_path):
    """无 SYS.1 需求文档 → 如实标注，绝不凭空造元素。"""
    sess = _make_session(tmp_path)
    step_sys_architecture(sess)  # 未跑 SYS.1
    text = (tmp_path / "docs" / "system-architecture.md").read_text(encoding="utf-8")

    assert "未解析到任何 SYS-REQ" in text
    assert "❌ Not Covered" in text
    assert "| SE-" not in text  # 不得凭空生成系统元素


def test_arch_keeps_required_traceability_section(tmp_path):
    """保留 ## 可追溯性 —— step_review_sys 确定性门禁依赖它。"""
    text = _gen_arch(tmp_path).read_text(encoding="utf-8")
    assert "## 可追溯性" in text


# ── 2. 合规引擎判定（验收）──────────────────────────────────────────────

def test_checker_sys2_no_longer_reports_no_substantive_arch(tmp_path):
    _gen_arch(tmp_path)
    checker = ComplianceChecker(project_dir=str(tmp_path),
                                profile=load_profile("aspice_sys_v3.1"))
    sys2 = checker.run()["swe_sections"]["sys.2"]
    details = [d for bp in sys2["base_practices"] for d in bp["details"]]

    assert not any("no substantive architecture doc found" in d for d in details), details
    statuses = {bp["id"]: bp["status"] for bp in sys2["base_practices"]}
    assert statuses["SYS.2.BP1"] == "✅"
    assert statuses["SYS.2.BP3"] == "✅"


def test_checker_sys2_bp2_stays_red_without_interfaces(tmp_path):
    """反假绿: 接口未定义时 BP2 必须仍是红的。"""
    _gen_arch(tmp_path)
    checker = ComplianceChecker(project_dir=str(tmp_path),
                                profile=load_profile("aspice_sys_v3.1"))
    sys2 = checker.run()["swe_sections"]["sys.2"]
    statuses = {bp["id"]: bp["status"] for bp in sys2["base_practices"]}
    assert statuses["SYS.2.BP2"] != "✅"


def test_swe_area_does_not_accept_sys_arch_document(tmp_path):
    """反假绿: SWE 区不得借系统架构文档蒙混（否则 SWE.2 凭空变绿）。"""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "system-architecture.md").write_text(
        "# 系统架构设计 (SYS.2)\n\n架构 architecture 组件 module 接口 interface\n"
        + "x" * 200, encoding="utf-8")

    checker = ComplianceChecker(str(tmp_path))
    assert checker._has_arch_document("SWE.2") is False
    assert checker._has_arch_document("SYS.2") is True
    assert checker._has_arch_document() is False  # 默认（不传 area）不放行
