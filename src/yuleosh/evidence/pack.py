"""
yuleOSH Evidence Engine — Backwards-compatible re-export module.

For backwards compatibility, this module re-exports all public symbols
from the sub-modules (generator, compliance, report, analysis).
"""

from yuleosh.evidence.generator import EvidenceCollector
from yuleosh.evidence.compliance import pack_compliance_zip, _check_pipeline_not_running
from yuleosh.evidence.analysis import (
    parse_scenario_refs,
    parse_module_covers,
    parse_comment_covers,
    parse_function_covers,
    infer_covers_from_function_names,
    parse_covers_from_file,
    categorize_uncovered,
)
from yuleosh.evidence.report import (
    format_maturity_label,
    format_status_icon,
    format_coverage_summary,
    make_table_row,
    make_header_row,
    make_acceptance_row,
    make_coverage_table_row,
    dedent,
    generate_timestamp,
)

import os
import sys


def generate_evidence(project_dir: str = None, spec_path: str = None):
    """Generate full evidence chain.

    Defined locally for mock-patch compatibility.
    """
    import time as _time
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    print(f"\n📦 OSH Evidence Generation")
    print(f"{'='*50}")

    _max_wait = 30
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
    artifacts.append(pack_compliance_zip(collector))

    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print()
    return artifacts


def main():
    """CLI entry point for evidence generation."""
    spec_path = None
    args = [a for a in sys.argv[1:] if a != "pack"]
    if args:
        spec_path = args[0]
    generate_evidence(spec_path=spec_path)
