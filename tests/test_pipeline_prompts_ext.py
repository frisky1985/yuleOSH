"""Tests for pipeline/prompts.py — LLM prompt builders."""

from yuleosh.pipeline.prompts import (
    get_prompt_versions,
    get_prompt_version,
    build_super_analysis_prompt,
    build_prd_prompt,
    build_architecture_prompt,
    build_development_prompt,
    build_test_planning_prompt,
    build_code_review_prompt,
    build_final_report_prompt,
    build_internal_review_prompt,
)


class TestPromptVersions:
    """Test prompt version management."""

    def test_get_prompt_versions(self):
        versions = get_prompt_versions()
        assert "super-analysis" in versions
        # super-analysis / prd bumped to 1.1.0 (2026-08-16, SPEC_INJECT_LIMIT)
        assert versions["super-analysis"] == "1.1.0"
        assert versions["prd"] == "1.1.0"
        assert all(versions[k] == "1.0.0" for k in versions if k not in ("super-analysis", "prd"))

    def test_get_prompt_version(self):
        assert get_prompt_version("super-analysis") == "1.1.0"
        assert get_prompt_version("prd") == "1.1.0"
        assert get_prompt_version("unknown") == "0.0.0"


class TestPromptBuilders:
    """Test prompt builder functions."""

    def test_build_super_analysis(self):
        system, user = build_super_analysis_prompt(
            spec_content="# Test Spec\nSHALL do X",
            spec_name="test.md",
            requirements=[{"shall_statements": ["SHALL X"]}],
            scenarios=["S1"],
        )
        assert "S.U.P.E.R" in system
        assert "test.md" in user

    def test_build_prd_prompt(self):
        system, user = build_prd_prompt(
            spec_content="# PRD Spec",
            spec_name="prd.md",
            requirements=[{"shall_statements": ["SHALL X"]}],
            scenarios=["S1"],
            super_analysis_content="## Analysis\nInsight",
        )
        assert "Product Requirements Document" in system
        assert "S.U.P.E.R. Analysis" in user

    def test_build_prd_prompt_no_super(self):
        system, user = build_prd_prompt(
            spec_content="# PRD",
            spec_name="prd.md",
            requirements=[],
            scenarios=[],
        )
        assert "S.U.P.E.R." not in user

    def test_build_prd_prompt_keeps_spec_tail_contracts(self):
        """Regression (2026-08-16, run-20260816-172910): spec truncation at 12000
        chars silently stripped the tail contract sections (§1.5 interface
        contract / §2.5 guardrail map / §3 acceptance) from the PRD prompt,
        causing claude-review blockers. SPEC_INJECT_LIMIT must keep the tail."""
        # Spec longer than the old 12000-char cap, with a marker at the very end
        spec = "# Test Spec\n" + ("SHALL contract\n" * 900) + "\n## 1.5 Interface Contract\nwindow_control_reset_tail_marker\n"
        assert len(spec) > 12000
        system, user = build_prd_prompt(
            spec_content=spec,
            spec_name="prd.md",
            requirements=[{"shall_statements": ["SHALL contract"]}],
            scenarios=["S1"],
        )
        assert "window_control_reset_tail_marker" in user, (
            "spec tail contract must survive injection (SPEC_INJECT_LIMIT regression)"
        )

    def test_spec_overflow_adds_truncation_warning(self):
        """方案 B (2026-08-17): spec 超过 SPEC_INJECT_LIMIT 时 prompt 必须
        显式标记 SPEC_TRUNCATED — 绝不静默截断 (静默截断曾导致 claude-review
        连续 3 轮误报缺失契约)."""
        from yuleosh.pipeline.prompts import _inject_spec, SPEC_INJECT_LIMIT

        big = "x" * (SPEC_INJECT_LIMIT + 1000)
        out = _inject_spec(big)
        assert len(out) <= SPEC_INJECT_LIMIT + 500
        assert "SPEC_TRUNCATED" in out
        assert str(len(big)) in out  # 显示实际长度

        small = "small spec"
        assert _inject_spec(small) == small  # 未超限不截断、无 marker

    def test_build_architecture_prompt(self):
        system, user = build_architecture_prompt(
            spec_content="# Arch Spec",
            spec_name="arch.md",
            session_name="session-1",
            directories=["src/", "tests/"],
            source_files=["src/main.py", "tests/test_main.py"],
            tech_stack=["Python"],
            source_tree_str="  src/\n    main.py",
            key_file_snippets=["### src/main.py\n```\npass\n```"],
        )
        assert "Architecture Decision Records" in system
        assert "Python" in user
        assert "session-1" in user

    def test_build_architecture_prompt_empty(self):
        system, user = build_architecture_prompt(
            spec_content="# Spec",
            spec_name="s.md",
            session_name="s1",
            directories=[],
            source_files=[],
            tech_stack=[],
            source_tree_str="",
            key_file_snippets=[],
        )
        assert "Python" in user  # default tech stack

    def test_build_development_prompt(self):
        system, user = build_development_prompt(
            spec_content="# Dev Spec",
            spec_name="dev.md",
            architecture_content="## Architecture\nDesign",
            prd_content="## PRD\nDocument",
            super_analysis_content="## Analysis",
            src_lines=500,
            src_file_count=10,
            test_lines=200,
            test_file_count=5,
            git_commits=15,
            git_log="abc123 Fix bug",
        )
        assert "Development Plan" in system
        assert "Source lines" in user

    def test_build_development_prompt_minimal(self):
        system, user = build_development_prompt(
            spec_content="# Spec", spec_name="s.md",
        )
        assert "Test-to-source ratio" in user

    def test_build_test_planning_prompt(self):
        system, user = build_test_planning_prompt(
            spec_content="# Test Spec",
            requirements=[{"shall_statements": ["SHALL X"], "name": "RS-001"}],
            architecture_content="## Architecture",
            development_plan_content="## Dev Plan",
        )
        assert "Test Strategy" in system
        assert "RS-001" in user

    def test_build_test_planning_no_optional(self):
        system, user = build_test_planning_prompt(
            spec_content="# Spec",
            requirements=[{"shall_statements": ["SHALL X"], "name": "R1"}],
        )
        assert "Architecture" not in user

    def test_build_code_review_prompt(self):
        system, user = build_code_review_prompt(
            spec_content="# Spec",
            spec_name="spec.md",
            session_name="session-1",
            artifact_contents={"analysis": "## Analysis\nContent"},
            source_files=[
                {"path": "src/main.py", "lines": 50, "content": "def main(): pass"}
            ],
            timestamp="2025-01-01T00:00:00",
        )
        assert "JSON" in system
        assert "src/main.py" in user

    def test_build_code_review_truncated(self):
        """More than 8 source files gets truncated."""
        system, user = build_code_review_prompt(
            spec_content="# S",
            spec_name="s.md",
            session_name="s1",
            artifact_contents={},
            source_files=[
                {"path": f"src/file{i}.py", "lines": 10, "content": "pass"}
                for i in range(10)
            ],
            timestamp="T",
        )
        assert "truncated" in user

    def test_build_final_report_prompt(self):
        system, user = build_final_report_prompt(
            session_name="session-1",
            session_status="completed",
            spec_path="/tmp/spec.md",
            steps=[
                {"step": 1, "agent": "小明", "name": "Spec Check", "status": "completed"},
                {"step": 2, "agent": "Claude", "name": "Arch", "status": "completed"},
            ],
            errors=[],
            artifact_paths={"analysis": "/tmp/analysis.md"},
            artifact_summaries={"analysis": "S.U.P.E.R analysis"},
        )
        assert "Executive Summary" in system
        assert "session-1" in user
        assert "2/2" in user  # steps completed/total

    def test_build_final_report_with_errors(self):
        system, user = build_final_report_prompt(
            session_name="failed-session",
            session_status="failed",
            spec_path="/spec.md",
            steps=[{"step": 1, "agent": "小明", "name": "Check", "status": "failed"}],
            errors=["Step 1 failed"],
            artifact_paths={},
            artifact_summaries={},
        )
        assert "Errors" in user
        assert "failed-session" in user

    def test_build_internal_review_prompt(self):
        system, user = build_internal_review_prompt(
            session_name="session-1",
            spec_content="# Spec",
            spec_name="spec.md",
            artifact_paths={"analysis": "/tmp/a.md"},
            artifact_summaries={"analysis": "Analysis done"},
        )
        assert "Completeness" in system
        assert "PASS/FAIL/WARN" in system
