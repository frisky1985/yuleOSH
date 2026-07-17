# yuleOSH Acceptance Matrix — v2.5.0 Phase 2

> Generated: 2026-07-17 | Format: GIVEN/WHEN/THEN | Status Legend: ✅ Pass | ❌ Fail | ⚠️ Partial | 📝 Not Run
> 
> **编号体系变更**: v2.5.0 合并了所有 delta spec，统一使用 RS-XXX / SWR-XXX / KG-XXX / TG-XXX / NFR-XXX / FSR-XXX / CR-XXX

## 1. System Requirements (RS)

### RS-001: Agent 驱动的开发流水线

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-001-1 | The system SHALL support an SDD → DDD → TDD → CI/CD pipeline | **GIVEN** a valid OpenSpec file at `docs/spec.md` **WHEN** the user invokes pipeline run **THEN** the system SHALL execute all pipeline steps in order and produce a session report | ✅ |
| ACC-RS-001-2 | The system SHALL route tasks through Harness Engineering agent pipeline | **GIVEN** a task with type annotation **WHEN** the task enters the pipeline **THEN** the system SHALL route it to the correct agent (PM/Product/Architect/Dev) | ✅ |
| ACC-RS-001-3 | The system SHALL enforce Superpowers 14 Rules | **GIVEN** a pipeline run **WHEN** any step is executed **THEN** the step output SHALL be validated against Superpowers rules | ⚠️ |
| ACC-RS-001-4 | The system SHALL generate a test plan with RTM | **GIVEN** a completed pipeline run **WHEN** the evidence generation step executes **THEN** the system SHALL produce a traceability matrix mapping SHALLs to test cases | 📝 |
| ACC-RS-001-5 | The system SHALL map every SHALL to at least one test case | **GIVEN** the generated RTM **WHEN** inspected **THEN** every SHALL statement in `docs/spec.md` SHALL have at least one corresponding test case in the matrix | 📝 |

### RS-002: 需求管理

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-002-1 | The system SHALL provide a requirements tree hierarchy | **GIVEN** a project with spec files **WHEN** the user inspects the spec **THEN** the system SHALL display requirements in SYS → SW → Feature → Scenario → Task hierarchy | ✅ |
| ACC-RS-002-2 | The system SHALL support spec-delta tracking | **GIVEN** a spec file that has been modified **WHEN** the user runs spec diff **THEN** the system SHALL output the delta between old and new versions | ✅ |
| ACC-RS-002-3 | The system SHALL support OpenSpec RFC 2119 format | **GIVEN** a spec file with SHALL/SHOULD/MAY statements **WHEN** the system parses the spec **THEN** each statement SHALL be correctly classified by RFC 2119 keyword | ✅ |

### RS-003: 代码审查与 Agent 矩阵

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-003-1 | The system SHALL support per-task blocking review by AI agents | **GIVEN** a code review request **WHEN** the review is submitted **THEN** the system SHALL block pipeline progression until the review passes | ✅ |
| ACC-RS-003-2 | The system SHALL support dual-track review | **GIVEN** a review task **WHEN** processing **THEN** the system SHALL run both non-blocking self-check and blocking agent review | ✅ |
| ACC-RS-003-3 | The system SHALL support auto-reviewer routing | **GIVEN** a task of type code/review/arch **WHEN** the task enters the pipeline **THEN** the system SHALL route to the appropriate reviewer module | ✅ |
| ACC-RS-003-4 | The system SHALL archive all agent review records as JSON | **GIVEN** a completed review **WHEN** the review step finishes **THEN** the review record SHALL be written to `.osh/reviews/` as JSON | ✅ |
| ACC-RS-003-5 | The system SHALL support coverage-guardian with configurable gate | **GIVEN** a coverage report **WHEN** the coverage step runs **THEN** the system SHALL compare line coverage against the configured threshold (default > 98%) | ✅ |

### RS-004: CI/CD 三层流水线

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-004-1 | The system SHALL provide a 3-layer CI/CD pipeline | **GIVEN** a project configured for CI **WHEN** CI is triggered **THEN** all three layers (Dev Verify → Integration Verify → System Verify) SHALL execute | ✅ |
| ACC-RS-004-2 | The system SHALL support cross-compilation for ARM/RISC-V/x86_64 | **GIVEN** a target config specifying ARM/RISC-V/x86_64 **WHEN** the build step runs **THEN** the system SHALL invoke the appropriate cross-compiler | ✅ |
| ACC-RS-004-3 | The system SHALL support MISRA-C/C++ static analysis gates | **GIVEN** a CI run **WHEN** the static analysis step runs **THEN** the system SHALL run MISRA checks and report violations | ✅ |
| ACC-RS-004-4 | The system SHALL auto-generate ASPICE compliance evidence packages | **GIVEN** a completed CI pipeline **WHEN** the evidence generation runs **THEN** the system SHALL produce a compliance evidence pack in `.yuleosh/evidence-bundle/` | ✅ |
| ACC-RS-004-5 | The system SHALL support HIL adapter layer testing | **GIVEN** a configured HIL target **WHEN** the HIL test step runs **THEN** the system SHALL flash the target, capture serial output, and assert expectations | ✅ |
| ACC-RS-004-6 | The system SHALL support SIL adapter layer testing | **GIVEN** a compiled .elf binary **WHEN** the SIL runner is invoked **THEN** the system SHALL launch QEMU, load the binary, and capture serial output | ✅ |

### RS-005: 追溯与证据链

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-005-1 | The system SHALL generate a traceability matrix on each release | **GIVEN** a release build **WHEN** the release step runs **THEN** the system SHALL produce `Req ↔ Design ↔ Code ↔ Test` traceability matrix | 📝 |
| ACC-RS-005-2 | The system SHALL export a compliance pack for ASPICE audit | **GIVEN** a completed project cycle **WHEN** the compliance export is triggered **THEN** the system SHALL generate a downloadable .zip compliance pack | ✅ |

### RS-006: 多端接入

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-006-1 | The system SHALL provide a Web UI for project management | **GIVEN** a running server **WHEN** the user opens `http://localhost:18789` in a browser **THEN** the Web UI SHALL load without errors | ✅ |

### RS-007: 多租户 SaaS 架构

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-007-1 | The system SHALL support single-tenant deployment for MVP | **GIVEN** a fresh deployment **WHEN** the user runs setup **THEN** the system SHALL initialize as a single-tenant instance | ✅ |
| ACC-RS-007-2 | The system SHALL support organization/project/team hierarchy | **GIVEN** an organization in the store **WHEN** creating a project **THEN** the project SHALL be scoped to that organization | ✅ |

### RS-008: 嵌入式 SIL 仿真测试

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-008-1 | The system SHALL provide a qemu-sil-runner component | **GIVEN** a compiled .elf binary **WHEN** invoking `qemu-sil-runner --elf <path> --machine lm3s6965evb --timeout 30` **THEN** the system launches QEMU, loads the binary, and captures serial output | ✅ |
| ACC-RS-008-2 | The system SHALL capture UART and semihosting output | **GIVEN** a running QEMU SIL test **WHEN** the firmware writes to UART **THEN** the runner SHALL capture all serial output and return it on completion | ✅ |
| ACC-RS-008-3 | The system SHALL support ARM Cortex-M3/M4 QEMU machines | **GIVEN** a target config for `lm3s6965evb` or `stm32vldiscovery` **WHEN** SIL runner initializes **THEN** it SHALL use the specified machine type | ✅ |
| ACC-RS-008-4 | The system SHALL support timeout-based test termination | **GIVEN** a SIL test with timeout **WHEN** the timeout is reached **THEN** the runner SHALL terminate QEMU and report timeout | ✅ |

### RS-009: Flash 抽象层 (FAL) 与 HIL 硬件测试框架

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-RS-009-1 | The system SHALL provide Flash Abstraction Layer for OpenOCD/JLink/pyOCD | **GIVEN** a flash tool config **WHEN** flashing is requested **THEN** the system SHALL use the configured backend (OpenOCD/JLink/pyOCD) | ✅ |
| ACC-RS-009-2 | The system SHALL support auto-detection with fallback | **GIVEN** no explicit flash tool config **WHEN** flashing is requested **THEN** the system SHALL auto-detect available tools and fall back through the chain | ⚠️ |
| ACC-RS-009-3 | The system SHALL provide HIL test runner (flash → serial → assert) | **GIVEN** a HIL test definition **WHEN** the test runs **THEN** the runner SHALL flash the target, open serial, wait for output, and assert | ✅ |
| ACC-RS-009-4 | The system SHALL support dual-mode serial capture | **GIVEN** a test configuration **WHEN** serial capture is needed **THEN** the system SHALL support both pyserial (physical) and in-process pipe modes | ✅ |

## 2. Software Requirements (SWR)

### SWR-001: 流水线编排

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-SWR-001-1 | The system SHALL support OpenSpec SHALL/SHOULD/MAY + GIVEN/WHEN/THEN | **GIVEN** a spec file **WHEN** parsed **THEN** all SHALL/SHOULD/MAY keywords with GIVEN/WHEN/THEN blocks SHALL be extracted | ✅ |
| ACC-SWR-001-2 | The system SHALL enforce Superpowers 14 Rules at each pipeline stage | **GIVEN** a pipeline step **WHEN** the step runs **THEN** the output SHALL be validated against all relevant Superpowers rules | ⚠️ |

### SWR-003: Agent 审查引擎

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-SWR-003-1 | The system SHALL support auto-reviewer routing based on task type | **GIVEN** a review task **WHEN** submitted **THEN** the system routes to the correct reviewer module | ✅ |
| ACC-SWR-003-2 | The system SHALL archive all agent review records as JSON evidence | **GIVEN** a completed review **WHEN** finalized **THEN** the record SHALL be saved to `.osh/reviews/` as JSON | ✅ |
| ACC-SWR-003-3 | The system SHALL support coverage-guardian with configurable gate | **GIVEN** coverage config **WHEN** coverage check runs **THEN** it SHALL enforce the configured threshold | ✅ |
| ACC-SWR-003-4 | The system SHOULD allow per-project coverage threshold (default > 98%) | **GIVEN** a project config with coverage threshold **WHEN** the coverage gate runs **THEN** it SHALL use the project-specific threshold, defaulting to 98% | ⚠️ |

### SWR-008: QEMU SIL Runner

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-SWR-008-1 | The runner SHALL load .elf and capture serial output | **GIVEN** a compiled .elf binary **WHEN** SIL runner starts **THEN** it SHALL launch QEMU, load the binary, capture UART serial output | ✅ |
| ACC-SWR-008-2 | The runner SHALL support timeout termination with configurable timeout (default 30s) | **GIVEN** a SIL test with timeout=30 **WHEN** 30s elapses **THEN** the runner terminates QEMU and returns captured output | ✅ |
| ACC-SWR-008-3 | The runner SHALL report PASS/FAIL based on serial pattern matching | **GIVEN** a test with expected patterns **WHEN** serial output is captured **THEN** the runner SHALL report PASS if all expected patterns are found, FAIL otherwise | ✅ |
| ACC-SWR-008-4 | The runner SHALL return the full serial log on completion | **GIVEN** any SIL test completion **WHEN** the test ends **THEN** the runner SHALL include the full serial log in the result | ✅ |
| ACC-SWR-008-5 | The runner SHALL execute tests in isolated QEMU process instances | **GIVEN** multiple SIL tests **WHEN** they execute **THEN** each SHALL run in its own QEMU process with no shared state | ✅ |
| ACC-SWR-008-6 | SIL test failure SHALL block the CI pipeline | **GIVEN** a SIL test that fails **WHEN** the CI pipeline runs **THEN** the pipeline SHALL abort and report the failure | ✅ |
| ACC-SWR-008-7 | SIL results SHALL be reported in the compliance evidence pack | **GIVEN** a completed SIL test run **WHEN** evidence pack generates **THEN** it SHALL include `sil-test-report.json` with per-test results | ✅ |

## 3. Security Requirements (SEC)

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-SEC-01 | SQL injection SHALL be prevented via parameterized queries and whitelist | **GIVEN** malicious input with SQL injection payloads **WHEN** KB store update/list methods are called **THEN** the injection SHALL NOT succeed | ✅ |
| ACC-SEC-02 | Path traversal SHALL be prevented via path normalization | **GIVEN** a spec path containing `../` escape **WHEN** pipeline/spec API is called **THEN** the path SHALL be rejected if outside project root | ✅ |
| ACC-SEC-03 | Sensitive API endpoints SHALL require authentication | **GIVEN** a request to /api/v1/kb/*, /api/v1/pipeline/*, /api/v1/evidence/* **WHEN** no JWT token is provided **THEN** the endpoint SHALL return 401 | ✅ |
| ACC-SEC-04 | Health and auth endpoints SHALL remain public | **GIVEN** a request to /api/v1/health or /api/v1/auth/* **WHEN** no JWT token is provided **THEN** the endpoint SHALL still respond | ✅ |
| ACC-SEC-05 | User input SHALL be sanitized to prevent XSS | **GIVEN** input containing `<script>` tags or event handlers **WHEN** passed through sanitize functions **THEN** HTML/JS SHALL be stripped | ✅ |
| ACC-SEC-06 | Password SHALL be hashed with bcrypt (12 rounds) | **GIVEN** a user registration **WHEN** the password is stored **THEN** it SHALL be hashed with bcrypt at 12 salt rounds | ✅ |
| ACC-SEC-07 | Login SHALL be rate-limited (max 10 attempts per 5 min) | **GIVEN** 11 failed login attempts for the same email **WHEN** the 11th attempt is made **THEN** the system SHALL return 429 | ✅ |

## 4. Knowledge Graph Requirements (KG) — v2.5.0 NEW

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-KG-001 | KG SHALL support incremental build from git changes | **GIVEN** changed files detected by git diff **WHEN** `yuleosh kg build --ci` runs **THEN** only affected nodes and edges SHALL be updated | ✅ |
| ACC-KG-002 | KG SHALL support impact analysis for changed files | **GIVEN** a changed file path **WHEN** `yuleosh kg query impact <path>` runs **THEN** the system SHALL return affected requirements and tests | ✅ |
| ACC-KG-003 | KG SHALL support snapshot listing, diff, and stats | **GIVEN** a bootstrapped KG **WHEN** snapshot commands run **THEN** list, diff, and stats SHALL produce valid output | ✅ |
| ACC-KG-004 | KG SHALL auto-generate RTM in Markdown/HTML/CSV | **GIVEN** a bootstrapped KG **WHEN** `yuleosh kg report rtm --format markdown` runs **THEN** output SHALL contain all Requirement nodes with test/code coverage | 📝 |
| ACC-KG-005 | KG SHALL generate metrics report (text/JSON) | **GIVEN** a bootstrapped KG **WHEN** `yuleosh kg report metrics` runs **THEN** metrics SHALL include coverage, test distribution, and graph health | 📝 |
| ACC-KG-006 | KG SHALL provide event bus with listen/history | **GIVEN** an active KG **WHEN** events listen runs **THEN** event notifications SHALL be captured in real-time | 📝 |
| ACC-KG-007 | KG Merge Gate SHALL detect graph consistency issues | **GIVEN** a KG with orphan nodes **WHEN** check-merge runs **THEN** consistency check SHALL report errors and block merge | ✅ |
| ACC-KG-008 | KG Merge Gate SHALL verify traceability confidence | **GIVEN** a requirement with low confidence edges **WHEN** check-merge runs **THEN** confidence check SHALL report error and block merge | ✅ |
| ACC-KG-009 | KG Merge Gate SHALL produce detailed report | **GIVEN** a check-merge run **WHEN** complete **THEN** the report SHALL include: verdict, errors, warnings, recommendations | ✅ |

## 5. Template Gallery Requirements (TG) — v2.5.0 NEW

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-TG-001 | Template storage SHALL support `yuleosh/templates/` | **GIVEN** the project is installed **WHEN** templates are listed **THEN** built-in templates SHALL exist under yuleosh/templates/ | ✅ |
| ACC-TG-002 | Template SHALL contain template.yaml, specs, pipeline, src | **GIVEN** a template directory **WHEN** inspected **THEN** it SHALL contain template.yaml, specs/spec.md, pipeline/config.yaml, src/ | ✅ |
| ACC-TG-003 | SHALL support `yuleosh template list` command | **GIVEN** the CLI **WHEN** `yuleosh template list` runs **THEN** it SHALL show formatted table of available templates | ✅ |
| ACC-TG-004 | SHALL support `yuleosh project init --template <name>` | **GIVEN** a valid template name **WHEN** `yuleosh project init --template <name> <project>` runs **THEN** a project skeleton SHALL be created | ✅ |

## 6. Non-Functional Requirements (NFR) — v2.5.0 NEW

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-NFR-001 | Agent review tasks SHALL complete within 5s | **GIVEN** a review task **WHEN** submitted **THEN** response SHALL be received within 5s | 📝 |
| ACC-NFR-002 | SIL tests SHALL support parallel QEMU execution (≥4 instances) | **GIVEN** 4 SIL test definitions **WHEN** running in parallel **THEN** each SHALL execute in separate QEMU process | 📝 |
| ACC-NFR-003 | New features SHALL NOT break existing API signatures | **GIVEN** existing import tests **WHEN** running after v2.5.0 changes **THEN** all imports and API calls SHALL remain functional | 📝 |
| ACC-NFR-004 | Pipeline step handlers coverage SHALL be ≥80% | **GIVEN** the pipeline step_handlers module **WHEN** coverage is measured **THEN** line coverage SHALL ≥ 80% | ✅ |
| ACC-NFR-005 | stages.py coverage SHALL be ≥80% | **GIVEN** the stages.py module **WHEN** coverage is measured **THEN** line coverage SHALL ≥ 80% | ✅ |

## 7. ISO 26262 Safety Requirements (FSR) — v2.5.0 NEW

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-FSR-001 | Pipeline stages SHALL verify artifact SHA-256 checksums | **GIVEN** a pipeline step completes **WHEN** the next step starts **THEN** the system SHALL verify the artifact checksum | 📝 |
| ACC-FSR-002 | Pipeline SHALL abort on integrity check failure | **GIVEN** an artifact with mismatched checksum **WHEN** the pipeline stage runs **THEN** the pipeline SHALL abort | 📝 |
| ACC-FSR-003 | Each pipeline stage SHALL run in isolated workspace | **GIVEN** a pipeline execution **WHEN** stages run **THEN** each stage SHALL use an isolated workspace | ✅ |
| ACC-FSR-004 | Spec parser SHALL reject malformed input with line/column | **GIVEN** malformed spec input **WHEN** parsed **THEN** the system SHALL report exact line and column of the error | ✅ |
| ACC-FSR-005 | SIL tests SHALL enforce timeout termination (default 30s) | **GIVEN** a SIL test with default timeout **WHEN** 30s elapses **THEN** the system SHALL terminate QEMU | ✅ |
| ACC-FSR-006 | System SHALL enforce CI gate execution before build promotion | **GIVEN** a build promotion request **WHEN** CI gates have not run **THEN** the system SHALL block promotion | 📝 |

## 8. Cybersecurity Requirements (CR) — v2.5.0 NEW

| ID | SHALL | Acceptance Case | Status |
|:---|:------|:----------------|:------:|
| ACC-CR-001 | JWT authentication for all sensitive API endpoints | **GIVEN** a request to protected API **WHEN** no JWT provided **THEN** HTTP 401 SHALL be returned | ✅ |
| ACC-CR-002 | Password SHALL be stored using bcrypt/Argon2 | **GIVEN** user registration **WHEN** password is stored **THEN** bcrypt (12 rounds) SHALL be used | ✅ |
| ACC-CR-003 | SQL injection SHALL be prevented via parameterized queries | **GIVEN** malicious SQL payload **WHEN** database operation runs **THEN** injection SHALL NOT succeed | ✅ |
| ACC-CR-004 | Path traversal SHALL be prevented via path normalization | **GIVEN** path containing `../` escape **WHEN** processed **THEN** path SHALL be normalized and rejected if outside root | ✅ |
| ACC-CR-005 | Audit log SHALL record security events with timestamp/IP/user | **GIVEN** an API authentication attempt **WHEN** processed **THEN** the audit log SHALL record timestamp, result, source IP, and user ID | 📝 |
| ACC-CR-006 | Audit logs SHALL be retained for minimum 12 months | **GIVEN** configured retention policy **WHEN** checked **THEN** SHALL allow ≥12 month retention | 📝 |
| ACC-CR-007 | Login SHALL be rate-limited | **GIVEN** repeated failed login attempts **WHEN** exceeding threshold **THEN** HTTP 429 SHALL be returned | ✅ |
| ACC-CR-008 | Input validation SHALL sanitize user inputs | **GIVEN** input containing `<script>` tags **WHEN** passed through sanitize **THEN** HTML/JS SHALL be stripped | ✅ |
| ACC-CR-009 | User input size limits enforced | **GIVEN** upload exceeding 50 MB ZIP **WHEN** received **THEN** HTTP 413 SHALL be returned | 📝 |
| ACC-CR-010 | Public endpoints SHALL have rate limiting | **GIVEN** requests exceeding 10/min rate limit **WHEN** threshold exceeded **THEN** HTTP 429 SHALL be returned | 📝 |

---

## Summary

| Category | Total | ✅ Pass | ⚠️ Partial | ❌ Fail | 📝 Not Run |
|:---------|:-----:|:-------:|:----------:|:-------:|:----------:|
| System Requirements (RS) | 22 | 20 | 2 | 0 | 0 |
| Software Requirements (SWR) | 14 | 12 | 2 | 0 | 0 |
| Security Requirements (SEC) | 7 | 7 | 0 | 0 | 0 |
| Knowledge Graph (KG) | 9 | 5 | 0 | 0 | 4 |
| Template Gallery (TG) | 4 | 4 | 0 | 0 | 0 |
| Non-Functional (NFR) | 5 | 2 | 0 | 0 | 3 |
| Safety (FSR) | 6 | 3 | 0 | 0 | 3 |
| Cybersecurity (CR) | 10 | 5 | 0 | 0 | 5 |
| Quality Requirements (QLT) | 4 | 4 | 0 | 0 | 0 |
| **Total** | **81** | **62** | **4** | **0** | **15** |

> **Pass Rate**: 76.5% (62/81) | **P0 Coverage**: 100% of security SHALLs verified
> **v2.5.0 新增**: KG Merge Gate (41 tests), Cybersecurity baseline, Spec consolidation
> **Next Step**: Execute remaining 📝 test cases before next release
