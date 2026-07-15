"""Depth tests for alm/__init__.py — ALM adapter factory, stub implementations, and registration.

Covers:
  - _ADAPTER_REGISTRY: initial state and registration mechanics
  - register_adapter(): adding new adapters
  - create_adapter(): factory pattern, success and error cases
  - list_available_adapters(): listing registered adapters
  - JiraAdapter: create_ticket, update_status, find_by_label (stub)
  - PolarionAdapter: create_ticket, update_status, find_by_label (stub)
  - JiraBackend and PolarionBackend re-export: module-level imports
  - Edge cases: unknown adapter, case-insensitive registry
"""

import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.alm import (
    _ADAPTER_REGISTRY,
    register_adapter,
    create_adapter,
    list_available_adapters,
    JiraAdapter,
    PolarionAdapter,
    JiraBackend,
    PolarionBackend,
    AlmBackend,
    AlmTicket,
)


# ── Adapter Registry ───────────────────────────────────────────────────

class TestAdapterRegistry:
    def test_initial_registry_has_adapters(self):
        """GIVEN module import WHEN checking registry THEN has jira and polarion."""
        assert "jira" in _ADAPTER_REGISTRY
        assert "polarion" in _ADAPTER_REGISTRY

    def test_register_adapter(self):
        """GIVEN a new adapter class WHEN registered THEN appears in registry."""
        class CustomAdapter(AlmBackend):
            def create_ticket(self, ticket): return "CUSTOM-001"
            def update_status(self, tid, s): return True
            def find_by_label(self, label): return []

        register_adapter("custom", CustomAdapter)
        assert "custom" in _ADAPTER_REGISTRY
        assert _ADAPTER_REGISTRY["custom"] == CustomAdapter

    def test_register_case_insensitive(self):
        """GIVEN uppercase name WHEN registered THEN stored lowercase."""
        class AnotherAdapter(AlmBackend):
            def create_ticket(self, ticket): return "A-001"
            def update_status(self, tid, s): return True
            def find_by_label(self, label): return []

        register_adapter("AnotherName", AnotherAdapter)
        assert "anothername" in _ADAPTER_REGISTRY

    def test_list_available_adapters(self):
        """GIVEN registered adapters WHEN listing THEN returns names."""
        names = list_available_adapters()
        assert "jira" in names
        assert "polarion" in names
        assert isinstance(names, list)

    def test_create_adapter_jira(self):
        """GIVEN 'jira' kind WHEN creating adapter THEN returns JiraBackend."""
        adapter = create_adapter("jira")
        assert isinstance(adapter, JiraBackend)

    def test_create_adapter_polarion(self):
        """GIVEN 'polarion' kind WHEN creating adapter THEN returns PolarionBackend."""
        adapter = create_adapter("polarion")
        assert isinstance(adapter, PolarionBackend)

    def test_create_adapter_with_kwargs(self):
        """GIVEN kind with kwargs WHEN creating adapter THEN passes kwargs."""
        adapter = create_adapter("jira", url="https://jira.test", api_token="tok")
        assert adapter.url == "https://jira.test"
        assert adapter.api_token == "tok"

    def test_create_adapter_unknown_raises(self):
        """GIVEN unknown kind WHEN creating adapter THEN ValueError."""
        with pytest.raises(ValueError, match="Unknown ALM adapter"):
            create_adapter("nonexistent")

    def test_create_adapter_case_insensitive(self):
        """GIVEN uppercase kind WHEN creating adapter THEN works."""
        adapter = create_adapter("JIRA")
        assert isinstance(adapter, JiraBackend)


# ── JiraAdapter (stub) ────────────────────────────────────────────────

class TestJiraAdapter:
    @pytest.fixture
    def adapter(self):
        return JiraAdapter(url="https://jira.test", api_token="test-token")

    def test_init(self, adapter):
        """GIVEN JiraAdapter with config WHEN initialized THEN stores config."""
        assert adapter.url == "https://jira.test"
        assert adapter.api_token == "test-token"

    def test_init_defaults(self):
        """GIVEN JiraAdapter with no args WHEN initialized THEN empty config."""
        a = JiraAdapter()
        assert a.url == ""
        assert a.api_token == ""

    def test_create_ticket(self, adapter):
        """GIVEN ticket WHEN creating THEN returns stub ID."""
        ticket = AlmTicket(title="Test Issue", description="Test desc")
        tid = adapter.create_ticket(ticket)
        assert tid.startswith("STUB-")
        assert len(tid) > 5

    def test_create_ticket_deterministic_stub(self, adapter):
        """GIVEN same title twice WHEN creating THEN same stub ID."""
        t1 = adapter.create_ticket(AlmTicket(title="Test"))
        t2 = adapter.create_ticket(AlmTicket(title="Test"))
        assert t1 == t2

    def test_update_status(self, adapter):
        """GIVEN ticket_id and status WHEN updating THEN returns True."""
        assert adapter.update_status("STUB-001", "in_progress") is True

    def test_find_by_label(self, adapter):
        """GIVEN label WHEN searching THEN returns empty list."""
        result = adapter.find_by_label("misra")
        assert result == []


# ── PolarionAdapter (stub) ────────────────────────────────────────────

class TestPolarionAdapter:
    @pytest.fixture
    def adapter(self):
        return PolarionAdapter(url="https://polarion.test", api_token="tok")

    def test_init(self, adapter):
        """GIVEN PolarionAdapter with config WHEN initialized THEN stores config."""
        assert adapter.url == "https://polarion.test"
        assert adapter.api_token == "tok"

    def test_init_defaults(self):
        """GIVEN PolarionAdapter with no args WHEN initialized THEN empty config."""
        a = PolarionAdapter()
        assert a.url == ""
        assert a.api_token == ""

    def test_create_ticket(self, adapter):
        """GIVEN ticket WHEN creating THEN returns stub WorkItem ID."""
        ticket = AlmTicket(title="Polarion Task")
        tid = adapter.create_ticket(ticket)
        assert tid.startswith("STUB-WI-")

    def test_update_status(self, adapter):
        """GIVEN ticket_id and status WHEN updating THEN returns True."""
        assert adapter.update_status("WI-001", "resolved") is True

    def test_find_by_label(self, adapter):
        """GIVEN label WHEN searching THEN returns empty list."""
        result = adapter.find_by_label("compliance")
        assert result == []


# ── JiraBackend / PolarionBackend re-export ──────────────────────────

class TestBackendReExports:
    def test_jira_backend_importable(self):
        """GIVEN JiraBackend re-exported WHEN imported THEN is correct class."""
        from yuleosh.alm import JiraBackend as JB
        from yuleosh.alm.jira import JiraBackend as JiraJB
        assert JB is JiraJB

    def test_polarion_backend_importable(self):
        """GIVEN PolarionBackend re-exported WHEN imported THEN is correct class."""
        from yuleosh.alm import PolarionBackend as PB
        from yuleosh.alm.polarion import PolarionBackend as PolarPB
        assert PB is PolarPB

    def test_alm_ticket_dataclass(self):
        """GIVEN AlmTicket WHEN created WITH all fields THEN works."""
        ticket = AlmTicket(
            id="ALM-001",
            title="Test",
            description="Desc",
            status="open",
            priority="high",
            assignee="dev@test.com",
            url="https://alm.test/browse/ALM-001",
            labels=["misra", "compliance"],
        )
        assert ticket.id == "ALM-001"
        assert "misra" in ticket.labels

    def test_alm_ticket_defaults(self):
        """GIVEN AlmTicket with minimal fields WHEN created THEN has defaults."""
        ticket = AlmTicket(title="Minimal")
        assert ticket.status == "open"
        assert ticket.priority == "medium"
        assert ticket.labels == []


# ── Edge cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_adapter_registry_is_dict(self):
        """GIVEN _ADAPTER_REGISTRY WHEN checking type THEN is dict."""
        assert isinstance(_ADAPTER_REGISTRY, dict)

    def test_create_adapter_accesses_base(self):
        """GIVEN create_adapter WHEN called THEN AlmBackend is ABC."""
        assert AlmBackend.__module__.endswith("alm.base")

    def test_backend_abstract_methods(self):
        """GIVEN AlmBackend WHEN checking methods THEN they're abstract."""
        import inspect
        for method_name in ["create_ticket", "update_status", "find_by_label"]:
            method = getattr(AlmBackend, method_name)
            assert getattr(method, "__isabstractmethod__", False), f"{method_name} should be abstract"
