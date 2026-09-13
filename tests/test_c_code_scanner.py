"""B1-09 c_code_scanner 对标接口测试。

验证：
  - scan_directory 写入 code_file/code_function + contains 边（与 code_scanner 同命名空间）
  - calls / potential_calls 边（函数指针取址记为 potential_calls）
  - CScanResult / CFileScan 结构 + 汇总 dict 形状对齐 code_scanner
  - scan_single_file 单文件增量
  - 容错（坏文件不抛）
"""

import os
import tempfile

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph import c_code_scanner
from yuleosh.knowledge_graph.c_code_scanner import CScanResult, CFunctionCollector


def _make_project():
    d = tempfile.mkdtemp(prefix="cscan_")
    # a.c: foo 调 bar；函数体内取址 &bar 传回调（potential-call）；volatile 全局；宏
    (Path := __import__("pathlib").Path)
    (Path(d) / "a.c").write_text(
        "#define LIMIT 10\n"
        "volatile int g_count = 0;\n"
        "void bar(void) { g_count = 1; }\n"
        "void foo(void) { bar(); void (*p)(void) = &bar; g_count += LIMIT; }\n"
    )
    # b.c: isr 命名启发式，调用 foo（跨文件 calls 边）
    (Path(d) / "b.c").write_text(
        "void USART1_IRQHandler(void) { foo(); }\n"
    )
    # 子目录 tests/ 下视为测试文件
    (Path(d) / "tests").mkdir()
    (Path(d) / "tests" / "t.c").write_text("void test_case(void) { foo(); }\n")
    return d


def _store():
    db = tempfile.mktemp(suffix=".db")
    KGStore.reset()
    return KGStore(db_path=db), db


def test_scan_directory_nodes_and_contains():
    proj = _make_project()
    store, db = _store()
    try:
        summary = c_code_scanner.scan_directory(store, proj)
        stats = store.get_stats()
        # 3 个 .c 文件（a.c / b.c / tests/t.c）
        assert summary["code_files"] == 2
        assert summary["test_files"] == 1
        assert summary["functions"] >= 4  # bar/foo/USART1_IRQHandler/test_case
        # contains 边存在
        assert summary["contains_edges"] == summary["functions"]
        # code_file 节点存在且 language=c
        a_node = store.get_node("code_file", "a.c")
        assert a_node is not None
        assert a_node.properties["language"] == "c"
        assert a_node.properties["c_function_count"] >= 2
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_call_and_potential_edges():
    proj = _make_project()
    store, db = _store()
    try:
        summary = c_code_scanner.scan_directory(store, proj)
        # a.c: foo 调 bar（calls）；&bar 取址（potential_calls）
        assert summary["call_edges_resolved"] >= 1
        # potential_calls：g_cb = &bar
        pot = store.list_edges("potential_calls")
        assert len(pot) >= 1
        calls = store.list_edges("calls")
        assert len(calls) >= 1
        # 跨文件：USART1_IRQHandler → foo（b.c 调 a.c 的函数）应解析为 calls 边
        src = store.get_node("code_function", "b.c::USART1_IRQHandler")
        outs = store.get_outgoing_edges(src.id)
        callees = {e.edge_type for e, _ in outs}
        assert "calls" in callees
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_scan_result_structure():
    proj = _make_project()
    store, db = _store()
    try:
        summary = c_code_scanner.scan_directory(store, proj)
        # 汇总 dict 含对齐 code_scanner 的键
        for k in ("code_files", "test_files", "functions", "edges"):
            assert k in summary
        # CScanResult 可由 files 构造
        res = CScanResult(files=[])
        assert res.code_files == 0
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_cfunction_collector_visitor():
    raw = b"#define N 3\nvolatile int x;\nvoid f(void){ g(); }\nvoid g(void){}\n"
    col = CFunctionCollector("x.c", raw)
    assert col.parse_ok is True
    names = {f["name"] for f in col.functions}
    assert names == {"f", "g"}
    assert col.error_rate == 0.0


def test_scan_single_file_incremental():
    proj = _make_project()
    store, db = _store()
    try:
        r = c_code_scanner.scan_single_file(store, proj, "a.c")
        assert r["functions"] >= 2
        assert r["parse_ok"] is True
        # 单文件仅 contains 边（无跨文件 calls 解析）
        assert r["edges"] == r["functions"]
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_bad_file_no_crash():
    proj = _make_project()
    store, db = _store()
    try:
        (Path := __import__("pathlib").Path)
        (Path(proj) / "bad.c").write_text("\x00\x01\x02 not c\n")
        # 不应抛异常；坏文件 parse_ok=False 但不崩溃
        summary = c_code_scanner.scan_directory(store, proj)
        assert summary["code_files"] >= 2
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)
