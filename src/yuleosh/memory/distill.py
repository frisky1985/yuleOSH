# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH 反思蒸馏器 (P1) — 每日使用 → 结构化记忆候选。

设计 (reflective-distillation-20260819):
    ① 蒸馏 Distill: 读最近 N 天 session 日志 + session 目录原始产物 →
       LLM 提炼 事实/经验/教训/纠正 四类候选 → 确定性去重 → 批量落库。

流程:
    collect_session_texts(days) → extract_candidates(texts) →
    dedupe(candidates) → _persist(kept)  [单事务]

LLM 可注入 (``llm_fn``)，默认走 ``LLMClient.call_sync``；``--mock`` 走
确定性启发式抽取（无 API key 也可演示/测试）。蒸馏产物写入 MemoryStore 后，
knowledge_injection 下次回话自动生效（链路已通，见 design doc §现状）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuleosh.memory.store import MemoryStore, normalize_text

log = logging.getLogger("yuleosh.memory.distill")

# 候选类型
KINDS = ("fact", "experience", "lesson", "correction")

# 单块喂给 LLM 的最大字符数（分块防超长 prompt）
CHUNK_CHARS = 12000
# 单次 distill 最多块数（预算保护）
MAX_CHUNKS = 8
# 单个 session 文件抽取上限
MAX_FILE_CHARS = 4000
# session 目录产物总上限
MAX_DIR_CHARS = 60000
# 最多扫描的 session 目录数
MAX_SESSION_DIRS = 40

DISTILL_SYSTEM_PROMPT = (
    "你是 yuleOSH 的记忆蒸馏器。下面是从最近几天会话日志/流水线产物中抽取的原始文本。\n"
    "请提炼出值得长期记忆的条目，输出**仅一个 JSON 数组**，不要输出其他文字。\n"
    "每条对象字段：\n"
    '  - "content": 简洁、自包含、可验证的一句话（中文，去掉人称与流水账）\n'
    '  - "entity": 主题实体（项目/模块/概念名，如 window-anti-pinch、coverage gate）\n'
    '  - "category": 从 [project, architecture, decision, process, tooling, lesson, general] 选一个\n'
    '  - "kind": 从 ["fact", "experience", "lesson", "correction"] 选一个\n'
    "      fact=客观事实/配置/结论；experience=可复用经验/最佳实践；\n"
    "      lesson=踩坑教训/反面教材；correction=对之前认知的纠正\n"
    '  - "trust": 0.0-1.0 初始信任度（fact/correction 0.7+，experience 0.6，lesson 0.5）\n'
    "只提炼有长期价值的内容（架构决策、接口契约、坑、修正、经验）；忽略临时状态与噪音。\n"
)

# 启发式 mock 抽取的信号词
_MOCK_SIGNAL = ("经验", "教训", "修复", "决定", "坑", "注意", "错误",
                "最佳实践", "配置", "契约", "必须", "禁止", "不要")
_LESSON_SIGNAL = ("教训", "坑", "错误", "失败", "不要", "禁止")
_CORRECTION_SIGNAL = ("修复", "纠正", "修正", "改为", "更正")
_EXPERIENCE_SIGNAL = ("经验", "最佳实践", "方法", "流程")


@dataclass
class DistillCandidate:
    """一条蒸馏候选（LLM 输出 → 去重 → 落库的中间形态）。"""

    content: str
    entity: str = ""
    category: str = "general"
    kind: str = "fact"
    trust: float = 0.5
    source_session: str = ""
    source_reliability: str = "llm"
    distilled_at: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DistillCandidate":
        known = {k: data.get(k) for k in (
            "content", "entity", "category", "kind", "trust",
            "source_session", "source_reliability", "distilled_at")}
        return cls(**known)  # type: ignore[arg-type]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp_trust(t) -> float:
    try:
        v = float(t)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


def _extract_json_array(text: str) -> list[dict]:
    """Robustly extract a JSON array from an LLM response.

    Handles stray prose before/after the array and a possible
    ``{"candidates": [...]}`` wrapper.
    """
    if not text:
        return []
    start = text.find("[")
    if start == -1:
        # try wrapper object
        m = re.search(r'"candidates"\s*:\s*(\[)', text)
        if m:
            start = m.start(1)
        else:
            return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(obj, list):
            return [d for d in obj if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass
    return []


def _coerce_candidate(item: dict, source_session: str = "") -> DistillCandidate | None:
    """Validate/normalize a raw LLM dict into a DistillCandidate."""
    content = str(item.get("content", "")).strip()
    if not content:
        return None
    kind = str(item.get("kind", "fact")).strip().lower()
    if kind not in KINDS:
        kind = "fact"
    entity = str(item.get("entity", "")).strip()
    category = str(item.get("category", "general")).strip() or "general"
    trust = _clamp_trust(item.get("trust", 0.5))
    return DistillCandidate(
        content=content,
        entity=entity,
        category=category,
        kind=kind,
        trust=trust,
        source_session=source_session,
    )


def similarity(a: str, b: str) -> float:
    """Normalized difflib similarity in [0, 1] (deterministic dedup)."""
    import difflib

    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


class Distiller:
    """蒸馏器：session 文本 → LLM 候选 → 去重 → 批量落库。"""

    def __init__(self, store: MemoryStore | None = None,
                 llm_fn=None, project_dir: str | Path | None = None,
                 similarity_threshold: float = 0.85):
        self._store = store or MemoryStore()
        self._llm_fn = llm_fn or _default_llm_fn
        self._project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.similarity_threshold = similarity_threshold
        self._last_chunks = 0

    # ── 输入收集 ──────────────────────────────────────────────────────

    def collect_session_texts(self, days: int = 1) -> list[str]:
        """收集蒸馏输入：session 日志 + session 目录原始产物。

        Returns:
            list[str]: 文本块（每块已按 CHUNK_CHARS 切分，可直接喂 LLM）。
        """
        parts: list[str] = []
        logs = self._store.list_session_logs(days=days, limit=500)
        if logs:
            log_lines = [f"[session_log #{r['id']} {r.get('kind', 'note')}] "
                         f"{r.get('content', '').strip()}"
                         for r in logs if r.get("content", "").strip()]
            if log_lines:
                parts.append("\n".join(log_lines))
        dir_text = self._collect_session_dir_text(days=days)
        if dir_text:
            parts.append(dir_text)
        if not parts:
            return []
        return self._chunk_texts("\n\n".join(parts))

    def _collect_session_dir_text(self, days: int = 1) -> str:
        """从 project_dir 的 sessions/ 与 .osh/sessions/ 目录收集产物文本。"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        dirs = [self._project_dir / "sessions", self._project_dir / ".osh" / "sessions"]
        session_dirs: list[Path] = []
        for base in dirs:
            if not base.is_dir():
                continue
            for d in base.iterdir():
                if not d.is_dir():
                    continue
                try:
                    mtime = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
                if mtime >= cutoff:
                    session_dirs.append(d)
        session_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        session_dirs = session_dirs[: MAX_SESSION_DIRS]

        out: list[str] = []
        total = 0
        for d in session_dirs:
            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                name = f.name
                if name == "session.json":
                    continue  # 元数据，非产物
                if not (name.endswith(".md") or name.endswith(".json")):
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                text = text.strip()
                if not text:
                    continue
                text = text[: MAX_FILE_CHARS]
                out.append(f"### [{d.name}/{name}]\n{text}")
                total += len(text)
                if total >= MAX_DIR_CHARS:
                    return "\n\n".join(out)
        return "\n\n".join(out)

    def _chunk_texts(self, text: str) -> list[str]:
        """Split one blob into ≤CHUNK_CHARS chunks at newline boundaries."""
        if len(text) <= CHUNK_CHARS:
            return [text]
        chunks: list[str] = []
        cur = ""
        for line in text.splitlines(keepends=True):
            if len(cur) + len(line) > CHUNK_CHARS and cur:
                chunks.append(cur)
                cur = line
            else:
                cur += line
            if len(chunks) >= MAX_CHUNKS:
                break
        if cur:
            chunks.append(cur)
        return chunks[: MAX_CHUNKS]

    # ── LLM 抽取 ──────────────────────────────────────────────────────

    def _build_prompt(self, chunk: str, days: int) -> str:
        return (
            f"最近 {days} 天的会话原始文本如下（可能含噪音，请过滤）：\n\n"
            f"---BEGIN---\n{chunk}\n---END---\n\n"
            "输出 JSON 数组（仅数组，无其他文字）："
        )

    def extract_candidates(self, texts: list[str], days: int = 1,
                           source_session: str = "") -> list[DistillCandidate]:
        """对每个文本块调用 LLM 并解析候选。"""
        self._last_chunks = len(texts)
        candidates: list[DistillCandidate] = []
        for chunk in texts:
            try:
                raw = self._llm_fn(self._build_prompt(chunk, days))
            except Exception as e:  # noqa: BLE001 — 蒸馏失败不致命
                log.warning("Distill LLM chunk failed (non-fatal): %s", e)
                continue
            for item in _extract_json_array(raw):
                cand = _coerce_candidate(item, source_session=source_session)
                if cand:
                    candidates.append(cand)
        return candidates

    # ── 确定性去重 ────────────────────────────────────────────────────

    def _is_duplicate(self, cand: DistillCandidate,
                      accepted: list[DistillCandidate]) -> bool:
        for k in accepted:
            same_entity = (not cand.entity and not k.entity) or (
                cand.entity and k.entity and normalize_text(cand.entity) == normalize_text(k.entity))
            if same_entity and similarity(cand.content, k.content) >= self.similarity_threshold:
                return True
        return False

    def dedupe(self, candidates: list[DistillCandidate]
               ) -> tuple[list[DistillCandidate], list[DistillCandidate]]:
        """去重：候选内部 + 与已有 active facts（幂等）。

        Returns:
            (kept, dropped)
        """
        kept: list[DistillCandidate] = []
        dropped: list[DistillCandidate] = []
        for cand in candidates:
            if self._is_duplicate(cand, kept):
                dropped.append(cand)
                continue
            existing = self._store.find_similar(
                cand.content, entity=cand.entity,
                threshold=self.similarity_threshold, limit=3)
            if existing:
                dropped.append(cand)
                continue
            kept.append(cand)
        return kept, dropped

    def _persist(self, candidates: list[DistillCandidate]) -> list[dict]:
        """批量落库（单事务）。"""
        items = [
            {
                "content": c.content,
                "entity": c.entity,
                "category": c.category,
                "trust": c.trust,
                "tags": f"distilled:{c.kind}",
                "source": c.source_session,
                "source_reliability": c.source_reliability,
                "distilled_at": c.distilled_at,
            }
            for c in candidates
        ]
        return self._store.remember_many(items)

    # ── 主入口 ────────────────────────────────────────────────────────

    def distill(self, days: int = 1, dry_run: bool = False) -> dict:
        """执行一次蒸馏：收集 → 抽取 → 去重 → 落库（dry_run 不写库）。

        Returns:
            summary dict（chunks/candidates/inserted/deduped/facts/…）
        """
        summary = {
            "days": days,
            "chunks": 0,
            "candidates": 0,
            "inserted": 0,
            "deduped": 0,
            "dry_run": dry_run,
            "facts": [],
            "note": "",
        }
        texts = self.collect_session_texts(days=days)
        summary["chunks"] = len(texts)
        if not texts:
            summary["note"] = "no session text in window"
            self._store.record_distill_run(
                days=days, chunks=0, candidates=0, inserted=0, deduped=0,
                note=summary["note"])
            return summary
        candidates = self.extract_candidates(texts, days=days)
        summary["candidates"] = len(candidates)
        kept, dropped = self.dedupe(candidates)
        summary["deduped"] = len(dropped)
        if not dry_run and kept:
            created = self._persist(kept)
            summary["inserted"] = len(created)
            summary["facts"] = [f["id"] for f in created]
        self._write_candidates_json(kept)
        self._store.record_distill_run(
            days=days, chunks=summary["chunks"], candidates=len(candidates),
            inserted=summary["inserted"], deduped=len(dropped),
            note=summary["note"])
        return summary

    def _write_candidates_json(self, candidates: list[DistillCandidate]) -> Path:
        """持久化候选，供 reflect（P2）复用，避免二次 LLM 抽取。"""
        path = self._project_dir / ".yuleosh" / "last-distill-candidates.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps([c.to_dict() for c in candidates],
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError as e:
            log.warning("Could not write candidates file (non-fatal): %s", e)
        return path


# ── LLM 默认实现 ────────────────────────────────────────────────────────


def _default_llm_fn(prompt: str) -> str:
    """默认蒸馏 LLM：走 LLMClient.call_sync（DeepSeek 等，统一路由）。"""
    from yuleosh.llm.client import LLMClient

    resp = LLMClient.call_sync(
        prompt,
        system_prompt=DISTILL_SYSTEM_PROMPT,
        task_type="memory_distill",
    )
    return resp["content"]


def mock_distill_llm(prompt: str) -> str:
    """确定性 mock 蒸馏：按信号词抽取句子（无 API key 演示/测试）。

    与真实 LLM 的输出契约一致：返回 JSON 数组字符串。
    """
    m = re.search(r"---BEGIN---\n(.*?)\n---END---", prompt, re.DOTALL)
    text = m.group(1) if m else prompt
    sents = re.split(r"(?<=[。！？!?])\s*", text)
    out: list[dict] = []
    for s in sents:
        s = s.strip()
        if len(s) < 15:
            continue
        if not any(k in s for k in _MOCK_SIGNAL):
            continue
        if any(k in s for k in _LESSON_SIGNAL):
            kind = "lesson"
        elif any(k in s for k in _CORRECTION_SIGNAL):
            kind = "correction"
        elif any(k in s for k in _EXPERIENCE_SIGNAL):
            kind = "experience"
        else:
            kind = "fact"
        out.append({
            "content": s,
            "entity": "",
            "category": "general",
            "kind": kind,
            "trust": 0.5 if kind == "lesson" else 0.7,
        })
    return json.dumps(out, ensure_ascii=False)


def load_last_candidates(project_dir: str | Path) -> list[DistillCandidate]:
    """读取上次 distill 写入的候选（reflect 复用，缺文件返回空列表）。"""
    path = Path(project_dir) / ".yuleosh" / "last-distill-candidates.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [c for c in (DistillCandidate.from_dict(d) for d in data) if c]
    except (OSError, ValueError, TypeError) as e:
        log.warning("Could not read last-distill-candidates.json: %s", e)
        return []
