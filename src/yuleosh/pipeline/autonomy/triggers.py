#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""triggers.py — 信号 → 工单（Autonomy Phase 2）。

两种触发路径：

* **Fast Path（默认，确定性）**：
  - ``spec-change``  — spec 文件内容/修改时间变化；
  - ``run-regression`` — 最近一次 run 的结论为 ``red`` / ``unverified``。
* **Slow Path（可选）**：调用方传入 ``llm_client`` 时，对
  ``run-regression`` 工单补充一段根因提示；任何失败都被吞掉，不影响
  Fast Path 结果。

模式（``OSH_AUTONOMY_MODE``）：

* ``off``（默认）— 不产生工单；
* ``observe`` — 产生 ``pending`` 工单，等人 ``accept``；
* ``auto`` — 直接产生 ``accepted`` 工单，交给 Router 执行。

工单持久化在 ``<project>/.osh/tickets/tickets.jsonl``（append-only 快照，
读取时按 ticket_id 取最后一条）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

log = logging.getLogger("pipeline.autonomy.triggers")

MODE_ENV = "OSH_AUTONOMY_MODE"
SLOW_PATH_ENV = "OSH_AUTONOMY_SLOW_PATH"
MODES = ("off", "observe", "auto")
ACTIVE_STATUSES = ("pending", "accepted", "running")
TERMINAL_STATUSES = ("done", "failed", "rejected", "unverified")


def autonomy_mode() -> str:
    """读取自动化模式；非法值按 ``off`` 处理（安全默认）。"""
    raw = os.environ.get(MODE_ENV, "").strip().lower()
    if raw in ("1", "true", "on", "yes"):
        return "auto"
    return raw if raw in MODES else "off"


def _now() -> str:
    return datetime.now().isoformat()


@dataclass
class Trigger:
    """一条待处理的信号。"""

    kind: str
    dedupe_key: str
    payload: dict = field(default_factory=dict)
    source: str = "fast-path"
    detected_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Ticket:
    """可执行的工单（Router 的输入单元）。"""

    kind: str
    dedupe_key: str
    payload: dict = field(default_factory=dict)
    status: str = "pending"
    ticket_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    run_id: str = ""
    note: str = ""
    attempts: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Ticket":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class TicketStore:
    """JSONL 工单存储（last snapshot wins）。

    单机文件锁粒度足够：写入是单行 ``write``，读取容错坏行。多进程同时
    写可能交错，但每个进程只 append 完整 JSON 行，最坏结果是丢掉一条
    中间快照，最新状态仍可由后续 append 恢复。
    """

    def __init__(self, project_dir: str | Path | None = None,
                 path: str | Path | None = None):
        self.project_dir = Path(
            project_dir or os.environ.get("OSH_HOME", "."))
        self.path = Path(path) if path else (
            self.project_dir / ".osh" / "tickets" / "tickets.jsonl")

    # ── persistence ────────────────────────────────────────────────
    def load(self) -> list[Ticket]:
        if not self.path.is_file():
            return []
        latest: dict[str, Ticket] = {}
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict) or not data.get("ticket_id"):
                    continue
                latest[str(data["ticket_id"])] = Ticket.from_dict(data)
        except Exception as exc:  # noqa: BLE001 — 坏文件按空处理
            log.warning("ticket store read failed: %s", exc)
            return []
        return sorted(latest.values(), key=lambda t: (t.created_at, t.ticket_id))

    def _append(self, ticket: Ticket) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ticket.to_dict(), ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 — 持久化失败不阻断决策
            log.warning("ticket store write failed: %s", exc)

    # ── API ───────────────────────────────────────────────────────
    def add(self, ticket: Ticket) -> tuple[Ticket, bool]:
        """添加工单；活动中的同 dedupe_key 工单直接复用。"""
        for existing in self.load():
            if (existing.dedupe_key == ticket.dedupe_key
                    and existing.status in ACTIVE_STATUSES):
                return existing, False
        self._append(ticket)
        return ticket, True

    def update(self, ticket: Ticket) -> Ticket:
        ticket.updated_at = _now()
        self._append(ticket)
        return ticket

    def get(self, ticket_id: str) -> Optional[Ticket]:
        return next((t for t in self.load() if t.ticket_id == ticket_id), None)

    def list(self, status: str | None = None) -> list[Ticket]:
        tickets = self.load()
        if status:
            tickets = [t for t in tickets if t.status == status]
        return tickets

    def accept(self, ticket_id: str) -> Optional[Ticket]:
        ticket = self.get(ticket_id)
        if ticket is None or ticket.status not in ("pending", "accepted"):
            return ticket
        ticket.status = "accepted"
        return self.update(ticket)

    def claim_next(self) -> Optional[Ticket]:
        """领取一条 accepted 工单并置为 running；无则返回 None。"""
        for ticket in self.load():
            if ticket.status == "accepted":
                ticket.status = "running"
                ticket.attempts += 1
                return self.update(ticket)
        return None


# ── Fast Path ──────────────────────────────────────────────────────

def _spec_candidates(project_dir: Path) -> list[Path]:
    out: list[Path] = []
    specs_dir = project_dir / ".osh" / "specs"
    if specs_dir.is_dir():
        out.extend(sorted(specs_dir.glob("*.md")))
    for rel in ("spec.md", "docs/spec.md", ".osh/spec.md"):
        p = project_dir / rel
        if p.is_file():
            out.append(p)
    # 去重，保持顺序
    seen: set[str] = set()
    unique: list[Path] = []
    for p in out:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def _fingerprint_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:  # noqa: BLE001
        return ""


def _state_path(project_dir: Path) -> Path:
    return project_dir / ".osh" / "autonomy" / "trigger-state.json"


def _load_state(project_dir: Path) -> dict:
    path = _state_path(project_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_state(project_dir: Path, state: dict) -> None:
    path = _state_path(project_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.debug("trigger state write failed: %s", exc)


def _latest_session(project_dir: Path) -> Optional[dict]:
    try:
        from yuleosh.pipeline.session import resolve_sessions_root

        root = resolve_sessions_root()
        # 项目自定义 OSH_HOME 时优先项目内 sessions
        candidates = [root, project_dir / ".osh" / "sessions"]
        files: list[Path] = []
        for base in candidates:
            if base.is_dir():
                files.extend(base.glob("*/session.json"))
        if not files:
            return None
        latest = max(files, key=lambda p: p.stat().st_mtime)
        data = json.loads(latest.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        log.debug("latest session lookup failed: %s", exc)
        return None


def collect_signals(project_dir: str | Path) -> list[Trigger]:
    """收集确定性信号（不写状态、不产生工单）。"""
    root = Path(project_dir or os.environ.get("OSH_HOME", "."))
    state = _load_state(root)
    seen_specs: dict = state.get("specs") or {}
    triggers: list[Trigger] = []

    for spec in _spec_candidates(root):
        key = str(spec.resolve())
        digest = _fingerprint_file(spec)
        previous = seen_specs.get(key) or {}
        if previous.get("sha256") == digest and digest:
            continue
        triggers.append(Trigger(
            kind="spec-change",
            dedupe_key=f"spec-change:{key}:{digest[:16]}",
            payload={
                "project_dir": str(root),
                "spec_path": str(spec),
                "sha256": digest,
            },
        ))

    latest = _latest_session(root)
    if latest:
        verdict = latest.get("gate_verdict") or {}
        outcome = str(verdict.get("outcome") or "").lower()
        if outcome in ("red", "unverified"):
            run_id = str(latest.get("run_id") or "")
            triggers.append(Trigger(
                kind="run-regression",
                dedupe_key=f"run-regression:{run_id}:{outcome}",
                payload={
                    "project_dir": str(root),
                    "spec_path": str(latest.get("spec_path") or ""),
                    "session_name": str(latest.get("name") or ""),
                    "outcome": outcome,
                    "reason": str(verdict.get("reason") or ""),
                },
            ))
    return triggers


def _slow_path_note(trigger: Trigger, llm_client) -> str:
    """可选 Slow Path：让 LLM 给出一条根因提示；失败返回空串。"""
    if llm_client is None or trigger.kind != "run-regression":
        return ""
    try:
        system = (
            "你是持续改进助手。根据一次未通过的流水线运行信息，给出一条"
            "最可能的根因与下一步动作。不超过 120 字，不要重复证据。")
        user = json.dumps(trigger.payload, ensure_ascii=False)
        resp = llm_client(system, user)
        if isinstance(resp, dict):
            content = resp.get("content") or (
                resp.get("choices", [{}])[0].get("message", {}).get("content"))
        else:
            content = str(resp)
        return str(content or "").strip()[:500]
    except Exception as exc:  # noqa: BLE001 — 慢路径失败不影响快路径
        log.debug("slow path failed: %s", exc)
        return ""


def propose_tickets(project_dir: str | Path,
                    store: TicketStore | None = None,
                    llm_client=None) -> list[Ticket]:
    """按当前模式把信号转成工单；返回本次**新建**的工单。"""
    mode = autonomy_mode()
    if mode == "off":
        return []
    root = Path(project_dir or os.environ.get("OSH_HOME", "."))
    store = store or TicketStore(root)
    created: list[Ticket] = []
    state = _load_state(root)
    specs_state = dict(state.get("specs") or {})

    for trigger in collect_signals(root):
        note = ""
        if llm_client is not None and os.environ.get(SLOW_PATH_ENV) == "1":
            note = _slow_path_note(trigger, llm_client)
        ticket = Ticket(
            kind=trigger.kind,
            dedupe_key=trigger.dedupe_key,
            payload=dict(trigger.payload),
            status="accepted" if mode == "auto" else "pending",
            note=note,
        )
        saved, is_new = store.add(ticket)
        if is_new:
            created.append(saved)
        if trigger.kind == "spec-change":
            spec_path = trigger.payload.get("spec_path", "")
            if spec_path:
                specs_state[spec_path] = {
                    "sha256": trigger.payload.get("sha256", ""),
                    "seen_at": _now(),
                }

    if specs_state != (state.get("specs") or {}):
        state["specs"] = specs_state
        state["updated_at"] = _now()
        _save_state(root, state)
    return created
