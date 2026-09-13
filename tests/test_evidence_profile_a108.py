"""A1-08: evidence 消费方适配 — gap check 改读 profile + OEM 模板注册表接口.

覆盖:
- aspice_gap_check 默认走 load_profile 路径，并把 StandardProfile 注入 ComplianceChecker
- 未知 profile 名透传 ProfileNotFoundError（调用方可据此提示可用清单）
- register_oem_template 在运行时挂入注册表，get_template 可检索；缺必填字段抛 ValueError
"""

import pytest
from types import SimpleNamespace
from unittest import mock

from yuleosh.compliance.profile import ProfileNotFoundError
from yuleosh.evidence import aspice_check
from yuleosh.evidence.oem_templates import (
    OEM_TEMPLATES,
    get_template,
    register_oem_template,
)

# 最小 checker 报告，足以驱动 _format_gap_markdown / _format_gap_json
_REPORT = {
    "generated_at": "2026-07-10T12:00:00",
    "project_dir": "/p",
    "standard": "ASPICE",
    "version": "3.1",
    "summary": {"total_bps": 1, "passed": 0, "partial": 1, "failed": 0},
    "swe_sections": {
        "swe.1": {
            "id": "SWE.1",
            "title": "Requirements",
            "description": "",
            "base_practices": [
                {
                    "id": "SWE.1.BP1",
                    "title": "Specify requirements",
                    "status": "⚠️",
                    "passed_checks": 1,
                    "failed_checks": 2,
                    "total_checks": 3,
                    "details": ["  ❌ 缺少需求文档"],
                },
            ],
        },
    },
}


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
@mock.patch("yuleosh.evidence.aspice_check.load_profile")
def test_aspice_gap_check_default_uses_profile(mock_load, mock_checker_cls):
    """GIVEN 默认调用 WHEN gap check THEN 走 load_profile 并注入 profile."""
    fake_profile = SimpleNamespace(standard="ASPICE", version="3.1")
    mock_load.return_value = fake_profile
    mock_checker_cls.return_value.run.return_value = _REPORT

    result = aspice_check.aspice_gap_check(project_dir="/p")

    mock_load.assert_called_once_with("aspice_v3.1")
    mock_checker_cls.assert_called_once_with(project_dir="/p", profile=fake_profile)
    assert "SWE.1" in result


@mock.patch("yuleosh.evidence.aspice_check.load_profile")
def test_aspice_gap_check_unknown_profile_propagates(mock_load):
    """GIVEN 未知 profile WHEN gap check THEN 透传 ProfileNotFoundError."""
    mock_load.side_effect = ProfileNotFoundError("nope", [], ["aspice_v3.1"])

    with pytest.raises(ProfileNotFoundError):
        aspice_check.aspice_gap_check(project_dir="/p", profile_name="nope")

    mock_load.assert_called_once_with("nope")


@mock.patch("yuleosh.evidence.aspice_check.ComplianceChecker")
@mock.patch("yuleosh.evidence.aspice_check.load_profile")
def test_aspice_gap_check_template_path_backward_compat(mock_load, mock_checker_cls):
    """GIVEN template_path WHEN gap check THEN 不走 load_profile，直接用 template_path."""
    mock_checker_cls.return_value.run.return_value = _REPORT

    aspice_check.aspice_gap_check(
        project_dir="/p", template_path="/fake/t.yaml"
    )

    mock_load.assert_not_called()
    mock_checker_cls.assert_called_once_with(
        project_dir="/p", template_path=mock.ANY
    )


def test_register_oem_template_and_lookup():
    """GIVEN 合法模板 WHEN register THEN get_template 可检索."""
    name = "a108test"
    assert name not in OEM_TEMPLATES
    tmpl = {
        "column_map": {"id": "ID"},
        "required_columns": ["id"],
        "sort_key": "id",
        "sort_reverse": False,
        "extra_columns": [],
        "header_style": "bold",
    }
    register_oem_template(name, tmpl)
    try:
        assert get_template(name) is tmpl
    finally:
        OEM_TEMPLATES.pop(name, None)


def test_register_oem_template_rejects_missing_fields():
    """GIVEN 缺 column_map WHEN register THEN 抛 ValueError."""
    with pytest.raises(ValueError):
        register_oem_template("bad", {"required_columns": []})
    with pytest.raises(ValueError):
        register_oem_template("bad2", {"column_map": {}})
