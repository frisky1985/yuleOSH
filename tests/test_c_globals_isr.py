"""B1-06 全局状态 + ISR 提取测试。

覆盖：全局/静态/extern/volatile/const/数组/函数指针/函数指针数组变量；排除函数原型与
typedef 别名；ISR 命名启发式 / __attribute__((interrupt)) / 中断向量表；容错（坏输入/缺文件）。
"""

import pytest

from yuleosh.knowledge_graph.c_parser import (
    extract_globals,
    extract_globals_file,
    extract_isrs,
    extract_isrs_file,
)

SRC = b"""
extern int g_ext;
volatile unsigned int g_tick = 0;
static const char *g_name = "dev";
int g_arr[4] = {1,2,3,4};
void (*g_handler)(void);
void (*const g_vec[])(void) = { handler_a };
typedef int my_int;
void foo_proto(void);
void handler_a(void) {}
void normal_fn(void) {}
__attribute__((interrupt)) void isr_timer(void) {}
void USART1_IRQHandler(void) {}
"""


def _gmap(g):
    return {x["name"]: x for x in g["globals"]}


def test_globals_basic_set():
    g = extract_globals(SRC, "f.c")
    assert g["parse_ok"] is True
    assert set(_gmap(g)) == {"g_ext", "g_tick", "g_name", "g_arr", "g_handler", "g_vec"}
    assert g["count"] == 6


def test_global_volatile_const_static_extern():
    g = extract_globals(SRC, "f.c")
    m = _gmap(g)
    assert m["g_tick"]["is_volatile"] is True
    assert m["g_tick"]["var_type"] == "volatile unsigned int"
    assert m["g_name"]["storage_class"] == "static"
    assert m["g_name"]["is_const"] is True
    assert m["g_name"]["var_type"] == "const char *"
    assert m["g_ext"]["storage_class"] == "extern"
    assert m["g_ext"]["initializer"] is None


def test_global_array_and_funcptr_types():
    g = extract_globals(SRC, "f.c")
    m = _gmap(g)
    assert m["g_arr"]["var_type"] == "int []"
    assert m["g_arr"]["initializer"] == "{1,2,3,4}"
    assert m["g_handler"]["var_type"] == "void (*)"
    assert m["g_vec"]["var_type"] == "void * []"


def test_excludes_prototype_and_typedef():
    g = extract_globals(SRC, "f.c")
    names = {x["name"] for x in g["globals"]}
    assert "foo_proto" not in names  # 函数原型不提取
    assert "my_int" not in names  # typedef 别名不提取
    assert "handler_a" not in names  # 函数定义不提取


def test_isr_heuristics_attribute_vector():
    g = extract_isrs(SRC, "f.c")
    names = {x["name"] for x in g["isrs"]}
    assert "USART1_IRQHandler" in names  # 命名（handler）
    assert "isr_timer" in names  # __attribute__((interrupt))
    assert "handler_a" in names  # 向量表注册
    assert "normal_fn" not in names  # 普通函数不标
    reason_of = {x["name"]: x["reason"] for x in g["isrs"]}
    assert "attribute" in reason_of["isr_timer"]
    assert "vector_table" in reason_of["handler_a"]
    assert reason_of["USART1_IRQHandler"] == "name"


def test_globals_as_dict_keys():
    g = extract_globals(SRC, "f.c")
    assert set(g["globals"][0]) == {
        "name", "var_type", "storage_class", "is_volatile",
        "is_const", "initializer", "line", "byte_start", "byte_end",
    }


def test_smoke_bad_input_no_crash():
    g = extract_globals(b"int x = ", "bad.c")
    assert g["parse_ok"] is True
    assert isinstance(g["globals"], list)
    i = extract_isrs(b"void (", "bad.c")
    assert i["parse_ok"] is True
    assert isinstance(i["isrs"], list)


def test_extract_globals_file(tmp_path):
    p = tmp_path / "a.c"
    p.write_bytes(SRC)
    g = extract_globals_file(str(p))
    assert g["parse_ok"] is True
    assert "g_tick" in {x["name"] for x in g["globals"]}


def test_extract_globals_file_missing():
    g = extract_globals_file("/nonexistent/x.c")
    assert g["parse_ok"] is False
    assert g["globals"] == []


def test_extract_isrs_file(tmp_path):
    p = tmp_path / "a.c"
    p.write_bytes(SRC)
    g = extract_isrs_file(str(p))
    assert g["parse_ok"] is True
    assert "USART1_IRQHandler" in {x["name"] for x in g["isrs"]}


def test_extract_isrs_file_missing():
    g = extract_isrs_file("/nonexistent/x.c")
    assert g["parse_ok"] is False
    assert g["isrs"] == []
