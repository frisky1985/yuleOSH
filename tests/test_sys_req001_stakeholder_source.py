"""T6 / SYS-REQ-001: 涉众需求源接入 + SYS.1 派生方向正位。

需求追溯: STAKE-01 → SYS-REQ-001

缺陷: SYS.1 恒由 spec（SWE.1 的输入）反推，sidecar 自述"SYS 系统需求向上
追溯至 SWE.1 软件需求（spec 派生）" —— 与 ASPICE 的 涉众需求 → SYS → SWE
方向相反，且**不标注降级**，审计时无法区分"做了涉众分析"与"拿 spec 反推"。

验收:
  ① 有涉众需求文件 → SYS-REQ 含 STAKE-xxx 映射且可核；
  ② 缺失 → 产物与 sidecar 明确标注降级来源，且机读字段存在。

反假绿红线: 涉众需求文件存在但无 STAKE-xxx 时，必须退回 spec-derived 并
如实标注，**不得**因"文件存在"就宣称涉众来源。
"""

import json
import os

from yuleosh.alm.traceability import load_sys_swe_trace
from yuleosh.pipeline.step_handlers.sys_layer import step_sys_requirements


def _make_session(tmp_path):
    os.environ["OSH_HOME"] = str(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    spec = tmp_path / "docs" / "spec.md"
    spec.write_text("# 车窗防夹\n\n## GPIO 控制\n\n系统应驱动 LED。\n",
                    encoding="utf-8")
    sess = type("S", (), {})()
    sess.project_dir = str(tmp_path)
    sess.spec_path = str(spec)
    sess.session_dir = str(tmp_path / ".osh" / "sessions" / "t6")
    return sess


def _sidecar(tmp_path):
    return json.loads(
        (tmp_path / ".osh" / "evidence" / "sys-to-swe-trace.json").read_text(
            encoding="utf-8"))


# ── ① 有涉众需求 → 正位派生 ─────────────────────────────────────────────

def test_stakeholder_source_derives_sys_req_with_stake_mapping(tmp_path):
    sess = _make_session(tmp_path)
    (tmp_path / "docs" / "stakeholder-requirements.md").write_text(
        "# 涉众需求\n\n"
        "- **STAKE-001**: 车辆应防止车窗夹伤乘客。\n"
        "- **STAKE-002**: 车窗应支持一键升降。\n", encoding="utf-8")

    step_sys_requirements(sess)
    doc = (tmp_path / "docs" / "system-requirements.md").read_text(encoding="utf-8")
    sc = _sidecar(tmp_path)

    assert "派生来源 (机读): `stakeholder`" in doc
    assert sc["source"] == "stakeholder"
    assert sc["sys_to_stake"] == {"SYS-REQ-001": "STAKE-001",
                                  "SYS-REQ-002": "STAKE-002"}
    # 文档内可核: 每条 SYS-REQ 显式挂 STAKE 上游（文档中 ID 以 ** 加粗）
    assert "**SYS-REQ-001** ← STAKE-001" in doc
    assert "**SYS-REQ-002** ← STAKE-002" in doc
    # 正位方向表述（不再声称"向上追溯至 SWE.1"）
    assert "涉众需求（STAKE-xxx）" in doc


# ── ② 缺失 → 显式降级标注 ───────────────────────────────────────────────

def test_missing_stakeholder_marks_degraded_source(tmp_path):
    sess = _make_session(tmp_path)  # 无 stakeholder-requirements.md

    step_sys_requirements(sess)
    doc = (tmp_path / "docs" / "system-requirements.md").read_text(encoding="utf-8")
    sc = _sidecar(tmp_path)

    assert "派生来源 (机读): `spec-derived`" in doc
    assert sc["source"] == "spec-derived"
    assert "降级" in sc["note"]
    assert "sys_to_stake" not in sc  # 无涉众来源就不得出现映射
    # 文档里也如实说明方向倒置
    assert "倒置" in doc


# ── ③ 反假绿 ────────────────────────────────────────────────────────────

def test_stakeholder_file_without_ids_falls_back_honestly(tmp_path):
    """文件在但无 STAKE-xxx → 不得宣称涉众来源。"""
    sess = _make_session(tmp_path)
    (tmp_path / "docs" / "stakeholder-requirements.md").write_text(
        "# 涉众需求\n\n（待补充，暂无编号需求）\n", encoding="utf-8")

    step_sys_requirements(sess)
    sc = _sidecar(tmp_path)

    assert sc["source"] == "spec-derived"
    assert "sys_to_stake" not in sc


def test_no_fabricated_stakeholder_ids(tmp_path):
    """无涉众需求时文档不得出现任何 STAKE- 编号。"""
    sess = _make_session(tmp_path)
    step_sys_requirements(sess)
    doc = (tmp_path / "docs" / "system-requirements.md").read_text(encoding="utf-8")
    assert "STAKE-" not in doc


# ── ④ 向后兼容 ──────────────────────────────────────────────────────────

def test_sidecar_stays_compatible_with_load_sys_swe_trace(tmp_path):
    sess = _make_session(tmp_path)
    (tmp_path / "docs" / "stakeholder-requirements.md").write_text(
        "- **STAKE-001**: 防夹。\n", encoding="utf-8")
    step_sys_requirements(sess)

    loaded = load_sys_swe_trace(str(tmp_path))
    # alm/traceability 与 report_builder 依赖 sys_to_swe，新增字段不得破坏它
    assert loaded["sys_to_swe"] == {"SYS-REQ-001": "SWE.1"}
    assert loaded["note"]
