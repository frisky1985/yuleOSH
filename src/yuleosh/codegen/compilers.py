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
    """Syntax-check Python files with ``python -m py_compile``."""
    cmd = [python_cmd, "-m", "py_compile", *[str(f) for f in files]]
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


def verify_c(files: list[Path], cc: Optional[str] = None) -> dict:
    """Syntax-check C/C++ files with ``gcc -fsyntax-only`` (or ``cc``)."""
    cc = cc or shutil.which("gcc") or shutil.which("cc")
    if not cc:
        return _result(False, LANGUAGE_C, "gcc -fsyntax-only",
                       "no C compiler (gcc/cc) found on PATH", -1)
    cmd = [cc, "-fsyntax-only", "-std=c11", "-Wall", *[str(f) for f in files]]
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
        return verify_c(files, cc=cc)
    return _result(False, LANGUAGE_UNKNOWN, "(none)",
                   "cannot verify: unknown language for files "
                   f"{[str(f) for f in files]}", -1)
