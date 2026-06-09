"""Edge case tests for evidence engine — parse errors, no files, coverage modes, acceptance matrix format.

Covers: _parse_covers_from_file syntax errors, _collect_test_coverage no markers message,
        _check_traceability_completeness printing, collect_requirements spec not found,
        collect_reviews with/without dirs, collect_ci_results, generate_acceptance_matrix
        summary lines, pack_compliance_zip additional files, generate_code_coverage_report
        no coverage, aggregate_review_logs, generate_traceability_matrix review records.
"""

import os
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "evidence"))

from pack import EvidenceCollector


# ===================================================================
# _parse_covers_from_file — syntax error & fallback
# ===================================================================

def test_parse_covers_syntax_error_fallback():
    """Test fallback to line-comment Covers: when AST parse fails."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = os.path.join(tmp, "tests")
        os.makedirs(test_dir, exist_ok=True)
        # Intentionally invalid Python — AST.parse will fail
        path = os.path.join(test_dir, "test_broken.py")
        with open(path, "w") as f:
            f.write('# Covers: broken-module, partial\n')
            f.write('def test_\n')  # Syntax error
        keywords = c._parse_covers_from_file(path)
        assert "broken-module" in keywords
        assert "partial" in keywords


def test_parse_covers_file_not_readable():
    """Test _parse_covers_from_file handles OSError gracefully."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        path = os.path.join(tmp, "nonexistent.py")
        keywords = c._parse_covers_from_file(path)
        assert keywords == []


# ===================================================================
# _collect_test_coverage — no markers message
# ===================================================================

def test_collect_coverage_no_markers_message():
    """Test _collect_test_coverage prints warning when no Covers: markers found."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        (test_dir / "test_plain.py").write_text('"""No markers here."""\ndef test_x():\n    pass\n')
        coverage = c._collect_test_coverage()
        assert coverage == {}


# ===================================================================
# collect_requirements — spec not found
# ===================================================================

def test_collect_requirements_no_spec():
    """Test collect_requirements handles missing spec file."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.collect_requirements(spec_path=os.path.join(tmp, "nonexistent.md"))
        assert c.requirements == []
        assert c.scenarios == []


# ===================================================================
# collect_reviews — empty / with data
# ===================================================================

def test_collect_reviews_empty():
    """Test collect_reviews with no review directory."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.collect_reviews()
        assert c.reviews == []


def test_collect_reviews_with_data():
    """Test collect_reviews reads review session files."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        # Create review session file
        rev_dir = Path(tmp) / ".osh" / "reviews" / "task-1"
        rev_dir.mkdir(parents=True)
        with open(rev_dir / "review-session.json", "w") as f:
            json.dump({"task": "task-1", "decision": "passed"}, f)
        c.collect_reviews()
        assert len(c.reviews) == 1
        assert c.reviews[0]["task"] == "task-1"


# ===================================================================
# collect_ci_results — empty / with data
# ===================================================================

def test_collect_ci_results_empty():
    """Test collect_ci_results with no CI directory."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.collect_ci_results()
        assert c.ci_results == []
        assert c.coverage_data is None


def test_collect_ci_results_with_data():
    """Test collect_ci_results reads CI layer files."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        ci_dir = Path(tmp) / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        with open(ci_dir / "layer1.json", "w") as f:
            json.dump({
                "layer": 1,
                "status": "passed",
                "coverage": {"line_coverage": 75, "threshold_line": 80, "line_pass": False},
            }, f)
        c.collect_ci_results()
        assert len(c.ci_results) == 1
        assert c.coverage_data is not None
        assert c.coverage_data["line_coverage"] == 75


# ===================================================================
# generate_code_coverage_report — no coverage data
# ===================================================================

def test_code_coverage_report_no_data():
    """Test generate_code_coverage_report when no coverage data available."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.coverage_data = None
        path = c.generate_code_coverage_report()
        assert os.path.exists(path)
        content = open(path).read()
        assert "No coverage data" in content


# ===================================================================
# aggregate_review_logs — empty / with data
# ===================================================================

def test_aggregate_review_logs_empty():
    """Test aggregate_review_logs with no review data."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.reviews = []
        path = c.aggregate_review_logs()
        assert os.path.exists(path)
        # Also check JSON
        json_path = Path(tmp) / ".osh" / "evidence" / "review-log.json"
        assert json_path.exists()


def test_aggregate_review_logs_with_data():
    """Test aggregate_review_logs renders review data."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.reviews = [{
            "task": "task-1",
            "decision": "passed",
            "created_at": "2024-01-01",
            "reviews": [
                {"reviewer": "arch", "status": "passed",
                 "finding_breakdown": {"critical": 0, "major": 0, "minor": 1},
                 "summary": "OK"},
            ],
        }]
        path = c.aggregate_review_logs()
        content = open(path).read()
        assert "task-1" in content
        assert "passed" in content
        assert "arch" in content


# ===================================================================
# generate_acceptance_matrix — format & summary
# ===================================================================

def test_acceptance_matrix_empty_requirements():
    """Test acceptance matrix with no requirements."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        path = c.generate_acceptance_matrix()
        content = open(path).read()
        assert "Acceptance Matrix" in content
        assert "Summary" in content
        assert "Total SHALL" in content


def test_acceptance_matrix_correct_line_format():
    """Test acceptance matrix rows use proper markdown table format."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{
            "name": "Test Req",
            "shall": ["The system SHALL do X"],
            "shall_count": 1,
            "req_id": "RS-001",
        }]
        path = c.generate_acceptance_matrix()
        content = open(path).read()
        lines = content.split("\n")
        # Find table rows
        table_rows = [l for l in lines if l.startswith("|")]
        # header, separator, 1 data row = 3; summary is not in table format
        assert len(table_rows) >= 3
        data_rows = [l for l in table_rows if l.startswith("| RS-001")]
        assert len(data_rows) == 1
        # Updated to 8-column format with 匹配方式 and 置信度
        assert "| RS-001 | Test Req | The system SHALL do X | Unit Test | — |" in data_rows[0]
        assert "| ❌ |" in data_rows[0]


# ===================================================================
# generate_traceability_matrix — review records in matrix
# ===================================================================

def test_traceability_matrix_with_reviews():
    """Test traceability matrix includes review records."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{
            "name": "Agent Pipeline",
            "shall": ["The system SHALL support pipeline"],
            "shall_count": 1,
            "req_id": "RS-001",
        }]
        c.reviews = [{
            "task": "Agent Pipeline",
            "decision": "passed",
            "reviews": [{"reviewer": "arch", "status": "passed"}],
        }]
        c.scenarios = []
        path = c.generate_traceability_matrix()
        content = open(path).read()
        # Should mention the review
        assert "Review" in content or "passed" in content


# ===================================================================
# pack_compliance_zip — additional files
# ===================================================================

def test_compliance_pack_with_spec_and_startup():
    """Test pack_compliance_zip includes spec and startup analysis if present."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{"name": "R1", "shall_count": 1, "reason": ""}]
        c.generate_traceability_matrix()

        # Create docs files
        docs_dir = Path(tmp) / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "spec.md").write_text("# Spec")
        (docs_dir / "startup-analysis.md").write_text("# Startup")

        zip_path = c.pack_compliance_zip()
        assert os.path.exists(zip_path)
        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "spec.md" in names
            assert "startup-analysis.md" in names


# ===================================================================
# EvidenceCollector Init edge case
# ===================================================================

def test_collector_init_creates_evidence_dir():
    """Test EvidenceCollector.__init__ creates evidence directory."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        assert c.evidence_dir.exists()
        assert c.evidence_dir.name == "evidence"


def test_generate_traceability_matrix_summary_lines():
    """Test traceability matrix summary section format."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{
            "name": "Req A",
            "shall": ["SHALL do thing"],
            "shall_count": 1,
            "req_id": "RS-A",
        }]
        c.scenarios = []
        path = c.generate_traceability_matrix()
        content = open(path).read()
        assert "## Summary" in content
        assert "Total Requirements" in content
        assert "SHALL" in content


# ===================================================================
# generate_requirement_coverage edge case
# ===================================================================

def test_requirement_coverage_empty():
    """Test requirement coverage with no requirements."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = []
        path = c.generate_requirement_coverage()
        assert os.path.exists(path)


# ===================================================================
# Scenario-Ref parsing & two-level matching (P0 I3)
# ===================================================================

def test_parse_scenario_refs_from_docstring():
    """Parse Scenario-Ref from module-level docstring."""
    text = '''"""Test module.

Scenario-Ref: SDD → DDD → TDD 全流程
Covers: pipeline, SDD
"""
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert "SDD → DDD → TDD 全流程" in refs
    assert len(refs) == 1


def test_parse_scenario_refs_inline_covers():
    """Parse Scenario-Ref inline on a Covers: line."""
    text = '''"""Test module.

Covers: pipeline, SDD, Scenario-Ref: CI/CD 三层验证
"""
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert "CI/CD 三层验证" in refs


def test_parse_scenario_refs_multiple():
    """Parse multiple Scenario-Ref entries."""
    text = '''"""Test module.

Scenario-Ref: SDD → DDD → TDD 全流程
Scenario-Ref: CI/CD 三层验证
Covers: pipeline
"""
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert "SDD → DDD → TDD 全流程" in refs
    assert "CI/CD 三层验证" in refs
    assert len(refs) == 2


def test_parse_scenario_refs_deduplicate():
    """Parse Scenario-Ref: deduplicates identical refs."""
    text = '''"""
Scenario-Ref: SIL 仿真测试
Scenario-Ref: SIL 仿真测试
"""
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert refs == ["SIL 仿真测试"]


def test_parse_scenario_refs_from_comment():
    """Parse Scenario-Ref from # comment lines."""
    text = '''# Covers: pipeline, Scenario-Ref: SDD → DDD → TDD 全流程
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert "SDD → DDD → TDD 全流程" in refs


def test_parse_scenario_refs_no_ref():
    """Parse Scenario-Ref returns empty when no refs present."""
    text = '''"""Test module.

Covers: pipeline, SDD
"""
def test_x():
    assert True
'''
    refs = EvidenceCollector._parse_scenario_refs(text)
    assert refs == []


def test_collect_scenario_refs_from_file():
    """End-to-end: collect Scenario-Ref from a real test file."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        path = test_dir / "test_with_ref.py"
        path.write_text('''"""Test module with Scenario-Ref.

Scenario-Ref: CI/CD 三层验证
Covers: pipeline, SDD
"""

def test_pipeline():
    """Covers: agent, orchestration, Scenario-Ref: SDD → DDD → TDD 全流程"""
    assert True
''')
        refs = c._collect_scenario_refs_from_file(str(path))
        assert "CI/CD 三层验证" in refs
        assert "SDD → DDD → TDD 全流程" in refs
        assert len(refs) >= 2


def test_scenario_ref_exact_match_mode():
    """Priority 1: Scenario-Ref exact match yields mode='exact' with confidence=1.0."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        # Test file with explicit Scenario-Ref pointing to a scenario
        tf = test_dir / "test_exact.py"
        tf.write_text('''"""Test module.

Scenario-Ref: Agent Pipeline 全流程验证
Covers: pipeline
"""
def test_thing():
    assert True
''')
        # Scenario that matches the ref AND contains requirement name as substring
        c.scenarios = [{"name": "Agent Pipeline 全流程验证", "given": ["a"], "when": ["b"], "then": ["c"]}]
        # Requirement name is a substring of scenario name
        c.requirements = [{
            "name": "Agent Pipeline",
            "shall": ["The system SHALL support pipeline"],
            "shall_count": 1,
            "req_id": "RS-001",
        }]

        c._collect_test_coverage()
        c._build_requirement_to_test_map()

        # Check match mode
        mode = c.match_modes.get("Agent Pipeline", {}).get("test_exact.py", "none")
        conf = c.match_confidences.get("Agent Pipeline", {}).get("test_exact.py", 0.0)
        assert mode == "exact", f"Expected 'exact', got '{mode}'"
        assert conf == 1.0, f"Expected 1.0, got {conf}"


def test_scenario_ref_keyword_fallback_mode():
    """Priority 2: Keyword match yields mode='keyword' with partial confidence."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        # Test file with Covers keywords but NO Scenario-Ref
        tf = test_dir / "test_keyword.py"
        tf.write_text('''"""Covers: pipeline, SDD"""
def test_thing():
    assert True
''')
        c.requirements = [{
            "name": "Agent Pipeline",
            "shall": [
                "The system SHALL support an SDD pipeline",
                "The system SHALL route tasks through agent orchestration",
                "The system SHALL enforce CI blocking logic",
            ],
            "shall_count": 3,
            "req_id": "RS-001",
        }]
        c.scenarios = []

        c._collect_test_coverage()
        c._build_requirement_to_test_map()

        mode = c.match_modes.get("Agent Pipeline", {}).get("test_keyword.py", "none")
        conf = c.match_confidences.get("Agent Pipeline", {}).get("test_keyword.py", 0.0)
        assert mode == "keyword", f"Expected 'keyword', got '{mode}'"
        assert 0.0 < conf < 1.0, f"Expected partial confidence, got {conf}"


def test_scenario_ref_strips_from_covers_keywords():
    """Scenario-Ref on Covers line is stripped from Covers keywords."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        tf = test_dir / "test_strip.py"
        tf.write_text('''"""Covers: pipeline, SDD, Scenario-Ref: CI/CD 三层验证"""
def test_x():
    assert True
''')
        coverage = c._collect_test_coverage()
        kws = coverage.get("test_strip.py", [])
        assert "pipeline" in kws
        assert "SDD" in kws
        # Scenario-Ref should NOT be in Covers keywords
        ref_values = [k for k in kws if "CI/CD" in k or "Scenario-Ref" in k]
        assert len(ref_values) == 0, f"Scenario-Ref leaked into keywords: {ref_values}"


def test_traceability_matrix_shows_match_mode():
    """Traceability matrix includes match mode (exact/keyword) and confidence."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        test_dir = Path(tmp) / "tests"
        test_dir.mkdir()
        tf = test_dir / "test_ref.py"
        tf.write_text('''"""Scenario-Ref: Agent Pipeline 全流程验证
Covers: pipeline"""
def test_x():
    assert True
''')
        c.scenarios = [{"name": "Agent Pipeline 全流程验证", "given": ["a"], "when": ["b"], "then": ["c"]}]
        c.requirements = [{
            "name": "Agent Pipeline",
            "shall": ["The system SHALL support pipeline"],
            "shall_count": 1,
            "req_id": "RS-001",
        }]

        path = c.generate_traceability_matrix()
        content = open(path).read()
        # Should show match mode and confidence
        assert "exact" in content, f"Matrix should show 'exact' match mode, got:\n{content}"
        assert "confidence" in content.lower(), f"Matrix should show confidence, got:\n{content}"


def test_acceptance_matrix_shows_match_columns():
    """Acceptance matrix includes 匹配方式和置信度 columns."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{
            "name": "Test Req",
            "shall": ["The system SHALL do X"],
            "shall_count": 1,
            "req_id": "RS-001",
        }]
        c.scenarios = []
        path = c.generate_acceptance_matrix()
        content = open(path).read()
        assert "匹配方式" in content, "Acceptance matrix should have 匹配方式 column"
        assert "置信度" in content, "Acceptance matrix should have 置信度 column"
