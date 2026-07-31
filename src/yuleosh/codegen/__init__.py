#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH 编码生成闭环 (D3) — spec/架构 → 代码 → 编译验证 → 自动修复.

Modules:

* :mod:`yuleosh.codegen.engine` — the generate → verify → fix loop
  (:class:`CodegenEngine`, :class:`GeneratedFile`, :class:`CodegenResult`).
* :mod:`yuleosh.codegen.compilers` — local compile verification
  (``py_compile`` / ``gcc -fsyntax-only`` / project build command).
* :mod:`yuleosh.codegen.prompts` — codegen prompt builders with skills
  splicing.
"""

from yuleosh.codegen.engine import (
    CodegenEngine,
    CodegenResult,
    GeneratedFile,
    build_codegen_report,
    default_output_dir,
    parse_generated_files,
)
from yuleosh.codegen.compilers import (
    compile_verify,
    detect_language,
    verify_c,
    verify_python,
)
from yuleosh.codegen.prompts import build_codegen_prompt

__all__ = [
    "CodegenEngine",
    "CodegenResult",
    "GeneratedFile",
    "build_codegen_report",
    "default_output_dir",
    "parse_generated_files",
    "compile_verify",
    "detect_language",
    "verify_c",
    "verify_python",
    "build_codegen_prompt",
]
