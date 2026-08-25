#!/usr/bin/env python3

# @req RS-001  @req RS-005
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Shared audit helpers for step handlers (Q1).

record_step_verdict() writes a step.verdict event into the SHA-256 audit
hash chain.  It is non-fatal: any exception is logged as a warning so
it never blocks the pipeline.
"""

import hashlib
import logging
import os

log = logging.getLogger("pipeline.step_handlers.audit_utils")


def record_step_verdict(
    session,
    step_name: str,
    verdict: str,
    artifact_paths: "list[str] | None" = None,
) -> None:
    """Write a step.verdict audit event into the SHA-256 hash chain.

    Parameters
    ----------
    session:
        PipelineSession (or any object with a ``name`` attribute).
    step_name:
        The pipeline step identifier, e.g. ``"code-review"``.
    verdict:
        Outcome string, e.g. ``"passed"``, ``"failed"``, ``"skipped"``.
    artifact_paths:
        List of file paths whose SHA-256 digests are recorded.
        Empty/missing paths are silently skipped.
    """
    try:
        from yuleosh.audit.model import AuditLog

        def _sha256(path: str) -> str:
            h = hashlib.sha256()
            try:
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
            except OSError:
                return ""
            return h.hexdigest()

        paths = [p for p in (artifact_paths or []) if p]
        artifact_hashes = {os.path.basename(p): _sha256(p) for p in paths}

        audit_root = os.environ.get("YULEOSH_AUDIT_ROOT")
        audit_log = AuditLog(data_root=audit_root)
        session_id = getattr(session, "name", "") or getattr(session, "session_id", "")
        audit_log.record(
            actor="system",
            action="step.verdict",
            target=f"step:{step_name}",
            tenant="",
            detail={
                "step": step_name,
                "session_id": session_id,
                "verdict": verdict,
                "artifact_hashes": artifact_hashes,
            },
        )
        log.debug("step.verdict recorded: step=%s verdict=%s", step_name, verdict)
    except Exception as exc:
        log.warning("record_step_verdict failed (non-fatal): %s", exc)
