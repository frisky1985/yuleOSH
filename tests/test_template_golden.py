
# @tests src/yuleosh/templates/golden.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for templates/golden.py — golden sample registry and comparison."""

import pytest
from pathlib import Path

from yuleosh.templates.golden import (
    GoldenSample,
    compare_to_golden,
    generate_golden,
    load_golden,
)


def test_load_golden_returns_none_when_no_golden_dir(tmp_path):
    template_dir = tmp_path / "my-template"
    template_dir.mkdir()
    assert load_golden(template_dir) is None


def test_load_golden_returns_sample_when_dir_exists(tmp_path):
    template_dir = tmp_path / "my-template"
    template_dir.mkdir()
    golden_dir = template_dir / "golden"
    golden_dir.mkdir()
    (golden_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    gs = load_golden(template_dir)
    assert gs is not None
    assert gs.template_name == "my-template"
    assert "main.c" in gs.critical_files


def test_compare_to_golden_pass_identical(tmp_path):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    gen_dir = tmp_path / "generated"
    gen_dir.mkdir()
    (gen_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    gs = GoldenSample("test", golden_dir, critical_files=["main.c"])
    result = compare_to_golden(gen_dir, gs)
    assert result["status"] == "pass"
    assert result["critical_failures"] == 0


def test_compare_to_golden_fail_missing_critical(tmp_path):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    gen_dir = tmp_path / "generated"
    gen_dir.mkdir()
    # main.c intentionally absent

    gs = GoldenSample("test", golden_dir, critical_files=["main.c"])
    result = compare_to_golden(gen_dir, gs)
    assert result["status"] == "fail"
    assert result["critical_failures"] >= 1
    assert any(d["type"] == "missing" for d in result["diffs"])


def test_compare_to_golden_fail_content_changed(tmp_path):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "main.c").write_text("int main(){ return 0; }", encoding="utf-8")

    gen_dir = tmp_path / "generated"
    gen_dir.mkdir()
    (gen_dir / "main.c").write_text("int main(){ return 1; }", encoding="utf-8")

    gs = GoldenSample("test", golden_dir, critical_files=["main.c"])
    result = compare_to_golden(gen_dir, gs)
    assert result["status"] == "fail"
    assert any(d["type"] == "content_changed" for d in result["diffs"])


def test_compare_to_golden_warn_on_extra_files(tmp_path):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    gen_dir = tmp_path / "generated"
    gen_dir.mkdir()
    (gen_dir / "main.c").write_text("int main(){}", encoding="utf-8")
    (gen_dir / "extra.c").write_text("// extra", encoding="utf-8")

    gs = GoldenSample("test", golden_dir, critical_files=["main.c"])
    result = compare_to_golden(gen_dir, gs)
    assert result["status"] == "warn"
    assert any(d["type"] == "extra" for d in result["diffs"])


def test_generate_golden_creates_manifest(tmp_path):
    template_dir = tmp_path / "my-template"
    template_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "main.c").write_text("int main(){}", encoding="utf-8")

    generate_golden(template_dir, output_dir)

    golden_dir = template_dir / "golden"
    assert golden_dir.is_dir()
    assert (golden_dir / "golden_manifest.json").exists()
    assert (golden_dir / "main.c").read_text() == "int main(){}"
