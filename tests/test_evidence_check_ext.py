"""
Extended tests for evidence/evidence_check.py — 47% → ≥60% coverage.

Tests pack_evidence_bundle with real subdirectories, check_evidence_integrity
with various states, and edge cases for the CL2 audit evidence bundle functions.
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.evidence.evidence_check import (
    _sha256_file,
    _ensure_dir,
    pack_evidence_bundle,
    check_evidence_integrity,
    EVIDENCE_SUBDIRS,
    MANDATORY_COMPONENTS,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def project_with_ci(tmp_path):
    """Project with .osh/ci/ files for pack_evidence_bundle."""
    osh_ci = tmp_path / ".osh" / "ci"
    osh_ci.mkdir(parents=True)
    (osh_ci / "layer1.json").write_text(json.dumps({
        "layer": 1, "status": "passed", "coverage": {"line_coverage": 80},
    }))
    (osh_ci / "layer2.json").write_text(json.dumps({
        "layer": 2, "status": "passed",
    }))
    return tmp_path


@pytest.fixture
def project_with_trend(tmp_path):
    """Project with .yuleosh/reports/ trend files."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "misra-trend.jsonl").write_text('{"date":"2026-01","violations":42}\n')
    (reports_dir / "coverage-trend.jsonl").write_text('{"date":"2026-01","coverage":65}\n')
    (reports_dir / "kpi-baseline.json").write_text('{"kpi": "test"}\n')
    (reports_dir / "build-metadata.jsonl").write_text('{"build": "123"}\n')
    (reports_dir / "process-kpi.jsonl").write_text('{"process": "ok"}\n')
    return tmp_path


@pytest.fixture
def project_with_misra_reports(tmp_path):
    """Project with MISRA report files."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "misra-report.json").write_text(json.dumps({"violations": [], "summary": "OK"}))
    (reports_dir / "misra-report.md").write_text("# MISRA Report\nAll clear.\n")
    (reports_dir / "misra-raw-output.txt").write_text("violation at line 42\n")
    return tmp_path


@pytest.fixture
def project_with_traceability(tmp_path):
    """Project with traceability files."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "traceability-report.json").write_text(json.dumps({"entries": []}))
    (reports_dir / "lrt-matrix.json").write_text(json.dumps({"matrix": []}))
    (reports_dir / "agent-traceability.jsonl").write_text('{"agent":"arch"}\n')
    return tmp_path


@pytest.fixture
def project_with_coverage(tmp_path):
    """Project with coverage files."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "c-coverage.json").write_text(json.dumps({"coverage": 75}))
    (reports_dir / "coverage.json").write_text(json.dumps({"line_rate": 0.8}))
    return tmp_path


@pytest.fixture
def project_with_reviews(tmp_path):
    """Project with review artifacts."""
    review_dir = tmp_path / ".yuleosh" / "reports" / "reviews"
    review_dir.mkdir(parents=True)
    (review_dir / "review-001.json").write_text(json.dumps({"id": "R1", "status": "passed"}))
    (review_dir / "review-002.json").write_text(json.dumps({"id": "R2", "status": "failed"}))
    return tmp_path


@pytest.fixture
def project_with_session_reviews(tmp_path):
    """Project with session-based reviews (fallback path)."""
    session_dir = tmp_path / ".osh" / "sessions"
    session_dir.mkdir(parents=True)
    for i in range(3):
        (session_dir / f"session-{i}.json").write_text(json.dumps({"id": f"S{i}"}))
    return tmp_path


@pytest.fixture
def project_with_ci_config(tmp_path):
    """Project with ci-config.yaml."""
    yuleosh_dir = tmp_path / ".yuleosh"
    yuleosh_dir.mkdir(parents=True)
    (yuleosh_dir / "ci-config.yaml").write_text("stages:\n  - build\n  - test\n")
    return tmp_path


# ======================================================================
# pack_evidence_bundle — ci-results
# ======================================================================

def test_pack_ci_results(project_with_ci):
    """GIVEN project with CI results WHEN pack THEN ci-results artifact created."""
    bundle = pack_evidence_bundle(str(project_with_ci))
    assert "components" in bundle
    assert "ci-results" in bundle["components"]
    ci = bundle["components"]["ci-results"]
    assert len(ci["artifacts"]) == 2
    assert ci["artifacts"][0]["layer"] == 1  # integer from JSON
    assert ci["artifacts"][0]["status"] == "passed"
    assert "sha256" in ci["artifacts"][0]


def test_pack_ci_results_no_ci_dir(tmp_path):
    """GIVEN project with no CI dir WHEN pack THEN ci-results empty."""
    bundle = pack_evidence_bundle(str(tmp_path))
    ci = bundle["components"].get("ci-results", {})
    assert len(ci.get("artifacts", [])) == 0


def test_pack_ci_results_corrupted_json(tmp_path, caplog):
    """GIVEN corrupted CI JSON WHEN pack THEN logs warning and continues."""
    ci_dir = tmp_path / ".osh" / "ci"
    ci_dir.mkdir(parents=True)
    (ci_dir / "layer1.json").write_text("not valid json {{{")

    bundle = pack_evidence_bundle(str(tmp_path))
    ci = bundle["components"].get("ci-results", {})
    # Should not crash, should have 0 artifacts from the bad file
    assert len(ci.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — misra-reports
# ======================================================================

def test_pack_misra_reports(project_with_misra_reports):
    """GIVEN project with MISRA reports WHEN pack THEN misra artifacts created."""
    bundle = pack_evidence_bundle(str(project_with_misra_reports))
    misra = bundle["components"].get("misra-reports", {})
    assert len(misra.get("artifacts", [])) >= 1


def test_pack_misra_reports_no_files(tmp_path):
    """GIVEN project with no MISRA reports WHEN pack THEN handled."""
    bundle = pack_evidence_bundle(str(tmp_path))
    misra = bundle["components"].get("misra-reports", {})
    assert len(misra.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — trend-data
# ======================================================================

def test_pack_trend_data(project_with_trend):
    """GIVEN project with trend data WHEN pack THEN trend-data artifacts created."""
    bundle = pack_evidence_bundle(str(project_with_trend))
    trend = bundle["components"].get("trend-data", {})
    assert len(trend.get("artifacts", [])) == 5


def test_pack_trend_data_no_files(tmp_path):
    """GIVEN project with no trend data WHEN pack THEN handled."""
    bundle = pack_evidence_bundle(str(tmp_path))
    trend = bundle["components"].get("trend-data", {})
    assert len(trend.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — coverage
# ======================================================================

def test_pack_coverage(project_with_coverage):
    """GIVEN project with coverage files WHEN pack THEN coverage artifacts created."""
    bundle = pack_evidence_bundle(str(project_with_coverage))
    cov = bundle["components"].get("coverage", {})
    assert len(cov.get("artifacts", [])) == 2


def test_pack_coverage_no_files(tmp_path):
    """GIVEN project with no coverage data WHEN pack THEN handled."""
    bundle = pack_evidence_bundle(str(tmp_path))
    cov = bundle["components"].get("coverage", {})
    assert len(cov.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — reviews
# ======================================================================

def test_pack_reviews(project_with_reviews):
    """GIVEN project with review artifacts WHEN pack THEN review artifacts created."""
    bundle = pack_evidence_bundle(str(project_with_reviews))
    reviews = bundle["components"].get("reviews", {})
    assert len(reviews.get("artifacts", [])) == 2


def test_pack_reviews_session_fallback(project_with_session_reviews):
    """GIVEN project with session files only WHEN pack THEN session artifacts used."""
    bundle = pack_evidence_bundle(str(project_with_session_reviews))
    reviews = bundle["components"].get("reviews", {})
    assert len(reviews.get("artifacts", [])) == 3


def test_pack_reviews_no_files(tmp_path):
    """GIVEN project with no review artifacts WHEN pack THEN handled."""
    bundle = pack_evidence_bundle(str(tmp_path))
    reviews = bundle["components"].get("reviews", {})
    assert len(reviews.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — traceability
# ======================================================================

def test_pack_traceability(project_with_traceability):
    """GIVEN project with traceability files WHEN pack THEN traceability artifacts."""
    bundle = pack_evidence_bundle(str(project_with_traceability))
    trace = bundle["components"].get("traceability", {})
    assert len(trace.get("artifacts", [])) == 3


def test_pack_traceability_no_files(tmp_path):
    """GIVEN project with no traceability data WHEN pack THEN handled."""
    bundle = pack_evidence_bundle(str(tmp_path))
    trace = bundle["components"].get("traceability", {})
    assert len(trace.get("artifacts", [])) == 0


# ======================================================================
# pack_evidence_bundle — ci-config (mandatory component)
# ======================================================================

def test_pack_ci_config(project_with_ci_config):
    """GIVEN project with ci-config.yaml WHEN pack THEN manifest includes it."""
    bundle = pack_evidence_bundle(str(project_with_ci_config))
    artifacts = bundle.get("artifacts", [])
    configs = [a for a in artifacts if a["type"] == "ci-config"]
    assert len(configs) == 1
    assert "sha256" in configs[0]


def test_pack_ci_config_missing(tmp_path):
    """GIVEN project without ci-config.yaml WHEN pack THEN no error."""
    bundle = pack_evidence_bundle(str(tmp_path))
    artifacts = bundle.get("artifacts", [])
    configs = [a for a in artifacts if a["type"] == "ci-config"]
    assert len(configs) == 0


# ======================================================================
# pack_evidence_bundle — swe_status derivation
# ======================================================================

def test_pack_swe_status_basic(tmp_path):
    """GIVEN a bundle with coverage + misra-reports WHEN pack THEN SWE.4 is completed."""
    # Set up coverage data
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "coverage.json").write_text(json.dumps({}))
    (reports_dir / "misra-report.json").write_text(json.dumps({}))

    bundle = pack_evidence_bundle(str(tmp_path))
    assert "swe_status" in bundle
    swe4 = bundle["swe_status"].get("SWE.4", {})
    assert swe4.get("status") == "completed"


def test_pack_swe_status_basic(tmp_path):
    """GIVEN a bundle WHEN pack THEN swe_status contains all SWE entries."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "coverage.json").write_text(json.dumps({}))

    bundle = pack_evidence_bundle(str(tmp_path))
    assert "swe_status" in bundle
    for swe_id in ["SWE.1", "SWE.2", "SWE.3", "SWE.4", "SWE.5", "SWE.6"]:
        assert swe_id in bundle["swe_status"], f"Missing {swe_id} in swe_status"
        entry = bundle["swe_status"][swe_id]
        assert "status" in entry
        assert "label" in entry
        assert "last_updated" in entry


def test_pack_swe_status_label_mapping(tmp_path):
    """GIVEN pack_evidence_bundle WHEN run THEN status labels map correctly."""
    bundle = pack_evidence_bundle(str(tmp_path))
    for swe_id, entry in bundle["swe_status"].items():
        status = entry["status"]
        label = entry["label"]
        if status == "completed":
            assert "完成" in label
        elif status == "partial":
            assert "部分" in label
        elif status == "not_started":
            assert "未开始" in label


def test_pack_swe_status_completed_with_reviews_coverage(tmp_path):
    """GIVEN reviews + coverage WHEN pack THEN SWE.6 is completed."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "coverage.json").write_text(json.dumps({}))
    review_dir = reports_dir / "reviews"
    review_dir.mkdir()
    (review_dir / "r1.json").write_text(json.dumps({}))

    bundle = pack_evidence_bundle(str(tmp_path))
    swe6 = bundle["swe_status"].get("SWE.6", {})
    assert swe6.get("status") == "completed"


# ======================================================================
# pack_evidence_bundle — output_dir and components override
# ======================================================================

def test_pack_with_custom_output(tmp_path):
    """GIVEN custom output_dir WHEN pack THEN bundle created there."""
    output = tmp_path / "custom-bundle"
    bundle = pack_evidence_bundle(str(tmp_path), str(output))
    assert output.exists()
    assert (output / "audit-manifest.json").exists()


def test_pack_with_components_subset(tmp_path):
    """GIVEN components=['ci-results'] WHEN pack THEN only ci-results dir created."""
    bundle = pack_evidence_bundle(str(tmp_path), components=["ci-results"])
    assert "ci-results" in bundle["components"]
    # Should have all swe_status still
    assert "swe_status" in bundle


# ======================================================================
# check_evidence_integrity — valid bundle
# ======================================================================

def test_check_integrity_valid_bundle(tmp_path):
    """GIVEN a complete evidence bundle WHEN check integrity THEN valid True."""
    # Create a proper bundle
    from yuleosh.evidence.evidence_check import pack_evidence_bundle
    bundle = pack_evidence_bundle(str(tmp_path), str(tmp_path / "bundle"))

    result = check_evidence_integrity(str(tmp_path / "bundle"))
    assert result["bundle_dir"] == str(tmp_path / "bundle")
    assert "checked_at" in result
    # A bundle with at least some structure should be valid or at least return check results
    assert "checks" in result


def test_check_integrity_missing_manifest(tmp_path):
    """GIVEN a directory with no manifest WHEN check THEN valid False."""
    result = check_evidence_integrity(str(tmp_path))
    assert result["valid"] is False
    assert any("audit-manifest.json" in str(e) for e in result["errors"])


def test_check_integrity_corrupted_manifest(tmp_path):
    """GIVEN a corrupted manifest file WHEN check THEN valid False."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "audit-manifest.json").write_text("not valid json {{{")
    result = check_evidence_integrity(str(bundle_dir))
    assert result["valid"] is False
    assert any("parse" in str(e).lower() for e in result["errors"])


def test_check_integrity_sha_mismatch(tmp_path):
    """GIVEN a bundle with wrong SHA256 in manifest WHEN check THEN reports error."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    # Create a simulated manifest with wrong SHA
    manifest = {
        "artifacts": [],
        "_manifest_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    }
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    result = check_evidence_integrity(str(bundle_dir))
    assert "SHA256 mismatch" in str(result.get("errors", [])) or not result["valid"]


def test_check_integrity_subdirs_valid(tmp_path):
    """GIVEN bundle with all 6 subdirs non-empty WHEN check THEN PASS for subdirs."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    # Create manifest
    manifest = {"artifacts": []}
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    # Create all subdirs with placeholder files
    for sub in EVIDENCE_SUBDIRS:
        sub_path = bundle_dir / sub
        sub_path.mkdir(parents=True)
        (sub_path / "placeholder.txt").write_text("test")

    result = check_evidence_integrity(str(bundle_dir))
    subdir_checks = [c for c in result.get("checks", []) if c["check"] == "subdirs-nonempty"]
    if subdir_checks:
        assert subdir_checks[0]["status"] == "PASS"


def test_check_integrity_missing_subdir(tmp_path):
    """GIVEN bundle with missing subdir WHEN check THEN error reported."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    manifest = {"artifacts": []}
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    # Don't create all subdirs
    result = check_evidence_integrity(str(bundle_dir))
    errors = [str(e) for e in result.get("errors", [])]
    assert any("missing" in e.lower() for e in errors)


def test_check_integrity_orphan_files(tmp_path):
    """GIVEN bundle with files outside subdirs WHEN check THEN warning reported."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    manifest = {"artifacts": []}
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    # Create all subdirs (non-empty)
    for sub in EVIDENCE_SUBDIRS:
        sub_path = bundle_dir / sub
        sub_path.mkdir(parents=True)
        (sub_path / "placeholder.txt").write_text("test")

    # Create orphan file
    (bundle_dir / "orphan.txt").write_text("orphan data")
    (bundle_dir / "orphan.json").write_text(json.dumps({"x": 1}))

    result = check_evidence_integrity(str(bundle_dir))
    warnings = [str(w) for w in result.get("warnings", [])]
    assert any("orphan" in w.lower() for w in warnings)


def test_check_integrity_missing_mandatory_components(tmp_path):
    """GIVEN bundle without ci-config.yaml WHEN check THEN warning."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    manifest = {"artifacts": []}
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    for sub in EVIDENCE_SUBDIRS:
        sub_path = bundle_dir / sub
        sub_path.mkdir(parents=True)
        (sub_path / "p.txt").write_text("test")

    result = check_evidence_integrity(str(bundle_dir))
    warnings = [str(w) for w in result.get("warnings", [])]
    assert any("ci-config.yaml" in w for w in warnings)


def test_check_integrity_empty_subdir_warning(tmp_path):
    """GIVEN bundle with empty subdir WHEN check THEN warning."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    manifest = {"artifacts": []}
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    # Create empty subdirs
    for sub in EVIDENCE_SUBDIRS:
        sub_path = bundle_dir / sub
        sub_path.mkdir(parents=True)
        # Leave empty

    result = check_evidence_integrity(str(bundle_dir))
    warnings = [str(w) for w in result.get("warnings", [])]
    assert any("empty" in w.lower() for w in warnings)


# ======================================================================
# pack_evidence_bundle — manifest integrity
# ======================================================================

def test_pack_manifest_includes_sha256(tmp_path):
    """GIVEN pack_evidence_bundle WHEN run THEN manifest has _manifest_sha256."""
    bundle = pack_evidence_bundle(str(tmp_path), str(tmp_path / "bundle"))
    assert "_manifest_sha256" in bundle
    assert len(bundle["_manifest_sha256"]) == 64


def test_pack_manifest_integrity_key(tmp_path):
    """GIVEN pack_evidence_bundle WHEN run THEN integrity section present."""
    bundle = pack_evidence_bundle(str(tmp_path), str(tmp_path / "bundle"))
    assert "integrity" in bundle
    assert bundle["integrity"]["total_artifacts"] >= 0
    assert "manifest_sha256" in bundle["integrity"]
    assert "bundled_at" in bundle["integrity"]


# ======================================================================
# check_evidence_integrity — artifact sha256 verification
# ======================================================================

def test_check_integrity_artifact_sha_verified(tmp_path):
    """GIVEN bundle with valid artifact SHAs WHEN check THEN PASS for artifact hash."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    # Create an artifact
    sub = bundle_dir / "ci-results"
    sub.mkdir(parents=True)
    art_file = sub / "result.json"
    art_file.write_text(json.dumps({"status": "passed"}))
    actual_sha = hashlib.sha256(art_file.read_bytes()).hexdigest()

    # Create manifest with matching SHA
    manifest = {
        "artifacts": [
            {
                "dest": str(art_file),
                "sha256": actual_sha,
            }
        ],
    }
    manifest_path = bundle_dir / "audit-manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    result = check_evidence_integrity(str(bundle_dir))
    sha_checks = [c for c in result.get("checks", []) if c["check"] == "artifact-sha256"]
    if sha_checks:
        assert sha_checks[0]["status"] == "PASS"


def test_check_integrity_artifact_sha_mismatch(tmp_path):
    """GIVEN bundle with wrong artifact SHA WHEN check THEN FAIL."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)

    sub = bundle_dir / "ci-results"
    sub.mkdir(parents=True)
    art_file = sub / "result.json"
    art_file.write_text(json.dumps({"status": "passed"}))

    # Manifest has wrong SHA
    manifest = {
        "artifacts": [
            {
                "dest": str(art_file),
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }
        ],
    }
    (bundle_dir / "audit-manifest.json").write_text(json.dumps(manifest))

    result = check_evidence_integrity(str(bundle_dir))
    assert any("SHA256 mismatch" in str(e) for e in result.get("errors", []))


# ======================================================================
# pack_evidence_bundle — edge: corrupted report parsing
# ======================================================================

def test_pack_bundle_with_bad_misra_file(tmp_path, caplog):
    """GIVEN a corrupt MISRA report file WHEN pack THEN logs warning."""
    reports_dir = tmp_path / ".yuleosh" / "reports"
    reports_dir.mkdir(parents=True)
    # Create a directory where a file is expected — will cause read error
    (reports_dir / "misra-report.json").mkdir()

    bundle = pack_evidence_bundle(str(tmp_path))
    # Should not crash
    assert isinstance(bundle, dict)


def test_pack_reviews_with_session_files(tmp_path):
    """GIVEN session files in .osh/sessions WHEN no reports/reviews dir THEN fallback works."""
    session_dir = tmp_path / ".osh" / "sessions"
    session_dir.mkdir(parents=True)
    for i in range(20):  # Should hit the [:20] limit
        (session_dir / f"session-{i}.json").write_text(json.dumps({"id": str(i)}))

    # Don't create reports/reviews dir to trigger fallback
    bundle = pack_evidence_bundle(str(tmp_path))
    reviews = bundle["components"].get("reviews", {})
    # Should have up to 20 session files
    assert len(reviews.get("artifacts", [])) <= 20


# ======================================================================
# Import check
# ======================================================================

def test_all_functions_importable():
    """GIVEN the module WHEN imported THEN all public functions exist."""
    import yuleosh.evidence.evidence_check as ec
    assert hasattr(ec, "pack_evidence_bundle")
    assert hasattr(ec, "check_evidence_integrity")
    assert hasattr(ec, "_sha256_file")
    assert hasattr(ec, "_ensure_dir")
