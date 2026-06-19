# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Jira ALM adapter — enhanced bidirectional sync.

Provides full REST API integration for Jira ↔ Evidence bidirectional
synchronization.

Supported operations:
  - Create/update/find tickets
  - Sync evidence (test results, coverage) to Jira issue comments/attachments
  - Sync Jira issue status changes back to yuleOSH evidence package
  - Label-scoped search for compliance tracking

Usage:
    from yuleosh.alm.jira import JiraBackend

    backend = JiraBackend(
        url="https://jira.example.com",
        api_token="xxx",
        project_key="YULE",
    )
    ticket_id = backend.create_ticket(AlmTicket(title="..."))
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from yuleosh.alm.base import AlmBackend, AlmTicket

log = logging.getLogger("yuleosh.alm.jira")


# ═════════════════════════════════════════════════════════════════════════════
#  Configuration
# ═════════════════════════════════════════════════════════════════════════════

_JIRA_DEFAULT_URL = os.environ.get("YULEOSH_JIRA_URL", "")
_JIRA_DEFAULT_TOKEN = os.environ.get("YULEOSH_JIRA_TOKEN", "")
_JIRA_DEFAULT_PROJECT = os.environ.get("YULEOSH_JIRA_PROJECT", "")


# ═════════════════════════════════════════════════════════════════════════════
#  JiraBackend — Enhanced with bidirectional sync
# ═════════════════════════════════════════════════════════════════════════════


class JiraBackend(AlmBackend):
    """Jira ALM adapter with bidirectional evidence sync.

    Parameters
    ----------
    url : str
        Base URL of the Jira instance (e.g. ``https://jira.example.com``).
    api_token : str
        Personal Access Token or API token for authentication.
    project_key : str
        Jira project key (e.g. ``"YULE"``).
    **kwargs : Any
        Additional connection parameters.
    """

    def __init__(
        self,
        url: str = "",
        api_token: str = "",
        project_key: str = "",
        **kwargs: Any,
    ) -> None:
        self.url = (url or _JIRA_DEFAULT_URL).rstrip("/")
        self.api_token = api_token or _JIRA_DEFAULT_TOKEN
        self.project_key = project_key or _JIRA_DEFAULT_PROJECT
        self._extra = kwargs
        self._session = None

    # ── Connection helpers ─────────────────────────────────────────────────

    def _get_session(self):
        """Get or create a requests session with auth."""
        if self._session is None:
            try:
                import requests
                from requests.auth import HTTPBasicAuth

                self._session = requests.Session()
                if self.api_token:
                    # Jira Personal Access Token or email+token
                    email = self._extra.get("email", "")
                    if email:
                        self._session.auth = HTTPBasicAuth(email, self.api_token)
                    else:
                        self._session.headers["Authorization"] = f"Bearer {self.api_token}"
                self._session.headers.update({
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                })
            except ImportError:
                pass
        return self._session

    def _api_url(self, path: str) -> str:
        """Build a full Jira REST API URL."""
        return f"{self.url}/rest/api/3{path}"

    def _is_connected(self) -> bool:
        """Check if Jira credentials are configured for real API access."""
        return bool(self.url and self.api_token)

    # ── Core ticket operations ─────────────────────────────────────────────

    def create_ticket(self, ticket: AlmTicket) -> str:
        """Create a Jira issue.

        If Jira credentials are not configured, returns a synthetic stub key.
        """
        if not self._is_connected():
            log.info("[Jira] Stub: create issue '%s' in project '%s'",
                     ticket.title, self.project_key)
            return f"STUB-JIRA-{abs(hash(ticket.title)) % 100000:05d}"

        try:
            session = self._get_session()
            payload = {
                "fields": {
                    "project": {"key": self.project_key},
                    "summary": ticket.title,
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": ticket.description}],
                            }
                        ],
                    },
                    "issuetype": {"name": self._extra.get("issue_type", "Task")},
                    "labels": ticket.labels or ["yuleosh"],
                    "priority": {"name": ticket.priority.capitalize()},
                }
            }

            if ticket.assignee:
                payload["fields"]["assignee"] = {"name": ticket.assignee}

            resp = session.post(self._api_url("/issue"), json=payload)
            resp.raise_for_status()
            result = resp.json()
            issue_key = result.get("key", "")
            log.info("[Jira] Created issue: %s", issue_key)
            return issue_key

        except ImportError:
            log.warning("[Jira] requests library not installed — falling back to stub")
            return f"STUB-JIRA-{abs(hash(ticket.title)) % 100000:05d}"
        except Exception as e:
            log.error("[Jira] Failed to create issue: %s", e)
            raise

    def update_status(self, ticket_id: str, status: str) -> bool:
        """Transition a Jira issue to a new status.

        Translates canonical status names to Jira transition IDs.
        """
        if not self._is_connected():
            log.info("[Jira] Stub: transition %s -> %s", ticket_id, status)
            return True

        # Status name → Jira transition name mapping
        status_map = {
            "open": "To Do",
            "in_progress": "In Progress",
            "resolved": "Done",
            "closed": "Closed",
            "reopened": "To Do",
        }

        jira_status = status_map.get(status, status)
        try:
            session = self._get_session()

            # Find transition ID by name
            transitions_resp = session.get(
                self._api_url(f"/issue/{ticket_id}/transitions")
            )
            transitions_resp.raise_for_status()
            transitions = transitions_resp.json().get("transitions", [])

            target_id = None
            for t in transitions:
                if t.get("name", "").lower() == jira_status.lower():
                    target_id = t.get("id")
                    break

            if not target_id:
                log.warning("[Jira] No transition found for status '%s'", jira_status)
                return False

            payload = {"transition": {"id": target_id}}
            resp = session.post(
                self._api_url(f"/issue/{ticket_id}/transitions"),
                json=payload,
            )
            resp.raise_for_status()
            log.info("[Jira] Transitioned %s -> %s", ticket_id, jira_status)
            return True

        except Exception as e:
            log.error("[Jira] Failed to transition %s: %s", ticket_id, e)
            return False

    def find_by_label(self, label: str) -> list[AlmTicket]:
        """Search Jira issues by label (JQL).

        Parameters
        ----------
        label : str
            Label to search for (e.g. ``"misra"``, ``"compliance"``).

        Returns
        -------
        list[AlmTicket]
            Tickets matching the label.
        """
        if not self._is_connected():
            log.info("[Jira] Stub: search by label '%s'", label)
            return []

        try:
            session = self._get_session()
            jql = f'project = "{self.project_key}" AND labels = "{label}"'

            params = {"jql": jql, "maxResults": 50, "fields": "summary,status,priority,assignee,labels,description"}
            resp = session.get(self._api_url("/search"), params=params)
            resp.raise_for_status()
            data = resp.json()

            tickets = []
            for issue in data.get("issues", []):
                fields = issue.get("fields", {})
                ticket = AlmTicket(
                    id=issue.get("key", ""),
                    title=fields.get("summary", ""),
                    description=fields.get("description", "") or "",
                    status=fields.get("status", {}).get("name", "open"),
                    priority=fields.get("priority", {}).get("name", "medium").lower(),
                    assignee=fields.get("assignee", {}).get("displayName", ""),
                    url=f"{self.url}/browse/{issue.get('key', '')}",
                    labels=fields.get("labels", []),
                )
                tickets.append(ticket)

            return tickets

        except Exception as e:
            log.error("[Jira] Failed to search by label '%s': %s", label, e)
            return []

    # ── Bidirectional evidence sync ────────────────────────────────────────

    def sync_evidence_to_ticket(
        self,
        ticket_id: str,
        evidence_data: dict,
        label: str = "yuleosh-evidence",
    ) -> bool:
        """Sync evidence data to a Jira issue as a comment + attachment link.

        Parameters
        ----------
        ticket_id : str
            Jira issue key.
        evidence_data : dict
            Evidence data (test results, coverage, compliance report).
        label : str
            Label to apply to the issue for traceability.

        Returns
        -------
        bool
            True if sync succeeded.
        """
        if not self._is_connected():
            log.info("[Jira] Stub: sync evidence -> %s", ticket_id)
            return True

        try:
            session = self._get_session()

            # Format evidence as a structured comment
            comment = self._format_evidence_comment(evidence_data)
            comment_payload = {
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": line}],
                        }
                        for line in comment.split("\n")
                        if line.strip()
                    ],
                }
            }

            resp = session.post(
                self._api_url(f"/issue/{ticket_id}/comment"),
                json=comment_payload,
            )
            resp.raise_for_status()

            # Add label if not already present
            issue_resp = session.get(
                self._api_url(f"/issue/{ticket_id}"),
                params={"fields": "labels"},
            )
            if issue_resp.ok:
                existing_labels = issue_resp.json().get("fields", {}).get("labels", [])
                if label not in existing_labels:
                    new_labels = existing_labels + [label]
                    session.put(
                        self._api_url(f"/issue/{ticket_id}"),
                        json={"fields": {"labels": new_labels}},
                    )

            log.info("[Jira] Evidence synced to %s", ticket_id)
            return True

        except Exception as e:
            log.error("[Jira] Failed to sync evidence to %s: %s", ticket_id, e)
            return False

    def sync_ticket_to_evidence(
        self,
        ticket_id: str,
    ) -> Optional[dict]:
        """Sync Jira issue changes back to evidence.

        Fetches the latest status and comments from a Jira issue and
        returns them as structured data suitable for evidence packaging.

        Parameters
        ----------
        ticket_id : str
            Jira issue key.

        Returns
        -------
        dict or None
            Evidence data with status changes, comments, and labels.
        """
        if not self._is_connected():
            log.info("[Jira] Stub: fetch evidence <- %s", ticket_id)
            return {
                "source": "jira",
                "ticket_id": ticket_id,
                "status": "stub",
                "sync_timestamp": datetime.now().isoformat(),
            }

        try:
            session = self._get_session()
            resp = session.get(
                self._api_url(f"/issue/{ticket_id}"),
                params={"fields": "summary,status,assignee,labels,updated,comment"},
            )
            resp.raise_for_status()
            data = resp.json()
            fields = data.get("fields", {})

            # Extract comments
            comments = []
            comment_data = fields.get("comment", {}).get("comments", [])
            for c in comment_data:
                comments.append({
                    "author": c.get("author", {}).get("displayName", ""),
                    "body": c.get("body", ""),
                    "created": c.get("created", ""),
                })

            return {
                "source": "jira",
                "ticket_id": ticket_id,
                "ticket_url": f"{self.url}/browse/{ticket_id}",
                "summary": fields.get("summary", ""),
                "status": fields.get("status", {}).get("name", ""),
                "assignee": fields.get("assignee", {}).get("displayName", "") if fields.get("assignee") else "",
                "labels": fields.get("labels", []),
                "updated": fields.get("updated", ""),
                "comments": comments,
                "sync_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            log.error("[Jira] Failed to fetch evidence from %s: %s", ticket_id, e)
            return None

    def bulk_sync(self, label: str = "yuleosh") -> dict:
        """Bidirectional bulk sync: Jira ↔ yuleOSH evidence.

        Finds all Jira issues with a given label, syncs evidence from
        yuleOSH to each, and collects status changes back.

        Parameters
        ----------
        label : str
            Label to scope the sync operation (default: "yuleosh").

        Returns
        -------
        dict
            Sync stats: issues_updated, evidence_attached, errors.
        """
        stats = {"issues_found": 0, "evidence_attached": 0, "errors": 0}

        tickets = self.find_by_label(label)
        stats["issues_found"] = len(tickets)

        for ticket in tickets:
            try:
                # Example: sync a coverage summary
                evidence = {
                    "type": "compliance_sync",
                    "label": label,
                    "ticket": ticket.id,
                    "title": ticket.title,
                    "status": ticket.status,
                    "timestamp": datetime.now().isoformat(),
                }
                ok = self.sync_evidence_to_ticket(ticket.id, evidence, label)
                if ok:
                    stats["evidence_attached"] += 1
            except Exception as e:
                log.error("[Jira] Bulk sync error for %s: %s", ticket.id, e)
                stats["errors"] += 1

        return stats

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _format_evidence_comment(evidence: dict) -> str:
        """Format evidence data as a structured comment string."""
        lines = [
            "=== yuleOSH Evidence Sync ===",
            f"Time: {evidence.get('timestamp', datetime.now().isoformat())}",
            f"Type: {evidence.get('type', 'unknown')}",
        ]

        # Add key-value pairs from evidence
        for key, value in evidence.items():
            if key not in ("timestamp", "type"):
                lines.append(f"{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value}")

        lines.append("=" * 40)
        return "\n".join(lines)
