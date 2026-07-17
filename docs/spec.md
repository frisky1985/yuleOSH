# yuleOSH · 嵌入式软件合规开发自动化平台 · 规范文档

> **Version**: 2.5.0 | **状态**: 正式发布 | **格式**: RFC 2119 (SHALL/SHOULD/MAY)  
> **编号体系**: RS-XXX (系统需求) / SWR-XXX (软件需求) / KG-XXX (知识图谱) / TG-XXX (模板) / NFR-XXX (非功能) / FSR-XXX (功能安全) / CR-XXX (网络安全)  
> 
> yuleOSH 是由 AI 驱动的 Automotive SPICE 合规开发平台，从需求定义到审计证据包，一站式覆盖嵌入式开发全生命周期。
> 
> **本文档合并了以下源文件**：
> - `docs/spec.md` (v2.3.0 主文档)
> - `specs/spec-delta-sprint2.md` (E2E集成测试 + 模块重构)
> - `specs/spec-delta-sprint3.md` (Pipeline 拆分)
> - `specs/spec-delta-sprint4.md` (覆盖率提升)
> - `specs/spec-delta-sprint5.md` (stages.py 覆盖)
> - `specs/spec-product-v1.md` (模板市场 + Demo + AI 预览)
> - `specs/critical-safety-amendment.md` (P0 关键安全)
> - `docs/spec-delta-kg-next.md` (KG P2 增量)
> - `docs/safety-concept.md` (ISO 26262 安全需求)
> - `docs/swe6-confirmation-spec.md`
> - `docs/review-swe1-software-requirements.md`

---

# 第一部分：系统需求 (RS)

## RS-001: Agent 驱动的开发流水线

- The system SHALL support an SDD → DDD → TDD → CI/CD pipeline orchestrated by AI agents
- The system SHALL route tasks through the Harness Engineering agent pipeline (PM → Product → Architect/Dev)

### Reason
核心架构需求：确保 Agent 编排的开发流程有规范可循、有流水线可自动流转

#### SWR-001.1: 流水线步骤编排
- The system SHALL support the OpenSpec specification format (SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)
- The system SHALL enforce Superpowers 14 Rules at each pipeline stage

##### Reason
流水线各步骤需统一遵守 Superpowers 规范，确保 Agent 行为一致

#### SWR-001.2: 测试规划与追溯
- The system SHALL generate a test plan with requirement traceability matrix for each pipeline run
- The system SHALL map every SHALL statement to at least one test case

##### Reason
ASPICE SWE.4 合规要求：测试规划必须与需求建立双向追溯
- SWE.4-BP3: 分支覆盖跟踪已启用（`--cov-branch`）
- SWE.4-BP4: 性能/资源消耗基线已就绪（`tests/test_perf_baseline.py` + `docs/perf-baseline.md`）

#### SWR-001.3: Pipeline 模块拆分
- The system SHALL split `pipeline/run.py` into at least 3 modules: `orchestrator.py`, `steps.py`, `session.py`
- Each resulting module SHALL be under 500 lines of code
- The public API SHALL remain backward compatible
- The system SHALL convert `pipeline/run.py` into a thin re-export shim (≤100 lines)
- The re-export shim SHALL forward all currently public symbols to their new module locations
- The shim SHALL NOT contain any executable pipeline logic — only import statements

##### GIVEN the current run.py (1668 lines)
##### WHEN conversion to re-export shim is complete
##### THEN run.py SHALL be ≤100 lines and contain zero duplicated step handler or session logic

##### GIVEN an existing test file that imports from yuleosh.pipeline.run
##### WHEN the shim conversion is complete
##### THEN the import SHALL continue to work without modification

## RS-002: 需求管理

- The system SHALL provide a requirements tree hierarchy (SYS → SW → Feature → Scenario → Task)
- The system SHALL support spec-delta tracking for requirement changes

### Reason
ASPICE SYS.3/SWE.1 合规关键：需求是 V-Model 的左起点，所有追溯都依赖于结构化的需求树

#### SWR-002.1: 需求树层次管理
- The system SHALL support OpenSpec RFC 2119 format for all requirements
- The system MAY support requirement baselining and versioning

##### Reason
标准化需求表述格式，确保跨团队一致理解

#### SWR-002.2: 需求变更追踪
- The system SHALL support S.U.P.E.R startup analysis for each new requirement
- The system SHALL track delta between requirement versions for audit

##### Reason
变更管理是 ASPICE 变更管理的核心实践

## RS-003: 代码审查与 Agent 矩阵

- The system SHALL support per-task blocking review by AI agents
- The system SHALL support dual-track review (non-blocking AI self-check + blocking agent review)

### Reason
质量门禁核心：Agent 审查矩阵是保证代码质量的关键机制

#### SWR-003.1: Agent 审查引擎
- The system SHALL support auto-reviewer routing based on task type
- The system SHALL archive all agent review records as JSON evidence

##### Reason
自动路由确保审查资源合理分配，JSON 归档为审计提供证据

#### SWR-003.2: 覆盖率门禁
- The system SHALL support coverage-guardian with configurable line coverage gate
- The system SHALL allow the coverage threshold to be set per-project (default > 85%)

##### Reason
高覆盖率指标是嵌入式安全关键系统的质量基线

## RS-004: CI/CD 三层流水线

- The system SHALL provide a 3-layer CI/CD pipeline (Dev Verify → Integration Verify → System Verify)
- The system SHALL support cross-compilation for ARM/RISC-V/x86_64 targets
- The system SHALL support MISRA-C/C++ static analysis gates
- The system SHALL auto-generate ASPICE compliance evidence packages
- The system SHALL support firmware signing and OTA package generation
- The system SHALL support HIL (Hardware-in-the-Loop) adapter layer testing
- The system SHALL support SIL (Software-in-the-Loop) adapter layer testing

### Reason
嵌入式专属 CI/CD：标准 CI/CD 不满足嵌入式交叉编译/MISRA/HIL 需求，必须定制三层流水线

#### SWR-004.1: CI 可配置化 (v2.5.0)
- The system SHALL provide a per-project CI configuration file (`.yuleosh/ci-config.yaml`)
- The system SHALL support configurable coverage thresholds per project
- The system SHALL provide a CI Layer 2.5 (Hardware-in-the-Loop) positioned between L2 and L3
- The system SHALL support mock mode for L2.5 HIL tests in CI environments without physical hardware
- The system SHALL support configurable layer dependency chain
- The system MAY support per-module coverage thresholds
- The system SHALL support CI layer argument aliases `25` and `2.5` for Layer 2.5

##### GIVEN a yuleOSH project without ci-config.yaml
##### WHEN the CI pipeline loads configuration
##### THEN all settings SHALL use defaults AND L2.5 HIL SHALL default to mock mode

##### GIVEN a developer runs `python3 -m ci.run 2.5`
##### WHEN the CLI processes the layer argument
##### THEN it SHALL recognize both `25` and `2.5` as valid aliases for L2.5

## RS-005: 追溯与证据链

- The system SHALL generate a traceability matrix (Req ↔ Design ↔ Code ↔ Test) on each release
- The system SHALL export a compliance pack for ASPICE audit

### Reason
ASPICE 审计关键产出：追溯矩阵和合规包是认证评审的必备证据

## RS-006: 多端接入

- The system SHALL provide a Web UI for project management
- The system SHALL provide a mobile-responsive interface
- The system MAY provide a desktop client

### Reason
平台化需求：用户需要 Web/Mobile/Desktop 三种接入方式覆盖不同工作场景

## RS-007: 多租户 SaaS 架构

- The system SHALL support single-tenant deployment for MVP
- The system SHALL support multi-tenant isolation
- The system SHALL provide organization/project/team hierarchy

### Reason
SaaS 商业化基础：多租户是平台服务的核心架构需求

## RS-008: 嵌入式 SIL 仿真测试

- The system SHALL support Software-in-the-Loop (SIL) testing for ARM Cortex-M targets
- The system SHALL execute the cross-compiled production binary (.elf) under QEMU system emulation
- The system SHALL capture UART and semihosting output from the simulated target for test assertion
- The system SHALL integrate SIL tests into CI L2 as a blocking stage before integration tests
- The system SHALL generate a SIL test report in the compliance evidence pack
- The system SHALL support SIL testing for RISC-V targets via QEMU
- The system MAY support Renode as an alternative SIL simulation platform

### Reason
在没有真实硬件的 CI 环境中，SIL 仿真是验证交叉编译产物运行时行为的唯一手段。

#### SWR-008.1: QEMU SIL Runner
- The system SHALL provide a `qemu-sil-runner` component that loads .elf, captures serial output, supports timeout-based termination, and reports PASS/FAIL
- The system SHALL support ARM Cortex-M3/M4 QEMU machines (e.g. `lm3s6965evb`, `stm32vldiscovery`)
- The system SHALL support RISC-V QEMU `virt` machine for 64-bit targets

##### GIVEN a compiled ARM .elf binary exists at a known path
##### WHEN the user invokes `qemu-sil-runner --elf <path> --machine lm3s6965evb --timeout 30`
##### THEN the system SHALL launch QEMU, capture UART serial output, terminate on timeout, and return result

#### SWR-008.2: HAL Mock 框架
- The system SHALL provide a HAL abstraction mock layer for host-compiled (native) SIL tests
- The system SHALL support HAL mocking for at least: UART, GPIO, Timer, I2C, SPI
- The system SHALL expose a call-history API for test verification

##### GIVEN a source file that calls HAL_UART_Transmit() and HAL_GPIO_WritePin()
##### WHEN compiled for host and linked against the HAL mock library
##### THEN the mock SHALL record all HAL calls without hardware

#### SWR-008.3: SIL 测试规范
- The system SHALL require each SIL test to use GIVEN/WHEN/THEN format
- The system SHALL execute SIL tests as a dedicated CI L2 stage
- The system SHALL report SIL test results in the compliance evidence pack
- A SIL test failure SHALL block the CI pipeline (L2 blocking gate)
- The system SHALL isolate each SIL test in its own QEMU process instance

## RS-009: Flash 抽象层 (FAL) 与 HIL 硬件测试框架

- The system SHALL provide a Flash Abstraction Layer (FAL) supporting OpenOCD, JLink, and pyOCD backends
- The system SHALL support auto-detection of available flash tools with configurable fallback chain
- The system SHALL provide a Hardware-in-the-Loop (HIL) test runner orchestrating flash → serial → assert lifecycle
- The system SHALL support dual-mode serial capture: physical port (pyserial) and in-process pipe

### Reason
HIL 是嵌入式 CI 流水线的最终验证环节：在 SIL 仿真通过后，真实硬件上验证固件行为。

#### SWR-009.1: Flash Abstraction Layer (FAL)
- The system SHALL provide abstract `FlashTool` base class with `write()`, `erase()`, `verify()` methods
- The system SHALL provide concrete implementations: `OpenOCDRunner`, `JLinkRunner`, `PyOCDRunner`
- The system SHALL provide a `FlashRunner` facade that auto-detects available tools
- FlashRunner SHALL support a preferred-tool override via `tool=` parameter
- FlashRunner SHALL attempt fallback tools in order (OpenOCD → JLink → pyOCD) when primary fails
- Each runner SHALL return a `FlashResult` dataclass with pass/fail status and full log

##### GIVEN the primary flash tool fails (e.g. OpenOCD cannot connect)
##### WHEN fallback tools are available
##### THEN the FlashRunner SHALL automatically retry with the next tool in the fallback chain

#### SWR-009.2: HIL 测试运行器
- The system SHALL provide a `HilTestRunner` class orchestrating: flash → boot → serial → assert → result
- The system SHALL return results as a `HilTestResult` dataclass with phase timings
- The system SHALL support a test script syntax with directives: expect, assert, wait, read_until

##### GIVEN a hardware target connected via serial and flash tool
##### WHEN the user invokes HilTestRunner
##### THEN the system SHALL flash firmware, wait for boot, capture serial, assert patterns, and return result

## RS-010: E2E 全流程集成测试

- The system SHALL provide a fully-mocked E2E test that exercises the pipeline from spec ingestion to evidence pack generation
- The E2E test SHALL mock all external dependencies (LLM, subprocess, file system I/O)
- The E2E test SHALL cover at least 80% of pipeline steps in a single end-to-end run

## RS-011: Template Gallery (模板市场)

- The system SHALL provide a Template Gallery of pre-built project templates
- The system SHALL store built-in templates under `yuleosh/templates/` directory
- Each template SHALL contain at minimum: `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`, `src/`
- The template manifest (`template.yaml`) SHALL include: name, version, description, platforms, tags, spec_sections, pipeline_config
- The system SHALL support at least 5 template directories at install time

#### TG-REQ-001: 模板存储结构
- The system SHALL store built-in templates under `yuleosh/templates/`
- Each template SHALL contain `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`, `src/`

#### TG-REQ-002: 模板搜索优先级
- The system SHALL search for templates in priority order: project-local → user-local → built-in
- User-local templates SHALL supplement (not replace) built-in templates

##### GIVEN a template name exists in both built-in and user-local directories
##### WHEN the system resolves the template
##### THEN the user-local version SHALL be used

#### TG-REQ-003: CLI 模板初始化
- The system SHALL support CLI command `yuleosh project init --template <name> [project_dir]`
- `project init` SHALL create: docs/spec.md, pipeline/config.yaml, src/, yuleosh.yaml
- When `--template` is omitted, the system SHALL enter interactive mode

##### GIVEN the user runs `yuleosh project init --template zephyr-rtos my-zephyr-app`
##### WHEN the template is resolved
##### THEN the system SHALL create `my-zephyr-app/` with pre-populated spec, pipeline config, and source skeleton

#### TG-REQ-004: CLI 模板列表
- The system SHALL support CLI command `yuleosh template list` to enumerate all templates

## RS-012: SaaS Try-it Demo

- The system SHALL provide a "Try Demo" button on the landing page hero section with minimum 48px height
- The system SHALL expose `GET /api/demo/pipeline` endpoint returning pre-seeded mock pipeline data
- The demo endpoint SHALL NOT require authentication or LLM API calls
- The system SHALL provide a `/demo` frontend page with animated pipeline progress UI
- The demo SHALL be rate-limited to 10 requests per minute per IP (HTTP 429 on exceed)

#### SWR-012.1: Demo API 规格
- The `GET /api/demo/pipeline` endpoint SHALL return JSON with pipeline state and steps
- The endpoint SHALL accept `?step=N` to return partial results
- The server SHALL validate demo readiness via `YULEOSH_DEMO_ENABLED` env var (503 when disabled)
- Mock steps SHALL include: Spec Parsing, Requirements Analysis, SDD, Code Generation, Internal Review, Test Plan, Code Review, CI L1-L3

##### GIVEN a client sends `GET /api/demo/pipeline`
##### WHEN the request is received
##### THEN the server SHALL return HTTP 200 without making any LLM API calls

#### SWR-012.2: Demo 前端体验
- The `/demo` page SHALL display all 10 pipeline steps with status animation
- After completion, the page SHALL display final report, "Download Evidence Pack" button, and "Sign Up Free" CTA

## RS-013: AI Preview Assessment (AI 预览评估)

- The system SHALL accept project analysis requests via `POST /api/preview/assess`

#### SWR-013.1: 输入验证与状态轮询
- ZIP uploads SHALL be limited to 50 MB; invalid ZIPs return HTTP 400
- Git URLs SHALL support GitHub, GitLab, Bitbucket; unsupported hosts return HTTP 400
- Clone timeout SHALL be 120 seconds; timeout returns HTTP 408
- Cloned repos SHALL be limited to 200 MB; excess returns HTTP 413
- The system SHALL provide `GET /api/preview/assess/<preview_id>` for status polling

##### GIVEN a client sends POST with a valid .zip file
##### WHEN the request is received
##### THEN the server SHALL return HTTP 202 with preview_id

#### SWR-013.2: 分析报告内容
- The coverage prediction SHALL include: current_coverage_estimate, projected_coverage_after_yuleosh, confidence, bottleneck_files
- The compliance risk SHALL analyze: MISRA-C violations, coding standard adherence, ASPICE readiness, safety-critical risk factors
- The recommended pipeline config SHALL include: recommended_template, steps, ci_layers, review_gates, yaml_snippet

#### SWR-013.3: 匿名使用与限制
- Unauthenticated users SHALL be limited to 3 preview assessments per 24 hours per IP
- Authenticated users SHALL have a limit of 20 per 24 hours
- Rate limit exceeded SHALL return HTTP 429
- Preview results SHALL be retained for 24 hours

## RS-014: SaaS 用户生命周期管理

- The system SHALL support user registration via name/email/password
- After registration the system SHALL auto-create a free Trial project
- The system SHALL return a JWT token for password-less first login
- The system SHALL allow users to view current subscription plan and usage
- The system SHALL support upgrade from Trial to Pro plan via Stripe Checkout

#### SWR-014.1: Stripe 支付
- The system SHALL use Stripe Checkout for paid upgrade processing
- After successful payment the system SHALL update the user's subscription status
- The system SHALL verify Stripe webhook event signatures

## RS-015: 知识图谱 (Knowledge Graph)

- The system SHALL maintain a traceability knowledge graph (TKG) linking requirements, code, tests, and reviews
- The system SHALL support incremental graph build for CI integration
- The system SHALL support graph snapshots for baseline comparison

#### KG-001: 增量构建 (KG-05 / KG-10)
- The system SHALL support incremental knowledge graph build from git changes
- The system SHALL detect changed files from git diff and selectively rebuild deltas
- The system SHALL support full bootstrap from traceability data

##### GIVEN a set of changed files detected by git diff
##### WHEN the incremental build runs
##### THEN the system SHALL update only the affected nodes and edges

#### KG-002: 图查询 (KG-20 / KG-25)
- The system SHALL support impact analysis query for changed files
- The system SHALL support snapshot listing, diff, and comparison
- The system SHALL provide graph statistics (nodes, edges, types distribution)

#### KG-003: 追溯矩阵生成 (KG-40-RTM, v2.5.0)
- The system SHALL provide automatic RTM generation from the knowledge graph
- RTM generation SHALL support Markdown, HTML, and CSV output formats
- RTM content SHALL include columns: Requirement ID, Statement, Test Files, Test Functions, Code Files, Status, Confidence
- RTM generation SHALL support per-layer filtering (unit/integration/sil/hil/system)
- The CLI command `yuleosh kg report rtm` SHALL trigger RTM generation

##### GIVEN a bootstrapped knowledge graph
##### WHEN executing `yuleosh kg report rtm --format markdown`
##### THEN output SHALL contain all Requirement nodes with test/code coverage

#### KG-004: 度量报告 (KG-METRICS, v2.5.0)
- The system SHALL provide metrics computation from the knowledge graph
- Metrics SHALL include: coverage percentage, test distribution by layer, graph health, change trend across snapshots
- The system SHALL support JSON and text output formats
- The CLI command `yuleosh kg report metrics` SHALL trigger metrics generation

#### KG-005: 事件通知 (KG-EVENT, v2.5.0)
- The system SHALL provide an event bus for KG state change notifications
- The system SHALL support `yuleosh kg events listen` for real-time event streaming
- The system SHALL support `yuleosh kg events history` for event log retrieval

#### KG-042: Merge Gate (v2.5.0, NEW)
- The system SHALL provide a KG Merge Gate that validates PR eligibility before merge
- The merge gate SHALL perform: incremental build trigger, graph consistency verification, confidence threshold check
- The merge gate SHALL block merges failing consistency or confidence checks
- The CLI command `yuleosh kg check-merge` SHALL trigger merge gate execution
- The pipeline SHALL include a `merge-gate` step in the PIPELINE_STEPS registry

##### GIVEN changed files are detected
##### WHEN `yuleosh kg check-merge` is invoked
##### THEN the gate SHALL verify graph consistency, check confidence thresholds, and output verdict

##### GIVEN the graph has orphan nodes exceeding the threshold
##### WHEN the merge gate consistency check runs
##### THEN the gate SHALL return verdict "fail" with detailed error report

##### GIVEN all consistency and confidence checks pass
##### WHEN the merge gate runs
##### THEN the gate SHALL return verdict "pass" allowing the merge to proceed

---

# 第二部分：非功能需求 (NFR)

## NFR-001: 性能

- The system SHALL provide response within 5s for agent review tasks
- The system SHALL support parallel execution of independent pipeline tasks
- The system SHALL gracefully handle agent failures with retry (max 5 rounds)
- Each SIL test SHALL have a configurable timeout with a default of 30 seconds
- The system SHALL support at least 4 concurrent QEMU instances for parallel SIL test execution
- The SIL runner SHALL gracefully handle QEMU process crashes and report them as FAIL with the crash log

## NFR-002: 可观测性

- The system SHALL maintain task execution logs for traceability
- The CLI output SHALL use ANSI color coding (green for success, yellow for warning)
- Pipeline step execution SHALL report token usage per step
- The system SHALL persist pipeline session logs to `.osh/sessions/`

## NFR-003: 向后兼容

- All new features SHALL NOT modify P0/P1 existing API signatures and behavior
- The re-export shim for pipeline/run.py SHALL preserve all public import paths
- Each incremental module SHALL be independently verifiable without other module dependencies

## NFR-004: 可观测性

- All modules SHALL provide CLI and log output for observability
- KG build operations SHALL write JSON logs to `knowledge-graph/` directory
- The merge gate SHALL write report to configurable output path

## NFR-005: 可靠性

- The system SHALL use isolated workspaces per pipeline run to prevent artifact contamination
- Feature gates (e.g., `--mock`, `YULEOSH_DEMO_ENABLED`) SHALL have safe defaults
- CI configuration SHALL fall back to safe defaults when config file is missing or invalid

## NFR-006: 覆盖率

- Python line coverage gate SHALL default to ≥85% for source modules
- Pipeline step handlers sub-module coverage SHALL be ≥80%
- `stages.py` coverage SHALL be ≥80%

---

# 第三部分：功能安全需求 (FSR) — ISO 26262:2018

> 参考文档: `docs/safety-concept.md` | ASIL: QM–D

## FSR-001: 安全目标 (SG)

### SG-001: Pipeline Execution Integrity (ASIL B)
- The system SHALL verify artifact checksum (SHA-256) after each pipeline stage
- The system SHALL abort the pipeline if any artifact integrity check fails
- The system SHALL log integrity failures with stage ID and artifact path
- The system SHALL execute each pipeline stage in an isolated workspace
- The system SHALL clean the workspace between pipeline runs
- The system SHALL reject cross-stage file references that violate stage boundaries

### SG-002: Spec Parsing Integrity (ASIL C)
- The system SHALL reject spec files containing unrecognized syntax constructs
- The system SHALL validate all SHALL/SHOULD/MAY statements against RFC 2119 grammar
- The system SHALL reject spec files exceeding a configurable maximum size (default 10 MB)
- The system SHALL report the exact line and column of any parse error
- The system SHALL NOT proceed to pipeline execution if spec parsing fails

### SG-003: CI/CD Gate Integrity (ASIL B)
- The system SHALL enforce that all configured CI gates execute before any build promotion
- The system SHALL NOT allow manual override of CI gate results without audit trail
- The system SHALL record every gate override with user ID, reason, and timestamp
- The system SHALL compare line/branch coverage against the configured threshold
- The system SHALL reject coverage data that is incomplete or corrupted

### SG-004: Authentication & Access Control (ASIL C)
- The system SHALL require valid JWT bearer tokens for all sensitive API endpoints
- The system SHALL reject requests with expired, revoked, or malformed tokens
- The system SHALL log all authentication failures with IP address and timestamp
- The system SHALL enforce role-based access (admin/member/viewer) for all operations
- The system SHALL deny write operations for read-only roles
- The system SHALL deny admin operations for non-admin roles

### SG-005: Audit Trail Integrity (ASIL A)
- The system SHALL record every API request (method, path, status, IP, duration)
- The system SHALL record every pipeline execution with stage-level granularity
- The system SHALL record every CI gate result with pass/fail/error distinction
- The system SHALL NOT allow deletion of audit log entries
- The system SHALL retain audit logs for a minimum of 12 months
- The audit logging system SHALL operate independently of the main request handling

### SG-006: Evidence Pack Integrity (ASIL A)
- The system SHALL generate evidence only from completed, verified pipeline runs
- The system SHALL include a manifest with SHA-256 checksums for every artifact
- The system SHALL verify evidence pack integrity on download (manifest checksums)
- The system SHALL log evidence pack verification results

### SG-007: SIL/HIL Test Safety (ASIL D)
- The system SHALL enforce timeout-based termination (default 30s) for all SIL tests
- The system SHALL isolate each SIL test in its own QEMU process
- The system SHALL clean up QEMU processes after test completion or timeout
- The system SHALL verify target connectivity before attempting to flash
- The system SHALL verify flash integrity (checksum comparison) after programming
- The system SHALL verify firmware binary checksum before flashing
- The system SHALL NOT flash firmware with unresolved safety violations

## FSR-002: 功能安全需求 (FSR)

### FSR-002.1: Error Detection
| ID | SHALL | ASIL | Ref SG |
|:---|:------|:----:|:------:|
| FSR-001-01 | The system SHALL detect pipeline stage execution failures within 500 ms | B | SG-001 |
| FSR-001-02 | The system SHALL detect spec parsing errors with line/column precision | C | SG-002 |
| FSR-001-03 | The system SHALL detect CI gate bypass attempts at runtime | B | SG-003 |
| FSR-001-04 | The system SHALL detect invalid/expired JWT tokens on each request | C | SG-004 |
| FSR-001-05 | The system SHALL detect evidence pack integrity violations on generation | A | SG-006 |
| FSR-001-06 | The system SHALL detect SIL test timeout and terminate the QEMU process | D | SG-007 |

### FSR-002.2: Error Response
| ID | SHALL | ASIL | Ref SG |
|:---|:------|:----:|:------:|
| FSR-002-01 | On stage failure, the system SHALL abort pipeline and mark downstream blocked | B | SG-001 |
| FSR-002-02 | On spec parse error, the system SHALL return 400-level error with diagnostics | C | SG-002 |
| FSR-002-03 | On CI gate failure, the system SHALL block build promotion | B | SG-003 |
| FSR-002-04 | On auth failure, the system SHALL return 401 and log the attempt | C | SG-004 |
| FSR-002-05 | On evidence integrity failure, the system SHALL reject the pack | A | SG-006 |
| FSR-002-06 | On HIL communication failure, the system SHALL abort and not attempt flash | D | SG-007 |

### FSR-002.3: Fault Tolerance
| ID | SHALL | ASIL | Ref SG |
|:---|:------|:----:|:------:|
| FSR-003-01 | The system SHALL use isolated workspaces per pipeline run | B | SG-001 |
| FSR-003-02 | The system SHALL use parameterized queries for all database operations | C | SG-004 |
| FSR-003-03 | The system SHALL apply path normalization to prevent traversal attacks | C | SG-004 |
| FSR-003-04 | The system SHALL clean up all QEMU processes on test timeout or abort | D | SG-007 |
| FSR-003-05 | The audit logging system SHALL operate independently of main request handling | A | SG-005 |

---

# 第四部分：网络安全需求 (CR)

## CR-001: API 鉴权

- The system SHALL require JWT bearer tokens for all API endpoints except public routes
- The system SHALL verify JWT signature and expiration on each request
- The system SHALL reject expired, revoked, or malformed tokens with HTTP 401
- The system SHALL log all authentication failures with IP, timestamp, and attempted resource
- The system SHALL support token refresh with configurable expiry

## CR-002: 数据加密

- The system SHALL encrypt all database connections using TLS (minimum TLS 1.2)
- The system SHALL store user passwords using bcrypt or Argon2 hashing
- The system SHALL encrypt sensitive configuration (API keys, tokens) at rest
- The system SHALL NOT log plaintext credentials or API keys
- The system SHALL support HTTPS for all web and API traffic

## CR-003: 日志审计

- The system SHALL record all security-relevant events to the audit log
- Audit log entries SHALL include: timestamp, event type, user ID, source IP, resource, action, result
- The system SHALL NOT allow modification or deletion of audit log entries
- The system SHALL support audit log export in tamper-evident format
- Audit logs SHALL be retained for a minimum of 12 months

## CR-004: 输入验证

- The system SHALL validate and sanitize all user inputs before processing
- The system SHALL reject spec files containing embedded scripts or control characters
- The system SHALL apply path normalization to prevent directory traversal attacks
- The system SHALL limit upload sizes (50 MB ZIP, 10 MB spec files)
- The system SHALL use parameterized queries for all database operations

## CR-005: 网络安全合规 (ISA/IEC 62443 基线)

- The system SHALL support role-based access control (admin/member/viewer) as per SL-2
- The system SHALL provide audit logging for all security events as per SL-2
- The system SHALL enforce secure communication (TLS) for all network traffic
- The system SHALL implement rate limiting for public API endpoints
- The system SHALL support session timeout and automatic logout

> 完整网络安全基线文档见: `docs/cybersecurity-baseline.md`

---

# 第五部分：验收场景

## Scenario: SDD → DDD → TDD 全流程
- GIVEN a developer has a new feature requirement written in OpenSpec format
- WHEN the developer submits the spec and triggers S.U.P.E.R analysis
- THEN the system SHALL generate a startup-analysis.md and execute TDD (RED→GREEN→REFACTOR) per task

## Scenario: CI/CD 三层验证
- GIVEN code has been committed to a worktree branch
- WHEN a PR/MR is created
- THEN Layer 1 CI SHALL run unit tests + coverage gate
- AND Layer 2 CI SHALL run cross-compilation + static analysis + integration tests
- AND Layer 2.5 CI SHALL run HIL tests
- AND upon release tag, Layer 3 CD SHALL generate evidence pack

## Scenario: SIL 仿真测试
- GIVEN a compiled firmware .elf exists after cross-compilation
- WHEN the CI L2 SIL stage runs
- THEN the system SHALL execute each SIL test in an isolated QEMU instance
- AND the system SHALL assert serial output against expected patterns

## Scenario: KG Merge Gate 验证
- GIVEN code changes are ready for merge
- WHEN the KG merge gate runs
- THEN the system SHALL trigger incremental KG build
- AND the system SHALL verify graph consistency (no orphans, no cycles)
- AND the system SHALL verify traceability confidence (min 70%)
- AND the system SHALL block the merge if either check fails

## Scenario: 网络安全 — API 鉴权失败
- GIVEN a client sends a request to a protected endpoint without valid JWT
- WHEN the request is received
- THEN the system SHALL return HTTP 401
- AND the system SHALL log the attempt with IP and timestamp
- AND the system SHALL NOT process the request further

---

# 第六部分：版本历史

| 版本 | 日期 | 变更说明 |
|:----|:-----|:---------|
| v2.5.0 | 2026-07-17 | 合并所有 delta spec 至主文档；新增 KG-042 Merge Gate；新增网络安全 CR-001~005；重编需求编号体系；新增 NFR、FSR 章节 |
| v2.4.0 | 2026-07-16 | Phase 1 完成：安全修复、ASPICE 检查清单、ISO 26262 骨架 |
| v2.3.0 | 2026-06-15 | 产品线 spec 合并（Template Gallery / Demo / AI Preview / SaaS） |

---

*本文档使用 RFC 2119 规范语言（SHALL / SHALL NOT / SHOULD / MAY）。*
*SHALL 级条件阻塞发布，SHOULD 级优先完成，MAY 级可选。*
