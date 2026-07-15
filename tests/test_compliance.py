"""
Tests for the yuleOSH Compliance Checker module.

Covers:
- Loading MISRA rules configuration (misra-rules.yaml)
- Loading ASPICE configuration (aspice_v3.1.yaml)
- Running compliance checks
- Mock mode checks
- Report generation (JSON + Markdown)
- Edge cases: empty project, missing files, custom templates
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
def _get_misra_report_module():
    """Lazy-load ci.misra_report with safe sys.path handling."""
    import sys as _sys
    from pathlib import Path as _Path
    _root = str(_Path(__file__).resolve().parent.parent)
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    try:
        from ci import misra_report as _mr
        return _mr
    except ImportError:
        _sys.path.insert(0, _root)  # retry
        from ci import misra_report as _mr
        return _mr





# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def misra_rules_path():
    """Path to the MISRA rules definition file."""
    path = Path(__file__).resolve().parent.parent / "misra-rules.yaml"
    if path.exists():
        return path
    pytest.skip("misra-rules.yaml not found")


@pytest.fixture
def aspice_yaml_path():
    """Path to the ASPICE v3.1 YAML definition."""
    path = Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "compliance" / "aspice_v3.1.yaml"
    if path.exists():
        return path
    pytest.skip("aspice_v3.1.yaml not found")


@pytest.fixture
def sample_project(tmp_path):
    """Create a minimal project directory for compliance testing."""
    # Create common compliance-evidence files
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "requirements.md").write_text("# Requirements\n- REQ-001: The system SHALL do X\n")
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n- Component A\n- Component B\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void) { return 0; }")
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "api.h").write_text("#ifndef API_H\n#define API_H\nvoid api_init(void);\n#endif\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_answer(): assert 1 + 1 == 2\n")
    (tmp_path / "tests" / "test_utils.py").write_text("def test_utils(): assert True\n")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "req-spec.md").write_text("# Spec\n")
    (tmp_path / ".osh" / "ci").mkdir(parents=True)
    (tmp_path / ".osh" / "ci" / "layer1-abc123.json").write_text('{"status": "passed"}')
    (tmp_path / ".osh" / "reviews").mkdir()
    (tmp_path / ".osh" / "reviews" / "review-1.md").write_text("# Review\n- Finding 1\n")
    (tmp_path / ".osh" / "evidence").mkdir()
    (tmp_path / ".osh" / "evidence" / "traceability-matrix.md").write_text("# Traceability\n")
    (tmp_path / ".clang-format").write_text("BasedOnStyle: LLVM\n")
    return tmp_path


@pytest.fixture
def empty_project(tmp_path):
    """Create an empty project directory with no compliance artifacts."""
    return tmp_path


# ===================================================================
# Test: ComplianceChecker basic instantiation
# ===================================================================




def test_compliance_checker_import():
    """Verify the ComplianceChecker class can be imported."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    assert ComplianceChecker is not None


def test_compliance_checker_instantiation(tmp_path, aspice_yaml_path):
    """Verify ComplianceChecker can be instantiated with defaults."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(tmp_path))
    assert checker.project_dir == tmp_path
    assert checker.template is not None
    assert "meta" in checker.template


def test_compliance_checker_custom_template(tmp_path, aspice_yaml_path):
    """Verify ComplianceChecker accepts a custom template path."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    assert checker.template_path == aspice_yaml_path
    assert checker.template is not None


# ===================================================================
# Test: Loading MISRA rules config
# ===================================================================


def test_load_misra_rules(misra_rules_path):
    """Verify misra-rules.yaml can be loaded and contains expected keys."""
    import yaml
    with open(misra_rules_path) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "meta" in data
    assert data["meta"]["standard"] == "MISRA C"
    assert data["meta"]["version"] == "2023-preview"

    # Check that we have rule entries (non-meta keys)
    rule_keys = [k for k in data.keys() if k != "meta"]
    assert len(rule_keys) > 20, "Should define at least 20 MISRA rules"

    # Verify a specific important rule
    assert "misra-c2023-17.7" in data
    rule = data["misra-c2023-17.7"]
    assert rule["severity"] == "required"
    assert "返回值" in rule["title"] or "return" in rule["title"].lower()


def test_load_aspice_rules(aspice_yaml_path):
    """Verify aspice_v3.1.yaml can be loaded and has expected structure."""
    import yaml
    with open(aspice_yaml_path) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "meta" in data
    assert data["meta"]["standard"] == "ASPICE"
    assert "swe.1" in data
    assert "swe.2" in data
    assert "swe.3" in data
    assert "swe.4" in data
    assert "swe.5" in data
    assert "swe.6" in data

    # Check base practices exist
    swe1 = data["swe.1"]
    assert "base_practices" in swe1
    assert len(swe1["base_practices"]) >= 2


# ===================================================================
# Test: Running compliance checks
# ===================================================================


def test_compliance_check_sample_project(sample_project, aspice_yaml_path):
    """Run compliance check on a sample project and verify results."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    report = checker.run()

    assert report["generated_at"] is not None
    assert report["standard"] == "ASPICE"
    assert report["summary"]["total_bps"] > 0

    # The sample project has docs, src, tests, evidence — should find some passes
    assert report["summary"]["passed"] > 0


def test_compliance_check_empty_project(empty_project, aspice_yaml_path):
    """Run compliance check on an empty project — should find mostly failures."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(empty_project), template_path=aspice_yaml_path)
    report = checker.run()

    assert report["summary"]["total_bps"] > 0
    # Most checks should fail for an empty project
    # But some might pass by default (evidenced-based fallbacks)
    assert report["summary"]["failed"] > 0


def test_compliance_check_file_exists_helper(tmp_path, aspice_yaml_path):
    """Test the _file_exists helper method."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    (tmp_path / "test.txt").write_text("hello")
    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    assert checker._file_exists("test.txt")
    assert not checker._file_exists("nonexistent.txt")


def test_compliance_check_has_content_matching(tmp_path, aspice_yaml_path):
    """Test the _has_content_matching helper method."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    (tmp_path / "test.txt").write_text("The system SHALL authenticate users")
    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    assert checker._has_content_matching("SHALL", "test.txt")
    assert not checker._has_content_matching("SHOULD", "test.txt")


# ===================================================================
# Test: Report generation
# ===================================================================


def test_generate_report_markdown(sample_project, aspice_yaml_path):
    """Test Markdown report generation from compliance check results."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    report = checker.run()
    markdown = checker.generate_report_markdown(report)

    assert markdown is not None
    assert "# ASPICE" in markdown
    assert "Summary" in markdown
    assert "Total Base Practices" in markdown
    assert "SWE.1" in markdown or "swe.1" in markdown


def test_run_and_save(sample_project, aspice_yaml_path):
    """Test running compliance check and saving report to file."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    output_path = checker.run_and_save()

    assert output_path is not None
    assert os.path.exists(output_path)
    content = Path(output_path).read_text()
    assert "# ASPICE" in content


# ===================================================================
# Test: Pipeline steps and orchestration integration
# ===================================================================


def test_compliance_checker_in_pipeline(tmp_path, aspice_yaml_path):
    """Simulate how compliance checker integrates with pipeline steps."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    # Create basic project structure
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "docs" / "requirements.md").write_text("# Req\n- REQ-001 SHALL work\n")
    (tmp_path / "src" / "main.c").write_text("int main(void) { return 0; }")
    (tmp_path / "tests" / "test_main.py").write_text("def test_x(): pass")

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    report = checker.run()

    # Pipeline integration would use the report as evidence
    assert report["summary"]["total_bps"] > 0
    assert "swe.1" in report["swe_sections"]
    assert "swe.3" in report["swe_sections"]


# ===================================================================
# Test: MISRA report formatter
# ===================================================================



def _load_misra_report():
    """Load yuleosh.ci.misra_report via normal import."""
    from yuleosh.ci import misra_report as _mr  # noqa: F811
    return _mr


def test_misra_report_parse_cppcheck_output():
    """Test parsing cppcheck MISRA output (supports both bracketed and legacy formats)."""
    _mr = _load_misra_report()

    sample_output = (
        "[src/main.c:42:5] (style) Operands shall not be of inappropriate type [misra-c2012-10.1]\n"
        "[src/utils.c:15:9] (warning) Return value of function must be used [misra-c2012-17.7]\n"
    )

    violations = _mr.parse_cppcheck_output(sample_output)
    assert len(violations) == 2
    assert violations[0]["file"] == "src/main.c"
    assert violations[0]["line"] == 42
    assert violations[0]["column"] == 5
    assert violations[0]["severity"] == "style"

def test_misra_report_group_by_rule():
    """Test grouping violations by rule ID."""
    _mr = _load_misra_report()

    sample = (
        "[src/a.c:10:1] (style) rule violated [misra-c2012-10.1]\n"
        "[src/b.c:20:2] (style) rule violated [misra-c2012-10.1]\n"
        "[src/a.c:30:3] (warning) rule violated [misra-c2012-17.7]\n"
    )
    violations = _mr.parse_cppcheck_output(sample)
    groups = _mr.group_by_rule(violations)

    assert "misra-c2023-10.1" in groups
    assert "misra-c2023-17.7" in groups
    assert len(groups["misra-c2023-10.1"]) == 2
    assert len(groups["misra-c2023-17.7"]) == 1

def test_misra_report_summary_stats():
    """Test computing summary statistics."""
    _mr = _load_misra_report()

    sample = (
        "[src/a.c:10:1] (style) rule X [misra-c2012-10.1]\n"
        "[src/a.c:20:2] (warning) rule Y [misra-c2012-17.7]\n"
        "[src/a.c:30:3] (style) rule X [misra-c2012-10.1]\n"
    )
    violations = _mr.parse_cppcheck_output(sample)
    groups = _mr.group_by_rule(violations)
    summary = _mr.compute_summary_stats(violations, groups)

    assert summary["total_violations"] == 3
    assert summary["unique_rules"] == 2
    assert summary["by_severity"].get("style") == 2
    assert summary["by_severity"].get("warning") == 1

def test_misra_report_enrich_with_definitions():
    """Test enriching violations with rule definitions."""
    _mr = _load_misra_report()

    violations = [{"file": "src/a.c", "line": 10, "column": 1,
                    "rule_id": "17.7", "severity": "style", "message": "test"}]
    rule_defs = {
        "misra-c2023-17.7": {
            "title": "Function return value must be used",
            "severity": "required",
            "category": "behavior",
            "description": "desc",
        },
    }

    enriched = _mr.enrich_with_definitions(violations, rule_defs)
    assert len(enriched) == 1
    assert enriched[0].get("rule_type")  # enriched with rule_type

def test_misra_report_generate_json():
    """Test JSON report generation."""
    _mr = _load_misra_report()

    violations = [{"file": "src/a.c", "line": 10, "column": 1, "severity": "style",
                    "message": "test violation", "rule_id": "10.1"}]
    groups = {"10.1": violations}

    data = _mr.generate_json_report(violations, groups)
    assert "schema_version" in data
    assert data["total_violations"] == 1

def test_misra_report_generate_markdown():
    """Test Markdown report generation."""
    _mr = _load_misra_report()

    violations = [{"file": "src/a.c", "line": 10, "column": 1, "severity": "style",
                    "message": "test msg", "rule_id": "10.1"}]
    groups = {"10.1": violations}

    # generate_json_report returns the dict expected by generate_markdown_report
    report = _mr.generate_json_report(violations, groups)
    md = _mr.generate_markdown_report(report)
    assert "MISRA" in md
    assert "10.1" in md

def test_misra_report_save(tmp_path):
    """Test saving MISRA report to disk."""
    _mr = _load_misra_report()

    violations = []
    groups = {}
    summary = {"total_violations": 0, "total_rules_violated": 0,
               "severity_counts": {}, "unique_files": [], "per_file_counts": {}}
    rule_defs = {}

    json_path, md_path, trace_path, excel_path = _mr.save_report(violations, groups, summary, rule_defs, tmp_path / "reports")
    assert json_path.exists()
    assert md_path.exists()
    assert "misra-report" in json_path.name
    assert "misra-report" in md_path.name

def test_misra_report_load_rule_definitions(misra_rules_path):
    """Test loading MISRA rule definitions from YAML file."""
    _mr = _load_misra_report()

    defs = _mr.load_rule_definitions(misra_rules_path)
    assert len(defs) > 20
    assert "misra-c2023-17.7" in defs
    assert defs["misra-c2023-17.7"]["title"] is not None

def test_compliance_checker_mock_report(tmp_path, aspice_yaml_path):
    """Verify compliance checker works with mock/minimal project."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker

    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    report = checker.run()

    # Should produce a valid report even for empty dir
    assert report["summary"]["total_bps"] > 0
    assert isinstance(report["summary"]["passed"], int)
    assert isinstance(report["summary"]["failed"], int)


# ===================================================================
# Test: Compliance module __init__
# ===================================================================


def test_compliance_module_init():
    """Test the compliance __init__ exports."""
    from yuleosh.compliance import ComplianceChecker
    assert ComplianceChecker is not None
    assert callable(ComplianceChecker)


# ===================================================================
# Test: CI config MisraConfig dataclass
# ===================================================================


def test_misra_config_dataclass():
    """Test MisraConfig dataclass default values."""
    from yuleosh.ci.config import MisraConfig
    cfg = MisraConfig()
    assert cfg.enabled is True
    assert cfg.addon == "misra"
    assert cfg.fail_on_required is True   # G-09: default True
    assert cfg.fail_on_violation is False  # G-09: default False (deprecated)
    assert cfg.fail_threshold == 10
    assert cfg.cppcheck_std == "c11"
    assert cfg.suppress_rules == []


def test_misra_config_custom_values():
    """Test MisraConfig with custom values."""
    from yuleosh.ci.config import MisraConfig
    cfg = MisraConfig(
        enabled=False,
        addon="misra-c-2023",
        fail_on_violation=True,
        fail_threshold=5,
        cppcheck_std="c99",
        suppress_rules=["17.7"],
    )
    assert cfg.enabled is False
    assert cfg.addon == "misra-c-2023"
    assert cfg.fail_on_violation is True
    assert cfg.fail_threshold == 5
    assert cfg.cppcheck_std == "c99"
    assert cfg.suppress_rules == ["17.7"]


# ===================================================================
# Test: CI Config loading with MISRA
# ===================================================================


def test_ci_config_misra_block(tmp_path):
    """Test loading CiConfig with MISRA block from YAML."""
    from yuleosh.ci.config import load_ci_config

    config_dir = tmp_path / ".yuleosh"
    config_dir.mkdir(parents=True)
    config = config_dir / "ci-config.yaml"
    config.write_text("""\
misra:
  enabled: true
  addon: misra-c-2023
  fail_on_violation: true
  fail_threshold: 5
  cppcheck_std: c11
  suppress_rules:
    - "17.7"
    - "21.3"
""")

    cfg = load_ci_config(str(tmp_path))
    assert cfg.misra.enabled is True
    assert cfg.misra.addon == "misra-c-2023"
    assert cfg.misra.fail_on_violation is True
    assert cfg.misra.fail_threshold == 5
    assert cfg.misra.cppcheck_std == "c11"
    assert "17.7" in cfg.misra.suppress_rules
    assert "21.3" in cfg.misra.suppress_rules


def test_misra_config_in_ci_config(tmp_path):
    """Verify MisraConfig is accessible from parsed CiConfig."""
    from yuleosh.ci.config import load_ci_config, MisraConfig

    config_dir = tmp_path / ".yuleosh"
    config_dir.mkdir(parents=True)
    (config_dir / "ci-config.yaml").write_text("misra:\n  enabled: false\n")

    cfg = load_ci_config(str(tmp_path))
    assert isinstance(cfg.misra, MisraConfig)
    assert cfg.misra.enabled is False


# ===================================================================
# Test: run_misra_check function signature
# ===================================================================


def test_run_misra_check_importable():
    """Verify run_misra_check is importable from stages."""
    from yuleosh.ci.stages import run_misra_check
    assert run_misra_check is not None
    assert callable(run_misra_check)


# ===================================================================
# Test: Edge cases for compliance
# ===================================================================


def test_compliance_dir_has_files(tmp_path, aspice_yaml_path):
    """Test _dir_has_files helper."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(tmp_path), template_path=aspice_yaml_path)
    assert not checker._dir_has_files("nonexistent")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "file.txt").write_text("hello")
    assert checker._dir_has_files("subdir")


def test_compliance_count_unit_tests(sample_project, aspice_yaml_path):
    """Test counting unit test files."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    count = checker._count_unit_tests()
    assert count >= 2


def test_compliance_has_traced_requirements(sample_project, aspice_yaml_path):
    """Test traceability matrix detection."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    assert checker._has_traced_requirements()


def test_compliance_ci_results_exist(sample_project, aspice_yaml_path):
    """Test CI result detection."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    assert checker._ci_results_exist()


def test_compliance_evidence_dir_exists(sample_project, aspice_yaml_path):
    """Test evidence directory detection."""
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(str(sample_project), template_path=aspice_yaml_path)
    assert checker._evidence_dir_exists()