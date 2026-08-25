
# @tests src/yuleosh/codegen/layered.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for codegen/layered.py — LayeredCodegenEngine."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from yuleosh.codegen.layered import LAYER_CONFIGS, LayeredCodegenEngine


def test_layer_configs_has_all_three_layers():
    assert "hal" in LAYER_CONFIGS
    assert "bsp" in LAYER_CONFIGS
    assert "app" in LAYER_CONFIGS


def test_layer_config_has_required_fields():
    for name, cfg in LAYER_CONFIGS.items():
        assert cfg.name == name
        assert len(cfg.file_globs) > 0
        assert len(cfg.system_prompt_fragment) > 20


def test_layered_engine_default_layers():
    engine = LayeredCodegenEngine()
    assert engine.layers == ["hal", "bsp", "app"]


def test_layered_engine_custom_layers():
    engine = LayeredCodegenEngine(layers=["hal", "app"])
    assert engine.layers == ["hal", "app"]


def test_generate_layered_hal_failure_blocks_subsequent(tmp_path):
    session = MagicMock()
    session.project_dir = str(tmp_path)
    session.name = "test-session"
    session.llm_client = None

    def no_files_llm(system, user, **kw):
        return ""  # no parseable files → no-files status

    engine = LayeredCodegenEngine(
        layers=["hal", "bsp", "app"],
        base_engine_kwargs={"llm_client": no_files_llm, "max_retries": 0},
    )
    result = engine.generate_layered(session, "system", "user", language_hint="c")
    assert result["overall_status"] == "failed"
    # bsp and app skipped because hal failed
    assert "bsp" not in result["layers"]
    assert "app" not in result["layers"]


def test_generate_layered_returns_summary_string(tmp_path):
    session = MagicMock()
    session.project_dir = str(tmp_path)
    session.name = "test-session"

    from yuleosh.codegen.engine import CodegenEngine, CodegenResult

    def patched_generate(self, session, sys_p, usr_p, **kw):
        r = CodegenResult(status="verified", max_retries=0, rounds=1)
        r.output_dir = str(self.output_dir) if self.output_dir else ""
        r.files = []
        return r

    with patch.object(CodegenEngine, "generate", patched_generate):
        engine = LayeredCodegenEngine(
            layers=["hal"],
            base_engine_kwargs={"max_retries": 0},
        )
        result = engine.generate_layered(session, "system", "user")

    assert "hal:" in result["summary"]


def test_generate_layered_seed_propagation(tmp_path):
    """Each layer's output_dir should become the next layer's seed_dir."""
    session = MagicMock()
    session.project_dir = str(tmp_path)
    session.name = "test-session"

    seed_dirs_seen: list = []

    from yuleosh.codegen.engine import CodegenEngine, CodegenResult

    def patched_generate(self, session, sys_p, usr_p, **kw):
        seed_dirs_seen.append(self.seed_dir)
        r = CodegenResult(status="verified", max_retries=0, rounds=1)
        r.output_dir = str(self.output_dir) if self.output_dir else ""
        r.files = []
        return r

    with patch.object(CodegenEngine, "generate", patched_generate):
        engine = LayeredCodegenEngine(
            layers=["hal", "bsp", "app"],
            base_engine_kwargs={"max_retries": 0},
        )
        engine.generate_layered(session, "system", "user")

    assert seed_dirs_seen[0] is None        # hal: no seed
    assert seed_dirs_seen[1] is not None    # bsp: hal output
    assert seed_dirs_seen[2] is not None    # app: bsp output
