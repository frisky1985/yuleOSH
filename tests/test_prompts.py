# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for centralized prompt templates in pipeline/prompts.py.

Verifies:
  - Each prompt builder returns (system_prompt, user_prompt) tuples
  - Prompts contain expected content markers (step-specific keywords)
  - Prompts handle optional inputs gracefully (empty strings, None, empty lists)
  - Token efficiency: prompts stay under reasonable limits
  - Integration: prompt builders used by step handlers produce valid prompts
"""

import os
import sys
from pathlib import Path

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def sample_spec_content():
    return (
        "# Test Spec\n\n"
        "### Req-RS-001: Authentication\n"
        "- The system SHALL authenticate users via OAuth2.\n"
        "- The system SHOULD support refresh tokens.\n\n"
        "### Req-SWR-001.1: Login Page\n"
        "- The login page SHALL have email and password fields.\n"
        "- The login page SHALL validate input before submission.\n\n"
        "### GIVEN a user with valid credentials\n"
        "WHEN they submit the login form\n"
        "THEN they are redirected to the dashboard\n"
    )


@pytest.fixture
def sample_requirements():
    return [
        {
            "name": "Req-RS-001: Authentication",
            "shall_statements": [
                "- The system SHALL authenticate users via OAuth2.",
                "- The system SHOULD support refresh tokens.",
            ],
        },
        {
            "name": "Req-SWR-001.1: Login Page",
            "shall_statements": [
                "- The login page SHALL have email and password fields.",
                "- The login page SHALL validate input before submission.",
            ],
        },
    ]


@pytest.fixture
def sample_scenarios():
    return [
        "GIVEN a user with valid credentials",
        "WHEN they submit the login form",
        "THEN they are redirected to the dashboard",
    ]


@pytest.fixture
def sample_source_files():
    return [
        {"path": "src/main.py", "lines": 50, "content": "def main(): pass\n"},
        {"path": "src/utils.py", "lines": 30, "content": "def helper(): pass\n"},
    ]


@pytest.fixture
def sample_steps():
    return [
        {"step": 1, "name": "spec-check", "agent": "小明", "status": "completed"},
        {"step": 2, "name": "super-analysis", "agent": "小明", "status": "completed"},
        {"step": 3, "name": "prd", "agent": "Hermes", "status": "completed"},
        {"step": 4, "name": "internal-review", "agent": "小明", "status": "completed"},
        {"step": 5, "name": "architecture", "agent": "Claude", "status": "failed"},
    ]


# ===================================================================
# S.U.P.E.R Analysis prompt
# ===================================================================

class TestBuildSuperAnalysisPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        system, user = build_super_analysis_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_super_keywords(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        system, _ = build_super_analysis_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert "S.U.P.E.R" in system or "Situation" in system
        assert "Understanding" in system
        assert "Priority" in system

    def test_user_prompt_contains_spec_content(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        _, user = build_super_analysis_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert "OAuth2" in user
        assert "Requirements found: 2" in user
        assert "SHALL statements: 4" in user

    def test_handles_empty_requirements(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        system, user = build_super_analysis_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=[],
            scenarios=[],
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "Requirements found: 0" in user

    def test_token_efficiency(self, sample_spec_content, sample_requirements, sample_scenarios):
        """Prompt should not exceed reasonable token limits."""
        from yuleosh.pipeline.prompts import build_super_analysis_prompt

        system, user = build_super_analysis_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        # Rough estimate: 1 token ≈ 4 chars
        estimated_tokens = (len(system) + len(user)) / 4
        assert estimated_tokens < 8000, f"Prompt too large: ~{estimated_tokens:.0f} tokens"


# ===================================================================
# PRD prompt
# ===================================================================

class TestBuildPrdPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, user = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_prd_sections(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, _ = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert "Product Overview" in system
        assert "User Stories" in system
        assert "Acceptance Criteria" in system
        assert "Out of Scope" in system

    def test_timing_metric_semantics_preserved(self, sample_spec_content, sample_requirements, sample_scenarios):
        """r22 复盘 (2026-08-20): PRD AC 时序指标必须保留 spec 分段语义。

        历史根因: prompt 示例 "50 ms pinch response" 把反转触发时间（50ms）
        误当检测时间，诱导 LLM 把 AC-003 写成 "50ms 内检测到防夹"（实际
        spec 契约 = 200ms 检测窗口 + 50ms 反转 ≈ 250ms 总响应）。修复后
        prompt 必须: ① 示例用总响应 + 分段组合; ② 含数值一致性纪律。
        """
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, _ = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        # 正确示例: 总响应 + 分段语义
        assert "250 ms total pinch response" in system
        assert "200 ms detection window + 50 ms reversal" in system
        # 纪律段: 禁止把总响应误写为分段值
        assert "数值一致性纪律" in system
        assert "50ms 内检测到防夹" in system  # 反例明确列出
        # 旧错误示例必须消失（50 ms pinch response 单值示例）
        assert "50 ms pinch response" not in system

    def test_out_of_scope_and_counting_discipline(self, sample_spec_content, sample_requirements, sample_scenarios):
        """r22 p9 复盘: Out-of-Scope 不得裁剪 spec 未限制的功能; 头部计数口径; 接口权威源。

        历史根因: PRD 自行声明 'Anti-pinch in manual mode' 为 Out of Scope
        （spec SW-004 无模式限制），claude-review 3 blockers 拦截 —— 若被
        codegen 采信会裁剪手动防夹（安全回归）。prompt 必须含纪律约束。
        """
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, _ = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        # Out-of-Scope 纪律段存在
        assert "Out of Scope 不得声明 spec 未限制的功能" in system
        assert "Anti-pinch in manual mode" in system  # 反例明确列出
        # 计数口径纪律
        assert "头部计数口径" in system
        assert "FRs: N (P0 x + P1 y)" in system
        # 接口权威源纪律
        assert "接口契约权威源" in system
        assert "src/app/include" in system

    def test_project_asil_injected_when_configured(self, sample_spec_content, sample_requirements, sample_scenarios):
        """r21b (claude-review minor): PRD 自封 ASIL-B/C 而 spec 未分级 —
        project_asil 注入后 prompt 必须携带 ASIL 纪律约束。
        2026-08-18 r21h: 配置声明时必须强制使用该等级, 不得因 spec 未提
        ASIL 就声称"不声明" (r21h PRD 与架构/测试计划跨工件不一致)。"""
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, _ = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
            project_asil="ASIL_B",
        )
        assert "ASIL discipline" in system
        assert "ASIL_B" in system
        assert "IS DECLARED by the platform config" in system
        assert "Do NOT invent a DIFFERENT ASIL class" in system
        assert "Do NOT claim the project has no ASIL level" in system

    def test_no_asil_still_injects_discipline(self, sample_spec_content, sample_requirements, sample_scenarios):
        """2026-08-18 r21e: 未配置 ASIL → 纪律段仍必须注入 (禁止自封)。

        r21e PRD 自造 'ASIL_B (平台配置)' 的根因正是 project_asil='' 时
        整段不注入 → LLM 自由发挥。无 ASIL 时 prompt 必须明确禁止自封。
        """
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, _ = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
        )
        assert "ASIL discipline" in system
        assert "does NOT declare an ASIL level" in system
        assert "Do NOT invent or self-declare an ASIL class" in system
        assert "ASIL level TBD by HARA" in system

    def test_includes_super_analysis_when_provided(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_prd_prompt

        _, user = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
            super_analysis_content="# S.U.P.E.R Analysis\n\nTest analysis content.",
        )
        assert "S.U.P.E.R. Analysis" in user
        assert "Test analysis content" in user

    def test_handles_empty_super_analysis(self, sample_spec_content, sample_requirements, sample_scenarios):
        from yuleosh.pipeline.prompts import build_prd_prompt

        _, user = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
            super_analysis_content="",
        )
        assert "S.U.P.E.R. Analysis" not in user  # Should not include when empty

    def test_handles_empty_requirements(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_prd_prompt

        system, user = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=[],
            scenarios=[],
        )
        assert "Requirements found: 0" in user


# ===================================================================
# Architecture prompt
# ===================================================================

class TestBuildArchitecturePrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        system, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            directories=["src", "src/api"],
            source_files=["src/main.py", "src/api/router.py"],
            tech_stack=["Python"],
            source_tree_str="src/\n  main.py\n  api/\n    router.py",
            key_file_snippets=["### src/main.py\n```\ndef main(): pass\n```"],
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_architecture_keywords(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        system, _ = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            directories=["src"],
            source_files=["src/main.py"],
            tech_stack=["Python"],
            source_tree_str="src/\n  main.py",
            key_file_snippets=[],
        )
        assert "Director" in system or "Directory" in system
        assert "ADR" in system or "design" in system.lower()

    def test_user_prompt_contains_tech_stack(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        _, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            directories=["src"],
            source_files=["src/main.py"],
            tech_stack=["Python", "React"],
            source_tree_str="src/\n  main.py",
            key_file_snippets=[],
        )
        assert "Python" in user
        assert "React" in user

    def test_handles_empty_source(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        system, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            directories=[],
            source_files=[],
            tech_stack=[],
            source_tree_str="(no source files found)",
            key_file_snippets=[],
        )
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_handles_empty_tech_stack_defaults_to_python(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        _, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            directories=["src"],
            source_files=["src/main.py"],
            tech_stack=[],
            source_tree_str="src/\n  main.py",
            key_file_snippets=[],
        )
        assert "Python" in user  # Default fallback

    def test_includes_repo_facts_when_provided(self, sample_spec_content, sample_source_files):
        """2026-08-18 r21f minor: 架构文档测试基建描述必须与仓库事实一致。"""
        from yuleosh.pipeline.prompts import build_architecture_prompt

        system, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="demo",
            directories=["src/app"],
            source_files=["src/app/main.c"],
            tech_stack=["C"],
            source_tree_str="src/app/main.c",
            key_file_snippets=[],
            repo_facts="# Repository Facts\n- Test framework: custom-Check",
        )
        assert "Repository Facts" in user
        assert "custom-Check" in user
        assert "test infrastructure descriptions MUST match" in system

    def test_omits_repo_facts_when_empty(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_architecture_prompt

        _, user = build_architecture_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="demo",
            directories=["src"],
            source_files=["src/main.c"],
            tech_stack=["C"],
            source_tree_str="src/main.c",
            key_file_snippets=[],
        )
        assert "Repository Facts" not in user


# ===================================================================
# Development prompt
# ===================================================================

class TestBuildDevelopmentPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        system, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_development_keywords(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        system, _ = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
        )
        assert "Development Plan" in system
        assert "Task Breakdown" in system
        assert "Tech Debt" in system or "Risk Assessment" in system

    def test_includes_optional_artifacts(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        _, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            architecture_content="# Architecture\nTest architecture",
            prd_content="# PRD\nTest PRD",
            super_analysis_content="# SUPER\nTest SUPER",
        )
        assert "Architecture Analysis" in user
        assert "PRD" in user
        assert "S.U.P.E.R" in user

    def test_handles_missing_optional_artifacts(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        _, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            architecture_content="",
            prd_content="",
            super_analysis_content="",
        )
        # Should not include empty sections
        assert "Architecture Analysis" not in user
        assert "S.U.P.E.R. Analysis" not in user

    def test_includes_project_metrics(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        _, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            src_lines=500,
            src_file_count=10,
            test_lines=200,
            test_file_count=5,
            git_commits=42,
            git_log="abc123 Initial commit (2 days ago)",
        )
        assert "Source lines: 500" in user
        assert "Test lines: 200" in user
        assert "40.0%" in user  # test-to-source ratio
        assert "42" in user  # git commits

    def test_includes_test_func_count_and_coverage(self, sample_spec_content):
        """r21d 复盘: 行数统计会误导 LLM (把 42 个测试函数说成 1 文件 108 行) —
        必须注入真实测试函数数与覆盖率报告。"""
        from yuleosh.pipeline.prompts import build_development_prompt

        _, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            src_lines=1000,
            test_lines=500,
            test_file_count=3,
            test_func_count=42,
            coverage_summary="line_rate=0.9285 branch_rate=0.8107 functions=54/54",
        )
        assert "Test functions: 42" in user
        assert "Coverage (latest report): line_rate=0.9285" in user

    def test_coverage_empty_no_report(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_development_prompt

        _, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            test_func_count=0,
            coverage_summary="",
        )
        assert "Test functions: 0" in user
        assert "no report" in user


# ===================================================================
# Test Planning prompt
# ===================================================================

class TestBuildTestPlanningPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_requirements):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        system, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_test_keywords(self, sample_spec_content, sample_requirements):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        system, _ = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert "Test Strategy" in system
        assert "Traceability" in system
        assert "Coverage" in system

    def test_user_prompt_maps_all_requirements(self, sample_spec_content, sample_requirements):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert "Req-RS-001" in user
        assert "Req-SWR-001.1" in user
        assert "SHALL" in user

    def test_includes_optional_artifacts(self, sample_spec_content, sample_requirements):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
            architecture_content="# Architecture\nTest",
            development_plan_content="# Dev Plan\nTest",
        )
        assert "Architecture Analysis" in user
        assert "Development Plan" in user

    def test_includes_repo_facts_when_provided(self, sample_spec_content, sample_requirements):
        """2026-08-18 r21e: repo_facts 注入 — 测试基建描述必须以机器收集事实为准。"""
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
            repo_facts="# Repository Facts\n- Test files (2): test_window_control.c",
        )
        assert "Repository Facts" in user
        assert "machine-collected" in user
        assert "test_window_control.c" in user

    def test_omits_repo_facts_when_empty(self, sample_spec_content, sample_requirements):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
            repo_facts="",
        )
        assert "Repository Facts" not in user

    def test_handles_empty_requirements(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        system, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=[],
        )
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_covers_all_shalls_clause(self, sample_spec_content, sample_requirements):
        """Verify the prompt asks LLM to cover ALL SHALL statements."""
        from yuleosh.pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        # Should mention the total SHALL count
        assert "4 SHALL statements" in user
        # Should instruct to cover ALL
        assert "ALL 4 SHALL" in user


# ===================================================================
# Code Review prompt
# ===================================================================

class TestBuildCodeReviewPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_code_review_prompt

        system, user = build_code_review_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            artifact_contents={"architecture": "# Architecture\nTest"},
            source_files=sample_source_files,
            timestamp="2024-01-01T00:00:00",
        )
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_requires_json_output(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_code_review_prompt

        system, _ = build_code_review_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            artifact_contents={},
            source_files=sample_source_files,
            timestamp="2024-01-01T00:00:00",
        )
        assert "JSON" in system
        assert "findings" in system
        assert "severity" in system

    def test_user_prompt_contains_session_info(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_code_review_prompt

        _, user = build_code_review_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            artifact_contents={},
            source_files=sample_source_files,
            timestamp="2024-01-01T00:00:00",
        )
        assert "test-session" in user
        assert "2024-01-01" in user

    def test_handles_empty_artifacts(self, sample_spec_content, sample_source_files):
        from yuleosh.pipeline.prompts import build_code_review_prompt

        system, user = build_code_review_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            artifact_contents={},
            source_files=sample_source_files,
            timestamp="",
        )
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_handles_empty_source_files(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_code_review_prompt

        system, user = build_code_review_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            session_name="test-session",
            artifact_contents={},
            source_files=[],
            timestamp="",
        )
        assert isinstance(system, str)
        assert isinstance(user, str)


# ===================================================================
# Final Report prompt
# ===================================================================

class TestBuildFinalReportPrompt:
    def test_returns_tuple_of_strings(self, sample_steps):
        from yuleosh.pipeline.prompts import build_final_report_prompt

        system, user = build_final_report_prompt(
            session_name="test-session",
            session_status="completed",
            spec_path="/path/to/spec.md",
            steps=sample_steps,
            errors=[],
            artifact_paths={"prd": "/path/to/prd.md"},
            artifact_summaries={"prd": "PRD document"},
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_report_sections(self, sample_steps):
        from yuleosh.pipeline.prompts import build_final_report_prompt

        system, _ = build_final_report_prompt(
            session_name="test-session",
            session_status="completed",
            spec_path="/path/to/spec.md",
            steps=sample_steps,
            errors=[],
            artifact_paths={},
            artifact_summaries={},
        )
        assert "Executive Summary" in system
        assert "Key Findings" in system
        assert "Next Steps" in system

    def test_user_prompt_contains_pipeline_status(self, sample_steps):
        from yuleosh.pipeline.prompts import build_final_report_prompt

        _, user = build_final_report_prompt(
            session_name="test-session",
            session_status="completed",
            spec_path="/path/to/spec.md",
            steps=sample_steps,
            errors=[],
            artifact_paths={},
            artifact_summaries={},
        )
        assert "test-session" in user
        assert "completed" in user
        assert "4/5 completed" in user
        assert "1 failed" in user

    def test_includes_errors_when_present(self, sample_steps):
        from yuleosh.pipeline.prompts import build_final_report_prompt

        _, user = build_final_report_prompt(
            session_name="test-with-errors",
            session_status="failed",
            spec_path="/path/to/spec.md",
            steps=sample_steps,
            errors=["LLM API timeout", "Validation failed"],
            artifact_paths={},
            artifact_summaries={},
        )
        assert "LLM API timeout" in user
        assert "Validation failed" in user

    def test_handles_empty_artifacts(self, sample_steps):
        from yuleosh.pipeline.prompts import build_final_report_prompt

        system, user = build_final_report_prompt(
            session_name="test-session",
            session_status="completed",
            spec_path="/path/to/spec.md",
            steps=[{"step": 1, "name": "spec-check", "agent": "小明", "status": "completed"}],
            errors=[],
            artifact_paths={},
            artifact_summaries={},
        )
        assert isinstance(system, str)
        assert isinstance(user, str)


# ===================================================================
# Internal Review prompt
# ===================================================================

class TestBuildInternalReviewPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_internal_review_prompt

        system, user = build_internal_review_prompt(
            session_name="test-session",
            spec_content=sample_spec_content,
            spec_name="spec.md",
            artifact_paths={"prd": "/path/to/prd.md", "super-analysis": "/path/to/super.md"},
            artifact_summaries={"prd": "PRD document", "super-analysis": "SUPER analysis"},
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_review_criteria(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_internal_review_prompt

        system, _ = build_internal_review_prompt(
            session_name="test-session",
            spec_content=sample_spec_content,
            spec_name="spec.md",
            artifact_paths={},
            artifact_summaries={},
        )
        assert "Completeness" in system
        assert "Consistency" in system
        assert "Quality" in system
        assert "Traceability" in system
        assert "PASS" in system or "FAIL" in system or "WARN" in system

    def test_user_prompt_contains_artifact_list(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_internal_review_prompt

        _, user = build_internal_review_prompt(
            session_name="test-session",
            spec_content=sample_spec_content,
            spec_name="spec.md",
            artifact_paths={"prd": "/tmp/prd.md"},
            artifact_summaries={"prd": "PRD document"},
        )
        assert "prd" in user
        assert "PRD document" in user

    def test_handles_empty_artifacts(self, sample_spec_content):
        from yuleosh.pipeline.prompts import build_internal_review_prompt

        system, user = build_internal_review_prompt(
            session_name="test-session",
            spec_content=sample_spec_content,
            spec_name="spec.md",
            artifact_paths={},
            artifact_summaries={},
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
