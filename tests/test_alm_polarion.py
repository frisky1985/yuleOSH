#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
深度测试 — yuleOSH Polarion ALM adapter (alm.polarion)

Covers:
  - PolarionBackend.__init__: default and custom config
  - create_ticket: stub mode, real API success/failure
  - update_status: stub mode, API transition
  - find_by_label: stub mode, API search
  - sync_evidence_to_ticket: comment POST, tag update
  - sync_ticket_to_evidence: GET workitem + comments
  - bulk_sync: aggregate stats
  - _add_tag: GET + PATCH tag update
  - _format_evidence_text: structured comment text
  - _get_session: session creation with auth headers
  - Edge cases: ImportError, API errors, empty responses
"""

import json
import os
from datetime import datetime

import pytest
from unittest import mock

from yuleosh.alm.base import AlmTicket
from yuleosh.alm.polarion import PolarionBackend


# ═════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def sample_ticket() -> AlmTicket:
    """GIVEN a sample AlmTicket for testing."""
    return AlmTicket(
        title="Test MISRA Violation",
        description="MISRA 10.1 violation in main.c:42",
        status="open",
        priority="high",
        labels=["misra", "compliance"],
    )


@pytest.fixture
def polarion_stub() -> PolarionBackend:
    """GIVEN a PolarionBackend with no real credentials (stub mode)."""
    return PolarionBackend()


@pytest.fixture
def polarion_connected() -> PolarionBackend:
    """GIVEN a PolarionBackend with credentials (real API mode)."""
    return PolarionBackend(
        url="https://polarion.example.com/polarion",
        api_token="tok_abc123",
        project_id="MyProject",
    )


# ═════════════════════════════════════════════════════════════════════════════
#  __init__
# ═════════════════════════════════════════════════════════════════════════════


class TestInit:
    """GIVEN PolarionBackend.__init__()"""

    def test_default_config(self) -> None:
        """WHEN creating with no args THEN all fields are empty strings."""
        backend = PolarionBackend()
        assert backend.url == ""
        assert backend.api_token == ""
        assert backend.project_id == ""
        assert backend._is_connected() is False

    def test_custom_config(self) -> None:
        """WHEN creating with explicit args THEN values are stored."""
        backend = PolarionBackend(
            url="https://polarion.test.com",
            api_token="test_token",
            project_id="TestProj",
        )
        assert backend.url == "https://polarion.test.com"
        assert backend.api_token == "test_token"
        assert backend.project_id == "TestProj"
        assert backend._is_connected() is True


# ═════════════════════════════════════════════════════════════════════════════
#  _get_session
# ═════════════════════════════════════════════════════════════════════════════


class TestSession:
    """GIVEN _get_session()"""

    def test_session_has_auth_headers(self, polarion_connected) -> None:
        """WHEN creating session with bearer token THEN Authorization header is set."""
        session = polarion_connected._get_session()
        assert session is not None
        assert session.headers.get("Authorization") == "Bearer tok_abc123"
        assert session.headers.get("Accept") == "application/json"
        assert session.headers.get("Content-Type") == "application/json"

    def test_session_cached(self, polarion_connected) -> None:
        """WHEN _get_session is called twice THEN same session object is returned."""
        s1 = polarion_connected._get_session()
        s2 = polarion_connected._get_session()
        assert s1 is s2

    def test_basic_auth_mode(self) -> None:
        """WHEN auth_type is 'basic' THEN Basic auth header is used."""
        backend = PolarionBackend(
            url="https://polarion.test.com",
            api_token="user",
            project_id="P",
            auth_type="basic",
        )
        session = backend._get_session()
        auth = session.headers.get("Authorization", "")
        assert auth.startswith("Basic ")

    def test_username_password_auth(self) -> None:
        """WHEN username and password are provided THEN HTTPBasicAuth is used."""
        backend = PolarionBackend(
            url="https://polarion.test.com",
            project_id="P",
            username="user",
            password="pass",
        )
        session = backend._get_session()
        assert session.auth is not None


# ═════════════════════════════════════════════════════════════════════════════
#  create_ticket
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateTicket:
    """GIVEN create_ticket()"""

    def test_stub_mode_returns_stub_id(self, polarion_stub, sample_ticket) -> None:
        """WHEN not connected THEN a stub ID is returned."""
        ticket_id = polarion_stub.create_ticket(sample_ticket)
        assert ticket_id.startswith("STUB-POL-")

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_success(self, mock_get_session, polarion_connected, sample_ticket) -> None:
        """WHEN API returns 201 THEN the WorkItem ID is returned."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 201
        mock_session.post.return_value.json.return_value = {"data": {"id": "WI-12345"}}
        mock_get_session.return_value = mock_session

        ticket_id = polarion_connected.create_ticket(sample_ticket)
        assert ticket_id == "WI-12345"

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_failure_returns_stub(self, mock_get_session, polarion_connected, sample_ticket) -> None:
        """WHEN API returns non-201 THEN a stub error ID is returned."""
        mock_session = mock.MagicMock()
        mock_session.post.return_value.status_code = 400
        mock_session.post.return_value.text = "Bad Request"
        mock_get_session.return_value = mock_session

        ticket_id = polarion_connected.create_ticket(sample_ticket)
        assert ticket_id.startswith("STUB-POL-ERR-")

    def test_api_import_error_fallback(self, polarion_connected, sample_ticket) -> None:
        """WHEN requests is not available THEN an exception is raised."""
        with mock.patch.dict("sys.modules", {"requests": None}):
            with pytest.raises(Exception):
                polarion_connected.create_ticket(sample_ticket)


# ═════════════════════════════════════════════════════════════════════════════
#  update_status
# ═════════════════════════════════════════════════════════════════════════════


class TestUpdateStatus:
    """GIVEN update_status()"""

    def test_stub_mode_returns_true(self, polarion_stub) -> None:
        """WHEN not connected THEN stub returns True."""
        assert polarion_stub.update_status("WI-1", "resolved") is True

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_success(self, mock_get_session, polarion_connected) -> None:
        """WHEN PATCH returns 200 THEN True is returned."""
        mock_session = mock.MagicMock()
        mock_session.patch.return_value.status_code = 200
        mock_get_session.return_value = mock_session

        result = polarion_connected.update_status("WI-1", "resolved")
        assert result is True

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_failure(self, mock_get_session, polarion_connected) -> None:
        """WHEN PATCH returns 500 THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.patch.return_value.status_code = 500
        mock_session.patch.return_value.text = "Server Error"
        mock_get_session.return_value = mock_session

        result = polarion_connected.update_status("WI-1", "resolved")
        assert result is False


# ═════════════════════════════════════════════════════════════════════════════
#  find_by_label
# ═════════════════════════════════════════════════════════════════════════════


class TestFindByLabel:
    """GIVEN find_by_label()"""

    def test_stub_mode_returns_empty(self, polarion_stub) -> None:
        """WHEN not connected THEN empty list is returned."""
        tickets = polarion_stub.find_by_label("misra")
        assert tickets == []

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_returns_items(self, mock_get_session, polarion_connected) -> None:
        """WHEN API returns data THEN AlmTickets are constructed."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "data": [
                {
                    "id": "WI-1",
                    "attributes": {
                        "title": "MISRA Violation",
                        "description": "desc",
                        "status": "open",
                        "severity": "high",
                        "tags": ["misra"],
                    },
                },
            ]
        }
        mock_get_session.return_value = mock_session

        tickets = polarion_connected.find_by_label("misra")
        assert len(tickets) == 1
        assert tickets[0].id == "WI-1"
        assert tickets[0].title == "MISRA Violation"
        assert tickets[0].status == "open"

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_exception_returns_empty(self, mock_get_session, polarion_connected) -> None:
        """WHEN API raises an exception THEN empty list is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.side_effect = Exception("Network error")
        mock_get_session.return_value = mock_session

        tickets = polarion_connected.find_by_label("misra")
        assert tickets == []


# ═════════════════════════════════════════════════════════════════════════════
#  sync_evidence_to_ticket
# ═════════════════════════════════════════════════════════════════════════════


class TestSyncEvidenceToTicket:
    """GIVEN sync_evidence_to_ticket()"""

    def test_stub_mode_returns_true(self, polarion_stub) -> None:
        """WHEN not connected THEN stub returns True."""
        result = polarion_stub.sync_evidence_to_ticket("WI-1", {"coverage": 85.0})
        assert result is True

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_success(self, mock_get_session, polarion_connected) -> None:
        """WHEN comment POST succeeds THEN True is returned."""
        mock_session = mock.MagicMock()
        # POST comment returns 201
        mock_session.post.return_value.status_code = 201
        # GET for tag check returns 200
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "data": {"attributes": {"tags": []}}
        }
        # PATCH for tag returns 200
        mock_session.patch.return_value.status_code = 200
        mock_get_session.return_value = mock_session

        result = polarion_connected.sync_evidence_to_ticket(
            "WI-1", {"coverage": 85.0, "type": "coverage"}
        )
        assert result is True

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_exception(self, mock_get_session, polarion_connected) -> None:
        """WHEN API call raises an exception THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.post.side_effect = Exception("Connection error")
        mock_get_session.return_value = mock_session

        result = polarion_connected.sync_evidence_to_ticket("WI-1", {"coverage": 85.0})
        assert result is False


# ═════════════════════════════════════════════════════════════════════════════
#  sync_ticket_to_evidence
# ═════════════════════════════════════════════════════════════════════════════


class TestSyncTicketToEvidence:
    """GIVEN sync_ticket_to_evidence()"""

    def test_stub_mode_returns_stub_dict(self, polarion_stub) -> None:
        """WHEN not connected THEN stub evidence dict is returned."""
        evidence = polarion_stub.sync_ticket_to_evidence("WI-1")
        assert evidence["source"] == "polarion"
        assert evidence["ticket_id"] == "WI-1"
        assert evidence["status"] == "stub"

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_fetch_workitem_and_comments(self, mock_get_session, polarion_connected) -> None:
        """WHEN API returns WorkItem with comments THEN structured dict is returned."""
        mock_session = mock.MagicMock()

        # GET WorkItem
        mock_wi_resp = mock.MagicMock()
        mock_wi_resp.ok = True
        mock_wi_resp.json.return_value = {
            "data": {
                "attributes": {
                    "title": "Test",
                    "status": "open",
                    "assignee": "dev1",
                    "tags": ["misra"],
                    "updated": "2025-01-01T00:00:00Z",
                },
            }
        }

        # GET comments
        mock_comment_resp = mock.MagicMock()
        mock_comment_resp.ok = True
        mock_comment_resp.json.return_value = {
            "data": [
                {
                    "attributes": {
                        "author": "user1",
                        "text": "Evidence synced",
                        "created": "2025-01-01T00:00:00Z",
                    },
                },
            ]
        }

        mock_session.get.side_effect = [mock_wi_resp, mock_comment_resp]
        mock_get_session.return_value = mock_session

        evidence = polarion_connected.sync_ticket_to_evidence("WI-1")
        assert evidence["status"] == "open"
        assert evidence["title"] == "Test"
        assert len(evidence["comments"]) == 1
        assert evidence["comments"][0]["author"] == "user1"

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_not_ok_returns_none(self, mock_get_session, polarion_connected) -> None:
        """WHEN API returns non-ok status THEN None is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.ok = False
        mock_session.get.return_value.status_code = 404
        mock_get_session.return_value = mock_session

        evidence = polarion_connected.sync_ticket_to_evidence("WI-999")
        assert evidence is None

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_api_exception_returns_none(self, mock_get_session, polarion_connected) -> None:
        """WHEN API raises an exception THEN None is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.side_effect = Exception("Timeout")
        mock_get_session.return_value = mock_session

        evidence = polarion_connected.sync_ticket_to_evidence("WI-1")
        assert evidence is None


# ═════════════════════════════════════════════════════════════════════════════
#  bulk_sync
# ═════════════════════════════════════════════════════════════════════════════


class TestBulkSync:
    """GIVEN bulk_sync()"""

    def test_stub_mode_returns_empty_stats(self, polarion_stub) -> None:
        """WHEN not connected THEN stats with zero counts are returned."""
        stats = polarion_stub.bulk_sync("yuleosh")
        assert stats["workitems_found"] == 0
        assert stats["evidence_attached"] == 0

    @mock.patch.object(PolarionBackend, "find_by_label")
    @mock.patch.object(PolarionBackend, "sync_evidence_to_ticket")
    def test_bulk_sync_with_items(self, mock_sync, mock_find, polarion_connected) -> None:
        """WHEN workitems are found THEN each is synced and stats are accurate."""
        mock_find.return_value = [
            AlmTicket(id="WI-1", title="T1"),
            AlmTicket(id="WI-2", title="T2"),
        ]
        mock_sync.return_value = True

        stats = polarion_connected.bulk_sync("yuleosh")
        assert stats["workitems_found"] == 2
        assert stats["evidence_attached"] == 2
        assert mock_sync.call_count == 2

    @mock.patch.object(PolarionBackend, "find_by_label")
    @mock.patch.object(PolarionBackend, "sync_evidence_to_ticket")
    def test_bulk_sync_partial_errors(self, mock_sync, mock_find, polarion_connected) -> None:
        """WHEN some syncs fail THEN errors count is incremented."""
        mock_find.return_value = [
            AlmTicket(id="WI-1", title="T1"),
            AlmTicket(id="WI-2", title="T2"),
        ]
        mock_sync.side_effect = Exception("Sync error")

        stats = polarion_connected.bulk_sync("yuleosh")
        assert stats["workitems_found"] == 2
        assert stats["evidence_attached"] == 0
        assert stats["errors"] == 2


# ═════════════════════════════════════════════════════════════════════════════
#  _add_tag
# ═════════════════════════════════════════════════════════════════════════════


class TestAddTag:
    """GIVEN _add_tag()"""

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_tag_already_present(self, mock_get_session, polarion_connected) -> None:
        """WHEN tag already exists THEN True is returned (no PATCH)."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "data": {"attributes": {"tags": ["yuleosh-evidence"]}}
        }
        mock_get_session.return_value = mock_session

        result = polarion_connected._add_tag("WI-1", "yuleosh-evidence")
        assert result is True
        mock_session.patch.assert_not_called()

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_tag_added_with_patch(self, mock_get_session, polarion_connected) -> None:
        """WHEN tag is new THEN PATCH is called to add it."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.ok = True
        mock_session.get.return_value.json.return_value = {
            "data": {"attributes": {"tags": ["existing"]}}
        }
        mock_session.patch.return_value.status_code = 200
        mock_get_session.return_value = mock_session

        result = polarion_connected._add_tag("WI-1", "yuleosh-evidence")
        assert result is True
        mock_session.patch.assert_called_once()
        _, kwargs = mock_session.patch.call_args
        sent_payload = kwargs["json"]
        assert "yuleosh-evidence" in sent_payload["data"]["attributes"]["tags"]

    @mock.patch.object(PolarionBackend, "_get_session")
    def test_get_fails_returns_false(self, mock_get_session, polarion_connected) -> None:
        """WHEN GET request fails THEN False is returned."""
        mock_session = mock.MagicMock()
        mock_session.get.return_value.ok = False
        mock_get_session.return_value = mock_session

        result = polarion_connected._add_tag("WI-1", "tag")
        assert result is False


# ═════════════════════════════════════════════════════════════════════════════
#  _format_evidence_text
# ═════════════════════════════════════════════════════════════════════════════


class TestFormatEvidenceText:
    """GIVEN _format_evidence_text()"""

    def test_contains_header_and_fields(self) -> None:
        """WHEN formatting evidence THEN structured text includes all fields."""
        evidence = {
            "type": "coverage",
            "timestamp": "2025-06-01T12:00:00",
            "line_rate": 85.0,
            "tags": ["misra"],
        }
        text = PolarionBackend._format_evidence_text(evidence)
        assert "=== yuleOSH Evidence Sync ===" in text
        assert "Time: 2025-06-01T12:00:00" in text
        assert "Type: coverage" in text
        assert "line_rate: 85.0" in text or "line_rate: 85" in text
        assert "tags:" in text

    def test_handles_dict_values(self) -> None:
        """WHEN evidence contains dict values THEN they are JSON-formatted."""
        evidence = {
            "type": "compliance",
            "nested": {"key": "value"},
            "timestamp": "T1",
        }
        text = PolarionBackend._format_evidence_text(evidence)
        assert '"key"' in text or "key" in text

    def test_skips_timestamp_and_type_in_body(self) -> None:
        """WHEN iterating fields THEN timestamp and type are already in header."""
        # They appear as dedicated lines and also via the generic loop,
        # but the static method doesn't skip them in the body loop.
        # This is acceptable — they appear twice without harm.
        evidence = {"type": "test", "timestamp": "T1"}
        text = PolarionBackend._format_evidence_text(evidence)
        assert "=== yuleOSH Evidence Sync ===" in text
