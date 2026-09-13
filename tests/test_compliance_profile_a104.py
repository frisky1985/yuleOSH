"""A1-04 决策落地回归测试。

覆盖三项设计决策 + 一个阻断性 bug 修复：
- 决策1：evidence.type 强制白名单（拼写漂移 → ProfileError，不再静默假阴性）
- 决策2：过程域可选 order 字段控制报告章节排序
- 决策3：过程域顶层键命名约定 `标准名.过程域`（仅约定，非强制）
- 阻断修复：run() 不再仅识别 swe.* 键，ISO 26262 等非 SWE 标准可被正常消费
"""

import pytest
import yaml
from pathlib import Path

from yuleosh.compliance.profile import (
    load_profile,
    StandardProfile,
    ProfileError,
    _EVIDENCE_TYPE_ENUM,
)
from yuleosh.compliance.compliance_checker import ComplianceChecker


def _write_profile(tmp_path: Path, data: dict, name: str = "p") -> str:
    p = tmp_path / f"{name}.yaml"
    # sort_keys=False 保留文档书写顺序，真实反映作者意图（order 字段缺省时按此序）
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(tmp_path)


# ── 决策1：evidence.type 强制白名单 ──────────────────────────────────

def test_evidence_type_whitelist_rejects_typo(tmp_path):
    data = {
        "meta": {"standard": "X", "version": "1"},
        "area1": {
            "id": "A1",
            "base_practices": [
                {"id": "BP1", "check": ["c"], "output_evidence": [
                    {"type": "documnt", "path": "docs/x.md"}  # 拼写错误
                ]},
            ],
        },
    }
    _write_profile(tmp_path, data, "bad")
    with pytest.raises(ProfileError) as exc:
        load_profile("bad", profile_dir=str(tmp_path))
    assert "type" in str(exc.value).lower()
    assert "documnt" in str(exc.value)


def test_evidence_type_valid_enum_accepted(tmp_path):
    data = {
        "meta": {"standard": "X", "version": "1"},
        "area1": {
            "id": "A1",
            "base_practices": [
                {"id": "BP1", "check": ["c"], "output_evidence": [
                    {"type": t, "path": f"p/{t}.x"} for t in sorted(_EVIDENCE_TYPE_ENUM)
                ]},
            ],
        },
    }
    _write_profile(tmp_path, data, "ok")
    prof = load_profile("ok", profile_dir=str(tmp_path))
    types = {ev.type for bp in prof.areas[0].base_practices for ev in bp.output_evidence}
    assert types == set(_EVIDENCE_TYPE_ENUM)


# ── 决策2 + 阻断修复：order 排序 & 非 SWE 键被消费 ───────────────────

@pytest.fixture
def iso26262_profile_dict():
    return {
        "meta": {"standard": "ISO26262", "version": "2018", "description": "Part6/Part8"},
        # 注意：先写 part8、后写 part6；part6 带 order=1 应排在前
        "iso26262.part8": {
            "id": "ISO26262-Part8", "title": "Support Processes", "description": "d8",
            "base_practices": [
                {"id": "BP8.1", "title": "t", "check": ["c1"], "output_evidence": [
                    {"type": "document", "path": "docs/part8.md", "description": "e1"}]},
            ],
        },
        "iso26262.part6": {
            "id": "ISO26262-Part6", "title": "SW Product Dev", "description": "d6", "order": 1,
            "base_practices": [
                {"id": "BP6.1", "title": "t", "check": ["c1"], "output_evidence": [
                    {"type": "source", "path": "src/", "description": "e1"}]},
            ],
        },
    }


def test_iso26262_non_swe_keys_consumed(iso26262_profile_dict, tmp_path):
    """阻断修复回归：run() 不再仅识别 swe.*，ISO 26262 非 SWE 键须被消费。"""
    _write_profile(tmp_path, iso26262_profile_dict, "iso26262")
    prof = load_profile("iso26262", profile_dir=str(tmp_path))
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=prof)
    report = checker.run()
    sections = list(report["swe_sections"].keys())
    assert sections, "阻断 bug 复现：ISO 26262 过程域被整组漏掉，报告为空"
    assert "iso26262.part6" in sections and "iso26262.part8" in sections


def test_order_field_sorts_areas(iso26262_profile_dict, tmp_path):
    """决策2：order 字段控制章节顺序，文档书写顺序被覆盖。"""
    _write_profile(tmp_path, iso26262_profile_dict, "iso26262")
    prof = load_profile("iso26262", profile_dir=str(tmp_path))
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=prof)
    report = checker.run()
    sections = list(report["swe_sections"].keys())
    # part6 有 order=1 虽写在后，应排在第一位
    assert sections[0] == "iso26262.part6"


def test_order_preserved_when_absent(tmp_path):
    """无 order 字段时保持 yaml 文档序（ASPICE 现状不受影响）。"""
    data = {
        "meta": {"standard": "ASPICE", "version": "3.1"},
        "swe.2": {"id": "SWE.2", "title": "t2", "base_practices": [
            {"id": "BP2.1", "check": ["c"], "output_evidence": [
                {"type": "document", "path": "docs/x.md"}]}]},
        "swe.1": {"id": "SWE.1", "title": "t1", "base_practices": [
            {"id": "BP1.1", "check": ["c"], "output_evidence": [
                {"type": "document", "path": "docs/y.md"}]}]},
    }
    _write_profile(tmp_path, data, "aspice")
    prof = load_profile("aspice", profile_dir=str(tmp_path))
    checker = ComplianceChecker(project_dir=str(tmp_path), profile=prof)
    report = checker.run()
    # 文档序：swe.2 先、swe.1 后（两者都无 order）
    assert list(report["swe_sections"].keys()) == ["swe.2", "swe.1"]


def test_order_field_parsed_into_model(iso26262_profile_dict, tmp_path):
    _write_profile(tmp_path, iso26262_profile_dict, "iso26262")
    prof = load_profile("iso26262", profile_dir=str(tmp_path))
    by_key = {a.key: a for a in prof.areas}
    assert by_key["iso26262.part6"].order == 1
    assert by_key["iso26262.part8"].order is None
    # to_template_dict 仅在 order 非 None 时透传
    tmpl = prof.to_template_dict()
    assert tmpl["iso26262.part6"]["order"] == 1
    assert "order" not in tmpl["iso26262.part8"]


def test_area_key_convention_standard_prefix(iso26262_profile_dict, tmp_path):
    """决策3：顶层键采用 `标准名.过程域` 约定，可被 loader 正常解析（无代码改动）。"""
    _write_profile(tmp_path, iso26262_profile_dict, "iso26262")
    prof = load_profile("iso26262", profile_dir=str(tmp_path))
    assert [a.id for a in prof.areas] == ["ISO26262-Part8", "ISO26262-Part6"]
