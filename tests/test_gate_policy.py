#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Gate Policy Matrix 单元测试 (方向3, 2026-08-11).

覆盖:
  - resolve_gate 纯函数三档语义
  - 默认矩阵关键门禁 (review-critical-safety / merge-gate = block)
  - ci-config.yaml gate_policy 覆盖
  - _propagate_step_verdict 按门禁强度分流 (block 中断 / warn 继续 / info 仅记录)
"""

import json
import os
import sys
from pathlib import Path

import pytest

from yuleosh.ci.gate_policy import (
    DEFAULT_GATE_POLICY,
    GATE_BLOCK,
    GATE_INFO,
    GATE_WARN,
    load_gate_policy,
    resolve_gate,
)


# ------------------------------------------------------------------
# resolve_gate 纯函数
# ------------------------------------------------------------------


class TestResolveGate:
    def test_unknown_step_defaults_to_warn(self):
        """未声明步骤 → warn（现状行为保持）。"""
        assert resolve_gate("no-such-step") == GATE_WARN

    def test_empty_step_key_defaults_to_warn(self):
        assert resolve_gate("") == GATE_WARN

    def test_critical_safety_blocks_by_default(self):
        """⛔ P0 GATE 默认 block。"""
        assert resolve_gate("review-critical-safety") == GATE_BLOCK

    def test_merge_gate_blocks_by_default(self):
        assert resolve_gate("merge-gate") == GATE_BLOCK

    def test_coverage_gate_blocks_by_default(self):
        assert resolve_gate("c-coverage-gate") == GATE_BLOCK

    def test_regular_review_warns_by_default(self):
        """普通 review 步骤默认 warn（现状：记 errors 不断链）。"""
        assert resolve_gate("review-linker") == GATE_WARN
        assert resolve_gate("misra-review") == GATE_WARN

    def test_info_steps(self):
        assert resolve_gate("spec-check") == GATE_INFO
        assert resolve_gate("final-report") == GATE_INFO

    def test_policy_override(self):
        """显式 policy 覆盖默认。"""
        policy = {"review-linker": GATE_BLOCK}
        assert resolve_gate("review-linker", policy) == GATE_BLOCK
        assert resolve_gate("review-rtos", policy) == GATE_WARN  # 未覆盖 → 默认

    def test_invalid_policy_value_falls_back(self):
        """非法档位 → 默认 warn。"""
        policy = {"review-linker": "explode"}
        assert resolve_gate("review-linker", policy) == GATE_WARN

    def test_default_policy_shape(self):
        """默认矩阵结构：block 集合是关键门禁。"""
        block_keys = [k for k, v in DEFAULT_GATE_POLICY.items() if v == GATE_BLOCK]
        assert "review-critical-safety" in block_keys
        assert "merge-gate" in block_keys
        assert "c-coverage-gate" in block_keys
        assert "coverage-gate" in block_keys
        assert "test-qualification" in block_keys


# ------------------------------------------------------------------
# load_gate_policy — ci-config.yaml 覆盖
# ------------------------------------------------------------------


class TestLoadGatePolicy:
    def test_no_config_returns_defaults(self, tmp_path):
        """无 ci-config.yaml → 默认矩阵。"""
        policy = load_gate_policy(str(tmp_path))
        assert policy["review-critical-safety"] == GATE_BLOCK
        # 未显式声明的步骤由 resolve_gate 兜底为 warn
        assert resolve_gate("review-linker", policy) == GATE_WARN

    def test_config_override(self, tmp_path):
        """ci.gate_policy 覆盖默认。"""
        cfg_dir = tmp_path / ".yuleosh"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "ci-config.yaml").write_text(
            "ci:\n"
            "  gate_policy:\n"
            "    review-critical-safety: warn\n"   # 降级（显式）
            "    review-linker: block\n"           # 升级（显式）
            "    unknown-step: info\n"
        )
        policy = load_gate_policy(str(tmp_path))
        assert policy["review-critical-safety"] == GATE_WARN
        assert policy["review-linker"] == GATE_BLOCK
        assert policy["unknown-step"] == GATE_INFO
        # 未覆盖的保持默认
        assert policy["merge-gate"] == GATE_BLOCK

    def test_invalid_level_ignored(self, tmp_path):
        """非法档位被忽略并告警，不炸。"""
        cfg_dir = tmp_path / ".yuleosh"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "ci-config.yaml").write_text(
            "ci:\n"
            "  gate_policy:\n"
            "    review-linker: nope\n"
        )
        policy = load_gate_policy(str(tmp_path))
        # 无效覆盖被忽略 → resolve_gate 兜底为 warn
        assert resolve_gate("review-linker", policy) == GATE_WARN


# ------------------------------------------------------------------
# CiConfig 解析 — gate_policy 字段
# ------------------------------------------------------------------


class TestCiConfigGatePolicy:
    def test_config_parses_gate_policy(self, tmp_path, monkeypatch):
        from yuleosh.ci.config import load_ci_config

        cfg_dir = tmp_path / ".yuleosh"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "ci-config.yaml").write_text(
            "ci:\n"
            "  gate_policy:\n"
            "    review-linker: block\n"
        )
        monkeypatch.chdir(tmp_path)
        cfg = load_ci_config(str(tmp_path))
        assert cfg.gate_policy == {"review-linker": "block"}

    def test_default_empty_gate_policy(self, tmp_path):
        from yuleosh.ci.config import load_ci_config

        cfg = load_ci_config(str(tmp_path))
        assert cfg.gate_policy == {}


# ------------------------------------------------------------------
# _propagate_step_verdict 分流 (orchestrator)
# ------------------------------------------------------------------


@pytest.fixture
def session_fixture(tmp_path):
    """Minimal PipelineSession-like object for verdict propagation tests."""
    from yuleosh.pipeline.session import PipelineSession

    spec = tmp_path / "spec.md"
    spec.write_text("# Test Spec\n")
    s = PipelineSession("test-session", str(spec))
    s.add_step("review-linker", "小克", "链接脚本审查")
    s.start_step(0)
    return s


class TestVerdictPropagation:
    def _write_verdict(self, tmp_path, status: str) -> Path:
        p = tmp_path / "review.json"
        p.write_text(json.dumps({"status": status}))
        return p

    def test_warn_verdict_records_error_continues(self, session_fixture, tmp_path):
        """warn 档（默认）：verdict failed → errors 记录，返回 None。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        out = self._write_verdict(tmp_path, "failed")
        result = _propagate_step_verdict(
            session_fixture, 0, "review-linker", str(out)
        )
        assert result is None
        assert session_fixture.errors  # 记录了警告
        assert session_fixture.status != "failed"

    def test_block_verdict_interrupts(self, session_fixture, tmp_path):
        """block 档（P0 GATE）：verdict failed → 返回 "block"，status=failed。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        out = self._write_verdict(tmp_path, "failed")
        result = _propagate_step_verdict(
            session_fixture, 0, "review-critical-safety", str(out)
        )
        assert result == "block"
        assert session_fixture.status == "failed"
        assert session_fixture.errors

    def test_info_verdict_no_error_entry(self, session_fixture, tmp_path):
        """info 档：verdict failed → 仅 step detail，errors 无新增。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        out = self._write_verdict(tmp_path, "failed")
        result = _propagate_step_verdict(
            session_fixture, 0, "spec-check", str(out)
        )
        assert result is None
        assert session_fixture.errors == []  # info 不进 errors

    def test_warn_verdict_no_json(self, session_fixture):
        """无 JSON artifact → 无操作。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        result = _propagate_step_verdict(session_fixture, 0, "review-linker", "")
        assert result is None
        assert session_fixture.errors == []

    def test_retry_verdict_records_info(self, session_fixture, tmp_path):
        """retry/warn verdict → 记录但不阻断（legacy 语义保持）。"""
        from yuleosh.pipeline.orchestrator import _propagate_step_verdict

        out = self._write_verdict(tmp_path, "retry")
        result = _propagate_step_verdict(
            session_fixture, 0, "review-linker", str(out)
        )
        assert result is None
        assert session_fixture.errors
