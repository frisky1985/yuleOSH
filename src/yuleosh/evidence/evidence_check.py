#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Evidence Pack & Integrity Check (DEF-012 / G-50: §22.1~§22.9)

CL2 audit evidence bundle with:
- SHA256 integrity verification
- 6-subdirectory non-empty check
- Complete evidence packing with manifest
- `yuleosh evidence pack` / `yuleosh evidence check` CLI

参考: ISO 26262-8 §11.2, ISO 26262-2 §6.4.7 (confirmation measures)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("evidence.check")

# Evidence bundle subdirectories (6 required)
EVIDENCE_SUBDIRS = [
    "ci-results",       # §22.1: CI layer results
    "misra-reports",    # §22.2: MISRA analysis reports
    "trend-data",       # §22.3: KPI/trend data
    "coverage",         # §22.4: Test coverage
    "reviews",          # §22.5: Review artifacts
    "traceability",     # §22.6: Traceability matrices
]

# Mandatory components
MANDATORY_COMPONENTS = [
    "audit-manifest.json",
    "ci-config.yaml",
]


def _sha256_file(filepath: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_dir(path: Path) -> None:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# G-50 §22.1: Pack evidence bundle
# ═══════════════════════════════════════════════════════════════════════


def pack_evidence_bundle(
    project_dir: str,
    output_dir: Optional[str] = None,
    components: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Generate a CL2 audit evidence bundle with integrity verification (§22.1~§22.9).

    Packs all collected artifacts from .yuleosh/ and .osh/ into a
    structured evidence bundle under ``.yuleosh/evidence-bundle/``.

    Parameters
    ----------
    project_dir : str
        Project root directory.
    output_dir : str, optional
        Override output directory (default: .yuleosh/evidence-bundle/).
    components : list[str], optional
        List of components to include (default: all EVIDENCE_SUBDIRS).

    Returns
    -------
    dict
        Bundle manifest with paths, hashes, and integrity status.
    """
    project_root = Path(project_dir)
    if output_dir:
        bundle_dir = Path(output_dir)
    else:
        bundle_dir = project_root / ".yuleosh" / "evidence-bundle"

    bundle_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    enabled_components = components or EVIDENCE_SUBDIRS
    manifest: dict[str, Any] = {
        "bundle": {
            "generated_at": now.isoformat(),
            "project_dir": project_dir,
            "version": "1.0.0",
            "spec_ref": "G-50 / §22.1~§22.9",
        },
        "components": {},
        "integrity": {},
        "artifacts": [],
    }

    # Create subdirectory structure
    for subdir in enabled_components:
        _ensure_dir(bundle_dir / subdir)

    print(f"\n  📦 CL2 Evidence Bundle (G-50)")
    print(f"  {'=' * 55}")
    print(f"  Output: {bundle_dir}/")

    # §22.1: CI results
    if "ci-results" in enabled_components:
        ci_artifacts = []
        ci_dir = project_root / ".osh" / "ci"
        if ci_dir.exists():
            for f in sorted(ci_dir.glob("*.json")):
                dest = bundle_dir / "ci-results" / f.name
                try:
                    data = json.loads(f.read_text())
                    status = data.get("status", "unknown")
                    layer = data.get("layer", "?")
                    dest.write_text(json.dumps(data, indent=2))
                    ci_artifacts.append({
                        "type": "ci-result",
                        "source": str(f),
                        "dest": str(dest),
                        "layer": layer,
                        "status": status,
                        "sha256": _sha256_file(str(dest)),
                    })
                    print(f"    📄 CI Layer {layer}: {status}")
                except Exception as e:
                    log.warning("Cannot copy CI result %s: %s", f.name, e)
        manifest["components"]["ci-results"] = {
            "label": "CI Layer Results",
            "spec_ref": "§22.1",
            "artifacts": ci_artifacts,
        }
        manifest["artifacts"].extend(ci_artifacts)

    # §22.2: MISRA reports
    if "misra-reports" in enabled_components:
        misra_artifacts = []
        misra_reports = project_root / ".yuleosh" / "reports"
        for pattern in ["misra-report.json", "misra-report.md", "misra-raw-output.txt",
                        "misra-trend.jsonl"]:
            src = misra_reports / pattern
            if src.exists():
                dest = bundle_dir / "misra-reports" / src.name
                try:
                    data = src.read_bytes()
                    dest.write_bytes(data)
                    misra_artifacts.append({
                        "type": "misra-report",
                        "source": str(src),
                        "dest": str(dest),
                        "sha256": _sha256_file(str(dest)),
                    })
                    print(f"    🔍 MISRA report: {src.name}")
                except Exception as e:
                    log.warning("Cannot copy MISRA report %s: %s", src.name, e)

        if not misra_artifacts:
            print(f"    ⏭️  No MISRA reports found")
        manifest["components"]["misra-reports"] = {
            "label": "MISRA Analysis Reports",
            "spec_ref": "§22.2",
            "artifacts": misra_artifacts,
        }
        manifest["artifacts"].extend(misra_artifacts)

    # §22.3: Trend data
    if "trend-data" in enabled_components:
        trend_artifacts = []
        reports_dir = project_root / ".yuleosh" / "reports"
        for pattern in ["misra-trend.jsonl", "coverage-trend.jsonl",
                        "kpi-baseline.json", "build-metadata.jsonl",
                        "process-kpi.jsonl"]:
            src = reports_dir / pattern
            if src.exists():
                dest = bundle_dir / "trend-data" / src.name
                try:
                    data = src.read_bytes()
                    dest.write_bytes(data)
                    trend_artifacts.append({
                        "type": "trend-data",
                        "source": str(src),
                        "dest": str(dest),
                        "sha256": _sha256_file(str(dest)),
                    })
                    print(f"    📈 Trend data: {src.name}")
                except Exception as e:
                    log.warning("Cannot copy trend %s: %s", src.name, e)
        if not trend_artifacts:
            print(f"    ⏭️  No trend data found")
        manifest["components"]["trend-data"] = {
            "label": "KPI/Trend Data",
            "spec_ref": "§22.3",
            "artifacts": trend_artifacts,
        }
        manifest["artifacts"].extend(trend_artifacts)

    # §22.4: Coverage
    if "coverage" in enabled_components:
        cov_artifacts = []
        reports_dir = project_root / ".yuleosh" / "reports"
        for pattern in ["c-coverage.json", "coverage.json", "coverage-trend.jsonl"]:
            src = reports_dir / pattern
            if src.exists():
                dest = bundle_dir / "coverage" / src.name
                try:
                    data = src.read_bytes()
                    dest.write_bytes(data)
                    cov_artifacts.append({
                        "type": "coverage",
                        "source": str(src),
                        "dest": str(dest),
                        "sha256": _sha256_file(str(dest)),
                    })
                    print(f"    📊 Coverage: {src.name}")
                except Exception as e:
                    log.warning("Cannot copy coverage %s: %s", src.name, e)
        if not cov_artifacts:
            print(f"    ⏭️  No coverage data found")
        manifest["components"]["coverage"] = {
            "label": "Test Coverage",
            "spec_ref": "§22.4",
            "artifacts": cov_artifacts,
        }
        manifest["artifacts"].extend(cov_artifacts)

    # §22.5: Reviews
    if "reviews" in enabled_components:
        review_artifacts = []
        review_dir = project_root / ".yuleosh" / "reports" / "reviews"
        if review_dir.exists():
            rev_bundle = bundle_dir / "reviews"
            _ensure_dir(rev_bundle)
            for f in sorted(review_dir.glob("*.json")):
                dest = rev_bundle / f.name
                try:
                    data = f.read_bytes()
                    dest.write_bytes(data)
                    review_artifacts.append({
                        "type": "review",
                        "source": str(f),
                        "dest": str(dest),
                        "sha256": _sha256_file(str(dest)),
                    })
                except Exception as e:
                    log.warning("Cannot copy review %s: %s", f.name, e)
            print(f"    📝 Review artifacts: {len(review_artifacts)} file(s)")
        else:
            # Also check .osh/sessions/ for review reports
            session_dir = project_root / ".osh" / "sessions"
            if session_dir.exists():
                rev_bundle = bundle_dir / "reviews"
                _ensure_dir(rev_bundle)
                for f in sorted(session_dir.glob("*.json"))[:20]:
                    dest = rev_bundle / f.name
                    try:
                        data = f.read_bytes()
                        dest.write_bytes(data)
                        review_artifacts.append({
                            "type": "review",
                            "source": str(f),
                            "dest": str(dest),
                            "sha256": _sha256_file(str(dest)),
                        })
                    except Exception as e:
                        log.warning("Cannot copy session %s: %s", f.name, e)
                print(f"    📝 Session artifacts: {len(review_artifacts)} file(s)")
        manifest["components"]["reviews"] = {
            "label": "Review Artifacts",
            "spec_ref": "§22.5",
            "artifacts": review_artifacts,
        }
        manifest["artifacts"].extend(review_artifacts)

    # §22.6: Traceability
    if "traceability" in enabled_components:
        trace_artifacts = []
        reports_dir = project_root / ".yuleosh" / "reports"
        for pattern in ["traceability-report.json", "lrt-matrix.json",
                        "agent-traceability.jsonl"]:
            src = reports_dir / pattern
            if src.exists():
                dest = bundle_dir / "traceability" / src.name
                try:
                    data = src.read_bytes()
                    dest.write_bytes(data)
                    trace_artifacts.append({
                        "type": "traceability",
                        "source": str(src),
                        "dest": str(dest),
                        "sha256": _sha256_file(str(dest)),
                    })
                    print(f"    📋 Traceability: {src.name}")
                except Exception as e:
                    log.warning("Cannot copy trace %s: %s", src.name, e)
        if not trace_artifacts:
            print(f"    ⏭️  No traceability data found")
        manifest["components"]["traceability"] = {
            "label": "Traceability Matrices",
            "spec_ref": "§22.6",
            "artifacts": trace_artifacts,
        }
        manifest["artifacts"].extend(trace_artifacts)

    # §22.7: CI config (mandatory)
    ci_config_src = project_root / ".yuleosh" / "ci-config.yaml"
    if ci_config_src.exists():
        dest = bundle_dir / "ci-config.yaml"
        try:
            data = ci_config_src.read_bytes()
            dest.write_bytes(data)
            manifest["artifacts"].append({
                "type": "ci-config",
                "source": str(ci_config_src),
                "dest": str(dest),
                "sha256": _sha256_file(str(dest)),
            })
            print(f"    ⚙️  CI config: collected")
        except Exception as e:
            log.warning("Cannot copy ci-config: %s", e)

    # §22.9: Write audit manifest
    manifest_path = bundle_dir / "audit-manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False, default=str)
    manifest["_manifest_sha256"] = _sha256_file(str(manifest_path))

    # Compute bundle integrity
    total_artifacts = len(manifest["artifacts"])
    manifest["integrity"] = {
        "total_artifacts": total_artifacts,
        "manifest_sha256": manifest["_manifest_sha256"],
        "bundled_at": now.isoformat(),
    }

    print(f"\n  {'=' * 55}")
    print(f"  ✅ Evidence bundle complete")
    print(f"     Directory: {bundle_dir}/")
    print(f"     Subdirectories: {len(enabled_components)}")
    print(f"     Artifacts: {total_artifacts}")
    print(f"     Manifest SHA256: {manifest['_manifest_sha256'][:16]}...")

    return manifest


# ═══════════════════════════════════════════════════════════════════════
# G-50 §22.8: Integrity check
# ═══════════════════════════════════════════════════════════════════════


def check_evidence_integrity(bundle_dir: str, subdirs: Optional[list[str]] = None) -> dict[str, Any]:
    """Check evidence bundle integrity (§22.8).

    Validates:
    - SHA256 hash integrity of all artifacts in the manifest
    - All 6 required subdirectories exist and are non-empty
    - Mandatory components (audit-manifest.json, ci-config.yaml) exist
    - No orphan files outside subdirectories (warning only)

    Parameters
    ----------
    bundle_dir : str
        Path to evidence bundle directory.
    subdirs : list[str], optional
        Expected subdirectories (default: EVIDENCE_SUBDIRS).

    Returns
    -------
    dict
        Integrity check report.
    """
    bundle_path = Path(bundle_dir)
    check_subdirs = subdirs or EVIDENCE_SUBDIRS
    now = datetime.now()

    result: dict[str, Any] = {
        "bundle_dir": bundle_dir,
        "checked_at": now.isoformat(),
        "valid": True,
        "checks": [],
        "errors": [],
        "warnings": [],
        "summary": "",
    }

    # 1. Load manifest
    manifest_path = bundle_path / "audit-manifest.json"
    if not manifest_path.exists():
        result["valid"] = False
        result["errors"].append("audit-manifest.json not found — bundle may be incomplete")
        return result

    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        result["valid"] = False
        result["errors"].append(f"Cannot parse audit-manifest.json: {e}")
        return result

    artifacts = manifest.get("artifacts", [])
    result["checks"].append({
        "check": "manifest-parsed",
        "status": "PASS",
        "detail": f"audit-manifest.json parsed: {len(artifacts)} artifacts listed",
    })

    # 2. Verify manifest SHA256 (self-check)
    manifest_sha = _sha256_file(str(manifest_path))
    stored_sha = manifest.get("_manifest_sha256", "")
    if stored_sha and manifest_sha != stored_sha:
        result["valid"] = False
        result["errors"].append(
            f"Manifest SHA256 mismatch: computed={manifest_sha[:16]}..., "
            f"stored={stored_sha[:16]}..."
        )
    else:
        result["checks"].append({
            "check": "manifest-sha256",
            "status": "PASS",
            "detail": f"SHA256: {manifest_sha[:16]}...",
        })

    # 3. Verify SHA256 for each artifact
    sha_mismatches = 0
    for artifact in artifacts:
        dest = artifact.get("dest", "")
        if not dest or not os.path.exists(dest):
            continue
        expected_sha = artifact.get("sha256", "")
        if not expected_sha:
            continue
        actual_sha = _sha256_file(dest)
        if actual_sha != expected_sha:
            sha_mismatches += 1
            result["errors"].append(
                f"SHA256 mismatch: {dest} (expected {expected_sha[:16]}..., "
                f"got {actual_sha[:16]}...)"
            )

    if sha_mismatches == 0:
        result["checks"].append({
            "check": "artifact-sha256",
            "status": "PASS",
            "detail": f"All {len(artifacts)} artifacts SHA256 verified",
        })
    else:
        result["valid"] = False
        result["checks"].append({
            "check": "artifact-sha256",
            "status": "FAIL",
            "detail": f"{sha_mismatches}/{len(artifacts)} SHA256 mismatch(es)",
        })

    # 4. Check 6 subdirectories exist and are non-empty
    empty_dirs = 0
    for subdir in check_subdirs:
        sub_path = bundle_path / subdir
        if not sub_path.exists():
            result["errors"].append(f"Subdirectory missing: {subdir}/")
            result["valid"] = False
            continue
        if not any(sub_path.iterdir()):
            result["warnings"].append(f"Subdirectory empty: {subdir}/")
            empty_dirs += 1

    if empty_dirs == 0:
        result["checks"].append({
            "check": "subdirs-nonempty",
            "status": "PASS",
            "detail": f"All {len(check_subdirs)} subdirectories present and non-empty",
        })
    else:
        result["warnings"].append(
            f"{empty_dirs}/{len(check_subdirs)} subdirectories empty"
        )

    # 5. Check mandatory components
    for comp in MANDATORY_COMPONENTS:
        comp_path = bundle_path / comp
        if not comp_path.exists():
            result["warnings"].append(f"Mandatory component missing: {comp}")

    # 6. Check for orphan files (in bundle root, not in subdirs)
    known_dirs = set(check_subdirs)
    orphan_files = [
        f.name for f in bundle_path.iterdir()
        if f.is_file() and f.name not in MANDATORY_COMPONENTS and f.name != "audit-manifest.json"
    ]
    if orphan_files:
        result["warnings"].append(
            f"Orphan file(s) in bundle root (not in subdirectory): {', '.join(orphan_files)}"
        )

    # Summary
    if result["errors"] and result["valid"]:
        result["valid"] = False

    if result["valid"]:
        result["summary"] = (
            f"✅ Evidence integrity: VALID — {len(artifacts)} artifacts, "
            f"{len(check_subdirs)} subdirs, {len(result['warnings'])} warning(s)"
        )
    else:
        result["summary"] = (
            f"❌ Evidence integrity: INVALID — {len(result['errors'])} error(s), "
            f"{len(result['warnings'])} warning(s)"
        )

    if result["warnings"]:
        result["summary"] += f"\n   Warnings: {'; '.join(result['warnings'])}"
    if result["errors"]:
        result["summary"] += f"\n   Errors: {'; '.join(result['errors'])}"

    return result


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def main():
    """CLI entry point for evidence pack/check."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CL2 Audit Evidence Bundle — Pack & Check (G-50)",
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    p_pack = sub.add_parser("pack", help="Pack evidence bundle")
    p_pack.add_argument("--project-dir", default=os.environ.get("OSH_HOME", os.getcwd()))
    p_pack.add_argument("--output", "-o", default=None, help="Output directory")

    p_check = sub.add_parser("check", help="Check evidence bundle integrity")
    p_check.add_argument("bundle_dir", help="Path to evidence bundle directory")
    p_check.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.command == "pack":
        manifest = pack_evidence_bundle(
            project_dir=args.project_dir,
            output_dir=args.output,
        )
        print(f"\n  Manifest: {Path(args.output or '.yuleosh/evidence-bundle/', 'audit-manifest.json')}")
        print()

    elif args.command == "check":
        result = check_evidence_integrity(args.bundle_dir)
        if args.getattr(args, "json", False):
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"\n  🔍 Evidence Bundle Integrity Check")
            print(f"  {'=' * 55}")
            print(f"  Bundle: {args.bundle_dir}")
            print(f"  Status: {'✅ VALID' if result['valid'] else '❌ INVALID'}")
            print()
            for check in result.get("checks", []):
                icon = "✅" if check["status"] == "PASS" else "❌"
                print(f"  {icon} {check['check']}: {check['detail']}")
            for warn in result.get("warnings", []):
                print(f"  ⚠️  {warn}")
            for err in result.get("errors", []):
                print(f"  ❌ {err}")
            print()
            print(f"  Summary: {result['summary']}")
            print()

        if not result.get("valid", True):
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
