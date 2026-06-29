#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
深度测试 — yuleOSH Jira ALM adapter (alm.jira)

Covers:
  - JiraBackend.__init__: default and custom config
  - create_ticket: stub mode, real API success/failure
  - update_status: stub mode, transition lookup + POST
  - find_by_label: stub mode, JQL search
  - sync_evidence_to_ticket: comment POST, label update
  - sync_ticket_to_evidence: GET issue + comments
  - bulk_sync: aggregate stats
  - _format_evidence_comment: structured comment text
  - _get_session: session creation with auth headers
  - Edge cases: ImportError, API errors, status_map edge cases
"""

import json
from datetime import datetime

import pytest
from unittest import mock

from yuleosh.alm.base import AlmTicket
from yuleosh.alm.jira import JiraBackend


# ═════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_ticket() -> AlmTicket:
    """GIVEN a sample AlmTicket for testing."""
    return AlmTicket(
        title="Fix MISRA Violation",
        description="Address MISRA 10.1 in main.c",
        status="open",
        priority="high",
        labels=["misra", "safety"],
        assignee="dev1",
    )


@pytest.fixture
def jira_stub() -> JiraBackend:
    """GIVEN a JiraBackend with no real credentials (stub mode)."""
    return JiraBackend()


@pytest.fixture
def jira_connected() -> JiraBackend:
    """GIVEN a JiraBackend with credentials (real API mode)."""
    return JiraBackend(
        url="https://jira.example.com",
        api_token="tok_xyz789",
        project_key="YULE",
    )


# ═════════════════════════════════════════════════════════════════════════════
#  __init__
# ═════════════════════════════════════════════════════════════════════════════


class TestInit:
    """GIVEN JiraBackend.__init__()"""

    def test_default_config(self) -> None:
        """WHEN creating with no args THEN all fields are empty."""
        backend = JiraBackend()
        assert backend.url == ""
        assert backend.api_token == ""
        assert backend.project_key == ""
        assert backend._is_connected() is False

    def test_custom_config(self) -> None:
        """WHEN creating with explicit args THEN values are stored."""
        backend = JiraBackend(
            url="https://jira.test.com",
            api_token="test_token",
            project_key="TEST",
        )
        assert backend.url == "https://jira.test.com"
        assert backend.api_token == "test_token"
        assert backend.project_key == "TEST"
        assert backend._is_connected() is True


# ═════════════════════════════════════════════════════════════════════════════
#  _get_session
# ═════════════════════════════════════════════════════════════════════════════


class TestSession:
    """GIVEN _get_session()"""

    def test_session_has_headers(self, jira_connected) -> None:
        """WHEN creating session THEN Accept and Content-Type are set."""
        session = jira_connected._get_session()
        assert session is not None
        assert session.headers.get("Accept") == "application/json"
        assert session.headers.get("Content-Type") == "application/json"

    def test_bearer_auth(self, jira_connected) -> None:
        """WHEN no email is provided THEN Bearer token is used."""
        session = jira_connected._get_session()
        assert session.headers["Authorization"] == "Bearer tok_xyz789"

    def test_basic_auth_with_email(self) -> None:
        """WHEN email is provided THEN HTTPBasicAuth is used."""
        backend = JiraBackend(
            url="https://jira.test.com",
            api_token="token",
            project_key="P",
            email="user@example.com",
        )
        session = backend._get_session()
        assert session.auth is not None

    def test_session_cached(self, jira_connected) -> None:
        """WHEN _get_session is called twice THEN the same session is returned."""
        s1 = jira_connected._get_session()
        s2 = jira_connected._get_session()
        assert s1 is s2


# ═════════════════════════════════════════════════════════════════════════════
#  create_ticket
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateTicket:
    """GIVEN create_ticket()"""

    def test_stub_mode_returns_stub_key(self, jira_stub, sample_ticket) -> None:
        """WHEN not connected THEN a stub key is returned."""
        key = jira_stub.create_ticket(sample_ticket)
        assert key.startswith("STUB-JIRA-")

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_success(self, mock_get_session, jira_connected, sample_ticket) -> None:
        """WHEN API returns 201 THEN the issue key is returned."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 201
        mock_session.post.return_value.json.return_value = {"key": "YULE-42"}
        mock_session.post.return_value.raise_for_status = mock.MagicMock()
        mock_get_session.return_value = mock_session

        key = jira_connected.create_ticket(sample_ticket)
        assert key == "YULE-42"

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_uses_labels_from_ticket(self, mock_get_session, jira_connected, sample_ticket) -> None:
        """WHEN ticket has labels THEN they are sent in the payload."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 201
        mock_session.post.return_value.json.return_value = {"key": "YULE-42"}
        mock_get_session.return_value = mock_session

        jira_connected.create_ticket(sample_ticket)
        _, kwargs = mock_session.post.call_args
        fields = kwargs["json"]["fields"]
        assert "misra" in fields["labels"]
        assert "safety" in fields["labels"]

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_exception_raises(self, mock_get_session, jira_connected, sample_ticket) -> None:
        """WHEN API raises an exception THEN it is re-raised."""
        mock_session = mock.MagicMock()
        mock_session.post.side_effect = Exception("API error")
        mock_get_session.return_value = mock_session

        with pytest.raises(Exception, match="API error"):
            jira_connected.create_ticket(sample_ticket)

    def test_api_import_error_fallback(self, jira_connected, sample_ticket) -> None:
        """WHEN requests is not available THEN an exception is raised."""
        with mock.patch.dict("sys.modules", {"requests": None}):
            with pytest.raises(Exception):
                jira_connected.create_ticket(sample_ticket)


# ═════════════════════════════════════════════════════════════════════════════
#  update_status
# ═════════════════════════════════════════════════════════════════════════════


class TestUpdateStatus:
    """GIVEN update_status()"""

    def test_stub_mode_returns_true(self, jira_stub) -> None:
        """WHEN not connected THEN stub returns True."""
        assert jira_stub.update_status("YULE-1", "resolved") is True

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_transition_success(self, mock_get_session, jira_connected) -> None:
        """WHEN transition is found and POST succeeds THEN True is returned."""
        mock_session = mock.MagicMock()
        # GET transitions
        mock_session.get.return_value.json.return_value = {
            "transitions": [
                {"id": "11", "name": "Done"},
                {"id": "21", "name": "In Progress"},
                {"id": "31", "name": "To Do"},
            ]
        }
        mock_get_session.return_value = mock_session

        result = jira_connected.update_status("YULE-1", "resolved")
        assert result is True
        # Should find "Done" transition (resolved → Done)
        _, kwargs = mock_session.post.call_args
        assert kwargs["json"]["transition"]["id"] == "11"

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_transition_not_found(self, mock_get_session, jira_connected) -> None:
        """WHEN no matching transition exists THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {"transitions": []}
        mock_get_session.return_value = mock_session

        result = jira_connected.update_status("YULE-1", "resolved")
        assert result is False

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_exception(self, mock_get_session, jira_connected) -> None:
        """WHEN API raises an exception THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.side_effect = Exception("Timeout")
        mock_get_session.return_value = mock_session

        result = jira_connected.update_status("YULE-1", "resolved")
        assert result is False


# ═════════════════════════════════════════════════════════════════════════════
#  find_by_label
# ═════════════════════════════════════════════════════════════════════════════


class TestFindByLabel:
    """GIVEN find_by_label()"""

    def test_stub_mode_returns_empty(self, jira_stub) -> None:
        """WHEN not connected THEN empty list is returned."""
        tickets = jira_stub.find_by_label("misra")
        assert tickets == []

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_returns_issues(self, mock_get_session, jira_connected) -> None:
        """WHEN API returns issues THEN AlmTickets are constructed."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {
            "issues": [
                {
                    "key": "YULE-1",
                    "fields": {
                        "summary": "MISRA Fix",
                        "description": "Fix 10.1",
                        "status": {"name": "In Progress"},
                        "priority": {"name": "High"},
                        "assignee": {"displayName": "dev1"},
                        "labels": ["misra"],
                    },
                },
            ]
        }
        mock_get_session.return_value = mock_session

        tickets = jira_connected.find_by_label("misra")
        assert len(tickets) == 1
        assert tickets[0].id == "YULE-1"
        assert tickets[0].title == "MISRA Fix"
        assert tickets[0].status == "In Progress"
        assert tickets[0].assignee == "dev1"
        assert tickets[0].labels == ["misra"]

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_exception_returns_empty(self, mock_get_session, jira_connected) -> None:
        """WHEN API raises an exception THEN empty list is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.side_effect = Exception("JQL error")
        mock_get_session.return_value = mock_session

        tickets = jira_connected.find_by_label("misra")
        assert tickets == []


# ═════════════════════════════════════════════════════════════════════════════
#  sync_evidence_to_ticket
# ═════════════════════════════════════════════════════════════════════════════


class TestSyncEvidenceToTicket:
    """GIVEN sync_evidence_to_ticket()"""

    def test_stub_mode_returns_true(self, jira_stub) -> None:
        """WHEN not connected THEN stub returns True."""
        result = jira_stub.sync_evidence_to_ticket("YULE-1", {"coverage": 85.0})
        assert result is True

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_success_with_label_add(self, mock_get_session, jira_connected) -> None:
        """WHEN comment POST succeeds AND label is new THEN label is added."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 201
        mock_session.post.return_value.raise_for_status = mock.MagicMock()

        # GET issue for label check
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "fields": {"labels": ["existing"]}
        }

        # PUT for label update
        mock_session.put.return_value.ok = True
        mock_get_session.return_value = mock_session

        result = jira_connected.sync_evidence_to_ticket(
            "YULE-1", {"type": "coverage", "line_rate": 85.0}
        )
        assert result is True
        # Verify PUT was called to add the label
        mock_session.put.assert_called_once()
        _, kwargs = mock_session.put.call_args
        assert "yuleosh-evidence" in kwargs["json"]["fields"]["labels"]

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_label_already_present(self, mock_get_session, jira_connected) -> None:
        """WHEN label already exists THEN no PUT is made."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 201
        mock_session.post.return_value.raise_for_status = mock.MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "fields": {"labels": ["yuleosh-evidence"]}
        }
        mock_get_session.return_value = mock_session

        result = jira_connected.sync_evidence_to_ticket(
            "YULE-1", {"type": "coverage"}
        )
        assert result is True
        mock_session.put.assert_not_called()

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_exception_returns_false(self, mock_get_session, jira_connected) -> None:
        """WHEN API raises an exception THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.post.side_effect = Exception("Comment error")
        mock_get_session.return_value = mock_session

        result = jira_connected.sync_evidence_to_ticket("YULE-1", {"type": "test"})
        assert result is False


# ═════════════════════════════════════════════════════════════════════════════
#  sync_ticket_to_evidence
# ═════════════════════════════════════════════════════════════════════════════


class TestSyncTicketToEvidence:
    """GIVEN sync_ticket_to_evidence()"""

    def test_stub_mode_returns_stub_dict(self, jira_stub) -> None:
        """WHEN not connected THEN stub evidence dict is returned."""
        evidence = jira_stub.sync_ticket_to_evidence("YULE-1")
        assert evidence["source"] == "jira"
        assert evidence["ticket_id"] == "YULE-1"
        assert evidence["status"] == "stub"

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_fetch_issue(self, mock_get_session, jira_connected) -> None:
        """WHEN API returns issue data THEN structured evidence is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.json.return_value = {
            "fields": {
                "summary": "Fix MISRA",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "dev1"},
                "labels": ["misra"],
                "updated": "2025-01-01T00:00:00Z",
                "comment": {
                    "comments": [
                        {
                            "author": {"displayName": "user1"},
                            "body": "Evidence synced",
                            "created": "2025-01-01T00:00:00Z",
                        },
                    ]
                },
            },
        }
        mock_get_session.return_value = mock_session

        evidence = jira_connected.sync_ticket_to_evidence("YULE-1")
        assert evidence["summary"] == "Fix MISRA"
        assert evidence["status"] == "In Progress"
        assert evidence["assignee"] == "dev1"
        assert evidence["labels"] == ["misra"]
        assert len(evidence["comments"]) == 1
        assert evidence["comments"][0]["author"] == "user1"

    @mock.patch.object(JiraBackend, "_get_session")
    def test_api_exception_returns_none(self, mock_get_session, jira_connected) -> None:
        """WHEN API raises an exception THEN None is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.side_effect = Exception("Network failure")
        mock_get_session.return_value = mock_session

        evidence = jira_connected.sync_ticket_to_evidence("YULE-1")
        assert evidence is None


# ═════════════════════════════════════════════════════════════════════════════
#  bulk_sync
# ═════════════════════════════════════════════════════════════════════════════


class TestBulkSync:
    """GIVEN bulk_sync()"""

    def test_stub_mode_returns_zero_stats(self, jira_stub) -> None:
        """WHEN not connected THEN stats with zero counts are returned."""
        stats = jira_stub.bulk_sync("yuleosh")
        assert stats["issues_found"] == 0
        assert stats["evidence_attached"] == 0

    @mock.patch.object(JiraBackend, "find_by_label")
    @mock.patch.object(JiraBackend, "sync_evidence_to_ticket")
    def test_bulk_sync_all_succeed(self, mock_sync, mock_find, jira_connected) -> None:
        """WHEN all syncs succeed THEN stats reflect all items."""
        mock_find.return_value = [
            AlmTicket(id="YULE-1", title="T1"),
            AlmTicket(id="YULE-2", title="T2"),
            AlmTicket(id="YULE-3", title="T3"),
        ]
        mock_sync.return_value = True

        stats = jira_connected.bulk_sync("safety")
        assert stats["issues_found"] == 3
        assert stats["evidence_attached"] == 3
        assert stats["errors"] == 0

    @mock.patch.object(JiraBackend, "find_by_label")
    @mock.patch.object(JiraBackend, "sync_evidence_to_ticket")
    def test_bulk_sync_with_errors(self, mock_sync, mock_find, jira_connected) -> None:
        """WHEN some syncs have errors THEN errors count is incremented."""
        mock_find.return_value = [
            AlmTicket(id="YULE-1", title="T1"),
        ]
        mock_sync.side_effect = Exception("Boom")

        stats = jira_connected.bulk_sync("safety")
        assert stats["issues_found"] == 1
        assert stats["evidence_attached"] == 0
        assert stats["errors"] == 1


# ═════════════════════════════════════════════════════════════════════════════
#  _format_evidence_comment
# ═════════════════════════════════════════════════════════════════════════════


class TestFormatEvidenceComment:
    """GIVEN _format_evidence_comment()"""

    def test_contains_all_fields(self) -> None:
        """WHEN formatting evidence THEN structured comment includes all fields."""
        evidence = {
            "type": "coverage",
            "timestamp": "2025-06-01T12:00:00",
            "line_rate": 85.0,
            "tags": ["misra"],
        }
        text = JiraBackend._format_evidence_comment(evidence)
        assert "=== yuleOSH Evidence Sync ===" in text
        assert "Time: 2025-06-01T12:00:00" in text
        assert "Type: coverage" in text

    def test_handles_dict_and_list_values(self) -> None:
        """WHEN evidence contains dict values THEN they are JSON-formatted."""
        evidence = {
            "type": "compliance",
            "report": {"line_rate": 85.0, "branch_rate": 72.0},
            "timestamp": "T1",
        }
        text = JiraBackend._format_evidence_comment(evidence)
        assert "line_rate" in text


# ═════════════════════════════════════════════════════════════════════════════
#  Edge cases: empty labels, status_map edge, assignee handling
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """GIVEN edge cases in JiraBackend"""

    def test_create_ticket_no_labels(self, jira_connected) -> None:
        """WHEN ticket has no labels THEN default labels are used."""
        ticket = AlmTicket(title="No Labels", description="test")
        with mock.patch.object(jira_connected, "_get_session") as mock_get:
            mock_session = mock.MagicMock()
            mock_session.post.return_value.status_code = 201
            mock_session.post.return_value.json.return_value = {"key": "YULE-1"}
            mock_get.return_value = mock_session

            jira_connected.create_ticket(ticket)
            _, kwargs = mock_session.post.call_args
            assert kwargs["json"]["fields"]["labels"] == ["yuleosh"]

    def test_update_status_reopened_map(self, jira_connected) -> None:
        """WHEN status is 'reopened' THEN it maps to 'To Do'."""
        with mock.patch.object(jira_connected, "_get_session") as mock_get:
            mock_session = mock.MagicMock()
            mock_session.get.return_value.json.return_value = {
                "transitions": [{"id": "31", "name": "To Do"}]
            }
            mock_get.return_value = mock_session

            jira_connected.update_status("YULE-1", "reopened")
            _, kwargs = mock_session.post.call_args
            assert kwargs["json"]["transition"]["id"] == "31"

    def test_sync_ticket_no_assignee(self, jira_connected) -> None:
        """WHEN issue has no assignee THEN empty string is returned."""
        with mock.patch.object(jira_connected, "_get_session") as mock_get:
            mock_session = mock.MagicMock()
            mock_session.get.return_value.json.return_value = {
                "fields": {
                    "summary": "Test",
                    "status": {"name": "Open"},
                    "assignee": None,
                    "labels": [],
                    "updated": "",
                    "comment": {"comments": []},
                },
            }
            mock_get.return_value = mock_session

            evidence = jira_connected.sync_ticket_to_evidence("YULE-1")
            assert evidence["assignee"] == ""

    def test_create_ticket_with_assignee(self, jira_connected) -> None:
        """WHEN ticket has an assignee THEN it is included in payload."""
        ticket = AlmTicket(title="Assigned", description="test", assignee="jane")
        with mock.patch.object(jira_connected, "_get_session") as mock_get:
            mock_session = mock.MagicMock()
            mock_session.post.return_value.status_code = 201
            mock_session.post.return_value.json.return_value = {"key": "YULE-1"}
            mock_get.return_value = mock_session

            jira_connected.create_ticket(ticket)
            _, kwargs = mock_session.post.call_args
            assert kwargs["json"]["fields"]["assignee"]["name"] == "jane"
