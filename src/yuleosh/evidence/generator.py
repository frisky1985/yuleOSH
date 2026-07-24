"""
yuleOSH Evidence Engine — Core EvidenceCollector.

Provides the ``EvidenceCollector`` class (via mixins for data collection and
report generation). Collects requirements, reviews, CI results, and SIL
reports, then produces traceability matrices, coverage reports, and
acceptance matrices.
"""

import json
import logging
import os
import re as _re
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.evidence.analysis import (
    parse_scenario_refs,
    parse_covers_from_file,
    categorize_uncovered,
)
from yuleosh.evidence.collection import DataCollectionMixin
from yuleosh.evidence.report_builder import ReportBuilderMixin

log = logging.getLogger("evidence.collector")

# Common stop words used for function-name inference
_INFERENCE_STOP_WORDS = {
    "test", "the", "and", "for", "with", "each", "from",
    "that", "this", "all", "support", "system", "shall",
    "should", "basic", "dummy", "can", "be", "is", "a",
    "an", "in", "to", "of", "it", "as", "at", "by", "on",
}


class EvidenceCollector(DataCollectionMixin, ReportBuilderMixin):
    """Collects and organizes evidence for ASPICE compliance.

    Inherits data collection methods from ``DataCollectionMixin`` and
    report generation methods from ``ReportBuilderMixin``.
    """

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
        self.session_data: list[dict] = []
        self.pipeline_steps: list[dict] = []

        # Traceability data
        self.test_coverage: dict[str, list[str]] = {}
        self.req_to_tests: dict[str, list[str]] = {}
        self.test_to_reqs: dict[str, list[str]] = {}

        # Scenario-Ref exact match data (Priority 1)
        self.scenario_refs: dict[str, list[str]] = {}

        # Match mode & confidence tracking
        self.match_modes: dict[str, dict[str, str]] = {}
        self.match_confidences: dict[str, dict[str, float]] = {}

        self._inference_stop_words: set[str] = _INFERENCE_STOP_WORDS

    # ------------------------------------------------------------------ #
    # Static delegate methods (backwards compat for tests)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_scenario_refs(text: str) -> list[str]:
        from yuleosh.evidence.analysis import parse_scenario_refs as _psr
        return _psr(text)

    @staticmethod
    def _parse_module_covers(tree) -> list[str]:
        from yuleosh.evidence.analysis import parse_module_covers as _pmc
        return _pmc(tree)

    @staticmethod
    def _parse_comment_covers(content: str) -> list[str]:
        from yuleosh.evidence.analysis import parse_comment_covers as _pcc
        return _pcc(content)

    def _parse_function_covers(self, tree) -> list[str]:
        from yuleosh.evidence.analysis import parse_function_covers as _pfc
        return _pfc(tree)

    @staticmethod
    def _infer_covers_from_function_names(tree, stop_words=None) -> list[str]:
        from yuleosh.evidence.analysis import infer_covers_from_function_names as _icffn
        return _icffn(tree, stop_words)

    @staticmethod
    def _categorize_uncovered(uncovered: list[dict]) -> tuple[list[dict], list[dict]]:
        from yuleosh.evidence.analysis import categorize_uncovered as _cu
        return _cu(uncovered)

    # ------------------------------------------------------------------ #
    # Scenario-Ref & Covers parsing wrappers
    # ------------------------------------------------------------------ #

    def _collect_scenario_refs_from_file(self, test_path: str) -> list[str]:
        try:
            with open(test_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return []
        return parse_scenario_refs(content)

    def _parse_covers_from_file(self, test_path: str) -> list[str]:
        return parse_covers_from_file(test_path, self._inference_stop_words)

    # ------------------------------------------------------------------ #
    # Test coverage collection
    # ------------------------------------------------------------------ #

    def _collect_test_coverage(self) -> dict[str, list[str]]:
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

    # ------------------------------------------------------------------ #
    # Requirement-to-test mapping
    # ------------------------------------------------------------------ #

    def _build_requirement_to_test_map(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        if not self.test_coverage:
            self._collect_test_coverage()

        _stop_words = {"the", "and", "for", "with", "each", "from", "that", "this",
                       "all", "support", "system", "shall", "should", "can", "be",
                       "is", "a", "an", "in", "to", "of", "it", "as", "at", "by", "on"}

        if not self.scenario_refs:
            tests_dir = Path(self.project_dir) / "tests"
            if tests_dir.is_dir():
                for test_file in sorted(tests_dir.glob("test_*.py")):
                    self.scenario_refs[test_file.name] = \
                        self._collect_scenario_refs_from_file(str(test_file))

        scenario_to_reqs: dict[str, list[str]] = {}
        for req in self.requirements:
            req_name = req.get("name", "")
            if not req_name:
                continue
            req_words: set[str] = set()
            for shall in req.get("shall", []):
                for w in _re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", shall.lower()):
                    if w not in _stop_words:
                        req_words.add(w)
            name_words = _re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", req_name.lower())
            for w in name_words:
                if w not in _stop_words:
                    req_words.add(w)

            for s in self.scenarios:
                s_name = s.get("name", "")
                if not s_name:
                    continue
                is_match = req_name.lower() in s_name.lower() or s_name.lower() in req_name.lower()
                if not is_match:
                    s_text = s_name.lower() + " " + " ".join(s.get("given", [])) + " " + " ".join(s.get("when", [])) + " " + " ".join(s.get("then", []))
                    s_words = set(_re.findall(r"[a-zA-Z_\u4e00-\u9fff][a-zA-Z0-9_\u4e00-\u9fff]{1,}", s_text))
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

            shall_keywords: set[str] = set()
            for shall in req.get("shall", []):
                words = _re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", shall.lower())
                for w in words:
                    if w not in _stop_words:
                        shall_keywords.add(w)

            name_words = _re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", req_name.lower())
            for w in name_words:
                if w not in _stop_words:
                    shall_keywords.add(w)

            # Priority 1: Exact Scenario-Ref matching
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

            # Priority 2: Keyword-weighted fallback
            keyword_matches: list[str] = []
            keyword_confidences: dict[str, float] = {}
            for test_file, covered_kws in self.test_coverage.items():
                covered_tokens: set[str] = set()
                for ck in covered_kws:
                    ck_lower = ck.lower()
                    eng_parts = _re.findall(r"[a-zA-Z0-9_]{2,}", ck_lower)
                    covered_tokens.update(eng_parts)
                    cjk = _re.findall(r"[\u4e00-\u9fff]+", ck_lower)
                    for cjk_phrase in cjk:
                        covered_tokens.add(cjk_phrase)
                        if len(cjk_phrase) >= 2:
                            for i in range(len(cjk_phrase) - 1):
                                covered_tokens.add(cjk_phrase[i:i+2])
                overlap = covered_tokens & shall_keywords
                if overlap:
                    keyword_matches.append(test_file)
                    confidence = min(1.0, len(overlap) / max(len(shall_keywords), 1))
                    keyword_confidences[test_file] = round(confidence, 2)

            all_matches: list[str] = []
            for t in exact_matches:
                if t not in all_matches:
                    all_matches.append(t)
            for t in keyword_matches:
                if t not in all_matches:
                    all_matches.append(t)

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
    # Traceability completeness check
    # ------------------------------------------------------------------ #

    def _check_traceability_completeness(self) -> list[dict]:
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
                print(f"  ℹ️  SHALL coverage: 0/{total_shalls} —"
                      f" Run pipeline with real LLM to see actual coverage")
                return uncovered

            critical, warn = categorize_uncovered(uncovered)

            print(f"  ⚠️  SHALL coverage: {covered_count}/{total_shalls}"
                  f" ({len(uncovered)} uncovered)")

            if critical:
                print(f"    🔴 CRITICAL: {len(critical)} core SHALL(s) not covered:")
                for u in critical[:5]:
                    print(f"      • {u['req_name']}: {u['shall'][:60]}...")
                if len(critical) > 5:
                    print(f"      … and {len(critical) - 5} more critical")

            if warn:
                print(f"    🟡 WARN: {len(warn)} non-functional SHALL(s) not covered:")
                for u in warn[:3]:
                    print(f"      • {u['req_name']}: {u['shall'][:60]}...")
                if len(warn) > 3:
                    print(f"      … and {len(warn) - 3} more non-functional")

        return uncovered

    # ------------------------------------------------------------------ #
    # Pipeline spec auto-discovery
    # ------------------------------------------------------------------ #

    def _find_latest_pipeline_spec(self) -> Optional[str]:
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
