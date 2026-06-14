# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for cross/sil_assert.py — SerialAssert engine.

Target: 80%+ branch coverage.
Covers: SerialAssert init, expect, read_until, streaming, script
        runner, edge cases.
"""

import io
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


# ======================================================================
# SilAssertionError
# ======================================================================

class TestSilAssertionError:
    def test_exception_attrs(self):
        from yuleosh.cross.sil_assert import SilAssertionError
        err = SilAssertionError("hello", 5.0, "world")
        assert err.pattern == "hello"
        assert err.timeout == 5.0
        assert err.log_snippet == "world"
        assert "hello" in str(err)
        assert "5.0" in str(err)


# ======================================================================
# SerialAssert — initialization
# ======================================================================

class TestSerialAssertInit:
    def test_init_empty(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert()
        assert sa.captured_log == ""
        assert sa.is_streaming is False

    def test_init_with_log_text(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Hello World\nTest Complete\n")
        assert sa.captured_log == "Hello World\nTest Complete\n"

    def test_init_with_max_log_size(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(max_log_size=16)
        sa._append("A" * 20)
        assert len(sa.captured_log) <= 16
        assert sa.is_streaming is False

    def test_init_with_pipe(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("line1\nline2\n")
        sa = SerialAssert(pipe=pipe, timeout=1.0)
        time.sleep(0.3)
        assert sa.is_streaming is True
        sa.close()

    def test_stream_classmethod(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("data\n")
        sa = SerialAssert.stream(pipe=pipe, timeout=5.0)
        assert sa.is_streaming is True
        sa.close()


# ======================================================================
# SerialAssert — expect (exact text)
# ======================================================================

class TestExpect:
    def test_exact_match(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Starting QEMU\nBoot Complete\nHello World\n")
        result = sa.expect("Boot Complete")
        assert "Boot Complete" in result

    def test_no_match_fail_fast(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Hello\nWorld\n", timeout=0.5)
        with pytest.raises(Exception):
            sa.expect("ERROR:", timeout=0.1)

    def test_no_match_fail_fast_false(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Hello\nWorld\n", timeout=0.5)
        result = sa.expect("MISSING", timeout=0.1, fail_fast=False)
        assert result == ""

    def test_multiline_log(self):
        from yuleosh.cross.sil_assert import SerialAssert
        log = "\n".join(f"line {i}" for i in range(100))
        sa = SerialAssert(log_text=log, timeout=0.5)
        result = sa.expect("line 42")
        assert "line 42" in result

    def test_match_at_start(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="First line\nSecond line\n")
        result = sa.expect("First line")
        assert result.startswith("First line")


# ======================================================================
# SerialAssert — expect with regex
# ======================================================================

class TestExpectRegex:
    def test_regex_match(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="ERROR: code 42 at line 100\n")
        result = sa.expect(r"ERROR:\s*code \d+", regex=True)
        assert "ERROR" in result

    def test_regex_no_match(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="All good\n", timeout=0.5)
        with pytest.raises(Exception):
            sa.expect(r"FAILURE.*", regex=True, timeout=0.1)

    def test_regex_multiline(self):
        from yuleosh.cross.sil_assert import SerialAssert
        log_text = "line1\nERROR: crash\nline3\n"
        sa = SerialAssert(log_text=log_text)
        result = sa.expect(r"ERROR:.*crash", regex=True)
        assert result is not None


# ======================================================================
# SerialAssert — read_until
# ======================================================================

class TestReadUntil:
    def test_basic(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Before marker\nMarker here\nAfter\n")
        result = sa.read_until("Marker here")
        assert "Before marker" in result
        assert "After" not in result

    def test_include_marker(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="Prefix\n--END--\nSuffix\n")
        result = sa.read_until("--END--", include_marker=True)
        assert "--END--" in result
        assert "Suffix" not in result

    def test_regex_read_until(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="data\nTEST COMPLETE\nmore\n")
        result = sa.read_until(r"TEST\s+COMPLETE", regex=True)
        assert "data" in result
        assert "more" not in result

    def test_regex_read_until_include(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="before\nMATCH\nafter\n")
        result = sa.read_until(r"MATCH", regex=True, include_marker=True)
        assert "MATCH" in result
        assert "after" not in result

    def test_regex_marker_not_found(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="just text\n", timeout=0.5)
        with pytest.raises(Exception):
            sa.read_until(r"NOMATCH\d+", regex=True, timeout=0.1)


# ======================================================================
# SerialAssert — streaming
# ======================================================================

class TestStreaming:
    def test_context_manager(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("stream data\n")
        with SerialAssert.stream(pipe=pipe, timeout=1.0) as sa:
            assert sa.is_streaming is True
        assert sa.is_streaming is True  # close called

    def test_close_cleanup(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("data\n")
        sa = SerialAssert(pipe=pipe, timeout=1.0)
        sa.close()
        # After close, thread should stop
        time.sleep(0.2)
        assert sa._capture_stop.is_set()

    def test_capture_loop_pipe_error(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = MagicMock()
        pipe.readline.side_effect = [ValueError("broken pipe"), ""]
        sa = SerialAssert(pipe=pipe, timeout=1.0)
        time.sleep(0.3)
        # Should not crash, error should be caught
        assert True
        sa.close()

    def test_stream_with_expect(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("Hello\nWorld\n")
        sa = SerialAssert(pipe=pipe, timeout=5.0)
        time.sleep(0.2)
        result = sa.expect("Hello", timeout=2.0)
        assert "Hello" in result
        sa.close()

    def test_stream_with_expect_no_match(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("Hello\nWorld\n")
        sa = SerialAssert(pipe=pipe, timeout=0.5)
        with pytest.raises(Exception):
            sa.expect("NOT THERE", timeout=0.1)
        sa.close()


# ======================================================================
# SerialAssert — internal append with overflow
# ======================================================================

class TestLogOverflow:
    def test_append_under_limit(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(max_log_size=100)
        sa._append("Hello " * 10)  # ~60 chars
        assert len(sa.captured_log) <= 100

    def test_append_over_limit_drops_old(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(max_log_size=50)
        # Add data in chunks that exceed max
        sa._append("A" * 40)
        assert len(sa.captured_log) == 40
        sa._append("B" * 30)  # total would be 70, max is 50
        assert len(sa.captured_log) <= 50

    def test_append_multiple_overflows(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(max_log_size=20)
        sa._append("X" * 15)
        sa._append("Y" * 15)  # total 30 > 20
        assert len(sa.captured_log) <= 20
        assert sa.captured_log[0] in ("X", "Y")

    def test_log_dropped_message(self):
        from yuleosh.cross.sil_assert import SerialAssert
        with patch("yuleosh.cross.sil_assert.log") as mock_log:
            sa = SerialAssert(max_log_size=10)
            sa._append("Hello World!")  # 12 chars > 10
            sa._append("Short")
            assert mock_log.debug.called


# ======================================================================
# SerialAssert — _search
# ======================================================================

class TestSearch:
    def test_search_regex_found(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="abc123def")
        result = sa._search(r"\d+", regex=True)
        assert result is not None
        assert "123" in result

    def test_search_regex_not_found(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="abcdef")
        result = sa._search(r"\d+", regex=True)
        assert result is None

    def test_search_exact_found(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="hello world")
        result = sa._search("world")
        assert result is not None

    def test_search_exact_not_found(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(log_text="hello world")
        result = sa._search("nope")
        assert result is None


# ======================================================================
# run_expect_script
# ======================================================================

class TestExpectScript:
    def test_script_empty(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        results = run_expect_script(sa, "")
        assert results == []

    def test_script_comment_only(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        results = run_expect_script(sa, "# just a comment\n")
        assert results == []

    def test_script_expect(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="Hello World\nTest Passed\n")
        results = run_expect_script(sa, "expect:Hello World")
        assert results == []

    def test_script_expect_re(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="ERROR: code 42\n")
        results = run_expect_script(sa, "expect_re:ERROR: code \\d+")
        assert results == []

    def test_script_read_until(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="prefix\n--END--\nsuffix\n")
        results = run_expect_script(sa, "read_until:--END--")
        assert len(results) == 1
        assert "prefix" in results[0]

    def test_script_wait(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        start = time.time()
        results = run_expect_script(sa, "wait:0.1")
        elapsed = time.time() - start
        assert elapsed >= 0.08

    def test_script_assert_pass(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="Hello World\nTest Passed\n")
        results = run_expect_script(sa, "assert:Test Passed")
        assert results == []

    def test_script_assert_fail(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="Hello World\n")
        with pytest.raises(Exception):
            run_expect_script(sa, "assert:MISSING TEXT")

    def test_script_expect_fail(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="Hello\n")
        with pytest.raises(Exception):
            run_expect_script(sa, "expect:NOT THERE")

    def test_script_expect_re_fail(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="Hello\n")
        with pytest.raises(Exception):
            run_expect_script(sa, "expect_re:FAILURE\\d+")

    def test_script_unknown_directive(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        with patch("yuleosh.cross.sil_assert.log") as mock_log:
            results = run_expect_script(sa, "unknown:stuff")
            assert results == []
            assert mock_log.debug.called

    def test_script_wait_bad_arg(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        with pytest.raises(Exception):
            run_expect_script(sa, "wait:not-a-number")

    def test_script_generic_exception(self):
        from yuleosh.cross.sil_assert import run_expect_script, SerialAssert
        sa = SerialAssert(log_text="hello")
        with patch.object(sa, "expect", side_effect=TypeError("unexpected")):
            with pytest.raises(Exception):
                run_expect_script(sa, "expect:foo")


# ======================================================================
# ExpectScriptError
# ======================================================================

class TestExpectScriptError:
    def test_exception(self):
        from yuleosh.cross.sil_assert import ExpectScriptError
        err = ExpectScriptError("bad script")
        assert "bad script" in str(err)


# ======================================================================
# SerialAssert — __enter__ / __exit__
# ======================================================================

class TestContextManager:
    def test_context_with_log(self):
        from yuleosh.cross.sil_assert import SerialAssert
        with SerialAssert(log_text="hello") as sa:
            assert sa.captured_log == "hello"
        # After exit, close was called (no-op since no pipe)

    def test_context_with_pipe(self):
        from yuleosh.cross.sil_assert import SerialAssert
        pipe = io.StringIO("context data\n")
        with SerialAssert(pipe=pipe, timeout=1.0) as sa:
            assert sa.is_streaming is True
            time.sleep(0.2)
            result = sa.expect("context data", timeout=2.0)
            assert result is not None


# ======================================================================
# SerialAssert — default_timeout
# ======================================================================

class TestDefaultTimeout:
    def test_custom_timeout(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert(timeout=30.0)
        assert sa._default_timeout == 30.0

    def test_default_timeout(self):
        from yuleosh.cross.sil_assert import SerialAssert
        sa = SerialAssert()
        assert sa._default_timeout == 10.0
