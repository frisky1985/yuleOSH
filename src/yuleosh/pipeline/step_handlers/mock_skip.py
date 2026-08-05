#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Mock-mode helpers for pipeline step handlers.

In ``--mock`` runs the LLM emits placeholder artifacts and code-quality
steps scan the REAL project tree, producing false failures (missing
headers, placeholder code, empty knowledge graph). Such steps SHALL
record a SKIPPED report and pass instead of blocking the demo.

Usage::

    from yuleosh.pipeline.step_handlers.mock_skip import is_mock, write_mock_skip

    def step_xxx(session) -> str:
        if is_mock(session):
            return write_mock_skip(session, "xxx", "mock mode — no real code")
        ...

The ``is True`` strict check keeps unittest MagicMock sessions honest:
``getattr(MagicMock(), "mock_mode", None)`` returns a truthy MagicMock,
which would otherwise flip every test into skip mode.
"""

import json
from datetime import datetime
from pathlib import Path


def is_mock(session) -> bool:
    """Return True only when the session is explicitly in mock mode."""
    return getattr(session, "mock_mode", None) is True


def write_mock_skip(session, step_key: str, reason: str,
                    report_extra: dict | None = None,
                    suffix: str = "json") -> str:
    """Write a SKIPPED report for ``step_key`` and return its path.

    Parameters
    ----------
    session : PipelineSession
        Active pipeline session (``session_dir`` must exist).
    step_key : str
        Pipeline step key, e.g. ``review-linker``.
    reason : str
        Human-readable skip reason (recorded in the report).
    report_extra : dict, optional
        Extra fields merged into the report.
    suffix : str
        Report file extension (default ``json``).
    """
    report = {
        "step": step_key,
        "session": getattr(session, "name", ""),
        "timestamp": datetime.now().isoformat(),
        "status": "skipped",
        "reason": reason,
    }
    if report_extra:
        report.update(report_extra)

    out_path = Path(session.session_dir) / f"{step_key}.{suffix}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return str(out_path)
