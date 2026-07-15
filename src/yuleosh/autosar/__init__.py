# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH AUTOSAR Integration — Phase 1: ARXML Reading

Provides lightweight parsing of AUTOSAR CP ARXML files focused on SWC
(Software Component) descriptors: Port interfaces, Runnables, and
internal behavior.

Modules:
    - models: AUTOSAR data model dataclasses (SWCComponent, PortPrototype,
              RunnableEntity, etc.)
    - parser: ARXML parser using lxml / xml.etree.ElementTree
    - cli:    CLI integration (yuleosh import arxml)
"""

from yuleosh.autosar.models import (
    SWCComponent,
    PortPrototype,
    RunnableEntity,
    SwcInternalBehavior,
    ComSpec,
    AutoSarPackage,
)
from yuleosh.autosar.parser import ARXMLParser, parse_arxml_file, parse_arxml_packages
from yuleosh.autosar.stubgen import StubGenerator, generate_stubs, StubModule, StubFunction

__all__ = [
    "ARXMLParser",
    "parse_arxml_file",
    "parse_arxml_packages",
    "StubGenerator",
    "generate_stubs",
    "StubModule",
    "StubFunction",
    "SWCComponent",
    "PortPrototype",
    "RunnableEntity",
    "SwcInternalBehavior",
    "ComSpec",
    "AutoSarPackage",
]
