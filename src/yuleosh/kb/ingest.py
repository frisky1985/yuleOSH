# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
Ingestion pipeline — 项目文档摄取为可检索知识（EI-M3D）。

流程: 项目文件 → 分块 → embedding → 写入 kb 向量表 + kb_articles。

设计:
- 摄取源（EI-M3D.1）: docs/spec.md, TASK_STATUS.md, requirements/, lessons, fmea
- 分块（EI-M3D.2）: 按标题/段落/表格，500-1000 tokens 目标，重叠 10%
- 增量（EI-M3D.3）: content hash 判定变更，文件删除同步清理索引
- 触发（EI-M3D.4）: 手动 ``yuleosh kb ingest <project>``；git hook / CI 后处理
  由外部接线（本模块提供可调用 API）。

依赖: KbStore（articles）+ VectorStore（向量）+ EmbeddingProvider（向量化）。
无 Ollama/无 sqlite-vec 时优雅降级：只写 kb_articles（关键词可检索），
向量层跳过（EI-M3C.4）。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("kb.ingest")

# 默认摄取源（项目根相对路径，EI-M3D.1）
DEFAULT_SOURCES = [
    "docs/spec.md",
    "TASK_STATUS.md",
    "requirements/",
]

# 分块参数（EI-M3D.2）
CHUNK_TARGET_TOKENS = 700  # 500-1000 中间值
CHUNK_OVERLAP_TOKENS = 70  # ~10%
CHUNK_MAX_CHARS = 3000
CHUNK_OVERLAP_CHARS = 300


@dataclass
class Chunk:
    """分块结果。"""

    source: str          # 文件路径（相对项目根）
    title: str           # 分块标题（文件基名 + 标题层级）
    content: str         # 分块正文
    content_hash: str    # 内容 hash（增量判定键）
    seq: int = 0         # 文件内分块序号


@dataclass
class IngestReport:
    """摄取报告。"""

    sources: list[str] = field(default_factory=list)
    chunks: int = 0
    articles_written: int = 0
    vectors_written: int = 0
    skipped_unchanged: int = 0
    removed_stale: int = 0
    errors: list[str] = field(default_factory=list)


# ── 分块（EI-M3D.2）───────────────────────────────────────────────────

def _token_estimate(text: str) -> int:
    """粗略 token 估算（中文按字、英文按词，1 token ≈ 2 字符保守）。"""
    return max(1, len(text) // 2)


def chunk_text(source: str, content: str) -> list[Chunk]:
    """把文件内容按标题/段落分块（EI-M3D.2）。

    策略: 按标题（## / ### 等）切分；无标题时按段落；仍超长则按字符
    窗口切分（重叠 CHUNK_OVERLAP_CHARS）。
    """
    if not content.strip():
        return []
    chunks: list[Chunk] = []

    # 1) 按标题切分
    title_pattern = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
    matches = list(title_pattern.finditer(content))
    segments: list[tuple[str, str]] = []
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            segments.append((m.group(2), content[start:end].strip()))
    else:
        segments = [("", content.strip())]

    for title, seg in segments:
        if not seg:
            continue
        # 2) 段内超长按段落/窗口切分
        if _token_estimate(seg) <= CHUNK_TARGET_TOKENS and len(seg) <= CHUNK_MAX_CHARS:
            chunks.append(_make_chunk(source, title, seg))
        else:
            chunks.extend(_split_long(source, title, seg))
    return chunks


def _make_chunk(source: str, title: str, content: str) -> Chunk:
    from yuleosh.kb.store import KbStore
    return Chunk(
        source=source,
        title=title or Path(source).name,
        content=content,
        content_hash=KbStore._content_hash(content),
    )


def _split_long(source: str, title: str, content: str) -> list[Chunk]:
    """超长段按字符窗口切分（重叠 10%）。"""
    chunks: list[Chunk] = []
    start = 0
    seq = 0
    while start < len(content):
        end = start + CHUNK_MAX_CHARS
        seg = content[start:end]
        # 优先在段落边界截断
        if end < len(content):
            boundary = seg.rfind("\n\n")
            if boundary > CHUNK_MAX_CHARS * 0.5:
                end = start + boundary
                seg = content[start:end]
        chunks.append(_make_chunk(source, f"{title} [{seq}]", seg))
        seq += 1
        step = max(1, CHUNK_MAX_CHARS - CHUNK_OVERLAP_CHARS)
        if end <= start:
            break
        start = end - CHUNK_OVERLAP_CHARS if end < len(content) else len(content)
    return chunks


# ── 摄取主流程（EI-M3D.3/.4）──────────────────────────────────────────

def collect_source_paths(project_dir: str | Path,
                         extra: list[str] | None = None) -> list[Path]:
    """收集摄取源文件路径（EI-M3D.1）。目录递归收集 *.md。"""
    project_dir = Path(project_dir)
    sources = list(DEFAULT_SOURCES) + (extra or [])
    paths: list[Path] = []
    for src in sources:
        p = project_dir / src
        if p.is_dir():
            paths.extend(sorted(p.rglob("*.md")))
        elif p.exists() and p.is_file():
            paths.append(p)
    return paths


def ingest_project(project_dir: str | Path,
                   store,
                   embedding_provider=None,
                   vector_store=None,
                   extra_sources: list[str] | None = None) -> IngestReport:
    """摄取项目文档（主入口，EI-M3D）。

    增量: 每分块 content_hash 已存在于 kb_articles → 跳过（EI-M3D.3）。
    删除: 源文件消失但 kb 有该 source 记录 → 清理（由调用方决定，见
    ingest_project_incremental 的 remove_stale）。
    """
    report = IngestReport()
    project_dir = Path(project_dir)
    sources = collect_source_paths(project_dir, extra_sources)
    report.sources = [str(s.relative_to(project_dir)) for s in sources]

    for path in sources:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            report.errors.append(f"{path}: {e}")
            continue
        rel = str(path.relative_to(project_dir))
        chunks = chunk_text(rel, content)
        if not chunks:
            continue
        for chunk in chunks:
            # 增量判定：同 hash 已存在 → 跳过（EI-M3D.3）
            if _exists(store, chunk.content_hash):
                report.skipped_unchanged += 1
                continue
            article = store.create_article({
                "title": f"[{chunk.source}] {chunk.title}",
                "content": chunk.content,
                "source": "ingest",
                "source_ref": chunk.source,
                "tags": "ingest",
            })
            report.articles_written += 1
            # 向量写入（可用时）
            if embedding_provider is not None and vector_store is not None:
                try:
                    vecs = embedding_provider.embed([chunk.content])
                    if vecs and vector_store.upsert(
                        chunk.content_hash, vecs[0], rowid=article.id,
                    ):
                        report.vectors_written += 1
                except Exception as e:  # noqa: BLE001 — 向量失败不影响文章写入
                    log.warning("vector write failed for %s: %s", rel, e)
                    report.errors.append(f"vector:{rel}: {e}")
        report.chunks += len(chunks)
    return report


def remove_stale_articles(project_dir: str | Path, store) -> int:
    """清理已消失源文件的摄取记录（EI-M3D.3 文件删除同步）。

    删除 source='ingest' 且 source_ref 不在当前源文件集合中的文章。
    返回删除数。
    """
    project_dir = Path(project_dir)
    current_sources = {
        str(s.relative_to(project_dir)) for s in collect_source_paths(project_dir)
    }
    removed = 0
    for article in store.list_articles(limit=10000):
        if article.source == "ingest" and article.source_ref not in current_sources:
            if store.delete_article(article.id):
                removed += 1
    return removed


def _exists(store, content_hash: str) -> bool:
    """content_hash 是否已入库（增量判定）。"""
    conn = store._get_conn()
    cur = conn.execute(
        "SELECT 1 FROM kb_articles WHERE content_hash = ? LIMIT 1",
        (content_hash,),
    )
    return cur.fetchone() is not None
