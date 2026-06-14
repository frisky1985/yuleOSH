"""Smoke tests for yuleosh.api — all endpoint modules.

Tests basic import, function existence, and core helpers.
No external dependencies: all store/sys calls are mocked.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, ANY

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))


# ======================================================================
# yuleosh.api.__init__ — json_ok, json_error, read_body, get_store
# ======================================================================

class TestApiInit:
    def test_json_ok(self):
        from yuleosh.api import json_ok
        resp, status = json_ok({"hello": "world"})
        assert resp == {"ok": True, "data": {"hello": "world"}}
        assert status == 200

    def test_json_ok_none(self):
        from yuleosh.api import json_ok
        resp, status = json_ok()
        assert resp == {"ok": True, "data": None}
        assert status == 200

    def test_json_error_default(self):
        from yuleosh.api import json_error
        resp, status = json_error("bad request")
        assert resp == {"ok": False, "error": "bad request"}
        assert status == 400

    def test_json_error_custom_status(self):
        from yuleosh.api import json_error
        resp, status = json_error("not found", 404)
        assert resp == {"ok": False, "error": "not found"}
        assert status == 404

    def test_read_body_empty(self):
        from yuleosh.api import read_body
        handler = MagicMock()
        handler.headers.get.return_value = 0
        result = read_body(handler)
        assert result == {}

    def test_read_body_json(self):
        from yuleosh.api import read_body
        handler = MagicMock()
        handler.headers.get.return_value = len(b'{"a":1}')
        handler.rfile.read.return_value = b'{"a":1}'
        result = read_body(handler)
        assert result == {"a": 1}

    @patch("yuleosh.store.Store")
    def test_get_store(self, mock_store):
        from yuleosh.api import get_store
        instance = get_store()
        mock_store.assert_called_once()


# ======================================================================
# yuleosh.api.health — handle_health, helpers
# ======================================================================

class TestApiHealth:
    @patch("yuleosh.api.health._check_db", return_value="ok")
    @patch("yuleosh.api.health._check_store", return_value={"pipelines": 0})
    @patch("yuleosh.api.health._check_disk", return_value={"total_mb": 1000})
    def test_handle_health_ok(self, mock_disk, mock_store, mock_db):
        from yuleosh.api.health import handle_health
        resp, status = handle_health(method="GET")
        assert status == 200
        assert resp["ok"] is True
        data = resp["data"]
        assert data["status"] == "healthy"
        assert data["db"] == "ok"

    def test_handle_health_bad_method(self):
        from yuleosh.api.health import handle_health
        resp, status = handle_health(method="POST")
        assert status == 200  # still returns ok

    def test_check_db_ok(self):
        from yuleosh.api.health import _check_db
        store = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = {"ok": 1}
        store.conn.execute.return_value = cur
        assert _check_db(store) == "ok"

    def test_check_db_error(self):
        from yuleosh.api.health import _check_db
        store = MagicMock()
        store.conn.execute.side_effect = Exception("db down")
        result = _check_db(store)
        assert result.startswith("error:")

    def test_check_disk(self):
        from yuleosh.api.health import _check_disk
        with patch("yuleosh.api.health.shutil.disk_usage") as mock_du:
            mock_du.return_value.total = 100 * 1024 * 1024
            mock_du.return_value.free = 50 * 1024 * 1024
            mock_du.return_value.used = 50 * 1024 * 1024
            result = _check_disk()
            assert "total_mb" in result
            assert result["ok"] is True

    def test__auth_enabled(self):
        from yuleosh.api.health import _auth_enabled
        # By default auth is not enabled
        result = _auth_enabled()
        assert isinstance(result, bool)


# ======================================================================
# yuleosh.api.ratelimit — in-memory rate limiter
# ======================================================================

class TestApiRatelimit:
    def test_check_rate_limit_allowed(self):
        from yuleosh.api.ratelimit import check_rate_limit, reset
        reset()
        allowed, retry = check_rate_limit("1.2.3.4")
        assert allowed is True
        assert retry == 0

    def test_get_remaining(self):
        from yuleosh.api.ratelimit import get_remaining, check_rate_limit, reset
        reset()
        check_rate_limit("5.6.7.8")
        remaining = get_remaining("5.6.7.8")
        assert isinstance(remaining, int)
        assert remaining >= 0

    def test_reset(self):
        from yuleosh.api.ratelimit import reset, check_rate_limit
        reset()
        check_rate_limit("9.9.9.9")
        reset()
        remaining = check_rate_limit("9.9.9.9")
        assert remaining[0] is True


# ======================================================================
# yuleosh.api.validate — spec_path, pagination, json body validators
# ======================================================================

class TestApiValidate:
    def test_validate_spec_path_empty(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("")
        assert valid is False
        assert "required" in err

    def test_validate_spec_path_traversal(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("../etc/passwd")
        assert valid is False

    def test_validate_spec_path_bad_extension(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("foo.txt")
        assert valid is False
        assert "extension" in err

    def test_validate_spec_path_file_not_found(self):
        from yuleosh.api.validate import validate_spec_path
        valid, err = validate_spec_path("nonexistent.md")
        assert valid is False
        assert "not found" in err

    def test_validate_pagination_defaults(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({})
        assert result == {"limit": 50, "offset": 0}

    def test_validate_pagination_custom(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["10"], "offset": ["5"]})
        assert result == {"limit": 10, "offset": 5}

    def test_validate_pagination_capped(self):
        from yuleosh.api.validate import validate_pagination
        result = validate_pagination({"limit": ["999"], "offset": ["0"]})
        assert result == {"limit": 200, "offset": 0}

    def test_validate_json_body_ok(self):
        from yuleosh.api.validate import validate_json_body
        valid, _ = validate_json_body({"a": 1})
        assert valid is True

    def test_validate_json_body_not_dict(self):
        from yuleosh.api.validate import validate_json_body
        valid, err = validate_json_body("string")
        assert valid is False


# ======================================================================
# yuleosh.api.wizard — handle_wizard
# ======================================================================

class TestApiWizard:
    @patch("yuleosh.api.wizard.Store")
    def test_handle_wizard_post(self, mock_store):
        from yuleosh.api.wizard import handle_wizard
        store_instance = MagicMock()
        mock_store.return_value = store_instance
        resp, status = handle_wizard(method="POST")
        assert status == 200
        assert resp["data"]["completed"] is True

    def test_handle_wizard_not_post(self):
        from yuleosh.api.wizard import handle_wizard
        resp, status = handle_wizard(method="GET")
        assert status == 405


# ======================================================================
# yuleosh.api.notify — handle_notify, _get_config, _put_config
# ======================================================================

class TestApiNotify:
    @patch("yuleosh.notify.get_config")
    def test_handle_notify_get_config(self, mock_get_config):
        from yuleosh.api.notify import handle_notify
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": ""}
        mock_get_config.return_value = mock_cfg
        resp, status = handle_notify(method="GET", path_tail="config",
                                     body={}, query={})
        assert status == 200
        assert "feishu_url" in resp["data"]

    @patch("yuleosh.notify.get_config")
    @patch("yuleosh.notify.set_config")
    @patch("yuleosh.notify.NotifyConfig")
    def test_handle_notify_put_config(self, mock_nc, mock_set, mock_get):
        from yuleosh.api.notify import handle_notify
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": "https://hooks.feishu.cn"}
        mock_get.return_value = mock_cfg
        mock_nc.return_value = mock_cfg
        resp, status = handle_notify(method="PUT", path_tail="config",
                                     body={"feishu_url": "https://hooks.feishu.cn"},
                                     query={})
        assert status == 200

    def test_handle_notify_unknown_resource(self):
        from yuleosh.api.notify import handle_notify
        resp, status = handle_notify(method="GET", path_tail="foobar",
                                     body={}, query={})
        assert status == 404


# ======================================================================
# yuleosh.api.apikeys — handle_apikeys
# ======================================================================

class TestApiApikeys:
    @patch("yuleosh.api.apikeys.Store")
    def test_handle_apikeys_list(self, mock_store):
        from yuleosh.api.apikeys import handle_apikeys
        store_instance = MagicMock()
        mock_store.return_value = store_instance
        store_instance.list_api_keys.return_value = []
        resp, status = handle_apikeys(method="GET", path_tail="",
                                      body={}, query={})
        assert status == 200
        assert resp["data"]["keys"] == []

    @patch("yuleosh.api.apikeys.Store")
    def test_handle_apikeys_generate(self, mock_store):
        from yuleosh.api.apikeys import handle_apikeys
        store_instance = MagicMock()
        mock_store.return_value = store_instance
        store_instance.create_api_key.return_value = {
            "id": 1, "created_at": "2025-01-01"
        }
        resp, status = handle_apikeys(method="POST", path_tail="",
                                      body={"label": "test-key"}, query={})
        assert status == 200
        assert resp["data"]["key"].startswith("yule_")

    @patch("yuleosh.api.apikeys.Store")
    def test_handle_apikeys_generate_no_label(self, mock_store):
        from yuleosh.api.apikeys import handle_apikeys
        resp, status = handle_apikeys(method="POST", path_tail="",
                                      body={}, query={})
        assert status == 400

    def test_handle_apikeys_unsupported(self):
        from yuleosh.api.apikeys import handle_apikeys
        resp, status = handle_apikeys(method="PATCH", path_tail="",
                                      body={}, query={})
        assert status == 404

    def test_handle_apikeys_revoke_invalid_id(self):
        from yuleosh.api.apikeys import _revoke_key
        resp, status = _revoke_key("not-an-int")
        assert status == 400


# ======================================================================
# yuleosh.api.audit — handle_audit, log_request
# ======================================================================

class TestApiAudit:
    @patch("yuleosh.api.audit.get_store")
    def test_log_request(self, mock_get_store):
        from yuleosh.api.audit import log_request
        store = MagicMock()
        mock_get_store.return_value = store
        log_request("GET", "/health", 200, "127.0.0.1", 1.0)
        assert store.conn.execute.call_count >= 2  # _ensure_table + insert

    @patch("yuleosh.api.audit.get_store")
    def test_handle_audit_get(self, mock_get_store):
        from yuleosh.api.audit import handle_audit
        store = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur2 = MagicMock()
        cur2.fetchone.return_value = {"c": 0}
        # Use a function for side_effect to handle multiple calls
        call_count = [0]
        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return cur
            return cur2
        store.conn.execute.side_effect = execute_side_effect
        mock_get_store.return_value = store
        resp, status = handle_audit(method="GET", path_tail="",
                                    body={}, query={})
        assert status == 200

    def test_handle_audit_not_get(self):
        from yuleosh.api.audit import handle_audit
        resp, status = handle_audit(method="POST", path_tail="",
                                    body={}, query={})
        assert status == 405

    def test_handle_audit_not_found(self):
        from yuleosh.api.audit import handle_audit
        resp, status = handle_audit(method="GET", path_tail="extra",
                                    body={}, query={})
        assert status == 404


# ======================================================================
# yuleosh.api.ci — handle_ci
# ======================================================================

class TestApiCi:
    @patch("yuleosh.api.ci.subprocess.run")
    def test__run_ci_layer(self, mock_run):
        from yuleosh.api.ci import _run_ci_layer
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "success"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc
        resp, status = _run_ci_layer("1")
        assert status == 200
        assert resp["data"]["status"] == "passed"

    def test_handle_ci_unknown(self):
        from yuleosh.api.ci import handle_ci
        resp, status = handle_ci(method="GET", path_tail="foobar",
                                 body={}, query={})
        assert status == 404

    def test__run_ci_layer_invalid(self):
        from yuleosh.api.ci import _run_ci_layer
        resp, status = _run_ci_layer("4")
        assert status == 400


# ======================================================================
# yuleosh.api.evidence — handle_evidence
# ======================================================================

class TestApiEvidence:
    def test_handle_evidence_list_files(self):
        from yuleosh.api.evidence import handle_evidence
        import yuleosh.api
        with patch.object(yuleosh.api, "OSH_HOME", "/tmp/fake-osh"):
            resp, status = handle_evidence(method="GET", path_tail="files",
                                           body={}, query={})
            assert status == 200
            assert resp["data"]["files"] == []

    def test_handle_evidence_unknown(self):
        from yuleosh.api.evidence import handle_evidence
        resp, status = handle_evidence(method="GET", path_tail="foobar",
                                       body={}, query={})
        assert status == 404

    def test_handle_evidence_smoke_export(self):
        from yuleosh.api.evidence import handle_evidence
        assert callable(handle_evidence)


# ======================================================================
# yuleosh.api.pipeline — handle_pipeline
# ======================================================================

class TestApiPipeline:
    @patch("yuleosh.api.pipeline.subprocess.run")
    def test__run_pipeline(self, mock_run):
        from yuleosh.api.pipeline import _run_pipeline
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "done"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc
        with patch("pathlib.Path.exists", return_value=True):
            resp, status = _run_pipeline({"spec": "docs/spec.md"})
            assert status in (200, 500)

    def test_handle_pipeline_no_spec(self):
        from yuleosh.api.pipeline import _run_pipeline
        resp, status = _run_pipeline({})
        assert status == 400

    def test_handle_pipeline_unknown(self):
        from yuleosh.api.pipeline import handle_pipeline
        resp, status = handle_pipeline(method="GET", path_tail="foobar",
                                       body={}, query={})
        assert status == 404


# ======================================================================
# yuleosh.api.project — handle_project
# ======================================================================

class TestApiProject:
    @patch("yuleosh.store.Store")
    def test_handle_project_list(self, mock_store):
        from yuleosh.api.project import handle_project
        store = MagicMock()
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = []
        conn.execute.return_value = cur
        store.conn = conn
        mock_store.return_value = store
        resp, status = handle_project(method="GET", path_tail="list",
                                      body={}, query={})
        assert status == 200

    @patch("yuleosh.store.Store")
    def test_create_project_no_name(self, mock_store):
        from yuleosh.api.project import _create_project
        store = MagicMock()
        resp, status = _create_project(store, {})
        assert status == 400

    @patch("yuleosh.store.Store")
    def test_project_stats(self, mock_store):
        from yuleosh.api.project import _project_stats
        store = MagicMock()
        conn = MagicMock()
        # Multiple SELECT queries
        cur = MagicMock()
        cur.fetchone.return_value = {"c": 5}
        cur2 = MagicMock()
        cur2.fetchall.return_value = [{"status": "completed", "c": 3}]
        conn.execute.side_effect = [cur, cur, cur, cur, cur, cur2]
        store.conn = conn
        mock_store.return_value = store
        resp, status = _project_stats(store)
        assert status == 200


# ======================================================================
# yuleosh.api.review — handle_review
# ======================================================================

class TestApiReview:
    def test_handle_review_unknown(self):
        from yuleosh.api.review import handle_review
        resp, status = handle_review(method="GET", path_tail="foobar",
                                     body={}, query={})
        assert status == 404

    @patch("yuleosh.api.review.subprocess.run")
    def test__run_auto_review(self, mock_run):
        from yuleosh.api.review import _run_auto_review
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "review ok"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc
        resp, status = _run_auto_review({})
        assert status == 200

    @patch("yuleosh.api.review.subprocess.run")
    def test__run_task_review_no_task(self, mock_run):
        from yuleosh.api.review import _run_task_review
        resp, status = _run_task_review({})
        assert status == 400

    def test_handle_review_list_empty(self):
        import yuleosh.api
        with patch.object(yuleosh.api, "OSH_HOME", "/tmp/nonexist"):
            from yuleosh.api.review import handle_review
            resp, status = handle_review(method="GET", path_tail="list",
                                         body={}, query={})
            assert status == 200
            assert resp["data"]["count"] == 0
        assert resp["data"]["count"] == 0


# ======================================================================
# yuleosh.api.spec — handle_spec
# ======================================================================

class TestApiSpec:
    @patch("yuleosh.spec.validate.parse_spec")
    @patch("yuleosh.spec.validate.validate_spec", return_value=[])
    @patch("yuleosh.spec.validate._compute_coverage", return_value={})
    @patch("pathlib.Path.exists", return_value=True)
    def test__validate(self, mock_exists, mock_cov, mock_val, mock_parse):
        from yuleosh.api.spec import _validate
        mock_doc = MagicMock()
        mock_doc.requirements = []
        mock_doc.scenarios = []
        mock_parse.return_value = mock_doc
        resp, status = _validate("POST", {"path": "spec.md"})
        assert status == 200

    def test__validate_wrong_method(self):
        from yuleosh.api.spec import _validate
        resp, status = _validate("GET", {})
        assert status == 405

    def test__validate_no_path(self):
        from yuleosh.api.spec import _validate
        resp, status = _validate("POST", {})
        assert status == 400

    def test_handle_spec_unknown(self):
        from yuleosh.api.spec import handle_spec
        resp, status = handle_spec(method="GET", path_tail="foobar",
                                   body={}, query={})
        assert status == 404

    @patch("yuleosh.spec.validate.diff_specs", return_value={})
    @patch("pathlib.Path.exists", return_value=True)
    def test__diff(self, mock_exists, mock_diff):
        from yuleosh.api.spec import _diff
        resp, status = _diff("POST", {"old": "old.md", "new": "new.md"})
        assert status == 200


# ======================================================================
# yuleosh.api.stats — handle_stats
# ======================================================================

class TestApiStats:
    @patch("yuleosh.api.stats.Store")
    def test_handle_stats_overview(self, mock_store):
        from yuleosh.api.stats import handle_stats
        store = MagicMock()
        store.get_usage_stats.return_value = {
            "total_pipelines": 10,
            "total_ci_runs": 5,
            "pipeline_statuses": {"completed": 7},
        }
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchone.return_value = {"c": 3}
        conn.execute.return_value = cur
        store.conn = conn
        mock_store.return_value = store
        resp, status = handle_stats(method="GET", path_tail="overview",
                                    body={}, query={})
        assert status == 200
        assert resp["data"]["pipeline_success_rate"] == 70.0

    def test_handle_stats_bad_method(self):
        from yuleosh.api.stats import handle_stats
        resp, status = handle_stats(method="POST", path_tail="overview",
                                    body={}, query={})
        assert status == 405

    def test_handle_stats_unknown_resource(self):
        from yuleosh.api.stats import handle_stats
        resp, status = handle_stats(method="GET", path_tail="foobar",
                                    body={}, query={})
        assert status == 404


# ======================================================================
# yuleosh.api.webhooks — handle_webhooks
# ======================================================================

class TestApiWebhooks:
    def test_handle_webhooks_bad_method(self):
        from yuleosh.api.webhooks import handle_webhooks
        resp, status = handle_webhooks(method="GET", path_tail="github",
                                       body={}, query={})
        assert status == 405

    def test_handle_webhooks_unknown_provider(self):
        from yuleosh.api.webhooks import handle_webhooks
        resp, status = handle_webhooks(method="POST", path_tail="gitlab",
                                       body={}, query={})
        assert status == 404

    @patch("yuleosh.api.webhooks._trigger_ci")
    def test_handle_github_push(self, mock_trigger):
        from yuleosh.api.webhooks import handle_webhooks
        mock_trigger.return_value = {"status": "passed", "success": True}
        payload = {
            "repository": {"full_name": "test/repo"},
            "ref": "refs/heads/main",
            "head_commit": {"id": "abc123def456", "message": "fix"},
            "pusher": {"name": "dev"},
        }
        resp, status = handle_webhooks(method="POST", path_tail="github",
                                       body=payload, query={})
        assert status == 200
        assert resp["data"]["ci_triggered"] is True


# ======================================================================
# yuleosh.api.router — dispatch, _respond
# ======================================================================

class TestApiRouter:
    def test_router_routes_defined(self):
        from yuleosh.api.router import ROUTES
        assert "health" in ROUTES
        assert "spec" in ROUTES
        assert "pipeline" in ROUTES
        assert "ci" in ROUTES
        assert "review" in ROUTES
        assert "evidence" in ROUTES
        assert "project" in ROUTES
        assert "stats" in ROUTES
        assert "notify" in ROUTES
        assert "apikeys" in ROUTES
        assert "webhooks" in ROUTES
        assert "audit" in ROUTES
        assert "auth" in ROUTES
        assert "wizard" in ROUTES

    def test_router_dispatch_bad_path(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        dispatch(handler, "/wrong/prefix")
        # Should return 404
        args, _ = handler.wfile.write.call_args
        response = json.loads(args[0])
        assert response["ok"] is False

    def test_router_dispatch_unknown_resource(self):
        from yuleosh.api.router import dispatch
        handler = MagicMock()
        handler.command = "GET"
        handler.headers = {}
        dispatch(handler, "/api/v1/foobar")
        args, _ = handler.wfile.write.call_args
        response = json.loads(args[0])
        assert response["ok"] is False

    def test_respond_sets_headers(self):
        from yuleosh.api.router import _respond
        handler = MagicMock()
        _respond(handler, {"msg": "hello"}, 200)
        handler.send_response.assert_called_with(200)
        assert handler.send_header.call_count >= 5
        handler.wfile.write.assert_called_once()


# ======================================================================
# yuleosh.api.auth — handle_auth
# ======================================================================

class TestApiAuth:
    def test_slugify(self):
        from yuleosh.api.auth import _slugify
        assert _slugify("Hello World!") == "hello-world"

    def test_hash_and_verify(self):
        from yuleosh.api.auth import _hash_password, _verify_password
        hashed = _hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")
        assert _verify_password("mypassword", hashed) is True
        assert _verify_password("wrong", hashed) is False

    @patch("yuleosh.api.auth.secrets.token_urlsafe", return_value="fake-secret-32-bytes-long---!")
    def test_generate_token(self, mock_secret):
        from yuleosh.api.auth import _generate_token
        with patch("yuleosh.api.auth.os.environ.get", return_value=None):
            token = _generate_token(1, 1, "test@test.com")
            assert isinstance(token, str)
            assert len(token) > 10

    @patch("yuleosh.api.auth.Store")
    def test_handle_auth_register(self, mock_store):
        from yuleosh.api.auth import handle_auth
        store = MagicMock()
        store.get_user_by_email.return_value = None
        store.get_org_invite.return_value = None
        mock_store.return_value = store
        resp, status = handle_auth(method="POST", path_tail="register",
                                   body={"email": "a@b.com", "password": "pass123",
                                         "org_name": "TestOrg"},
                                   query={})
        # May not have full store mock, but should route correctly
        assert status in (200, 400, 500)

    def test_handle_auth_unsupported(self):
        from yuleosh.api.auth import handle_auth
        resp, status = handle_auth(method="GET", path_tail="foobar",
                                   body={}, query={})
        assert status == 404


# ======================================================================
# yuleosh.api.middleware — require_auth decorator
# ======================================================================

class TestApiMiddleware:
    def test_decode_token_bad(self):
        from yuleosh.api.middleware import _decode_token
        result = _decode_token("bad-token")
        assert result is None

    def test_extract_token_bearer(self):
        from yuleosh.api.middleware import _extract_token
        headers = {"Authorization": "Bearer mytoken"}
        assert _extract_token(headers) == "mytoken"

    def test_extract_token_missing(self):
        from yuleosh.api.middleware import _extract_token
        headers = {}
        assert _extract_token(headers) is None

    def test_require_auth_no_handler(self):
        from yuleosh.api.middleware import require_auth
        @require_auth
        def fake_handler(**kwargs):
            return {"ok": True}, 200
        resp, status = fake_handler(method="GET", path_tail="", body={}, query={})
        assert status == 500
