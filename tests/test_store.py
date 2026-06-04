"""Tests for SQLite persistent store."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from store import Store


def setup_function():
    Store.reset()


def test_save_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_pipeline("test-pipe", {
            "spec_path": "spec.md", "status": "completed",
            "artifacts": {"report": "final.md"},
            "steps": [{"name": "test", "status": "passed"}],
        })
        p = s.get_pipeline("test-pipe")
        assert p is not None
        assert p["status"] == "completed"


def test_list_pipelines():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_pipeline("p1", {"status": "completed"})
        pipes = s.list_pipelines()
        assert len(pipes) >= 1


def test_save_ci():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_ci({"layer": 1, "commit": "abc", "status": "passed"})
        results = s.list_ci()
        assert len(results) >= 1


def test_save_review():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.save_review("task-1", {"decision": "passed", "status": "completed"})
        reviews = s.list_reviews()
        assert len(reviews) >= 1


def test_init_project():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.init_project("my-project", "Test project")
        p = s.get_project("my-project")
        assert p is not None
        assert p["name"] == "my-project"


def test_evidence_log():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "test.db")
        s = Store(db)
        s.log_evidence("report.md", "md", "/tmp/report.md", 1024)
        evs = s.list_evidence()
        assert len(evs) >= 1
        assert evs[0]["name"] == "report.md"
