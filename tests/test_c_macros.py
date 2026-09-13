"""B1-07 宏处理策略测试。

覆盖：对象宏/函数式宏/flag 宏提取；stddef/stdint 白名单跳过；置信度初值
（函数式/flag=0.35，带值对象=0.9）；``#ifdef``/``#ifndef``/``#if``/``#elif``/
``#else``/``#endif`` 分支全解析与「编译激活条件」标注；嵌套条件；分支内宏；
文件 I/O 与容错（坏输入/缺文件永不抛）。
"""

import os
import tempfile

import pytest

from yuleosh.knowledge_graph.c_parser import extract_macros, extract_macros_file

SRC = b"""
#include <stdio.h>
#include <stdint.h>
#define PI 3.14
#define BUF_SIZE 256
#define EMPTY
#define MAX(a,b) ((a)>(b)?(a):(b))
#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
#define INT8_MAX 127
#define UINT32_MAX 4294967295U
#ifdef FOO
int foo(void) { return 1; }
#define INSIDE 1
#else
int foo(void) { return 2; }
#endif
#ifndef BAR
#define BAR 5
#endif
#if defined(Z) && X > 0
void g(void){}
#elif W
void g2(void){}
#else
void g3(void){}
#endif
#if 0
void dead(void){}
#endif
"""


def _mmap(r):
    return {m["name"]: m for m in r["macros"]}


def test_parse_ok_and_counts():
    r = extract_macros(SRC, "f.c")
    assert r["parse_ok"] is True
    # 记录实体：PI/BUF_SIZE/EMPTY/MAX/LOG/INSIDE/BAR = 7（INT8_MAX/UINT32_MAX 被白名单跳过）
    assert r["macros_count"] == 7
    assert r["conditionals_count"] == 7  # 4 个条件块：ifdef(2) + ifndef(1) + if/elif/else(3) + if0(1)
    assert set(_mmap(r)) == {"PI", "BUF_SIZE", "EMPTY", "MAX", "LOG", "INSIDE", "BAR"}


def test_object_macro_value_and_confidence():
    r = extract_macros(SRC, "f.c")
    m = _mmap(r)
    assert m["PI"]["kind"] == "object"
    assert m["PI"]["body"] == "3.14"
    assert m["PI"]["confidence"] == 0.90
    assert m["PI"]["params"] == []
    assert m["BUF_SIZE"]["body"] == "256"
    assert m["BUF_SIZE"]["confidence"] == 0.90


def test_function_macro_params_and_low_confidence():
    r = extract_macros(SRC, "f.c")
    m = _mmap(r)
    assert m["MAX"]["kind"] == "function"
    assert m["MAX"]["params"] == ["a", "b"]
    assert m["MAX"]["body"] == "((a)>(b)?(a):(b))"
    # 函数式宏 → 低置信度（D4 宏重度 = 0.35）
    assert m["MAX"]["confidence"] == 0.35
    assert m["LOG"]["kind"] == "function"
    assert m["LOG"]["confidence"] == 0.35


def test_flag_empty_macro_low_confidence():
    r = extract_macros(SRC, "f.c")
    m = _mmap(r)
    assert m["EMPTY"]["kind"] == "empty"
    assert m["EMPTY"]["body"] is None
    assert m["EMPTY"]["confidence"] == 0.35


def test_std_whitelist_skipped():
    r = extract_macros(SRC, "f.c")
    # 整数极值宏（INT8_MAX / UINT32_MAX）走白名单，不记为实体
    assert "INT8_MAX" in r["whitelisted_skipped"]
    assert "UINT32_MAX" in r["whitelisted_skipped"]
    # 精确名白名单（NULL 等）也应跳过；LEAST/FAST 极值宏模式也命中
    r2 = extract_macros(b"#define NULL ((void*)0)\n#define INT_LEAST32_MAX 2147483647\n", "w.c")
    assert "NULL" in r2["whitelisted_skipped"]
    assert "INT_LEAST32_MAX" in r2["whitelisted_skipped"]
    assert r2["macros_count"] == 0
    # 函数式宏即便名似标准库（如 offsetof/assert）也记实体（低置信度），不进白名单
    r3 = extract_macros(b"#define offsetof(t,m) __builtin_offsetof(t,m)\n", "o.c")
    assert r3["whitelisted_skipped"] == []
    assert r3["macros_count"] == 1
    assert r3["macros"][0]["kind"] == "function"


def test_macro_inside_branch_recorded():
    # 分支内的宏也应被提取（逆向分析需知道全部定义点）
    r = extract_macros(SRC, "f.c")
    assert "INSIDE" in _mmap(r)
    assert _mmap(r)["INSIDE"]["body"] == "1"


def test_ifdef_branches_and_active_condition():
    r = extract_macros(SRC, "f.c")
    conds = [c for c in r["conditionals"] if c["block_id"] == 1]
    roles = {c["branch_role"]: c for c in conds}
    assert "consequent" in roles and "else" in roles
    # #ifdef FOO：主分支激活 = FOO，else 激活 = !FOO
    assert roles["consequent"]["condition"] == "FOO"
    assert roles["consequent"]["active_condition"] == "FOO"
    assert roles["else"]["active_condition"] == "!(FOO)"
    # 行区间：主分支含 foo 定义行，else 含 foo 另一实现
    assert roles["consequent"]["start_line"] > 0
    assert roles["else"]["start_line"] > roles["consequent"]["end_line"]


def test_ifndef_active_condition_negated():
    r = extract_macros(SRC, "f.c")
    conds = [c for c in r["conditionals"] if c["block_id"] == 2]
    # #ifndef BAR：主分支激活 = !BAR（tree-sitter 把 #ifndef 归为 preproc_ifdef，需读 token 区分）
    assert conds[0]["directive"] == "ifndef"
    assert conds[0]["active_condition"] == "!BAR"


def test_if_elif_else_active_conditions():
    r = extract_macros(SRC, "f.c")
    conds = [c for c in r["conditionals"] if c["block_id"] == 3]
    roles = {c["branch_role"]: c for c in conds}
    assert set(roles) == {"consequent", "elif", "else"}
    assert roles["consequent"]["active_condition"] == "defined(Z) && X > 0"
    # elif：前置取反 且 本条件
    assert roles["elif"]["active_condition"] == "!(defined(Z) && X > 0) && W"
    # else：既不满足 #if 也不满足 #elif → 所有前置条件取反
    assert roles["else"]["active_condition"] == "!(defined(Z) && X > 0 || W)"
    # 行区间连续且非交错
    assert roles["elif"]["start_line"] > roles["consequent"]["end_line"]
    assert roles["else"]["start_line"] > roles["elif"]["end_line"]


def test_if0_dead_branch_parsed():
    r = extract_macros(SRC, "f.c")
    conds = [c for c in r["conditionals"] if c["block_id"] == 4]
    assert len(conds) == 1
    assert conds[0]["condition"] == "0"
    assert conds[0]["active_condition"] == "0"


def test_nested_conditional_depth():
    nested = b"""
#ifdef A
int a(void){ return 1; }
#ifdef B
int b(void){ return 2; }
#endif
#else
int c(void){ return 3; }
#endif
"""
    r = extract_macros(nested, "n.c")
    depths = {c["block_id"]: c["depth"] for c in r["conditionals"]}
    # 外层 block=1 depth 0，内层 block=2 depth 1
    assert 0 in depths.values() and 1 in depths.values()


def test_conditional_block_id_groups_branches():
    r = extract_macros(SRC, "f.c")
    # 每个 block 的分支共享 block_id
    ids = sorted({c["block_id"] for c in r["conditionals"]})
    assert ids == [1, 2, 3, 4]
    assert len(r["conditionals"]) == 7  # 1 ifdef(2) + 1 ifndef(1) + 1 if/elif/else(3) + 1 if0(1)


def test_file_io_and_error_tolerance():
    with tempfile.NamedTemporaryFile("wb", suffix=".c", delete=False) as f:
        f.write(SRC)
        path = f.name
    try:
        r = extract_macros_file(path)
        assert r["parse_ok"] is True
        assert r["macros_count"] == 7
        assert r["conditionals_count"] == 7
    finally:
        os.unlink(path)
    # 缺文件：容错返回 parse_ok=False，不抛
    miss = extract_macros_file("/no/such/file_xyz.c")
    assert miss["parse_ok"] is False
    assert miss["macros"] == []
    # 坏字节：容错不抛
    bad = extract_macros(b"\x00\x01\x02\x03", "bad.c")
    assert "macros" in bad
    # 非空返回但解析容错
    assert extract_macros(b"#define BROKEN (\n", "x.c")["parse_ok"] is True
