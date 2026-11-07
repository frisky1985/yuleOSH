# 待评审清单（按 ASPICE 过程域）

- 生成时间：2026-11-07T22:49:52
- 真源：`.osh/evidence/traceability-matrix.json`（generated 2026-11-07T22:41:09.117113）
- 评审策略：`review_required=true`，`min_review_coverage_pct=100`，仅独立评审计入覆盖
- 当前独立评审覆盖：0/290（自评审不计入）
- 填表方式：按模板 `docs/templates/independent-review-record.template.json` 创建记录，放入 `docs/evidence/reviews/`，然后运行 `PYTHONPATH=src python3 -m yuleosh.cli.main evidence chain --check`

## 汇总

| 过程域 | 需求数 | 有实现 | 有测试 | 已有评审 | 待独立评审 |
|---|---:|---:|---:|---:|---:|
| SYS.1 | 43 | 43 | 43 | 0 | 43 |
| SYS.2 | 99 | 99 | 99 | 0 | 99 |
| SYS.3 | 8 | 8 | 8 | 0 | 8 |
| SWE.1 | 124 | 124 | 124 | 2 | 122 |
| SWE.2 | 8 | 8 | 8 | 0 | 8 |
| SWE.3 | 8 | 8 | 8 | 0 | 8 |
| **合计** | **290** | | | | |

## SYS.1（43 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `SHALL-170` | The system SHALL verify artifact checksum (SHA-256) after each pipeline stage | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-171` | The system SHALL abort the pipeline if any artifact integrity check fails | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-172` | The system SHALL log integrity failures with stage ID and artifact path | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-173` | The system SHALL execute each pipeline stage in an isolated workspace | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-174` | The system SHALL clean the workspace between pipeline runs | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-175` | The system SHALL reject cross-stage file references that violate stage boundaries | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-176` | The system SHALL reject spec files containing unrecognized syntax constructs | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-177` | The system SHALL validate all SHALL/SHOULD/MAY statements against RFC 2119 grammar | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-178` | The system SHALL reject spec files exceeding a configurable maximum size (default 10 MB) | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-179` | The system SHALL report the exact line and column of any parse error | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-180` | The system SHALL NOT proceed to pipeline execution if spec parsing fails | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-181` | The system SHALL enforce that all configured CI gates execute before any build promotion | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-182` | The system SHALL NOT allow manual override of CI gate results without audit trail | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-183` | The system SHALL record every gate override with user ID, reason, and timestamp | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-184` | The system SHALL compare line/branch coverage against the configured threshold | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-185` | The system SHALL reject coverage data that is incomplete or corrupted | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-186` | The system SHALL require valid JWT bearer tokens for all sensitive API endpoints | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-187` | The system SHALL reject requests with expired, revoked, or malformed tokens | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-188` | The system SHALL log all authentication failures with IP address and timestamp | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-189` | The system SHALL enforce role-based access (admin/member/viewer) for all operations | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-190` | The system SHALL deny write operations for read-only roles | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-191` | The system SHALL deny admin operations for non-admin roles | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-192` | The system SHALL record every API request (method, path, status, IP, duration) | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-193` | The system SHALL record every pipeline execution with stage-level granularity | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-194` | The system SHALL record every CI gate result with pass/fail/error distinction | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-195` | The system SHALL NOT allow deletion of audit log entries | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-196` | The system SHALL retain audit logs for a minimum of 12 months | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-197` | The audit logging system SHALL operate independently of the main request handling | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-198` | The system SHALL generate evidence only from completed, verified pipeline runs | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-199` | The system SHALL include a manifest with SHA-256 checksums for every artifact | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-200` | The system SHALL verify evidence pack integrity on download (manifest checksums) | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-201` | The system SHALL log evidence pack verification results | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-202` | The system SHALL enforce timeout-based termination (default 30s) for all SIL tests | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-203` | The system SHALL isolate each SIL test in its own QEMU process | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-204` | The system SHALL clean up QEMU processes after test completion or timeout | `src/ci/fi_cmd.py`<br>`src/yuleosh/_entry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-205` | The system SHALL verify target connectivity before attempting to flash | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-206` | The system SHALL verify flash integrity (checksum comparison) after programming | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-207` | The system SHALL verify firmware binary checksum before flashing | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-208` | The system SHALL NOT flash firmware with unresolved safety violations | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `STAKE-001` | **STAKE-001**: 干系人要求平台 SHALL 提供从规范、设计、实现、测试到审计证据的自动化开发流程，减少人工合规工作量。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_sys_layer.py`<br>`tests/test_sys_req001_stakeholder_source.py` | 缺失 | [ ] |
| `STAKE-002` | **STAKE-002**: 干系人要求平台 SHALL 建立需求、架构、代码、测试、评审与证据之间的双向追溯关系，并支持审计查询。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_sys_layer.py`<br>`tests/test_sys_req001_stakeholder_source.py` | 缺失 | [ ] |
| `STAKE-003` | **STAKE-003**: 干系人要求平台 SHALL 产出可校验、可复现、防篡改的审计证据包，且不得用示例数据替代项目证据。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `STAKE-004` | **STAKE-004**: 干系人要求平台 SHALL 在多租户环境下隔离租户数据，并对访问、变更与导出操作保留审计记录。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |

## SYS.2（99 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `SHALL-1` | The system SHALL support an SDD → DDD → TDD → CI/CD pipeline orchestrated by AI agents | `src/yuleosh/alm/traceability.py`<br>`src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/loop_engine/test_feedback_handlers.py`<br>… 另有 64 个 | 缺失 | [ ] |
| `SHALL-101` | The system SHALL accept project analysis requests via `POST /api/preview/assess` | `src/yuleosh/preview/analyzer.py`<br>`src/yuleosh/preview/code_parser.py`<br>… 另有 5 个 | `tests/test_preview_analyzer.py`<br>`tests/test_preview_code_parser.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-114` | The system SHALL support user registration via name/email/password | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-115` | After registration the system SHALL auto-create a free Trial project | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-116` | The system SHALL return a JWT token for password-less first login | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-117` | The system SHALL allow users to view current subscription plan and usage | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-118` | The system SHALL support upgrade from Trial to Pro plan via Stripe Checkout | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-122` | The system SHALL maintain a traceability knowledge graph (TKG) linking requirements, code… | `src/yuleosh/kb/codegen_failures.py`<br>`src/yuleosh/kb/store.py`<br>… 另有 10 个 | `tests/test_code_scanner.py`<br>`tests/test_codegen_failures.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-123` | The system SHALL support incremental graph build for CI integration | `src/yuleosh/kb/codegen_failures.py`<br>`src/yuleosh/kb/store.py`<br>… 另有 10 个 | `tests/test_code_scanner.py`<br>`tests/test_codegen_failures.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-124` | The system SHALL support graph snapshots for baseline comparison | `src/yuleosh/kb/codegen_failures.py`<br>`src/yuleosh/kb/store.py`<br>… 另有 10 个 | `tests/test_code_scanner.py`<br>`tests/test_codegen_failures.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-13` | The system SHALL provide a requirements tree hierarchy (SYS → SW → Feature → Scenario → T… | `src/yuleosh/alm/traceability.py`<br>`src/yuleosh/api/requirements.py`<br>… 另有 8 个 | `tests/ci/test_compliance_checker.py`<br>`tests/loop_engine/test_spec_delta_gen.py`<br>… 另有 29 个 | 缺失 | [ ] |
| `SHALL-14` | The system SHALL support spec-delta tracking for requirement changes | `src/yuleosh/alm/traceability.py`<br>`src/yuleosh/api/requirements.py`<br>… 另有 8 个 | `tests/ci/test_compliance_checker.py`<br>`tests/loop_engine/test_spec_delta_gen.py`<br>… 另有 29 个 | 缺失 | [ ] |
| `SHALL-148` | The system SHALL provide response within 5s for agent review tasks | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-149` | The system SHALL support parallel execution of independent pipeline tasks | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-150` | The system SHALL gracefully handle agent failures with retry (max 5 rounds) | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-151` | Each SIL test SHALL have a configurable timeout with a default of 30 seconds | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-152` | The system SHALL support at least 4 concurrent QEMU instances for parallel SIL test execu… | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-153` | The SIL runner SHALL gracefully handle QEMU process crashes and report them as FAIL with … | `src/yuleosh/pipeline/orchestrator.py` | `tests/test_coverage_phase7_orchestrator_o1.py`<br>`tests/test_coverage_phase7_orchestrator_o2.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-154` | The system SHALL maintain task execution logs for traceability | `src/yuleosh/audit/model.py` | `tests/test_audit_ai_provenance_unit.py`<br>`tests/test_audit_hash_chain_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-155` | The CLI output SHALL use ANSI color coding (green for success, yellow for warning) | `src/yuleosh/audit/model.py` | `tests/test_audit_ai_provenance_unit.py`<br>`tests/test_audit_hash_chain_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-156` | Pipeline step execution SHALL report token usage per step | `src/yuleosh/audit/model.py` | `tests/test_audit_ai_provenance_unit.py`<br>`tests/test_audit_hash_chain_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-157` | The system SHALL persist pipeline session logs to `.osh/sessions/` | `src/yuleosh/audit/model.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-158` | All new features SHALL NOT modify P0/P1 existing API signatures and behavior | `src/yuleosh/api/router.py` | `tests/test_api.py`<br>`tests/test_api_router_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-159` | The re-export shim for pipeline/run.py SHALL preserve all public import paths | `src/yuleosh/api/router.py` | `tests/test_api.py`<br>`tests/test_api_router_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-160` | Each incremental module SHALL be independently verifiable without other module dependenci… | `src/yuleosh/api/router.py` | `tests/test_api.py`<br>`tests/test_api_router_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-161` | All modules SHALL provide CLI and log output for observability | `src/yuleosh/api/stats.py` | `tests/test_api.py`<br>`tests/test_api_small_modules.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-162` | KG build operations SHALL write JSON logs to `knowledge-graph/` directory | `src/yuleosh/api/stats.py` | `tests/test_api.py`<br>`tests/test_api_small_modules.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-163` | The merge gate SHALL write report to configurable output path | `src/yuleosh/api/stats.py` | `tests/test_api.py`<br>`tests/test_api_small_modules.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-164` | The system SHALL use isolated workspaces per pipeline run to prevent artifact contaminati… | `src/yuleosh/api/audit.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-165` | Feature gates (e.g., `--mock`, `YULEOSH_DEMO_ENABLED`) SHALL have safe defaults | `src/yuleosh/api/audit.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-166` | CI configuration SHALL fall back to safe defaults when config file is missing or invalid | `src/yuleosh/api/audit.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-167` | Python line coverage gate SHALL default to ≥85% for source modules | `src/yuleosh/ci/config.py` | `tests/test_ci_config.py`<br>`tests/test_ci_config_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-168` | Pipeline step handlers sub-module coverage SHALL be ≥80% | `src/yuleosh/ci/config.py` | `tests/test_ci_config.py`<br>`tests/test_ci_config_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-169` | `stages.py` coverage SHALL be ≥80% | `src/yuleosh/ci/config.py` | `tests/test_ci_config.py`<br>`tests/test_ci_config_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-18` | The system SHALL support per-task blocking review by AI agents | `src/yuleosh/api/review.py`<br>`src/yuleosh/pipeline/step_handlers/review.py`<br>… 另有 7 个 | `tests/test_consistency_cli.py`<br>`tests/test_coverage_phase10_knowledge.py`<br>… 另有 12 个 | 缺失 | [ ] |
| `SHALL-19` | The system SHALL support dual-track review (non-blocking AI self-check + blocking agent r… | `src/yuleosh/api/review.py`<br>`src/yuleosh/pipeline/step_handlers/review.py`<br>… 另有 7 个 | `tests/test_consistency_cli.py`<br>`tests/test_coverage_phase10_knowledge.py`<br>… 另有 12 个 | 缺失 | [ ] |
| `SHALL-2` | The system SHALL route tasks through the Harness Engineering agent pipeline (PM → Product… | `src/yuleosh/alm/traceability.py`<br>`src/yuleosh/codegen/engine.py`<br>… 另有 17 个 | `tests/ci/test_compliance_checker.py`<br>`tests/loop_engine/test_feedback_handlers.py`<br>… 另有 64 个 | 缺失 | [ ] |
| `SHALL-209` | The system SHALL require JWT bearer tokens for all API endpoints except public routes | `src/yuleosh/api/auth.py`<br>`src/yuleosh/rbac/model.py`<br>… 另有 1 个 | `tests/ci/test_compliance_checker.py`<br>`tests/test_api_services_extended.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-210` | The system SHALL verify JWT signature and expiration on each request | `src/yuleosh/api/auth.py`<br>`src/yuleosh/rbac/model.py`<br>… 另有 1 个 | `tests/ci/test_compliance_checker.py`<br>`tests/test_api_services_extended.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-211` | The system SHALL reject expired, revoked, or malformed tokens with HTTP 401 | `src/yuleosh/api/auth.py`<br>`src/yuleosh/rbac/model.py`<br>… 另有 1 个 | `tests/ci/test_compliance_checker.py`<br>`tests/test_api_services_extended.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-212` | The system SHALL log all authentication failures with IP, timestamp, and attempted resour… | `src/yuleosh/api/auth.py`<br>`src/yuleosh/rbac/model.py`<br>… 另有 1 个 | `tests/ci/test_compliance_checker.py`<br>`tests/test_api_services_extended.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-213` | The system SHALL support token refresh with configurable expiry | `src/yuleosh/api/auth.py`<br>`src/yuleosh/rbac/model.py`<br>… 另有 1 个 | `tests/ci/test_compliance_checker.py`<br>`tests/test_api_services_extended.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-214` | The system SHALL encrypt all database connections using TLS (minimum TLS 1.2) | `src/yuleosh/engine/tenant_security.py` | `tests/test_security.py` | 缺失 | [ ] |
| `SHALL-215` | The system SHALL store user passwords using bcrypt or Argon2 hashing | `src/yuleosh/engine/tenant_security.py` | `tests/test_security.py` | 缺失 | [ ] |
| `SHALL-216` | The system SHALL encrypt sensitive configuration (API keys, tokens) at rest | `src/yuleosh/engine/tenant_security.py` | `tests/test_security.py` | 缺失 | [ ] |
| `SHALL-217` | The system SHALL NOT log plaintext credentials or API keys | `src/yuleosh/engine/tenant_security.py` | `tests/test_security.py` | 缺失 | [ ] |
| `SHALL-218` | The system SHALL support HTTPS for all web and API traffic | `src/yuleosh/engine/tenant_security.py` | `tests/test_security.py` | 缺失 | [ ] |
| `SHALL-219` | The system SHALL record all security-relevant events to the audit log | `src/yuleosh/api/audit.py`<br>`src/yuleosh/audit/model.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-220` | Audit log entries SHALL include: timestamp, event type, user ID, source IP, resource, act… | `src/yuleosh/api/audit.py`<br>`src/yuleosh/audit/model.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-221` | The system SHALL NOT allow modification or deletion of audit log entries | `src/yuleosh/api/audit.py`<br>`src/yuleosh/audit/model.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-222` | The system SHALL support audit log export in tamper-evident format | `src/yuleosh/api/audit.py`<br>`src/yuleosh/audit/model.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-223` | Audit logs SHALL be retained for a minimum of 12 months | `src/yuleosh/api/audit.py`<br>`src/yuleosh/audit/model.py` | `tests/test_api.py`<br>`tests/test_api_audit_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-224` | The system SHALL validate and sanitize all user inputs before processing | `src/yuleosh/llm/validation.py` | `tests/test_llm_validation_deep.py`<br>`tests/test_security.py` | 缺失 | [ ] |
| `SHALL-225` | The system SHALL reject spec files containing embedded scripts or control characters | `src/yuleosh/llm/validation.py` | `tests/test_llm_validation_deep.py`<br>`tests/test_security.py` | 缺失 | [ ] |
| `SHALL-226` | The system SHALL apply path normalization to prevent directory traversal attacks | `src/yuleosh/llm/validation.py` | `tests/test_llm_validation_deep.py`<br>`tests/test_security.py` | 缺失 | [ ] |
| `SHALL-227` | The system SHALL limit upload sizes (50 MB ZIP, 10 MB spec files) | `src/yuleosh/llm/validation.py` | `tests/test_llm_validation_deep.py`<br>`tests/test_security.py` | 缺失 | [ ] |
| `SHALL-228` | The system SHALL use parameterized queries for all database operations | `src/yuleosh/llm/validation.py` | `tests/test_llm_validation_deep.py`<br>`tests/test_security.py` | 缺失 | [ ] |
| `SHALL-229` | The system SHALL support role-based access control (admin/member/viewer) as per SL-2 | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-230` | The system SHALL provide audit logging for all security events as per SL-2 | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-231` | The system SHALL enforce secure communication (TLS) for all network traffic | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-232` | The system SHALL implement rate limiting for public API endpoints | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-233` | The system SHALL support session timeout and automatic logout | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-24` | The system SHALL provide a 3-layer CI/CD pipeline (Dev Verify → Integration Verify → Syst… | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-25` | The system SHALL support cross-compilation for ARM/RISC-V/x86_64 targets | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-26` | The system SHALL support MISRA-C/C++ static analysis gates | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-27` | The system SHALL auto-generate ASPICE compliance evidence packages | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-28` | The system SHALL support firmware signing and OTA package generation | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-29` | The system SHALL support HIL (Hardware-in-the-Loop) adapter layer testing | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-30` | The system SHALL support SIL (Software-in-the-Loop) adapter layer testing | `src/yuleosh/api/ci.py`<br>`src/yuleosh/ci/config.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 6 个 | 缺失 | [ ] |
| `SHALL-37` | The system SHALL generate a traceability matrix (Req ↔ Design ↔ Code ↔ Test) on each rele… | `src/yuleosh/alm/base.py`<br>`src/yuleosh/alm/traceability.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-38` | The system SHALL export a compliance pack for ASPICE audit | `src/yuleosh/alm/base.py`<br>`src/yuleosh/alm/traceability.py`<br>… 另有 12 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-39` | The system SHALL provide a Web UI for project management | `src/yuleosh/api/audit.py`<br>`src/yuleosh/api/auth.py`<br>… 另有 9 个 | `tests/test_coverage_phase6_spec.py`<br>`tests/test_kg_performance.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-40` | The system SHALL provide a mobile-responsive interface | `src/yuleosh/api/audit.py`<br>`src/yuleosh/api/auth.py`<br>… 另有 9 个 | `tests/test_coverage_phase6_spec.py`<br>`tests/test_kg_performance.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-41` | The system SHALL support single-tenant deployment for MVP | `src/yuleosh/rbac/model.py`<br>`src/yuleosh/rbac/role_contract.py`<br>… 另有 1 个 | `tests/test_coverage_phase2_lowcov.py`<br>`tests/test_rbac_model_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-42` | The system SHALL support multi-tenant isolation | `src/yuleosh/rbac/model.py`<br>`src/yuleosh/rbac/role_contract.py`<br>… 另有 1 个 | `tests/test_coverage_phase2_lowcov.py`<br>`tests/test_rbac_model_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-43` | The system SHALL provide organization/project/team hierarchy | `src/yuleosh/rbac/model.py`<br>`src/yuleosh/rbac/role_contract.py`<br>… 另有 1 个 | `tests/test_coverage_phase2_lowcov.py`<br>`tests/test_rbac_model_unit.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-44` | The system SHALL support Software-in-the-Loop (SIL) testing for ARM Cortex-M targets | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `tests/test_codegen_behavior_guardrail.py`<br>`tests/test_cross_sil_assert_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-45` | The system SHALL execute the cross-compiled production binary (.elf) under QEMU system em… | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `tests/test_codegen_behavior_guardrail.py`<br>`tests/test_cross_sil_assert_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-46` | The system SHALL capture UART and semihosting output from the simulated target for test a… | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `tests/test_codegen_behavior_guardrail.py`<br>`tests/test_cross_sil_assert_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-47` | The system SHALL integrate SIL tests into CI L2 as a blocking stage before integration te… | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `tests/test_codegen_behavior_guardrail.py`<br>`tests/test_cross_sil_assert_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-48` | The system SHALL generate a SIL test report in the compliance evidence pack | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-49` | The system SHALL support SIL testing for RISC-V targets via QEMU | `src/yuleosh/cross/sil_assert.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 1 个 | `tests/test_codegen_behavior_guardrail.py`<br>`tests/test_cross_sil_assert_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-61` | The system SHALL provide a Flash Abstraction Layer (FAL) supporting OpenOCD, JLink, and p… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 1 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-62` | The system SHALL support auto-detection of available flash tools with configurable fallba… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 1 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-63` | The system SHALL provide a Hardware-in-the-Loop (HIL) test runner orchestrating flash → s… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 1 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-64` | The system SHALL support dual-mode serial capture: physical port (pyserial) and in-proces… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 1 个 | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_coverage_phase6_spec.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-74` | The system SHALL provide a fully-mocked E2E test that exercises the pipeline from spec in… | `src/yuleosh/sil/adapter.py` | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_req_annotation_scanner.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-75` | The E2E test SHALL mock all external dependencies (LLM, subprocess, file system I/O) | `src/yuleosh/sil/adapter.py` | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_req_annotation_scanner.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-76` | The E2E test SHALL cover at least 80% of pipeline steps in a single end-to-end run | `src/yuleosh/sil/adapter.py` | `tests/test_coverage_phase10_knowledge.py`<br>`tests/test_req_annotation_scanner.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-77` | The system SHALL provide a Template Gallery of pre-built project templates | `src/yuleosh/codegen/engine.py` | `tests/test_codegen_brainstorm_20260816.py`<br>`tests/test_codegen_engine.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-78` | The system SHALL store built-in templates under `yuleosh/templates/` directory | `src/yuleosh/codegen/engine.py` | `tests/test_codegen_brainstorm_20260816.py`<br>`tests/test_codegen_engine.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-79` | Each template SHALL contain at minimum: `template.yaml`, `specs/spec.md`, `pipeline/confi… | `src/yuleosh/codegen/engine.py` | `tests/test_codegen_brainstorm_20260816.py`<br>`tests/test_codegen_engine.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-80` | The template manifest (`template.yaml`) SHALL include: name, version, description, platfo… | `src/yuleosh/codegen/engine.py` | `tests/test_codegen_brainstorm_20260816.py`<br>`tests/test_codegen_engine.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-81` | The system SHALL support at least 5 template directories at install time | `src/yuleosh/codegen/engine.py` | `tests/test_codegen_brainstorm_20260816.py`<br>`tests/test_codegen_engine.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-90` | The system SHALL provide a "Try Demo" button on the landing page hero section with minimu… | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |
| `SHALL-91` | The system SHALL expose `GET /api/demo/pipeline` endpoint returning pre-seeded mock pipel… | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |
| `SHALL-92` | The demo endpoint SHALL NOT require authentication or LLM API calls | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |
| `SHALL-93` | The system SHALL provide a `/demo` frontend page with animated pipeline progress UI | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |
| `SHALL-94` | The demo SHALL be rate-limited to 10 requests per minute per IP (HTTP 429 on exceed) | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |

## SYS.3（8 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `SYSARCH-001` | **SYSARCH-001**: 系统架构 SHALL 包含流水线编排元素，负责阶段调度、Agent 执行、状态持久化与失败恢复。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-002` | **SYSARCH-002**: 系统架构 SHALL 包含需求与追溯元素，负责需求解析、稳定标识、追溯索引与基线比较。 | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-003` | **SYSARCH-003**: 系统架构 SHALL 包含评审与门禁元素，负责规则执行、问题分级与放行判定。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-004` | **SYSARCH-004**: 系统架构 SHALL 包含构建与测试执行元素，负责单元、集成、合格性、SIL 与 HIL 测试运行及结果采集。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-005` | **SYSARCH-005**: 系统架构 SHALL 包含证据与合规元素，负责证据采集、哈希清单、证据链构建与合规包导出。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-006` | **SYSARCH-006**: 系统架构 SHALL 包含 SaaS 平台元素，负责租户隔离、订阅配额、身份认证与审计日志。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-007` | **SYSARCH-007**: 系统架构 SHALL 包含客户端接入元素，负责 CLI、Web UI、API 与模板市场的统一入口。 | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SYSARCH-008` | **SYSARCH-008**: 系统架构 SHALL 包含知识图谱与度量元素，负责实体关系存储、关联查询、指标计算与趋势分析。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |

## SWE.1（124 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `SHALL-10` | The system SHALL convert `pipeline/run.py` into a thin re-export shim (≤100 lines) | `src/yuleosh/ci/review_helpers.py`<br>`src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/ci/test_review_helpers.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-100` | After completion, the page SHALL display final report, "Download Evidence Pack" button, a… | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |
| `SHALL-102` | ZIP uploads SHALL be limited to 50 MB; invalid ZIPs return HTTP 400 | `src/yuleosh/preview/code_parser.py` | `tests/test_preview_parser_deep.py` | 缺失 | [ ] |
| `SHALL-103` | Git URLs SHALL support GitHub, GitLab, Bitbucket; unsupported hosts return HTTP 400 | `src/yuleosh/preview/code_parser.py` | `tests/test_preview_parser_deep.py` | 缺失 | [ ] |
| `SHALL-104` | Clone timeout SHALL be 120 seconds; timeout returns HTTP 408 | `src/yuleosh/preview/code_parser.py` | `tests/test_preview_parser_deep.py` | 缺失 | [ ] |
| `SHALL-105` | Cloned repos SHALL be limited to 200 MB; excess returns HTTP 413 | `src/yuleosh/preview/code_parser.py` | `tests/test_preview_parser_deep.py` | 缺失 | [ ] |
| `SHALL-106` | The system SHALL provide `GET /api/preview/assess/<preview_id>` for status polling | `src/yuleosh/preview/code_parser.py` | `tests/test_preview_parser_deep.py` | 缺失 | [ ] |
| `SHALL-107` | The coverage prediction SHALL include: current_coverage_estimate, projected_coverage_afte… | `src/yuleosh/preview/analyzer.py`<br>`src/yuleosh/preview/compliance_analyzer.py` | `tests/test_phase0_coverage_boost.py`<br>`tests/test_preview_analyzer.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-108` | The compliance risk SHALL analyze: MISRA-C violations, coding standard adherence, ASPICE … | `src/yuleosh/preview/analyzer.py`<br>`src/yuleosh/preview/compliance_analyzer.py` | `tests/test_phase0_coverage_boost.py`<br>`tests/test_preview_analyzer.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-109` | The recommended pipeline config SHALL include: recommended_template, steps, ci_layers, re… | `src/yuleosh/preview/analyzer.py`<br>`src/yuleosh/preview/compliance_analyzer.py` | `tests/test_phase0_coverage_boost.py`<br>`tests/test_preview_analyzer.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-11` | The re-export shim SHALL forward all currently public symbols to their new module locatio… | `src/yuleosh/pipeline/run.py` | `tests/test_agent_pipeline_inline.py`<br>`tests/test_e2e.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-110` | Unauthenticated users SHALL be limited to 3 preview assessments per 24 hours per IP | `src/yuleosh/api/ratelimit.py` | `tests/test_alpha01_full_flow.py`<br>`tests/test_alpha02_onboarding.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-111` | Authenticated users SHALL have a limit of 20 per 24 hours | `src/yuleosh/api/ratelimit.py` | `tests/test_alpha01_full_flow.py`<br>`tests/test_alpha02_onboarding.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-112` | Rate limit exceeded SHALL return HTTP 429 | `src/yuleosh/api/ratelimit.py` | `tests/test_alpha01_full_flow.py`<br>`tests/test_alpha02_onboarding.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-113` | Preview results SHALL be retained for 24 hours | `src/yuleosh/api/ratelimit.py` | `tests/test_alpha01_full_flow.py`<br>`tests/test_alpha02_onboarding.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-119` | The system SHALL use Stripe Checkout for paid upgrade processing | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-12` | The shim SHALL NOT contain any executable pipeline logic — only import statements | `src/yuleosh/pipeline/run.py` | `tests/test_agent_pipeline_inline.py`<br>`tests/test_e2e.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-120` | After successful payment the system SHALL update the user's subscription status | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-121` | The system SHALL verify Stripe webhook event signatures | `src/yuleosh/billing/metering.py` | `tests/test_billing_metering_unit.py` | 缺失 | [ ] |
| `SHALL-125` | The system SHALL support incremental knowledge graph build from git changes | `src/yuleosh/knowledge_graph/incremental.py`<br>`src/yuleosh/knowledge_graph/store.py` | `tests/ci/test_kpi_kg_integration.py`<br>`tests/test_c_code_scanner.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-126` | The system SHALL detect changed files from git diff and selectively rebuild deltas | `src/yuleosh/knowledge_graph/incremental.py`<br>`src/yuleosh/knowledge_graph/store.py` | `tests/ci/test_kpi_kg_integration.py`<br>`tests/test_c_code_scanner.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-127` | The system SHALL support full bootstrap from traceability data | `src/yuleosh/knowledge_graph/incremental.py`<br>`src/yuleosh/knowledge_graph/store.py` | `tests/ci/test_kpi_kg_integration.py`<br>`tests/test_c_code_scanner.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-128` | The system SHALL support impact analysis query for changed files | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_kg_queries_deep.py` | 缺失 | [ ] |
| `SHALL-129` | The system SHALL support snapshot listing, diff, and comparison | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_kg_queries_deep.py` | 缺失 | [ ] |
| `SHALL-130` | The system SHALL provide graph statistics (nodes, edges, types distribution) | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_kg_queries_deep.py` | 缺失 | [ ] |
| `SHALL-131` | The system SHALL provide automatic RTM generation from the knowledge graph | `src/yuleosh/knowledge_graph/reporter.py` | `tests/test_llm_anchoring.py`<br>`tests/test_traceability_rtm_deep.py` | 缺失 | [ ] |
| `SHALL-132` | RTM generation SHALL support Markdown, HTML, and CSV output formats | `src/yuleosh/knowledge_graph/reporter.py` | `tests/test_llm_anchoring.py`<br>`tests/test_traceability_rtm_deep.py` | 缺失 | [ ] |
| `SHALL-133` | RTM content SHALL include columns: Requirement ID, Statement, Test Files, Test Functions,… | `src/yuleosh/knowledge_graph/reporter.py` | `tests/test_llm_anchoring.py`<br>`tests/test_traceability_rtm_deep.py` | 缺失 | [ ] |
| `SHALL-134` | RTM generation SHALL support per-layer filtering (unit/integration/sil/hil/system) | `src/yuleosh/knowledge_graph/reporter.py` | `tests/test_llm_anchoring.py`<br>`tests/test_traceability_rtm_deep.py` | 缺失 | [ ] |
| `SHALL-135` | The CLI command `yuleosh kg report rtm` SHALL trigger RTM generation | `src/yuleosh/knowledge_graph/reporter.py` | `tests/test_llm_anchoring.py`<br>`tests/test_traceability_rtm_deep.py` | 缺失 | [ ] |
| `SHALL-136` | The system SHALL provide metrics computation from the knowledge graph | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_code_scanner.py`<br>`tests/test_kg_p1_incremental.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-137` | Metrics SHALL include: coverage percentage, test distribution by layer, graph health, cha… | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_code_scanner.py`<br>`tests/test_kg_p1_incremental.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-138` | The system SHALL support JSON and text output formats | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_code_scanner.py`<br>`tests/test_kg_p1_incremental.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-139` | The CLI command `yuleosh kg report metrics` SHALL trigger metrics generation | `src/yuleosh/knowledge_graph/queries.py` | `tests/test_code_scanner.py`<br>`tests/test_kg_p1_incremental.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-140` | The system SHALL provide an event bus for KG state change notifications | `src/yuleosh/knowledge_graph/events.py` | `tests/test_kg_events_deep.py` | 缺失 | [ ] |
| `SHALL-141` | The system SHALL support `yuleosh kg events listen` for real-time event streaming | `src/yuleosh/knowledge_graph/events.py` | `tests/test_kg_events_deep.py` | 缺失 | [ ] |
| `SHALL-142` | The system SHALL support `yuleosh kg events history` for event log retrieval | `src/yuleosh/knowledge_graph/events.py` | `tests/test_kg_events_deep.py` | 缺失 | [ ] |
| `SHALL-143` | The system SHALL provide a KG Merge Gate that validates PR eligibility before merge | `src/yuleosh/knowledge_graph/merge_gate.py` | `tests/test_merge_gate.py`<br>`tests/test_mock_gate_no_fake_pass.py` | 缺失 | [ ] |
| `SHALL-144` | The merge gate SHALL perform: incremental build trigger, graph consistency verification, … | `src/yuleosh/knowledge_graph/merge_gate.py` | `tests/test_merge_gate.py`<br>`tests/test_mock_gate_no_fake_pass.py` | 缺失 | [ ] |
| `SHALL-145` | The merge gate SHALL block merges failing consistency or confidence checks | `src/yuleosh/knowledge_graph/merge_gate.py` | `tests/test_merge_gate.py`<br>`tests/test_mock_gate_no_fake_pass.py` | 缺失 | [ ] |
| `SHALL-146` | The CLI command `yuleosh kg check-merge` SHALL trigger merge gate execution | `src/yuleosh/knowledge_graph/merge_gate.py` | `tests/test_merge_gate.py`<br>`tests/test_mock_gate_no_fake_pass.py` | 缺失 | [ ] |
| `SHALL-147` | The pipeline SHALL include a `merge-gate` step in the PIPELINE_STEPS registry | `src/yuleosh/knowledge_graph/merge_gate.py` | `tests/test_merge_gate.py`<br>`tests/test_mock_gate_no_fake_pass.py` | 缺失 | [ ] |
| `SHALL-15` | The system SHALL support OpenSpec RFC 2119 format for all requirements | `src/yuleosh/spec/patterns.py`<br>`src/yuleosh/spec/validate.py` | `tests/test_coverage_phase6_spec.py`<br>`tests/test_kg_performance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-16` | The system SHALL support S.U.P.E.R startup analysis for each new requirement | `src/yuleosh/loop_engine/spec_delta_gen.py`<br>`src/yuleosh/spec/changes.py`<br>… 另有 2 个 | `tests/loop_engine/test_spec_delta_gen.py`<br>`tests/test_spec_changes_cp.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-17` | The system SHALL track delta between requirement versions for audit | `src/yuleosh/loop_engine/spec_delta_gen.py`<br>`src/yuleosh/spec/changes.py`<br>… 另有 2 个 | `tests/loop_engine/test_spec_delta_gen.py`<br>`tests/test_spec_changes_cp.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-20` | The system SHALL support auto-reviewer routing based on task type | `src/yuleosh/pipeline/step_handlers/review.py`<br>`src/yuleosh/pipeline/step_handlers/review_code.py`<br>… 另有 2 个 | `tests/test_c_review.py`<br>`tests/test_c_review_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-21` | The system SHALL archive all agent review records as JSON evidence | `src/yuleosh/pipeline/step_handlers/review.py`<br>`src/yuleosh/pipeline/step_handlers/review_code.py`<br>… 另有 2 个 | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-22` | The system SHALL support coverage-guardian with configurable line coverage gate | `src/yuleosh/ci/config.py`<br>`src/yuleosh/ci/coverage_pipeline.py`<br>… 另有 2 个 | `tests/test_ci_config.py`<br>`tests/test_ci_config_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-23` | The system SHALL allow the coverage threshold to be set per-project (default > 85%) | `src/yuleosh/ci/config.py`<br>`src/yuleosh/ci/coverage_pipeline.py`<br>… 另有 2 个 | `tests/test_ci_config.py`<br>`tests/test_ci_config_deep.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-234` | THEN the system SHALL generate a startup-analysis.md and execute TDD (RED→GREEN→REFACTOR)… | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-235` | THEN Layer 1 CI SHALL run unit tests + coverage gate | `src/yuleosh/compliance/compliance_checker.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-236` | AND Layer 2 CI SHALL run cross-compilation + static analysis + integration tests | `src/yuleosh/compliance/compliance_checker.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-237` | AND Layer 2.5 CI SHALL run HIL tests | `src/yuleosh/compliance/compliance_checker.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-238` | AND upon release tag, Layer 3 CD SHALL generate evidence pack | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-239` | THEN the system SHALL execute each SIL test in an isolated QEMU instance | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-240` | AND the system SHALL assert serial output against expected patterns | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-241` | THEN the system SHALL trigger incremental KG build | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-242` | AND the system SHALL verify graph consistency (no orphans, no cycles) | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-243` | AND the system SHALL verify traceability confidence (min 70%) | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-244` | AND the system SHALL block the merge if either check fails | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-245` | THEN the system SHALL return HTTP 401 | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-246` | AND the system SHALL log the attempt with IP and timestamp | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-247` | AND the system SHALL NOT process the request further | `src/yuleosh/compliance/compliance_checker.py` | `tests/ci/test_compliance_checker.py`<br>`tests/test_compliance.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-248` | **SHALL** 提供基于 Agent 的自动化开发流水线，支持 spec → code → test → evidence 全流程 | `desktop/main.js`<br>`desktop/server-manager.js` | `desktop/tests/backend-startup.test.js`<br>`tests/ci/test_compliance_checker.py`<br>… 另有 42 个 | 自评审（不计入） | [ ] |
| `SHALL-249` | **SHALL** 提供需求管理功能，支持需求标识、结构化、影响分析与变更追溯 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/ci/test_compliance_checker.py`<br>`tests/ci/test_kpi_kg_integration.py`<br>… 另有 17 个 | 缺失 | [ ] |
| `SHALL-250` | **SHALL** 提供多 Agent 协作的代码审查能力，覆盖 MISRA/CERT/安全规则 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/ci/test_kpi_kg_integration.py`<br>`tests/test_alm_traceability.py`<br>… 另有 5 个 | 缺失 | [ ] |
| `SHALL-251` | **SHALL** 实现三层 CI/CD 流水线 — L1 单元验证 / L25 集成测试 / L3 合格性测试 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/ci/test_kpi_kg_integration.py`<br>`tests/test_evidence_collection_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-252` | **SHALL** 自动生成需求→设计→代码→测试的双向追溯矩阵与合规证据链 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_product_v1.py`<br>`tests/test_sys_req005_traceability.py` | 缺失 | [ ] |
| `SHALL-253` | **SHALL** 支持 CLI / Web UI / API 三种接入方式 | `desktop/main.js`<br>`desktop/preload.js`<br>… 另有 2 个 | `desktop/tests/backend-startup.test.js`<br>`desktop/tests/main.test.js`<br>… 另有 2 个 | 自评审（不计入） | [ ] |
| `SHALL-254` | **SHALL** 支持多租户 SaaS 部署，租户间数据隔离 | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/alm/traceability.py`<br>… 另有 18 个 | `tests/test_api_services_extended.py`<br>`tests/test_gap_close.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-255` | **SHALL** 提供软件在环 (SIL) 仿真测试能力，支持 GCC/Clang 交叉编译与 QEMU 执行 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-256` | **SHALL** 提供 Flash 抽象层 (FAL) 与 HIL 硬件在环测试框架 | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_kb_store.py` | 缺失 | [ ] |
| `SHALL-257` | **SHALL** 提供端到端全流程集成测试，覆盖 spec → pipeline → evidence 完整链路 | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_evidence_analysis_ext.py`<br>`tests/test_evidence_collection_ext.py`<br>… 另有 1 个 | 缺失 | [ ] |
| `SHALL-258` | **SHALL** 提供模板市场，预置 ASPICE/ISO 26262/IEC 61508 等合规模板 | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_evidence_analysis_ext.py` | 缺失 | [ ] |
| `SHALL-259` | **SHALL** 提供在线试用 Demo 环境，零配置体验核心功能 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-260` | **SHALL** 提供 AI 驱动的合规预评估，快速识别合规缺口 | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-261` | **SHALL** 单次合规检查在 30 秒内完成（100 文件以内项目） | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-262` | **SHALL** 支持通过 yaml profile 扩展新的合规标准，无需修改核心代码 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-3` | The system SHALL support the OpenSpec specification format (SHALL/SHOULD/MAY + GIVEN/WHEN… | `src/yuleosh/alm/traceability.py` | `tests/test_alm_traceability.py`<br>`tests/test_coverage_phase10_knowledge.py`<br>… 另有 10 个 | 缺失 | [ ] |
| `SHALL-31` | The system SHALL provide a per-project CI configuration file (`.yuleosh/ci-config.yaml`) | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-32` | The system SHALL support configurable coverage thresholds per project | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-33` | The system SHALL provide a CI Layer 2.5 (Hardware-in-the-Loop) positioned between L2 and … | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-34` | The system SHALL support mock mode for L2.5 HIL tests in CI environments without physical… | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-35` | The system SHALL support configurable layer dependency chain | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-36` | The system SHALL support CI layer argument aliases `25` and `2.5` for Layer 2.5 | `src/yuleosh/ci/config.py` | `tests/test_ci_config_deep.py` | 缺失 | [ ] |
| `SHALL-4` | The system SHALL enforce Superpowers 14 Rules at each pipeline stage | `src/yuleosh/codegen/engine.py`<br>`src/yuleosh/pipeline/gates.py`<br>… 另有 4 个 | `tests/test_alm_traceability.py`<br>`tests/test_coverage_phase10_knowledge.py`<br>… 另有 10 个 | 缺失 | [ ] |
| `SHALL-5` | The system SHALL generate a test plan with requirement traceability matrix for each pipel… | `src/yuleosh/alm/traceability.py` | `tests/test_spec_v03_it2.py`<br>`tests/test_spec_validate_deep.py` | 缺失 | [ ] |
| `SHALL-50` | The system SHALL provide a `qemu-sil-runner` component that loads .elf, captures serial o… | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-51` | The system SHALL support ARM Cortex-M3/M4 QEMU machines (e.g. `lm3s6965evb`, `stm32vldisc… | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-52` | The system SHALL support RISC-V QEMU `virt` machine for 64-bit targets | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-53` | The system SHALL provide a HAL abstraction mock layer for host-compiled (native) SIL tests | `src/yuleosh/cross/sil_assert.py` | `tests/test_cross_sil_assert_deep.py`<br>`tests/test_cross_smoke.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-54` | The system SHALL support HAL mocking for at least: UART, GPIO, Timer, I2C, SPI | `src/yuleosh/cross/sil_assert.py` | `tests/test_cross_sil_assert_deep.py`<br>`tests/test_cross_smoke.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-55` | The system SHALL expose a call-history API for test verification | `src/yuleosh/cross/sil_assert.py` | `tests/test_cross_sil_assert_deep.py`<br>`tests/test_cross_smoke.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-56` | The system SHALL require each SIL test to use GIVEN/WHEN/THEN format | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-57` | The system SHALL execute SIL tests as a dedicated CI L2 stage | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-58` | The system SHALL report SIL test results in the compliance evidence pack | `src/yuleosh/sil/adapter.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-59` | A SIL test failure SHALL block the CI pipeline (L2 blocking gate) | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-6` | The system SHALL map every SHALL statement to at least one test case | `src/yuleosh/alm/traceability.py`<br>`src/yuleosh/pipeline/step_handlers/test_c_unit.py`<br>… 另有 3 个 | `tests/test_spec_v03_it2.py`<br>`tests/test_spec_validate_deep.py` | 缺失 | [ ] |
| `SHALL-60` | The system SHALL isolate each SIL test in its own QEMU process instance | `src/yuleosh/sil/adapter.py` | `tests/test_max_import.py`<br>`tests/test_sil.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-65` | The system SHALL provide abstract `FlashTool` base class with `write()`, `erase()`, `veri… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `tests/test_spec_coverage_boost.py` | 缺失 | [ ] |
| `SHALL-66` | The system SHALL provide concrete implementations: `OpenOCDRunner`, `JLinkRunner`, `PyOCD… | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `tests/test_spec_coverage_boost.py` | 缺失 | [ ] |
| `SHALL-67` | The system SHALL provide a `FlashRunner` facade that auto-detects available tools | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `tests/test_spec_coverage_boost.py` | 缺失 | [ ] |
| `SHALL-68` | FlashRunner SHALL support a preferred-tool override via `tool=` parameter | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `tests/test_spec_coverage_boost.py` | 缺失 | [ ] |
| `SHALL-69` | FlashRunner SHALL attempt fallback tools in order (OpenOCD → JLink → pyOCD) when primary … | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `tests/test_spec_coverage_boost.py` | 缺失 | [ ] |
| `SHALL-7` | The system SHALL split `pipeline/run.py` into at least 3 modules: `orchestrator.py`, `ste… | `src/yuleosh/pipeline/run.py` | `tests/test_agent_pipeline_inline.py`<br>`tests/test_e2e.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-70` | Each runner SHALL return a `FlashResult` dataclass with pass/fail status and full log | `src/yuleosh/adapter/dspace_adapter.py`<br>`src/yuleosh/adapter/vector_adapter.py` | `docs/evidence/sessions/desktop-self-evolution-20261107/desktop-test.json` | 缺失 | [ ] |
| `SHALL-71` | The system SHALL provide a `HilTestRunner` class orchestrating: flash → boot → serial → a… | `src/yuleosh/cross/hil_runner.py` | `tests/test_cross_smoke.py`<br>`tests/test_hil_runner.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-72` | The system SHALL return results as a `HilTestResult` dataclass with phase timings | `src/yuleosh/cross/hil_runner.py` | `tests/test_cross_smoke.py`<br>`tests/test_hil_runner.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-73` | The system SHALL support a test script syntax with directives: expect, assert, wait, read… | `src/yuleosh/cross/hil_runner.py` | `tests/test_cross_smoke.py`<br>`tests/test_hil_runner.py`<br>… 另有 2 个 | 缺失 | [ ] |
| `SHALL-8` | Each resulting module SHALL be under 500 lines of code | `src/yuleosh/pipeline/run.py` | `tests/test_agent_pipeline_inline.py`<br>`tests/test_e2e.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-82` | The system SHALL store built-in templates under `yuleosh/templates/` | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-83` | Each template SHALL contain `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`, `sr… | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-84` | The system SHALL search for templates in priority order: project-local → user-local → bui… | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-85` | User-local templates SHALL supplement (not replace) built-in templates | `src/ci/fi_cmd.py`<br>`src/yuleosh/agent_registry.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-86` | The system SHALL support CLI command `yuleosh project init --template <name> [project_dir… | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-87` | `project init` SHALL create: docs/spec.md, pipeline/config.yaml, src/, yuleosh.yaml | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-88` | When `--template` is omitted, the system SHALL enter interactive mode | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-89` | The system SHALL support CLI command `yuleosh template list` to enumerate all templates | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-9` | The public API SHALL remain backward compatible | `src/yuleosh/pipeline/run.py` | `tests/test_agent_pipeline_inline.py`<br>`tests/test_e2e.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SHALL-95` | The `GET /api/demo/pipeline` endpoint SHALL return JSON with pipeline state and steps | `src/yuleosh/api/demo.py` | `tests/test_api_demo_extended.py`<br>`tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-96` | The endpoint SHALL accept `?step=N` to return partial results | `src/yuleosh/api/demo.py` | `tests/test_api_demo_extended.py`<br>`tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-97` | The server SHALL validate demo readiness via `YULEOSH_DEMO_ENABLED` env var (503 when dis… | `src/yuleosh/api/demo.py` | `tests/test_api_demo_extended.py`<br>`tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-98` | Mock steps SHALL include: Spec Parsing, Requirements Analysis, SDD, Code Generation, Inte… | `src/yuleosh/api/demo.py` | `tests/test_api_demo_extended.py`<br>`tests/test_product_v1.py` | 缺失 | [ ] |
| `SHALL-99` | The `/demo` page SHALL display all 10 pipeline steps with status animation | `src/yuleosh/api/demo_quick.py` | `tests/test_api_demo_extended.py`<br>`tests/test_coverage_phase6_demo.py` | 缺失 | [ ] |

## SWE.2（8 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `SWARCH-001` | **SWARCH-001**: 软件架构 SHALL 提供流水线编排器，实现阶段状态机、Agent 调用、并发控制与断点续跑。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-002` | **SWARCH-002**: 软件架构 SHALL 提供需求与追溯服务，实现需求解析、稳定 ID 生成、追溯图构建与基线差异计算。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-003` | **SWARCH-003**: 软件架构 SHALL 提供评审引擎，实现规则加载、多 Agent 结果聚合、问题去重与放行门禁。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-004` | **SWARCH-004**: 软件架构 SHALL 提供构建与测试执行器，实现工具链适配、测试分层调度、结果采集与环境快照。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-005` | **SWARCH-005**: 软件架构 SHALL 提供证据引擎，实现证据采集、SHA256 清单、证据链校验与 HTML/JSON 视图生成。 | `src/ci/fi_cmd.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_jira.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-006` | **SWARCH-006**: 软件架构 SHALL 提供 SaaS 平台服务，实现租户上下文、配额校验、订阅状态与审计日志写入。 | `src/yuleosh/__init__.py`<br>`src/yuleosh/adapter/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-007` | **SWARCH-007**: 软件架构 SHALL 提供客户端接入层，实现 CLI 命令分发、API 路由、Web UI 适配与模板加载。 | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `SWARCH-008` | **SWARCH-008**: 软件架构 SHALL 提供知识图谱服务，实现实体关系存储、关联查询、指标计算与影响分析。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/vector_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |

## SWE.3（8 条）

| 需求 ID | 摘要 | 实现证据 | 测试证据 | 当前评审 | 确认 |
|---|---|---|---|---|---|
| `DD-001` | **DD-001**: 详细设计 SHALL 定义流水线阶段状态、转换条件、持久化字段与失败恢复序列。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-002` | **DD-002**: 详细设计 SHALL 定义需求稳定标识规则、节点/边数据结构与追溯索引的持久化格式。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-003` | **DD-003**: 详细设计 SHALL 定义规则执行结果、问题记录、去重键与门禁判定的数据结构。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-004` | **DD-004**: 详细设计 SHALL 定义测试运行元数据、通过判据、结果快照与环境配置的采集格式。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-005` | **DD-005**: 详细设计 SHALL 定义证据链 JSON schema、哈希校验流程与单文件 HTML 深链导航结构。 | `src/ci/fi_cmd.py`<br>`src/yuleosh/__init__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_jira.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-006` | **DD-006**: 详细设计 SHALL 定义租户隔离键、订阅状态、配额字段与审计日志结构。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_traceability.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-007` | **DD-007**: 详细设计 SHALL 定义 CLI 命令注册、参数校验、退出码与 JSON 输出约定。 | `src/ci/fi_cmd.py`<br>`src/yuleosh/__main__.py`<br>… 另有 18 个 | `tests/test_agent_registry.py`<br>`tests/test_alm_jira.py`<br>… 另有 3 个 | 缺失 | [ ] |
| `DD-008` | **DD-008**: 详细设计 SHALL 定义图谱实体、关系类型、索引策略与影响分析查询接口。 | `src/yuleosh/adapter/__init__.py`<br>`src/yuleosh/adapter/dspace_adapter.py`<br>… 另有 18 个 | `tests/test_alm_traceability.py`<br>`tests/test_alm_traceability_ext.py`<br>… 另有 3 个 | 缺失 | [ ] |

## 评审签署

| 过程域 | 评审人 | 独立性声明 | 签名 | 日期 | 结论 |
|---|---|---|---|---|---|
| SYS.1 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |
| SYS.2 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |
| SYS.3 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |
| SWE.1 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |
| SWE.2 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |
| SWE.3 |  | [ ] 非作者 / [ ] 非变更贡献者 / [ ] 无利益冲突 |  |  |  |

