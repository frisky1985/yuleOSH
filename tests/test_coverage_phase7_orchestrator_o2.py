"""Coverage tests for O2: ``load_agent_constraints`` and ``_mock_llm_client``.

Target: src/yuleosh/pipeline/orchestrator.py L173-268.

``load_agent_constraints`` branches:
  - agents_dir exists + readable ``*.md`` files -> ("...", "agents_dir")
  - agents_dir exists + one unreadable file -> warning, still "agents_dir"
  - agents_dir exists + ALL files unreadable -> parts empty -> fall through
  - agents_dir exists + no ``*.md`` files -> fall through
  - agents_dir missing -> fall through
  - ci-config.yaml exists + parses + truthy default_agent_spec -> "ci_config"
  - ci-config.yaml exists + missing/empty default_agent_spec -> fall through
  - ci-config.yaml exists + non-dict/empty YAML -> fall through
  - ci-config.yaml exists + malformed YAML -> parse error -> fall through
  - no ci-config.yaml -> built-in fallback

Error paths are exercised with real filesystem objects (a directory named
``*.md`` raises IsADirectoryError on read_text; malformed YAML raises
ScannerError in yaml.safe_load) — no mocks needed.
"""

from yuleosh.pipeline.orchestrator import (
    _DEFAULT_AGENT_SPEC,
    _mock_llm_client,
    load_agent_constraints,
)

# ── load_agent_constraints: agents_dir path ──────────────────────────

def test_load_agents_dir_returns_combined_md_files(tmp_path):
    """All readable *.md files are concatenated with source markers."""
    agents = tmp_path / ".yuleosh" / "agents"
    agents.mkdir(parents=True)
    (agents / "a.md").write_text("alpha-rules", encoding="utf-8")
    (agents / "b.md").write_text("beta-rules", encoding="utf-8")

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "agents_dir"
    assert "<!-- from: a.md -->\nalpha-rules" in text
    assert "<!-- from: b.md -->\nbeta-rules" in text


def test_load_agents_dir_skips_unreadable_file(tmp_path):
    """A file that fails to read is skipped (warning) but others are kept."""
    agents = tmp_path / ".yuleosh" / "agents"
    agents.mkdir(parents=True)
    (agents / "good.md").write_text("good-rules", encoding="utf-8")
    (agents / "broken.md").mkdir()  # directory: read_text raises IsADirectoryError

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "agents_dir"
    assert "good-rules" in text
    assert "broken" not in text


def test_load_agents_dir_all_unreadable_falls_through(tmp_path):
    """Zero readable parts -> falls through to built-in fallback."""
    agents = tmp_path / ".yuleosh" / "agents"
    agents.mkdir(parents=True)
    (agents / "broken.md").mkdir()

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_agents_dir_empty_falls_through(tmp_path):
    """Empty agents dir (no *.md) -> falls through."""
    (tmp_path / ".yuleosh" / "agents").mkdir(parents=True)

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_no_agents_dir_falls_through(tmp_path):
    """Missing .yuleosh/agents -> built-in fallback."""
    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


# ── load_agent_constraints: ci-config.yaml path ──────────────────────

def test_load_ci_config_default_spec(tmp_path):
    """ci-config.yaml with default_agent_spec is used."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
        "default_agent_spec: 'custom spec from ci'\n", encoding="utf-8"
    )

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "ci_config"
    assert text == "custom spec from ci"


def test_load_ci_config_missing_spec_key_falls_back(tmp_path):
    """Dict without default_agent_spec key -> built-in fallback."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
        "unrelated: 1\n", encoding="utf-8"
    )

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_ci_config_empty_spec_falls_back(tmp_path):
    """Falsy default_agent_spec (empty string) -> built-in fallback."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
        "default_agent_spec: ''\n", encoding="utf-8"
    )

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_ci_config_non_dict_yaml_falls_back(tmp_path):
    """YAML that parses to a non-dict -> built-in fallback."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
        "- just\n- a\n- list\n", encoding="utf-8"
    )

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_ci_config_empty_yaml_falls_back(tmp_path):
    """Empty YAML file (raw is None) -> built-in fallback."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text("", encoding="utf-8")

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


def test_load_ci_config_malformed_yaml_falls_back(tmp_path):
    """Malformed YAML (ScannerError) -> caught, built-in fallback."""
    (tmp_path / ".yuleosh").mkdir(parents=True)
    (tmp_path / ".yuleosh" / "ci-config.yaml").write_text(
        "\tkey: value\n", encoding="utf-8"
    )

    text, source = load_agent_constraints(str(tmp_path))

    assert source == "builtin_fallback"
    assert text == _DEFAULT_AGENT_SPEC.strip()


# ── _mock_llm_client ─────────────────────────────────────────────────

def test_mock_llm_client_returns_callable():
    """The factory returns a callable with chat_completion signature."""
    client = _mock_llm_client()

    assert callable(client)


def test_mock_llm_client_response_structure():
    """Response dict matches what pipeline step handlers expect."""
    client = _mock_llm_client()

    result = client("system prompt", "user prompt")

    assert isinstance(result, dict)
    assert "Mock Response" in result["content"]
    assert "Generated at" in result["content"]
    assert result["model"] == "mock-mode"
    assert result["usage"] == {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
    }


def test_mock_llm_client_accepts_extra_kwargs():
    """Extra LLM kwargs (temperature, max_tokens) are accepted."""
    client = _mock_llm_client()

    result = client(
        system_prompt="sys",
        user_prompt="user",
        temperature=0.0,
        max_tokens=42,
    )

    assert "Mock Response" in result["content"]


def test_mock_llm_client_returns_fresh_dict_per_call():
    """Each call builds a new dict (no shared mutable state)."""
    client = _mock_llm_client()

    first = client("s", "u")
    second = client("s", "u")

    assert first is not second
