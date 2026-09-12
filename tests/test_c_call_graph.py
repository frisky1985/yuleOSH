"""B1-05 调用图提取测试。

覆盖：直接调用、外部调用、函数指针取址(&func)、赋值(=func)、间接调用((*fp)())、
递归、嵌套调用、field_expression(obj.method())、容错（坏输入/二进制不崩溃）。
"""

import os

import pytest

from yuleosh.knowledge_graph.c_parser import (
    CallGraph,
    extract_call_graph,
    extract_call_graph_file,
)


def _edges_by_type(g, edge_type):
    return [e for e in g["edges"] if e["edge_type"] == edge_type]


def _callees(g, caller, edge_type="call"):
    return [e["callee"] for e in g["edges"] if e["caller"] == caller and e["edge_type"] == edge_type]


def test_direct_call():
    src = b"void foo(void) {}\nint main(void) { foo(); return 0; }\n"
    g = extract_call_graph(src, filename="t.c")
    assert g["parse_ok"] is True
    assert set(g["functions"]) == {"foo", "main"}
    assert _callees(g, "main", "call") == ["foo"]
    assert g["external_calls"] == []
    assert g["call_count"] == 1
    assert g["potential_count"] == 0


def test_external_call_recorded():
    src = b'int main(void) { printf("hi"); return 0; }\n'
    g = extract_call_graph(src, filename="t.c")
    assert _callees(g, "main", "call") == ["printf"]
    assert g["external_calls"] == ["printf"]


def test_recursive_self_loop():
    src = b"int fac(int n) { if (n<=1) return 1; return n * fac(n-1); }\n"
    g = extract_call_graph(src, filename="t.c")
    assert _callees(g, "fac", "call") == ["fac"]


def test_nested_calls():
    src = b"""
void c(void) {}
void b(void) { c(); }
void a(void) { b(); }
"""
    g = extract_call_graph(src, filename="t.c")
    assert set(_callees(g, "a", "call")) == {"b"}
    assert set(_callees(g, "b", "call")) == {"c"}
    assert g["external_calls"] == []


def test_indirect_deref_is_potential():
    # (*fp)() —— 间接调用，必须建模为 potential-call，不静默丢弃
    src = b"""
void bar(void) {}
int main(void) { void (*fp)(void) = bar; (*fp)(); return 0; }
"""
    g = extract_call_graph(src, filename="t.c")
    potential = _edges_by_type(g, "potential-call")
    assert any(e["callee"] == "fp" and e["raw"] == "(*fp)" for e in potential)
    # 初始化器 =bar 也记为 potential-call
    assert any(e["callee"] == "bar" and e["raw"] == "=bar" for e in potential)
    assert g["potential_count"] == 2


def test_address_taken_is_potential():
    # &handler 取址（作为回调注册）—— potential-call
    src = b"""
void handler(int sig) {}
void register_cb(void (*cb)(int)) {}
int main(void) { register_cb(&handler); return 0; }
"""
    g = extract_call_graph(src, filename="t.c")
    assert _callees(g, "main", "call") == ["register_cb"]
    potential = _edges_by_type(g, "potential-call")
    assert any(e["callee"] == "handler" and e["raw"] == "&handler" for e in potential)


def test_fnptr_assignment_is_potential():
    # 运行时赋值 fp = bar（非声明初始化器）
    src = b"""
void bar(void) {}
void other(void) {}
int main(void) { void (*fp)(void); fp = bar; fp = other; return 0; }
"""
    g = extract_call_graph(src, filename="t.c")
    potential = _edges_by_type(g, "potential-call")
    callees = {e["callee"] for e in potential}
    assert callees == {"bar", "other"}
    assert all(e["raw"].endswith(("=bar", "=other")) for e in potential)


def test_field_expression_is_potential():
    # obj.method() —— 间接调用，建模为 potential-call
    src = b"""
struct S { void (*m)(void); };
void real(void){}
int main(void){ struct S s; s.m(); real(); return 0; }
"""
    g = extract_call_graph(src, filename="t.c")
    assert _callees(g, "main", "call") == ["real"]
    potential = _edges_by_type(g, "potential-call")
    assert any(e["callee"] == "s" and e["raw"] == "s.m" for e in potential)


def test_as_dict_structure():
    src = b"void foo(void){}\nint main(void){ foo(); return 0; }\n"
    g = extract_call_graph(src, filename="f.c")
    assert set(g.keys()) >= {
        "filename", "functions", "edges", "external_calls",
        "call_count", "potential_count", "parse_ok",
    }
    assert g["filename"] == "f.c"
    edge = g["edges"][0]
    assert set(edge.keys()) == {"caller", "callee", "edge_type", "line", "raw"}


def test_smoke_binary_no_crash():
    # 二进制/非 C 输入：容错，不抛异常，返回空图
    g = extract_call_graph(b"\x00\x01\x02\x03\xff\xfe", filename="bin")
    assert isinstance(g, dict)
    assert g["parse_ok"] is True  # 树可构建（含 ERROR），不崩溃
    assert g["functions"] == []
    assert g["edges"] == []


def test_bad_syntax_no_crash():
    # 语法残缺：容错返回，不抛
    g = extract_call_graph(b"int main( { printf(\n", filename="bad.c")
    assert isinstance(g, dict)
    assert g["call_count"] == 0


def _write_tmp(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def test_extract_call_graph_file(tmp_path):
    path = _write_tmp(tmp_path, "a.c", b"void foo(void){}\nint main(void){ foo(); }\n")
    g = extract_call_graph_file(path)
    assert g["parse_ok"] is True
    assert _callees(g, "main", "call") == ["foo"]


def test_extract_call_graph_file_missing():
    g = extract_call_graph_file("/nonexistent/path/xyz.c")
    assert g["parse_ok"] is False
    assert g["functions"] == []
    assert g["edges"] == []


def test_callgraph_dataclass_ok():
    # dataclass 构造 + 计数属性
    cg = CallGraph(filename="x", functions=["a"], edges=[], external_calls=[], parse_ok=True)
    assert cg.call_count == 0
    assert cg.potential_count == 0
