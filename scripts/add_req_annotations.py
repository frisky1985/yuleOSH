#!/usr/bin/env python3
"""Batch add @req annotations to source files for traceability.

Usage:
    python scripts/add_req_annotations.py

This script adds `# @req <ID>` comments to source files based on a
pre-defined requirement-to-module mapping derived from docs/spec.md.
"""

from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src" / "yuleosh"

# ── Requirement → Primary source files mapping ──────────────────────────
# Format: { relative_path: [req_ids] }
# Only annotate the PRIMARY implementation files, not every file in a module.

REQ_MAP: dict[str, list[str]] = {
    # ── RS-001: Agent 驱动的开发流水线 ──
    "pipeline/orchestrator.py": ["RS-001", "SWR-001.1"],
    "pipeline/steps.py": ["RS-001", "SWR-001.1"],
    "pipeline/session.py": ["RS-001", "SWR-001.1"],
    "pipeline/run.py": ["RS-001", "SWR-001.3"],
    "pipeline/gates.py": ["RS-001", "SWR-001.1"],
    "pipeline/llm_gateway.py": ["RS-001"],
    "pipeline/step_cache.py": ["RS-001"],
    "pipeline/repo_facts.py": ["RS-001"],
    "pipeline/source_grounding.py": ["RS-001"],
    "pipeline/review_guard.py": ["RS-001"],
    "pipeline/guardrail.py": ["RS-001"],

    # ── RS-001 step handlers ──
    "pipeline/step_handlers/handler_base.py": ["RS-001", "SWR-001.1"],
    "pipeline/step_handlers/audit_utils.py": ["RS-001", "RS-005"],
    "pipeline/step_handlers/test_qualification.py": ["SWR-001.2"],
    "pipeline/step_handlers/test_c_unit.py": ["SWR-001.2", "RS-008"],
    "pipeline/step_handlers/test_python_unit.py": ["SWR-001.2"],
    "pipeline/step_handlers/test_case_gen.py": ["SWR-001.2"],
    "pipeline/step_handlers/review.py": ["RS-003", "SWR-003.1"],
    "pipeline/step_handlers/review_code.py": ["RS-003", "SWR-003.1"],
    "pipeline/step_handlers/review_arch.py": ["RS-003"],
    "pipeline/step_handlers/review_prd.py": ["RS-003"],
    "pipeline/step_handlers/review_test.py": ["RS-003"],
    "pipeline/step_handlers/review_misra.py": ["RS-003"],
    "pipeline/step_handlers/review_safety.py": ["RS-003", "FSR-001"],

    # ── RS-002: 需求管理 ──
    "spec/validate.py": ["RS-002", "SWR-002.1"],
    "spec/changes.py": ["RS-002", "SWR-002.2"],
    "spec/diff.py": ["RS-002", "SWR-002.2"],
    "spec/merge.py": ["RS-002", "SWR-002.2"],
    "spec/patterns.py": ["RS-002", "SWR-002.1"],
    "spec/version.py": ["RS-002"],

    # ── RS-003: 代码审查 ──
    "review/run.py": ["RS-003", "SWR-003.1"],
    "review/c_review.py": ["RS-003", "SWR-003.1"],
    "review/tracker.py": ["RS-003"],
    "review/resource_predictor.py": ["RS-003"],

    # ── RS-004: CI/CD ──
    "ci/run.py": ["RS-004"],
    "ci/config.py": ["RS-004", "SWR-004.1", "SWR-003.2"],
    "ci/layers.py": ["RS-004"],
    "ci/runner.py": ["RS-004"],
    "ci/honesty_gate.py": ["RS-004"],
    "ci/gate_policy.py": ["RS-004", "SWR-003.2"],
    "ci/coverage_pipeline.py": ["RS-004", "SWR-003.2"],
    "ci/coverage_trend.py": ["RS-004", "SWR-003.2"],
    "ci/diff_planner.py": ["RS-004"],
    "ci/profile.py": ["RS-004"],
    "ci/profiles.py": ["RS-004"],
    "ci/misra_deviations.py": ["RS-004"],
    "ci/misra_fusion.py": ["RS-004"],

    # ── RS-005: 追溯与证据链 ──
    "alm/traceability.py": ["RS-005", "SWR-001.2"],
    "alm/traceability_config.py": ["RS-005"],
    "alm/base.py": ["RS-005"],
    "evidence/generator.py": ["RS-005"],
    "evidence/pack.py": ["RS-005"],
    "evidence/collection.py": ["RS-005"],
    "evidence/manifest.py": ["RS-005"],
    "evidence/signer.py": ["RS-005"],
    "evidence/compliance.py": ["RS-005"],
    "evidence/report.py": ["RS-005"],
    "evidence/report_builder.py": ["RS-005"],
    "evidence/aspice_check.py": ["RS-005"],

    # ── RS-006: 多端接入 ──
    "api/pipeline.py": ["RS-006"],
    "api/auth.py": ["RS-006", "CR-001"],
    "api/requirements.py": ["RS-006", "RS-002"],
    "api/spec.py": ["RS-006", "RS-002"],
    "api/review.py": ["RS-006", "RS-003"],
    "api/evidence.py": ["RS-006", "RS-005"],
    "api/compliance.py": ["RS-006"],
    "api/ci.py": ["RS-006", "RS-004"],
    "api/audit.py": ["RS-006", "CR-003"],
    "api/dashboard.py": ["RS-006"],
    "cli/main.py": ["RS-006"],

    # ── RS-007: 多租户 SaaS ──
    "tenant/model.py": ["RS-007"],
    "rbac/model.py": ["RS-007", "CR-001"],

    # ── RS-008: SIL 仿真 ──
    "sil/adapter.py": ["RS-008", "SWR-008.1"],
    "cross/sil_assert.py": ["RS-008", "SWR-008.2"],

    # ── RS-009: FAL/HIL ──
    "adapter/dspace_adapter.py": ["RS-009", "SWR-009.1"],
    "adapter/vector_adapter.py": ["RS-009", "SWR-009.1"],
    "cross/hil_runner.py": ["RS-009", "SWR-009.2"],

    # ── RS-013: AI Preview ──
    "preview/analyzer.py": ["RS-013", "SWR-013.2"],
    "preview/code_parser.py": ["RS-013", "SWR-013.1"],
    "preview/compliance_analyzer.py": ["RS-013", "SWR-013.2"],
    "preview/coverage_predictor.py": ["RS-013"],
    "preview/config_recommender.py": ["RS-013"],
    "preview/score_engine.py": ["RS-013"],
    "preview/reporter.py": ["RS-013"],

    # ── RS-014/RS-015: Billing / Knowledge Graph ──
    "billing/metering.py": ["RS-014", "SWR-014.1"],
    "knowledge_graph/store.py": ["RS-015", "KG-001"],
    "knowledge_graph/queries.py": ["RS-015", "KG-002"],
    "knowledge_graph/incremental.py": ["RS-015", "KG-001"],
    "knowledge_graph/reporter.py": ["RS-015", "KG-003"],
    "knowledge_graph/events.py": ["RS-015", "KG-005"],
    "knowledge_graph/merge_gate.py": ["RS-015", "KG-042"],
    "knowledge_graph/edge_builder.py": ["RS-015"],
    "knowledge_graph/code_scanner.py": ["RS-015"],

    # ── Cross-cutting: audit, llm, codegen ──
    "audit/model.py": ["CR-003", "NFR-002"],
    "llm/client.py": ["RS-001"],
    "llm/fallback.py": ["RS-001"],
    "llm/validation.py": ["RS-001", "CR-004"],
    "codegen/engine.py": ["RS-001", "SWR-001.1"],
    "codegen/layered.py": ["RS-001"],
    "memory/store.py": ["RS-015"],
    "memory/llm_context.py": ["RS-015"],
    "kb/store.py": ["RS-015"],
    "kb/codegen_failures.py": ["RS-015"],
    "compliance/compliance_checker.py": ["CR-005", "FSR-001"],
    "loop_engine/spec_delta_gen.py": ["RS-002", "SWR-002.2"],
}


def add_annotation(filepath: Path, req_ids: list[str]) -> bool:
    """Add @req annotation to a Python file. Returns True if modified."""
    if not filepath.exists():
        return False

    content = filepath.read_text()
    tag = "  ".join(f"@req {rid}" for rid in req_ids)
    annotation = f"# {tag}"

    if annotation in content:
        return False

    lines = content.split("\n")
    insert_idx = 0

    if lines and (lines[0].startswith("#!") or lines[0].startswith("# -*-")):
        insert_idx = 1

    if len(lines) > insert_idx:
        next_line = lines[insert_idx].strip() if insert_idx < len(lines) else ""
        if next_line.startswith('"""') or next_line.startswith("'''"):
            quote = next_line[:3]
            if next_line.count(quote) >= 2 and len(next_line) > 3:
                insert_idx += 1
            else:
                for i in range(insert_idx + 1, len(lines)):
                    if quote in lines[i]:
                        insert_idx = i + 1
                        break

    while insert_idx < len(lines) and lines[insert_idx].strip() == "":
        insert_idx += 1

    if insert_idx > 0:
        insert_idx_after = insert_idx
        while insert_idx_after < len(lines) and lines[insert_idx_after].strip().startswith("import ") or (insert_idx_after < len(lines) and lines[insert_idx_after].strip().startswith("from ")):
            insert_idx_after += 1
        if insert_idx_after > insert_idx:
            insert_idx = insert_idx_after

    new_lines = lines[:insert_idx] + ["", annotation] + lines[insert_idx:]
    filepath.write_text("\n".join(new_lines))
    return True


def main():
    added = 0
    skipped = 0
    missing = 0

    for rel_path, req_ids in sorted(REQ_MAP.items()):
        fpath = SRC / rel_path
        if not fpath.exists():
            print(f"  MISSING: {rel_path}")
            missing += 1
            continue
        if add_annotation(fpath, req_ids):
            print(f"  + {rel_path}  {req_ids}")
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} annotated, {skipped} already done, {missing} missing")


if __name__ == "__main__":
    main()
