#!/usr/bin/env python3

# @req RS-015
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Codegen failure case store — records codegen failures for RAG retrieval.

Every failed codegen run is stored as a structured failure case in the KB.
Before a new repair round the engine queries similar past failures to prime
the LLM repair prompt with "what we tried before and why it failed".

Usage in CodegenEngine:
    from yuleosh.kb.codegen_failures import CodegenFailureStore
    failure_store = CodegenFailureStore()
    # After generate():
    if result.status == "failed":
        failure_store.record_failure(project_id, session_id, result, "c")
    # Before repair:
    cases = failure_store.find_similar(result.last_errors, language="c")
    hint = failure_store.format_for_prompt(cases)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from .store import KbStore

if TYPE_CHECKING:
    from yuleosh.codegen.engine import CodegenResult

_SOURCE = "codegen_failure"


@dataclass
class CodegenFailureCase:
    id: int
    project_id: str
    session_id: str
    error_signature: str
    error_text: str
    language: str
    round_count: int
    strategy_used: str
    resolution: str
    created_at: Optional[datetime]


def _dedup_ref(project_id: str, error_signature: str) -> str:
    return hashlib.sha256(
        f"{project_id}|{error_signature}".encode("utf-8")
    ).hexdigest()[:16]


def _short_sig(errors: str) -> str:
    # Strip digits and all symbols (backticks, quotes, brackets, ...) —
    # keep letters and underscores so C symbols like HAL_Init survive.
    text = re.sub(r"[\d\W]+", " ", errors or "")
    words = [w for w in text.split() if len(w) > 3][:6]
    return " ".join(words) or "unknown"


def _keywords(text: str) -> list[str]:
    text = re.sub(r"[\d\W]+", " ", text or "")
    return [w for w in text.split() if len(w) > 4][:8]


class CodegenFailureStore:
    """Records and retrieves codegen failure cases via KbStore."""

    def __init__(
        self, kb_store: Optional[KbStore] = None, db_path: Optional[str] = None
    ) -> None:
        self._store = kb_store or KbStore(db_path=db_path)

    def record_failure(
        self,
        project_id: str,
        session_id: str,
        result: "CodegenResult",
        language: str = "",
    ) -> None:
        """Store a failed codegen result. Dedup by (project_id, error_signature)."""
        error_sig = (
            result.brainstorm.get("strategy", "") if result.brainstorm else ""
        ) or _short_sig(result.last_errors)
        strategy = (result.brainstorm or {}).get("strategy", "")
        dedup_ref = _dedup_ref(project_id, error_sig)

        content = json.dumps({
            "project_id": project_id,
            "session_id": session_id,
            "error_signature": error_sig,
            "error_text": result.last_errors,
            "language": language,
            "round_count": result.rounds,
            "strategy_used": strategy,
            "resolution": "unresolved",
        }, ensure_ascii=False)

        # Dedup: check source_ref for existing entry with same dedup_ref
        existing = self._store.list_articles(
            search=dedup_ref[:12], limit=10
        )
        for art in existing:
            if art.source == _SOURCE and (art.source_ref or "").startswith(dedup_ref):
                self._store.update_article(art.id, {"content": content})
                return

        self._store.create_article({
            "title": f"CodegenFail {project_id[:20]} {error_sig[:40]}",
            "content": content,
            "source": _SOURCE,
            "source_ref": dedup_ref,
            # dedup_ref 同时写入 tags —— FTS 索引只覆盖 title/content/tags，
            # 不含 source_ref；trigram 短语匹配可命中前缀，供去重检查使用。
            "tags": f"codegen_failure lang:{language} strategy:{strategy} ref:{dedup_ref}",
        })

    def record_resolution(self, session_id: str, resolution: str) -> None:
        """Update matching failure cases with a resolution note."""
        articles = self._store.list_articles(search=session_id[:20], limit=20)
        for art in articles:
            if art.source != _SOURCE:
                continue
            try:
                data = json.loads(art.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if data.get("session_id") == session_id:
                data["resolution"] = resolution
                self._store.update_article(
                    art.id,
                    {"content": json.dumps(data, ensure_ascii=False)},
                )

    def find_similar(
        self,
        error_text: str,
        language: str = "",
        limit: int = 5,
    ) -> list[CodegenFailureCase]:
        """Search for past failure cases similar to *error_text*."""
        kws = _keywords(error_text)
        if not kws:
            return []
        # FTS trigram 短语匹配要求关键词连续出现 —— 原始错误文本常含
        # stop words（"implicit declaration OF function"），多词短语会漏匹配。
        # 因此用首个关键词检索 + Python 侧全关键词过滤（词序无关）。
        articles = self._store.list_articles(search=kws[0], limit=limit * 8)
        cases: list[CodegenFailureCase] = []
        for art in articles:
            if art.source != _SOURCE:
                continue
            try:
                data = json.loads(art.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if language and data.get("language") and data["language"] != language:
                continue
            stored = (data.get("error_text") or "").lower()
            if not all(kw in stored for kw in kws):
                continue
            cases.append(CodegenFailureCase(
                id=art.id,
                project_id=data.get("project_id", ""),
                session_id=data.get("session_id", ""),
                error_signature=data.get("error_signature", ""),
                error_text=data.get("error_text", ""),
                language=data.get("language", ""),
                round_count=int(data.get("round_count", 0)),
                strategy_used=data.get("strategy_used", ""),
                resolution=data.get("resolution", "unresolved"),
                created_at=art.created_at,
            ))
            if len(cases) >= limit:
                break
        return cases

    def format_for_prompt(
        self, cases: list[CodegenFailureCase], max_chars: int = 2000
    ) -> str:
        """Format cases as a 'Past Similar Failures' block for LLM repair prompts."""
        if not cases:
            return ""
        lines = ["## Past Similar Failures\n"]
        total = len(lines[0])
        for c in cases:
            entry = (
                f"- Error: {c.error_signature}\n"
                f"  Rounds: {c.round_count}  Strategy: {c.strategy_used or 'none'}\n"
                f"  Resolution: {c.resolution}\n"
                f"  Detail: {c.error_text[:200]}\n"
            )
            if total + len(entry) > max_chars:
                break
            lines.append(entry)
            total += len(entry)
        return "\n".join(lines)
