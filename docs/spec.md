# OSH-Fusion 嵌入式开发平台 · 规范文档

> Version: 0.1.1 (MVP) | 状态: 需求定义 | 格式: RS-XXX / SWR-XXX 层级

---

## 1. 系统需求

### RS-001: Agent 驱动的开发流水线
- The system SHALL support an SDD → DDD → TDD → CI/CD pipeline orchestrated by AI agents
- The system SHALL route tasks through the Harness Engineering agent pipeline (PM → Product → Architect/Dev)

#### Reason
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

### RS-002: 需求管理
- The system SHALL provide a requirements tree hierarchy (SYS → SW → Feature → Scenario → Task)
- The system SHALL support spec-delta tracking for requirement changes

#### Reason
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

### RS-003: 代码审查与 Agent 矩阵
- The system SHALL support per-task blocking review by AI agents
- The system SHALL support dual-track review (non-blocking AI self-check + blocking agent review)

#### Reason
质量门禁核心：Agent 审查矩阵是保证代码质量的关键机制

#### SWR-003.1: Agent 审查引擎
- The system SHALL support auto-reviewer routing based on task type
- The system SHALL archive all agent review records as JSON evidence

##### Reason
自动路由确保审查资源合理分配，JSON 归档为审计提供证据

#### SWR-003.2: 覆盖率门禁
- The system SHALL support coverage-guardian with configurable line coverage gate
- The system SHOULD allow the coverage threshold to be set per-project (default > 98%)

##### Reason
高覆盖率指标是嵌入式安全关键系统的质量基线

### RS-004: CI/CD 三层流水线
- The system SHALL provide a 3-layer CI/CD pipeline (Dev Verify → Integration Verify → System Verify)
- The system SHALL support cross-compilation for ARM/RISC-V/x86_64 targets
- The system SHALL support MISRA-C/C++ static analysis gates
- The system SHALL auto-generate ASPICE compliance evidence packages
- The system SHOULD support firmware signing and OTA package generation
- The system MAY support HIL/SIL adapter layer testing

#### Reason
嵌入式专属 CI/CD：标准 CI/CD 不满足嵌入式交叉编译/MISRA/HIL 需求，必须定制三层流水线

### RS-005: 追溯与证据链
- The system SHALL generate a traceability matrix (Req ↔ Design ↔ Code ↔ Test) on each release
- The system SHALL export a compliance pack for ASPICE audit

#### Reason
ASPICE 审计关键产出：追溯矩阵和合规包是认证评审的必备证据

### RS-006: 多端接入
- The system SHALL provide a Web UI for project management
- The system SHOULD provide a mobile-responsive interface
- The system MAY provide a desktop client

#### Reason
平台化需求：用户需要 Web/Mobile/Desktop 三种接入方式覆盖不同工作场景

### RS-007: 多租户 SaaS 架构
- The system SHALL support single-tenant deployment for MVP
- The system SHOULD support multi-tenant isolation
- The system SHOULD provide organization/project/team hierarchy

#### Reason
SaaS 商业化基础：多租户是平台服务的核心架构需求

### RS-008: 嵌入式 SIL 仿真测试
- The system SHALL support Software-in-the-Loop (SIL) testing for ARM Cortex-M targets
- The system SHALL execute the cross-compiled production binary (.elf) under QEMU system emulation
- The system SHALL capture UART and semihosting output from the simulated target for test assertion
- The system SHALL integrate SIL tests into CI L2 as a blocking stage before integration tests
- The system SHALL generate a SIL test report in the compliance evidence pack
- The system SHOULD support SIL testing for RISC-V targets via QEMU
- The system MAY support Renode as an alternative SIL simulation platform
- The system MAY support SIL testing for ARM Cortex-A/R series targets

#### Reason
在没有真实硬件的 CI 环境中，SIL 仿真是验证交叉编译产物运行时行为的唯一手段。ASPICE SWE.5 (软件集成测试) 要求在测试环境中验证软件组件集成，QEMU SIL 提供零硬件成本的集成验证通道。

#### SWR-008.1: QEMU SIL Runner
- The system SHALL provide a `qemu-sil-runner` component that:
  - Loads a compiled .elf file into a QEMU system emulator instance
  - Captures serial output via `-serial stdio` or `-chardev` pipe
  - Supports timeout-based test termination with configurable timeout (default 30s)
  - Reports PASS/FAIL based on serial output assertions (expect-like pattern matching)
  - Returns the full captured serial log on test completion regardless of result
- The system SHALL support ARM Cortex-M3/M4 QEMU machines (e.g. `lm3s6965evb`, `stm32vldiscovery`)
- The system SHOULD support RISC-V QEMU `virt` machine for 64-bit targets
- The system SHOULD support user-provided QEMU machine type and CPU configuration via YAML target config

##### Reason
QEMU SIL Runner 是 SIL 测试的执行引擎，需要封装 QEMU 启动、串口采集、超时中止和断言判定等可复用能力，避免每个测试手动管理 QEMU 子进程。

##### GIVEN a compiled ARM .elf binary exists at a known path
##### WHEN the user invokes `qemu-sil-runner --elf <path> --machine lm3s6965evb --timeout 30`
##### THEN the system SHALL launch a QEMU system emulator process with the specified machine type
##### AND the system SHALL load the .elf binary into the emulated target
##### AND the system SHALL capture all UART serial output from the simulated target
##### AND the system SHALL terminate the QEMU process when the timeout expires
##### AND the system SHALL return a SIL test result containing: passed (bool), log (str), duration_seconds (float)

##### GIVEN a SIL test that expects specific serial output
##### WHEN the test script contains an assertion `serial.expect("Hello World")`
##### THEN the system SHALL scan the captured serial log for the expected string
##### AND the system SHALL report PASS if the string appears before timeout
##### AND the system SHALL report FAIL if the string does not appear before timeout

#### SWR-008.2: HAL Mock 框架
- The system SHALL provide a HAL abstraction mock layer for host-compiled (native) SIL tests
- The system SHALL support HAL mocking for at least: UART (transmit/receive), GPIO (read/write/interrupt), Timer (start/stop/elapsed), I2C (master read/write), SPI (transfer)
- The system SHOULD support HAL call-sequence verification against expected state machine transitions
- The system MAY support automatic mock generation from HAL header files

##### Reason
HAL Mock 框架使嵌入式代码可以在没有硬件的情况下，以宿主机构建模式运行单元测试和集成测试（CI L1 级别）。这是测试左移的关键使能器——在 QEMU SIL 之前，先用 mock 验证 HAL 层逻辑。

##### GIVEN a source file that calls HAL_UART_Transmit() and HAL_GPIO_WritePin()
##### WHEN the file is compiled for the host (not cross-compiled) and linked against the HAL mock library
##### THEN the mock SHALL accept and record all HAL calls without requiring real hardware
##### AND the test code SHALL be able to query the recorded call sequence for verification

##### GIVEN a state machine implementation that must toggle GPIO A before sending UART message
##### WHEN a HAL mock test validates the execution sequence
##### THEN the mock SHALL expose a call-history API that returns all HAL calls in chronological order
##### AND the test SHALL be able to assert `call_history[0] == ("HAL_GPIO_WritePin", "GPIOA", 1)`
##### AND the test SHALL be able to assert `call_history[1] == ("HAL_UART_Transmit", "USART1", expected_data)`

#### SWR-008.3: SIL 测试规范
- The system SHALL require each SIL test to use GIVEN/WHEN/THEN format in its specification
- The system SHALL execute SIL tests as a dedicated CI L2 stage, positioned after cross-compilation and before integration tests
- The system SHALL report SIL test results in the compliance evidence pack with per-test granularity (passed/failed, log snippet, duration)
- A SIL test failure SHALL block the CI pipeline (L2 blocking gate)
- The system SHALL isolate each SIL test in its own QEMU process instance — no shared state between tests
- The system SHOULD support parameterized SIL tests across multiple target machines (ARM M3, M4, RISC-V)
- The system MAY support parallel SIL test execution for independent test cases

##### Reason
SIL 测试是软件集成验证的关键环节，需要标准化测试格式、隔离执行、结果纳入合规包。只有严格规范才能确保 SIL 测试可重复、可审计、可追溯，满足 ASPICE SWE.5 合规要求。

##### GIVEN a set of SIL test definitions in GIVEN/WHEN/THEN format
##### WHEN the CI L2 stage runs SIL tests
##### THEN each test SHALL execute in an isolated QEMU process
##### AND the evidence pack SHALL contain a sil-test-report.json with per-test results
##### AND the pipeline SHALL abort if any SIL test reports FAIL

##### GIVEN two SIL tests that test different target machines (e.g. ARM Cortex-M3 and RISC-V)
##### WHEN the user invokes the SIL test suite
##### THEN each test SHALL use its configured target machine independently
##### AND the system SHALL report results per target in the evidence pack

---

## 2. MVP 验收场景

### Scenario: SDD → DDD → TDD 全流程
- GIVEN a developer has a new feature requirement written in OpenSpec format
- WHEN the developer submits the spec and triggers S.U.P.E.R analysis
- THEN the system SHALL generate a startup-analysis.md
- AND the system SHALL auto-decompose into tasks with kind classification
- AND the system SHALL create isolated worktrees for each task
- AND the system SHALL execute TDD (RED→GREEN→REFACTOR) per task
- AND each task SHALL pass per-task blocking review before commit

### Scenario: CI/CD 三层验证
- GIVEN code has been committed to a worktree branch
- WHEN a PR/MR is created
- THEN Layer 1 CI SHALL run unit tests + coverage gate
- AND Layer 2 CI SHALL run cross-compilation + static analysis + integration tests
- AND upon release tag, Layer 3 CD SHALL run system tests + generate evidence pack

### Scenario: 变更管理
- GIVEN an existing requirement needs to change
- WHEN the user updates the spec with delta markers
- THEN the system SHALL track the diff in spec-delta.md
- AND the system SHALL re-evaluate affected tasks and tests

### Scenario: SIL 仿真测试 (v0.4.0 新增)
- GIVEN a compiled firmware .elf exists after cross-compilation
- WHEN the CI L2 SIL stage runs
- THEN the system SHALL execute each SIL test in an isolated QEMU instance
- AND the system SHALL assert serial output against expected patterns
- AND the system SHALL generate a sil-test-report.json with per-test PASS/FAIL
- AND a failure in any SIL test SHALL block the pipeline
- AND the report SHALL be bundled into the compliance evidence pack

### Scenario: HAL Mock 单元测试
- GIVEN embedded firmware source code that depends on HAL peripheral APIs
- WHEN the developer compiles for host (native) and links against the HAL mock library
- THEN the mock SHALL record all HAL invocations without hardware
- AND the developer SHALL write test assertions against the recorded call history

---

## 3. 非功能性需求

- The system SHALL provide response within 5s for agent review tasks
- The system SHALL support parallel execution of independent tasks
- The system SHALL gracefully handle agent failures with retry (max 5 rounds)
- The system SHOULD maintain task execution logs for traceability
- Each SIL test SHALL have a configurable timeout with a default of 30 seconds
- The system SHALL support at least 4 concurrent QEMU instances for parallel SIL test execution
- The SIL runner SHALL gracefully handle QEMU process crashes and report them as FAIL with the crash log
