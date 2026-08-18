# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""SWC (软件编程规范 v0.3) 代码风格扫描器 — C 语言.

读取项目根 ``swc-c-rules.yaml``（规范规则集）并对 C 源文件执行可机器
检查的规则子集（``check_method: code_style``）。

诚实原则（第一准则）:
- 只实现高可靠、可判定的检查; 误报率高的规则标 ``auto_checkable: false``
  交给 LLM 审查/人工（check_method: manual_review）。
- 检查报告必须反映真实扫描结果, 不虚构通过。

输出: ``.yuleosh/reports/code-style-report.json``
用法:
    python -m yuleosh.ci.stages.code_style [--project-dir <path>] [--json]
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("ci.code_style")

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "swc-c-rules.yaml"
REPORT_RELPATH = ".yuleosh/reports/code-style-report.json"

# 扫描排除目录（与平台其它扫描器对齐 — c-unit-test _iter_sources 排除集）
_EXCLUDED_PARTS = {
    ".git", ".osh", ".yuleosh", ".pytest_cache", "__pycache__",
    "artifacts", "build", "cmake-build", "cmake-build-coverage",
    "node_modules", "third_party", "third-party", "vendor", "external",
    "tests", "test", "examples", "demos",
}

_C_EXTENSIONS = {".c", ".h", ".cc", ".cpp", ".hpp", ".inc"}

# 可检查规则 → 检查器名映射（rules YAML check_method=code_style 且 auto_checkable）
CHECKER_BY_RULE = {
    "1-1": "indent_4spaces",
    "1-3": "line_length_80",
    "1-6": "one_statement_per_line",
    "1-7": "control_braces",
    "1-8": "no_tab",
    "1-10": "brace_own_line",
    "2-1": "comment_ratio_20",
    "3-4": "no_single_char_var",
    "3-6": "type_prefix",
    "3-7": "macro_upper",
    "7-1": "macro_parens",
    "7-2": "macro_multi_stmt_braces",
    "7-3": "macro_param_no_mutation",
    "11-18": "no_goto",
    "11-19": "const_left_compare",
}


@dataclass
class Violation:
    rule_id: str
    file: str
    line: int
    column: int
    severity: str
    message: str
    checker: str = ""

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "checker": self.checker,
        }


@dataclass
class ScanResult:
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    comment_ratio: dict = field(default_factory=dict)

    def summary(self) -> dict:
        from collections import Counter
        by_rule = Counter(v.rule_id for v in self.violations)
        by_sev = Counter(v.severity for v in self.violations)
        return {
            "files_scanned": self.files_scanned,
            "violations_total": len(self.violations),
            "violations_by_rule": dict(by_rule),
            "violations_by_severity": dict(by_sev),
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _strip_comments_and_strings(line: str) -> str:
    """粗略剥离字符串字面量与行注释, 用于代码模式匹配.

    字符串字面量整体替换为单个空格（长度压缩, 便于行宽检查反映真实代码长度）;
    行注释截断。不做块注释完整解析（那是逐行扫描的职责）。
    """
    out = []
    i = 0
    n = len(line)
    in_str = False
    str_ch = ""
    while i < n:
        ch = line[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == str_ch:
                in_str = False
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_ch = ch
            out.append(" ")
            i += 1
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            break  # 行注释截断
        out.append(ch)
        i += 1
    return "".join(out)


def _is_excluded_dir(name: str) -> bool:
    """判断目录是否应排除（全名匹配 + 前缀匹配 cmake-build*/build*）。"""
    if name in _EXCLUDED_PARTS:
        return True
    # cmake-build*, build*, cmake 都是构建产物目录
    if name.startswith(("cmake-build", "build", ".git")):
        return True
    return name == "cmake"


def _iter_source_files(project_dir: Path) -> Iterable[Path]:
    """遍历项目 C 源文件, 排除构建产物/第三方目录（平台统一排除集）。"""
    for root, dirs, files in os.walk(project_dir):
        # 原地裁剪目录列表, 避免进入排除目录
        dirs[:] = [d for d in dirs if not _is_excluded_dir(d)]
        for fname in files:
            if Path(fname).suffix in _C_EXTENSIONS:
                yield Path(root) / fname


def _load_rules(rules_path: Path | None = None) -> dict:
    import yaml
    path = rules_path or DEFAULT_RULES_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001 — 规则文件损坏不应让扫描器崩溃
        log.warning("Failed to load rules file %s: %s", path, exc)
        return {}
    return data.get("rules", {})


# ---------------------------------------------------------------------------
# 检查器实现
# ---------------------------------------------------------------------------

def _check_indent_4spaces(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-1: 程序块缩进为 4 个空格（倍数）。"""
    out = []
    # 统计非空、非注释行的前导空格, 要求是 4 的倍数（允许 0）
    for lineno, raw in stripped_lines:
        if not raw.strip():
            continue
        if raw.lstrip().startswith(("#", "//", "/*", "*", "*/")):
            continue
        lead = len(raw) - len(raw.lstrip())
        if lead % 4 != 0:
            out.append(Violation(
                rule_id="1-1", file=rel, line=lineno, column=lead + 1,
                severity="warning",
                message=f"缩进必须为 4 的倍数 (当前 {lead} 空格)",
                checker="indent_4spaces",
            ))
    return out[:50]  # 防止刷屏


def _check_line_length_80(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-3: 较长语句(>80 字符)应分行。排除纯注释行与长字符串字面量行。"""
    out = []
    for lineno, raw in raw_lines:
        if len(raw) <= 80:
            continue
        stripped = raw.strip()
        # 排除注释行（// 或 /* ... */ 整行）与字符串表（如日志/消息数组）
        if stripped.startswith(("//", "/*", "*", "#")):
            continue
        code = _strip_comments_and_strings(raw)
        # 若去掉字符串后仍超 80, 说明是真实代码过长; 否则可能是长字符串字面量
        if len(code) > 80:
            out.append(Violation(
                rule_id="1-3", file=rel, line=lineno, column=81,
                severity="warning",
                message=f"语句长度 {len(raw)} 字符 > 80, 应在低优先级操作符处分行",
                checker="line_length_80",
            ))
    return out[:100]


def _check_one_statement_per_line(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-6: 一行只写一条语句。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        if not code:
            continue
        # 排除: 控制语句头（for/while 括号内分号合法）、宏定义、声明
        if code.startswith(("#", "for", "while", "switch", "typedef", "struct", "union", "enum")):
            continue
        # 计算代码中分号数量
        semis = code.count(";")
        if semis > 1:
            out.append(Violation(
                rule_id="1-6", file=rel, line=lineno, column=1,
                severity="warning",
                message=f"一行包含 {semis} 条语句, 应一行只写一条",
                checker="one_statement_per_line",
            ))
    return out[:80]


def _check_control_braces(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-7: if/for/do/while 执行语句无论多少都要加 {}。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        # 匹配 if (...) 语句体在同一行且无 {
        m = re.match(r"^(if|for|while)\s*\(.*\)\s*([^;{][^;]*);\s*$", code)
        if m:
            out.append(Violation(
                rule_id="1-7", file=rel, line=lineno, column=1,
                severity="warning",
                message=f"{m.group(1)} 的执行语句必须加大括号 {{}}",
                checker="control_braces",
            ))
        # 匹配 if/for/while 头与 { 同行（规则1-10 也查, 但这里查无括号体）
    return out[:50]


def _check_no_tab(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-8: 对齐只使用空格, 不使用 TAB。"""
    out = []
    for lineno, raw in raw_lines:
        if "\t" in raw:
            out.append(Violation(
                rule_id="1-8", file=rel, line=lineno,
                column=raw.index("\t") + 1,
                severity="warning",
                message="禁止使用 TAB 键对齐, 使用空格",
                checker="no_tab",
            ))
    return out[:80]


def _check_brace_own_line(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 1-10: 程序块分界符 { } 各独占一行, 与引用语句左对齐。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        # { 前有代码（非 } 结尾的控制头）→ 违反独占一行
        # 排除 struct 初始化/数组初始化等场景
        if "{" in code and not code.endswith("{") and re.match(r"^(if|for|while|switch|do|else|case|default)\b.*\{", code):
            out.append(Violation(
                rule_id="1-10", file=rel, line=lineno, column=1,
                severity="warning",
                message="大括号 { 应独占一行（规则 1-10）",
                checker="brace_own_line",
            ))
    return out[:80]


def _comment_ratio(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> dict | None:
    """规则 2-1: 有效注释量 >= 20%（按注释字符/总字符估算）。"""
    total_chars = 0
    comment_chars = 0
    in_block = False
    for lineno, raw in raw_lines:
        total_chars += len(raw)
        stripped = raw.strip()
        if in_block:
            comment_chars += len(raw)
            if "*/" in raw:
                in_block = False
            continue
        if stripped.startswith("/*"):
            comment_chars += len(raw)
            if "*/" not in raw:
                in_block = True
            continue
        if stripped.startswith(("//", "*")):
            comment_chars += len(raw)
            continue
        # 行内注释（/* ... */ 或 // ...）
        if "/*" in raw:
            comment_chars += len(raw)
            continue
        if "//" in raw:
            comment_chars += len(raw.partition("//")[2])
    if total_chars == 0:
        return None
    ratio = comment_chars / total_chars
    return {"file": rel, "comment_chars": comment_chars, "total_chars": total_chars, "ratio": round(ratio, 4)}


def _check_comment_ratio_20(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 2-1: 源程序有效注释量必须在 20% 以上。"""
    info = _comment_ratio(path, rel, raw_lines)
    if not info:
        return []
    if info["ratio"] < 0.20:
        return [Violation(
            rule_id="2-1", file=rel, line=1, column=1,
            severity="warning",
            message=f"注释量 {info['ratio']*100:.1f}% < 20% (注释 {info['comment_chars']}/{info['total_chars']} 字符)",
            checker="comment_ratio_20",
        )]
    return []


def _check_no_single_char_var(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 3-4: 变量命名禁止取单个字符（如 i、j、k...）。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        if not code or code.startswith(("#", "//")):
            continue
        # 简单类型声明: int a; uint8_t b; char c; float f; (不含初始化)
        m = re.match(r"^(?:unsigned\s+|signed\s+)?(?:int|char|float|double|long|short|BOOL|uint8_t|uint16_t|uint32_t|uint64_t|int8_t|int16_t|int32_t|int64_t)\s+([a-zA-Z_]\w*)\s*(?:=|;)", code)
        if m:
            name = m.group(1)
            if len(name) == 1:
                out.append(Violation(
                    rule_id="3-4", file=rel, line=lineno, column=code.index(name) + 1,
                    severity="warning",
                    message=f"禁止单字符变量名 '{name}', 应使用有意义名称",
                    checker="no_single_char_var",
                ))
    return out[:50]


# 类型前缀表（规则 3-6）
_TYPE_PREFIXES = [
    ("uc", {"uint8_t"}), ("u8", {"uint8_t"}),
    ("sc", {"int8_t"}), ("i8", {"int8_t"}),
    ("uw", {"uint16_t"}), ("u16", {"uint16_t"}),
    ("sw", {"int16_t"}), ("i16", {"int16_t"}),
    ("udw", {"uint32_t"}), ("u32", {"uint32_t"}),
    ("dw", {"int32_t"}), ("i32", {"int32_t"}),
    ("ul", {"uint64_t"}), ("u64", {"uint64_t"}),
    ("l", {"int64_t", "long", "int64"}), ("i64", {"int64_t"}),
    ("b", {"BOOL", "bool"}),
    ("f", {"float", "FLOAT"}),
]


def _check_type_prefix(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 3-6: 变量命名需要加数据类型前缀。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        if not code or code.startswith(("#", "//")):
            continue
        for prefix, types in _TYPE_PREFIXES:
            matched_type = None
            m = None
            for t in types:
                m = re.match(rf"^(?:{t})\s+([a-zA-Z_]\w*)\s*(?:=|;)", code)
                if m:
                    matched_type = t
                    break
            if matched_type is None or m is None:
                continue
            name = m.group(1)
            if not name.startswith(prefix):
                out.append(Violation(
                    rule_id="3-6", file=rel, line=lineno, column=code.index(name) + 1,
                    severity="warning",
                    message=f"变量 '{name}' 类型 {matched_type} 应加前缀 '{prefix}' (规则 3-6)",
                    checker="type_prefix",
                ))
            break  # 命中任一类型即停止, 避免同变量重复报
    return out[:80]


def _check_macro_upper(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 3-7: 宏命名全部大写, 单词间下划线。"""
    out = []
    for lineno, raw in stripped_lines:
        code = raw.strip()
        m = re.match(r"^#define\s+([a-zA-Z_]\w*)", code)
        if m:
            name = m.group(1)
            if not re.match(r"^[A-Z][A-Z0-9_]*$", name):
                out.append(Violation(
                    rule_id="3-7", file=rel, line=lineno, column=code.index(name) + 1,
                    severity="warning",
                    message=f"宏 '{name}' 应全部大写, 单词间下划线 (规则 3-7)",
                    checker="macro_upper",
                ))
    return out[:80]


def _check_macro_parens(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 7-1: 宏定义表达式要使用完备括号（函数宏）。"""
    out = []
    for lineno, raw in raw_lines:
        code = raw.strip()
        m = re.match(r"^#define\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s+(.+)$", code)
        if not m:
            continue
        name, _params, body = m.group(1), m.group(2), m.group(3)
        # 跳过 do{}while(0) / { } 块
        if body.startswith(("{", "do")):
            continue
        # 有表达式但整体未包裹括号 → 风险（含算术/比较操作符就要求整体括号）
        if not body.startswith("(") and re.search(r"[+\-*/%<>&|^!~=]", body):
            out.append(Violation(
                rule_id="7-1", file=rel, line=lineno, column=1,
                severity="warning",
                message=f"宏 '{name}' 表达式应使用完备括号, 如 ((a) * (b)) (规则 7-1)",
                    checker="macro_parens",
                ))
    return out[:50]


def _check_macro_multi_stmt_braces(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 7-2: 宏定义多条表达式应放在大括号中。"""
    out = []
    i = 0
    while i < len(raw_lines):
        lineno, raw = raw_lines[i]
        code = raw.strip()
        m = re.match(r"^#define\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\\?$", code)
        if m:
            # 收集宏体（可能跨行）
            body_lines = []
            j = i
            while j < len(raw_lines):
                _l2, r2 = raw_lines[j]
                body_lines.append(r2)
                if "\\" not in r2 or j > i + 1 and not r2.rstrip().endswith("\\"):
                    break
                j += 1
            # 判断体是否多语句且无大括号
            body = " ".join(x.strip().lstrip("\\") for x in body_lines[1:])
            if body.count(";") >= 1 and not body.strip().startswith(("{", "do")):
                out.append(Violation(
                    rule_id="7-2", file=rel, line=lineno, column=1,
                    severity="warning",
                    message=f"宏 '{m.group(1)}' 含多条表达式, 应使用大括号包裹 (规则 7-2)",
                    checker="macro_multi_stmt_braces",
                ))
            i = j + 1
            continue
        i += 1
    return out[:50]


def _check_macro_param_no_mutation(path: Path, rel: str, raw_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 7-3: 使用宏时不允许参数发生变化（++/-- 传入宏）。"""
    out = []
    for lineno, raw in raw_lines:
        code = _strip_comments_and_strings(raw).strip()
        # 函数宏调用: NAME(arg); 且参数含 ++ / --（允许行首有赋值, 如 b = SQUARE(a++);）
        m = re.search(r"([A-Z][A-Z0-9_]*)\s*\(([^()]*)\)\s*;", code)
        if m:
            args = m.group(2)
            if re.search(r"\+\+|--", args):
                out.append(Violation(
                    rule_id="7-3", file=rel, line=lineno, column=1,
                    severity="warning",
                    message=f"宏 '{m.group(1)}' 参数含 ++/--, 宏参数不允许变化 (规则 7-3)",
                    checker="macro_param_no_mutation",
                ))
    return out[:50]


def _check_no_goto(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 11-18: 不要滥用 goto。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        if re.match(r"^goto\s+\w+\s*;", code):
            out.append(Violation(
                rule_id="11-18", file=rel, line=lineno, column=1,
                severity="warning",
                message="不要滥用 goto 语句 (规则 11-18)",
                checker="no_goto",
            ))
    return out


def _check_const_left_compare(path: Path, rel: str, stripped_lines: list[tuple[int, str]]) -> list[Violation]:
    """规则 11-19: 变量与常量比较时, 常量写在左边（如 if (5 == x)）。"""
    out = []
    for lineno, raw in stripped_lines:
        code = _strip_comments_and_strings(raw).strip()
        # 匹配 x == CONST / x != CONST 形式（x 是标识符, CONST 是字面量）
        m = re.search(r"\b([a-zA-Z_]\w*)\s*(==|!=)\s*([0-9]+(?:\.[0-9]+)?|'[^']*')", code)
        if m:
            out.append(Violation(
                rule_id="11-19", file=rel, line=lineno,
                column=code.index(m.group(0)) + 1,
                severity="info",
                message=f"常量应写在左边: {m.group(2)} 比较建议写成 {m.group(3)} {m.group(2)} {m.group(1)} (规则 11-19)",
                checker="const_left_compare",
            ))
    return out[:50]


_CHECKERS = {
    "indent_4spaces": _check_indent_4spaces,
    "line_length_80": _check_line_length_80,
    "one_statement_per_line": _check_one_statement_per_line,
    "control_braces": _check_control_braces,
    "no_tab": _check_no_tab,
    "brace_own_line": _check_brace_own_line,
    "comment_ratio_20": _check_comment_ratio_20,
    "no_single_char_var": _check_no_single_char_var,
    "type_prefix": _check_type_prefix,
    "macro_upper": _check_macro_upper,
    "macro_parens": _check_macro_parens,
    "macro_multi_stmt_braces": _check_macro_multi_stmt_braces,
    "macro_param_no_mutation": _check_macro_param_no_mutation,
    "no_goto": _check_no_goto,
    "const_left_compare": _check_const_left_compare,
}


# ---------------------------------------------------------------------------
# 扫描入口
# ---------------------------------------------------------------------------

def scan_file(path: Path, rules: dict | None = None, project_root: Path | None = None) -> ScanResult:
    """扫描单个 C 源文件, 返回违规列表。"""
    rules = rules if rules is not None else _load_rules()
    result = ScanResult()
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return result

    rel = str(path)
    # 优先相对项目根, 其次相对 cwd
    base = project_root or Path.cwd()
    try:
        rel = str(path.relative_to(base))
    except ValueError:
        try:
            rel = str(path.relative_to(Path.cwd()))
        except ValueError:
            pass

    stripped_lines = [(i + 1, ln) for i, ln in enumerate(raw_lines)]
    raw_tuples = [(i + 1, ln) for i, ln in enumerate(raw_lines)]

    # 规则启用: 只跑 rules 中 check_method=code_style 且 auto_checkable 的
    enabled_rules = set()
    for rid, rdef in rules.items():
        if rdef.get("check_method") == "code_style" and rdef.get("auto_checkable"):
            short = rid.replace("SWC-C-", "")
            if short in CHECKER_BY_RULE:
                enabled_rules.add(short)

    for rid in sorted(enabled_rules, key=lambda x: int(x.split("-")[0])):
        checker_name = CHECKER_BY_RULE[rid]
        fn = _CHECKERS[checker_name]
        try:
            vios = fn(path, rel, raw_tuples if checker_name in ("line_length_80", "no_tab", "macro_parens", "macro_multi_stmt_braces", "macro_param_no_mutation") else stripped_lines)
            for v in vios:
                v.checker = checker_name
                result.violations.append(v)
        except Exception as exc:  # noqa: BLE001 — 单个检查器失败不影响整体
            log.warning("Checker %s failed on %s: %s", checker_name, rel, exc)

    # 注释量统计（独立于规则启用, 用于报告）
    ratio = _comment_ratio(path, rel, raw_tuples)
    if ratio:
        result.comment_ratio[rel] = ratio
    result.files_scanned = 1
    return result


def scan_project(project_dir: str | Path, rules: dict | None = None) -> ScanResult:
    """扫描整个项目的 C 源文件。"""
    root = Path(project_dir)
    result = ScanResult()
    for path in _iter_source_files(root):
        r = scan_file(path, rules, project_root=root)
        result.violations.extend(r.violations)
        result.files_scanned += r.files_scanned
        result.comment_ratio.update(r.comment_ratio)
    return result


def write_report(project_dir: str | Path, result: ScanResult, save: bool = True) -> dict:
    """将扫描结果写入 .yuleosh/reports/code-style-report.json。"""
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "ruleset": "SWC-C (软件编程规范 v0.3)",
        "summary": result.summary(),
        "comment_ratio": result.comment_ratio,
        "violations": [v.to_dict() for v in result.violations],
    }
    if save:
        root = Path(project_dir)
        out = root / REPORT_RELPATH
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def run_code_style(project_dir: str, ci=None, target_files: list[str] | None = None,
                   block_on_violations: bool | None = None) -> bool:
    """CI stage 入口 — 运行 SWC 代码风格扫描。

    Returns
    -------
    bool
        True = stage 通过（违规可作为 warning 记录）。
        仅在显式配置 ``code_style.block_on: true`` 时违规才阻断。
    """
    root = Path(project_dir)
    # 项目根有 swc-c-rules.yaml 才启用检查; 没有 → skip (不破坏 pipeline)
    # 平台约定: ci.stages 只在 failure/error 时记录, skip/warning 不记录
    project_rules_path = root / "swc-c-rules.yaml"
    if not project_rules_path.exists():
        msg = "项目根缺少 swc-c-rules.yaml — code-style stage 跳过 (复制平台默认规则到项目根可启用)"
        print(f"  ⚠️  {msg}")
        return True
    rules = _load_rules(project_rules_path)
    if not rules:
        msg = "swc-c-rules.yaml 为空 — code-style stage 跳过"
        print(f"  ⚠️  {msg}")
        return True

    result = scan_project(root, rules)
    write_report(root, result)

    total = len(result.violations)
    print(f"  🔍 SWC code-style: {result.files_scanned} 文件, {total} 违规")
    from collections import Counter
    by_rule = Counter(v.rule_id for v in result.violations)
    for rid, n in by_rule.most_common(8):
        print(f"     SWC-C-{rid}: {n}")

    # 配置: block_on 默认 False — 不破坏现有 pipeline
    if block_on_violations is None:
        block_on_violations = _config_block_on(project_dir)

    if total == 0:
        print("     ✅ 0 violations")
        return True

    if block_on_violations:
        if ci is not None:
            ci.add_stage("code-style", "failed", f"{total} violations (block_on)")
            ci.errors.append(f"code-style: {total} violations")
        return False
    else:
        # warning 不记录 stages（平台约定: 仅 failure/error 记录）, 只打印
        print(f"     ⚠️  {total} violations (non-blocking — 配置 code_style.block_on: true 可阻断)")
        return True


def _config_block_on(project_dir: str) -> bool:
    """从 .yuleosh/ci-config.yaml 读取 code_style.block_on (默认 False)。"""
    import yaml
    cfg_path = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return bool(cfg.get("code_style", {}).get("block_on", False))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# LLM 审查规则文本 (check_method=manual_review 的语义规则)
# ---------------------------------------------------------------------------

def format_style_rules_for_review(rules_path: Path | None = None) -> str:
    """从 swc-c-rules.yaml 提取 manual_review 语义规则, 生成 LLM 审查注入文本.

    返回空字符串 = 规则文件不存在/无可注入规则（调用方不注入, 保持原行为）。
    """
    rules = _load_rules(rules_path)
    if not rules:
        return ""
    lines = []
    for key in sorted(rules.keys()):
        rdef = rules[key]
        if rdef.get("check_method") == "manual_review":
            kind = rdef.get("kind", "规则")
            sev = rdef.get("severity", "S2")
            title = rdef.get("title", "").strip()
            rid = key.replace("SWC-C-", "")
            lines.append(f"- [{rid}] ({kind}/{sev}) {title}")
    if not lines:
        return ""
    header = (
        "以下为项目启用的《软件编程规范 v0.3》语义规则（无法静态机器检查, 需人工/LLM 判断）:\n"
        "审查时逐条对照源代码, 违规项记入 findings (category=style)。\n"
    )
    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="SWC 软件编程规范代码风格扫描 (C)")
    parser.add_argument("--project-dir", default=os.environ.get("OSH_HOME", os.getcwd()),
                        help="Project root directory")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--no-save", action="store_true", help="Do not write report file")
    parser.add_argument("--block", action="store_true", help="Exit non-zero on violations")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    result = scan_project(args.project_dir)
    report = write_report(args.project_dir, result, save=not args.no_save)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"SWC code-style scan: {result.files_scanned} files, {len(result.violations)} violations")
        for v in result.violations[:30]:
            print(f"  [{v.rule_id}] {v.file}:{v.line} {v.message}")
        if len(result.violations) > 30:
            print(f"  ... and {len(result.violations) - 30} more")

    if args.block and result.violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
