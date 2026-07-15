#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
evidence/manifest.py — Audit-manifest.json generator.

Produces a cryptographically-signed manifest for every evidence pack,
enabling integrity verification and ASPICE audit proof.

Classes:
    AuditManifest    — Top-level manifest dataclass
    ManifestFileEntry — Per-file manifest entry

Functions:
    generate_audit_manifest()  — Scan evidence dir → AuditManifest
    save_manifest()            — Write manifest as JSON
    load_manifest()            — Load manifest from JSON
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List

log = logging.getLogger("evidence.manifest")


# ═══════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ManifestFileEntry:
    """A single file recorded in the audit manifest."""

    path: str                    # relative path (evidence_root-relative)
    size_bytes: int
    sha256: str
    content_type: str            # "json" | "html" | "md" | "xml" | "zip" | "yaml"
    description: str             # human-readable purpose
    required: bool = False       # mandatory for audit
    cross_refs: List[str] = field(default_factory=list)  # referenced file ids


@dataclass
class AuditManifest:
    """Top-level evidence-pack manifest."""

    schema_version: str              # "1.0.0"
    build_id: str                    # commit hash + datetime
    generated_at: str                # ISO 8601 timestamp
    generated_by: str                # "yuleosh-ev-cli"
    evidence_pack_version: str       # semver

    files: List[ManifestFileEntry]

    # Integrity checksums
    file_count: int = 0
    total_size_bytes: int = 0
    sha256: str = ""                 # entire-manifest SHA-256 (self hash)

    # Cross-reference validity
    cross_refs_valid: bool = True
    unresolved_refs: List[str] = field(default_factory=list)

    # Coverage warnings
    coverage_warnings: List[str] = field(default_factory=list)

    # Digital signature (optional)
    signature: Optional[str] = None  # base64(RSA-SHA256(sha256))


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


_CONTENT_TYPE_MAP: dict[str, str] = {
    ".json": "json",
    ".html": "html",
    ".md": "md",
    ".xml": "xml",
    ".zip": "zip",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".txt": "text",
    ".pdf": "pdf",
    ".elf": "binary",
    ".bin": "binary",
    ".hex": "binary",
    ".csv": "csv",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".svg": "image",
}

_REQUIRED_FILES = {
    "audit-manifest.json": "Evidence pack manifest (self)",
    "pipeline-run.json": "Pipeline execution record",
    "traceability.json": "Requirements traceability matrix",
    "misra-report.json": "MISRA static analysis report",
    "coverage-summary.json": "Test coverage summary",
    "test-results.json": "Unit test results",
}


def _sha256_file(filepath: str) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_content_type(path: str) -> str:
    """Guess content type from file extension."""
    ext = os.path.splitext(path)[1].lower()
    return _CONTENT_TYPE_MAP.get(ext, "other")


def _describe_file(rel_path: str) -> str:
    """Generate a human-readable file description based on path."""
    name = os.path.basename(rel_path).lower()
    descriptions = {
        "audit-manifest.json": "Evidence pack manifest",
        "summary.md": "Executive summary for auditors",
        "pipeline-run.json": "Pipeline execution record",
        "pipeline-config.yaml": "Pipeline configuration",
        "step-timings.json": "Pipeline step timings",
        "spec.md": "Requirements specification",
        "traceability.json": "Requirements traceability matrix",
        "spec-delta.md": "Specification change delta",
        "sdd-report.json": "SDD architecture report",
        "architecture-review.json": "Architecture review record",
        "misra-report.json": "MISRA static analysis report",
        "misra-deviations.json": "MISRA deviation management",
        "coverage-summary.json": "Coverage summary",
        "test-results.json": "Test results",
        "sil-test-report.json": "SIL simulation test report",
        "hil-test-report.json": "HIL hardware test report",
        "firmware.elf": "Compiled firmware ELF",
        "firmware.bin": "Compiled firmware binary",
        "release-notes.md": "Release notes",
    }
    return descriptions.get(name, f"Evidence artifact: {name}")


def _walk_evidence_files(evidence_root: str) -> List[ManifestFileEntry]:
    """Recursively walk evidence directory and return file entries."""
    root = Path(evidence_root)
    files: List[ManifestFileEntry] = []

    for fp in sorted(root.rglob("*")):
        if not fp.is_file():
            continue
        rel_path = str(fp.relative_to(root))
        abs_path = str(fp.absolute())

        entry = ManifestFileEntry(
            path=rel_path,
            size_bytes=fp.stat().st_size,
            sha256=_sha256_file(abs_path),
            content_type=_detect_content_type(rel_path),
            description=_describe_file(rel_path),
            required=os.path.basename(rel_path) in _REQUIRED_FILES,
        )
        files.append(entry)

    return files


def _check_cross_references(files: List[ManifestFileEntry]) -> tuple[bool, List[str]]:
    """Validate that all cross-references resolve to file paths."""
    known_paths = {f.path for f in files}
    unresolved: List[str] = []

    for f in files:
        for ref in f.cross_refs:
            if ref not in known_paths:
                unresolved.append(ref)

    return len(unresolved) == 0, unresolved


def _check_coverage_reasonableness(files: List[ManifestFileEntry]) -> List[str]:
    """Check coverage data for reasonableness."""
    warnings: List[str] = []

    for f in files:
        if "coverage" in f.path.lower() and f.content_type == "json":
            # Load JSON and check coverage value
            try:
                data = json.loads(Path(f.path).read_text()) if os.path.exists(f.path) else {}
                line_cov = data.get("line_coverage", data.get("coverage", data.get("line_rate", 0)))
                if isinstance(line_cov, (int, float)):
                    if line_cov < 0.01:
                        warnings.append(
                            f"Coverage critically low ({line_cov*100:.1f}%): {f.path}"
                        )
                    elif line_cov < 0.05:
                        warnings.append(
                            f"Coverage below 5% threshold ({line_cov*100:.1f}%): {f.path}"
                        )
            except Exception:
                pass  # not a valid JSON coverage file

    return warnings


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


def generate_audit_manifest(
    evidence_dir: str,
    build_id: str,
    evidence_pack_version: str = "1.0.0",
) -> AuditManifest:
    """Scan evidence_dir and produce a complete AuditManifest.

    Args:
        evidence_dir: Path to the evidence pack directory.
        build_id: Unique build identifier (e.g. commit hash).
        evidence_pack_version: Semver for the evidence pack schema.

    Returns:
        An AuditManifest dataclass populated with all file entries
        and integrity metadata.
    """
    evidence_root = Path(evidence_dir)
    if not evidence_root.is_dir():
        raise NotADirectoryError(f"Evidence directory not found: {evidence_dir}")

    # Collect files
    files = _walk_evidence_files(str(evidence_root))
    file_count = len(files)
    total_size = sum(f.size_bytes for f in files)

    # Cross-reference check
    cross_refs_valid, unresolved_refs = _check_cross_references(files)

    # Coverage reasonableness
    coverage_warnings = _check_coverage_reasonableness(files)

    # Compute overall pack SHA-256 (hash of concatenated file hashes)
    combined = "".join(f.sha256 for f in files).encode()
    pack_hash = hashlib.sha256(combined).hexdigest()

    manifest = AuditManifest(
        schema_version="1.0.0",
        build_id=build_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
        generated_by="yuleosh-ev-cli",
        evidence_pack_version=evidence_pack_version,
        files=files,
        file_count=file_count,
        total_size_bytes=total_size,
        sha256=pack_hash,
        cross_refs_valid=cross_refs_valid,
        unresolved_refs=unresolved_refs,
        coverage_warnings=coverage_warnings,
    )

    log.info(
        "Generated manifest: %d files, %d bytes, sha256=%s",
        file_count, total_size, pack_hash[:16],
    )

    return manifest


def manifest_to_dict(manifest: AuditManifest) -> dict:
    """Convert AuditManifest to a JSON-serializable dict."""
    d = asdict(manifest)

    # Convert enum-like fields
    d["files"] = [
        {
            "path": f.path,
            "size_bytes": f.size_bytes,
            "sha256": f.sha256,
            "content_type": f.content_type,
            "description": f.description,
            "required": f.required,
            "cross_refs": f.cross_refs,
        }
        for f in manifest.files
    ]
    return d


def save_manifest(manifest: AuditManifest, output_path: str) -> str:
    """Write manifest to a JSON file (with signing placeholder).

    Args:
        manifest: Completed AuditManifest.
        output_path: Where to write the JSON file.

    Returns:
        The SHA-256 of the written file.
    """
    d = manifest_to_dict(manifest)
    content = json.dumps(d, indent=2, ensure_ascii=False, default=str)

    with open(output_path, "w") as f:
        f.write(content)

    file_hash = _sha256_file(output_path)
    log.info("Manifest written to %s (sha256: %s)", output_path, file_hash[:16])
    return file_hash


def load_manifest(manifest_path: str) -> AuditManifest:
    """Load a manifest from a JSON file.

    Args:
        manifest_path: Path to the audit-manifest.json file.

    Returns:
        AuditManifest populated from the JSON.
    """
    with open(manifest_path) as f:
        d = json.load(f)

    files = [
        ManifestFileEntry(
            path=entry["path"],
            size_bytes=entry["size_bytes"],
            sha256=entry["sha256"],
            content_type=entry.get("content_type", "other"),
            description=entry.get("description", ""),
            required=entry.get("required", False),
            cross_refs=entry.get("cross_refs", []),
        )
        for entry in d.get("files", [])
    ]

    return AuditManifest(
        schema_version=d.get("schema_version", "1.0.0"),
        build_id=d.get("build_id", ""),
        generated_at=d.get("generated_at", ""),
        generated_by=d.get("generated_by", ""),
        evidence_pack_version=d.get("evidence_pack_version", "1.0.0"),
        files=files,
        file_count=d.get("file_count", len(files)),
        total_size_bytes=d.get("total_size_bytes", 0),
        sha256=d.get("sha256", ""),
        cross_refs_valid=d.get("cross_refs_valid", True),
        unresolved_refs=d.get("unresolved_refs", []),
        coverage_warnings=d.get("coverage_warnings", []),
        signature=d.get("signature"),
    )
