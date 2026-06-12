#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

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
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("evidence.collector")


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
        self.sil_reports: list[dict] = []

        # Traceability data
        self.test_coverage: dict[str, list[str]] = {}  # test_file -> [covered_keywords]
        self.req_to_tests: dict[str, list[str]] = {}   # req_name -> [test_files]
        self.test_to_reqs: dict[str, list[str]] = {}   # test_file -> [req_names]

        # Scenario-Ref exact match data (Priority 1)
        self.scenario_refs: dict[str, list[str]] = {}  # test_file -> [explicit scenario names]

        # Match mode & confidence tracking
        # mode: "exact" | "keyword" | "none"
        self.match_modes: dict[str, dict[str, str]] = {}
        self.match_confidences: dict[str, dict[str, float]] = {}

        # Stop words for function-name inference
        _common_test_words = {"test", "the", "and", "for", "with", "each", "from",
                              "that", "this", "all", "support", "system", "shall",
                              "should", "basic", "dummy", "can", "be", "is", "a",
                              "an", "in", "to", "of", "it", "as", "at", "by", "on"}
        self._inference_stop_words: set[str] = _common_test_words

    # ------------------------------------------------------------------ #
    # Scenario-Ref parsing (Priority 1 exact matching)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_scenario_refs(text: str) -> list[str]:
        """Parse Scenario-Ref: markers from docstring or comment text.

        Supports two formats:
          1. Inline on a Covers: line:
             Covers: pipeline, SDD, Scenario-Ref: SDD → DDD → TDD 全流程
          2. Standalone line:
             Scenario-Ref: CI/CD 三层验证

        Returns deduplicated list of scenario reference names.
        """
        refs: list[str] = []
        seen: set[str] = set()
        for line in text.split("\n"):
            m = re.search(r"Scenario-Ref:\s*(.+)$", line, re.IGNORECASE)
            if m:
                raw = m.group(1).strip()
                # Strip trailing Scenario-Ref segments
                raw = re.split(r",\s*Scenario-Ref:", raw, flags=re.IGNORECASE)[0]
                # Strip trailing quotes, commas, semicolons, whitespace
                raw = raw.rstrip('",; \t\n\r')
                # Also strip trailing triple-quote sequences
                raw = re.sub(r'"{2,}$', '', raw)
                if raw and raw not in seen:
                    seen.add(raw)
                    refs.append(raw)
        return refs

    def _collect_scenario_refs_from_file(self, test_path: str) -> list[str]:
        """Extract Scenario-Ref values from a test file.

        Scans module docstring, function docstrings, and line comments.
        """
        try:
            with open(test_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        return self._parse_scenario_refs(content)

    # ------------------------------------------------------------------ #
    # Layer-1: Module-level Covers (existing logic)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_module_covers(tree: ast.AST) -> list[str]:
        """Parse module-level docstring Covers: marker.

        Strips Scenario-Ref: portions to keep keywords clean.
        """
        keywords = []
        docstring = ast.get_docstring(tree)
        if docstring:
            for line in docstring.split("\n"):
                m = re.search(r"^\s*Covers:\s*(.+)$", line, re.IGNORECASE)
                if m:
                    raw = m.group(1)
                    # Strip Scenario-Ref: portions from Covers line
                    raw = re.sub(r"Scenario-Ref:\s*[^,]+(?:,\s*)?", "", raw, flags=re.IGNORECASE)
                    keywords.extend(
                        k.strip() for k in raw.split(",") if k.strip()
                    )
        return keywords

    @staticmethod
    def _parse_comment_covers(content: str) -> list[str]:
        """Parse # Covers: line comments (fallback when no module docstring).

        Strips Scenario-Ref: portions to keep keywords clean.
        """
        keywords = []
        for line in content.split("\n"):
            m = re.search(r"^\s*#\s*Covers:\s*(.+)$", line, re.IGNORECASE)
            if m:
                raw = m.group(1)
                # Strip Scenario-Ref: portions from Covers line
                raw = re.sub(r"Scenario-Ref:\s*[^,]+(?:,\s*)?", "", raw, flags=re.IGNORECASE)
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
                \"\"\"Covers: CI 阻断逻辑, pipeline 硬错误\"\"\"
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

        Note: Scenario-Ref markers on Covers lines are stripped from keywords;
        they are parsed separately via _collect_scenario_refs_from_file().
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
            print("  ⏭️  No tests/ directory found")
            return {}

        coverage: dict[str, list[str]] = {}
        failed_parse: list[str] = []
        for test_file in sorted(tests_dir.glob("test_*.py")):
            try:
                keywords = self._parse_covers_from_file(str(test_file))
                if keywords:
                    coverage[test_file.name] = keywords
            except Exception as e:
                failed_parse.append(f"{test_file.name}: {e}")

        self.test_coverage = coverage
        print(f"  📋 Collected test coverage from {len(coverage)} test file(s)")
        if failed_parse:
            print(f"  ⚠️  {len(failed_parse)} file(s) failed to parse:")
            for fp in failed_parse[:5]:
                print(f"     - {fp}")
            if len(failed_parse) > 5:
                print(f"     ... and {len(failed_parse) - 5} more")
        if not coverage:
            print("  ⚠️  No Covers: markers found in any test file")
        return coverage

    def _build_requirement_to_test_map(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        """Build bidirectional map: req_name <-> test_files via two-level matching.

        Priority 1: Exact Scenario-Ref matching — test file declares explicit scenario ref
        Priority 2: Keyword-weighted overlap fallback — current substring matching

        Also populates self.match_modes and self.match_confidences per (req, test_file).
        """
        if not self.test_coverage:
            self._collect_test_coverage()

        # Common stop words (define early, used by both reverse-index and keyword matching)
        _stop_words = {"the", "and", "for", "with", "each", "from", "that", "this",
                       "all", "support", "system", "shall", "should", "can", "be",
                       "is", "a", "an", "in", "to", "of", "it", "as", "at", "by", "on"}

        # Collect Scenario-Ref data for all test files
        if not self.scenario_refs:
            tests_dir = Path(self.project_dir) / "tests"
            if tests_dir.is_dir():
                for test_file in sorted(tests_dir.glob("test_*.py")):
                    self.scenario_refs[test_file.name] = \
                        self._collect_scenario_refs_from_file(str(test_file))

        # Build scenario → requirements reverse index via keyword overlap
        scenario_to_reqs: dict[str, list[str]] = {}
        for req in self.requirements:
            req_name = req.get("name", "")
            if not req_name:
                continue
            # Collect SHALL keywords for this requirement
            req_words: set[str] = set()
            for shall in req.get("shall", []):
                for w in re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", shall.lower()):
                    if w not in _stop_words:
                        req_words.add(w)
            name_words = re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", req_name.lower())
            for w in name_words:
                if w not in _stop_words:
                    req_words.add(w)

            for s in self.scenarios:
                s_name = s.get("name", "")
                if not s_name:
                    continue
                # Match: req_name substring in scenario name OR vice versa
                is_match = req_name.lower() in s_name.lower() or s_name.lower() in req_name.lower()
                if not is_match:
                    # Keyword overlap fallback for scenario→req
                    s_text = s_name.lower() + " " + " ".join(s.get("given", [])) + " " + " ".join(s.get("when", [])) + " " + " ".join(s.get("then", []))
                    s_words = set(re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", s_text))
                    if s_words & req_words:
                        is_match = True
                if is_match:
                    scenario_to_reqs.setdefault(s_name, []).append(req_name)

        self.req_to_tests = {}
        self.test_to_reqs = {t: [] for t in self.test_coverage}
        self.match_modes = {}
        self.match_confidences = {}

        for req in self.requirements:
            req_name = req.get("name", "")
            if not req_name:
                continue

            # Collect SHALL-level keywords
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

            # ---- Priority 1: Exact Scenario-Ref matching ----
            exact_matches: list[str] = []
            for test_file, srefs in self.scenario_refs.items():
                if not srefs:
                    continue
                for sref in srefs:
                    reqs_for_scenario = scenario_to_reqs.get(sref, [])
                    if req_name in reqs_for_scenario:
                        if test_file not in exact_matches:
                            exact_matches.append(test_file)
                        break

            # ---- Priority 2: Keyword-weighted fallback ----
            keyword_matches: list[str] = []
            keyword_confidences: dict[str, float] = {}
            for test_file, covered_kws in self.test_coverage.items():
                # Tokenize Covers keywords: split English words AND Chinese chars
                covered_tokens: set[str] = set()
                for ck in covered_kws:
                    ck_lower = ck.lower()
                    # Split on spaces/underscores for English words
                    eng_parts = re.findall(r"[a-zA-Z0-9_]{2,}", ck_lower)
                    covered_tokens.update(eng_parts)
                    # Also extract Chinese character bigrams for CJK matching
                    cjk = re.findall(r"[\u4e00-\u9fff]+", ck_lower)
                    for cjk_phrase in cjk:
                        covered_tokens.add(cjk_phrase)  # full phrase
                        if len(cjk_phrase) >= 2:
                            # Add bigrams for partial matching
                            for i in range(len(cjk_phrase) - 1):
                                covered_tokens.add(cjk_phrase[i:i+2])
                overlap = covered_tokens & shall_keywords
                if overlap:
                    keyword_matches.append(test_file)
                    confidence = min(1.0, len(overlap) / max(len(shall_keywords), 1))
                    keyword_confidences[test_file] = round(confidence, 2)

            # Merge: exact first, then keyword (deduplicated)
            all_matches: list[str] = []
            for t in exact_matches:
                if t not in all_matches:
                    all_matches.append(t)
            for t in keyword_matches:
                if t not in all_matches:
                    all_matches.append(t)

            # Record modes and confidences
            self.match_modes.setdefault(req_name, {})
            self.match_confidences.setdefault(req_name, {})
            for test_file in all_matches:
                if test_file in exact_matches:
                    self.match_modes[req_name][test_file] = "exact"
                    self.match_confidences[req_name][test_file] = 1.0
                elif test_file in keyword_matches:
                    self.match_modes[req_name][test_file] = "keyword"
                    self.match_confidences[req_name][test_file] = \
                        keyword_confidences.get(test_file, 0.5)
                else:
                    self.match_modes[req_name][test_file] = "keyword"
                    self.match_confidences[req_name][test_file] = 0.5

            self.req_to_tests[req_name] = all_matches
            for t in all_matches:
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
                print(f"  ℹ️  SHALL coverage: 0/{total_shalls} —"
                      f" Run pipeline with real LLM to see actual coverage")
                return uncovered

            # Partial coverage: categorize and show graded output
            critical, warn = self._categorize_uncovered(uncovered)

            print(f"  ⚠️  SHALL coverage: {covered_count}/{total_shalls}"
                  f" ({len(uncovered)} uncovered)")

            # Show critical first
            if critical:
                print(f"    🔴 CRITICAL: {len(critical)} core SHALL(s) not covered:")
                for u in critical[:5]:
                    print(f"      • {u['req_name']}: {u['shall'][:60]}...")
                if len(critical) > 5:
                    print(f"      … and {len(critical) - 5} more critical")

            # Warn with sample only
            if warn:
                print(f"    🟡 WARN: {len(warn)} non-functional SHALL(s) not covered:")
                for u in warn[:3]:
                    print(f"      • {u['req_name']}: {u['shall'][:60]}...")
                if len(warn) > 3:
                    print(f"      … and {len(warn) - 3} more non-functional")

        return uncovered

    def _find_latest_pipeline_spec(self) -> Optional[str]:
        """Auto-discover spec_path from the most recent pipeline session.

        Queries the SQLite store for the latest pipeline, falling back to
        session JSON on disk if the store is unavailable.
        """
        # Try SQLite store first
        try:
            from store import Store
            store = Store(db_path=os.path.join(self.project_dir, ".osh", "store.db"))
            pipelines = store.list_pipelines()
            if pipelines:
                latest_name = pipelines[0].get("name")
                if latest_name:
                    full = store.get_pipeline(latest_name)
                    if full and full.get("spec_path"):
                        return full["spec_path"]
        except Exception as e:
            log.warning("Store lookup for latest pipeline spec failed: %s", e)

        # Fallback: scan .osh/sessions/ on disk
        sessions_dir = Path(self.project_dir) / ".osh" / "sessions"
        if sessions_dir.is_dir():
            session_files = sorted(
                sessions_dir.rglob("session.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for sf in session_files:
                try:
                    data = json.loads(sf.read_text())
                    sp = data.get("spec_path")
                    if sp and os.path.exists(sp):
                        return sp
                except (json.JSONDecodeError, OSError, KeyError):
                    continue

        return None

    def collect_requirements(self, spec_path: str = None):
        """Parse OpenSpec and collect requirements.

        When *spec_path* is None, auto-discovers the spec from the most
        recent pipeline session.  Falls back to ``docs/spec.md``.
        """
        if spec_path is None:
            spec_path = self._find_latest_pipeline_spec()
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")

        if not os.path.exists(spec_path):
            print(f"  ⏭️  Spec not found: {spec_path}")
            return

        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        from validate import parse_spec

        doc = parse_spec(spec_path)
        self.requirements = [r.to_dict() for r in doc.requirements]
        self.scenarios = [s.to_dict() for s in doc.scenarios]
        print(f"  📋 Collected {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

    def collect_reviews(self):
        """Collect all review session records."""
        rev_dir = Path(self.project_dir) / ".osh" / "reviews"
        if not rev_dir.exists():
            print("  ⏭️  No review records found")
            return

        for task_dir in rev_dir.iterdir():
            if task_dir.is_dir():
                sess_file = task_dir / "review-session.json"
                if sess_file.exists():
                    with open(sess_file) as f:
                        self.reviews.append(json.load(f))

        print(f"  📋 Collected {len(self.reviews)} review session(s)")

    def collect_ci_results(self):
        """Collect all CI layer results."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI results found")
            return

        for f in sorted(ci_dir.glob("layer*.json")):
            with open(f) as fh:
                data = json.load(fh)
                self.ci_results.append(data)

                # Extract latest coverage data
                if data.get("coverage"):
                    self.coverage_data = data["coverage"]

        print(f"  📋 Collected {len(self.ci_results)} CI result(s)")

    def collect_sil_reports(self):
        """Collect SIL (Software-in-the-Loop) test report files from
        ``.osh/ci/*sil*.json`` and integrate into the evidence chain."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI directory — no SIL reports to collect")
            return

        sil_files = sorted(ci_dir.glob("*sil*.json"))
        if not sil_files:
            print("  ⏭️  No SIL test reports found (*sil*.json)")
            return

        for sf in sil_files:
            try:
                with open(sf) as f:
                    data = json.load(f)
                data["_source_file"] = sf.name
                self.sil_reports.append(data)
                # Also add to ci_results for traceability
                self.ci_results.append(data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"    ⚠️  Could not read SIL report {sf.name}: {e}")

        total_tests = sum(
            len(r.get("results", [])) for r in self.sil_reports
        )
        print(f"  🖥️  Collected {len(self.sil_reports)} SIL report(s)"
              f" ({total_tests} test case(s))")

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
            f"## Requirements → Implementation → Tests",
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
            implementation_status = '✅ Covered' if shall_count > 0 else '❌ No implementation'
            lines.append(f"- Status: {implementation_status}")

            # Check for matching scenarios
            matching_scenarios = [
                s for s in self.scenarios
                if name.lower() in s.get("name", "").lower()
            ]
            if matching_scenarios:
                lines.append(f"- Scenarios: {len(matching_scenarios)}")
                for s in matching_scenarios:
                    lines.append(f"  - {s['name']}: GIVEN({len(s['given'])}) → WHEN({len(s['when'])}) → THEN({len(s['then'])})")
            else:
                lines.append(f"- Scenarios: 0 ⚠️")

            # Test coverage mapping with match mode and confidence
            matching_tests = self.req_to_tests.get(name, [])
            if matching_tests:
                lines.append(f"- Test files ({len(matching_tests)}):")
                for tf in matching_tests:
                    mode = self.match_modes.get(name, {}).get(tf, "keyword")
                    conf = self.match_confidences.get(name, {}).get(tf, 0.5)
                    mode_icon = "🎯" if mode == "exact" else "🔍"
                    lines.append(f"  - {tf} ({mode_icon} {mode}, confidence: {conf:.0%})")
            else:
                lines.append(f"- Test files: 0 ❌ Not covered by any test")

            # List individual SHALL coverage
            lines.append(f"- SHALL details:")
            for shall in req.get("shall", []):
                is_covered = bool(matching_tests)
                icon = "✅" if is_covered else "❌"
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
        print(f"  ✅ Traceability matrix generated: {output_path}")

        # Also output structured JSON for downstream tooling
        json_data: dict = {
            "generated": self.generated_at,
            "version": self.version,
            "summary": {
                "total_requirements": total,
                "with_implementation": covered,
                "with_test_coverage": test_covered,
                "uncovered_shalls": len(uncovered),
                "total_scenarios": len(self.scenarios),
                "total_reviews": len(self.reviews),
                "total_ci_runs": len(self.ci_results),
            },
            "requirements": [],
        }
        for req in self.requirements:
            req_name = req.get("name", "Unknown")
            matching_tests = self.req_to_tests.get(req_name, [])
            json_req: dict = {
                "name": req_name,
                "req_id": req.get("req_id", ""),
                "shall_count": req.get("shall_count", 0),
                "shall_statements": req.get("shall", []),
                "matched_tests": [
                    {
                        "file": tf,
                        "mode": self.match_modes.get(req_name, {}).get(tf, "keyword"),
                        "confidence": self.match_confidences.get(req_name, {}).get(tf, 0.0),
                    }
                    for tf in matching_tests
                ],
            }
            json_data["requirements"].append(json_req)

        json_path = self.evidence_dir / "traceability-matrix.json"
        json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False))
        print(f"  ✅ Traceability JSON generated: {json_path}")

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
            status = "✅" if sc > 0 else "❌"
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
            f"**Pass**: {'✅' if pct >= 100 else '❌'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "requirement-coverage.md"
        output_path.write_text(content)
        print(f"  ✅ Requirement coverage report: {output_path}")
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
                f"| Line Coverage | {self.coverage_data.get('line_coverage', 'N/A')}% | {self.coverage_data.get('threshold_line', 80)}% | {'✅' if self.coverage_data.get('line_pass') else '❌'} |",
                f"| Condition Coverage | {self.coverage_data.get('condition_coverage', 'N/A')}% | {self.coverage_data.get('threshold_condition', 75)}% | {'✅' if self.coverage_data.get('condition_pass') else '❌'} |",
            ])
        else:
            lines.append("No coverage data available — run CI Layer 1 first.")

        content = "\n".join(lines)
        output_path = self.evidence_dir / "code-coverage-report.md"
        output_path.write_text(content)
        print(f"  ✅ Code coverage report: {output_path}")
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
                status_icon = {"passed": "✅", "failed": "❌", "retry": "🔄", "running": "⏳"}
                icon = status_icon.get(rev.get("status", ""), "❓")
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

        print(f"  ✅ Review logs aggregated: {output_path}")
        return str(output_path)

    def generate_acceptance_matrix(self) -> str:
        """Generate acceptance matrix: Req/SHALL -> verification method -> test file -> status.

        Includes match mode and confidence columns for traceability quality.
        """
        if not self.req_to_tests:
            self._build_requirement_to_test_map()

        lines = [
            f"# Acceptance Matrix",
            f"",
            f"> Generated: {self.generated_at}",
            f"> Version: {self.version}",
            f"",
            f"| Req ID | Requirement | SHALL | 验证方法 | 测试文件 | 匹配方式 | 置信度 | 状态 |",
            f"|:------:|:-----------|:------|:---------|:--------|:--------:|:------:|:----:|",
        ]

        total_shalls = 0
        covered_shalls = 0
        for req in self.requirements:
            name = req.get("name", "Unknown")
            req_id = req.get("req_id", "RS---")
            shall_list = req.get("shall", [])
            matching_tests = self.req_to_tests.get(name, [])
            test_str = ", ".join(matching_tests) if matching_tests else "—"
            status = "✅" if matching_tests else "❌"

            # Determine dominant match mode and confidence for this req
            modes = self.match_modes.get(name, {})
            confs = self.match_confidences.get(name, {})
            if matching_tests:
                # Pick best mode: "exact" if any test matched exactly
                dominant_mode = "exact" if any(m == "exact" for m in modes.values()) else "keyword"
                best_conf = max(confs.values()) if confs else 0.0
            else:
                dominant_mode = "—"
                best_conf = 0.0

            for idx, shall in enumerate(shall_list):
                total_shalls += 1
                shall_status = status if matching_tests else "❌"
                if matching_tests:
                    covered_shalls += 1
                mode_str = dominant_mode if idx == 0 else ""
                conf_str = f"{best_conf:.0%}" if idx == 0 and matching_tests else ""
                lines.append(
                    f"| {req_id} | {name} | {shall} | Unit Test | {test_str} | {mode_str} | {conf_str} | {shall_status} |"
                )

        # Summary
        pct = (covered_shalls / total_shalls * 100) if total_shalls > 0 else 0
        lines.extend([
            f"",
            f"## Summary",
            f"- Total SHALL statements: {total_shalls}",
            f"- Covered by tests: {covered_shalls} ({pct:.0f}%)",
            f"- Uncovered: {total_shalls - covered_shalls}",
            f"- Threshold: 100% → {'✅ PASS' if pct >= 100 else '❌ FAIL'}",
        ])

        content = "\n".join(lines)
        output_path = self.evidence_dir / "acceptance-matrix.md"
        output_path.write_text(content)
        print(f"  ✅ Acceptance matrix generated: {output_path}")
        return str(output_path)

    def pack_compliance_zip(self) -> str:
        """Create compliance pack ZIP for ASPICE audit.

        Includes all generated evidence files, the requirements spec,
        startup analysis, and any SIL test reports found in
        ``.osh/ci/``.
        """
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

            # Include SIL test reports from .osh/ci/*sil*.json
            ci_dir = Path(self.project_dir) / ".osh" / "ci"
            if ci_dir.exists():
                for sil_file in sorted(ci_dir.glob("*sil*.json")):
                    zf.write(sil_file, arcname=f"sil-reports/{sil_file.name}")

        print(f"  📦 Compliance pack created: {zip_path}")
        return str(zip_path)


def _check_pipeline_not_running(project_dir: str) -> bool:
    """Check that no pipeline is currently writing to avoid race conditions.

    Checks session status AND recent write activity in reviews/ci directories
    to detect the window where pipeline is done but artifacts are still flushing.

    Returns True if it's safe to collect evidence (no running pipeline).
    """
    import time as _time
    _now = _time.time()
    _grace_window = 5  # seconds — ignore writes older than this

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
                if (_now - recent) < _grace_window:
                    print(f"  ⚠️  Recent writes in .osh/{subdir}/ ({_now - recent:.1f}s ago) — may be pipeline flushing")
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
    import time as _time
    _max_wait = 30  # seconds
    _waited = 0
    while not _check_pipeline_not_running(project_dir) and _waited < _max_wait:
        _sleep = min(2, _max_wait - _waited)
        print(f"  ⏳ Waiting for pipeline to finish... ({_waited}s elapsed)")
        _time.sleep(_sleep)
        _waited += _sleep
    if _waited >= _max_wait:
        print(f"  ⚠️  Timed out waiting for pipeline (waited {_waited}s). Collecting anyway — data may be incomplete.")

    collector = EvidenceCollector(project_dir)

    collector.collect_requirements(spec_path=spec_path)
    collector.collect_reviews()
    collector.collect_ci_results()
    collector.collect_sil_reports()

    print(f"\n{'='*50}")

    artifacts = []
    artifacts.append(collector.generate_traceability_matrix())
    artifacts.append(collector.generate_requirement_coverage())
    artifacts.append(collector.generate_code_coverage_report())
    artifacts.append(collector.generate_acceptance_matrix())
    artifacts.append(collector.aggregate_review_logs())
    artifacts.append(collector.pack_compliance_zip())

    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print(f"   - traceability-matrix.md + traceability-matrix.json")
    print(f"   - requirement-coverage.md")
    print(f"   - code-coverage-report.md")
    print(f"   - review-log-summary.md + review-log.json")
    print(f"   - acceptance-matrix.md")
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
