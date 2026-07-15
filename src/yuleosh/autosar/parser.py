# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""ARXML Parser — lightweight AUTOSAR SWC descriptor reader.

Parses AUTOSAR CP R20-11 ARXML files using Python's xml.etree.ElementTree
(standard library, no lxml dependency). Focuses on SWC-level elements:

  - AR-PACKAGE hierarchy
  - ApplicationSwComponentType / ComplexDeviceDriverSwComponentType
  - Port prototypes (R-PORT-PROTOTYPE, P-PORT-PROTOTYPE)
  - Port interface references
  - SWC Internal Behavior → Runnables
  - Timing Events, DataReceivedEvents

Usage::

    from yuleosh.autosar.parser import ARXMLParser

    parser = ARXMLParser()
    swcs = parser.parse_swc("path/to/file.arxml")
    for swc in swcs:
        print(f"SWC: {swc.short_name}, {len(swc.ports)} ports")
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Any, Dict, List, Optional

from yuleosh.autosar.models import (
    AutoSarPackage,
    ComSpec,
    PortPrototype,
    RunnableEntity,
    SwcInternalBehavior,
    SWCComponent,
)

log = logging.getLogger("autosar.parser")

# ---------------------------------------------------------------------------
# Namespace handling
# ---------------------------------------------------------------------------

# AUTOSAR 4.x uses namespace: http://autosar.org/schema/r4.0
# We handle both explicit namespace and namespace-less ARXML
_AUTOSAR_NS = "http://autosar.org/schema/r4.0"

# Common AUTOSAR tags used in SWC descriptions
_SWC_TYPES = frozenset({
    "APPLICATION-SW-COMPONENT-TYPE",
    "COMPLEX-DEVICE-DRIVER-SW-COMPONENT-TYPE",
    "SENSOR-ACTUATOR-SW-COMPONENT-TYPE",
    "SERVICE-SW-COMPONENT-TYPE",
    "ECU-ABSTRACTION-SW-COMPONENT-TYPE",
})


def _ns(tag: str) -> str:
    """Add the AUTOSAR namespace to a tag name."""
    return f"{{{_AUTOSAR_NS}}}{tag}"


def _local(tag: str) -> str:
    """Strip namespace from a tag name, returning the local part."""
    return tag.split("}")[-1] if "}" in tag else tag


def _findtext(elem: ET.Element, tag: str, default: str = "", ns: str = _AUTOSAR_NS) -> str:
    """Find text in child element, trying both namespaced and plain forms."""
    namespaced = elem.findtext(f"{{{ns}}}{tag}")
    if namespaced is not None:
        return namespaced
    plain = elem.findtext(tag)
    return plain.strip() if plain else default


def _find(elem: ET.Element, tag: str, ns: str = _AUTOSAR_NS) -> Optional[ET.Element]:
    """Find child element, trying both namespaced and plain forms."""
    result = elem.find(f"{{{ns}}}{tag}")
    if result is not None:
        return result
    return elem.find(tag)


def _findall(elem: ET.Element, tag: str, ns: str = _AUTOSAR_NS) -> List[ET.Element]:
    """Find all child elements, trying both namespaced and plain forms."""
    results = elem.findall(f"{{{ns}}}{tag}")
    if results:
        return results
    return elem.findall(tag)


def _findall_recursive(elem: ET.Element, tag: str, ns: str = _AUTOSAR_NS) -> List[ET.Element]:
    """Recursively find all descendant elements with the given tag."""
    results = elem.findall(f".//{{{ns}}}{tag}")
    if results:
        return results
    return elem.findall(f".//{tag}")


def _getattr(elem: ET.Element, attr: str, ns: str = _AUTOSAR_NS, default: str = "") -> str:
    """Get attribute from element, trying both namespaced and plain forms."""
    val = elem.get(f"{{{ns}}}{attr}")
    if val is not None:
        return val
    val = elem.get(attr)
    return val if val is not None else default


# ---------------------------------------------------------------------------
# ARXML Parser
# ---------------------------------------------------------------------------


class ARXMLParser:
    """Lightweight ARXML parser focused on SWC descriptors.

    Supports AUTOSAR CP R20-11 (schema 4.x) ARXML files.
    Uses stdlib ElementTree — no external dependencies required.
    """

    def __init__(self, schema_version: str = "4.2"):
        self.schema_version = schema_version

    def _has_ns(self, root: ET.Element) -> bool:
        """Detect whether the root element uses explicit AUTOSAR namespace."""
        return _AUTOSAR_NS in root.tag or bool(
            root.get(f"{{{_AUTOSAR_NS}}}UUID") or root.get("UUID")
        )

    def _safe_tag(self, tag: str) -> str:
        """Return the correct tag (namespaced or not) for the current document.

        Since we use _findtext/_find patterns that try both forms, this is
        mostly organisational.
        """
        return tag

    # ------------------------------------------------------------------
    # Top-level parse entry points
    # ------------------------------------------------------------------

    def parse_file(self, filepath: str) -> List[SWCComponent]:
        """Parse an ARXML file and return all SWC components.

        This is a convenience wrapper over parse_swc() with logging.
        """
        swcs = self.parse_swc(filepath)
        log.info("Parsed %d SWC components from %s", len(swcs), Path(filepath).name)
        return swcs

    def parse_swc(self, filepath: str) -> List[SWCComponent]:
        """Parse an ARXML file, extracting all SWC components.

        Args:
            filepath: Path to the .arxml file.

        Returns:
            List of SWCComponent instances.
        """
        tree = ET.parse(filepath)
        root = tree.getroot()

        swcs: List[SWCComponent] = []

        # Determine document UUID
        doc_uuid = _getattr(root, "UUID")

        # Try the AR-PACKAGE hierarchy approach first
        packages = root.findall(f"{{{_AUTOSAR_NS}}}AR-PACKAGE")
        if not packages:
            packages = root.findall("AR-PACKAGE")

        for pkg_elem in packages:
            pkg = self._parse_package(pkg_elem, filepath, doc_uuid)
            swcs.extend(pkg.all_components())

        return swcs

    def parse_packages(self, filepath: str) -> List[AutoSarPackage]:
        """Parse an ARXML file and return the AR-PACKAGE hierarchy.

        Args:
            filepath: Path to the .arxml file.

        Returns:
            List of top-level AutoSarPackage instances.
        """
        tree = ET.parse(filepath)
        root = tree.getroot()

        packages: List[AutoSarPackage] = []
        for pkg_elem in _findall(root, "AR-PACKAGE"):
            pkg = self._parse_package(pkg_elem, filepath)
            packages.append(pkg)

        return packages

    # ------------------------------------------------------------------
    # Package parsing
    # ------------------------------------------------------------------

    def _parse_package(
        self,
        elem: ET.Element,
        filepath: str,
        doc_uuid: str = "",
    ) -> AutoSarPackage:
        """Recursively parse an AR-PACKAGE element."""
        short_name = _findtext(elem, "SHORT-NAME", "unnamed_package")
        uuid = _getattr(elem, "UUID")

        pkg = AutoSarPackage(
            short_name=short_name,
            uuid=uuid,
        )

        # Parse sub-packages
        for sub_elem in _findall(elem, "AR-PACKAGE"):
            sub_pkg = self._parse_package(sub_elem, filepath, doc_uuid)
            pkg.sub_packages.append(sub_pkg)

        # Parse SWC elements
        for swc_type in _SWC_TYPES:
            for swc_elem in _findall(elem, swc_type):
                swc = self._parse_swc_component(swc_elem, filepath)
                swc.document_uuid = doc_uuid
                swc.package_refs = [pkg.short_name]
                pkg.sw_components.append(swc)

        # Also check ELEMENTS wrapper (some ARXML variants)
        elements = _find(elem, "ELEMENTS")
        if elements is not None:
            for swc_type in _SWC_TYPES:
                for swc_elem in _findall(elements, swc_type):
                    swc = self._parse_swc_component(swc_elem, filepath)
                    swc.document_uuid = doc_uuid
                    swc.package_refs = [pkg.short_name]
                    pkg.sw_components.append(swc)

        return pkg

    # ------------------------------------------------------------------
    # SWC component parsing
    # ------------------------------------------------------------------

    def _parse_swc_component(self, elem: ET.Element, filepath: str) -> SWCComponent:
        """Parse a single SWC component element."""
        short_name = _findtext(elem, "SHORT-NAME", "unnamed_swc")
        uuid = _getattr(elem, "UUID")
        tag_local = _local(elem.tag)

        swc = SWCComponent(
            short_name=short_name,
            uuid=uuid,
            component_type=tag_local,
            arxml_file=filepath,
        )

        # Parse ports
        for port_elem in _findall(elem, "PORT-PROTOTYPE"):
            port = self._parse_port(port_elem)
            swc.ports.append(port)

        # Also check for R-PORT-PROTOTYPE / P-PORT-PROTOTYPE
        for rp_elem in _findall(elem, "R-PORT-PROTOTYPE"):
            port = self._parse_port(rp_elem, direction="in")
            swc.ports.append(port)

        for pp_elem in _findall(elem, "P-PORT-PROTOTYPE"):
            port = self._parse_port(pp_elem, direction="out")
            swc.ports.append(port)

        # Parse internal behavior
        for ib_elem in _findall(elem, "SWC-INTERNAL-BEHAVIOR"):
            ib = self._parse_internal_behavior(ib_elem)
            swc.internal_behaviors.append(ib)
            swc.runnables.extend(ib.runnables)

        return swc

    # ------------------------------------------------------------------
    # Port parsing
    # ------------------------------------------------------------------

    def _parse_port(self, elem: ET.Element, direction: str = "") -> PortPrototype:
        """Parse a PORT-PROTOTYPE / R-PORT-PROTOTYPE / P-PORT-PROTOTYPE."""
        short_name = _findtext(elem, "SHORT-NAME", "unnamed_port")
        tag_local = _local(elem.tag)

        # Determine direction from tag if not provided
        if not direction:
            if tag_local in ("R-PORT-PROTOTYPE",):
                direction = "in"
            elif tag_local in ("P-PORT-PROTOTYPE",):
                direction = "out"
            else:
                direction = "in"

        # Determine port kind from interface reference
        interface_ref = ""
        kind = "SenderReceiver"

        # Check PROVIDED-INTERFACE / REQUIRED-INTERFACE
        for iface_tag in ("PROVIDED-INTERFACE", "REQUIRED-INTERFACE"):
            iface_elem = _find(elem, iface_tag)
            if iface_elem is not None:
                ref_elem = _find(iface_elem, "PORT-INTERFACE-REF")
                if ref_elem is not None:
                    val = ref_elem.text or _findtext(ref_elem, "TARGET")
                    if val:
                        interface_ref = self._extract_ref_name(val)
                    # Determine kind from reference value
                    if "ClientServer" in (val or ""):
                        kind = "ClientServer"
                    elif "ModeSwitch" in (val or ""):
                        kind = "ModeSwitch"
                    elif "Trigger" in (val or ""):
                        kind = "Trigger"

        # Check COM-SPECS
        com_spec = None
        for cs_elem in _findall(elem, "REQUIRED-COM-SPECS"):
            for spec_elem in _findall(cs_elem, "DATA-ELEMENT-REF"):
                pass
            # Try to parse simple com spec properties
            for spec_elem in cs_elem:
                spec_local = _local(spec_elem.tag)
                if spec_local == "DATA-ELEMENT-REF":
                    continue
                if com_spec is None:
                    com_spec = ComSpec()
                com_spec.properties[_local(spec_elem.tag)] = spec_elem.text

        for cs_elem in _findall(elem, "PROVIDED-COM-SPECS"):
            if com_spec is None:
                com_spec = ComSpec()
            for spec_elem in cs_elem:
                com_spec.properties[_local(spec_elem.tag)] = spec_elem.text

        # Parse init value if present
        if com_spec is not None:
            init_elem = _find(elem, "INIT-VALUE")
            if init_elem is not None:
                com_spec.init_value = init_elem.text

        is_service = "SERVICE-" in elem.tag.upper()

        return PortPrototype(
            short_name=short_name,
            kind=kind,
            direction=direction,
            interface_ref=interface_ref,
            com_spec=com_spec,
            is_service=is_service,
        )

    # ------------------------------------------------------------------
    # Internal behavior parsing
    # ------------------------------------------------------------------

    def _parse_internal_behavior(self, elem: ET.Element) -> SwcInternalBehavior:
        """Parse an SWC-INTERNAL-BEHAVIOR element."""
        short_name = _findtext(elem, "SHORT-NAME", "unnamed_behavior")

        ib = SwcInternalBehavior(short_name=short_name)

        # Parse exclusive areas
        for area_elem in _findall(elem, "EXCLUSIVE-AREA"):
            area_name = _findtext(area_elem, "SHORT-NAME", "")
            if area_name:
                ib.exclusive_areas.append(area_name)

        # Parse mode machine
        mm_elem = _find(elem, "MODE-MACHINE")
        if mm_elem is not None:
            ib.mode_machine_name = _findtext(mm_elem, "SHORT-NAME", "")

        # Parse runnables
        for runnable_elem in _findall(elem, "RUNNABLE-ENTITY"):
            runnable = self._parse_runnable(runnable_elem)
            ib.runnables.append(runnable)

        return ib

    # ------------------------------------------------------------------
    # Runnable parsing
    # ------------------------------------------------------------------

    def _parse_runnable(self, elem: ET.Element) -> RunnableEntity:
        """Parse a RUNNABLE-ENTITY element."""
        short_name = _findtext(elem, "SHORT-NAME", "unnamed_runnable")
        symbol = _findtext(elem, "SYMBOL", short_name)

        runnable = RunnableEntity(
            short_name=short_name,
            symbol=symbol,
        )

        # Check can-be-invoked-concurrently
        cbic = _find(elem, "CAN-BE-INVOKED-CONCURRENTLY")
        if cbic is not None and cbic.text and cbic.text.strip().upper() == "TRUE":
            runnable.can_be_invoked_concurrently = True

        # Minimum start interval
        msi = _find(elem, "MINIMUM-START-INTERVAL")
        if msi is not None and msi.text:
            try:
                runnable.minimum_start_interval_ms = float(msi.text)
            except (ValueError, TypeError):
                pass

        # Parse data read/write access
        data_read = _find(elem, "DATA-READ-ACCESS")
        if data_read is not None:
            for ref_elem in _findall_recursive(data_read, "TARGET"):
                if ref_elem.text:
                    runnable.data_read_access.append(
                        self._extract_ref_name(ref_elem.text)
                    )
            for ref_elem in _findall_recursive(data_read, "PORT-PROTOTYPE-REF"):
                if ref_elem.text:
                    runnable.data_read_access.append(
                        self._extract_ref_name(ref_elem.text)
                    )

        data_write = _find(elem, "DATA-WRITE-ACCESS")
        if data_write is not None:
            for ref_elem in _findall_recursive(data_write, "TARGET"):
                if ref_elem.text:
                    runnable.data_write_access.append(
                        self._extract_ref_name(ref_elem.text)
                    )
            for ref_elem in _findall_recursive(data_write, "PORT-PROTOTYPE-REF"):
                if ref_elem.text:
                    runnable.data_write_access.append(
                        self._extract_ref_name(ref_elem.text)
                    )

        # Server call points
        for scp_elem in _findall(elem, "SERVER-CALL-POINT"):
            scp_name = _findtext(scp_elem, "SHORT-NAME", "")
            if scp_name:
                runnable.server_call_points.append(scp_name)

        # Parse events
        self._parse_runnable_events(elem, runnable)

        return runnable

    def _parse_runnable_events(self, elem: ET.Element, runnable: RunnableEntity) -> None:
        """Parse event references within a runnable entity."""
        for event_elem in _findall(elem, "EVENT"):
            # Timing Event
            te = _find(event_elem, "TIMING-EVENT")
            if te is not None:
                period = _find(te, "PERIOD")
                if period is not None and period.text:
                    try:
                        runnable.period_ms = float(period.text) * 1000.0
                    except (ValueError, TypeError):
                        pass
                    runnable.timing_event = f"TimingEvent_{int(runnable.period_ms)}ms"
                continue

            # Data Received Event
            dre = _find(event_elem, "DATA-RECEIVED-EVENT")
            if dre is not None:
                ref = _findall_recursive(dre, "TARGET")
                for r in ref:
                    if r.text:
                        runnable.data_received_events.append(
                            self._extract_ref_name(r.text)
                        )
                continue

            # Mode Switch Event
            mse = _find(event_elem, "MODE-SWITCH-EVENT")
            if mse is not None:
                ref = _findall_recursive(mse, "TARGET")
                for r in ref:
                    if r.text:
                        runnable.mode_switch_events.append(
                            self._extract_ref_name(r.text)
                        )
                continue

        # Also check event refs at the runnable level (older ARXML variants)
        te = _find(elem, "TIMING-EVENT")
        if te is not None and runnable.timing_event is None:
            period = _find(te, "PERIOD")
            if period is not None and period.text:
                try:
                    runnable.period_ms = float(period.text) * 1000.0
                except (ValueError, TypeError):
                    pass
                runnable.timing_event = f"TimingEvent_{int(runnable.period_ms)}ms"

    # ------------------------------------------------------------------
    # Reference name extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ref_name(ref_value: str) -> str:
        """Extract the short name from an AUTOSAR reference path.

        AUTOSAR references use '/' as separator::
            /pkg/sub_pkg/SwcName/PortName
        """
        if not ref_value:
            return ""
        # Strip trailing slash first
        cleaned = ref_value.rstrip("/")
        # Take the last segment of the path
        name = cleaned.split("/")[-1]
        # Strip any surrounding whitespace
        return name.strip()

    # ------------------------------------------------------------------
    # Output formatting
    # ------------------------------------------------------------------

    def to_markdown(self, swcs: List[SWCComponent]) -> str:
        """Format SWC components as Markdown for spec/documentation."""
        lines: list[str] = []
        lines.append("# AUTOSAR SWC Structure\n")
        lines.append(f"_Parsed from ARXML — {len(swcs)} components_\n")

        for swc in swcs:
            lines.append(f"## SWC: {swc.short_name}")
            lines.append(f"")
            lines.append(f"- **Type**: {swc.component_type}")
            lines.append(f"- **UUID**: {swc.uuid}")
            lines.append(f"- **Ports**: {len(swc.ports)}")
            lines.append(f"- **Runnables**: {len(swc.runnables)}")
            lines.append(f"")

            if swc.ports:
                lines.append("### Ports")
                lines.append("| Name | Direction | Kind | Interface |")
                lines.append("|------|-----------|------|-----------|")
                for port in swc.ports:
                    lines.append(
                        f"| {port.short_name} | {port.direction} | "
                        f"{port.kind} | {port.interface_ref} |"
                    )
                lines.append(f"")

            if swc.runnables:
                lines.append("### Runnables")
                lines.append("| Name | Symbol | Period (ms) | Concurrent | Events |")
                lines.append("|------|--------|-------------|------------|--------|")
                for r in swc.runnables:
                    period = f"{r.period_ms}" if r.period_ms is not None else "-"
                    concurrent = "Yes" if r.can_be_invoked_concurrently else "No"
                    events = []
                    if r.timing_event:
                        events.append(r.timing_event)
                    if r.data_received_events:
                        events.extend(r.data_received_events)
                    events_str = ", ".join(events) if events else "-"
                    lines.append(
                        f"| {r.short_name} | {r.symbol} | {period} | "
                        f"{concurrent} | {events_str} |"
                    )
                lines.append(f"")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_default_parser = ARXMLParser()


def parse_arxml_file(filepath: str) -> List[SWCComponent]:
    """Convenience function: parse an ARXML file and return SWC components.

    Uses a default parser instance.  Equivalent to::

        parser = ARXMLParser()
        return parser.parse_swc(filepath)

    Args:
        filepath: Path to ARXML file.

    Returns:
        List of SWCComponent instances.
    """
    return _default_parser.parse_swc(filepath)


def parse_arxml_packages(filepath: str) -> List[AutoSarPackage]:
    """Convenience function: parse an ARXML file and return package hierarchy.

    Args:
        filepath: Path to ARXML file.

    Returns:
        List of top-level AutoSarPackage instances.
    """
    return _default_parser.parse_packages(filepath)
