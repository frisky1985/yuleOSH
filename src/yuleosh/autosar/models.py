# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""AUTOSAR data model — dataclasses for SWC descriptors.

Supports AUTOSAR CP R20-11 standard elements relevant to Phase 1:
  - AR-PACKAGE → SWC-IMPLEMENTATION
  - SWC-IMPLEMENTATION → BEHAVIOR → PORTS (R-PORT-PROTOTYPE, P-PORT-PROTOTYPE)
  - Each PORT → REQUIRED-COM-SPECS / PROVIDED-COM-SPECS
  - RUNNABLE-ENTITY → TIMING-EVENT / DATA-RECEIVED-EVENT
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ComSpec:
    """Communication specification for a port.

    Attached to R-PORT-PROTOTYPE (RequiredComSpec) or
    P-PORT-PROTOTYPE (ProvidedComSpec).
    """

    data_element: str = ""
    """Name of the data element this spec applies to."""

    init_value: Optional[str] = None
    """Initial value (optional)."""

    queue_length: Optional[int] = None
    """Queue length for queued receiver ports."""

    alive_timeout: Optional[float] = None
    """Alive timeout in seconds."""

    handle_never_received: Optional[bool] = None
    """Whether to handle never-received status."""

    properties: Dict[str, Any] = field(default_factory=dict)
    """Additional properties not explicitly modelled."""


@dataclass
class PortPrototype:
    """AUTOSAR PortPrototype (R-PORT-PROTOTYPE or P-PORT-PROTOTYPE).

    Represents a required or provided port on an SWC.
    """

    short_name: str
    """Port short name."""

    kind: str = "SenderReceiver"
    """Port kind: SenderReceiver, ClientServer, Trigger, ModeSwitch."""

    direction: str = "in"
    """Port direction: 'in' (R-PORT), 'out' (P-PORT), 'inout'."""

    interface_ref: str = ""
    """Reference to the port interface short name."""

    com_spec: Optional[ComSpec] = None
    """Communication specification (optional)."""

    is_service: bool = False
    """Whether this port is a service port."""

    properties: Dict[str, Any] = field(default_factory=dict)
    """Raw properties from ARXML."""


@dataclass
class RunnableEntity:
    """AUTOSAR RunnableEntity.

    Represents a C function that the RTE can schedule.
    """

    short_name: str
    """Runnable short name."""

    symbol: str = ""
    """C function symbol name (defaults to short_name)."""

    period_ms: Optional[float] = None
    """Period in milliseconds (for TimingEvent-triggered runnables)."""

    can_be_invoked_concurrently: bool = False
    """Whether this runnable supports concurrent invocation."""

    minimum_start_interval_ms: Optional[float] = None
    """Minimum start interval (for queued or multi-instance runnables)."""

    data_read_access: List[str] = field(default_factory=list)
    """Names of ports/data elements the runnable reads."""

    data_write_access: List[str] = field(default_factory=list)
    """Names of ports/data elements the runnable writes."""

    server_call_points: List[str] = field(default_factory=list)
    """Server call point names (ClientServer calls)."""

    timing_event: Optional[str] = None
    """Timing event reference (e.g. 'TimingEvent_10ms')."""

    data_received_events: List[str] = field(default_factory=list)
    """Data received event references."""

    mode_switch_events: List[str] = field(default_factory=list)
    """Mode switch event references."""

    properties: Dict[str, Any] = field(default_factory=dict)
    """Additional raw properties."""


@dataclass
class SwcInternalBehavior:
    """SWC InternalBehavior — container for runnables and mode machine.

    Maps to <SWC-INTERNAL-BEHAVIOR> in ARXML.
    """

    short_name: str
    """Behavior short name."""

    runnables: List[RunnableEntity] = field(default_factory=list)
    """Runnable entities within this behavior."""

    exclusive_areas: List[str] = field(default_factory=list)
    """Exclusive areas (for concurrent access protection)."""

    mode_machine_name: Optional[str] = None
    """Mode machine name if a mode machine is defined."""

    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SWCComponent:
    """AUTOSAR ApplicationSwComponentType or ComplexDeviceDriverSwComponentType.

    The top-level descriptor for a software component.
    """

    short_name: str
    """Component short name."""

    uuid: str = ""
    """AUTOSAR UUID (from the XML element attribute)."""

    component_type: str = "ApplicationSwComponentType"
    """Component type: ApplicationSwComponentType,
       ComplexDeviceDriverSwComponentType, etc."""

    ports: List[PortPrototype] = field(default_factory=list)
    """Port prototypes (both R-PORT and P-PORT)."""

    runnables: List[RunnableEntity] = field(default_factory=list)
    """All runnables across all internal behaviors."""

    internal_behaviors: List[SwcInternalBehavior] = field(default_factory=list)
    """Internal behaviors."""

    arxml_file: str = ""
    """Source ARXML file path."""

    document_uuid: str = ""
    """ARXML document UUID."""

    package_refs: List[str] = field(default_factory=list)
    """AR-PACKAGE path the component lives in."""

    properties: Dict[str, Any] = field(default_factory=dict)

    def port_by_name(self, name: str) -> Optional[PortPrototype]:
        """Look up a port by its short name."""
        for p in self.ports:
            if p.short_name == name:
                return p
        return None

    def runnable_by_name(self, name: str) -> Optional[RunnableEntity]:
        """Look up a runnable by its short name."""
        for r in self.runnables:
            if r.short_name == name:
                return r
        return None


@dataclass
class AutoSarPackage:
    """AUTOSAR AR-PACKAGE — top-level package container.

    Represents a package node in the AR-PACKAGE hierarchy.
    """

    short_name: str
    """Package short name."""

    uuid: str = ""
    """AUTOSAR UUID."""

    sub_packages: List[AutoSarPackage] = field(default_factory=list)
    """Sub-packages (AR-PACKAGE children)."""

    sw_components: List[SWCComponent] = field(default_factory=list)
    """SWC components in this package."""

    properties: Dict[str, Any] = field(default_factory=dict)

    def find_component(self, name: str) -> Optional[SWCComponent]:
        """Recursively find an SWC component by short name."""
        for swc in self.sw_components:
            if swc.short_name == name:
                return swc
        for sub in self.sub_packages:
            result = sub.find_component(name)
            if result is not None:
                return result
        return None

    def all_components(self) -> List[SWCComponent]:
        """Get all SWC components in this package tree."""
        result: List[SWCComponent] = []
        result.extend(self.sw_components)
        for sub in self.sub_packages:
            result.extend(sub.all_components())
        return result

    def print_tree(self, indent: int = 0) -> str:
        """Pretty-print the package tree."""
        lines: list[str] = []
        prefix = "  " * indent
        lines.append(f"{prefix}📦 {self.short_name}")
        for swc in self.sw_components:
            lines.append(f"{prefix}  └ 📄 {swc.short_name} ({swc.component_type})")
        for sub in self.sub_packages:
            lines.append(sub.print_tree(indent + 1))
        return "\n".join(lines)
