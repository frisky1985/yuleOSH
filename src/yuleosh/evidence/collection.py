"""
yuleOSH Evidence Engine — Data collection.

Provides the ``DataCollectionMixin`` mixin class that implements data
collection methods (requirements, reviews, CI results, SIL reports) for
``EvidenceCollector``.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("evidence.collection")


class DataCollectionMixin:
    """Mixin adding data-collection methods to EvidenceCollector."""

    def collect_requirements(self, spec_path: str = None):
        """Collect requirements from ALL spec files.

        Scans docs/spec.md, the specified spec_path, and ALL specs/*.md files,
        merging requirements and scenarios from each.
        """
        if spec_path is None:
            spec_path = self._find_latest_pipeline_spec()
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")

        # Build list of spec files to parse
        spec_files = []
        if os.path.exists(spec_path):
            spec_files.append(spec_path)

        # Always include docs/spec.md if different
        docs_path = os.path.join(self.project_dir, "docs", "spec.md")
        if docs_path not in spec_files and os.path.exists(docs_path):
            spec_files.append(docs_path)

        # Include ALL specs/*.md files
        specs_dir = os.path.join(self.project_dir, "specs")
        if os.path.isdir(specs_dir):
            for f in sorted(os.listdir(specs_dir)):
                if f.endswith(".md"):
                    fp = os.path.join(specs_dir, f)
                    if fp not in spec_files:
                        spec_files.append(fp)

        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        try:
            from validate import parse_spec
        except ImportError:
            from yuleosh.spec.validate import parse_spec

        all_reqs = []
        all_scenarios = []
        seen_names = set()

        for sf in spec_files:
            try:
                doc = parse_spec(sf)
                new_reqs = 0
                for r in doc.requirements:
                    if r.name not in seen_names:
                        all_reqs.append(r.to_dict())
                        seen_names.add(r.name)
                        new_reqs += 1
                all_scenarios.extend(s.to_dict() for s in doc.scenarios)
                print(f"  📋 Parsed {sf}: {new_reqs} new requirements, {len(doc.scenarios)} scenarios")
            except Exception as e:
                print(f"  ⚠️  Skipped {sf}: {e}")

        self.requirements = all_reqs
        self.scenarios = all_scenarios
        print(f"  📋 Total: {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

    def collect_reviews(self):
        """Collect review records from .osh/reviews/.

        Scans both subdirectory-based review-session.json files (e.g.
        code-review/review-session.json) and flat JSON files in
        latest/ directory (e.g. latest/code-review.json).
        Deduplicates by (commit_sha, review_type) pair.
        """
        rev_dir = Path(self.project_dir) / ".osh" / "evidence" / "reviews"
        if not rev_dir.exists():
            print("  ⏭️  No review records found")
            return

        seen_keys: set[tuple[str, str]] = set()
        for task_dir in rev_dir.iterdir():
            json_files: list[Path] = []
            if task_dir.is_dir():
                # Collect all .json files in the subdirectory
                for f in sorted(task_dir.glob("*.json")):
                    json_files.append(f)
            elif task_dir.suffix == ".json":
                # Flat JSON files at the reviews/ root level
                json_files.append(task_dir)

            for f in json_files:
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    key = (data.get("commit_sha", ""), data.get("review_type", ""))
                    if key == ("", ""):
                        # No dedup key — always include
                        self.reviews.append(data)
                    elif key not in seen_keys:
                        seen_keys.add(key)
                        self.reviews.append(data)
                except (json.JSONDecodeError, OSError) as e:
                    print(f"    ⚠️  Could not read review file {f}: {e}")

        print(f"  📋 Collected {len(self.reviews)} review session(s)")

    def collect_ci_results(self):
        """Collect CI layer results from .osh/ci/."""
        ci_dir = Path(self.project_dir) / ".osh" / "ci"
        if not ci_dir.exists():
            print("  ⏭️  No CI results found")
            return

        for f in sorted(ci_dir.glob("layer*.json")):
            with open(f) as fh:
                data = json.load(fh)
                self.ci_results.append(data)
                if data.get("coverage"):
                    self.coverage_data = data["coverage"]

        print(f"  📋 Collected {len(self.ci_results)} CI result(s)")

    def collect_sil_reports(self):
        """Collect SIL test reports from .osh/ci/."""
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
                self.ci_results.append(data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"    ⚠️  Could not read SIL report {sf.name}: {e}")

        total_tests = sum(len(r.get("results", [])) for r in self.sil_reports)
        print(f"  🖥️  Collected {len(self.sil_reports)} SIL report(s)"
              f" ({total_tests} test case(s))")

    def collect_session_data(self):
        """Collect pipeline session data from .osh/sessions/.

        Scans all session subdirectories for session.json, spec-check.json,
        and per-step review files (arch-review.json, code-review.json, etc.),
        capturing the full pipeline lifecycle as evidence.

        This extends evidence coverage to ALL pipeline stages (not just
        review/L3), enabling traceability across spec-check, architecture
        review, devplan review, code review, MISRA review, linker review,
        memory review, startup review, selftest review, unit tests,
        integration tests, and coverage review.
        """
        sessions_dir = Path(self.project_dir) / ".osh" / "sessions"
        if not sessions_dir.exists():
            print("  ⏭️  No pipeline session data found")
            return

        session_count = 0
        step_files_found = 0
        step_coverage = {}  # step_name -> count of sessions with data

        for session_folder in sorted(sessions_dir.iterdir()):
            if not session_folder.is_dir():
                continue

            # Read session.json for metadata
            session_json = session_folder / "session.json"
            if not session_json.exists():
                continue

            try:
                with open(session_json) as f:
                    session_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            session_count += 1
            self.session_data.append(session_data)

            # Collect per-step review files
            # These match the pattern: {step_name}-review.json or spec-check.json
            for step_file in sorted(session_folder.glob("*.json")):
                if step_file.name == "session.json":
                    continue
                step_name = step_file.stem  # e.g. "arch-review", "spec-check"
                try:
                    with open(step_file) as f:
                        step_data = json.load(f)
                    step_data["_session_name"] = session_data.get("name", session_folder.name)
                    step_data["_step_name"] = step_name
                    step_data["_session_status"] = session_data.get("status", "unknown")
                    self.pipeline_steps.append(step_data)
                    step_files_found += 1
                    step_coverage[step_name] = step_coverage.get(step_name, 0) + 1
                except (json.JSONDecodeError, OSError):
                    pass

        if session_count > 0:
            print(f"  📋 Collected {session_count} session(s) with {step_files_found} step data file(s)")
            # Print coverage summary showing which pipeline stages are covered
            covered_stages = sorted(step_coverage.keys())
            stages_summary = ", ".join(covered_stages[:10])
            if len(covered_stages) > 10:
                stages_summary += f" ... and {len(covered_stages) - 10} more"
            print(f"     Pipeline stages covered: {stages_summary}")
        else:
            print("  ⏭️  No session data found in .osh/sessions/")

    def _find_latest_pipeline_spec(self) -> Optional[str]:
        """Find the spec file path from the most recent pipeline session."""
        sessions_dir = Path(self.project_dir) / ".osh" / "sessions"
        if not sessions_dir.exists():
            return None

        latest_session = None
        latest_mtime = 0
        for sf in sessions_dir.iterdir():
            sj = sf / "session.json"
            if sj.exists():
                mtime = sj.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_session = sj

        if latest_session:
            try:
                data = json.loads(latest_session.read_text())
                spec = data.get("spec_path", "")
                if spec and os.path.exists(spec):
                    return spec
            except (json.JSONDecodeError, OSError):
                pass
        return None
