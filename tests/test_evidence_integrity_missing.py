"""
Tests: evidence bundle integrity — missing artifact & unhashed artifact handling.

Covers the P0 fix: a manifest that declares an artifact whose file is
missing must be INVALID (not silently skipped); artifacts packed without a
stored SHA-256 must surface as a warning (not silently skipped).
"""

import hashlib
import json

from yuleosh.evidence.evidence_check import check_evidence_integrity


def _make_bundle(tmp_path, artifacts, manifest_extra=None):
    """Build a minimal evidence bundle with the given artifact list."""
    root = tmp_path / "bundle"
    for sub in ("ci-results", "misra-reports", "trend-data", "coverage",
                "reviews", "traceability"):
        (root / sub).mkdir(parents=True)
    # mandatory component
    (root / "ci-config.yaml").write_text("ci:\n  enabled: true\n", encoding="utf-8")

    manifest = {
        "bundle": {"generated_at": "2026-08-07T00:00:00", "version": "1.0.0"},
        "artifacts": artifacts,
        "integrity": {},
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    (root / "audit-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return root


def _artifact(dest, content=None, sha256=None):
    return {
        "type": "ci-result",
        "source": "/tmp/src.json",
        "dest": str(dest),
        "sha256": sha256 or (hashlib.sha256(content or b"x").hexdigest()),
    }


# ── Missing artifact → INVALID ─────────────────────────────────────────
def test_missing_artifact_is_invalid(tmp_path):
    """GIVEN manifest declares a file that does not exist
    WHEN checking integrity THEN result is INVALID with a missing-artifact error."""
    root = _make_bundle(tmp_path, [
        _artifact(str(tmp_path / "bundle" / "missing.json"), b"data"),
    ])
    result = check_evidence_integrity(str(root))
    assert result["valid"] is False
    assert any("Missing artifact" in e for e in result["errors"])


def test_missing_artifact_among_valid_ones(tmp_path):
    """GIVEN one valid + one missing artifact
    WHEN checking THEN INVALID and the valid one still verified."""
    root = _make_bundle(tmp_path, [
        _artifact(str(tmp_path / "bundle" / "ci-results" / "ok.json"), b"ok"),
        _artifact(str(tmp_path / "bundle" / "gone.json"), b"data"),
    ])
    (tmp_path / "bundle" / "ci-results" / "ok.json").write_bytes(b"ok")
    result = check_evidence_integrity(str(root))
    assert result["valid"] is False
    assert any("Missing artifact" in e for e in result["errors"])


def test_all_artifacts_present_still_valid(tmp_path):
    """GIVEN all declared artifacts exist with correct hashes
    WHEN checking THEN result is VALID."""
    root = _make_bundle(tmp_path, [
        _artifact(str(tmp_path / "bundle" / "ci-results" / "ok.json"), b"ok"),
    ])
    (tmp_path / "bundle" / "ci-results" / "ok.json").write_bytes(b"ok")
    result = check_evidence_integrity(str(root))
    assert result["valid"] is True
    assert result["checks"][-1]["status"] == "PASS"


# ── Unhashed artifact → WARNING (not INVALID) ──────────────────────────

def test_unhashed_artifact_warns_but_valid(tmp_path):
    """GIVEN artifact without stored sha256
    WHEN checking THEN warning surfaces but bundle stays valid."""
    root = _make_bundle(tmp_path, [
        {"type": "ci-result", "source": "/tmp/src.json",
         "dest": str(tmp_path / "bundle" / "ci-results" / "nohash.json"),
         "sha256": ""},
    ])
    (tmp_path / "bundle" / "ci-results" / "nohash.json").write_bytes(b"x")
    result = check_evidence_integrity(str(root))
    assert result["valid"] is True
    assert any("without stored SHA256" in w for w in result["warnings"])


def test_unhashed_detail_shows_count(tmp_path):
    """GIVEN artifact without sha256 WHEN checking THEN check detail mentions unhashed count."""
    root = _make_bundle(tmp_path, [
        {"type": "ci-result", "source": "/tmp/src.json",
         "dest": str(tmp_path / "bundle" / "ci-results" / "nohash.json"), "sha256": ""},
    ])
    (tmp_path / "bundle" / "ci-results" / "nohash.json").write_bytes(b"x")
    result = check_evidence_integrity(str(root))
    sha_check = next(c for c in result["checks"] if c["check"] == "artifact-sha256")
    assert "1 unhashed" in sha_check["detail"]


# ── SHA-256 mismatch still INVALID (regression) ────────────────────────

def test_hash_mismatch_still_invalid(tmp_path):
    """GIVEN artifact hash does not match file content
    WHEN checking THEN INVALID (regression — existing behavior preserved)."""
    root = _make_bundle(tmp_path, [
        _artifact(str(tmp_path / "bundle" / "ci-results" / "bad.json"), b"expected"),
    ])
    (tmp_path / "bundle" / "ci-results" / "bad.json").write_bytes(b"actual-different")
    result = check_evidence_integrity(str(root))
    assert result["valid"] is False
    assert any("SHA256 mismatch" in e for e in result["errors"])
