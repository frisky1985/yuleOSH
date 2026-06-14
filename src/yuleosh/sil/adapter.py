"""
SIL Kit Adapter — yuleOSH Pipeline ↔ SIL Kit Runtime bridge
============================================================

Translates yuleOSH test cases into SIL Kit simulations and converts raw
SIL Kit output into structured Pipeline reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ParticipantState(Enum):
    """State of a SIL Kit participant from the adapter's perspective."""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RUNNING = auto()
    STOPPED = auto()
    CRASHED = auto()
    RESTARTED = auto()


class SimulationState(Enum):
    """Overall simulation state."""
    IDLE = auto()
    BOOTING = auto()
    RUNNING = auto()
    TEARDOWN = auto()
    ERROR = auto()


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class SilTestConfig:
    """A simulation-ready test configuration converted from yuleOSH test cases.

    Attributes:
        simulation_name:  Name for the SIL Kit simulation session.
        participants:     Dict mapping participant name to firmware path.
        registry_uri:     SIL Kit Registry endpoint.
        timeout_s:        Wall-clock timeout in seconds.
        test_signals:     Optional signal definitions to monitor/inject.
    """
    simulation_name: str
    participants: Dict[str, str]
    registry_uri: str = "silkit://localhost:8500"
    timeout_s: float = 30.0
    test_signals: Optional[Dict[str, Dict[str, Any]]] = None


@dataclass
class SimReport:
    """A structured report of one participant's simulation outcome.

    Attributes:
        participant_name:  Name of the participant.
        state:             Final participant state.
        simulation_time_ns:  Simulated time elapsed (nanoseconds).
        signal_count:      Number of monitored signals.
        error_count:       Number of errors encountered.
        warnings:          List of warning messages.
        raw_data:          Optional raw SIL Kit data blob.
    """
    participant_name: str
    state: ParticipantState
    simulation_time_ns: int = 0
    signal_count: int = 0
    error_count: int = 0
    warnings: List[str] = field(default_factory=list)
    raw_data: Optional[bytes] = None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class SILKitAdapter:
    """Bridges the yuleOSH Pipeline with Vector SIL Kit.

    Responsibilities:

    1. Convert yuleOSH test cases → :class:`SilTestConfig`
    2. Launch / attach to SIL Kit simulations
    3. Parse raw SIL Kit output → :class:`SimReport`
    4. Aggregate reports into a Pipeline-ready dict
    """

    def __init__(self) -> None:
        self._state = SimulationState.IDLE
        self._participant_handles: Dict[str, Any] = {}  # name → mock handle
        self._manager: Any = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, registry_uri: str) -> None:
        """Connect to a SIL Kit Registry.

        Args:
            registry_uri:  Registry endpoint (e.g. ``"silkit://localhost:8500"``).

        Raises:
            ConnectionError: On failure to reach the registry.
        """
        logger.info("Connecting to SIL Kit Registry at %s", registry_uri)
        # In production this opens a VAsio connection via SIL Kit C API.
        # In stub/mock mode we simulate success.
        self._state = SimulationState.IDLE
        logger.info("Connected to SIL Kit Registry: %s", registry_uri)

    def shutdown(self) -> None:
        """Gracefully stop all participants and disconnect."""
        logger.info("Shutting down SIL Kit adapter")
        self._stop_participants()
        self._state = SimulationState.IDLE
        self._participant_handles.clear()

    def _stop_participants(self) -> None:
        for name in list(self._participant_handles.keys()):
            logger.debug("Stopping participant '%s'", name)
        self._participant_handles.clear()

    # ------------------------------------------------------------------
    # Test case conversion
    # ------------------------------------------------------------------

    def convert_testcases(self, cases: List[Dict[str, Any]]) -> List[SilTestConfig]:
        """Convert yuleOSH test cases into SIL Kit simulation configurations.

        Each test case in ``cases`` is expected to have at least:
            - ``simulation_name`` (str)
            - ``participants`` (dict[str, str])  — name → firmware path
            - ``timeout_s`` (float, optional)

        Args:
            cases:  List of raw yuleOSH test case dicts.

        Returns:
            List of :class:`SilTestConfig` objects ready for simulation.
        """
        configs: List[SilTestConfig] = []
        for case in cases:
            configs.append(SilTestConfig(
                simulation_name=case.get("simulation_name", "unnamed"),
                participants=case.get("participants", {}),
                registry_uri=case.get("registry_uri", "silkit://localhost:8500"),
                timeout_s=float(case.get("timeout_s", 30)),
                test_signals=case.get("signals"),
            ))
        return configs

    # ------------------------------------------------------------------
    # Simulation orchestration
    # ------------------------------------------------------------------

    def run_simulation(self, config: SilTestConfig) -> "SimResult":
        """Execute one simulation session.

        Args:
            config:  The simulation configuration.

        Returns:
            An aggregated :class:`SimResult` (imported from ``.__init__``).
        """
        from . import SimResult, SimStatus, Participant

        self._state = SimulationState.BOOTING
        logger.info(
            "Starting simulation '%s' with %d participants",
            config.simulation_name,
            len(config.participants),
        )

        # --- Start SIL Kit Manager (mock) ---
        self._start_manager(config.simulation_name)

        # --- Create participants ---
        participants: List[Participant] = []
        for p_name, fw_path in config.participants.items():
            participant = self._create_participant_internal(p_name, config.simulation_name, fw_path)
            participants.append(participant)

        # --- Run (simulated delay) ---
        self._state = SimulationState.RUNNING
        import time
        time.sleep(0.05)  # simulate a brief computation

        # --- Collect results ---
        self._state = SimulationState.TEARDOWN
        for p in participants:
            p.status = ParticipantState.RUNNING

        # Build SimResult
        status = SimStatus.COMPLETED
        sim_time_ns = int(config.timeout_s * 1e9)

        self._state = SimulationState.IDLE
        logger.info("Simulation '%s' completed", config.simulation_name)

        return SimResult(
            status=status,
            simulation_time_ns=sim_time_ns,
            participants=participants,
        )

    def _start_manager(self, simulation_name: str) -> None:
        """Start (or attach to) a SIL Kit Manager."""
        logger.debug("SIL Kit Manager started for '%s'", simulation_name)
        self._manager = {"simulation": simulation_name, "state": "running"}

    def _create_participant_internal(
        self, name: str, simulation_name: str, firmware_path: str
    ) -> "Participant":
        """Internal helper to create a Participant and store its handle."""
        from . import Participant
        participant = Participant(
            name=name,
            simulation_name=simulation_name,
            firmware_path=firmware_path,
            status=ParticipantState.CONNECTED,
        )
        # Save opaque handle for future operations
        self._participant_handles[name] = {
            "participant": participant,
            "lifecycle": None,  # would hold ILifecycleService in production
        }
        return participant

    # ------------------------------------------------------------------
    # Result parsing
    # ------------------------------------------------------------------

    def parse_results(self, raw: bytes) -> SimReport:
        """Parse raw SIL Kit output bytes into a structured :class:`SimReport`.

        Args:
            raw:  Raw bytes from SIL Kit (e.g. protobuf-serialized signal data).

        Returns:
            A parsed :class:`SimReport`.
        """
        # Placeholder: in production this deserializes protobuf / JSON payloads
        # from SIL Kit's SystemMonitor or data loggers.
        participant_name = "unknown"
        error_count = 0
        warnings: List[str] = []

        try:
            text = raw.decode("utf-8", errors="replace")
            # Simple heuristic parsing for demo purposes
            if "ERROR" in text:
                error_count = text.count("ERROR")
            if "WARN" in text:
                warnings = [line for line in text.splitlines() if "WARN" in line]
            # Extract participant name from first line if prefixed
            first_line = text.splitlines()[0] if text.splitlines() else ""
            if "[" in first_line and "]" in first_line:
                participant_name = first_line.split("[")[1].split("]")[0]
        except Exception:
            logger.exception("Failed to parse SIL Kit raw output")

        return SimReport(
            participant_name=participant_name,
            state=ParticipantState.STOPPED,
            simulation_time_ns=len(raw),  # dummy metric
            signal_count=0,
            error_count=error_count,
            warnings=warnings,
            raw_data=raw,
        )

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    def generate_report(self, results: List["SimResult"]) -> dict:
        """Aggregate simulation results into a yuleOSH Pipeline report dict.

        Args:
            results:  One or more :class:`SimResult` from completed simulations.

        Returns:
            A dict with keys: ``status``, ``summary``, ``participants``, ``reports``.
        """
        from . import SimStatus

        total_sim_time_ns = 0
        all_participants: List[dict] = []
        all_reports: List[dict] = []
        ok = True

        for r in results:
            total_sim_time_ns += r.simulation_time_ns
            for p in r.participants:
                entry = {
                    "name": p.name,
                    "simulation": p.simulation_name,
                    "firmware": p.firmware_path,
                    "status": p.status.name,
                    "log_count": len(p.logs),
                    "error_count": len(p.errors),
                }
                all_participants.append(entry)

                report = {
                    "participant": p.name,
                    "state": p.status.name,
                    "warnings": p.logs[:5],
                    "errors": p.errors,
                }
                all_reports.append(report)

                if p.status == ParticipantState.CRASHED or p.errors:
                    ok = False

            if r.status in (SimStatus.FAILED, SimStatus.TIMED_OUT):
                ok = False

        return {
            "step": "sil_kit_simulation",
            "status": "passed" if ok else "failed",
            "summary": {
                "total_participants": len(all_participants),
                "total_simulation_time_ns": total_sim_time_ns,
                "simulation_time_s": round(total_sim_time_ns / 1e9, 3),
            },
            "participants": all_participants,
            "reports": all_reports,
        }
