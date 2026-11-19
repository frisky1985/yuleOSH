#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""recall.py — 以 spec 指纹召回历史运行结果。

目的：同一条 spec 反复跑时，把「上次为什么没过」提前告诉本轮的生产者，
避免重复踩同一个坑。召回只提供**提示**，不替代本轮门禁证据。

存储：``<project>/.osh/autonomy/recall.db``（独立 SQLite，不污染应用
Store）。每次操作独立连接，天然支持 Router 的并发 worker。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("pipeline.autonomy.recall")

RECALL_HINTS_ENV = "OSH_RECALL_HINTS"
DEFAULT_DB_REL = Path(".osh") / "autonomy" / "recall.db"
MAX_HINT_CHARS = 1200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS recall_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint       TEXT NOT NULL,
    run_id            TEXT,
    name              TEXT,
    outcome           TEXT,
    reason            TEXT,
    failed_signatures TEXT,
    recorded_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recall_fingerprint ON recall_runs(fingerprint);
"""


def _project_dir(project_dir: str | Path | None) -> Path:
    return Path(project_dir or os.environ.get("OSH_HOME", "."))


def _normalize_spec(text: str) -> str:
    """规范化 spec 文本：折叠空白、去行首尾空格（忽略排版差异）。"""
    return re.sub(r"\s+", " ", text or "").strip()


def spec_fingerprint(spec_path: str | Path | None) -> str:
    """spec 内容指纹（sha256）；文件缺失/不可读返回空串。"""
    if not spec_path:
        return ""
    try:
        p = Path(spec_path)
        if not p.is_file():
            return ""
        normalized = _normalize_spec(p.read_text(encoding="utf-8"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    except Exception as exc:  # noqa: BLE001 — 指纹失败不影响运行
        log.debug("spec fingerprint failed: %s", exc)
        return ""


def failed_signatures(session: Any) -> list[str]:
    """从 session.steps 提取失败/未通过的签名（用于历史聚合）。"""
    out: list[str] = []
    for step in getattr(session, "steps", []) or []:
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "").lower()
        if status not in ("failed", "retry", "incomplete", "blocked", "error"):
            continue
        name = str(step.get("name") or step.get("step") or "step")
        errors = step.get("errors") or []
        first = ""
        if isinstance(errors, list) and errors:
            first = str(errors[0])
        sig = f"{name}:{status}"
        if first:
            sig += f":{first[:160]}"
        if sig not in out:
            out.append(sig)
    return out


def _session_outcome(session: Any) -> tuple[str, str]:
    verdict = getattr(session, "gate_verdict", None)
    if isinstance(verdict, dict) and verdict.get("outcome"):
        return str(verdict["outcome"]), str(verdict.get("reason") or "")
    return str(getattr(session, "status", "unknown")), ""


class RecallStore:
    """历史运行结果索引（按 spec 指纹）。"""

    def __init__(self, project_dir: str | Path | None = None,
                 db_path: str | Path | None = None):
        self.project_dir = _project_dir(project_dir)
        self.db_path = Path(db_path) if db_path else self.project_dir / DEFAULT_DB_REL

    # ── sqlite plumbing ────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    # ── write ─────────────────────────────────────────────────────
    def record(self, fingerprint: str, run_id: str = "", name: str = "",
               outcome: str = "", reason: str = "",
               failures: Optional[list[str]] = None) -> bool:
        """记录一次运行结果；失败返回 False（不抛异常）。"""
        if not fingerprint:
            return False
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO recall_runs "
                    "(fingerprint, run_id, name, outcome, reason, "
                    " failed_signatures, recorded_at) VALUES (?,?,?,?,?,?,?)",
                    (fingerprint, run_id, name, outcome, reason,
                     json.dumps(failures or [], ensure_ascii=False),
                     datetime.now().isoformat()),
                )
            return True
        except Exception as exc:  # noqa: BLE001 — 历史记录不得阻断运行
            log.warning("recall record failed: %s", exc)
            return False

    # ── read ──────────────────────────────────────────────────────
    def query(self, fingerprint: str, limit: int = 20) -> list[dict]:
        if not fingerprint:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT run_id, name, outcome, reason, failed_signatures, "
                    "       recorded_at FROM recall_runs "
                    "WHERE fingerprint = ? ORDER BY id DESC LIMIT ?",
                    (fingerprint, int(limit)),
                ).fetchall()
        except Exception as exc:  # noqa: BLE001
            log.warning("recall query failed: %s", exc)
            return []
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            try:
                item["failed_signatures"] = json.loads(
                    item.get("failed_signatures") or "[]")
            except Exception:
                item["failed_signatures"] = []
            out.append(item)
        return out

    def suggest(self, fingerprint: str, limit: int = 20) -> dict:
        """聚合历史结果，返回 {runs, outcomes, top_failures, hint}。"""
        runs = self.query(fingerprint, limit=limit)
        outcomes: dict[str, int] = {}
        counts: dict[str, int] = {}
        for run in runs:
            key = str(run.get("outcome") or "unknown")
            outcomes[key] = outcomes.get(key, 0) + 1
            for sig in run.get("failed_signatures") or []:
                counts[str(sig)] = counts.get(str(sig), 0) + 1
        top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        hint = _render_hint(runs, outcomes, top)
        return {
            "runs": runs,
            "outcomes": outcomes,
            "top_failures": [{"signature": s, "count": c} for s, c in top],
            "hint": hint,
        }


def _render_hint(runs: list[dict], outcomes: dict[str, int],
                 top: list[tuple[str, int]]) -> str:
    if not runs:
        return ""
    latest = runs[0]
    outcome_summary = ", ".join(
        f"{k}={v}" for k, v in sorted(outcomes.items()))
    lines = [
        "## 历史运行提示（同 spec 指纹）",
        f"- 近 {len(runs)} 次结果: {outcome_summary}",
        f"- 最近一次: {latest.get('outcome') or '?'}"
        + (f" — {latest.get('reason')}" if latest.get("reason") else ""),
    ]
    if top:
        lines.append("- 反复出现的失败点（按出现次数）:")
        for idx, (sig, count) in enumerate(top, 1):
            lines.append(f"  {idx}. {sig} ({count} 次)")
    lines.append(
        "把以上历史失败点当作本轮自检清单；历史结论不代表本轮通过，"
        "放行仍以本轮门禁证据为准。")
    text = "\n".join(lines)
    return text[:MAX_HINT_CHARS]


def suggest_hint(project_dir: str | Path | None,
                 spec_path: str | Path | None) -> str:
    fp = spec_fingerprint(spec_path)
    if not fp:
        return ""
    try:
        return RecallStore(project_dir).suggest(fp).get("hint", "")
    except Exception as exc:  # noqa: BLE001
        log.debug("recall suggest failed: %s", exc)
        return ""


def record_session(project_dir: str | Path | None, session: Any,
                   spec_path: str | Path | None = None) -> bool:
    """把一次 run 的结论写进历史索引。"""
    spec = spec_path or getattr(session, "spec_path", None)
    fp = spec_fingerprint(spec)
    if not fp:
        return False
    outcome, reason = _session_outcome(session)
    return RecallStore(project_dir).record(
        fp,
        run_id=str(getattr(session, "run_id", "") or ""),
        name=str(getattr(session, "name", "") or ""),
        outcome=outcome,
        reason=reason,
        failures=failed_signatures(session),
    )


# ── prompt 注入 ────────────────────────────────────────────────────

def set_hint(text: str) -> None:
    if text:
        os.environ[RECALL_HINTS_ENV] = text


def clear_hint() -> None:
    os.environ.pop(RECALL_HINTS_ENV, None)


def directive() -> str:
    """供 prompt builder 调用：当前召回提示（无则空串）。"""
    return os.environ.get(RECALL_HINTS_ENV, "").strip()
