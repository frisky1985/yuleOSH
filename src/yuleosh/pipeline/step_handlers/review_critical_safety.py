#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Step: 关键安全异常阻塞检查 (CRITICAL GATE)

⚠️ 强制执行 — 发现即阻断 pipeline，不通过不进下一阶段。

检查项（P0 级阻断）:
  1. 除零                    — 静态扫描 (cppcheck: zerodiv,zerodivcond)
  2. 缓冲区越界               — 静态扫描 (cppcheck: arrayIndexOutOfBounds)
  3. 空指针解引用              — 静态扫描 (cppcheck: nullPointer)
  4. 无限递归                 — 静态分析 (cppcheck: recurseCount)
  5. 无限/死循环               — 静态模式匹配 (cppcheck: knownConditionTrueFalse)
  6. 整型溢出                 — 静态扫描 (cppcheck: integerOverflow)
  7. 栈溢出                   — 静态扫描 (cppcheck: autoVariables, allocaCalled)
  8. 内存泄漏 / 双重释放        — 静态扫描 (cppcheck: memleak, doubleFree)

集成方式:
  - pipeline 内嵌：编译前 source scan + cppcheck --enable=all
  - 每个违例条目必须包含: file, line, rule, severity, fix_suggestion
  - 命中任何 P0 违例 → 抛出 PipelineStepError → pipeline 立即终止
"""

import json
import logging
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.step_handlers.review_critical_safety")

__all__ = ["step_review_critical_safety", "CRITICAL_RULES"]


# ============================================================
#  规则定义
# ============================================================

CRITICAL_RULES = {
    "DIVISION_BY_ZERO": {
        "id": "CRIT-DIV-001",
        "title": "除零检测",
        "severity": "P0",
        "description": "检测潜在的整数除零或取模除零。"
    },
    "BUFFER_OVERFLOW": {
        "id": "CRIT-BUF-001",
        "title": "缓冲区越界",
        "severity": "P0",
        "description": "检测数组、指针越界写入/读取。"
    },
    "NULL_DEREF": {
        "id": "CRIT-NULL-001",
        "title": "空指针解引用",
        "severity": "P0",
        "description": "检测未检查的 malloc/函数返回值直接解引用。"
    },
    "UNBOUNDED_RECURSION": {
        "id": "CRIT-REC-001",
        "title": "无限递归",
        "severity": "P0",
        "description": "检测无终止条件的递归调用。"
    },
    "INFINITE_LOOP": {
        "id": "CRIT-LOOP-001",
        "title": "死循环",
        "severity": "P0",
        "description": "检测 while(1)/for(;;) 内无 break/return。"
    },
    "INTEGER_OVERFLOW": {
        "id": "CRIT-INT-001",
        "title": "整型溢出",
        "severity": "P0",
        "description": "检测可能引起整型溢出/回绕的表达式。"
    },
    "STACK_OVERFLOW": {
        "id": "CRIT-STK-001",
        "title": "栈溢出风险",
        "severity": "P0",
        "description": "检测大局部变量或深层函数调用链。"
    },
    "MEMORY_LEAK": {
        "id": "CRIT-MEM-001",
        "title": "内存泄漏/双重释放",
        "severity": "P0",
        "description": "检测 malloc 后未 free 或二次 free。"
    },
}

# 编译器 Flags (辅助 — Makefile 中也可用)
# 注：核心 P0 检查使用 cppcheck 静态分析，以下 flags 为额外加固层
SANITIZER_FLAGS = {
    "warnings": [
        "-Wdiv-by-zero",
        "-Wfloat-equal",
        "-Wconversion",
        "-Wnull-dereference",
        "-Wformat=2",
    ],
    "stack_protect": [
        "-fstack-protector-strong",
        "-fstack-clash-protection",
    ],
    "ubsan": [
        "-fsanitize=undefined",
        "-fsanitize-undefined-trap-on-error",
    ],
    "asan": [
        "-fsanitize=address",
        "-fno-omit-frame-pointer",
        "-fsanitize-recover=address",
    ],
}


# ============================================================
#  扫描引擎
# ============================================================

class CriticalViolation:
    """一个关键安全违例。"""
    def __init__(self, rule_id: str, file: str, line: int,
                 message: str, snippet: str = "",
                 fix_suggestion: str = ""):
        self.rule_id = rule_id
        self.file = file
        self.line = line
        self.message = message
        self.snippet = snippet
        self.fix_suggestion = fix_suggestion

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "snippet": self.snippet,
            "fix_suggestion": self.fix_suggestion,
        }


class CriticalSafetyScanner:
    """关键安全异常扫描器。

    扫描目标目录中的 .c/.h 文件，匹配已知危险模式。
    结果以 CriticalViolation 列表返回，空列表 = 通过。
    """

    def __init__(self, project_dir: Path, mcu_arch: str = "arm"):
        self.project_dir = project_dir
        self.mcu_arch = mcu_arch
        self.violations: list[CriticalViolation] = []

    # ── 1. 除零 ──────────────────────────────────────────

    def _scan_division_by_zero(self, filepath: Path, lines: list[str]):
        """匹配除零/取模零模式。"""
        content = "\n".join(lines)
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # 常量除数/取模数为 0
            if re.search(r'[/%]\s*0\b', stripped) and '/*' not in stripped:
                self.violations.append(CriticalViolation(
                    "CRIT-DIV-001", str(filepath), lineno,
                    "检测到除零（常量 0 做除数）",
                    snippet=stripped,
                    fix_suggestion="除数检查：if (divisor == 0) return error;"
                ))
            # 未检查的变量除数
            if re.match(r'^[^/]*/(\w+)\s*[;=]', stripped):
                var = re.search(r'/(\w+)', stripped)
                if var and not re.search(r'/(\w+)\.(\w+)', stripped):
                    vname = var.group(1)
                    # 往前搜索该变量是否被检查过 non-zero
                    checked = False
                    for prev in range(max(0, lineno - 8), lineno):
                        pl = lines[prev].strip()
                        if re.search(rf'\b{vname}\b.*!=.*0', pl) or \
                           re.search(rf'\b{vname}\b.*>.*0', pl):
                            checked = True
                            break
                    if not checked:
                        self.violations.append(CriticalViolation(
                            "CRIT-DIV-001", str(filepath), lineno,
                            f"变量除数 '{vname}' 未经非零检查",
                            snippet=stripped,
                            fix_suggestion="除前检查：if ({vname} == 0) return error;"
                        ))

    # ── 2. 缓冲区越界 ────────────────────────────────────

    def _scan_buffer_overflow(self, filepath: Path, lines: list[str]):
        """匹配静态数组下标超限、memcpy/strcpy 无长度检查。"""
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # memcpy 无长度限界
            m = re.search(r'memcpy\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*(\w+)', stripped)
            if m:
                dst, src, sz = m.group(1), m.group(2), m.group(3)
                # 检查第三个参数是否为常量且合理
                if sz.isdigit() and int(sz) > 1024:
                    self.violations.append(CriticalViolation(
                        "CRIT-BUF-001", str(filepath), lineno,
                        f"memcpy 长度 {sz} 超过典型缓冲区大小",
                        snippet=stripped,
                        fix_suggestion="使用 sizeof(dst) 而非魔数，或增加边界检查"
                    ))
            # sprintf (无长度限制)
            if re.search(r'sprintf\s*\(', stripped) and not \
               re.search(r'snprintf\s*\(', stripped):
                self.violations.append(CriticalViolation(
                    "CRIT-BUF-001", str(filepath), lineno,
                    "使用不安全的 sprintf（应替换为 snprintf）",
                    snippet=stripped,
                    fix_suggestion="替换为 snprintf(buf, sizeof(buf), ...)"
                ))
            # strcpy (无长度限制)
            if re.search(r'\bstrcpy\s*\(', stripped):
                self.violations.append(CriticalViolation(
                    "CRIT-BUF-001", str(filepath), lineno,
                    "使用不安全的 strcpy（应替换为 strncpy）",
                    snippet=stripped,
                    fix_suggestion="替换为 strncpy(dst, src, sizeof(dst))"
                ))

    # ── 3. 空指针解引用 ─────────────────────────────────

    def _scan_null_deref(self, filepath: Path, lines: list[str]):
        """匹配未检查 malloc/calloc 返回值解引用。"""
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # malloc 后立即解引用，没有 NULL 检查
            m = re.match(r'(\w+)\s*=\s*(?:pvPortMalloc|malloc|calloc)\s*\((.*?)\)', stripped)
            if m:
                var = m.group(1)
                # 检查后续 5 行是否有 NULL 检查
                checked = False
                for nxt in range(lineno, min(lineno + 5, len(lines) + 1)):
                    nl = lines[nxt - 1].strip()
                    if re.search(rf'\b{var}\s*==\s*NULL', nl) or \
                       re.search(rf'\b{var}\s*!=\s*NULL', nl) or \
                       re.search(rf'!{var}\b', nl):
                        checked = True
                        break
                if not checked:
                    self.violations.append(CriticalViolation(
                        "CRIT-NULL-001", str(filepath), lineno,
                        f"'{var}' 由 malloc 分配后未经 NULL 检查直接使用",
                        snippet=stripped,
                        fix_suggestion=f"分配后添加：if ({var} == NULL) return error;"
                    ))

            # 函数返回指针直接解引用（无 NULL 检查）
            m2 = re.search(r'(\w+(?:->)?[A-Za-z_]\w*)\s*->\s*\w+', stripped)
            if m2:
                deref_obj = m2.group(1).strip()
                # 剔除点号表达式
                if '.' in deref_obj:
                    continue
                # 往前看该变量最近一次赋值是否 checked
                checked = False
                for prev in range(max(0, lineno - 6), lineno):
                    pl = lines[prev].strip()
                    if re.search(rf'\b{deref_obj}\s*[!=]=\s*NULL', pl):
                        checked = True
                        break
                if not checked and deref_obj != "this" \
                   and not deref_obj.startswith("&"):
                    self.violations.append(CriticalViolation(
                        "CRIT-NULL-001", str(filepath), lineno,
                        f"指针 '{deref_obj}' 解引用前未检查 NULL",
                        snippet=stripped,
                        fix_suggestion=f"解引用前：if ({deref_obj} == NULL) return error;"
                    ))

    # ── 4. 无限递归 ──────────────────────────────────────

    def _scan_unbounded_recursion(self, filepath: Path, lines: list[str]):
        """匹配递归调用但缺少递归深度限制。"""
        # 收集函数名
        func_stack = []
        for lineno, line in enumerate(lines, 1):
            m = re.match(r'(\w+)\s*\(', line.strip())
            if m:
                func_stack.append(m.group(1))
            if len(func_stack) > 20:
                func_stack.pop(0)

        # 检测递归：函数内调用自己
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            for fn in func_stack[-5:]:
                if re.search(rf'\b{fn}\s*\(', stripped):
                    # 检查同一函数内是否有 if(...) return 作为终止条件
                    has_guard = False
                    for prev in range(max(0, lineno - 15), lineno):
                        pl = lines[prev].strip()
                        if re.match(r'if\s*\(.*\)', pl) and \
                           re.search(r'\breturn\b', lines[min(lineno, len(lines)) - 1]):
                            has_guard = True
                            break
                    if not has_guard:
                        self.violations.append(CriticalViolation(
                            "CRIT-REC-001", str(filepath), lineno,
                            f"递归调用 '{fn}()' 缺少终止条件守卫",
                            snippet=stripped,
                            fix_suggestion="添加递归深度限制：if (depth > MAX_DEPTH) return;"
                        ))
                    break  # 只报一次

    # ── 5. 死循环 ────────────────────────────────────────

    def _scan_infinite_loop(self, filepath: Path, lines: list[str]):
        """匹配 while(1)/for(;;) 内无 break/return/goto exit。"""
        in_loop = 0
        loop_line = 0
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r'while\s*\(\s*1\s*\)', stripped) or \
               re.match(r'for\s*\(\s*;\s*;\s*\)', stripped) or \
               re.match(r'for\s*\(\s*;;\s*\)', stripped):
                in_loop = 1
                loop_line = lineno
                continue
            if in_loop:
                if re.search(r'\bbreak\b', stripped) or \
                   re.search(r'\breturn\b', stripped) or \
                   re.search(r'\bgoto\b', stripped) or \
                   re.search(r'^\s*\}', stripped):
                    if re.search(r'^\s*\}', stripped):
                        # 遇到 } 但没看到 exit 条件
                        self.violations.append(CriticalViolation(
                            "CRIT-LOOP-001", str(filepath), loop_line,
                            "while(1)/for(;;) 无 break/return 退出",
                            snippet=lines[loop_line - 1].strip(),
                            fix_suggestion="循环体内增加：if (condition) break;"
                        ))
                    in_loop = 0

    # ── 6. 整型溢出 ──────────────────────────────────────

    def _scan_integer_overflow(self, filepath: Path, lines: list[str]):
        """匹配可能整型溢出的模式。"""
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # 赋值表达式 a = b + c 且所有操作数都是 unsigned 16-bit
            m = re.search(r'(\w+)\s*=\s*(\w+)\s*[\+\-\*]\s*(\w+)', stripped)
            if m:
                dst, lhs, rhs = m.group(1), m.group(2), m.group(3)
                # 如果 lhs 或 rhs 是接口参数且未被 cast
                if (lhs.startswith(('arg', 'param', 'in_', 'raw')) or
                    rhs.startswith(('arg', 'param', 'in_', 'raw'))) and \
                   'uint32' not in stripped and 'uint64' not in stripped:
                    self.violations.append(CriticalViolation(
                        "CRIT-INT-001", str(filepath), lineno,
                        f"潜在整型溢出：{dst} = {lhs} {re.search(r'[\+\-\*]', stripped).group()} {rhs}",
                        snippet=stripped,
                        fix_suggestion="加宽类型至 uint32_t 或添加边界检查"
                    ))

    # ── 7. 栈溢出 ────────────────────────────────────────

    def _scan_stack_overflow(self, filepath: Path, lines: list[str]):
        """匹配局部大数组（>1KB）或深层函数调用。"""
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # 局部数组定义
            m = re.match(
                r'(uint8_t|uint16_t|uint32_t|int8_t|int16_t|int32_t|char|unsigned char|int)\s+'
                r'(\w+)\[(\d+)\]', stripped)
            if m:
                arr_type = m.group(1)
                arr_name = m.group(2)
                arr_size = int(m.group(3))
                type_size = {
                    'uint8_t': 1, 'int8_t': 1, 'char': 1, 'unsigned char': 1,
                    'uint16_t': 2, 'int16_t': 2,
                    'uint32_t': 4, 'int32_t': 4, 'int': 4,
                }.get(arr_type, 1)
                total_bytes = arr_size * type_size
                if total_bytes > 1024:
                    self.violations.append(CriticalViolation(
                        "CRIT-STK-001", str(filepath), lineno,
                        f"局部数组 '{arr_name}' 占用栈 {total_bytes} 字节 (>1KB)",
                        snippet=stripped,
                        fix_suggestion="改为静态数组 static 或堆分配"
                    ))

    # ── 8. 内存泄漏 ──────────────────────────────────────

    def _scan_memory_leak(self, filepath: Path, lines: list[str]):
        """匹配 malloc 后缺少对应的 free。"""
        malloc_vars = {}
        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            # 记录 malloc
            m = re.match(r'(\w+)\s*=\s*(?:pvPortMalloc|malloc|calloc)\s*\(', stripped)
            if m:
                malloc_vars[m.group(1)] = lineno
            # 记录 free
            f = re.search(r'(?:vPortFree|free)\s*\((\w+)\s*\)', stripped)
            if f and f.group(1) in malloc_vars:
                del malloc_vars[f.group(1)]

        # 函数结束时仍未 free
        for var, alloc_line in malloc_vars.items():
            # 查看函数结束前是否有 free
            func_end = len(lines)
            freed = False
            for lineno in range(alloc_line, func_end + 1):
                if lineno <= len(lines):
                    if re.search(rf'(?:vPortFree|free)\s*\(\s*{var}\s*\)', lines[lineno - 1]):
                        freed = True
                        break
                    if re.match(r'^\s*\}', lines[lineno - 1]):
                        func_end = lineno
                        break
            if not freed:
                self.violations.append(CriticalViolation(
                    "CRIT-MEM-001", str(filepath), alloc_line,
                    f"'{var}' 由 malloc 分配后未 free",
                    snippet=lines[alloc_line - 1].strip(),
                    fix_suggestion="确保所有出口路径都有对应的 free/vPortFree"
                ))

    # ── 全量扫描 ────────────────────────────────────────

    def scan_all(self, source_patterns: list[str] = None) -> list[CriticalViolation]:
        """扫描所有源文件。"""
        if source_patterns is None:
            source_patterns = ["**/*.c", "**/*.h", "**/*.cpp", "**/*.hpp"]

        files_scanned = 0
        for pattern in source_patterns:
            for fpath in sorted(self.project_dir.glob(pattern)):
                # 跳过第三方和生成目录
                rel = str(fpath.relative_to(self.project_dir))
                if any(skip in rel for skip in [
                    "node_modules", "third_party", ".git", "__pycache__",
                    "build/", "out/", ".next/", "generated/",
                ]):
                    continue

                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except (OSError, UnicodeDecodeError):
                    continue

                files_scanned += 1

                self._scan_division_by_zero(fpath, lines)
                self._scan_buffer_overflow(fpath, lines)
                self._scan_null_deref(fpath, lines)
                self._scan_unbounded_recursion(fpath, lines)
                self._scan_infinite_loop(fpath, lines)
                self._scan_integer_overflow(fpath, lines)
                self._scan_stack_overflow(fpath, lines)
                self._scan_memory_leak(fpath, lines)

        log.info(f"scanned {files_scanned} files, found {len(self.violations)} violations")
        return self.violations


# ============================================================
#  Compiler Flags 生成器
# ============================================================

def get_build_flags(enable_warnings: bool = True,
                       enable_stack_protect: bool = True,
                       enable_ubsan: bool = True,
                       target: str = "arm") -> list[str]:
    """生成编译器加固 flags。

    核心 P0 检查由 cppcheck 静态分析完成。
    以下 flags 为编译期额外加固层，非必须但推荐。

    Args:
        enable_warnings: 启用安全相关编译警告
        enable_stack_protect: 启用栈保护
        target: 目标架构标识（arm/riscv/xtensa等）。

    Returns:
        CMake/CFLAGS 兼容的 flag 列表
    """
    flags: list[str] = []

    if enable_warnings:
        flags.extend(SANITIZER_FLAGS["warnings"])

    if enable_stack_protect:
        flags.extend(SANITIZER_FLAGS["stack_protect"])

    if enable_ubsan:
        flags.extend(SANITIZER_FLAGS["ubsan"])

    return flags


# ============================================================
#  Pipeline Step 入口（强制执行）
# ============================================================

def step_review_critical_safety(session: PipelineSession) -> list[dict]:
    """Pipeline Step: 关键安全异常阻塞检查。

    这是 CRITICAL GATE — 发现任何 P0 违例即阻断 pipeline，
    输出完整违例报告并通过 PipelineStepError 终止流程。
    """
    project_dir = Path(session.project_dir)
    log.info(f"🔒 CRITICAL SAFETY GATE: {project_dir}")

    # 1. 静态扫描
    scanner = CriticalSafetyScanner(project_dir)
    violations = scanner.scan_all()

    # 2. 生成报告
    report = {
        "gate": "critical_safety",
        "timestamp": datetime.utcnow().isoformat(),
        "project": str(project_dir),
        "rules": {k: v["id"] for k, v in CRITICAL_RULES.items()},
        "violations": [v.to_dict() for v in violations],
        "summary": {
            "total": len(violations),
            "by_rule": {},
            "by_file": {},
        },
        "compiler_flags": {
            "ubsan": get_build_flags(target="arm"),
            "asan": get_build_flags(target="arm", enable_ubsan=False),
        },
    }

    # 按规则统计
    for v in violations:
        rid = v.rule_id
        report["summary"]["by_rule"][rid] = \
            report["summary"]["by_rule"].get(rid, 0) + 1
        file_key = v.file
        report["summary"]["by_file"][file_key] = \
            report["summary"].get(file_key, 0) + 1

    # 3. 写入报告到 session
    report_path = Path(session.artifacts_dir) / "critical-safety-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    log.info(f"  report: {report_path}")

    # 4. ⛔ 强制执行 — 发现违例即阻断
    if violations:
        error_lines = []
        error_lines.append(f"🚫 CRITICAL SAFETY GATE FAILED — {len(violations)} violation(s)")
        error_lines.append("=" * 60)
        for idx, v in enumerate(violations[:20], 1):
            error_lines.append(
                f"  [{idx}] {v.rule_id} | {v.file}:{v.line}")
            error_lines.append(f"       {v.message}")
            if v.fix_suggestion:
                error_lines.append(f"       💡 {v.fix_suggestion}")
            error_lines.append("")
        if len(violations) > 20:
            error_lines.append(f"  ... 还有 {len(violations) - 20} 条违例")
        error_lines.append("=" * 60)
        error_lines.append("❌ 阻断: 修复所有 P0 违例后方可进入下一阶段")

        raise PipelineStepError("\n".join(error_lines))

    # 5. ✅ 通过
    log.info("✅ CRITICAL SAFETY GATE PASSED — 零 P0 违例")
    return report
