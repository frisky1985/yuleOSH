# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Audit Log — Event Sourcing (SAAS-4).

Each state-changing operation is recorded as an immutable audit event.

Storage: data/audit/YYYY-MM-DD.jsonl (JSON Lines, one event per line)
Events are written in append mode — no edits, no deletes.

Usage:
    from yuleosh.audit import AuditLog

    log = AuditLog()
    log.record("user:42", "project.create", "project:my-proj",
               detail={"name": "My Project"}, tenant="my-org")
    events = log.query(tenant="my-org", from_date="2026-07-01", to_date="2026-07-27")
"""

from yuleosh.audit.model import (
    AuditLog,
    AuditEvent,
)
