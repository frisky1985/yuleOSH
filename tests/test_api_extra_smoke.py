"""Additional smoke tests for yuleosh.api coverage — hitting more lines."""
import os, sys, json
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock, ANY
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestApiExtra:
    def test_json_ok_with_data(self):
        from yuleosh.api import json_ok
        r, s = json_ok([1, 2, 3])
        assert r["data"] == [1, 2, 3]

    def test_json_error_with_code(self):
        from yuleosh.api import json_error
        r, s = json_error("not found", 404)
        assert s == 404

    def test_apikeys_revoke(self):
        from yuleosh.api.apikeys import _revoke_key
        r, s = _revoke_key("invalid")
        assert s == 400

    def test_pipeline_handle_bad(self):
        from yuleosh.api.pipeline import handle_pipeline
        r, s = handle_pipeline("GET", "", {}, {})
        assert s == 405

    def test_project_get_nonexistent(self):
        from yuleosh.api.project import _get_project
        store = MagicMock()
        store.get_project.return_value = None
        r, s = _get_project(store, "nonexistent")
        assert s == 404

    def test_evidence_list_empty(self):
        from yuleosh.api.evidence import _list_evidence_files
        with patch("yuleosh.api.evidence.Path.exists", return_value=False):
            r, s = _list_evidence_files()
            assert s == 200
            assert r["data"]["files"] == []
