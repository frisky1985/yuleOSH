#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""router.py — 领取工单并驱动 ``run_pipeline``（Autonomy Phase 3）。

职责边界（合规红线）：

* Router **只决定「何时跑、跑哪个 spec」**，执行始终调用
  ``yuleosh.pipeline.run_pipeline`` —— 确定性 Gate、返工路由、审计链、
  人工签批全部照旧，Autonomy 层不参与「是否放行」。
* 不启用 danger-full-access，不绕过任何门禁。

并发：默认 1 个 worker（``OSH_AUTONOMY_WORKERS`` 可调），每个 worker 独立
领取一条 ``accepted`` 工单并跑完整条 pipeline。
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from yuleosh.pipeline.autonomy.triggers import (
    Ticket,
    TicketStore,
    propose_tickets,
)

log = logging.getLogger("pipeline.autonomy.router")

WORKERS_ENV = "OSH_AUTONOMY_WORKERS"
MAX_WORKERS_CAP = 8


def _workers() -> int:
    raw = os.environ.get(WORKERS_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(int(raw), MAX_WORKERS_CAP)
    return 1


def default_spec_path(project_dir: str | Path | None) -> Optional[str]:
    """项目默认 spec：``.osh/specs/*.md``（取最新）→ ``spec.md`` → ``docs/spec.md``。"""
    root = Path(project_dir or os.environ.get("OSH_HOME", "."))
    specs_dir = root / ".osh" / "specs"
    if specs_dir.is_dir():
        files = sorted(specs_dir.glob("*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            return str(files[0])
    for rel in ("spec.md", "docs/spec.md"):
        candidate = root / rel
        if candidate.is_file():
            return str(candidate)
    return None


def _default_runner(spec_path: str, project_dir: str) -> Any:
    from yuleosh.pipeline.run import run_pipeline

    return run_pipeline(spec_path)


class Router:
    """工单 → pipeline 执行器。"""

    def __init__(self, project_dir: str | Path | None = None,
                 store: TicketStore | None = None,
                 max_workers: int | None = None,
                 runner: Callable[[str, str], Any] | None = None):
        self.project_dir = Path(
            project_dir or os.environ.get("OSH_HOME", "."))
        self.store = store or TicketStore(self.project_dir)
        self.max_workers = max_workers or _workers()
        self.runner = runner or _default_runner

    # ── single ticket ──────────────────────────────────────────────
    def _execute(self, ticket: Ticket) -> dict:
        spec = (ticket.payload or {}).get("spec_path") or default_spec_path(
            self.project_dir)
        if not spec or not Path(spec).is_file():
            ticket.status = "failed"
            ticket.note = f"spec not found: {spec or '<none>'}"
            self.store.update(ticket)
            log.warning("Ticket %s failed: %s", ticket.ticket_id, ticket.note)
            return self._result(ticket)

        print(f"\n🎫 [autonomy] ticket {ticket.ticket_id} ({ticket.kind}) → {spec}")
        session = None
        try:
            session = self.runner(str(spec), str(self.project_dir))
        except Exception as exc:  # noqa: BLE001 — 单工单失败不影响其他 worker
            ticket.status = "failed"
            ticket.note = f"router runner crashed: {exc}"
            self.store.update(ticket)
            log.exception("Ticket %s crashed", ticket.ticket_id)
            return self._result(ticket)

        verdict = getattr(session, "gate_verdict", None) or {}
        outcome = str(verdict.get("outcome") or "").lower()
        status = str(getattr(session, "status", "") or "")
        ticket.run_id = str(getattr(session, "run_id", "") or "")
        if status == "completed" and outcome in ("green", "awaiting-signoff"):
            ticket.status = "done"
        elif status == "completed" and outcome == "unverified":
            ticket.status = "unverified"
        else:
            ticket.status = "failed"
        ticket.note = str(verdict.get("reason") or status or "")
        self.store.update(ticket)
        return self._result(ticket)

    @staticmethod
    def _result(ticket: Ticket) -> dict:
        return {
            "ticket_id": ticket.ticket_id,
            "kind": ticket.kind,
            "status": ticket.status,
            "run_id": ticket.run_id,
            "note": ticket.note,
        }

    # ── batch / loop ──────────────────────────────────────────────
    def run_once(self) -> list[dict]:
        """领取并执行至多 ``max_workers`` 条 accepted 工单。"""
        claimed: list[Ticket] = []
        for _ in range(self.max_workers):
            ticket = self.store.claim_next()
            if ticket is None:
                break
            claimed.append(ticket)
        if not claimed:
            return []
        if len(claimed) == 1:
            return [self._execute(claimed[0])]
        with ThreadPoolExecutor(max_workers=len(claimed)) as pool:
            futures = [pool.submit(self._execute, t) for t in claimed]
            return [f.result() for f in futures]

    def run_loop(self, cycles: int = 0, interval: float = 5.0,
                 propose: bool = True, stop_when_idle: bool = True) -> list[dict]:
        """持续「扫描信号 → 领工单 → 跑 pipeline」。

        Args:
            cycles: 0 表示无限循环（由调用方中断）。
            interval: 空闲时的轮询间隔（秒）。
            propose: 每轮先调用 ``propose_tickets``（受 OSH_AUTONOMY_MODE 控制）。
            stop_when_idle: 无工单可跑时是否退出（CLI 默认 True）。
        """
        results: list[dict] = []
        done_cycles = 0
        while cycles <= 0 or done_cycles < cycles:
            if propose:
                try:
                    propose_tickets(self.project_dir, store=self.store)
                except Exception as exc:  # noqa: BLE001
                    log.warning("propose_tickets failed (non-fatal): %s", exc)
            batch = self.run_once()
            results.extend(batch)
            done_cycles += 1
            if not batch and stop_when_idle:
                break
            if cycles <= 0 or done_cycles < cycles:
                time.sleep(max(interval, 0))
        return results
