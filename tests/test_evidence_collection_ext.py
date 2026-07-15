"""Extended tests for evidence.collection — targeting uncovered paths."""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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
