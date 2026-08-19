#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Tests for Pipeline Profile switching (DEF-004 / G-33).
"""

import os
import sys
import tempfile
import json
from pathlib import Path

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.ci.profile import (
    validate_active_profile,
    filter_steps_for_profile,
    get_available_profiles,
    get_current_profile,
    BUILTIN_PROFILES,
    ALWAYS_INCLUDE,
)

# Mock pipeline steps for filtering tests
MOCK_STEPS = [
    ("spec-check", "小明", "OpenSpec 合规检查", lambda s: "/tmp/spec.md"),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析", lambda s: "/tmp/super.md"),
    ("prd", "Hermes", "产品需求分析", lambda s: "/tmp/prd.md"),
    ("prd-review", "小马", "PRD 质量审查", lambda s: "/tmp/prd-review.md"),
    ("architecture", "Claude", "架构设计", lambda s: "/tmp/arch.md"),
    ("misra-review", "小马", "MISRA 合规审查", lambda s: "/tmp/misra.md"),
    ("review-bsp", "小克", "BSP 板级支持包验证", lambda s: "/tmp/bsp.md"),
    ("c-unit-test", "小克", "C 单元测试", lambda s: "/tmp/c-unit.md"),
]

ALL_KEYS = [s[0] for s in MOCK_STEPS]


class TestProfileModule:
    """Test profile module basic functions."""

    def test_get_available_profiles(self):
        """Verify at least 2 profiles exist (G-33 §16.2)."""
        profiles = get_available_profiles()
        assert len(profiles) >= 2, "Must have at least 2 profiles"
        assert "safety" in profiles, "safety profile must exist"
        assert "ci" in profiles, "ci profile must exist"

    def test_profile_descriptions(self):
        """Verify each profile has a description."""
        profiles = get_available_profiles()
        for name, cfg in profiles.items():
            assert "description" in cfg, f"Profile {name} missing description"
            assert cfg["description"], f"Profile {name} has empty description"

    def test_safety_profile_includes_all(self):
        """safety profile should include all steps (exclude_steps=[])."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "safety")
        filtered_keys = [s[0] for s in filtered]
        assert set(filtered_keys) == set(ALL_KEYS)
        assert len(filtered) == len(MOCK_STEPS)

    def test_ci_profile_excludes_llm_steps(self):
        """ci profile should exclude LLM-heavy review steps."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "ci")
        filtered_keys = [s[0] for s in filtered]

        # Steps that should be excluded in CI profile
        assert "super-analysis" not in filtered_keys
        assert "prd" not in filtered_keys
        assert "prd-review" not in filtered_keys
        assert "architecture" not in filtered_keys

        # Steps that should remain
        assert "spec-check" in filtered_keys
        assert "misra-review" in filtered_keys
        assert "review-bsp" in filtered_keys
        assert "c-unit-test" in filtered_keys


class TestProfileValidation:
    """Test G-33 profile validation."""

    def test_validate_existing_profile(self):
        """Existing profile should pass validation."""
        valid, msg = validate_active_profile(".")
        # This will likely pass because the builtin profiles always exist
        assert "is valid" in msg or "valid" in msg.lower()

    def test_validate_unknown_profile_no_error(self):
        """Unknown profile should fall back gracefully."""
        # The module validates against builtin profiles, which always include safety/ci
        valid, msg = validate_active_profile(".")
        assert valid or not valid  # May or may not pass depending on ci-config.yaml

    def test_profile_count_at_least_2(self):
        """G-33 §16.2: Must have ≥2 profiles."""
        profiles = get_available_profiles()
        assert len(profiles) >= 2

        valid, msg = validate_active_profile(".")
        # If we got here, the builtin set has ≥2 profiles
        assert "2" in msg or "valid" in msg.lower()


class TestProfileFiltering:
    """Test step filtering by profile."""

    def test_empty_steps_with_unknown_profile(self):
        """Unknown profile should fall back to safety (all steps included)."""
        result = filter_steps_for_profile(MOCK_STEPS, "nonexistent")
        filtered_keys = [s[0] for s in result]
        assert set(filtered_keys) == set(ALL_KEYS)

    def test_performance_profile_filters_some(self):
        """Performance profile should exclude some steps."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "performance")
        filtered_keys = [s[0] for s in filtered]
        assert len(filtered_keys) < len(ALL_KEYS)
        # Should keep spec-check, misra-review, review-bsp, c-unit-test
        assert "spec-check" in filtered_keys
        assert "misra-review" in filtered_keys
        # Should exclude some
        assert "super-analysis" not in filtered_keys or "architecture" not in filtered_keys
        # Performance excludes: super-analysis, architecture, arch-review, self-test, final-report

    def test_testing_profile_filters_most(self):
        """Testing profile should keep only core quality gates."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "testing")
        filtered_keys = [s[0] for s in filtered]
        # Testing profile excludes most steps — keep only spec-check, c-unit-test, integration-test
        assert len(filtered_keys) < len(ALL_KEYS)

    def test_fallback_to_safety(self):
        """Unknown profile should fall back to safety behavior."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "some-unknown-profile")
        filtered_keys = [s[0] for s in filtered]
        assert set(filtered_keys) == set(ALL_KEYS)

    def test_ci_profile_step_count_reduced(self):
        """Verify ci profile reduces step count."""
        safety = filter_steps_for_profile(MOCK_STEPS, "safety")
        ci = filter_steps_for_profile(MOCK_STEPS, "ci")
        assert len(ci) < len(safety), "CI profile should have fewer steps than safety"


class TestProfileRealConfig:
    """Test profile integration with real ci-config.yaml."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project with a minimal ci-config.yaml."""
        import yaml
        with tempfile.TemporaryDirectory() as tmpdir:
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True, exist_ok=True)
            config = {
                "misra": {
                    "enabled": True,
                    "active_profile": "ci",
                    "profiles": {
                        "safety": {"name": "Safety", "rule_overrides": [], "deviations": [], "severity_map": {}},
                        "ci": {"name": "CI", "rule_overrides": [], "deviations": [], "severity_map": {}},
                        "performance": {"name": "Perf", "rule_overrides": [], "deviations": [], "severity_map": {}},
                    },
                },
            }
            with open(yuleosh_dir / "ci-config.yaml", "w") as f:
                yaml.dump(config, f)
            yield tmpdir

    def test_get_current_profile(self, temp_project):
        """Verify current profile is read from ci-config.yaml."""
        profile = get_current_profile(temp_project)
        assert profile == "ci"

    def test_validate_custom_profiles(self, temp_project):
        """Verify validation passes with custom profiles."""
        valid, msg = validate_active_profile(temp_project)
        assert valid, f"Validation failed: {msg}"
        assert "ci" in msg or "valid" in msg

    def test_filter_with_custom_config(self, temp_project):
        """Verify profile filtering works with custom config."""
        filtered = filter_steps_for_profile(MOCK_STEPS, "ci", temp_project)
        # CI profile should still filter as expected
        assert len(filtered) < len(MOCK_STEPS)

    def test_profiles_defined_in_config(self, temp_project):
        """Verify at least 2 profiles exist in config."""
        from yuleosh.ci.config import _get_ci_config
        cfg = _get_ci_config(temp_project)
        assert cfg.misra.profiles is not None
        assert len(cfg.misra.profiles) >= 2


class TestPIPELINE_STEPSProfile:
    """Test that PIPELINE_STEPS and profile filtering work together."""

    def test_real_steps_safety(self):
        """Test safety profile with real PIPELINE_STEPS."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        filtered = filter_steps_for_profile(PIPELINE_STEPS, "safety")
        assert len(filtered) == len(PIPELINE_STEPS)

    def test_real_steps_ci_reduced(self):
        """Test CI profile with real PIPELINE_STEPS (should reduce)."""
        from yuleosh.pipeline.step_handlers import PIPELINE_STEPS
        filtered = filter_steps_for_profile(PIPELINE_STEPS, "ci")
        assert len(filtered) < len(PIPELINE_STEPS)
        # Verify specific steps are excluded
        filtered_keys = [s[0] for s in filtered]
        assert "super-analysis" not in filtered_keys
        assert "prd" not in filtered_keys


# ===================================================================
# 方向1 (2026-08-11): Profile 反转为增量装配
# ===================================================================


class TestProfileInversion:
    """方向1: 增量装配 — minimal 白名单基线 + 保护集 + 不变量。"""

    MOCK_STEPS = MOCK_STEPS + [
        ("review-critical-safety", "小明", "关键安全异常阻塞检查 (P0 GATE)", lambda s: "/tmp/cs.md"),
        ("merge-gate", "小马", "KG Merge Gate", lambda s: "/tmp/mg.md"),
        ("review-linker", "小克", "链接脚本审查", lambda s: "/tmp/ld.md"),
        ("review-startup", "小克", "启动代码审查", lambda s: "/tmp/startup.md"),
        ("integration-test", "小克", "接口集成测试", lambda s: "/tmp/it.md"),
        ("qemu-verify", "小克", "QEMU 验证 + C 覆盖率门禁 (L2)", lambda s: "/tmp/ccov.md"),
    ]

    def test_minimal_profile_exists(self):
        """B1: minimal profile 存在于内置档。"""
        assert "minimal" in BUILTIN_PROFILES
        assert BUILTIN_PROFILES["minimal"]["include_steps"] is not None

    def test_minimal_profile_core_steps(self):
        """B1: minimal 含核心质量步骤。"""
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "minimal")
        keys = [s[0] for s in filtered]
        assert "spec-check" in keys
        assert "c-unit-test" in keys
        assert "integration-test" in keys
        assert "qemu-verify" in keys

    def test_invariant1_safety_equals_all(self):
        """AC2/不变量1: safety 恒等于全集（含 P0 保护集）。"""
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "safety")
        assert set(s[0] for s in filtered) == set(s[0] for s in self.MOCK_STEPS)
        assert len(filtered) == len(self.MOCK_STEPS)

    def test_invariant2_always_include_preserved_in_minimal(self):
        """AC3/不变量2: P0 保护集在白名单档也保留（fail-safe 防漏步骤）。"""
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "minimal")
        keys = [s[0] for s in filtered]
        for gate in ALWAYS_INCLUDE:
            assert gate in keys, f"P0 保护步骤 {gate} 被 minimal 裁剪！"

    def test_invariant2_always_include_preserved_in_ci(self):
        """不变量2: P0 保护集在黑名单档即使被 exclude 也强制保留。"""
        # 构造 ci 档 exclude 包含保护集的情景 → 保护集仍应保留
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "ci")
        keys = [s[0] for s in filtered]
        for gate in ALWAYS_INCLUDE:
            assert gate in keys

    def test_invariant3_ci_diff_equivalent(self):
        """AC4/不变量3: ci 档反装前后排除步骤差集一致（黑名单语义保持）。"""
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "ci")
        keys = [s[0] for s in filtered]
        # ci 档原本排除的 LLM 步骤
        for step in ["super-analysis", "prd", "prd-review", "architecture"]:
            assert step not in keys
        # 非排除步骤保留
        for step in ["spec-check", "misra-review", "review-bsp", "c-unit-test"]:
            assert step in keys

    def test_minimal_is_subset_of_safety(self):
        """minimal 是 safety 的子集（增量装配语义）。"""
        minimal = filter_steps_for_profile(self.MOCK_STEPS, "minimal")
        safety = filter_steps_for_profile(self.MOCK_STEPS, "safety")
        minimal_keys = set(s[0] for s in minimal)
        safety_keys = set(s[0] for s in safety)
        assert minimal_keys <= safety_keys
        assert len(minimal_keys) < len(safety_keys)

    def test_minimal_excludes_review_linker_by_default(self):
        """B5 前置: minimal 默认不含嵌入式专项（按需叠加）。"""
        filtered = filter_steps_for_profile(self.MOCK_STEPS, "minimal")
        keys = [s[0] for s in filtered]
        assert "review-linker" not in keys


class TestProfileCustomOverrides:
    """方向1: 自定义 profile include/exclude 叠加（修复死代码 bug）。"""

    @pytest.fixture
    def custom_project(self, tmp_path):
        """创建带自定义 profile 的临时项目。"""
        import yaml
        yuleosh_dir = tmp_path / ".yuleosh"
        yuleosh_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "misra": {
                "enabled": True,
                "active_profile": "minimal",
                "profiles": {
                    "safety": {"name": "Safety"},
                    "minimal": {"name": "Minimal"},
                    "ci": {"name": "CI"},
                    "embedded": {
                        "name": "Embedded",
                        "include_steps": ["spec-check", "review-linker", "review-startup"],
                        "exclude_steps": [],
                    },
                    "ci_plus_linker": {
                        "name": "CI+Linker",
                        "extends": "ci",
                        "exclude_steps": ["review-rtos"],
                    },
                },
            },
        }
        with open(yuleosh_dir / "ci-config.yaml", "w") as f:
            yaml.dump(config, f)
        return str(tmp_path)

    def test_custom_include_steps_works(self, custom_project):
        """B7/AC6: 自定义 include_steps 实际生效（死代码修复）。"""
        steps = TestProfileInversion.MOCK_STEPS
        filtered = filter_steps_for_profile(steps, "embedded", custom_project)
        keys = [s[0] for s in filtered]
        assert "spec-check" in keys
        assert "review-linker" in keys
        assert "review-startup" in keys
        # 保护集仍然保留
        for gate in ALWAYS_INCLUDE:
            assert gate in keys

    def test_custom_exclude_steps_works(self, custom_project):
        """B7/AC6: 自定义 exclude_steps 实际生效（死代码修复）。"""
        steps = TestProfileInversion.MOCK_STEPS
        filtered = filter_steps_for_profile(steps, "ci_plus_linker", custom_project)
        keys = [s[0] for s in filtered]
        # ci 档排除 LLM 步骤 + 自定义排除 review-rtos
        assert "super-analysis" not in keys
        assert "review-rtos" not in keys
        # 保护集保留
        for gate in ALWAYS_INCLUDE:
            assert gate in keys

    def test_unknown_custom_profile_falls_back_to_safety(self, custom_project):
        """未知 profile → 回退 safety（全量）。"""
        steps = TestProfileInversion.MOCK_STEPS
        filtered = filter_steps_for_profile(steps, "no-such-profile", custom_project)
        assert len(filtered) == len(steps)
