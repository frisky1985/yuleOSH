"""Unit tests for yuleosh.spec.diff — CLI interface, no external deps."""

# @tests src/yuleosh/spec/diff.py

import pytest

from yuleosh.spec.diff import (
    parse_spec,
    diff_specs,
)


class TestSpecDiffModuleImports:
    def test_import_functions(self):
        assert callable(diff_specs)
