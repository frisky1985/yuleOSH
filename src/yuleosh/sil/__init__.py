"""
yuleOSH SIL Kit Digital Twin Integration
=========================================

Provides software-in-the-loop simulation capabilities via Vector SIL Kit.
Exposes high-level APIs for creating participants, running simulations,
and collecting results within the yuleOSH Pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from .adapter import SILKitAdapter, ParticipantState


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class SimStatus(Enum):
    """Simulation lifecycle status."""
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMED_OUT = auto()
    PARTIAL = auto()  # some participants succeeded, some failed


@dataclass
class Participant:
    """A single SIL Kit participant (virtual ECU)."""

    name: str
    simulation_name: str
    firmware_path: str
    status: ParticipantState = ParticipantState.DISCONNECTED
    logs: List[str] = field(default_factory=list)
    signal_traces: Dict[str, List[Any]] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class SimResult:
    """Aggregated result of one simulation run."""

    status: SimStatus
    simulation_time_ns: int
    participants: List[Participant]
    raw_report: Optional[bytes] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Configuration model for a single simulation run.

    Attributes:
        simulation_name:  Unique name for this simulation session.
        participants:     List of participant configurations (name → firmware path).
        registry_uri:     SIL Kit Registry URI (e.g. "silkit://localhost:8500").
        timeout_s:        Simulation wall-clock timeout in seconds.
        signal_map:       Optional mapping of CAN/LIN signal definitions.
    """

    simulation_name: str
    participants: Dict[str, str]  # { participant_name: firmware_path }
    registry_uri: str = "silkit://localhost:8500"
    timeout_s: float = 30.0
    signal_map: Optional[Dict[str, Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Main integration facade
# ---------------------------------------------------------------------------

class SILKitIntegration:
    """SIL Kit Digital Twin integration for the yuleOSH Pipeline.

    Usage::

        integration = SILKitIntegration()
        integration.connect("silkit://localhost:8500")

        participant = integration.create_participant("ECU_01")
        participant.firmware_path = "build/firmware.elf"

        result = integration.run_simulation({
            "simulation_name": "brake-system-test",
            "participants": {"ECU_01": "build/firmware.elf"},
            "registry_uri": "silkit://localhost:8500",
            "timeout_s": 45.0,
        })

        if result.status == SimStatus.COMPLETED:
            print("Simulation passed")
        else:
            print(f"Simulation failed: {result.status}")
    """

    def __init__(self) -> None:
        from .adapter import SILKitAdapter

        self._adapter: SILKitAdapter = SILKitAdapter()
        self._participants: Dict[str, Participant] = {}
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, registry_uri: str) -> None:
        """Connect to a SIL Kit Registry.

        Args:
            registry_uri:  SIL Kit Registry URI (e.g. ``"silkit://localhost:8500"``).

        Raises:
            ConnectionError: If the registry cannot be reached.
        """
        self._adapter.connect(registry_uri)
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from the SIL Kit Registry and clean up."""
        if self._connected:
            self._adapter.shutdown()
            self._connected = False
            self._participants.clear()

    # ------------------------------------------------------------------
    # Participant management
    # ------------------------------------------------------------------

    def create_participant(self, name: str, *, simulation_name: str = "default") -> Participant:
        """Create and register a SIL Kit participant.

        Args:
            name:             Participant name (must be unique within the simulation).
            simulation_name:  Simulation group this participant belongs to.

        Returns:
            A :class:`Participant` instance (not yet connected to firmware).
        """
        participant = Participant(
            name=name,
            simulation_name=simulation_name,
            firmware_path="",
        )
        self._participants[name] = participant
        return participant

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def run_simulation(self, model_config: ModelConfig | Dict[str, Any]) -> SimResult:
        """Run a SIL Kit simulation for a given model configuration.

        Args:
            model_config:  Either a :class:`ModelConfig` instance or a plain dict.

        Returns:
            An aggregated :class:`SimResult`.
        """
        if isinstance(model_config, dict):
            model_config = ModelConfig(**model_config)

        if not self._connected:
            raise RuntimeError(
                "Not connected to SIL Kit Registry. Call connect() first."
            )

        # Adapter layer handles the actual SIL Kit interaction
        sim_result = self._adapter.run_simulation(model_config)

        # Update local participant cache
        for p in sim_result.participants:
            self._participants[p.name] = p

        return sim_result

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_report(self, results: List[SimResult]) -> dict:
        """Generate a structured Pipeline report from simulation results.

        Args:
            results:  List of :class:`SimResult` from one or more simulation runs.

        Returns:
            A dict conforming to the yuleOSH Pipeline report schema.
        """
        return self._adapter.generate_report(results)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the integration is currently connected to SIL Kit."""
        return self._connected

    @property
    def participants(self) -> Dict[str, Participant]:
        """All registered participants, keyed by name."""
        return dict(self._participants)


__all__ = [
    "SILKitIntegration",
    "SILKitAdapter",
    "Participant",
    "ParticipantState",
    "SimResult",
    "SimStatus",
    "ModelConfig",
]
