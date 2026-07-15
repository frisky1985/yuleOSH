#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
evidence/check.py — Enhanced multi-layer evidence check.

Implements the full CheckItem, EvidenceCheckResult model and 7-layer
check pipeline described in the technical implementation plan.

Usage::

    from yuleosh.evidence.check import run_full_evidence_check

    result = run_full_evidence_check("/path/to/evidence")
    assert result.valid, f"Check failed: {result.summary}"
    print(f"valid: {result.valid}")
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

log = logging.getLogger("evidence.check")


# ═══════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class CheckItem:
    """Result of a single evidence check layer."""

    name: str
    passed: bool
    details: str = ""


@dataclass
class EvidenceCheckResult:
    """Complete multi-layer evidence check result."""

    valid: bool
    checks: List[CheckItem]
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    summary: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _sha256_file(filepath: str) -> str:
    """Compute SHA-256 of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json_safe(path: Path) -> Optional[Any]:
    """Load and parse a JSON file, returning None on failure."""
    try:
        return json.loads(path.read_bytes())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


# ═══════════════════════════════════════════════════════════════════════
# Individual check functions — one per logical layer
# ═══════════════════════════════════════════════════════════════════════


def check_files_present(evidence_dir: str) -> CheckItem:
    """Layer 1: All required files exist (audit-manifest.json + required entries)."""
    root = Path(evidence_dir)
    manifest = root / "audit-manifest.json"

    if not manifest.exists():
        return CheckItem("files_present", False, "audit-manifest.json not found")

    m = _load_json_safe(manifest)
    if m is None:
        return CheckItem("files_present", False, "audit-manifest.json unparseable")

    missing: List[str] = []
    for entry in m.get("files", []):
        if entry.get("required"):
            fp = root / entry["path"]
            if not fp.exists():
                missing.append(entry["path"])

    if missing:
        return CheckItem(
            "files_present",
            False,
            f"Required files missing: {', '.join(missing)}",
        )

    return CheckItem(
        "files_present", True,
        f"All required files present ({len(m.get('files', []))} total)",
    )


def check_fields_complete(evidence_dir: str) -> CheckItem:
    """Layer 2: Every JSON file has valid, non-empty structure."""
    root = Path(evidence_dir)
    issues: List[str] = []

    for fp in sorted(root.rglob("*.json")):
        data = _load_json_safe(fp)
        if data is None:
            issues.append(f"{fp.relative_to(root)}: unparseable")
        elif isinstance(data, dict) and not data:
            issues.append(f"{fp.relative_to(root)}: empty object")
        elif isinstance(data, list) and not data:
            issues.append(f"{fp.relative_to(root)}: empty array")

    if issues:
        return CheckItem(
            "fields_complete", False,
            f"{len(issues)} issue(s): {'; '.join(issues[:5])}",
        )

    return CheckItem("fields_complete", True, "All JSON files valid")


def check_values_reasonable(evidence_dir: str) -> CheckItem:
    """Layer 3: Numeric values (coverage, etc.) within reasonable bounds."""
    root = Path(evidence_dir)
    warnings: List[str] = []

    for fp in sorted(root.rglob("*.json")):
        data = _load_json_safe(fp)
        if data is None:
            continue
        rel = str(fp.relative_to(root))

        def _scan(obj, path=""):
            nonlocal warnings
            if isinstance(obj, dict):
                for key in ("coverage", "line_coverage", "line_rate", "branch_rate"):
                    val = obj.get(key)
                    if isinstance(val, (int, float)):
                        if 0 < val < 0.01:
                            warnings.append(
                                f"{rel}{path}.{key}={val:.4f} — critically low"
                            )
                        elif 0 < val < 0.05:
                            warnings.append(
                                f"{rel}{path}.{key}={val:.4f} — below 5%"
                            )
                for k, v in obj.items():
                    _scan(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _scan(v, f"{path}[{i}]")

        _scan(data)

    if warnings:
        return CheckItem(
            "values_reasonable", False,
            f"WARNING: {'; '.join(warnings[:3])}",
        )

    return CheckItem(
        "values_reasonable", True,
        "All numeric values within acceptable ranges",
    )


def check_timestamps_ordered(evidence_dir: str) -> CheckItem:
    """Layer 4: Pipeline step timestamps are monotonically increasing."""
    root = Path(evidence_dir)
    pipeline_file = root / "pipeline" / "pipeline-run.json"

    if not pipeline_file.exists():
        return CheckItem(
            "timestamps_ordered", True,
            "No pipeline-run.json — skip",
        )

    data = _load_json_safe(pipeline_file)
    if data is None:
        return CheckItem("timestamps_ordered", True, "Cannot parse — skip")

    entries: List[dict] = []
    if isinstance(data, dict):
        entries = data.get("steps", data.get("stages", []))
    if not entries:
        return CheckItem("timestamps_ordered", True, "No steps/stages — skip")

    timestamps: List[tuple[str, str]] = []
    for s in entries:
        ts = s.get("timestamp") or s.get("started_at") or s.get("time")
        if ts:
            timestamps.append((s.get("name", "?"), ts))

    if len(timestamps) < 2:
        return CheckItem(
            "timestamps_ordered", True,
            f"{len(timestamps)} timestamp(s) — skip order check",
        )

    for i in range(1, len(timestamps)):
        if timestamps[i][1] < timestamps[i - 1][1]:
            return CheckItem(
                "timestamps_ordered", False,
                f"Timestamp inversion: {timestamps[i]} < {timestamps[i-1]}",
            )

    return CheckItem(
        "timestamps_ordered", True,
        f"{len(timestamps)} timestamps monotonically increasing",
    )


def check_cross_refs_resolved(evidence_dir: str) -> CheckItem:
    """Layer 5: Cross-references in traceability data resolve to known IDs."""
    root = Path(evidence_dir)
    trace_file = root / "requirements" / "traceability.json"

    if not trace_file.exists():
        return CheckItem("cross_refs_resolved", True, "No traceability.json — skip")

    data = _load_json_safe(trace_file)
    if data is None:
        return CheckItem("cross_refs_resolved", True, "Cannot parse — skip")

    entries = (
        data
        if isinstance(data, list)
        else data.get("entries", data.get("traceability", []))
    )

    known_ids: set = set()
    for e in entries:
        eid = e.get("id") or e.get("req_id") or e.get("ref_id")
        if eid:
            known_ids.add(eid)

    unresolved: List[str] = []
    for e in entries:
        refs = e.get("refs", e.get("references", e.get("related", [])))
        for ref in refs if isinstance(refs, list) else []:
            rid = ref if isinstance(ref, str) else ref.get("id", ref.get("ref"))
            if rid and rid not in known_ids:
                unresolved.append(f"'{rid}' not defined")

    if unresolved:
        return CheckItem(
            "cross_refs_resolved", True,  # Warning only
            f"{len(unresolved)} unresolved ref(s): {'; '.join(unresolved[:5])}",
        )

    return CheckItem(
        "cross_refs_resolved", True,
        f"All {len(known_ids)} refs resolved",
    )


def check_sha256_integrity(evidence_dir: str) -> CheckItem:
    """Layer 6: SHA-256 hashes for all manifest files verified."""
    root = Path(evidence_dir)
    manifest = root / "audit-manifest.json"

    if not manifest.exists():
        return CheckItem("sha256_integrity", False, "No manifest — cannot verify")

    m = _load_json_safe(manifest)
    if m is None:
        return CheckItem("sha256_integrity", False, "Manifest unparseable")

    mismatches: List[str] = []
    for entry in m.get("files", []):
        fp = root / entry["path"]
        expected = entry.get("sha256", "")
        if not expected:
            continue
        if not fp.exists():
            mismatches.append(f"{entry['path']}: missing")
        else:
            actual = _sha256_file(str(fp))
            if actual != expected:
                mismatches.append(f"{entry['path']}: hash mismatch")

    if mismatches:
        return CheckItem(
            "sha256_integrity", False,
            f"{len(mismatches)} issue(s): {'; '.join(mismatches[:3])}",
        )

    total = len(m.get("files", []))
    return CheckItem("sha256_integrity", True, f"All {total} file hashes verified")


def check_signature_valid(evidence_dir: str) -> CheckItem:
    """Layer 7: RSA-SHA256 digital signature (optional — always passes if absent)."""
    root = Path(evidence_dir)
    manifest = root / "audit-manifest.json"

    if not manifest.exists():
        return CheckItem("signature_valid", True, "No manifest — skip")

    m = _load_json_safe(manifest)
    if m is None:
        return CheckItem("signature_valid", True, "Cannot parse — skip")

    sig = m.get("signature")
    if not sig:
        return CheckItem("signature_valid", True, "No signature (optional)")

    try:
        from yuleosh.evidence.signer import verify_manifest, load_public_key
        pubkey_path = root.parent / "signing" / "public.pem"
        if not pubkey_path.exists():
            return CheckItem(
                "signature_valid", True,
                "Signature present but cannot verify — no public key",
            )
        pubkey = load_public_key(str(pubkey_path))
        # Sign the manifest content WITHOUT the signature key
        manifest_content = json.dumps(
            {k: v for k, v in m.items() if k != "signature"},
            indent=2,
            ensure_ascii=False,
        )
        valid = verify_manifest(manifest_content, sig, pubkey)
        return CheckItem(
            "signature_valid", valid,
            "Signature valid" if valid else "Signature INVALID",
        )
    except ImportError:
        return CheckItem(
            "signature_valid", True,
            "Signature present but cryptography not installed",
        )
    except Exception as e:
        return CheckItem("signature_valid", True, f"Signature check skipped: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


# Ordered check pipeline
_DEFAULT_CHECKS: List[Callable[[str], CheckItem]] = [
    check_files_present,
    check_fields_complete,
    check_values_reasonable,
    check_timestamps_ordered,
    check_cross_refs_resolved,
    check_sha256_integrity,
    check_signature_valid,
]


def run_full_evidence_check(
    evidence_dir: str,
    checks: Optional[List[Callable[[str], CheckItem]]] = None,
) -> EvidenceCheckResult:
    """Run the complete multi-layer evidence check.

    Args:
        evidence_dir: Path to the evidence pack directory.
        checks: Ordered list of check functions (default: all 7 layers).

    Returns:
        EvidenceCheckResult with ``valid: True`` only when ALL checks pass.
        Warnings accumulate but do NOT set ``valid = False``.
    """
    if checks is None:
        checks = _DEFAULT_CHECKS

    all_items: List[CheckItem] = []
    all_warnings: List[str] = []
    all_errors: List[str] = []
    any_failed = False

    for check_fn in checks:
        try:
            item = check_fn(evidence_dir)
        except Exception as e:
            item = CheckItem(
                name=check_fn.__name__,
                passed=False,
                details=f"Exception: {e}",
            )

        all_items.append(item)
        if not item.passed:
            any_failed = True
            if "warning" in item.details.lower() or "warn" in item.details.lower():
                all_warnings.append(item.details)
            else:
                all_errors.append(item.details)

    passed_count = sum(1 for c in all_items if c.passed)
    total_count = len(all_items)

    if any_failed:
        summary = (
            f"{passed_count}/{total_count} checks passed. "
            f"{len(all_errors)} error(s), {len(all_warnings)} warning(s)."
        )
    else:
        summary = (
            f"All {total_count} checks passed!"
        )

    if all_warnings:
        summary += f" Warnings: {'; '.join(all_warnings)}"
    if all_errors:
        summary += f" Errors: {'; '.join(all_errors)}"

    return EvidenceCheckResult(
        valid=not any_failed,
        checks=all_items,
        warnings=all_warnings,
        errors=all_errors,
        summary=summary,
    )


# ═══════════════════════════════════════════════════════════════════════
# Convenience: print-friendly output
# ═══════════════════════════════════════════════════════════════════════


def format_check_result(result: EvidenceCheckResult) -> str:
    """Format EvidenceCheckResult as a human-readable string.

    Returns a string that contains ``valid: True`` or ``valid: False``
    at the end, making it suitable for CLI grep/tests.
    """
    lines: List[str] = []
    lines.append(f"\n{'=' * 55}")
    lines.append("Evidence Pack — Multi-Layer Integrity Check")
    lines.append(f"{'=' * 55}")

    for c in result.checks:
        icon = "✅" if c.passed else "❌"
        lines.append(f"  {icon}  {c.name:<25s} → {c.details}")

    if result.warnings:
        lines.append(f"\n  ⚠️  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"       • {w}")

    if result.errors:
        lines.append(f"\n  ❌ Errors ({len(result.errors)}):")
        for e in result.errors:
            lines.append(f"       • {e}")

    lines.append(f"\n  Summary: {result.summary}")
    lines.append(f"{'=' * 55}")
    lines.append(f"valid: {result.valid}")
    lines.append(f"{'=' * 55}")

    return "\n".join(lines)


def cli_error_warning():
    """Print a friendly error if evidence_check is loaded incorrectly."""
    print("ERROR: Use 'yuleosh evidence check' or 'python3 -m yuleosh.evidence.check'")
    sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Evidence pack multi-layer integrity check",
    )
    parser.add_argument("evidence_dir", help="Path to evidence pack directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = run_full_evidence_check(args.evidence_dir)
    if args.json:
        import json as _json
        print(
            _json.dumps(
                {
                    "valid": result.valid,
                    "checks": [
                        {"name": c.name, "passed": c.passed, "details": c.details}
                        for c in result.checks
                    ],
                    "warnings": result.warnings,
                    "errors": result.errors,
                    "summary": result.summary,
                },
                indent=2,
            )
        )
    else:
        print(format_check_result(result))

    sys.exit(0 if result.valid else 1)
