"""Unit tests for yuleosh.store_interface — pure Python interface definitions."""

# @tests src/yuleosh/store.py

import pytest
from yuleosh.store_interface import (
    AbstractStore,
)


class TestAbstractStore:
    def test_is_abstract(self):
        # Cannot instantiate abstract class
        with pytest.raises(TypeError):
            AbstractStore()

    def test_has_abstract_methods(self):
        """Verify abstract methods exist on the class."""
        import inspect
        methods = [name for name, _ in inspect.getmembers(AbstractStore, predicate=inspect.isfunction)]
        assert len(methods) > 0
        # Should have some abstract methods
        abstract_methods = [
            name for name, method in inspect.getmembers(AbstractStore, predicate=inspect.isfunction)
            if getattr(method, '__isabstractmethod__', False)
        ]
        assert len(abstract_methods) > 0
