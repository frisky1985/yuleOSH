# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""AUTOSAR CLI integration — ``yuleosh import arxml`` command.

Provides CLI entry points for importing and inspecting AUTOSAR ARXML files.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from yuleosh.autosar.parser import ARXMLParser
from yuleosh.autosar.models import (
    SWCComponent,
    AutoSarPackage,
)

log = logging.getLogger("autosar.cli")


def register_cli(subparsers) -> None:
    """Register the ``import arxml`` subcommand on the given subparsers group.

    Should be called during CLI setup::

        from yuleosh.autosar.cli import register_cli
        register_cli(subparsers)
    """
    parser = subparsers.add_parser(
        "arxml",
        help="Import and analyze AUTOSAR ARXML files",
        description="Parse AUTOSAR CP ARXML files to extract SWC structure.",
    )
    parser.add_argument(
        "file",
        type=str,
        help="Path to the .arxml file",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json", "tree"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--swc",
        type=str,
        default="",
        help="Filter to a specific SWC by short name",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    parser.set_defaults(func=_handle_arxml_command)


def _handle_arxml_command(args) -> None:
    """Handle the ``yuleosh import arxml`` CLI command."""
    filepath = Path(args.file)
    if not filepath.exists():
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        logging.getLogger("autosar").setLevel(logging.DEBUG)

    parser = ARXMLParser()

    try:
        swcs = parser.parse_swc(str(filepath))
    except Exception as e:
        print(f"Error parsing ARXML: {e}", file=sys.stderr)
        sys.exit(1)

    # Filter by SWC name if specified
    if args.swc:
        filtered = [s for s in swcs if s.short_name == args.swc]
        if not filtered:
            print(f"SWC '{args.swc}' not found in {filepath}", file=sys.stderr)
            sys.exit(1)
        swcs = filtered

    # Format output
    if args.format == "json":
        output = _format_json(swcs)
    elif args.format == "tree":
        output = _format_tree(swcs)
    else:
        output = parser.to_markdown(swcs)

    # Write output
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output, encoding="utf-8")
        print(f"Output written to {out_path}")
    else:
        print(output)


def _format_json(swcs: List[SWCComponent]) -> str:
    """Format SWC data as JSON."""
    data: List[Dict[str, Any]] = []
    for swc in swcs:
        swc_dict = {
            "short_name": swc.short_name,
            "uuid": swc.uuid,
            "component_type": swc.component_type,
            "arxml_file": swc.arxml_file,
            "ports": [
                {
                    "short_name": p.short_name,
                    "kind": p.kind,
                    "direction": p.direction,
                    "interface_ref": p.interface_ref,
                }
                for p in swc.ports
            ],
            "runnables": [
                {
                    "short_name": r.short_name,
                    "symbol": r.symbol,
                    "period_ms": r.period_ms,
                    "timing_event": r.timing_event,
                    "data_read_access": r.data_read_access,
                    "data_write_access": r.data_write_access,
                }
                for r in swc.runnables
            ],
            "port_count": len(swc.ports),
            "runnable_count": len(swc.runnables),
        }
        data.append(swc_dict)
    return json.dumps(data, indent=2, ensure_ascii=False)


def _format_tree(swcs: List[SWCComponent]) -> str:
    """Format SWC data as an ASCII tree."""
    lines: list[str] = []
    lines.append("AUTOSAR SWC Structure")
    lines.append("=" * 40)
    lines.append("")

    for i, swc in enumerate(swcs):
        prefix = "└── " if i == len(swcs) - 1 else "├── "
        lines.append(f"{prefix}📦 {swc.short_name} ({swc.component_type})")

        if swc.ports:
            for j, port in enumerate(swc.ports):
                p_pfx = "    └── " if j == len(swc.ports) - 1 else "    ├── "
                lines.append(
                    f"{p_pfx}🔌 {port.short_name} "
                    f"[{port.direction}] {port.kind}"
                )

        if swc.runnables:
            for j, runnable in enumerate(swc.runnables):
                r_pfx = "    └── " if j == len(swc.runnables) - 1 else "    ├── "
                period = f" ({runnable.period_ms}ms)" if runnable.period_ms else ""
                lines.append(f"{r_pfx}⚡ {runnable.short_name}{period}")

        if i < len(swcs) - 1:
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Spec integration helper
# ---------------------------------------------------------------------------

def import_arxml_to_spec(filepath: str, output_dir: str) -> Dict[str, str]:
    """Import ARXML to project spec files.

    This function is called by the ``yuleosh import`` pipeline step.

    Args:
        filepath: Path to the ARXML file.
        output_dir: Directory to write spec files.

    Returns:
        Dict mapping SWC short names to their spec file paths.
    """
    parser = ARXMLParser()
    swcs = parser.parse_swc(filepath)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, str] = {}
    for swc in swcs:
        spec_content = parser.to_markdown([swc])
        spec_path = out_dir / f"{swc.short_name.lower()}-spec.md"
        spec_path.write_text(spec_content, encoding="utf-8")
        result[swc.short_name] = str(spec_path)
        log.info("Generated spec: %s", spec_path)

    return result
