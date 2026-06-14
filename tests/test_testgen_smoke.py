"""Smoke tests for yuleosh.testgen — generator, formatter, runner."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestTestgen:
    def test_import(self):
        import yuleosh.testgen
        assert hasattr(yuleosh.testgen, "generator")

    def test_generator_import(self):
        from yuleosh.testgen.generator import TestGenerator, TestCase
        assert TestGenerator is not None

    def test_runner_import(self):
        from yuleosh.testgen.runner import TestRunner
        assert TestRunner is not None

    def test_runner_create(self):
        from yuleosh.testgen.runner import TestRunner
        runner = TestRunner()
        assert runner is not None
