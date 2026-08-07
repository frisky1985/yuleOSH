"""
Tests: compliance checker depth upgrade — empty templates no longer count.

Covers the P1 fix: existence-only checks upgraded to content checks.
An empty architecture doc, a comment-only .clang-format, or test files
without passing-run evidence must now FAIL instead of PASS.
"""

import json

from yuleosh.compliance.compliance_checker import ComplianceChecker


def _make_checker(tmp_path):
    return ComplianceChecker(str(tmp_path))


def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── _file_has_content ──────────────────────────────────────────────────

def test_file_has_content_substantive(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/x.md", "# Title\n\nReal content line one.\nReal content line two.\nReal content line three.\n")
    assert c._file_has_content("docs", "x.md") is True


def test_file_has_content_empty(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/x.md", "")
    assert c._file_has_content("docs", "x.md") is False


def test_file_has_content_only_heading(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/x.md", "# Just A Heading\n")
    assert c._file_has_content("docs", "x.md") is False


def test_file_has_content_placeholder(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/x.md", "# Spec\n\nTODO\n\nTBD\n")
    assert c._file_has_content("docs", "x.md") is False


def test_file_has_content_missing(tmp_path):
    c = _make_checker(tmp_path)
    assert c._file_has_content("docs", "nope.md") is False


# ── _has_arch_document ─────────────────────────────────────────────────

def test_arch_document_substantive(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/architecture.md",
           "# Architecture\n\nThe system is composed of the following components: "
           "the main module handles I/O, the controller module implements the "
           "control loop, and the interface layer exposes the public API.\n")
    assert c._has_arch_document() is True


def test_arch_document_empty_template_fails(tmp_path):
    """Empty architecture template must NOT count as evidence."""
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/architecture.md", "# Architecture\n")
    assert c._has_arch_document() is False


def test_arch_document_missing(tmp_path):
    c = _make_checker(tmp_path)
    assert c._has_arch_document() is False


# ── _has_code_standard ─────────────────────────────────────────────────

def test_code_standard_real_rules(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, ".clang-format", "BasedOnStyle: LLVM\nIndentWidth: 4\nColumnLimit: 100\n")
    assert c._has_code_standard() is True


def test_code_standard_comment_only_fails(tmp_path):
    """A comment-only .clang-format must NOT count as a coding standard."""
    c = _make_checker(tmp_path)
    _write(tmp_path, ".clang-format", "# This is just a comment placeholder\n")
    assert c._has_code_standard() is False


def test_code_standard_missing(tmp_path):
    c = _make_checker(tmp_path)
    assert c._has_code_standard() is False


# ── _test_suite_passes ─────────────────────────────────────────────────

def test_suite_passes_ci_json(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, ".osh/ci/layer1.json",
           json.dumps({"layer": 1, "status": "passed", "passed": 42, "failed": 0}))
    assert c._test_suite_passes() is True


def test_suite_fails_ci_json(tmp_path):
    """CI result with failed > 0 must NOT count as passing."""
    c = _make_checker(tmp_path)
    _write(tmp_path, ".osh/ci/layer1.json",
           json.dumps({"layer": 1, "status": "failed", "passed": 10, "failed": 3}))
    assert c._test_suite_passes() is False


def test_suite_passes_junit_xml(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "tests/junit.xml",
           '<testsuite tests="5" failures="0" errors="0"><testcase name="a"/></testsuite>')
    assert c._test_suite_passes() is True


def test_suite_no_evidence(tmp_path):
    c = _make_checker(tmp_path)
    assert c._test_suite_passes() is False


# ── _acceptance_matrix_nonempty ────────────────────────────────────────

def test_acceptance_matrix_content(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, ".osh/evidence/acceptance-matrix.md",
           "| REQ | Test | Status |\n"
           "|-----|------|--------|\n"
           "| REQ-1 | test_a | PASS |\n"
           "| REQ-2 | test_b | PASS |\n"
           "| REQ-3 | test_c | PASS |\n"
           "| REQ-4 | test_d | PASS |\n")
    assert c._acceptance_matrix_nonempty() is True


def test_acceptance_matrix_empty_fails(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, ".osh/evidence/acceptance-matrix.md", "# Acceptance Matrix\n")
    assert c._acceptance_matrix_nonempty() is False


def test_acceptance_matrix_missing(tmp_path):
    c = _make_checker(tmp_path)
    assert c._acceptance_matrix_nonempty() is False


# ── integration: empty template now FAILS the BP check ─────────────────

def test_architecture_check_rejects_empty_template(tmp_path):
    """End-to-end: an empty architecture doc must make the architecture
    BP check FAIL (not silently pass as before)."""
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/architecture.md", "# Architecture\n")
    check_item = "architecture design exists"
    status = c._check_bp(
        {"id": "SWE.2.BP1", "title": "Architecture", "check": [check_item], "output_evidence": []},
        "SWE.2",
    )
    # failed > 0 → status is ❌ (not ✅)
    assert status["status"] == "❌"


def test_architecture_check_passes_with_content(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "docs/architecture.md",
           "# Architecture\n\nThe system has a main controller component, "
           "an interface layer, and a communication module architecture.\n"
           "Each component is documented with its responsibilities.\n")
    status = c._check_bp(
        {"id": "SWE.2.BP1", "title": "Architecture", "check": ["architecture design"], "output_evidence": []},
        "SWE.2",
    )
    assert status["status"] == "✅"


def test_test_check_rejects_no_pass_evidence(tmp_path):
    """End-to-end: test files without passing-run evidence must FAIL
    (previously any test file passed the check)."""
    c = _make_checker(tmp_path)
    _write(tmp_path, "tests/test_foo.py", "def test_x():\n    assert True\n")
    status = c._check_bp(
        {"id": "SWE.4.BP1", "title": "Unit Verification", "check": ["unit test"], "output_evidence": []},
        "SWE.4",
    )
    assert status["status"] == "❌"


def test_test_check_passes_with_evidence(tmp_path):
    c = _make_checker(tmp_path)
    _write(tmp_path, "tests/test_foo.py", "def test_x():\n    assert True\n")
    _write(tmp_path, ".osh/ci/layer1.json",
           json.dumps({"status": "passed", "passed": 1, "failed": 0}))
    status = c._check_bp(
        {"id": "SWE.4.BP1", "title": "Unit Verification", "check": ["unit test"], "output_evidence": []},
        "SWE.4",
    )
    assert status["status"] == "✅"
