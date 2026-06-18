"""
yuleOSH Evidence Engine.

Submodules:
  generator    — ``EvidenceCollector`` class, traceability & acceptance matrices
  compliance   — Compliance pack ZIP generation, ``generate_evidence()``, CLI
  report       — Report formatting utilities
  analysis     — Traceability parsing and requirement-to-test mapping
"""

from yuleosh.evidence.generator import EvidenceCollector
from yuleosh.evidence.compliance import (
    pack_compliance_zip,
    generate_evidence,
    main,
)
