# yuleOSH 需求追溯验收矩阵 (Acceptance Matrix — RTM)

> **版本**: v1.0.0 | **生成时间**: 2026-06-19T15:11:20
> **维护人**: 小克 (自动生成)
> **数据源**: `.yuleosh/reports/traceability-report.json`

---

## 全局统计

| 指标 | 值 |
|:-----|:---:|
| SHALL 总数 | 184 |
| 已覆盖 | 128 |
| 未覆盖 | 56 |
| **覆盖率** | **70.1%** |
| 状态 | ✅ PASS (≥50%) |

---

## 模块级详细

| # | 需求 ID | 模块名称 | SHALL 数 | 已覆盖 | 覆盖率 | 状态 |
|:-:|:--------|:---------|:--------:|:------:|:------:|:----:|
| 1 | RS-001 | — | 2 | 2 | 100.0% | ✅ |
| 2 | RS-002 | — | 2 | 2 | 100.0% | ✅ |
| 3 | RS-003 | — | 2 | 2 | 100.0% | ✅ |
| 4 | RS-004 | — | 6 | 6 | 100.0% | ✅ |
| 5 | RS-005 | — | 2 | 2 | 100.0% | ✅ |
| 6 | RS-006 | — | 1 | 1 | 100.0% | ✅ |
| 7 | RS-007 | — | 1 | 1 | 100.0% | ✅ |
| 8 | RS-008 | — | 5 | 5 | 100.0% | ✅ |
| 9 | RS-009 | — | 5 | 5 | 100.0% | ✅ |
| 10 | RS-010 | — | 5 | 5 | 100.0% | ✅ |
| 11 | RS-011 | — | 5 | 5 | 100.0% | ✅ |
| 12 | RS-012 | — | 6 | 6 | 100.0% | ✅ |
| 13 | RS-013 | — | 1 | 1 | 100.0% | ✅ |
| 14 | SWR-001.1 | — | 2 | 2 | 100.0% | ✅ |
| 15 | SWR-001.2 | — | 2 | 2 | 100.0% | ✅ |
| 16 | SWR-002.1 | — | 1 | 1 | 100.0% | ✅ |
| 17 | SWR-002.2 | — | 2 | 2 | 100.0% | ✅ |
| 18 | SWR-003.1 | — | 2 | 2 | 100.0% | ✅ |
| 19 | SWR-003.2 | — | 1 | 1 | 100.0% | ✅ |
| 20 | SWR-008.1 | — | 2 | 2 | 100.0% | ✅ |
| 21 | SWR-008.2 | — | 2 | 2 | 100.0% | ✅ |
| 22 | SWR-008.3 | — | 5 | 5 | 100.0% | ✅ |
| 23 | SWR-009.1 | — | 8 | 8 | 100.0% | ✅ |
| 24 | SWR-009.2 | — | 5 | 5 | 100.0% | ✅ |
| 25 | SWR-009.3 | — | 5 | 5 | 100.0% | ✅ |
| 26 | SWR-010.1 | — | 5 | 5 | 100.0% | ✅ |
| 27 | SWR-010.2 | — | 5 | 5 | 100.0% | ✅ |
| 28 | SWR-010.3 | — | 7 | 7 | 100.0% | ✅ |
| 29 | SWR-011.1 | — | 2 | 2 | 100.0% | ✅ |
| 30 | SWR-011.2 | — | 5 | 5 | 100.0% | ✅ |
| 31 | SWR-012.1 | — | 5 | 5 | 100.0% | ✅ |
| 32 | SWR-012.2 | — | 4 | 4 | 100.0% | ✅ |
| 33 | SWR-013.1 | — | 6 | 6 | 100.0% | ✅ |
| 34 | SWR-013.2 | — | 5 | 5 | 100.0% | ✅ |
| 35 | SWR-013.3 | — | 5 | 5 | 100.0% | ✅ |
| 36 | SWR-014.1 | — | 3 | 0 | 0.0% | 🔴 |
| 37 | SWR-014.2 | — | 2 | 0 | 0.0% | 🔴 |
| 38 | SWR-014.3 | — | 50 | 0 | 0.0% | 🔴 |

---

## 需求→测试映射详情

| # | 需求 ID | SHALL 语句 (截取) | 覆盖 | 测试文件 |
|:-:|:--------|:-----------------|:----:|:---------|
| 1 | RS-001 | The system SHALL support an SDD → DDD → TDD → CI/CD pip | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_evidence_edge.py; /Users/ste... |
| 2 | RS-001 | The system SHALL route tasks through the Harness Engine | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_evidence_edge.py; /Users/ste... |
| 3 | SWR-001.1 | The system SHALL support the OpenSpec specification for | ✅ | tests/test_e2e.py; tests/test_spec_engine.py; tests/test_pipeline_engine.py; tests/test... |
| 4 | SWR-001.1 | The system SHALL enforce Superpowers 14 Rules at each p | ✅ | tests/test_e2e.py; tests/test_spec_engine.py; tests/test_pipeline_engine.py; tests/test... |
| 5 | SWR-001.2 | The system SHALL generate a test plan with requirement  | ✅ | tests/test_evidence_engine.py; tests/test_spec_v03_it2.py; /Users/stefan/.openclaw/work... |
| 6 | SWR-001.2 | The system SHALL map every SHALL statement to at least  | ✅ | tests/test_evidence_engine.py; tests/test_spec_v03_it2.py; /Users/stefan/.openclaw/work... |
| 7 | RS-002 | The system SHALL provide a requirements tree hierarchy  | ✅ | tests/test_deep_execution.py; tests/test_pipeline_engine.py; /Users/stefan/.openclaw/wo... |
| 8 | RS-002 | The system SHALL support spec-delta tracking for requir | ✅ | tests/test_deep_execution.py; tests/test_pipeline_engine.py; /Users/stefan/.openclaw/wo... |
| 9 | SWR-002.1 | The system SHALL support OpenSpec RFC 2119 format for a | ✅ | tests/test_deep_execution.py; tests/test_spec_coverage_boost.py |
| 10 | SWR-002.2 | The system SHALL support S.U.P.E.R startup analysis for | ✅ | tests/test_pipeline_engine.py; tests/test_spec_v03_it2.py |
| 11 | SWR-002.2 | The system SHALL track delta between requirement versio | ✅ | tests/test_pipeline_engine.py; tests/test_spec_v03_it2.py |
| 12 | RS-003 | The system SHALL support per-task blocking review by AI | ✅ | tests/test_spec_v03_it2.py; tests/test_review_engine.py; /Users/stefan/.openclaw/worksp... |
| 13 | RS-003 | The system SHALL support dual-track review (non-blockin | ✅ | tests/test_spec_v03_it2.py; tests/test_review_engine.py; /Users/stefan/.openclaw/worksp... |
| 14 | SWR-003.1 | The system SHALL support auto-reviewer routing based on | ✅ | tests/test_review_engine_extended.py |
| 15 | SWR-003.1 | The system SHALL archive all agent review records as JS | ✅ | tests/test_review_engine_extended.py |
| 16 | SWR-003.2 | The system SHALL support coverage-guardian with configu | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 17 | RS-004 | The system SHALL provide a 3-layer CI/CD pipeline (Dev  | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 18 | RS-004 | The system SHALL support cross-compilation for ARM/RISC | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 19 | RS-004 | The system SHALL support MISRA-C/C++ static analysis ga | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 20 | RS-004 | The system SHALL auto-generate ASPICE compliance eviden | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 21 | RS-004 | The system SHALL support HIL (Hardware-in-the-Loop) ada | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 22 | RS-004 | The system SHALL support SIL (Software-in-the-Loop) ada | ✅ | tests/test_sil_runner.py; tests/test_evidence_engine.py; tests/test_hil_runner.py; test... |
| 23 | RS-005 | The system SHALL generate a traceability matrix (Req ↔  | ✅ | tests/test_traceability.py; tests/test_spec_v03_it2.py; tests/test_evidence_engine.py; ... |
| 24 | RS-005 | The system SHALL export a compliance pack for ASPICE au | ✅ | tests/test_traceability.py; tests/test_spec_v03_it2.py; tests/test_evidence_engine.py; ... |
| 25 | RS-006 | The system SHALL provide a Web UI for project managemen | ✅ | tests/test_server_integration.py; tests/test_ui_auth_smoke.py |
| 26 | RS-007 | The system SHALL support single-tenant deployment for M | ✅ | tests/test_jwt_auth.py; tests/test_auth_extended.py |
| 27 | RS-008 | The system SHALL support Software-in-the-Loop (SIL) tes | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py; tests/test_cross_sil_assert_deep.py |
| 28 | RS-008 | The system SHALL execute the cross-compiled production  | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py; tests/test_cross_sil_assert_deep.py |
| 29 | RS-008 | The system SHALL capture UART and semihosting output fr | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py; tests/test_cross_sil_assert_deep.py |
| 30 | RS-008 | The system SHALL integrate SIL tests into CI L2 as a bl | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py; tests/test_cross_sil_assert_deep.py |
| 31 | RS-008 | The system SHALL generate a SIL test report in the comp | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py; tests/test_cross_sil_assert_deep.py |
| 32 | SWR-008.1 | The system SHALL provide a `qemu-sil-runner` component  | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py |
| 33 | SWR-008.1 | The system SHALL support ARM Cortex-M3/M4 QEMU machines | ✅ | tests/test_sil_runner.py; tests/test_sil_smoke.py |
| 34 | SWR-008.2 | The system SHALL provide a HAL abstraction mock layer f | ✅ | tests/test_sil_runner.py; tests/test_cross_sil_assert_deep.py |
| 35 | SWR-008.2 | The system SHALL support HAL mocking for at least: UART | ✅ | tests/test_sil_runner.py; tests/test_cross_sil_assert_deep.py |
| 36 | SWR-008.3 | The system SHALL require each SIL test to use GIVEN/WHE | ✅ | tests/test_sil_runner.py |
| 37 | SWR-008.3 | The system SHALL execute SIL tests as a dedicated CI L2 | ✅ | tests/test_sil_runner.py |
| 38 | SWR-008.3 | The system SHALL report SIL test results in the complia | ✅ | tests/test_sil_runner.py |
| 39 | SWR-008.3 | A SIL test failure SHALL block the CI pipeline (L2 bloc | ✅ | tests/test_sil_runner.py |
| 40 | SWR-008.3 | The system SHALL isolate each SIL test in its own QEMU  | ✅ | tests/test_sil_runner.py |
| 41 | RS-009 | The system SHALL provide a Flash Abstraction Layer (FAL | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 42 | RS-009 | The system SHALL support auto-detection of available fl | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 43 | RS-009 | The system SHALL provide a Hardware-in-the-Loop (HIL) t | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 44 | RS-009 | The system SHALL support dual-mode serial capture: phys | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 45 | RS-009 | The system SHALL support test script execution with exp | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 46 | SWR-009.1 | The system SHALL provide abstract `FlashTool` base clas | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 47 | SWR-009.1 | The system SHALL provide concrete implementations: `Ope | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 48 | SWR-009.1 | The system SHALL provide a `FlashRunner` facade that au | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 49 | SWR-009.1 | FlashRunner SHALL support a preferred-tool override via | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 50 | SWR-009.1 | FlashRunner SHALL attempt fallback tools in order (Open | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 51 | SWR-009.1 | Each runner SHALL return a `FlashResult` dataclass with | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 52 | SWR-009.1 | The system SHALL provide `flash_firmware()` and `detect | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 53 | SWR-009.1 | Flash tools SHALL be configured per target in `.yuleosh | ✅ | tests/test_cross_flash_deep.py; /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/t... |
| 54 | SWR-009.2 | The system SHALL provide a `SerialMonitor` class for ph | ✅ | tests/test_hw_monitor_deep.py; tests/test_cross_monitor_deep.py; tests/test_serial_moni... |
| 55 | SWR-009.2 | The system SHALL provide a `PipeSerialMonitor` class fo | ✅ | tests/test_hw_monitor_deep.py; tests/test_cross_monitor_deep.py; tests/test_serial_moni... |
| 56 | SWR-009.2 | Both monitor variants SHALL support: | ✅ | tests/test_hw_monitor_deep.py; tests/test_cross_monitor_deep.py; tests/test_serial_moni... |
| 57 | SWR-009.2 | The monitors SHALL run background capture threads with  | ✅ | tests/test_hw_monitor_deep.py; tests/test_cross_monitor_deep.py; tests/test_serial_moni... |
| 58 | SWR-009.2 | The monitors SHALL raise `SerialMonitorTimeout` on patt | ✅ | tests/test_hw_monitor_deep.py; tests/test_cross_monitor_deep.py; tests/test_serial_moni... |
| 59 | SWR-009.3 | The system SHALL provide a `HilTestRunner` class orches | ✅ | tests/test_hil_runner_deep_v2.py; tests/test_hil_runner.py |
| 60 | SWR-009.3 | The system SHALL return results as a `HilTestResult` da | ✅ | tests/test_hil_runner_deep_v2.py; tests/test_hil_runner.py |
| 61 | SWR-009.3 | The system SHALL support a test script syntax with dire | ✅ | tests/test_hil_runner_deep_v2.py; tests/test_hil_runner.py |
| 62 | SWR-009.3 | The system SHALL provide shortcut methods: `flash_and_e | ✅ | tests/test_hil_runner_deep_v2.py; tests/test_hil_runner.py |
| 63 | SWR-009.3 | The system SHALL provide `hil_test()` one-shot convenie | ✅ | tests/test_hil_runner_deep_v2.py; tests/test_hil_runner.py |
| 64 | RS-011 | The system SHALL provide a Template Gallery of pre-buil | ✅ | tests/test_cli_smoke.py; tests/test_cli_template_deep.py |
| 65 | RS-011 | The system SHALL store built-in templates under `yuleos | ✅ | tests/test_cli_smoke.py; tests/test_cli_template_deep.py |
| 66 | RS-011 | Each template SHALL contain at minimum: `template.yaml` | ✅ | tests/test_cli_smoke.py; tests/test_cli_template_deep.py |
| 67 | RS-011 | The template manifest (`template.yaml`) SHALL include:  | ✅ | tests/test_cli_smoke.py; tests/test_cli_template_deep.py |
| 68 | RS-011 | The system SHALL support at least 5 template directorie | ✅ | tests/test_cli_smoke.py; tests/test_cli_template_deep.py |
| 69 | SWR-011.1 | The system SHALL search for templates in priority order | ✅ | tests/test_cli_template_deep.py |
| 70 | SWR-011.1 | User-local templates SHALL supplement (not replace) bui | ✅ | tests/test_cli_template_deep.py |
| 71 | SWR-011.2 | The system SHALL support CLI command `yuleosh project i | ✅ | tests/test_cli_template_deep.py |
| 72 | SWR-011.2 | The system SHALL support CLI command `yuleosh template  | ✅ | tests/test_cli_template_deep.py |
| 73 | SWR-011.2 | `project init` SHALL create: docs/spec.md, pipeline/con | ✅ | tests/test_cli_template_deep.py |
| 74 | SWR-011.2 | When `--template` is omitted, the system SHALL enter in | ✅ | tests/test_cli_template_deep.py |
| 75 | SWR-011.2 | The init command SHALL NOT overwrite existing files unl | ✅ | tests/test_cli_template_deep.py |
| 76 | RS-012 | The system SHALL provide a "Try Demo" button on the lan | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 77 | RS-012 | The system SHALL expose `GET /api/demo/pipeline` endpoi | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 78 | RS-012 | The demo endpoint SHALL NOT require authentication or L | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 79 | RS-012 | The system SHALL provide a `/demo` frontend page with a | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 80 | RS-012 | The demo SHALL be rate-limited to 10 requests per minut | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 81 | RS-012 | The demo experience SHALL be fully functional without u | ✅ | tests/test_ui_server_smoke.py; tests/test_api.py; tests/test_api_smoke.py |
| 82 | SWR-012.1 | The `GET /api/demo/pipeline` endpoint SHALL return JSON | ✅ | tests/test_api.py; tests/test_api_smoke.py |
| 83 | SWR-012.1 | The endpoint SHALL accept `?step=N` to return partial r | ✅ | tests/test_api.py; tests/test_api_smoke.py |
| 84 | SWR-012.1 | The server SHALL validate demo readiness via `YULEOSH_D | ✅ | tests/test_api.py; tests/test_api_smoke.py |
| 85 | SWR-012.1 | Mock steps SHALL include: Spec Parsing, Requirements An | ✅ | tests/test_api.py; tests/test_api_smoke.py |
| 86 | SWR-012.1 | The server SHALL expose `GET /api/demo/evidence/<pipeli | ✅ | tests/test_api.py; tests/test_api_smoke.py |
| 87 | SWR-012.2 | The `/demo` page SHALL display all 10 pipeline steps wi | ✅ | tests/test_ui_server_smoke.py |
| 88 | SWR-012.2 | The page SHALL show expandable step details (output sum | ✅ | tests/test_ui_server_smoke.py |
| 89 | SWR-012.2 | After completion, the page SHALL display: final report, | ✅ | tests/test_ui_server_smoke.py |
| 90 | SWR-012.2 | The page SHALL NOT require authentication before showin | ✅ | tests/test_ui_server_smoke.py |
| 91 | RS-013 | The system SHALL accept project analysis requests via ` | ✅ | tests/test_preview_analyzer.py |
| 92 | SWR-013.1 | ZIP uploads SHALL be limited to 50 MB; invalid ZIPs ret | ✅ | tests/test_preview_analyzer.py |
| 93 | SWR-013.1 | Git URLs SHALL support GitHub, GitLab, Bitbucket; unsup | ✅ | tests/test_preview_analyzer.py |
| 94 | SWR-013.1 | Clone timeout SHALL be 120 seconds; timeout returns HTT | ✅ | tests/test_preview_analyzer.py |
| 95 | SWR-013.1 | Cloned repos SHALL be limited to 200 MB; excess returns | ✅ | tests/test_preview_analyzer.py |
| 96 | SWR-013.1 | The system SHALL provide `GET /api/preview/assess/<prev | ✅ | tests/test_preview_analyzer.py |
| 97 | SWR-013.1 | Extracted files SHALL be scanned for supported extensio | ✅ | tests/test_preview_analyzer.py |
| 98 | SWR-013.2 | The coverage prediction SHALL estimate line coverage ba | ✅ | tests/test_preview_analyzer.py |
| 99 | SWR-013.2 | The prediction SHALL include: current_coverage_estimate | ✅ | tests/test_preview_analyzer.py |
| 100 | SWR-013.2 | The compliance risk SHALL analyze: MISRA-C violations,  | ✅ | tests/test_preview_analyzer.py |
| 101 | SWR-013.2 | Risk factors SHALL include: risk_level, description, oc | ✅ | tests/test_preview_analyzer.py |
| 102 | SWR-013.2 | The recommended pipeline config SHALL include: recommen | ✅ | tests/test_preview_analyzer.py |
| 103 | SWR-013.3 | Unauthenticated users SHALL be limited to 3 preview ass | ✅ | tests/test_preview_analyzer.py; tests/test_api.py |
| 104 | SWR-013.3 | Authenticated users SHALL have a limit of 20 per 24 hou | ✅ | tests/test_preview_analyzer.py; tests/test_api.py |
| 105 | SWR-013.3 | Rate limit exceeded SHALL return HTTP 429 | ✅ | tests/test_preview_analyzer.py; tests/test_api.py |
| 106 | SWR-013.3 | Preview results SHALL be retained for 24 hours, after w | ✅ | tests/test_preview_analyzer.py; tests/test_api.py |
| 107 | SWR-013.3 | Cloned repositories SHALL be cleaned up within 30 minut | ✅ | tests/test_preview_analyzer.py; tests/test_api.py |
| 108 | SWR-014.1 | The system SHALL support user registration via name/ema | ❌ | — |
| 109 | SWR-014.1 | After registration the system SHALL auto-create a free  | ❌ | — |
| 110 | SWR-014.1 | The system SHALL return a JWT token for password-less f | ❌ | — |
| 111 | SWR-014.2 | The system SHALL allow users to view current subscripti | ❌ | — |
| 112 | SWR-014.2 | The system SHALL support upgrade from Trial to Pro plan | ❌ | — |
| 113 | SWR-014.3 | The system SHALL use Stripe Checkout for paid upgrade p | ❌ | — |
| 114 | SWR-014.3 | The system SHALL support creating and managing subscrip | ❌ | — |
| 115 | SWR-014.3 | After successful payment the system SHALL update the us | ❌ | — |
| 116 | SWR-014.3 | THEN the system SHALL generate a startup-analysis.md | ❌ | — |
| 117 | SWR-014.3 | AND the system SHALL auto-decompose into tasks with kin | ❌ | — |
| 118 | SWR-014.3 | AND the system SHALL create isolated worktrees for each | ❌ | — |
| 119 | SWR-014.3 | AND the system SHALL execute TDD (RED→GREEN→REFACTOR) p | ❌ | — |
| 120 | SWR-014.3 | AND each task SHALL pass per-task blocking review befor | ❌ | — |
| 121 | SWR-014.3 | THEN Layer 1 CI SHALL run unit tests + coverage gate | ❌ | — |
| 122 | SWR-014.3 | AND Layer 2 CI SHALL run cross-compilation + static ana | ❌ | — |
| 123 | SWR-014.3 | AND upon release tag, Layer 3 CD SHALL run system tests | ❌ | — |
| 124 | SWR-014.3 | THEN the system SHALL track the diff in spec-delta.md | ❌ | — |
| 125 | SWR-014.3 | AND the system SHALL re-evaluate affected tasks and tes | ❌ | — |
| 126 | SWR-014.3 | THEN the system SHALL execute each SIL test in an isola | ❌ | — |
| 127 | SWR-014.3 | AND the system SHALL assert serial output against expec | ❌ | — |
| 128 | SWR-014.3 | AND the system SHALL generate a sil-test-report.json wi | ❌ | — |
| 129 | SWR-014.3 | AND a failure in any SIL test SHALL block the pipeline | ❌ | — |
| 130 | SWR-014.3 | AND the report SHALL be bundled into the compliance evi | ❌ | — |
| 131 | SWR-014.3 | THEN the mock SHALL record all HAL invocations without  | ❌ | — |
| 132 | SWR-014.3 | AND the developer SHALL write test assertions against t | ❌ | — |
| 133 | SWR-014.3 | THEN the system SHALL auto-detect the appropriate flash | ❌ | — |
| 134 | SWR-014.3 | AND the system SHALL flash the firmware via the detecte | ❌ | — |
| 135 | SWR-014.3 | AND the system SHALL open serial connection to the targ | ❌ | — |
| 136 | SWR-014.3 | AND the system SHALL assert serial output against expec | ❌ | — |
| 137 | SWR-014.3 | AND the system SHALL return a HIL test result with pass | ❌ | — |
| 138 | SWR-014.3 | THEN the system SHALL automatically retry with the next | ❌ | — |
| 139 | SWR-014.3 | AND the system SHALL continue with serial verification  | ❌ | — |
| 140 | SWR-014.3 | THEN the system SHALL create a complete project skeleto | ❌ | — |
| 141 | SWR-014.3 | AND the generated spec SHALL contain pre-populated Zeph | ❌ | — |
| 142 | SWR-014.3 | AND the generated pipeline config SHALL include Zephyr- | ❌ | — |
| 143 | SWR-014.3 | THEN the system SHALL display an interactive numbered l | ❌ | — |
| 144 | SWR-014.3 | THEN the system SHALL navigate to `/demo` without requi | ❌ | — |
| 145 | SWR-014.3 | AND the demo page SHALL call `GET /api/demo/pipeline` | ❌ | — |
| 146 | SWR-014.3 | AND the page SHALL animate through 10 pipeline steps wi | ❌ | — |
| 147 | SWR-014.3 | AND after all steps complete, the page SHALL display th | ❌ | — |
| 148 | SWR-014.3 | THEN steps 0-2 SHALL have status "completed" | ❌ | — |
| 149 | SWR-014.3 | AND step 3 SHALL have status "running" | ❌ | — |
| 150 | SWR-014.3 | AND steps 4-9 SHALL have status "pending" | ❌ | — |
| 151 | SWR-014.3 | THEN the system SHALL return HTTP 202 with a preview_id | ❌ | — |
| 152 | SWR-014.3 | AND the system SHALL complete the analysis within 300 s | ❌ | — |
| 153 | SWR-014.3 | AND the user SHALL poll `GET /api/preview/assess/<previ | ❌ | — |
| 154 | SWR-014.3 | AND the final report SHALL include: coverage prediction | ❌ | — |
| 155 | SWR-014.3 | AND the analysis SHALL NOT execute, compile, or flash a | ❌ | — |
| 156 | SWR-014.3 | THEN the server SHALL return HTTP 429 | ❌ | — |
| 157 | SWR-014.3 | The system SHALL provide response within 5s for agent r | ❌ | — |
| 158 | SWR-014.3 | The system SHALL support parallel execution of independ | ❌ | — |
| 159 | SWR-014.3 | The system SHALL gracefully handle agent failures with  | ❌ | — |
| 160 | SWR-014.3 | Each SIL test SHALL have a configurable timeout with a  | ❌ | — |
| 161 | SWR-014.3 | The system SHALL support at least 4 concurrent QEMU ins | ❌ | — |
| 162 | SWR-014.3 | The SIL runner SHALL gracefully handle QEMU process cra | ❌ | — |
| 163 | RS-010 | The system SHALL provide a per-project CI configuration | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_spec_coverage_boost.py; test... |
| 164 | RS-010 | The system SHALL support configurable coverage threshol | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_spec_coverage_boost.py; test... |
| 165 | RS-010 | The system SHALL provide a CI Layer 2.5 (Hardware-in-th | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_spec_coverage_boost.py; test... |
| 166 | RS-010 | The system SHALL support mock mode for L2.5 HIL tests i | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_spec_coverage_boost.py; test... |
| 167 | RS-010 | The system SHALL support configurable layer dependency  | ✅ | /Users/stefan/.openclaw/workspace/tasks/yuleOSH/tests/test_spec_coverage_boost.py; test... |
| 168 | SWR-010.1 | The system SHALL store CI configuration in ``.yuleosh/c | ✅ | tests/test_ci_config_smoke.py; tests/test_ci_config.py |
| 169 | SWR-010.1 | The system SHALL support sections for: ci (layers, depe | ✅ | tests/test_ci_config_smoke.py; tests/test_ci_config.py |
| 170 | SWR-010.1 | The system SHALL fall back to safe defaults when the co | ✅ | tests/test_ci_config_smoke.py; tests/test_ci_config.py |
| 171 | SWR-010.1 | The system SHALL fall back to safe defaults with a warn | ✅ | tests/test_ci_config_smoke.py; tests/test_ci_config.py |
| 172 | SWR-010.1 | The system SHALL load the config once and cache it per  | ✅ | tests/test_ci_config_smoke.py; tests/test_ci_config.py |
| 173 | SWR-010.2 | The system SHALL support ``coverage.threshold_line`` in | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 174 | SWR-010.2 | The system SHALL support ``coverage.threshold_condition | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 175 | SWR-010.2 | The system SHALL support ``coverage.strict`` mode (fail | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 176 | SWR-010.2 | The default line coverage threshold SHALL be 85.0% for  | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 177 | SWR-010.2 | The default condition coverage threshold SHALL be 80.0% | ✅ | tests/test_coverage_boost_final.py; tests/test_ci_config.py |
| 178 | SWR-010.3 | The system SHALL provide a ``run_layer_25()`` function  | ✅ | tests/test_ci_layer_25.py |
| 179 | SWR-010.3 | L2.5 SHALL run after L2 passes and before L3 | ✅ | tests/test_ci_layer_25.py |
| 180 | SWR-010.3 | L2.5 SHALL support mock mode where no real hardware is  | ✅ | tests/test_ci_layer_25.py |
| 181 | SWR-010.3 | In mock mode, L2.5 SHALL simulate flash → boot → assert | ✅ | tests/test_ci_layer_25.py |
| 182 | SWR-010.3 | In mock mode, L2.5 SHALL still discover and validate HI | ✅ | tests/test_ci_layer_25.py |
| 183 | SWR-010.3 | L2.5 SHALL accept the CLI argument ``25`` or ``2.5`` | ✅ | tests/test_ci_layer_25.py |
| 184 | SWR-010.3 | L2.5 SHALL produce two report files: | ✅ | tests/test_ci_layer_25.py |

---

## 门禁结果

```
🔍 yuleOSH RTM 门禁验证报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SHALL Coverage:  128/184 = 70.1%
📊 Uncovered SHALLs: 56 (SWR-014.1, SWR-014.2, SWR-014.3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 门禁裁决: PASS — 覆盖率达标
⚠️ 未覆盖需求 (RS-014/SWR-014): Stripe 支付集成 (SaaS 用户生命周期) 需在 v1.1.0 完成
```
