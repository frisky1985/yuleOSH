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
__all__ = ["CParseResult", "ErrorNode", "parse", "parse_file"]
