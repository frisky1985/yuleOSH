# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Knowledge Base data models — dataclasses for kb_articles, lessons, fmea_entries."""

import html.parser
import re

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class KbArticle:
    """A knowledge base entry (MISRA violations, best practices, etc.)."""
    id: Optional[int] = None
    title: str = ""
    content: str = ""
    source: str = ""
    source_ref: str = ""
    tags: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "source_ref": self.source_ref,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KbArticle":
        """Deserialize from a dict (from JSON body or DB row)."""
        created = d.get("created_at")
        updated = d.get("updated_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if isinstance(updated, str):
            updated = datetime.fromisoformat(updated)
        return cls(
            id=d.get("id"),
            title=d.get("title", ""),
            content=d.get("content", ""),
            source=d.get("source", ""),
            source_ref=d.get("source_ref", ""),
            tags=d.get("tags", ""),
            created_at=created,
            updated_at=updated,
        )


@dataclass
class Lesson:
    """A lessons-learned entry."""
    id: Optional[int] = None
    title: str = ""
    problem: str = ""
    solution: str = ""
    root_cause: str = ""
    project_id: str = ""
    severity: str = "medium"
    # 工单→Lesson 闭环：关联改进工单 (IMP-xxx) 与需求 (REQ-xxx)
    ticket_id: str = ""
    requirement_id: str = ""
    created_at: Optional[datetime] = None

    VALID_SEVERITIES = {"low", "medium", "high", "critical"}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "problem": self.problem,
            "solution": self.solution,
            "root_cause": self.root_cause,
            "project_id": self.project_id,
            "severity": self.severity,
            "ticket_id": self.ticket_id,
            "requirement_id": self.requirement_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Lesson":
        created = d.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        sev = d.get("severity", "medium")
        if sev not in cls.VALID_SEVERITIES:
            sev = "medium"
        return cls(
            id=d.get("id"),
            title=d.get("title", ""),
            problem=d.get("problem", ""),
            solution=d.get("solution", ""),
            root_cause=d.get("root_cause", ""),
            project_id=d.get("project_id", ""),
            severity=sev,
            ticket_id=d.get("ticket_id", ""),
            requirement_id=d.get("requirement_id", ""),
            created_at=created,
        )


@dataclass
class FmeaEntry:
    """A FMEA entry (simplified)."""
    id: Optional[int] = None
    item: str = ""
    failure_mode: str = ""
    effect: str = ""
    cause: str = ""
    severity: int = 1
    occurence: int = 1
    detection: int = 1
    rpn: int = 0  # GENERATED: severity * occurence * detection
    recommendation: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        self._compute_rpn()

    def _compute_rpn(self):
        self.rpn = self.severity * self.occurence * self.detection

    def to_dict(self) -> dict:
        self._compute_rpn()
        return {
            "id": self.id,
            "item": self.item,
            "failure_mode": self.failure_mode,
            "effect": self.effect,
            "cause": self.cause,
            "severity": self.severity,
            "occurence": self.occurence,
            "detection": self.detection,
            "rpn": self.rpn,
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FmeaEntry":
        created = d.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return cls(
            id=d.get("id"),
            item=d.get("item", ""),
            failure_mode=d.get("failure_mode", ""),
            effect=d.get("effect", ""),
            cause=d.get("cause", ""),
            severity=d.get("severity", 1),
            occurence=d.get("occurence", 1),
            detection=d.get("detection", 1),
            recommendation=d.get("recommendation", ""),
            created_at=created,
        )



def _strip_html(text: str) -> str:
    """Remove HTML tags and dangerous patterns from text (XSS write-path guard).

    M-1 (ARC-W6 / Fix 12, route A — 小明拍板 2026-08-02): the old regex
    blacklist (known dangerous tags + event attributes + script protocols)
    could be bypassed by nested / mixed-case / entity-obfuscated variants.
    This implementation parses with ``html.parser`` (stdlib) instead:
      - all KNOWN HTML tags are stripped; text content of benign tags is kept
        (``<b>hello</b>`` -> ``hello``);
      - dangerous tag BLOCKS (script/iframe/svg/...) are dropped entirely
        including their content;
      - tags that are NOT known HTML (code samples like ``<vector>``,
        ``<int>``) survive as literal text — unless they contain dangerous
        substrings, in which case the fragment is dropped;
      - a final regex pass neutralizes anything that survived as literal
        text (e.g. entity double-encoding ``&#106;avascript:``).

    KNOWN LIMITATION (documented): html.parser is a sanitizer, NOT a
    security boundary.  The frontend render-time escaping (escape-first,
    X-01) remains the primary XSS defense; this is defense-in-depth on the
    write path.
    """
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    stripper = _HTMLStripper()
    stripper.feed(text)
    stripper.close()
    cleaned = "".join(stripper._out)
    # Post-pass (defense in depth): neutralize dangerous patterns that
    # survived as literal text (entity double-encoding, residual fragments).
    cleaned = re.sub(r'<script[^>]*?>.*?</script>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<iframe[^>]*?>.*?</iframe>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<object[^>]*?>.*?</object>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<svg[^>]*?>.*?</svg>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<math[^>]*?>.*?</math>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<img\b[^>]*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<meta\b[^>]*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<link\b[^>]*>', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<base\b[^>]*>', '', cleaned, flags=re.IGNORECASE)
    # Event handler attributes — quoted, unquoted, backtick, mixed-case
    cleaned = re.sub(r'\s+on\w+\s*=\s*"[^"]*"', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+on\w+\s*=\s*'[^']*'", '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+on\w+\s*=\s*`[^`]*`', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+on\w+\s*=\s*[^\s"\'`>]+', '', cleaned, flags=re.IGNORECASE)
    # Script protocols (incl. HTML-entity obfuscation, e.g. &#106;avascript:)
    cleaned = re.sub(r'javascript\s*:', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'&#(?:x6a|106|X6A);\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t\s*:', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'vbscript\s*:', '', cleaned, flags=re.IGNORECASE)
    return cleaned


# ── M-1: html.parser whitelist stripper ────────────────────────────────────

# Dangerous tag BLOCKS — the tag shell AND its content are dropped entirely.
# These are never valid inside markdown-ish KB text, and their content is
# the payload carrier (script bodies, svg onload, etc.).
_DROP_CONTENT_TAGS = frozenset({
    "script", "style", "iframe", "object", "svg", "math",
    "video", "audio", "template", "form", "noscript", "applet",
    "frameset", "frame", "portal", "head", "title",
})

# Void/self-closing dangerous tags — the tag shell is dropped, but they
# CANNOT contain content so they must never enter the drop-depth state
# (an unclosed ``<img>`` would otherwise swallow every following line of
# legitimate text).  This matches the pre-M-1 regex behavior which removed
# only the ``<img ...>`` token itself.
_DROP_VOID_TAGS = frozenset({
    "img", "embed", "input", "meta", "link", "base", "source",
    "track", "area",
})

# Known benign HTML tags — shell stripped, inner TEXT preserved.
_STRIP_SHELL_TAGS = frozenset({
    "a", "abbr", "address", "article", "aside", "b", "bdi", "bdo",
    "big", "blockquote", "body", "br", "button", "caption", "center",
    "cite", "code", "col", "colgroup", "data", "datalist", "dd", "del",
    "details", "dfn", "dialog", "dir", "div", "dl", "dt", "em",
    "fieldset", "figcaption", "figure", "font", "footer", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "html", "i",
    "ins", "kbd", "label", "legend", "li", "main", "map", "mark",
    "menu", "menuitem", "meter", "nav", "nobr", "ol", "optgroup",
    "option", "output", "p", "param", "picture", "pre", "progress",
    "q", "rp", "rt", "ruby", "s", "samp", "section", "select",
    "small", "span", "strike", "strong", "sub", "summary", "sup",
    "table", "tbody", "td", "textarea", "tfoot", "th", "thead", "time",
    "tr", "tt", "u", "ul", "var", "wbr", "xmp",
})

# Dirty substrings: unknown tags containing any of these are dropped whole
# instead of being preserved as literal text (obfuscated tag names such as
# ``scr<script``, event attributes, script protocols).
_DIRTY_TAG_RE = re.compile(
    r"script|iframe|svg|math|object|embed|form|style|template|video|audio|"
    r"meta|link|base|applet|frame|frameset|portal|on[a-z]+\s*=|javascript:|vbscript:",
    re.IGNORECASE,
)


class _HTMLStripper(html.parser.HTMLParser):
    """Whitelist-style HTML stripper (M-1).

    - known dangerous tags -> drop shell AND content (tracked depth);
    - known benign tags    -> drop shell, keep inner text;
    - unknown tags         -> keep as literal text if clean, else drop
      (code samples like ``<vector>``/``<int>`` survive, obfuscated tag
      names like ``<scr<script>`` do not).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._drop_depth = 0

    @staticmethod
    def _clean_unknown(raw: str) -> bool:
        return not _DIRTY_TAG_RE.search(raw)

    def _emit_unknown(self, raw: str) -> None:
        if self._clean_unknown(raw):
            self._out.append(raw)
        # else: drop the dirty fragment entirely — no residue.

    def handle_starttag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in _DROP_CONTENT_TAGS:
            self._drop_depth += 1
        elif t in _DROP_VOID_TAGS:
            return  # drop the shell; no content to track
        elif t not in _STRIP_SHELL_TAGS:
            # Unknown tag: preserve as literal text only when clean.
            self._emit_unknown(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag: str, attrs) -> None:
        t = tag.lower()
        if t in _DROP_CONTENT_TAGS or t in _DROP_VOID_TAGS or t in _STRIP_SHELL_TAGS:
            return
        self._emit_unknown(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
        elif t in _DROP_VOID_TAGS:
            return  # stray </img> etc. — drop silently
        elif t not in _STRIP_SHELL_TAGS:
            raw = f"</{tag}>"
            if self._clean_unknown(raw):
                self._out.append(raw)

    def handle_data(self, data: str) -> None:
        if self._drop_depth == 0:
            self._out.append(data)

    # Comments / declarations / processing instructions: HTMLParser's
    # defaults are no-ops (never forwarded to handle_data), so they are
    # dropped automatically.


def sanitize_kb_article_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a KbArticle."""
    allowed = {"title", "content", "source", "source_ref", "tags"}
    cleaned = {}
    for k, v in body.items():
        if k in allowed and isinstance(v, str):
            cleaned[k] = _strip_html(v)
    return cleaned


def sanitize_lesson_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a Lesson."""
    allowed = {"title", "problem", "solution", "root_cause", "project_id", "severity",
               "ticket_id", "requirement_id"}
    cleaned = {}
    for k, v in body.items():
        if k in allowed:
            if isinstance(v, str):
                cleaned[k] = _strip_html(v)
            else:
                cleaned[k] = v
    sev = cleaned.get("severity", "medium")
    if sev not in Lesson.VALID_SEVERITIES:
        cleaned["severity"] = "medium"
    return cleaned


def sanitize_fmea_fields(body: dict) -> dict:
    """Extract and validate only the allowed fields for a FmeaEntry."""
    allowed = {"item", "failure_mode", "effect", "cause", "severity",
               "occurence", "detection", "recommendation"}
    cleaned = {}
    for k in allowed:
        if k in body:
            if isinstance(body[k], str):
                cleaned[k] = _strip_html(body[k])
            else:
                cleaned[k] = body[k]
    # Clamp numeric ratings to 1-10
    for num_field in ("severity", "occurence", "detection"):
        val = cleaned.get(num_field, 1)
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = 1
        cleaned[num_field] = max(1, min(10, val))
    return cleaned
