# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""v3.8.0 Track2 — A4 Store 抽象补方法验收测试（acceptance-matrix T-A4-*）。

覆盖:
  - T-A4-01/02/03 project 走接口（list / spec_path / stats）
  - T-A4-04 stats ci_pass_rate
  - T-A4-05 PG 三实现同步（接口完整性）
  - T-A4-06-neg api/project.py + api/stats.py 无裸 SQL
  - T-A4-07 接口完整性（AbstractStore 全实现）
  - T-A4-08 空表行为
"""

import inspect
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.store import Store
from yuleosh.store_interface import AbstractStore


class TestA4StoreInterface:
    """T-A4-05/07 — 三实现同步 + 接口完整性."""

    def test_all_abstract_methods_implemented(self):
        abstract = {n for n, v in inspect.getmembers(AbstractStore)
                    if getattr(v, "__isabstractmethod__", False)}
        store = Store()
        missing = {n for n in abstract if not hasattr(store, n)}
        assert missing == set(), f"Store 未实现: {missing}"

    def test_new_methods_exist(self):
        store = Store()
        for name in ("list_projects", "update_project_spec_path",
                     "get_project_stats", "count_ci_passed",
                     "get_pipeline_trend_rows", "get_ci_trend_rows",
                     "get_review_trend_rows"):
            assert callable(getattr(store, name)), name

    def test_pg_store_has_new_methods(self):
        """T-A4-05: PostgresStore 同步实现（接口存在性，不连库）."""
        from yuleosh.store_pg import PostgresStore
        for name in ("list_projects", "update_project_spec_path",
                     "get_project_stats", "count_ci_passed",
                     "get_pipeline_trend_rows", "get_ci_trend_rows",
                     "get_review_trend_rows"):
            assert callable(getattr(PostgresStore, name)), name


class TestA4ProjectViaInterface:
    """T-A4-01/02/03 — project 端点走接口."""

    @mock.patch("yuleosh.store.Store")
    def test_list_via_interface(self, mock_store_cls):
        from yuleosh.api.project import handle_project
        mock_store = mock.MagicMock()
        mock_store.list_projects.return_value = [
            {"name": "p1", "created_at": "2025-01-01"},
            {"name": "p2", "created_at": "2025-01-02"},
        ]
        mock_store_cls.return_value = mock_store
        result, code = handle_project(
            "GET", "", {}, {},
            current_user={"user_id": 1, "org_id": 1,
                          "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["count"] == 2
        mock_store.list_projects.assert_called_once()

    @mock.patch("yuleosh.store.Store")
    def test_spec_path_via_interface(self, mock_store_cls):
        from yuleosh.api.project import handle_project
        mock_store = mock.MagicMock()
        mock_store.get_project.return_value = {
            "name": "p1", "spec_path": "docs/spec.md"}
        mock_store_cls.return_value = mock_store
        result, code = handle_project(
            "POST", "", {"name": "p1", "spec_path": "docs/spec.md"}, {},
            current_user={"user_id": 1, "org_id": 1,
                          "email": "t@t.com", "role": "admin"})
        assert code == 200
        mock_store.update_project_spec_path.assert_called_once_with(
            "p1", "docs/spec.md")

    @mock.patch("yuleosh.store.Store")
    def test_stats_via_interface(self, mock_store_cls):
        from yuleosh.api.project import handle_project
        mock_store = mock.MagicMock()
        mock_store.get_project_stats.return_value = {
            "projects": 1, "pipelines": 2, "pipeline_statuses": {},
            "ci_runs": 3, "reviews": 4, "evidence_files": 5,
        }
        mock_store_cls.return_value = mock_store
        result, code = handle_project(
            "GET", "stats", {}, {},
            current_user={"user_id": 1, "org_id": 1,
                          "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["ci_runs"] == 3
        mock_store.get_project_stats.assert_called_once()


class TestA4StatsViaInterface:
    """T-A4-04 — stats ci_pass_rate 走接口."""

    @mock.patch("yuleosh.api.stats.Store")
    def test_ci_pass_rate_via_interface(self, mock_store_cls):
        from yuleosh.api.stats import handle_stats
        mock_store = mock.MagicMock()
        mock_store.get_usage_stats.return_value = {
            "total_pipelines": 10,
            "pipeline_statuses": {"completed": 8},
            "total_ci_runs": 20,
            "total_reviews": 5,
        }
        mock_store.count_ci_passed.return_value = 15
        mock_store_cls.return_value = mock_store
        result, code = handle_stats(
            "GET", "overview", {}, {},
            current_user={"user_id": 1, "org_id": 1,
                          "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["ci_pass_rate"] == 75.0
        mock_store.count_ci_passed.assert_called_once()


class TestA4NoBareSql:
    """T-A4-06-neg — api/project.py + api/stats.py 无 conn.execute."""

    def test_no_conn_execute(self):
        for rel in ("src/yuleosh/api/project.py",
                    "src/yuleosh/api/stats.py"):
            text = (Path(__file__).resolve().parent.parent / rel).read_text(
                encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("conn.execute") or \
                        stripped.startswith("store.conn.execute"):
                    pytest.fail(f"{rel}:{i} 裸 SQL 残留: {line}")


class TestA4EmptyTables:
    """T-A4-08 — 空表行为."""

    def test_empty_store_behavior(self):
        store = Store()
        # 空表（或至少不抛错）——计数与列表为 0/空
        assert isinstance(store.list_projects(), list)
        stats = store.get_project_stats()
        assert stats["projects"] >= 0
        assert store.count_ci_passed() >= 0
