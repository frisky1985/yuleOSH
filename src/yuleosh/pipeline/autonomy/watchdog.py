#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""watchdog.py — 无实质进展检测。

背景
----
返工（review → producer → review）在「评审意见没变、产物也没变」时会
空转：每一轮都消耗 LLM token，却不可能收敛。Watchdog 记录同一步骤连续
出现的**相同失败签名**，达到阈值即判定「无实质进展」并升级，而不是等到
轮次耗尽才发现。

判定规则
--------
1. 有失败签名（findings/错误摘要）时，只看签名是否变化；
2. 无签名时退化为比较产物内容摘要（sha256）；
3. 首次观察记 streak=1，连续相同 +1，出现变化立即重置为 1；
4. ``streak >= max_stalls`` → tripped，写 ``<session_dir>/watchdog.json``。

该模块只做本地状态，不发网络请求，失败不影响主流程。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger("pipeline.autonomy.watchdog")

DEFAULT_MAX_STALLS = 3
MAX_STALLS_ENV = "OSH_WATCHDOG_MAX_STALLS"
STATE_FILENAME = "watchdog.json"


def resolve_max_stalls() -> int:
    """阈值（默认 3，可由 ``OSH_WATCHDOG_MAX_STALLS`` 覆盖）。"""
    raw = os.environ.get(MAX_STALLS_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_MAX_STALLS


def artifact_digest(path: Path | str) -> str:
    """产物内容摘要；文件不存在或不可读返回空串。"""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001 — 摘要失败不阻断流水线
        return ""


def findings_signature(findings: Iterable[dict[str, Any]] | None) -> str:
    """把 findings 规范化成稳定签名（与顺序/时间戳无关）。"""
    parts: list[str] = []
    for item in findings or []:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule") or item.get("code")
                   or item.get("category") or "FINDING")
        message = str(item.get("message") or item.get("detail") or "")
        where = str(item.get("file") or item.get("artifact") or "")
        parts.append(f"{rule}|{where}|{message}".strip())
    if not parts:
        return ""
    parts.sort()
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


@dataclass
class ProgressRecord:
    """单个步骤的一次进展观察。"""

    step: str
    signature: str = ""
    artifact_digest: str = ""
    status: str = ""
    streak: int = 1
    tripped: bool = False
    at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class Watchdog:
    """跨步骤的进展观察器（每个 session 一个实例）。"""

    def __init__(self, session_dir: Path | str | None = None,
                 max_stalls: int | None = None):
        self.session_dir = Path(session_dir) if session_dir else None
        self.max_stalls = max_stalls or resolve_max_stalls()
        self._records: dict[str, ProgressRecord] = {}
        self._load()

    # ── persistence ────────────────────────────────────────────────
    @property
    def state_path(self) -> Optional[Path]:
        if self.session_dir is None:
            return None
        return self.session_dir / STATE_FILENAME

    def _load(self) -> None:
        path = self.state_path
        if path is None or not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — 坏文件按空状态处理
            return
        for key, item in (raw.get("records") or {}).items():
            if not isinstance(item, dict):
                continue
            try:
                self._records[key] = ProgressRecord(**item)
            except TypeError:
                continue

    def _save(self) -> None:
        path = self.state_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "max_stalls": self.max_stalls,
                "updated_at": datetime.now().isoformat(),
                "tripped": self.tripped,
                "records": {k: v.to_dict() for k, v in self._records.items()},
            }
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 — 落盘失败不阻断流水线
            log.debug("watchdog state write failed: %s", exc)

    # ── observation ────────────────────────────────────────────────
    def record(self, step: str, signature: str = "",
               artifact_digest_value: str = "", status: str = "") -> ProgressRecord:
        """记录一次观察；返回本条记录（含 streak/tripped）。"""
        prev = self._records.get(step)

        def _same(rec: ProgressRecord) -> bool:
            if signature:
                return rec.signature == signature
            if artifact_digest_value:
                return rec.artifact_digest == artifact_digest_value
            # 什么都没有可比时，相同 status 视为无进展
            return bool(status) and rec.status == status

        streak = 1
        if prev is not None and _same(prev):
            streak = prev.streak + 1
        rec = ProgressRecord(
            step=step,
            signature=signature,
            artifact_digest=artifact_digest_value,
            status=status,
            streak=streak,
            tripped=streak >= self.max_stalls,
        )
        self._records[step] = rec
        self._save()
        if rec.tripped:
            log.warning(
                "Watchdog tripped: step=%s streak=%d/%d signature=%s status=%s",
                step, streak, self.max_stalls, signature[:12], status,
            )
        return rec

    def reset(self) -> None:
        self._records.clear()
        self._save()

    @property
    def tripped(self) -> bool:
        return any(r.tripped for r in self._records.values())

    def snapshot(self) -> dict:
        return {
            "max_stalls": self.max_stalls,
            "tripped": self.tripped,
            "records": {k: v.to_dict() for k, v in self._records.items()},
        }


def get_watchdog(session: Any) -> Watchdog:
    """取（或创建并缓存）session 级 Watchdog 实例。"""
    wd = getattr(session, "watchdog", None)
    if isinstance(wd, Watchdog):
        return wd
    sdir = getattr(session, "session_dir", None)
    wd = Watchdog(session_dir=sdir)
    try:
        session.watchdog = wd
    except Exception:  # noqa: BLE001 — 只读 session 也不应崩溃
        pass
    return wd
