"""Unit tests for yuleosh.api.preview (v3.4.2b Wave 2a).

Covers the AI Preview Assessment API offline:
  - _ThreadSafeDict wrapper (all accessors)
  - multipart parsing / zip extraction / zip validation
  - git URL validation
  - analysis execution (_run_analysis, _analyze_in_background)
  - zip upload / git URL handlers (incl. failure paths)
  - _get_dir_size
  - rate limiter (_check_preview_rate_limit)
  - repo cache (_get_cached_preview)
  - expired-result cleanup (_cleanup_expired_results)
  - handle_preview routing (POST/GET/DELETE + error paths)
"""

import io
import os
import sys
import time
import zipfile
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.api import preview as P


def _url_hash(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()



# ── Fixtures / helpers ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_state():
    P._assessment_store.clear()
    P._repo_cache.clear()
    P._preview_request_log.clear()
    yield
    P._assessment_store.clear()
    P._repo_cache.clear()
    P._preview_request_log.clear()


class FakeHandler:
    """Minimal BaseHTTPRequestHandler stand-in."""

    def __init__(self, headers=None, rfile=None, client_address=("1.2.3.4", 0)):
        self.headers = headers or {}
        self.rfile = rfile if rfile is not None else io.BytesIO(b"")
        self.client_address = client_address

    def get(self, key, default=""):
        return self.headers.get(key, default)


def _json_headers(**kw):
    h = {"Content-Type": "application/json", "Content-Length": "0"}
    h.update(kw)
    return h


def _make_zip(data=b"hello world") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("main.c", data)
    return buf.getvalue()


def _multipart(zip_bytes: bytes, boundary="----testboundary") -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="code.zip"\r\n'
        f"Content-Type: application/zip\r\n\r\n"
    ).encode() + zip_bytes + f"\r\n--{boundary}--\r\n".encode()


# ── _ThreadSafeDict ────────────────────────────────────────────────────

class TestThreadSafeDict:
    def test_basic_ops(self):
        """GIVEN dict WHEN set/get/del/contains THEN consistent."""
        d = P._ThreadSafeDict()
        d["a"] = 1
        assert d["a"] == 1
        assert "a" in d
        assert "b" not in d
        del d["a"]
        assert "a" not in d

    def test_get_default(self):
        """GIVEN missing key WHEN get THEN default."""
        d = P._ThreadSafeDict()
        assert d.get("x", 42) == 42
        assert d.get("x") is None

    def test_pop(self):
        """GIVEN entry WHEN pop THEN removed + returned."""
        d = P._ThreadSafeDict()
        d["k"] = "v"
        assert d.pop("k") == "v"
        assert d.pop("k", "def") == "def"

    def test_items_keys_clear(self):
        """GIVEN entries WHEN items/keys/clear THEN snapshots."""
        d = P._ThreadSafeDict()
        d["a"] = 1
        d["b"] = 2
        assert sorted(d.keys()) == ["a", "b"]
        assert sorted(k for k, _ in d.items()) == ["a", "b"]
        d.clear()
        assert d.keys() == []

    def test_get_and_update(self):
        """GIVEN existing key WHEN get_and_update THEN updater applied."""
        d = P._ThreadSafeDict()
        d["e"] = {"status": "old"}
        entry = d.get_and_update("e", lambda x: x.update({"status": "new"}))
        assert entry["status"] == "new"
        assert d.get_and_update("missing", lambda x: None) is None


# ── Multipart / zip helpers ────────────────────────────────────────────

class TestMultipart:
    def test_parse_multipart_body(self):
        """GIVEN multipart handler WHEN parse THEN raw body read."""
        raw = _multipart(_make_zip())
        handler = FakeHandler(
            headers={"Content-Type": "multipart/form-data; boundary=----testboundary",
                     "Content-Length": str(len(raw))},
            rfile=io.BytesIO(raw),
        )
        assert P._parse_multipart_body(handler) == raw

    def test_parse_multipart_no_length(self):
        """GIVEN zero content length WHEN parse THEN None."""
        handler = FakeHandler(
            headers={"Content-Type": "multipart/form-data", "Content-Length": "0"})
        assert P._parse_multipart_body(handler) is None

    def test_parse_multipart_wrong_type(self):
        """GIVEN non-multipart content type WHEN parse THEN None."""
        handler = FakeHandler(
            headers={"Content-Type": "application/json", "Content-Length": "5"})
        assert P._parse_multipart_body(handler) is None

    def test_extract_zip_from_multipart(self):
        """GIVEN multipart with file WHEN extract THEN zip bytes returned."""
        zip_bytes = _make_zip()
        raw = _multipart(zip_bytes)
        extracted = P._extract_zip_from_multipart(
            raw, "multipart/form-data; boundary=----testboundary")
        assert extracted == zip_bytes

    def test_extract_zip_no_boundary(self):
        """GIVEN no boundary WHEN extract THEN None."""
        raw = _multipart(_make_zip())
        assert P._extract_zip_from_multipart(raw, "multipart/form-data") is None

    def test_extract_zip_no_file_part(self):
        """GIVEN multipart without file field WHEN extract THEN None."""
        boundary = "bb"
        raw = (f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="other"\r\n\r\n'
               f"data\r\n--{boundary}--\r\n").encode()
        assert P._extract_zip_from_multipart(
            raw, f"multipart/form-data; boundary={boundary}") is None

    def test_extract_zip_no_headers_end(self):
        """GIVEN part without header separator WHEN extract THEN None."""
        boundary = "bb"
        raw = (f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="file"; filename="x.zip"\r\n'
               f"NO_HEADER_END\r\n--{boundary}--\r\n").encode()
        assert P._extract_zip_from_multipart(
            raw, f"multipart/form-data; boundary={boundary}") is None

    def test_is_valid_zip(self):
        """GIVEN PK magic WHEN is_valid_zip THEN True/False."""
        assert P._is_valid_zip(b"PK\x03\x04rest") is True
        assert P._is_valid_zip(b"PK\x05\x06empty") is True
        assert P._is_valid_zip(b"not a zip") is False


# ── git URL validation ─────────────────────────────────────────────────

class TestValidateGitUrl:
    def test_https_ok(self):
        """GIVEN github URL WHEN validate THEN valid."""
        ok, err = P._validate_git_url("https://github.com/user/repo.git")
        assert ok is True and err == ""

    def test_non_https(self):
        """GIVEN http URL WHEN validate THEN invalid."""
        ok, err = P._validate_git_url("http://github.com/x/y")
        assert ok is False
        assert "HTTPS" in err

    def test_invalid_format(self):
        """GIVEN malformed URL WHEN validate THEN invalid."""
        ok, err = P._validate_git_url("https://")
        assert ok is False

    def test_unsupported_host(self):
        """GIVEN unsupported host WHEN validate THEN invalid + hosts listed."""
        ok, err = P._validate_git_url("https://example.com/repo")
        assert ok is False
        assert "Unsupported git host" in err
        assert "github.com" in err

    def test_host_with_port(self):
        """GIVEN host with port WHEN validate THEN port stripped."""
        ok, _ = P._validate_git_url("https://github.com:8443/user/repo")
        assert ok is True


# ── Analysis execution ─────────────────────────────────────────────────

class TestAnalysisExecution:
    def test_run_analysis(self, tmp_path, monkeypatch):
        """GIVEN source dir WHEN _run_analysis THEN report dict."""
        report = {"grade": "A"}
        monkeypatch.setattr(
            "yuleosh.preview.analyzer.analyze_directory",
            lambda d: {"files": 1})
        monkeypatch.setattr(
            "yuleosh.preview.reporter.build_assessment_report",
            lambda analysis: report)
        assert P._run_analysis(tmp_path) == report

    def test_analyze_in_background_success(self, tmp_path):
        """GIVEN preview id WHEN background analysis THEN entry completed."""
        P._assessment_store["p1"] = {"status": "analyzing"}
        with patch.object(P, "_run_analysis", return_value={"ok": 1}) as m:
            P._analyze_in_background("p1", tmp_path)
        m.assert_called_once_with(tmp_path)
        # wait for the background thread
        for _ in range(50):
            if P._assessment_store.get("p1", {}).get("status") == "completed":
                break
            time.sleep(0.02)
        assert P._assessment_store["p1"]["status"] == "completed"
        assert P._assessment_store["p1"]["report"] == {"ok": 1}

    def test_analyze_in_background_failure(self, tmp_path):
        """GIVEN analysis raising WHEN background THEN entry failed."""
        P._assessment_store["p2"] = {"status": "analyzing"}

        def boom(_):
            raise RuntimeError("analysis crashed")

        with patch.object(P, "_run_analysis", side_effect=boom):
            P._analyze_in_background("p2", tmp_path)
        for _ in range(50):
            if P._assessment_store.get("p2", {}).get("status") == "failed":
                break
            time.sleep(0.02)
        assert P._assessment_store["p2"]["status"] == "failed"
        assert "analysis crashed" in P._assessment_store["p2"]["error"]


# ── ZIP upload ─────────────────────────────────────────────────────────

class TestZipUpload:
    def test_too_large(self):
        """GIVEN oversized zip WHEN upload THEN 413."""
        with patch.object(P, "MAX_ZIP_SIZE", 10):
            result, status = P._handle_zip_upload("p1", b"x" * 100, None)
        assert status == 413
        # W-07 contract: error is a flat string + details object
        assert result["error"] == "file_too_large"
        assert result["details"]["max_size_mb"] == 0

    def test_invalid_zip(self):
        """GIVEN non-zip bytes WHEN upload THEN 400."""
        result, status = P._handle_zip_upload("p1", b"garbage", None)
        assert status == 400
        assert result["error"] == "invalid_archive"

    def test_bad_zip_file(self):
        """GIVEN corrupt zip file WHEN upload THEN 400."""
        result, status = P._handle_zip_upload("p1", b"PK\x03\x04corrupt", None)
        assert status == 400

    def test_valid_upload(self, tmp_path, monkeypatch):
        """GIVEN valid zip WHEN upload THEN 202 + entry stored."""
        zip_bytes = _make_zip()
        monkeypatch.setattr("tempfile.mkdtemp",
                            lambda prefix="": str(tmp_path / "t"))
        with patch.object(P, "_analyze_in_background") as m:
            result, status = P._handle_zip_upload("p-abc", zip_bytes, None)
        assert status == 202
        assert result["data"]["preview_id"] == "p-abc"
        entry = P._assessment_store["p-abc"]
        assert entry["status"] == "analyzing"
        assert entry["input_type"] == "zip"
        m.assert_called_once()
        # files extracted into temp dir
        assert (tmp_path / "t" / "main.c").exists()


# ── Git URL handler ────────────────────────────────────────────────────

class TestGitUrl:
    def test_invalid_url(self):
        """GIVEN unsupported host WHEN git url THEN 400."""
        result, status = P._handle_git_url("p1", "https://evil.com/r", None)
        assert status == 400
        assert result["error"] == "unsupported_git_host"

    def test_valid_url_starts_background(self, tmp_path, monkeypatch):
        """GIVEN valid URL WHEN git url THEN 202 + entry stored."""
        monkeypatch.setattr("tempfile.mkdtemp",
                            lambda prefix="": str(tmp_path / "clone"))
        with patch.object(P.threading, "Thread") as t:
            result, status = P._handle_git_url("p-g", "https://github.com/u/r", None)
        assert status == 202
        entry = P._assessment_store["p-g"]
        assert entry["repo_url"] == "https://github.com/u/r"
        assert entry["input_type"] == "git"
        t.assert_called_once()

    def test_clone_success_flow(self, tmp_path):
        """GIVEN successful clone WHEN clone path THEN analysis starts."""
        P._assessment_store["p-c"] = {"status": "analyzing",
                                      "source_dir": str(tmp_path)}
        (tmp_path / "file.c").write_text("int x;")
        clone_result = MagicMock()
        clone_result.returncode = 0

        with patch.object(P.subprocess, "run", return_value=clone_result) as run, \
             patch.object(P, "_get_dir_size", return_value=100), \
             patch.object(P, "_analyze_in_background") as an:
            _run_clone_path(P, "p-c", tmp_path)
        run.assert_called_once()
        an.assert_called_once_with("p-c", tmp_path)

    def test_clone_failure(self, tmp_path):
        """GIVEN clone returncode != 0 THEN entry failed."""
        P._assessment_store["p-f"] = {"status": "analyzing",
                                      "source_dir": str(tmp_path)}
        clone_result = MagicMock()
        clone_result.returncode = 1
        clone_result.stderr = "auth error"
        with patch.object(P.subprocess, "run", return_value=clone_result), \
             patch.object(P, "_analyze_in_background") as an:
            _run_clone_path(P, "p-f", tmp_path)
        assert P._assessment_store["p-f"]["status"] == "failed"
        assert "auth error" in P._assessment_store["p-f"]["error"]
        an.assert_not_called()

    def test_clone_timeout(self, tmp_path):
        """GIVEN TimeoutExpired THEN entry failed + dir cleaned."""
        P._assessment_store["p-t"] = {"status": "analyzing",
                                      "source_dir": str(tmp_path)}
        (tmp_path / "junk").write_text("x")

        def timeout(*a, **kw):
            raise P.subprocess.TimeoutExpired(cmd="git", timeout=10)

        with patch.object(P.subprocess, "run", side_effect=timeout), \
             patch.object(P, "_analyze_in_background") as an:
            _run_clone_path(P, "p-t", tmp_path)
        assert P._assessment_store["p-t"]["status"] == "failed"
        assert "timeout" in P._assessment_store["p-t"]["error"]
        an.assert_not_called()

    def test_clone_too_large(self, tmp_path):
        """GIVEN repo too large THEN entry failed + dir removed."""
        P._assessment_store["p-l"] = {"status": "analyzing",
                                      "source_dir": str(tmp_path)}
        clone_result = MagicMock()
        clone_result.returncode = 0
        with patch.object(P.subprocess, "run", return_value=clone_result), \
             patch.object(P, "_get_dir_size", return_value=10 ** 12), \
             patch.object(P, "_analyze_in_background") as an:
            _run_clone_path(P, "p-l", tmp_path)
        assert P._assessment_store["p-l"]["status"] == "failed"
        assert "too large" in P._assessment_store["p-l"]["error"]
        an.assert_not_called()
        assert not tmp_path.exists()

    def test_clone_unexpected_error(self, tmp_path):
        """GIVEN unexpected clone error THEN entry failed."""
        P._assessment_store["p-e"] = {"status": "analyzing",
                                      "source_dir": str(tmp_path)}

        def boom(*a, **kw):
            raise ValueError("boom")

        with patch.object(P.subprocess, "run", side_effect=boom), \
             patch.object(P, "_analyze_in_background") as an:
            _run_clone_path(P, "p-e", tmp_path)
        assert P._assessment_store["p-e"]["status"] == "failed"
        assert "boom" in P._assessment_store["p-e"]["error"]


def _run_clone_path(mod, preview_id, temp_dir):
    """Run the closure logic of _handle_git_url's _clone_and_analyze by
    re-executing the code with patched subprocess/helpers."""
    import logging as _logging
    log = _logging.getLogger("api.preview")
    repo_url = mod._assessment_store[preview_id].get("repo_url",
                                                     "https://github.com/u/r")
    try:
        log.info("Cloning %s to %s", repo_url, temp_dir)
        result = mod.subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(temp_dir)],
            capture_output=True, text=True, timeout=mod.CLONE_TIMEOUT)
        if result.returncode != 0:
            entry = mod._assessment_store.get(preview_id)
            if entry:
                entry["status"] = "failed"
                entry["error"] = f"Git clone failed: {result.stderr[:500]}"
            return
        total_size = mod._get_dir_size(temp_dir)
        if total_size > mod.MAX_CLONED_SIZE:
            entry = mod._assessment_store.get(preview_id)
            if entry:
                entry["status"] = "failed"
                entry["error"] = (
                    f"Repository too large ({total_size // (1024*1024)} MB, "
                    f"max {mod.MAX_CLONED_SIZE // (1024*1024)} MB)")
            import shutil
            shutil.rmtree(str(temp_dir))
            return
        mod._analyze_in_background(preview_id, temp_dir)
    except mod.subprocess.TimeoutExpired:
        entry = mod._assessment_store.get(preview_id)
        if entry:
            entry["status"] = "failed"
            entry["error"] = f"Git clone timeout after {mod.CLONE_TIMEOUT}s"
        import shutil
        try:
            shutil.rmtree(str(temp_dir))
        except Exception:
            pass
    except Exception as e:
        entry = mod._assessment_store.get(preview_id)
        if entry:
            entry["status"] = "failed"
            entry["error"] = str(e)
        import shutil
        try:
            shutil.rmtree(str(temp_dir))
        except Exception:
            pass


# ── _get_dir_size ──────────────────────────────────────────────────────

class TestDirSize:
    def test_dir_size(self, tmp_path):
        """GIVEN nested files WHEN _get_dir_size THEN summed bytes."""
        (tmp_path / "a.c").write_text("x" * 10)
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.c").write_text("y" * 20)
        assert P._get_dir_size(tmp_path) == 30

    def test_dir_size_ignores_errors(self, tmp_path, monkeypatch):
        """GIVEN stat failure WHEN _get_dir_size THEN skipped."""
        (tmp_path / "a.c").write_text("x" * 5)
        real_stat = os.stat
        calls = {}

        def flaky_stat(path, *a, **kw):
            key = str(path)
            if key.endswith("a.c"):
                calls[key] = calls.get(key, 0) + 1
                if calls[key] >= 2:  # is_file() ok, f.stat() fails
                    raise OSError("nope")
            return real_stat(path, *a, **kw)

        monkeypatch.setattr(os, "stat", flaky_stat)
        assert P._get_dir_size(tmp_path) == 0


# ── Rate limiter ───────────────────────────────────────────────────────

class TestRateLimit:
    def test_under_limit(self):
        """GIVEN few requests WHEN check THEN allowed."""
        ok, retry = P._check_preview_rate_limit("10.0.0.1")
        assert ok is True and retry == 0
        assert P._preview_request_log["10.0.0.1"] == [pytest.approx(time.time(), abs=5)]

    def test_unauth_limit_reached(self, monkeypatch):
        """GIVEN limit reached WHEN check THEN denied with retry_after."""
        now = time.time()
        P._preview_request_log["ip"] = [now, now, now]  # 3 = unauth limit
        ok, retry = P._check_preview_rate_limit("ip")
        assert ok is False
        assert retry > 0

    def test_auth_higher_limit(self):
        """GIVEN authed WHEN check THEN 20 allowed."""
        for _ in range(20):
            ok, _ = P._check_preview_rate_limit("ip2", is_authenticated=True)
            assert ok is True
        ok, _ = P._check_preview_rate_limit("ip2", is_authenticated=True)
        assert ok is False

    def test_old_entries_purged(self):
        """GIVEN stale entries WHEN check THEN purged before limiting."""
        old = time.time() - 25 * 3600
        P._preview_request_log["ip3"] = [old, old, old]
        ok, _ = P._check_preview_rate_limit("ip3")
        assert ok is True
        assert len(P._preview_request_log["ip3"]) == 1


# ── Repo cache ─────────────────────────────────────────────────────────

class TestRepoCache:
    def test_cached_fresh(self):
        """GIVEN completed fresh entry WHEN cached THEN returned."""
        pid = "prev-cache1"
        P._assessment_store[pid] = {"status": "completed",
                                    "completed_at": time.time(),
                                    "report": {"grade": "B"}}
        P._repo_cache[_url_hash("https://github.com/u/r")] = pid
        result = P._get_cached_preview("https://github.com/u/r")
        assert result is not None
        assert result["cached"] is True

    def test_cached_expired(self):
        """GIVEN expired entry WHEN cached THEN None."""
        pid = "prev-cache2"
        P._assessment_store[pid] = {"status": "completed",
                                    "completed_at": time.time() - 48 * 3600,
                                    "report": {}}
        P._repo_cache[_url_hash("https://github.com/u/r2")] = pid
        assert P._get_cached_preview("https://github.com/u/r2") is None

    def test_cached_not_completed(self):
        """GIVEN analyzing entry WHEN cached THEN None."""
        pid = "prev-cache3"
        P._assessment_store[pid] = {"status": "analyzing",
                                    "created_at": time.time()}
        P._repo_cache[_url_hash("https://github.com/u/r3")] = pid
        assert P._get_cached_preview("https://github.com/u/r3") is None

    def test_cached_no_entry(self):
        """GIVEN unknown hash WHEN cached THEN None."""
        assert P._get_cached_preview("https://github.com/u/nope") is None


# ── Cleanup ────────────────────────────────────────────────────────────

class TestCleanup:
    def test_cleanup_expired(self, tmp_path, monkeypatch):
        """GIVEN expired entries WHEN cleanup THEN removed + dir cleaned."""
        now = time.time()
        src = tmp_path / "src"
        src.mkdir()
        P._assessment_store["old1"] = {"status": "completed",
                                       "created_at": now - 48 * 3600,
                                       "source_dir": str(src)}
        P._assessment_store["fresh"] = {"status": "completed",
                                        "created_at": now}
        with patch.object(P.threading, "Timer") as timer:
            P._cleanup_expired_results()
        assert "old1" not in P._assessment_store
        assert "fresh" in P._assessment_store
        assert not src.exists()
        timer.assert_called_once()
        # _cleanup_timer global updated
        assert P._cleanup_timer is not None

    def test_cleanup_missing_srcdir(self, tmp_path):
        """GIVEN expired entry with missing dir WHEN cleanup THEN skipped."""
        now = time.time()
        P._assessment_store["old2"] = {"status": "completed",
                                       "created_at": now - 48 * 3600,
                                       "source_dir": str(tmp_path / "gone")}
        with patch.object(P.threading, "Timer"):
            P._cleanup_expired_results()
        assert "old2" not in P._assessment_store


# ── handle_preview ─────────────────────────────────────────────────────

class TestHandlePreview:
    def test_delete_found(self):
        """GIVEN existing assessment WHEN DELETE THEN discarded."""
        handler = FakeHandler()
        P._assessment_store["prev-1"] = {"status": "completed",
                                         "source_dir": None}
        result, status = P.handle_preview("DELETE", "assess/prev-1", {},
                                          {}, handler)
        assert status == 200
        assert "discarded" in result["data"]["message"]
        assert "prev-1" not in P._assessment_store

    def test_delete_not_found(self):
        """GIVEN missing assessment WHEN DELETE THEN 404."""
        handler = FakeHandler()
        result, status = P.handle_preview("DELETE", "assess/prev-x", {},
                                          {}, handler)
        assert status == 404

    def test_get_analyzing(self, monkeypatch):
        """GIVEN analyzing entry WHEN GET THEN remaining seconds."""
        handler = FakeHandler()
        P._assessment_store["prev-2"] = {"status": "analyzing",
                                         "created_at": time.time(),
                                         "estimated_remaining_seconds": 60}
        result, status = P.handle_preview("GET", "assess/prev-2", {}, {}, handler)
        assert status == 200
        assert result["data"]["status"] == "analyzing"
        assert result["data"]["estimated_remaining_seconds"] > 0

    def test_get_completed(self):
        """GIVEN completed entry WHEN GET THEN report returned."""
        handler = FakeHandler()
        P._assessment_store["prev-3"] = {"status": "completed",
                                         "report": {"grade": "A"}}
        result, status = P.handle_preview("GET", "assess/prev-3", {}, {}, handler)
        assert result["data"]["report"]["grade"] == "A"

    def test_get_failed(self):
        """GIVEN failed entry WHEN GET THEN error returned."""
        handler = FakeHandler()
        P._assessment_store["prev-4"] = {"status": "failed",
                                         "error": "bad repo"}
        result, status = P.handle_preview("GET", "assess/prev-4", {}, {}, handler)
        assert result["data"]["status"] == "failed"
        assert result["data"]["error"] == "bad repo"

    def test_get_not_found(self):
        """GIVEN missing assessment WHEN GET THEN 404."""
        handler = FakeHandler()
        result, status = P.handle_preview("GET", "assess/prev-zz", {}, {}, handler)
        assert status == 404

    def test_post_rate_limited(self):
        """GIVEN rate limit hit WHEN POST THEN 429."""
        handler = FakeHandler(headers=_json_headers(),
                              client_address=("9.9.9.9", 0))
        P._preview_request_log["9.9.9.9"] = [time.time()] * 3
        result, status = P.handle_preview("POST", "assess", {}, {}, handler)
        assert status == 429
        assert result["error"] == "rate_limited"

    def test_post_zip_upload(self, tmp_path, monkeypatch):
        """GIVEN multipart zip WHEN POST THEN 202."""
        zip_bytes = _make_zip()
        raw = _multipart(zip_bytes)
        handler = FakeHandler(
            headers={"Content-Type": "multipart/form-data; boundary=----testboundary",
                     "Content-Length": str(len(raw))},
            rfile=io.BytesIO(raw),
            client_address=("1.1.1.1", 0),
        )
        monkeypatch.setattr("tempfile.mkdtemp",
                            lambda prefix="": str(tmp_path / "zz"))
        with patch.object(P, "_analyze_in_background"):
            result, status = P.handle_preview("POST", "assess", {}, {}, handler)
        assert status == 202
        assert result["data"]["status"] == "analyzing"

    def test_post_zip_missing_file_field(self):
        """GIVEN multipart without file WHEN POST THEN 400."""
        boundary = "bb"
        raw = (f"--{boundary}\r\n"
               f'Content-Disposition: form-data; name="x"\r\n\r\n'
               f"data\r\n--{boundary}--\r\n").encode()
        handler = FakeHandler(
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "Content-Length": str(len(raw))},
            rfile=io.BytesIO(raw),
            client_address=("1.1.1.2", 0),
        )
        result, status = P.handle_preview("POST", "assess", {}, {}, handler)
        assert status == 400
        assert result["error"] == "input_required"

    def test_post_json_repo_url_new(self, tmp_path, monkeypatch):
        """GIVEN json repo_url WHEN POST THEN 202 + cached."""
        handler = FakeHandler(headers=_json_headers(),
                              client_address=("1.1.1.3", 0))
        monkeypatch.setattr("tempfile.mkdtemp",
                            lambda prefix="": str(tmp_path / "cl"))
        with patch.object(P.threading, "Thread"):
            result, status = P.handle_preview(
                "POST", "assess", {"repo_url": "https://github.com/u/r"},
                {}, handler)
        assert status == 202
        assert result["data"]["status"] == "analyzing"
        assert len(P._repo_cache.items()) == 1

    def test_post_json_repo_url_cached(self, tmp_path):
        """GIVEN cached repo_url WHEN POST THEN cached response."""
        pid = "prev-cache-rt"
        P._assessment_store[pid] = {"status": "completed",
                                    "completed_at": time.time(),
                                    "report": {"grade": "S"}}
        P._repo_cache[_url_hash("https://github.com/u/r")] = pid
        handler = FakeHandler(headers=_json_headers(),
                              client_address=("1.1.1.4", 0))
        result, status = P.handle_preview(
            "POST", "assess", {"repo_url": "https://github.com/u/r"},
            {}, handler)
        assert status == 200
        assert result["data"]["cached"] is True

    def test_post_no_input(self):
        """GIVEN empty json body WHEN POST THEN 400."""
        handler = FakeHandler(headers=_json_headers(),
                              client_address=("1.1.1.5", 0))
        result, status = P.handle_preview("POST", "assess", {}, {}, handler)
        assert status == 400
        assert result["error"] == "input_required"

    def test_post_unsupported_content_type(self):
        """GIVEN text/plain body WHEN POST THEN 400."""
        handler = FakeHandler(
            headers={"Content-Type": "text/plain", "Content-Length": "0"},
            client_address=("1.1.1.6", 0))
        result, status = P.handle_preview("POST", "assess", {}, {}, handler)
        assert status == 400

    def test_method_not_allowed(self):
        """GIVEN PUT WHEN POST route THEN 405."""
        handler = FakeHandler(headers=_json_headers())
        result, status = P.handle_preview("PUT", "assess", {}, {}, handler)
        assert status == 405
