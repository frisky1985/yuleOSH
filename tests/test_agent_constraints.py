"""
Tests for agent constraint integration (QG-005).

Tests T11: .yuleosh/agents/ file format and loading
Tests T12: Pipeline integration — loading and injection into LLM context
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open


# ═══════════════════════════════════════════════════════════════════════
# T11: Agent constraint file loading
# ═══════════════════════════════════════════════════════════════════════

class TestLoadAgentConstraints:
    """Test load_agent_constraints from orchestrator.py."""

    def test_load_from_agents_dir(self):
        """Loads agent constraints from .yuleosh/agents/ *.md files."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / ".yuleosh" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "AGENTS.md").write_text(
                "# AGENTS.md\n小明: PM\n小克: Dev\n小马: QA\n"
            )
            (agents_dir / "RULES.md").write_text(
                "# RULES.md\nP0/P1 zero tolerance.\n"
            )

            text, source = load_agent_constraints(tmpdir)
            assert source == "agents_dir"
            assert "AGENTS.md" in text
            assert "RULES.md" in text
            assert "小明: PM" in text
            assert "P0/P1 zero tolerance" in text

    def test_load_agents_dir_empty(self):
        """Empty .yuleosh/agents/ falls back to ci-config or builtin."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / ".yuleosh" / "agents"
            agents_dir.mkdir(parents=True)
            # Empty — no *.md files

            text, source = load_agent_constraints(tmpdir)
            # Falls back to builtin
            assert source == "builtin_fallback"
            assert "Default Agent Spec" in text
            assert "Core Rules" in text or "Roles" in text

    def test_no_agents_dir_fallback_ci_config(self):
        """No .yuleosh/agents/ directory — falls back to ci-config.yaml default_agent_spec."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True)
            (yuleosh_dir / "ci-config.yaml").write_text(
                "default_agent_spec: |\n  Custom default spec for testing.\n"
            )

            text, source = load_agent_constraints(tmpdir)
            assert source == "ci_config"
            assert "Custom default spec for testing" in text

    def test_no_agents_dir_no_ci_config(self):
        """No .yuleosh/agents/ and no ci-config.yaml — built-in fallback."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            text, source = load_agent_constraints(tmpdir)
            assert source == "builtin_fallback"
            assert text  # non-empty

    def test_agents_dir_malformed_file_skipped(self):
        """Malformed agent constraint file is skipped without crashing."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / ".yuleosh" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "GOOD.md").write_text("# Good\nContent here.")
            # Create a binary file that would cause read errors
            (agents_dir / "bad.bin").write_bytes(b"\x00\x01\x02")

            text, source = load_agent_constraints(tmpdir)
            assert source == "agents_dir"
            assert "GOOD.md" in text
            assert "Content here" in text

    def test_constraints_file_must_be_md(self):
        """Only .md files are loaded from .yuleosh/agents/."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            agents_dir = Path(tmpdir) / ".yuleosh" / "agents"
            agents_dir.mkdir(parents=True)

            (agents_dir / "AGENTS.md").write_text("# Agents\ncontent")
            (agents_dir / "NOTES.txt").write_text("txt files should be ignored")
            (agents_dir / "config.json").write_text('{"key": "value"}')

            text, source = load_agent_constraints(tmpdir)
            assert source == "agents_dir"
            assert "AGENTS.md" in text
            assert "NOTES.txt" not in text
            assert "config.json" not in text


# ═══════════════════════════════════════════════════════════════════════
# T12: LLM context injection
# ═══════════════════════════════════════════════════════════════════════

class TestLLMContextInjection:
    """Test that agent constraints are injected into LLM system prompts."""

    def test_build_effective_system_prompt_with_constraints(self):
        """Constraints are prepended to system prompt."""
        from yuleosh.pipeline.stages.llm import _build_effective_system_prompt
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession(
            "test-session",
            "/tmp/test.md",
            agent_constraints="# AGENTS.md\n小明: PM\n小克: Dev",
        )

        result = _build_effective_system_prompt(
            session,
            "You are a code reviewer.",
        )

        assert "[Agent Constraints" in result
        assert "# AGENTS.md" in result
        assert "小明: PM" in result
        assert "小克: Dev" in result
        assert "You are a code reviewer." in result
        assert "[End Agent Constraints]" in result

    def test_build_effective_system_prompt_no_constraints(self):
        """No constraints — system prompt returned as-is."""
        from yuleosh.pipeline.stages.llm import _build_effective_system_prompt
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession("test-session", "/tmp/test.md")

        result = _build_effective_system_prompt(
            session,
            "You are a code reviewer.",
        )

        assert result == "You are a code reviewer."

    def test_build_effective_system_prompt_duplicate_avoidance(self):
        """Constraints not re-injected if already present."""
        from yuleosh.pipeline.stages.llm import _build_effective_system_prompt
        from yuleosh.pipeline.session import PipelineSession

        session = PipelineSession(
            "test-session",
            "/tmp/test.md",
            agent_constraints="# AGENTS.md\nSome content",
        )

        result = _build_effective_system_prompt(
            session,
            "# AGENTS.md\nAlready in prompt",
        )

        # Should detect duplicate and return as-is
        assert result == "# AGENTS.md\nAlready in prompt"

    def test_call_llm_injects_constraints(self):
        """_call_llm injects agent constraints into the LLM system prompt."""
        from yuleosh.pipeline.stages.llm import _call_llm
        from yuleosh.pipeline.session import PipelineSession

        mock_client = MagicMock(return_value={
            "content": "Mock response",
            "model": "mock",
            "usage": {"total_tokens": 100},
        })

        session = PipelineSession(
            "test-session",
            "/tmp/test.md",
            llm_client=mock_client,
            agent_constraints="# RULES.md\nP0/P1 zero tolerance.",
        )

        result = _call_llm(session, "Be a code reviewer.", "Review this code.")

        # Verify mock was called with constraints prepended to system prompt
        call_system, call_user = mock_client.call_args[0]
        assert "[Agent Constraints" in call_system
        assert "# RULES.md" in call_system
        assert "P0/P1 zero tolerance" in call_system
        assert "Be a code reviewer." in call_system
        assert call_user == "Review this code."
        assert result["content"] == "Mock response"

    def test_call_llm_no_constraints(self):
        """_call_llm works normally when no constraints are set."""
        from yuleosh.pipeline.stages.llm import _call_llm
        from yuleosh.pipeline.session import PipelineSession

        mock_client = MagicMock(return_value={
            "content": "Mock response",
            "model": "mock",
            "usage": {"total_tokens": 100},
        })

        session = PipelineSession(
            "test-session",
            "/tmp/test.md",
            llm_client=mock_client,
        )

        result = _call_llm(session, "Be a code reviewer.", "Review this code.")

        call_system, call_user = mock_client.call_args[0]
        assert call_system == "Be a code reviewer."
        assert call_user == "Review this code."


# ═══════════════════════════════════════════════════════════════════════
# Pipeline integration (orchestrator)
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineIntegration:
    """Test that orchestrator loads and passes agent constraints to session.

    These tests verify the integration between load_agent_constraints and
    the PipelineSession at the component level rather than via the full
    ``run_pipeline`` function, which has many external dependencies.
    """

    def test_orchestrator_loads_constraints_and_creates_session(self):
        """load_agent_constraints returns proper constraints from .yuleosh/agents/. """
        from yuleosh.pipeline.orchestrator import load_agent_constraints
        from yuleosh.pipeline.session import PipelineSession

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .yuleosh/agents/
            agents_dir = Path(tmpdir) / ".yuleosh" / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "AGENTS.md").write_text("# AGENTS.md\n小明: PM\n")
            (agents_dir / "RULES.md").write_text("# RULES.md\nP0 zero tolerance.\n")

            text, source = load_agent_constraints(tmpdir)
            assert source == "agents_dir"
            assert "AGENTS.md" in text
            assert "RULES.md" in text

            # Verify the constraints can be passed to a session
            session = PipelineSession(
                "test-session",
                "/tmp/spec.md",
                agent_constraints=text,
            )
            assert "AGENTS.md" in session.agent_constraints
            assert "RULES.md" in session.agent_constraints

    def test_orchestrator_no_agents_dir_uses_default(self):
        """load_agent_constraints returns built-in default when dir missing."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            text, source = load_agent_constraints(tmpdir)
            assert source == "builtin_fallback"
            assert len(text) > 0
            assert "Default Agent Spec" in text

    def test_orchestrator_ci_config_default(self):
        """load_agent_constraints falls back to ci-config.yaml default."""
        from yuleosh.pipeline.orchestrator import load_agent_constraints

        with tempfile.TemporaryDirectory() as tmpdir:
            yuleosh_dir = Path(tmpdir) / ".yuleosh"
            yuleosh_dir.mkdir(parents=True)
            (yuleosh_dir / "ci-config.yaml").write_text(
                "default_agent_spec: |\n  Custom default for pipeline tests.\n"
            )

            text, source = load_agent_constraints(tmpdir)
            assert source == "ci_config"
            assert "Custom default for pipeline tests" in text

    def test_session_with_constraints_in_llm_call(self):
        """End-to-end: session with constraints → _call_llm injects them."""
        from yuleosh.pipeline.stages.llm import _call_llm
        from yuleosh.pipeline.session import PipelineSession

        mock_client = MagicMock(return_value={
            "content": "Constraint-aware response",
            "model": "mock",
            "usage": {"total_tokens": 50},
        })

        # Simulate what the orchestrator does: load constraints, pass to session
        constraints = (
            "<!-- from: AGENTS.md -->\n# AGENTS.md\n小明: PM\n\n"
            "<!-- from: RULES.md -->\n# RULES.md\nP0/P1 zero tolerance.\n"
        )
        session = PipelineSession(
            "test-session",
            "/tmp/spec.md",
            llm_client=mock_client,
            agent_constraints=constraints,
        )

        _call_llm(session, "Be a code reviewer.", "Review this code.")

        call_system, call_user = mock_client.call_args[0]
        assert "[Agent Constraints" in call_system
        assert "AGENTS.md" in call_system
        assert "RULES.md" in call_system
        assert "Be a code reviewer." in call_system
        assert call_user == "Review this code."
