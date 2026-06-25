# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""yuleOSH CI — Fault Injection (FI) subcommand.

Usage:
    yuleosh ci fi run <target>          — Execute a fault injection test
    yuleosh ci fi list                  — List available fault injectors
    yuleosh ci fi status <run-id>       — Check FI run status
    yuleosh ci fi report <run-id>       — Generate FI report

This module defines the CLI entry point and parameter structures for
the Fault Injection executor. The actual CAN-layer injection will be
implemented in a later phase; for now this is a scaffold with
simulation/mock support.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ====================================================================
# Enums & Types
# ====================================================================


class FaultDomain(Enum):
    """Fault injection domains."""
    CAN = "can"            # CAN bus fault (bit error, frame loss, bus-off)
    SIGNAL = "signal"      # Signal-level fault (stuck-at, range, rate)
    MEMORY = "memory"      # Memory corruption (bit flip, overflow)
    TIMING = "timing"      # Timing fault (delay, jitter, timeout)
    CPU = "cpu"            # CPU fault (exception, watchdog)
    SENSOR = "sensor"      # Sensor fault (drift, noise, saturation)
    ACTUATOR = "actuator"  # Actuator fault (stuck, deadband, latency)
    POWER = "power"        # Power fault (brownout, spike, ripple)
    COMM = "comm"          # Communication fault (drop, duplicate, reorder)


class FaultSeverity(Enum):
    """Severity of a fault injection."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InjectionMode(Enum):
    """How the fault is injected."""
    ONCE = "once"            # Single injection at trigger
    PERIODIC = "periodic"    # Repeat at interval
    STOCHASTIC = "stochastic"  # Random probability-based
    CONDITIONAL = "conditional"  # Triggered by condition
    MANUAL = "manual"        # User-triggered (interactive)


class FiRunStatus(Enum):
    """Fault injection run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


# ====================================================================
# Data Models
# ====================================================================


@dataclass
class FaultInjectionConfig:
    """Configuration for a single fault injection."""
    name: str
    domain: FaultDomain
    target: str                        # e.g., "CAN0", "signal:VCU_State"
    fault_type: str                    # e.g., "stuck_at", "bit_flip"
    severity: FaultSeverity = FaultSeverity.MEDIUM
    mode: InjectionMode = InjectionMode.ONCE
    duration_ms: int = 1000            # How long the fault lasts
    value: Optional[str] = None        # Fault value/parameter
    probability: float = 0.5           # For stochastic mode (0.0-1.0)
    interval_ms: int = 100             # For periodic mode
    condition: Optional[str] = None    # For conditional mode

    def validate(self) -> list:
        """Validate configuration. Returns list of error messages."""
        errors = []
        if not self.name:
            errors.append("name is required")
        if not self.target:
            errors.append("target is required")
        if not self.fault_type:
            errors.append("fault_type is required")
        if self.duration_ms < 0:
            errors.append("duration_ms must be >= 0")
        if not 0.0 <= self.probability <= 1.0:
            errors.append("probability must be in [0.0, 1.0]")
        return errors


@dataclass
class FiTestScenario:
    """A complete fault injection test scenario with one or more faults."""
    name: str
    description: str = ""
    faults: list[FaultInjectionConfig] = field(default_factory=list)
    setup_script: Optional[str] = None      # Pre-injection setup
    teardown_script: Optional[str] = None   # Post-injection cleanup
    timeout_s: int = 60                     # Overall scenario timeout
    monitor_signals: list[str] = field(default_factory=list)
    expected_behavior: str = ""             # Expected system response
    knowledge_refs: list[str] = field(default_factory=list)  # KB-xxx / LL-xxx / FMEA-xxx refs
    tags: list[str] = field(default_factory=list)

    def add_fault(self, fault: FaultInjectionConfig):
        """Add a fault to the scenario."""
        self.faults.append(fault)

    def validate(self) -> list:
        """Validate the entire scenario. Returns list of error messages."""
        errors = []
        if not self.name:
            errors.append("scenario name is required")
        if not self.faults:
            errors.append("at least one fault injection is required")
        for i, fault in enumerate(self.faults):
            fault_errors = fault.validate()
            for fe in fault_errors:
                errors.append(f"faults[{i}]: {fe}")
        return errors


@dataclass
class FiRunResult:
    """Result of a fault injection run."""
    run_id: str
    scenario_name: str
    status: FiRunStatus
    started_at: str
    completed_at: Optional[str] = None
    faults_executed: int = 0
    faults_succeeded: int = 0
    faults_failed: int = 0
    errors: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    system_responses: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "FiRunResult":
        return FiRunResult(**data)


# ====================================================================
# Fault Injector Registry
# ====================================================================

class _FaultInjectorRegistry:
    """Registry of available fault injectors by domain."""

    def __init__(self):
        self._injectors = {
            FaultDomain.CAN: [
                {"id": "can_bus_off", "name": "CAN Bus-Off", "description": "Force CAN controller into bus-off state"},
                {"id": "can_bit_error", "name": "CAN Bit Error", "description": "Inject single-bit errors on CAN frame"},
                {"id": "can_frame_loss", "name": "CAN Frame Loss", "description": "Drop selected CAN frames"},
                {"id": "can_bus_load", "name": "CAN Bus Load", "description": "Increase bus load beyond threshold"},
            ],
            FaultDomain.SIGNAL: [
                {"id": "signal_stuck_at", "name": "Signal Stuck-At", "description": "Hold signal at a fixed value"},
                {"id": "signal_range", "name": "Signal Out of Range", "description": "Force signal beyond valid range"},
                {"id": "signal_rate", "name": "Signal Rate Limit", "description": "Limit signal rate of change"},
                {"id": "signal_noise", "name": "Signal Noise Injection", "description": "Add Gaussian noise to signal"},
            ],
            FaultDomain.MEMORY: [
                {"id": "mem_bit_flip", "name": "Memory Bit Flip", "description": "Flip a specific memory bit"},
                {"id": "mem_overflow", "name": "Buffer Overflow", "description": "Trigger buffer overflow condition"},
                {"id": "mem_corrupt", "name": "Memory Corruption", "description": "Corrupt a memory region"},
            ],
            FaultDomain.TIMING: [
                {"id": "timing_delay", "name": "Task Delay", "description": "Inject execution delay into a task"},
                {"id": "timing_jitter", "name": "Timing Jitter", "description": "Add random jitter to periodic task"},
                {"id": "timing_timeout", "name": "Timeout Trigger", "description": "Force a timeout condition"},
            ],
            FaultDomain.CPU: [
                {"id": "cpu_exception", "name": "CPU Exception", "description": "Trigger a CPU exception handler"},
                {"id": "cpu_watchdog", "name": "Watchdog Trigger", "description": "Prevent watchdog reset"},
                {"id": "cpu_overload", "name": "CPU Overload", "description": "Max out CPU utilization"},
            ],
            FaultDomain.SENSOR: [
                {"id": "sensor_drift", "name": "Sensor Drift", "description": "Gradual sensor value drift"},
                {"id": "sensor_saturation", "name": "Sensor Saturation", "description": "Force sensor to min/max"},
                {"id": "sensor_dead", "name": "Sensor Dead", "description": "Simulate sensor failure/disconnection"},
            ],
            FaultDomain.ACTUATOR: [
                {"id": "actuator_stuck", "name": "Actuator Stuck", "description": "Prevent actuator movement"},
                {"id": "actuator_latency", "name": "Actuator Latency", "description": "Delayed actuator response"},
                {"id": "actuator_deadband", "name": "Actuator Deadband", "description": "Expanded actuator deadband"},
            ],
            FaultDomain.POWER: [
                {"id": "power_brownout", "name": "Power Brownout", "description": "Voltage below operating range"},
                {"id": "power_spike", "name": "Power Spike", "description": "Voltage transient injection"},
                {"id": "power_ripple", "name": "Power Ripple", "description": "AC ripple on DC supply"},
            ],
            FaultDomain.COMM: [
                {"id": "comm_drop", "name": "Message Drop", "description": "Drop outbound messages"},
                {"id": "comm_duplicate", "name": "Message Duplicate", "description": "Duplicate inbound messages"},
                {"id": "comm_reorder", "name": "Message Reorder", "description": "Reorder message sequence"},
            ],
        }

    def list_injectors(self, domain: FaultDomain = None) -> list:
        """List available injectors, optionally filtered by domain."""
        if domain:
            return self._injectors.get(domain, [])
        result = []
        for inj_list in self._injectors.values():
            result.extend(inj_list)
        return result

    def get_injector(self, injector_id: str) -> Optional[dict]:
        """Get an injector by ID."""
        for inj_list in self._injectors.values():
            for inj in inj_list:
                if inj["id"] == injector_id:
                    return inj
        return None


# Singleton
_injector_registry = _FaultInjectorRegistry()


# ====================================================================
# Fault Injection Runner (Mock Implementation)
# ====================================================================

class FiExecutor:
    """Fault Injection executor.

    Current phase: mock/simulation mode.
    CAN-layer integration (PCAN, Vector, Kvaser) will be added in Phase 2.
    """

    def __init__(self, results_dir: str = None):
        self.results_dir = results_dir or os.path.join(
            os.environ.get("OSH_HOME", "."), ".osh", "fi-runs"
        )
        os.makedirs(self.results_dir, exist_ok=True)
        self._running_runs = {}

    def list_injectors(self, domain: str = None) -> list:
        """List available fault injectors."""
        fd = FaultDomain(domain) if domain else None
        return _injector_registry.list_injectors(fd)

    def run_scenario(self, scenario: FiTestScenario, mock: bool = True) -> FiRunResult:
        """Execute a fault injection test scenario.

        In mock mode, simulates the injection run without real hardware.
        Returns a FiRunResult.
        """
        # Validate first
        errors = scenario.validate()
        if errors:
            result = FiRunResult(
                run_id=str(uuid.uuid4()),
                scenario_name=scenario.name,
                status=FiRunStatus.FAILED,
                started_at=datetime.now().isoformat(),
                completed_at=datetime.now().isoformat(),
                errors=errors,
            )
            self._save_result(result)
            return result

        run_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        result = FiRunResult(
            run_id=run_id,
            scenario_name=scenario.name,
            status=FiRunStatus.RUNNING,
            started_at=now,
        )
        self._running_runs[run_id] = result

        if mock:
            return self._run_mock(scenario, result)
        else:
            return self._run_real(scenario, result)

    def _run_mock(self, scenario: FiTestScenario, result: FiRunResult) -> FiRunResult:
        """Simulate a fault injection run without real hardware."""
        time.sleep(0.1)  # Simulate setup

        for i, fault in enumerate(scenario.faults):
            result.faults_executed += 1
            # Simulate injection (no real CAN interaction)
            obs = (
                f"[mock] Injected {fault.domain.value}.{fault.fault_type} "
                f"on '{fault.target}' (dur={fault.duration_ms}ms, "
                f"mode={fault.mode.value})"
            )
            result.observations.append(obs)
            result.faults_succeeded += 1

        result.status = FiRunStatus.COMPLETED
        result.completed_at = datetime.now().isoformat()
        result.duration_ms = int(len(scenario.faults) * 100)
        result.system_responses.append(
            "[mock] All faults injected successfully (simulation mode)"
        )

        result = self._save_result(result)
        self._running_runs.pop(result.run_id, None)
        return result

    def _run_real(self, scenario: FiTestScenario, result: FiRunResult) -> FiRunResult:
        """Execute a real fault injection run.

        CAN-layer integration TBD in Phase 2.
        """
        result.status = FiRunStatus.FAILED
        result.completed_at = datetime.now().isoformat()
        result.errors.append(
            "Real hardware mode not yet implemented. "
            "Use --mock for simulation, or implement FiExecutor._run_real() "
            "with CAN driver (PCAN/Vector/Kvaser)."
        )
        return self._save_result(result)

    def get_status(self, run_id: str) -> Optional[FiRunResult]:
        """Get the status of a fault injection run."""
        # Check running runs first
        if run_id in self._running_runs:
            return self._running_runs[run_id]
        # Check saved results
        path = os.path.join(self.results_dir, f"{run_id}.json")
        if os.path.exists(path):
            with open(path) as f:
                return FiRunResult.from_dict(json.load(f))
        return None

    def get_report(self, run_id: str, format: str = "text") -> str:
        """Generate a fault injection report."""
        result = self.get_status(run_id)
        if not result:
            return f"Run {run_id} not found."

        if format == "json":
            return json.dumps(result.to_dict(), indent=2, ensure_ascii=False)

        # Text report
        lines = [
            f"═" * 60,
            f"  Fault Injection Run Report",
            f"═" * 60,
            f"  Run ID:         {result.run_id}",
            f"  Scenario:       {result.scenario_name}",
            f"  Status:         {result.status.value}",
            f"  Started:        {result.started_at}",
            f"  Completed:      {result.completed_at or 'N/A'}",
            f"  Duration:       {result.duration_ms}ms",
            f"",
            f"  Faults Executed:   {result.faults_executed}",
            f"  ├─ Succeeded:      {result.faults_succeeded}",
            f"  └─ Failed:         {result.faults_failed}",
        ]

        if result.errors:
            lines.append(f"")
            lines.append(f"  Errors:")
            for err in result.errors:
                lines.append(f"    ❌ {err}")

        if result.observations:
            lines.append(f"")
            lines.append(f"  Observations:")
            for obs in result.observations:
                lines.append(f"    • {obs}")

        if result.system_responses:
            lines.append(f"")
            lines.append(f"  System Responses:")
            for resp in result.system_responses:
                lines.append(f"    → {resp}")

        lines.append(f"═" * 60)
        return "\n".join(lines)

    def list_runs(self, limit: int = 20) -> list[dict]:
        """List recent fault injection runs."""
        runs = []
        if os.path.isdir(self.results_dir):
            files = sorted(
                [f for f in os.listdir(self.results_dir) if f.endswith(".json")],
                reverse=True,
            )[:limit]
            for f in files:
                path = os.path.join(self.results_dir, f)
                try:
                    with open(path) as fh:
                        runs.append(json.load(fh))
                except (json.JSONDecodeError, OSError):
                    pass
        return runs

    def _save_result(self, result: FiRunResult) -> FiRunResult:
        """Save the run result to disk."""
        path = os.path.join(self.results_dir, f"{result.run_id}.json")
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        return result


# ====================================================================
# CLI Commands
# ====================================================================

def cmd_fi_run(args):
    """Execute a fault injection test.

    Usage: yuleosh ci fi run <target> [--mock] [--domain <d>] [--fault <f>]
    """
    executor = FiExecutor()
    mock = getattr(args, "mock", True)
    target = args.target

    # Build scenario
    scenario = FiTestScenario(
        name=f"FI: {target}",
        description=f"Fault injection test on '{target}'",
    )

    fault = FaultInjectionConfig(
        name=args.fault_type or "default",
        domain=FaultDomain(args.domain) if args.domain else FaultDomain.CAN,
        target=target,
        fault_type=args.fault_type or "generic",
        severity=FaultSeverity(args.severity) if args.severity else FaultSeverity.MEDIUM,
        duration_ms=args.duration_ms,
    )
    scenario.add_fault(fault)

    if args.duration_ms:
        scenario.timeout_s = max(args.duration_ms // 1000 + 10, 30)

    print(f"🚀 Running fault injection: {scenario.name}")
    print(f"   Target:     {target}")
    print(f"   Domain:     {fault.domain.value}")
    print(f"   Fault:      {fault.fault_type}")
    print(f"   Duration:   {fault.duration_ms}ms")
    if mock:
        print(f"   Mode:       ⚡ SIMULATION (use --no-mock for real hardware)")
    print()

    result = executor.run_scenario(scenario, mock=mock)

    print(executor.get_report(result.run_id, format="text"))

    if result.status in (FiRunStatus.FAILED, FiRunStatus.ERROR):
        sys.exit(1)


def cmd_fi_list(args):
    """List available fault injectors."""
    executor = FiExecutor()
    domain = args.domain

    injectors = executor.list_injectors(domain)
    if not injectors:
        print("No fault injectors found.")
        return

    if domain:
        print(f"\n📋 Fault Injectors (domain: {domain}):")
    else:
        print(f"\n📋 All Fault Injectors:")

    print(f"{'ID':<30} {'Name':<30} {'Description'}")
    print(f"{'-'*30} {'-'*30} {'-'*50}")

    for inj in injectors:
        desc = inj["description"]
        if len(desc) > 50:
            desc = desc[:47] + "..."
        print(f"{inj['id']:<30} {inj['name']:<30} {desc}")

    print(f"\n{len(injectors)} injector(s) available.")
    print()


def cmd_fi_status(args):
    """Check fault injection run status."""
    executor = FiExecutor()
    run_id = args.run_id

    result = executor.get_status(run_id)
    if not result:
        print(f"❌ Run '{run_id}' not found.")
        sys.exit(1)

    print(f"\n📊 Fault Injection Run Status")
    print(f"{'=' * 50}")
    print(f"  Run ID:      {result.run_id}")
    print(f"  Scenario:    {result.scenario_name}")
    print(f"  Status:      {'✅ ' if result.status == FiRunStatus.COMPLETED else '🔄 '}"
          f"{result.status.value}")
    print(f"  Started:     {result.started_at}")
    if result.completed_at:
        print(f"  Completed:   {result.completed_at}")
    print(f"  Duration:    {result.duration_ms}ms")
    print(f"  Faults:      {result.faults_succeeded}/{result.faults_executed} succeeded")
    if result.errors:
        print(f"  Errors:      {len(result.errors)}")
    print()


def cmd_fi_report(args):
    """Generate a fault injection report."""
    executor = FiExecutor()
    run_id = args.run_id
    fmt = "json" if args.json else "text"

    report = executor.get_report(run_id, format=fmt)
    print(report)


def cmd_fi_list_runs(args):
    """List recent fault injection runs."""
    executor = FiExecutor()
    runs = executor.list_runs(limit=args.limit)

    if not runs:
        print("No fault injection runs found.")
        return

    print(f"\n📋 Recent Fault Injection Runs:")
    print(f"{'Run ID':<40} {'Scenario':<30} {'Status':<15} {'Duration':<12} {'Started'}")
    print(f"{'-'*40} {'-'*30} {'-'*15} {'-'*12} {'-'*24}")

    for r in runs:
        rid = r.get("run_id", "?")[:36]
        name = r.get("scenario_name", "?")[:28]
        status = r.get("status", "?")
        dur = f"{r.get('duration_ms', 0)}ms"
        started = r.get("started_at", "?")[:19]
        print(f"{rid:<40} {name:<30} {status:<15} {dur:<12} {started}")

    print()


# ====================================================================
# Parser Registration
# ====================================================================

def register_ci_fi_subcommand(subparsers):
    """Register the 'ci fi' subcommand with argparse.

    This is designed to be called from yuleosh_cli.py's _build_parser().
    """
    # 'ci fi' is a third-level subcommand under 'ci'
    # It's registered as: yuleosh ci fi <action> [args]
    p_fi = subparsers.add_parser("fi", help="Fault Injection (FI) executor")

    fi_sub = p_fi.add_subparsers(dest="fi_sub", help="FI action")
    fi_sub.required = True

    # fi run
    p_run = fi_sub.add_parser("run", help="Execute a fault injection test")
    p_run.add_argument("target", help="Injection target (e.g., CAN0, signal:VCU_State)")
    p_run.add_argument("--mock", action="store_true", default=True,
                       help="Run in simulation mode (default: true)")
    p_run.add_argument("--no-mock", action="store_false", dest="mock",
                       help="Run with real hardware (TBD)")
    p_run.add_argument("--domain", default=None,
                       choices=[d.value for d in FaultDomain],
                       help="Fault domain (default: can)")
    p_run.add_argument("--fault-type", "--fault", dest="fault_type",
                       default="generic", help="Fault type to inject")
    p_run.add_argument("--severity", default=None,
                       choices=[s.value for s in FaultSeverity],
                       help="Fault severity")
    p_run.add_argument("--duration-ms", type=int, default=1000,
                       help="Fault duration in milliseconds")

    # fi list
    p_list = fi_sub.add_parser("list", help="List available fault injectors")
    p_list.add_argument("--domain", default=None,
                        choices=[d.value for d in FaultDomain],
                        help="Filter by domain")

    # fi status
    p_status = fi_sub.add_parser("status", help="Check FI run status")
    p_status.add_argument("run_id", help="FI run UUID")

    # fi report
    p_report = fi_sub.add_parser("report", help="Generate FI report")
    p_report.add_argument("run_id", help="FI run UUID")
    p_report.add_argument("--json", action="store_true",
                          help="Output as JSON")

    # fi list-runs
    p_lr = fi_sub.add_parser("list-runs", help="List recent FI runs")
    p_lr.add_argument("--limit", type=int, default=20,
                      help="Max runs to show")


# ====================================================================
# Action dispatcher (called from yuleosh_cli.py main loop)
# ====================================================================

def handle_fi_command(args):
    """Dispatch 'ci fi <action>' commands.

    Called from yuleosh_cli.py when args.command == "ci" and args.ci_sub == "fi".
    """
    dispatch = {
        "run": cmd_fi_run,
        "list": cmd_fi_list,
        "status": cmd_fi_status,
        "report": cmd_fi_report,
        "list-runs": cmd_fi_list_runs,
    }

    handler = dispatch.get(args.fi_sub)
    if handler:
        handler(args)
    else:
        print(f"Unknown FI sub-command: {args.fi_sub}")
        sys.exit(1)
