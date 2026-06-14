"""Smoke tests for sil/ module — adapter and integration (__init__)."""
import pytest
from unittest.mock import MagicMock, patch

from yuleosh.sil import (
    SILKitIntegration, Participant, SimResult, SimStatus,
    ModelConfig, SILKitAdapter, ParticipantState,
)
from yuleosh.sil.adapter import (
    SimulationState, SilTestConfig, SimReport,
)


class TestEnums:
    """Smoke tests for enums in sil/__init__ and sil/adapter."""

    def test_sim_status_values(self):
        assert SimStatus.PENDING.name == "PENDING"
        assert SimStatus.RUNNING.name == "RUNNING"
        assert SimStatus.COMPLETED.name == "COMPLETED"
        assert SimStatus.FAILED.name == "FAILED"

    def test_participant_state_values(self):
        assert ParticipantState.DISCONNECTED.name == "DISCONNECTED"
        assert ParticipantState.CONNECTED.name == "CONNECTED"
        assert ParticipantState.RUNNING.name == "RUNNING"

    def test_simulation_state_values(self):
        assert SimulationState.IDLE.name == "IDLE"
        assert SimulationState.RUNNING.name == "RUNNING"


class TestDataClasses:
    """Smoke tests for dataclass models."""

    def test_participant_create(self):
        p = Participant(name="ECU_01", simulation_name="brake-test", firmware_path="build/fw.elf")
        assert p.name == "ECU_01"
        assert p.status == ParticipantState.DISCONNECTED
        assert p.logs == []
        assert p.errors == []

    def test_participant_custom_status(self):
        p = Participant(name="ECU_01", simulation_name="sim", firmware_path="fw.elf",
                        status=ParticipantState.RUNNING, logs=["started"], errors=["err"])
        assert p.status == ParticipantState.RUNNING
        assert p.logs == ["started"]

    def test_sim_result_create(self):
        p = Participant(name="ECU_01", simulation_name="sim", firmware_path="fw.elf")
        result = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000000, participants=[p])
        assert result.status == SimStatus.COMPLETED
        assert len(result.participants) == 1

    def test_model_config_defaults(self):
        mc = ModelConfig(simulation_name="test", participants={"ECU_01": "fw.elf"})
        assert mc.registry_uri == "silkit://localhost:8500"
        assert mc.timeout_s == 30.0

    def test_model_config_custom(self):
        mc = ModelConfig(simulation_name="custom", participants={"ECU_01": "fw.elf"},
                         registry_uri="silkit://192.168.1.1:8500", timeout_s=60.0)
        assert mc.timeout_s == 60.0

    def test_sil_test_config_defaults(self):
        stc = SilTestConfig(simulation_name="test", participants={"ECU_01": "fw.elf"})
        assert stc.registry_uri == "silkit://localhost:8500"

    def test_sim_report_create_and_defaults(self):
        sr = SimReport(participant_name="ECU_01", state=ParticipantState.STOPPED,
                       simulation_time_ns=5000000, signal_count=3)
        assert sr.participant_name == "ECU_01"
        assert sr.warnings == []
        assert sr.raw_data is None

    def test_sim_report_full(self):
        sr = SimReport(participant_name="ECU_01", state=ParticipantState.CRASHED,
                       error_count=2, warnings=["overheat"])
        assert sr.state == ParticipantState.CRASHED
        assert sr.error_count == 2
        assert "overheat" in sr.warnings


class TestSILKitAdapter:
    """Smoke tests for the adapter layer."""

    def test_instantiate(self):
        adapter = SILKitAdapter()
        assert adapter._state == SimulationState.IDLE

    def test_connect(self):
        adapter = SILKitAdapter()
        adapter.connect("silkit://localhost:8500")
        assert adapter._state == SimulationState.IDLE

    def test_shutdown(self):
        adapter = SILKitAdapter()
        adapter.connect("silkit://localhost:8500")
        adapter.shutdown()
        assert adapter._state == SimulationState.IDLE
        assert adapter._participant_handles == {}

    def test_convert_testcases_empty(self):
        adapter = SILKitAdapter()
        configs = adapter.convert_testcases([])
        assert configs == []

    def test_convert_testcases_one(self):
        adapter = SILKitAdapter()
        configs = adapter.convert_testcases([
            {"simulation_name": "test1", "participants": {"ECU_01": "fw.elf"}, "timeout_s": 45.0}
        ])
        assert len(configs) == 1
        assert configs[0].simulation_name == "test1"
        assert configs[0].timeout_s == 45.0

    def test_convert_testcases_defaults(self):
        adapter = SILKitAdapter()
        configs = adapter.convert_testcases([{"simulation_name": "unnamed"}])
        assert configs[0].simulation_name == "unnamed"
        assert configs[0].timeout_s == 30.0

    def test_convert_with_signals(self):
        adapter = SILKitAdapter()
        configs = adapter.convert_testcases([{
            "simulation_name": "sigtest",
            "participants": {"ECU_01": "fw.elf"},
            "signals": {"CAN1": {"id": "0x100"}},
        }])
        assert configs[0].test_signals == {"CAN1": {"id": "0x100"}}

    def test_parse_results(self):
        adapter = SILKitAdapter()
        report = adapter.parse_results(b"[ECU_01] INFO: starting\nWARN: low voltage\nERROR: timeout\n")
        assert report.participant_name == "ECU_01"
        assert report.error_count > 0

    def test_parse_results_empty(self):
        adapter = SILKitAdapter()
        report = adapter.parse_results(b"")
        assert report.simulation_time_ns == 0

    def test_generate_report_empty(self):
        adapter = SILKitAdapter()
        report = adapter.generate_report([])
        assert report["status"] == "passed"
        assert report["summary"]["total_participants"] == 0

    def test_generate_report_with_results(self):
        adapter = SILKitAdapter()
        p = Participant(name="ECU_01", simulation_name="sim", firmware_path="fw.elf",
                        status=ParticipantState.RUNNING)
        result = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000, participants=[p])
        report = adapter.generate_report([result])
        assert report["status"] == "passed"
        assert report["summary"]["total_participants"] == 1

    def test_generate_report_with_failures(self):
        adapter = SILKitAdapter()
        p = Participant(name="ECU_01", simulation_name="sim", firmware_path="fw.elf",
                        status=ParticipantState.CRASHED, errors=["timeout"])
        result = SimResult(status=SimStatus.FAILED, simulation_time_ns=1000, participants=[p])
        report = adapter.generate_report([result])
        assert report["status"] == "failed"


class TestSILKitIntegration:
    """Smoke tests for the SILKitIntegration facade."""

    def test_instantiate(self):
        integration = SILKitIntegration()
        assert integration.connected is False
        assert integration.participants == {}

    def test_connect_and_disconnect(self):
        integration = SILKitIntegration()
        # Patch adapter methods directly on the integration's adapter
        integration._adapter.connect = MagicMock()
        integration._adapter.shutdown = MagicMock()
        integration.connect("silkit://localhost:8500")
        assert integration.connected is True
        integration.disconnect()
        assert integration.connected is False
        integration._adapter.shutdown.assert_called_once()

    def test_create_participant(self):
        integration = SILKitIntegration()
        with patch.object(SILKitAdapter, "connect"):
            integration.connect("silkit://")
            p = integration.create_participant("ECU_01", simulation_name="sim1")
            assert p.name == "ECU_01"
            assert "ECU_01" in integration.participants

    def test_create_participant_default_simulation(self):
        integration = SILKitIntegration()
        integration._adapter.connect = MagicMock()
        integration.connect("silkit://")
        p = integration.create_participant("ECU_01")
        assert p.simulation_name == "default"

    def test_run_simulation_not_connected(self):
        integration = SILKitIntegration()
        with pytest.raises(RuntimeError, match="Not connected"):
            integration.run_simulation(ModelConfig(simulation_name="test", participants={}))

    def test_run_simulation_with_dict(self):
        integration = SILKitIntegration()
        mock_result = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000, participants=[])
        integration._adapter.connect = MagicMock()
        integration._adapter.run_simulation = MagicMock(return_value=mock_result)
        integration.connect("silkit://localhost:8500")
        result = integration.run_simulation({"simulation_name": "test", "participants": {}})
        assert result.status == SimStatus.COMPLETED

    def test_run_simulation_with_modelconfig(self):
        integration = SILKitIntegration()
        mock_result = SimResult(
            status=SimStatus.COMPLETED, simulation_time_ns=1000,
            participants=[Participant(name="ECU_01", simulation_name="s", firmware_path="f")]
        )
        integration._adapter.connect = MagicMock()
        integration._adapter.run_simulation = MagicMock(return_value=mock_result)
        integration.connect("silkit://")
        mc = ModelConfig(simulation_name="test", participants={"ECU_01": "f.elf"})
        result = integration.run_simulation(mc)
        assert len(result.participants) == 1

    def test_run_simulation_caches_participants(self):
        integration = SILKitIntegration()
        integration._adapter.connect = MagicMock()
        p = Participant(name="ECU_01", simulation_name="s", firmware_path="f")
        mock_result = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000, participants=[p])
        integration._adapter.run_simulation = MagicMock(return_value=mock_result)
        integration.connect("silkit://")
        result = integration.run_simulation(ModelConfig(simulation_name="test", participants={"ECU_01": "f"}))
        assert integration.participants["ECU_01"] is p

    def test_get_report(self):
        integration = SILKitIntegration()
        integration._adapter.connect = MagicMock()
        integration._adapter.shutdown = MagicMock()
        integration._adapter.generate_report = MagicMock(return_value={
            "step": "sil_kit_simulation", "status": "passed"
        })
        result = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000, participants=[])
        report = integration.get_report([result])
        assert report["status"] == "passed"

    def test_properties(self):
        integration = SILKitIntegration()
        assert integration.connected is False
        assert isinstance(integration.participants, dict)


class TestInitExports:
    """Verify sil/__init__ exports."""

    def test_all_exported(self):
        import yuleosh.sil
        assert hasattr(yuleosh.sil, "SILKitIntegration")
        assert hasattr(yuleosh.sil, "SILKitAdapter")
        assert hasattr(yuleosh.sil, "Participant")
        assert hasattr(yuleosh.sil, "ParticipantState")
        assert hasattr(yuleosh.sil, "SimResult")
        assert hasattr(yuleosh.sil, "SimStatus")
        assert hasattr(yuleosh.sil, "ModelConfig")

    def test_adapter_all_exported(self):
        import yuleosh.sil.adapter
        assert hasattr(yuleosh.sil.adapter, "SILKitAdapter")
        assert hasattr(yuleosh.sil.adapter, "ParticipantState")
        assert hasattr(yuleosh.sil.adapter, "SimulationState")
