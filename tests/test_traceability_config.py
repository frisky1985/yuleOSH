
# @tests src/yuleosh/alm/traceability.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for traceability config loader (Q5-d).

Verifies:
- Missing config file → returns built-in defaults + logs warning
- Valid YAML → correctly loaded and merged with defaults
- Malformed YAML → falls back to defaults + logs warning
- stop_words merged (project additions + built-in)
- component_map values normalized to list[str]
- _extract_keywords uses config stop_words
"""

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from yuleosh.alm.traceability_config import (
    load_traceability_config,
    get_stop_words,
    get_test_id_prefixes,
    _DEFAULT_STOP_WORDS,
    _DEFAULT_ZH_STOP_WORDS,
    _DEFAULT_TEST_ID_PREFIXES,
    _DEFAULT_SCENARIO_TERMS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def project_dir(tmp_path):
    """Project dir with .yuleosh/ subdir."""
    yuleosh_dir = tmp_path / ".yuleosh"
    yuleosh_dir.mkdir()
    return tmp_path


def write_config(project_dir: Path, content: str) -> Path:
    p = project_dir / ".yuleosh" / "traceability.yaml"
    p.write_text(content, encoding="utf-8")
    return p


# ── Tests: missing file ───────────────────────────────────────────────────────

class TestMissingConfig:

    def test_missing_file_returns_defaults(self, tmp_path, caplog):
        """No config file → returns built-in default dict."""
        with caplog.at_level(logging.WARNING, logger="yuleosh.alm.traceability_config"):
            cfg = load_traceability_config(tmp_path)
        assert cfg["component_map"] == {}
        assert cfg["scenario_terms"] == list(_DEFAULT_SCENARIO_TERMS)
        assert cfg["test_id_prefixes"] == list(_DEFAULT_TEST_ID_PREFIXES)
        assert cfg["stop_words"] == frozenset(_DEFAULT_STOP_WORDS | _DEFAULT_ZH_STOP_WORDS)

    def test_missing_file_logs_warning(self, tmp_path, caplog):
        """No config file → warning mentions traceability config."""
        with caplog.at_level(logging.WARNING, logger="yuleosh.alm.traceability_config"):
            load_traceability_config(tmp_path)
        assert any("traceability config" in r.message.lower() for r in caplog.records)


# ── Tests: valid YAML ─────────────────────────────────────────────────────────

class TestValidConfig:

    def test_component_map_loaded(self, project_dir):
        """component_map entries are loaded correctly."""
        pytest.importorskip("yaml")
        write_config(project_dir, """
component_map:
  RS-001: [init, startup, boot]
  RS-002: [uart, can, spi]
""")
        cfg = load_traceability_config(project_dir)
        assert cfg["component_map"]["RS-001"] == ["init", "startup", "boot"]
        assert cfg["component_map"]["RS-002"] == ["uart", "can", "spi"]

    def test_scenario_terms_loaded(self, project_dir):
        """Custom scenario_terms replace defaults when provided."""
        pytest.importorskip("yaml")
        write_config(project_dir, """
scenario_terms:
  - heartbeat
  - watchdog
  - calibrate
""")
        cfg = load_traceability_config(project_dir)
        assert "heartbeat" in cfg["scenario_terms"]
        assert "watchdog" in cfg["scenario_terms"]

    def test_test_id_prefixes_loaded(self, project_dir):
        """Custom test_id_prefixes are returned."""
        pytest.importorskip("yaml")
        write_config(project_dir, """
test_id_prefixes:
  - "MY-TC-"
  - "PROJ-"
""")
        cfg = load_traceability_config(project_dir)
        assert "MY-TC-" in cfg["test_id_prefixes"]
        assert "PROJ-" in cfg["test_id_prefixes"]

    def test_stop_words_merged_with_defaults(self, project_dir):
        """Project stop_words are merged with (not replacing) built-in defaults."""
        pytest.importorskip("yaml")
        write_config(project_dir, """
stop_words:
  - firmware
  - embedded
""")
        cfg = load_traceability_config(project_dir)
        # Project additions present
        assert "firmware" in cfg["stop_words"]
        assert "embedded" in cfg["stop_words"]
        # Built-in defaults still present
        assert "the" in cfg["stop_words"]
        assert "shall" in cfg["stop_words"]

    def test_empty_component_map_is_valid(self, project_dir):
        """Empty YAML is valid — returns defaults."""
        pytest.importorskip("yaml")
        write_config(project_dir, "component_map: {}\n")
        cfg = load_traceability_config(project_dir)
        assert cfg["component_map"] == {}

    def test_component_map_scalar_value_normalized_to_list(self, project_dir):
        """Scalar value in component_map is wrapped into a list."""
        pytest.importorskip("yaml")
        write_config(project_dir, """
component_map:
  RS-001: init
""")
        cfg = load_traceability_config(project_dir)
        assert isinstance(cfg["component_map"]["RS-001"], list)
        assert cfg["component_map"]["RS-001"] == ["init"]


# ── Tests: malformed YAML ─────────────────────────────────────────────────────

class TestMalformedConfig:

    def test_invalid_yaml_falls_back_to_defaults(self, project_dir, caplog):
        """Unparseable YAML → falls back to defaults and logs warning."""
        pytest.importorskip("yaml")
        write_config(project_dir, "component_map: [unclosed bracket\n  - bad yaml{{{")
        with caplog.at_level(logging.WARNING, logger="yuleosh.alm.traceability_config"):
            cfg = load_traceability_config(project_dir)
        assert cfg["component_map"] == {}
        assert any("traceability config" in r.message.lower() or
                   "failed to parse" in r.message.lower() or
                   "built-in defaults" in r.message.lower()
                   for r in caplog.records)

    def test_non_mapping_yaml_falls_back(self, project_dir, caplog):
        """YAML that is a list not a dict → falls back to defaults."""
        pytest.importorskip("yaml")
        write_config(project_dir, "- item1\n- item2\n")
        with caplog.at_level(logging.WARNING, logger="yuleosh.alm.traceability_config"):
            cfg = load_traceability_config(project_dir)
        assert cfg["component_map"] == {}


# ── Tests: convenience functions ─────────────────────────────────────────────

class TestConvenienceFunctions:

    def test_get_stop_words_returns_frozenset(self, tmp_path):
        """get_stop_words returns a frozenset."""
        result = get_stop_words(tmp_path)
        assert isinstance(result, frozenset)
        assert "the" in result

    def test_get_test_id_prefixes_returns_list(self, tmp_path):
        """get_test_id_prefixes returns a list."""
        result = get_test_id_prefixes(tmp_path)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_stop_words_uses_project_config(self, project_dir):
        """get_stop_words merges project additions."""
        pytest.importorskip("yaml")
        write_config(project_dir, "stop_words:\n  - myterm\n")
        result = get_stop_words(project_dir)
        assert "myterm" in result
        assert "the" in result  # built-in still there


# ── Tests: _extract_keywords integration ─────────────────────────────────────

class TestExtractKeywordsIntegration:

    def test_extract_keywords_uses_config_stop_words(self, project_dir):
        """_extract_keywords excludes project-defined stop words."""
        pytest.importorskip("yaml")
        write_config(project_dir, "stop_words:\n  - firmware\n  - embedded\n")
        from yuleosh.alm.traceability import _extract_keywords
        result = _extract_keywords(
            "The firmware shall initialize the embedded system within 100ms",
            project_dir=str(project_dir),
        )
        assert "firmware" not in result
        assert "embedded" not in result
        assert "initialize" in result or "system" in result

    def test_extract_keywords_default_when_no_config(self, tmp_path):
        """_extract_keywords works with no config file (uses defaults)."""
        from yuleosh.alm.traceability import _extract_keywords
        result = _extract_keywords(
            "The system shall initialize within 100ms",
            project_dir=str(tmp_path),
        )
        assert "initialize" in result
        assert "the" not in result
        assert "shall" not in result
