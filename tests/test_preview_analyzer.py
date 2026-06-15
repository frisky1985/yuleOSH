#!/usr/bin/env python3
"""
Tests for yuleOSH AI Preview Analyzer enhancements (v2).
Covers: language detection, documentation quality, effort estimation,
maturity rating, per-file complexity, nesting depth, and new risk checks.
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ═════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════


@pytest.fixture
def simple_c_project(tmp_path: Path) -> Path:
    """Create a minimal C source directory."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "main.c").write_text(
        "#include <stdio.h>\n"
        "#include \"hal/gpio.h\"\n"
        "int main(void) {\n"
        "    gpio_init();\n"
        "    return 0;\n"
        "}\n"
    )
    hal = src / "hal"
    hal.mkdir()
    (hal / "gpio.h").write_text(
        "#ifndef GPIO_H\n#define GPIO_H\nvoid gpio_init(void);\n#endif\n"
    )
    (hal / "gpio.c").write_text(
        "#include \"gpio.h\"\n"
        "#include <stdlib.h>\n"
        "void gpio_init(void) {\n"
        "    void *p = malloc(16);\n"
        "    volatile int x = 0;\n"
        "    for (int i = 0; i < 10; i++) x++;\n"
        "    free(p);\n"
        "}\n"
    )
    # spec.md for maturity
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text(
        "# Spec\nREQ-001 SHALL do something.\n"
    )
    # readme for doc quality
    (tmp_path / "README.md").write_text(
        "# My Project\nThis is a test project.\n\n## Usage\nRun main.\n"
    )
    return tmp_path


@pytest.fixture
def mixed_lang_project(tmp_path: Path) -> Path:
    """Project with multiple languages."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (tmp_path / "src" / "module.py").write_text("def hello():\n    print('hello')\n")
    (tmp_path / "src" / "util.ts").write_text("export function add(a: number, b: number): number { return a + b; }\n")
    (tmp_path / "src" / "index.js").write_text("const x = 1;\n")
    return tmp_path


@pytest.fixture
def well_tested_project(tmp_path: Path) -> Path:
    """Project with good test infrastructure."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.c").write_text(
        "/**\n * Main module\n * Implements system init\n */\n"
        "#include <assert.h>\n"
        "int main(void) {\n"
        "    assert(1 == 1);\n"
        "    int x = 0;\n"
        "    if (x > 0) {\n"
        "        if (x > 1) {\n"
        "            if (x > 2) {\n"
        "                return 3;\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
        "void helper(void) {\n"
        "    // do something\n"
        "    volatile int a = 1;\n"
        "    while (1) { a++; }\n"
        "}\n"
    )
    test_src = tmp_path / "tests"
    test_src.mkdir()
    (test_src / "test_main.c").write_text(
        "#include \"unity.h\"\n"
        "void setUp(void) {}\n"
        "void tearDown(void) {}\n"
        "void test_main(void) {\n"
        "    TEST_ASSERT_EQUAL(1, 1);\n"
        "}\n"
    )
    (test_src / "test_gpio.c").write_text("// empty test\n")
    (tmp_path / "README.md").write_text(
        "# Project\n\n## Getting Started\n\n## API\n\n## Contributing\n\n## License\n"
    )
    return tmp_path


# ═════════════════════════════════════════════════════════════════════════
# Language detection tests
# ═════════════════════════════════════════════════════════════════════════


class TestLanguageDetection:

    def test_detect_multi_language(self, mixed_lang_project):
        """Detects C, Python, TypeScript, JavaScript."""
        from yuleosh.preview.analyzer import _detect_languages, _discover_files

        all_files, *_ = _discover_files(mixed_lang_project)
        result = _detect_languages(all_files, mixed_lang_project)

        assert "distribution" in result
        dist = result["distribution"]
        langs = list(dist.keys())
        assert any("C" in l for l in langs), f"Expected C, got {langs}"
        assert any("Python" in l for l in langs), f"Expected Python, got {langs}"
        assert any("TypeScript" in l or "JavaScript" in l for l in langs)

    def test_primary_language_c(self, simple_c_project):
        """C is detected as primary language for C project."""
        from yuleosh.preview.analyzer import _detect_languages, _discover_files

        all_files, *_ = _discover_files(simple_c_project)
        result = _detect_languages(all_files, simple_c_project)
        dist = result["distribution"]
        # C + C Header combined should exceed other languages
        c_count = dist.get("C", {}).get("file_count", 0)
        h_count = dist.get("C Header", {}).get("file_count", 0)
        c_total = c_count + h_count
        others_total = sum(
            v["file_count"] for k, v in dist.items()
            if k not in ("C", "C Header")
        )
        assert c_total >= others_total, (
            f"C/C++ files ({c_total}) should >= other languages ({others_total})"
        )

    def test_language_percentage_consistency(self, mixed_lang_project):
        """Language percentages sum to ~100%."""
        from yuleosh.preview.analyzer import _detect_languages, _discover_files

        all_files, *_ = _discover_files(mixed_lang_project)
        result = _detect_languages(all_files, mixed_lang_project)

        total_pct = sum(v["percentage"] for v in result["distribution"].values())
        assert abs(total_pct - 100.0) < 1.0, f"Percentages should sum to ~100, got {total_pct}"


# ═════════════════════════════════════════════════════════════════════════
# Documentation quality tests
# ═════════════════════════════════════════════════════════════════════════


class TestDocumentationQuality:

    def test_detect_readme(self, simple_c_project):
        """README.md is detected."""
        from yuleosh.preview.analyzer import _assess_documentation

        result = _assess_documentation(simple_c_project)
        assert result["has_readme"] is True
        assert result["readme_quality"] > 0

    def test_no_readme(self, tmp_path: Path):
        """Missing README is detected."""
        from yuleosh.preview.analyzer import _assess_documentation

        result = _assess_documentation(tmp_path)
        assert result["has_readme"] is False
        assert result["readme_quality"] == 0

    def test_comment_ratio(self, simple_c_project):
        """Comment-to-code ratio computed correctly."""
        from yuleosh.preview.analyzer import _assess_documentation

        result = _assess_documentation(simple_c_project)
        assert result["comment_to_code_ratio"] >= 0
        assert result["comment_to_code_ratio"] <= 1.0
        assert "doc_score" in result

    def test_spec_detection(self, simple_c_project):
        """spec.md presence is detected."""
        from yuleosh.preview.analyzer import _assess_documentation

        result = _assess_documentation(simple_c_project)
        assert result["has_spec"] is True, "spec.md should be detected"

    def test_doc_score_range(self, simple_c_project):
        """Doc score is 0-100."""
        from yuleosh.preview.analyzer import _assess_documentation

        result = _assess_documentation(simple_c_project)
        assert 0 <= result["doc_score"] <= 100


# ═════════════════════════════════════════════════════════════════════════
# Effort estimation tests
# ═════════════════════════════════════════════════════════════════════════


class TestEffortEstimation:

    def test_effort_positive(self, simple_c_project):
        """Effort estimation produces positive values."""
        from yuleosh.preview.analyzer import _estimate_effort, _discover_files, _measure_complexity, _scan_frameworks

        all_files, *_ = _discover_files(simple_c_project)
        complexity = _measure_complexity(simple_c_project)
        frameworks = _scan_frameworks(simple_c_project)

        result = _estimate_effort(all_files, frameworks, complexity)
        assert result["estimated_person_hours"] > 0
        assert result["source_lines_of_code"] > 0
        assert result["complexity_multiplier"] >= 1.0

    def test_effort_fields(self, simple_c_project):
        """Effort result has all required fields."""
        from yuleosh.preview.analyzer import _estimate_effort, _discover_files, _measure_complexity, _scan_frameworks

        all_files, *_ = _discover_files(simple_c_project)
        complexity = _measure_complexity(simple_c_project)
        frameworks = _scan_frameworks(simple_c_project)

        result = _estimate_effort(all_files, frameworks, complexity)
        assert "estimated_person_hours" in result
        assert "source_lines_of_code" in result
        assert "lines_per_hour_assumption" in result
        assert result["lines_per_hour_assumption"] == 50


# ═════════════════════════════════════════════════════════════════════════
# Maturity rating tests
# ═════════════════════════════════════════════════════════════════════════


class TestMaturityRating:

    def test_maturity_fields(self, simple_c_project):
        """Maturity rating has all required fields."""
        from yuleosh.preview.analyzer import (_assess_documentation, _compute_maturity,
                                                _discover_files, _measure_complexity,
                                                _predict_coverage, _scan_frameworks)

        result = _compute_maturity(
            test_framework="Unity",
            test_density=0.5,
            test_file_count=2,
            complexity=_measure_complexity(simple_c_project),
            doc_quality=_assess_documentation(simple_c_project),
            frameworks=[],
            coverage=_predict_coverage(0.5, "Unity", 10),
        )
        assert "score" in result
        assert "rating" in result
        assert "test_maturity_score" in result
        assert "documentation_score" in result
        assert 0 <= result["score"] <= 100

    def test_no_tests_low_maturity(self, tmp_path: Path):
        """Project without tests gets low maturity."""
        from yuleosh.preview.analyzer import (_assess_documentation, _compute_maturity,
                                                _measure_complexity, _predict_coverage)

        result = _compute_maturity(
            test_framework="none",
            test_density=0.0,
            test_file_count=0,
            complexity=_measure_complexity(tmp_path),
            doc_quality=_assess_documentation(tmp_path),
            frameworks=[],
            coverage=_predict_coverage(0.0, "none", 0),
        )
        assert result["score"] < 40

    def test_well_tested_high_maturity(self, well_tested_project):
        """Well-tested project gets higher maturity."""
        from yuleosh.preview.analyzer import (_assess_documentation, _compute_maturity,
                                                _measure_complexity, _predict_coverage,
                                                _scan_frameworks, _detect_test_framework,
                                                _discover_files)

        all_files, src, hdr, test_files, cfg = _discover_files(well_tested_project)
        det = _detect_test_framework(well_tested_project)
        complexity = _measure_complexity(well_tested_project)
        doc = _assess_documentation(well_tested_project)
        fw = _scan_frameworks(well_tested_project)
        cv = _predict_coverage(len(test_files) / max(len(src), 1), det, complexity.get("avg_lines_per_function", 0))

        result = _compute_maturity(
            test_framework=det,
            test_density=len(test_files) / max(len(src), 1),
            test_file_count=len(test_files),
            complexity=complexity,
            doc_quality=doc,
            frameworks=fw,
            coverage=cv,
        )
        assert result["score"] >= 30


# ═════════════════════════════════════════════════════════════════════════
# Per-file complexity tests
# ═════════════════════════════════════════════════════════════════════════


class TestPerFileComplexity:

    def test_per_file_metrics(self, simple_c_project):
        """Per-file complexity returns structured data."""
        from yuleosh.preview.analyzer import _measure_per_file_complexity

        result = _measure_per_file_complexity(simple_c_project)
        assert len(result) > 0

        entry = result[0]
        assert "file" in entry
        assert "total_lines" in entry
        assert "code_lines" in entry
        assert "function_count" in entry
        assert "malloc_count" in entry
        assert "free_count" in entry

    def test_sorted_by_complexity(self, simple_c_project):
        """Per-file results sorted by most code lines first."""
        from yuleosh.preview.analyzer import _measure_per_file_complexity

        result = _measure_per_file_complexity(simple_c_project)
        for i in range(len(result) - 1):
            assert result[i]["code_lines"] >= result[i + 1]["code_lines"]


# ═════════════════════════════════════════════════════════════════════════
# Nesting depth tests
# ═════════════════════════════════════════════════════════════════════════


class TestNestingDepth:

    def test_max_nesting_detected(self, well_tested_project):
        """Nesting depth is measured."""
        from yuleosh.preview.analyzer import _measure_max_nesting

        depth = _measure_max_nesting(well_tested_project)
        assert depth > 0, f"Expected nesting depth >0, got {depth}"

    def test_no_nesting(self, simple_c_project):
        """Project with no nesting depth still returns valid value."""
        from yuleosh.preview.analyzer import _measure_max_nesting

        depth = _measure_max_nesting(simple_c_project)
        assert depth >= 0
        assert isinstance(depth, int)


# ═════════════════════════════════════════════════════════════════════════
# File discovery tests
# ═════════════════════════════════════════════════════════════════════════


class TestFileDiscovery:

    def test_discover_supports_cpp(self, tmp_path: Path):
        """C++ files (.cpp, .hpp) are discovered."""
        from yuleosh.preview.analyzer import _discover_files

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.cpp").write_text("int main() { return 0; }\n")
        (tmp_path / "src" / "module.hpp").write_text("#pragma once\n")

        all_files, source_files, header_files, *_ = _discover_files(tmp_path)
        assert any(f.endswith(".cpp") for f in source_files)
        assert any(f.endswith(".hpp") for f in header_files)

    def test_discover_supports_new_configs(self, tmp_path: Path):
        """JSON, TOML, INI, SVG, CSS are discovered as config/other files."""
        from yuleosh.preview.analyzer import _discover_files

        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "config.toml").write_text("[tool]")
        (tmp_path / "config.ini").write_text("[section]")

        all_files, *_ = _discover_files(tmp_path)
        found_exts = {f.suffix.lower() for f in all_files}
        assert ".json" in found_exts
        assert ".toml" in found_exts
        assert ".ini" in found_exts

    def test_hidden_files_skipped(self, tmp_path: Path):
        """Dotfiles are skipped."""
        from yuleosh.preview.analyzer import _discover_files

        (tmp_path / ".secret.c").write_text("int main() { return 0; }\n")
        (tmp_path / "public.c").write_text("int main() { return 0; }\n")

        all_files, *_ = _discover_files(tmp_path)
        # Only public.c should be discovered (hidden .secret.c skipped)
        found_names = [f.name for f in all_files]
        assert ".secret.c" not in found_names


# ═════════════════════════════════════════════════════════════════════════
# New risk checks
# ═════════════════════════════════════════════════════════════════════════


class TestNewRisks:

    def test_high_function_count_risk(self, tmp_path: Path):
        """Many functions trigger a modularization recommendation."""
        from yuleosh.preview.analyzer import _scan_risks

        src = tmp_path / "src"
        src.mkdir()

        # Generate many small functions
        content = ""
        for i in range(120):
            content += f"int func_{i}(void) {{ return {i}; }}\n"
        (src / "busy.c").write_text(content)

        complexity = {
            "total_functions": 120,
            "total_function_lines": 120,
            "avg_lines_per_function": 1.0,
            "max_function_lines": 2,
        }
        risks = _scan_risks(tmp_path, complexity)
        func_risks = [r for r in risks if "Large number of functions" in r["description"]]
        assert len(func_risks) > 0, "Expected high function count risk"

    def test_nesting_depth_risk(self, tmp_path: Path):
        """Deep nesting triggers a refactoring recommendation."""
        from yuleosh.preview.analyzer import _scan_risks

        src = tmp_path / "src"
        src.mkdir()

        # Create deeply nested code
        content = "int main(void) {\n"
        for i in range(7):
            content += "    " * (i + 1) + "if (x > " + str(i) + ") {\n"
        for i in range(7):
            content += "    " * (7 - i) + "}\n"
        content += "    return 0;\n}\n"
        (src / "deep.c").write_text(content)

        complexity = {
            "total_functions": 1,
            "total_function_lines": 20,
            "avg_lines_per_function": 20.0,
            "max_function_lines": 20,
            "max_nesting_depth": 7,
        }
        risks = _scan_risks(tmp_path, complexity)
        nesting_risks = [r for r in risks if "Deep nesting" in r["description"]]
        assert len(nesting_risks) > 0, "Expected nesting depth risk"

    def test_comment_deficiency_risk(self, tmp_path: Path):
        """Low comment ratio triggers a documentation risk."""
        from yuleosh.preview.analyzer import _scan_risks

        src = tmp_path / "src"
        src.mkdir()

        # Many lines of code with no comments
        content = "\n".join([f"int x{i} = {i};" for i in range(200)])
        (src / "nocomment.c").write_text(content)

        complexity = {
            "total_functions": 0,
            "total_function_lines": 0,
            "avg_lines_per_function": 0,
            "max_function_lines": 0,
        }
        risks = _scan_risks(tmp_path, complexity)
        comment_risks = [r for r in risks if "comment" in r["description"].lower()]
        assert len(comment_risks) > 0, "Expected comment deficiency risk"


# ═════════════════════════════════════════════════════════════════════════
# Full analysis integration test
# ═════════════════════════════════════════════════════════════════════════


class TestFullAnalysis:

    def test_analyze_returns_new_fields(self, simple_c_project):
        """analysis includes all new v2 fields."""
        from yuleosh.preview.analyzer import analyze_directory

        result = analyze_directory(simple_c_project)

        # Core (v1) fields
        assert "file_summary" in result
        assert "detected_frameworks" in result
        assert "complexity" in result
        assert "test_infrastructure" in result
        assert "compliance_risks" in result
        assert "recommended_template" in result
        assert "coverage_prediction" in result

        # New (v2) fields
        assert "per_file_complexity" in result
        assert "documentation_quality" in result
        assert "estimated_effort" in result
        assert "maturity_rating" in result

        # File summary has language info
        fs = result["file_summary"]
        assert "by_language" in fs
        assert "distribution" in fs["by_language"]

        # Complexity has nesting depth
        comp = result["complexity"]
        assert "max_nesting_depth" in comp

    def test_framework_detection_new(self, simple_c_project):
        """Frameworks list includes new detections."""
        from yuleosh.preview.analyzer import _scan_frameworks

        results = _scan_frameworks(simple_c_project)
        names = [f["name"] for f in results]
        # check for existing expected frameworks
        for r in results:
            assert "name" in r
            assert "detected" in r
            assert "matched_patterns" in r
            assert "sample_files" in r


# ═════════════════════════════════════════════════════════════════════════
# Reporter enhancements
# ═════════════════════════════════════════════════════════════════════════


class TestReporterEnhancements:

    def test_report_structure_v2(self):
        """Report includes all enhanced sections."""
        from yuleosh.preview.reporter import build_assessment_report

        analysis = {
            "file_summary": {
                "total_files": 10, "total_lines": 500,
                "source_files": 5, "test_files": 2, "header_files": 2,
                "config_files": 1,
                "by_extension": {".c": 3, ".h": 2, ".py": 1},
                "by_language": {
                    "distribution": {"C": {"file_count": 3, "total_lines": 300, "percentage": 50.0}},
                    "primary_language": "C",
                },
            },
            "detected_frameworks": [{"name": "FreeRTOS", "detected": True, "matched_patterns": 2, "sample_files": ["main.c"]}],
            "complexity": {"total_functions": 10, "total_function_lines": 200,
                           "avg_lines_per_function": 20.0, "max_function_lines": 50,
                           "max_nesting_depth": 4},
            "per_file_complexity": [
                {"file": "src/main.c", "total_lines": 100, "code_lines": 80,
                 "function_count": 5, "avg_function_lines": 16, "max_function_lines": 30}
            ],
            "test_infrastructure": {"detected_framework": "Unity", "test_density": 0.4, "test_file_count": 2},
            "compliance_risks": [
                {"risk_level": "medium", "description": "Test", "occurrences": 1, "recommendation": "Fix"}
            ],
            "recommended_template": {
                "recommended_template": "freertos-misra",
                "steps": [{"name": "Spec", "rationale": "Parse"}],
                "ci_layers": {"L1": {"unit_test": True}},
                "review_gates": [{"type": "internal", "before": "code-gen"}],
                "yaml_snippet": "steps: []",
            },
            "coverage_prediction": {
                "current_coverage_estimate": 45.0, "projected_coverage_after_yuleosh": 75.0,
                "confidence": "medium", "bottleneck_files": ["main.c"],
            },
            "documentation_quality": {
                "has_readme": True, "readme_quality": 50,
                "comment_to_code_ratio": 0.12, "docstring_count": 2,
                "has_spec": True, "doc_score": 75,
            },
            "estimated_effort": {
                "estimated_person_hours": 20.5, "source_lines_of_code": 500,
                "lines_per_hour_assumption": 50, "complexity_multiplier": 1.0,
                "framework_multiplier": 1.0,
            },
            "maturity_rating": {
                "score": 65, "rating": "good",
                "test_maturity_score": 25, "documentation_score": 75,
            },
        }

        report = build_assessment_report(analysis)

        assert "project_summary" in report
        assert "coverage_prediction" in report
        assert "compliance_risks" in report
        assert "recommended_pipeline" in report

        # Check project_summary includes new fields
        ps = report["project_summary"]
        assert "primary_language" in ps
        assert "language_distribution" in ps
        assert "maturity_rating" in ps
        assert "estimated_effort_hours" in ps
    def test_report_structure_v2_enhancements(self):
        """Verify specific new fields have correct values."""
        from yuleosh.preview.reporter import build_assessment_report

        analysis = {
            "file_summary": {
                "total_files": 10, "total_lines": 500,
                "source_files": 5, "test_files": 2, "header_files": 2,
                "config_files": 1,
                "by_extension": {".c": 3, ".h": 2, ".py": 1},
                "by_language": {
                    "distribution": {"C": {"file_count": 3, "total_lines": 300, "percentage": 50.0}},
                    "primary_language": "C",
                },
            },
            "detected_frameworks": [{"name": "FreeRTOS", "detected": True, "matched_patterns": 2, "sample_files": ["main.c"]}],
            "complexity": {"total_functions": 10, "total_function_lines": 200,
                           "avg_lines_per_function": 20.0, "max_function_lines": 50,
                           "max_nesting_depth": 4},
            "per_file_complexity": [
                {"file": "src/main.c", "total_lines": 100, "code_lines": 80,
                 "function_count": 5, "avg_function_lines": 16, "max_function_lines": 30}
            ],
            "test_infrastructure": {"detected_framework": "Unity", "test_density": 0.4, "test_file_count": 2},
            "compliance_risks": [
                {"risk_level": "medium", "description": "Test", "occurrences": 1, "recommendation": "Fix"}
            ],
            "recommended_template": {
                "recommended_template": "freertos-misra",
                "steps": [{"name": "Spec", "rationale": "Parse"}],
                "ci_layers": {"L1": {"unit_test": True}},
                "review_gates": [{"type": "internal", "before": "code-gen"}],
                "yaml_snippet": "steps: []",
            },
            "coverage_prediction": {
                "current_coverage_estimate": 45.0, "projected_coverage_after_yuleosh": 75.0,
                "confidence": "medium", "bottleneck_files": ["main.c"],
            },
            "documentation_quality": {
                "has_readme": True, "readme_quality": 50,
                "comment_to_code_ratio": 0.12, "docstring_count": 2,
                "has_spec": True, "doc_score": 75,
            },
            "estimated_effort": {
                "estimated_person_hours": 20.5, "source_lines_of_code": 500,
                "lines_per_hour_assumption": 50, "complexity_multiplier": 1.0,
                "framework_multiplier": 1.0,
            },
            "maturity_rating": {
                "score": 65, "rating": "good",
                "test_maturity_score": 25, "documentation_score": 75,
            },
        }

        report = build_assessment_report(analysis)

        ps = report["project_summary"]
        assert ps["primary_language"] == "C"
        assert ps["maturity_rating"] == "good"
        assert ps["estimated_effort_hours"] == 20.5
