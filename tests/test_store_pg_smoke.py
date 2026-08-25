"""Smoke tests for yuleosh.store_pg — PostgreSQL store adapter."""

# @tests src/yuleosh/store.py
import sys
from pathlib import Path
# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


class TestStorePg:
    def test_import(self):
        from yuleosh.store_pg import PostgresStore
        assert PostgresStore is not None
        assert hasattr(PostgresStore, '_instances')
        assert hasattr(PostgresStore, '_lock')
