"""B1-10 KG 入库 + 置信度初始规则测试。

验证：
  - models 扩展：ENTITY_TYPES 含 CFunction/CGlobalVar/CMacro/ISR；
    EDGE_TYPES 含 calls/potential_calls
  - c_code_scanner 写入上述专属 C 实体节点 + contains 边
  - 置信度初值（D4）：CFunction/CGlobalVar/ISR 干净 0.9、含错 0.5；
    CMacro 函数式/flag 0.35、对象 0.9
  - Node.confidence 经 store 持久化并回读
"""

import os
import tempfile

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import (
    ENTITY_TYPES,
    EDGE_TYPES,
    c_entity_confidence,
    C_CONFIDENCE_CLEAN,
    C_CONFIDENCE_ERROR,
    C_CONFIDENCE_MACRO_HEAVY,
)
from yuleosh.knowledge_graph import c_code_scanner


def _make_project():
    d = tempfile.mkdtemp(prefix="ckg_")
    Path = __import__("pathlib").Path
    (Path(d) / "a.c").write_text(
        "#define LIMIT 10\n"          # 对象宏 → 0.9
        "#define MAX(a,b) ((a)>(b)?(a):(b))\n"  # 函数式宏 → 0.35
        "volatile int g_count = 0;\n"
        "void bar(void);\n"
        "void foo(void) { bar(); g_count += LIMIT; MAX(1,2); }\n"
        "void bar(void) { g_count = 1; }\n"
    )
    (Path(d) / "b.c").write_text(
        "void USART1_IRQHandler(void) { foo(); }\n"  # ISR + 跨文件调用
    )
    return d


def _store():
    db = tempfile.mktemp(suffix=".db")
    KGStore.reset()
    return KGStore(db_path=db), db


def test_models_c_entities_and_edges():
    for e in ("CFunction", "CGlobalVar", "CMacro", "ISR"):
        assert e in ENTITY_TYPES
    for ed in ("calls", "potential_calls"):
        assert ed in EDGE_TYPES


def test_confidence_rules_d4():
    # 干净函数/全局/ISR = 0.9
    assert c_entity_confidence("CFunction", has_error=False) == C_CONFIDENCE_CLEAN
    assert c_entity_confidence("CGlobalVar", has_error=False) == C_CONFIDENCE_CLEAN
    assert c_entity_confidence("ISR", has_error=False) == C_CONFIDENCE_CLEAN
    # 含错 = 0.5
    assert c_entity_confidence("CFunction", has_error=True) == C_CONFIDENCE_ERROR
    # 宏重度（函数式/flag）= 0.35；对象宏干净 = 0.9
    assert c_entity_confidence("CMacro", has_error=False, macro_heavy=True) == C_CONFIDENCE_MACRO_HEAVY
    assert c_entity_confidence("CMacro", has_error=False, macro_heavy=False) == C_CONFIDENCE_CLEAN


def test_c_entities_written_with_confidence():
    proj = _make_project()
    store, db = _store()
    try:
        c_code_scanner.scan_directory(store, proj)
        # CFunction 节点存在且置信度 0.9（干净文件）
        foo = store.get_node("CFunction", "a.c::foo")
        assert foo is not None
        assert foo.confidence == C_CONFIDENCE_CLEAN
        assert foo.properties["confidence"] == C_CONFIDENCE_CLEAN
        # CGlobalVar
        g = store.get_node("CGlobalVar", "a.c::var::g_count")
        assert g is not None
        assert g.confidence == C_CONFIDENCE_CLEAN
        # CMacro：对象宏 LIMIT = 0.9，函数式 MAX = 0.35
        lim = store.get_node("CMacro", "a.c::macro::LIMIT")
        assert lim is not None
        assert lim.confidence == C_CONFIDENCE_CLEAN
        assert lim.properties["macro_kind"] == "object"
        mx = store.get_node("CMacro", "a.c::macro::MAX")
        assert mx is not None
        assert mx.confidence == C_CONFIDENCE_MACRO_HEAVY
        assert mx.properties["macro_kind"] == "function"
        # ISR
        isr = store.get_node("ISR", "b.c::isr::USART1_IRQHandler")
        assert isr is not None
        assert isr.properties["reason"] is not None
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_error_file_lowers_confidence():
    proj = _make_project()
    Path = __import__("pathlib").Path
    (Path(proj) / "bad.c").write_text("void broken( {\n")  # 语法错误
    store, db = _store()
    try:
        c_code_scanner.scan_directory(store, proj)
        b = store.get_node("CFunction", "bad.c::broken")
        # 含语法错误 → 0.5（若仍能提取到函数名）
        if b is not None:
            assert b.confidence == C_CONFIDENCE_ERROR
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)


def test_calls_edges_between_cfunctions():
    proj = _make_project()
    store, db = _store()
    try:
        summary = c_code_scanner.scan_directory(store, proj)
        # 跨文件 calls：USART1_IRQHandler → foo
        assert summary["call_edges_resolved"] >= 1
        src = store.get_node("CFunction", "b.c::USART1_IRQHandler")
        outs = store.get_outgoing_edges(src.id)
        targets = {(e.edge_type, t.label) for e, t in outs}
        assert ("calls", "foo") in targets
    finally:
        KGStore.reset()
        os.unlink(db)
        __import__("shutil").rmtree(proj, ignore_errors=True)
