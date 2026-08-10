# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""KnowledgeIndexer — 沉淀知识自动收集 + 人工确认生效（方案 B, 2026-08-07）。

每次"新沉淀"（lesson / memory fact / KB article / skill / KG edge）通过
:meth:`KnowledgeIndexer.record` 自动进入"待生效"索引（``.yuleosh/knowledge-pending.json``），
由人工 ``yuleosh knowledge approve`` 确认后转入"生效"索引
（``.yuleosh/knowledge-active.json``）。pipeline 注入层（方案 A 的
``assemble_pipeline_knowledge``）只读生效索引；pending 条目仅在
``inject_pending=true`` 时带 ``[pending-review]`` 标注进入注入。

设计规则（方案 B 契约）:

- **hash 去重**：同一 (kind, content) 不重复入列（sha256 of kind+content）。
- **幂等不循环**：record 只写索引文件，不 emit 事件；更新索引本身不触发新事件。
- **人工门槛**：approve / reject 是唯一流转通道（四专家 P1-6：不做全自动自进化）。
- **审计**：每次 approve / reject 写 ``.yuleosh/knowledge-audit.log``（JSONL）。
- **非致命**：索引损坏/IO 失败降级为警告，绝不让沉淀/注入流程崩溃。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("yuleosh.knowledge.indexer")

# 相对 OSH_HOME（或传入 project_dir）的索引文件路径。
PENDING_RELPATH = ".yuleosh/knowledge-pending.json"
ACTIVE_RELPATH = ".yuleosh/knowledge-active.json"
AUDIT_RELPATH = ".yuleosh/knowledge-audit.log"

# 支持的沉淀类型（与 LoopEventType 沉淀事件一一对应）。
SUPPORTED_KINDS = {
    "lesson_create",
    "memory_remember",
    "kb_article_created",
    "skill_created",
    "kg_edge_merged",
}


def _now() -> str:
    """ISO-8601 UTC 时间戳。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _content_hash(kind: str, content: str) -> str:
    """去重哈希：kind + 规范化 content。"""
    raw = f"{kind}:{content.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _resolve_project_dir(project_dir: Optional[str | Path] = None) -> Path:
    """项目根目录：显式传入 > OSH_HOME > 仓库根（当前文件推断）。"""
    if project_dir is not None:
        return Path(project_dir).resolve()
    env = os.environ.get("OSH_HOME")
    if env:
        return Path(env).resolve()
    # src/yuleosh/knowledge/indexer.py → 仓库根
    return Path(__file__).resolve().parent.parent.parent.parent


def _load_json(path: Path) -> list[dict]:
    """Read a JSON list, tolerating missing/corrupt files (non-fatal)."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Index file unreadable (%s), starting fresh: %s", path, e)
        return []


def _write_json(path: Path, items: list[dict]) -> None:
    """Atomically write a JSON list (tmp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


class KnowledgeIndexer:
    """待生效/生效知识索引 + 人工确认流转。"""

    def __init__(self, project_dir: Optional[str | Path] = None):
        self.project_dir = _resolve_project_dir(project_dir)
        self.pending_path = self.project_dir / PENDING_RELPATH
        self.active_path = self.project_dir / ACTIVE_RELPATH
        self.audit_path = self.project_dir / AUDIT_RELPATH

    # ── 写入 ─────────────────────────────────────────────────────────

    def record(
        self,
        kind: str,
        content: str,
        source: str = "",
        meta: Optional[dict] = None,
    ) -> dict | None:
        """记录一条新沉淀到待生效索引（hash 去重，幂等）。

        返回新条目 dict（重复时返回 None 且不写文件）。
        """
        if kind not in SUPPORTED_KINDS:
            log.warning("Unsupported knowledge kind %r — ignored", kind)
            return None
        content = (content or "").strip()
        if not content:
            log.warning("Empty knowledge content ignored (kind=%s)", kind)
            return None

        entry_hash = _content_hash(kind, content)
        pending = _load_json(self.pending_path)
        active = _load_json(self.active_path)
        for item in pending + active:
            if item.get("hash") == entry_hash:
                log.info("Duplicate knowledge skipped (hash=%s)", entry_hash)
                return None

        entry = {
            "hash": entry_hash,
            "kind": kind,
            "content": content,
            "source": source,
            "meta": meta or {},
            "created_at": _now(),
            "status": "pending",
        }
        pending.append(entry)
        try:
            _write_json(self.pending_path, pending)
        except OSError as e:
            log.warning("Failed to write pending index (non-fatal): %s", e)
            return None
        log.info("Recorded %s → pending (hash=%s)", kind, entry_hash)
        return entry

    # ── 查询 ─────────────────────────────────────────────────────────

    def list_pending(self) -> list[dict]:
        """列出待生效条目（新的在前）。"""
        items = _load_json(self.pending_path)
        return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)

    def list_active(self) -> list[dict]:
        """列出已生效条目（新的在前）。"""
        items = _load_json(self.active_path)
        return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)

    def _find_pending(self, item_id: str) -> Optional[dict]:
        """按 hash 或序号定位 pending 条目。"""
        for i, item in enumerate(_load_json(self.pending_path)):
            if item.get("hash") == item_id or str(i) == item_id:
                return item
        return None

    # ── 流转 ─────────────────────────────────────────────────────────

    def approve(self, item_id: Optional[str] = None, all_: bool = False) -> int:
        """人工确认：pending → active。

        ``item_id`` 为 hash（或序号）；``all_=True`` 全部批准。
        返回批准条数；每条写审计日志。
        """
        pending = _load_json(self.pending_path)
        if all_:
            selected = list(pending)
        elif item_id:
            item = self._find_pending(item_id)
            selected = [item] if item else []
            if not selected:
                log.info("No pending item matches %r", item_id)
                return 0
        else:
            log.info("approve requires --all or an item id")
            return 0

        approved = []
        remaining = list(pending)
        for item in selected:
            if item in remaining:
                remaining.remove(item)
                item["status"] = "active"
                item["approved_at"] = _now()
                approved.append(item)

        active = _load_json(self.active_path)
        active.extend(approved)
        try:
            _write_json(self.pending_path, remaining)
            _write_json(self.active_path, active)
        except OSError as e:
            log.warning("Failed to persist approval (non-fatal): %s", e)
            return 0

        for item in approved:
            self._audit("approve", item)
        return len(approved)

    def reject(self, item_id: Optional[str] = None, all_: bool = False) -> int:
        """人工否决：从 pending 移除（不进入 active）。

        ``item_id`` 为 hash（或序号）；``all_=True`` 全部否决。
        返回否决条数；每条写审计日志。
        """
        pending = _load_json(self.pending_path)
        if all_:
            selected = list(pending)
        elif item_id:
            item = self._find_pending(item_id)
            selected = [item] if item else []
            if not selected:
                log.info("No pending item matches %r", item_id)
                return 0
        else:
            log.info("reject requires --all or an item id")
            return 0

        remaining = list(pending)
        rejected = []
        for item in selected:
            if item in remaining:
                remaining.remove(item)
                rejected.append(item)

        try:
            _write_json(self.pending_path, remaining)
        except OSError as e:
            log.warning("Failed to persist rejection (non-fatal): %s", e)
            return 0

        for item in rejected:
            self._audit("reject", item)
        return len(rejected)

    # ── 审计 ─────────────────────────────────────────────────────────

    def _audit(self, action: str, item: dict) -> None:
        """写 JSONL 审计行（approve/reject）。"""
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                {
                    "ts": _now(),
                    "action": action,
                    "hash": item.get("hash", ""),
                    "kind": item.get("kind", ""),
                    "content": item.get("content", ""),
                },
                ensure_ascii=False,
            )
            with self.audit_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            log.warning("Failed to write audit log (non-fatal): %s", e)

    def audit_log(self, limit: int = 50) -> list[dict]:
        """读取审计日志（新的在前）。"""
        if not self.audit_path.exists():
            return []
        lines: list[dict] = []
        try:
            for line in self.audit_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError as e:
            log.warning("Audit log unreadable: %s", e)
            return []
        return list(reversed(lines))[:limit]
