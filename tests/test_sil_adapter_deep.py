
# @tests src/yuleosh/sil/adapter.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""
SIL Kit Adapter deep tests — P1-3b.

Targets edge cases and private helpers of sil/adapter.py that
the existing test_sil.py does not cover:

- connect() post-state assertion
- shutdown() with populated participant handles
- convert_testcases: signals absent, timeout int→float coercion
- run_simulation: intermediate state transitions (BOOTING, RUNNING)
- parse_results: empty text, byte-length time, multi-bracket name
- generate_report: >5 warnings truncation, TIMED_OUT status, time rounding
- _start_manager / _create_participant_internal direct verification
"""

from __future__ import annotations

import pytest

from yuleosh.sil import SimResult, SimStatus, Participant, ParticipantState
from yuleosh.sil.adapter import (
    SILKitAdapter,
    SimulationState,
    SilTestConfig,
    SimReport,
)


# ---------------------------------------------------------------------------
# connect / shutdown
# ---------------------------------------------------------------------------

class TestAdapterConnectShutdown:
    def test_connect_leaves_state_idle(self):
        adapter = SILKitAdapter()
        adapter.connect("silkit://localhost:8500")
        assert adapter._state == SimulationState.IDLE

    def test_shutdown_clears_participant_handles(self):
        adapter = SILKitAdapter()
        adapter._participant_handles["ecu1"] = {"participant": "mock"}
        adapter._participant_handles["ecu2"] = {"participant": "mock"}
        adapter.shutdown()
        assert len(adapter._participant_handles) == 0
        assert adapter._state == SimulationState.IDLE

    def test_shutdown_when_not_connected(self):
        adapter = SILKitAdapter()
        adapter.shutdown()
        assert adapter._state == SimulationState.IDLE

    def test_shutdown_stops_each_participant(self):
        adapter = SILKitAdapter()
        adapter._participant_handles = {
            "a": {"participant": None},
            "b": {"participant": None},
        }
        adapter.shutdown()
        assert adapter._participant_handles == {}


# ---------------------------------------------------------------------------
# convert_testcases edge cases
# ---------------------------------------------------------------------------

class TestConvertTestcasesEdge:
    def test_signals_absent_sets_none(self):
        adapter = SILKitAdapter()
        cases = [{"simulation_name": "sim1", "participants": {"ecu1": "fw.elf"}}]
        configs = adapter.convert_testcases(cases)
        assert len(configs) == 1
        assert configs[0].test_signals is None

    def test_timeout_int_coerced_to_float(self):
        adapter = SILKitAdapter()
        cases = [{"simulation_name": "sim1", "participants": {}, "timeout_s": 45}]
        configs = adapter.convert_testcases(cases)
        assert isinstance(configs[0].timeout_s, float)
        assert configs[0].timeout_s == 45.0

    def test_empty_cases_returns_empty_list(self):
        adapter = SILKitAdapter()
        configs = adapter.convert_testcases([])
        assert configs == []

    def test_defaults_applied(self):
        adapter = SILKitAdapter()
        cases = [{}]
        configs = adapter.convert_testcases(cases)
        assert configs[0].simulation_name == "unnamed"
        assert configs[0].registry_uri == "silkit://localhost:8500"
        assert configs[0].timeout_s == 30.0


# ---------------------------------------------------------------------------
# run_simulation state transitions
# ---------------------------------------------------------------------------

class TestSimulationStateTransitions:
    def test_state_idle_after_simulation(self):
        adapter = SILKitAdapter()
        config = SilTestConfig(
            simulation_name="test",
            participants={"ecu1": "fw.elf"},
            timeout_s=0.01,
        )
        adapter.run_simulation(config)
        assert adapter._state == SimulationState.IDLE

    def test_manager_set_during_simulation(self):
        adapter = SILKitAdapter()
        config = SilTestConfig(
            simulation_name="mgr_test",
            participants={"ecu1": "fw.elf"},
            timeout_s=0.01,
        )
        adapter.run_simulation(config)
        assert adapter._manager is not None
        assert adapter._manager["simulation"] == "mgr_test"

    def test_participant_handles_populated_after_run(self):
        adapter = SILKitAdapter()
        config = SilTestConfig(
            simulation_name="test",
            participants={"ecu1": "fw1.elf", "ecu2": "fw2.elf"},
            timeout_s=0.01,
        )
        adapter.run_simulation(config)
        assert "ecu1" in adapter._participant_handles
        assert "ecu2" in adapter._participant_handles

    def test_simulation_time_from_timeout(self):
        adapter = SILKitAdapter()
        config = SilTestConfig(
            simulation_name="test",
            participants={"ecu1": "fw.elf"},
            timeout_s=5.0,
        )
        result = adapter.run_simulation(config)
        assert result.simulation_time_ns == int(5.0 * 1e9)


# ---------------------------------------------------------------------------
# parse_results edge cases
# ---------------------------------------------------------------------------

class TestParseResultsEdge:
    def test_empty_bytes(self):
        adapter = SILKitAdapter()
        report = adapter.parse_results(b"")
        assert report.participant_name == "unknown"
        assert report.error_count == 0
        assert report.warnings == []
        assert report.simulation_time_ns == 0

    def test_simulation_time_equals_byte_length(self):
        adapter = SILKitAdapter()
        raw = b"[ecu1] running\n[ecu1] data: 0x1234"
        report = adapter.parse_results(raw)
        assert report.simulation_time_ns == len(raw)

    def test_multiple_errors_counted(self):
        adapter = SILKitAdapter()
        raw = b"[ecu1] ERROR: crash\n[ecu1] ERROR: overflow\n[ecu1] ok"
        report = adapter.parse_results(raw)
        assert report.error_count == 2

    def test_warnings_collected(self):
        adapter = SILKitAdapter()
        raw = b"[ecu1] WARN: low battery\n[ecu1] WARN: high temp\n[ecu1] ok"
        report = adapter.parse_results(raw)
        assert len(report.warnings) == 2

    def test_no_brackets_in_first_line(self):
        adapter = SILKitAdapter()
        raw = b"plain text without brackets\nERROR: something"
        report = adapter.parse_results(raw)
        assert report.participant_name == "unknown"

    def test_multiple_lines_with_brackets(self):
        adapter = SILKitAdapter()
        raw = b"[ecu1] started\n[ecu1] ERROR: crash"
        report = adapter.parse_results(raw)
        assert report.participant_name == "ecu1"

    def test_raw_data_preserved(self):
        adapter = SILKitAdapter()
        raw = b"[ecu1] test data"
        report = adapter.parse_results(raw)
        assert report.raw_data == raw


# ---------------------------------------------------------------------------
# generate_report edge cases
# ---------------------------------------------------------------------------

class TestGenerateReportEdge:
    def test_warnings_truncated_to_five(self):
        adapter = SILKitAdapter()
        p = Participant(
            name="ecu1", simulation_name="sim", firmware_path="fw.elf",
            status=ParticipantState.RUNNING,
        )
        p.logs = [f"warn_{i}" for i in range(10)]
        result = SimResult(
            status=SimStatus.COMPLETED,
            simulation_time_ns=1_000_000_000,
            participants=[p],
        )
        report = adapter.generate_report([result])
        assert len(report["reports"][0]["warnings"]) == 5

    def test_timed_out_status_fails(self):
        adapter = SILKitAdapter()
        result = SimResult(
            status=SimStatus.TIMED_OUT,
            simulation_time_ns=30_000_000_000,
            participants=[],
        )
        report = adapter.generate_report([result])
        assert report["status"] == "failed"

    def test_failed_status_fails(self):
        adapter = SILKitAdapter()
        result = SimResult(
            status=SimStatus.FAILED,
            simulation_time_ns=1_000_000_000,
            participants=[],
        )
        report = adapter.generate_report([result])
        assert report["status"] == "failed"

    def test_simulation_time_s_rounding(self):
        adapter = SILKitAdapter()
        result = SimResult(
            status=SimStatus.COMPLETED,
            simulation_time_ns=1_234_567_890,
            participants=[],
        )
        report = adapter.generate_report([result])
        assert report["summary"]["simulation_time_s"] == 1.235

    def test_crashed_participant_fails_report(self):
        adapter = SILKitAdapter()
        p = Participant(
            name="ecu1", simulation_name="sim", firmware_path="fw.elf",
            status=ParticipantState.CRASHED,
        )
        result = SimResult(
            status=SimStatus.COMPLETED,
            simulation_time_ns=1_000_000_000,
            participants=[p],
        )
        report = adapter.generate_report([result])
        assert report["status"] == "failed"

    def test_errors_in_participant_fails_report(self):
        adapter = SILKitAdapter()
        p = Participant(
            name="ecu1", simulation_name="sim", firmware_path="fw.elf",
            status=ParticipantState.RUNNING,
        )
        p.errors = ["fatal error"]
        result = SimResult(
            status=SimStatus.COMPLETED,
            simulation_time_ns=1_000_000_000,
            participants=[p],
        )
        report = adapter.generate_report([result])
        assert report["status"] == "failed"

    def test_empty_results(self):
        adapter = SILKitAdapter()
        report = adapter.generate_report([])
        assert report["status"] == "passed"
        assert report["summary"]["total_participants"] == 0


# ---------------------------------------------------------------------------
# Private helpers direct tests
# ---------------------------------------------------------------------------

class TestPrivateHelpers:
    def test_start_manager_sets_handle(self):
        adapter = SILKitAdapter()
        adapter._start_manager("my_sim")
        assert adapter._manager is not None
        assert adapter._manager["simulation"] == "my_sim"
        assert adapter._manager["state"] == "running"

    def test_create_participant_internal_stores_handle(self):
        adapter = SILKitAdapter()
        p = adapter._create_participant_internal("ecu1", "sim1", "fw.elf")
        assert p.name == "ecu1"
        assert p.status == ParticipantState.CONNECTED
        assert "ecu1" in adapter._participant_handles

    def test_create_multiple_participants(self):
        adapter = SILKitAdapter()
        adapter._create_participant_internal("ecu1", "sim1", "fw1.elf")
        adapter._create_participant_internal("ecu2", "sim1", "fw2.elf")
        assert len(adapter._participant_handles) == 2
