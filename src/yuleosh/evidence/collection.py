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
        """Collect requirements from a spec file."""
        if spec_path is None:
            spec_path = self._find_latest_pipeline_spec()
        if spec_path is None:
            spec_path = os.path.join(self.project_dir, "docs", "spec.md")

        if not os.path.exists(spec_path):
            print(f"  ⏭️  Spec not found: {spec_path}")
            return

        sys.path.insert(0, os.path.join(self.project_dir, "src", "spec"))
        try:
            from validate import parse_spec
        except ImportError:
            from yuleosh.spec.validate import parse_spec

        doc = parse_spec(spec_path)
        self.requirements = [r.to_dict() for r in doc.requirements]
        self.scenarios = [s.to_dict() for s in doc.scenarios]
        print(f"  📋 Collected {len(self.requirements)} requirements, {len(self.scenarios)} scenarios")

    def collect_reviews(self):
        """Collect review records from .osh/reviews/."""
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
