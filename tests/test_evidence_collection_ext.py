"""Extended tests for evidence.collection — targeting uncovered paths."""

import sys
import os
import json
import tempfile
# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src

from yuleosh.evidence.collection import DataCollectionMixin


class FakeCollector(DataCollectionMixin):
    """Fake collector that inherits DataCollectionMixin for testing."""
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.requirements = []
        self.scenarios = []
        self.reviews = []
        self.ci_results = []
        self.coverage_data = None
        self.sil_reports = []

    def _find_latest_pipeline_spec(self):
        """Stub needed by collect_requirements."""
        return None


class TestDataCollectionMixin:
    """Cover DataCollectionMixin method paths."""

    def test_collect_requirements_no_spec(self):
        """collect_requirements: spec not found."""
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeCollector(tmp)
            c.collect_requirements()  # no spec → prints skip msg
            assert c.requirements == []
            assert c.scenarios == []

    def test_collect_reviews_no_dir(self):
        """collect_reviews: reviews dir doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeCollector(tmp)
            c.collect_reviews()
            assert c.reviews == []

    def test_collect_reviews_with_data(self):
        """collect_reviews: with review JSON files."""
        with tempfile.TemporaryDirectory() as tmp:
            reviews_dir = os.path.join(tmp, ".osh", "evidence", "reviews")
            os.makedirs(reviews_dir)

            # Write a review JSON file
            review = {
                "commit_sha": "abc123",
                "review_type": "code_review",
                "comments": ["looks good"]
            }
            with open(os.path.join(reviews_dir, "review.json"), "w") as f:
                json.dump(review, f)

            c = FakeCollector(tmp)
            c.collect_reviews()
            assert len(c.reviews) == 1
            assert c.reviews[0]["review_type"] == "code_review"

    def test_collect_reviews_corrupt_file(self):
        """collect_reviews: JSON decode error handled gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            reviews_dir = os.path.join(tmp, ".osh", "evidence", "reviews")
            os.makedirs(reviews_dir)

            with open(os.path.join(reviews_dir, "bad.json"), "w") as f:
                f.write("not valid json{{{")

            c = FakeCollector(tmp)
            c.collect_reviews()  # should not raise
            assert c.reviews == []

    def test_collect_reviews_dedup_by_key(self):
        """collect_reviews: deduplicates by (commit_sha, review_type)."""
        with tempfile.TemporaryDirectory() as tmp:
            reviews_dir = os.path.join(tmp, ".osh", "evidence", "reviews")
            os.makedirs(reviews_dir)

            for i in range(3):
                with open(os.path.join(reviews_dir, f"review{i}.json"), "w") as f:
                    json.dump({"commit_sha": "abc", "review_type": "code"}, f)

            c = FakeCollector(tmp)
            c.collect_reviews()
            assert len(c.reviews) == 1  # deduplicated

    def test_collect_reviews_no_dedup_key(self):
        """collect_reviews: items with empty commit_sha and review_type not deduped."""
        with tempfile.TemporaryDirectory() as tmp:
            reviews_dir = os.path.join(tmp, ".osh", "evidence", "reviews")
            os.makedirs(reviews_dir)

            for i in range(2):
                with open(os.path.join(reviews_dir, f"review{i}.json"), "w") as f:
                    json.dump({"comment": f"entry{i}"}, f)

            c = FakeCollector(tmp)
            c.collect_reviews()
            assert len(c.reviews) == 2  # no dedup key → both included

    def test_collect_ci_no_dir(self):
        """collect_ci_results: CI dir doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeCollector(tmp)
            c.collect_ci_results()
            assert c.ci_results == []

    def test_collect_ci_with_data(self):
        """collect_ci_results: reads layer*.json files."""
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = os.path.join(tmp, ".osh", "ci")
            os.makedirs(ci_dir)

            with open(os.path.join(ci_dir, "layer1.json"), "w") as f:
                json.dump({"layer": 1, "coverage": {"line": 50.0}}, f)
            with open(os.path.join(ci_dir, "layer2.json"), "w") as f:
                json.dump({"layer": 2}, f)

            c = FakeCollector(tmp)
            c.collect_ci_results()
            assert len(c.ci_results) == 2
            assert c.coverage_data == {"line": 50.0}

    def test_collect_ci_no_coverage(self):
        """collect_ci_results: files without coverage data."""
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = os.path.join(tmp, ".osh", "ci")
            os.makedirs(ci_dir)

            with open(os.path.join(ci_dir, "layer1.json"), "w") as f:
                json.dump({"layer": 1}, f)

            c = FakeCollector(tmp)
            c.collect_ci_results()
            assert c.coverage_data is None

    def test_collect_sil_no_dir(self):
        """collect_sil_reports: CI dir doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            c = FakeCollector(tmp)
            c.collect_sil_reports()
            assert c.sil_reports == []

    def test_collect_sil_no_files(self):
        """collect_sil_reports: no *sil*.json files."""
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = os.path.join(tmp, ".osh", "ci")
            os.makedirs(ci_dir)

            c = FakeCollector(tmp)
            c.collect_sil_reports()
            assert c.sil_reports == []

    def test_collect_sil_with_data(self):
        """collect_sil_reports: reads SIL report files."""
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = os.path.join(tmp, ".osh", "ci")
            os.makedirs(ci_dir)

            sil_data = {"results": [{"name": "test1", "passed": True}]}
            with open(os.path.join(ci_dir, "test_sil.json"), "w") as f:
                json.dump(sil_data, f)

            c = FakeCollector(tmp)
            c.collect_sil_reports()
            assert len(c.sil_reports) == 1
            assert c.sil_reports[0]["_source_file"] == "test_sil.json"
            assert len(c.ci_results) == 1  # also appended to ci_results

    def test_collect_sil_corrupt_file(self):
        """collect_sil_reports: corrupt SIL file handled."""
        with tempfile.TemporaryDirectory() as tmp:
            ci_dir = os.path.join(tmp, ".osh", "ci")
            os.makedirs(ci_dir)

            with open(os.path.join(ci_dir, "corrupt_sil.json"), "w") as f:
                f.write("{bad json")

            c = FakeCollector(tmp)
            c.collect_sil_reports()  # should not raise
            assert c.sil_reports == []


class TestLegacyMapping:
    """Legacy SHALL ID → current REQ mapping filter (P1-2)."""

    def _make_project(self, tmp):
        """Project with a spec file (legacy + REQ rows) and a mapping doc."""
        specs = tmp / "specs"
        specs.mkdir(parents=True)
        (specs / "requirements-shall-table.md").write_text(
            "# REQ 需求表\n"
            "\n"
            "| ID | SHALL 语句 | ASIL | 范围 |\n"
            "|:---|:-----------|:-----|:-----|\n"
            "| REQ-001 | SHALL register a device | QM | 全部 |\n"
            "| REQ-010 | SHALL bind a key | ASIL-B | DKCS Core |\n",
            encoding="utf-8",
        )
        (specs / "legacy-shall-mapping.md").write_text(
            "# 遗留 SHALL ID 映射\n"
            "\n"
            "| 遗留 ID 模式 | 状态 | 现需求 ID | 说明 |\n"
            "|:-------------|:-----|:----------|:-----|\n"
            "| KL-SHALL-* | superseded | REQ-010~014 | 钥匙生命周期 → 密钥绑定/解绑/撤销/列表/分享 |\n"
            "| PE-SHALL-* | superseded | REQ-004 | 性能指标 |\n"
            "| 用户设备注册 | mapped | REQ-001 | 系统需求下放为软件需求 |\n",
            encoding="utf-8",
        )
        # A legacy spec file with table-style SHALL rows
        (specs / "spec-fix-p0.md").write_text(
            "# 修复 P0 遗留\n"
            "\n"
            "| ID | 描述 |\n"
            "|:---|:-----|\n"
            "| KL-SHALL-01 | 支持钥匙生命周期 |\n"
            "| KL-SHALL-02 | 非对称密钥对 |\n"
            "| PE-SHALL-01 | 解锁响应 ≤1s |\n",
            encoding="utf-8",
        )
        return tmp

    def test_legacy_ids_dropped_and_rs_mapped(self, tmp_path):
        """Legacy SHALL IDs dropped; RS entries deduped into existing REQ; REQ kept."""
        tmp = self._make_project(tmp_path)
        from yuleosh.evidence.collection import DataCollectionMixin

        class FakeCollector(DataCollectionMixin):
            def __init__(self, project_dir):
                self.project_dir = project_dir
                self.requirements = []
                self.scenarios = []

            def _find_latest_pipeline_spec(self):
                return None

        c = FakeCollector(str(tmp))
        c.collect_requirements()

        names = sorted(r.get("name", "") for r in c.requirements)
        # legacy KL-/PE- entries dropped; RS entry 用户设备注册 mapped → REQ-001
        # but the authoritative REQ-001 table row already exists → deduped
        assert not any(n.startswith("KL-SHALL") or n.startswith("PE-SHALL") for n in names), names
        assert "用户设备注册" not in names, names
        assert names == ["REQ-001", "REQ-010"], names
        # The authoritative table row (with SHALL statement) must be the one kept
        req001 = next(r for r in c.requirements if r.get("name") == "REQ-001")
        assert len(req001.get("shall", [])) == 1, req001

    def test_no_mapping_doc_no_filter(self, tmp_path):
        """Without the mapping doc, collection behaves as before."""
        specs = tmp_path / "specs"
        specs.mkdir()
        (specs / "spec-fix-p0.md").write_text(
            "# 修复\n\n| ID | 描述 |\n|:---|:-----|\n| KL-SHALL-01 | 生命周期 |\n",
            encoding="utf-8",
        )
        from yuleosh.evidence.collection import DataCollectionMixin

        class FakeCollector(DataCollectionMixin):
            def __init__(self, project_dir):
                self.project_dir = project_dir
                self.requirements = []
                self.scenarios = []

            def _find_latest_pipeline_spec(self):
                return None

        c = FakeCollector(str(tmp_path))
        c.collect_requirements()
        assert [r.get("name") for r in c.requirements] == ["KL-SHALL-01"]
