# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
ALM (Application Lifecycle Management) integration interfaces.

Provides abstract base classes for connecting to ALM systems
like Jira, Polarion, or Codebeamer.

Usage:
    from yuleosh.alm import AlmBackend, AlmTicket
"""

from yuleosh.alm.base import AlmBackend, AlmTicket

__all__ = [
    "AlmBackend",
    "AlmTicket",
]
