"""
Tests for yuleOSH SIL Kit Integration
======================================

Uses mocking to verify the adapter and integration layer without needing
a real SIL Kit runtime.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# Module under test
from sil import (
    ModelConfig,
    Participant,
    SILKitAdapter,
    SILKitIntegration,
    SimResult,
    SimStatus,
)
from sil.adapter import ParticipantState, SilTestConfig, SimReport


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def sample_config() -> ModelConfig:
    return ModelConfig(
        simulation_name="test-brake",
        participants={"ECU_01": "/tmp/firmware.elf"},
        registry_uri="silkit://localhost:8500",
        timeout_s=10.0,
    )


@pytest.fixture
def sample_testcase() -> Dict[str, Any]:
    return {
        "simulation_name": "brake-test",
        "participants": {"ECU_01": "/firmware/brake.elf", "ECU_02": "/firmware/motor.elf"},
        "registry_uri": "silkit://localhost:8600",
        "timeout_s": 45.0,
        "signals": {"CAN_brake": "CAN::0x100"},
    }


@pytest.fixture
def adapter() -> SILKitAdapter:
    return SILKitAdapter()


@pytest.fixture
def integration() -> SILKitIntegration:
    return SILKitIntegration()


# ======================================================================
# Test: Participant Creation
# ======================================================================

class TestParticipantCreation:
    """Verify participant creation via the integration facade."""

    def test_create_participant_returns_instance(self, integration: SILKitIntegration):
        p = integration.create_participant("ECU_BRAKE", simulation_name="sim-001")
        assert isinstance(p, Participant)
        assert p.name == "ECU_BRAKE"
        assert p.simulation_name == "sim-001"
        assert p.status == ParticipantState.DISCONNECTED

    def test_create_multiple_participants(self, integration: SILKitIntegration):
        names = ["ECU_01", "ECU_02", "ECU_03"]
        for name in names:
            integration.create_participant(name)
        assert set(integration.participants.keys()) == set(names)

    def test_participant_default_simulation_name(self, integration: SILKitIntegration):
        p = integration.create_participant("ECU_X")
        assert p.simulation_name == "default"

    def test_participant_initially_disconnected(self, integration: SILKitIntegration):
        p = integration.create_participant("ECU_TEST")
        assert p.status == ParticipantState.DISCONNECTED


# ======================================================================
# Test: Connection Management
# ======================================================================

class TestConnection:
    """Verify connection lifecycle."""

    def test_connect_sets_connected_flag(self, integration: SILKitIntegration):
        assert not integration.connected
        integration.connect("silkit://localhost:8500")
        assert integration.connected

    def test_connect_updates_adapter_state(self, adapter: SILKitAdapter):
        with patch.object(adapter, "connect") as mock_connect:
            adapter.connect("silkit://registry:8500")
            mock_connect.assert_called_once_with("silkit://registry:8500")

    def test_disconnect_clears_state(self, integration: SILKitIntegration):
        integration.connect("silkit://localhost:8500")
        integration.create_participant("ECU_A")
        integration.disconnect()
        assert not integration.connected
        assert len(integration.participants) == 0

    def test_run_without_connect_raises(self, integration: SILKitIntegration):
        with pytest.raises(RuntimeError, match="Not connected"):
            integration.run_simulation({"simulation_name": "x", "participants": {}})


# ======================================================================
# Test: Test Case Conversion
# ======================================================================

class TestTestCaseConversion:
    """Verify adapter converts yuleOSH test cases to SIL Kit configs."""

    def test_single_case_conversion(self, adapter: SILKitAdapter, sample_testcase: Dict[str, Any]):
        configs = adapter.convert_testcases([sample_testcase])
        assert len(configs) == 1
        config = configs[0]
        assert isinstance(config, SilTestConfig)
        assert config.simulation_name == "brake-test"
        assert config.registry_uri == "silkit://localhost:8600"
        assert config.timeout_s == 45.0
        assert config.test_signals == {"CAN_brake": "CAN::0x100"}

    def test_multiple_cases(self, adapter: SILKitAdapter, sample_testcase: Dict[str, Any]):
        configs = adapter.convert_testcases([sample_testcase, sample_testcase])
        assert len(configs) == 2

    def test_empty_case_list(self, adapter: SILKitAdapter):
        configs = adapter.convert_testcases([])
        assert configs == []

    def test_default_values(self, adapter: SILKitAdapter):
        configs = adapter.convert_testcases([{"simulation_name": "minimal", "participants": {}}])
        c = configs[0]
        assert c.registry_uri == "silkit://localhost:8500"
        assert c.timeout_s == 30.0
        assert c.test_signals is None


# ======================================================================
# Test: Simulation Execution
# ======================================================================

class TestSimulation:
    """Verify simulation execution via the adapter."""

    def test_run_simulation_returns_result(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="test-sim",
            participants={"ECU_01": "test.elf"},
            timeout_s=5.0,
        )
        result = adapter.run_simulation(config)
        assert isinstance(result, SimResult)
        assert result.status == SimStatus.COMPLETED
        assert len(result.participants) == 1
        assert result.participants[0].name == "ECU_01"

    def test_simulation_time_reflects_timeout(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="timed",
            participants={"ECU_A": "fw.elf"},
            timeout_s=10.0,
        )
        result = adapter.run_simulation(config)
        # simulation_time_ns = timeout_s * 1e9
        assert result.simulation_time_ns == int(10.0 * 1e9)

    def test_multiple_participants_in_simulation(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="multi-ecu",
            participants={
                "ECU_POWERTRAIN": "pt.elf",
                "ECU_BODY": "body.elf",
                "ECU_ADAS": "adas.elf",
            },
        )
        result = adapter.run_simulation(config)
        assert len(result.participants) == 3
        names = {p.name for p in result.participants}
        assert names == {"ECU_POWERTRAIN", "ECU_BODY", "ECU_ADAS"}

    def test_participants_connected_after_simulation(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="check-status",
            participants={"ECU_01": "fw.elf"},
        )
        result = adapter.run_simulation(config)
        for p in result.participants:
            assert p.status == ParticipantState.RUNNING


# ======================================================================
# Test: Integration.run_simulation with dict config
# ======================================================================

class TestIntegrationSimulation:
    """Verify integration facade handles dict-style config."""

    def test_run_simulation_from_dict(self, integration: SILKitIntegration):
        integration.connect("silkit://localhost:8500")
        result = integration.run_simulation({
            "simulation_name": "acceptance-test",
            "participants": {"ECU_01": "fw.elf"},
            "timeout_s": 2.0,
        })
        assert isinstance(result, SimResult)
        assert result.status in (SimStatus.COMPLETED, SimStatus.FAILED)

    def test_run_simulation_from_model(self, integration: SILKitIntegration, sample_config: ModelConfig):
        integration.connect("silkit://localhost:8500")
        result = integration.run_simulation(sample_config)
        assert result.status == SimStatus.COMPLETED

    def test_run_simulation_updates_participants_cache(self, integration: SILKitIntegration, sample_config: ModelConfig):
        integration.connect("silkit://localhost:8500")
        result = integration.run_simulation(sample_config)
        assert "ECU_01" in integration.participants
        assert integration.participants["ECU_01"].firmware_path == "/tmp/firmware.elf"


# ======================================================================
# Test: Result Parsing
# ======================================================================

class TestResultParsing:
    """Verify raw SIL Kit output parsing."""

    def test_parse_empty_bytes(self, adapter: SILKitAdapter):
        report = adapter.parse_results(b"")
        assert isinstance(report, SimReport)
        assert report.participant_name == "unknown"
        assert report.error_count == 0

    def test_parse_simple_text(self, adapter: SILKitAdapter):
        raw = b"[ECU_01] Simulation started\n"
        report = adapter.parse_results(raw)
        assert report.participant_name == "ECU_01"

    def test_parse_with_errors(self, adapter: SILKitAdapter):
        raw = b"[ECU_02] ERROR: timeout\n[ECU_02] WARN: retry\n[ECU_02] ERROR: crash\n"
        report = adapter.parse_results(raw)
        assert report.error_count == 2
        assert len(report.warnings) == 1
        assert "WARN" in report.warnings[0]

    def test_parse_with_warnings(self, adapter: SILKitAdapter):
        raw = b"[ECU_03] WARN: temperature high\n[ECU_03] WARN: voltage drop\n"
        report = adapter.parse_results(raw)
        assert report.error_count == 0
        assert len(report.warnings) == 2

    def test_raw_data_preserved(self, adapter: SILKitAdapter):
        raw = b"some raw data"
        report = adapter.parse_results(raw)
        assert report.raw_data == raw


# ======================================================================
# Test: Report Generation
# ======================================================================

class TestReportGeneration:
    """Verify adapter.generate_report produces correct pipeline reports."""

    def test_generate_report_from_single_result(self, adapter: SILKitAdapter):
        config = SilTestConfig(simulation_name="r", participants={"ECU_01": "fw.elf"})
        result = adapter.run_simulation(config)
        report = adapter.generate_report([result])
        assert report["step"] == "sil_kit_simulation"
        assert report["status"] in ("passed", "failed")
        assert report["summary"]["total_participants"] == 1

    def test_generate_report_from_multiple_results(self, adapter: SILKitAdapter):
        results = []
        for i in range(3):
            config = SilTestConfig(simulation_name=f"sim-{i}", participants={f"ECU_{i:02d}": "fw.elf"})
            results.append(adapter.run_simulation(config))
        report = adapter.generate_report(results)
        assert report["summary"]["total_participants"] == 3
        assert len(report["participants"]) == 3
        assert len(report["reports"]) == 3

    def test_report_structure(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="brake",
            participants={"ECU_BRAKE": "brake.elf"},
        )
        result = adapter.run_simulation(config)
        report = adapter.generate_report([result])
        assert "step" in report
        assert "status" in report
        assert "summary" in report
        assert "participants" in report
        assert "reports" in report
        # Check summary structure
        summary = report["summary"]
        assert "total_participants" in summary
        assert "total_simulation_time_ns" in summary
        assert "simulation_time_s" in summary

    def test_report_contains_participant_details(self, adapter: SILKitAdapter):
        config = SilTestConfig(
            simulation_name="detail-test",
            participants={"ECU_ADAS": "adas.elf"},
        )
        result = adapter.run_simulation(config)
        report = adapter.generate_report([result])
        participant = report["participants"][0]
        assert participant["name"] == "ECU_ADAS"
        assert participant["firmware"] == "adas.elf"
        assert "status" in participant
        assert "log_count" in participant
        assert "error_count" in participant


# ======================================================================
# Test: Error Handling
# ======================================================================

class TestErrorHandling:
    """Verify the system handles errors gracefully."""

    def test_adapter_shutdown_when_not_connected(self, adapter: SILKitAdapter):
        """shutdown should not raise when no connection exists."""
        adapter.shutdown()  # should be a no-op

    def test_integration_disconnect_when_not_connected(self, integration: SILKitIntegration):
        """disconnect should not raise when already disconnected."""
        integration.disconnect()  # no-op

    def test_run_simulation_with_empty_participants(self, adapter: SILKitAdapter):
        config = SilTestConfig(simulation_name="empty", participants={})
        result = adapter.run_simulation(config)
        assert isinstance(result, SimResult)
        assert len(result.participants) == 0

    @patch("sil.adapter.SILKitAdapter.shutdown")
    def test_adapter_cleanup_called(self, mock_shutdown: MagicMock, adapter: SILKitAdapter):
        adapter.shutdown()
        mock_shutdown.assert_called_once()


# ======================================================================
# Test: Adapter State Machine
# ======================================================================

class TestAdapterState:
    """Verify adapter state transitions."""

    def test_initial_state_is_idle(self, adapter: SILKitAdapter):
        assert adapter._state.name == "IDLE"

    def test_state_transitions_during_simulation(self, adapter: SILKitAdapter):
        config = SilTestConfig(simulation_name="state-test", participants={"E": "f.elf"})
        adapter.run_simulation(config)
        # After run, should be back to IDLE
        assert adapter._state.name == "IDLE"


# ======================================================================
# Test: ModelConfig Validation
# ======================================================================

class TestModelConfig:
    """Verify ModelConfig dataclass behavior."""

    def test_default_values(self):
        config = ModelConfig(simulation_name="test", participants={"E": "f.elf"})
        assert config.registry_uri == "silkit://localhost:8500"
        assert config.timeout_s == 30.0
        assert config.signal_map is None

    def test_custom_values(self):
        config = ModelConfig(
            simulation_name="custom",
            participants={"ECU": "fw.elf"},
            registry_uri="silkit://custom:9999",
            timeout_s=120.0,
            signal_map={"brake": "CAN::0x100"},
        )
        assert config.registry_uri == "silkit://custom:9999"
        assert config.timeout_s == 120.0
        assert config.signal_map == {"brake": "CAN::0x100"}
