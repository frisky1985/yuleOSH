# yuleOSH · 一站式 ASPICE 合规开发平台 · 规范文档

> Version: 1.0.0 | 状态: 发布候选 | 格式: RS-XXX / SWR-XXX 层级
>
> yuleOSH 是由 AI 驱动的 Automotive SPICE 合规开发平台，从需求定义到审计证据包，一站式覆盖嵌入式开发全生命周期。

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
- SWE.4-BP3: 分支覆盖跟踪已启用（`--cov-branch`）
- SWE.4-BP4: 性能/资源消耗基线已就绪（`tests/test_perf_baseline.py` + `docs/perf-baseline.md`）

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
- The system SHALL support HIL (Hardware-in-the-Loop) adapter layer testing
- The system SHALL support SIL (Software-in-the-Loop) adapter layer testing

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

### RS-009: Flash 抽象层 (FAL) 与 HIL 硬件测试框架 (v0.5.0 新增)
- The system SHALL provide a Flash Abstraction Layer (FAL) supporting OpenOCD, JLink, and pyOCD backends
- The system SHALL support auto-detection of available flash tools with configurable fallback chain
- The system SHALL provide a Hardware-in-the-Loop (HIL) test runner orchestrating flash → serial → assert lifecycle
- The system SHALL support dual-mode serial capture: physical port (pyserial) and in-process pipe
- The system SHALL support test script execution with expect/regex/assert/wait directives
- The system SHOULD support parallel HIL test execution for multi-board setups
- The system MAY support ST-Link CLI and DAPLink as additional flash backends

#### Reason
HIL 是嵌入式 CI 流水线的最终验证环节：在 SIL 仿真通过后，真实硬件上验证固件行为。Flash Abstraction Layer 解决多工具碎片化问题，提供统一的 flash/erase/verify 接口。

#### SWR-009.1: Flash Abstraction Layer (FAL)
- The system SHALL provide abstract `FlashTool` base class with `write()`, `erase()`, `verify()` methods
- The system SHALL provide concrete implementations: `OpenOCDRunner`, `JLinkRunner`, `PyOCDRunner`
- The system SHALL provide a `FlashRunner` facade that auto-detects available tools
- FlashRunner SHALL support a preferred-tool override via `tool=` parameter
- FlashRunner SHALL attempt fallback tools in order (OpenOCD → JLink → pyOCD) when primary fails
- Each runner SHALL return a `FlashResult` dataclass with: passed (bool), log (str), tool (str), elapsed (float), error (str | None)
- The system SHALL provide `flash_firmware()` and `detect_hardware()` convenience functions
- Flash tools SHALL be configured per target in `.yuleosh/targets/*.yaml` via `flash_openocd`, `flash_jlink`, `flash_pyocd` fields

##### Reason
统一烧录接口消除工具碎片化。ABC 模式确保每个 runner 实现相同协议。fallback 链提高硬件测试鲁棒性。

##### GIVEN a developer has a compiled firmware .elf and a hardware target
##### WHEN the developer calls `FlashRunner(target="stm32f4").flash("firmware.elf")`
##### THEN the system SHALL auto-detect the preferred available flash tool (or use the explicitly specified one)
##### AND the system SHALL construct the appropriate command line and execute it
##### AND the system SHALL return a FlashResult with pass/fail status and full log

##### GIVEN the primary flash tool fails (e.g. OpenOCD cannot connect)
##### WHEN fallback tools are available
##### THEN the FlashRunner SHALL automatically retry with the next tool in the fallback chain
##### AND if all tools fail, the FlashRunner SHALL return a FlashResult with passed=False and last error

#### SWR-009.2: 串口监视器 (Serial Monitor)
- The system SHALL provide a `SerialMonitor` class for physical serial ports via pyserial
- The system SHALL provide a `PipeSerialMonitor` class for in-process pipe or StringIO capture
- Both monitor variants SHALL support:
  - `expect(pattern, timeout, fail_fast)` — blocking pattern match
  - `expect(pattern, regex=True)` — regex pattern match
  - `expect_all(patterns)` — match multiple patterns in order
  - `read_until(marker)` — read up to a delimiter
  - `assert_text_present(text)` / `assert_text_absent(text)` — log assertions
  - `captured_log` property — full captured output
- The monitors SHALL run background capture threads with thread-safe log accumulation
- The monitors SHALL raise `SerialMonitorTimeout` on pattern match failure

##### Reason
串口是嵌入式设备的标准调试输出通道。双模式设计允许真实硬件（pyserial）和仿真（pipe）使用同一套断言 API。

##### GIVEN a serial monitor connected to a hardware target outputting "Boot OK"
##### WHEN the monitor calls `expect("Boot OK", timeout=10)`
##### THEN it SHALL return the matched text if the pattern appears before timeout
##### AND it SHALL raise `SerialMonitorTimeout` if the pattern does not appear

#### SWR-009.3: HIL 测试运行器 (HIL Test Runner)
- The system SHALL provide a `HilTestRunner` class orchestrating the full test lifecycle:
  1. Flash firmware to target using FAL
  2. Wait for target boot (configurable flash_delay)
  3. Open serial connection
  4. Execute test script with assertions
  5. Return HIL test result with phase timings
- The system SHALL return results as a `HilTestResult` dataclass with: passed (bool), flash_result, boot_log, error, phase_timings
- The system SHALL support a test script syntax with directives:
  - `expect:<text>` — blocking pattern match
  - `expect_re:<regex>` — regex pattern match
  - `assert:<text>` — non-blocking log assertion
  - `assert_not:<text>` — assert text absent
  - `wait:<seconds>` — pause execution
  - `read_until:<marker>` — read serial up to marker
  - `# comment` — ignored lines
- The system SHALL provide shortcut methods: `flash_and_expect()`, `flash_and_boot()`, `skip_flash_test()`
- The system SHALL provide `hil_test()` one-shot convenience function

##### Reason
HIL 测试运行器封装了嵌入式硬件测试的全生命周期（烧录→等待→采集→断言），提供统一的脚本化测试体验。

##### GIVEN a hardware target connected via serial and flash tool
##### WHEN the user invokes `HilTestRunner(target="stm32f4").run(firmware="app.elf", expect_pattern="Boot Complete")`
##### THEN the system SHALL flash the firmware
##### AND the system SHALL wait for the target to boot
##### AND the system SHALL open the serial port and capture output
##### AND the system SHALL assert the expected pattern appears before timeout
##### AND the system SHALL return a HilTestResult with pass/fail, boot log, and phase timings

### RS-011: Template Gallery (模板市场) (v1.0.0 新增)
- The system SHALL provide a Template Gallery of pre-built project templates
- The system SHALL store built-in templates under `yuleosh/templates/` directory
- Each template SHALL contain at minimum: `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`, `src/`
- The template manifest (`template.yaml`) SHALL include: name, version, description, platforms, tags, spec_sections, pipeline_config
- The system SHALL support at least 5 template directories at install time

#### Reason
模板化项目管理是产品化的关键能力，降低新项目启动门槛。用户只需选择模板即可获得完整的 OpenSpec + pipeline + 代码骨架。

#### SWR-011.1: 模板搜索优先级
- The system SHALL search for templates in priority order: project-local → user-local → built-in
- User-local templates SHALL supplement (not replace) built-in templates

##### Reason
三层搜索优先级确保平台升级不影响用户自定义模板，同时用户可覆盖内置模板。

##### GIVEN a template name exists in both built-in and user-local directories
##### WHEN the system resolves the template
##### THEN the user-local version SHALL be used
##### AND files only present in the built-in version SHALL be inherited

#### SWR-011.2: CLI 模板初始化和列表
- The system SHALL support CLI command `yuleosh project init --template <name> [project_dir]`
- The system SHALL support CLI command `yuleosh template list` to enumerate all templates
- `project init` SHALL create: docs/spec.md, pipeline/config.yaml, src/, yuleosh.yaml
- When `--template` is omitted, the system SHALL enter interactive mode listing available templates
- The init command SHALL NOT overwrite existing files unless `--force` is specified

##### Reason
CLI 是 Developer Experience 的核心入口。模板选择和初始化流程应在 CLI 中无缝完成。

##### GIVEN the user runs `yuleosh project init --template zephyr-rtos my-zephyr-app`
##### WHEN the template is resolved
##### THEN the system SHALL create `my-zephyr-app/` with pre-populated spec, pipeline config, and source skeleton

##### GIVEN the user runs `yuleosh project init` without `--template`
##### WHEN no flag is provided
##### THEN the system SHALL display an interactive numbered list of all available templates

### RS-012: SaaS Try-it Demo (v1.0.0 新增)
- The system SHALL provide a "Try Demo" button on the landing page hero section with minimum 48px height
- The system SHALL expose `GET /api/demo/pipeline` endpoint returning pre-seeded mock pipeline data
- The demo endpoint SHALL NOT require authentication or LLM API calls
- The system SHALL provide a `/demo` frontend page with animated pipeline progress UI
- The demo SHALL be rate-limited to 10 requests per minute per IP (HTTP 429 on exceed)
- The demo experience SHALL be fully functional without user registration

#### Reason
SaaS Demo 是市场获客的核心工具。用户可在无需注册的情况下体验 yuleOSH 的完整 pipeline 能力。Mock 数据保证稳定性和低延迟。

#### SWR-012.1: Demo API 规格
- The `GET /api/demo/pipeline` endpoint SHALL return JSON with: status, pipeline_id, total_steps, current_step, steps[], final_report, evidence_pack_url
- The endpoint SHALL accept `?step=N` to return partial results (status="running")
- The server SHALL validate demo readiness via `YULEOSH_DEMO_ENABLED` env var (default: enabled, 503 when disabled)
- Mock steps SHALL include: Spec Parsing, Requirements Analysis, SDD, Code Generation, Internal Review, Test Plan, Code Review, CI L1-L3
- The server SHALL expose `GET /api/demo/evidence/<pipeline_id>.zip` with pre-seeded mock evidence pack

##### Reason
标准化的 Demo API 确保前后端解耦。step 参数允许前端实现渐进式动画效果。

##### GIVEN a client sends `GET /api/demo/pipeline`
##### WHEN the request is received
##### THEN the server SHALL return HTTP 200 with the full JSON schema
##### AND the response SHALL NOT make any LLM API calls

##### GIVEN `YULEOSH_DEMO_ENABLED=false` is set
##### WHEN a client sends `GET /api/demo/pipeline`
##### THEN the server SHALL return HTTP 503

#### SWR-012.2: Demo 前端体验
- The `/demo` page SHALL display all 10 pipeline steps with status animation (pending → running → completed)
- The page SHALL show expandable step details (output summary and artifacts)
- After completion, the page SHALL display: final report, "Download Evidence Pack" button, "Sign Up Free" CTA
- The page SHALL NOT require authentication before showing results

##### Reason
Demo 页面是产品能力的第一印象。动画效果和可展开详情提升了用户参与感。

##### GIVEN a user navigates to `/demo`
##### WHEN all 10 steps complete
##### THEN the final report SHALL be visible with download button and sign-up CTA

### RS-013: AI Preview Assessment (AI 预览评估) (v1.0.0 新增)
- The system SHALL accept project analysis requests via `POST /api/preview/assess`

#### Reason
AI Preview Assessment 是市场漏斗的中间环节：Demo 吸引 → Preview 建立信任 → 注册转化。用户在提交代码前即可获得价值评估。

#### SWR-013.1: 输入验证与状态轮询
- ZIP uploads SHALL be limited to 50 MB; invalid ZIPs return HTTP 400
- Git URLs SHALL support GitHub, GitLab, Bitbucket; unsupported hosts return HTTP 400
- Clone timeout SHALL be 120 seconds; timeout returns HTTP 408
- Cloned repos SHALL be limited to 200 MB; excess returns HTTP 413
- The system SHALL provide `GET /api/preview/assess/<preview_id>` for status polling (analyzing/completed/failed)
- Extracted files SHALL be scanned for supported extensions only (`.c`, `.h`, `.py`, `.yaml`, `.md`, `.cfg`, `.cmake`, etc.)

##### Reason
输入验证和资源限制防止恶意或意外的大负载拖垮服务。轮询 API 支持异步分析流程。

##### GIVEN a client sends `POST /api/preview/assess` with a valid `.zip` file
##### WHEN the request is received
##### THEN the server SHALL return HTTP 202 with preview_id and status="analyzing"

##### GIVEN a client uploads a 60 MB ZIP file
##### WHEN the server receives the request
##### THEN the server SHALL reject with HTTP 413

#### SWR-013.2: 分析报告内容
- The coverage prediction SHALL estimate line coverage based on: test framework detection, test file density, call graph analysis
- The prediction SHALL include: current_coverage_estimate, projected_coverage_after_yuleosh, confidence, bottleneck_files
- The compliance risk SHALL analyze: MISRA-C violations, coding standard adherence, ASPICE readiness, safety-critical risk factors
- Risk factors SHALL include: risk_level, description, occurrences, recommendation
- The recommended pipeline config SHALL include: recommended_template, steps, ci_layers, review_gates, yaml_snippet

##### Reason
三个分析维度覆盖用户最关心的核心问题：我的测试够吗？我合规吗？yuleOSH 能帮我做什么？

#### SWR-013.3: 匿名使用与限制
- Unauthenticated users SHALL be limited to 3 preview assessments per 24 hours per IP
- Authenticated users SHALL have a limit of 20 per 24 hours
- Rate limit exceeded SHALL return HTTP 429
- Preview results SHALL be retained for 24 hours, after which they MAY be deleted
- Cloned repositories SHALL be cleaned up within 30 minutes
- The system MAY cache results by git repo URL hash within 24 hours

##### Reason
预览评估是资源密集型操作。限流保护后端稳定性，匿名/已认证的区分鼓励注册转化。

##### GIVEN an unauthenticated IP has submitted 3 preview assessments in the last 24 hours
##### WHEN the 4th request arrives
##### THEN the server SHALL return HTTP 429

### RS-014: SaaS 用户生命周期管理 (v1.0.0 新增)

**描述**: yuleOSH SHALL 提供完整的用户注册、订阅管理和 Stripe 支付集成
**优先级**: P0
**Reason**: 产品化必须支持用户从注册到付费的完整闭环

#### SWR-014.1: 用户注册
- The system SHALL support user registration via name/email/password
- After registration the system SHALL auto-create a free Trial project
- The system SHALL return a JWT token for password-less first login

##### Reason
零阻力的首次用户体验：注册即用，无需手动创建项目或额外验证步骤。

##### GIVEN a new user submits registration with name, email, and password
##### WHEN the registration endpoint is called
##### THEN the system SHALL create a user account
##### AND the system SHALL auto-create a free Trial project
##### AND the system SHALL return a JWT token for immediate access

#### SWR-014.2: 订阅管理
- The system SHALL allow users to view current subscription plan and usage
- The system SHALL support upgrade from Trial to Pro plan
- The system SHOULD support subscription cancellation

##### Reason
订阅管理是 SaaS 计费的核心环节。用户需要透明地了解当前套餐状态和用量，自主完成升级/降级操作。

##### GIVEN a Trial user navigates to subscription settings
##### WHEN the user requests to view their current plan
##### THEN the system SHALL display the current plan name, usage limits, and remaining quota
##### AND the system SHALL provide an upgrade CTA to Pro plan

##### GIVEN a Trial user initiates an upgrade to Pro
##### WHEN the upgrade flow is triggered
##### THEN the system SHALL redirect to Stripe Checkout for payment

#### SWR-014.3: Stripe 支付
- The system SHALL use Stripe Checkout for paid upgrade processing
- The system SHALL support creating and managing subscription plans
- After successful payment the system SHALL update the user's subscription status

##### Reason
Stripe Checkout 是业界标准的安全支付流程。通过 server-side webhook 确认支付结果，确保订阅状态准确可靠。

##### GIVEN a user completes Stripe Checkout payment successfully
##### WHEN the Stripe webhook delivers a `checkout.session.completed` event
##### THEN the system SHALL verify the event signature
##### AND the system SHALL update the user's subscription status to Pro

##### GIVEN an admin creates a new subscription plan in Stripe
##### WHEN the plan is created
##### THEN the system SHALL sync the plan configuration to local data

---

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

### Scenario: Flash 烧录 + HIL 硬件测试 (v0.5.0 新增)
- GIVEN a compiled firmware .elf and a physical hardware target
- WHEN the user invokes the HIL test runner
- THEN the system SHALL auto-detect the appropriate flash tool (OpenOCD/JLink/pyOCD)
- AND the system SHALL flash the firmware via the detected tool
- AND the system SHALL open serial connection to the target
- AND the system SHALL assert serial output against expected patterns
- AND the system SHALL return a HIL test result with pass/fail and full boot log

- GIVEN the primary flash tool fails during firmware write
- WHEN fallback tools are available
- THEN the system SHALL automatically retry with the next available tool
- AND the system SHALL continue with serial verification on success

### Scenario: 模板初始化 (v1.0.0 新增)
- GIVEN a user runs `yuleosh project init --template zephyr-rtos my-zephyr-app`
- WHEN the template is resolved
- THEN the system SHALL create a complete project skeleton with docs/spec.md, pipeline/config.yaml, src/, and yuleosh.yaml
- AND the generated spec SHALL contain pre-populated Zephyr RTOS requirement sections
- AND the generated pipeline config SHALL include Zephyr-specific steps

- GIVEN the user runs `yuleosh project init` without `--template`
- WHEN no template is specified
- THEN the system SHALL display an interactive numbered list of available templates

### Scenario: SaaS Demo Pipeline (v1.0.0 新增)
- GIVEN a user visits the landing page
- WHEN the user clicks "Try Demo"
- THEN the system SHALL navigate to `/demo` without requiring login
- AND the demo page SHALL call `GET /api/demo/pipeline`
- AND the page SHALL animate through 10 pipeline steps with status transitions (pending → running → completed)
- AND after all steps complete, the page SHALL display the final report, evidence pack download, and sign-up CTA

- GIVEN a client sends `GET /api/demo/pipeline?step=3`
- WHEN the request is received
- THEN steps 0-2 SHALL have status "completed"
- AND step 3 SHALL have status "running"
- AND steps 4-9 SHALL have status "pending"

### Scenario: AI Preview Assessment (v1.0.0 新增)
- GIVEN a user uploads a project ZIP or provides a git repo URL via `POST /api/preview/assess`
- WHEN the request is valid
- THEN the system SHALL return HTTP 202 with a preview_id
- AND the system SHALL complete the analysis within 300 seconds
- AND the user SHALL poll `GET /api/preview/assess/<preview_id>` for results
- AND the final report SHALL include: coverage prediction, compliance risk analysis, and recommended pipeline config
- AND the analysis SHALL NOT execute, compile, or flash any code on hardware

- GIVEN an unauthenticated IP has submitted 3 preview assessments in 24 hours
- WHEN the 4th request arrives
- THEN the server SHALL return HTTP 429

---

## 3. 非功能性需求

- The system SHALL provide response within 5s for agent review tasks
- The system SHALL support parallel execution of independent tasks
- The system SHALL gracefully handle agent failures with retry (max 5 rounds)
- The system SHOULD maintain task execution logs for traceability
- Each SIL test SHALL have a configurable timeout with a default of 30 seconds
- The system SHALL support at least 4 concurrent QEMU instances for parallel SIL test execution
- The SIL runner SHALL gracefully handle QEMU process crashes and report them as FAIL with the crash log

### RS-010: CI 硬化与可配置化 (v0.6.0 新增)
- The system SHALL provide a per-project CI configuration file (``.yuleosh/ci-config.yaml``)
- The system SHALL support configurable coverage thresholds per project (SWR-003.2)
- The system SHALL provide a CI Layer 2.5 (Hardware-in-the-Loop) positioned between L2 and L3
- The system SHALL support mock mode for L2.5 HIL tests in CI environments without physical hardware
- The system SHALL support configurable layer dependency chain
- The system MAY support per-module coverage thresholds

#### Reason
CI 配置硬编码不利于多项目管理。可配置化支持不同项目根据成熟度设置不同的覆盖率门禁。L2.5 HIL 层补全了 CI 流水线的硬件测试阶段。

#### SWR-010.1: CI 配置文件
- The system SHALL store CI configuration in ``.yuleosh/ci-config.yaml``
- The system SHALL support sections for: ci (layers, dependencies), coverage (thresholds, strict), hardware_test (HIL settings)
- The system SHALL fall back to safe defaults when the config file is missing
- The system SHALL fall back to safe defaults with a warning when the YAML is invalid
- The system SHALL load the config once and cache it per project path

##### Reason
确定性加载策略：首次加载后缓存，避免重复解析。缺失/损坏文件降级到默认值，确保 CI 不因配置问题中断。

##### GIVEN a yuleOSH project without ci-config.yaml
##### WHEN the CI pipeline loads configuration
##### THEN all settings SHALL use defaults
##### AND L2.5 HIL SHALL default to mock mode (safe for CI)

##### GIVEN a ci-config.yaml with coverage.threshold_line = 90.0
##### WHEN the CI Layer 1 coverage check runs
##### THEN the coverage gate SHALL use 90.0% instead of the hardcoded value

#### SWR-010.2: Coverage Guardian 可配置化
- The system SHALL support ``coverage.threshold_line`` in ci-config.yaml
- The system SHALL support ``coverage.threshold_condition`` in ci-config.yaml
- The system SHALL support ``coverage.strict`` mode (fail on missing coverage tool)
- The system MAY support per-module coverage thresholds via ``coverage.module_thresholds``
- The default line coverage threshold SHALL be 85.0% for v1.0.0
- The default condition coverage threshold SHALL be 80.0% for v1.0.0

##### Reason
将覆盖阈值的控制权交还给项目。项目成熟后可逐步提升至 98%（生产目标），新项目可从 85% 起步。

##### GIVEN a project with ci-config.yaml coverage.threshold_line = 92.0
##### WHEN CI L1 coverage-check runs
##### THEN it SHALL use 92.0% as the pass/fail boundary

#### SWR-010.3: CI L2.5 硬件在环 (HIL) 层
- The system SHALL provide a ``run_layer_25()`` function as a new CI layer
- L2.5 SHALL run after L2 passes and before L3
- L2.5 SHALL support mock mode where no real hardware is required
- In mock mode, L2.5 SHALL simulate flash → boot → assert lifecycle
- In mock mode, L2.5 SHALL still discover and validate HIL test script syntax
- L2.5 SHALL accept the CLI argument ``25`` or ``2.5``
- L2.5 SHALL produce two report files:
  - ``.osh/ci/layer25-{commit}.json`` (standard CI layer result)
  - ``.osh/ci/hil-report-{commit}.json`` (HIL-specific detailed report)

##### Reason
L2.5 HIL 层补全 CI 流水线的硬件测试阶段。Mock 模式可在无硬件环境中验证 HIL 测试脚本语法与流程，真实模式连接硬件执行 flash → boot → assert 完整生命周期。分层执行保证 L1/L2 通过后才进入 L2.5，避免硬件资源无效占用。

##### GIVEN a CI pipeline run with mock mode
##### WHEN Layer 2.5 executes
##### THEN the system SHALL simulate all HIL test scripts
##### AND SHALL report all as passed (or failed based on script validation)
##### AND SHALL produce both report files

##### GIVEN a developer runs ``python3 -m ci.run 2.5``
##### WHEN the CLI processes the layer argument
##### THEN it SHALL recognize both ``25`` and ``2.5`` as valid aliases for L2.5

