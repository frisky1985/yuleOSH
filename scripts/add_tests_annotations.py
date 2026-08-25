#!/usr/bin/env python3
"""Batch add @tests annotations to test files for traceability.

Usage:
    python scripts/add_tests_annotations.py

Maps test files to their primary source files based on naming conventions.
"""

from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS = PROJECT_ROOT / "tests"
SRC_PREFIX = "src/yuleosh"

# ── Test file → Source file mapping ─────────────────────────────────────
# Format: { test_file_pattern: source_file }
# Patterns use fnmatch-style globs matched against test filename.

TEST_TO_SRC: dict[str, list[str]] = {
    # ── Pipeline ──
    "test_pipeline_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_orchestrator*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_session*.py": [f"{SRC_PREFIX}/pipeline/session.py"],
    "test_steps*.py": [f"{SRC_PREFIX}/pipeline/steps.py"],
    "test_step_*.py": [f"{SRC_PREFIX}/pipeline/steps.py"],
    "test_gate*.py": [f"{SRC_PREFIX}/pipeline/gates.py"],
    "test_llm_gateway*.py": [f"{SRC_PREFIX}/pipeline/llm_gateway.py"],
    "test_repo_facts*.py": [f"{SRC_PREFIX}/pipeline/repo_facts.py"],
    "test_review_guard*.py": [f"{SRC_PREFIX}/pipeline/review_guard.py"],
    "test_source_grounding*.py": [f"{SRC_PREFIX}/pipeline/source_grounding.py"],
    "test_step_cache*.py": [f"{SRC_PREFIX}/pipeline/step_cache.py"],
    "test_guardrail*.py": [f"{SRC_PREFIX}/pipeline/guardrail.py"],
    "test_run*.py": [f"{SRC_PREFIX}/pipeline/run.py"],

    # ── Pipeline step handlers ──
    "test_audit_step_verdict*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/audit_utils.py"],
    "test_review_selfcheck*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/review_selfcheck/handler.py"],
    "test_python_unit_step*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/test_python_unit.py"],
    "test_h3_changeset*.py": [f"{SRC_PREFIX}/pipeline/llm_gateway.py"],

    # ── Spec ──
    "test_spec_validate*.py": [f"{SRC_PREFIX}/spec/validate.py"],
    "test_spec_changes*.py": [f"{SRC_PREFIX}/spec/changes.py"],
    "test_spec_diff*.py": [f"{SRC_PREFIX}/spec/diff.py"],
    "test_spec_merge*.py": [f"{SRC_PREFIX}/spec/merge.py"],
    "test_spec_patterns*.py": [f"{SRC_PREFIX}/spec/patterns.py"],
    "test_spec_version*.py": [f"{SRC_PREFIX}/spec/version.py"],
    "test_spec_*.py": [f"{SRC_PREFIX}/spec/validate.py"],
    "test_openspec*.py": [f"{SRC_PREFIX}/spec/validate.py"],

    # ── CI ──
    "test_ci_*.py": [f"{SRC_PREFIX}/ci/run.py"],
    "test_ci*.py": [f"{SRC_PREFIX}/ci/run.py"],
    "test_honesty*.py": [f"{SRC_PREFIX}/ci/honesty_gate.py"],
    "test_gate_policy*.py": [f"{SRC_PREFIX}/ci/gate_policy.py"],
    "test_coverage_*.py": [f"{SRC_PREFIX}/ci/coverage_pipeline.py"],
    "test_misra_*.py": [f"{SRC_PREFIX}/ci/misra_fusion.py"],
    "test_profile*.py": [f"{SRC_PREFIX}/ci/profile.py"],

    # ── Review ──
    "test_review_*.py": [f"{SRC_PREFIX}/review/run.py"],
    "test_review_tracker*.py": [f"{SRC_PREFIX}/review/tracker.py"],

    # ── ALM / Traceability ──
    "test_alm_*.py": [f"{SRC_PREFIX}/alm/traceability.py"],
    "test_traceability*.py": [f"{SRC_PREFIX}/alm/traceability.py"],
    "test_audit_traceability*.py": [f"{SRC_PREFIX}/alm/traceability.py"],
    "test_req_annotation*.py": [f"{SRC_PREFIX}/alm/traceability.py"],
    "test_traceability_config*.py": [f"{SRC_PREFIX}/alm/traceability_config.py"],

    # ── Evidence ──
    "test_evidence_*.py": [f"{SRC_PREFIX}/evidence/generator.py"],
    "test_evidence*.py": [f"{SRC_PREFIX}/evidence/generator.py"],

    # ── SIL / Adapter ──
    "test_sil_*.py": [f"{SRC_PREFIX}/sil/adapter.py"],
    "test_sil*.py": [f"{SRC_PREFIX}/sil/adapter.py"],
    "test_adapter_*.py": [f"{SRC_PREFIX}/adapter/dspace_adapter.py"],
    "test_cross_*.py": [f"{SRC_PREFIX}/cross/sil_assert.py"],

    # ── API ──
    "test_api_auth*.py": [f"{SRC_PREFIX}/api/auth.py"],
    "test_api_pipeline*.py": [f"{SRC_PREFIX}/api/pipeline.py"],
    "test_api_evidence*.py": [f"{SRC_PREFIX}/api/evidence.py"],
    "test_api_ci*.py": [f"{SRC_PREFIX}/api/ci.py"],
    "test_api_compliance*.py": [f"{SRC_PREFIX}/api/compliance.py"],
    "test_api_audit*.py": [f"{SRC_PREFIX}/api/audit.py"],
    "test_api_dashboard*.py": [f"{SRC_PREFIX}/api/dashboard.py"],
    "test_api_demo*.py": [f"{SRC_PREFIX}/api/demo.py"],
    "test_api_apikeys*.py": [f"{SRC_PREFIX}/api/apikeys.py"],
    "test_api_artifacts*.py": [f"{SRC_PREFIX}/api/artifacts.py"],
    "test_api_device*.py": [f"{SRC_PREFIX}/api/device_ui.py"],
    "test_api_*.py": [f"{SRC_PREFIX}/api/pipeline.py"],
    "test_api.py": [f"{SRC_PREFIX}/api/pipeline.py"],

    # ── LLM ──
    "test_llm_client*.py": [f"{SRC_PREFIX}/llm/client.py"],
    "test_llm_fallback*.py": [f"{SRC_PREFIX}/llm/fallback.py"],
    "test_llm_*.py": [f"{SRC_PREFIX}/llm/client.py"],

    # ── Memory / KB ──
    "test_memory_*.py": [f"{SRC_PREFIX}/memory/store.py"],
    "test_memory*.py": [f"{SRC_PREFIX}/memory/store.py"],
    "test_kb_*.py": [f"{SRC_PREFIX}/kb/store.py"],
    "test_codegen_failures*.py": [f"{SRC_PREFIX}/kb/codegen_failures.py"],
    "test_rule_sink*.py": [f"{SRC_PREFIX}/memory/rule_sink.py"],

    # ── Knowledge Graph ──
    "test_knowledge_graph*.py": [f"{SRC_PREFIX}/knowledge_graph/store.py"],
    "test_kg_*.py": [f"{SRC_PREFIX}/knowledge_graph/store.py"],

    # ── Codegen ──
    "test_codegen_*.py": [f"{SRC_PREFIX}/codegen/engine.py"],
    "test_layered_codegen*.py": [f"{SRC_PREFIX}/codegen/layered.py"],

    # ── Preview ──
    "test_preview_*.py": [f"{SRC_PREFIX}/preview/analyzer.py"],
    "test_preview*.py": [f"{SRC_PREFIX}/preview/analyzer.py"],

    # ── Tenant / RBAC ──
    "test_tenant*.py": [f"{SRC_PREFIX}/tenant/model.py"],
    "test_rbac*.py": [f"{SRC_PREFIX}/rbac/model.py"],
    "test_auth*.py": [f"{SRC_PREFIX}/api/auth.py"],

    # ── Audit ──
    "test_audit_*.py": [f"{SRC_PREFIX}/audit/model.py"],
    "test_audit*.py": [f"{SRC_PREFIX}/audit/model.py"],

    # ── Compliance ──
    "test_compliance*.py": [f"{SRC_PREFIX}/compliance/compliance_checker.py"],

    # ── Billing / Usage ──
    "test_billing*.py": [f"{SRC_PREFIX}/billing/metering.py"],
    "test_stripe*.py": [f"{SRC_PREFIX}/billing/metering.py"],
    "test_usage*.py": [f"{SRC_PREFIX}/usage/metering.py"],

    # ── Loop Engine ──
    "test_loop_*.py": [f"{SRC_PREFIX}/loop_engine/spec_delta_gen.py"],
    "test_spec_delta*.py": [f"{SRC_PREFIX}/loop_engine/spec_delta_gen.py"],

    # ── Test case gen ──
    "test_case_gen*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/test_case_gen.py"],

    # ── Consistency / Baseline ──
    "test_consistency*.py": [f"{SRC_PREFIX}/cli/commands/consistency.py"],
    "test_baseline*.py": [f"{SRC_PREFIX}/pipeline/step_cache.py"],

    # ── Template golden ──
    "test_template_golden*.py": [f"{SRC_PREFIX}/templates/golden.py"],

    # ── Entry / CLI ──
    "test_entry*.py": [f"{SRC_PREFIX}/_entry.py"],
    "test_cli*.py": [f"{SRC_PREFIX}/cli/main.py"],
    "test_max_import*.py": [f"{SRC_PREFIX}/__init__.py"],

    # ── Integration / E2E ──
    "test_alpha*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_e2e*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_integration*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_pipeline_engine*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_review_engine*.py": [f"{SRC_PREFIX}/review/run.py"],
    "test_spec_engine*.py": [f"{SRC_PREFIX}/spec/validate.py"],
    "test_full_flow*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],

    # ── Misc ──
    "test_agent_*.py": [f"{SRC_PREFIX}/agent_registry.py"],
    "test_plugins*.py": [f"{SRC_PREFIX}/plugins/registry.py"],
    "test_sandbox*.py": [f"{SRC_PREFIX}/plugins/sandbox.py"],
    "test_hooks*.py": [f"{SRC_PREFIX}/hooks/"],
    "test_skills*.py": [f"{SRC_PREFIX}/skills/registry.py"],
    "test_store*.py": [f"{SRC_PREFIX}/store.py"],
    "test_server*.py": [f"{SRC_PREFIX}/api/dashboard.py"],
    "test_methodology*.py": [f"{SRC_PREFIX}/cli/main.py"],

    # ── Autosar ──
    "test_autosar_*.py": [f"{SRC_PREFIX}/autosar/"],

    # ── CI extras ──
    "test_build_metadata*.py": [f"{SRC_PREFIX}/ci/build_metadata.py"],
    "test_diff_planner*.py": [f"{SRC_PREFIX}/ci/diff_planner.py"],
    "test_gcov*.py": [f"{SRC_PREFIX}/ci/gcov_coverage.py"],
    "test_stages_deep*.py": [f"{SRC_PREFIX}/ci/stage_utils.py"],
    "test_verify_c_coverage*.py": [f"{SRC_PREFIX}/ci/verify_c_coverage_gate.py"],
    "test_final_coverage*.py": [f"{SRC_PREFIX}/ci/coverage_pipeline.py"],
    "test_quick_cover*.py": [f"{SRC_PREFIX}/ci/coverage_pipeline.py"],
    "test_mock_gate*.py": [f"{SRC_PREFIX}/ci/honesty_gate.py"],
    "test_phase0_coverage*.py": [f"{SRC_PREFIX}/ci/coverage_pipeline.py"],

    # ── Review extras ──
    "test_c_review*.py": [f"{SRC_PREFIX}/review/c_review.py"],
    "test_stack_review*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/review_stack.py"],
    "test_mmio_review*.py": [f"{SRC_PREFIX}/review/c_review.py"],
    "test_round9_review*.py": [f"{SRC_PREFIX}/review/run.py"],

    # ── Hardware / Cross ──
    "test_hardware*.py": [f"{SRC_PREFIX}/hardware/"],
    "test_debugger*.py": [f"{SRC_PREFIX}/hardware/debugger.py"],
    "test_flasher*.py": [f"{SRC_PREFIX}/hardware/flasher.py"],
    "test_flash*.py": [f"{SRC_PREFIX}/cross/flash.py"],
    "test_hil_runner*.py": [f"{SRC_PREFIX}/cross/hil_runner.py"],
    "test_hw_monitor*.py": [f"{SRC_PREFIX}/hardware/monitor.py"],
    "test_serial_monitor*.py": [f"{SRC_PREFIX}/cross/serial_monitor.py"],
    "test_target_config*.py": [f"{SRC_PREFIX}/cross/target_config.py"],
    "test_dspace_adapter*.py": [f"{SRC_PREFIX}/adapter/dspace_adapter.py"],
    "test_vector_adapter*.py": [f"{SRC_PREFIX}/adapter/vector_adapter.py"],

    # ── Pipeline extras ──
    "test_context_guard*.py": [f"{SRC_PREFIX}/pipeline/context_guard.py"],
    "test_container_executor*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_executor_interface*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_external_agents*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/"],
    "test_d2_parallel*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_docker_stability*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_deep_execution*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_production_smoke*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_split_modules*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_targeted_exec*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_stress_100k*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_prompts*.py": [f"{SRC_PREFIX}/pipeline/prompts.py"],
    "test_checkpoint_session*.py": [f"{SRC_PREFIX}/pipeline/session.py"],
    "test_engine_checkpoint*.py": [f"{SRC_PREFIX}/engine/"],
    "test_prd_*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/review_prd.py"],
    "test_test_qualification*.py": [f"{SRC_PREFIX}/pipeline/step_handlers/test_qualification.py"],
    "test_h3_confidence*.py": [f"{SRC_PREFIX}/pipeline/llm_gateway.py"],

    # ── Knowledge / Knowledge Graph extras ──
    "test_knowledge_indexer*.py": [f"{SRC_PREFIX}/knowledge_management/"],
    "test_knowledge_management*.py": [f"{SRC_PREFIX}/knowledge_management/"],
    "test_code_scanner*.py": [f"{SRC_PREFIX}/knowledge_graph/code_scanner.py"],
    "test_cm_checks*.py": [f"{SRC_PREFIX}/knowledge_graph/cm_checks.py"],
    "test_merge_gate*.py": [f"{SRC_PREFIX}/knowledge_graph/merge_gate.py"],

    # ── Loop Engine extras ──
    "test_loop2_*.py": [f"{SRC_PREFIX}/loop_engine/"],
    "test_loop3_*.py": [f"{SRC_PREFIX}/loop_engine/"],
    "test_loop4_*.py": [f"{SRC_PREFIX}/loop_engine/"],
    "test_kpi*.py": [f"{SRC_PREFIX}/loop_engine/"],
    "test_rca_engine*.py": [f"{SRC_PREFIX}/loop_engine/"],

    # ── Report ──
    "test_report_*.py": [f"{SRC_PREFIX}/report/"],
    "test_feishu_*.py": [f"{SRC_PREFIX}/report/feishu_notifier.py"],
    "test_notify*.py": [f"{SRC_PREFIX}/notify.py"],

    # ── Plan ──
    "test_plan_*.py": [f"{SRC_PREFIX}/plan/"],

    # ── UI ──
    "test_ui_*.py": [f"{SRC_PREFIX}/ui/"],

    # ── Testgen ──
    "test_testgen*.py": [f"{SRC_PREFIX}/testgen/"],

    # ── Device ──
    "test_device_management*.py": [f"{SRC_PREFIX}/device/"],

    # ── Templates / Evidence extras ──
    "test_templates_*.py": [f"{SRC_PREFIX}/templates/"],
    "test_oem_templates*.py": [f"{SRC_PREFIX}/evidence/oem_templates.py"],

    # ── Auth / Security ──
    "test_jwt_auth*.py": [f"{SRC_PREFIX}/api/auth.py"],
    "test_security*.py": [f"{SRC_PREFIX}/rbac/model.py"],
    "test_ratelimit*.py": [f"{SRC_PREFIX}/api/middleware.py"],

    # ── Project detection ──
    "test_project_detection*.py": [f"{SRC_PREFIX}/project_detection.py"],
    "test_project_venv*.py": [f"{SRC_PREFIX}/project_detection.py"],

    # ── Onboarding ──
    "test_onboard*.py": [f"{SRC_PREFIX}/api/pipeline.py"],

    # ── Perf ──
    "test_perf*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],

    # ── Product ──
    "test_product_v1*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],

    # ── Arch ──
    "test_arch_source_tree*.py": [f"{SRC_PREFIX}/pipeline/repo_facts.py"],

    # ── Gap / Backlog ──
    "test_gap_close*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_backlog_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v070_gaps*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v090_modules*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],

    # ── Version-specific integration tests ──
    "test_v344_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v361_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v370_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v380_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
    "test_v390_*.py": [f"{SRC_PREFIX}/api/dashboard.py"],
    "test_v391_*.py": [f"{SRC_PREFIX}/pipeline/orchestrator.py"],
}

SKIP_PATTERNS = [
    "test_*.pyc",
    "__pycache__",
    "conftest.py",
]


def match_test_file(test_name: str) -> list[str] | None:
    """Find the source file(s) for a test file."""
    import fnmatch
    for pattern, sources in TEST_TO_SRC.items():
        if fnmatch.fnmatch(test_name, pattern):
            return sources
    return None


def add_annotation(filepath: Path, src_files: list[str]) -> bool:
    """Add @tests annotation to a test file. Returns True if modified."""
    content = filepath.read_text()

    parts = []
    for sf in src_files:
        parts.append(f"@tests {sf}")
    annotation = f"# {'  '.join(parts)}"

    if "@tests" in content.split("\n")[0] or (len(content.split("\n")) > 1 and "@tests" in content.split("\n")[1]):
        return False

    if annotation in content:
        return False

    lines = content.split("\n")
    insert_idx = 0

    if lines and (lines[0].startswith("#!") or lines[0].startswith("# -*-")):
        insert_idx = 1

    if len(lines) > insert_idx:
        next_line = lines[insert_idx].strip()
        if next_line.startswith('"""') or next_line.startswith("'''"):
            quote = next_line[:3]
            if next_line.count(quote) >= 2 and len(next_line) > 3:
                insert_idx += 1
            else:
                for i in range(insert_idx + 1, len(lines)):
                    if quote in lines[i]:
                        insert_idx = i + 1
                        break

    new_lines = lines[:insert_idx] + ["", annotation] + lines[insert_idx:]
    filepath.write_text("\n".join(new_lines))
    return True


def main():
    added = 0
    skipped = 0
    unmatched = 0
    unmatched_files = []

    test_files = sorted(TESTS.glob("test_*.py"))

    for tf in test_files:
        if any(tf.name == p for p in SKIP_PATTERNS):
            continue

        src_files = match_test_file(tf.name)
        if src_files is None:
            unmatched += 1
            unmatched_files.append(tf.name)
            continue

        if add_annotation(tf, src_files):
            print(f"  + {tf.name}  →  {src_files}")
            added += 1
        else:
            skipped += 1

    print(f"\nDone: {added} annotated, {skipped} already done, {unmatched} unmatched")
    if unmatched_files:
        print(f"\nUnmatched test files ({len(unmatched_files)}):")
        for f in unmatched_files[:20]:
            print(f"  - {f}")
        if len(unmatched_files) > 20:
            print(f"  ... and {len(unmatched_files) - 20} more")


if __name__ == "__main__":
    main()
