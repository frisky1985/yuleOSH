#!/usr/bin/env python3

# @tests src/yuleosh/preview/code_parser.py

"""Deep tests for preview/code_parser.py — SWR-013.1 input validation."""

import pytest
from pathlib import Path

from yuleosh.preview.code_parser import (
    _discover_files,
    _scan_frameworks,
    SUPPORTED_EXTENSIONS,
)


class TestDiscoverFiles:
    def test_empty_dir(self, tmp_path):
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert all_f == []
        assert src == []

    def test_c_source_detected(self, tmp_path):
        (tmp_path / "main.c").write_text("int main() {}")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert "main.c" in src

    def test_header_detected(self, tmp_path):
        (tmp_path / "main.h").write_text("#pragma once")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert "main.h" in hdr

    def test_test_file_detected(self, tmp_path):
        (tmp_path / "test_main.py").write_text("def test_x(): pass")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert "test_main.py" in test

    def test_config_file_detected(self, tmp_path):
        (tmp_path / "config.yaml").write_text("key: value")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert "config.yaml" in cfg

    def test_unsupported_extension_skipped(self, tmp_path):
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert all_f == []

    def test_hidden_files_skipped(self, tmp_path):
        (tmp_path / ".hidden.c").write_text("int x;")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert all_f == []

    def test_nested_files_found(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.c").write_text("int y;")
        all_f, src, hdr, test, cfg = _discover_files(tmp_path)
        assert len(src) == 1


class TestScanFrameworks:
    def test_empty_dir_no_frameworks(self, tmp_path):
        result = _scan_frameworks(tmp_path)
        assert result == []

    def test_freertos_detected(self, tmp_path):
        (tmp_path / "main.c").write_text('#include "FreeRTOS.h"\nvTaskStartScheduler();')
        result = _scan_frameworks(tmp_path)
        names = [f.get("name", f.get("framework", "")) for f in result]
        assert any("FreeRTOS" in n for n in names)

    def test_zephyr_detected(self, tmp_path):
        (tmp_path / "main.c").write_text('#include <zephyr/kernel.h>\nK_SEM_DEFINE(my_sem, 0, 1);')
        result = _scan_frameworks(tmp_path)
        names = [f.get("name", f.get("framework", "")) for f in result]
        assert any("Zephyr" in n for n in names)

    def test_autosar_detected(self, tmp_path):
        (tmp_path / "main.c").write_text('#include "Rte_Type.h"\n#include "Os.h"')
        result = _scan_frameworks(tmp_path)
        names = [f.get("name", f.get("framework", "")) for f in result]
        assert any("AUTOSAR" in n for n in names)


class TestSupportedExtensions:
    def test_c_extensions_supported(self):
        assert ".c" in SUPPORTED_EXTENSIONS
        assert ".h" in SUPPORTED_EXTENSIONS

    def test_python_supported(self):
        assert ".py" in SUPPORTED_EXTENSIONS

    def test_yaml_supported(self):
        assert ".yaml" in SUPPORTED_EXTENSIONS
        assert ".yml" in SUPPORTED_EXTENSIONS
