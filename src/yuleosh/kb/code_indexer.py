# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Code indexer — 项目源码索引到 KB 向量库（P1: 代码级语义索引）。

Pipeline 生成代码后，自动将源文件索引到 KB，使后续步骤可通过 RAG
检索项目自身代码上下文（函数签名、类定义、文档字符串）。

设计:
- 索引粒度: 文件级（非函数级），RAG 检索时上下文更完整
- 索引内容: 文件路径 + 语言 + 函数签名列表 + 类定义 + 文档字符串摘要
- 索引源: src/ 目录（C/C++/Python），排除测试文件和生成文件
- 增量索引: content_hash 判定变更，未变文件跳过（复用 kb_articles 去重）
- 向量写入: 可选，依赖 embedding_provider + vector_store
- 优雅降级: 无向量扩展时只写 kb_articles（关键词检索仍可用）

与 knowledge_graph 的关系:
- knowledge_graph/code_scanner.py 提取函数/类到 KG 节点（图结构）
- 本模块提取同样的信息到 KB 文章（文本检索）
- 两者互补: KG 用于调用图/依赖分析，KB 用于语义搜索/RAG
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("kb.code_indexer")

# 源文件扩展名
_C_EXTENSIONS = {".c", ".h"}
_PYTHON_EXTENSIONS = {".py"}
_ALL_EXTENSIONS = _C_EXTENSIONS | _PYTHON_EXTENSIONS

# 排除目录
_EXCLUDED_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "build", "dist", ".yuleosh", "artifacts",
}

# 排除文件模式
_EXCLUDED_PATTERNS = {
    r"test_.*\.py$",       # 测试文件
    r".*_test\.py$",       # 测试文件（后缀）
    r"conftest\.py$",      # pytest 配置
    r".*\.min\..*",        # 压缩文件
    r".*generated.*",      # 生成文件
}


@dataclass
class CodeIndexReport:
    """索引报告。"""

    files_scanned: int = 0
    files_indexed: int = 0
    files_skipped_unchanged: int = 0
    files_skipped_excluded: int = 0
    vectors_written: int = 0
    errors: list[str] = field(default_factory=list)


# ── 代码解析 ────────────────────────────────────────────────────────────

def _extract_python_signatures(filepath: Path) -> dict:
    """从 Python 文件提取函数/类签名（AST 解析）。

    返回:
        {
            "functions": [{"name": str, "line": int, "docstring": str}],
            "classes": [{"name": str, "line": int, "methods": [str]}],
        }
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, OSError) as e:
        log.debug("Failed to parse %s: %s", filepath, e)
        return {"functions": [], "classes": []}

    functions: list[dict] = []
    classes: list[dict] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "line": node.lineno,
                "docstring": ast.get_docstring(node) or "",
            })
        elif isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in ast.iter_child_nodes(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "methods": methods,
                "docstring": ast.get_docstring(node) or "",
            })

    return {"functions": functions, "classes": classes}


def _extract_c_signatures(filepath: Path) -> dict:
    """从 C/H 文件提取函数签名（正则解析）。

    返回:
        {"functions": [{"name": str, "line": int, "signature": str}]}
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        log.debug("Failed to read %s: %s", filepath, e)
        return {"functions": []}

    # C 函数定义/声明正则（简化版，覆盖常见模式）。
    # 2026-11-02: 结尾接受 `;` — .h 头文件里的 API 声明以分号结尾,
    # 只匹配 `{`/行尾会把整个头文件 API 契约漏提 (C 索引核心价值)。
    C_FUNC_RE = re.compile(
        r"^"
        r"(?:static\s+|extern\s+|inline\s+)?"
        r"(?:const\s+|volatile\s+)?"
        r"(\w[\w\s\*]+?)"        # 返回类型
        r"\s+"
        r"(\w[\w\d_]*)"          # 函数名
        r"\s*\(([^;{}]*)\)"      # 参数列表
        r"\s*(?:\{|;|$)",        # 函数体开始 / 声明分号 / 行尾
        re.MULTILINE,
    )

    _CONTROL_KW = {
        "if", "else", "for", "while", "do", "switch", "case",
        "return", "typedef", "struct", "enum", "union",
    }

    functions: list[dict] = []
    lines = source.split("\n")

    for i, line in enumerate(lines, 1):
        m = C_FUNC_RE.match(line)
        if m:
            ret_type = m.group(1).strip()
            name = m.group(2)
            params = m.group(3).strip()
            if name not in _CONTROL_KW and ret_type:
                signature = f"{ret_type} {name}({params})"
                functions.append({
                    "name": name,
                    "line": i,
                    "signature": signature,
                })

    return {"functions": functions}


def _build_index_content(rel_path: str, language: str, signatures: dict) -> str:
    """构建索引内容（用于 KB 文章正文）。

    格式:
        File: <path>
        Language: <lang>

        Functions:
        - <name> (line <N>): <docstring/signature>

        Classes:
        - <name> (line <N>): methods: <m1>, <m2>, ...
    """
    lines = [f"File: {rel_path}", f"Language: {language}", ""]

    # 函数部分
    funcs = signatures.get("functions", [])
    if funcs:
        lines.append("Functions:")
        for f in funcs:
            name = f["name"]
            line_no = f["line"]
            # Python: docstring; C: signature
            detail = f.get("docstring") or f.get("signature") or ""
            if detail:
                # 取第一行
                first_line = detail.split("\n")[0].strip()
                lines.append(f"- {name} (line {line_no}): {first_line}")
            else:
                lines.append(f"- {name} (line {line_no})")
        lines.append("")

    # 类部分
    classes = signatures.get("classes", [])
    if classes:
        lines.append("Classes:")
        for c in classes:
            name = c["name"]
            line_no = c["line"]
            methods = c.get("methods", [])
            if methods:
                method_list = ", ".join(methods[:5])  # 最多 5 个方法
                if len(methods) > 5:
                    method_list += f" ... (+{len(methods) - 5} more)"
                lines.append(f"- {name} (line {line_no}): methods: {method_list}")
            else:
                lines.append(f"- {name} (line {line_no})")

    return "\n".join(lines)


# ── 文件遍历 ────────────────────────────────────────────────────────────

def _should_exclude(filepath: Path) -> bool:
    """判断文件是否应排除。"""
    # 排除目录
    for part in filepath.parts:
        if part in _EXCLUDED_DIRS:
            return True

    # 排除文件模式
    filename = filepath.name
    for pattern in _EXCLUDED_PATTERNS:
        if re.match(pattern, filename):
            return True

    return False


def _collect_source_files(project_dir: Path) -> list[Path]:
    """收集项目源文件（src/ 目录，递归）。"""
    src_dir = project_dir / "src"
    if not src_dir.exists():
        return []

    files: list[Path] = []
    for ext in _ALL_EXTENSIONS:
        for f in src_dir.rglob(f"*{ext}"):
            if not _should_exclude(f):
                files.append(f)

    return sorted(files)


# ── 主入口 ──────────────────────────────────────────────────────────────

def index_project_code(
    project_dir: str | Path,
    store,
    embedding_provider=None,
    vector_store=None,
    tenant_org: str = "",
) -> CodeIndexReport:
    """索引项目源码到 KB（主入口）。

    Args:
        project_dir: 项目根目录
        store: KbStore 实例
        embedding_provider: 嵌入提供者（可选）
        vector_store: VectorStore 实例（可选）
        tenant_org: 租户标识（可选）

    Returns:
        CodeIndexReport: 索引报告
    """
    report = CodeIndexReport()
    project_dir = Path(project_dir)
    source_files = _collect_source_files(project_dir)

    if not source_files:
        log.info("No source files found in %s/src/", project_dir)
        return report

    # 批量向量写入队列（P1 优化：减少事务次数）
    vector_batch: list[dict] = []

    for filepath in source_files:
        report.files_scanned += 1

        try:
            # 确定语言
            ext = filepath.suffix
            if ext in _PYTHON_EXTENSIONS:
                language = "python"
                signatures = _extract_python_signatures(filepath)
            elif ext in _C_EXTENSIONS:
                language = "c" if ext == ".c" else "c_header"
                signatures = _extract_c_signatures(filepath)
            else:
                report.files_skipped_excluded += 1
                continue

            # 构建索引内容
            rel_path = str(filepath.relative_to(project_dir))
            content = _build_index_content(rel_path, language, signatures)

            # 计算 content_hash（用于增量判定）
            from yuleosh.kb.store import KbStore
            content_hash = KbStore._content_hash(content)

            # 增量判定 (2026-11-02, 反假陈旧): 按 (source, source_ref)
            # 定位**该文件**的既有索引, 而非全局 content_hash 去重 —
            # 内容未变 → 跳过; 已变 (函数改名/签名修改/文件移动) → 先删
            # 旧条目 (文章 + 向量) 再插新的。全局 hash 去重会让旧签名
            # 永驻 KB, RAG 回注给 LLM 的代码上下文包含已删除的 API。
            conn = store._get_conn()
            cur = conn.execute(
                "SELECT id, content_hash FROM kb_articles "
                "WHERE source = 'code_index' AND source_ref = ?",
                (rel_path,),
            )
            existing = cur.fetchall()
            if any(row["content_hash"] == content_hash for row in existing):
                report.files_skipped_unchanged += 1
                continue
            if existing:
                stale_hashes = [row["content_hash"] for row in existing]
                for row in existing:
                    store.delete_article(row["id"])
                if vector_store is not None:
                    try:
                        vector_store.remove_by_content_hashes(stale_hashes)
                    except Exception as e:  # noqa: BLE001 — 清理失败不阻断索引
                        log.warning(
                            "Stale vector cleanup failed for %s: %s", rel_path, e
                        )
                log.info(
                    "Re-indexing %s: removed %d stale article(s)",
                    rel_path, len(existing),
                )

            # 创建 KB 文章
            title = f"[code:{language}] {rel_path}"
            article = store.create_article({
                "title": title,
                "content": content,
                "source": "code_index",
                "source_ref": rel_path,
                "tags": f"code,{language}",
                "tenant_org": tenant_org,
            })
            report.files_indexed += 1

            # 向量写入（批量，P1 优化）
            if embedding_provider is not None and vector_store is not None:
                vector_batch.append({
                    "content_hash": content_hash,
                    "embedding": None,  # 延迟计算
                    "rowid": article.id,
                    "_content": content,  # 内部使用
                })

        except Exception as e:
            log.warning("Failed to index %s: %s", filepath, e)
            report.errors.append(f"{filepath}: {e}")

    # 批量嵌入 + 写入向量（P1 优化：减少 embedding API 调用次数）
    if vector_batch and embedding_provider is not None and vector_store is not None:
        try:
            # 提取所有文本
            texts = [item.pop("_content") for item in vector_batch]
            # 批量嵌入
            embeddings = embedding_provider.embed(texts)
            if embeddings:
                # 填充 embedding 向量
                for item, emb in zip(vector_batch, embeddings):
                    item["embedding"] = emb
                # 批量写入
                written = vector_store.batch_upsert(vector_batch)
                report.vectors_written = written
        except Exception as e:
            log.warning("Batch vector indexing failed (non-fatal): %s", e)
            report.errors.append(f"batch_vector: {e}")

    log.info(
        "Code indexing complete: %d scanned, %d indexed, %d skipped (unchanged), "
        "%d vectors written",
        report.files_scanned,
        report.files_indexed,
        report.files_skipped_unchanged,
        report.vectors_written,
    )

    return report
