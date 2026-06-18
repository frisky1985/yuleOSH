# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
ALM (Application Lifecycle Management) — abstract base backends + stubs.

Provides abstract base classes for connecting to ALM systems
like Jira, Polarion, Codebeamer, plus concrete stub implementations
for Jira and Polarion (reserved for future full integration, G-13).

Current stubs:
  - :class:`JiraAdapter` — Atlassian Jira (create/update/link/attach tickets)
  - :class:`PolarionAdapter` — Siemens Polarion (WorkItem CRUD)

Usage:
    from yuleosh.alm import AlmBackend, AlmTicket, create_adapter

    adapter = create_adapter("jira", url="https://jira.example.com")
    ticket = AlmTicket(title="MISRA deviation", description="Rule 17.7")
    tid = adapter.create_ticket(ticket)
"""

from __future__ import annotations

import logging
from typing import Any

from yuleosh.alm.base import AlmBackend, AlmTicket

log = logging.getLogger("yuleosh.alm")


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

_ADAPTER_REGISTRY: dict[str, type[AlmBackend]] = {}


def register_adapter(name: str, cls: type[AlmBackend]) -> None:
    """Register an ALM adapter class."""
    _ADAPTER_REGISTRY[name.lower()] = cls


def create_adapter(kind: str, **conn_kw: Any) -> AlmBackend:
    """Factory: create an ALM adapter by kind name."""
    cls = _ADAPTER_REGISTRY.get(kind.lower())
    if cls is None:
        raise ValueError(
            f"Unknown ALM adapter '{kind}'. "
            f"Available: {list(_ADAPTER_REGISTRY)}"
        )
    return cls(**conn_kw)


def list_available_adapters() -> list[str]:
    """Return the list of registered ALM adapter names."""
    return list(_ADAPTER_REGISTRY)


# ------------------------------------------------------------------
# Jira stub adapter
# ------------------------------------------------------------------


class JiraAdapter(AlmBackend):
    """Atlassian Jira adapter (stub)."""

    def __init__(self, url: str = "", api_token: str = "", **_: Any) -> None:
        self.url = url
        self.api_token = api_token

    def create_ticket(self, ticket: AlmTicket) -> str:
        log.info("[Jira] Stub: create '%s'", ticket.title)
        return f"STUB-{abs(hash(ticket.title)) % 100000:05d}"

    def update_status(self, ticket_id: str, status: str) -> bool:
        log.info("[Jira] Stub: update %s -> %s", ticket_id, status)
        return True

    def find_by_label(self, label: str) -> list[AlmTicket]:
        log.info("[Jira] Stub: find by label '%s'", label)
        return []


class PolarionAdapter(AlmBackend):
    """Siemens Polarion WorkItem adapter (stub)."""

    def __init__(self, url: str = "", api_token: str = "", **_: Any) -> None:
        self.url = url
        self.api_token = api_token

    def create_ticket(self, ticket: AlmTicket) -> str:
        log.info("[Polarion] Stub: create WorkItem '%s'", ticket.title)
        return f"STUB-WI-{abs(hash(ticket.title)) % 100000:05d}"

    def update_status(self, ticket_id: str, status: str) -> bool:
        log.info("[Polarion] Stub: update %s -> %s", ticket_id, status)
        return True

    def find_by_label(self, label: str) -> list[AlmTicket]:
        log.info("[Polarion] Stub: find by label '%s'", label)
        return []


# Auto-register built-in adapters
register_adapter("jira", JiraAdapter)
register_adapter("polarion", PolarionAdapter)

__all__ = [
    "AlmBackend",
    "AlmTicket",
    "JiraAdapter",
    "PolarionAdapter",
    "create_adapter",
    "list_available_adapters",
    "register_adapter",
]
