"""Smoke tests for yuleosh.store_pg — PostgreSQL store adapter."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestStorePg:
    def test_import(self):
        from yuleosh.store_pg import PostgresStore
        assert PostgresStore is not None
        assert hasattr(PostgresStore, '_instances')
        assert hasattr(PostgresStore, '_lock')
