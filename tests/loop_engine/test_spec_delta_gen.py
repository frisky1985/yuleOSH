#!/usr/bin/env python3
"""
SpecDelta 生成器测试。
"""

import os
import json
import tempfile
import pytest

from yuleosh.loop_engine.spec_delta_gen import (
    SpecDeltaGenerator,
    SpecDelta,
    ChangeType,
)


# ═══════════════════════════════════════════════════════════════════════
# SpecDelta 数据类
# ═══════════════════════════════════════════════════════════════════════

def test_spec_delta_defaults():
    """SpecDelta 默认值。"""
    d = SpecDelta(req_id="RS-001", change_type=ChangeType.MODIFIED)
    assert d.req_id == "RS-001"
    assert d.change_type == ChangeType.MODIFIED
    assert d.timestamp != ""
    assert d.generator_version == "2.5.0"


def test_spec_delta_change_type_coercion():
    """字符串 change_type 应自动转换为枚举。"""
    d = SpecDelta(req_id="RS-001", change_type="needs_review")
    assert d.change_type == ChangeType.NEEDS_REVIEW


def test_spec_delta_to_dict():
    """SpecDelta.to_dict() 应包含所有字段。"""
    d = SpecDelta(
        req_id="RS-001",
        change_type=ChangeType.MODIFIED,
        reason="CI fail: test_brake",
        attributed_test="test_brake",
        tags=["cicd"],
    )
    di = d.to_dict()
    assert di["req_id"] == "RS-001"
    assert di["change_type"] == "modified"
    assert di["reason"] == "CI fail: test_brake"
    assert di["attributed_test"] == "test_brake"
    assert "cicd" in di["tags"]


def test_spec_delta_to_markdown():
    """SpecDelta.to_markdown() 生成正确格式。"""
    d = SpecDelta(
        req_id="RS-001-01",
        change_type=ChangeType.NEEDS_REVIEW,
        reason="CI test failure",
        attributed_test="test_brake_light",
    )
    md = d.to_markdown()
    assert "### RS-001-01 [needs_review]" in md
    assert "**原因**: CI test failure" in md
    assert "**归因测试**: `test_brake_light`" in md


def test_spec_delta_repr():
    """repr 应清晰。"""
    d = SpecDelta(req_id="RS-001", change_type="modified")
    r = repr(d)
    assert "RS-001" in r
    assert "modified" in r


# ═══════════════════════════════════════════════════════════════════════
# SpecDeltaGenerator
# ═══════════════════════════════════════════════════════════════════════

def test_gen_basic():
    """基础生成。"""
    g = SpecDeltaGenerator()
    d = g.generate("RS-001", ChangeType.MODIFIED, reason="review change")
    assert d.req_id == "RS-001"
    assert d.change_type == ChangeType.MODIFIED
    assert d.attributed_source == "loop_engine"


def test_gen_from_test_failure():
    """从测试失败生成。"""
    g = SpecDeltaGenerator()
    d = g.generate_from_test_failure(
        test_name="test_brake_light",
        req_id="RS-001",
        error_message="AssertionError: expected True",
    )
    assert d.change_type == ChangeType.NEEDS_REVIEW
    assert d.attributed_test == "test_brake_light"
    assert "ci_failure" in d.tags
    assert "needs_review" in d.tags
    assert "defect_backprop" in d.tags
    assert d.attributed_source == "ci.failure"


def test_gen_with_metadata():
    """生成时带额外 metadata。"""
    g = SpecDeltaGenerator()
    d = g.generate("RS-002", "modified", reason="update",
                   some_extra="value", numeric=42)
    assert d.metadata["some_extra"] == "value"
    assert d.metadata["numeric"] == 42


def test_gen_default_tags():
    """default_tags 应合并。"""
    g = SpecDeltaGenerator(default_tags=["auto"])
    d = g.generate("RS-001", "modified", reason="test",
                   tags=["extra"])
    assert "auto" in d.tags
    assert "extra" in d.tags


def test_to_json():
    """to_json() 应序列化为 JSON 数组。"""
    g = SpecDeltaGenerator()
    d1 = g.generate("RS-001", "modified", reason="r1")
    d2 = g.generate("RS-002", "added", reason="r2")
    js = g.to_json([d1, d2])
    parsed = json.loads(js)
    assert len(parsed) == 2
    assert parsed[0]["req_id"] == "RS-001"
    assert parsed[1]["req_id"] == "RS-002"


def test_append_to_file():
    """append_to_file() 应写入/追加到文件。"""
    with tempfile.TemporaryDirectory() as tmp:
        g = SpecDeltaGenerator(output_dir=tmp)
        d = g.generate("RS-001", "modified", reason="test")

        path = g.append_to_file(d, filepath=os.path.join(tmp, "sd.md"))
        assert os.path.exists(path)

        with open(path) as f:
            content = f.read()
        assert "RS-001" in content
        assert "modified" in content

        # 追加第二条
        d2 = g.generate("RS-002", "added", reason="test2")
        g.append_to_file(d2, filepath=path)
        with open(path) as f:
            content2 = f.read()
        assert "RS-002" in content2


# ═══════════════════════════════════════════════════════════════════════
# 类方法
# ═══════════════════════════════════════════════════════════════════════

def test_from_test_failure_simple():
    """类方法快速生成。"""
    d = SpecDeltaGenerator.from_test_failure_simple(
        test_name="test_foo",
        req_id="RS-001",
        error_message="failed",
    )
    assert d.req_id == "RS-001"
    assert d.change_type == ChangeType.NEEDS_REVIEW
    assert d.attributed_test == "test_foo"
