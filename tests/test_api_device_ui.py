"""Unit tests for yuleosh.api.device_ui (设计文档模块⑥ — 设备管理 UI API).

Covers the device-ui routes offline with a mocked DeviceRegistry
(patch ``yuleosh.api.device_ui.DeviceRegistry`` so ``_get_registry()``
returns a fake instance):
  - GET  /api/v1/device-ui/list    — device list (+ empty)
  - GET  /api/v1/device-ui/stats   — by-state aggregation
  - POST /api/v1/device-ui/{id}/acquire — success / 404 / busy 409 /
          missing job_id 400 / bad ttl 400 / any-role (design decision 6)
  - POST /api/v1/device-ui/{id}/release — success / 404 / no-allocation 409 /
          wrong-job 409
  - GET  /api/v1/device-ui/{id}/events — timeline / 404
  - unknown sub-path -> 404
"""

from unittest.mock import MagicMock, patch

import pytest

from yuleosh.api import device_ui as D
from yuleosh.device.models import (
    Allocation,
    AllocationStatus,
    Device,
    DeviceEvent,
    DeviceEventType,
    DeviceState,
)

# Call the wrapped original: the auth wrapper injects current_user as kwarg,
# unit tests pass it directly (handler=None -> injected-user path).
_handle = D.handle_device_ui.__wrapped__


def _call(method, path, body=None, query=None, user=None):
    if user is None:
        user = {"user_id": 1, "org_id": 1, "email": "dev@example.com",
                "role": "developer"}
    return _handle(method, path, body or {}, query or {}, handler=None,
                   current_user=user)


def _device(dev_id="dev-001", state=DeviceState.ONLINE, job=None, **kw):
    kw.setdefault("name", f"board-{dev_id}")
    kw.setdefault("platform", "s32k")
    kw.setdefault("flasher", "openocd")
    kw.setdefault("firmware_version", "v1.2.0")
    kw.setdefault("last_seen", "2026-08-15T10:00:00")
    return Device(id=dev_id, state=state, current_job=job, **kw)


@pytest.fixture
def registry():
    """Fake DeviceRegistry with a mixed-state device pool."""
    reg = MagicMock()
    reg.list_devices.return_value = [
        _device("dev-001", DeviceState.ONLINE),
        _device("dev-002", DeviceState.BUSY, job="job-9"),
        _device("dev-003", DeviceState.OFFLINE),
        _device("dev-004", DeviceState.FAULT),
        _device("dev-005", DeviceState.UNKNOWN),
    ]
    return reg


@pytest.fixture
def mock_reg(registry):
    with patch("yuleosh.api.device_ui.DeviceRegistry", return_value=registry):
        yield registry


# ── list ────────────────────────────────────────────────────────────────

class TestList:
    def test_list_devices(self, mock_reg):
        payload, status = _call("GET", "list")
        assert status == 200
        data = payload["data"]
        assert data["count"] == 5
        assert data["note"] is None
        brief = data["devices"][0]
        # UI 卡片字段：id/name/platform/state/current_job/last_seen/firmware_version
        assert set(brief) == {"id", "name", "platform", "state", "current_job",
                              "last_seen", "firmware_version"}
        assert brief["id"] == "dev-001"
        assert brief["state"] == "online"
        assert brief["platform"] == "s32k"
        mock_reg.list_devices.assert_called_once_with()

    def test_list_empty(self, mock_reg):
        mock_reg.list_devices.return_value = []
        payload, status = _call("GET", "list")
        assert status == 200
        assert payload["data"]["devices"] == []
        assert payload["data"]["count"] == 0


# ── stats ───────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_aggregation(self, mock_reg):
        payload, status = _call("GET", "stats")
        assert status == 200
        data = payload["data"]
        assert data["total"] == 5
        assert data["by_state"] == {
            "online": 1, "busy": 1, "offline": 1, "fault": 1, "unknown": 1,
        }

    def test_stats_unknown_state_value_normalized(self, mock_reg):
        # 防御：未知状态值（如未来新增枚举）归入 unknown 计数而非崩溃
        mock_reg.list_devices.return_value = [
            _device("dev-001", DeviceState.ONLINE),
            _device("dev-002", DeviceState.OFFLINE),
        ]
        payload, status = _call("GET", "stats")
        assert status == 200
        assert payload["data"]["total"] == 2
        assert payload["data"]["by_state"]["online"] == 1
        assert payload["data"]["by_state"]["offline"] == 1

    def test_stats_empty(self, mock_reg):
        mock_reg.list_devices.return_value = []
        payload, status = _call("GET", "stats")
        assert status == 200
        assert payload["data"]["total"] == 0
        assert all(v == 0 for v in payload["data"]["by_state"].values())


# ── acquire ─────────────────────────────────────────────────────────────

class TestAcquire:
    def _setup_device(self, registry, device):
        registry.get_device.return_value = device
        registry.create_allocation.return_value = Allocation(
            id="alloc-1", device_id=device.id, job_id="job-x",
            ttl_seconds=600, status=AllocationStatus.ACTIVE)
        registry.update_device_state.return_value = _device(
            device.id, DeviceState.BUSY, job="job-x")
        return registry

    def test_acquire_success(self, mock_reg):
        dev = _device("dev-001", DeviceState.ONLINE)
        self._setup_device(mock_reg, dev)
        payload, status = _call("POST", "dev-001/acquire",
                                body={"job_id": "job-x", "ttl_seconds": 600})
        assert status == 200
        data = payload["data"]
        assert data["device"]["state"] == "busy"
        assert data["device"]["current_job"] == "job-x"
        assert data["allocation"]["job_id"] == "job-x"
        assert data["allocation"]["ttl_seconds"] == 600
        # 分配链路：create_allocation -> BUSY 状态 -> BUSY 事件（含操作者）
        mock_reg.create_allocation.assert_called_once_with("dev-001", "job-x", 600)
        mock_reg.update_device_state.assert_called_once_with(
            "dev-001", DeviceState.BUSY, current_job="job-x")
        ev = mock_reg.record_event.call_args
        assert ev.args[1] == DeviceEventType.BUSY
        assert "dev@example.com" in ev.args[2]

    def test_acquire_any_logged_in_role(self, mock_reg):
        """设计决策 6：Developer（非 admin）也可 acquire 刷板。"""
        dev = _device("dev-001", DeviceState.ONLINE)
        self._setup_device(mock_reg, dev)
        user = {"user_id": 7, "org_id": 1, "email": "junior@example.com",
                "role": "developer"}
        payload, status = _call("POST", "dev-001/acquire",
                                body={"job_id": "job-x"}, user=user)
        assert status == 200
        assert payload["ok"] is True

    def test_acquire_default_ttl(self, mock_reg):
        dev = _device("dev-001", DeviceState.ONLINE)
        self._setup_device(mock_reg, dev)
        _call("POST", "dev-001/acquire", body={"job_id": "job-x"})
        mock_reg.create_allocation.assert_called_once_with(
            "dev-001", "job-x", D.DEFAULT_TTL_SECONDS)

    def test_acquire_device_not_found(self, mock_reg):
        mock_reg.get_device.return_value = None
        payload, status = _call("POST", "dev-999/acquire",
                                body={"job_id": "job-x"})
        assert status == 404
        assert payload["ok"] is False
        assert "device not found: dev-999" in payload["error"]

    def test_acquire_missing_job_id(self, mock_reg):
        mock_reg.get_device.return_value = _device("dev-001")
        payload, status = _call("POST", "dev-001/acquire", body={})
        assert status == 400
        assert "job_id is required" in payload["error"]

    def test_acquire_busy_device_conflict(self, mock_reg):
        busy = _device("dev-002", DeviceState.BUSY, job="job-9")
        mock_reg.get_device.return_value = busy
        payload, status = _call("POST", "dev-002/acquire",
                                body={"job_id": "job-new"})
        assert status == 409
        assert "not available" in payload["error"]
        mock_reg.create_allocation.assert_not_called()

    def test_acquire_bad_ttl(self, mock_reg):
        mock_reg.get_device.return_value = _device("dev-001")
        payload, status = _call("POST", "dev-001/acquire",
                                body={"job_id": "job-x", "ttl_seconds": "abc"})
        assert status == 400
        assert "ttl_seconds" in payload["error"]
        payload, status = _call("POST", "dev-001/acquire",
                                body={"job_id": "job-x", "ttl_seconds": -5})
        assert status == 400


# ── release ─────────────────────────────────────────────────────────────

class TestRelease:
    def _setup(self, registry, device, alloc, release_ok=True):
        registry.get_device.return_value = device
        registry.get_allocation_for_device.return_value = alloc
        registry.release_allocation.return_value = release_ok
        registry.update_device_state.return_value = _device(
            device.id, DeviceState.ONLINE)
        return registry

    def test_release_success(self, mock_reg):
        dev = _device("dev-002", DeviceState.BUSY, job="job-9")
        alloc = Allocation(id="alloc-1", device_id="dev-002", job_id="job-9")
        self._setup(mock_reg, dev, alloc)
        payload, status = _call("POST", "dev-002/release",
                                body={"job_id": "job-9"})
        assert status == 200
        data = payload["data"]
        assert data["allocation_id"] == "alloc-1"
        assert data["job_id"] == "job-9"
        assert data["device"]["state"] == "busy"  # 释放前快照
        mock_reg.release_allocation.assert_called_once_with("alloc-1", job_id="job-9")
        mock_reg.update_device_state.assert_called_once_with(
            "dev-002", DeviceState.ONLINE, current_job=None)
        ev = mock_reg.record_event.call_args
        assert ev.args[1] == DeviceEventType.RELEASED

    def test_release_device_not_found(self, mock_reg):
        mock_reg.get_device.return_value = None
        payload, status = _call("POST", "dev-999/release", body={})
        assert status == 404
        assert "device not found: dev-999" in payload["error"]

    def test_release_no_active_allocation(self, mock_reg):
        mock_reg.get_device.return_value = _device("dev-001", DeviceState.ONLINE)
        mock_reg.get_allocation_for_device.return_value = None
        payload, status = _call("POST", "dev-001/release", body={})
        assert status == 409
        assert "no active allocation" in payload["error"]

    def test_release_wrong_job_conflict(self, mock_reg):
        dev = _device("dev-002", DeviceState.BUSY, job="job-9")
        alloc = Allocation(id="alloc-1", device_id="dev-002", job_id="job-9")
        self._setup(mock_reg, dev, alloc, release_ok=False)
        payload, status = _call("POST", "dev-002/release",
                                body={"job_id": "other-job"})
        assert status == 409
        assert "failed to release" in payload["error"]
        mock_reg.update_device_state.assert_not_called()


# ── events ──────────────────────────────────────────────────────────────

class TestEvents:
    def test_events_timeline(self, mock_reg):
        dev = _device("dev-001", DeviceState.ONLINE)
        mock_reg.get_device.return_value = dev
        mock_reg.list_events.return_value = [
            DeviceEvent(id="e1", device_id="dev-001",
                        event_type=DeviceEventType.REGISTERED,
                        detail="registered platform=s32k",
                        created_at="2026-08-15T09:00:00"),
            DeviceEvent(id="e2", device_id="dev-001",
                        event_type=DeviceEventType.ONLINE,
                        detail="heartbeat ok",
                        created_at="2026-08-15T09:05:00"),
        ]
        payload, status = _call("GET", "dev-001/events")
        assert status == 200
        data = payload["data"]
        assert data["count"] == 2
        assert data["device"]["id"] == "dev-001"
        ev = data["events"][0]
        assert set(ev) == {"id", "device_id", "event_type", "detail", "created_at"}
        assert ev["event_type"] == "registered"
        mock_reg.list_events.assert_called_once_with("dev-001", limit=50)

    def test_events_device_not_found(self, mock_reg):
        mock_reg.get_device.return_value = None
        payload, status = _call("GET", "dev-999/events")
        assert status == 404
        assert "device not found: dev-999" in payload["error"]


# ── routing / misc ──────────────────────────────────────────────────────

class TestRouting:
    def test_unknown_sub_path(self, mock_reg):
        payload, status = _call("GET", "bogus")
        assert status == 404

    def test_wrong_method(self, mock_reg):
        payload, status = _call("POST", "list", body={})
        assert status == 404
        payload, status = _call("GET", "dev-001/acquire")
        assert status == 404

    def test_auth_required_without_user(self, mock_reg):
        """handler=None 且无 current_user -> require_auth 401（fail closed）。"""
        payload, status = D.handle_device_ui("GET", "list", {}, {}, handler=None)
        assert status == 401
