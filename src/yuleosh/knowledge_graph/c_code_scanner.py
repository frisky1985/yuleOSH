#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
C AST 代码扫描器（B-M1 / T-011 B1-09）。

对标 ``code_scanner.py`` 的接口（访问者模式 / ScanResult 结构），用 tree-sitter C
解析替换正则，提供与 Python 扫描器**并存**的 C 扫描能力。

接口对齐点（与 code_scanner 一致）：
  - ``scan_directory(store, project_base)`` → 返回汇总 dict（code_files/test_files/
    functions/edges ...），与 code_scanner 同形状。
  - ``scan_single_file(store, project_base, rel_path)`` → 单文件增量扫描。
  - 节点命名空间与 code_scanner 相同（code_file/code_function/test_file/
    test_function），用 ``language="c"`` + ``source="c_code_scanner"`` 区分；
    FQN 用 ``{rel_path}::{name}`` 与 Python 扫描器一致。
  - ``contains`` 边 file→function（与 code_scanner 同义）。

C 专属增强（code_scanner 无）：
  - ``calls`` / ``potential_calls`` 边（来自调用图；``potential_calls`` 为函数指针
    取址/赋值/间接调用，交 B-M2 LLM 推断补齐）。
  - 文件节点属性携带 c_function_count / c_global_count / c_isr_count /
    c_macro_count / parse_ok / error_rate（供 B1-08 / B1-12 门禁趋势）。

注：B1-10 将在此之上扩展专用 C 实体（CFunction/CGlobalVar/CMacro/ISR）与
置信度初值（D4: 0.9 / 0.5 / 0.35），本模块先以对齐接口落地，零回归。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.models import Node, Edge, c_entity_confidence
from yuleosh.knowledge_graph import c_parser

log = logging.getLogger("yuleosh.knowledge_graph.c_code_scanner")

_C_EXTENSIONS = {".c", ".h"}


# ── ScanResult 结构（对标 code_scanner 的 AST 产出） ───────────────────────

@dataclass
class CFileScan:
    """单文件 C 扫描结果（ScanResult 结构的逐项）。"""

    rel_path: str
    language: str            # "c" | "c_header" | "c_test"
    parse_ok: bool
    error_rate: float
    functions: List[dict] = field(default_factory=list)
    globals: List[dict] = field(default_factory=list)
    isrs: List[dict] = field(default_factory=list)
    macros: List[dict] = field(default_factory=list)
    call_edges: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "rel_path": self.rel_path,
            "language": self.language,
            "parse_ok": self.parse_ok,
            "error_rate": round(self.error_rate, 6),
            "function_count": len(self.functions),
            "global_count": len(self.globals),
            "isr_count": len(self.isrs),
            "macro_count": len(self.macros),
            "call_edge_count": len(self.call_edges),
        }


@dataclass
class CScanResult:
    """一次目录扫描的聚合结果（对标 code_scanner.scan_directory 返回）。"""

    files: List[CFileScan] = field(default_factory=list)

    @property
    def code_files(self) -> int:
        return sum(1 for f in self.files if not f.language.endswith("_test"))

    @property
    def test_files(self) -> int:
        return sum(1 for f in self.files if f.language.endswith("_test"))

    @property
    def function_count(self) -> int:
        return sum(len(f.functions) for f in self.files)

    @property
    def global_count(self) -> int:
        return sum(len(f.globals) for f in self.files)

    @property
    def isr_count(self) -> int:
        return sum(len(f.isrs) for f in self.files)

    @property
    def macro_count(self) -> int:
        return sum(len(f.macros) for f in self.files)

    @property
    def call_edge_count(self) -> int:
        return sum(len(f.call_edges) for f in self.files)

    def as_dict(self) -> dict:
        return {
            "code_files": self.code_files,
            "test_files": self.test_files,
            "functions": self.function_count,
            "globals": self.global_count,
            "isrs": self.isr_count,
            "macros": self.macro_count,
            "call_edges": self.call_edge_count,
            "files": [f.as_dict() for f in self.files],
        }


# ── 访问者模式类比：CFunctionCollector ─────────────────────────────────────

class CFunctionCollector:
    """对标 code_scanner.FunctionCollector：收集单个 C 文件的
    函数 / 全局 / ISR / 宏 / 调用边。

    底层用 ``c_parser.extract_c_ast``（单次 parse）实现，不重复构造 AST。
    容错：解析失败返回空结构，不抛异常。
    """

    def __init__(self, rel_path: str, source_bytes: bytes):
        self.rel_path = rel_path
        ast = c_parser.extract_c_ast(source_bytes, rel_path)
        self.parse_ok: bool = ast["parse_ok"]
        self.error_rate: float = ast["error_rate"]
        self.functions: List[dict] = ast["functions"]
        self.globals: List[dict] = ast["globals"]
        self.isrs: List[dict] = ast["isrs"]
        self.macros: List[dict] = ast["macros"]
        self.call_graph: dict = ast["call_graph"]
        self.call_edges: List[dict] = ast["call_graph"]["edges"]


# ── 核心扫描（对齐 code_scanner.scan_directory） ──────────────────────────

def _c_language_for(ext: str, is_test: bool) -> str:
    if is_test:
        return "c_test"
    return "c_header" if ext == ".h" else "c"


def _discover_c_files(project_path: Path) -> List[Path]:
    out: List[Path] = []
    for ext in _C_EXTENSIONS:
        for f in sorted(project_path.rglob(f"*{ext}")):
            parts = f.relative_to(project_path).parts
            if any(p.startswith(".") for p in parts):
                continue
            if "__pycache__" in parts:
                continue
            out.append(f)
    return out


def scan_directory(store: KGStore, project_base: str) -> dict:
    """递归扫描 ``project_base`` 下全部 .c/.h，写入 KG（对齐 code_scanner）。

    节点：
      - code_file / test_file（language="c"/"c_header"/"c_test"）
      - code_function / test_function（FQN = ``{rel_path}::{name}``）
    边：
      - contains   file→function
      - calls / potential_calls  function→function（跨文件解析到全局函数节点）

    Returns:
        汇总 dict（code_files/test_files/functions/globals/isrs/macros/
        call_edges/edges）。
    """
    project_path = Path(project_base)

    # 第一遍：创建 file + function 节点，收集调用边与全局 name→节点映射
    file_scans: List[CFileScan] = []
    local_name_to_nid: dict = {}        # (rel_path, name) -> nid
    global_name_to_nid: dict = {}       # name -> nid（跨文件，首次胜出）
    pending_call_edges: List[dict] = []  # {src_rel, caller, callee, edge_type, raw}
    contains_count = 0

    for c_file in _discover_c_files(project_path):
        try:
            rel_path = str(c_file.relative_to(project_path)).replace("\\", "/")
        except ValueError:
            rel_path = str(c_file)
        parts = c_file.relative_to(project_path).parts
        is_test = ("tests" in parts) or c_file.name.startswith("test_")
        ext = c_file.suffix
        lang = _c_language_for(ext, is_test)
        file_type = "test_file" if is_test else "code_file"
        func_type = "test_function" if is_test else "code_function"

        try:
            raw = c_file.read_bytes()
        except Exception as exc:
            log.warning("读取失败 %s: %s", c_file, exc)
            raw = b""

        collector = CFunctionCollector(rel_path, raw)
        fs = CFileScan(
            rel_path=rel_path,
            language=lang,
            parse_ok=collector.parse_ok,
            error_rate=collector.error_rate,
            functions=collector.functions,
            globals=collector.globals,
            isrs=collector.isrs,
            macros=collector.macros,
            call_edges=collector.call_edges,
        )
        file_scans.append(fs)

        # B1-10 置信度（文件级）：含语法错误 → 0.5，否则 0.9
        has_error = (not collector.parse_ok) or collector.error_rate > 0.0
        func_conf = c_entity_confidence("CFunction", has_error)
        var_conf = c_entity_confidence("CGlobalVar", has_error)
        isr_conf = c_entity_confidence("ISR", has_error)

        # file 节点（属性携带 C 统计，供门禁）
        file_node = Node(
            entity_type=file_type,
            entity_id=rel_path,
            label=c_file.name,
            confidence=var_conf,
            properties={
                "language": lang,
                "path": rel_path,
                "source": "c_code_scanner",
                "c_function_count": len(collector.functions),
                "c_global_count": len(collector.globals),
                "c_isr_count": len(collector.isrs),
                "c_macro_count": len(collector.macros),
                "parse_ok": collector.parse_ok,
                "error_rate": round(collector.error_rate, 6),
            },
        )
        file_nid = store.upsert_node(file_node)

        # ── B1-10 专属 C 实体节点 + contains 边 ──
        # CFunction（代码与测试文件均归为 CFunction，测试文件标记 is_test）
        func_entity = "CFunction"
        for fn in collector.functions:
            fqn = f"{rel_path}::{fn['name']}"
            fp = {
                "file_path": rel_path,
                "start_line": fn["start_line"],
                "end_line": fn["end_line"],
                "kind": "function",
                "is_definition": fn.get("is_definition", False),
                "return_type": fn.get("return_type", ""),
                "source": "c_code_scanner",
                "confidence": func_conf,
            }
            if is_test:
                fp["is_test"] = True
            func_node = Node(
                entity_type=func_entity,
                entity_id=fqn,
                label=fn["name"],
                confidence=func_conf,
                properties=fp,
            )
            fn_nid = store.upsert_node(func_node)
            store.upsert_edge(Edge(
                source_id=file_nid,
                target_id=fn_nid,
                edge_type="contains",
                properties={"function": fn["name"], "kind": "function"},
            ))
            contains_count += 1
            local_name_to_nid[(rel_path, fn["name"])] = fn_nid
            global_name_to_nid.setdefault(fn["name"], fn_nid)

        # CGlobalVar
        for g in collector.globals:
            gqn = f"{rel_path}::var::{g['name']}"
            g_node = Node(
                entity_type="CGlobalVar",
                entity_id=gqn,
                label=g["name"],
                confidence=var_conf,
                properties={
                    "file_path": rel_path,
                    "var_type": g.get("var_type", ""),
                    "storage_class": g.get("storage_class"),
                    "is_volatile": g.get("is_volatile", False),
                    "is_const": g.get("is_const", False),
                    "source": "c_code_scanner",
                    "confidence": var_conf,
                },
            )
            g_nid = store.upsert_node(g_node)
            store.upsert_edge(Edge(
                source_id=file_nid, target_id=g_nid, edge_type="contains",
                properties={"global": g["name"]},
            ))
            contains_count += 1

        # CMacro（白名单宏已排除在 collector.macros 外；函数式/flag → 0.35）
        for m in collector.macros:
            mqn = f"{rel_path}::macro::{m['name']}"
            macro_heavy = m.get("kind") in ("function", "empty")
            m_conf = c_entity_confidence("CMacro", has_error, macro_heavy=macro_heavy)
            m_node = Node(
                entity_type="CMacro",
                entity_id=mqn,
                label=m["name"],
                confidence=m_conf,
                properties={
                    "file_path": rel_path,
                    "macro_kind": m.get("kind"),
                    "body": m.get("body"),
                    "source": "c_code_scanner",
                    "confidence": m_conf,
                },
            )
            m_nid = store.upsert_node(m_node)
            store.upsert_edge(Edge(
                source_id=file_nid, target_id=m_nid, edge_type="contains",
                properties={"macro": m["name"]},
            ))
            contains_count += 1

        # ISR
        for isr in collector.isrs:
            iqn = f"{rel_path}::isr::{isr['name']}"
            i_node = Node(
                entity_type="ISR",
                entity_id=iqn,
                label=isr["name"],
                confidence=isr_conf,
                properties={
                    "file_path": rel_path,
                    "line": isr.get("line"),
                    "reason": isr.get("reason"),
                    "source": "c_code_scanner",
                    "confidence": isr_conf,
                },
            )
            i_nid = store.upsert_node(i_node)
            store.upsert_edge(Edge(
                source_id=file_nid, target_id=i_nid, edge_type="contains",
                properties={"isr": isr["name"]},
            ))
            contains_count += 1

        # 收集调用边（callee 名 → 后续解析）
        for e in collector.call_edges:
            pending_call_edges.append({
                "src_rel": rel_path,
                "caller": e["caller"],
                "callee": e["callee"],
                "edge_type": "calls" if e["edge_type"] == "call" else "potential_calls",
                "raw": e.get("raw"),
            })

    # 第二遍：解析并写入 calls / potential_calls 边
    call_count = 0
    potential_count = 0
    for spec in pending_call_edges:
        src_nid = local_name_to_nid.get((spec["src_rel"], spec["caller"]))
        tgt_nid = global_name_to_nid.get(spec["callee"])
        if src_nid is None or tgt_nid is None:
            continue  # 目标函数不在本次扫描范围（外部库/未扫描）
        props = {"callee": spec["callee"]}
        if spec["raw"] is not None:
            props["raw"] = spec["raw"]
        store.upsert_edge(Edge(
            source_id=src_nid,
            target_id=tgt_nid,
            edge_type=spec["edge_type"],
            properties=props,
        ))
        if spec["edge_type"] == "calls":
            call_count += 1
        else:
            potential_count += 1

    total_edges = contains_count + call_count + potential_count
    result = CScanResult(files=file_scans)
    summary = result.as_dict()
    summary["contains_edges"] = contains_count
    summary["call_edges_resolved"] = call_count
    summary["potential_edges_resolved"] = potential_count
    summary["edges"] = total_edges
    log.info(
        "C scan complete: %d code / %d test files, %d funcs, %d globals, "
        "%d isrs, %d macros, %d edges (contains=%d calls=%d potential=%d)",
        summary["code_files"], summary["test_files"], summary["functions"],
        summary["globals"], summary["isrs"], summary["macros"],
        total_edges, contains_count, call_count, potential_count,
    )
    return summary


def scan_single_file(store: KGStore, project_base: str, rel_path: str) -> dict:
    """扫描单个 C 文件并写入/更新其节点（对齐 code_scanner.scan_single_file）。

    用于增量 KG 更新。单次 parse、仅写本文件节点 + 文件内 contains 边；
    跨文件 calls 边需全量 scan_directory 才有完整解析。

    Returns:
        dict 含本文件的 functions/globals/isrs/macros/edges 计数。
    """
    project_path = Path(project_base).resolve()
    c_file = (project_path / rel_path).resolve()
    if not c_file.exists() or not c_file.is_file():
        log.warning("scan_single_file: 文件不存在 %s", c_file)
        return {"functions": 0, "globals": 0, "isrs": 0, "macros": 0, "edges": 0}

    parts = c_file.relative_to(project_path).parts
    is_test = ("tests" in parts) or c_file.name.startswith("test_")
    ext = c_file.suffix
    lang = _c_language_for(ext, is_test)
    file_type = "test_file" if is_test else "code_file"
    func_type = "test_function" if is_test else "code_function"
    norm_path = rel_path.replace("\\", "/")

    try:
        raw = c_file.read_bytes()
    except Exception as exc:
        log.warning("读取失败 %s: %s", c_file, exc)
        raw = b""

    collector = CFunctionCollector(norm_path, raw)
    has_error = (not collector.parse_ok) or collector.error_rate > 0.0
    func_conf = c_entity_confidence("CFunction", has_error)
    var_conf = c_entity_confidence("CGlobalVar", has_error)
    isr_conf = c_entity_confidence("ISR", has_error)

    file_node = Node(
        entity_type=file_type,
        entity_id=norm_path,
        label=c_file.name,
        confidence=var_conf,
        properties={
            "language": lang,
            "path": norm_path,
            "source": "c_code_scanner",
            "c_function_count": len(collector.functions),
            "c_global_count": len(collector.globals),
            "c_isr_count": len(collector.isrs),
            "c_macro_count": len(collector.macros),
            "parse_ok": collector.parse_ok,
            "error_rate": round(collector.error_rate, 6),
        },
    )
    file_nid = store.upsert_node(file_node)

    func_count = 0
    edge_count = 0
    for fn in collector.functions:
        fqn = f"{norm_path}::{fn['name']}"
        fp = {
            "file_path": norm_path,
            "start_line": fn["start_line"],
            "end_line": fn["end_line"],
            "kind": "function",
            "is_definition": fn.get("is_definition", False),
            "return_type": fn.get("return_type", ""),
            "source": "c_code_scanner",
            "confidence": func_conf,
        }
        if is_test:
            fp["is_test"] = True
        func_node = Node(
            entity_type="CFunction",
            entity_id=fqn,
            label=fn["name"],
            confidence=func_conf,
            properties=fp,
        )
        fn_nid = store.upsert_node(func_node)
        store.upsert_edge(Edge(
            source_id=file_nid,
            target_id=fn_nid,
            edge_type="contains",
            properties={"function": fn["name"], "kind": "function"},
        ))
        func_count += 1
        edge_count += 1

    # 全局/宏/ISR 实体（单文件增量，仅 contains 边）
    for g in collector.globals:
        g_node = Node(
            entity_type="CGlobalVar",
            entity_id=f"{norm_path}::var::{g['name']}",
            label=g["name"],
            confidence=var_conf,
            properties={
                "file_path": norm_path,
                "var_type": g.get("var_type", ""),
                "source": "c_code_scanner",
                "confidence": var_conf,
            },
        )
        g_nid = store.upsert_node(g_node)
        store.upsert_edge(Edge(source_id=file_nid, target_id=g_nid,
                               edge_type="contains", properties={"global": g["name"]}))
        edge_count += 1
    for m in collector.macros:
        macro_heavy = m.get("kind") in ("function", "empty")
        m_conf = c_entity_confidence("CMacro", has_error, macro_heavy=macro_heavy)
        m_node = Node(
            entity_type="CMacro",
            entity_id=f"{norm_path}::macro::{m['name']}",
            label=m["name"],
            confidence=m_conf,
            properties={
                "file_path": norm_path,
                "macro_kind": m.get("kind"),
                "source": "c_code_scanner",
                "confidence": m_conf,
            },
        )
        m_nid = store.upsert_node(m_node)
        store.upsert_edge(Edge(source_id=file_nid, target_id=m_nid,
                               edge_type="contains", properties={"macro": m["name"]}))
        edge_count += 1
    for isr in collector.isrs:
        i_node = Node(
            entity_type="ISR",
            entity_id=f"{norm_path}::isr::{isr['name']}",
            label=isr["name"],
            confidence=isr_conf,
            properties={
                "file_path": norm_path,
                "line": isr.get("line"),
                "reason": isr.get("reason"),
                "source": "c_code_scanner",
                "confidence": isr_conf,
            },
        )
        i_nid = store.upsert_node(i_node)
        store.upsert_edge(Edge(source_id=file_nid, target_id=i_nid,
                               edge_type="contains", properties={"isr": isr["name"]}))
        edge_count += 1

    return {
        "functions": func_count,
        "globals": len(collector.globals),
        "isrs": len(collector.isrs),
        "macros": len(collector.macros),
        "edges": edge_count,
        "parse_ok": collector.parse_ok,
    }


# 别名：与 code_scanner 命名风格一致
scan_project = scan_directory
