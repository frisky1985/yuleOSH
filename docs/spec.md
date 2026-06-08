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

---

## 3. 非功能性需求

- The system SHALL provide response within 5s for agent review tasks
- The system SHALL support parallel execution of independent tasks
- The system SHALL gracefully handle agent failures with retry (max 5 rounds)
- The system SHOULD maintain task execution logs for traceability
