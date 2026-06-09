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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


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
        from pipeline.prompts import build_super_analysis_prompt

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
        from pipeline.prompts import build_super_analysis_prompt

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
        from pipeline.prompts import build_super_analysis_prompt

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
        from pipeline.prompts import build_super_analysis_prompt

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
        from pipeline.prompts import build_super_analysis_prompt

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
        from pipeline.prompts import build_prd_prompt

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
        from pipeline.prompts import build_prd_prompt

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

    def test_includes_super_analysis_when_provided(self, sample_spec_content, sample_requirements, sample_scenarios):
        from pipeline.prompts import build_prd_prompt

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
        from pipeline.prompts import build_prd_prompt

        _, user = build_prd_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
            requirements=sample_requirements,
            scenarios=sample_scenarios,
            super_analysis_content="",
        )
        assert "S.U.P.E.R. Analysis" not in user  # Should not include when empty

    def test_handles_empty_requirements(self, sample_spec_content):
        from pipeline.prompts import build_prd_prompt

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
        from pipeline.prompts import build_architecture_prompt

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
        from pipeline.prompts import build_architecture_prompt

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
        from pipeline.prompts import build_architecture_prompt

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
        from pipeline.prompts import build_architecture_prompt

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
        from pipeline.prompts import build_architecture_prompt

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


# ===================================================================
# Development prompt
# ===================================================================

class TestBuildDevelopmentPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content):
        from pipeline.prompts import build_development_prompt

        system, user = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_development_keywords(self, sample_spec_content):
        from pipeline.prompts import build_development_prompt

        system, _ = build_development_prompt(
            spec_content=sample_spec_content,
            spec_name="spec.md",
        )
        assert "Development Plan" in system
        assert "Task Breakdown" in system
        assert "Tech Debt" in system or "Risk Assessment" in system

    def test_includes_optional_artifacts(self, sample_spec_content):
        from pipeline.prompts import build_development_prompt

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
        from pipeline.prompts import build_development_prompt

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
        from pipeline.prompts import build_development_prompt

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


# ===================================================================
# Test Planning prompt
# ===================================================================

class TestBuildTestPlanningPrompt:
    def test_returns_tuple_of_strings(self, sample_spec_content, sample_requirements):
        from pipeline.prompts import build_test_planning_prompt

        system, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert len(system) > 0
        assert len(user) > 0

    def test_system_prompt_contains_test_keywords(self, sample_spec_content, sample_requirements):
        from pipeline.prompts import build_test_planning_prompt

        system, _ = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert "Test Strategy" in system
        assert "Traceability" in system
        assert "Coverage" in system

    def test_user_prompt_maps_all_requirements(self, sample_spec_content, sample_requirements):
        from pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
        )
        assert "Req-RS-001" in user
        assert "Req-SWR-001.1" in user
        assert "SHALL" in user

    def test_includes_optional_artifacts(self, sample_spec_content, sample_requirements):
        from pipeline.prompts import build_test_planning_prompt

        _, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=sample_requirements,
            architecture_content="# Architecture\nTest",
            development_plan_content="# Dev Plan\nTest",
        )
        assert "Architecture Analysis" in user
        assert "Development Plan" in user

    def test_handles_empty_requirements(self, sample_spec_content):
        from pipeline.prompts import build_test_planning_prompt

        system, user = build_test_planning_prompt(
            spec_content=sample_spec_content,
            requirements=[],
        )
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_covers_all_shalls_clause(self, sample_spec_content, sample_requirements):
        """Verify the prompt asks LLM to cover ALL SHALL statements."""
        from pipeline.prompts import build_test_planning_prompt

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
        from pipeline.prompts import build_code_review_prompt

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
        from pipeline.prompts import build_code_review_prompt

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
        from pipeline.prompts import build_code_review_prompt

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
        from pipeline.prompts import build_code_review_prompt

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
        from pipeline.prompts import build_code_review_prompt

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
        from pipeline.prompts import build_final_report_prompt

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
        from pipeline.prompts import build_final_report_prompt

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
        from pipeline.prompts import build_final_report_prompt

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
        from pipeline.prompts import build_final_report_prompt

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
        from pipeline.prompts import build_final_report_prompt

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
        from pipeline.prompts import build_internal_review_prompt

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
        from pipeline.prompts import build_internal_review_prompt

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
        from pipeline.prompts import build_internal_review_prompt

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
        from pipeline.prompts import build_internal_review_prompt

        system, user = build_internal_review_prompt(
            session_name="test-session",
            spec_content=sample_spec_content,
            spec_name="spec.md",
            artifact_paths={},
            artifact_summaries={},
        )
        assert isinstance(system, str)
        assert isinstance(user, str)
