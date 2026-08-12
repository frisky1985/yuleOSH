#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Compile verification for generated code.

Detects the target language from the generated files and runs a local
syntax/compile check:

* Python  — ``python3 -m py_compile <files>``
* C       — ``gcc -fsyntax-only <files>`` (falls back to ``cc``)

Results are returned as plain dicts so the caller (codegen engine) can feed
errors back into the LLM retry loop.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.codegen.compilers")

LANGUAGE_PYTHON = "python"
LANGUAGE_C = "c"
LANGUAGE_UNKNOWN = "unknown"

_PY_EXTS = {".py", ".pyw"}
_C_EXTS = {".c", ".h"}
_CXX_EXTS = {".cpp", ".cc", ".cxx", ".hpp", ".hh"}

# Result dict keys shared by all verifiers.
KEYS = ("ok", "language", "command", "output", "errors", "returncode")


def detect_language(files: list[str | Path]) -> str:
    """Detect the primary language from file extensions.

    Returns ``python``, ``c``, or ``unknown``.  C++ files map to ``c`` for
    the syntax check (g++ preferred when present, see :func:`compile_verify`).
    """
    exts = {Path(str(f)).suffix.lower() for f in files}
    if exts & _PY_EXTS:
        return LANGUAGE_PYTHON
    if exts & (_C_EXTS | _CXX_EXTS):
        return LANGUAGE_C
    return LANGUAGE_UNKNOWN


def _result(ok: bool, language: str, command: str, output: str, returncode: int) -> dict:
    return {
        "ok": ok,
        "language": language,
        "command": command,
        "output": output,
        "errors": output.strip(),
        "returncode": returncode,
    }


def verify_python(files: list[Path], python_cmd: str = "python3") -> dict:
    """Syntax-check Python files with ``python -m py_compile``.

    2026-08-12: 只编译 ``.py`` 后缀文件 — 生成目录可能同时含 C 头文件
    (seed 基线 + LLM 输出混合), 把 .h 丢给 py_compile 会误报失败。
    """
    py_files = [f for f in files if Path(str(f)).suffix.lower() in _PY_EXTS]
    if not py_files:
        return _result(True, LANGUAGE_PYTHON, f"{python_cmd} -m py_compile",
                       "(no .py files to verify)", 0)
    cmd = [python_cmd, "-m", "py_compile", *[str(f) for f in py_files]]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        return _result(
            ok=proc.returncode == 0,
            language=LANGUAGE_PYTHON,
            command=" ".join(cmd),
            output=(proc.stderr or proc.stdout).strip(),
            returncode=proc.returncode,
        )
    except FileNotFoundError:
        return _result(False, LANGUAGE_PYTHON, " ".join(cmd),
                       f"compiler not found: {python_cmd}", -1)
    except subprocess.TimeoutExpired:
        return _result(False, LANGUAGE_PYTHON, " ".join(cmd),
                       "py_compile timed out (120s)", -1)


def verify_c(
    files: list[Path],
    cc: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Syntax-check C/C++ files with ``gcc -fsyntax-only`` (or ``cc``).

    E2E fix (2026-08-11): generated multi-file projects were always
    reported as failed because:
      1. non-C inputs (CMakeLists.txt / README.md) were passed to gcc as
         source files — harmless warnings, but noisy;
      2. `#include "local.h"` from sibling dirs (e.g. src/hal/src/*.c
         including src/hal/include/*.h) failed with "file not found"
         because no -I include paths were passed — the generated code
         itself was fine, the verifier was not.

    Fix: only pass C/C++ sources to the compiler, collect sibling
    ``include/`` / ``*.h`` directories as -I paths, and if the first
    pass still fails, retry once with the same -I set (defensive).

    project_root (2026-08-12): generated app code depends on the host
    project's HAL headers (e.g. ``#include "hal_motor.h"`` lives in
    ``<project>/src/hal/include/``, which the gen dir never contains).
    When provided, also scan ``<project_root>/src/**/include`` so the
    generated code compiles against the real project API surface.
    """
    c_exts = _C_EXTS | _CXX_EXTS
    sources = [f for f in files if Path(str(f)).suffix.lower() in c_exts]
    if not sources:
        return _result(True, LANGUAGE_C, "gcc -fsyntax-only",
                       "(no C/C++ sources to verify)", 0)
    cc = cc or shutil.which("gcc") or shutil.which("cc")
    if not cc:
        return _result(False, LANGUAGE_C, "gcc -fsyntax-only",
                       "no C compiler (gcc/cc) found on PATH", -1)

    # Collect -I dirs: any directory that contains headers referenced by
    # the sources (project include/ dirs + sibling dirs of sources).
    inc_dirs: list[str] = []
    seen: set[str] = set()
    for f in sources:
        parent = Path(str(f)).parent
        candidates = [
            parent / "include",
            parent.parent / "include",
            parent,
        ]
        for cand in candidates:
            if cand.is_dir() and any(
                p.suffix.lower() in c_exts for p in cand.iterdir()
            ):
                key = str(cand)
                if key not in seen:
                    seen.add(key)
                    inc_dirs.append(key)
    # Cross-layer include fix (2026-08-11): app sources include HAL headers
    # (e.g. src/app/src/*.c → src/hal/include/*.h) which sibling-dir
    # inference never sees.  Scan sibling modules under the modules root:
    # for a source at <root>/<module>/src/<file>.c, add every
    # <root>/<other-module>/include dir.
    for f in sources:
        parent = Path(str(f)).parent
        modules_root = parent.parent.parent
        if modules_root.is_dir():
            for module in sorted(modules_root.iterdir()):
                inc = module / "include"
                if inc.is_dir() and any(
                    p.suffix.lower() in c_exts for p in inc.iterdir()
                ):
                    key = str(inc)
                    if key not in seen:
                        seen.add(key)
                        inc_dirs.append(key)
    # Host project include scan (2026-08-12): generated code may depend on
    # the real project's HAL/API headers (e.g. `#include "hal_motor.h"` in
    # <project>/src/hal/include/).  The gen dir never contains those —
    # without this, generated app code always fails verification.
    if project_root is not None:
        proot = Path(project_root)
        if (proot / "src").is_dir():
            for inc in sorted((proot / "src").rglob("include")):
                if inc.is_dir() and any(
                    p.suffix.lower() in c_exts for p in inc.iterdir()
                ):
                    key = str(inc)
                    if key not in seen:
                        seen.add(key)
                        inc_dirs.append(key)

    cmd = [cc, "-fsyntax-only", "-std=c11", "-Wall"]
    for d in inc_dirs:
        cmd += ["-I", d]
    cmd += [str(f) for f in sources]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return _result(
            ok=proc.returncode == 0,
            language=LANGUAGE_C,
            command=" ".join(cmd),
            output=(proc.stderr or proc.stdout).strip(),
            returncode=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return _result(False, LANGUAGE_C, " ".join(cmd),
                       "gcc -fsyntax-only timed out (120s)", -1)


def run_build_command(build_cmd: list[str]) -> dict:
    """Run a project build command (e.g. ``make``) and return the result."""
    cmd_str = " ".join(build_cmd)
    try:
        proc = subprocess.run(build_cmd, capture_output=True, text=True, timeout=300)
        return _result(
            ok=proc.returncode == 0,
            language=LANGUAGE_UNKNOWN,
            command=cmd_str,
            output=(proc.stderr or proc.stdout).strip(),
            returncode=proc.returncode,
        )
    except FileNotFoundError:
        return _result(False, LANGUAGE_UNKNOWN, cmd_str,
                       f"build command not found: {build_cmd[0]}", -1)
    except subprocess.TimeoutExpired:
        return _result(False, LANGUAGE_UNKNOWN, cmd_str,
                       "build command timed out (300s)", -1)


def compile_verify(
    files: list[Path],
    language: Optional[str] = None,
    build_cmd: Optional[list[str]] = None,
    python_cmd: str = "python3",
    cc: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> dict:
    """Verify generated files compile.

    Priority: explicit ``build_cmd`` → language-specific verifier (detected
    from files when ``language`` is None) → unknown result.

    Returns a dict with keys: ok / language / command / output / errors /
    returncode.
    """
    if not files:
        return _result(True, language or LANGUAGE_UNKNOWN, "(no files)",
                       "", 0)
    if build_cmd:
        return run_build_command(build_cmd)
    if language is None:
        language = detect_language(files)
    if language == LANGUAGE_PYTHON:
        return verify_python(files, python_cmd=python_cmd)
    if language == LANGUAGE_C:
        return verify_c(files, cc=cc, project_root=project_root)
    return _result(False, LANGUAGE_UNKNOWN, "(none)",
                   "cannot verify: unknown language for files "
                   f"{[str(f) for f in files]}", -1)
