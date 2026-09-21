#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0
"""Robust subprocess runner that avoids the classic ``capture_output`` deadlock.

Background
----------
Several pipeline steps shell out to ``cmake`` / ``ctest`` / ``make`` / a test
binary. Those programs spawn child processes (``cc1``, ``as``, the test exe
itself, …) that **inherit the captured stdout/stderr pipe**. When the direct
child is killed by ``subprocess.run(..., timeout=N)``, the grandchildren keep
the pipe write-end open, so ``communicate()`` blocks forever waiting for EOF —
the timeout no longer fires and the orchestrator thread hangs indefinitely.

Fix
---
* Redirect stdout+stderr to a **temp file** (no pipe → nothing to deadlock on).
* ``start_new_session=True`` puts the whole tree in its own process group, so
  on timeout we can ``os.killpg`` the entire group, not just the direct child.
* Returns a :class:`RunResult` (``returncode`` is ``None`` on timeout, ``stdout``/
  ``stderr`` hold the combined temp-file text). ``returncode`` being ``None`` lets
  the caller distinguish a timeout from a real non-zero exit.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
from pathlib import Path


def _normalize_env(env):
    """Return a str-keyed env dict safe for ``subprocess.Popen``.

    On macOS (and some sandboxed shells) ``os.environ`` can carry *bytes* keys
    (e.g. ``b'PATH'``) alongside the str ``'PATH'``. ``subprocess`` then raises
    ``ValueError: env cannot contain 'PATH' and b'PATH' keys`` when it resolves
    the executable path. We collapse bytes keys to str (surrogate-escape) and
    let a later ``'PATH'`` win, so the conflict can never occur.
    """
    if env is None:
        env = os.environ
    out = {}
    for k, v in env.items():
        if isinstance(k, bytes):
            k = k.decode("utf-8", "surrogateescape")
        out[k] = v
    return out


def run_captured(
    cmd,
    cwd=None,
    timeout: int = 180,
    label: str = "cmd",
    log_dir=None,
    env=None,
) -> "RunResult":
    """Run ``cmd`` without a captured pipe.

    Returns a :class:`RunResult` with ``returncode`` (``None`` on timeout) and
    ``stdout``/``stderr`` (combined stream text). ``returncode`` is ``None``
    when the command timed out; ``stdout``/``stderr`` are the combined text.
    """
    log_path = Path(
        tempfile.mktemp(prefix=f"yuleosh-{label}-", suffix=".log", dir=log_dir)
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as lf:
        proc = subprocess.Popen(
            list(cmd),
            cwd=cwd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_normalize_env(env),
        )
        try:
            proc.wait(timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
            rc = None
    try:
        out = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        out = ""
    try:
        log_path.unlink()
    except OSError:
        pass
    return RunResult(rc, out, out, cmd)


__all__ = ["run_captured", "safe_subprocess_run", "RunResult"]


class RunResult:
    """Minimal ``subprocess.CompletedProcess``-compatible result.

    Returned by :func:`safe_subprocess_run` so existing call sites that read
    ``proc.returncode`` / ``proc.stdout`` / ``proc.stderr`` keep working
    unchanged. ``stdout`` and ``stderr`` are the *combined* stream text.
    """

    def __init__(self, returncode, stdout, stderr, args):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.args = args

    def __repr__(self):  # pragma: no cover - debug aid
        return f"RunResult(returncode={self.returncode!r})"

    def check_returncode(self):  # pragma: no cover - parity with stdlib
        if self.returncode != 0:
            raise subprocess.CalledProcessError(
                self.returncode, self.args, self.stdout, self.stderr,
            )


def safe_subprocess_run(
    cmd,
    *,
    cwd=None,
    timeout=None,
    capture_output=False,  # accepted for drop-in parity, ignored (always captured)
    text=False,            # accepted for parity, ignored (always returns str)
    check=False,
    input=None,
    env=None,
    shell=False,
    encoding=None,
    errors=None,
    **kwargs,
) -> RunResult:
    """Drop-in replacement for ``subprocess.run(..., capture_output=True)``.

    Unlike ``subprocess.run`` with a captured pipe, this redirects the child's
    stdout+stderr to a **temp file** and runs the whole process tree in its own
    session. On timeout it kills the *entire process group* (grandchildren
    included) and then raises ``subprocess.TimeoutExpired`` — exactly mirroring
    stdlib ``subprocess.run(..., timeout=N)`` semantics, but without the classic
    pipe-deadlock where a grandchild (cc1 / make / gcov) keeps the pipe write-end
    open and ``communicate()`` blocks forever.

    Returns a :class:`RunResult` with ``returncode`` / ``stdout`` / ``stderr``
    (both streams combined into ``stdout`` and ``stderr`` for safety).
    """
    log_path = Path(
        tempfile.mktemp(prefix="yuleosh-run-", suffix=".log")
    )
    popen_cmd = cmd if shell else list(cmd)
    feed = (
        input.encode(encoding or "utf-8", errors=errors or "replace")
        if isinstance(input, str) else input
    )
    # Drop any explicit stdout/stderr the caller passed — we always redirect to
    # a temp file to avoid the captured-pipe deadlock.
    kwargs.pop("stdout", None)
    kwargs.pop("stderr", None)
    with open(log_path, "w") as lf:
        proc = subprocess.Popen(
            popen_cmd,
            cwd=cwd,
            stdout=lf,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if input is not None else None,
            start_new_session=True,
            shell=shell,
            env=_normalize_env(env),
            **kwargs,
        )
        try:
            proc.communicate(feed, timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            try:
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
            # Mirror stdlib: timeout raises TimeoutExpired (not a None return).
            raise
    try:
        out = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        out = ""
    try:
        log_path.unlink()
    except OSError:
        pass
    if check and rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, out, out)
    return RunResult(rc, out, out, cmd)
