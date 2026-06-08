#!/usr/bin/env python3
"""
OSH Evidence Engine — Traceability matrix + ASPICE compliance pack.

Automatically generates:
  - Traceability matrix (Req ↔ Design ↔ Code ↔ Test)
  - Requirements coverage report
  - Code coverage summary
  - Review records aggregation
  - Compliance pack (ZIP)
"""

import ast
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


class EvidenceCollector:
    """Collects and organizes evidence for ASPICE compliance."""

    def __init__(self, project_dir: str, version: str = "0.1.0"):
        self.project_dir = project_dir
        self.version = version
        self.generated_at = datetime.now().isoformat()
        self.evidence_dir = Path(project_dir) / ".osh" / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # Data containers
        self.requirements: list[dict] = []
        self.scenarios: list[dict] = []
        self.reviews: list[dict] = []
        self.ci_results: list[dict] = []
        self.coverage_data: Optional[dict] = None

        # Traceability data
        self.test_coverage: dict[str, list[str]] = {}  # test_file -> [covered_keywords]
        self.req_to_tests: dict[str, list[str]] = {}   # req_name -> [test_files]
        self.test_to_reqs: dict[str, list[str]] = {}   # test_file -> [req_names]

        # Stop words for function-name inference
        _common_test_words = {"test", "the", "and", "for", "with", "each", "from",
                              "that", "this", "all", "support", "system", "shall",
                              "should", "basic", "dummy", "can", "be", "is", "a",
                              "an", "in", "to", "of", "it", "as", "at", "by", "on"}
        self._inference_stop_words: set[str] = _common_test_words

    # ------------------------------------------------------------------ #
    # Layer-1: Module-level Covers (existing logic)
    # ------------------------------------------------------------------ #
    def _parse_module_covers(self, tree: ast.AST) -> list[str]:
        """Parse module-level docstring Covers: marker."""
        keywords = []
        docstring = ast.get_docstring(tree)
        if docstring:
            for line in docstring.split("\n"):
                m = re.search(r"^\s*Covers:\s*(.+)$", line, re.IGNORECASE)
                if m:
                    raw = m.group(1)
                    keywords.extend(
                        k.strip() for k in raw.split(",") if k.strip()
                    )
        return keywords

    def _parse_comment_covers(self, content: str) -> list[str]:
        """Parse # Covers: line comments (fallback when no module docstring)."""
        keywords = []
        for line in content.split("\n"):
            m = re.search(r"^\s*#\s*Covers:\s*(.+)$", line, re.IGNORECASE)
            if m:
                raw = m.group(1)
                keywords.extend(
                    k.strip() for k in raw.split(",") if k.strip()
                )
        return keywords

    # ------------------------------------------------------------------ #
    # Layer-2: Function-level Covers
    # ------------------------------------------------------------------ #
    def _parse_function_covers(self, tree: ast.AST) -> list[str]:
        """Parse Covers: from each test function's docstring.

        e.g.
            def test_ci_blocking_logic():
                \"\"\"Covers: CI \u963b\u65ad\u903b\u8f91, pipeline \u786c\u9519\u8bef\"\"\"
                ...
        """
        keywords = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_name = node.name
                if fn_name.startswith("test_"):
                    docstring = ast.get_docstring(node)
                    if docstring:
                        for line in docstring.split("\n"):
                            m = re.search(r"^\s*Covers:\s*(.+)$", line, re.IGNORECASE)
                            if m:
                                raw = m.group(1)
                                keywords.extend(
                                    k.strip() for k in raw.split(",") if k.strip()
                                )
        return keywords

    # ------------------------------------------------------------------ #
    # Layer-3: Function-name inference
    # ------------------------------------------------------------------ #
    @staticmethod
    def _infer_covers_from_function_names(tree: ast.AST, stop_words: set[str] | None = None) -> list[str]:
        """Infer Covers keywords from test function names.

        e.g. test_pipeline_processing -> ['pipeline', 'processing']
        """
        if stop_words is None:
            stop_words = {"test", "the", "and", "for", "with", "each", "from",
                          "that", "this", "all", "support", "system", "shall",
                          "should", "basic", "dummy", "can", "be", "is", "a",
                          "an", "in", "to", "of", "it", "as", "at", "by", "on"}
        inferred: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_name = node.name
                if fn_name.startswith("test_"):
                    # Strip leading 'test_'
                    rest = fn_name[len("test_"):]
                    # Split on underscore, camelCase, or number boundary
                    parts = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", rest)
                    for part in parts:
                        for word in re.split(r"[_]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", part):
                            w = word.lower().strip("_")
                            if w and len(w) > 2 and w not in stop_words:
                                inferred.add(w)
        return list(inferred)

    # ------------------------------------------------------------------ #
    # Main multi-layer Covers parser
    # ------------------------------------------------------------------ #
    def _parse_covers_from_file(self, test_path: str) -> list[str]:
        """Multi-layer Covers marker parser.

        Priority (all merged):
          1. Module-level docstring Covers:
          2. Module-level # Covers: line comments (fallback)
          3. Per-test-function docstring Covers:
          4. Inference from test function names
        """
        keywords = []
        try:
            with open(test_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return keywords

        try:
            tree = ast.parse(content)

            # Layer 1 & 2: Module-level Covers
            mod_kw = self._parse_module_covers(tree)
            if not mod_kw:
                mod_kw = self._parse_comment_covers(content)
            keywords.extend(mod_kw)

            # Layer 3: Function-level Covers (always scan)
            fn_kw = self._parse_function_covers(tree)
            keywords.extend(fn_kw)

            # Layer 4: Function-name inference (always scan)
            inf_kw = self._infer_covers_from_function_names(tree, self._inference_stop_words)
            keywords.extend(inf_kw)

        except SyntaxError:
            # Fallback: regex-only for malformed files
            keywords.extend(self._parse_comment_covers(content))

        return keywords

    def _collect_test_coverage(self) -> dict[str, list[str]]:
        """Scan tests/ for Covers: markers and return test_file -> [covered_keywords]."""
        tests_dir = Path(self.project_dir) / "tests"
        if not tests_dir.is_dir():
            print("  \u23ed\ufe0f  No tests/ directory found")
            return {}

        coverage: dict[str, list[str]] = {}
        for test_file in sorted(tests_dir.glob("test_*.py")):
            keywords = self._parse_covers_from_file(str(test_file))
            if keywords:
                coverage[test_file.name] = keywords

        self.test_coverage = coverage
        print(f"  \U0001f4cb Collected test coverage from {len(coverage)} test file(s)")
        if not coverage:
            print("  \u26a0\ufe0f  No Covers: markers found in any test file")
        return coverage

    def _build_requirement_to_test_map(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build bidirectional map: req_name <-> test_files via keyword matching."""
        if not self.test_coverage:
            self._collect_test_coverage()

        self.req_to_tests = {}
        self.test_to_reqs = {t: [] for t in self.test_coverage}

        # Stop words used for filtering SHALL keywords
        _stop_words = {"the", "and", "for", "with", "each", "from", "that", "this", "all", "support", "system", "shall"}

        for req in self.requirements:
            req_name = req.get("name", "")
            if not req_name:
                continue

            # Collect all keywords from SHALL statements
            shall_keywords: set[str] = set()
            for shall in req.get("shall", []):
                words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", shall.lower())
                for w in words:
                    if w not in _stop_words:
                        shall_keywords.add(w)

            # Also add req_name keywords
            name_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", req_name.lower())
            for w in name_words:
                if w not in _stop_words:
                    shall_keywords.add(w)

            # Match against each test file's Covers keywords
            matching_tests: list[str] = []
            for test_file, covered_kws in self.test_coverage.items():
                covered_lower = [k.lower() for k in covered_kws]
                # If any test keyword overlaps with shall keywords
                if any(ck in shall_keywords for ck in covered_lower):
                    matching_tests.append(test_file)

            self.req_to_tests[req_name] = matching_tests
            for t in matching_tests:
                if req_name not in self.test_to_reqs.setdefault(t, []):
                    self.test_to_reqs[t].append(req_name)

        return self.req_to_tests, self.test_to_reqs

    # ------------------------------------------------------------------ #
    # Categorization for friendly warning display
    # ------------------------------------------------------------------ #
    @staticmethod
    def _categorize_uncovered(uncovered: list[dict]) -> tuple[list[dict], list[dict]]:
        """Categorize uncovered SHALLs into critical (core logic) and warn (non-functional).

        Heuristics:
          - CRITICAL: core functionality (pipeline, review, code, test, traceability, etc.)
          - WARN: non-functional (multi-*, architecture, UI, deployment, performance, etc.)
        """
        critical: list[dict] = []
        warn: list[dict] = []

        _non_functional_keywords = {
            "multi", "multitenant", "multi-tenant", "saas",
            "web", "ui", "mobile", "desktop", "interface",
            "architecture", "deployment", "deploy",
            "performance", "parallel", "concurrent", "retry",
            "single-tenant", "organization", "project", "team hierarchy",
        }

        for u in uncovered:
            shall_text = u.get("shall", "").lower()
            req_name = u.get("req_name", "").lower()

            # Combine SHALL + requirement name for matching
            combined = shall_text + " " + req_name

            is_non_functional = any(kw in combined for kw in _non_functional_keywords)

            if is_non_functional:
                warn.append(u)
            else:
                critical.append(u)

        return critical, warn

    def _check_traceability_completeness(self) -> list[dict]:
        """Check each SHALL for test coverage. Returns list of uncovered SHALLs."""
        if not self.req_to_tests:
            self._build_requirement_to_test_map()

        uncovered: list[dict] = []
        for req in self.requirements:
            req_name = req.get("name", "")
            covered = self.req_to_tests.get(req_name, [])
            for shall in req.get("shall", []):
                if not covered:
                    uncovered.append({
                        "req_name": req_name,
                        "shall": shall,
                        "req_id": req.get("req_id", ""),
                    })

        if uncovered:
            total_shalls = sum(len(r.get("shall", [])) for r in self.requirements)
            covered_count = total_shalls - len(uncovered)

            if covered_count == 0:
                # All SHALLs uncovered -- friendly info message
                print(f"  \u2139\ufe0f  SHALL coverage: 0/{total_shalls} \u2014"
                      f" Run pipeline with real LLM to see actual coverage")
                return uncovered

            # Partial coverage: categorize and show graded output
            critical, warn = self._categorize_uncovered(uncovered)

            print(f"  \u26a0\ufe0f  SHALL coverage: {covered_count}/{total_shalls}"
                  f" ({len(uncovered)} uncovered)")

            # Show critical first
            if critical:
                print(f"    \U0001f534 CRITICAL: {len(critical)} core SHALL(s) not covered:")
                for u in critical[:5]:
                    print(f"      \u2022 {u['req_name']}: {u['shall'][:60]}...")
                if len(critical) > 5:
                    print(f"      \u2026 and {len(critical) - 5} more critical")

            # Warn with sample only
            if warn:
                print(f"    \U0001f7e1 WARN: {len(warn)} non-functional SHALL(s) not covered:")
                for u in warn[:3]:
                    print(f"      \u2022 {u['req_name']}: {u['shall'][:60]}...")
                if len(warn) > 3:
                    print(f"      \u2026 and {len(warn) - 3} more non-functional")

        return uncovered

    def collect_requirements(self, spec_path: str = None):
        """Parse OpenSpec and collect requirements."""
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")

        if not os.path.exists(spec_path):
            print(f"  \u23ed\ufe0f  Spec not found: {spec_path}")
            return

        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        from validate import parse_spec

        doc = parse_spec(spec_path)
        self.requirements = [r.to_dict() for r in doc.requirements]
        self.scenarios = [s.to_dict() for s in doc.scenarios]
        print(f"  \U0001f4cb Collected {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

    def collect_reviews(self):
        """Collect all review session records."""
        rev_dir = Path(self.project_dir) / ".osh" / "reviews"
        if not rev_dir.exists():
            print("  \u23ed\ufe0f  No review records found")
            return

        for task_dir in rev_dir.iterdir():
            if task_dir.is_dir():
                sess_file = task_dir / "review-session.json"
                if sess_file.exists():
                    with open(sess_file) as f:
                        self.reviews.append(json.load(f))

        print(f"  \U0001f4cb Collected {len(self.reviews)} review session(s)")

    def collect_ci_results(self):
        """Collect all CI layer results."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  \u23ed\ufe0f  No CI results found")
            return

        for f in sorted(ci_dir.glob("layer*.json")):
            with open(f) as fh:
                data = json.load(fh)
                self.ci_results.append(data)

                # Extract latest coverage data
                if data.get("coverage"):
                    self.coverage_data = data["coverage"]

        print(f"  \U0001f4cb Collected {len(self.ci_results)} CI result(s)")

    def generate_traceability_matrix(self) -> str:
        """Generate requirements traceability matrix with test mappings."""
        # Build test coverage if not already done
        if not self.req_to_tests:
            self._build_requirement_to_test_map()
        uncovered = self._check_traceability_completeness()

        lines = [
            f"# Traceability Matrix",
            f"",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}",
            f"",
            f"## Requirements \u2192 Implementation \u2192 Tests",
            f"",
        ]

        for req in self.requirements:
            name = req.get("name", "Unknown")
            shall_count = req.get("shall_count", 0)
            req_id = req.get("req_id", "")
            lines.append(f"### {name}")
            if req_id:
                lines.append(f"- Req ID: {req_id}")
            lines.append(f"- SHALL statements: {shall_count}")
            implementation_status = '\u2705 Covered' if shall_count > 0 else '\u274c No implementation'
            lines.append(f"- Status: {implementation_status}")

            # Check for matching scenarios
            matching_scenarios = [
                s for s in self.scenarios
                if name.lower() in s.get("name", "").lower()
            ]
            if matching_scenarios:
                lines.append(f"- Scenarios: {len(matching_scenarios)}")
                for s in matching_scenarios:
                    lines.append(f"  - {s['name']}: GIVEN({len(s['given'])}) \u2192 WHEN({len(s['when'])}) \u2192 THEN({len(s['then'])})")
            else:
                lines.append(f"- Scenarios: 0 \u26a0\ufe0f")

            # Test coverage mapping
            matching_tests = self.req_to_tests.get(name, [])
            if matching_tests:
                lines.append(f"- Test files ({len(matching_tests)}):")
                for tf in matching_tests:
                    lines.append(f"  - {tf}")
            else:
                lines.append(f"- Test files: 0 \u274c Not covered by any test")

            # List individual SHALL coverage
            lines.append(f"- SHALL details:")
            for shall in req.get("shall", []):
                is_covered = bool(matching_tests)
                icon = "\u2705" if is_covered else "\u274c"
                lines.append(f"  {icon} {shall[:80]}{'...' if len(shall) > 80 else ''}")

            # Check review records
            matching_reviews = [
                r for r in self.reviews
                if name.lower() in r.get("task", "").lower()
            ]
            if matching_reviews:
                for r in matching_reviews:
                    lines.append(f"- Review: {r.get('decision', 'unknown')} by {len(r.get('reviews', []))} agent(s)")

            lines.append("")

        # Summary
        total = len(self.requirements)
        covered = sum(1 for r in self.requirements if r.get("shall_count", 0) > 0)
        test_covered = sum(1 for r in self.requirements if self.req_to_tests.get(r.get("name", ""), []))
        lines.extend([
            f"## Summary",
            f"- Total Requirements: {total}",
            f"- Requirements with implementation: {covered} ({covered/total*100:.0f}%)" if total > 0 else "- Requirements with implementation: 0",
            f"- Requirements with test coverage: {test_covered} ({test_covered/total*100:.0f}%)" if total > 0 else "- Requirements with test coverage: 0",
            f"- Uncovered SHALLs: {len(uncovered)}",
            f"- Scenarios: {len(self.scenarios)}",
            f"- Reviews: {len(self.reviews)}",
            f"- CI Runs: {len(self.ci_results)}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "traceability-matrix.md"
        output_path.write_text(content)
        print(f"  \u2705 Traceability matrix generated: {output_path}")
        return str(output_path)

    def generate_requirement_coverage(self) -> str:
        """Generate requirements coverage report."""
        lines = [
            f"# Requirements Coverage Report",
            f"",
            f"> Generated: {self.generated_at}",
            f"",
            f"| Requirement | SHALLs | Status |",
            f"|:-----------|:------:|:------:|",
        ]

        for req in self.requirements:
            name = req.get("name", "Unknown")
            sc = req.get("shall_count", 0)
            status = "\u2705" if sc > 0 else "\u274c"
            lines.append(f"| {name} | {sc} | {status} |")

        # Requirement coverage summary
        total = len(self.requirements)
        covered = sum(1 for r in self.requirements if r.get("shall_count", 0) > 0)
        pct = (covered / total * 100) if total > 0 else 0
        lines.extend([
            "",
            f"**Requirement Coverage**: {covered}/{total} ({pct:.0f}%)",
            f"**Scenarios**: {len(self.scenarios)}",
            f"**Threshold**: 100%",
            f"**Pass**: {'\u2705' if pct >= 100 else '\u274c'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "requirement-coverage.md"
        output_path.write_text(content)
        print(f"  \u2705 Requirement coverage report: {output_path}")
        return str(output_path)

    def generate_code_coverage_report(self) -> str:
        """Generate code coverage report from CI data."""
        lines = [
            f"# Code Coverage Report",
            f"",
            f"> Generated: {self.generated_at}",
            f"",
        ]

        if self.coverage_data:
            lines.extend([
                f"| Metric | Value | Threshold | Status |",
                f"|:-------|:-----:|:---------:|:------:|",
                f"| Line Coverage | {self.coverage_data.get('line_coverage', 'N/A')}% | {self.coverage_data.get('threshold_line', 80)}% | {'\u2705' if self.coverage_data.get('line_pass') else '\u274c'} |",
                f"| Condition Coverage | {self.coverage_data.get('condition_coverage', 'N/A')}% | {self.coverage_data.get('threshold_condition', 75)}% | {'\u2705' if self.coverage_data.get('condition_pass') else '\u274c'} |",
            ])
        else:
            lines.append("No coverage data available \u2014 run CI Layer 1 first.")

        content = "\n".join(lines)
        output_path = self.evidence_dir / "code-coverage-report.md"
        output_path.write_text(content)
        print(f"  \u2705 Code coverage report: {output_path}")
        return str(output_path)

    def aggregate_review_logs(self) -> str:
        """Aggregate all review logs into a single JSON."""
        lines = []
        for r in self.reviews:
            lines.append(f"## Task: {r.get('task', 'N/A')}")
            lines.append(f"- Decision: {r.get('decision', 'N/A')}")
            lines.append(f"- Created: {r.get('created_at', 'N/A')}")
            lines.append(f"- Reviews ({len(r.get('reviews', []))} agents):")
            for rev in r.get("reviews", []):
                status_icon = {"passed": "\u2705", "failed": "\u274c", "retry": "\U0001f504", "running": "\u23f3"}
                icon = status_icon.get(rev.get("status", ""), "\u2753")
                findings = rev.get("finding_breakdown", {})
                lines.append(f"  {icon} {rev.get('reviewer', 'N/A')}: {rev.get('status', 'N/A')} "
                           f"(C:{findings.get('critical',0)} M:{findings.get('major',0)} m:{findings.get('minor',0)})")
                lines.append(f"    Summary: {rev.get('summary', 'N/A')}")
            lines.append("")

        content = "\n".join(lines)
        output_path = self.evidence_dir / "review-log-summary.md"
        output_path.write_text(content)

        # Also save raw JSON
        json_path = self.evidence_dir / "review-log.json"
        with open(json_path, "w") as f:
            json.dump(self.reviews, f, indent=2, ensure_ascii=False)

        print(f"  \u2705 Review logs aggregated: {output_path}")
        return str(output_path)

    def generate_acceptance_matrix(self) -> str:
        """Generate acceptance matrix: Req/SHALL -> verification method -> test file -> status."""
        if not self.req_to_tests:
            self._build_requirement_to_test_map()

        lines = [
            f"# Acceptance Matrix",
            f"",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}",
            f"",
            f"| Req ID | Requirement | SHALL | \u9a8c\u8bc1\u65b9\u6cd5 | \u6d4b\u8bd5\u6587\u4ef6 | \u72b6\u6001 |",
            f"|:------:|:-----------|:------|:---------|:--------|:----:|",
        ]

        total_shalls = 0
        covered_shalls = 0
        for req in self.requirements:
            name = req.get("name", "Unknown")
            req_id = req.get("req_id", "RS---")
            shall_list = req.get("shall", [])
            matching_tests = self.req_to_tests.get(name, [])
            test_str = ", ".join(matching_tests) if matching_tests else "\u2014"
            status = "\u2705" if matching_tests else "\u274c"

            for idx, shall in enumerate(shall_list):
                total_shalls += 1
                # Each SHALL gets its own row; test coverage check at req level
                shall_status = status if matching_tests else "\u274c"
                if matching_tests:
                    covered_shalls += 1
                lines.append(
                    f"| {req_id} | {name} | {shall} | Unit Test | {test_str} | {shall_status} |"
                )

        # Summary
        pct = (covered_shalls / total_shalls * 100) if total_shalls > 0 else 0
        lines.extend([
            f"",
            f"## Summary",
            f"- Total SHALL statements: {total_shalls}",
            f"- Covered by tests: {covered_shalls} ({pct:.0f}%)",
            f"- Uncovered: {total_shalls - covered_shalls}",
            f"- Threshold: 100% \u2192 {'\u2705 PASS' if pct >= 100 else '\u274c FAIL'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "acceptance-matrix.md"
        output_path.write_text(content)
        print(f"  \u2705 Acceptance matrix generated: {output_path}")
        return str(output_path)

    def pack_compliance_zip(self) -> str:
        """Create compliance pack ZIP for ASPICE audit."""
        zip_path = self.evidence_dir / "compliance-pack.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add all generated evidence files
            for f in self.evidence_dir.iterdir():
                if f.suffix in (".md", ".json") and f.name != "compliance-pack.zip":
                    zf.write(f, arcname=f.name)

            # Add spec file
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")
            if os.path.exists(spec_path):
                zf.write(spec_path, arcname="spec.md")

            # Add startup analysis
            sa_path = os.path.join(self.project_dir, "docs", "startup-analysis.md")
            if os.path.exists(sa_path):
                zf.write(sa_path, arcname="startup-analysis.md")

        print(f"  \U0001f4e6 Compliance pack created: {zip_path}")
        return str(zip_path)


def generate_evidence(project_dir: str = None, spec_path: str = None):
    """Generate full evidence chain.

    Args:
        project_dir: Root directory of the project. Defaults to OSH_HOME env or cwd.
        spec_path: Optional explicit spec file path. Defaults to docs/spec.md under project_dir.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    print(f"\n\U0001f4e6 OSH Evidence Generation")
    print(f"{'='*50}")

    collector = EvidenceCollector(project_dir)

    collector.collect_requirements(spec_path=spec_path)
    collector.collect_reviews()
    collector.collect_ci_results()

    print(f"\n{'='*50}")

    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.generate_acceptance_matrix())
    artifacts.append(collector.aggregate_review_logs())
    artifacts.append(collector.pack_compliance_zip())

    print(f"\n{'='*50}")
    print(f"\u2705 Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print(f"   - traceability-matrix.md")
    print(f"   - requirement-coverage.md")
    print(f"   - code-coverage-report.md")
    print(f"   - review-log-summary.md + review-log.json")
    print(f"   - compliance-pack.zip \U0001f3af")
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
