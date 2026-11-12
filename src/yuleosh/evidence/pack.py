"""
yuleOSH Evidence Engine — Backwards-compatible re-export module.

For backwards compatibility, this module re-exports all public symbols
from the sub-modules (generator, compliance, report, analysis).
"""

from yuleosh.evidence.generator import EvidenceCollector
from yuleosh.evidence.compliance import pack_compliance_zip, _check_pipeline_not_running
from yuleosh.evidence.analysis import (

# @req RS-005
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


def generate_evidence(project_dir: str = None, spec_path: str = None, formats=None):
    """Generate full evidence chain.

    ``formats`` 选择人类可读产物格式（md/html/xlsx/pdf，逗号分隔或列表）；
    缺省只产 Markdown，保持既有行为。派生格式在打包阶段生成，确保合规 ZIP
    与 manifest 覆盖全部所选格式。

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

    # 派生格式（HTML/Excel/PDF）在 pack_compliance_zip 内生成：
    # process-capability-map / capability-statement 由打包函数末尾补齐，
    # 派生必须发生在它们之后、ZIP 打开之前，否则这两份报告没有对应格式。
    zip_path = pack_compliance_zip(collector, formats=formats)
    for p in sorted(collector.evidence_dir.iterdir()):
        if p.suffix in (".html", ".xlsx", ".pdf"):
            artifacts.append(str(p))
    artifacts.append(zip_path)

    print(f"\n{'='*50}")
    print(f"✅ Evidence generation complete")
    print(f"   Output: {collector.evidence_dir}")
    print(f"   Artifacts: {len(artifacts)}")
    print()
    return artifacts


def main():
    """CLI entry point for evidence generation.

    用法::
        python -m yuleosh.evidence.pack pack [--formats md,html,xlsx,pdf] [spec_path]
    """
    spec_path = None
    formats = None
    args = [a for a in sys.argv[1:] if a != "pack"]
    if "--formats" in args:
        idx = args.index("--formats")
        if idx + 1 >= len(args):
            raise SystemExit("--formats requires a value, e.g. --formats md,html,xlsx,pdf")
        formats = args[idx + 1]
        del args[idx:idx + 2]
    if args:
        spec_path = args[0]
    # 未指定 --formats 时不传参，保持 generate_evidence 既有调用签名（mock 兼容）。
    if formats is None:
        generate_evidence(spec_path=spec_path)
    else:
        generate_evidence(spec_path=spec_path, formats=formats)


if __name__ == "__main__":
    # 假绿修复 (2026-08-07): CI 用 `python -m yuleosh.evidence.pack` 调用本模块，
    # 但此前缺入口，导入即静默退出 0 → .osh/evidence/ 从未生成 →
    # 下一步 upload-artifact (if-no-files-found: error) 失败。
    # 与 evidence/check.py、compliance.py 等模块保持一致，补 __main__ 入口。
    main()
