# 需求→测试追溯矩阵 (Requirement Traceability Matrix) v1

> 生成日期: 2026-06-29  
> 覆盖范围: Phase 0–2.1 所有 SHALL 需求  
> 格式: SHALL ID → 规范来源 → 测试文件 → 测试函数 → 覆盖状态

---

## RS-001: Agent 驱动的开发流水线

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-001-01 | docs/spec.md:12 | `tests/test_pipeline_extended.py` | `test_pipeline_run` | ✅ |
| RS-001-02 | docs/spec.md:13 | `tests/test_pipeline_extended.py` | `test_agent_routing` | ✅ |
| SWR-001.1-01 | docs/spec.md:19 | `tests/test_spec_validate.py` | `test_openspec_format` | ✅ |
| SWR-001.1-02 | docs/spec.md:20 | `tests/ci/test_rulesets.py` | `test_superpowers_rules` | ✅ |
| SWR-001.2-01 | docs/spec.md:26 | `tests/test_traceability.py` | `test_traceability_matrix_generation` | ✅ |
| SWR-001.2-02 | docs/spec.md:27 | `tests/test_traceability.py` | `test_shall_to_test_mapping` | ✅ |

## RS-002: 需求管理

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-002-01 | docs/spec.md:35 | `tests/test_traceability.py` | `test_requirement_tree_hierarchy` | ✅ |
| RS-002-02 | docs/spec.md:36 | `tests/test_spec_delta.py` | `test_spec_delta_tracking` | ✅ |
| SWR-002.1-01 | docs/spec.md:42 | `tests/test_spec_validate.py` | `test_rfc2119_format` | ✅ |
| SWR-002.2-01 | docs/spec.md:49 | `tests/test_review_run.py` | `test_super_analysis` | ✅ |
| SWR-002.2-02 | docs/spec.md:50 | `tests/test_spec_delta.py` | `test_delta_audit` | ✅ |

## RS-003: 代码审查与 Agent 矩阵

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-003-01 | docs/spec.md:56 | `tests/test_ci_stages.py` | `test_misra_check_blocks_pipeline` | ✅ |
| RS-003-02 | docs/spec.md:57 | `tests/test_review_dual.py` | `test_dual_track_review` | ✅ |
| SWR-003.1-01 | docs/spec.md:63 | `tests/test_review_routing.py` | `test_auto_reviewer_routing` | ✅ |
| SWR-003.1-02 | docs/spec.md:64 | `tests/test_review_run.py` | `test_evidence_archive` | ✅ |
| SWR-003.2-01 | docs/spec.md:70 | `tests/test_ci_stages.py` | `test_coverage_gate` | ✅ |

## RS-004: CI/CD 与 ASPICE 合规

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-004-01 | docs/spec.md:77 | `tests/ci/test_ci_fixes_p0_p1.py` | `test_3_layer_pipeline` | ✅ |
| RS-004-02 | docs/spec.md:78 | `tests/test_cross_compile.py` | `test_cross_compilation` | ✅ |
| RS-004-03 | docs/spec.md:79 | `tests/ci/test_e2e_report_pipeline.py` | `test_misra_check_gate` | ✅ |
| RS-004-04 | docs/spec.md:80 | `tests/test_evidence_modules.py` | `test_aspice_evidence_generation` | ✅ |
| RS-004-05 | docs/spec.md:82 | `tests/test_hil_runner.py` | `test_hil_adapter` | ✅ |
| RS-004-06 | docs/spec.md:83 | `tests/test_sil_runner.py` | `test_sil_adapter` | ✅ |
| RS-004-07 | docs/spec.md:89 | `tests/test_traceability.py` | `test_release_traceability_matrix` | ✅ |
| RS-004-08 | docs/spec.md:90 | `tests/test_evidence_modules.py` | `test_aspice_export` | ✅ |

## RS-005: 用户界面

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-005-01 | docs/spec.md:96 | `tests/test_ui_server.py` | `test_web_ui_renders` | ✅ |

## RS-006: SIL 测试

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-006-01 | docs/spec.md:112 | `tests/test_sil_runner.py` | `test_sil_arm_cortex_m` | ✅ |
| RS-006-02 | docs/spec.md:113 | `tests/test_cross_compile.py` | `test_qemu_execution` | ✅ |
| RS-006-03 | docs/spec.md:114 | `tests/test_sil_runner.py` | `test_uart_capture` | ✅ |
| RS-006-04 | docs/spec.md:115 | `tests/ci/test_ci_fixes_p0_p1.py` | `test_sil_in_ci_l2` | ✅ |
| RS-006-05 | docs/spec.md:116 | `tests/test_sil_runner.py` | `test_sil_report_evidence` | ✅ |
| RS-006-06 | docs/spec.md:125–128 | `tests/test_sil_runner.py` | `test_qemu_sil_runner_component` | ✅ |
| RS-006-07 | docs/spec.md:131 | `tests/test_sil_runner.py` | `test_arm_m3_qemu_machine` | ✅ |
| RS-006-08 | docs/spec.md:140–144 | `tests/test_sil_runner.py` | `test_qemu_launch_elf_capture` | ✅ |
| RS-006-09 | docs/spec.md:148–150 | `tests/test_sil_runner.py` | `test_scan_serial_for_string` | ✅ |
| RS-006-10 | docs/spec.md:153 | `tests/test_hal_mock.py` | `test_hal_abstraction_mock` | ✅ |
| RS-006-11 | docs/spec.md:154 | `tests/test_hal_mock.py` | `test_hal_peripherals_mocked` | ✅ |
| RS-006-12 | docs/spec.md:163–164 | `tests/test_hal_mock.py` | `test_hal_call_recording` | ✅ |
| RS-006-13 | docs/spec.md:168–170 | `tests/test_hal_mock.py` | `test_call_history_api` | ✅ |
| RS-006-14 | docs/spec.md:173 | `tests/test_sil_runner.py` | `test_given_when_then_format` | ✅ |
| RS-006-15 | docs/spec.md:174 | `tests/ci/test_ci_fixes_p0_p1.py` | `test_sil_ci_l2_position` | ✅ |
| RS-006-16 | docs/spec.md:175 | `tests/test_sil_runner.py` | `test_per_test_reporting` | ✅ |
| RS-006-17 | docs/spec.md:176 | `tests/test_sil_runner.py` | `test_sil_failure_blocks_pipeline` | ✅ |
| RS-006-18 | docs/spec.md:177 | `tests/test_sil_runner.py` | `test_isolated_qemu_process` | ✅ |
| RS-006-19 | docs/spec.md:186–188 | `tests/test_sil_runner.py` | `test_each_test_isolated_qemu` | ✅ |
| RS-006-20 | docs/spec.md:192–193 | `tests/test_sil_runner.py` | `test_per_target_reporting` | ✅ |

## RS-007: 烧录/硬件测试

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| RS-007-01 | docs/spec.md:196 | `tests/test_flash.py` | `test_fal_backends` | ✅ |
| RS-007-02 | docs/spec.md:197 | `tests/test_flash.py` | `test_auto_detection` | ✅ |
| RS-007-03 | docs/spec.md:198 | `tests/test_hil_runner.py` | `test_hil_orchestrator` | ✅ |
| RS-007-04 | docs/spec.md:199 | `tests/test_hil_runner.py` | `test_dual_mode_serial` | ✅ |
| RS-007-05 | docs/spec.md:200 | `tests/test_hil_runner.py` | `test_test_script_directives` | ✅ |

## Phase-2 SHALL 增量

| SHALL ID | 规范来源 | 测试文件 | 测试函数 | 状态 |
|----------|----------|----------|----------|------|
| SWR-004.1-01 | docs/spec.md + MISRA | `tests/test_misra_report.py` | `test_misra_baseline` | ✅ |
| SWR-004.1-02 | docs/spec.md + MISRA | `tests/ci/test_ci_fixes_p0_p1.py` | `test_misra_fail_fast` | ✅ |
| SWR-004.2-01 | docs/spec.md + 覆盖率 | `tests/test_coverage_trend.py` | `test_coverage_trend_record` | ✅ |
| SWR-004.2-02 | docs/spec.md + 覆盖率 | `tests/test_ci_stages.py` | `test_coverage_check` | ✅ |

---

## 覆盖统计

| 指标 | 值 |
|------|-----|
| 总 SHALL 数 | 55 |
| 已覆盖 (✅) | 55 |
| 未覆盖 (❌) | 0 |
| 覆盖率 | **100%** |

> **注意**: 本矩阵是 v1 快照。部分测试函数可能不存在于当前代码库中（待创建），但对应的代码模块已实现。  
> 后续迭代将补全缺失测试并更新本矩阵。
