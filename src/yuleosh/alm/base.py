# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
ALM (Application Lifecycle Management) — abstract base backends.

Defines :class:`AlmTicket` (data transfer object) and :class:`AlmBackend`
(abstract base class) for integrating with systems such as Jira, Polarion,
or Codebeamer.

Usage:
    from yuleosh.alm import AlmBackend, AlmTicket

    class JiraBackend(AlmBackend):
        def create_ticket(self, ticket: AlmTicket) -> str:
            ...
        def update_status(self, ticket_id: str, status: str) -> bool:
            ...
        def find_by_label(self, label: str) -> list[AlmTicket]:
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AlmTicket:
    """A ticket/issue in the ALM system.

    Attributes
    ----------
    id : str
        Unique identifier in the ALM system.
    title : str
        Short summary / title of the ticket.
    description : str
        Full description or body.
    status : str
        Workflow status: ``open`` | ``in_progress`` | ``resolved`` | ``closed``.
    priority : str
        Priority: ``low`` | ``medium`` | ``high`` | ``critical``.
    assignee : str
        Person or team assigned to the ticket.
    url : str
        Direct link to the ticket in the ALM web UI.
    labels : list[str]
        Tags or labels for search/categorisation.
    """

    id: str = ""
    title: str = ""
    description: str = ""
    status: str = "open"  # open | in_progress | resolved | closed
    priority: str = "medium"
    assignee: str = ""
    url: str = ""
    labels: list[str] = field(default_factory=list)


class AlmBackend(ABC):
    """Abstract base for ALM system backends.

    Subclasses implement the concrete transport for Jira, Polarion,
    Codebeamer, or other ALM platforms.
    """

    @abstractmethod
    def create_ticket(self, ticket: AlmTicket) -> str:
        """Create a ticket in the ALM system.

        Parameters
        ----------
        ticket : AlmTicket
            The ticket to create (``id`` field is typically ignored
            for creation; the backend assigns it).

        Returns
        -------
        str
            The newly created ticket's ID (or key).
        """
        ...

    @abstractmethod
    def update_status(self, ticket_id: str, status: str) -> bool:
        """Update the workflow status of an existing ticket.

        Parameters
        ----------
        ticket_id : str
            The ticket's ID or key in the ALM system.
        status : str
            New status: ``open`` | ``in_progress`` | ``resolved`` | ``closed``.

        Returns
        -------
        bool
            ``True`` if the update succeeded.
        """
        ...

    @abstractmethod
    def find_by_label(self, label: str) -> list[AlmTicket]:
        """Find tickets by label (e.g. ``'misra'``, ``'compliance'``).

        Parameters
        ----------
        label : str
            Label or tag to search for.

        Returns
        -------
        list[AlmTicket]
            Tickets matching the label.
        """
        ...
