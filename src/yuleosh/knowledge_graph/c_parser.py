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
