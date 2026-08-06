# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH Memory ↔ LLM context bridge.

Assembles project memory (structured facts + session history) into a
compact, de-duplicated, length-capped context block for injection into
LLM system prompts — the "project memory" knowledge source in
``docs/llm-strategy.md``.

Design notes:
- Retrieval is non-destructive: facts are read with ``reinforce=False``
  so automatic injection never inflates trust/recall counts (only
  explicit user recalls reinforce).
- The output is capped by ``max_chars`` so memory context can never
  blow the token budget — it sits alongside RAG context and is governed
  by the same non-fatal degradation rule (any failure → empty context +
  warning, the LLM call proceeds).
"""

import logging
import os
import re
from dataclasses import dataclass

from yuleosh.memory.store import MemoryStore

log = logging.getLogger("llm.memory_context")

# Global switch: YULEOSH_MEMORY_LLM_ENABLED (default "1" = enabled)
_ENV_ENABLED = "YULEOSH_MEMORY_LLM_ENABLED"
_FALSE_VALUES = {"0", "false", "no", "off", ""}

# Words that carry no retrieval signal — dropped when tokenizing a
# natural-language LLM prompt before token-level recall.
_STOPWORDS = {
    "what", "which", "where", "when", "who", "how", "why", "the", "and",
    "are", "was", "were", "for", "with", "that", "this", "please", "can",
    "you", "tell", "me", "about", "give", "explain", "describe", "list",
    "show", "write", "using", "use", "need", "want", "should", "would",
    "could", "does", "do", "did", "have", "has", "had", "not", "but",
    "from", "into", "over", "under", "then", "than", "also", "very",
}


def _query_tokens(query: str) -> list[str]:
    """Extract retrieval-significant tokens from a query/prompt.

    Lowercases, keeps alphanumeric tokens of ≥3 chars, drops stopwords.
    """
    words = re.findall(r"[A-Za-z0-9_]{3,}", query.lower())
    return [w for w in words if w not in _STOPWORDS]


def is_memory_context_enabled() -> bool:
    """Global on/off switch for memory → LLM context injection.

    Reads ``YULEOSH_MEMORY_LLM_ENABLED`` (default "1" → enabled).
    """
    raw = os.environ.get(_ENV_ENABLED, "1")
    return raw.strip().lower() not in _FALSE_VALUES


@dataclass
class MemoryContextItem:
    """A single retrieved memory item (fact or session entry)."""

    source: str  # "fact" | "session"
    item_id: int
    content: str
    entity: str = ""
    category: str = ""
    tags: str = ""
    trust: float = 0.0
    kind: str = ""
    created_at: str = ""


class MemoryContextAssembler:
    """Retrieve, de-duplicate and cap project memory for LLM injection.

    Usage::

        assembler = MemoryContextAssembler()
        context = assembler.assemble("UART DMA driver")
        # → "## Project Memory\\n\\nRetrieved 3 item(s) ..."
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        max_facts: int = 5,
        max_sessions: int = 3,
        max_chars: int = 2000,
    ):
        self._store = store or MemoryStore()
        self.max_facts = max(1, int(max_facts))
        self.max_sessions = max(1, int(max_sessions))
        self.max_chars = max(200, int(max_chars))

    # ── Retrieval ──────────────────────────────────────────────────────

    def _recall_facts(self, query: str) -> list[dict]:
        """Recall facts, whole-query first with token-level fallback.

        Never reinforces trust (``reinforce=False``) — automatic
        injection must not inflate recall counts.
        """
        results = self._store.recall(
            query, limit=self.max_facts, reinforce=False
        )
        if not results:
            for tok in _query_tokens(query):
                results.extend(
                    self._store.recall(
                        tok, limit=self.max_facts, reinforce=False
                    )
                )
        return results

    def _search_sessions(self, query: str) -> list[dict]:
        """Search sessions, whole-query first with token-level fallback.

        Token fallback uses FTS5 prefix queries (``tok*``) so e.g.
        "deploy" reaches "deployment"; malformed queries degrade to
        LIKE inside ``search_sessions``.
        """
        results = self._store.search_sessions(query, limit=self.max_sessions)
        if not results:
            for tok in _query_tokens(query):
                results.extend(
                    self._store.search_sessions(
                        f"{tok}*", limit=self.max_sessions
                    )
                )
        return results

    def retrieve(self, query: str) -> list[MemoryContextItem]:
        """Retrieve facts + sessions for ``query``.

        Facts first (sorted by trust), then sessions (newest first).
        Identical content (case-insensitive) is kept once — the first
        occurrence wins. Each source is capped by its own limit.
        """
        items: list[MemoryContextItem] = []
        seen: set = set()

        # Facts: de-dupe by id + content, sort trust desc, cap max_facts.
        fact_items: list[MemoryContextItem] = []
        seen_ids: set = set()
        for f in self._recall_facts(query):
            if f["id"] in seen_ids:
                continue
            seen_ids.add(f["id"])
            key = f["content"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            fact_items.append(
                MemoryContextItem(
                    source="fact",
                    item_id=f["id"],
                    content=f["content"],
                    entity=f.get("entity", ""),
                    category=f.get("category", ""),
                    tags=f.get("tags", ""),
                    trust=float(f.get("trust", 0.0) or 0.0),
                    created_at=f.get("created_at", ""),
                )
            )
        fact_items.sort(key=lambda i: i.trust, reverse=True)
        items.extend(fact_items[: self.max_facts])

        # Sessions: de-dupe by content, sort newest first, cap max_sessions.
        session_items: list[MemoryContextItem] = []
        for s in self._search_sessions(query):
            key = s["content"].strip().lower()
            if key in seen:
                continue
            seen.add(key)
            session_items.append(
                MemoryContextItem(
                    source="session",
                    item_id=s["id"],
                    content=s.get("snippet") or s["content"],
                    kind=s.get("kind", ""),
                    created_at=s.get("created_at", ""),
                )
            )
        session_items.sort(key=lambda i: i.created_at, reverse=True)
        items.extend(session_items[: self.max_sessions])

        return items

    # ── Formatting ─────────────────────────────────────────────────────

    def format_context(self, items: list[MemoryContextItem]) -> str:
        """Render items as a markdown context block ("" when empty)."""
        if not items:
            return ""
        lines = [
            "## Project Memory",
            "",
            (
                f"Retrieved {len(items)} item(s) from project memory "
                "(facts + session history)."
            ),
            "",
        ]
        facts = [i for i in items if i.source == "fact"]
        sessions = [i for i in items if i.source == "session"]

        if facts:
            lines.append("### Memory Facts")
            lines.append("")
            for i in facts:
                meta = []
                if i.entity:
                    meta.append(f"entity={i.entity}")
                if i.category and i.category != "general":
                    meta.append(f"category={i.category}")
                if i.tags:
                    meta.append(f"tags={i.tags}")
                if i.trust:
                    meta.append(f"trust={i.trust:.2f}")
                suffix = f" ({', '.join(meta)})" if meta else ""
                lines.append(f"- [fact #{i.item_id}] {i.content}{suffix}")
            lines.append("")

        if sessions:
            lines.append("### Session History")
            lines.append("")
            for i in sessions:
                kind = i.kind or "note"
                lines.append(
                    f"- [session #{i.item_id} ({kind})] {i.content}"
                )
            lines.append("")

        return "\n".join(lines)

    # ── Assemble ───────────────────────────────────────────────────────

    def assemble(self, query: str) -> str:
        """Retrieve + format + enforce ``max_chars`` cap. "" when empty.

        Truncation keeps the final block within the configured budget so
        injected memory can never exceed the token-budget guardrails.
        """
        context = self.format_context(self.retrieve(query))
        if not context:
            return ""
        if len(context) <= self.max_chars:
            return context
        return context[: self.max_chars].rstrip() + "\n…[truncated by max_chars]"


# ── Convenience: default assembler singleton + one-shot helper ─────────

_default_assembler: MemoryContextAssembler | None = None


def get_default_assembler() -> MemoryContextAssembler:
    """Get or create the default assembler (lazy singleton)."""
    global _default_assembler
    if _default_assembler is None:
        _default_assembler = MemoryContextAssembler()
    return _default_assembler


def assemble_memory_context(
    query: str,
    max_facts: int = 5,
    max_sessions: int = 3,
    max_chars: int = 2000,
) -> str:
    """One-shot helper: project memory as a capped context block.

    Honors the ``YULEOSH_MEMORY_LLM_ENABLED`` global switch. Any
    retrieval error degrades to "" (non-fatal) — the caller's LLM call
    must proceed regardless.
    """
    if not is_memory_context_enabled():
        return ""
    try:
        return MemoryContextAssembler(
            max_facts=max_facts,
            max_sessions=max_sessions,
            max_chars=max_chars,
        ).assemble(query)
    except Exception as e:  # noqa: BLE001 — non-fatal by design
        log.warning("Memory context retrieval failed (non-fatal): %s", e)
        return ""
