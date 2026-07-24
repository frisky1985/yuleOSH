"""
yuleOSH Evidence Engine — Compliance pack generation and CLI.

Provides the top-level ``generate_evidence()`` function, the CLI ``main()``
entry point, the race-condition guard ``_check_pipeline_not_running()``,
and the ``pack_compliance_zip()`` function that bundles evidence into a
ZIP archive suitable for ASPICE audit.
"""

import json
import logging
import os
import sys
import time as _time
from pathlib import Path
from typing import Optional
import zipfile

log = logging.getLogger("evidence.collector")


def _compute_sha256(file_path: str) -> str:
    """Compute SHA256 hex digest of a file."""
    import hashlib
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _build_manifest_entry(file_path: Path, arcname: str) -> dict:
    """Build a manifest entry with path, SHA256, size, and timestamp."""
    stat = file_path.stat()
    return {
        "path": arcname,
        "sha256": _compute_sha256(str(file_path)),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "mtime_iso": _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(stat.st_mtime)),
    }


def pack_compliance_zip(collector: "EvidenceCollector") -> str:
    """Create compliance pack ZIP for ASPICE audit.

    Includes all generated evidence files, the requirements spec,
    startup analysis, and any SIL test reports found in
    ``.osh/ci/``.

    Also generates a manifest.json inside the ZIP with path, SHA256,
    size, and timestamp for every file.

    Args:
        collector: An ``EvidenceCollector`` instance that has already
            collected data and generated reports.

    Returns:
        Path to the created ZIP file.
    """
    zip_path = collector.evidence_dir / "compliance-pack.zip"
    manifest_entries: list[dict] = []

    def _add_to_zip(file_path: Path, arcname: str):
        if file_path.exists():
            zf.write(file_path, arcname=arcname)
            manifest_entries.append(_build_manifest_entry(file_path, arcname))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all generated evidence files
        for f in collector.evidence_dir.iterdir():
            if f.suffix in (".md", ".json") and f.name != "compliance-pack.zip":
                _add_to_zip(f, f.name)

        # Add spec file
        spec_path = Path(collector.project_dir) / "docs" / "spec.md"
        _add_to_zip(spec_path, "spec.md")

        # Add startup analysis
        sa_path = Path(collector.project_dir) / "docs" / "startup-analysis.md"
        _add_to_zip(sa_path, "startup-analysis.md")

        # Include SIL test reports from .osh/ci/*sil*.json
        ci_dir = Path(collector.project_dir) / ".osh" / "ci"
        if ci_dir.exists():
            for sil_file in sorted(ci_dir.glob("*sil*.json")):
                _add_to_zip(sil_file, f"sil-reports/{sil_file.name}")

        # Include pipeline session step data (all stages)
        sessions_dir = Path(collector.project_dir) / ".osh" / "sessions"
        if sessions_dir.exists():
            for session_folder in sorted(sessions_dir.iterdir()):
                if not session_folder.is_dir():
                    continue
                for step_file in sorted(session_folder.glob("*.json")):
                    arcname = f"session-steps/{session_folder.name}/{step_file.name}"
                    _add_to_zip(step_file, arcname)

        # Generate manifest.json
        manifest = {
            "manifest_version": "1.0",
            "pack_generated_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_dir": collector.project_dir,
            "total_files": len(manifest_entries),
            "files": manifest_entries,
        }
        manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
        zf.writestr("manifest.json", manifest_json)

    print(f"  📦 Compliance pack created: {zip_path}")
    print(f"     Manifest: {len(manifest_entries)} files tracked")
    print(f"     Pipeline sessions included: ✓")
    return str(zip_path)


def _check_pipeline_not_running(project_dir: str) -> bool:
    """Check that no pipeline is currently writing to avoid race conditions.

    Checks session status AND recent write activity in reviews/ci directories
    to detect the window where pipeline is done but artifacts are still flushing.

    Returns True if it's safe to collect evidence (no running pipeline).
    """
    sessions_dir = Path(project_dir) / ".osh" / "sessions"
    if sessions_dir.is_dir():
        for sf in sorted(
            sessions_dir.rglob("session.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:3]:
            try:
                data = json.loads(sf.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            status = data.get("status", "")
            if status in ("running", "in_progress"):
                print(f"  ⚠️  Pipeline still running: {sf.parent.name} (status={status})")
                return False

    # Also check reviews/ and ci/ for recent writes (artifact flush window)
    for subdir in ("reviews", "ci"):
        d = Path(project_dir) / ".osh" / subdir
        if d.is_dir():
            try:
                recent = max(
                    (f.stat().st_mtime for f in d.rglob("*.json") if f.is_file()),
                    default=0,
                )
                if (_time.time() - recent) < 5:  # 5-second grace window
                    print(f"  ⚠️  Recent writes in .osh/{subdir}/ ({_time.time() - recent:.1f}s ago) — may be pipeline flushing")
                    return False
            except OSError:
                pass

    return True


def generate_evidence(project_dir: str = None, spec_path: str = None):
    """Generate full evidence chain.

    Args:
        project_dir: Root directory of the project. Defaults to OSH_HOME env or cwd.
        spec_path: Optional explicit spec file path. Defaults to docs/spec.md under project_dir.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    print(f"\n📦 OSH Evidence Generation")
    print(f"{'='*50}")

    # Race condition guard: wait if pipeline is still running
    _max_wait = 30  # seconds
    _waited = 0
    while not _check_pipeline_not_running(project_dir) and _waited < _max_wait:
        _sleep = min(2, _max_wait - _waited)
        print(f"  ⏳ Waiting for pipeline to finish... ({_waited}s elapsed)")
        _time.sleep(_sleep)
        _waited += _sleep
    if _waited >= _max_wait:
        print(f"  ⚠️  Timed out waiting for pipeline (waited {_waited}s). Collecting anyway — data may be incomplete.")

    from yuleosh.evidence.generator import EvidenceCollector

    collector = EvidenceCollector(project_dir)

    collector.collect_requirements(spec_path=spec_path)
    collector.collect_reviews()
    collector.collect_ci_results()
    collector.collect_sil_reports()
    collector.collect_session_data()

    print(f"\n{'='*50}")

    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.generate_acceptance_matrix())
    artifacts.append(collector.aggregate_review_logs())
    artifacts.append(pack_compliance_zip(collector))

    # Generate standalone manifest.json for the evidence directory
    manifest_path = collector.evidence_dir / "manifest.json"
    ev_manifest_entries = []
    for f in sorted(collector.evidence_dir.iterdir()):
        if f.name == "compliance-pack.zip":
            continue
        if f.suffix in (".md", ".json", ".zip"):
            ev_manifest_entries.append(_build_manifest_entry(f, f.name))
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "manifest_version": "1.0",
            "generated_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_dir": collector.project_dir,
            "total_files": len(ev_manifest_entries),
            "files": ev_manifest_entries,
        }, f, indent=2, ensure_ascii=False)
    artifacts.append(str(manifest_path))

    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print(f"   - traceability-matrix.md + traceability-matrix.json")
    print(f"   - requirement-coverage.md")
    print(f"   - code-coverage-report.md")
    print(f"   - review-log-summary.md + review-log.json")
    print(f"   - acceptance-matrix.md")
    print(f"   - manifest.json (目录清单 + SHA256)")
    print(f"   - sil-reports/ (in compliance-pack.zip) 🖥")
    print(f"   - compliance-pack.zip 🎯")
    print()

    return artifacts


def main():
    """CLI entry point for evidence generation."""
    spec_path = None
    args = [a for a in sys.argv[1:] if a != "pack"]
    if args:
        spec_path = args[0]
    generate_evidence(spec_path=spec_path)


if __name__ == "__main__":
    main()
