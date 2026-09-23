"""Regression: ``run_captured`` must not deadlock on inherited capture fds.

Promoted from a scratch script that lived in ``.pytest-tmp/`` (since deleted),
because the suite had **no** coverage for the failure mode it pinned.

The real incident (pipeline step-17 ``integration-test``): ``cmake -S -B build``
spawns cc1/configure children which inherit the stdout/stderr pipe. With the old
``subprocess.run(capture_output=True, timeout=N)`` the write end of the pipe is
never closed by the grandchild, so ``communicate()`` blocks forever — the
``timeout`` never fires and the worker thread hangs (this is what wedged the
pipeline thread before commit ``07cc1dfb``).

``run_captured`` fixes that by redirecting stdout/stderr to a temp *file*
(no pipe to inherit) and, on timeout, ``killpg``-ing the whole process group so
the grandchildren die too. ``returncode is None`` signals the timeout.

Each test below uses ``bash`` to spawn ``(sleep N &)`` so a grandchild outlives
the direct child while holding the inherited fd.
"""

import shutil
import time

import pytest

from yuleosh.pipeline.safe_run import run_captured

_BASH = shutil.which("bash") or "/bin/bash"


def test_no_pipe_deadlock_when_grandchild_holds_capture_fd():
    """Parent exits at once but its grandchild keeps the fd → must not hang.

    Under the old implementation this call never returned; the assertion on
    ``elapsed`` is the actual regression guard.
    """
    cmd = [_BASH, "-c", "(sleep 8 &) ; echo CHILD_DONE ; exit 0"]

    t0 = time.time()
    res = run_captured(cmd, cwd=None, timeout=10, label="deadlock-regression")
    elapsed = time.time() - t0

    assert elapsed < 8, f"DEADLOCK: run_captured hung for {elapsed:.1f}s"
    assert res.returncode == 0, f"expected rc=0, got {res.returncode!r}"
    assert "CHILD_DONE" in res.stdout, f"output not captured: {res.stdout!r}"


def test_timeout_returns_none_instead_of_hanging():
    """A live child past the deadline → rc is None (no raise, no hang)."""
    cmd = [_BASH, "-c", "(sleep 8 &) ; sleep 30"]

    t0 = time.time()
    res = run_captured(cmd, cwd=None, timeout=2, label="deadlock-timeout")
    elapsed = time.time() - t0

    assert res.returncode is None, f"expected rc=None on timeout, got {res.returncode!r}"
    assert 1.5 <= elapsed < 10, f"timeout path took {elapsed:.1f}s (expected ~2s)"


def test_timeout_kills_the_whole_process_group(tmp_path):
    """killpg, not just ``proc.kill()`` — the grandchild must die too.

    The grandchild touches a marker 3s in; the group is killed at 2s, so a
    surviving grandchild is observable as a marker file that should not exist.
    """
    marker = tmp_path / "grandchild_survived.txt"
    cmd = [_BASH, "-c", f"(sleep 3 && touch {marker}) & sleep 30"]

    res = run_captured(cmd, cwd=None, timeout=2, label="killpg-check")
    assert res.returncode is None

    time.sleep(4)  # let the grandchild prove it lived, if it did
    assert not marker.exists(), (
        "grandchild outlived the timeout → killpg did not reap the process group"
    )


if __name__ == "__main__":  # pragma: no cover - manual smoke entry
    raise SystemExit(pytest.main([__file__, "-q"]))
