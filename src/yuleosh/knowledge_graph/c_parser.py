"""容错 C 源码解析封装 (B-M1 / T-011 B1-02).

基于 ``tree-sitter`` + ``tree-sitter-c`` 提供**永不抛异常**的 C 解析入口。
设计目标（验收 B1-02）：
  - ``parse()`` / ``parse_file()`` 对任何输入（坏 C、截断、二进制、超大文件）
    都不抛出异常；解析失败转为可量化的错误统计返回。
  - 返回 ``CParseResult`` 含语法树、ERROR / MISSING 节点计数与位置，
    使「错误率」可被后续门禁（B1-08 / B1-12）量化。

节点错误语义（tree-sitter Python 绑定实测）：
  - ``node.type == "ERROR"``      → 语法错误节点
  - ``node.is_missing is True``   → 缺失的必要 token（如少写的 ``;``、未闭合 ``}``）
  - ``node.has_error is True``    → 子树内含错误（用于快速短路）

后续 B1-03~B1-07 在此文件扩展函数/调用图/全局状态/ISR/宏提取。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from tree_sitter import Language, Parser

try:  # grammar 包可能未安装（依赖未就位时给出清晰报错而非崩溃）
    import tree_sitter_c
except Exception as _err:  # pragma: no cover - 仅依赖缺失路径
    tree_sitter_c = None
    _GRAMMAR_ERR = _err
else:
    _GRAMMAR_ERR = None

_C_LANGUAGE = None


def _get_c_language() -> Language:
    """惰性加载 C grammar；首次调用后缓存。"""
    global _C_LANGUAGE
    if _GRAMMAR_ERR is not None:
        raise RuntimeError(
            "tree-sitter-c 未安装或导入失败，无法解析 C 源码："
            f"{_GRAMMAR_ERR}。请先 `pip install tree-sitter-c`（见 pyproject 依赖）。"
        )
    if _C_LANGUAGE is None:
        _C_LANGUAGE = Language(tree_sitter_c.language())
    return _C_LANGUAGE


@dataclass
class ErrorNode:
    """单个错误/缺失节点的位置信息。"""

    line: int  # 0-based 行号
    column: int  # 0-based 列号
    node_type: str  # "ERROR" 或缺失节点的期望类型（如 ";" / "}"）
    kind: str  # "error" | "missing"


@dataclass
class CParseResult:
    """一次解析的结果（容错，永不抛异常）。"""

    filename: str
    ok: bool  # True = 语法树构建成功（不代表无语法错误）
    total_nodes: int = 0
    error_count: int = 0  # ERROR + MISSING 节点总数
    missing_count: int = 0  # 缺失 token 数
    error_nodes: List[ErrorNode] = field(default_factory=list)
    exception: Optional[str] = None  # 解析器级异常信息（如 grammar 未装）
    byte_length: int = 0
    # 内部持有的 tree（可为 None），外部如需遍历用 root_node
    _tree: Optional[object] = field(default=None, repr=False)

    @property
    def root_node(self):
        """语法树根节点（解析失败时为 None）。"""
        return self._tree.root_node if self._tree is not None else None

    @property
    def has_syntax_error(self) -> bool:
        """是否存在任何语法错误/缺失节点。"""
        return self.error_count > 0

    @property
    def error_rate(self) -> float:
        """错误节点占比（0.0~1.0）；无节点时返回 0.0。"""
        if self.total_nodes == 0:
            return 0.0
        return self.error_count / self.total_nodes

    def as_dict(self) -> dict:
        """可序列化摘要（供日志/门禁使用）。"""
        return {
            "filename": self.filename,
            "ok": self.ok,
            "total_nodes": self.total_nodes,
            "error_count": self.error_count,
            "missing_count": self.missing_count,
            "error_rate": round(self.error_rate, 6),
            "has_syntax_error": self.has_syntax_error,
            "byte_length": self.byte_length,
            "exception": self.exception,
            "error_nodes": [
                {"line": e.line, "column": e.column, "type": e.node_type, "kind": e.kind}
                for e in self.error_nodes
            ],
        }


def _count_errors(root) -> Tuple[int, int, List[ErrorNode]]:
    """遍历语法树，统计 ERROR / MISSING 节点。"""
    error_count = 0
    missing_count = 0
    nodes: List[ErrorNode] = []
    total = 0

    def visit(n):
        nonlocal error_count, missing_count, total
        total += 1
        is_missing = bool(getattr(n, "is_missing", False))
        is_error = n.type == "ERROR"
        if is_error or is_missing:
            error_count += 1
            if is_missing:
                missing_count += 1
            nodes.append(
                ErrorNode(
                    line=n.start_point[0],
                    column=n.start_point[1],
                    node_type=n.type if n.type != "ERROR" else "ERROR",
                    kind="missing" if is_missing else "error",
                )
            )
        for c in n.children:
            visit(c)

    if root is not None:
        visit(root)
    return error_count, missing_count, nodes, total


def parse(source: bytes, filename: str = "<string>") -> CParseResult:
    """解析 C 源码字节流（容错，永不抛异常）。

    Args:
        source: C 源码字节（建议用 utf-8/latin-1 解码后的 bytes）。
        filename: 来源文件名（仅用于错误定位与日志）。

    Returns:
        CParseResult：即使源码损坏/截断也返回统计结果，``ok`` 标解析器是否成功构建树。
    """
    if not isinstance(source, (bytes, bytearray)):
        # 容错：允许传入 str
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    byte_length = len(source)
    try:
        lang = _get_c_language()
    except Exception as exc:  # grammar 未安装
        return CParseResult(
            filename=filename, ok=False, byte_length=byte_length, exception=str(exc)
        )
    try:
        parser = Parser()
        parser.language = lang
        tree = parser.parse(bytes(source))
    except Exception as exc:  # 解析器级崩溃（极罕见）
        return CParseResult(
            filename=filename, ok=False, byte_length=byte_length, exception=repr(exc)
        )
    error_count, missing_count, nodes, total = _count_errors(tree.root_node)
    return CParseResult(
        filename=filename,
        ok=True,
        total_nodes=total,
        error_count=error_count,
        missing_count=missing_count,
        error_nodes=nodes,
        byte_length=byte_length,
        _tree=tree,
    )


def parse_file(path: str, encoding: str = "utf-8") -> CParseResult:
    """解析磁盘上的 C 文件（容错，永不抛异常）。

    读取失败（文件不存在/无权限/解码失败）也返回 CParseResult 而非抛异常：
    解码失败用 latin-1 兜底（二进制也能解析而不崩溃）；其余异常记入 ``exception``。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception as exc:
        return CParseResult(
            filename=path, ok=False, byte_length=0, exception=f"read failed: {exc!r}"
        )
    try:
        text = raw.decode(encoding)
    except Exception:
        # 兜底：二进制/混合编码也能喂给解析器而不崩溃
        text = raw.decode("latin-1", errors="replace")
    return parse(text.encode("utf-8", "replace"), filename=path)


# 便捷：模块级常量导出，供测试与后续扩展引用
__all__ = [
    "CParseResult",
    "ErrorNode",
    "parse",
    "parse_file",
    "FunctionInfo",
    "FunctionParam",
    "extract_functions",
    "extract_functions_file",
    "CallEdge",
    "CallGraph",
    "extract_call_graph",
    "extract_call_graph_file",
]


# ══════════════════════════════════════════════════════════════════
# B1-03 函数级提取
# ══════════════════════════════════════════════════════════════════
# 参与「返回类型 / 存储类」拼装的节点类型（按 C 语法分类）。
_TYPE_NODE_TYPES = {
    "primitive_type",       # int / char / float / void ...
    "type_identifier",      # 自定义类型名（typedef / struct tag）
    "type_specifier",       # signed / unsigned / long / short / _Bool / _Complex ...
    "struct_specifier",     # struct X { ... }
    "enum_specifier",       # enum X { ... }
    "union_specifier",      # union X { ... }
    "sized_type_specifier", # __int128 / _Float128 ...
    "typeof_type_specifier",
    "typedef_type",         # 经 typedef 引入的类型别名
}
# declaration 前导中除 declarator / storage 外的修饰节点也并入返回类型。
_QUAL_NODE_TYPES = {"type_qualifier"}  # const / volatile / restrict / _Atomic


@dataclass
class FunctionParam:
    """单个函数参数（K&R 老式声明时 type 可能为空，类型在外部声明中解析）。"""

    name: Optional[str]
    type: str


@dataclass
class FunctionInfo:
    """一个函数（定义或原型）的提取结果。"""

    name: str
    return_type: str
    storage_class: Optional[str]
    parameters: List[FunctionParam]
    is_definition: bool  # True=带函数体（function_definition）；False=仅原型
    start_line: int  # 1-based
    end_line: int  # 1-based
    byte_start: int
    byte_end: int
    leading_comment: Optional[str]  # 紧邻函数上方的注释块（不含远处注释）

    def as_dict(self) -> dict:
        """可序列化摘要（供下游调用图 / 知识图谱入库）。"""
        return {
            "name": self.name,
            "return_type": self.return_type,
            "storage_class": self.storage_class,
            "parameters": [{"name": p.name, "type": p.type} for p in self.parameters],
            "is_definition": self.is_definition,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "leading_comment": self.leading_comment,
        }


def _declarator_name(declarator) -> Optional[object]:
    """从 function_declarator（或其包装层）取函数名 identifier 节点。"""
    if declarator is None:
        return None
    if declarator.type == "identifier":
        return declarator
    for c in declarator.children:
        if c.type == "identifier":
            return c
        # 穿透 pointer/array/parenthesized/qualified 包装层（函数指针/数组参数名）
        deeper = _declarator_name(c)
        if deeper is not None:
            return deeper
    return None


def _param_list(declarator) -> Optional[object]:
    for c in declarator.children:
        if c.type == "parameter_list":
            return c
    return None


def _declarator_base_type(decl, collected: List[str]) -> None:
    """把 pointer/array/parenthesized/qualified 包装层拆成类型标记（* / []），剥离名字。

    指针在外层先记 ``*``，数组在内层后记 ``[]``，从而 ``char *argv[]`` →
    ``char * []``；名字（identifier）不计。
    """
    t = decl.type
    if t == "identifier":
        return
    if t == "pointer_declarator":
        collected.append("*")
        for c in decl.children:
            _declarator_base_type(c, collected)
    elif t == "array_declarator":
        for c in decl.children:
            _declarator_base_type(c, collected)
        collected.append("[]")
    elif t in ("parenthesized_declarator", "qualified_declarator"):
        for c in decl.children:
            _declarator_base_type(c, collected)


def _extract_params(plist) -> List[FunctionParam]:
    """从 parameter_list 抽取参数名与类型。

    支持：普通声明、指针/数组参数（类型剥离参数名）、K&R 老式
    （parameter_list 直接含 identifier，type 留空由外部声明解析）。
    """
    params: List[FunctionParam] = []
    if plist is None:
        return params
    for child in plist.children:
        if child.type == "parameter_declaration":
            name = None
            type_parts: List[str] = []
            for sub in child.children:
                if sub.type == "identifier":
                    name = sub.text.decode("utf-8", "replace")
                elif sub.type in _TYPE_NODE_TYPES or sub.type in _QUAL_NODE_TYPES:
                    type_parts.append(sub.text.decode("utf-8", "replace"))
                elif sub.type in (
                    "pointer_declarator",
                    "array_declarator",
                    "parenthesized_declarator",
                    "qualified_declarator",
                ):
                    _declarator_base_type(sub, type_parts)
                    nm = _declarator_name(sub)
                    if nm is not None and name is None:
                        name = nm.text.decode("utf-8", "replace")
            params.append(FunctionParam(name=name, type=" ".join(type_parts).strip()))
        elif child.type == "identifier":
            # K&R 老式：parameter_list 直接列名，类型在声明内补
            params.append(FunctionParam(name=child.text.decode("utf-8", "replace"), type=""))
    return params


def _extract_head(func_node) -> Tuple[str, Optional[str]]:
    """从 function_definition / declaration 前导子节点抽取返回类型与存储类。

    遇到 function_declarator 即停止（其后的 parameter_list 不计入返回类型）。
    """
    return_type_parts: List[str] = []
    storage: Optional[str] = None
    for c in func_node.children:
        if c.type == "function_declarator":
            break
        if c.type == "storage_class_specifier":
            storage = c.text.decode("utf-8", "replace")
        elif c.type in _TYPE_NODE_TYPES or c.type in _QUAL_NODE_TYPES:
            return_type_parts.append(c.text.decode("utf-8", "replace"))
    return " ".join(return_type_parts).strip(), storage


def _collect_comments(root) -> List[Tuple[int, int, str]]:
    """收集语法树中所有 comment 节点：(start, end, text) 按 start 排序。"""
    out: List[Tuple[int, int, str]] = []

    def visit(n):
        if n.type == "comment":
            out.append(
                (n.start_byte, n.end_byte, n.text.decode("utf-8", "replace"))
            )
        for c in n.children:
            visit(c)

    if root is not None:
        visit(root)
    out.sort()
    return out


def _leading_comment(func_start: int, source_bytes: bytes, comments) -> Optional[str]:
    """取紧邻函数上方、仅以空白（含空行）隔开的连续注释块。

    约束：距函数起点不超过 600 字节，避免误吞远处注释。
    """
    result: List[str] = []
    boundary = func_start
    for s, e, t in reversed(comments):
        if e > boundary:
            continue
        gap = source_bytes[e:boundary]
        if gap.strip() == b"" and (boundary - e) <= 600:
            result.append(t)
            boundary = s
        else:
            break
    if not result:
        return None
    return "\n".join(reversed(result))


def _extract_functions_from_tree(root, source_bytes: bytes, filename: str) -> List[FunctionInfo]:
    """遍历语法树，抽取所有函数定义与原型（容错：解析失败/坏树返回空列表）。"""
    if root is None:
        return []
    funcs: List[FunctionInfo] = []
    comments = _collect_comments(root)

    def visit(n):
        if n.type in ("function_definition", "declaration"):
            fd = None
            for c in n.children:
                if c.type == "function_declarator":
                    fd = c
                    break
            if fd is not None:
                info = _build_function(n, fd, source_bytes, comments)
                if info is not None:
                    funcs.append(info)
        for c in n.children:
            visit(c)

    visit(root)
    funcs.sort(key=lambda f: f.byte_start)
    return funcs


def _build_function(node, fd, source_bytes: bytes, comments) -> Optional[FunctionInfo]:
    name_node = _declarator_name(fd)
    if name_node is None:
        return None
    name = name_node.text.decode("utf-8", "replace")
    return_type, storage = _extract_head(node)
    params = _extract_params(_param_list(fd))
    is_def = any(c.type == "compound_statement" for c in node.children)
    leading = _leading_comment(node.start_byte, source_bytes, comments)
    return FunctionInfo(
        name=name,
        return_type=return_type,
        storage_class=storage,
        parameters=params,
        is_definition=is_def,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        byte_start=node.start_byte,
        byte_end=node.end_byte,
        leading_comment=leading,
    )


def extract_functions(source: bytes, filename: str = "<string>") -> dict:
    """从 C 源码抽取全部函数（定义 + 原型），容错、永不抛异常。

    Returns:
        dict: ``{filename, functions:[...as_dict], count, parse_ok}``
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    funcs = _extract_functions_from_tree(res.root_node, source_bytes, filename)
    return {
        "filename": filename,
        "functions": [f.as_dict() for f in funcs],
        "count": len(funcs),
        "parse_ok": res.ok,
    }


def extract_functions_file(path: str, encoding: str = "utf-8") -> dict:
    """从磁盘 C 文件抽取函数（容错、永不抛异常）。

    读取/解码失败时不抛异常：返回 ``functions=[]`` 并标记 ``parse_ok=False``。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return {"filename": path, "functions": [], "count": 0, "parse_ok": False}
    try:
        text = raw.decode(encoding)
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return extract_functions(text.encode("utf-8", "replace"), filename=path)


# ══════════════════════════════════════════════════════════════════
# B1-05 调用图提取
# ══════════════════════════════════════════════════════════════════
# 调用边类型：
#   "call"            → 直接函数调用（call_expression 的 function 是裸标识符）
#   "potential-call"  → 潜在调用（函数指针取址 / 赋值 / 间接调用），不静默丢弃，
#                       交给 B-M2 的 LLM 推断补齐（有 KG 锚定，见 SPRINT §5 风险表）
_CALL_EDGE = "call"
_POTENTIAL_EDGE = "potential-call"


@dataclass
class CallEdge:
    """一条调用边（容错；永不抛异常）。"""

    caller: str
    callee: str
    edge_type: str  # _CALL_EDGE | _POTENTIAL_EDGE
    line: int  # 1-based（call_expression / 取址 / 赋值所在行）
    raw: Optional[str] = None  # potential-call 时记录原始算子文本（如 "(*fp)" / "&handler"）

    def as_dict(self) -> dict:
        return {
            "caller": self.caller,
            "callee": self.callee,
            "edge_type": self.edge_type,
            "line": self.line,
            "raw": self.raw,
        }


@dataclass
class CallGraph:
    """一个 C 文件的调用图（容错；解析失败返回空图 + parse_ok=False）。"""

    filename: str
    functions: List[str]  # 本文件定义的函数名（去重）
    edges: List[CallEdge]
    external_calls: List[str]  # 被 call 但不在本文件定义的函数名（潜在外部依赖）
    parse_ok: bool = True

    @property
    def call_count(self) -> int:
        return sum(1 for e in self.edges if e.edge_type == _CALL_EDGE)

    @property
    def potential_count(self) -> int:
        return sum(1 for e in self.edges if e.edge_type == _POTENTIAL_EDGE)

    def as_dict(self) -> dict:
        return {
            "filename": self.filename,
            "functions": self.functions,
            "edges": [e.as_dict() for e in self.edges],
            "external_calls": self.external_calls,
            "call_count": self.call_count,
            "potential_count": self.potential_count,
            "parse_ok": self.parse_ok,
        }


def _find_func_declarator(node) -> Optional[object]:
    """从 function_definition / declaration 取 function_declarator 子节点。"""
    for c in node.children:
        if c.type == "function_declarator":
            return c
    return None


def _function_definitions(root) -> List[Tuple[str, object]]:
    """返回 [(函数名, function_definition 节点)]（仅顶层，不含原型）。"""
    out: List[Tuple[str, object]] = []

    def visit(n):
        if n.type == "function_definition":
            fd = _find_func_declarator(n)
            nm = _declarator_name(fd) if fd is not None else None
            if nm is not None:
                out.append((nm.text.decode("utf-8", "replace"), n))
        for c in n.children:
            visit(c)

    if root is not None:
        visit(root)
    return out


def _indirect_target(func_child) -> Optional[str]:
    """从间接调用算子（parenthesized / field_expression / pointer 等）提取可能的指针/对象名。

    例如 ``(*fp)`` → ``fp``；``obj.method`` → ``obj``（raw 仍保留完整文本）；
    取不到则返回 None。
    """
    found: List[str] = []

    def collect(n):
        if n.type == "identifier":
            found.append(n.text.decode("utf-8", "replace"))
        for c in n.children:
            collect(c)

    collect(func_child)
    return found[0] if found else None


def _handle_call(call_node, caller: str, edges: List[CallEdge], defined: set) -> None:
    """处理一个 call_expression，产出直接边或潜在边。"""
    line = call_node.start_point[0] + 1
    func_child = None
    for c in call_node.children:
        if c.type == "arguments":
            continue
        if func_child is None:
            func_child = c
    if func_child is None:
        return
    if func_child.type == "identifier":
        callee = func_child.text.decode("utf-8", "replace")
        # 自调用/普通调用统一记 call；外部判定在外层汇总
        edges.append(
            CallEdge(caller=caller, callee=callee, edge_type=_CALL_EDGE, line=line)
        )
    else:
        raw = func_child.text.decode("utf-8", "replace")
        target = _indirect_target(func_child)
        edges.append(
            CallEdge(
                caller=caller,
                callee=target or raw,
                edge_type=_POTENTIAL_EDGE,
                line=line,
                raw=raw,
            )
        )


def _collect_calls(func_node, caller: str, defined: set, edges: List[CallEdge]) -> None:
    """遍历函数体，收集直接调用 + 函数指针取址/赋值（potential-call）。"""
    body = None
    for c in func_node.children:
        if c.type == "compound_statement":
            body = c
            break
    if body is None:
        return

    def visit(n):
        # 不进入嵌套函数定义（若有 gcc 嵌套函数扩展）
        if n is not func_node and n.type == "function_definition":
            return
        if n.type == "call_expression":
            _handle_call(n, caller, edges, defined)
        elif n.type == "pointer_expression":
            # &func ：取址（函数指针作为回调传递）
            operand = None
            for c in n.children:
                if c.type == "identifier":
                    operand = c
            if operand is not None:
                name = operand.text.decode("utf-8", "replace")
                if name in defined:
                    edges.append(
                        CallEdge(
                            caller=caller,
                            callee=name,
                            edge_type=_POTENTIAL_EDGE,
                            line=n.start_point[0] + 1,
                            raw="&" + name,
                        )
                    )
        elif n.type == "init_declarator":
            # T x = func; / void (*fp)(void) = bar; ：初始化器右值是已定义函数名
            ids = [c for c in n.children if c.type == "identifier"]
            has_eq = any(
                c.type == "=" or c.text.decode("utf-8", "replace").strip() == "="
                for c in n.children
            )
            if has_eq and ids:
                rhs = ids[-1].text.decode("utf-8", "replace")
                if rhs in defined:
                    edges.append(
                        CallEdge(
                            caller=caller,
                            callee=rhs,
                            edge_type=_POTENTIAL_EDGE,
                            line=n.start_point[0] + 1,
                            raw="=" + rhs,
                        )
                    )
        elif n.type == "assignment_expression":
            # ptr = func ：右值标识符是已定义函数名 → 潜在调用（指针被赋值）
            ids = [c for c in n.children if c.type == "identifier"]
            if len(ids) >= 2:
                rhs = ids[-1].text.decode("utf-8", "replace")
                if rhs in defined:
                    lhs = ids[0].text.decode("utf-8", "replace")
                    edges.append(
                        CallEdge(
                            caller=caller,
                            callee=rhs,
                            edge_type=_POTENTIAL_EDGE,
                            line=n.start_point[0] + 1,
                            raw=f"{lhs}={rhs}",
                        )
                    )
        for c in n.children:
            visit(c)

    visit(body)


def extract_call_graph(source: bytes, filename: str = "<string>") -> dict:
    """从 C 源码抽取调用图（容错、永不抛异常）。

    边型：
      - ``call``          直接调用（``foo()``）
      - ``potential-call`` 潜在调用（函数指针取址 ``&handler`` / 赋值 ``fp=foo`` /
                          间接调用 ``(*fp)()``、``obj.method()``），显式建模不丢弃。

    ``external_calls``：被 ``call`` 但不在本文件定义的函数名（潜在外部依赖）；
    内部调用（含递归、自调用）不计为 external。

    Returns:
        CallGraph.as_dict()
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    if not res.ok or res.root_node is None:
        return CallGraph(
            filename=filename, functions=[], edges=[], external_calls=[], parse_ok=False
        ).as_dict()
    root = res.root_node
    defs = _function_definitions(root)
    defined = {name for name, _ in defs}
    edges: List[CallEdge] = []
    for name, node in defs:
        _collect_calls(node, name, defined, edges)
    called_direct = {e.callee for e in edges if e.edge_type == _CALL_EDGE}
    external = sorted(called_direct - defined)
    return CallGraph(
        filename=filename,
        functions=sorted(defined),
        edges=edges,
        external_calls=external,
        parse_ok=True,
    ).as_dict()


def extract_call_graph_file(path: str, encoding: str = "utf-8") -> dict:
    """从磁盘 C 文件抽取调用图（容错、永不抛异常）。

    读取/解码失败时不抛异常：返回空图 + ``parse_ok=False``。
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return CallGraph(
            filename=path, functions=[], edges=[], external_calls=[], parse_ok=False
        ).as_dict()
    try:
        text = raw.decode(encoding)
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return extract_call_graph(text.encode("utf-8", "replace"), filename=path)


# ══════════════════════════════════════════════════════════════════
# B1-06 全局状态 + ISR 提取
# ══════════════════════════════════════════════════════════════════
# ISR 命名启发式关键词（大小写不敏感子串匹配）
_ISR_NAME_KEYWORDS = ("isr", "irq", "handler", "interrupt", "vector")


@dataclass
class GlobalVar:
    """一个全局/静态变量（容错）。"""

    name: str
    var_type: str
    storage_class: Optional[str]  # static / extern / None(全局)
    is_volatile: bool
    is_const: bool
    initializer: Optional[str]
    line: int
    byte_start: int
    byte_end: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "var_type": self.var_type,
            "storage_class": self.storage_class,
            "is_volatile": self.is_volatile,
            "is_const": self.is_const,
            "initializer": self.initializer,
            "line": self.line,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
        }


def _is_function_prototype(decl_node) -> bool:
    """顶层 declaration 直接含函数原型（function_declarator 且其 declarator 是裸标识符，
    非函数指针变量 ``void (*h)(void)`` 内 pointer/array 包裹）→ 跳过。

    函数指针变量 ``void (*h)(void);`` 顶层直接子即 function_declarator（内含
    pointer_declarator），不应误判为函数原型。
    """
    for c in decl_node.children:
        if c.type == "function_declarator":
            for sub in c.children:
                if sub.type in (
                    "pointer_declarator",
                    "array_declarator",
                    "parenthesized_declarator",
                ):
                    return False
            return True
    return False


def _var_declarator_info(decl, type_marks: List[str]) -> Optional[str]:
    """从 declarator 抽变量名；指针/数组/函数指针标记追加到 type_marks。

    handled: identifier / pointer_declarator / array_declarator /
    parenthesized_declarator / function_declarator(函数指针变量) /
    qualified_declarator / declarator / init_declarator。
    """
    t = decl.type
    if t == "identifier":
        return decl.text.decode("utf-8", "replace")
    if t == "pointer_declarator":
        type_marks.append("*")
        for c in decl.children:
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    elif t == "array_declarator":
        type_marks.append("[]")
        for c in decl.children:
            if c.type in ("[", "]"):
                continue
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    elif t == "parenthesized_declarator":
        for c in decl.children:
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    elif t == "function_declarator":
        direct_id = next((c for c in decl.children if c.type == "identifier"), None)
        if direct_id is not None:
            type_marks.append("(*)")
            return direct_id.text.decode("utf-8", "replace")
        for c in decl.children:
            if c.type == "parameter_list":
                continue
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    elif t == "qualified_declarator":
        for c in decl.children:
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    elif t in ("declarator", "init_declarator"):
        for c in decl.children:
            if c.type == "=" or c.text.decode("utf-8", "replace").strip() == "=":
                continue
            nm = _var_declarator_info(c, type_marks)
            if nm:
                return nm
    return None


def _initializer_text(init_decl_node, limit: int = 60) -> Optional[str]:
    """从 init_declarator 取 = 后的初始化值文本（常量/字面量），过长截断。"""
    eq_idx = None
    for i, c in enumerate(init_decl_node.children):
        if c.type == "=" or c.text.decode("utf-8", "replace").strip() == "=":
            eq_idx = i
            break
    if eq_idx is None or eq_idx + 1 >= len(init_decl_node.children):
        return None
    val = init_decl_node.children[eq_idx + 1]
    text = val.text.decode("utf-8", "replace").strip()
    if len(text) > limit:
        text = text[:limit] + "..."
    return text


def _extract_globals_from_tree(root, source_bytes: bytes) -> List[GlobalVar]:
    out: List[GlobalVar] = []
    if root is None:
        return out
    for child in root.children:  # translation_unit 顶层
        if child.type != "declaration":
            continue
        if _is_function_prototype(child):
            continue
        storage = None
        type_parts: List[str] = []
        quals: List[str] = []
        for c in child.children:
            if c.type == "storage_class_specifier":
                storage = c.text.decode("utf-8", "replace")
            elif c.type in _QUAL_NODE_TYPES:
                quals.append(c.text.decode("utf-8", "replace"))
            elif c.type in _TYPE_NODE_TYPES:
                type_parts.append(c.text.decode("utf-8", "replace"))
            elif c.type in ("init_declarator", "declarator"):
                type_marks: List[str] = []
                name = _var_declarator_info(c, type_marks)
                if name is None or storage == "typedef":
                    continue  # typedef 别名不记为变量
                init = _initializer_text(c) if c.type == "init_declarator" else None
                var_type = " ".join(quals + type_parts + type_marks).strip()
                out.append(
                    GlobalVar(
                        name=name,
                        var_type=var_type,
                        storage_class=storage,
                        is_volatile="volatile" in quals,
                        is_const="const" in quals,
                        initializer=init,
                        line=child.start_point[0] + 1,
                        byte_start=child.start_byte,
                        byte_end=child.end_byte,
                    )
                )
            elif c.type == "identifier":
                # extern int g_ext; 等无 declarator 包装的顶层变量
                if storage == "typedef":
                    continue
                var_type = " ".join(quals + type_parts).strip()
                out.append(
                    GlobalVar(
                        name=c.text.decode("utf-8", "replace"),
                        var_type=var_type,
                        storage_class=storage,
                        is_volatile="volatile" in quals,
                        is_const="const" in quals,
                        initializer=None,
                        line=child.start_point[0] + 1,
                        byte_start=child.start_byte,
                        byte_end=child.end_byte,
                    )
                )
            elif c.type == "function_declarator":
                # 函数指针变量 void (*g_handler)(void);（非原型，已在上面排除）
                name = _var_declarator_info(c, [])
                if name is None or storage == "typedef":
                    continue
                var_type = " ".join(quals + type_parts + ["(*)"]).strip()
                out.append(
                    GlobalVar(
                        name=name,
                        var_type=var_type,
                        storage_class=storage,
                        is_volatile="volatile" in quals,
                        is_const="const" in quals,
                        initializer=None,
                        line=child.start_point[0] + 1,
                        byte_start=child.start_byte,
                        byte_end=child.end_byte,
                    )
                )
    return out


def _collect_vector_isrs(root, func_names: set) -> set:
    """扫描 init_declarator 初始化器中的函数名（中断向量表注册）→ ISR 候选。"""
    found: set = set()

    def visit(n):
        if n.type == "init_declarator":
            eq_idx = None
            for i, c in enumerate(n.children):
                if c.type == "=" or c.text.decode("utf-8", "replace").strip() == "=":
                    eq_idx = i
                    break
            if eq_idx is not None and eq_idx + 1 < len(n.children):
                val = n.children[eq_idx + 1]

                def scan(o):
                    if o.type == "identifier" and o.text.decode("utf-8", "replace") in func_names:
                        found.add(o.text.decode("utf-8", "replace"))
                    for cc in o.children:
                        scan(cc)

                scan(val)
        for c in n.children:
            visit(c)

    if root is not None:
        visit(root)
    return found


def _attr_isrs(defs) -> set:
    """``__attribute__((interrupt/isr))`` 修饰的函数 → ISR。"""
    found: set = set()
    for name, node in defs:
        for c in node.children:
            if c.type == "attribute_specifier" and (
                "interrupt" in c.text.decode("utf-8", "replace").lower()
                or "isr" in c.text.decode("utf-8", "replace").lower()
            ):
                found.add(name)
    return found


def _extract_isrs_from_tree(root) -> List[dict]:
    if root is None:
        return []
    defs = _function_definitions(root)
    func_names = {n for n, _ in defs}
    by_name: set = set()
    for name, _ in defs:
        low = name.lower()
        if any(k in low for k in _ISR_NAME_KEYWORDS):
            by_name.add(name)
    by_vector = _collect_vector_isrs(root, func_names)
    by_attr = _attr_isrs(defs)
    merged: dict = {}
    for name in by_name:
        merged.setdefault(name, set()).add("name")
    for name in by_vector:
        merged.setdefault(name, set()).add("vector_table")
    for name in by_attr:
        merged.setdefault(name, set()).add("attribute")
    line_of = {n: nd.start_point[0] + 1 for n, nd in defs}
    out = []
    for name in sorted(merged):
        reasons = sorted(merged[name])
        out.append(
            {
                "name": name,
                "line": line_of.get(name, 0),
                "reason": "+".join(reasons),
            }
        )
    return out


def extract_globals(source: bytes, filename: str = "<string>") -> dict:
    """从 C 源码抽取全局/静态变量（容错、永不抛异常）。

    Returns:
        {filename, globals:[GlobalVar.as_dict], count, parse_ok}
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    if not res.ok or res.root_node is None:
        return {"filename": filename, "globals": [], "count": 0, "parse_ok": False}
    g = _extract_globals_from_tree(res.root_node, source_bytes)
    return {
        "filename": filename,
        "globals": [x.as_dict() for x in g],
        "count": len(g),
        "parse_ok": True,
    }


def extract_globals_file(path: str, encoding: str = "utf-8") -> dict:
    """从磁盘 C 文件抽取全局变量（容错、永不抛异常）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return {"filename": path, "globals": [], "count": 0, "parse_ok": False}
    try:
        text = raw.decode(encoding)
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return extract_globals(text.encode("utf-8", "replace"), filename=path)


def extract_isrs(source: bytes, filename: str = "<string>") -> dict:
    """从 C 源码识别 ISR（容错、永不抛异常）。

    识别策略（任一命中即判 ISR）：
      - 命名启发式：函数名含 isr/irq/handler/interrupt/vector（大小写不敏感）
      - 中断向量表：初始化器（数组）中引用的本文件函数
      - ``__attribute__((interrupt/isr))`` 修饰

    Returns:
        {filename, isrs:[{name,line,reason}], count, parse_ok}
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    if not res.ok or res.root_node is None:
        return {"filename": filename, "isrs": [], "count": 0, "parse_ok": False}
    isrs = _extract_isrs_from_tree(res.root_node)
    return {
        "filename": filename,
        "isrs": isrs,
        "count": len(isrs),
        "parse_ok": True,
    }


def extract_isrs_file(path: str, encoding: str = "utf-8") -> dict:
    """从磁盘 C 文件识别 ISR（容错、永不抛异常）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return {"filename": path, "isrs": [], "count": 0, "parse_ok": False}
    try:
        text = raw.decode(encoding)
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return extract_isrs(text.encode("utf-8", "replace"), filename=path)


# ══════════════════════════════════════════════════════════════════
# B1-07 宏处理策略（stddef/stdint 白名单 + 函数式宏实体 + #ifdef 分支全解析）
# ══════════════════════════════════════════════════════════════════
# 设计目标（验收 B1-07）：
#   - stddef/stdint 等标准库常见宏走白名单，不记为 KG 实体（避免噪声）。
#   - 项目自定义**函数式宏**记 macro entity，且给「低置信度」（D4: 宏重度 = 0.35），
#     因为宏展开后真实语义需 B-M2 的 LLM 推断补齐。
#   - 对象宏（带值）记 macro entity，置信度 0.9（clean）。
#   - ``#ifdef`` / ``#ifndef`` / ``#if`` / ``#elif`` / ``#else`` / ``#endif``
#     分支**全解析**并标注每个分支的「编译激活条件」（active_condition），
#     供逆向分析判断某段代码所属配置。
#
# 置信度取值对齐 B1-10 决策点 D4（三级流转阈值）：
#   clean = 0.9 / 含 ERROR 节点 = 0.5（此处宏无语法错概念，统一 clean 级） /
#   宏重度 = 0.35。
_MACRO_CONF_FUNCTION = 0.35   # 函数式宏 / 空定义（flag 宏）：低置信度
_MACRO_CONF_OBJECT = 0.90      # 带值对象宏：高置信度

# stddef / stdint / 标准库常见宏白名单（对象宏，不记为实体）。
# 含精确名集合 + 整数极值宏模式（INT*_MAX / UINT*_MIN / SIZE_MAX ...）。
_STD_MACRO_WHITELIST = frozenset({
    # stddef.h
    "NULL", "nullptr", "offsetof", "max_align_t",
    # stdbool.h / 通用布尔
    "true", "false", "TRUE", "FALSE", "bool",
    # 断言 / 编译器内建
    "assert", "static_assert", "_Static_assert",
    "__FILE__", "__LINE__", "__func__", "__FUNCTION__",
    "__DATE__", "__TIME__", "__COUNTER__", "__cplusplus",
    "_MSC_VER", "__GNUC__", "__GNUC_MINOR__", "__GNUC_PATCHLEVEL__",
    # 平台/编译器属性常用对象宏
    "WIN32", "WIN64", "_WIN32", "_WIN64", "__linux__", "__APPLE__",
    "INT_MAX", "INT_MIN", "UINT_MAX",
    "LONG_MAX", "LONG_MIN", "ULONG_MAX",
    "LLONG_MAX", "LLONG_MIN", "ULLONG_MAX",
    "SIZE_MAX", "PTRDIFF_MAX", "PTRDIFF_MIN",
    "INTPTR_MAX", "INTPTR_MIN", "UINTPTR_MAX",
    "INTMAX_MAX", "INTMAX_MIN", "UINTMAX_MAX",
    "WCHAR_MAX", "WCHAR_MIN", "WINT_MAX", "WINT_MIN",
    "CHAR_BIT", "MB_LEN_MAX",     "SIG_ATOMIC_MAX", "SIG_ATOMIC_MIN",
})

# 整数宽度极值宏模式：INT8_MAX / UINT16_MIN / INT_LEAST32_MAX / UINT_FAST64_MAX /
# SIZE_MAX / INTPTR_MIN / INTMAX_MAX / PTRDIFF_MIN ...（含 INT_LEAST/INT_FAST 的下划线）
_RE_INT_MACRO = re.compile(
    r"^(?:[U]?INT(?:_LEAST|_FAST)?[0-9]+|SIZE|PTRDIFF|INTPTR|UINTPTR|"
    r"INTMAX|UINTMAX|WCHAR|WINT|SIG_ATOMIC)_(?:MAX|MIN)$"
)


def _is_object_macro_whitelisted(name: str) -> bool:
    """对象宏是否落入标准库白名单（精确名或整数极值宏模式）。"""
    if name in _STD_MACRO_WHITELIST:
        return True
    return bool(_RE_INT_MACRO.match(name))


@dataclass
class MacroInfo:
    """一个宏定义（容错提取）。

    - ``kind``: ``"object"``（对象宏，``#define X v``）/ ``"function"``（函数式宏）/
      ``"empty"``（flag 宏，``#define FLAG`` 无值）。
    - ``confidence``: B1-10 置信度初值（函数式/flag=0.35，带值对象=0.9）。
    - ``is_whitelisted``: 仅对「被白名单跳过」的宏为真（此类不入库，仅统计）。
    """

    name: str
    kind: str  # "object" | "function" | "empty"
    params: List[str]        # 函数式宏参数名（对象宏为空）
    body: Optional[str]      # 宏体（对象宏值 / 函数式展开）；flag 宏为 None
    line: int
    byte_start: int
    byte_end: int
    is_whitelisted: bool
    confidence: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "params": list(self.params),
            "body": self.body,
            "line": self.line,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "is_whitelisted": self.is_whitelisted,
            "confidence": self.confidence,
        }


@dataclass
class ConditionalInfo:
    """条件编译的一个分支（``#ifdef``/``#if``/... 全解析的产出之一）。

    一个条件块（``#ifdef X ... #else ... #endif``）会产出多个分支：
    consequent（主分支）/ elif / else，每个分支含**编译激活条件**标注。

    - ``block_id``: 同一条件块的所有分支共享（用于聚合）。
    - ``branch_role``: ``"consequent"`` | ``"elif"`` | ``"else"``。
    - ``condition``: 该分支原始条件文本（如 ``X`` / ``defined(Z) && A>0``）。
    - ``active_condition``: 该分支**被编译**时的逻辑条件（含前置分支取反），
      例如 else 分支 = ``!(X)``，elif 分支 = ``!(X) && (Y)``。
    - ``depth``: 嵌套深度（顶层 0）。
    """

    block_id: int
    directive: str        # "ifdef" | "ifndef" | "if" | "elif" | "else"
    branch_role: str      # "consequent" | "elif" | "else"
    condition: Optional[str]
    active_condition: Optional[str]
    start_line: int
    end_line: int
    depth: int

    def as_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "directive": self.directive,
            "branch_role": self.branch_role,
            "condition": self.condition,
            "active_condition": self.active_condition,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "depth": self.depth,
        }


def _conditional_expr_text(node) -> Optional[str]:
    """从条件指令节点取条件表达式文本。

    ``#ifdef X`` / ``#ifndef X`` → 标识符名 ``X``；
    ``#if expr`` / ``#elif expr`` → expr 子树文本（binary_expression /
    preproc_defined / number_literal / identifier ...）。
    """
    # 跳过首个子节点（指令 token：#ifdef/#if/#ifndef/#elif）
    for c in node.children:
        if c.type in ("#ifdef", "#ifndef", "#if", "#elif"):
            continue
        # 条件表达式通常是 identifier / binary_expression / preproc_defined /
        # number_literal / parenthesized_expression 等
        return c.text.decode("utf-8", "replace").strip()
    return None


def _find_endif_line(node) -> int:
    """找条件块的 #endif 行（递归，取块子树内首个 #endif）。"""
    stack = [node]
    while stack:
        n = stack.pop()
        for c in n.children:
            if c.type == "#endif":
                return c.start_point[0] + 1
            stack.append(c)
    return node.start_point[0] + 1


def _collect_branch_nodes(node) -> List[object]:
    """收集一个条件块的**全部分支节点**（含嵌套的 #elif/#else）。

    tree-sitter-c 的 if/elif/else 为**右嵌套**结构：``#if`` 块根的直接子含首个
    ``preproc_elif``；该 ``preproc_elif`` 内部又含下一个 ``preproc_elif``/``preproc_else``，
    依此类推（``#else`` 总是嵌在最后一个 ``preproc_elif`` 内）。本函数沿此链顺序收集，
    返回 ``[块根(if/ifdef/ifndef), 首个 elif..., 末个 else?]``。

    行区间用相邻分支节点的起始行与 ``#endif`` 行推算，无需展开分支内容。
    """
    branches = [node]
    cur = node
    while True:
        nxt = None
        for c in cur.children:
            if c.type in ("preproc_elif", "preproc_else"):
                nxt = c
                break
        if nxt is None:
            break
        branches.append(nxt)
        cur = nxt
    return branches


def _process_conditional_block(node, depth: int, block_id: int, out: List[ConditionalInfo]) -> None:
    """解析单个条件块的各分支，写入 ``out``。

    分支节点经 ``_collect_branch_nodes`` 收集（含右嵌套的 #elif/#else）；
    ``#endif``（匿名节点，type 即 "#endif"）为终止。每个分支标注
    「编译激活条件」（active_condition，含前置分支取反）。

    注意：tree-sitter-c 把 ``#ifndef`` 也解析成 ``preproc_ifdef`` 节点，
    仅首个子 token 文本为 ``#ifndef``（与 ``#ifdef`` 区分）。因此指令类型
    必须读首个子 token，不能依赖 ``node.type``。
    """
    directive_line = node.start_point[0] + 1
    first_tok = node.children[0].text.decode("utf-8", "replace") if node.children else ""
    if first_tok == "#ifndef":
        directive = "ifndef"
    elif first_tok == "#ifdef":
        directive = "ifdef"
    else:
        directive = "if"  # preproc_if
    endif_line = _find_endif_line(node)

    branches = _collect_branch_nodes(node)

    # 各分支的「规范化条件」（用于激活条件取反拼接）
    branch_conds: List[Optional[str]] = []
    for bi, bnode in enumerate(branches):
        if bi == 0:
            raw = _conditional_expr_text(node)
            if directive == "ifdef":
                norm = raw
            elif directive == "ifndef":
                norm = ("!" + raw) if raw else None
            else:
                norm = raw
        else:
            if bnode.type == "preproc_elif":
                norm = _conditional_expr_text(bnode)
            else:  # preproc_else
                norm = None
        branch_conds.append(norm)

    for bi, bnode in enumerate(branches):
        if bi == 0:
            role = "consequent"
            drtv = directive
            cond = _conditional_expr_text(node)
            active = branch_conds[0]
            start_line = directive_line + 1
        else:
            if bnode.type == "preproc_elif":
                role = "elif"
                drtv = "elif"
                cond = _conditional_expr_text(bnode)
            else:
                role = "else"
                drtv = "else"
                cond = None
            # 激活条件：前置所有分支（consequent + 之前 elif）取反 且 本分支条件
            prior = [x for x in branch_conds[:bi] if x]
            selfc = branch_conds[bi]
            parts = []
            if prior:
                parts.append("!(" + " || ".join(prior) + ")")
            if selfc:
                parts.append(selfc)
            active = " && ".join(parts) or None
            start_line = bnode.start_point[0] + 1
        # 行区间：到下一分支起始行前一行，或 #endif 前一行
        if bi + 1 < len(branches):
            end_line = branches[bi + 1].start_point[0]  # 下一分支 0-based 行 = 本分支结束(1-based)
        else:
            end_line = endif_line - 1
        out.append(
            ConditionalInfo(
                block_id=block_id,
                directive=drtv,
                branch_role=role,
                condition=cond,
                active_condition=active,
                start_line=start_line,
                end_line=end_line,
                depth=depth,
            )
        )


def _extract_conditionals_from_tree(root) -> List[ConditionalInfo]:
    out: List[ConditionalInfo] = []
    if root is None:
        return out
    counter = {"id": 0}

    def walk(n, depth: int) -> None:
        for c in n.children:
            if c.type in ("preproc_ifdef", "preproc_if"):
                counter["id"] += 1
                _process_conditional_block(c, depth, counter["id"], out)
                walk(c, depth + 1)  # 进入块内找嵌套条件
            else:
                walk(c, depth)

    walk(root, 0)
    return out


def _extract_macros_from_tree(root, source_bytes: bytes) -> Tuple[List[MacroInfo], List[str]]:
    """遍历语法树，抽取所有宏定义（对象/函数式/flag），容错永不抛。

    Returns:
        (记录为实体的 MacroInfo 列表, 被白名单跳过的宏名列表)
    """
    macros: List[MacroInfo] = []
    skipped: List[str] = []
    if root is None:
        return macros, skipped

    def walk(n) -> None:
        for c in n.children:
            if c.type == "preproc_function_def":
                name = None
                params: List[str] = []
                body = None
                for sub in c.children:
                    if sub.type == "identifier":
                        name = sub.text.decode("utf-8", "replace")
                    elif sub.type == "preproc_params":
                        for p in sub.children:
                            if p.type == "identifier":
                                params.append(p.text.decode("utf-8", "replace"))
                    elif sub.type == "preproc_arg":
                        body = sub.text.decode("utf-8", "replace").strip()
                if name is not None:
                    macros.append(
                        MacroInfo(
                            name=name,
                            kind="function",
                            params=params,
                            body=body,
                            line=c.start_point[0] + 1,
                            byte_start=c.start_byte,
                            byte_end=c.end_byte,
                            is_whitelisted=False,
                            confidence=_MACRO_CONF_FUNCTION,
                        )
                    )
            elif c.type == "preproc_def":
                name = None
                body = None
                for sub in c.children:
                    if sub.type == "identifier":
                        name = sub.text.decode("utf-8", "replace")
                    elif sub.type == "preproc_arg":
                        body = sub.text.decode("utf-8", "replace").strip()
                if name is not None:
                    if _is_object_macro_whitelisted(name):
                        skipped.append(name)
                    else:
                        kind = "empty" if body is None else "object"
                        conf = _MACRO_CONF_FUNCTION if body is None else _MACRO_CONF_OBJECT
                        macros.append(
                            MacroInfo(
                                name=name,
                                kind=kind,
                                params=[],
                                body=body,
                                line=c.start_point[0] + 1,
                                byte_start=c.start_byte,
                                byte_end=c.end_byte,
                                is_whitelisted=False,
                                confidence=conf,
                            )
                        )
            else:
                walk(c)

    walk(root)
    macros.sort(key=lambda m: m.byte_start)
    return macros, skipped


def extract_macros(source: bytes, filename: str = "<string>") -> dict:
    """从 C 源码抽取宏定义与条件编译分支（容错、永不抛异常）。

    宏策略（验收 B1-07）：
      - 标准库白名单宏（stddef/stdint 等）跳过实体化，仅计入 ``whitelisted_skipped``。
      - 函数式宏 / flag 宏 → macro entity，置信度 0.35（低）。
      - 带值对象宏 → macro entity，置信度 0.9。
      - ``#ifdef`` 等条件分支全解析，每个分支标注 ``active_condition``。

    Returns:
        {filename, macros:[MacroInfo.as_dict], macros_count,
         whitelisted_skipped:[...], conditionals:[ConditionalInfo.as_dict],
         conditionals_count, parse_ok}
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    if not res.ok or res.root_node is None:
        return {
            "filename": filename,
            "macros": [],
            "macros_count": 0,
            "whitelisted_skipped": [],
            "conditionals": [],
            "conditionals_count": 0,
            "parse_ok": False,
        }
    macros, skipped = _extract_macros_from_tree(res.root_node, source_bytes)
    conds = _extract_conditionals_from_tree(res.root_node)
    return {
        "filename": filename,
        "macros": [m.as_dict() for m in macros],
        "macros_count": len(macros),
        "whitelisted_skipped": sorted(set(skipped)),
        "conditionals": [c.as_dict() for c in conds],
        "conditionals_count": len(conds),
        "parse_ok": True,
    }


def extract_macros_file(path: str, encoding: str = "utf-8") -> dict:
    """从磁盘 C 文件抽取宏与条件编译分支（容错、永不抛异常）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except Exception:
        return {
            "filename": path,
            "macros": [],
            "macros_count": 0,
            "whitelisted_skipped": [],
            "conditionals": [],
            "conditionals_count": 0,
            "parse_ok": False,
        }
    try:
        text = raw.decode(encoding)
    except Exception:
        text = raw.decode("latin-1", errors="replace")
    return extract_macros(text.encode("utf-8", "replace"), filename=path)


def extract_c_ast(source: bytes, filename: str = "<string>") -> dict:
    """一次性解析并提取全部 C AST 信息（函数/全局/ISR/宏/调用图），**单次 parse**。

    供 ``c_code_scanner`` / ``reverse`` CLI / B1-10 KG 入库复用，避免每个提取器
    重复 parse 同一份源码。容错永不抛异常。

    Returns:
        {
          filename, parse_ok, error_rate,
          functions:[FunctionInfo.as_dict], globals:[GlobalVar.as_dict],
          isrs:[{...}], macros:[MacroInfo.as_dict], whitelisted_skipped:[...],
          call_graph:{functions, edges, external_calls, call_count, potential_count}
        }
    """
    if not isinstance(source, (bytes, bytearray)):
        try:
            source = source.encode("utf-8")
        except Exception:
            source = str(source).encode("utf-8", "replace")
    source_bytes = bytes(source)
    res = parse(source_bytes, filename=filename)
    if not res.ok or res.root_node is None:
        return {
            "filename": filename,
            "parse_ok": False,
            "error_rate": (res.error_rate if res.ok else 1.0),
            "functions": [],
            "globals": [],
            "isrs": [],
            "macros": [],
            "whitelisted_skipped": [],
            "call_graph": {
                "functions": [],
                "edges": [],
                "external_calls": [],
                "call_count": 0,
                "potential_count": 0,
            },
        }
    root = res.root_node
    funcs = [f.as_dict() for f in _extract_functions_from_tree(root, source_bytes, filename)]
    g = [x.as_dict() for x in _extract_globals_from_tree(root, source_bytes)]
    isrs = _extract_isrs_from_tree(root)
    macros, skipped = _extract_macros_from_tree(root, source_bytes)
    # 调用图：复用内部 defs + _collect_calls（不二次 parse）
    defs = _function_definitions(root)
    defined = {name for name, _ in defs}
    edges: List[CallEdge] = []
    for name, node in defs:
        _collect_calls(node, name, defined, edges)
    called_direct = {e.callee for e in edges if e.edge_type == _CALL_EDGE}
    external = sorted(called_direct - defined)
    cg = {
        "functions": sorted(defined),
        "edges": [e.as_dict() for e in edges],
        "external_calls": external,
        "call_count": sum(1 for e in edges if e.edge_type == _CALL_EDGE),
        "potential_count": sum(1 for e in edges if e.edge_type == _POTENTIAL_EDGE),
    }
    return {
        "filename": filename,
        "parse_ok": True,
        "error_rate": res.error_rate,
        "functions": funcs,
        "globals": g,
        "isrs": isrs,
        "macros": [m.as_dict() for m in macros],
        "whitelisted_skipped": sorted(set(skipped)),
        "call_graph": cg,
    }


__all__ = [
    "CParseResult",
    "ErrorNode",
    "parse",
    "parse_file",
    "FunctionInfo",
    "FunctionParam",
    "extract_functions",
    "extract_functions_file",
    "CallEdge",
    "CallGraph",
    "extract_call_graph",
    "extract_call_graph_file",
    "GlobalVar",
    "extract_globals",
    "extract_globals_file",
    "extract_isrs",
    "extract_isrs_file",
    "MacroInfo",
    "ConditionalInfo",
    "extract_macros",
    "extract_macros_file",
    "extract_c_ast",
]
