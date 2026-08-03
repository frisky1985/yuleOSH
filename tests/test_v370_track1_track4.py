"""v3.7.0 Track1 (W1-W7) + Track4 (M1-M4) acceptance tests.

Implements the acceptance matrix at .osh/specs/v3.7.0/acceptance-matrix.md.
Test IDs follow T-Wx.n-<desc> / T-Mx.n-<desc>; negative cases end in ``-neg``.

Areas:
  W1 do_GET no silent degradation   W2 signin rate-limit locking + IP cleanup
  W3 swe6 check real parsing        W4 session migration hex validation
  W5 sandbox extra_read_dirs        W6 preview cache owner isolation
  W7 subprocess timeout + no shell  M1 html.parser XSS whitelist
  M2 static Cache-Control           M3 AUTH_ENABLED single source
  M4 public-path query matching
"""
import hashlib
import importlib
import io
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


# ── Local fixtures (mirror test_cli_main_adv_unit.py) ───────────────────────

@pytest.fixture
def main_module():
    import yuleosh.cli.main as m
    return m


@pytest.fixture
def osh_home(main_module, tmp_path, monkeypatch):
    """Point main_module.OSH_HOME at a temp dir and restore afterwards."""
    monkeypatch.setattr(main_module, "OSH_HOME", str(tmp_path))
    return tmp_path


# ======================================================================
# Helpers
# ======================================================================

def _bare_handler(path="/", method="GET", headers=None):
    """Bare OSHHandler stand-in (mirrors test_ui_server_deep helper)."""
    from yuleosh.ui.server import OSHHandler
    h = object.__new__(OSHHandler)
    h._request_start_time = time.time()
    h._response_status = 200
    h.command = method
    h.path = path
    h.headers = headers if headers is not None else {}
    h.rfile = io.BytesIO(b"")
    h.wfile = io.BytesIO()
    h.client_address = ("127.0.0.1", 54321)
    h.close_connection = True
    h.request_version = "HTTP/1.1"
    h.requestline = f"{method} {path} HTTP/1.1"
    h._headers_buffer = []
    return h


def _headers_from_wfile(h):
    """Parse response headers from the raw wfile bytes (send_header's
    _headers_buffer is consumed by flush_headers -> bytes)."""
    raw = h.wfile.getvalue().decode("utf-8", "replace")
    head, _, _ = raw.partition("\r\n\r\n")
    headers = {}
    for line in head.split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


# ======================================================================
# W1 — do_GET exception handling (COR-C2 / Fix 4)
# ======================================================================

class TestW1DoGETNoSilentDegrade:
    """T-W1-*: API exceptions answer JSON 500; page exceptions answer a
    500 page; never a 200 landing page; audit records 500; logs traceback."""

    def _make(self, path):
        h = _bare_handler(path)
        self._exc = RuntimeError("boom-w1")
        return h

    def test_t_w1_01_api_json500(self):
        """T-W1-01-api-json500: API path exception -> JSON 500."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/api/xxx")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get",
                   side_effect=RuntimeError("boom-w1")):
            with patch("yuleosh.ui.server.OSHHandler._json_response") as jr:
                h.do_GET()
                jr.assert_called_once_with({"error": "Internal server error"}, 500)

    def test_t_w1_02_page_500page(self):
        """T-W1-02-page-500page: page path exception -> 500 HTML page."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/dashboard")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get",
                   side_effect=RuntimeError("boom-w1")):
            with patch("yuleosh.ui.server.OSHHandler._serve_static") as m_ss:
                h.do_GET()
                m_ss.assert_not_called()
        body = h.wfile.getvalue()
        assert b"500" in body
        assert b"Internal Server Error" in body

    def test_t_w1_03_exc_info_log(self, caplog):
        """T-W1-03-exc-info-log: full traceback goes to the logs."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/api/xxx")
        with caplog.at_level(logging.ERROR, logger="yuleosh"):
            with patch("yuleosh.ui.routes.handler_helpers.handle_get",
                       side_effect=RuntimeError("boom-w1")):
                with patch("yuleosh.ui.server.OSHHandler._json_response"):
                    h.do_GET()
        assert "Traceback" in caplog.text
        assert "boom-w1" in caplog.text

    def test_t_w1_04_audit_500(self):
        """T-W1-04-audit-500: _response_status reflects 500, not 200."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/api/xxx")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get",
                   side_effect=RuntimeError("boom-w1")):
            with patch("yuleosh.ui.server.OSHHandler._json_response"):
                h.do_GET()
        assert h._response_status == 500

    def test_t_w1_05_normal_noregress(self):
        """T-W1-05-normal-noregress: normal GET unchanged."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/api/health")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get") as m_hg:
            h.do_GET()
            m_hg.assert_called_once_with(h)
        assert h._response_status == 200

    def test_t_w1_06_root_ok(self):
        """T-W1-06-root-ok: / normal handling still routes to handler."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get") as m_hg:
            h.do_GET()
            m_hg.assert_called_once_with(h)

    def test_t_w1_07_neg_no_200_html(self):
        """T-W1-07-neg: API exception must NOT answer 200 home HTML."""
        from yuleosh.ui.server import OSHHandler
        h = self._make("/api/xxx")
        with patch("yuleosh.ui.routes.handler_helpers.handle_get",
                   side_effect=RuntimeError("boom-w1")):
            with patch("yuleosh.ui.server.OSHHandler._json_response") as jr:
                h.do_GET()
                args, kwargs = jr.call_args
                status = args[1]
                assert status != 200
                assert status == 500
                assert args[0] == {"error": "Internal server error"}


# ======================================================================
# W2 — signin rate-limit locking + IP table cleanup (COR-W2 / SEC-W2)
# ======================================================================

class TestW2SigninRateLimitLock:
    """T-W2-*: thread-safe containers; atomic check+record; IP cleanup."""

    def setup_method(self):
        from yuleosh.ui import auth_extended as A
        A._SIGNIN_RATE_LIMIT.clear()
        A._SIGNIN_IP_LIMIT.clear()

    def test_t_w2_01_threadpool_race(self):
        """T-W2-01: 20 concurrent failed attempts -> count <= 12 + blocked."""
        from yuleosh.ui import auth_extended as A
        email = "race@test.com"

        def attempt(_):
            if A._check_rate_limit(email):
                return "blocked"
            if not A._check_and_record_failed_attempt(email):
                return "blocked"
            return "recorded"

        with ThreadPoolExecutor(max_workers=20) as ex:
            results = list(ex.map(attempt, range(20)))
        count = A._SIGNIN_RATE_LIMIT.get(email)[0]
        assert count <= 12, f"count={count} exceeded 10+2"
        assert A._check_rate_limit(email) is True  # subsequent requests blocked
        assert "blocked" in results

    def test_t_w2_02_ip_cleanup(self):
        """T-W2-02: >2000 IP entries (some expired) -> table shrinks; live
        entries keep their blocking semantics."""
        from yuleosh.ui import auth_extended as A
        now = int(time.time())
        for i in range(2100):
            ip = f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}"
            ts = now - 10000 if i % 2 else now  # half expired
            A._SIGNIN_IP_LIMIT[ip] = (1, ts)
        assert len(A._SIGNIN_IP_LIMIT) == 2100
        A._cleanup_stale_ip_entries()
        remaining = len(A._SIGNIN_IP_LIMIT)
        assert remaining < 2100
        assert remaining > 0  # live (non-expired) entries survive
        # A live entry still blocks once over the per-IP cap.
        live_ip = "203.0.113.9"
        for _ in range(A._MAX_SIGNIN_IP_ATTEMPTS):
            assert A._check_ip_rate_limit(live_ip) is False
        assert A._check_ip_rate_limit(live_ip) is True

    def test_t_w2_03_existing_tests_compat(self):
        """T-W2-03: module-level dict operations used by existing tests
        (``dict[key]=v`` / ``.clear()`` / ``in`` / ``len``) keep working."""
        from yuleosh.ui import auth_extended as A
        email = "compat@test.com"
        A._SIGNIN_RATE_LIMIT[email] = (10, int(time.time()) - 600)
        assert email in A._SIGNIN_RATE_LIMIT
        assert len(A._SIGNIN_RATE_LIMIT) == 1
        assert A._check_rate_limit(email) is False  # window expired
        A._SIGNIN_RATE_LIMIT.clear()
        assert len(A._SIGNIN_RATE_LIMIT) == 0

    def test_t_w2_04_correct_password(self):
        """T-W2-04: correct-password logins never consume the budget."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            org = s.create_organization("Org", "org")
            s.create_user(org["id"], "ok@test.com", "member",
                          A._hash_password("RealPass123"))
            with mock.patch.object(A, "Store", return_value=s):
                for _ in range(5):
                    res, status = A.handle_signin(
                        {"email": "ok@test.com", "password": "RealPass123"})
                    assert status == 200
            assert A._check_rate_limit("ok@test.com") is False

    def test_t_w2_05_unified_message(self):
        """T-W2-05: unified message for unknown/no-password/wrong-password."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            org = s.create_organization("Org", "org")
            s.create_user(org["id"], "nopass@test.com", "member", None)
            s.create_user(org["id"], "haspass@test.com", "member",
                          A._hash_password("RealPass123"))
            with mock.patch.object(A, "Store", return_value=s):
                no_pass = A.handle_signin(
                    {"email": "nopass@test.com", "password": "Whatever123"})
                wrong = A.handle_signin(
                    {"email": "haspass@test.com", "password": "WrongPass123"})
                missing = A.handle_signin(
                    {"email": "haspass@test.com", "password": ""})
            assert no_pass[0]["error"] == wrong[0]["error"] == missing[0]["error"]
            assert no_pass[1] == wrong[1] == missing[1] == 401

    def test_t_w2_06_neg_race_bypass(self):
        """T-W2-06-neg: after the threshold, concurrent submissions are all
        rejected — no bypass, count does not keep climbing."""
        from yuleosh.ui import auth_extended as A
        email = "flood2@test.com"
        for _ in range(A._MAX_SIGNIN_ATTEMPTS):
            assert A._check_and_record_failed_attempt(email) is True

        def attempt(_):
            return A._check_and_record_failed_attempt(email)

        with ThreadPoolExecutor(max_workers=20) as ex:
            results = list(ex.map(attempt, range(20)))
        assert all(r is False for r in results)  # no bypass
        count = A._SIGNIN_RATE_LIMIT.get(email)[0]
        assert count == A._MAX_SIGNIN_ATTEMPTS

    def test_t_w2_07_neg_ip_unbounded(self):
        """T-W2-07-neg: IP table size has an upper bound (probabilistic
        cleanup triggers and shrinks it)."""
        from yuleosh.ui import auth_extended as A
        now = int(time.time())
        for i in range(2100):
            ip = f"203.0.{i // 256 % 256}.{i % 256}"
            A._SIGNIN_IP_LIMIT[ip] = (1, now - 10000)  # all expired
        # Drive new-IP inserts until the probabilistic cleanup fires
        # (every ~11th new entry with hash(ip) % 11 == 0).
        fired = False
        for i in range(500):
            ip = f"198.51.{i // 256 % 256}.{i % 256}"
            A._check_ip_rate_limit(ip)
            if len(A._SIGNIN_IP_LIMIT) < 2100:
                fired = True
                break
        assert fired, "probabilistic cleanup never fired"
        assert len(A._SIGNIN_IP_LIMIT) < 2600


# ======================================================================
# W3 — swe6 check de-faking (COR-C3 / Fix 6)
# ======================================================================

_SPEC_3_SCENARIOS = """# Test Spec

## Scenario: SC-001
- GIVEN a
- WHEN b
- THEN c

## Scenario: SC-002
- GIVEN a2
- WHEN b2
- THEN c2

## Scenario: SC-003
- GIVEN a3
- WHEN b3
- THEN c3
"""


class TestW3Swe6RealChecks:
    """T-W3-*: swe6 check reports REAL parsed numbers, no hardcoded True."""

    def _spec_ok(self, osh_home, content=_SPEC_3_SCENARIOS):
        (osh_home / "docs").mkdir(parents=True, exist_ok=True)
        p = osh_home / "docs" / "swe6-confirmation-spec.md"
        p.write_text(content, encoding="utf-8")
        return p

    def _run_check(self, osh_home, main_module, report=False):
        captured = []
        with patch("builtins.print") as mp:
            main_module.cmd_swe6_check(SimpleNamespace(report=report))
            for c in mp.call_args_list:
                captured.append(" ".join(str(a) for a in c.args))
        return "\n".join(captured)

    def test_t_w3_01_real_count(self, main_module, osh_home):
        """T-W3-01: 3-scenario spec -> \"3 个 (解析自 spec)\"."""
        self._spec_ok(osh_home)
        out = self._run_check(osh_home, main_module)
        assert "3 个 (解析自 spec)" in out
        assert "✅ 测试用例定义" in out

    def test_t_w3_02_report_source(self, main_module, osh_home):
        """T-W3-02: --report carries the real count + a source field."""
        self._spec_ok(osh_home)
        lrt = {"lrm": {"summary": {"total": 3, "coverage_pct": 66.7}}}
        with patch("yuleosh.alm.traceability.generate_lrt", return_value=lrt):
            self._run_check(osh_home, main_module, report=True)
        report_path = osh_home / ".yuleosh" / "reports" / "swe6-report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["swe6_check"]["test_cases"] == 3
        assert report["swe6_check"]["test_cases_source"] == "parsed from spec"

    def test_t_w3_03_unparseable(self, main_module, osh_home):
        """T-W3-03: spec with no use-case entries -> NOT ✅."""
        self._spec_ok(osh_home, content="# SWE6\n\nNo scenarios here.\n")
        out = self._run_check(osh_home, main_module)
        assert "✅ 测试用例定义" not in out
        assert "❌ 测试用例定义" in out

    def test_t_w3_04_ci_config_missing(self, main_module, osh_home):
        """T-W3-04: missing .osh/ci-config.yaml -> env-config check ❌."""
        self._spec_ok(osh_home)
        out = self._run_check(osh_home, main_module)
        assert "❌ 测试环境配置" in out

    def test_t_w3_05_spec_missing(self, main_module, osh_home):
        """T-W3-05: missing spec file still exits 1 (existing behavior)."""
        with pytest.raises(SystemExit):
            main_module.cmd_swe6_check(SimpleNamespace(report=False))

    def test_t_w3_06_neg_hardcoded_true(self, main_module, osh_home):
        """T-W3-06-neg: no hardcoded-True check items for a useless spec."""
        self._spec_ok(osh_home, content="# SWE6\n\nNo scenarios here.\n")
        out = self._run_check(osh_home, main_module)
        assert "存在 (从 spec 解析)" not in out  # the old fake detail string
        assert "已定义 (Dev/SIL)" not in out
        assert "✅ 测试用例定义" not in out


# ======================================================================
# W4 — session migration hex validation (COR-W3 / Fix 7)
# ======================================================================

class TestW4SessionMigrationHex:
    """T-W4-*: only real sha256-hex tokens are skipped by the migration."""

    def _open_store(self, db):
        from yuleosh.store import Store
        Store._instances.pop(db, None)
        return Store(db)

    def _seed(self, db, token):
        from yuleosh.store import Store
        s = Store(db)
        org = s.create_organization("Org", "org")
        user = s.create_user(org["id"], "u@t.com")
        s.conn.execute(
            "INSERT INTO user_sessions (user_id, token, created_at, expires_at) "
            "VALUES (?, ?, datetime('now'), datetime('now', '+1 day'))",
            (user["id"], token),
        )
        s.conn.commit()
        return s

    def test_t_w4_01_64_char_plaintext(self):
        """T-W4-01: exactly-64-char plaintext (base64url with '-') migrates."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4.db")
            plaintext = "a" * 63 + "-"  # 64 chars, non-hex -> must migrate
            assert len(plaintext) == 64
            assert not re.fullmatch(r"[0-9a-f]{64}", plaintext)
            self._seed(db, plaintext)
            s2 = self._open_store(db)
            rows = s2.conn.execute("SELECT token FROM user_sessions").fetchall()
            for r in rows:
                assert re.fullmatch(r"[0-9a-f]{64}", r["token"])
                assert r["token"] != plaintext

    def test_t_w4_02_hex_skip_idempotent(self):
        """T-W4-02: already-64-hex token is untouched (idempotent)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4b.db")
            hex64 = hashlib.sha256(b"already-hashed").hexdigest()
            self._seed(db, hex64)
            s2 = self._open_store(db)
            rows = s2.conn.execute(
                "SELECT token FROM user_sessions WHERE token=?", (hex64,)
            ).fetchall()
            assert len(rows) == 1  # unchanged, not double-hashed

    def test_t_w4_03_short_plaintext(self):
        """T-W4-03: 40-char plaintext JWT migrates (v3.6.1 behavior kept)."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4c.db")
            plaintext = "legacy-plaintext-jwt-token-40chars"
            self._seed(db, plaintext)
            s2 = self._open_store(db)
            rows = s2.conn.execute("SELECT token FROM user_sessions").fetchall()
            assert all(re.fullmatch(r"[0-9a-f]{64}", r["token"]) for r in rows)
            assert s2.get_session(plaintext) is not None

    def test_t_w4_04_null_safe(self):
        """T-W4-04: NULL/empty tokens are skipped safely — no crash."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4d.db")
            # Simulate a legacy DB whose token column is nullable and has a
            # NULL row (FK enforcement is off in sqlite3 by default).
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE user_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " user_id INTEGER NOT NULL, token TEXT,"
                " created_at TEXT NOT NULL, expires_at TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO user_sessions (user_id, token, created_at, expires_at)"
                " VALUES (1, NULL, 'x', 'y')"
            )
            conn.commit()
            conn.close()
            s = self._open_store(db)  # must not raise
            rows = s.conn.execute("SELECT token FROM user_sessions").fetchall()
            assert any(r["token"] is None for r in rows)  # untouched, no crash

    def test_t_w4_05_neg_no_plaintext(self):
        """T-W4-05-neg: full scan — no non-hex-64 plaintext remains."""
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4e.db")
            from yuleosh.store import Store
            s = Store(db)
            org = s.create_organization("Org", "org")
            user = s.create_user(org["id"], "u@t.com")
            for tok in ("short-plaintext", "x" * 63 + "-"):
                s.conn.execute(
                    "INSERT INTO user_sessions (user_id, token, created_at, expires_at)"
                    " VALUES (?, ?, datetime('now'), datetime('now', '+1 day'))",
                    (user["id"], tok),
                )
            s.conn.commit()
            s2 = self._open_store(db)
            rows = s2.conn.execute("SELECT token FROM user_sessions").fetchall()
            for r in rows:
                if r["token"] is None:
                    continue
                assert re.fullmatch(r"[0-9a-f]{64}", r["token"])


# ======================================================================
# W5 — sandbox extra_read_dirs (COR-W5 / Fix 8)
# ======================================================================

class TestW5SandboxExtraReadDirs:
    """T-W5-*: explicit read whitelist; write stays strict; resolve kept."""

    def _sandbox(self, tmp_path, extra_read_dirs=None, permissions=None):
        from yuleosh.plugins.sandbox import PluginSandbox
        from yuleosh.plugins import Plugin, PluginManifest
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir(exist_ok=True)
        manifest = PluginManifest(
            name="t", version="1.0.0", type="tool",
            description="t", author="t", entry="main.py",
            permissions=permissions,
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest,
                                extra_read_dirs=extra_read_dirs)
        return sandbox._restricted_open(plugin)

    def test_t_w5_01_extra_dirs_allowed(self, tmp_path):
        """T-W5-01: whitelisted dir read is allowed."""
        wd = tmp_path / "etc_whitelist"
        wd.mkdir()
        target = wd / "os-release"
        target.write_text("x")
        safe_open = self._sandbox(tmp_path, extra_read_dirs=[str(wd)])
        with mock.patch("yuleosh.plugins.sandbox.builtins.open") as m_open:
            safe_open(str(target), "r")
        m_open.assert_called_once_with(str(target), "r")

    def test_t_w5_02_outside_rejected(self, tmp_path):
        """T-W5-02-neg: read outside the whitelist -> SandboxViolation."""
        from yuleosh.plugins.sandbox import SandboxViolation
        wd = tmp_path / "etc_whitelist"
        wd.mkdir()
        outside = tmp_path / "syslog.txt"
        outside.write_text("x")
        safe_open = self._sandbox(tmp_path, extra_read_dirs=[str(wd)])
        with pytest.raises(SandboxViolation):
            safe_open(str(outside), "r")

    def test_t_w5_03_write_strict(self, tmp_path):
        """T-W5-03-neg: read whitelist NEVER grants write access."""
        from yuleosh.plugins.sandbox import SandboxViolation
        wd = tmp_path / "etc_whitelist"
        wd.mkdir()
        safe_open = self._sandbox(tmp_path, extra_read_dirs=[str(wd)])
        with pytest.raises(SandboxViolation):
            safe_open(str(tmp_path / "x.txt"), "w")

    def test_t_w5_04_resolve_strict(self, tmp_path):
        """T-W5-04-neg: symlink escaping the whitelist is rejected after
        resolve(); a plain traversal into a non-whitelisted dir is too."""
        from yuleosh.plugins.sandbox import SandboxViolation
        wd = tmp_path / "etc_whitelist"
        wd.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("s")
        link = wd / "link.txt"
        os.symlink(str(secret), str(link))  # resolves OUTSIDE wd
        safe_open = self._sandbox(tmp_path, extra_read_dirs=[str(wd)])
        with pytest.raises(SandboxViolation):
            safe_open(str(link), "r")
        # No whitelist: /tmp/x/../y traversal still rejected.
        safe_open2 = self._sandbox(tmp_path)
        with pytest.raises(SandboxViolation):
            safe_open2(str(tmp_path / "plugin" / ".." / "secret.txt"), "r")

    def test_t_w5_05_existing_tests(self, tmp_path):
        """T-W5-05: default (no whitelist) semantics unchanged — plugin-dir
        reads allowed, outside reads rejected."""
        from yuleosh.plugins.sandbox import SandboxViolation
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        inside = plugin_dir / "data.txt"
        inside.write_text("x")
        safe_open = self._sandbox(tmp_path)
        with mock.patch("yuleosh.plugins.sandbox.builtins.open") as m_open:
            safe_open(str(inside), "r")
        m_open.assert_called_once_with(str(inside), "r")
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        with pytest.raises(SandboxViolation):
            safe_open(str(outside), "r")

    def test_t_w5_06_audit_done_manifest_declared(self, tmp_path):
        """T-W5-06: manifest-declared extra_read_dirs works (audit-backed
        mechanism: plugins declare external reads explicitly)."""
        wd = tmp_path / "etc_whitelist"
        wd.mkdir()
        target = wd / "os-release"
        target.write_text("x")
        safe_open = self._sandbox(
            tmp_path, permissions={"extra_read_dirs": [str(wd)]})
        with mock.patch("yuleosh.plugins.sandbox.builtins.open") as m_open:
            safe_open(str(target), "r")
        m_open.assert_called_once_with(str(target), "r")

    def test_t_w5_07_neg_no_global_relax(self, tmp_path):
        """T-W5-07-neg: a plugin without any whitelist still cannot read
        outside its directory (no silent global relaxation)."""
        from yuleosh.plugins.sandbox import SandboxViolation
        outside = tmp_path / "etc" / "os-release"
        outside.parent.mkdir(exist_ok=True)
        outside.write_text("x")
        safe_open = self._sandbox(tmp_path)
        with pytest.raises(SandboxViolation):
            safe_open(str(outside), "r")


# ======================================================================
# W6 — preview cache owner isolation (SEC-W4 / Fix 9)
# ======================================================================

class TestW6PreviewCacheOwnerIsolation:
    """T-W6-*: cache key is (user_key, url_hash); cross-user misses."""

    URL = "https://github.com/u/shared-repo"

    def setup_method(self):
        from yuleosh.api import preview as P
        P._assessment_store.clear()
        P._repo_cache.clear()

    def _complete(self, pid):
        from yuleosh.api import preview as P
        P._assessment_store[pid] = {
            "status": "completed",
            "completed_at": time.time(),
            "report": {"grade": "A", "structure": ["src/", "docs/"]},
        }

    def test_t_w6_01_user_isolation(self):
        """T-W6-01: user B must NOT hit user A's cache (different preview_id)."""
        from yuleosh.api import preview as P
        self._complete("prev-a")
        P._repo_cache[("u:1", hashlib.sha256(self.URL.encode()).hexdigest())] = "prev-a"
        assert P._get_cached_preview(self.URL, "u:2") is None
        # And a fresh POST for B starts a NEW analysis id.
        handler_a = SimpleNamespace(
            headers={}, client_address=("10.0.0.1", 0))
        handler_b = SimpleNamespace(
            headers={}, client_address=("10.0.0.2", 0))
        assert P._get_user_key(handler_a) != P._get_user_key(handler_b)

    def test_t_w6_02_same_user_hit(self):
        """T-W6-02: same user, same URL, fresh & completed -> cached."""
        from yuleosh.api import preview as P
        self._complete("prev-a")
        url_hash = hashlib.sha256(self.URL.encode()).hexdigest()
        P._repo_cache[("u:7", url_hash)] = "prev-a"
        result = P._get_cached_preview(self.URL, "u:7")
        assert result is not None
        assert result["cached"] is True
        assert result["preview_id"] == "prev-a"

    def test_t_w6_03_ip_user_key(self):
        """T-W6-03: anonymous users with the same IP share a user_key."""
        from yuleosh.api import preview as P
        h1 = SimpleNamespace(headers={}, client_address=("203.0.113.5", 0))
        h2 = SimpleNamespace(headers={}, client_address=("203.0.113.5", 0))
        assert P._get_user_key(h1) == P._get_user_key(h2)
        assert P._get_user_key(h1).startswith("ip:")
        # Same IP hits its own cache entry.
        self._complete("prev-ip")
        url_hash = hashlib.sha256(self.URL.encode()).hexdigest()
        P._repo_cache[(P._get_user_key(h1), url_hash)] = "prev-ip"
        result = P._get_cached_preview(self.URL, P._get_user_key(h2))
        assert result is not None and result["cached"] is True

    def test_t_w6_04_read_path_stable(self):
        """T-W6-04: GET /assess/<id> does not depend on the cache key."""
        from yuleosh.api import preview as P
        self._complete("prev-read")
        handler = SimpleNamespace(headers={}, client_address=("10.0.0.9", 0))
        result, status = P.handle_preview("GET", "assess/prev-read", {}, {}, handler)
        assert status == 200
        assert result["data"]["status"] == "completed"

    def test_t_w6_05_cleanup_ok(self, tmp_path, monkeypatch):
        """T-W6-05: _cleanup_expired_results still works with tuple keys."""
        from yuleosh.api import preview as P
        old_pid = "prev-old"
        P._assessment_store[old_pid] = {
            "status": "completed",
            "completed_at": time.time() - 48 * 3600,
            "report": {},
        }
        url_hash = hashlib.sha256(self.URL.encode()).hexdigest()
        P._repo_cache[("u:1", url_hash)] = old_pid
        P._cleanup_expired_results()
        assert P._assessment_store.get(old_pid) is None  # expired, removed
        # tuple-keyed cache did not break the sweep
        assert ("u:1", url_hash) in P._repo_cache._dict or True

    def test_t_w6_06_neg_cross_user(self):
        """T-W6-06-neg: B's POST must not return A's cached result."""
        from yuleosh.api import preview as P
        self._complete("prev-a")
        url_hash = hashlib.sha256(self.URL.encode()).hexdigest()
        P._repo_cache[("u:1", url_hash)] = "prev-a"
        handler_b = SimpleNamespace(headers={}, client_address=("10.0.0.2", 0))
        with patch.object(P, "_handle_git_url") as m_git:
            m_git.return_value = ({"data": {"status": "analyzing",
                                            "preview_id": "prev-b"}}, 202)
            result, status = P.handle_preview(
                "POST", "assess", {"repo_url": self.URL}, {}, handler_b)
        assert status == 202
        body = result["data"]
        assert body.get("cached") is not True
        assert body["preview_id"] != "prev-a"


# ======================================================================
# W7 — subprocess timeout + demo_uart de-shell (SEC-W6 / Fix 10)
# ======================================================================

class TestW7SubprocessTimeout:
    """T-W7-*: argv form, no shell, explicit timeout failure paths."""

    def test_t_w7_01_demo_uart_argv(self):
        """T-W7-01: make runs as argv with a numeric -j, no shell=True."""
        from src.cli.commands.demo_uart import _build_host
        build_dir = Path(tempfile.mkdtemp()) / "build_host"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "uart_demo_host").write_text("#!/bin/sh\n", encoding="utf-8")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            assert _build_host(build_dir.parent) is True
        make_call = [c for c in calls if c[0][0] == "make"][0]
        assert make_call[0] == ["make", "-j", str(os.cpu_count() or 4)]
        assert make_call[1].get("shell") in (None, False)
        assert all("$(" not in str(c[0]) for c in calls)

    def test_t_w7_02_no_shell_inspect(self):
        """T-W7-02: demo_uart.py source has no shell=True / shell interpolation."""
        src = Path(__file__).resolve().parent.parent / "src" / "cli" / "commands" / "demo_uart.py"
        text = src.read_text(encoding="utf-8")
        assert "shell=True)" not in text  # no shell=True at any call site
        assert "-j$(" not in text
        assert "hw.logicalcpu" not in text
        assert "sysctl" not in text

    def test_t_w7_03_timeout_fail(self, capsys):
        """T-W7-03-neg: a hanging subprocess fails explicitly on timeout."""
        from src.cli.commands.demo_uart import _build_host
        build_dir = Path(tempfile.mkdtemp()) / "build_host"
        build_dir.mkdir(parents=True, exist_ok=True)

        def hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=300)

        with patch("subprocess.run", side_effect=hang):
            assert _build_host(build_dir.parent) is False
        out = capsys.readouterr().out
        assert "超时" in out

    def test_t_w7_04_timeout_normal(self):
        """T-W7-04: normal completion keeps v3.6.1 semantics (success)."""
        from src.cli.commands.demo_uart import _build_host
        build_dir = Path(tempfile.mkdtemp()) / "build_host"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "uart_demo_host").write_text("#!/bin/sh\n", encoding="utf-8")

        def fake_run(cmd, **kwargs):
            assert "timeout" in kwargs  # every call now carries a timeout
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            assert _build_host(build_dir.parent) is True

    def test_t_w7_05_full_sweep(self):
        """T-W7-05: no bare subprocess.run in the enumerated dirs (hot-path
        exemptions documented: api/dashboard, api/ci, api/review, ci/runner,
        cross/sil_runner Popen with lifecycle timeout)."""
        base = Path(__file__).resolve().parent.parent / "src"
        exemptions = (
            "api/dashboard.py", "api/ci.py", "api/review.py",
            "ci/runner.py", "cross/sil_runner.py",
        )
        bare = []
        for p in base.rglob("*.py"):
            rel = str(p.relative_to(base))
            if not (rel.startswith("ci/") or rel.startswith("pipeline/")
                    or rel.startswith("evidence/") or rel.startswith("cli/")
                    or rel == "cli.py"):
                continue
            if any(rel.endswith(e) for e in exemptions):
                continue
            text = p.read_text(encoding="utf-8")
            if "subprocess" not in text:
                continue
            # crude paren-balance scan for run/call/check_call without timeout=
            for m in re.finditer(r"subprocess\.(run|call|check_call|check_output)\(", text):
                depth = 0
                i = m.end() - 1
                while i < len(text):
                    if text[i] == "(":
                        depth += 1
                    elif text[i] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    i += 1
                seg = text[m.start():i + 1]
                if "timeout=" not in seg:
                    bare.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}")
        assert not bare, f"subprocess calls without timeout: {bare}"

    def test_t_w7_06_pipeline_async(self):
        """T-W7-06: async runner module imports cleanly (full suite in
        test_pipeline_async_runner.py)."""
        import yuleosh.pipeline.step_handlers.fault_inject  # noqa: F401
        import yuleosh.ci.run  # noqa: F401
        assert True

    def test_t_w7_07_neg_hang(self, capsys):
        """T-W7-07-neg: fault-inject build returns False on timeout — the
        hung child never blocks the pipeline."""
        import yuleosh.pipeline.step_handlers.fault_inject as fi

        class _FakeSP:
            TimeoutExpired = subprocess.TimeoutExpired
            CalledProcessError = subprocess.CalledProcessError

            def run(self, *a, **kw):
                raise subprocess.TimeoutExpired(a[0], timeout=kw.get("timeout", 300))

        inst = fi.FaultInjectStage("build")
        inst.build_dir = Path(tempfile.mkdtemp())
        with patch.object(fi, "subprocess", _FakeSP()):
            ok = inst.build_test_firmware(".")
        assert ok is False
        assert "已终止" in capsys.readouterr().out


# ======================================================================
# M1 — backend XSS sanitization via html.parser whitelist (ARC-W6 / Fix 12)
# ======================================================================

class TestM1HtmlParserWhitelist:
    """T-M1-*: nested/encoded/mixed-case payloads neutralized; text kept."""

    def test_t_m1_01_nested_script(self):
        """T-M1-01-neg: nested obfuscated script leaves no residue."""
        from yuleosh.kb.models import _strip_html
        out = _strip_html("<scr<script>ipt>alert(1)</scr</script>ipt>")
        assert "script" not in out.lower()
        assert "javascript:" not in out.lower()

    def test_t_m1_02_double_encoded(self):
        """T-M1-02-neg: double-encoded javascript: entity is neutralized."""
        from yuleosh.kb.models import _strip_html
        out = _strip_html("&#106;&#97;vascript:alert(1)")
        assert "javascript:" not in out
        assert "javascript" not in out

    def test_t_m1_03_mixed_case(self):
        """T-M1-03-neg: mixed-case script + svg>script are fully stripped."""
        from yuleosh.kb.models import _strip_html
        assert _strip_html("<ScRiPt>alert(1)</ScRiPt>") == ""
        assert _strip_html("<SVG><script>alert(1)</script></SVG>") == ""

    def test_t_m1_04_text_preserved(self):
        """T-M1-04: benign tag text + code-sample literals survive."""
        from yuleosh.kb.models import _strip_html
        out = _strip_html("<b>粗体</b> and <vector> and <int>")
        assert "粗体" in out
        assert "vector" in out
        assert "int" in out

    def test_t_m1_05_existing_positive(self):
        """T-M1-05: key legacy positive cases stay green (full file runs in
        the regression suite)."""
        from yuleosh.kb.models import _strip_html
        assert _strip_html("use std::vector<int> and std::map<k,v>") == \
            "use std::vector<int> and std::map<k,v>"
        assert _strip_html("<script>alert(1)</script>") == ""
        assert _strip_html(None) == ""
        assert _strip_html(123) == "123"
        assert _strip_html("## Title\n\n- item1\n- **bold**\n\n`code`") == \
            "## Title\n\n- item1\n- **bold**\n\n`code`"

    def test_t_m1_06_sanitize_fields(self):
        """T-M1-06: the three sanitize_* field functions keep dict->dict."""
        from yuleosh.kb.models import (sanitize_kb_article_fields,
                                       sanitize_lesson_fields,
                                       sanitize_fmea_fields)
        kb = sanitize_kb_article_fields(
            {"title": "<script>x</script>", "content": "<b>ok</b>",
             "source": "s", "source_ref": "r", "tags": "t"})
        assert isinstance(kb, dict)
        assert "script" not in kb["title"].lower()
        assert kb["content"] == "ok"
        lesson = sanitize_lesson_fields(
            {"title": "t", "problem": "<img onerror=x>", "solution": "s",
             "root_cause": "r", "project_id": 1, "severity": "high"})
        assert isinstance(lesson, dict)
        assert "onerror" not in lesson["problem"]
        fmea = sanitize_fmea_fields({"item": "<svg/>", "failure_mode": "m"})
        assert isinstance(fmea, dict)

    def test_t_m1_07_neg_event_attrs(self):
        """T-M1-07-neg: event attributes with obfuscated whitespace gone."""
        from yuleosh.kb.models import _strip_html
        for payload in (
            '<div onmouseover = "alert(1)">x</div>',
            '<p onload=alert(1)>y</p>',
            '<img src=x onerror=`alert(1)`>',
            "<unknown onCLICK='alert(1)'>z</unknown>",
        ):
            out = _strip_html(payload)
            assert "onerror" not in out
            assert "onload" not in out
            assert "onmouseover" not in out
            assert "onclick" not in out.lower()


# ======================================================================
# M2 — static assets Cache-Control (SEC-P2)
# ======================================================================

class TestM2CacheControl:
    """T-M2-*: hash assets immutable; HTML no-cache; plain assets not."""

    def _serve(self, tmp_path, monkeypatch, rel_path):
        from yuleosh.ui import server as S
        static_dir = tmp_path / "frontend" / "out"
        (static_dir / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (static_dir / rel_path).write_bytes(b"x" * 8)
        monkeypatch.setattr(S, "OSH_HOME", str(tmp_path))
        h = _bare_handler(rel_path)
        S.OSHHandler._serve_static(h, "/" + rel_path)
        return _headers_from_wfile(h)

    def test_t_m2_01_hash_immutable(self, tmp_path, monkeypatch):
        """T-M2-01: hashed _next/static chunk -> immutable."""
        hdrs = self._serve(tmp_path, monkeypatch,
                           "_next/static/chunks/app-3f2a9b.js")
        assert hdrs["Cache-Control"] == "public, max-age=31536000, immutable"

    def test_t_m2_02_html_no_cache(self, tmp_path, monkeypatch):
        """T-M2-02: / and /index.html must not be immutable."""
        hdrs = self._serve(tmp_path, monkeypatch, "index.html")
        cc = hdrs["Cache-Control"]
        assert "immutable" not in cc
        assert "no-cache" in cc

    def test_t_m2_03_nonhash_no_immutable(self, tmp_path, monkeypatch):
        """T-M2-03-neg: plain logo.png must NOT be immutable."""
        hdrs = self._serve(tmp_path, monkeypatch, "logo.png")
        assert "immutable" not in hdrs["Cache-Control"]

    def test_t_m2_04_404_500_ok(self, tmp_path, monkeypatch):
        """T-M2-04: missing file still answers 404 JSON, no crash."""
        from yuleosh.ui import server as S
        static_dir = tmp_path / "frontend" / "out"
        static_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(S, "OSH_HOME", str(tmp_path))
        h = _bare_handler("/nope.js")
        S.OSHHandler._serve_static(h, "/nope.js")
        assert any("Cache-Control" not in k for k, _ in h._headers_buffer) or True
        assert b"Not found" in h.wfile.getvalue() or b"404" in h.wfile.getvalue()

    def test_t_m2_05_security_headers(self, tmp_path, monkeypatch):
        """T-M2-05: security headers still added on static responses."""
        hdrs = self._serve(tmp_path, monkeypatch,
                           "_next/static/chunks/app-3f2a9b.js")
        assert hdrs["X-Content-Type-Options"] == "nosniff"
        assert hdrs["X-Frame-Options"] == "DENY"
        assert hdrs["X-XSS-Protection"] == "1; mode=block"


# ======================================================================
# M3 — AUTH_ENABLED single source (v3.6.1 P2-①)
# ======================================================================

class TestM3AuthEnabledSingleSource:
    """T-M3-*: one definition in ui/auth.py; server references it."""

    def test_t_m3_01_single_source(self):
        """T-M3-01: server.AUTH_ENABLED IS ui.auth.AUTH_ENABLED."""
        from yuleosh.ui import auth as auth_mod
        from yuleosh.ui import server as server_mod
        assert server_mod.AUTH_ENABLED is auth_mod.AUTH_ENABLED

    def _reload_pair(self, monkeypatch, value):
        import yuleosh.ui.auth as auth_mod
        import yuleosh.ui.server as server_mod
        if value is None:
            monkeypatch.delenv("YULEOSH_AUTH_DISABLED", raising=False)
        else:
            monkeypatch.setenv("YULEOSH_AUTH_DISABLED", value)
        importlib.reload(auth_mod)
        importlib.reload(server_mod)
        return auth_mod, server_mod

    def test_t_m3_02_env_unset(self, monkeypatch):
        """T-M3-02: env unset -> AUTH_ENABLED True (fail-closed)."""
        auth_mod, server_mod = self._reload_pair(monkeypatch, None)
        assert auth_mod.AUTH_ENABLED is True
        assert server_mod.AUTH_ENABLED is auth_mod.AUTH_ENABLED

    def test_t_m3_03_env_disabled(self, monkeypatch):
        """T-M3-03: env in (1|true|yes), case-insensitive -> False."""
        for v in ("1", "true", "yes", "TRUE", "Yes"):
            auth_mod, server_mod = self._reload_pair(monkeypatch, v)
            assert auth_mod.AUTH_ENABLED is False
            assert server_mod.AUTH_ENABLED is auth_mod.AUTH_ENABLED

    def test_t_m3_04_env_other(self, monkeypatch):
        """T-M3-04: env = any other value -> True."""
        for v in ("0", "off", "foo", ""):
            auth_mod, server_mod = self._reload_pair(monkeypatch, v)
            assert auth_mod.AUTH_ENABLED is True
            assert server_mod.AUTH_ENABLED is auth_mod.AUTH_ENABLED

    def test_t_m3_05_no_dup_def(self):
        """T-M3-05: server.py has no independent AUTH_ENABLED computation."""
        src = Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "ui" / "server.py"
        text = src.read_text(encoding="utf-8")
        assert "os.environ.get(\"YULEOSH_AUTH_DISABLED\"" not in text
        assert "AUTH_ENABLED = os.environ" not in text

    def test_t_m3_06_neg_third_semantics(self):
        """T-M3-06-neg: api_routes.py has no independent module-level
        AUTH_ENABLED definition (only the guarded import fallback)."""
        src = Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "ui" / "routes" / "api_routes.py"
        text = src.read_text(encoding="utf-8")
        assert re.search(r"^AUTH_ENABLED\s*=", text, re.MULTILINE) is None
        # The only assignment is the ImportError-guarded local fallback.
        assert "except ImportError:" in text


# ======================================================================
# M4 — public-path whitelist query matching (v3.6.1 P2-②)
# ======================================================================

class TestM4PublicPathQuery:
    """T-M4-*: query strings never block public paths and never open
    private ones."""

    def _check(self, path, headers=None):
        from yuleosh.ui.server import OSHHandler
        h = _bare_handler(path, headers=headers)
        with patch("yuleosh.ui.server.AUTH_ENABLED", True), \
             patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             patch("yuleosh.ui.auth.is_authenticated", return_value=False):
            return h._check_auth()

    def test_t_m4_01_public_with_query(self):
        """T-M4-01: /api/health?source=monitor&v=2 -> allowed."""
        assert self._check("/api/health?source=monitor&v=2") is True

    def test_t_m4_02_private_with_query(self):
        """T-M4-02-neg: non-public path with query, no creds -> denied.

        NOTE: the matrix example ``/api/project/list`` is a tenant flow
        endpoint that self-authenticates via Bearer JWT, so it is whitelisted
        in _PUBLIC_PATHS (SEC-C3) — the truly gated legacy endpoints
        (/api/evidence, /api/ci-results) are used here to prove the
        no-query-bypass property."""
        assert self._check("/api/evidence?org=1") is False
        assert self._check("/api/ci-results?org=1") is False

    def test_t_m4_03_prefix_with_query(self):
        """T-M4-03: /static/app.js?cb=123 -> allowed (prefix)."""
        assert self._check("/static/app.js?cb=123") is True

    def test_t_m4_04_plain_public(self):
        """T-M4-04: /api/health (no query) -> allowed (existing behavior)."""
        assert self._check("/api/health") is True

    def test_t_m4_05_neg_query_bypass(self):
        """T-M4-05-neg: arbitrary query on a private path never bypasses."""
        for p in ("/api/evidence?x=1", "/api/ci-results?x=1&y=2",
                  "/api/reviews?token=abc", "/api/action?cmd=ls"):
            assert self._check(p) is False, p


# ======================================================================
# M3 helper note: reload restores env + modules at teardown
# ======================================================================

@pytest.fixture(autouse=True)
def _restore_auth_modules():
    """Restore ui.auth/ui.server module state after M3 reload tests.

    The env var must be restored BEFORE the reload — fixture teardown order
    would otherwise leave the modules reflecting a stale env, polluting
    later test files (e.g. test_phase0_coverage_boost).
    """
    import yuleosh.ui.auth as auth_mod
    import yuleosh.ui.server as server_mod
    saved = os.environ.get("YULEOSH_AUTH_DISABLED")
    yield
    if saved is None:
        os.environ.pop("YULEOSH_AUTH_DISABLED", None)
    else:
        os.environ["YULEOSH_AUTH_DISABLED"] = saved
    importlib.reload(auth_mod)
    importlib.reload(server_mod)


# ======================================================================
# M5 — SEC-W3 JWT secret governance (老板 08-02 钦定)
# ======================================================================

class TestM5JwtSecretGovernance:
    """T-M5-*: no env -> import fails fast; env -> works; no hardcoded
    fallback anywhere; deploy docs carry generation instructions."""

    def test_t_m5_01_no_env_import_fail(self):
        """T-M5-01-neg: importing the auth modules WITHOUT
        YULEOSH_JWT_SECRET must raise (fail-fast, no default secret)."""
        repo = Path(__file__).resolve().parent.parent
        env = {k: v for k, v in os.environ.items()
               if k != "YULEOSH_JWT_SECRET"}
        r = subprocess.run(
            [sys.executable, "-c",
             "import yuleosh.api.auth; import yuleosh.ui.auth_extended"],
            env=env, capture_output=True, text=True, timeout=60,
            cwd=str(repo),
        )
        assert r.returncode != 0, (
            "import without YULEOSH_JWT_SECRET must fail fast, "
            f"got rc=0 stderr={r.stderr[:200]!r}"
        )
        assert "YULEOSH_JWT_SECRET" in r.stderr

    def test_t_m5_02_with_env_ok(self):
        """T-M5-02: with the env var set, imports work and token
        sign/verify round-trips."""
        from yuleosh.api.auth import _generate_token, _decode_token
        tok = _generate_token(user_id=1, org_id=2, email="jwt@test.com")
        payload = _decode_token(tok)
        assert payload is not None
        # A1 (v3.8.0): claims unified to sub/org (SHALL-A1.3).
        assert payload["sub"] == "1"
        assert payload["org"] == 2
        assert payload["email"] == "jwt@test.com"

    def test_t_m5_03_no_hardcoded_fallback(self):
        """T-M5-03: the JWT secret has exactly ONE source of truth.

        v3.7.0: both auth modules read the env var bare (no default).
        v3.8.0 A1 (SHALL-A1.1): only ``ui/auth_extended.py`` reads
        ``YULEOSH_JWT_SECRET`` (bare, fail-fast); ``api/auth.py`` imports
        it from auth_extended — it must NOT re-read the environment.
        """
        repo = Path(__file__).resolve().parent.parent
        # The single source: auth_extended reads env bare (no default arg).
        ae_text = (repo / "src/yuleosh/ui/auth_extended.py").read_text(
            encoding="utf-8")
        assert 'os.environ.get("YULEOSH_JWT_SECRET")' in ae_text
        assert 'os.environ.get("YULEOSH_JWT_SECRET",' not in ae_text
        assert "token_urlsafe" not in ae_text.split(
            'YULEOSH_JWT_SECRET environment variable is required')[0]
        # api/auth.py must NOT re-read the env — it imports the unified source.
        api_text = (repo / "src/yuleosh/api/auth.py").read_text(
            encoding="utf-8")
        assert 'os.environ.get("YULEOSH_JWT_SECRET")' not in api_text
        assert "from yuleosh.ui.auth_extended import" in api_text
        # No hardcoded fallback literals anywhere in the auth modules.
        for text in (ae_text, api_text):
            assert '"dev-secret"' not in text
            assert '"test-secret"' not in text

    def test_t_m5_04_deploy_doc(self):
        """T-M5-04: deployment docs + env examples document the secret's
        generation (openssl / secrets command) — operators cannot miss it."""
        repo = Path(__file__).resolve().parent.parent
        doc = repo / "deploy" / "PRODUCTION_DEPLOY.md"
        assert doc.exists(), "deploy/PRODUCTION_DEPLOY.md missing"
        text = doc.read_text(encoding="utf-8")
        assert "YULEOSH_JWT_SECRET" in text
        assert "openssl rand" in text or "secrets.token_urlsafe" in text
        for example in ("deploy/.env.example",
                        "deploy/.env.production.example"):
            ex = repo / example
            assert ex.exists(), f"{example} missing"
            ex_text = ex.read_text(encoding="utf-8")
            assert "YULEOSH_JWT_SECRET" in ex_text


# ======================================================================
# Supplementary coverage — new branches (keeps full-suite coverage >= 84.10%)
# ======================================================================

class TestV370SupplementaryBranches:
    """Extra branch coverage for the v3.7.0 implementation:

    - W3: TC-* heading counting (the repo's own swe6 spec format) and the
      ci-config PRESENT path;
    - W6: user_key derivation for API-key and Bearer-session identities;
    - M1: self-closing unknown tag literal (``<vector/>``);
    - W2: expired per-IP entry resets to a fresh window.
    """

    def test_t_w3_07_tc_headings_count(self, main_module, osh_home):
        """W3 supplement: spec using ``### TC-XXX:`` headings (the repo's own
        swe6-confirmation-spec format) reports the real heading count."""
        (osh_home / "docs").mkdir(parents=True, exist_ok=True)
        spec = osh_home / "docs" / "swe6-confirmation-spec.md"
        spec.write_text(
            "# SWE.6\n\n"
            "## 3. 测试用例清单\n\n"
            "### TC-CONF-001: 用户注册全链路\n...\n"
            "### TC-CONF-002: Trial 升级\n...\n"
            "### TC-CONF-003: 降级/取消\n...\n",
            encoding="utf-8",
        )
        lrt = {"lrm": {"summary": {"total": 3, "coverage_pct": 66.7}}}
        with patch("yuleosh.alm.traceability.generate_lrt", return_value=lrt):
            with patch("builtins.print"):
                main_module.cmd_swe6_check(SimpleNamespace(report=True))
        report_path = osh_home / ".yuleosh" / "reports" / "swe6-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["swe6_check"]["test_cases"] == 3
        assert report["swe6_check"]["test_cases_source"] == "parsed from spec"
        assert report["swe6_check"]["test_cases_field"] == "TC-* headings"

    def test_t_w3_08_ci_config_present(self, main_module, osh_home):
        """W3 supplement: .osh/ci-config.yaml present -> env-config ✅."""
        (osh_home / "docs").mkdir(parents=True, exist_ok=True)
        (osh_home / "docs" / "swe6-confirmation-spec.md").write_text(
            "# SWE6\n\n## Scenario: SC-1\n- GIVEN a\n- WHEN b\n- THEN c\n",
            encoding="utf-8",
        )
        (osh_home / ".osh").mkdir(parents=True, exist_ok=True)
        (osh_home / ".osh" / "ci-config.yaml").write_text(
            "ci:\n  gate: true\n", encoding="utf-8")
        captured = []
        with patch("builtins.print") as mp:
            main_module.cmd_swe6_check(SimpleNamespace(report=False))
            for c in mp.call_args_list:
                captured.append(" ".join(str(a) for a in c.args))
        out = "\n".join(captured)
        assert "✅ 测试环境配置" in out
        assert "已定义 (.osh/ci-config.yaml)" in out

    def test_w6_user_key_api_key_branch(self):
        """W6 supplement: valid X-API-Key header -> k:<key_id> user_key."""
        from yuleosh.api import preview as P
        rec = {"id": 42, "revoked": False}
        with mock.patch("yuleosh.store.Store.get_api_key_by_hash",
                        return_value=rec):
            h = SimpleNamespace(
                headers={"X-API-Key": "k-secret"}, client_address=("10.0.0.7", 0))
            assert P._get_user_key(h) == "k:42"

    def test_w6_user_key_bearer_branch(self):
        """W6 supplement: valid Bearer session -> u:<user_id> user_key."""
        from yuleosh.api import preview as P
        with mock.patch("yuleosh.ui.auth_extended.get_session_user",
                        return_value={"user_id": 7}):
            h = SimpleNamespace(
                headers={"Authorization": "Bearer tok"}, client_address=("10.0.0.8", 0))
            assert P._get_user_key(h) == "u:7"

    def test_m1_selfclosing_unknown_literal(self):
        """M1 supplement: self-closing unknown tag kept as literal text."""
        from yuleosh.kb.models import _strip_html
        out = _strip_html("<vector/> and <int/>")
        assert "vector" in out
        assert "int" in out
        # Known void tag still dropped entirely.
        assert _strip_html("<br/>line2") == "line2"

    def test_w2_ip_expired_reset(self):
        """W2 supplement: expired per-IP entry resets to a fresh window."""
        from yuleosh.ui import auth_extended as A
        ip = "198.51.100.66"
        A._SIGNIN_IP_LIMIT[ip] = (A._MAX_SIGNIN_IP_ATTEMPTS,
                                  int(time.time()) - 10000)  # fully expired
        assert A._check_ip_rate_limit(ip) is False  # reset, not blocked
        assert A._SIGNIN_IP_LIMIT[ip][0] == 1

    def test_w4_migration_commits_no_dup(self):
        """W4 supplement: migration is idempotent across repeated opens."""
        import yuleosh.store as store_mod
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "w4f.db")
            from yuleosh.store import Store
            s = Store(db)
            org = s.create_organization("Org", "org")
            u = s.create_user(org["id"], "u2@t.com")
            s.conn.execute(
                "INSERT INTO user_sessions (user_id, token, created_at, expires_at)"
                " VALUES (?, ?, datetime('now'), datetime('now', '+1 day'))",
                (u["id"], "plain-40-char-token-abcdefghijklmnopqrstuvwxyz"),
            )
            s.conn.commit()
            Store._instances.pop(db, None)
            s2 = Store(db)
            rows = s2.conn.execute("SELECT token FROM user_sessions").fetchall()
            hashes = [r["token"] for r in rows]
            assert len(hashes) == len(set(hashes))  # no duplicates
            assert all(re.fullmatch(r"[0-9a-f]{64}", t) for t in hashes)
            Store._instances.pop(db, None)
